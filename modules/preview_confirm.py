"""The preview-then-confirm contract: one builder, six parts, every time.

Stage 7.1 (NSOT_STAGE7_PLAN.md section 2, pattern 1). Deploy, restore,
onboarding, NetBox import and remove, and bulk intent each had their own
preview, and each dropped something: D4 (the deploy wizard drew the diff
standing in for the program), C27 (the restore preview never drew the lines
to add), the pending banner dropping its list. So there is ONE shape, built
here, and ONE renderer that draws it (`static/js/nmas_preview_confirm.js`).
Per-screen adapters would be six drifting implementations.

The six parts, in order:
1. **what**: what will happen, each target named;
2. **what_not**: what will NOT happen (residue that stays, targets skipped
   and why, what Remove will not touch);
3. **program**: per target, what is sent, byte for byte;
4. **operands**: per target, the values the confirm is bound to;
5. **gates**: per target, each gate by name with its state;
6. **confirm**: who is confirming, or why they may not.

**The six parts are a FLOOR, not a template** (the operator, 2026-09-27). A
part with nothing to say states that in a sentence, and `build()` refuses a
part that is empty without one: an empty section and a missing section read
the same to a person, and the difference is the whole point.

A gate is one of five states. `at_apply` is its own: a check made at apply
time (the device re-read, the credential compared) has NOT passed at plan
time, and drawing it as passed would be a claim nothing established. So is
`not_reached`: a check that did not run because an earlier step failed is
neither a pass nor "not applicable", and saying either would be a claim.
"""

import logging

log = logging.getLogger(__name__)

PARTS = ("what", "what_not", "program", "operands", "gates", "confirm")
GATE_STATES = ("pass", "fail", "not_applicable", "at_apply", "not_reached")


class PreviewIncomplete(ValueError):
    """A part is missing, or empty without saying so."""


def gate(name: str, state: str, detail: str = "") -> dict:
    if state not in GATE_STATES:
        raise PreviewIncomplete(f"gate {name!r}: unknown state {state!r}")
    return {"name": name, "state": state, "detail": detail}


def confirm_part(request, action: str = "confirm") -> dict:
    """Who is confirming, from the SAME functions the gate uses, so the
    screen cannot disagree with what apply will do."""
    from modules import identity

    ident = identity.identify(request)
    allowed, reason = identity.may(ident, action)
    if allowed and ident.is_identified:
        return {"may": True, "actor": ident.actor, "kind": ident.kind,
                "statement": f"You are confirming as {ident.actor}."}
    return {"may": bool(allowed), "actor": ident.actor if ident.is_identified else "",
            "kind": ident.kind,
            "statement": ("You may not confirm: " + (reason or "no verified person"))
            if not allowed else f"You are confirming as {ident.actor or 'an unverified caller'}."}


def build(*, action: str, summary: str, targets: list, what_not: list,
          nothing_left_out: str, confirm: dict, explain: dict = None) -> dict:
    """The preview. *targets* is ``[{"name", "state", "selectable",
    "select_data", "program": {"lines", "dangerous", "authorised", "none",
    "notes"}, "operands": [{"name", "value"}], "gates": [gate(...)]}]``;
    *what_not* is ``[{"target", "kind", "text", "lines"}]``."""
    if not summary:
        raise PreviewIncomplete("part 1 (what) has no summary")
    if not targets:
        raise PreviewIncomplete("part 1 (what) names no target")
    if not what_not and not nothing_left_out:
        raise PreviewIncomplete("part 2 (what_not) is empty and does not say so")
    for t in targets:
        name = t.get("name") or "?"
        program = t.get("program") or {}
        if not program.get("lines") and not program.get("none"):
            raise PreviewIncomplete(f"part 3 (program) for {name} is empty and does not say so")
        if not t.get("operands"):
            raise PreviewIncomplete(f"part 4 (operands) for {name} is empty")
        if not t.get("gates"):
            raise PreviewIncomplete(f"part 5 (gates) for {name} is empty")
    if not (confirm or {}).get("statement"):
        raise PreviewIncomplete("part 6 (confirm) has no statement")
    explain = explain or {}
    unknown = set(explain) - set(PARTS)
    if unknown:
        raise PreviewIncomplete(f"explanations for no such part: {sorted(unknown)}")
    return {"action": action, "parts": list(PARTS),
            # {part: [{"concept", "text"}]}: a concept taught at the point of
            # action (section 4), drawn by the renderer in that part.
            "explain": explain,
            "what": {"summary": summary,
                     "targets": [{"name": t["name"], "state": t.get("state", ""),
                                  "selectable": bool(t.get("selectable")),
                                  "select_data": t.get("select_data") or {}}
                                 for t in targets]},
            "what_not": {"items": what_not, "none": "" if what_not else nothing_left_out},
            "targets": [{"name": t["name"], "program": t["program"],
                         "operands": t["operands"], "gates": t["gates"]}
                        for t in targets],
            "confirm": confirm}


