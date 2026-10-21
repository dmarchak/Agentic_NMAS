"""What each lab startup file is built FROM (plan item 4, the operator's
decision, 2026-10-01).

The lab's startup sync wrote each device's startup file from Oxidized's last copy, so
a redeploy booted whatever the device last ran, approved or not, and one
device's unapproved change held every file back (C306, C309). The source is
now the list's **newest EARNED baseline**: a moment the tool recorded every
device at its committed intent (7.2's `Baseline: earned`), never a withdrawn
one (C177), never a deleted tag, never one taken before baselines recorded
what they earned. (Oxidized's copy was the cross-check until Phase 3 retired
Oxidized; the lab startup check reads each file against the record.)

**Credentials always from the CURRENT state** (C309). A baseline is a record
of a moment, and moments contain credentials (C75): one older than a rotation
holds the password the rotation retired, and a redeploy from it would lock
the tool out. So every credential family below is taken from the device's
current committed golden, as a block, where the baseline's first line of that
family sat (appended before `end` when the baseline had none); the baseline's
own lines of that family are dropped. A family the current golden lacks is
dropped too: the current state wins in both directions.

A device the baseline does not hold (onboarded since) is REFUSED for that
device, naming the baseline, never filled from another source: the sync
writes every device it can and names the rest.
"""

import logging
import re

log = logging.getLogger(__name__)

#: Top-level credential families, each replaced as a block from the current
#: golden. `username` and `enable` can lock the tool out; a community is how
#: the monitoring reads the device.
FAMILIES = (
    ("accounts", re.compile(r"^username\s")),
    ("enable", re.compile(r"^enable\s+(secret|password)\b")),
    ("SNMP communities", re.compile(r"^snmp-server community\s")),
)


def newest_earned(repo: str) -> dict:
    """The newest baseline that EARNED its tag, or ``{}``: not withdrawn, not
    deleted, its commit recording ``Baseline: earned``."""
    from modules.nsot.repo import list_baselines

    for b in list_baselines(repo):
        if not b.get("deleted") and not b.get("withdrawn") and b.get("decision") == "earned":
            return b
    return {}


def _family(line: str) -> str:
    return next((name for name, rx in FAMILIES if rx.match(line)), "")


def compose(baseline_text: str, current_text: str) -> dict:
    """The baseline's configuration with every credential family's lines
    taken from *current_text*. ``{"text", "replaced": [family], "nested": [masked]}``:
    ``nested`` names a secret inside a stanza that differs between the two,
    which this does not replace (none in this fleet), so it is said."""
    from modules.redact import redact_positional

    current = {}
    for line in (current_text or "").splitlines():
        fam = _family(line)
        if fam:
            current.setdefault(fam, []).append(line)
    out, placed = [], set()
    for line in (baseline_text or "").splitlines():
        fam = _family(line)
        if not fam:
            out.append(line)                 # verbatim: the sanitiser decides the rest
            continue
        if fam not in placed:
            placed.add(fam)
            out.extend(current.get(fam, []))
    missing = [f for f in current if f not in placed]
    if missing:
        at = next((i for i in range(len(out) - 1, -1, -1) if out[i].strip() == "end"), len(out))
        add = [l for f in missing for l in current[f]]
        out[at:at] = add
    replaced = sorted(placed | set(missing))

    def nested(text):
        """``{masked line: real line}`` for each secret inside a stanza."""
        return {redact_positional(l.rstrip()): l.rstrip() for l in (text or "").splitlines()
                if l[:1].isspace() and redact_positional(l) != l}

    old, new = nested(baseline_text), nested(current_text)
    differs = sorted(m for m in old if m in new and old[m] != new[m])
    return {"text": "\n".join(out) + "\n", "replaced": replaced, "nested": differs}


#: What a lab startup file must carry for Mercury to manage the device it boots (the redeploy's
#: pre-flight, the operator, 2026-10-19): the heartbeat applet, the monitoring lines, the
#: management access. Each a pattern searched line by line (`re.M`); the check says which are
#: absent. The monitoring three are `monitoring_coverage.CHECKS`, the one owner of what shows a
#: device monitored.
def _carries():
    from modules.monitoring_coverage import CHECKS
    return (
        ("heartbeat applet", CHECKS["heartbeat"]),
        ("syslog host", CHECKS["syslog"]),
        ("SNMP community", CHECKS["snmp"]),
        ("NTP", re.compile(r"^ntp server\s", re.M)),
        ("SSH", re.compile(r"^ip ssh\s", re.M)),
        ("vty lines", re.compile(r"^line vty\s", re.M)),
        ("an account", re.compile(r"^username\s", re.M)),
    )
