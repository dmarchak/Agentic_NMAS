"""Reveal one log line (C818; board F3's Reveal…, approved 2026-10-15; the operator's decision
2026-10-15: a reveal of its own, person-gated and audited).

Every log line Mercury shows is masked by `redact_text`. A line with a masked value offers
Reveal… in History › Query's Lines view; revealing it is an operation of its own:

1. ``person``: only a VERIFIED PERSON sees an unmasked line. A service is refused whatever its
   grants, and so is a request no one is identified behind.
2. ``reason``: a stated reason, the shape every recorded reason has (at least three words and
   eight characters, `authorisation.MIN_WORDS` and `MIN_CHARS`), never judged.
3. ``line``: the line is named by what the page drew: its Loki stream (the labels, as drawn),
   its time to the nanosecond, and the sha256 of the masked line. Nothing else is taken.
4. ``read``: the line is read from Loki AGAIN, now, by its stream and time, never kept from
   the page's ask; it must be the line that was shown (its masked form's digest the same), and
   exactly one.
5. ``record``: the reveal is recorded BEFORE anything is shown (`reveal_audit`, the record every
   reveal writes): who, when, the network, which line by its stream and time, the digest of
   what was shown and the reason, each masked at rest; NEVER the line or the value. A reveal
   that cannot be recorded shows nothing.
6. ``show``: the line, unmasked, in place under its row, to that person only, in the answer
   to their own request; it is kept nowhere. History's timeline draws the record
   (`history_sources.log_reveals`).

A refusal names the comparison it made and both operands.
"""

import hashlib
import json
import logging
import re
import time

log = logging.getLogger(__name__)

#: The operation's steps, in order (the manual's page names each: tests/test_manual.py).
STEPS = (
    ("person", "a verified person asks"),
    ("reason", "with a stated reason"),
    ("line", "the line named by its stream, its time and what was shown"),
    ("read", "the line read from Loki again, now"),
    ("record", "the reveal recorded first, never the value"),
    ("show", "the line drawn unmasked, in place, to that person"),
)
#: The reveal record's `what` for a log line.
WHAT = "log_line"
#: The longest reason taken, the most labels a stream carries, the longest label value.
REASON_MAX = 300
LABELS_MAX = 30
VALUE_MAX = 512
#: The most lines Loki is asked for at the one nanosecond (a stream holds one, normally).
READ_LIMIT = 20

_LABEL = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_NS = re.compile(r"^\d{1,19}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")


def digest(masked: str) -> str:
    """The sha256 of a line as Mercury drew it, masked."""
    return hashlib.sha256((masked or "").encode("utf-8", "replace")).hexdigest()


def _masked_labels(labels: dict) -> dict:
    from modules.redact import redact_text
    return {str(k): redact_text(str(v)) for k, v in sorted((labels or {}).items())}


def carried(labels: dict, ns, masked: str) -> dict:
    """What a row's Reveal… carries (`history_logq.lines`): its stream as drawn (each value
    masked), its time in nanoseconds, the digest of the masked line, and the slot its answer
    is drawn in. Never the line."""
    sha = digest(masked)
    return {"stream": json.dumps(_masked_labels(labels), sort_keys=True), "ns": str(int(ns)),
            "shown": sha, "slot": slot(str(int(ns)), sha)}


def slot(ns: str, sha: str) -> str:
    """The id of the place a reveal's answer is drawn, from what the form carries."""
    return f"lq-rv-{ns}-{sha[:12]}"


def _iso_ns(ns: int) -> str:
    secs, frac = divmod(int(ns), 10 ** 9)
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(secs)) + f".{frac:09d}Z"


# ---------------------------------------------------------------------------- the steps