#: What the apply compares, stated exactly (register C78). This gate read
#: "device unchanged since capture: re-read at apply", and the apply re-reads
#: the STORED capture, never the device: the pipeline reads the device at its
#: pre-change snapshot and compares it with nothing. A sentence claiming a
#: check the code does not make is the finding, so it says what is checked
#: and what is not.
CAPTURE_GATE = "capture unchanged since this preview"
CAPTURE_GATE_DETAIL = ("the stored capture is re-read at apply, and a change to it "
                       "refuses this device. The DEVICE is not compared with it: a "
                       "change made on the device since its capture is not detected "
                       "here, so save its golden first")


def _deploy_gates(d: dict, failed: str) -> list:
    """One gate per reason a deploy can be refused, by name: the same
    conditions `blocking_reasons` states as sentences, plus the two checked
    at apply. A device whose artifact could not be built reached none."""
    if "template" not in d:
        why = "; ".join(d.get("blocking_reasons") or []) or "not built"
        return [gate("artifact built", "fail", why)] + [
            gate(n, "not_reached", "nothing was built to check")
            for n in ("template approved", "committed intent", "template reproduces the device",
                      "every line modelled or acknowledged", "printable ASCII",
                      "dangerous lines", "rollback block")]
    gaps = d.get("template_gaps") or {}
    gap_words = [f"{n} {w}" for n, w in ((gaps.get("missing"), "line(s) not reproduced"),
                                         (gaps.get("extra"), "line(s) invented"),
                                         (gaps.get("reordered"), "section(s) reordered"))
                 if n]
    fidelity = (f"fidelity {d.get('round_trip_fidelity', 0)}%, modelled "
                f"{d.get('modeled_coverage', 0)}%")
    excluded = d.get("excluded_unrenderable") or []
    if excluded:
        fidelity += f", {len(excluded)} line(s) excluded as unrenderable"
    unmodeled = d.get("unmodeled") or []
    unacked = d.get("unacknowledged") or []
    stale = d.get("stale_acknowledgements") or []
    unsendable = d.get("unsendable") or []
    dangerous = d.get("dangerous") or []
    rolled = d.get("rolled_back")
    built = [
        gate("template approved", "pass" if d.get("template_approved") else "fail",
             f"template {d.get('template')}" + ("" if d.get("template_approved")
                                                 else ": its current version is not approved")),
        gate("committed intent", "fail" if d.get("bootstrap") else "pass",
             "none committed: review and commit extracted host_vars first"
             if d.get("bootstrap") else ""),
        gate("template reproduces the device", "fail" if gap_words else "pass",
             "; ".join(gap_words + [fidelity])),
        gate("every line modelled or acknowledged", "fail" if (unacked or stale) else "pass",
             "; ".join(filter(None, [
                 f"{len(unacked)} unmodelled line(s) not acknowledged" if unacked else "",
                 f"{len(stale)} stale acknowledgement(s)" if stale else "",
                 f"{len(unmodeled)} unmodelled line(s), all acknowledged"
                 if unmodeled and not unacked else ""]))),
        gate("printable ASCII", "fail" if unsendable else "pass",
             "; ".join(unsendable[:2])),
        gate("dangerous lines",
             "not_applicable" if not dangerous
             else "pass" if d.get("authorisation_ok") else "fail",
             "" if not dangerous else (d.get("authorisation_error")
                                       or f"{len(dangerous)} authorised")),
        gate("rollback block", "fail" if rolled else "pass",
             f"rolled back at {(rolled or {}).get('at', 'an earlier time')}"
             + (f" ({rolled['reason']})" if (rolled or {}).get("reason") else "")
             if rolled else ""),
    ]
    if failed:
        built.insert(0, gate("program built", "fail", failed))
    return built + [
        gate(CAPTURE_GATE, "at_apply", CAPTURE_GATE_DETAIL),
        gate("credential unchanged", "at_apply",
             "compared with the capture at apply, before anything connects")]


