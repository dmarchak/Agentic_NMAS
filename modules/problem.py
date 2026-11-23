"""THE problem schema (the operator's R4, 2026-11-14; docs/MERCURY_CHARTER.md, "R4. Incidents are
problems, not signals"): syslog lines, alerts, lost streams and reads are EVIDENCE; Mercury
classifies evidence into a PROBLEM and titles the incident by it, the alerts listed under it as
evidence. One module defines the problem's fields; the BLUF table (`modules/bluf.py`) is keyed
by a problem's condition and uses only these fields (tests/test_bluf.py parses it), and the saved
fixes' match (C3696) and G7 import it later: a saved script matches on these fields, never an
alert's name or a raw line.

**A problem** (`Problem`, `FIELDS`):
- ``device``: the device it is on, by its name (a label: its identity is the incident's);
- ``object``: what on the device, in words ("telemetry streams 101 and 102", "an interface");
- ``condition``: what is wrong with it, one of `CONDITIONS` (the problem's kind);
- ``cause``: why, when Mercury knows it, else ``""`` (never guessed);
- ``port_role``: the role of the port it is on (``uplink``, ``access``, ``management``), when
  the problem is a port's and its role is known, else ``""``;
- ``affected``: who or what is affected, in words, when known, else ``""``;
- ``cause_cleared``: the name of the check that says the cause has cleared (a read Mercury
  makes before and after a fix), one of `CLEARED_CHECKS`.

**Classification** (`classify`): from the incident's own records, the most specific first: a lost
telemetry stream (`heal.diagnose_stream.target_from`), else the fix kind the heal's decision
classified the departure as (`heal.kinds.TIER`), else what its first trigger was
(`heal.incidents.CAUSE_KINDS`, `SYMPTOM_KINDS`). `CONDITION_OF` maps every declared signal kind to
its condition, so a signal Mercury raises always has its problem kind; an alert Mercury has not
classified is ``alert_unclassified`` (the AI names its problem in these same fields). Reads only
what it is handed.
"""

from dataclasses import asdict, dataclass

#: The problem's fields, exactly (`Problem`). G7 (C3712; the operator's walk item 3,
#: 2026-11-15) appends ``cleared`` (whether the cause has cleared: ``true``, ``false`` or
#: ``unknown``, `CLEARED`) and ``cleared_at`` (when that was read, an ISO instant).
FIELDS = ("device", "object", "condition", "cause", "port_role", "affected", "cause_cleared",
          "cleared", "cleared_at")
#: Whether a problem's cause has cleared, as ``cleared`` says it.
CLEARED = ("true", "false", "unknown", "")
#: What a saved script matches on (R4, the operator, 2026-11-15): the classified problem's
#: fields, never an alert's name or a raw line (C3696 builds the match on these).
MATCH_FIELDS = ("condition", "cause", "port_role", "cleared")
#: The checks a problem's cause clears by, each a read Mercury makes. G7 appends an
#: err-disabled port's two (`heal.errdisable.CLEARED_CHECKS`).
CLEARED_CHECKS = ("stream_back", "neighbour_up", "matches_intent", "link_up", "port_passing",
                  "session_up", "alert_resolved", "logs_quiet", "", "no_bpdu_since",
                  "violator_gone")
#: The lost telemetry stream's signal kind.
LOST_STREAM = "lost_stream"
#: An err-disabled switch port's signal kind (G7, `heal.errdisable.SIGNAL`): classified from
#: the device's err-disable line and the Interface down alert, kept on the incident's record.
ERR_DISABLE = "err_disable"

