"""nsot/hostvars.py

Reading and writing extracted ``host_vars`` YAML.

Two stores, and the distinction is the whole point.

``config_repo/.nsot/staging/host_vars/<device>.yml`` is **gitignored scratch**:
what the extractor read off a captured config. It is a proposal.

``config_repo/host_vars/<device>.yml`` is **committed intent**: what the network
is supposed to look like, reviewed by a person and recorded in git. This is the
only intent source on the deploy path.

Deriving intent by parsing the device's current configuration makes intent a
function of current state, which guarantees an empty diff by construction — the
same error as comparing a masked render against itself. Both sides come from
one source, so the comparison cannot say anything. A device with no committed
intent has nothing to deploy *toward*, and is marked ``bootstrap`` and not
deployable rather than having its status quo treated as its goal.

Secrets never appear in YAML. The extractor replaces every secret value with a
``secret_ref`` and hands the value to the credential store. For a hashed secret
the *value is the hash string* — ``9 $9$…`` carries a per-hash salt and cannot
be regenerated, so the store holds it verbatim and the template emits it
verbatim. Storing plaintext there would make those lines fail every round trip,
permanently.
"""

import logging
import os

log = logging.getLogger(__name__)

STAGING_REL = os.path.join(".nsot", "staging", "host_vars")

#: Committed intent, version-controlled. Never gitignored.
COMMITTED_REL = "host_vars"


class SecretLeak(ValueError):
    """A resolved secret value reached something that gets committed."""


class NonPrintableContent(ValueError):
    """Committed intent contains a character an IOS CLI cannot accept."""

#: Secret kinds that must be emitted verbatim and never re-derived.
HASH_KINDS = ("secret", "password")


def staging_dir(repo: str) -> str:
    path = os.path.join(repo, STAGING_REL)
    os.makedirs(path, exist_ok=True)
    return path


def staging_path(repo: str, hostname: str) -> str:
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in hostname)
    return os.path.join(staging_dir(repo), f"{safe}.yml")


def to_yaml(host_vars: dict) -> str:
    """Serialise host_vars deterministically, with secrets removed.

    ``sort_keys=True`` matters: the fixed-point test requires that extracting
    twice produces byte-identical YAML, and dict ordering would otherwise make
    that depend on insertion order.
    """
    import yaml

    payload = {k: v for k, v in host_vars.items() if k != "secrets"}
    # `lineno` points into the source document, not the model. Rendering moves
    # lines around, so keeping it would break the fixed-point property for a
    # reason that has nothing to do with what was extracted.
    payload["unmodeled"] = [
        {k: v for k, v in entry.items() if k != "lineno"}
        for entry in host_vars.get("unmodeled", [])
    ]
    # Idempotent over its own output. ``secrets`` is stripped on the way out,
    # so recomputing the refs from it on a second pass yielded an empty list
    # and silently destroyed them: to_yaml(from_yaml(to_yaml(x))) lost every
    # secret_ref. The existing fixed-point test could not see this — it runs
    # parse → render → parse, and both of those inputs come from the parser
    # and therefore always carry ``secrets``. The serialiser's own round trip
    # was never exercised.
    if "secrets" in host_vars:
        payload["secret_refs"] = sorted((host_vars.get("secrets") or {}).keys())
    else:
        payload["secret_refs"] = sorted(host_vars.get("secret_refs") or [])
    return yaml.safe_dump(payload, sort_keys=True, default_flow_style=False,
                          allow_unicode=True, width=10000)


def from_yaml(text: str) -> dict:
    import yaml
    return yaml.safe_load(text) or {}


def write_staged(repo: str, host_vars: dict) -> str:
    """Write an extraction to the staging area. Nothing is committed."""
    hostname = host_vars.get("hostname") or "unknown"
    path = staging_path(repo, hostname)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(to_yaml(host_vars))
    log.info("hostvars: staged %s (not committed)", path)
    return path


def read_staged(repo: str, hostname: str):
    path = staging_path(repo, hostname)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return from_yaml(fh.read())


def list_staged(repo: str) -> list:
    directory = os.path.join(repo, STAGING_REL)
    if not os.path.isdir(directory):
        return []
    return sorted(f[:-4] for f in os.listdir(directory) if f.endswith(".yml"))


# ---------------------------------------------------------------------------
# Committed intent
# ---------------------------------------------------------------------------

def committed_dir(repo: str) -> str:
    path = os.path.join(repo, COMMITTED_REL)
    os.makedirs(path, exist_ok=True)
    return path


def committed_path(repo: str, hostname: str) -> str:
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in hostname)
    return os.path.join(committed_dir(repo), f"{safe}.yml")


def read_committed(repo: str, hostname: str):
    """Committed intent for *hostname*, or ``None`` if it has none.

    ``None`` is meaningful and must not be papered over: it means nobody has
    said what this device is supposed to look like.
    """
    path = committed_path(repo, hostname)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return from_yaml(fh.read())