def deploy_preview(devices: list, request) -> dict:
    """The deploy plan's per-device entries, as the six parts."""
    targets, what_not = [], []
    for d in devices:
        name = d.get("device", "?")
        blocked = not d.get("deployable")
        unauthorised = bool(d.get("dangerous")) and d.get("authorisation_ok") is False
        failed = d.get("refused") or d.get("error") or ""
        state = ("blocked" if blocked else "refused" if failed
                 else "not_authorised" if unauthorised else "deployable")
        commands = d.get("commands") or []
        if blocked:
            none = "Nothing is sent to this device: it is blocked (see its gates)."
        elif failed:
            none = f"Nothing is sent to this device: {failed}"
        else:
            none = "Nothing will be sent: the device already has every line."
        notes = []
        a = d.get("attribution")
        if a and (d.get("to_add") or []):
            notes.append({"title": "Where the added lines come from"
                                   + ("" if a.get("attributable", True)
                                      else " (could not be attributed)"),
                          "intent_commit": a.get("intent_commit", ""),
                          "intent_subject": a.get("intent_subject", ""),
                          "note": a.get("note", ""),
                          "from_this_edit": a.get("from_this_edit") or [],
                          "pre_existing": a.get("pre_existing") or []})
        if d.get("removal_warnings"):
            what_not.append({"target": name, "kind": "residue",
                             "text": "On the device but not in intent: will NOT be "
                                     "removed (merge-only). Remove them by hand, or "
                                     "adopt them into the template.",
                             "lines": list(d.get("residue_in_context")
                                           or d["removal_warnings"])})
        if blocked:
            reasons = "; ".join(d.get("blocking_reasons") or []) or "not deployable"
            what_not.append({"target": name, "kind": "blocked",
                             "text": f"Not sent: {reasons}", "lines": []})
        if failed:
            what_not.append({"target": name, "kind": "refused",
                             "text": f"Not sent: {failed}", "lines": []})
        drift = d.get("intent_drift") or {}
        operands = [
            {"name": "capture hash", "value": d.get("capture_hash") or "none"},
            {"name": "command hash", "value": d.get("command_hash") or "none"},
            {"name": "intent commit", "value": ((a or {}).get("intent_commit") or "none")[:12]},
            {"name": "authorised lines", "value": str(len(d.get("authorised") or []))},
            {"name": "template", "value": d.get("template") or "none"},
            {"name": "platform", "value": d.get("platform") or "unknown"},
            {"name": "intent vs capture",
             "value": (f"{drift.get('adds', 0)} to add, {drift.get('removes', 0)} absent "
                       f"from intent, {drift.get('reordered', 0)} reordered")
             if drift.get("differs") else "no difference"},
            {"name": "lines already on the device", "value": str(d.get("unchanged_count", 0))},
            {"name": "secrets masked in this preview",
             "value": ", ".join(d.get("masked_refs") or []) or "none"},
        ]
        targets.append({
            "name": name, "state": state,
            "selectable": not (blocked or unauthorised or failed),
            "select_data": {"hash": d.get("capture_hash") or "",
                            "command-hash": d.get("command_hash") or ""},
            "program": {"lines": commands, "dangerous": d.get("dangerous") or [],
                        "authorised": d.get("authorised") or [],
                        "authorisation_error": d.get("authorisation_error") or "",
                        "none": "" if commands else none, "notes": notes},
            "operands": operands, "gates": _deploy_gates(d, failed)})
    n = len(targets)
    ready = sum(1 for t in targets if t["selectable"])
    return build(
        action="deploy",
        summary=(f"Deploy to the devices you tick, merge-only: {ready} of {n} can be "
                 "deployed now, and for each, exactly the program shown is sent, in order."),
        targets=targets, what_not=what_not,
        nothing_left_out=("Nothing: every planned device can be sent, and no line on "
                          "any device lies outside intent."),
        confirm=confirm_part(request),
        explain={
            "what_not": [{"concept": "merge-only",
                          "text": "Merge-only: lines are added or replaced. A line on the "
                                  "device that intent does not mention is never removed; "
                                  "it is listed here as not removed."}],
            "confirm": [{"concept": "confirm-by-hash",
                         "text": "You are confirming this exact program. If the device's "
                                 "stored capture or its intent moves before you apply, the "
                                 "apply is refused for that device and nothing is sent to "
                                 "it."}]})


