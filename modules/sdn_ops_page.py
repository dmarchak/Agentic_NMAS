"""What SDN's operation cards and the Responses tab draw (PHASE8_PLAN 17.1 S8 to S10, S16;
boards SdnResponse, SdnResponses and SdnFlowEdit, signed off 2026-10-27 under the Phase 7
mode). Reads only: the stores the operations keep and the plan or result handed in.

- `preview`, `response_preview`: the card in place of the control: what it does, exactly these
  requests (method, path, body), what will not happen, the warnings, the checks, Verify's
  limit (S20), the hash it is bound to, and the hidden fields the confirm carries back (the
  ask as JSON, unchanged, and the hash);
- `result`: the outcome first (green only when every gating check passed), Verify's checks,
  the counters, the rollback, the record;
- `responses_view`: the responses awaiting a person, the mode, the loop and its log, the
  detection rules' thresholds and the response timeouts.
"""

import json

#: A response's parameters as its card draws them.
PARAMS_DRAWN = ("source", "targets", "hard_timeout", "priority", "rate", "unit", "burst",
                "meter_id", "flow", "cookie")
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
    person's, who and when)."""
    c = row.get("classification")
    if not isinstance(c, dict):
        return None
    from modules.ai import profiles
    model = c.get("model") or ""
    words = profiles.MODELS.get(model, {}).get("words", model)
    return {"threat_detected": bool(c.get("threat_detected")),
            "threat_type": (c.get("threat_type") or "").replace("_", " "),
            "severity": c.get("severity") or "", "devices": list(c.get("affected_devices") or []),
            "recommended": c.get("recommended_action") or "", "reasoning": c.get("reasoning") or "",
            "action": c.get("action_id") or "", "params": dict(c.get("params") or {}),
            "refs": list(c.get("evidence_refs") or []), "call_id": c.get("call_id") or "",
            "model": words, "cost_usd": float(c.get("cost_usd") or 0.0),
            "by": ("a person" if c.get("trigger") == "person" else "the loop"),
            "who": row.get("classified_by") or "", "at": row.get("classified_at") or row.get("at")}


def responses_view(network: str) -> dict:
    """SDN › Responses (board SdnResponses)."""
    from modules.sdn import closed_loop, detect, flow_ops, loop, modes

    awaiting = loop.awaiting(network)
    rows = []
    for r in awaiting["rows"]:
        d = r.get("detection") or {}
        entry = closed_loop.CATALOGUE.get(r.get("action") or "", {})
        rows.append({"id": r.get("id"), "at": r.get("at"), "rule": d.get("rule"),
                     "title": d.get("title") or d.get("rule"), "words": d.get("words"),
                     "source": d.get("source"), "dpid_hex": d.get("dpid_hex"),
                     "confidence": d.get("confidence"), "action": r.get("action"),
                     "label": entry.get("label", r.get("action")),
                     "risk": r.get("risk"), "action_words": entry.get("words", ""),
                     "why": r.get("why", ""),
                     "classified": r.get("classified") or closed_loop.DEFAULT_WORDS,
                     "ai": _classification(r), "params": dict(r.get("params") or {})})
    th = detect.thresholds(network)
    limits = flow_ops.settings_of(network)
    log_rows = loop.log_lines(network, 30)
    return {"network": network, "tab": "responses", "listed": "ok", "awaiting": rows,
            "awaiting_state": awaiting["state"], "awaiting_error": awaiting["error"],
            "mode": modes.current(network), "loop": loop.status(network),
            "log": list(reversed(log_rows["rows"])), "log_error": log_rows["error"],
            "thresholds": th, "limits": limits, "risks": modes.RISKS,
            "max_hours": modes.MAX_AUTO_SECONDS // 3600,
            "verify_limit": flow_ops.VERIFY_LIMIT, "controllers": True,
            # A person's Classify answered in place: its refusal drawn on its card (the route
            # sets it; a read has none).
            "classify": None}
