"""A VLAN read where the device keeps it (C1646): ``show vlan id <N>``.

An IOS switch in VTP server or client mode keeps its VLANs in the VLAN database (vlan.dat) and
does not print them in ``show running-config``; one in transparent mode prints them in both. So a
``vlan <N>`` line, and the ``name`` under it, are read where every mode keeps them: the VLAN
table ``show vlan id <N>`` prints. Measured on two lab vIOS-L2 switches, one in VTP server mode
and one transparent (tests/fixtures/console/vios_l2_*_show_vlan_id_*.txt, 2026-10-24): the first
table's row is ``<N> <name> <status> <ports>``, and a VLAN the database lacks answers ``VLAN id
<N> not found in current VLAN database``.

One home for the deploy's verify (`verify_scope.read_back`) and the out-of-band kick-start's
read-back (`console_kickstart.readback_plan`). Pure: it builds the command and reads its answer.
"""

import re

#: The read, one command at the privileged prompt (`readonly_commands`: a ``show``).
READ = "show vlan id {vlan}"
#: A VLAN id as typed in a ``vlan`` line or a read: an integer 1 to 4094, no sign, no leading 0.
VLAN_ID = re.compile(r"[1-9][0-9]{0,3}")
LOWEST, HIGHEST = 1, 4094
#: The first table's header and its rule; the row under them is the VLAN's.
HEADER = re.compile(r"VLAN\s+Name\s+Status\s+Ports\s*$")
RULE = re.compile(r"-{4}\s+-+")
ROW = re.compile(r"([1-9][0-9]{0,3})\s+(\S+)\s+(\S+)(?:\s+(.*))?$")
#: IOS's answer for a VLAN its database lacks.
NOT_FOUND = re.compile(r"VLAN id ([1-9][0-9]{0,3}) not found in current VLAN database\s*$")


def vlan_id(value) -> str:
    """*value* as a VLAN id (``"10"``), or ValueError naming it and the shape it must have."""
    text = str(value)
    if not VLAN_ID.fullmatch(text) or not LOWEST <= int(text) <= HIGHEST:
        raise ValueError(f"the VLAN id {value!r} is not an integer from {LOWEST} to {HIGHEST}")
    return text


def command(value) -> str:
    """The read for VLAN *value*; ValueError (`vlan_id`) before any command is built."""
    return READ.format(vlan=vlan_id(value))


def vlan_of(line: str):
    """The id a top-level ``vlan <N>`` line configures (``"10"``), or None: a list or range
    (``vlan 10,20``, ``vlan 10-12``), ``vlan internal allocation ...`` or anything else is not
    one VLAN, and is read where it was before."""
    words = str(line or "").split()
    if len(words) != 2 or words[0] != "vlan":
        return None
    try:
        return vlan_id(words[1])
    except ValueError:
        return None


def parse(value, text) -> dict:
    """What ``show vlan id <value>``'s answer *text* says: ``{"state": "present" | "absent" |
    "unreadable", "name", "status", "row", "why"}``. Present: the first table's ONE row is the
    VLAN's; absent: IOS's not-found line for this VLAN; anything else (no answer, a refusal, a
    table with no row or another VLAN's) is unreadable, which neither passes nor fails."""
    want = vlan_id(value)
    out = {"state": "unreadable", "name": "", "status": "", "row": "", "why": ""}
    lines = str(text or "").split("\n")             # each use strips its line whole
    for ln in lines:
        m = NOT_FOUND.match(ln.strip())
        if m and m.group(1) == want:
            return dict(out, state="absent", row=ln.strip(),
                        why=f"VLAN {want} is not in the device's VLAN database")
    at = next((i for i, ln in enumerate(lines) if HEADER.match(ln.strip())), None)
    if at is None:
        shown = next((ln.strip() for ln in lines if ln.strip()), "")
        return dict(out, why=f"the answer has no VLAN table ({shown!r})" if shown
                    else "the answer is empty")
    rows = []
    for ln in lines[at + 1:]:
        if not ln.strip() or RULE.match(ln.strip()):
            if rows:
                break
            continue
        m = ROW.match(ln.strip())
        if not m:
            break
        rows.append(m)
    if len(rows) != 1 or rows[0].group(1) != want:
        found = [r.group(1) for r in rows]
        return dict(out, why=f"the VLAN table shows {found or 'no row'}, not VLAN {want} alone")
    row = rows[0]
    return {"state": "present", "name": row.group(2), "status": row.group(3),
            "row": row.group(0), "why": f"VLAN {want} is {row.group(3)}, named {row.group(2)}"}