#: What a restore's intent half will do, in words (`_intent_preview`'s actions).
_INTENT_WORDS = {
    "restore": "set back to this ref's version by a forward commit",
    "un_onboard": "REMOVED by a forward commit (un-onboarding)",
    "unchanged": "already matches this ref; nothing is committed for it",
    "none": "none at this ref",
}


def _restore_gates(d: dict, failed: str) -> list:
    """The restore's OWN gates, from `RestoreTarget.checks` (the list its
    refusal is computed from), plus what the preview and the apply add.
    Never the deploy's template gates: a restore has no template."""
    out = [gate(c.get("name", "?"), c.get("state", "not_reached"), c.get("detail", ""))
           for c in d.get("checks") or []]
    if not out:
        out = [gate("restore target built", "fail",
                    "; ".join(d.get("blocking_reasons") or []) or "not built")]
    action = (d.get("intent") or {}).get("action", "none")
    # build_targets() refuses a ref whose intent does not round-trip through
    # today's template or names a secret the store lacks, so a target here
    # passed it. An un-onboarding carries no intent, so it was not checked.
    out.append(gate("this ref's intent usable today",
                    "pass" if action in ("restore", "unchanged") else "not_applicable",
                    "round-trips through today's template; every secret it names is "
                    "held" if action in ("restore", "unchanged")
                    else "no intent at this ref to check"))
    dangerous = d.get("dangerous") or []
    out.append(gate("dangerous lines",
                    "not_applicable" if not dangerous
                    else "pass" if d.get("authorisation_ok") else "fail",
                    "" if not dangerous else (d.get("authorisation_error")
                                              or f"{len(dangerous)} authorised")))
    if failed and d.get("deployable"):
        out.insert(0, gate("program built", "fail", failed))
    return out + [gate(CAPTURE_GATE, "at_apply", CAPTURE_GATE_DETAIL)]


