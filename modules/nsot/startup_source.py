"""What each lab startup file is built FROM (plan item 4, the operator's
decision, 2026-10-01; per device since C1454, 2026-10-28).

The lab's startup sync wrote each device's startup file from Oxidized's last copy, so
a redeploy booted whatever the device last ran, approved or not, and one
device's unapproved change held every file back (C306, C309). The source was
then the list's **newest EARNED baseline**: a moment the tool recorded every
device at its committed intent (7.2's `Baseline: earned`), never a withdrawn
one (C177), never a deleted tag, never one taken before baselines recorded
what they earned. (Oxidized's copy was the cross-check until Phase 3 retired
Oxidized; the lab startup check reads each file against the record.)

**Each device's source is its newest golden recorded AT ITS COMMITTED INTENT** (C1454 (1)):
a baseline is a moment, and a scoped deploy never earns one, so the newest earned baseline
lagged every verified per-device deploy, and a redeploy silently reverted it. The record is
the one every save writes, whatever the path: a commit's `Intent-Match:` trailer judges each
device the save read (`Devices:`, `Devices-Measured:`) against the render of committed
intent, read here by `device_list`'s own parsers (one reading of the trailer). The newest
commit that records the device at intent is its source; an earned baseline is a source for
every device its tree holds (it judged them all), and the newest earned baseline is the
fallback when no such commit is within the read. This keeps C306: a golden is a source only
where the tool recorded it equal to committed intent, the same per-device judgement a
baseline makes, so a change nobody approved (a capture that departs) is never booted. A
source is never older than the device's current golden file (its life since onboarding or
a rename): a retired device's golden never boots the new device given its name. A device
with no such golden is REFUSED for that device, named, never built from a golden nobody
recorded at intent.

**Credentials always from the CURRENT state** (C309). A source is a record
of a moment, and moments contain credentials (C75): one older than a rotation
holds the password the rotation retired, and a redeploy from it would lock
the tool out. So every credential family below is taken from the device's
current committed golden, as a block, where the baseline's first line of that
family sat (appended before `end` when the baseline had none); the baseline's
own lines of that family are dropped. A family the current golden lacks is
dropped too: the current state wins in both directions.

A device refused (no golden at intent, and the baseline holds none for it)
is named alone: the sync writes every device it can and names the rest.
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
        if _is_earned(b):
            return b
    return {}


def _is_earned(b: dict) -> bool:
    return not b.get("deleted") and not b.get("withdrawn") and b.get("decision") == "earned"


def _golden_rel(host: str) -> str:
    from modules.nsot.repo import _safe_name   # noqa: SLF001 (golden_at's own path rule)
    return f"golden/{_safe_name(host)}.cfg"


def _life_start(repo: str, host: str) -> str:
    """The commit that created *host*'s CURRENT golden file at HEAD (its onboarding, or the
    rename that gave it this name), or "" when HEAD holds none. Nothing older is a source: a
    retired device's golden never boots the new device that took its name."""
    return _git1(repo, "log", "-1", "--diff-filter=A", "--format=%H", "HEAD", "--",
                 _golden_rel(host))


def _in_life(repo: str, start: str, sha: str) -> bool:
    from modules.nsot.repo import git

    return bool(start and sha) and (
        sha == start or git(repo, "merge-base", "--is-ancestor", start, sha)[0] == 0)


#: What each `Intent-Match:` commit is read for: its sha, its workflow and the devices it
#: judged (`device_list`'s own fields and parsers: one reading of the trailers).
def _measurements(repo: str) -> tuple:
    """``(records, error, full)``: the newest `device_list.LOG_BOUND` commits carrying
    `Intent-Match:`, newest first, each ``(sha, source, judged, trailer)``; *full* says the
    read returned its whole bound, so an older record may exist beyond it."""
    from modules import device_list as DL
    from modules.nsot.repo import git

    fmt = DL._FIELD.join(["%H", "%(trailers:key=Source,valueonly)",            # noqa: SLF001
                          "%(trailers:key=Device-Name,valueonly,separator=%x2c)",
                          "%(trailers:key=Devices,valueonly,separator=%x2c)",
                          "%(trailers:key=Devices-Measured,valueonly,separator=%x2c)",
                          "%(trailers:key=Intent-Match,valueonly)"]) + DL._RECORD  # noqa: SLF001
    rc, out, err = git(repo, "log", f"-n{DL.LOG_BOUND}", "-E", "--grep=^Intent-Match: ",
                       f"--format={fmt}", "HEAD")
    if rc != 0:
        return [], (err or out or "git log failed").strip(), False
    records = []
    for record in out.split(DL._RECORD):                                     # noqa: SLF001
        parts = record.strip("\n").split(DL._FIELD)                          # noqa: SLF001
        if len(parts) < 6:
            continue
        sha, source, names, devices, measured, trailer = parts[:6]
        judged, _moved = DL._measured_by(names, devices, measured)           # noqa: SLF001
        records.append((sha, source.strip(), set(judged), trailer.strip()))
    return records, "", len(records) >= DL.LOG_BOUND