def list_committed(repo: str) -> list:
    directory = os.path.join(repo, COMMITTED_REL)
    if not os.path.isdir(directory):
        return []
    return sorted(f[:-4] for f in os.listdir(directory) if f.endswith(".yml"))


#: Below this, a stored value cannot be distinguished from ordinary config
#: text and value-checking it would refuse legitimate commits. ``admin`` is the
#: worked example: stored as a value it would trip on
#: ``username admin privilege 15``, and a false refusal blocks the entire
#: intent path behind an error that looks like a security incident.
MIN_CHECKABLE_SECRET = 8

#: Characters that continue a token. A match flanked by one of these is part of
#: a longer string and is not the secret — ``Secret12`` inside ``Secret123456``
#: is a different value, not a leak.
_TOKEN_CHAR = r"[A-Za-z0-9_]"


def _locate(text: str, value: str):
    """``(lineno, field)`` where *value* appears as a whole token, or ``None``."""
    import re

    pattern = re.compile(f"(?<!{_TOKEN_CHAR})" + re.escape(value)
                         + f"(?!{_TOKEN_CHAR})")
    for lineno, line in enumerate(text.splitlines(), 1):
        if not pattern.search(line):
            continue
        head = line.split(":", 1)[0].strip().lstrip("-").strip()
        return lineno, (head or "(list item)")
    return None


def assert_no_secret_values(text: str, hostname: str) -> None:
    """Refuse to write a resolved secret into something git will keep.

    The masking contract in one function: committed host_vars hold
    ``secret_refs`` — *names* — and the credential store holds values. A preview
    masks; a deploy resolves in memory and calls ``assert_no_mask()``. Nothing
    in between ever writes a value to disk.

    Checked structurally (no ``secrets:`` mapping) **and** by value, because the
    structural check alone would miss a value pasted into an unrelated field by
    a hand edit — exactly what the editor route makes possible.

    The value check is **deliberately incomplete**, and saying so matters more
    than the check. It skips anything shorter than
    :data:`MIN_CHECKABLE_SECRET` and requires a whole-token match, because a
    short stored value is indistinguishable from ordinary configuration text:
    a stored ``admin`` would refuse ``username admin privilege 15`` and take
    the whole intent path down behind an error that reads like a breach. Short
    secrets are covered by the structural refusal and by the extractor
    substituting refs at extraction time; they are not covered here, and
    pretending otherwise would be worse than the gap.
    """
    if "\nsecrets:" in "\n" + text:
        raise SecretLeak(
            f"{hostname}: committed host_vars must not contain a 'secrets' "
            "mapping — values live in the credential store, names in secret_refs")

    from modules.credentials import get_template_secret, list_template_secrets

    prefix = f"{hostname}:"
    for entry in list_template_secrets():
        name = entry["name"]
        if not name.startswith(prefix):
            continue
        value = get_template_secret(name)
        if not value or len(value) < MIN_CHECKABLE_SECRET:
            if value:
                log.debug("hostvars: %s is shorter than %d characters — not "
                          "value-checked", name, MIN_CHECKABLE_SECRET)
            continue
        found = _locate(text, value)
        if found:
            lineno, field = found
            raise SecretLeak(
                f"{hostname}: the resolved value of secret '{name}' appears on "
                f"line {lineno}, in field '{field}'. Commit the secret_ref "
                f"('{name.split(':', 1)[1]}') instead — the value belongs in "
                "the credential store.")


def assert_printable(text: str, hostname: str) -> None:
    """Refuse intent containing anything an IOS CLI cannot accept.

    The first boundary. Catching it here means the character never reaches a
    plan, so nobody confirms a command list that cannot be sent. The deploy
    path checks again before connecting — this is a value an operator types,
    and a guard on typed input belongs where the typing happens *and* where the
    sending happens.
    """
    from modules.nsot import normalize

    found = normalize.find_non_printable(text.replace("\n", ""))
    if found:
        raise NonPrintableContent(
            f"{hostname}: host_vars contains {len(found)} character(s) an IOS "
            f"CLI cannot accept — {normalize.describe_non_printable(found)}. "
            "Use printable ASCII (0x20-0x7E); an em dash or a smart quote "
            "desynchronises the device's line parser and truncates the command.")


def write_committed(repo: str, host_vars: dict) -> str:
    """Write committed intent. Refuses anything carrying a resolved secret."""
    hostname = host_vars.get("hostname") or "unknown"
    text = to_yaml(host_vars)
    assert_no_secret_values(text, hostname)
    assert_printable(text, hostname)
    path = committed_path(repo, hostname)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    log.info("hostvars: committed intent written for %s", hostname)
    return path


