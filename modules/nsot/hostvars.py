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


def _safe_hostname(hostname: str) -> str:
    """The on-disk form of a device name. **One producer.**

    It was inline in `committed_path()`, which was fine while that was the
    only reader. `committed_at_head()` reads the same file out of git and
    needs the identical spelling — a second copy of this mapping is how the
    working-tree reader and the git reader come to disagree about which file
    they are talking about, which is the class of defect this whole change is
    correcting.
    """
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in hostname)


def committed_path(repo: str, hostname: str) -> str:
    return os.path.join(committed_dir(repo), f"{_safe_hostname(hostname)}.yml")


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


def list_name_for_repo(repo: str) -> str:
    """The device list a repo belongs to: ``data/lists/<slug>/config_repo``.

    Derived, not passed. A ``list_name`` parameter alongside a ``repo`` argument
    is two sources for one answer, and the audit found exactly that shape in
    ``restore.build_targets()`` — repo from the argument, inventory from a
    global. The repo path is already threaded everywhere and cannot disagree
    with the repo being written to.
    """
    return os.path.basename(os.path.dirname(os.path.abspath(repo)))


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

    from modules.credentials import (get_template_secret, list_template_secrets,
                                     split_template_secret_key)

    # EVERY list's secrets, narrowed only by device. This is a leak guard, and
    # narrowing it by list would make a wrong list derivation silently check
    # nothing — a guard that fails open. Scanning wider costs a few string
    # searches and cannot produce a false negative; the device narrowing is
    # pre-existing and deliberate (see the docstring).
    for entry in list_template_secrets():
        name = entry["name"]
        if split_template_secret_key(name)[1] != hostname:
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


# ---------------------------------------------------------------------------
# The authoring schema: what a hand-written interface may omit, and what it
# may not misspell
# ---------------------------------------------------------------------------

#: Every key the interface macro reads, with the value that means "absent".
#:
#: **The template renders under `StrictUndefined`**, so a dict lacking any of
#: these raises `UndefinedError: 'dict object' has no attribute
#: 'no_switchport'` — for a key the author has never heard of and that does
#: nothing. A parser always emits all thirty, so every render this project had
#: ever done was fed a complete dict and the authoring path was the first to
#: meet it. That is the shortest distance between *"this tool lets you write
#: configuration"* and *"this tool doesn't"*.
#:
#: Filling an absent key with its falsy default changes **no output**: the
#: macro's `{% if i.x %}` emits nothing either way. `test_authoring_schema.py`
#: pins that against the whole fleet, and pins this set equal to what the
#: parsers actually emit — a second copy of a key list is how the two come to
#: disagree.
INTERFACE_DEFAULTS = {
    "name": "", "description": "", "ipv4": "", "vrf": "", "mtu": "",
    "negotiation": "", "encapsulation": "", "channel_group": "",
    "switchport_mode": "", "switchport_access_vlan": "",
    "switchport_trunk_encapsulation": "",
    "no_switchport": False, "shutdown": False, "no_shutdown": False,
    "ipv6_enable": False, "no_ip_address": False,
    "ipv6": [], "ipv6_nd": [], "ospf": [], "ospfv3": [], "ripng": [],
    "vrrp": [], "vrrp_groups": [], "mop": [], "ip_nat": [], "switchport": [],
    "switchport_trunk_vlans": [], "helper_addresses": [], "dhcpv6_relay": [],
    "unmodeled": [],
}


def complete_interfaces(host_vars: dict) -> dict:
    """*host_vars* with every absent interface key filled with its default.

    Returns a **copy**; the caller's document is never mutated, because the
    committed file is the record and a render must not edit it.
    """
    if not isinstance(host_vars, dict):
        return host_vars
    interfaces = host_vars.get("interfaces")
    if not isinstance(interfaces, list):
        return host_vars
    filled = []
    for entry in interfaces:
        if not isinstance(entry, dict):
            filled.append(entry)
            continue
        merged = {key: (list(value) if isinstance(value, list) else value)
                  for key, value in INTERFACE_DEFAULTS.items()}
        merged.update(entry)
        filled.append(merged)
    return {**host_vars, "interfaces": filled}


