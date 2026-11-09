"""An incident event put into a message, and the egress mask on every byte of it.

**What a message carries** (docs/HEAL_TO_INTENT.md section 10): Mercury's facts first
(detected what and when, each step tried and its result, the outcome, what to do), then the
link. An event is a closed set of fields (`FIELDS`); any other key is refused by name, so a
caller cannot hand a configuration's lines in under a new name: the heal says each unit by its
kind ("inbound ACL added on Gi2, 2 lines, content withheld"), and the lines are one click away
in Mercury.

**The AI analysis block** (H8, section 12): a can't-fix's message carries, after Mercury's
facts and before the link, the analysis's block (`ANALYSIS_FIELDS`: its state's words, the
advisory label and score, the rationale, at most three hypotheses each with its next step), or
its state alone ("AI analysis: pending", off, capped, couldn't analyse, the provider not
answering): never a silent absence. The analysis that arrives after the first message goes as a
follow-up, the event ``analysis``, threaded under the incident's first message (an email's
``In-Reply-To``; a webhook's second event with the incident's id). The block is the
notifier's (`modules/heal_notice.py`), which has withheld the incident's configuration lines
from it.

**Mercury's diagnosis block** (H17, 19.3): an Alert incident's message carries, after what
was detected and before the steps, its diagnosis by kind (`DIAGNOSIS_FIELDS`: its state's
words, how many reads on which devices, at most five hypotheses each its rule's words, the
ends it read and its strength, and what was ruled out), never a value it compared or a
configuration line; or that it did not finish within its bound, its result following on the
same thread (the event ``diagnosis`` when the analysis was already final).

**The egress mask.** Everything a message carries, an email's subject and text and a
webhook's whole JSON, goes through `redact.egress_payload` at its sender, the one place per
channel (`relay.build`, `webhook.request`) (masked by
position, by every known stored secret's value, and by the egress shapes). Then the bytes
built from it are checked once more against the secrets this send holds (the relay's
password, the webhook's signing secret): one found refuses the send, so nothing sent carries
one even where the redaction table could not be read (`carries_secret`).
"""

import re
import time

#: The events that notify, each with its words (section 10, "Which events notify"), and the
#: two Mercury sends itself: a test, and a verification code.
EVENTS = {"cant_fix": "could not fix", "proposal": "a fix waits for a person",
          "halted": "self-healing halted", "held": "a device held from healing",
          "healed": "healed, verified", "cleared": "cleared",
          # An automatic action that ended as it should (19.4, H23): named as an action.
          "action": "an action taken, verified",
          "analysis": "AI analysis of what could not be fixed",
          "diagnosis": "Mercury's diagnosis of what could not be fixed",
          "test": "a test send", "verification": "a verification code"}
#: An event's fields and each one's bound; nothing else is carried.
#: C2817, C2823: *happened* is what happened, the cause the decision stated (facts first, a
#: hypothesis labelled), before the outcome; the outcome's bound holds the plain words.
FIELDS = {"incident": 80, "event": 20, "network": 80, "device": 80, "kind": 80,
          "happened": 800, "outcome": 400, "detected": 400, "detected_at": 40, "steps": 20,
          "todo": 400, "link": 400, "analysis": 1, "diagnosis": 1}
#: Mercury's diagnosis block's fields (H17) and each one's bound; its hypotheses at most
#: `DIAGNOSIS_HYPOTHESES` (the diagnosis's own `MAX_SHOWN`), each `DIAGNOSIS_HYPOTHESIS_FIELDS`;
#: what was ruled out at most `DIAGNOSIS_RULED_OUT` checks.
DIAGNOSIS_FIELDS = {"state": 20, "words": 400, "reads": 200, "hypotheses": 5,
                    "ruled_out": 20}
DIAGNOSIS_HYPOTHESIS_FIELDS = {"claim": 300, "strength": 20}
DIAGNOSIS_HYPOTHESES, DIAGNOSIS_RULED_OUT = 5, 20
#: A step's *said* is what it does in words (`heal_notice.STEP_WORDS`), drawn in the text;
#: *what* keeps its key, for the webhook's JSON.
STEP_FIELDS = {"what": 200, "said": 240, "result": 200}
#: The AI analysis block's fields (H8) and each one's bound; its hypotheses at most
#: `ANALYSIS_HYPOTHESES`, each `HYPOTHESIS_FIELDS`.
ANALYSIS_FIELDS = {"state": 20, "words": 400, "label": 120, "score": 300, "rationale": 800,
                   "hypotheses": 3}
HYPOTHESIS_FIELDS = {"claim": 400, "next": 200}
ANALYSIS_HYPOTHESES = 3
_INCIDENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}")
#: A link Mercury's own page path (History's `_PRODUCED` shape): never another site.
_LINK = re.compile(r"^/v2/[A-Za-z0-9/_.~%-]*(\?[A-Za-z0-9_.~%=&+-]*)?(#[A-Za-z0-9_-]{1,80})?$")
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def _line(value, bound: int) -> str:
    """One line of text: control characters (a header's CR and LF among them) become spaces,
    cut to *bound*."""
    text = _CONTROL.sub(" ", str(value if value is not None else "")).replace("\n", " ")
    return text.strip()[:bound]