def restore_preview(devices: list, skipped: list, *, ref: str, summary: str,
                    scope: str, request) -> dict:
    """The restore preview's per-device entries, as the six parts (7.1).

    Its own adapter over the same builder, for the reason `RestoreTarget`
    has its own short list of blocking reasons: a restore re-applies stored
    configuration, so the deploy's template gates do not apply, and drawing
    them would be a claim about a template nobody used.
    """
    targets, what_not = [], []
    for d in devices:
        name = d.get("device", "?")
        blocked = not d.get("deployable")
        unauthorised = bool(d.get("dangerous")) and d.get("authorisation_ok") is False
        failed = "" if blocked else (d.get("error") or "")
        state = ("blocked" if blocked else "refused" if failed
                 else "not_authorised" if unauthorised else "deployable")
        commands = d.get("commands") or []
        if blocked:
            none = "Nothing is sent to this device: it is blocked (see its gates)."
        elif failed:
            none = f"Nothing is sent to this device: {failed}"
        else:
            none = ("Nothing will be sent: the device already matches this ref. It "
                    "is still read back at apply, so the baseline can count it as "
                    "measured.")
        notes = []
        replace = d.get("replace") or []
        if replace and commands:
            notes.append({"title": "What these lines replace on the device",
                          "lines": [f"{str(r.get('old', '')).strip()}  ->  "
                                    f"{str(r.get('new', '')).strip()}" for r in replace]})
        if d.get("residue"):
            what_not.append({"target": name, "kind": "residue",
                             "text": "On the device but not in this ref: will NOT be "
                                     "removed (a re-apply adds and replaces; it never "
                                     "removes). Remove them by hand if the ref is "
                                     "what the device should be.",
                             "lines": list(d.get("residue_in_context") or d["residue"])})
        excluded = d.get("excluded_unrenderable") or []
        if excluded:
            what_not.append({"target": name, "kind": "excluded",
                             "text": "Blocks in the stored config that a re-apply cannot "
                                     "send at all (certificates, licence UDI, banners). "
                                     "If one of these drifted, this does not restore it.",
                             "lines": [str(x) for x in excluded]})
        if blocked:
            reasons = "; ".join(d.get("blocking_reasons") or []) or "not deployable"
            what_not.append({"target": name, "kind": "blocked",
                             "text": f"Not sent: {reasons}", "lines": []})
        if failed:
            what_not.append({"target": name, "kind": "refused",
                             "text": f"Not sent: {failed}", "lines": []})
        intent = d.get("intent") or {}
        operands = [
            {"name": "ref", "value": ref},
            {"name": "capture hash", "value": d.get("capture_hash") or "none"},
            {"name": "command hash", "value": d.get("command_hash") or "none"},
            {"name": "authorised lines", "value": str(len(d.get("authorised") or []))},
            {"name": "platform", "value": d.get("platform") or "unknown"},
            {"name": "committed intent",
             "value": _INTENT_WORDS.get(intent.get("action", "none"),
                                        intent.get("detail") or "unknown")},
            {"name": "lines already on the device", "value": str(d.get("unchanged_count", 0))},
        ]
        targets.append({
            "name": name, "state": state,
            "selectable": not (blocked or unauthorised or failed),
            "select_data": {"hash": d.get("capture_hash") or "",
                            "command-hash": d.get("command_hash") or ""},
            "program": {"lines": commands, "dangerous": d.get("dangerous") or [],
                        "authorised": d.get("authorised") or [],
                        "authorisation_error": d.get("authorisation_error") or "",
                        "none": "" if commands else none, "notes": notes},
            "operands": operands, "gates": _restore_gates(d, failed)})
    for s in skipped or []:
        what_not.append({"target": s.get("hostname") or "(the ref)", "kind": "skipped",
                         "text": "Not touched: " + s.get("reason", "skipped")
                                 + (f". {s['detail']}" if s.get("detail") else ""),
                         "lines": []})
    if scope:
        what_not.append({"target": "this restore", "kind": "scope", "text": scope,
                         "lines": []})
    if not targets:
        # Every device skipped: the parts still say so, rather than a builder
        # refusal reading as a crash.
        targets.append({"name": "(no device)", "state": "blocked", "selectable": False,
                        "program": {"lines": [], "none": "Nothing is sent: no device "
                                                         "in this restore can be "
                                                         "re-applied."},
                        "operands": [{"name": "ref", "value": ref}],
                        "gates": [gate("a device to restore", "fail",
                                       "every device was skipped; see what will not "
                                       "happen")]})
    return build(
        action="restore",
        summary=summary or f"Re-apply {ref}.",
        targets=targets, what_not=what_not,
        nothing_left_out="Nothing: every device can be re-applied, and nothing on "
                         "any device lies outside this ref.",
        confirm=confirm_part(request),
        explain={
            "what_not": [{"concept": "merge-only",
                          "text": "A re-apply adds and replaces. A line on the device "
                                  "that the ref does not mention is never removed; it is "
                                  "listed here as not removed."}],
            "confirm": [{"concept": "confirm-by-hash",
                         "text": "You are confirming this exact program for every "
                                 "device marked deployable. If a device's stored capture "
                                 "moves before you apply, it is skipped and nothing is "
                                 "sent to it."}]})


# ---------------------------------------------------------------------------
# The RESULT half (7.1 step 2): what happened, drawn the way what-will-happen
# already is.
# ---------------------------------------------------------------------------

#: The parts of a result, mirroring the preview's.
RESULT_PARTS = ("happened", "did_not", "sent", "checks", "record", "not_watched")

#: The level is COMPUTED here and only drawn by the renderer, because colour is
#: part of the result (the operator, 2026-09-27): a green result on a partial
#: success is a false statement in a different medium. ``success`` needs every
#: target done, every sent program matching its confirmed hash, every check
#: that ran passing, and the record written.
RESULT_LEVELS = ("success", "partial", "failed", "nothing")

OUTCOME_WORDS = {
    "deployed": "done",
    "refused": "refused: nothing was sent",
    "skipped_drifted": "skipped: its capture moved since the preview, nothing was sent",
    "failed": "failed",
    "unattempted": "not attempted",
    "skipped_not_selected": "not selected",
}


class ResultIncomplete(ValueError):
    """A result part is missing, or empty without saying so."""


