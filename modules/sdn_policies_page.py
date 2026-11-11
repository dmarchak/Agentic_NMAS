"""SDN › Policies' data (Lab 9 Objective B2; board docs/boards/lab9-sdn.html artboard E): the tab
(`policies_view`: the words box's model and cost, and the network's committed policies from its
flow intent), a draft's or a check's answer as the card draws it (`answer_view`), and a
policy's preview as the flow-operation card draws it (`preview_card`). Reads only: the
committed policies are the flow intent's records, never a switch read."""

import json
import logging

log = logging.getLogger(__name__)

#: The committed policies the tab draws before "and N more" (each is a few flows).
POLICIES_DRAWN = 25


def policy_json(policy: dict) -> str:
    """What a form carries back of a policy: its id, words, rules, call and any choice made."""
    keep = ("id", "network", "words", "call_id", "rules", "instead")
    return json.dumps({k: policy[k] for k in keep if k in (policy or {})}, sort_keys=True)


def pin_words() -> dict:
    """The words box's model and its per-call cap, as the board draws them beside Draft."""
    from modules.ai import profiles
    from modules.sdn import policy_intent

    pin = profiles.task(policy_intent.FEATURE)
    return {"model": profiles.profile(pin["model"])["words"],
            "cap": f"{profiles.cap_per_call(policy_intent.FEATURE):.4f}"}


def _rule_lines(rules: list) -> list:
    from modules.sdn import policy_intent

    out = []
    for r in rules or []:
        try:
            out.append(policy_intent.rule_words(policy_intent.Rule.model_validate_json(
                json.dumps(r))))
        except ValueError:
            out.append("a rule not of the policy's shape")
    return out


def policies_view(network: str) -> dict:
    """The tab: ``{"network", "export", "committed", "pin"}``."""
    from modules.nsot import export as X
    from modules.sdn import policy_intent
    from modules.sdn.drivers.base import dpid_hex

    got = X.read(network)
    export = ({"state": "ok", "error": "", "sha256": got["sha256"]} if got["ok"] else
              {"state": "none" if got.get("absent") else "unreadable", "error": got["error"],
               "sha256": ""})
    held = policy_intent.committed(network)
    rows = []
    for p in held["policies"][:POLICIES_DRAWN]:
        dpids = sorted({f.get("dpid") for f in p["flows"] if f.get("dpid") is not None})
        rows.append({"id": p["id"], "words": p["words"], "rules": _rule_lines(p["rules"]),
                     "switches": [dpid_hex(d) for d in dpids], "flows": len(p["flows"]),
                     "by": p["by"], "at": p["at"], "operation": p["operation"]})
    return {"network": network, "export": export, "pin": pin_words(),
            "committed": {"state": held["state"], "error": held["error"], "rows": rows,
                          "more": max(0, len(held["policies"]) - POLICIES_DRAWN)}}


def answer_view(network: str, got: dict) -> dict:
    """A draft's or a check's answer as the card draws it: its state (``asked``, ``refused``,
    ``question``, ``checked``), the words as typed, the title and words, the checks' rows,
    Mercury's choices, the refusal's offers, the policy the next control carries, and the
    call's id and cost."""
    from modules import sdn_ops_page
    from modules.sdn import policy_intent

    a = {"network": network, "state": got.get("state", "refused"), "kind": got.get("kind", ""),
         "title": got.get("title") or policy_intent.TITLES.get(got.get("kind", ""), ""),
         "words": got.get("words", ""), "typed": got.get("words_typed", ""),
         "decided": got.get("decided", ""), "call_id": got.get("call_id", ""),
         "cost": f"{float(got.get('cost_usd') or 0.0):.4f}", "by": got.get("by", "mercury"),
         "rows": list(got.get("rows") or []), "offers": list(got.get("offers") or []),
         "typed_masked": got.get("typed_masked"),
         # A policy the protected set refused keeps a record of its own (C2944).
         "refusal": sdn_ops_page.refusal_said(got.get("refusal"))}
    ask = got.get("ask") if got.get("state") == "asked" else None
    a["choices"] = ({"word": ask["word"], "candidates": ask["candidates"]} if ask else None)
    policy = got.get("policy")
    a["policy"] = policy_json(policy) if policy and policy.get("rules") else ""
    a["rules"] = _rule_lines((policy or {}).get("rules")) if policy else []
    a["instead"] = ((policy or {}).get("instead") or {}) if got.get("state") == "checked" else {}
    return a


def preview_card(network: str, got: dict, refusal: dict = None) -> dict:
    """A policy's preview (`policy_intent.preview`) as the flow-operation card draws it, with
    the policy's own header and the policy the confirm carries; or its refusal, with the
    record it kept when the protected set refused it (*refusal*, C2944)."""
    from modules import sdn_ops_page

    chk = got.get("check") or {}
    policy = chk.get("policy") or {}
    if not chk.get("ok"):
        return sdn_ops_page.refused(network, "policy", f"{chk.get('title') or 'refused'}: "
                                                       f"{chk.get('words', '')}", refusal)
    extra = {"label": f"Policy {policy.get('id', '')}: {policy.get('words', '')}",
             "policy": policy_json(policy)}
    return sdn_ops_page.preview(network, "policy", chk["ask"], got["plan"], extra,
                                refusal=refusal)
