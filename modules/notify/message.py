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

**Local times and display names in the body** (the operator, 2026-11-12, Lab 10 objective 2:
"Objective 2 (couldn't fix → notify an engineer with the steps taken): verify end to end with
stand-ins that the can't-fix email lists the steps taken in plain words, with local times and
display names, and links to the incident. Fix any gaps."). The records keep UTC; a body says
every time in the installation's own zone, the time zone of the host Mercury runs on (Python's
`time.localtime`, the reading `job_health` already draws by; no setting), its zone named ONCE,
on the body's last line (`zone_line`); a time on the other side of a daylight-saving change
says its own zone beside it. A time a recorded text holds ("at 14:02 UTC", an ISO stamp) is
said locally too (`localised`). A person is named by display name (`display_names.people`),
never by identity, in the text and the webhook's JSON alike: a message has no "identity as
recorded" line, and the record keeps the identity.

**The egress mask.** Everything a message carries, an email's subject and text and a
webhook's whole JSON, goes through `redact.egress_payload` at its sender, the one place per
channel (`relay.build`, `webhook.request`) (masked by
position, by every known stored secret's value, and by the egress shapes). Then the bytes
built from it are checked once more against the secrets this send holds (the relay's
password, the webhook's signing secret): one found refuses the send, so nothing sent carries
one even where the redaction table could not be read (`carries_secret`).
"""

import calendar
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
          # The deploy bar (the operator, 2026-11-11): GitHub's CI failed the release the host
          # runs after it was deployed on the gate's green (modules/readers/ci_agreement.py,
          # `notify_reds`), once per commit and GitHub run.
          "ci_disagrees": "CI disagrees with the deployed release",
          # AI troubleshooting's hand-over (the fix-it board's step 8; modules/fixit/handover.py
          # `send`): a person handed an incident over to an engineer, sent to the teams they
          # chose among those told about the network's can't-fix, with the incident's link.
          "fixit_handover": "an incident handed over to an engineer",
          # C3330 (the operator, 2026-11-12): self-healing's detection cannot see, or a person
          # turned self-healing off or stopped it; on by default for every team
          # (modules/heal/blind_notice.py), once per raise.
          "heal_blind": "self-healing is blind or paused",
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
#: A step's *said* is what it does in words (its operation's short label and its recorded
#: words, `heal_notice.steps_said`), drawn in the text; *what* keeps its key, for the webhook's
#: JSON; *at* is when it was recorded (ISO UTC, as kept), drawn in local time before it.
STEP_FIELDS = {"what": 200, "said": 240, "result": 200, "at": 40}
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
                             if k not in ("said", "at") or s.get(k)})
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
    `redact.egress_payload`, the known secrets' table read once; its people already named by
    display name (`_people`), so no address is labelled (C3424's labels are an AI request's)."""
    from modules import redact
    return redact.egress_payload(obj, values, people=False)


def carries_secret(data: bytes, held) -> bool:
    """Whether *data*, the bytes about to be sent, carry any of *held* (this send's own
    secret values, decrypted for the send): checked as bytes, after every mask, so the answer
    is about what would leave."""
    return any(v and v.encode("utf-8") in data for v in held)


# ── Local times (the operator's order of 2026-11-12, objective 2: "with local times") ────────

#: An ISO UTC stamp as the records keep it, and "HH:MM UTC" as recorded words say a time.
_ISO = re.compile(r"(?<![\d-])(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})(?::\d{2}(?:\.\d+)?)?Z(?![\w])")
_HHMM_UTC = re.compile(r"(?<![\d:])([01]\d|2[0-3]):([0-5]\d)(?::[0-5]\d)? UTC\b")


def epoch_of(iso) -> float:
    """A record's ISO UTC time (``2026-11-12T14:02:07Z``) as epoch seconds, or None."""
    try:
        return float(calendar.timegm(time.strptime(str(iso or "")[:19], "%Y-%m-%dT%H:%M:%S")))
    except (ValueError, OverflowError):
        return None


def zone_name(epoch: float) -> str:
    """The installation's zone at *epoch* (the host's own, `time.localtime`) as a person reads
    it: its abbreviation and its offset from UTC ("IST (UTC+05:30)"), or "UTC"."""
    t = time.localtime(float(epoch))
    off = int(t.tm_gmtoff or 0)
    name = t.tm_zone or ""
    if off == 0 and name in ("UTC", "GMT", ""):
        return "UTC"
    sign, off = ("+", off) if off >= 0 else ("-", -off)
    stated = f"UTC{sign}{off // 3600:02d}:{off % 3600 // 60:02d}"
    return f"{name} ({stated})" if name and not name.startswith(("+", "-")) else stated


def local(epoch: float, named: str, *, day: bool = True) -> str:
    """*epoch* in the installation's zone, "2026-11-12 19:32" (or "19:32" without *day*); its
    own zone beside it only when it is not *named*, the body's one zone (a time across a
    daylight-saving change)."""
    t = time.localtime(float(epoch))
    said = time.strftime("%Y-%m-%d %H:%M" if day else "%H:%M", t)
    own = zone_name(epoch)
    return said if own == named else f"{said} {own}"


def localised(words: str, ref: float, named: str) -> str:
    """*words* with each time a record wrote in UTC said in the installation's zone: an ISO
    stamp exactly, and an "HH:MM UTC" on the UTC day that puts it nearest *ref* (the record's
    own time: the words were written then, so the day before, that day or the day after)."""
    if not words:
        return words or ""

    def iso(m):
        at = epoch_of(f"{m.group(1)}T{m.group(2)}:00Z")
        return local(at, named) if at is not None else m.group(0)

    def hhmm(m):
        day = time.gmtime(ref)
        base = calendar.timegm((day.tm_year, day.tm_mon, day.tm_mday, int(m.group(1)),
                                int(m.group(2)), 0, 0, 0, 0))
        at = min((base + d * 86400 for d in (-1, 0, 1)), key=lambda a: abs(a - ref))
        return local(at, named, day=False)

    return _HHMM_UTC.sub(hhmm, _ISO.sub(iso, words))


def zone_line(named: str) -> str:
    """The body's one line naming its zone."""
    return f"Times are in {named}, the time zone of the host Mercury runs on."


def _people(text: str) -> str:
    """*text* with each person named by display name (`display_names.people`)."""
    from modules import display_names
    return display_names.people(text)


def subject(facts: dict) -> str:
    """The subject line, unmasked: the sender masks it (`relay.build`)."""
    where = " on ".join(x for x in (facts.get("device"), facts.get("network")) if x)
    return f"[Mercury] {where or 'Mercury'}: {EVENTS[facts['event']]}"


def text(facts: dict, *, sent_at: float = None) -> str:
    """The message's text, facts first, then the link; unmasked: the sender masks it at the
    boundary (`relay.build`), so one place per channel owns the mask.

    Every time in it is local, its zone named once on the last line, and every person is named
    by display name (the operator, 2026-11-12, objective 2: "the can't-fix email lists the steps
    taken in plain words, with local times and display names, and links to the incident"):
    each step leads with its own time, "  - 14:02 Read edge-b: edge-b read again: done"."""
    sent_epoch = time.time() if sent_at is None else float(sent_at)
    named = zone_name(sent_epoch)
    detected = epoch_of(facts.get("detected_at"))
    ref = detected if detected is not None else sent_epoch

    def said(words, at=None):
        return localised(_people(words), ref if at is None else at, named)

    lines = [f"Mercury: {EVENTS[facts['event']]}"]
    where = " · ".join(x for x in (facts.get("network"), facts.get("device")) if x)
    if where:
        lines.append(where)
    lines.append("")
    if facts.get("happened"):
        lines.append(f"What happened: {said(facts['happened'])}")
    if facts.get("outcome"):
        lines.append(f"Outcome: {said(facts['outcome'])}")
    if facts.get("detected"):
        when = (f" at {local(detected, named)}" if detected is not None else
                f" at {said(facts['detected_at'])}" if facts.get("detected_at") else "")
        lines.append(f"Detected: {said(facts['detected'])}{when}")
    if facts.get("kind"):
        lines.append(f"Fix kind: {facts['kind']}")
    if facts.get("diagnosis"):
        # Mercury's own reads (board H's artboard L): after what was detected, before the
        # steps; by kind, never a value or a configuration line.
        lines += [said(x) for x in diagnosis_lines(facts["diagnosis"])]
    if facts["steps"]:
        lines.append("What Mercury tried:")
        for s in facts["steps"]:
            at = epoch_of(s.get("at"))
            when = f"{local(at, named, day=False)} " if at is not None else ""
            lines.append(f"  - {when}{said(s.get('said') or s['what'], at)}: "
                         f"{said(s['result'], at)}")
    if facts.get("todo"):
        lines.append(f"What to do: {said(facts['todo'])}")
    if facts.get("analysis"):
        # After Mercury's facts, before the link (section 12's order); advisory only.
        lines += [""] + [said(x) for x in analysis_lines(facts["analysis"])]
    url, why = link_url(facts.get("link", ""))
    if url:
        lines += ["", f"Open in Mercury: {url}{why}"]
    lines += ["", f"Incident {facts['incident']} · sent {local(sent_epoch, named)}",
              zone_line(named)]
    return "\n".join(lines) + "\n"


def payload(facts: dict, *, sent_at: float = None) -> dict:
    """The generic webhook's JSON: the incident's id, network, device, kind, outcome, step
    summary and link (section 10); unmasked: the sender masks it (`webhook.request`). Its
    times stay ISO UTC, for the receiver to draw in its own reader's zone; each person in its
    words is named by display name, as in the text (`display_names.people_payload`)."""
    from modules import display_names

    url, _said = link_url(facts.get("link", ""))
    sent = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() if sent_at is None
                                                            else sent_at))
    return display_names.people_payload({"incident": facts["incident"], "event": facts["event"],
            "summary": EVENTS[facts["event"]], "network": facts.get("network", ""),
            "device": facts.get("device", ""), "kind": facts.get("kind", ""),
            "outcome": facts.get("outcome", ""), "detected": facts.get("detected", ""),
            "detected_at": facts.get("detected_at", ""), "steps": facts["steps"],
            "todo": facts.get("todo", ""), "link": url, "sent_at": sent,
            **({"analysis": facts["analysis"]} if facts.get("analysis") else {}),
            **({"diagnosis": facts["diagnosis"]} if facts.get("diagnosis") else {})})
