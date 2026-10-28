"""Whether a device has a VLAN database (C1692; the operator's decision, 2026-10-28).

A `vlan <N>` line creates a VLAN only on a device with a VLAN database (a switch). A router's
intent holds ``vlans: []`` all the same, so the intent patch alone could not tell, and an
`add_vlan` on a router would have reached a deploy as `vlan 40`. So a device has VLANs only by:

1. **A declaration**, per config dialect and device type: Mercury's platform table
   (`platform_capabilities.json`, ``vlan_database``), keyed by the device's dialect
   (`platform.platform_for_device`) and its device type as NetBox names it (the inventory's
   ``_model``, NetBox's ``device_type.model``). A device type not listed is not declared.
2. **Else a measurement**: the device's own answer to :data:`CHECK`, as Show commands (or Ask
   the device) recorded it (`reads`), the newest readable one, with its time and its run. A
   recorded answer from before the name's cut (`retire.name_cuts`: its retirement, abandon or
   Create) is an earlier device's, never this one's.
3. **Else unknown**, which refuses the VLAN, naming the check to run.

Never by a name or a role: a device named like a switch, or in a role called a switch, is
answered by its declaration or its measurement alone (refusing by resemblance is safe,
allowing by resemblance is not).

**The check, `show vlan id 1`:** VLAN 1 is in every VLAN database and is never deleted, so a
device with one lists it (measured on two vIOS-L2 switches, VTP server and transparent,
2026-10-24: tests/fixtures/console/vios_l2_*_show_vlan_id_1.txt), and `vlan_read.parse` reads
the table. A device refusing the command (IOS's ``% Invalid input detected at '^' marker.``)
has no VLAN database. **What a router answers is not captured** (C1692's measurement is owed):
the refusal's shape is IOS's and IOS-XE's own for a command they lack (`show foobar`,
tests/fixtures/operational/*__show_foobar.txt), and an answer of any other shape is unreadable,
which leaves the device unknown and the VLAN refused. A wrong "no" refuses; only a VLAN table
says "yes".

Read once per request, from stored data only: the inventory (served from memory for a NetBox
list), the table, and the network's recorded Show commands runs. Never a device read.

**One check for every intent write path** (C2043, C2044): :func:`judge` refuses a change that
ADDS a VLAN (an entry of ``vlans`` present after and not before) to a device whose answer is
not yes, in :func:`refusal`'s words, which the intent patch (per operation), the intent
editor's commit and bulk intent all use. Removing a VLAN, or leaving the list as it was, is
never asked about, so a document committed before the check stays committable.
"""

import json
import logging
import os
import re
import time

log = logging.getLogger(__name__)

TABLE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "platform_capabilities.json")
#: The check: one read at the privileged prompt (`readonly_commands`: a ``show``).
CHECK = "show vlan id 1"
_CHECK_WORDS = ("show", "vlan", "id", "1")
#: IOS's refusal of a command it lacks, its own line (captured on IOS and IOS-XE).
REFUSED = re.compile(r"% Invalid input detected at '\^' marker\.\s*$")
#: How many of a device's newest Show commands runs are read for the check's answer.
RUNS_READ = 200

DECLARED, MEASURED, UNKNOWN = "declared", "measured", "unknown"


def _table() -> dict:
    with open(TABLE_FILE, encoding="utf-8") as fh:
        return json.load(fh)


def declared(dialect: str, model: str):
    """The table's entry for *dialect* and device type *model* (``{"has", "basis", "source",
    ...}``), or None when it declares none. The device type is compared whole, ignoring case:
    never a prefix or a family."""
    dialect, model = (dialect or "").strip(), (model or "").strip()
    if not dialect or not model:
        return None
    types = (_table().get("vlan_database") or {}).get(dialect) or {}
    for name, entry in types.items():
        if name.casefold() == model.casefold() and isinstance(entry.get("has"), bool):
            return dict(entry, device_type=name)
    return None


def is_check(command: str) -> bool:
    """Whether *command* is the check, whole: its four words (IOS abbreviations allowed) and
    nothing after them, no output modifier (a filtered answer is another answer)."""
    from modules.nsot import reads

    words = str(command or "").split()
    return (len(words) == len(_CHECK_WORDS) and "|" not in str(command)
            and reads.matches(command, _CHECK_WORDS))