def unknown_interface_keys(host_vars: dict) -> list:
    """``[(index, key)]`` for interface keys nothing reads.

    **The opposite half of the same problem, and the silent one.**
    `StrictUndefined` catches a *missing* key and can never catch a
    *misspelled* one: `descripton` is simply never read, the line does not
    render, and nothing says a word. That is the failure a human author
    actually has — and before this, the noisy half fired on the keys they were
    right to omit while the quiet half said nothing about the key they got
    wrong.
    """
    found = []
    for index, entry in enumerate(host_vars.get("interfaces") or []):
        if not isinstance(entry, dict):
            continue
        for key in entry:
            if key not in INTERFACE_DEFAULTS:
                found.append((index, key))
    return found


#: `vs_intent` answers *"what does my edit change"*, and "what is committed"
#: has to mean **committed**. See :func:`committed_at_head`.
NEVER_COMMITTED = "never_committed"
COMMITTED = "committed"


def committed_at_head(repo: str, hostname: str) -> tuple:
    """``(text | None, state)`` — committed intent read from **git**, not disk.

    `read_committed()` opens the working file, which is correct for *"what
    would deploy"* and wrong for *"what is committed"*. The two are the same
    bytes only while nobody edits the file directly — and editing it directly
    is how a person actually works. Measured: with the file edited in place,
    the editor's `vs_intent` compared the edit against itself and was empty by
    construction, and `document_changed`, added precisely to disambiguate an
    empty diff, read the **same** working file and was fooled by the same
    cause. Two signals that look independent, sharing one source, so their
    agreement carried no information.

    Reads through :class:`repo.RefSource` with `host_vars/` declared, so the
    capability is bounded at the call site rather than by this function being
    careful.

    **Three states, not two.** `None` with :data:`NEVER_COMMITTED` is a
    different fact from committed-and-identical, and both currently render as
    an empty diff — the absent-versus-empty distinction that erased the
    settings file, arriving in the editor.
    """
    from modules.nsot.repo import RefSource

    source = RefSource(repo, "HEAD", allow=("host_vars/",))
    raw = source.read(f"{COMMITTED_REL}/{_safe_hostname(hostname)}.yml")
    if raw is None:
        return None, NEVER_COMMITTED
    return raw, COMMITTED


def intent_gap_note(repo: str, hostname: str) -> dict:
    """What the editor SAYS for a device with no committed intent.

    A state the payload carries and the screen does not name is the defect the
    state was added to prevent. And the same absence means opposite things:
    **mid-onboarding it is normal and expected**; for a device that has been
    in the fleet for weeks it is a gap — nothing has ever declared what that
    device should look like, so it is `bootstrap` and not deployable.
    """
    try:
        from modules.nsot import manifest as _m

        entry = _m.find_by_name(repo, hostname)[1] or {}
    except Exception:                          # noqa: BLE001
        entry = {}
    # PENDING IS DERIVED, NOT STORED. The manifest has no `pending` key --
    # `upsert_device(pending=True)` writes `onboarded_at` and leaves
    # `verified_at` None, and `manifest.pending_devices()` is the one place
    # that reads the pair. The first version of this function read
    # `entry["pending"]`, a field nothing writes, so every device answered
    # "not pending" and the mid-onboarding case was unreachable -- a field
    # declared and never written, which is the `next_ts` shape.
    is_pending = bool(entry.get("onboarded_at")) and not entry.get("verified_at")
    if is_pending:
        return {"severity": "info", "pending": True,
                "note": (f"{hostname} has no committed intent yet. It is "
                         "mid-onboarding, which is the normal state here — "
                         "intent is written once the device has been reached "
                         "and captured.")}
    since = entry.get("onboarded_at") or ""
    return {"severity": "warning", "pending": False, "onboarded_at": since,
            "note": (f"{hostname} has **no committed intent**"
                     + (f" and has been in the fleet since {since[:10]}"
                        if since else "")
                     + ". Nothing has ever declared what this device should "
                       "look like, so it is 'bootstrap' and cannot be "
                       "deployed. Seed it from its own capture (Extract, "
                       "review, Commit) and the next edit becomes a diff.")}


