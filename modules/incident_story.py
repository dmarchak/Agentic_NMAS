"""The incident's story at a glance (the GUI redesign brief §4.1, 2026-11-18; the mockup
design/incident-detail.html, its shots in design/shots/): the chain of events as one lifecycle
bar, a four-line summary (What, Likely cause, Evidence, Next), the AI's hypotheses with their
evidence, and the right rail's AI call (model, tokens, cost, latency). Built from what the page's
model already holds (`incident_page._page`) and the incident's troubleshooting record
(`fixit.incident.read`), never a value Mercury does not record: a panel whose data is not
recorded carries a ``needs`` line naming what is missing (the brief: "mark it needs: …").

**The lifecycle** (`STAGES`), each node ``{"name", "state", "at", "words"}`` with *state*
``done``, ``now``, ``todo``, ``skip`` (a stage this incident did not need: a self-heal that
fixed it needs no AI) or ``failed``:
- Detected: the page header's Detected cell;
- Self-heal tried: the header's Decided cell (the decision's own words);
- Diagnosing: the troubleshooting record's first ``start`` line (the AI asked);
- Fix proposed: its newest proposal line (its operation, its source);
- Approved: its approve choice (who, when);
- Applying: the fix's run (the card's run's first step, else the header's Fixed cell);
- Verifying: the run's verify step;
- Healed: the header's Verified cell; ``failed`` where the verify failed or the run did.
The first stage not done on an open incident is ``now``.

**The summary**: What from the BLUF (`bluf.what`); Likely cause from the newest proposal's first
hypothesis, else the page's What's wrong, else "Inconclusive: <why>" when the AI ended without a
fix; Evidence the BLUF's evidence (at most `EVIDENCE_SHOWN`, each its kind, time and words);
Next the page's own next step (`todo`), or "Nothing to do" on a resolved incident with its time
to repair.

**Hypotheses**: the newest proposal's (`shown.hypotheses`: claim, the reads it cites, the read
that confirms it), the first the one the plan acts on. Mercury records no hypothesis ruled out
with its reason, and no likelihood: both are ``needs`` lines.

**The AI call**: the newest call the record's proposals name (`calls.rows_since` within the
incident, never the whole record): model, prompt, tokens (input, cache write and read, output),
cost and latency.

Display only: nothing that decides reads it. Masked and its people named by the page's model
(`incident_page._page`), as every other part of the page."""

import datetime
import logging

log = logging.getLogger(__name__)

STAGES = ("Detected", "Self-heal tried", "Diagnosing", "Fix proposed", "Approved", "Applying",
          "Verifying", "Healed")
#: Evidence lines the summary draws; the rest stay in the BLUF's evidence below.
EVIDENCE_SHOWN = 4
#: What Mercury does not record yet, said on the panel that would draw it.
NEEDS = {
    "confidence": "a likelihood per hypothesis (the AI's answer carries none; Mercury's own "
                  "diagnosis has only decisive, strong or circumstantial)",
    "ruled_out": "the AI's ruled-out hypotheses, each with its reason (its answer carries none)",
    "severity": "a severity kept on the incident (the page derives it from impact)",
    "risk": "a risk level per plan",
}


def _cells(model: dict) -> dict:
    return {str(c.get("name") or ""): c for c in model.get("header") or []}


def _lines(network: str, found: dict) -> list:
    """The incident's troubleshooting record's lines, oldest first; [] when it has none or it
    cannot be read (the page's own section says so)."""
    from modules.fixit import incident as F
    from modules.fixit import section

    try:
        inc = section.incident_of(network, found).get("incident")
        return list(F.read(inc).get("lines") or []) if inc is not None else []
    except Exception as exc:                          # noqa: BLE001 (the story is display only)
        log.info("incident story: the troubleshooting record was not read: %s",
                 type(exc).__name__)
        return []


def _newest(lines: list, test) -> dict:
    for line in reversed(lines):
        if test(line):
            return line
    return {}


def _first(lines: list, test) -> dict:
    return next((line for line in lines if test(line)), {})