#: A masked placeholder where a secret should be: a file holding one boots a device nobody can
#: sign in to (Mercury masks on the way OUT; a golden is kept verbatim). Mercury's one mask is
#: `redact.PLACEHOLDER`; a banner's row of asterisks is not one (the first run, 2026-10-19,
#: counted every vIOS banner's borders).
def _placeholder():
    from modules.redact import PLACEHOLDER
    return re.compile(re.escape(PLACEHOLDER.split("{", 1)[0]))


def _configuration(text: str) -> list:
    """*text*'s lines outside the credential families, blank lines and trailing space
    dropped: what a startup file must hold of the current golden (the credential families
    are compared on their own, `credentials_current`)."""
    return [l.rstrip() for l in (text or "").splitlines() if l.strip() and not _family(l)]


def _git1(repo: str, *args) -> str:
    from modules.nsot.repo import git

    rc, out, _ = git(repo, *args)
    return (out or "").strip() if rc == 0 else ""


def check(list_name: str, hosts=None, built=None) -> dict:
    """The pre-flight of a redeploy (the operator, 2026-10-19): for each device the lab boots,
    facts about its startup file, never a value. ``{"ok", "baseline", "devices": {host:
    {...}}, "error"?}``; per device:

    - ``built``: whether a file is built (else ``why``);
    - ``baseline_golden`` / ``latest_golden``: the commit of the device's golden the file's
      configuration comes from (the newest earned baseline's) and the device's latest golden
      commit, with ``commits_since`` between them;
    - ``credentials_current``: every credential family's lines in the file equal its current
      golden's, compared inside this function (sha256), the families named;
    - ``placeholders``: lines holding a masked placeholder (none is the only right answer);
    - ``golden_after_rotation``: the current golden was committed at or after the device's last
      rotation that reached it (a golden older than the rotation holds the retired secret);
    - ``read_by_drift``: the last drift run read the device (its session signed in with the
      credential Mercury holds), and when;
    - ``carries`` / ``lacks``: which of `_carries()` the file holds;
    - ``config_current``: every line of the file outside the credential families equals the
      current golden's (C1454: the baseline is a moment, so a deploy verified after it is in no
      file, and a redeploy reverts it while every other fact here reads green); when it does
      not, ``undoes`` names the device's golden commits after the baseline's (short sha and
      subject) and ``lines_undone`` counts the configuration lines that differ, never one.

    Together ``credentials_current``, ``golden_after_rotation`` and ``read_by_drift`` say the
    file holds the secret the device runs and that Mercury's held credential signs in to it,
    shown without any secret being read here."""
    import difflib
    import hashlib

    from modules import drift_check
    from modules.nsot import listref, manifest
    from modules.nsot import repo as R
    from modules.nsot.scheduled_rotation import last_rotation_commits, last_rotations

    got = build(list_name, hosts) if built is None else built
    if not got.get("ok"):
        return {"ok": False, "baseline": {}, "devices": {}, "error": got.get("error", "")}
    ref = listref.resolve(list_name)
    base = got["baseline"]
    rotations = last_rotations()
    rotation_commits = last_rotation_commits()
    drift = drift_check._load_state(list_name)                  # noqa: SLF001
    last = (drift or {}).get("last_result") or {}
    # A run stores the devices it could not read (`errors`) and did not check (`skipped`), each
    # `{"hostname", "reason"}`; every other device of its inventory it read (clean or drifted).
    failed = {str((e or {}).get("hostname", "")) for e in last.get("errors") or []}
    failed |= {str((s or {}).get("hostname", "")) for s in last.get("skipped") or []}
    out = {}
    for host, d in sorted(got["devices"].items()):
        row = {"built": d["state"] == "ok"}
        rel = f"golden/{host}.cfg"
        row["baseline_golden"] = _git1(ref.repo_dir, "log", "-1", "--format=%h", base["commit"],
                                       "--", rel)
        row["latest_golden"] = _git1(ref.repo_dir, "log", "-1", "--format=%h", "HEAD", "--", rel)
        since = _git1(ref.repo_dir, "rev-list", "--count",
                      f"{row['baseline_golden']}..HEAD", "--", rel) if row["baseline_golden"] else ""
        row["commits_since"] = int(since) if since.isdigit() else None
        if not row["built"]:
            row["why"] = d.get("why", "")
            out[host] = row
            continue
        text = d["text"]
        _ident, entry = manifest.find_by_name(ref.repo_dir, host)
        now = R.committed_golden_for(ref.repo_dir, entry) if entry else {}
        current = (now or {}).get("text") or ""

        def family_digest(t, rx):
            lines = [l.rstrip() for l in t.splitlines() if rx.match(l)]
            return hashlib.sha256("\n".join(lines).encode()).hexdigest(), len(lines)

        fams = {}
        for name, rx in FAMILIES:
            a, na = family_digest(text, rx)
            b, _nb = family_digest(current, rx)
            fams[name] = {"equal": a == b, "lines": na}
        row["credentials_current"] = all(f["equal"] for f in fams.values())
        row["families"] = fams
        masked = _placeholder()
        row["placeholders"] = sum(1 for l in text.splitlines() if masked.search(l))
        committed_at = _git1(ref.repo_dir, "log", "-1", "--format=%ct", "HEAD", "--", rel)
        rotated = rotations.get(host)
        rot_sha = rotation_commits.get(host, "")
        golden_sha = _git1(ref.repo_dir, "log", "-1", "--format=%H", "HEAD", "--", rel)
        if rotated and rot_sha and golden_sha:
            # By identity (C1472): the golden is after the rotation when its commit IS the
            # rotation's or descends from it. The record trails its own commit by about a
            # second, so a comparison of times failed the rotation's own golden.
            from modules.nsot.repo import git
            row["golden_after_rotation"] = (
                golden_sha == rot_sha
                or git(ref.repo_dir, "merge-base", "--is-ancestor", rot_sha, golden_sha)[0] == 0)
        else:
            row["golden_after_rotation"] = (None if not rotated or not committed_at.isdigit()
                                            else int(committed_at) >= int(rotated[0]))
        row["rotated_at"] = rotated[1] if rotated else ""
        row["read_by_drift"] = bool(last.get("checked")) and host not in failed
        row["drift_at"] = drift.get("last_check_ts") if isinstance(drift, dict) else None
        row["carries"] = [n for n, rx in _carries() if rx.search(text)]
        row["lacks"] = [n for n, _rx in _carries() if n not in row["carries"]]
        built_cfg, current_cfg = _configuration(text), _configuration(current)
        row["config_current"] = built_cfg == current_cfg
        row["undoes"], row["lines_undone"] = [], 0
        if not row["config_current"]:
            row["lines_undone"] = sum(1 for d in difflib.ndiff(built_cfg, current_cfg)
                                      if d[:2] in ("- ", "+ "))
            log_out = _git1(ref.repo_dir, "log", "--format=%h %s",
                            f"{row['baseline_golden']}..HEAD", "--", rel) \
                if row["baseline_golden"] else ""
            row["undoes"] = [l for l in log_out.splitlines() if l.strip()]
        out[host] = row
    return {"ok": True, "baseline": base, "devices": out}


