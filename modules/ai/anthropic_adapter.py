"""The Anthropic adapter: one POST to the Messages API over `requests`, no SDK (the operator,
2026-10-25, PHASE8_PLAN 15.12: "a thin one over requests, behind the gateway's interface ...
so taking the SDK later changes one module").

Its contract with the gateway: `send(body, api_key)` returns a `Reply` or raises one
`AdapterError` subclass, each a kind the gateway records by name:

- `RateLimited` (429) and `Overloaded` (529): retried only these, up to `MAX_RETRIES`,
  waiting what `retry-after` says (seconds), else 1, 2, 4 s; a wait longer than
  `MAX_WAIT_S` is not slept but raised, naming it (a person is waiting on the call);
- `KeyRefused` (401, 403): the key, never retried;
- `BadRequest` (400, 404, 413): the request, never retried;
- `ProviderDown` (any other status, a connection error, a timeout): never retried here.

Never logs or returns the key, the request or the response body (the gateway records the
masked request and the masked answer). The wire shape is Anthropic's reference, read
2026-10-25: `POST /v1/messages`, headers `x-api-key` and `anthropic-version: 2023-06-01`.

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
import time
from dataclasses import dataclass, field

import requests

log = logging.getLogger(__name__)

URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
#: Connect and read bounds, seconds. A Haiku answer of about 400 tokens takes a few seconds
#: (PHASE8_PLAN 15.9's budgets: 5 s); 60 s read is room for the longest feature's
#: max_tokens. Not yet measured on the host: re-derived from the first live calls' latency.
TIMEOUT = (5.0, 60.0)
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


@dataclass
class Reply:
    status: int
    body: dict
    headers: dict = field(default_factory=dict)
    attempts: int = 1
    latency_s: float = 0.0


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


def send(body: dict, api_key: str, *, session=None, sleep=time.sleep, clock=time.monotonic,
         timeout=TIMEOUT) -> Reply:
    """POST *body* to the Messages API with *api_key*; a `Reply`, or an `AdapterError`."""
    if not api_key:
        raise KeyRefused("no API key is set")
    http = session or requests
    headers = {"x-api-key": api_key, "anthropic-version": API_VERSION,
               "content-type": "application/json"}
    started = clock()
    attempt = 0
    while True:
        attempt += 1
        try:
            resp = http.post(URL, json=body, headers=headers, timeout=timeout)
        except requests.Timeout as exc:
            raise ProviderDown(f"no answer within {timeout[1]:.0f} s ({type(exc).__name__})",
                               attempts=attempt)
        except requests.RequestException as exc:
            raise ProviderDown(f"could not reach {URL} ({type(exc).__name__})",
                               attempts=attempt)
        kept = ratelimit_headers(resp.headers)
        status = resp.status_code
        if status == 200:
            try:
                parsed = resp.json()
            except ValueError:
                raise ProviderDown("HTTP 200 with a body that is not JSON", status=status,
                                   attempts=attempt, headers=kept)
            return Reply(status=status, body=parsed, headers=kept, attempts=attempt,
                         latency_s=clock() - started)
        words = _error_words(resp)
        if status in (429, 529):
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
    cls = {429: RateLimited, 529: Overloaded, 401: KeyRefused, 403: KeyRefused,
           400: BadRequest, 404: BadRequest, 413: BadRequest}.get(status, ProviderDown)
    raise cls(f"HTTP {status}: {words}", status=status, headers=kept)
