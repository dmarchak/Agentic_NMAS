"""What SDN's operation cards and the Responses tab draw (PHASE8_PLAN 17.1 S8 to S10, S16;
boards SdnResponse, SdnResponses and SdnFlowEdit, signed off 2026-10-27 under the Phase 7
mode). Reads only: the stores the operations keep and the plan or result handed in.

- `preview`, `response_preview`, `reapply_preview` (a lost response put back, C2018): the card
  in place of the control: what it does, exactly these
  requests (method, path, body), what will not happen, the warnings, the checks, Verify's
  limit (S20), the hash it is bound to, and the hidden fields the confirm carries back (the
  ask as JSON, unchanged, and the hash);
- `result`: the outcome first (green only when every gating check passed), Verify's checks,
  the counters, the rollback, the record;
- `responses_view`: the incidents awaiting a person (C1999, `incident_rows`: one response
  each, a compact table by severity then age, filtered by words or a severity, the detail on
  expand; board SdnResponses revised 2026-10-28), the mode, the loop and its log, the
  detection rules' thresholds and the response timeouts.
"""

import json

#: A response's parameters as its card draws them.
PARAMS_DRAWN = ("source", "source_from", "targets", "hard_timeout", "priority", "rate", "unit",
                "burst", "meter_id", "flow", "cookie")
OUTCOME = {"verified": ("Done, verified", "ok"),
           "rolled_back": ("Rolled back: Verify or a request failed", "warn"),
           "rollback_failed": ("Rollback did not complete: look at the switch now", "danger"),
           "refused": ("Nothing was sent", "danger")}


def _requests(steps: list) -> list:
    return [{"line": f"{s['request']['method']} {s['request']['path']}",
             "body": s["request"]["body"], "words": s["words"]} for s in steps or []]


def refused(network: str, kind: str, words: str) -> dict:
    return {"network": network, "kind": kind, "state": "refused", "error": words}


def preview(network: str, kind: str, ask: dict, plan: dict, extra: dict = None) -> dict:
    """A plan drawn as its preview card (or its refusal)."""
    if not plan.get("ok"):
        return dict(refused(network, kind, plan.get("error") or "the plan was refused"),
                    **(extra or {}))
    return {"network": network, "kind": kind, "state": "preview",
            "connection": plan["connection"], "dpid_hex": plan["dpid_hex"],
            "words": plan["words"], "requests": _requests(plan["steps"]),
            "will_not": plan["will_not"], "warnings": plan["warnings"],
            "checks": plan["checks"], "hash": plan["hash"], "short": plan["hash"][:12], "needs_typed": plan["needs_typed"],
            "ask": json.dumps(ask, sort_keys=True), "count": len(plan["steps"]),
            **(extra or {})}


def response_preview(network: str, row: dict, got: dict) -> dict:
    """A response's preview: the plan's card with the detection, the action and its risk, and
    who chose the action (the AI call that proposed it, or the catalogue's default)."""
    from modules.sdn import closed_loop

    params = got.get("params") or {}
    extra = {"rid": row.get("id"), "action": got.get("action"), "risk": got.get("risk"),
             "detection": {"words": (row.get("detection") or {}).get("words", "")},
             "params": {k: params[k] for k in PARAMS_DRAWN if k in params},
             "label": closed_loop.CATALOGUE.get(got.get("action") or "", {}).get("label", ""),
             "classified": closed_loop.classified_words(row.get("classification"),
                                                        got.get("action") or "")}
    if not got.get("ok") or not got.get("plan"):
        return dict(refused(network, "response", got.get("error") or "refused"), **extra)
    return preview(network, "response", got["ask"], got["plan"], extra)


def reapply_preview(network: str, got: dict) -> dict:
    """A lost response's Re-apply… preview (C2018): the plan's card with what it puts back and
    until when (`reapply.preview`'s words), or its refusal."""
    from modules.sdn import reapply

    extra = {"label": "Re-apply: " + reapply.response_words(got.get("response") or {}),
             "reapply_words": got.get("words", "")}
    if not got.get("ok") or not got.get("plan"):
        return dict(refused(network, "reapply", got.get("error") or "refused"), **extra)
    return preview(network, "reapply", got["ask"], got["plan"], extra)


def _rollback(rb: dict) -> dict:
    return {"ran": bool(rb.get("ran")),
            "steps": [{k: s.get(k, "") for k in ("role", "state", "words", "error")}
                      for s in rb.get("steps") or []],
            "read_back": [{"state": c.get("state"), "words": c.get("words")}
                          for c in rb.get("read_back") or []]}