def write_committed_text(repo: str, hostname: str, text: str) -> str:
    """Write edited YAML verbatim, after the same refusal.

    The editor path. Round-tripping through ``from_yaml``/``to_yaml`` would
    silently discard anything the model does not know about, so the operator's
    text is kept as written — which is also why the value-level leak check
    matters here and not only structurally.
    """
    assert_printable(text, hostname)
    parsed = from_yaml(text)
    if not isinstance(parsed, dict):
        raise ValueError("host_vars must be a YAML mapping")
    if (parsed.get("hostname") or hostname) != hostname:
        raise ValueError(
            f"hostname in the document ({parsed.get('hostname')!r}) does not "
            f"match {hostname!r} — a host_vars file names its own device")
    assert_no_secret_values(text, hostname)
    path = committed_path(repo, hostname)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text if text.endswith("\n") else text + "\n")
    return path


def intent_commits(repo: str, hostname: str, limit: int = 20) -> list:
    """Commits that changed this device's committed intent, newest first."""
    from modules.nsot.repo import git

    rel = os.path.join(COMMITTED_REL, os.path.basename(committed_path(repo, hostname)))
    rc, out, _ = git(repo, "log", f"-{limit}", "--format=%H\x1f%s\x1f%aI",
                     "--", rel)
    if rc != 0 or not out:
        return []
    entries = []
    for line in out.splitlines():
        parts = line.split("\x1f")
        if len(parts) == 3:
            entries.append({"sha": parts[0], "subject": parts[1], "date": parts[2]})
    return entries


def committed_at(repo: str, hostname: str, ref: str):
    """This device's committed intent as of *ref*, or ``None``."""
    from modules.nsot.repo import git

    rel = os.path.join(COMMITTED_REL, os.path.basename(committed_path(repo, hostname)))
    rc, out, _ = git(repo, "show", f"{ref}:{rel}")
    if rc != 0 or not out.strip():
        return None
    return from_yaml(out)


def intent_change(repo: str, hostname: str) -> dict:
    """The most recent intent commit and the YAML diff it introduced.

    What a reviewer needs to answer "is this push mine?". The deploy is
    merge-only, so it pushes every line the render has and the device lacks —
    not only the line the operator changed. Anything that drifted on the device
    since the capture rides along in the same push unless it is visible first.
    """
    from modules.nsot.repo import git

    rel = os.path.join(COMMITTED_REL, os.path.basename(committed_path(repo, hostname)))
    commits = intent_commits(repo, hostname, limit=2)
    if not commits:
        return {"sha": "", "subject": "", "diff": "", "previous_sha": ""}

    latest = commits[0]
    previous = commits[1]["sha"] if len(commits) > 1 else ""
    rc, diff, _ = git(repo, "show", "--format=", "--unified=1", latest["sha"],
                      "--", rel)
    return {"sha": latest["sha"], "subject": latest["subject"],
            "date": latest["date"], "previous_sha": previous,
            "diff": diff if rc == 0 else ""}


def hydrate_secrets(host_vars: dict, hostname: str) -> dict:
    """Return a copy with ``secrets`` resolved from the credential store.

    **In memory only.** The result must never be written anywhere — it is the
    deploy-time render input, and ``assert_no_mask()`` guards the other end.
    Committed intent carries ``secret_refs``; this is where names become values,
    once, as late as possible.
    """
    from modules.credentials import get_template_secret

    refs = host_vars.get("secret_refs") or sorted(
        (host_vars.get("secrets") or {}).keys())
    secrets = {}
    for ref in refs:
        value = get_template_secret(f"{hostname}:{ref}")
        if value:
            secrets[ref] = value
        else:
            log.warning("hostvars: %s references secret %r with no stored value",
                        hostname, ref)
    return {**host_vars, "secrets": secrets}


def store_secrets(host_vars: dict, hostname: str, dry_run: bool = True) -> dict:
    """Move extracted secret values into the credential store.

    Returns what was moved — names only, never values. With *dry_run* (the
    Phase 3a default) nothing is written; the report just says what would move.
    """
    secrets = host_vars.get("secrets") or {}
    moved = []
    for ref, value in sorted(secrets.items()):
        kind = "hash" if _looks_hashed(value) else "plaintext"
        moved.append({"ref": f"{hostname}:{ref}", "kind": kind})
        if not dry_run:
            from modules.credentials import set_template_secret
            set_template_secret(f"{hostname}:{ref}", value, secret_kind=kind)
    return {"moved": moved, "dry_run": dry_run, "count": len(moved)}


def _looks_hashed(value: str) -> bool:
    """True for an IOS password hash, which must be emitted verbatim.

    Type 5 (``$1$``), type 8 (``$8$``), type 9 (``$9$``), and the numeric
    ``<type> <hash>`` form all carry salts that cannot be regenerated.
    """
    text = (value or "").strip()
    if text.startswith(("$1$", "$5$", "$8$", "$9$")):
        return True
    parts = text.split(None, 1)
    return len(parts) == 2 and parts[0] in ("5", "7", "8", "9")