def sources(repo: str, hosts, base: dict = None) -> dict:
    """Each device's startup source (C1454 (1)): ``{host: {"commit", "how", "text"}}``, or
    ``{host: {"commit": "", "why"}}`` when there is none.

    The source is the newest commit, within the device's current golden's life, that records
    its golden at its committed intent: a save that judged it (`Devices:` or
    `Devices-Measured:`) with its `Intent-Match:` saying it matched, or an earned baseline
    holding its golden (a baseline judged every device). *base*, the newest earned baseline,
    is the fallback when the read reaches no such commit. A golden recorded off intent, or
    unknown, or never judged, is never a source: that is a change nobody approved (C306)."""
    from modules import device_list as DL
    from modules.nsot.repo import golden_at, list_baselines

    earned = {}
    for b in list_baselines(repo):                    # newest first: a commit's newest tag
        if _is_earned(b):
            earned.setdefault(b["commit"], b["tag"])
    records, error, full = _measurements(repo)
    out = {}
    for h in [h for h in hosts if h]:
        start = _life_start(repo, h)
        if not start:
            out[h] = {"commit": "", "why": f"{h} has no committed golden"}
            continue
        chosen = None
        for sha, source, judged, trailer in records:
            tag = earned.get(sha, "")
            if h in judged:
                if DL._intent_of(h, trailer)["state"] != "at_intent":   # noqa: SLF001
                    continue
                how = (f"recorded at its committed intent by "
                       f"{DL.SOURCE_WORDS.get(source, source.replace('_', ' ') or 'a save')}"
                       + (f", which earned {tag}" if tag else ""))
            elif tag:
                how = f"held by {tag}, which recorded every device at its committed intent"
            else:
                continue
            if not _in_life(repo, start, sha):
                break                                 # every older record is older still
            text = golden_at(repo, h, sha)
            if text:
                chosen = {"commit": sha, "how": how, "text": text}
                break
        if chosen is None and base and _in_life(repo, start, base["commit"]):
            text = golden_at(repo, h, base["commit"])
            if text:
                chosen = {"commit": base["commit"], "text": text,
                          "how": (f"the newest earned baseline {base['tag']}, the fallback: no "
                                  "newer record of it at its committed intent"
                                  + (f" in the last {DL.LOG_BOUND} measurements" if full
                                     else ""))}
        if chosen is None:
            read = (f" (the measurement history could not be read: {error})" if error else
                    f" in the last {DL.LOG_BOUND} measurements" if full else "")
            held = (f"{base['tag']} holds no golden of it since its current golden was "
                    "created (onboarded or renamed since)" if base else
                    "no earned baseline holds one")
            out[h] = {"commit": "", "why": (
                f"no golden of {h} is recorded at its committed intent{read}, and {held}: "
                "bring it to its intent and Save All to build its file")}
            continue
        out[h] = chosen
    return out


