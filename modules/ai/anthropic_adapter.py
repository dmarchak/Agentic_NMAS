"""The Anthropic adapter: one POST to the Messages API over `requests`, no SDK (the operator,
2026-10-25, PHASE8_PLAN 15.12: "a thin one over requests, behind the gateway's interface ...
so taking the SDK later changes one module").

Its contract with the gateway: `send(body, api_key)` returns a `Reply` or raises one
`AdapterError` subclass, each a kind the gateway records by name:

- `RateLimited` (429) and `Overloaded` (529): retried only these, up to `MAX_RETRIES`,
  waiting what `retry-after` says (seconds), else 1, 2, 4 s; a wait longer than
  `MAX_WAIT_S` is not slept but raised, naming it (a person is waiting on the call);
- `KeyRefused` (401, 403): the key, never retried;
- `WorkspaceLimit` (C2084): the provider's workspace has reached the usage limit its admin
  set. The provider answers HTTP 400, ``invalid_request_error``, "You have reached your
  specified workspace API usage limits. You will regain access on 2026-11-01 at 00:00 UTC."
  (read 2026-10-28, every call refused). Recognised by the error's type AND the phrase
  ``usage limits`` in its message (`workspace_limit`), whatever the status, never by the
  status alone; it carries the moment the message names as ``until``
  (``YYYY-MM-DDTHH:MM:SSZ``), or None when it names none. Never retried: it is not transient,
  and no request is answered before that moment unless an admin raises the limit;
- `BadRequest` (400, 404, 413, but the workspace's limit): the request, never retried;
- `ProviderDown` (any other status, a connection error, a timeout): never retried here.

Never logs or returns the key, the request or the response body (the gateway records the
masked request and the masked answer). The wire shape is Anthropic's reference, read
2026-10-25: `POST /v1/messages`, headers `x-api-key` and `anthropic-version: 2023-06-01`.

**Every send is streamed** (the operator, 2026-11-16: a call's ``max_tokens`` is sized to what
the spend caps leave, up to the model's 128,000): the body is sent with ``"stream": true`` over
`requests` (still no SDK) and its server-sent events read as they come (`_read_stream`:
``message_start`` with the input and cache usage, ``content_block_start``/``_delta``/``_stop``,
``message_delta`` with the stop reason and the output usage so far, ``message_stop``, ``ping``,
and ``error``), assembled into the same `Reply` body a whole answer had. Its bounds and its
failures:

- **an idle bound per chunk** (`STREAM_IDLE_S`, the read bound `requests` applies to every
  read of the socket) in place of the 60 s whole-answer bound; no whole-answer bound;
- a 429 or 529 status before the stream starts, and an ``overloaded_error`` or
  ``rate_limit_error`` event before any output arrived, are retried as before (`MAX_RETRIES`);
- **a disconnect or an idle bound reached mid-stream** raises `StreamFailed` (``partial``
  once ``message_start`` arrived), and **an ``error`` event after output began** raises
  `StreamError`: neither is retried here, nothing partial is parsed as an answer, and each
  carries the usage the stream reported (``message_start``'s input and cache tokens, the last
  ``message_delta``'s output tokens) so the gateway records what it may have cost (the
  gateway's own retry of a `StreamError`, once, only while the caps' remaining covers it,
  `gateway.ask`);
- **the live count**: after each event the gateway's *progress* hook is given the output so far
  (the provider's ``message_delta`` count where it sent one, else the deltas' characters at
  `LIVE_CHARS_PER_TOKEN`, an over-estimate) and may answer why to stop: the connection is then
  closed at once (closing it is what stops the provider generating and billing) and
  `StreamAborted` raised (``budget_ran_out``), never parsed.

**The token count** (C1898, the operator's decision of 2026-10-28): `count_tokens(body,
api_key)` asks `POST /v1/messages/count_tokens` how many input tokens the masked request is,
before it is sent. Anthropic's pages, read 2026-10-28 (platform.claude.com/docs/en/
build-with-claude/token-counting and /api/messages/count_tokens): free to use, its own
requests-per-minute limit apart from message creation's (5,000 a minute at the Start tier);
the body takes the request's ``model``, ``messages``, ``system``, ``tools``, ``tool_choice``,
``thinking``, ``output_config``, ``cache_control`` and ``speed`` (`COUNT_KEYS`), never
``max_tokens`` or ``temperature``; the answer is ``{"input_tokens": N}``, "an estimate" that
"might differ by a small amount" from what the call then uses; caching is not applied to a
count. The same failures as a send, each its own kind, but none is retried: a count that
fails is the gateway's to replace by its estimate, said.
"""
import logging
import re
import time
from dataclasses import dataclass, field