def result(network: str, kind: str, done: dict) -> dict:
    words, tone = OUTCOME.get(done.get("outcome"), ("Unknown outcome", "danger"))
    sent = []
    for s in done.get("sent") or []:
        answer = s.get("answer") or {}
        sent.append({"line": f"{s['request']['method']} {s['request']['path']}",
                     "answer": (f"HTTP {answer.get('status')}, sent" if answer.get("ok") else
                                f"refused: {answer.get('error')}")})
    return {"network": network, "kind": kind, "state": "result",
            "outcome_words": words, "tone": tone, "error": done.get("error", ""),
            "id": done.get("id", ""),
            "checks": [{"state": c.get("state"), "words": c.get("words")}
                       for c in (done.get("verify") or {}).get("checks") or []],
            "counters": [{"words": c.get("words")} for c in done.get("counters") or []],
            "rollback": _rollback(done.get("rollback") or {}),
            "record": done.get("record") or {}, "sent": sent, "note": done.get("note", "")}


def carried_ask(form) -> tuple:
    """``(ask, refusal)``: the preview's ask, carried back by the confirm as JSON."""
    try:
        ask = json.loads(form.get("ask") or "")
    except ValueError:
        return None, "the confirm carried no preview (its ask): nothing was sent; preview again"
    if not isinstance(ask, dict):
        return None, "the confirm's ask is not an operation: nothing was sent"
    return ask, ""


def _classification(row: dict):
    """A response's AI classification as the card draws it (board SdnResponses' AI box), or
    None: its threat, severity, type, the devices it names, its recommendation and reasoning,
    the catalogue action it proposed (``none``: a person decides) and its parameters, the
    evidence ids it cites, and the call (its id, model, cost, and whose: the loop's or a
    person's, who and when). A severity an unauthorised flow's effect raised in code
    (`closed_loop.apply_floor`, C2021) carries the model's own rating and the floor's words, so
    the card never shows the code's severity as the model's."""
    c = row.get("classification")
    if not isinstance(c, dict):
        return None
    from modules.ai import profiles
    model = c.get("model") or ""
    words = profiles.MODELS.get(model, {}).get("words", model)
    return {"threat_detected": bool(c.get("threat_detected")),
            "threat_type": (c.get("threat_type") or "").replace("_", " "),
            "severity": c.get("severity") or "",
            "severity_from_model": c.get("severity_from_model") or "",
            "severity_floor": c.get("severity_floor") or "",
            "devices": list(c.get("affected_devices") or []),
            "recommended": c.get("recommended_action") or "", "reasoning": c.get("reasoning") or "",
            "action": c.get("action_id") or "", "params": dict(c.get("params") or {}),
            "refs": list(c.get("evidence_refs") or []), "call_id": c.get("call_id") or "",
            "model": words, "cost_usd": float(c.get("cost_usd") or 0.0),
            "by": ("a person" if c.get("trigger") == "person" else "the loop"),
            "who": row.get("classified_by") or "", "at": row.get("classified_at") or row.get("at")}


#: C1971: the most lines of one run the log panel draws. A 3-minute run at the shortest interval
#: (5 s) writes about 150 lines (two to five a pass); 2,000 holds a run of about 40 minutes at
#: that interval and keeps the page's HTML near 200 kB. A longer run is drawn newest first to
#: this many, the panel saying how many of how many, and Download log gives every line.
LOG_PANEL_LINES = 2000


def log_view(network: str, run: str = "") -> dict:
    """The loop's log panel (C1971): one run whole, newest line first, *run* the job id asked
    for (the newest run when empty). ``{"network", "job", "at", "until", "lines", "count",
    "drawn", "runs", "state", "error"}``: *count* every line of the run, *drawn* those drawn
    (at most `LOG_PANEL_LINES`); *runs* every run in the log, newest first, for the picker."""
    from modules.sdn import loop

    got = loop.run_log(network, run)
    rows = got["rows"]
    lines = [{"at": r.get("at") or "", "step": r.get("step") or "", "words": r.get("words") or ""}
             for r in reversed(rows[-LOG_PANEL_LINES:])]
    return {"network": network, "job": got["job"], "at": got["at"], "until": got["until"],
            "lines": lines, "count": len(rows), "drawn": len(lines), "runs": got["runs"],
            "state": got["state"], "error": got["error"]}


#: Each rule as the rules table names it.
RULE_LABELS = {"scan": "Scan", "flood": "Flood", "unauthorised_flow": "Unauthorised flow"}
#: Where the network's response policy comes from, in words (`list_settings.resolve`'s origin).
POLICY_ORIGIN = {"set here": "set on this network",
                 "unset everywhere": "the default: every catalogue action that answers the rule",
                 "unset here": "the default: every catalogue action that answers the rule"}


