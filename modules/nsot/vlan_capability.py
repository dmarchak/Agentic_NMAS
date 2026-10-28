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
    return dict(out, words=(
        f"not declared and not measured: run `{CHECK}` on {hostname} (Show commands, or Ask "
        f"the device on its page) to measure it"))
