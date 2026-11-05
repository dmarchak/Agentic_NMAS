"""Which Host a request may name, and where a write may come from (the operator, 2026-11-05).

C248: Mercury carries no CSRF token, and on the NMAS host Cloudflare Access is what absorbs a
forged cross-site write (every mutating route needs its verified assertion). An install with
the identity gates off has no such layer: the final SDN lab's laptop install (identity option
(c) for its hardware sitting, C2520) is reachable by any page the laptop's browser opens. Two
checks stand in for the missing tokens, OWASP's "verifying origin with standard headers" and
Fetch Metadata, both off by default (the prior behaviour) and turned on by the install that
needs them:

- **`allowed_host_names`** (comma-separated, blank = no check): a request whose Host header
  names any other host is refused, before any route runs. This answers DNS rebinding: a page
  on an attacker's name resolved to 127.0.0.1 still sends its own name as Host.
- **`require_same_origin_writes`**: a write (any method but GET, HEAD and OPTIONS) is refused
  unless it shows it came from Mercury's own pages:
  - `Sec-Fetch-Site`, when sent, must be `same-origin`;
  - `Origin`, when sent, must be this request's own scheme, host and port;
  - with no `Origin`, a `Referer` must be on that origin;
  - a write carrying none of the three is refused (the operator's condition).

The Socket.IO handshake never reaches Flask's hooks, so `socket_origin_allowed` is engineio's
`cors_allowed_origins` callable: with the check on, an Origin is accepted only on an allowed host
and Mercury's own port. Every refusal names what it compared, both operands
(CLAUDE.md, "A refusal or guard names the comparison it made").
"""
import logging
from urllib.parse import urlsplit

log = logging.getLogger(__name__)

SAFE_METHODS = ("GET", "HEAD", "OPTIONS")


def allowed_hosts() -> list:
    """The host names a request may name, lower case; [] when the check is off."""
    from modules.settings_schema import get_setting

    raw = (get_setting("allowed_host_names", "") or "").strip()
    return [h.strip().lower().strip("[]") for h in raw.split(",") if h.strip()]


def same_origin_required() -> bool:
    from modules.settings_schema import get_setting

    return bool(get_setting("require_same_origin_writes", False))


def host_name(host_header: str) -> str:
    """The host of a Host header or an origin's netloc, without its port: ``[::1]:5080`` is
    ``::1``, ``127.0.0.1:5080`` is ``127.0.0.1``."""
    try:
        return (urlsplit("//" + (host_header or "")).hostname or "").lower()
    except ValueError:
        return ""


def _origin_of(url: str) -> str:
    """``scheme://netloc`` of *url*, lower case; "" when it has none."""
    try:
        parts = urlsplit(url or "")
    except ValueError:
        return ""
    if not parts.scheme or not parts.netloc:
        return ""
    return f"{parts.scheme}://{parts.netloc}".lower()


def refusal(method: str, host_header: str, own_origin: str, headers) -> str:
    """Why this request is refused, or "" when it may go on. *own_origin* is the request's own
    ``scheme://host[:port]``; *headers* is any mapping with ``get``."""
    hosts = allowed_hosts()
    if hosts:
        name = host_name(host_header)
        if name not in hosts:
            return (f"the Host header names {name or '(none)'!r}, and this installation "
                    f"answers only to {', '.join(hosts)} (allowed_host_names)")
    if method.upper() in SAFE_METHODS or not same_origin_required():
        return ""
    own = (own_origin or "").lower()
    site = (headers.get("Sec-Fetch-Site") or "").strip().lower()
    origin = (headers.get("Origin") or "").strip()
    referer = (headers.get("Referer") or "").strip()
    if site and site != "same-origin":
        return (f"a write from Sec-Fetch-Site {site!r}, where only 'same-origin' is accepted "
                f"(require_same_origin_writes)")
    if origin:
        if origin.lower() != own:
            return (f"a write from Origin {origin!r}, where only this installation's own "
                    f"{own!r} is accepted (require_same_origin_writes)")
        return ""
    if referer:
        if _origin_of(referer) != own:
            return (f"a write whose Referer is on {_origin_of(referer) or referer!r}, where only "
                    f"this installation's own {own!r} is accepted (require_same_origin_writes)")
        return ""
    if site:
        return ""
    return ("a write carrying none of Origin, Referer and Sec-Fetch-Site, so where it came "
            f"from cannot be shown to be {own!r} (require_same_origin_writes)")


def enforce():
    """The `before_request` hook: a refusal answers 403 (400 for a foreign Host), naming why."""
    from flask import jsonify, request

    why = refusal(request.method, request.host, request.host_url.rstrip("/"), request.headers)
    if not why:
        return None
    log.warning("request refused: %s %s: %s", request.method, request.path, why)
    status = 400 if why.startswith("the Host header") else 403
    return jsonify({"ok": False, "error": f"Refused: {why}"}), status


def socket_origin_allowed(origin: str) -> bool:
    """engineio's `cors_allowed_origins` callable. Off (both settings at their defaults): every
    Origin, as `"*"` was. On: an Origin on an allowed host and Mercury's own port only."""
    hosts = allowed_hosts()
    if not hosts and not same_origin_required():
        return True
    from modules import config

    try:
        parts = urlsplit(origin or "")
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError:
        return False
    name = (parts.hostname or "").lower()
    ok = bool(name) and (not hosts or name in hosts) and port == int(config.FLASK_PORT)
    if not ok:
        log.warning("socket refused: Origin %r, where %s on port %s is accepted", origin,
                    ", ".join(hosts) or "any host", config.FLASK_PORT)
    return ok


def install(app) -> None:
    app.before_request(enforce)
