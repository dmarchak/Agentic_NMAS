"""Flow placement by a switch's own tables (the SDN platform design revision 6, section 7 E; T10;
C2601): a flow goes in the FIRST table, by table id, whose recorded match fields, instructions
and actions accept it, and a flow no table accepts is refused naming each table and the field
or action it refused.

The tables come from one of two records, in one shape (`Table`):
- a switch's `table_features` answer, as a driver reads it (`from_features`): what the switch
  itself says it accepts;
- a platform profile's measured `openflow.tables` (`from_profile`,
  `modules/platforms/profile.py`): a pipeline measured before its answer was a fixture, with the
  rules a table-features answer cannot say (a table reserved for the pipeline's own goto, the
  ethertypes a table takes, the match fields it refuses).

What a table refuses, each said with the table and the operand:
- a reserved table (the ProCurve's table 0, which holds only the pipeline's goto to table 100);
- a match field not in its `match` (or in its `match_excludes`), or a flow without `eth_type`,
  or with one outside its `eth_types`;
- an instruction (GOTO_TABLE, METER, WRITE_METADATA, WRITE_ACTIONS, CLEAR_ACTIONS) not in its
  `instructions`; any apply-action when APPLY_ACTIONS is not; an action not in its
  `apply_actions`; a SET_FIELD of a field not in its `apply_setfield`; a GOTO_TABLE to a table
  not in its `next_tables`.

A placement in a software table says so beside it (`notes`), with the rate the profile records
(the ProCurve's table 200 at 100 packets a second): documented, never hidden.
"""

import dataclasses
from typing import Any, Optional

from modules.sdn.drivers.base import INSTRUCTION_TYPES

ANY = "any"


@dataclasses.dataclass
class Table:
    """One flow table's acceptance rules; a list field is a list or ANY (no restriction)."""

    table_id: int
    match: Any = ANY
    match_excludes: list = dataclasses.field(default_factory=list)
    eth_types: Any = ANY
    instructions: Any = ANY
    apply_actions: Any = ANY
    apply_setfield: Any = ANY
    next_tables: Any = ANY
    reserved: str = ""
    hardware: Optional[bool] = None
    max_entries: Optional[int] = None
    software_pps: Optional[int] = None
    source: str = ""


def from_features(answer: dict) -> list:
    """Tables from a driver's `table_features` answer (`{"ok", "tables": [...]}`)."""
    if not answer.get("ok"):
        raise ValueError(f"the table features were not read: {answer.get('error')}")
    out = []
    for t in answer["tables"]:
        out.append(Table(table_id=t["table_id"], match=list(t["match"]),
                         instructions=list(t["instructions"]),
                         apply_actions=list(t["apply_actions"]),
                         apply_setfield=list(t["apply_setfield"]),
                         next_tables=list(t["next_tables"]), max_entries=t["max_entries"],
                         source="the switch's table features"))
    return sorted(out, key=lambda t: t.table_id)


def from_profile(entry: dict) -> list:
    """Tables from a platform profile entry's measured `openflow.tables`."""
    tables = entry["openflow"].get("tables")
    if not tables:
        raise ValueError("the profile entry records no tables (its pipeline is discovered)")
    fields = {f.name for f in dataclasses.fields(Table)}
    out = [Table(source="the platform profile",
                 **{k: v for k, v in t.items() if k in fields}) for t in tables]
    return sorted(out, key=lambda t: t.table_id)


def _allowed(value, allowed) -> bool:
    return allowed == ANY or value in allowed


def refusals(table: Table, flow: dict) -> list:
    """Why *table* cannot hold *flow* (a normalised flow: `match`, `actions`), in words; empty
    when it can."""
    if table.reserved:
        return [f"table {table.table_id} is reserved: {table.reserved}"]
    out = []
    match = flow.get("match") or {}
    for field in sorted(match):
        if field in table.match_excludes or not _allowed(field, table.match):
            out.append(f"table {table.table_id} matches no {field}")
    if table.eth_types != ANY:
        eth_type = match.get("eth_type")
        if eth_type is None:
            out.append(f"table {table.table_id} takes only a match carrying eth_type "
                       f"({', '.join(hex(e) for e in table.eth_types)}), and this one has none")
        elif eth_type not in table.eth_types:
            out.append(f"table {table.table_id} takes eth_type "
                       f"{', '.join(hex(e) for e in table.eth_types)}, not {hex(eth_type)}")
    applies = False
    for action in flow.get("actions") or []:
        kind = action.get("type")
        if kind in INSTRUCTION_TYPES:
            if not _allowed(kind, table.instructions):
                out.append(f"table {table.table_id} takes no {kind} instruction")
            if kind == "GOTO_TABLE" and not _allowed(action.get("table_id"), table.next_tables):
                out.append(f"table {table.table_id} cannot go to table {action.get('table_id')} "
                           f"(its next tables: {table.next_tables})")
            continue
        applies = True
        if not _allowed(kind, table.apply_actions):
            out.append(f"table {table.table_id} applies no {kind} action")
        elif kind == "SET_FIELD" and not _allowed(action.get("field"), table.apply_setfield):
            out.append(f"table {table.table_id} sets no {action.get('field')} field")
    if applies and not _allowed("APPLY_ACTIONS", table.instructions):
        out.append(f"table {table.table_id} takes no APPLY_ACTIONS instruction")
    return out


def place(flow: dict, tables: list) -> dict:
    """`{"ok": True, "table_id", "notes", "passed": [why each earlier table refused]}` for the
    first table that accepts *flow*, or `{"ok": False, "error"}` naming every table's refusal."""
    passed = []
    for table in sorted(tables, key=lambda t: t.table_id):
        why = refusals(table, flow)
        if why:
            passed.append("; ".join(why))
            continue
        notes = []
        if table.hardware is False:
            rate = (f", at {table.software_pps} packets a second" if table.software_pps
                    else "")
            notes.append(f"table {table.table_id} is a software table{rate} "
                         f"({table.source})")
        return {"ok": True, "error": "", "table_id": table.table_id, "notes": notes,
                "passed": passed}
    return {"ok": False, "error": "no table accepts this flow: " + " | ".join(passed),
            "passed": passed}
