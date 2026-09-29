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
    # No `actor` field: the apply records the VERIFIED actor from the request,
    # never one the browser echoes back, and the statement names the person.
    # A separate field was carried to every preview and read by nothing.
    if allowed and ident.is_identified:
        return {"may": True, "kind": ident.kind,
                "statement": f"You are confirming as {ident.actor}."}
    return {"may": bool(allowed),
            "kind": ident.kind,
            "statement": ("You may not confirm: " + (reason or "no verified person"))
            if not allowed else f"You are confirming as {ident.actor or 'an unverified caller'}."}


def _why_not(target: dict, what_not: list) -> str:
    """Why a target cannot be selected, in words: its failing gates, else
    what part 2 says about it. A target that cannot be selected and says
    neither is refused, like any other silent part: its box would be greyed
    with no reason (the C70 re-run: the busy gate held the device and the
    deploy wizard's checkbox said nothing)."""
    failing = [f"{g['name']}: {g['detail']}" if g.get("detail") else g["name"]
               for g in target.get("gates") or [] if g.get("state") == "fail"]
    if failing:
        return "; ".join(failing)
    said = [i.get("text", "") for i in what_not
            if i.get("target") == target.get("name") and i.get("text")]
    if said:
        return "; ".join(said)
    raise PreviewIncomplete(f"{target.get('name') or '?'} cannot be selected and "
                            "nothing says why")