def check_event(event: dict) -> dict:
    """The event as a message may carry it: its fields only, each one line and bounded; an
    unknown field, an unknown event or a link off Mercury refused (ValueError) by name."""
    if not isinstance(event, dict):
        raise ValueError("an event is a dict of its fields")
    unknown = sorted(set(event) - set(FIELDS))
    if unknown:
        raise ValueError(f"an event carries only {', '.join(FIELDS)}; not {', '.join(unknown)} "
                         "(a configuration's lines are never in a message)")
    if event.get("event") not in EVENTS:
        raise ValueError(f"event {event.get('event')!r} is not one of {', '.join(EVENTS)}")
    incident = str(event.get("incident") or "")
    if not _INCIDENT.fullmatch(incident):
        raise ValueError(f"incident {incident!r} is not an id (letters, digits, . _ -)")
    link = str(event.get("link") or "")
    if link and not _LINK.match(link):
        raise ValueError(f"the link {link[:80]!r} is not a Mercury page's path (/v2/...)")
    out = {k: _line(event.get(k), FIELDS[k]) for k in FIELDS
           if k not in ("steps", "analysis", "diagnosis")}
    out["analysis"] = _analysis(event.get("analysis"))
    out["diagnosis"] = _diagnosis(event.get("diagnosis"))
    steps = event.get("steps") or []
    if not isinstance(steps, list):
        raise ValueError("an event's steps are a list")
    out["steps"] = []
    for s in steps[:FIELDS["steps"]]:
        if not isinstance(s, dict) or set(s) - set(STEP_FIELDS):
            raise ValueError(f"a step carries only {', '.join(STEP_FIELDS)}")
        out["steps"].append({k: _line(s.get(k), b) for k, b in STEP_FIELDS.items()
                             if k != "said" or s.get("said")})
    return out


def _analysis(block) -> dict:
    """The AI analysis block as a message may carry it (`ANALYSIS_FIELDS`), or ``{}`` for none;
    an unknown field refused by name, each line bounded."""
    if not block:
        return {}
    if not isinstance(block, dict) or set(block) - set(ANALYSIS_FIELDS):
        raise ValueError(f"an analysis block carries only {', '.join(ANALYSIS_FIELDS)}")
    out = {k: _line(block.get(k), b) for k, b in ANALYSIS_FIELDS.items() if k != "hypotheses"}
    hyps = block.get("hypotheses") or []
    if not isinstance(hyps, list):
        raise ValueError("an analysis block's hypotheses are a list")
    out["hypotheses"] = []
    for h in hyps[:ANALYSIS_HYPOTHESES]:
        if not isinstance(h, dict) or set(h) - set(HYPOTHESIS_FIELDS):
            raise ValueError(f"a hypothesis carries only {', '.join(HYPOTHESIS_FIELDS)}")
        out["hypotheses"].append({k: _line(h.get(k), b) for k, b in HYPOTHESIS_FIELDS.items()})
    return out


def _diagnosis(block) -> dict:
    """Mercury's diagnosis block as a message may carry it (`DIAGNOSIS_FIELDS`), or ``{}`` for
    none; an unknown field refused by name, each line bounded."""
    if not block:
        return {}
    if not isinstance(block, dict) or set(block) - set(DIAGNOSIS_FIELDS):
        raise ValueError(f"a diagnosis block carries only {', '.join(DIAGNOSIS_FIELDS)}")
    out = {k: _line(block.get(k), b) for k, b in DIAGNOSIS_FIELDS.items()
           if k not in ("hypotheses", "ruled_out")}
    hyps, ruled = block.get("hypotheses") or [], block.get("ruled_out") or []
    if not isinstance(hyps, list) or not isinstance(ruled, list):
        raise ValueError("a diagnosis block's hypotheses and ruled-out checks are lists")
    out["hypotheses"] = []
    for h in hyps[:DIAGNOSIS_HYPOTHESES]:
        if not isinstance(h, dict) or set(h) - set(DIAGNOSIS_HYPOTHESIS_FIELDS):
            raise ValueError("a diagnosis hypothesis carries only "
                             f"{', '.join(DIAGNOSIS_HYPOTHESIS_FIELDS)}")
        out["hypotheses"].append({k: _line(h.get(k), b)
                                  for k, b in DIAGNOSIS_HYPOTHESIS_FIELDS.items()})
    out["ruled_out"] = [_line(r, 200) for r in ruled[:DIAGNOSIS_RULED_OUT]]
    return out


def diagnosis_lines(block: dict) -> list:
    """Mercury's diagnosis in a message's words: its reads, each hypothesis by kind, what was
    ruled out; or its state's words alone (not made, or not finished in time)."""
    if not block:
        return []
    if not block.get("hypotheses") and block.get("state") != "done":
        return [f"Mercury's diagnosis: {block.get('words') or 'not recorded'}"]
    lines = ["Mercury's diagnosis" + (f" ({block['reads']})" if block.get("reads") else "")]
    if not block.get("hypotheses"):
        lines.append(f"  {block.get('words') or 'no cause found in what Mercury reads'}")
    lines += [f"  {i}. {h['claim']}" for i, h in enumerate(block.get("hypotheses") or [], 1)]
    if block.get("ruled_out"):
        lines.append("  Ruled out: " + "; ".join(block["ruled_out"]))
    return lines