def build_result(*, action: str, level: str, summary: str, targets: list,
                 did_not: list, nothing_left_out: str, record: dict,
                 not_watched: str) -> dict:
    """The result. Floors, as the preview's: a part with nothing to say states
    it, because an empty section and a missing one read the same."""
    if level not in RESULT_LEVELS:
        raise ResultIncomplete(f"unknown level {level!r}")
    if not summary:
        raise ResultIncomplete("part 1 (happened) has no summary")
    if not did_not and not nothing_left_out:
        raise ResultIncomplete("part 2 (did_not) is empty and does not say so")
    for t in targets:
        sent = t.get("sent") or {}
        if not sent.get("lines") and not sent.get("none"):
            raise ResultIncomplete(f"part 3 (sent) for {t.get('name')} is empty and does not say so")
        checks = t.get("checks") or {}
        if not checks.get("ran") and not checks.get("why"):
            raise ResultIncomplete(f"part 4 (checks) for {t.get('name')} neither ran nor says why")
    if not (record or {}).get("statement"):
        raise ResultIncomplete("part 5 (record) has no statement")
    if not not_watched:
        raise ResultIncomplete("part 6 (not_watched) is empty")
    return {"action": action, "parts": list(RESULT_PARTS), "level": level,
            "happened": {"summary": summary,
                         "targets": [{"name": t["name"], "outcome": t.get("outcome", ""),
                                      "words": t.get("words", "")} for t in targets]},
            "did_not": {"items": did_not, "none": "" if did_not else nothing_left_out},
            "targets": [{"name": t["name"], "sent": t["sent"], "checks": t["checks"],
                         "rollback": t.get("rollback") or {}, "stage": t.get("stage", ""),
                         "reason": t.get("reason", ""), "outcome": t.get("outcome", "")}
                        for t in targets],
            "record": record, "not_watched": not_watched}


def result_level(rows: list, receipt_ok: bool, breaker_tripped: bool = False) -> str:
    """``success`` only when nothing is left to qualify it."""
    if not rows:
        return "nothing"
    done = [r for r in rows if r.get("outcome") == "deployed"]
    if not done:
        return "failed"
    clean = (len(done) == len(rows) and receipt_ok and not breaker_tripped
             and all(r.get("matches_confirmed") is True for r in done if r.get("sent"))
             and all((r.get("checks") or {}).get("ok") is True
                     for r in done if (r.get("checks") or {}).get("ran")))
    return "success" if clean else "partial"