import requests

log = logging.getLogger(__name__)

URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
#: The most seconds between two reads of a streamed answer (the operator, 2026-11-16: a
#: per-chunk idle bound in place of the 60 s whole-answer read bound). NOT MEASURED as a gap:
#: no stream has been recorded yet. Reasoned: every recorded call was answered whole within the
#: old 60 s read bound (none recorded as its timeout), so no wait inside any of them, the time
#: to the first token included, was longer than 60 s; 60 s keeps that. Re-derived as about
#: 2.5x the largest gap once streamed calls record theirs (``stream.longest_gap_s``).
STREAM_IDLE_S = 60.0
#: Connect and per-read bounds, seconds: the read bound is the stream's idle bound
#: (`STREAM_IDLE_S`), so `gateway.send_bound_s` derives from it as before.
TIMEOUT = (5.0, STREAM_IDLE_S)
MAX_RETRIES = 2
MAX_WAIT_S = 20.0
#: The token count's endpoint and the fields its body takes (the pages read 2026-10-28, the
#: module's docstring): every other key of a send's body is left out of the count's.
COUNT_URL = "https://api.anthropic.com/v1/messages/count_tokens"
COUNT_KEYS = ("model", "messages", "system", "tools", "tool_choice", "thinking",
              "output_config", "cache_control", "speed")
#: The count's own connect and read bounds, seconds: a count runs no model, so it is short.
#: Not measured yet: each count's latency is recorded on its call's row
#: (``prompt_count.latency_s``), and the bound is re-derived from those (about 2.5x).
COUNT_TIMEOUT = (5.0, 10.0)
#: The provider's rate-limit headers kept with the record (both prefixes Anthropic has used).
RATELIMIT_PREFIXES = ("anthropic-ratelimit-", "x-ratelimit-")


class AdapterError(Exception):
    kind = "provider_error"

    def __init__(self, message: str, *, status: int = 0, attempts: int = 1,
                 headers: dict = None):
        super().__init__(message)
        self.status = status
        self.attempts = attempts
        self.headers = headers or {}


class RateLimited(AdapterError):
    kind = "rate_limited"


class Overloaded(AdapterError):
    kind = "overloaded"


class KeyRefused(AdapterError):
    kind = "key_refused"


class BadRequest(AdapterError):
    kind = "bad_request"


class ProviderDown(AdapterError):
    kind = "provider_down"


class StreamFailed(AdapterError):
    """A streamed answer that broke off: the connection dropped, or no event came within
    `STREAM_IDLE_S`. *usage* is what the stream reported before it broke (``{}`` when nothing
    did); *partial* whether ``message_start`` arrived (the provider took the request, so it may
    bill it); *output_began* whether any content arrived. Never retried; nothing of it is
    parsed as an answer."""
    kind = "stream_failed"

    def __init__(self, message: str, *, usage: dict = None, partial: bool = False,
                 output_began: bool = False, stream: dict = None, **kw):
        super().__init__(message, **kw)
        self.usage = dict(usage or {})
        self.partial = bool(partial)
        self.output_began = bool(output_began)
        self.stream = dict(stream or {})


class StreamError(StreamFailed):
    """An ``error`` event after output began (an ``overloaded_error``, an ``api_error``):
    recorded as partial, never retried here (a retry bills twice: `gateway.ask` may ask once
    more, as a new call, only while the caps' remaining covers it)."""
    kind = "stream_error"