class PartialSyslogBlock(ValueError):
    """Committed intent carrying some of the syslog block and not the rest."""


#: The parts of the syslog block (NSOT_PLAN P.1), each with what it is for,
#: because a refusal that names a field without its purpose is one a reader
#: satisfies with any value.
SYSLOG_PARTS = {
    "trap": "the severity that leaves the device",
    "origin_id": "puts the hostname in every line, which the alert keys on",
    "source_interface": "the address the lines come from",
    "hosts": "where they go",
    "heartbeat": "the EEM interval that makes silence detectable",
}

#: Lines in `logging.settings` / `logging.hosts` that the block owns.
_SYSLOG_OWNED = {"trap": "trap ", "origin_id": "origin-id ",
                 "source_interface": "source-interface "}


def syslog_block_problems(host_vars: dict) -> list:
    """Why this intent's syslog block may not be committed; ``[]`` if it may.

    **One block, whole or absent.** Heartbeat, trap level, origin-id, source
    interface and hosts are one unit: a heartbeat with no host is silence
    nobody receives, and a host with no heartbeat is the pre-P.1 state in
    which "no lines" could not be told from "nothing happening". Absent is
    fine -- intent that predates P.1 is untouched -- and a partial block is
    refused with each missing part named.

    Also refused: the same fact in two places. A trap level in both
    ``logging.settings`` and the block renders twice, the device keeps the
    last, and the reader cannot tell which one is meant.
    """
    logging_ = (host_vars or {}).get("logging") or {}
    block = logging_.get("syslog")
    if not block:
        return []
    problems = []
    for part, purpose in SYSLOG_PARTS.items():
        value = block.get(part)
        missing = (not value) if part != "heartbeat" else not (
            isinstance(value, int) and value > 0)
        if missing:
            problems.append(f"syslog block has no {part} ({purpose})")
    for part, prefix in _SYSLOG_OWNED.items():
        if any(str(s).startswith(prefix) for s in logging_.get("settings") or []):
            problems.append(f"{part} is set in logging.settings as well as in "
                            "the syslog block -- one owner per fact")
    if logging_.get("hosts"):
        problems.append("logging.hosts is set as well as syslog.hosts -- one "
                        "owner per fact")
    return problems


def write_committed(repo: str, host_vars: dict) -> str:
    """Write committed intent. Refuses anything carrying a resolved secret.

    **Does not judge the syslog block**, deliberately. This path takes
    EXTRACTED intent -- a device parsed as it is -- and a pre-P.1 device
    genuinely holds a partial block; refusing it would refuse to record a
    true fact, and blocked Extract -> Commit for every device in the fleet
    when it was tried. Whole-or-absent is a rule about AUTHORED intent, so it
    is enforced where intent is authored: `write_committed_text()` and the
    editor's gate. Onboarding's block is complete by construction
    (`onboard.syslog_baseline()` runs the same check before building one).
    """
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
    problems = syslog_block_problems(parsed)
    if problems:
        raise PartialSyslogBlock(f"{hostname}: " + "; ".join(problems))
    assert_no_secret_values(text, hostname)
    path = committed_path(repo, hostname)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text if text.endswith("\n") else text + "\n")
    return path


# ---------------------------------------------------------------------------
# Rolled-back intent
# ---------------------------------------------------------------------------

ROLLED_BACK_REL = os.path.join(".nsot", "rolled_back.json")