def build(*, action: str, summary: str, targets: list, what_not: list,
          nothing_left_out: str, confirm: dict, explain: dict = None,
          titles: dict = None) -> dict:
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
    why_not = {t["name"]: _why_not(t, what_not) for t in targets if not t.get("selectable")}
    explain = explain or {}
    unknown = set(explain) - set(PARTS)
    if unknown:
        raise PreviewIncomplete(f"explanations for no such part: {sorted(unknown)}")
    return {"action": action, "parts": list(PARTS),
            # A part's heading where the operation's own words differ (a
            # capture RECORDS; it sends nothing). The parts never change.
            **({"titles": dict(titles)} if titles else {}),
            # {part: [{"concept", "text"}]}: a concept taught at the point of
            # action (section 4), drawn by the renderer in that part.
            "explain": explain,
            "what": {"summary": summary,
                     "targets": [{"name": t["name"], "state": t.get("state", ""),
                                  "selectable": bool(t.get("selectable")),
                                  # Drawn beside the disabled box: a control
                                  # greyed with no reason says "you can't"
                                  # and never says why (the C70 re-run).
                                  "why_not": why_not.get(t["name"], ""),
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


BUSY_GATE = "no other operation holds this device"

#: C118: what a rollback leaves behind blocks the CHANGE that failed (its
#: lines, while a program would re-send them), never the device.
BLOCKED_CHANGE = "blocked change"


def busy_gate(d: dict) -> dict:
    """C99: another operation holding the device is said at the PREVIEW,
    naming it, not first as the apply's refusal. It is checked again at
    apply, where the lock is taken, so a free device reads `at_apply`."""
    busy = d.get("busy") or ""
    return (gate(BUSY_GATE, "fail", busy + " Preview again when it has finished.")
            if busy else
            gate(BUSY_GATE, "at_apply", "nothing holds it now; the apply takes the device "
                                        "and refuses if another operation has it by then"))


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
                      "dangerous lines", BLOCKED_CHANGE)]
        # No busy gate: a device that cannot be built reaches no apply, so
        # "the apply takes the device" would be a claim about nothing.
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
        # Named for what it blocks (C118): a CHANGE, never a device. It was
        # "rollback block", and the operator read it as a device block.
        gate(BLOCKED_CHANGE, "fail" if rolled else "pass",
             ("this program re-sends the change that was rolled back at "
              f"{(rolled or {}).get('at', 'an earlier time')}"
              + (f" ({rolled['reason']})" if (rolled or {}).get("reason") else "")
              + ": it is not sent again until that change is gone from intent, or a "
                "retry is authorised. Other changes to this device are not blocked.")
             if rolled else "nothing this program sends is a change that was rolled back"),
    ]
    if failed:
        built.insert(0, gate("program built", "fail", failed))
    return built + [
        busy_gate(d),
        gate(CAPTURE_GATE, "at_apply", CAPTURE_GATE_DETAIL),
        gate("credential unchanged", "at_apply",
             "compared with the capture at apply, before anything connects")]


def _removal_words(rm: dict) -> str:
    """Mode B's selection for one device, in words: what will be removed (the
    program's last lines), what was refused and why, and how many sit in a
    secret position (each still needs its stated reason)."""
    removed, refused = rm.get("removed") or [], rm.get("refused") or []
    if not removed and not refused:
        return "none"
    parts = [f"{len(removed)} removed by the last {len(rm.get('removal_commands') or [])} "
             "line(s) of the program: " + "; ".join(
                 " > ".join(list(u.get("chain") or []) + [u["line"].strip()]) for u in removed)]
    if rm.get("secret_position"):
        parts.append(f"{len(rm['secret_position'])} in a secret position")
    if refused:
        parts.append(f"{len(refused)} refused: " + "; ".join(
            f"{r['line'].strip()} ({r['reason']})" for r in refused))
    return ", ".join(parts)


def deploy_preview(devices: list, request) -> dict:
    """The deploy plan's per-device entries, as the six parts."""
    targets, what_not = [], []
    for d in devices:
        name = d.get("device", "?")
        blocked = not d.get("deployable")
        unauthorised = (bool(d.get("dangerous")) or bool(d.get("secret_readded"))) \
            and d.get("authorisation_ok") is False
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
        removing = {u["line"].strip() for u in ((d.get("removals") or {}).get("removed") or [])}
        chosen = set((d.get("removals") or {}).get("ids") or [])
        removable = [{"id": c["id"], "text": " > ".join(list(c["chain"]) + [c["line"].strip()]),
                      "selected": c["id"] in chosen, "why_not": c.get("why_not", ""),
                      "children": len(c.get("children") or []) if c.get("kind") == "stanza" else 0}
                     for c in (d.get("removable") or [])]
        if d.get("removal_warnings") or removable:
            left = [l for l in (d.get("residue_in_context") or d.get("removal_warnings") or [])
                    if l.strip() not in removing]
            item = {"target": name, "kind": "residue",
                    "text": ("On the device but not in intent. Tick a line to remove it "
                             "(Mode B): it joins the program and needs your stated reason "
                             "there. An unticked line will NOT be removed."
                             if removable else
                             "On the device but not in intent: will NOT be removed. Remove "
                             "them by hand, or adopt them into the template."),
                    "lines": left}
            if removable:
                item["removable"] = removable
            if removable or [l for l in (d.get("removal_warnings") or [])
                             if l.strip() not in removing]:
                what_not.append(item)
        if d.get("shares_key"):
            # C201, option (b): a line a shared setting key hides from the
            # residue is NAMED with the line it collides with, and not offered.
            what_not.append({
                "target": name, "kind": "shares_key",
                "text": ("On the device and not in intent, but sharing a setting key with a "
                         "line intent keeps, which the device already holds: the tool cannot "
                         "tell the two apart (C201), so this line will NOT be removed and is "
                         "not offered for removal. Remove it by hand if intent is what the "
                         "device should be."),
                "lines": [" > ".join(list(s.get("chain") or []) + [s["line"].strip()])
                          + f"   (shares a setting key with `{s['with'].strip()}`)"
                          for s in d["shares_key"]]})
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
            {"name": "removals selected", "value": _removal_words(d.get("removals") or {})},
            {"name": "secrets masked in this preview",
             "value": ", ".join(d.get("masked_refs") or []) or "none"},
        ]
        targets.append({
            "name": name, "state": state,
            "selectable": not (blocked or unauthorised or failed or d.get("busy")),
            "select_data": {"hash": d.get("capture_hash") or "",
                            "command-hash": d.get("command_hash") or ""},
            "program": {"lines": commands, "dangerous": d.get("dangerous") or [],
                        # A restore's secret-position lines it would ADD
                        # (C79), authorised by the same box as a dangerous one.
                        "secret": d.get("secret_readded") or [],
                        # Mode B: each selected removal, keyed as authorised.
                        "removal": list((d.get("removals") or {}).get("keys") or []),
                        "authorised": d.get("authorised") or [],
                        # How often each was authorised here before (C140).
                        "prior": d.get("prior_authorised") or {"state": "ok", "lines": {}},
                        "authorisation_error": d.get("authorisation_error") or "",
                        "none": "" if commands else none, "notes": notes},
            "operands": operands, "gates": _deploy_gates(d, failed)})
    n = len(targets)
    ready = sum(1 for t in targets if t["selectable"])
    # Mode B: "merge-only, never removed" is false the moment a removal is
    # selected, so both sentences say what this program does.
    removing_any = any(((d.get("removals") or {}).get("removed")) for d in devices)
    return build(
        action="deploy",
        summary=(f"Deploy to the devices you tick, "
                 + ("merge-only plus the removals you selected" if removing_any
                    else "merge-only")
                 + f": {ready} of {n} can be "
                 "deployed now, and for each, exactly the program shown is sent, in order."),
        targets=targets, what_not=what_not,
        nothing_left_out=("Nothing: every planned device can be sent, and no line on "
                          "any device lies outside intent."),
        confirm=confirm_part(request),
        explain={
            "what_not": [{"concept": "merge-only",
                          "text": ("Lines are added or replaced. A line on the device that "
                                   "intent does not mention is removed ONLY where you "
                                   "selected it, each with your stated reason; every other "
                                   "one is listed here as not removed."
                                   if removing_any else
                                   "Merge-only: lines are added or replaced. A line on the "
                                   "device that intent does not mention is never removed; "
                                   "it is listed here as not removed.")}],
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
    flagged = list(d.get("dangerous") or []) + list(d.get("secret_readded") or [])
    out.append(gate("lines needing an authorisation (dangerous, or a secret re-added)",
                    "not_applicable" if not flagged
                    else "pass" if d.get("authorisation_ok") else "fail",
                    "" if not flagged else (d.get("authorisation_error")
                                            or f"{len(flagged)} authorised, each with a "
                                               "stated reason")))
    if failed and d.get("deployable"):
        out.insert(0, gate("program built", "fail", failed))
    return out + [busy_gate(d), gate(CAPTURE_GATE, "at_apply", CAPTURE_GATE_DETAIL)]


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
        unauthorised = (bool(d.get("dangerous")) or bool(d.get("secret_readded"))) \
            and d.get("authorisation_ok") is False
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
                                     "removes). Removal has ONE home, the Deploy plan "
                                     f"(Mode B): {name}'s Deploy plan offers each line "
                                     "the device holds and its committed intent lacks, "
                                     "for removal with a stated reason. After this "
                                     "re-apply, that intent is the ref's wherever the "
                                     "ref carries one.",
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
            "selectable": not (blocked or unauthorised or failed or d.get("busy")),
            "select_data": {"hash": d.get("capture_hash") or "",
                            "command-hash": d.get("command_hash") or ""},
            "program": {"lines": commands, "dangerous": d.get("dangerous") or [],
                        # A restore's secret-position lines it would ADD
                        # (C79), authorised by the same box as a dangerous one.
                        "secret": d.get("secret_readded") or [],
                        "authorised": d.get("authorised") or [],
                        # How often each was authorised here before (C140).
                        "prior": d.get("prior_authorised") or {"state": "ok", "lines": {}},
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
    "captured": "recorded as its golden",
    "unchanged": "unchanged: measured, nothing to record",
    "moved": "refused: it changed since the preview, nothing was recorded",
    "unread": "could not be read, nothing was recorded",
    "refused": "refused: nothing was sent",
    "busy": "refused: another operation holds this device (C98), nothing was recorded",
    "skipped_drifted": "skipped: its capture moved since the preview, nothing was sent",
    "failed": "failed",
    "unattempted": "not attempted",
    "skipped_not_selected": "not selected",
}


class ResultIncomplete(ValueError):
    """A result part is missing, or empty without saying so."""


def build_result(*, action: str, level: str, summary: str, targets: list,
                 did_not: list, nothing_left_out: str, record: dict,
                 not_watched: str, titles: dict = None) -> dict:
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
            **({"titles": dict(titles)} if titles else {}),
            "happened": {"summary": summary,
                         "targets": [{"name": t["name"], "outcome": t.get("outcome", ""),
                                      "words": t.get("words", "")} for t in targets]},
            "did_not": {"items": did_not, "none": "" if did_not else nothing_left_out},
            # A rollback only where the operation has one: an import does not.
            "targets": [{"name": t["name"], "sent": t["sent"], "checks": t["checks"],
                         **({"rollback": t["rollback"]} if "rollback" in t else {}),
                         "stage": t.get("stage", ""),
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
                     "none": "" if sent else (r.get("reason") or "Nothing was sent."),
                     # Each authorised line with the person's stated reason
                     # (C140), read back from the receipt: the deliberate
                     # exception and why, where it can be read afterwards.
                     "authorised": list(r.get("authorised") or []),
                     "actor": r.get("actor", "")},
            "checks": r.get("checks") or {"ran": False, "why": "no check was recorded"},
            "rollback": r.get("rollback") or {},
        })
        if outcome != "deployed":
            did_not.append({"target": name, "kind": outcome,
                            "text": f"{words}" + (f": {r['reason']}" if r.get("reason") else ""),
                            "lines": []})
        rb = r.get("rollback") or {}
        if rb.get("performed") and rb.get("state") not in ("", "restored", "nothing_to_undo"):
            did_not.append({"target": name, "kind": "not_restored",
                            "text": "The rollback did NOT leave this device as it was "
                                    f"({rb.get('state')}): {rb.get('detail') or 'no detail'}. "
                                    "Read it before anything else is sent to it.",
                            "lines": list(rb.get("remaining") or [])})
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


def onboard_preview(plan: dict, bootstrap_config: str, confirm: dict) -> dict:
    """Onboarding's review, drawn by the preview component (7.1). Replaces
    `onboardReviewHtml`, a second renderer. Its sentences are kept: every
    refusal at once with the count, advisories as notes that never block,
    "Nothing has been created yet", and the startup config it will boot,
    which is downloaded or served and SENT nowhere (C127)."""
    plan = plan or {}
    host = plan.get("hostname") or "(no name)"
    reasons = list(plan.get("blocking_reasons") or [])
    notes = list(plan.get("advisories") or [])
    source = plan.get("address_source") or "static"
    iface = plan.get("manager_interface") or "(no interface)"
    if source in ("dhcp", "ztp"):
        address = f"{plan.get('address_claim') or source.upper()} on {iface}"
    elif plan.get("mgmt_mask"):
        address = f"{plan.get('mgmt_ip')} {plan.get('mgmt_mask')} on {iface}"
    else:
        address = plan.get("mgmt_ip") or ""
    n = len(reasons)
    if n:
        summary = (f"{n} reason{'' if n == 1 else 's'} this device cannot be onboarded, all of "
                   f"them, so they can be fixed in one pass: each is a failed gate below. "
                   f"Nothing has been created yet.")
    else:
        summary = (f"Create {host} in {plan.get('list') or 'its list'}: its one-time credential, "
                   f"its identity and intent in one commit"
                   + (", its Kea reservation" if source == "ztp" else "")
                   + ", and the startup config it will boot. Nothing reaches a device.")
    # Refusals FIRST, then the notes: an advisory must never push a refusal
    # off the top of the panel, nor read like one (4C.8's rule, kept).
    what_not = [{"target": host, "kind": "refused", "lines": [],
                 "text": "Not created: " + r} for r in reasons] + [
        {"target": host, "kind": "nothing_yet", "lines": [],
         "text": "Nothing has been created yet. This is what will be. Every step before Create "
                 "is a read: you can go Back from here without undoing anything."},
        {"target": host, "kind": "phase_two", "lines": [],
         "text": "No device is reached, nothing enters the inventory and nothing is created in "
                 "NetBox: phase 2 (Verify) does those, once the device answers."},
        {"target": host, "kind": "credential", "lines": [],
         "text": "The real bootstrap credential is not shown: the one in the startup config is "
                 "a placeholder. The real one-time credential is generated when you press "
                 "Create and is never sent to the browser."},
    ] + [{"target": host, "kind": "advisory", "lines": [],
          "text": "Worth knowing (this does not block onboarding): " + note} for note in notes]
    config = (bootstrap_config or "").splitlines()
    gates = ([gate("refused", "fail", r) for r in reasons] if reasons else
             [gate("every check the plan makes", "pass", "")])
    gates.append(gate("the plan rebuilt at Create", "at_apply",
                      "Create rebuilds the plan from the stores and refuses if anything moved"))
    target = {
        "name": host, "state": "blocked" if reasons else "ready", "selectable": not reasons,
        "program": {"lines": config, "dangerous": [], "authorised": [],
                    "authorisation_error": "",
                    "caption": ("The startup config this device will boot with. It is downloaded "
                                "or served, and sent to no device from here. The credential in it "
                                "is a placeholder: the real one-time bootstrap credential is "
                                "generated when you press Create and is never sent to the browser"),
                    "none": "No startup config: the plan could not render one (its reason is a "
                            "failed gate below).",
                    "notes": []},
        "operands": [
            {"name": "Name", "value": host},
            {"name": "Platform", "value": plan.get("platform") or ""},
            {"name": "List", "value": f"{plan.get('list') or ''} ({plan.get('source_kind') or ''})"},
            {"name": "Management IP", "value": address},
            {"name": "Gateway", "value": plan.get("manager_gateway") or
             "none: the NMAS is on this subnet"},
            {"name": "Template", "value": plan.get("template") or "(none bound)"},
            {"name": "Credential source", "value": plan.get("cred_source") or "(not resolved)"},
            {"name": "NetBox", "value": plan.get("netbox_note") or
             "created in phase 2, from the first capture"},
            {"name": "Adds to inventory", "value": plan.get("inventory_note") or
             "after it answers"},
        ],
        "gates": gates,
    }
    return build(action="onboard", summary=summary, targets=[target], what_not=what_not,
                 nothing_left_out="", confirm=confirm,
                 titles={"program": "What will be created (on no device)"})


def netbox_removal_result(row: dict, record_status: dict = None) -> dict:
    """A NetBox Remove, drawn by the result component (7.1, C121), from the
    ROW that records it, so the result at apply and the one read back later
    are one computation. Its level comes from `complete`: a removal NetBox
    refused part of was drawn in green."""
    def _line(o):
        return f"{o.get('endpoint', '')} #{o.get('id')} {o.get('name', '')}".strip()
    deleted, skipped, failed = (row.get("deleted") or [], row.get("skipped") or [],
                                row.get("failed") or [])
    name = row.get("list") or "the list"
    if row.get("forget_only"):
        level, summary = "nothing", (f"Nothing was deleted from NetBox. NMAS no longer "
                                     f"records the objects it created for {name}.")
    elif not row.get("ok"):
        level, summary = "failed", f"The removal for {name} did not run: {row.get('error') or 'no reason'}"
    elif failed:
        level = "partial" if deleted else "failed"
        summary = (f"{len(deleted)} object(s) deleted from NetBox for {name}; NetBox REFUSED "
                   f"{len(failed)}, which are still there.")
    elif deleted:
        level, summary = "success", f"{len(deleted)} object(s) deleted from NetBox for {name}."
    else:
        level, summary = "nothing", (row.get("message") or
                                     f"Nothing NMAS created for {name} was left to delete.")
    did_not = []
    if failed:
        did_not.append({"target": name, "kind": "refused",
                        "text": "Not deleted: NetBox refused the delete, or the object could "
                                "not be read (each reason says which). They may still be in "
                                "NetBox, and NMAS still records them:",
                        "lines": [f"{_line(o)}: {o.get('reason') or 'no reason'}" for o in failed]})
    if skipped:
        did_not.append({"target": name, "kind": "skipped",
                        "text": "Left alone: no nmas-managed tag, so treated as a person's:",
                        "lines": [_line(o) for o in skipped]})
    target = {"name": name,
              "outcome": {"success": "deployed", "partial": "partial"}.get(level, level),
              "words": {"success": "removed", "partial": "partly removed",
                        "failed": "not removed", "nothing": "nothing deleted"}[level],
              "sent": {"lines": [_line(o) for o in deleted], "program_hash": "",
                       "caption": f"{len(deleted)} object(s) deleted",
                       "none": "Nothing was deleted from NetBox."},
              "checks": {"ran": bool(deleted or failed), "ok": not failed,
                         "statements": [f"NetBox accepted {len(deleted)} delete(s) and "
                                        f"refused {len(failed)}"],
                         "why": "no delete was sent"}}
    rs = record_status or {"ok": True}
    statement = (f"Recorded {row.get('at', '?')} by {row.get('actor') or 'an unrecorded actor'} "
                 "in the removal record; NetBox's own changelog holds each delete."
                 if rs.get("ok") else
                 f"THE REMOVAL RECORD WAS NOT WRITTEN: {rs.get('error') or 'no reason'}. "
                 "The removal happened; only NetBox's changelog holds it.")
    return build_result(
        action="netbox_remove", level=level, summary=summary, targets=[target],
        did_not=did_not, nothing_left_out="Nothing: every object NMAS created was removed.",
        record={"commit": "", "tags": [], "baseline": "", "statement": statement},
        not_watched=("NetBox cascades a delete through relationships: the preview named "
                     "what else would go, and nothing re-reads NetBox after the removal."),
        titles={"sent": "What was deleted from NetBox", "checks": "What NetBox answered"})


def _nb_gates(d: dict, what: str) -> list:
    """The gates every NetBox write shares, in the words of what each
    establishes (netbox_authz, netbox_guard). None has passed at preview
    except the dry run itself: the rest are checked when Confirm is pressed."""
    minutes = max(1, round((d.get("expires_in") or 300) / 60))
    return [
        gate(f"a dry run of the real {what} against the real NetBox", "pass",
             "this preview ran the same code with every write captured; nothing was written"),
        gate("NetBox writes permitted for this instance", "pass" if d.get("writes_allowed")
             else "at_apply",
             "the saved switch is on" if d.get("writes_allowed") else
             "the saved switch is OFF: the 'Permit NetBox writes' box below turns it on "
             "when you confirm, and without it the confirm is refused"),
        gate("NetBox unchanged since this preview", "at_apply",
             "the plan is recomputed when you confirm and its hash compared; if NetBox "
             "moved, nothing is written and you are asked to preview again"),
        gate("a one-shot confirmation", "at_apply",
             f"valid {minutes} minute(s), once, for this plan only; it never leaves "
             "NetBox open for writes"),
    ]


def _nb_line(verb: str, o: dict) -> str:
    oid = o.get("id")
    ident = f" #{oid}" if isinstance(oid, int) and oid > 0 else ""
    payload = o.get("payload") or {}
    # A device type is named by its model, not a `name` (the dry run's label
    # reads name, address, prefix, display).
    label = o.get("name") or payload.get("model") or payload.get("slug") or ""
    return f"{verb} {o.get('endpoint', '')}{ident} {label}".rstrip()


def netbox_import_preview(d: dict, confirm: dict, *, all_lists: bool = False) -> dict:
    """The NetBox import's preview, drawn by the component (7.1). Replaces
    the safety modal's own body, which drew two count tables: what it
    creates and updates is now each object by name, and an update names the
    fields it sets (never their values, which carry configs)."""
    plan = d.get("plan") or {}
    name = "every device list" if all_lists else (d.get("list") or "the list")
    creates, updates = plan.get("creates") or [], plan.get("updates") or []

    def _update_line(o):
        # What the PATCH CHANGES, from the object as NetBox holds it (C135):
        # "sets tags" over tags the device already had read as a change, and
        # the operator could not tell a real one from a re-send.
        ch = o.get("changed", False)
        if ch == {}:
            return _nb_line("update", o) + ": changes nothing (sent; every value already held)"
        if isinstance(ch, dict):
            return _nb_line("update", o) + ": changes " + ", ".join(sorted(ch))
        keys = ", ".join(sorted(o.get("payload") or {}))
        return (_nb_line("update", o) + ": sets " + keys
                + (" (what it changes is UNKNOWN: the object could not be read)"
                   if ch is None else ""))

    real = [o for o in updates if o.get("changed", False) != {}]
    noop = len(updates) - len(real)
    n = len(creates) + len(real)
    lines = [_nb_line("create", o) for o in creates] + [_update_line(o) for o in updates]
    summary = (f"Import {name} ({d.get('device_count', 0)} device(s)) into NetBox: create "
               f"{len(creates)} object(s) and change {len(real)}"
               + (f"; {noop} more update(s) are sent and change nothing" if noop else "")
               + "." if n else
               f"Import {name} ({d.get('device_count', 0)} device(s)): nothing to create or "
               "update. NetBox already matches.")
    what_not = [
        {"target": name, "kind": "no_delete", "lines": [],
         "text": "Nothing is deleted: an import only creates and updates. Remove is its own "
                 "operation."},
        {"target": name, "kind": "no_device", "lines": [],
         "text": "No device is reached: the import reads each device's committed golden "
                 "config, not the device."},
        {"target": name, "kind": "provenance", "lines": [],
         "text": "An object it UPDATES is not tagged nmas-managed and is never made removable: "
                 "the tag marks only what NMAS creates. Each update's before and after goes to "
                 "the modification record. A device's `tags` update carries only its routing-"
                 "protocol tags (bgp, ospf, rip, cdp), merged with what it holds."},
    ]
    what_not += _nb_skipped(d.get("skipped"))
    target = {
        "name": name, "state": "ready" if n else "unchanged", "selectable": True,
        "program": {"lines": lines, "dangerous": [], "authorised": [],
                    "authorisation_error": "", "notes": [],
                    "caption": "What NetBox will be told to create and update. Nothing is "
                               "sent to a device",
                    "none": "Nothing: NetBox already holds what the golden configs describe."},
        "operands": [
            {"name": "List", "value": name},
            {"name": "Devices", "value": str(d.get("device_count", 0))},
            {"name": "Creates", "value": str(len(creates))},
            {"name": "Updates", "value": str(len(updates))},
            {"name": "Plan hash", "value": (d.get("plan_hash") or "")[:16]},
        ],
        "gates": _nb_gates(d, "import"),
    }
    return build(action="netbox_import_all" if all_lists else "netbox_import",
                 summary=summary, targets=[target], what_not=what_not,
                 nothing_left_out="", confirm=confirm,
                 titles={"program": "What will be written to NetBox"})


def netbox_removal_preview(d: dict, confirm: dict) -> dict:
    """NetBox Remove's preview, drawn by the component (7.1). What the
    database takes WITH each delete (the cascade, `netbox_cascade`) is drawn
    only when there is some, as before: a clean, proven preview adds no
    alarm, or the operator learns to click through it. A cascade that could
    not be established is its own statement, never "nothing"."""
    name = d.get("list") or "the list"
    deleted, skipped = d.get("deleted") or [], d.get("skipped") or []
    # C130: a recorded object NetBox could not be READ is not gone. The
    # preview names it and cannot be confirmed; one that answered 404 is gone,
    # and only a real removal drops it from the record.
    unreadable, gone = d.get("failed") or [], d.get("gone") or []
    cascade = d.get("cascade") or {}
    foreign, taken = cascade.get("foreign") or [], cascade.get("taken") or []
    unproven = cascade.get("unproven") or []
    # What the database takes that is ALREADY in the delete list is not more
    # (the operator, R2a: "5 further object(s)" read as five MORE when all five
    # were interfaces and addresses listed above).
    listed = {(o.get("endpoint"), o.get("id")) for o in deleted}
    own = [o for o in taken if not o.get("foreign")]
    own_new = [o for o in own if (o.get("endpoint"), o.get("id")) not in listed]
    own_listed = len(own) - len(own_new)

    def _via(o):
        return f"{o.get('endpoint', '')} {o.get('name') or o.get('id')} (via {o.get('via', '?')})"

    if deleted:
        summary = (f"{len(deleted)} object(s) will be PERMANENTLY deleted from NetBox for "
                   f"{name}. Only objects NMAS created AND tagged nmas-managed are eligible."
                   + (f" NetBox will ALSO delete {len(foreign)} object(s) NMAS did not create, "
                      "because they hang off one of these: read them below." if foreign else ""))
    else:
        summary = d.get("message") or f"Nothing NMAS created for {name} is left to delete."
    if unreadable:
        # The headline leads with what blocks it: "nothing left to delete"
        # over objects that could not be read is the wrong thing looking right.
        summary = (f"This removal cannot be confirmed: {len(unreadable)} object(s) NMAS recorded "
                   f"for {name} could not be read from NetBox (not gone). " + summary)
    notes = []
    if foreign:
        notes.append({"title": f"ALSO DELETED BY NETBOX: {len(foreign)} object(s) NMAS did NOT "
                               "create. They carry no nmas-managed tag, so the provenance check "
                               "would leave them alone; it protects an object, and this travels "
                               "a relationship.",
                      "lines": [_via(o) for o in foreign]})
    if own_new:
        notes.append({"title": f"Also removed by NetBox with these: {len(own_new)} further "
                               "object(s) NOT in the list above, all of them NMAS's own.",
                      "lines": [_via(o) for o in own_new]})
    what_not = []
    if not deleted:
        what_not.append({"target": name, "kind": "nothing", "lines": [],
                         "text": "Nothing to delete: " + summary})
    if skipped:
        what_not.append({"target": name, "kind": "skipped",
                         # Removal needs BOTH the record and the tag. These
                         # lack one, and the reason on each line says which.
                         "text": f"Left alone ({len(skipped)}): removal needs an object NMAS "
                                 "recorded creating AND NetBox shows tagged nmas-managed; these "
                                 "are not both, so they are treated as a person's:",
                         "lines": [f"{_nb_line('keep', o)} ({o.get('reason') or ''})"
                                   for o in skipped]})
    if unreadable:
        what_not.insert(0, {"target": name, "kind": "unreadable",
                            "text": f"Could NOT be read from NetBox ({len(unreadable)}), which is "
                                    "not the same as gone: nothing will be deleted or forgotten "
                                    "for them, and this preview cannot be confirmed until they "
                                    "can be read:",
                            "lines": [f"{_nb_line('read', o)}: {o.get('reason') or ''}"
                                      for o in unreadable]})
    if gone:
        what_not.append({"target": name, "kind": "gone",
                         "text": f"Already gone from NetBox ({len(gone)}, it answered 404). A real "
                                 "removal drops them from NMAS's record; this preview wrote "
                                 "nothing:",
                         "lines": [_nb_line("gone", o) for o in gone]})
    if unproven:
        what_not.append({"target": name, "kind": "unproven",
                         "text": "This preview could NOT establish what some of these deletions "
                                 "take with them, which is not the same as nothing:",
                         "lines": list(unproven)})
    what_not += [
        {"target": name, "kind": "updated", "lines": [],
         "text": "Nothing NMAS only UPDATED is deleted: removal needs an object NMAS created."},
        {"target": name, "kind": "no_device", "lines": [],
         "text": "No device is reached and nothing in git changes."},
        {"target": name, "kind": "forget", "lines": [],
         "text": "'Just stop tracking' is the other choice: it deletes nothing, and NMAS "
                 "forgets what it created for this list, so NetBox keeps every object."},
    ]
    gates = _nb_gates(d, "removal")
    if not deleted:
        cascade_gate = gate("what the database takes with each delete, asked of NetBox",
                            "not_applicable", "nothing is deleted")
    elif not d.get("cascade"):
        # Absent is not empty: a preview that never asked must not say "nothing".
        cascade_gate = gate("what the database takes with each delete, asked of NetBox",
                            "not_reached", "NOT asked: nothing is known about what goes with "
                                           "these deletes, which is not the same as nothing")
    elif unproven:
        cascade_gate = gate("what the database takes with each delete, asked of NetBox",
                            "not_reached", "NOT established for some deletes: see what will "
                                           "not happen")
    else:
        cascade_gate = gate("what the database takes with each delete, asked of NetBox",
                            "pass", (f"asked: {len(taken) - own_listed} further object(s) go "
                                     "with them" if len(taken) > own_listed else
                                     "asked: nothing beyond the list above goes with them")
                            + (f"; {own_listed} of what NetBox takes with them is already "
                               "listed above" if own_listed else ""))
    gates.insert(1, cascade_gate)
    gates.insert(1, gate("every recorded object read from NetBox", "fail" if unreadable else "pass",
                         f"{len(unreadable)} could not be read: not gone, and not forgotten"
                         if unreadable else "read, or answered 404 (gone)"))
    target = {
        "name": name, "state": "blocked" if unreadable else "ready" if deleted else "unchanged",
        "selectable": bool(deleted) and not unreadable,
        "program": {"lines": [_nb_line("delete", o) for o in deleted], "dangerous": [],
                    "authorised": [], "authorisation_error": "", "notes": notes,
                    "caption": "What NetBox will be told to delete",
                    "none": "Nothing: " + summary},
        "operands": [
            {"name": "List", "value": name},
            {"name": "Deletes", "value": str(len(deleted))},
            {"name": "Left alone", "value": str(len(skipped))},
            {"name": "Taken with them by NetBox", "value":
             f"{len(taken)} ({len(foreign)} NMAS did not create)"},
            {"name": "Plan hash", "value": (d.get("plan_hash") or "")[:16]},
        ],
        "gates": gates,
    }
    return build(action="netbox_remove", summary=summary, targets=[target],
                 what_not=what_not, nothing_left_out="", confirm=confirm,
                 titles={"program": "What will be deleted from NetBox"})


#: What phase 1 of onboarding creates, per completed step, in words (C86).
_ONBOARD_STEP_WORDS = {
    "credentials": "the bootstrap credential, staged in the credential store for this device",
    "commit": "the device's identity and committed intent, in one commit",
    "reserve": "the Kea reservation that gives the device its address",
    "render": "the bootstrap config, downloadable from the device's pending row",
}


def onboard_create_result(run: dict, plan) -> dict:
    """Onboarding's Create, drawn by the result component (7.1, C86).

    Create is PHASE 1: it touches no device, and the device it leaves is
    PENDING (in the manifest and in git, not in the inventory, never
    reached). The toast it replaces said "Device onboarded.", the outcome of
    phase 2. So a complete phase 1 is "Partly done", never green: what the
    operator asked for is an onboarded device, and that needs the device
    booted and Verify pressed.
    """
    host = getattr(plan, "hostname", "") or "the device"
    completed = list(run.get("completed") or [])
    failed_at = run.get("failed_at") or ""
    commit = run.get("commit") or ""
    source = getattr(plan, "address_source", "static") or "static"
    lines = []
    for step in completed:
        words = _ONBOARD_STEP_WORDS.get(step, step)
        if step == "commit" and commit:
            words += f" ({commit[:12]})"
        if step == "reserve":
            words += (f" ({getattr(plan, 'mgmt_mac', '') or '?'} -> "
                      f"{getattr(plan, 'mgmt_ip', '') or '?'})")
        lines.append(f"{step}: {words}")
    if run.get("ok"):
        level = "partial"
        outcome, words = "pending", "created, and PENDING: not reached, not onboarded"
        summary = (f"{host} is created and PENDING, not onboarded: nothing has reached it. "
                   f"Next: boot it with its bootstrap config"
                   + (" (it fetches its config over ZTP)" if source == "ztp" else "")
                   + ", then press Verify on its pending row. Verify is phase 2, and "
                     "only a device the tool has REACHED is onboarded.")
    else:
        level = "failed"
        outcome, words = "failed", f"not created: stopped at {failed_at or 'an unnamed step'}"
        summary = (f"{host} was not created: onboarding stopped at "
                   f"{failed_at or 'an unnamed step'}. "
                   + ("What it had already written is listed below; Abandon removes it."
                      if completed else "Nothing was written."))
    did_not = []
    if not run.get("ok") or failed_at:
        did_not.append({"target": host, "kind": failed_at or "failed",
                        "text": run.get("reason") or "no reason was reported", "lines": []})
    did_not.append({"target": host, "kind": "phase_two",
                    "text": "Not reached, not in the inventory, not in NetBox: phase 2 "
                            "(Verify) reaches the device, rotates its credential, records "
                            "its first golden, creates its NetBox record and promotes it.",
                    "lines": []})
    target = {
        "name": host, "outcome": outcome, "words": words, "stage": failed_at,
        "reason": run.get("reason") or "",
        "sent": {"lines": lines, "program_hash": "",
                 "caption": f"{len(lines)} thing(s) created, none of them on a device",
                 "none": "Nothing was created." if not lines else ""},
        "checks": {"ran": False,
                   "why": "phase 1 touches no device; phase 2 (Verify) reaches it and "
                          "checks what it finds"},
    }
    statement = (f"Commit {commit[:12]} records {host} as pending." if commit
                 else "No commit was made.") + " Onboarding takes no baseline."
    return build_result(
        action="onboard", level=level, summary=summary, targets=[target],
        did_not=did_not, nothing_left_out="",
        record={"commit": commit, "tags": [], "baseline": "", "statement": statement},
        not_watched=("Nothing watches a pending device but its pending row: it has not "
                     "been reached, so no heartbeat, drift check or backup covers it yet."),
        titles={"sent": "What was created (on no device)",
                "checks": "What was checked on the device"})


def _run_record_statement(row: dict, rs: dict, tail: str) -> str:
    if not (rs or {"ok": True}).get("ok"):
        return (f"THE RUN RECORD WAS NOT WRITTEN: {(rs or {}).get('error') or 'no reason'}. "
                "The run happened; only this screen shows it.")
    return (f"Recorded {row.get('at', '?')} by {row.get('actor') or 'an unrecorded actor'} in "
            f"the onboarding run record. {tail}")


def onboard_verify_result(row: dict, record_status: dict = None) -> dict:
    """Onboarding's Verify (phase 2), drawn by the result component (7.1),
    from the ROW that records it, so the result at apply and the one read back
    from the pending banner are one computation. It keeps the diagnosis the
    old failure panel drew (`verifyFailureHtml`, removed): "did not answer" is
    never "wrong interface", the causes in the order worth checking, and the
    recovery command. `ok` is every step, promotion last."""
    host = row.get("device") or "the device"
    ip = row.get("mgmt_ip") or "its address"
    steps = row.get("steps") or []
    v = row.get("verify") or {}
    failed = next((st for st in steps if not st.get("ok") and st.get("detail") != "did not run"),
                  None)
    at = (failed or {}).get("step") or ("verify" if not row.get("ok") else "")
    ran = [st["step"] for st in steps if st.get("ok")]
    not_run = [st["step"] for st in steps if st.get("detail") == "did not run"]
    did_not = []
    if row.get("ok"):
        level = "success"
        summary = (f"{host} is onboarded: reached at {ip}, its credential rotated and saved on "
                   "the device, its first golden recorded, its NetBox record created, and it "
                   "is now in the inventory.")
    elif at == "verify":
        level = "failed"
        summary = (f"{host} did not answer at {ip}: nothing about it has changed, and it is "
                   "still pending. Not answering proves nothing about why; the causes below "
                   "are possibilities, in the order they are worth checking.")
        did_not.append({"target": host, "kind": "did_not_answer", "lines": [],
                        "text": v.get("error") or row.get("reason") or "no reason was reported"})
        causes = v.get("causes") or []
        if causes:
            did_not.append({"target": host, "kind": "causes",
                            "text": "Worth checking, in this order:",
                            "lines": [f"{i}. {c.get('cause', '')}: {c.get('why', '')} "
                                      f"({c.get('where', '')}: {c.get('command', '')})"
                                      for i, c in enumerate(causes, 1)]})
        rec = v.get("recovery") or {}
        if rec.get("available"):
            did_not.append({"target": host, "kind": "recovery",
                            "text": "Locked out? " + (rec.get("note") or ""),
                            "lines": [rec.get("command") or ""]})
        elif rec.get("note"):
            did_not.append({"target": host, "kind": "recovery", "lines": [],
                            "text": rec["note"]})
    else:
        level = "partial" if ran else "failed"
        summary = (f"{host} answered, and phase 2 stopped at {at}: "
                   f"{row.get('reason') or 'no reason was reported'}. It is still PENDING. "
                   f"Steps that ran: {', '.join(ran) or 'none'}. The device may have changed; "
                   "read the steps before trying again.")
    if not row.get("ok") and not_run:
        did_not.append({"target": host, "kind": "not_run",
                        "text": "Did not run, because phase 2 stopped first:",
                        "lines": not_run})
    lines = [f"{st.get('step')}: " + ("done" if st.get("ok") else
                                      "did not run" if st.get("detail") == "did not run"
                                      else "FAILED")
             + (f" ({st['detail']})" if st.get("detail") and st.get("detail") != "did not run"
                else "") for st in steps]
    answered = v.get("state") == "answered" or bool(ran)
    target = {
        "name": host, "stage": at, "reason": row.get("reason") or "",
        "outcome": "deployed" if row.get("ok") else ("partial" if level == "partial" else "failed"),
        "words": "onboarded" if row.get("ok") else f"stopped at {at}",
        "sent": {"lines": lines, "program_hash": "",
                 "caption": "The steps phase 2 ran, in order. Rotate and persist change the "
                            "device; the rest read it or write the record",
                 "none": "No step ran."},
        "checks": {"ran": True, "ok": answered, "words": ["answered", "did not answer"],
                   "statements": [f"reaching the device IS the verification: {host} "
                                  + (f"answered at {ip}" if answered else f"did not answer at {ip}")
                                  + (f" with the {v['credential_source']} credential"
                                     if v.get("credential_source") else "")]},
    }
    # A promoted device with no golden commit of this run's own is not
    # "pending": its golden step found the golden already committed (R1,
    # 2026-09-28: the rotation had committed it first, C147). Said as that,
    # never as the pending sentence, which contradicted the summary above it.
    if row.get("ok") and row.get("golden_commit"):
        tail = (f"Its first golden is commit {row['golden_commit'][:12]}; its history is "
                "the golden history, and it is in the inventory.")
    elif row.get("ok"):
        tail = ("Its golden step made no commit: the repository already held that "
                "golden, committed earlier. Its history is the golden history, and it is "
                "in the inventory.")
    else:
        tail = "The device's pending row shows it until the next run."
    return build_result(
        action="onboard_verify", level=level, summary=summary, targets=[target],
        did_not=did_not, nothing_left_out="Nothing: every step of phase 2 ran.",
        record={"commit": row.get("golden_commit", ""), "tags": [], "baseline": "",
                "statement": _run_record_statement(row, record_status, tail)},
        not_watched=("Nothing re-reads the device after promotion except what watches every "
                     "device: drift, heartbeats and backups." if row.get("ok") else
                     "Nothing retries: the device stays pending until Verify is pressed again "
                     "or it is abandoned."),
        titles={"sent": "What phase 2 did", "checks": "Whether the device answered"})


def onboard_abandon_result(row: dict, record_status: dict = None) -> dict:
    """Onboarding's Abandon, drawn by the result component (7.1), from the
    row that records it. The toast it replaces said "abandoned; the name is
    free" and showed nothing it removed. `ok` is every step AND the name
    released, and release re-derives the references itself."""
    host = row.get("device") or "the device"
    steps = row.get("steps") or []
    remaining = row.get("remaining") or []
    done = [st for st in steps if st.get("ok")]
    if row.get("ok"):
        level = "success"
        summary = (f"{host} is abandoned: what its onboarding created is removed, and the name "
                   f"'{row.get('released') or host}' is free.")
    elif not steps:
        level = "failed"
        summary = f"{host} was not abandoned: {row.get('error') or 'no reason was reported'}"
    else:
        level = "partial" if done else "failed"
        summary = (f"{host} was NOT fully abandoned: {len(remaining)} step(s) remain, and the "
                   "name is not free. " + (row.get("error") or ""))
    did_not = []
    if remaining:
        did_not.append({"target": host, "kind": "remaining",
                        "text": "Still there, with how to finish each:",
                        "lines": [f"{r.get('step')}: {r.get('detail')}"
                                  + (f" -- to finish: {r['how_to_finish']}"
                                     if r.get("how_to_finish") else "") for r in remaining]})
    target = {
        "name": host, "reason": row.get("error") or "",
        "outcome": "deployed" if row.get("ok") else ("partial" if level == "partial" else "failed"),
        "words": "abandoned" if row.get("ok") else "not fully abandoned",
        "sent": {"lines": [f"{st.get('step')}: {'done' if st.get('ok') else 'NOT done'}"
                           + (f" ({st['detail']})" if st.get("detail") else "") for st in steps],
                 "program_hash": "",
                 "caption": "What abandon removed, in the reverse of the order onboarding "
                            "created it. Nothing reaches the device",
                 "none": "Nothing was removed."},
        "checks": {"ran": bool(steps), "ok": bool(row.get("released")),
                   "words": ["released", "not released"],
                   "why": "abandon refused before any step",
                   "statements": ["the name is released only when nothing references it, "
                                  "re-derived rather than trusted from the steps above"]},
    }
    return build_result(
        action="onboard_abandon", level=level, summary=summary, targets=[target],
        did_not=did_not, nothing_left_out="Nothing: every step ran and the name is free.",
        record={"commit": "", "tags": [], "baseline": "",
                "statement": _run_record_statement(
                    row, record_status, "The removal of its intent is a commit in the list's "
                                        "repository.")},
        not_watched=("Nothing re-reads NetBox, Kea or the credential store after the abandon; "
                     "the steps above are what each answered."),
        titles={"sent": "What abandon did", "checks": "Whether the name was released"})


def onboard_run_result(row: dict, record_status: dict = None) -> dict:
    return (onboard_verify_result if row.get("kind") == "verify"
            else onboard_abandon_result)(row, record_status)


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


def _nb_skipped(groups) -> list:
    """What an import deliberately did not model (a default route as a
    prefix, the addresses in an excluded VRF), as what-did-not-happen items:
    named per class with its devices and its reason, never a failure and
    never a refusal, and never silent (the operator, 2026-09-28: "5 fewer
    writes" must be explained)."""
    out = []
    for g in groups or []:
        devices = ", ".join(g.get("devices") or []) or "no device named"
        out.append({"target": "this import", "kind": "not_modelled", "lines": [],
                    "text": f"Not imported, on purpose: {g.get('what', '?')} on {devices} "
                            f"({g.get('count', 0)}), because {g.get('why', 'no reason recorded')}."})
    return out


def netbox_sync_result(summary: dict) -> dict:
    """A NetBox import's outcome as a result (C85, 7.1 step 2).

    The import runs on a thread, so its result is the stored summary, read
    whenever the NetBox tab is. C8 put `write_failures`, `partial` and
    `complete` into that summary so a partial import could not read as clean;
    the card read `failed` and drew green, so the fix never reached the
    screen. Here `complete` decides the level, every write that did not land
    is named with its device, and a summary that predates C8's counting says
    what landed is UNKNOWN rather than drawing green."""
    s = summary or {}
    failed = list(s.get("failed") or [])
    partial = list(s.get("partial") or [])
    write_failures = list(s.get("write_failures") or [])
    counted = "complete" in s
    targets, did_not = [], []
    for f in failed:
        name = f.get("hostname") or f.get("name") or "?"
        targets.append({"name": name, "outcome": "failed", "words": "not imported",
                        "sent": {"none": "Nothing was written for this device."},
                        "checks": {"ran": False, "why": "an import writes NetBox and checks no device"}})
        did_not.append({"target": name, "kind": "failed",
                        "text": "Not imported: " + str(f.get("error") or f.get("reason") or "the upsert failed"),
                        "lines": []})
    for name in partial:
        mine = [w for w in write_failures if w.get("device") == name]
        targets.append({"name": name, "outcome": "partial",
                        "words": f"partly written: {len(mine)} write(s) did not land",
                        "sent": {"none": "Written to NetBox, except the writes named under what did not happen."},
                        "checks": {"ran": False, "why": "an import writes NetBox and checks no device"}})
        did_not.append({"target": name, "kind": "write_failed",
                        "text": f"{len(mine)} write(s) did not land",
                        "lines": [f"{w.get('write', '?')}: {w.get('error', '')}" for w in mine]})
    loose = [w for w in write_failures if not w.get("device")]
    if loose:
        did_not.append({"target": "this import", "kind": "write_failed",
                        "text": f"{len(loose)} write(s) with no device did not land",
                        "lines": [f"{w.get('write', '?')}: {w.get('error', '')}" for w in loose]})
    # The import's own refusals (a site it adopted and declined to re-parent,
    # a definition it could not ensure). Collected into the summary "because
    # a refusal nobody reads is the same as no refusal", and drawn nowhere
    # until this (found by the fixture that could finally reach a summary).
    for note in s.get("notes") or []:
        did_not.append({"target": "this import", "kind": "declined", "text": str(note),
                        "lines": []})
    did_not += _nb_skipped(s.get("skipped"))
    if not counted:
        did_not.append({"target": "this import", "kind": "uncounted",
                        "text": "This summary predates the counting of individual writes (C8), so "
                                "what landed is unknown. Import again to find out.",
                        "lines": []})
    total, synced = s.get("total", 0), s.get("synced", 0)
    if not total:
        level = "nothing"
    elif s.get("complete") is True:
        level = "success"
    elif synced == 0:
        level = "failed"
    else:
        level = "partial"
    summary_text = (f"{synced} of {total} device(s) imported into NetBox "
                    f"({s.get('created', 0)} created, {s.get('updated', 0)} updated): "
                    + ("everything landed." if s.get("complete") is True
                       else f"{len(partial)} partly written, {len(failed)} not imported."
                       if counted else "whether every write landed is unknown."))
    return build_result(
        action="netbox_import", level=level, summary=summary_text, targets=targets,
        did_not=did_not, nothing_left_out="Nothing: every write landed.",
        record={"statement": f"Stored as the last import of this list, at "
                             f"{s.get('timestamp') or 'an unrecorded time'}, into region "
                             f"{s.get('region') or '?'}, site {s.get('site') or '?'}."},
        not_watched="Nothing re-reads NetBox after an import to check it against what was "
                    "written; the census and the modification record are the checks that "
                    "exist, and they are run by hand.")



# ---------------------------------------------------------------------------
# Capture (7.1 step 4, register C82 and C89): recording a device's running
# config as its golden is itself an operation, previewed and confirmed. A
# capture BECOMES the golden, so what it is checked against is committed
# INTENT (`intent_match`), and a departure is recorded, marked, and kept out
# of any baseline rather than refused: the record must say what the device
# holds.
# ---------------------------------------------------------------------------

CAPTURE_TITLES = {"program": "What will change in its golden",
                  "what": "What will be recorded"}
CAPTURE_RESULT_TITLES = {"sent": "What was recorded", "checks": "Checked against committed intent",
                         "happened": "What was recorded"}


def _intent_resolutions(i: dict) -> list:
    from modules.nsot.intent_match import resolutions
    return resolutions(i)


def _intent_sentence(i: dict) -> str:
    from modules.nsot.intent_match import explain
    return explain(i) if i else "not compared"


def _intent_words(i: dict) -> str:
    from modules.nsot.intent_match import words
    return words(i) if i else "not compared"


def capture_preview(entries: list, *, fleet: bool, inventory: list, request=None,
                    not_read: list = None, timing: dict = None, confirm: dict = None) -> dict:
    """*entries*: per device ``{device, read, error, capture_hash, diff,
    changed, intent, platform}`` from reading it now. *not_read*: devices a
    scope left out (they already have a committed golden), named so the
    preview never reads as the whole list. *confirm*: the confirm part,
    decided from the request before the reads ran on their own thread (C188
    step 2); without it, it is decided from *request*."""
    targets, what_not = [], []
    if not_read:
        what_not.append({"target": "devices that already have a golden", "kind": "scope",
                         "text": (f"{len(not_read)} device(s) already have a committed golden "
                                  f"and are not read or recorded: " + ", ".join(sorted(not_read))
                                  + "."),
                         "lines": []})
    read = [e for e in entries if e.get("read")]
    for e in entries:
        name = e["device"]
        intent = e.get("intent") or {}
        if not e.get("read"):
            what_not.append({"target": name, "kind": "unread",
                             "text": "Could not be read, so it is not recorded: "
                                     + (e.get("error") or "no answer"), "lines": []})
        elif intent.get("state") != "match":
            what_not.append({
                "target": name, "kind": "departs_from_intent",
                "text": (_intent_sentence(intent)[0].upper() + _intent_sentence(intent)[1:] + ". "
                         "Recording it makes the golden a state nobody intended: it will be "
                         "recorded, marked `Intent-Match: no`, and it cannot be part of a baseline."
                         if intent.get("state") == "differs" else
                         "Cannot be compared with committed intent (" + (intent.get("why") or "?")
                         + "): it will be recorded, marked, and it cannot be part of a baseline."),
                "lines": list(intent.get("lines") or [])})
        targets.append({
            "name": name,
            "state": ("unread" if not e.get("read") else
                      "capturable" if e.get("changed") else "unchanged"),
            "selectable": bool(e.get("read")) and not e.get("busy"),
            "select_data": {"hash": e.get("capture_hash") or ""},
            "program": {"lines": list(e.get("diff") or []) if e.get("read") else [],
                        # A capture SENDS NOTHING (C127): the diff is what the
                        # golden will become, not a program for the device.
                        "caption": ("The difference between the device now and its golden. "
                                    "Nothing is sent: confirming records the device as it is"),
                        "none": ("Nothing is recorded: it could not be read." if not e.get("read")
                                 else "Unchanged: the device matches its current golden. Confirming "
                                      "records that it was measured.")},
            "operands": [{"name": "capture hash", "value": e.get("capture_hash") or "none"},
                         {"name": "read in", "value": _read_in_words(timing, name)},
                         {"name": "platform", "value": e.get("platform") or "unknown"},
                         {"name": "committed intent", "value": _intent_sentence(intent),
                          # It decides a fleet capture's outcome: drawn apart,
                          # with its lines and the two ways out, each saying
                          # what it asserts.
                          **({"blocks": "the baseline",
                              "lines": list(intent.get("lines") or []),
                              "resolutions": _intent_resolutions(intent)}
                             if fleet and e.get("read") and intent.get("state") != "match"
                             else {})}],
            "gates": ([gate("device read", "pass" if e.get("read") else "fail",
                            "" if e.get("read") else (e.get("error") or "no answer")),
                       busy_gate(e)]
                      + ([gate("capture unchanged since this preview", "at_apply",
                               "the device IS re-read at apply, and one that moved is refused")]
                         if e.get("read") else [])),
        })
    what_not.append({"target": "the devices", "kind": "scope",
                     "text": "Nothing is sent to any device: a capture reads and records.",
                     "lines": []})
    if fleet:
        reasons = []
        if len(read) < len(inventory):
            reasons.append(f"{len(inventory) - len(read)} inventory device(s) could not be read")
        reasons += [f"{e['device']} does not match its committed intent"
                    for e in read if (e.get("intent") or {}).get("state") != "match"]
        what_not.append({"target": "the baseline", "kind": "baseline",
                         "text": ("No baseline tag will be taken: " + "; ".join(reasons) + ". A "
                                  "baseline asserts the network is at its committed intent."
                                  if reasons else
                                  "A baseline tag is taken only if you confirm EVERY device and "
                                  "each still matches its committed intent at apply."),
                         "lines": []})
    else:
        what_not.append({"target": "the baseline", "kind": "baseline",
                         "text": "No baseline tag: capturing part of the fleet never earns one.",
                         "lines": []})
    changed = sum(1 for e in read if e.get("changed"))
    departs = sum(1 for e in read if (e.get("intent") or {}).get("state") != "match")
    confirm = dict(confirm if confirm is not None else confirm_part(request, "approve"))
    # The MODE travels back with the confirm and names the held devices on the
    # in-flight panel ("read for the denial record", never "captured"). It is
    # display only: what the apply does is decided by what it reads.
    confirm["mode"] = "record"
    # WHAT CONFIRMING ACHIEVES, at the confirm (the operator, 2026-09-28): a
    # preview that knows the operation has no effect says so there, and the
    # button says it too, never "Record 9 device(s)" over a save recording none.
    # And a control named for its OUTCOME says the WORK it still does (the
    # operator, the same night): "Record the denial only" was read as "skip
    # the reads", and nine SSH sessions followed.
    still_read = (" Every device is still read at apply: the decision depends on each "
                  "one's state now, and a device that moved since this preview is refused. "
                  "Nothing is sent to any device.")
    reading = f"all {len(read)} devices" if len(read) > 1 else "the device"
    if read and not changed:
        if not fleet:
            confirm.update(may=False, statement=(
                "Nothing to confirm: every selected device matches its golden, so "
                "nothing would be recorded."))
        elif len(read) == len(inventory) and not departs:
            confirm.update(effect=("No golden will change: every device matches its golden. "
                                   "Confirming takes a baseline at this measured state, and "
                                   "records the decision." + still_read),
                           button=f"Read {reading} and take the baseline",
                           working=f"Reading {reading} for the baseline…",
                           mode="baseline_only")
        else:
            blockers = [f"{e['device']} {_intent_sentence(e.get('intent') or {})}"
                        for e in read if (e.get("intent") or {}).get("state") != "match"]
            if len(read) < len(inventory):
                blockers.append(f"{len(inventory) - len(read)} device(s) could not be read")
            confirm.update(effect=("Nothing will be recorded as a golden and no baseline will be "
                                   "taken: " + "; ".join(blockers) + ". Confirming records only "
                                   "that the fleet was measured and why no baseline was earned, "
                                   "as a commit that changes nothing." + still_read),
                           button=f"Read {reading} and record the denial only",
                           working=f"Reading {reading} for the denial record…",
                           mode="denial_only")
    return build(
        action="capture",
        summary=(f"Record the running config of {len(read)} of {len(entries)} device(s) as "
                 f"their goldens, in one commit: {changed} differ from their current golden, "
                 f"{departs} depart from committed intent."
                 + (" " + read_timing_words(timing) if timing else "")),
        targets=targets, what_not=what_not,
        nothing_left_out="Nothing: every device was read and matches its intent.",
        confirm=confirm, titles=CAPTURE_TITLES,
        explain={"confirm": [{"concept": "confirm-by-hash",
                              "text": "You are confirming these captures. Each device is read again "
                                      "at apply, and one whose config moved is refused."}]})


def _read_in_words(timing: dict, name: str) -> str:
    """One device's read time, split where it was measured (C188): the SSH
    connect (with `enable`) against `show running-config`."""
    per = (timing or {}).get("per_device_s", {})
    if name not in per:
        return "not timed"
    p = (timing or {}).get("phases_s", {}).get(name)
    if not p:
        return f"{per[name]} s"
    read = "not reached" if p.get("read_s") is None else f"{p['read_s']} s"
    return f"{per[name]} s (connect {p['connect_s']} s, show running-config {read})"


def read_timing_words(timing: dict) -> str:
    """How long the device reads took, in one sentence (C188): concurrently,
    against what one after another would have cost, and the slowest device,
    since a parallel read is only as fast as its slowest member."""
    if not timing or not timing.get("per_device_s"):
        return ""
    n = len(timing["per_device_s"])
    split = (f", of which connecting {timing['connect_series_s']} s and reading "
             f"{timing['read_series_s']} s" if timing.get("phases_s") else "")
    return (f"Read {n} device(s) {'at once' if timing.get('workers', 1) > 1 else ''} in "
            f"{timing['wall_s']} s (one after another: {timing['series_s']} s{split}); "
            f"slowest {timing['slowest']}, {timing['slowest_s']} s.").replace("  ", " ")


def capture_result(outcomes: list, save: dict, *, fleet: bool, timing: dict = None) -> dict:
    """*outcomes*: per device ``{device, outcome, diff, intent, reason}``;
    *save*: `save_golden()`'s answer, or ``{}`` when nothing was saved."""
    targets, did_not = [], []
    for o in outcomes:
        name, outcome = o["device"], o["outcome"]
        intent = o.get("intent") or {}
        words = OUTCOME_WORDS.get(outcome, outcome)
        recorded = outcome in ("captured", "unchanged")
        targets.append({
            "name": name, "outcome": outcome, "words": words, "reason": o.get("reason", ""),
            "sent": {"lines": list(o.get("diff") or []) if outcome == "captured" else [],
                     "caption": f"{len(o.get('diff') or [])} line(s) of its golden changed",
                     "none": ("Its golden already matched: measured, nothing to record."
                              if outcome == "unchanged" else "Nothing was recorded.")},
            "checks": ({"ran": True, "ok": intent.get("state") == "match",
                        "statements": ["committed intent: " + _intent_words(intent)],
                        "issues": list(intent.get("lines") or [])}
                       if recorded else
                       {"ran": False, "why": o.get("reason") or "nothing was recorded"}),
        })
        if not recorded:
            did_not.append({"target": name, "kind": outcome,
                            "text": words + (f": {o['reason']}" if o.get("reason") else ""),
                            "lines": []})
        elif intent.get("state") != "match":
            did_not.append({"target": name, "kind": "departs_from_intent",
                            "text": "Recorded, and it departs from committed intent ("
                                    + _intent_words(intent) + "): marked `Intent-Match: no`.",
                            "lines": []})
    for reason in (save or {}).get("baseline_denied") or []:
        did_not.append({"target": "the baseline", "kind": "no_baseline",
                        "text": "No baseline tag: " + reason, "lines": []})
    commit = (save or {}).get("commit", "")
    baseline = (save or {}).get("baseline", "")
    decision_only = bool((save or {}).get("decision_only"))
    denied = list((save or {}).get("baseline_denied") or [])
    changed = [o for o in outcomes if o["outcome"] == "captured"]
    unchanged = [o for o in outcomes if o["outcome"] == "unchanged"]
    recorded = changed + unchanged
    # "Recorded" means a golden CHANGED and a commit holds it (the operator,
    # 2026-09-28: "9 of 9 device(s) recorded" was drawn over a Save All that
    # wrote nothing). An unchanged device was MEASURED, and says so.
    if decision_only:
        statement = (f"No golden changed. Commit {commit[:12]} records the baseline "
                     f"decision ({'earned' if baseline else 'denied'}), so the reason is kept.")
    elif commit:
        statement = (f"Golden commit {commit[:12]} records "
                     f"{', '.join((save or {}).get('changed') or [])}. The commit's "
                     "`Intent-Match:` trailer says which captures depart from intent.")
    else:
        statement = "No commit: nothing changed, or nothing was recorded."
    if baseline:
        statement += (f" Baseline {baseline} was tagged: every device captured and at its "
                      "committed intent.")
    read_part = (f"{len(recorded)} of {len(outcomes)} device(s) read: {len(changed)} recorded "
                 f"as a new golden, {len(unchanged)} unchanged"
                 + (", so no golden changed" if recorded and not changed else "") + ".")
    if fleet and not baseline:
        # THE THING SAVE ALL WAS RUN FOR leads the result, as the preview led
        # with it: the operator ran it because the panel said to take a
        # current baseline, and the result never said none was taken.
        summary = ("No baseline was taken: " + ("; ".join(denied) if denied else
                   "not every device was captured") + ". " + read_part)
    else:
        summary = read_part + (f" Baseline {baseline} taken." if baseline else "")
    # A device that could not be read leads with WHY and what to do (the
    # operator, 2026-09-29): s3's connect failed on a Save All and the result
    # said only "s3 skipped", while the reason sat in a lower row and the log.
    unread = [o for o in outcomes if o["outcome"] == "unread"]
    if unread:
        summary = (" ".join(f"{o['device']} could not be read: "
                            f"{o.get('reason') or 'no reason was recorded'}."
                            for o in unread)
                   + (" Nothing was recorded for "
                      + ", ".join(o["device"] for o in unread)
                      + ". When it answers (its status dot on the Device page), "
                      + ("run Save All again: a baseline needs every device read. "
                         if fleet else "capture it again. "))
                   + summary)
    if timing:
        summary += " " + read_timing_words(timing)
    clean = (recorded and len(recorded) == len(outcomes)
             and all((o.get("intent") or {}).get("state") == "match" for o in recorded)
             and (baseline or not fleet) and (save or {}).get("ok", False))
    if not outcomes:
        level = "nothing"
    elif not recorded:
        level = "failed"
    elif clean:
        level = "success"
    elif fleet and not baseline and not changed:
        level = "failed"     # no golden moved and no baseline: nothing it was run for happened
    else:
        level = "partial"
    return build_result(
        action="capture", level=level,
        summary=summary,
        targets=targets, did_not=did_not,
        nothing_left_out="Nothing: every device was recorded and matches its intent.",
        record={"commit": commit, "tags": list((save or {}).get("tags") or []),
                "baseline": baseline, "statement": statement},
        not_watched="A capture records the device at one moment; nothing watches it after. "
                    "The drift check compares the device with this golden from now on, and the "
                    "Intent-Match trailer is what says whether this golden is what was intended.",
        titles=CAPTURE_RESULT_TITLES)


# ---------------------------------------------------------------------------
# Seed intent (C148, 7.3's first item): a device's first full intent, from
# its committed golden. Built here so the ONE renderer draws it.
# ---------------------------------------------------------------------------

SEED_TITLES = {"program": "What will be committed as its intent",
               "what": "What will be seeded"}
SEED_RESULT_TITLES = {"sent": "What was committed as intent",
                      "checks": "Can the template reproduce it",
                      "happened": "What was seeded"}

SEED_WORDS = {
    "seeded": "seeded: its intent is committed",
    "refused": "refused: nothing was committed",
    "moved": "refused: its golden moved since the preview, nothing was committed",
    "busy": "refused: another operation holds this device (C98), nothing was committed",
    "failed": "failed: the commit did not happen, and each file is back as it was",
    "unknown_device": "refused: not in this list, nothing was committed",
}

_INTENT_NOW = {"never_committed": "none committed",
               "bootstrap_only": "only the bootstrap onboarding wrote",
               "full": "full intent (a seed would replace it)"}


def _fidelity_words(e: dict) -> str:
    if e.get("fidelity") is None:
        return "not measured"
    return (f"{e['fidelity']}% round-trip, {e.get('coverage')}% modelled, "
            f"{len(e.get('unmodeled') or [])} unmodelled line(s)")


def seed_preview(entries: list, *, request) -> dict:
    """*entries*: `seed.public()` of each device's `entry_for()`."""
    targets, what_not = [], []
    for e in entries:
        name = e["device"]
        state = e.get("intent_state", "")
        ok = not e.get("error")
        if ok and not e.get("reproduced"):
            lines = ([f"not reproduced: {l}" for l in e.get("missing") or []]
                     + [f"rendered, not on the device: {l}" for l in e.get("extra") or []]
                     + [f"unmodelled: {l}" for l in e.get("unmodeled") or []])
            what_not.append({
                "target": name, "kind": "not_reproduced",
                "text": ("The template does not fully model this device ("
                         + _fidelity_words(e) + "). The seed still commits the intent, "
                         "unmodelled lines recorded as such, and a deploy to it stays "
                         "blocked until they are modelled or acknowledged in its intent "
                         "(`unmodeled_ack`)."),
                "lines": lines})
        if ok and state == "full":
            what_not.append({"target": name, "kind": "has_intent",
                             "text": ("Not seeded: it already has full committed intent, and a "
                                      "seed would replace what it SHOULD be with what it IS, "
                                      "erasing any intended change not yet deployed. Change it "
                                      "by editing its intent."),
                             "lines": []})
        targets.append({
            "name": name,
            "state": ("unseedable" if not ok else "has_intent" if state == "full" else "seedable"),
            "selectable": ok and bool(e.get("seedable")) and not e.get("busy"),
            "select_data": {"hash": e.get("hash") or "", "list": e.get("list") or ""},
            "program": {
                "lines": list(e.get("diff") or []) if ok else [],
                "caption": ("The intent document to commit, against what is committed now. "
                            "Nothing is sent to the device: seeding records what it should be"),
                "none": ("Nothing to commit: " + (e.get("error") or "")) if not ok
                        else "Its committed intent already equals the seed."},
            "operands": [
                {"name": "seed hash", "value": e.get("hash") or "none"},
                {"name": "from golden", "value": e.get("golden") or "none"},
                {"name": "platform", "value": e.get("platform") or "unknown"},
                {"name": "committed intent now", "value": _INTENT_NOW.get(state, state or "?")},
                {"name": "template", "value": _fidelity_words(e) if ok else "not parsed"},
                {"name": "secrets into the credential store",
                 "value": ", ".join(e.get("secret_refs") or []) or "none"}],
            "gates": ([gate("committed golden", "pass" if ok else "fail",
                            e.get("golden") and f"commit {e['golden']}" or (e.get("error") or ""))]
                      + ([gate("no full intent to replace",
                               "fail" if state == "full" else "pass",
                               "it has full committed intent: edit it instead"
                               if state == "full" else _INTENT_NOW.get(state, state))]
                         if ok else [])
                      + [busy_gate(e)]
                      + ([gate("golden unchanged since this preview", "at_apply",
                               "the golden is parsed again at apply, and a different seed hash "
                               "refuses this device")] if ok else [])),
        })
    what_not.append({"target": "the devices", "kind": "scope",
                     "text": "Nothing is sent to any device, and no golden changes: a seed "
                             "commits intent read from the golden.", "lines": []})
    seedable = sum(1 for t in targets if t["selectable"])
    return build(
        action="seed",
        summary=(f"Commit full intent for {seedable} of {len(entries)} device(s), parsed from "
                 f"each one's committed golden, in one commit. A seeded device's template "
                 f"plan then deploys toward this intent."),
        targets=targets, what_not=what_not,
        nothing_left_out="Nothing: every device can be seeded and its template reproduces it.",
        confirm=confirm_part(request, "approve"), titles=SEED_TITLES,
        explain={"confirm": [{"concept": "confirm-by-hash",
                              "text": "You are confirming this intent. Each golden is parsed "
                                      "again at apply, and a device whose seed moved is refused."}],
                 "program": [{"concept": "intent",
                              "text": "Intent is what the device SHOULD be. Seeding takes it "
                                      "from what the device IS, once; from then on a change is "
                                      "an edit to intent, deployed from a plan."}]})


def seed_result(outcomes: list, save: dict) -> dict:
    """*outcomes*: `seed.apply()`'s; *save*: `save_host_vars()`'s, or ``{}``."""
    targets, did_not = [], []
    for o in outcomes:
        name, outcome = o["device"], o["outcome"]
        e = o.get("entry") or {}
        words = SEED_WORDS.get(outcome, outcome)
        done = outcome == "seeded"
        targets.append({
            "name": name, "outcome": outcome, "words": words, "reason": o.get("reason", ""),
            "sent": {"lines": list(e.get("diff") or []) if done else [],
                     "caption": "Committed as its intent. Nothing was sent to the device",
                     "none": "Nothing was committed."},
            "checks": ({"ran": True, "ok": bool(e.get("reproduced")),
                        "statements": ["template: " + _fidelity_words(e),
                                       "secrets stored: " + (", ".join(o.get("secrets") or [])
                                                             or "none")],
                        "issues": list(e.get("unmodeled") or []) + list(e.get("missing") or [])}
                       if done else
                       {"ran": False, "why": o.get("reason") or "nothing was committed"}),
        })
        if not done:
            did_not.append({"target": name, "kind": outcome,
                            "text": words + (f": {o['reason']}" if o.get("reason") else ""),
                            "lines": []})
        elif not e.get("reproduced"):
            did_not.append({"target": name, "kind": "not_reproduced",
                            "text": "Seeded, and the template does not fully model it ("
                                    + _fidelity_words(e) + "): a deploy stays blocked until "
                                    "those lines are modelled or acknowledged.",
                            "lines": list(e.get("unmodeled") or [])})
    commit = (save or {}).get("commit", "")
    seeded = [o for o in outcomes if o["outcome"] == "seeded"]
    statement = (f"Intent commit {commit[:12]} (`Source: seed`, one `Seeded-From:` trailer per "
                 f"device naming its golden) records {', '.join(o['device'] for o in seeded)}."
                 if commit else "No intent commit: nothing was seeded.")
    clean = (seeded and len(seeded) == len(outcomes)
             and all((o.get("entry") or {}).get("reproduced") for o in seeded))
    level = ("nothing" if not outcomes else "success" if clean
             else "failed" if not seeded else "partial")
    return build_result(
        action="seed", level=level,
        summary=f"{len(seeded)} of {len(outcomes)} device(s) seeded.",
        targets=targets, did_not=did_not,
        nothing_left_out="Nothing: every device was seeded and its template reproduces it.",
        record={"commit": commit, "tags": [], "baseline": "", "statement": statement},
        not_watched="A seed records intent once. Nothing was sent, so nothing on the device "
                    "changed; its next deploy plans from this intent, and should propose "
                    "nothing until the intent is edited.",
        titles=SEED_RESULT_TITLES)


# ---------------------------------------------------------------------------
# Retire (7.3): the whole exit, previewed and confirmed. The model is r5's
# retirement commit (3592113): every step, and every thing it deliberately
# does NOT do, drawn before the confirm and again in the result.
# ---------------------------------------------------------------------------

RETIRE_TITLES = {"program": "What retire changes in the record, in order",
                 "what_not": "What retire does NOT do",
                 "what": "What will be retired"}
RETIRE_RESULT_TITLES = {"sent": "What was done", "checks": "The break-glass basis",
                        "happened": "What was retired", "did_not": "What retire did NOT do"}

#: Each refusal the plan can make, as the gate that draws it (plan()'s
#: `refused_by` keys). A key with no gate here would be a reason drawn
#: nowhere, and a test holds the two sets equal.
RETIRE_GATES = (
    ("list", "a list of that name exists", "the list is in the registry"),
    ("reason", "a reason is given", "it goes into the commit, the declaration and the history"),
    ("source", "the list is not NetBox-sourced", "a NetBox list's inventory is NetBox's"),
    ("present", "the device is in this list", "it has a row, an identity or files"),
    ("pending", "the device is not pending onboarding", "a pending device is abandoned instead"),
    ("clean", "no uncommitted changes would ride into the commit",
     "host_vars/, golden/ and the manifest are clean"),
    ("credentials", "the credential store can be read", "its override can be cleared"),
    ("netbox_mask", "NetBox holds no credential retire cannot mask",
     "its stored config context is masked, or will be, or holds none"),
)
BREAKGLASS_GATE = "a break-glass export holds its current credential"


def _retire_step_line(s: dict) -> str:
    return ("done already: " if s.get("done") else "") + s.get("what", "")


def retire_preview(plan: dict, *, busy: str, request) -> dict:
    """*plan*: `retire.plan()`'s. One target, the device."""
    name = plan.get("hostname") or "?"
    refused = plan.get("refused_by") or {}
    bg = plan.get("breakglass_log") or {}
    row_pending = any(s["key"] == "row" and not s["done"] for s in plan.get("steps") or [])
    gates = [gate(title, "fail" if key in refused else "pass",
                  refused.get(key) or ok_detail)
             for key, title, ok_detail in RETIRE_GATES]
    if row_pending:
        export = bg.get("export") or {}
        gates.append(gate(BREAKGLASS_GATE, "pass" if bg.get("ok") else "fail",
                          (f"the export log: the newest export of {plan.get('list_name')} "
                           f"({export.get('at')}, to {export.get('path')}) recorded its current "
                           "credential; checked again at apply. " + (bg.get("statement") or ""))
                          if bg.get("ok") else (bg.get("why") or "not established")))
    else:
        gates.append(gate(BREAKGLASS_GATE, "not_applicable",
                          "no CSV row: there is no stored credential to lose"))
    gates.append(busy_gate({"busy": busy}))
    gates.append(gate("plan unchanged since this preview", "at_apply",
                      "the plan is computed again at apply, and a different hash refuses "
                      "with nothing done"))
    selectable = bool(plan.get("ok")) and (bool(bg.get("ok")) or not row_pending) and not busy
    what_not = [{"target": name, "kind": "not_doing", "text": n, "lines": []}
                for n in plan.get("not_doing") or []]
    what_not += [{"target": name, "kind": "advisory", "text": "Advisory: " + a, "lines": []}
                 for a in plan.get("advisories") or []]
    if row_pending:
        what_not.append({"target": name, "kind": "basis", "lines": [], "text": (
            "This screen does not open the break-glass record: it cannot reach a file on "
            "your laptop. It trusts the EXPORT LOG on this host, which records what an export "
            "wrote, and cannot show the file still exists or that its passphrase is known. "
            "On the command line, `nmas-retire --breakglass <file>` opens the record itself.")})
    identity = plan.get("identity") or "none"
    export = bg.get("export") or {}
    target = {
        "name": name,
        "state": "retirable" if selectable else "refused",
        "selectable": selectable,
        "select_data": {"hash": plan.get("hash") or "", "list": plan.get("list_name") or "",
                        "reason": plan.get("reason") or ""},
        "program": {"lines": [_retire_step_line(s) for s in plan.get("steps") or []],
                    "caption": ("Each step is skipped if already done, so a retirement that "
                                "stopped part way is finished by running it again. Nothing is "
                                "sent to the device"),
                    "none": "Nothing to do: " + "; ".join(plan.get("refusals") or ["no steps"])},
        "operands": [
            {"name": "reason", "value": plan.get("reason") or "none given"},
            {"name": "list", "value": plan.get("list_name") or "?"},
            {"name": "identity", "value": identity},
            {"name": "management address", "value": plan.get("ip") or "none recorded"},
            {"name": "files removed (kept in history)",
             "value": ", ".join(plan.get("files") or []) or "none"},
            {"name": "startup config, frozen",
             "value": f"{plan.get('startup') or '?'} (lab {plan.get('lab') or '?'})"},
            {"name": "break-glass basis",
             "value": ("the export log (not the record): newest export "
                       f"{export.get('at') or 'none'}"
                       + (f", key {export.get('key_fingerprint')}"
                          if export.get("key_fingerprint") else ""))
                      if row_pending else "not needed: no CSV row"},
            {"name": "plan hash", "value": plan.get("hash") or "none"}],
        "gates": gates,
    }
    confirm = confirm_part(request, "approve")
    if selectable:
        files = ", ".join(plan.get("files") or []) or "no files"
        confirm["effect"] = (
            f"Retiring {name} takes it out of management. What SURVIVES: its intent and "
            f"golden ({files}) stay in history, the parent of the retire commit; "
            + (f"its credential survives ONLY in the break-glass export of "
               f"{export.get('at')} (to {export.get('path')}), since the CSV row is its only "
               "copy here and is deleted last. " if row_pending else "")
            + "To manage it again is onboarding or adopt, not an undo.")
        confirm["button"] = f"Retire {name}"
    return build(
        action="retire",
        summary=(f"Retire {name} from {plan.get('list_name')}: "
                 f"{sum(1 for s in plan.get('steps') or [] if not s['done'])} step(s) to do, "
                 "each one a change to the record, in one commit and the row last."),
        targets=[target], what_not=what_not,
        nothing_left_out="Nothing: retire states what it does not do on every run.",
        confirm=confirm, titles=RETIRE_TITLES,
        explain={"confirm": [{"concept": "confirm-by-hash",
                              "text": "You are confirming this plan. It is computed again at "
                                      "apply, and a different one refuses with nothing done."}]})


RETIRE_STEP_WORDS = {"netbox_mask": "masked the credentials NetBox held in its stored config "
                                    "context, read back clean (C139)",
                     "override": "cleared its credential override",
                     "declare": "declared its startup config deliberately unmapped",
                     "commit": "removed its intent and golden and released its identity, "
                               "in one commit",
                     "legacy": "deleted its file from the deprecated golden_configs/ store, "
                               "whose content survives in the repository (C176)",
                     "row": "deleted its CSV row, last"}


def retire_result(result: dict, plan: dict) -> dict:
    """*result*: `retire.apply()`'s; *plan*: the plan it ran (carried on a
    refusal, or recomputed by the route)."""
    name = (plan or {}).get("hostname") or "?"
    done = list(result.get("done") or [])
    ok = bool(result.get("ok"))
    basis = result.get("breakglass") or {}
    did_not = [{"target": name, "kind": "not_doing", "text": n, "lines": []}
               for n in (result.get("not_doing") or (plan or {}).get("not_doing") or [])]
    if not ok:
        did_not.insert(0, {"target": name, "kind": "stopped",
                           "text": ("Stopped" + (f" at {result['failed_at']}"
                                                 if result.get("failed_at") else "")
                                    + ": " + (result.get("error") or "no reason recorded")
                                    + (". " + result["note"] if result.get("note") else "")),
                           "lines": list(result.get("remaining") or [])})
    for a in result.get("advisories") or []:
        did_not.append({"target": name, "kind": "advisory", "text": "Advisory: " + a,
                        "lines": []})
    level = "success" if ok else ("partial" if done else "failed")
    commit = result.get("commit") or ""
    words = ("retired" if ok else
             "partly retired: run it again to finish" if done else "refused: nothing was done")
    return build_result(
        action="retire", level=level,
        summary=((f"{name} is retired." if ok else
                  f"{name} is PARTLY retired: " + ", ".join(done) + " done, the rest not."
                  if done else f"{name} was not retired: nothing was done.")),
        targets=[{"name": name, "outcome": "retired" if ok else "failed", "words": words,
                  "reason": result.get("error", ""),
                  "sent": {"lines": [RETIRE_STEP_WORDS.get(k, k) for k in done],
                           "caption": "Changes to the record. Nothing was sent to the device",
                           "none": "Nothing was done."},
                  "checks": ({"ran": True, "ok": True,
                              "statements": [basis.get("statement") or ""], "issues": []}
                             if basis.get("basis") else
                             {"ran": False, "why": basis.get("statement")
                              or "the break-glass check was not reached"})}],
        did_not=did_not,
        nothing_left_out="Nothing: every step was done.",
        record={"commit": commit, "tags": [], "baseline": "",
                "statement": (f"Retire commit {commit[:12]} (`Source: retire`, `Retired-Device: "
                              f"{name}`, one `Not-Done:` trailer per thing it did not do) removed "
                              "its intent and golden; history keeps both."
                              if commit else "No retire commit was made by this run.")},
        not_watched=(f"Nothing in NMAS watches {name} after this: no drift check, capture or "
                     "deploy. Oxidized still polls it, and NetBox still records it."),
        titles=RETIRE_RESULT_TITLES)