class StreamAborted(StreamFailed):
    """A stream Mercury closed itself: its running cost was about to pass a spending limit (the
    operator, 2026-11-16: "the cap is enforced live ... Billing stops at the abort"). The
    message is the gateway's reason, naming the cap; never retried, never parsed."""
    kind = "budget_ran_out"


class WorkspaceLimit(AdapterError):
    """The provider's workspace reached its usage limit (C2084): *until* is the moment the
    provider says access returns (``YYYY-MM-DDTHH:MM:SSZ``), or None when it names none;
    *said* the provider's own message, masked and cut (`_error_words`)."""
    kind = "workspace_limit"

    def __init__(self, message: str, *, until=None, said: str = "", **kw):
        super().__init__(message, **kw)
        self.until = until
        self.said = said


#: The provider's error type for a workspace's usage limit, and the phrase its message holds
#: (the module's docstring: both are required, so another 400 is never read as the limit).
LIMIT_TYPE = "invalid_request_error"
LIMIT_PHRASE = "usage limits"
#: The moment the message names: "regain access on 2026-11-01 at 00:00 UTC" (seconds, when
#: given, kept).
_REGAIN = re.compile(r"regain access on (\d{4}-\d{2}-\d{2}) at (\d{2}:\d{2}(?::\d{2})?) UTC",
                     re.I)