def policy_view(network: str) -> dict:
    """The response policy as the rules table draws it and its form edits it (the Lab 8
    walk's objective 3.1): per rule, the catalogue actions that answer it, those the policy
    allows and its default; *loaded*, the policy as drawn, which Save carries back (or
    ``unreadable``); where it comes from. A policy that cannot be read is drawn as that, its
    reason said, and every rule shown allowing nothing."""
    from modules import list_settings
    from modules.sdn import closed_loop as CL

    pol = CL.policy(network)
    try:
        origin = list_settings.resolve(network, CL.POLICY_KEY)[1]
    except Exception as exc:                          # noqa: BLE001 (said as unread)
        origin = f"not read ({type(exc).__name__})"
    rows = []
    for rule in CL.RULES:
        got = pol["rules"].get(rule) or {}
        rows.append({"rule": rule, "label": RULE_LABELS[rule], "default": got.get("default", ""),
                     "allowed": list(got.get("allowed") or []),
                     "answers": [{"id": a, "label": CL.CATALOGUE[a]["label"],
                                  "risk": CL.CATALOGUE[a]["risk"]} for a in CL.answering(rule)]})
    loaded = (json.dumps({r: pol["rules"][r]["allowed"] for r in CL.RULES}, sort_keys=True)
              if pol["ok"] else "unreadable")
    return {"ok": pol["ok"], "error": pol["error"], "rows": rows, "loaded": loaded,
            "by_rule": {r["rule"]: r for r in rows},
            "origin": POLICY_ORIGIN.get(str(origin), str(origin))}


#: An incident's severity as its table row and the summary name it (`incidents.severity`).
SEVERITY_WORDS = {"critical": "Critical", "high": "High", "unclassified": "Not classified",
                  "medium": "Medium", "low": "Low", "none": "No threat"}
#: Each severity's chip colour.
SEVERITY_TONE = {"critical": "danger", "high": "danger", "unclassified": "warn",
                 "medium": "warn", "low": "muted", "none": "muted"}
#: Incidents drawn before the table says how many more a filter would show; the rest are
#: counted, never drawn as one long list (CLAUDE.md, "Built for large fleets").
INCIDENTS_DRAWN = 50


def _verdict(r: dict, ai: dict) -> str:
    """The AI verdict column: the classification in a few words, or why there is none."""
    if ai:
        return (f"{ai['threat_type'] or 'a threat'}, {ai['severity']}" if ai["threat_detected"]
                else f"no threat, {ai['severity'] or 'none'}")
    words = r.get("classified") or ""
    return "refused" if words.startswith("AI classification refused") else "not classified"


def incident_rows(awaiting: dict) -> list:
    """The incidents awaiting a person (C1999; board SdnResponses), as the table draws them:
    each its rule, source, how many switches saw it, the ingress and the switches seen also,
    its age, the AI verdict and the proposed action, by severity then the longest waiting."""
    from modules.sdn import closed_loop, incidents

    rows = []
    for r in incidents.order(awaiting["rows"]):
        d = r.get("detection") or {}
        inc = r.get("incident") or {}
        entry = closed_loop.CATALOGUE.get(r.get("action") or "", {})
        ai = _classification(r)
        sev = incidents.severity(r)
        # Each switch seen also as its list draws it (the DPID in hex; the detection's key and
        # numeric DPID stay in the store).
        also = [{k: s.get(k) for k in ("dpid_hex", "port", "connection", "at", "words")}
                for s in r.get("seen_also") or []]
        rows.append({"id": r.get("id"), "at": r.get("at"), "rule": d.get("rule"),
                     "rule_label": RULE_LABELS.get(d.get("rule"), d.get("rule") or ""),
                     "title": d.get("title") or d.get("rule"), "words": d.get("words"),
                     "source": d.get("source"), "dpid_hex": d.get("dpid_hex"),
                     "confidence": d.get("confidence"), "action": r.get("action"),
                     "label": entry.get("label", r.get("action")),
                     "risk": r.get("risk"), "action_words": entry.get("words", ""),
                     "why": r.get("why", ""),
                     "classified": r.get("classified") or closed_loop.DEFAULT_WORDS,
                     "refused_call": r.get("refused_call") or "",
                     "inactive_since": r.get("inactive_since") or "",
                     "ai": ai, "params": dict(r.get("params") or {}),
                     "severity": sev, "severity_words": SEVERITY_WORDS[sev],
                     "severity_tone": SEVERITY_TONE[sev], "verdict": _verdict(r, ai),
                     "switches": 1 + len(also), "seen_also": also,
                     "last_seen": r.get("last_seen") or r.get("at"),
                     "ingress_known": bool(inc.get("ingress_known")),
                     "ingress_words": inc.get("ingress_words") or (
                         "kept before incidents were grouped (C1999): proposed at the switch "
                         "that saw it"),
                     "window_words": inc.get("window_words") or "",
                     "pick": _pick(d, r.get("action"))})
    return rows