def build(list_name: str, hosts=None) -> dict:
    """Every device's startup source for *list_name*.

    ``{"ok", "baseline": {tag, commit}|{}, "devices": {host: {"state":
    "ok"|"refused", "text"?, "why"?, "replaced", "nested"}}, "error"?}``.
    No earned baseline is ``ok: False`` with why; a device it does not hold is
    refused alone."""
    from modules.nsot import listref, manifest
    from modules.nsot import repo as R

    ref = listref.resolve(list_name)
    base = newest_earned(ref.repo_dir)
    if not base:
        return {"ok": False, "baseline": {}, "devices": {}, "error": (
            f"{list_name} has no earned baseline (one taken with every device at its "
            "committed intent, not withdrawn): Save All earns one")}
    if hosts is None:
        from modules.device import load_saved_devices
        hosts = [d.get("hostname") for d in load_saved_devices(ref.csv_path) if d.get("hostname")]
    devices = {}
    for h in hosts:
        old = R.golden_at(ref.repo_dir, h, base["commit"])
        if not old:
            devices[h] = {"state": "refused", "why": (
                f"{base['tag']} holds no golden for {h} (onboarded since, or renamed): "
                "earn a new baseline (Save All) to build its file")}
            continue
        _ident, entry = manifest.find_by_name(ref.repo_dir, h)
        now = R.committed_golden_for(ref.repo_dir, entry) if entry else {}
        if not (now or {}).get("text"):
            devices[h] = {"state": "refused", "why": (
                f"{h}'s current golden could not be read ({(now or {}).get('refused') or 'none'}), "
                "and its credentials come from there, never from the baseline")}
            continue
        got = compose(old, now["text"])
        devices[h] = {"state": "ok", "text": got["text"], "replaced": got["replaced"],
                      "nested": got["nested"]}
    return {"ok": True, "baseline": {"tag": base["tag"], "commit": base["commit"]},
            "devices": devices}
