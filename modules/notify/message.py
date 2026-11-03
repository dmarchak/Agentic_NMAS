"""An incident event put into a message, and the egress mask on every byte of it.

**What a message carries** (docs/HEAL_TO_INTENT.md section 10): Mercury's facts first
(detected what and when, each step tried and its result, the outcome, what to do), then the
link. An event is a closed set of fields (`FIELDS`); any other key is refused by name, so a
caller cannot hand a configuration's lines in under a new name: the heal says each unit by its
kind ("inbound ACL added on Gi2, 2 lines, content withheld"), and the lines are one click away
in Mercury. (The AI analysis block of a can't-fix is H8's, and not in this slice.)

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
          "test": "a test send", "verification": "a verification code"}
#: An event's fields and each one's bound; nothing else is carried.
FIELDS = {"incident": 80, "event": 20, "network": 80, "device": 80, "kind": 80,
          "outcome": 200, "detected": 400, "detected_at": 40, "steps": 20, "todo": 400,
          "link": 400}
STEP_FIELDS = {"what": 200, "result": 200}
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
    out = {k: _line(event.get(k), FIELDS[k]) for k in FIELDS if k not in ("steps",)}
    steps = event.get("steps") or []
    if not isinstance(steps, list):
        raise ValueError("an event's steps are a list")
    out["steps"] = []
    for s in steps[:FIELDS["steps"]]:
        if not isinstance(s, dict) or set(s) - set(STEP_FIELDS):
            raise ValueError(f"a step carries only {', '.join(STEP_FIELDS)}")
        out["steps"].append({k: _line(s.get(k), b) for k, b in STEP_FIELDS.items()})
    return out


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
    if facts.get("outcome"):
        lines.append(f"Outcome: {facts['outcome']}")
    if facts.get("detected"):
        when = f" at {facts['detected_at']}" if facts.get("detected_at") else ""
        lines.append(f"Detected: {facts['detected']}{when}")
    if facts.get("kind"):
        lines.append(f"Fix kind: {facts['kind']}")
    if facts["steps"]:
        lines.append("What Mercury tried:")
        lines += [f"  {i}. {s['what']}: {s['result']}" for i, s in enumerate(facts["steps"], 1)]
    if facts.get("todo"):
        lines.append(f"What to do: {facts['todo']}")
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
            "todo": facts.get("todo", ""), "link": url, "sent_at": sent}