def _person(ident, refused) -> str:
    """Why *ident* may not see an unmasked line, or ""."""
    if refused:
        return refused.get("error") or "a verified person reveals"
    if ident is None or not getattr(ident, "is_identified", False):
        return "a log line is revealed only to a verified person; no one is identified " \
               "behind this request"
    if getattr(ident, "kind", "") != "person":
        return (f"a log line is revealed only to a verified person; this request is a "
                f"{getattr(ident, 'kind', '') or 'caller of no kind'}, not a person")
    return ""


def _reason(text: str) -> str:
    """Why *text* is not the shape of a reason, or ""."""
    from modules.nsot.authorisation import MIN_CHARS, MIN_WORDS
    words, chars = len(text.split()), len(text)
    if not text:
        return (f"a reveal needs a reason: at least {MIN_WORDS} words and {MIN_CHARS} "
                "characters; none was given")
    if words < MIN_WORDS or chars < MIN_CHARS:
        return (f"a reveal needs a reason of at least {MIN_WORDS} words and {MIN_CHARS} "
                f"characters; this one is {words} word{'s' if words != 1 else ''} and "
                f"{chars} characters")
    if chars > REASON_MAX:
        return f"a reason is at most {REASON_MAX} characters; this one is {chars}"
    bad = sorted({c for c in text if not c.isprintable()})
    if bad:
        return "a reason holds printable characters only; it holds " + ", ".join(
            f"U+{ord(c):04X}" for c in bad)
    return ""


def _line(values) -> tuple:
    """``(stream, ns, shown, refusal)`` from what the form carried."""
    raw = (values.get("stream") or "").strip()
    ns, shown = (values.get("ns") or "").strip(), (values.get("shown") or "").strip()
    try:
        stream = json.loads(raw) if raw else None
    except ValueError:
        stream = None
    if not isinstance(stream, dict) or not stream:
        return None, 0, "", "the line's stream is not a set of labels: nothing names the line"
    if len(stream) > LABELS_MAX:
        return None, 0, "", (f"a stream carries at most {LABELS_MAX} labels; this one "
                             f"carries {len(stream)}")
    for k, v in stream.items():
        if not _LABEL.match(str(k)):
            return None, 0, "", f"{str(k)[:40]!r} is not a label name"
        if not isinstance(v, str) or len(v) > VALUE_MAX:
            return None, 0, "", (f"the label {k}'s value is not text of at most {VALUE_MAX} "
                                 "characters")
    if not _NS.match(ns):
        return None, 0, "", f"{ns[:30]!r} is not a time in nanoseconds"
    if not _SHA.match(shown):
        return None, 0, "", "what was shown is not named (the masked line's sha256)"
    return stream, int(ns), shown, ""


def _read(client, stream: dict, ns: int, shown: str) -> tuple:
    """``(raw, labels, refusal)``: the one line Loki holds NOW in *stream* at *ns* whose masked
    form is the one shown."""
    from modules import history_ask, history_logq
    from modules.redact import redact_text

    # The stream's indexed labels (Loki's own label API over the second around the line): only
    # an indexed label can select; the stream's others (structured metadata) are compared below.
    names, err = history_logq._json(client, "loki/api/v1/labels",       # noqa: SLF001
                                    start=str(ns - 10 ** 9), end=str(ns + 10 ** 9))
    if err:
        return "", {}, f"the line could not be read again: {err}"
    indexed = {n for n in names or [] if isinstance(n, str)}
    # A label is selected on only where its value as drawn is its value (nothing masked in it).
    usable = sorted(k for k, v in stream.items() if k in indexed and redact_text(v) == v)
    if not usable:
        return "", {}, ("none of the line's labels is one Loki indexes over its time "
                        f"({', '.join(sorted(stream)) or 'none'} carried; "
                        f"{', '.join(sorted(indexed)) or 'none'} indexed): the line cannot "
                        "be selected")
    selector = "{" + ", ".join(f"{k}={history_ask.string(stream[k])}" for k in usable) + "}"
    data, err = history_logq._json(client, "loki/api/v1/query_range",   # noqa: SLF001
                                   query=selector, limit=READ_LIMIT, start=str(ns),
                                   end=str(ns + 1), direction="forward")
    if err:
        return "", {}, f"the line could not be read again: {err}"
    found, labels = [], {}
    for s in (data or {}).get("result") or []:
        got = s.get("stream") or {}
        if _masked_labels(got) != stream:
            continue
        for t, raw in s.get("values") or []:
            if str(t) == str(ns) and digest(redact_text(raw)) == shown and raw not in found:
                found.append(raw)
                labels = got
    if not found:
        return "", {}, (f"Loki holds no line at {_iso_ns(ns)} in the stream {selector} whose "
                        "masked form is the one shown (asked now; it may have passed Loki's "
                        "retention)")
    if len(found) > 1:
        return "", {}, (f"{len(found)} different lines at {_iso_ns(ns)} in {selector} are "
                        "masked to the one shown: which one is meant cannot be told")
    raw = found[0]
    if redact_text(raw) == raw:
        return "", {}, "nothing in this line is masked: there is nothing to reveal"
    return raw, labels, ""