#: Each condition (a problem's kind): its default object in words, and its cause-cleared check.
CONDITIONS = {
    "telemetry_lost": ("its telemetry", "stream_back"),
    "neighbour_down": ("a routing neighbour", "neighbour_up"),
    "neighbour_dropped": ("a routing neighbour", "neighbour_up"),
    "router_id_duplicate": ("its OSPF router ID", "logs_quiet"),
    "changed_outside_mercury": ("its configuration", "matches_intent"),
    "departs_from_golden": ("its configuration", "matches_intent"),
    "alert_unclassified": ("an alert", "alert_resolved"),
    "line_missing": ("a line its intent needs", "matches_intent"),
    "line_changed": ("a line of its configuration", "matches_intent"),
    "line_added": ("a line its intent does not have", "matches_intent"),
    "interface_shut": ("an interface", "link_up"),
    "security_broke_neighbour": ("a security change", "neighbour_up"),
    "needs_process_reset": ("a change", "matches_intent"),
    "qos_changed": ("its QoS policy", "matches_intent"),
    "secret_changed": ("a password or key line", "matches_intent"),
    "acl_changed": ("a security ACL", "matches_intent"),
    "security_changed": ("a security control", "matches_intent"),
    "link_down": ("a link", "link_up"),
    "cause_unknown": ("something", "alert_resolved"),
    "account_changed": ("an account or sign-in setting", "matches_intent"),
    "management_path_changed": ("Mercury's path to it", "matches_intent"),
    "multi_device_change": ("a change spanning devices", "matches_intent"),
    "port_stuck": ("a port", "port_passing"),
    "bgp_session_stuck": ("a BGP session", "session_up"),
    "ospf_neighbour_stuck": ("an OSPF neighbour", "neighbour_up"),
    "port_flapping": ("a port", "port_passing"),
    # G7 (C3712): a switch port err-disabled by BPDU guard or port security; its check is the
    # cause's own (`heal.errdisable.CLEARED_CHECKS`), set by the classification.
    "err_disabled": ("a switch port", ""),
    # The err-disable syslog trigger (7cc49a1b) before its port's confirming read: the device
    # said a port was err-disabled, and `heal.errdisable.problem_fields` has not confirmed it
    # yet, so it is classified as reported, never as `err_disabled` (no saved fix matches it,
    # `MATCHABLE`).
    "err_disable_reported": ("a switch port", ""),
}

#: The conditions a saved fix's match may name: every condition but a report awaiting its
#: confirming read, so no fix is offered, or fires in Auto, on an unconfirmed classification.
UNCONFIRMED = ("err_disable_reported",)
MATCHABLE = tuple(c for c in CONDITIONS if c not in UNCONFIRMED)

#: Every signal kind Mercury raises, to its problem's condition: the heal's trigger kinds, the
#: lost stream, and the fix kinds the decision classifies a departure as.
CONDITION_OF = {
    LOST_STREAM: "telemetry_lost",
    "adjacency": "neighbour_down", "adjacency_log": "neighbour_dropped",
    "duplicate_router_id": "router_id_duplicate", "config_change": "changed_outside_mercury",
    "drift": "departs_from_golden", "alert": "alert_unclassified",
    "missing_line": "line_missing", "changed_line": "line_changed", "added_line": "line_added",
    "admin_down": "interface_shut", "security_revert": "security_broke_neighbour",
    "process_reset": "needs_process_reset", "qos_policy": "qos_changed",
    "secret_added_back": "secret_changed", "security_acl": "acl_changed",
    "security_control": "security_changed", "physical": "link_down",
    "unknown_cause": "cause_unknown", "credentials": "account_changed",
    "management_path": "management_path_changed", "multi_device": "multi_device_change",
    "port_bounce": "port_stuck", "session_clear": "bgp_session_stuck",
    "ospf_reset": "ospf_neighbour_stuck", "dampening_proposal": "port_flapping",
    ERR_DISABLE: "err_disabled",
    "errdisable": "err_disable_reported",
}