#: The catalogue actions that act on a source address, so the card says where it came from.
SOURCE_ACTIONS = ("drop_source", "rate_limit_source")


def _pick(d: dict, action: str) -> dict:
    """The card's source line and picker (C2002; board SdnResponses revised for C2002): how the
    detection's source was found (``named``), the hosts a person chooses among (``several``,
    each ``{"address", "label"}``), why there is none to choose (``none``, ``no_address``,
    ``link``: no Preview), or that the preview reads the topology again (``unread``, or a
    detection kept before C2002 naming none: ``lookup``). Empty ``state`` for an action that
    acts on no source, or a source the flows named (nothing more to say)."""
    from modules.sdn import closed_loop

    out = {"state": "", "words": "", "hosts": [], "port": d.get("port")}
    if action not in SOURCE_ACTIONS:
        return out
    choice = closed_loop.source_choice(d)
    state = choice["state"]
    if state == "named" and not choice["words"]:
        return out
    if state == "" and d.get("port") is not None:
        state = "lookup"
    out.update(state=state, words=choice["words"], port=choice.get("port", d.get("port")),
               hosts=[{"address": h["address"],
                       "label": f"{h['address']} ({h['mac']})" if h.get("mac") else h["address"]}
                      for h in choice["hosts"]] if state == "several" else [])
    return out


def _matches(row: dict, q: str) -> bool:
    text = " ".join(str(x or "") for x in (
        row["rule_label"], row["title"], row["source"], row["dpid_hex"], row["label"],
        row["action"], row["verdict"], row["severity_words"],
        *[s.get("dpid_hex") for s in row["seen_also"]])).lower()
    return all(word in text for word in q.lower().split())


def responses_view(network: str, run: str = "", q: str = "", sev: str = "",
                   incident: str = "") -> dict:
    """SDN › Responses (board SdnResponses). *run*: the loop run whose log the panel draws
    (C1971; the newest when empty). *q* and *sev* filter the incidents (words each row must
    hold; one severity); *incident* names the one drawn open (Needs attention's link)."""
    from modules import sdn_page
    from modules.sdn import detect, flow_ops, incidents, loop, modes

    awaiting = loop.awaiting(network)
    every = incident_rows(awaiting)
    q, sev = (q or "").strip(), sev if sev in incidents.SEVERITY_ORDER else ""
    shown = [r for r in every if (not sev or r["severity"] == sev) and (not q or _matches(r, q))]
    counts = [{"severity": s, "words": SEVERITY_WORDS[s], "tone": SEVERITY_TONE[s],
               "count": sum(1 for r in every if r["severity"] == s)}
              for s in incidents.SEVERITY_ORDER]
    th = detect.thresholds(network)
    limits = flow_ops.settings_of(network)
    return {"network": network, "tab": "responses", "listed": "ok",
            "awaiting": shown[:INCIDENTS_DRAWN],
            "incidents": {"total": len(every), "shown": len(shown),
                          "drawn": min(len(shown), INCIDENTS_DRAWN),
                          "switches": sum(r["switches"] for r in every),
                          "counts": [c for c in counts if c["count"]], "q": q, "sev": sev,
                          "open": (incident or "").strip()},
            "awaiting_state": awaiting["state"], "awaiting_error": awaiting["error"],
            # The mode as drawn (C2082): AUTO or HITL and its words, which carry who, why,
            # until when, the allowed risk, an unreadable record and a lapsed AUTO.
            "mode": {k: v for k, v in modes.current(network).items() if k in ("mode", "words")},
            "loop": loop.status(network),
            # C2009: the network's stage; Turn AUTO on is drawn only on a network marked lab,
            # and AUTO recorded on elsewhere is drawn suspended (`modes.decide` runs nothing).
            "stage": {k: v for k, v in sdn_page.stage_line(network).items() if k != "stages"},
            "log": log_view(network, run),
            "thresholds": th, "limits": limits, "risks": modes.RISKS,
            "max_hours": modes.MAX_AUTO_SECONDS // 3600,
            "verify_limit": flow_ops.VERIFY_LIMIT, "controllers": True,
            "policy": policy_view(network),
            # A person's Classify answered in place: its refusal drawn on its card (the route
            # sets it; a read has none).
            "classify": None}
