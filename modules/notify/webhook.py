"""The generic signed webhook (docs/HEAL_TO_INTENT.md section 10).

A POST of JSON (`message.payload`: the incident's id, network, device, kind, outcome, step
summary and link), masked, with two headers a receiver checks:

- ``X-Mercury-Timestamp``: the send's time, whole seconds since the epoch;
- ``X-Mercury-Signature: sha256=<hex>``: HMAC-SHA256, keyed by the webhook's signing secret,
  over the timestamp, a full stop, and the body's exact bytes (``f"{ts}.".encode() + body``).

A receiver recomputes it over the bytes it received, compares in constant time, and refuses
a timestamp more than `TOLERANCE_S` (5 minutes) from its clock, so a captured request cannot
be replayed later (`verify`, the receiver's side, is here for a receiver to copy and for the
tests). The secret is typed by a person and held by the credential store under the
webhook's reference; it is read only here, at the send, and never sent (the signature is a
one-way function of it). Redirects are not followed: the body goes to the URL a person
verified, or nowhere. https, or http only to this host's loopback; IPv6 as IPv4.
"""

import hashlib
import hmac
import json
import time

import requests

from modules.notify import message

#: The receiver's window on the timestamp (section 10: older than 5 minutes is refused).
TOLERANCE_S = 300
#: What a send posts with, a module attribute so a test hands in a fake.
POST = requests.post
USER_AGENT = "Mercury-notify/1"


class Refused(ValueError):
    """A webhook send refused before anything left, and why."""


def body_bytes(payload: dict) -> bytes:
    """The body exactly as sent and signed: compact JSON, keys sorted, UTF-8."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def signature(secret: str, timestamp: str, body: bytes) -> str:
    """``sha256=<hex>``: HMAC-SHA256 keyed by *secret* over ``<timestamp>.<body>``."""
    mac = hmac.new(secret.encode("utf-8"), f"{timestamp}.".encode("ascii") + body,
                   hashlib.sha256)
    return "sha256=" + mac.hexdigest()


def verify(secret: str, timestamp: str, body: bytes, header: str, *, now: float = None,
           tolerance: int = TOLERANCE_S) -> tuple:
    """The receiver's check: ``(ok, why)``. Refuses a timestamp that is not whole seconds or
    is more than *tolerance* seconds from *now*, then compares the signature in constant
    time."""
    now = time.time() if now is None else now
    if not str(timestamp or "").isdigit():
        return False, f"the timestamp {timestamp!r} is not whole seconds"
    age = now - int(timestamp)
    if abs(age) > tolerance:
        return False, (f"the timestamp is {int(age)} s from the receiver's clock, past the "
                       f"{tolerance} s window")
    if not hmac.compare_digest(signature(secret, str(timestamp), body), str(header or "")):
        return False, "the signature does not match the body and timestamp"
    return True, ""


def request(dest: dict, payload: dict, *, event: str, now: float = None) -> tuple:
    """``(url, body, headers)`` for one send, signed; refused (`Refused`) when the secret is
    not set or the bytes would carry it."""
    from modules import credentials
    from modules.notify import addresses

    url = addresses.check_webhook_url(dest.get("url", ""))
    secret = credentials.get_notify_secret(dest.get("secret_ref", "")) \
        if dest.get("secret_ref") else ""
    if not secret:
        raise Refused("the webhook's signing secret is not set, so nothing was sent")
    body = body_bytes(message.mask(payload))
    if message.carries_secret(body, [secret]):
        raise Refused("the body carried the webhook's signing secret, so it was not sent")
    ts = str(int(time.time() if now is None else now))
    headers = {"Content-Type": "application/json", "User-Agent": USER_AGENT,
               "X-Mercury-Event": event, "X-Mercury-Timestamp": ts,
               "X-Mercury-Signature": signature(secret, ts, body)}
    return url, body, headers


def send(dest: dict, payload: dict, *, event: str, timeout: float, now: float = None) -> int:
    """POST one signed event; the HTTP status on a 2xx, else raises naming the status."""
    url, body, headers = request(dest, payload, event=event, now=now)
    resp = POST(url, data=body, headers=headers, timeout=timeout, allow_redirects=False)
    if not 200 <= resp.status_code < 300:
        raise requests.HTTPError(f"the receiver answered HTTP {resp.status_code}")
    return resp.status_code