def read_answer(text) -> dict:
    """What the check's answer *text* says: ``{"has": True | False | None, "why"}``. A VLAN
    table, or IOS's line naming its VLAN database: True. IOS's refusal of the command: False.
    Anything else: None (unreadable, which neither allows nor declares anything)."""
    from modules.nsot import vlan_read

    text = str(text or "")
    got = vlan_read.parse("1", text)
    if got["state"] == "present":
        return {"has": True, "why": f"it lists VLAN 1 ({got['row']})"}
    if got["state"] == "absent":
        return {"has": True, "why": f"it answers from a VLAN database ({got['row']})"}
    refused = next((ln.strip() for ln in text.splitlines() if REFUSED.search(ln.strip())), "")
    if refused:
        return {"has": False, "why": f"it refuses the command ({refused})"}
    return {"has": None, "why": got["why"]}


def _when(at) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(at)))


def measured(list_name: str, hostname: str, *, cut: dict = None):
    """The newest readable answer *hostname* gave to the check in *list_name*'s recorded Show
    commands runs (its newest :data:`RUNS_READ`): ``{"has", "why", "at", "run"}``, or None.
    An unreadable or failed answer is passed over for an older readable one (a failed read
    keeps the last good value); an answer from before the name's cut is an earlier device's,
    and ends the search. Reads files only, where `reads` writes them; called for a network
    whose committed intent was just read, so its folder is there."""
    from modules.nsot import reads, retire

    got = reads.runs(list_name, device=hostname, limit=RUNS_READ)
    cut = retire.name_cuts(list_name) if cut is None else cut
    for run in got["runs"]:
        result = (run.get("results") or {}).get(hostname) or {}
        for answer in result.get("answers") or []:
            if answer.get("state") != reads.ANSWERED or not is_check(answer.get("command")):
                continue
            at = answer.get("at") or run.get("started_at")
            if not isinstance(at, (int, float)) or retire.before_retirement(cut, hostname, at):
                return None
            read = read_answer(answer.get("answer"))
            if read["has"] is None:
                continue
            return dict(read, at=_when(at), run=run.get("id", ""))
    return None


def _inventory(list_name: str) -> list:
    """*list_name*'s devices as the inventory serves them (`load_saved_devices`: from memory
    for a NetBox list). A seam for tests."""
    from modules.device import load_saved_devices
    from modules.nsot import listref

    return load_saved_devices(listref.resolve(list_name).csv_path)


def of(list_name: str, hostname: str) -> dict:
    """*hostname*'s VLAN database, and where the answer came from: ``{"hostname", "platform",
    "device_type", "has": True | False | None, "source": declared | measured | unknown,
    "words", "at", "check"}``. *words* says the answer and its source, for a refusal or a
    preview to quote."""
    from modules.nsot import platform

    try:
        device = next((d for d in _inventory(list_name) if d.get("hostname") == hostname), {})
    except Exception as exc:                          # noqa: BLE001 (unknown, said)
        log.warning("vlan capability: %s's inventory unreadable: %s", list_name, exc)
        device = {}
    dialect = platform.platform_for_device(device) if device else ""
    model = str(device.get("_model") or "").strip()
    out = {"hostname": hostname, "platform": dialect, "device_type": model, "has": None,
           "source": UNKNOWN, "at": "", "check": CHECK}
    entry = declared(dialect, model)
    if entry is not None:
        state = "a VLAN database" if entry["has"] else "no VLAN database"
        owed = f"; owed: {entry['owed']}" if entry.get("owed") else ""
        return dict(out, has=entry["has"], source=DECLARED, words=(
            f"declared: {state} (Mercury's platform table, {dialect} device type "
            f"{entry['device_type']}, {entry.get('basis', '')}: {entry.get('source', '')}"
            f"{owed})"))
    try:
        seen = measured(list_name, hostname)
    except Exception as exc:                          # noqa: BLE001 (unknown, said)
        log.warning("vlan capability: %s's Show commands runs unreadable: %s", list_name, exc)
        seen = None
    if seen is not None:
        state = "a VLAN database" if seen["has"] else "no VLAN database"
        return dict(out, has=seen["has"], source=MEASURED, at=seen["at"], words=(
            f"measured: {state} ({hostname}'s answer to `{CHECK}` at {seen['at']}, Show "
            f"commands run {seen['run']}: {seen['why']})"))
    return dict(out, words=unknown_words(hostname, dialect, model))


