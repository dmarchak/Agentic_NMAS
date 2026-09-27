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