def _rolled_back_path(repo: str) -> str:
    return os.path.join(repo, ROLLED_BACK_REL)


def _load_rolled_back(repo: str) -> dict:
    try:
        import json
        with open(_rolled_back_path(repo), encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def record_rolled_back(repo: str, hostname: str, intent_commit: str,
                       reason: str = "", pipeline_id: str = "",
                       commands: list = None) -> dict:
    """Note that deploying this device's current intent was rolled back.

    Rollback restores the *device*. It says nothing about the *intent*, which
    still asserts the change should be there — so the next plan computes the
    same diff and offers to push the thing that just failed verification. The
    tool would loop, confidently, and each attempt would look like a fresh
    proposal.

    Keyed on **the command program that failed**, which is the only thing that
    answers the question the note asks. Two weaker keys were tried first and
    both lift the block while the failing change is still in intent:

    * the intent **commit sha** — any later commit clears it, including one
      that does not touch the rolled-back setting at all
    * a **content hash of the whole host_vars document** — editing an unrelated
      field changes the hash, so the same ``shutdown`` is offered again

    The test is **containment**, not equality: the block stands while the failed
    lines are still among the lines that would be sent. Equality lifts whenever
    the program merely grows — an unrelated edit that adds its own sent line
    bundles the failed change back out with it.

    Lifting is therefore only ever "the failed change is genuinely absent". A
    deliberate retry is :func:`authorise_retry`, an explicit recorded action,
    never a side effect of editing something else.

    Local operational state, like the migration marker — gitignored. The
    version-controlled record of what happened is the intent history itself.
    """
    import json
    import time as _time

    from modules.nsot.deploy import command_fingerprint

    commands = list(commands or [])
    data = _load_rolled_back(repo)
    entry = {
        "intent_commit": intent_commit,
        "commands": commands,
        "command_fingerprint": command_fingerprint(commands) if commands else "",
        "at": _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime()),
        "reason": reason,
        "pipeline_id": pipeline_id,
    }
    data[hostname] = entry
    os.makedirs(os.path.dirname(_rolled_back_path(repo)), exist_ok=True)
    with open(_rolled_back_path(repo), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
        fh.write("\n")
    log.warning("hostvars: %s intent %s is marked rolled back — %s",
                hostname, intent_commit[:8], reason or "no reason given")
    return entry


def rolled_back_note(repo: str, hostname: str, current_commands: list = None):
    """The standing note for *hostname*, or ``None``.

    *current_commands* is the program a fresh plan would send. The note stands
    while that program matches the one that failed, and lifts when it does not
    — an unrelated edit leaves the program identical and therefore leaves the
    block in place, which is the whole point.

    Called without *current_commands* it reports the raw note, for listing.
    A note with no recorded program falls back to the commit sha rather than
    being silently ignored.
    """
    entry = _load_rolled_back(repo).get(hostname)
    if not entry:
        return None
    if current_commands is None:
        return entry

    failed = entry.get("commands")
    if failed:
        from modules.nsot.deploy import program_contains
        return entry if program_contains(list(current_commands), failed) else None

    current = intent_commits(repo, hostname, limit=1)
    current_sha = current[0]["sha"] if current else ""
    if current_sha and current_sha != entry.get("intent_commit"):
        return None
    return entry


# ---------------------------------------------------------------------------
# Targeted revert
# ---------------------------------------------------------------------------

_MISSING = object()


def _walk(doc, path=()):
    """``{path: leaf}`` for a host_vars document.

    A list whose items all carry a ``name`` is keyed by that name rather than
    by index, so ``interfaces`` survives insertion and reordering: the path to
    Gi0/1's description stays the same when Gi0/2 gains one. Any other list is
    a single leaf, because nothing identifies its items.
    """
    if isinstance(doc, dict):
        out = {}
        for key, value in doc.items():
            out.update(_walk(value, path + (key,)))
        return out
    if isinstance(doc, list) and doc and all(
            isinstance(i, dict) and i.get("name") for i in doc):
        out = {}
        for item in doc:
            out.update(_walk(item, path + (item["name"],)))
        return out
    return {path: doc}


def _set_path(doc, path, value):
    """Set *path* in *doc*, mirroring :func:`_walk`'s keying. Deletes on _MISSING."""
    node = doc
    for index, key in enumerate(path[:-1]):
        if isinstance(node, dict):
            if key not in node:
                return False
            node = node[key]
        elif isinstance(node, list):
            match = next((i for i in node
                          if isinstance(i, dict) and i.get("name") == key), None)
            if match is None:
                return False
            node = match
        else:
            return False

    leaf = path[-1]
    if isinstance(node, dict):
        if value is _MISSING:
            node.pop(leaf, None)
        else:
            node[leaf] = value
        return True
    if isinstance(node, list):
        match = next((i for i in node
                      if isinstance(i, dict) and i.get("name") == leaf), None)
        if match is None:
            return False
        return True
    return False


class RevertConflict(ValueError):
    """A later commit changed the same lines this revert would undo."""


def revert_intent_change(repo: str, hostname: str, sha: str = "") -> dict:
    """Undo one intent commit's change, keeping every later one.

    Restoring the previous *snapshot* is the obvious implementation and it is
    wrong as soon as the commit to undo is not at HEAD. With

    ``A`` shutdown Gi0/1 (rolled back) then ``B`` describe Gi0/2 (unrelated),
    restoring "the previous committed intent" either restores ``A`` — which
    still contains the shutdown — or walks back past it and silently discards
    ``B``. Neither is a revert of ``A``.

    This applies the inverse of ``A``'s own diff onto current intent: every
    path ``A`` changed goes back to what it was *before* ``A``, and nothing
    else is touched. A path that a later commit also changed is a genuine
    conflict and is **refused with the paths named**, because guessing which
    edit wins is the operator's call.
    """
    commits = intent_commits(repo, hostname, limit=50)
    if not commits:
        return {"ok": False, "error": f"'{hostname}' has no committed intent."}

    target = sha or commits[0]["sha"]
    position = next((i for i, c in enumerate(commits)
                     if c["sha"].startswith(target)), None)
    if position is None:
        return {"ok": False,
                "error": f"{target[:8]} is not an intent commit for {hostname}"}
    target = commits[position]["sha"]

    if position + 1 >= len(commits):
        return {"ok": False, "error": (
            f"{target[:8]} is the first intent commit for '{hostname}', so "
            "there is no earlier state for its change to be undone to. Edit "
            "the intent instead.")}

    before = committed_at(repo, hostname, commits[position + 1]["sha"])
    after = committed_at(repo, hostname, target)
    current = read_committed(repo, hostname)
    if before is None or after is None or current is None:
        return {"ok": False, "error": "could not read intent around that commit"}

    flat_before, flat_after = _walk(before), _walk(after)
    flat_current = _walk(current)

    changed = [p for p in set(flat_before) | set(flat_after)
               if flat_before.get(p, _MISSING) != flat_after.get(p, _MISSING)]
    if not changed:
        return {"ok": False,
                "error": f"{target[:8]} changed nothing to undo"}

    conflicts = [p for p in changed
                 if flat_current.get(p, _MISSING) != flat_after.get(p, _MISSING)]
    if conflicts:
        named = ", ".join(".".join(str(part) for part in p)
                          for p in sorted(conflicts)[:5])
        raise RevertConflict(
            f"refusing to revert {target[:8]}: a later commit changed the same "
            f"setting(s) — {named}. Decide which edit should win and make that "
            "edit explicitly.")

    reverted = []
    for path in sorted(changed):
        if _set_path(current, path, flat_before.get(path, _MISSING)):
            reverted.append(".".join(str(part) for part in path))

    write_committed(repo, current)
    return {"ok": True, "target": target, "reverted_paths": reverted,
            "kept_later_commits": [c["sha"] for c in commits[:position]]}


RETRY_LOG_REL = os.path.join(".nsot", "retry_log.json")


def authorise_retry(repo: str, hostname: str, actor: str = "user",
                    reason: str = "") -> dict:
    """Deliberately allow a rolled-back change to be attempted again.

    The only way a block lifts while the failed change is still in intent. It
    is an action someone takes and it is recorded, because "we tried this, it
    was rolled back, and we chose to try it again" is exactly the sequence an
    audit needs to see — and exactly the sequence that disappears if a retry is
    a side effect of an unrelated edit.
    """
    import json
    import time as _time

    note = _load_rolled_back(repo).get(hostname)
    if not note:
        return {"ok": False, "error": f"'{hostname}' has no rolled-back note"}

    path = os.path.join(repo, RETRY_LOG_REL)
    try:
        with open(path, encoding="utf-8") as fh:
            log_entries = json.load(fh)
    except (OSError, ValueError):
        log_entries = []
    if not isinstance(log_entries, list):
        log_entries = []

    record = {"device": hostname, "actor": actor, "reason": reason,
              "at": _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime()),
              "note": note}
    log_entries.append(record)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(log_entries, fh, indent=2, sort_keys=True)
        fh.write("\n")

    clear_rolled_back(repo, hostname)
    log.warning("hostvars: retry of a rolled-back change authorised for %s by "
                "%s — %s", hostname, actor, reason or "no reason given")
    return {"ok": True, "device": hostname, "record": record}