def _run_steps(model: dict) -> list:
    card = (model.get("fixit") or {}).get("card") or {}
    return [s for s in card.get("run") or [] if isinstance(s, dict)]


def lifecycle(model: dict, lines: list) -> list:
    """The eight nodes (`STAGES`) for *model* and its record's *lines*."""
    cells = _cells(model)
    start = _first(lines, lambda l: "start" in l)
    proposal = _newest(lines, lambda l: "proposal" in l)
    approve = _newest(lines, lambda l: l.get("choice") == "approve")
    steps = _run_steps(model)
    verify = next((s for s in steps if "verify" in str(s.get("key") or "")), {})
    detected, decided = cells.get("Detected") or {}, cells.get("Decided") or {}
    fixed, verified = cells.get("Fixed") or {}, cells.get("Verified") or {}
    ai = bool(start or proposal)
    failed = verified.get("state") == "failed" or fixed.get("state") == "failed"
    nodes = [
        ("Detected", detected.get("at"), detected.get("words") or ""),
        ("Self-heal tried", decided.get("at"), decided.get("words") or ""),
        ("Diagnosing", start.get("at"), "the AI asked" if start else ""),
        ("Fix proposed", proposal.get("at"),
         " ".join(x for x in (str(proposal.get("operation") or ""),
                              f"({proposal.get('source')})" if proposal.get("source") else "")
                  if x) if proposal else ""),
        ("Approved", approve.get("at"), f"by {approve.get('by')}" if approve.get("by") else ""),
        ("Applying", (steps[0].get("since") if steps else None) or fixed.get("at"),
         fixed.get("words") or ""),
        ("Verifying", verify.get("since") or (verified.get("at") if verified.get("at") else None),
         verify.get("words") or ""),
        ("Healed", verified.get("at") if not failed else None,
         # "not healed", never "verify failed": the page says that once, on its attempt line
         # (tests/test_incident_titles.py, each fact once).
         "not healed" if failed else (verified.get("words") or "")),
    ]
    resolved = bool(model.get("resolved"))
    fixit = model.get("fixit") or {}
    # "now" only where something is happening (tonight's shot of a rolled-back heal drew
    # Diagnosing "now" with nothing diagnosing it): a run in progress at its first undone
    # stage, a proposal waiting for its approval, or the AI investigating.
    running = bool((model.get("done") or {}).get("running")) and not resolved
    if resolved:
        now_at = ""
    elif running:
        now_at = "first"
    elif proposal and not approve:
        now_at = "Approved"
    elif start and not proposal and fixit.get("state") not in ("cant_fix", "ai_failed"):
        now_at = "Diagnosing"
    else:
        now_at = ""
    out, now_set = [], False
    for name, at, words in nodes:
        if name in ("Diagnosing", "Fix proposed", "Approved") and not ai and (
                resolved or fixed.get("at") or failed or running):
            state = "skip"
            words = words or "not needed: self-healing's own fix"
        elif name == "Healed" and failed:
            state = "failed"
        elif name == "Applying" and fixed.get("state") == "failed":
            state = "failed"
        elif at:
            state = "done"
        elif not now_set and (now_at == name or now_at == "first"):
            state, now_set = "now", True
        else:
            state = "todo"
        out.append({"name": name, "state": state, "at": at or "", "words": words})
    return out