def regain_moment(message: str):
    """The moment *message* says access returns, as ``YYYY-MM-DDTHH:MM:SSZ``, or None when it
    names none (or one that is not a date and time)."""
    import datetime

    found = _REGAIN.search(message or "")
    if not found:
        return None
    hm = found.group(2) if found.group(2).count(":") == 2 else found.group(2) + ":00"
    try:
        at = datetime.datetime.strptime(f"{found.group(1)} {hm}", "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    return at.strftime("%Y-%m-%dT%H:%M:%SZ")


def workspace_limit(resp):
    """``{"until", "message"}`` when *resp* is the provider refusing because the workspace's
    usage limit is reached (its error's type `LIMIT_TYPE` and `LIMIT_PHRASE` in its message),
    else None. The message is the provider's own, unmasked here: only its moment is read from
    it; what is kept is `_error_words`'."""
    try:
        err = (resp.json() or {}).get("error") or {}
    except (ValueError, AttributeError):
        return None
    if not isinstance(err, dict) or err.get("type") != LIMIT_TYPE:
        return None
    message = str(err.get("message") or "")
    if LIMIT_PHRASE not in message.lower():
        return None
    return {"until": regain_moment(message), "message": message}


def _limit_error(resp, status, words, attempts, kept):
    """The `WorkspaceLimit` *resp* is, or None (`workspace_limit`)."""
    got = workspace_limit(resp)
    if got is None:
        return None
    return WorkspaceLimit(f"HTTP {status}: {words}", until=got["until"], said=words,
                          status=status, attempts=attempts, headers=kept)


@dataclass
class Reply:
    status: int
    body: dict
    headers: dict = field(default_factory=dict)
    attempts: int = 1
    latency_s: float = 0.0
    #: What a streamed answer's stream measured (`_read_stream`): its events, its longest gap
    #: between two events and whether output began; ``{}`` for an answer read whole.
    stream: dict = field(default_factory=dict)


def ratelimit_headers(headers) -> dict:
    return {k.lower(): v for k, v in (headers or {}).items()
            if k.lower().startswith(RATELIMIT_PREFIXES) or k.lower() == "retry-after"}


def _retry_after(headers):
    """The seconds the provider's `retry-after` asks for, at least 0; None when it sends none
    or one that is not a number (the caller then backs off on its own)."""
    value = (headers or {}).get("retry-after")
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return None


def _error_words(resp) -> str:
    """The provider's own error type and message, masked, cut (never the request)."""
    try:
        err = (resp.json() or {}).get("error") or {}
        text = f"{err.get('type', '')}: {err.get('message', '')}".strip(": ")
    except ValueError:
        text = (resp.text or "")[:200]
    from modules.redact import redact_egress
    return redact_egress(text, values={})[:300] or f"HTTP {resp.status_code}"


#: The stream's error events that are a 429 or a 529 in another form, retried as those are
#: when no output has arrived yet (`send`).
RETRIED_EVENTS = {"rate_limit_error": (RateLimited, 429), "overloaded_error": (Overloaded, 529)}


class _EarlyError(Exception):
    """An ``error`` event of `RETRIED_EVENTS` before any output: the send's retry loop takes it
    as the status it stands for."""

    def __init__(self, kind: str, words: str):
        super().__init__(words)
        self.kind = kind
        self.words = words


def _events(resp):
    """The server-sent events of *resp*, each its ``data`` parsed as JSON (``{"type", ...}``),
    in order; a ``data`` that is not JSON is skipped, logged by its event name (never its
    text). Raises what reading the socket raises (`requests.RequestException`)."""
    import json as _json

    name, data = "", []
    for raw in resp.iter_lines(chunk_size=None):
        line = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
        if not line:
            if data:
                try:
                    yield _json.loads("\n".join(data))
                except ValueError:
                    log.warning("anthropic: a stream's %s event was not JSON; skipped",
                                name or "unnamed")
            name, data = "", []
            continue
        if line.startswith(":"):
            continue
        field_, _, value = line.partition(":")
        value = value[1:] if value.startswith(" ") else value
        if field_ == "event":
            name = value
        elif field_ == "data":
            data.append(value)
    if data:
        try:
            yield _json.loads("\n".join(data))
        except ValueError:
            log.warning("anthropic: a stream's last %s event was not JSON; skipped",
                        name or "unnamed")


#: Characters a token the live count of a stream's output assumes before the provider's own
#: usage arrives (`live_output_tokens`): the gateway's fallback estimate's 1.8
#: (`gateway.CHARS_PER_TOKEN`, calibrated to be OVER every recorded call's real tokens), so
#: the running cost is never under what the provider bills.
LIVE_CHARS_PER_TOKEN = 1.8


def live_output_tokens(chars: int, deltas: int, reported: int) -> int:
    """A stream's output so far in tokens, for its running cost: the provider's own
    ``output_tokens`` where a ``message_delta`` reported it, else the deltas' characters at
    `LIVE_CHARS_PER_TOKEN` (at least one token a delta), whichever is larger, so it is never
    under."""
    return max(int(reported or 0), int(chars / LIVE_CHARS_PER_TOKEN) + 1 if chars else 0,
               int(deltas or 0))


def _read_stream(resp, *, clock, progress=None) -> tuple:
    """``(body, stream)``: a streamed answer assembled as the whole answer's body
    (``content``, ``stop_reason``, ``usage``, ``model``, ``id``), and what the stream measured
    (``{"events", "longest_gap_s", "output_began", "output_estimated"}``). Raises
    `_EarlyError` for a retried error event before any output, `StreamError` for any other
    error event, `StreamFailed` for a stream that broke off or ended without
    ``message_stop``, and `StreamAborted` when *progress* stops it.

    *progress*, when given, is called after each event with the live count ``{"usage",
    "output_tokens", "how"}`` (*output_tokens* by `live_output_tokens`, *how* ``reported``
    once a ``message_delta`` gave the provider's own count, else ``estimated``); a non-empty
    string back is why to stop: the connection is closed at once (closing it is what stops the
    provider generating, and billing), and `StreamAborted` raised with that reason."""
    msg, blocks, usage = {}, {}, {}
    began, started, stopped = False, False, False
    events, longest, last = 0, 0.0, clock()
    live = {"chars": 0, "deltas": 0, "reported": 0}

    def counted():
        return live_output_tokens(live["chars"], live["deltas"], live["reported"])

    def failed(cls, words):
        return cls(words, usage=usage, partial=started, output_began=began,
                   stream={"events": events, "longest_gap_s": round(longest, 3),
                           "output_began": began, "output_estimated": counted(),
                           "output_reported": live["reported"] or None})

    try:
        for ev in _events(resp):
            now = clock()
            longest, last = max(longest, now - last), now
            events += 1
            kind = ev.get("type") if isinstance(ev, dict) else ""
            if kind == "message_start":
                started = True
                msg = dict(ev.get("message") or {})
                usage.update(msg.get("usage") or {})
            elif kind == "content_block_start":
                blocks[int(ev.get("index") or 0)] = dict(ev.get("content_block") or {})
            elif kind == "content_block_delta":
                began = True
                block = blocks.setdefault(int(ev.get("index") or 0), {"type": "text"})
                delta = ev.get("delta") or {}
                live["deltas"] += 1
                for key in ("text", "thinking", "signature", "partial_json"):
                    if key in delta:
                        block[key] = str(block.get(key) or "") + str(delta[key])
                        live["chars"] += len(str(delta[key]))
            elif kind == "message_delta":
                msg.update({k: v for k, v in (ev.get("delta") or {}).items()})
                usage.update(ev.get("usage") or {})
                live["reported"] = int((ev.get("usage") or {}).get("output_tokens")
                                       or live["reported"])
            elif kind == "message_stop":
                stopped = True
            elif kind == "error":
                err = ev.get("error") or {}
                etype = str(err.get("type") or "error")
                from modules.redact import redact_egress
                words = redact_egress(f"{etype}: {err.get('message') or ''}",
                                      values={})[:300]
                if not began and etype in RETRIED_EVENTS:
                    raise _EarlyError(etype, words)
                raise failed(StreamError, f"the stream's error event after "
                                          f"{'output began' if began else 'it started'}: "
                                          f"{words}")
            # Never once the answer is whole: a message_delta carrying its stop reason, or
            # message_stop, ends the answer, so a complete answer is never thrown away by a
            # late check (the review, 2026-11-16).
            if progress is not None and not stopped and not msg.get("stop_reason"):
                why = progress({"usage": dict(usage), "output_tokens": counted(),
                                "how": "reported" if live["reported"] else "estimated"})
                if why:
                    close = getattr(resp, "close", None)
                    if callable(close):
                        close()
                    raise failed(StreamAborted, str(why))
            if stopped:
                break
    except (requests.RequestException, OSError) as exc:
        if not msg.get("stop_reason"):
            idle = isinstance(exc, requests.RequestException) and "timed out" in str(exc).lower()
            raise failed(StreamFailed, (f"no event within {STREAM_IDLE_S:.0f} s" if idle else
                                        "the connection broke") + f" mid-stream "
                                       f"({type(exc).__name__}) after {events} event(s)") from exc
        # The answer was whole (its message_delta carried the stop reason and its usage) and
        # only message_stop was lost: kept as complete, the missing stop recorded (the review,
        # 2026-11-16: a whole answer is never lost).
        missing = type(exc).__name__
    else:
        missing = "" if stopped or msg.get("stop_reason") else None
    if missing is None and not events:
        # Said as what it was: a 200 carrying no event at all is no stream (a proxy's HTML
        # page), never "a stream that ended" (the correctness review's audit, half 1 row 4).
        raise failed(StreamFailed, "HTTP 200 with a body that is not an event stream: no "
                                   "event in it")
    if missing is None:
        raise failed(StreamFailed, f"the stream ended without message_stop after {events} "
                                   "event(s)")
    body = {k: v for k, v in msg.items() if k not in ("content", "usage")}
    body["content"] = [blocks[i] for i in sorted(blocks)]
    body["usage"] = usage
    return body, {"events": events, "longest_gap_s": round(longest, 3), "output_began": began,
                  "output_estimated": counted(),
                  **({"message_stop_missing": missing or "the stream ended"}
                     if not stopped else {})}


def send(body: dict, api_key: str, *, session=None, sleep=time.sleep, clock=time.monotonic,
         timeout=TIMEOUT, progress=None) -> Reply:
    """POST *body* to the Messages API with *api_key*, streamed (the module's docstring); a
    `Reply` whose body is the assembled answer, or an `AdapterError`. *progress* is called
    after each event of the stream (`_read_stream`)."""
    if not api_key:
        raise KeyRefused("no API key is set")
    http = session or requests
    headers = {"x-api-key": api_key, "anthropic-version": API_VERSION,
               "content-type": "application/json"}
    streamed = dict(body, stream=True)
    started = clock()
    attempt = 0
    while True:
        attempt += 1
        try:
            resp = http.post(URL, json=streamed, headers=headers, timeout=timeout, stream=True)
        except requests.Timeout as exc:
            raise ProviderDown(f"no answer within {timeout[1]:.0f} s ({type(exc).__name__})",
                               attempts=attempt)
        except requests.RequestException as exc:
            raise ProviderDown(f"could not reach {URL} ({type(exc).__name__})",
                               attempts=attempt)
        kept = ratelimit_headers(resp.headers)
        status = resp.status_code
        early = None
        if status == 200:
            try:
                parsed, stream = _read_stream(resp, clock=clock, progress=progress)
            except _EarlyError as exc:
                early = exc
            except StreamFailed as exc:
                exc.attempts, exc.headers, exc.status = attempt, kept, status
                raise
            else:
                return Reply(status=status, body=parsed, headers=kept, attempts=attempt,
                             latency_s=clock() - started, stream=stream)
            finally:
                close = getattr(resp, "close", None)
                if callable(close):
                    close()
        if early is not None:
            cls, status = RETRIED_EVENTS[early.kind]
            words, wait = early.words, float(2 ** (attempt - 1))
        else:
            words = _error_words(resp)
            limited = _limit_error(resp, status, words, attempt, kept)
            if limited is not None:
                raise limited
        if status in (429, 529):
            if early is None:
                cls = RateLimited if status == 429 else Overloaded
                wait = _retry_after(resp.headers)
                if wait is None:
                    wait = float(2 ** (attempt - 1))
            if attempt > MAX_RETRIES:
                raise cls(f"HTTP {status} after {attempt} attempts: {words}", status=status,
                          attempts=attempt, headers=kept)
            if wait > MAX_WAIT_S:
                raise cls(f"HTTP {status}: the provider asks for {wait:.0f} s, over the "
                          f"{MAX_WAIT_S:.0f} s a waiting call allows: {words}",
                          status=status, attempts=attempt, headers=kept)
            log.info("anthropic: HTTP %s, attempt %s, waiting %.1f s", status, attempt, wait)
            sleep(wait)
            continue
        if status in (401, 403):
            raise KeyRefused(f"HTTP {status}: {words}", status=status, attempts=attempt,
                             headers=kept)
        if status in (400, 404, 413):
            raise BadRequest(f"HTTP {status}: {words}", status=status, attempts=attempt,
                             headers=kept)
        raise ProviderDown(f"HTTP {status}: {words}", status=status, attempts=attempt,
                           headers=kept)


@dataclass
class Count:
    tokens: int
    headers: dict = field(default_factory=dict)
    latency_s: float = 0.0


def count_body(body: dict) -> dict:
    """What the count is sent of a send's *body*: its `COUNT_KEYS`, the same values (the same
    masked bytes the send would carry), every other key (``max_tokens``, ``temperature``) left
    out, as the endpoint takes none of them."""
    return {k: body[k] for k in COUNT_KEYS if k in body}


def count_tokens(body: dict, api_key: str, *, session=None, clock=time.monotonic,
                 timeout=COUNT_TIMEOUT) -> Count:
    """The provider's count of *body*'s input tokens (`count_body` of it), with *api_key*; a
    `Count`, or an `AdapterError` (never retried: a 429 or 529 is raised at once, a person may
    be waiting and the gateway has its estimate)."""
    if not api_key:
        raise KeyRefused("no API key is set")
    http = session or requests
    headers = {"x-api-key": api_key, "anthropic-version": API_VERSION,
               "content-type": "application/json"}
    started = clock()
    try:
        resp = http.post(COUNT_URL, json=count_body(body), headers=headers, timeout=timeout)
    except requests.Timeout as exc:
        raise ProviderDown(f"no count within {timeout[1]:.0f} s ({type(exc).__name__})")
    except requests.RequestException as exc:
        raise ProviderDown(f"could not reach {COUNT_URL} ({type(exc).__name__})")
    kept = ratelimit_headers(resp.headers)
    status = resp.status_code
    if status == 200:
        try:
            got = (resp.json() or {}).get("input_tokens")
        except (ValueError, AttributeError):
            got = None
        if not isinstance(got, int) or isinstance(got, bool) or got < 0:
            raise ProviderDown("HTTP 200 with no input_tokens count", status=status,
                               headers=kept)
        return Count(tokens=got, headers=kept, latency_s=clock() - started)
    words = _error_words(resp)
    limited = _limit_error(resp, status, words, 1, kept)
    if limited is not None:
        raise limited
    cls = {429: RateLimited, 529: Overloaded, 401: KeyRefused, 403: KeyRefused,
           400: BadRequest, 404: BadRequest, 413: BadRequest}.get(status, ProviderDown)
    raise cls(f"HTTP {status}: {words}", status=status, headers=kept)


# ── The Message Batches API (evaluation rounds only: the operator's decision of 2026-10-29,
#    PHASE8_PLAN 15.12; `gateway.ask_batch`) ───────────────────────────────────────────────
#
# The wire shape is Anthropic's, read 2026-10-29 (platform.claude.com/docs/en/build-with-
# claude/batch-processing; the claude-api reference's Message Batches): `POST
# /v1/messages/batches` with ``{"requests": [{"custom_id", "params"}]}``, each ``params`` a
# Messages request body; `GET /v1/messages/batches/<id>` its state (``processing_status``
# ``in_progress``, ``canceling`` or ``ended``, and ``request_counts``); `POST
# .../<id>/cancel`; `GET .../<id>/results`, one JSON line a request, ``{"custom_id",
# "result": {"type": "succeeded", "message"} | {"type": "errored", "error"} | {"type":
# "canceled"} | {"type": "expired"}}``, in any order. The same headers as a send. None is
# retried here: the gateway's poll asks again on its own bound.

BATCHES_URL = "https://api.anthropic.com/v1/messages/batches"
#: A batch's create and state reads, connect and read bounds, seconds (a create uploads every
#: request's body; not measured yet, re-derived from the first live rounds).
BATCH_TIMEOUT = (5.0, 60.0)
#: The results' read bound: every answer of the batch in one body.
BATCH_RESULTS_TIMEOUT = (5.0, 120.0)
#: A batch's id as the provider names one (``msgbatch_...``): checked before it is put in an
#: address, so an answer can never steer where the key is sent.
_BATCH_ID = re.compile(r"^msgbatch_[A-Za-z0-9]{1,100}$")


@dataclass
class Batch:
    id: str
    status: str
    counts: dict = field(default_factory=dict)
    headers: dict = field(default_factory=dict)
    ended_at: str = ""


def _batch_url(batch_id: str, tail: str = "") -> str:
    """The provider's address for *batch_id* (and *tail*), always under `BATCHES_URL`: the
    results are read from the address built here, never from the ``results_url`` an answer
    names, so the key goes to the provider's own host only."""
    if not isinstance(batch_id, str) or not _BATCH_ID.match(batch_id):
        raise BadRequest(f"{batch_id!r} is not a batch id the provider names (msgbatch_...)")
    return f"{BATCHES_URL}/{batch_id}{tail}"


def _batch_http(method: str, url: str, api_key: str, *, body=None, session=None,
                timeout=BATCH_TIMEOUT):
    """One request to the batches API: ``(resp, kept headers)`` for a 200, else the
    `AdapterError` its status is (a workspace's usage limit its own kind, as a send's)."""
    if not api_key:
        raise KeyRefused("no API key is set")
    http = session or requests
    headers = {"x-api-key": api_key, "anthropic-version": API_VERSION,
               "content-type": "application/json"}
    try:
        if method == "POST":
            resp = http.post(url, json=body if body is not None else {}, headers=headers,
                             timeout=timeout)
        else:
            resp = http.get(url, headers=headers, timeout=timeout)
    except requests.Timeout as exc:
        raise ProviderDown(f"no answer from the batches API within {timeout[1]:.0f} s "
                           f"({type(exc).__name__})")
    except requests.RequestException as exc:
        raise ProviderDown(f"could not reach {BATCHES_URL} ({type(exc).__name__})")
    kept = ratelimit_headers(resp.headers)
    status = resp.status_code
    if status == 200:
        return resp, kept
    words = _error_words(resp)
    limited = _limit_error(resp, status, words, 1, kept)
    if limited is not None:
        raise limited
    cls = {429: RateLimited, 529: Overloaded, 401: KeyRefused, 403: KeyRefused,
           400: BadRequest, 404: BadRequest, 413: BadRequest}.get(status, ProviderDown)
    raise cls(f"HTTP {status}: {words}", status=status, headers=kept)


def _batch_of(resp, kept) -> Batch:
    try:
        got = resp.json() or {}
    except ValueError:
        raise ProviderDown("HTTP 200 from the batches API with a body that is not JSON",
                           status=200, headers=kept)
    if not isinstance(got, dict) or not isinstance(got.get("id"), str) \
            or not _BATCH_ID.match(got["id"]) or not isinstance(got.get("processing_status"),
                                                                 str):
        raise ProviderDown("HTTP 200 from the batches API with no batch id or state",
                           status=200, headers=kept)
    counts = got.get("request_counts")
    return Batch(id=got["id"], status=got["processing_status"],
                 counts=dict(counts) if isinstance(counts, dict) else {}, headers=kept,
                 ended_at=str(got.get("ended_at") or ""))


def batch_create(batch_requests: list, api_key: str, *, session=None,
                 timeout=BATCH_TIMEOUT) -> Batch:
    """Submit *batch_requests* (``[{"custom_id", "params"}]``) as one batch: its `Batch`."""
    resp, kept = _batch_http("POST", BATCHES_URL, api_key, body={"requests": batch_requests},
                             session=session, timeout=timeout)
    return _batch_of(resp, kept)


def batch_get(batch_id: str, api_key: str, *, session=None, timeout=BATCH_TIMEOUT) -> Batch:
    """The batch's state now."""
    resp, kept = _batch_http("GET", _batch_url(batch_id), api_key, session=session,
                             timeout=timeout)
    return _batch_of(resp, kept)


def batch_cancel(batch_id: str, api_key: str, *, session=None,
                 timeout=BATCH_TIMEOUT) -> Batch:
    """Ask the provider to cancel the batch: requests not yet processed end ``canceled``."""
    resp, kept = _batch_http("POST", _batch_url(batch_id, "/cancel"), api_key,
                             session=session, timeout=timeout)
    return _batch_of(resp, kept)


def batch_results(batch_id: str, api_key: str, *, session=None,
                  timeout=BATCH_RESULTS_TIMEOUT) -> list:
    """An ended batch's results, one dict a request, in the provider's order (any order): read
    from `_batch_url`'s results address. A line that is not JSON is `ProviderDown`, never
    skipped: a result missing would be a request whose bill is unknown."""
    import json as _json

    resp, kept = _batch_http("GET", _batch_url(batch_id, "/results"), api_key,
                             session=session, timeout=timeout)
    out = []
    for n, line in enumerate((resp.text or "").splitlines(), 1):
        if not line.strip():
            continue
        try:
            got = _json.loads(line)
        except ValueError:
            raise ProviderDown(f"the batch's results line {n} is not JSON", status=200,
                               headers=kept)
        if not isinstance(got, dict):
            raise ProviderDown(f"the batch's results line {n} is not a result", status=200,
                               headers=kept)
        out.append(got)
    return out