@dataclass(frozen=True)
class Problem:
    device: str
    object: str
    condition: str
    cause: str = ""
    port_role: str = ""
    affected: str = ""
    cause_cleared: str = ""
    cleared: str = ""
    cleared_at: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def declared_signals() -> tuple:
    """Every signal kind Mercury raises, read from the code's own declarations: the heal's
    trigger kinds, the lost stream, and the decision's fix kinds."""
    from modules.heal import incidents, kinds

    return (tuple(incidents.CAUSE_KINDS) + tuple(incidents.SYMPTOM_KINDS) + (LOST_STREAM,)
            + tuple(kinds.TIER) + (ERR_DISABLE,))


def _listed(items) -> str:
    items = [str(i) for i in items]
    return " and ".join([", ".join(items[:-1]), items[-1]]) if len(items) > 1 else (
        items[0] if items else "")


def _object(condition: str, record: dict, triggers: list) -> str:
    """The problem's object in words, from the evidence where it names one, else the
    condition's default (`CONDITIONS`)."""
    from modules.heal import diagnose_stream

    if condition == "telemetry_lost":
        subs = (diagnose_stream.target_from(record) or {}).get("subscriptions") or []
        if subs:
            return (f"telemetry stream{'s' if len(subs) != 1 else ''} {_listed(subs)}")
    if condition in ("neighbour_down", "neighbour_dropped"):
        t = next((t for t in triggers if t.get("peer") or t.get("neighbor")
                  or t.get("related")), {})
        peer = t.get("peer") or t.get("neighbor") or ", ".join(
            d for d in t.get("related") or [] if d != record.get("device"))
        if peer:
            return f"its {t.get('protocol') or 'routing'} neighbour {peer}"
    return CONDITIONS.get(condition, ("something", ""))[0]


def classify(found: dict) -> Problem:
    """The problem the incident `incident_page.resolve` *found* is (the module's docstring);
    ``condition`` ``""`` when nothing it holds names one."""
    from modules.heal import diagnose_stream, errdisable

    record, entry = found.get("incident") or {}, found.get("entry") or {}
    device = record.get("device") or entry.get("device") or ""
    # G7 (C3712): an err-disabled port its own evidence classified (`errdisable.classify`, kept
    # on the record by `errdisable.reclassify_step`) is the most specific of all.
    port = errdisable.problem_fields(device, errdisable.of_record(record))
    if port:
        return Problem(**port)
    triggers =[t for t in record.get("triggers") or entry.get("triggers") or []
                if isinstance(t, dict)]
    signal = ""
    if diagnose_stream.target_from(record):
        signal = LOST_STREAM
    elif (entry.get("kind") or "") in CONDITION_OF:
        signal = entry["kind"]
    elif triggers and (triggers[0].get("kind") or "") in CONDITION_OF:
        signal = triggers[0]["kind"]
    condition = CONDITION_OF.get(signal, "")
    cause = entry.get("cause") if isinstance(entry.get("cause"), str) else ""
    return Problem(device=device, object=_object(condition, record, triggers),
                   condition=condition, cause=cause or "",
                   cause_cleared=CONDITIONS.get(condition, ("", ""))[1])


def evidence(found: dict) -> list:
    """The signals the problem was classified from, as evidence under it: ``[{"kind", "words",
    "at"}]``, each trigger's own words (`said.symptom_words` for a symptom, the kind's words for
    a cause) and its time as an ISO instant (the page localises it)."""
    from modules.heal import incidents, said

    record = found.get("incident") or {}
    device = record.get("device") or ""
    out = []
    for t in [t for t in record.get("triggers") or [] if isinstance(t, dict)][:10]:
        kind = t.get("kind") or ""
        words = (said.symptom_words(t, device) if kind in incidents.SYMPTOM_KINDS
                 else incidents.KIND_WORDS.get(kind) or t.get("words") or kind)
        out.append({"kind": kind, "words": words, "at": t.get("at") or ""})
    # G7 (the operator's walk item 2, 2026-11-15): an err-disabled port's device confirmation
    # read (which port, which cause, when it was read) and the lines it was classified from.
    from modules.heal import errdisable
    return errdisable.evidence_rows(record) + out