def unknown_words(hostname: str, dialect: str = "", model: str = "") -> str:
    """What an unknown answer says, naming what would answer it: the check, run through Show
    commands, or the device's NetBox device type, by which the platform table declares."""
    measure = (f"not declared and not measured: run `{CHECK}` on {hostname} (Show commands, "
               f"or Ask the device on its page) to measure it")
    if not model:
        return (f"{measure}, or name its device type in NetBox, by which Mercury's platform "
                f"table declares a VLAN database (none is named)")
    return (f"{measure}; Mercury's platform table declares nothing for "
            f"{dialect or 'an unknown platform'} device type {model}")


# ── the one check every intent write path asks (C1692, C2043, C2044) ──────────
#
# The intent patch (`intent_patch`, per operation, its apply pure), the intent editor's commit
# (`intent_edit.commit_many`) and bulk intent (`bulk_intent.plan`) each refuse a VLAN added to
# a device whose answer is not yes, in these words. A VLAN removed, or a list left as it was,
# is never asked about, so a document committed before this check stays committable.

def _vlan_keys(doc) -> list:
    """``[(key, label)]`` for each entry of *doc*'s ``vlans``: a mapping by its ``id`` (as
    text, so ``40`` and ``"40"`` are one VLAN), anything else by its whole value."""
    vlans = doc.get("vlans") if isinstance(doc, dict) else None
    if vlans in (None, "", [], {}):
        return []
    out = []
    for entry in vlans if isinstance(vlans, list) else [vlans]:
        if isinstance(entry, dict) and entry.get("id") not in (None, ""):
            label = str(entry["id"]).strip()
            out.append(("id:" + label, label))
        else:
            label = json.dumps(entry, sort_keys=True, default=str)
            out.append(("entry:" + label, label))
    return out


def added(before, after) -> list:
    """The VLANs the intent document *after* holds and *before* does not, by id, in *after*'s
    order: what a change ADDS. A VLAN removed, renamed or left as it was is not added."""
    had = {key for key, _label in _vlan_keys(before)}
    out = []
    for key, label in _vlan_keys(after):
        if key not in had and label not in out:
            out.append(label)
    return out


def refusal(hostname: str, capability, adds: str) -> str:
    """The refusal of *adds* (what is added, as its caller names it: ``operations[0] adds VLAN
    40``) on *hostname*, or ``""`` when *capability* (`of`'s answer) says it has a VLAN
    database. A declared or measured "no", and an unknown (none given is unknown), each name
    the device, its platform and device type, where the answer came from, and, unknown, what
    would answer it. Never judged from a name or a role."""
    cap = capability if isinstance(capability, dict) else {}
    if cap.get("has") is True:
        return ""
    what = (f"{hostname} ({cap.get('platform') or 'platform not known'}, device type "
            f"{cap.get('device_type') or 'not named'})")
    if cap.get("has") is False:
        return (f"{adds}, and {what} has no VLAN database: "
                f"{cap.get('words') or 'said by its caller'}. Nothing is added")
    return (f"{adds}, and whether {what} has a VLAN database is "
            + (cap.get("words") or unknown_words(hostname, cap.get("platform") or "",
                                                 cap.get("device_type") or ""))
            + ". A VLAN is added only where a VLAN database is declared or measured")


#: Given as *capability* to :func:`judge` when no network was named to read the answer from.
NOT_READ = {"has": None, "words": "not read: no network was named to read it from"}


def judge(list_name: str, hostname: str, before, after, *, subject: str,
          capability=None) -> dict:
    """Whether the change from intent document *before* to *after* may be committed for
    *hostname*: ``{"ok": True, "added", "capability"}``, or the refusal ``{"ok": False,
    "status": 409, "stage": "capability", "hostname", "added", "capability", "error"}``, its
    words :func:`refusal`'s with *subject* (``this edit``, ``the change``) as what adds.

    The device's answer is read (`of`) only when the change adds a VLAN, and only when its
    caller did not hand in the *capability* it read for this request already."""
    vlans = added(before, after)
    if not vlans:
        return {"ok": True, "added": [], "capability": None}
    if capability is None:
        capability = of(list_name, hostname) if list_name else dict(NOT_READ)
    words = refusal(hostname, capability, (
        f"{subject} adds VLAN {vlans[0]}" if len(vlans) == 1
        else f"{subject} adds VLANs {', '.join(vlans)}"))
    if not words:
        return {"ok": True, "added": vlans, "capability": capability}
    return {"ok": False, "status": 409, "stage": "capability", "hostname": hostname,
            "added": vlans, "capability": capability, "error": words}