def operation_result(rows: list, report: dict, receipt_status: dict, action: str,
                     from_receipt: dict = None) -> dict:
    """A deploy's or restore's result, built FROM THE RECEIPT ROWS the apply
    has just written, so the screen and the record are one computation.
    Every field is already masked in the rows (`receipts.rows_for`)."""
    from modules.nsot.receipts import FOLLOW_UP_NOT_BUILT

    verb = {"deploy": "deployed"}.get(action, "re-applied")
    receipt_ok = bool((receipt_status or {}).get("ok"))
    targets, did_not = [], []
    for r in rows:
        name = r.get("device", "?")
        outcome = r.get("outcome", "")
        words = OUTCOME_WORDS.get(outcome, outcome.replace("_", " "))
        sent = r.get("sent")
        matches = r.get("matches_confirmed")
        targets.append({
            "name": name, "outcome": outcome, "words": words,
            "stage": r.get("stage", ""), "reason": r.get("reason", ""),
            "sent": {"lines": r.get("program") if sent else [],
                     "program_hash": r.get("program_hash", ""),
                     "confirmed_hash": r.get("confirmed_hash") or "",
                     "matches": matches,
                     "match_words": ("matches the program you confirmed" if matches is True
                                     else "DOES NOT MATCH the program you confirmed"
                                     if matches is False
                                     else "no confirmed program to compare with"),
                     "none": "" if sent else (r.get("reason") or "Nothing was sent.")},
            "checks": r.get("checks") or {"ran": False, "why": "no check was recorded"},
            "rollback": r.get("rollback") or {},
        })
        if outcome != "deployed":
            did_not.append({"target": name, "kind": outcome,
                            "text": f"{words}" + (f": {r['reason']}" if r.get("reason") else ""),
                            "lines": []})
        not_undone = (r.get("rollback") or {}).get("not_undone") or []
        if not_undone:
            did_not.append({"target": name, "kind": "not_undone",
                            "text": "Rejected by the device when pushed, so not undone by the "
                                    "rollback: never applied.", "lines": list(not_undone)})
    if report.get("breaker_tripped"):
        did_not.append({"target": "this batch", "kind": "breaker",
                        "text": f"Stopped early: {report.get('breaker_reason', '')}", "lines": []})
    for s in report.get("skipped") or []:
        did_not.append({"target": s.get("hostname") or "(the ref)", "kind": "skipped",
                        "text": "Not touched: " + (s.get("reason") or "skipped"), "lines": []})

    golden = report.get("golden") or {}
    tags = list(golden.get("tags") or [])
    baseline = next((t for t in tags if t.startswith("baseline/")), "")
    commit = golden.get("commit", "")
    statement = (f"Golden commit {commit[:12]} records the captures of "
                 f"{', '.join(golden.get('devices') or []) or 'no device'}."
                 if commit else "No golden commit: nothing succeeded, or no capture changed.")
    statement += (f" Baseline {baseline} was tagged." if baseline else
                  " No baseline tag: " + "; ".join(golden.get("baseline_reasons") or
                                                   ["not earned"]) + ".")
    if receipt_ok:
        statement += (f" Receipt: {receipt_status.get('written', 0)} device row(s) recorded, "
                      "each with the program sent and the checks that ran.")
    else:
        statement += (" RECEIPT NOT WRITTEN: " + str((receipt_status or {}).get("error") or
                                                     "no receipt was reported")
                      + ". The change happened and its record did not.")
    if from_receipt:
        # Read back LATER from the receipt store (step 3): the receipt names
        # the commit and not its tags, so the record says where it was read
        # from rather than claiming no baseline was taken.
        statement = (f"Read back from the receipt recorded {from_receipt.get('at', '?')} by "
                     f"{from_receipt.get('actor') or 'an unrecorded actor'}"
                     + (f", golden commit {commit[:12]}" if commit else ", no golden commit")
                     + ". Its tags are in the golden history.")
    record = {"commit": commit, "tags": tags, "baseline": baseline,
              "receipt": {"ok": receipt_ok, "written": (receipt_status or {}).get("written", 0),
                          "error": (receipt_status or {}).get("error", "")},
              "statement": statement}

    done = sum(1 for r in rows if r.get("outcome") == "deployed")
    if from_receipt and from_receipt.get("device"):
        # One device's row of a batch: never "every device appears here".
        summary = (f"{from_receipt['device']}: "
                   + (OUTCOME_WORDS.get(rows[0].get("outcome", ""), "") if rows else "no row")
                   + f". One row of batch {from_receipt.get('batch_id') or '?'}; the other "
                     "devices in it are in their own histories.")
    else:
        summary = (f"{done} of {len(rows)} device(s) {verb}. {len(rows)} device(s) accounted "
                   "for: every device in the batch appears here.")
    return build_result(
        action=action,
        level=result_level(rows, receipt_ok, bool(report.get("breaker_tripped"))),
        summary=summary,
        targets=targets, did_not=did_not,
        nothing_left_out="Nothing: every device was done, and the rollback had nothing to leave.",
        record=record, not_watched=FOLLOW_UP_NOT_BUILT["why"])


def receipt_history(rows: list, device: str = "") -> list:
    """The receipt store read back as results (7.1 step 3): one per batch,
    newest first, each drawn by the same component as the result shown at
    apply. ``rows`` come from `receipts.read()` and are already masked."""
    batches, order = {}, []
    for r in rows:
        key = r.get("batch_id") or f"{r.get('at', '')}|{r.get('action', '')}"
        if key not in batches:
            batches[key] = []
            order.append(key)
        batches[key].append(r)
    out = []
    for key in order:
        group = batches[key]
        first = group[0]
        commit = next((r.get("golden_commit") for r in group if r.get("golden_commit")), "")
        report = {"golden": {"commit": commit,
                             "devices": [r.get("device") for r in group if r.get("golden_commit")]}}
        meta = {"at": first.get("at", ""), "actor": first.get("actor", ""),
                "batch_id": first.get("batch_id", ""), "device": device}
        out.append({"batch_id": first.get("batch_id", ""), "at": first.get("at", ""),
                    "action": first.get("action", ""), "actor": first.get("actor", ""),
                    "source_ref": first.get("source_ref", ""),
                    "result": operation_result(group, report, {"ok": True, "written": len(group)},
                                               "deploy" if first.get("action") == "deploy"
                                               else "restore", from_receipt=meta)})
    return out