def standing(list_name: str, hosts) -> dict:
    """Whether each device OUTSIDE a deploy stands at its committed intent, by its record
    (C1454 (2)): ``{"head": sha, "devices": {host: {"ok", "why", "golden", "drift_at"}}}``.

    A device stands when its intent state (`device_list.intent_state`, the one owner: its
    newest measurement at intent, nothing it was judged against moved since) is at intent,
    it has a committed golden, the last drift run did not find it departing from that golden,
    and the last drift run read it, unless its newest measurement (a capture) is newer than
    that run, which is then the newest read. *head* is the commit the judgement read, so the
    commit that rests on it refuses if anything it judged moved since
    (`repo._standing_moved`). Each ``why`` holds no "; " (the trailer's separator, C885)."""
    from modules import device_list as DL
    from modules import drift_check
    from modules.nsot import listref

    repo = listref.resolve(list_name).repo_dir
    head = _git1(repo, "rev-parse", "HEAD")
    got = DL.reads(repo)
    drift = drift_check._load_state(list_name) or {}           # noqa: SLF001
    last = drift.get("last_result") or {}
    ran_at = float(drift.get("last_check_ts") or 0)
    unread = {str((e or {}).get("hostname", "")) for e in
              (last.get("errors") or []) + (last.get("skipped") or [])}
    drifted = {str((d or {}).get("hostname", "")) for d in last.get("drifted_devices") or []}
    out = {}
    for h in hosts:
        state = DL.intent_state(h, got)
        m = DL.newest_measurement(h, got) if not got["error"] else None
        # The one golden-history read names it; a device beyond its bound costs one read.
        golden = ((got["history"].get(h) or {}).get("commit")
                  or _git1(repo, "log", "-1", "--format=%H", "HEAD", "--", _golden_rel(h)))
        why = ""
        if state["state"] != "at_intent":
            why = f"its intent state is {state['words']}" + (
                f" ({state['why']})" if state.get("why") else "")
        elif not golden:
            why = "it has no committed golden"
        elif h in drifted:
            why = "the last drift run found it departing from its golden"
        elif m and m["at"] > ran_at:
            pass                                       # its newest capture is the newest read
        elif not last.get("checked"):
            why = "no drift run has read it since its last measurement"
        elif h in unread:
            why = "the last drift run could not read it"
        out[h] = {"ok": not why, "why": " ".join(why.replace(";", ",").split()),
                  "golden": golden, "drift_at": ran_at or None}
    return {"head": head, "devices": out}


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
    - ``source_commit`` / ``source_how`` / ``latest_golden``: the commit the file's
      configuration comes from (its source, `sources`: the newest golden recorded at its
      committed intent, else the fallback baseline) and how it was recorded there, and the
      device's latest golden commit, with ``commits_since`` (golden commits after the source);
    - ``credentials_current``: every credential family's lines in the file equal its current
      golden's, compared inside this function (sha256), the families named;
    - ``placeholders``: lines holding a masked placeholder (none is the only right answer);
    - ``golden_after_rotation``: the current golden was committed at or after the device's last
      rotation that reached it (a golden older than the rotation holds the retired secret);
    - ``read_by_drift``: the last drift run read the device (its session signed in with the
      credential Mercury holds), and when;
    - ``drifted``: the last drift run found the device departing from its golden, so the file
      would undo a change nobody recorded (C1454 (1): "no drift since");
    - ``carries`` / ``lacks``: which of `_carries()` the file holds;
    - ``config_current``: every line of the file outside the credential families equals the
      current golden's (C1454: a golden committed after the source, recorded off its intent,
      is in no file, and a redeploy reverts it while every other fact here reads green); when
      it does not, ``undoes`` names the device's golden commits after the source (short sha
      and subject) and ``lines_undone`` counts the configuration lines that differ, never one.

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
    drifted = {str((x or {}).get("hostname", "")) for x in last.get("drifted_devices") or []}
    out = {}
    for host, d in sorted(got["devices"].items()):
        row = {"built": d["state"] == "ok"}
        rel = _golden_rel(host)
        src = d.get("source") or {}
        row["source_commit"] = (src.get("commit") or "")[:10]
        row["source_how"] = src.get("how", "")
        row["latest_golden"] = _git1(ref.repo_dir, "log", "-1", "--format=%h", "HEAD", "--", rel)
        since = _git1(ref.repo_dir, "rev-list", "--count",
                      f"{src['commit']}..HEAD", "--", rel) if src.get("commit") else ""
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
        row["drifted"] = host in drifted
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
                            f"{src['commit']}..HEAD", "--", rel) if src.get("commit") else ""
            row["undoes"] = [l for l in log_out.splitlines() if l.strip()]
        out[host] = row
    return {"ok": True, "baseline": base, "devices": out}


def build(list_name: str, hosts=None) -> dict:
    """Every device's startup source for *list_name*.

    ``{"ok", "baseline": {tag, commit}|{}, "devices": {host: {"state":
    "ok"|"refused", "text"?, "why"?, "replaced", "nested", "source"?: {commit, how}}},
    "error"?}``. Each device's configuration is its source's (`sources`), every credential
    family its current golden's. No earned baseline is ``ok: False`` with why, as before
    C1454: the baseline is the fallback, and the lab's sync names its records by it; a device
    with no source is refused alone."""
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
    found = sources(ref.repo_dir, hosts, base)
    devices = {}
    for h in hosts:
        src = found.get(h) or {"commit": "", "why": f"{h} has no committed golden"}
        if not src["commit"]:
            devices[h] = {"state": "refused", "why": src["why"]}
            continue
        _ident, entry = manifest.find_by_name(ref.repo_dir, h)
        now = R.committed_golden_for(ref.repo_dir, entry) if entry else {}
        if not (now or {}).get("text"):
            devices[h] = {"state": "refused", "why": (
                f"{h}'s current golden could not be read ({(now or {}).get('refused') or 'none'}), "
                "and its credentials come from there, never from its source")}
            continue
        got = compose(src["text"], now["text"])
        devices[h] = {"state": "ok", "text": got["text"], "replaced": got["replaced"],
                      "nested": got["nested"],
                      "source": {"commit": src["commit"], "how": src["how"]}}
    return {"ok": True, "baseline": {"tag": base["tag"], "commit": base["commit"]},
            "devices": devices}
