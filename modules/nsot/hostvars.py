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
    payload["secret_refs"] = sorted((host_vars.get("secrets") or {}).keys())
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


def assert_no_secret_values(text: str, hostname: str) -> None:
    """Refuse to write a resolved secret into something git will keep.

    The masking contract in one function: committed host_vars hold
    ``secret_refs`` — *names* — and the credential store holds values. A preview
    masks; a deploy resolves in memory and calls ``assert_no_mask()``. Nothing
    in between ever writes a value to disk.

    Checked structurally (no ``secrets:`` mapping) **and** by value: every
    secret this device has in the store must be absent from the text. The
    structural check alone would miss a value pasted into an unrelated field by
    a hand edit, which is exactly what the editor route makes possible.
    """
    if "\nsecrets:" in "\n" + text:
        raise SecretLeak(
            f"{hostname}: committed host_vars must not contain a 'secrets' "
            "mapping — values live in the credential store, names in secret_refs")

    from modules.credentials import list_template_secrets
    prefix = f"{hostname}:"
    for entry in list_template_secrets():
        name = entry["name"]
        if not name.startswith(prefix):
            continue
        from modules.credentials import get_template_secret
        value = get_template_secret(name)
        if value and len(value) > 3 and value in text:
            raise SecretLeak(
                f"{hostname}: the resolved value of {name} appears in the "
                "host_vars text — commit the secret_ref, never the value")


def write_committed(repo: str, host_vars: dict) -> str:
    """Write committed intent. Refuses anything carrying a resolved secret."""
    hostname = host_vars.get("hostname") or "unknown"
    text = to_yaml(host_vars)
    assert_no_secret_values(text, hostname)
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
