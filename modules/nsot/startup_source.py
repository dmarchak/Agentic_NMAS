"""What each lab startup file is built FROM (plan item 4, the operator's
decision, 2026-10-01).

The clab sync wrote each device's startup file from Oxidized's last copy, so
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