def refusal(values, words: str) -> dict:
    """A refused answer, drawn in the slot the form's line names (or a blank one when what it
    carried names none), nothing shown."""
    ns = (values.get("ns") or "").strip()
    shown = (values.get("shown") or "").strip()
    return {"state": "refused", "refused": words, "text": "", "by": "", "line_at": "",
            "device": "", "slot": slot(ns if _NS.match(ns) else "0",
                                       shown if _SHA.match(shown) else "0" * 64)}


def reveal(list_name: str, values, ident, refused=None, client=None) -> tuple:
    """``(answer, status)``: one log line revealed to a verified person, recorded first; or
    refused, naming why, with nothing shown. *answer* is ``{"state": "revealed"|"refused",
    "slot", "refused", "text", "by", "at", "line_at", "device", "recorded"}``."""
    from modules import history_logq, reveal_audit
    from modules.readers.logs_summary import _fields_of
    from modules.redact import redact_text

    out = refusal(values, "")

    def no(words, status):
        log.info("log_reveal: refused for %s: %s", getattr(ident, "actor", "?"), words)
        return dict(out, refused=words), status

    # 1. person
    why = _person(ident, refused)
    if why:
        return no(why, 403)
    # 2. reason
    reason = (values.get("reason") or "").strip()
    why = _reason(reason)
    if why:
        return no(why, 400)
    # 3. line
    stream, ns, shown, why = _line(values)
    if why:
        return no(why, 400)
    out["line_at"] = _iso_ns(ns)
    # 4. read: from Loki again, now; the wait is Loki's own query_timeout and 5 s.
    if client is None:
        probe = history_logq._client(list_name, 15.0)                     # noqa: SLF001
        if not probe.is_configured():
            return no("no log store is configured for this network (its Loki card in "
                      "Settings): the line cannot be read again", 409)
        client = history_logq._client(                                     # noqa: SLF001
            list_name, history_logq.wait(history_logq.limits(list_name, client=probe)))
    raw, labels, why = _read(client, stream, ns, shown)
    if why:
        return no(why, 409)
    device = labels.get("device") or _fields_of(redact_text(raw))[0] or ""
    # 5. record: before anything is shown; masked at rest; never the line.
    entry = reveal_audit.record(
        actor=ident.actor, kind=ident.kind, what=WHAT, target=device,
        detail=f"{json.dumps(stream, sort_keys=True)} at {ns}", peer=getattr(ident, "peer", ""),
        extra={"list": list_name, "stream": stream, "ns": str(ns), "line_at": out["line_at"],
               "shown_sha256": shown, "reason": redact_text(reason)})
    if not entry.get("recorded"):
        return no("the reveal could not be recorded, so nothing is shown: a log line is "
                  "never revealed unrecorded", 503)
    # 6. show
    return dict(out, state="revealed", text=raw, by=ident.actor, at=entry.get("at", ""),
                device=device, recorded=True), 200