def summary(model: dict, lines: list) -> dict:
    """The four lines: what, cause, evidence (chips), next; ``inconclusive`` when the AI ended
    without a fix and nothing else names a cause."""
    fixit = model.get("fixit") or {}
    bluf = fixit.get("bluf") or {}
    proposal = _newest(lines, lambda l: "proposal" in l)
    hyps = ((proposal.get("shown") or {}).get("hypotheses") or [])
    evidence = [{"kind": str(e.get("kind") or ""), "at": str(e.get("at") or ""),
                 "words": str(e.get("words") or "")}
                for e in (bluf.get("evidence") or [])[:EVIDENCE_SHOWN] if isinstance(e, dict)]
    cause, inconclusive = "", False
    if hyps:
        cause = str(hyps[0].get("claim") or "")
    elif fixit.get("state") in ("cant_fix", "ai_failed") or fixit.get("ai_failed"):
        cause, inconclusive = f"Inconclusive: {fixit.get('why') or 'the AI named no cause'}", True
    else:
        # No hypothesis: the kind of what opened it (`heal.incidents.KIND_WORDS`), never the
        # page's What's wrong, which says the fix or the reason it cannot be made (tonight's
        # shots: "Mercury is putting it back itself ..." and a can't-fix's reason drawn as the
        # cause; each fact once).
        from modules.heal.incidents import KIND_WORDS
        words = next((KIND_WORDS[e["kind"]] for e in evidence if e["kind"] in KIND_WORDS), "")
        cause = words[:1].upper() + words[1:]
    todo = model.get("todo") or {}
    if model.get("resolved"):
        ttr = (model.get("ttr") or {}).get("words") or ""
        nxt = "Nothing to do" + (f": resolved in {ttr}" if ttr else "")
    else:
        nxt = str(todo.get("words") or "")
    return {"what": str(bluf.get("what") or model.get("title") or ""), "cause": cause,
            "inconclusive": inconclusive, "evidence": evidence,
            "evidence_more": max(0, len(bluf.get("evidence") or []) - len(evidence)),
            "next": nxt}


def hypotheses(lines: list) -> list:
    """The newest proposal's hypotheses, the first the one its plan acts on."""
    proposal = _newest(lines, lambda l: "proposal" in l)
    out = []
    for n, h in enumerate((proposal.get("shown") or {}).get("hypotheses") or []):
        if isinstance(h, dict):
            out.append({"claim": str(h.get("claim") or ""), "chosen": n == 0,
                        "cites": [str(c) for c in h.get("cites") or []],
                        "confirm": str(h.get("confirm") or "")})
    return out


def ai_call(lines: list, detected_epoch) -> dict:
    """The newest call the record's proposals name, from the record of AI calls within the
    incident; ``{}`` when no proposal names one, ``{"state": "unreadable"}`` when it cannot be
    read."""
    ids = [c for line in lines if "proposal" in line for c in line.get("calls") or []]
    if not ids:
        return {}
    from modules.ai import calls

    try:
        since = datetime.datetime.fromtimestamp(float(detected_epoch or 0),
                                                datetime.timezone.utc)
        got = calls.rows_since(since)
    except Exception as exc:                          # noqa: BLE001 (display only)
        return {"state": "unreadable", "id": ids[-1], "error": type(exc).__name__}
    if got.get("state") == "unreadable":
        return {"state": "unreadable", "id": ids[-1], "error": got.get("error") or ""}
    row = next((r for r in got.get("rows") or [] if r.get("id") == ids[-1]), None)
    if row is None:
        return {"state": "missing", "id": ids[-1]}
    t = row.get("tokens") or {}
    return {"state": "ok", "id": ids[-1], "model": str(row.get("model") or ""),
            "prompt": str(row.get("prompt") or ""),
            "tokens": {"input": int(t.get("input_tokens") or 0),
                       "cache_write": int(t.get("cache_creation_input_tokens") or 0),
                       "cache_read": int(t.get("cache_read_input_tokens") or 0),
                       "output": int(t.get("output_tokens") or 0)},
            "usd": float(row.get("cost_usd") or 0.0),
            "latency_s": float(row.get("latency_s") or 0.0), "calls": len(set(ids))}


def build(model: dict, network: str, found: dict) -> dict:
    """The story for the page's *model*, its incident *found* by `incident_page.resolve`."""
    lines = _lines(network, found)
    inc = (found or {}).get("incident") or {}
    return {"lifecycle": lifecycle(model, lines), "summary": summary(model, lines),
            "hypotheses": hypotheses(lines),
            "ai": ai_call(lines, inc.get("opened_epoch")),
            "needs": dict(NEEDS)}