def analysis_lines(block: dict) -> list:
    """The analysis block in a message's words: its state's words, then the label and score,
    the rationale and each hypothesis with its next step (advisory: a person confirms)."""
    if not block:
        return []
    lines = [block.get("words") or "AI analysis"]
    if block.get("score"):
        lines.append(f"  Measured: {block['score']}")
    if block.get("rationale"):
        lines.append(f"  {block['rationale']}")
    hyps = block.get("hypotheses") or []
    for i, h in enumerate(hyps, 1):
        n = f" {i}" if len(hyps) > 1 else ""
        lines.append(f"  Hypothesis{n}: {h['claim']}")
        if h.get("next"):
            lines.append(f"  Next step: {h['next']}")
    return lines


def link_url(path: str) -> tuple:
    """``(url, said)``: the link with the installation's address before it
    (`notify_link_base`), or the path alone and the words saying why."""
    from modules.settings_schema import get_setting
    if not path:
        return "", ""
    base = (get_setting("notify_link_base", "") or "").strip().rstrip("/")
    if not base:
        return path, " (the address Mercury is reached by is not set: notify_link_base)"
    return base + path, ""


def mask(obj, values: dict = None):
    """The egress mask on *obj* (a string, or a payload of dicts, lists and strings):
    `redact.egress_payload`, the known secrets' table read once."""
    from modules import redact
    return redact.egress_payload(obj, values)


def carries_secret(data: bytes, held) -> bool:
    """Whether *data*, the bytes about to be sent, carry any of *held* (this send's own
    secret values, decrypted for the send): checked as bytes, after every mask, so the answer
    is about what would leave."""
    return any(v and v.encode("utf-8") in data for v in held)


def subject(facts: dict) -> str:
    """The subject line, unmasked: the sender masks it (`relay.build`)."""
    where = " on ".join(x for x in (facts.get("device"), facts.get("network")) if x)
    return f"[Mercury] {where or 'Mercury'}: {EVENTS[facts['event']]}"


def text(facts: dict, *, sent_at: float = None) -> str:
    """The message's text, facts first, then the link; unmasked: the sender masks it at the
    boundary (`relay.build`), so one place per channel owns the mask."""
    sent = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() if sent_at is None
                                                            else sent_at))
    lines = [f"Mercury: {EVENTS[facts['event']]}"]
    where = " · ".join(x for x in (facts.get("network"), facts.get("device")) if x)
    if where:
        lines.append(where)
    lines.append("")
    if facts.get("happened"):
        lines.append(f"What happened: {facts['happened']}")
    if facts.get("outcome"):
        lines.append(f"Outcome: {facts['outcome']}")
    if facts.get("detected"):
        when = f" at {facts['detected_at']}" if facts.get("detected_at") else ""
        lines.append(f"Detected: {facts['detected']}{when}")
    if facts.get("kind"):
        lines.append(f"Fix kind: {facts['kind']}")
    if facts.get("diagnosis"):
        # Mercury's own reads (board H's artboard L): after what was detected, before the
        # steps; by kind, never a value or a configuration line.
        lines += diagnosis_lines(facts["diagnosis"])
    if facts["steps"]:
        lines.append("What Mercury tried:")
        lines += [f"  - {s.get('said') or s['what']}: {s['result']}" for s in facts["steps"]]
    if facts.get("todo"):
        lines.append(f"What to do: {facts['todo']}")
    if facts.get("analysis"):
        # After Mercury's facts, before the link (section 12's order); advisory only.
        lines += [""] + analysis_lines(facts["analysis"])
    url, said = link_url(facts.get("link", ""))
    if url:
        lines += ["", f"Open in Mercury: {url}{said}"]
    lines += ["", f"Incident {facts['incident']} · sent {sent}"]
    return "\n".join(lines) + "\n"


def payload(facts: dict, *, sent_at: float = None) -> dict:
    """The generic webhook's JSON: the incident's id, network, device, kind, outcome, step
    summary and link (section 10); unmasked: the sender masks it (`webhook.request`)."""
    url, _said = link_url(facts.get("link", ""))
    sent = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() if sent_at is None
                                                            else sent_at))
    return {"incident": facts["incident"], "event": facts["event"],
            "summary": EVENTS[facts["event"]], "network": facts.get("network", ""),
            "device": facts.get("device", ""), "kind": facts.get("kind", ""),
            "outcome": facts.get("outcome", ""), "detected": facts.get("detected", ""),
            "detected_at": facts.get("detected_at", ""), "steps": facts["steps"],
            "todo": facts.get("todo", ""), "link": url, "sent_at": sent,
            **({"analysis": facts["analysis"]} if facts.get("analysis") else {}),
            **({"diagnosis": facts["diagnosis"]} if facts.get("diagnosis") else {})}