def retry_log(repo: str) -> list:
    """Every authorised retry, newest last."""
    import json

    try:
        with open(os.path.join(repo, RETRY_LOG_REL), encoding="utf-8") as fh:
            entries = json.load(fh)
    except (OSError, ValueError):
        return []
    return entries if isinstance(entries, list) else []


def clear_rolled_back(repo: str, hostname: str) -> bool:
    """Drop the note — used when the intent is reverted or overridden."""
    import json

    data = _load_rolled_back(repo)
    if hostname not in data:
        return False
    data.pop(hostname)
    with open(_rolled_back_path(repo), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return True


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


def hydrate_secrets(host_vars: dict, hostname: str,
                    list_name: str = "") -> dict:
    """Return a copy with ``secrets`` resolved from the credential store.

    **In memory only.** The result must never be written anywhere — it is the
    deploy-time render input, and ``assert_no_mask()`` guards the other end.
    Committed intent carries ``secret_refs``; this is where names become values,
    once, as late as possible.
    """
    from modules.credentials import get_template_secret, template_secret_key

    refs = host_vars.get("secret_refs") or sorted(
        (host_vars.get("secrets") or {}).keys())
    secrets = {}
    for ref in refs:
        value = get_template_secret(template_secret_key(list_name, hostname, ref))
        if value:
            secrets[ref] = value
        else:
            log.warning("hostvars: %s references secret %r with no stored value "
                        "in list %r", hostname, ref, list_name)
    return {**host_vars, "secrets": secrets}


def store_secrets(host_vars: dict, hostname: str, dry_run: bool = True,
                  list_name: str = "") -> dict:
    """Move extracted secret values into the credential store.

    Returns what was moved — names only, never values. With *dry_run* (the
    Phase 3a default) nothing is written; the report just says what would move.

    *list_name* scopes the key. It is required in practice: without it the key
    is built unscoped and two networks' devices of the same name collide.
    """
    from modules.credentials import template_secret_key

    secrets = host_vars.get("secrets") or {}
    moved = []
    for ref, value in sorted(secrets.items()):
        kind = "hash" if _looks_hashed(value) else "plaintext"
        key = template_secret_key(list_name, hostname, ref)
        moved.append({"ref": key, "kind": kind})
        if not dry_run:
            from modules.credentials import set_template_secret
            set_template_secret(key, value, secret_kind=kind, list_name=list_name)
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
