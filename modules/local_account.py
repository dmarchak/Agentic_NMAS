"""One local account for an installation that listens on loopback only (C2520's first step; the
operator, 2026-11-10, at the Lab 9 sitting: on the laptop kit no request was a verified person,
so every operation that asks for one refused).

**Off unless four things hold** (`state`): the setting ``local_account_enabled`` is on (off by
default), no access proxy is configured (`identity.is_configured`: a proxy on the same machine
would make every proxied request's peer a loopback address), Mercury listens on loopback only
(`config.FLASK_HOST` is a loopback address, the value the server binds), and an account is set.
A request carrying a header a proxy writes (`identity.PROXY_WRITTEN_HEADERS`) is never taken as
this machine's own.
Behind an access proxy nothing here is reached: `identity.identify` asks this only when the
proxy's assertion did not identify the request, and the proxy's path is unchanged.

**The account**: one name and an scrypt hash of its password (`hashlib.scrypt`, a random salt,
compared in constant time), in ``local_account.json``, owner-only from creation
(`config.open_secure`). The password is set by `scripts/nmas-local-account` with `getpass`; it
is never echoed, logged, stored or returned, here or there.

**The session**: a cookie signed with the app's own secret by Flask's own session signing
(`flask.sessions.SecureCookieSessionInterface`, under this module's salt, so it and Flask's
session cookie never verify as each other), HttpOnly and SameSite=Strict, holding the name, when it was issued, when it was last
seen and the account's key id (so a new password ends every session). It ends `IDLE_S` after
its last use and `MAX_S` after it was issued, whichever is first.

**Sign-in** (`sign_in`): refused unless the request shows it came from Mercury's own page
(`origin_refusal`, whatever ``require_same_origin_writes`` is set to) and from a loopback peer.
A failure makes the next attempt wait (`BACKOFF_S`, doubling to `BACKOFF_MAX_S`), kept in a file
so it holds across processes; an attempt inside the wait is refused without the password being
checked.

**What a signed-in request is** (`identity`): a person, verified as ``local-account``
(`VERIFICATION`), never ``access``. Every record says so beside the name.
"""

import hashlib
import hmac
import ipaddress
import json
import logging
import os
import re
import secrets
import time

from modules.identity import LOCAL_ACCOUNT

log = logging.getLogger(__name__)

SETTING = "local_account_enabled"
#: How a request signed in here was established: a kind of its own, never the proxy's
#: (`identity.REQUEST_VERIFICATIONS` holds the two).
VERIFICATION = LOCAL_ACCOUNT
FILE = "local_account.json"
ATTEMPTS_FILE = "local_account_attempts.json"
COOKIE = "mercury_local_account"
#: The session ends this long after its last use, and this long after it was issued.
IDLE_S = 30 * 60
MAX_S = 12 * 3600
#: The cookie's last-seen time is written again when it is older than this.
REFRESH_S = 60
#: The wait after the first failed sign-in; it doubles with each failure, to the maximum.
BACKOFF_S = 2
BACKOFF_MAX_S = 300
MIN_PASSWORD = 12
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._@-]{0,63}\Z")
#: scrypt's cost (RFC 7914's interactive parameters, N raised): about 32 MiB and well under a
#: second on the laptop.
SCRYPT = {"n": 2 ** 15, "r": 8, "p": 1}
_DKLEN = 32
_SALT = "mercury-local-account-v1"


class Refused(ValueError):
    """Nothing was changed; the message says why. It never holds a password."""


def _path(name: str = FILE) -> str:
    from modules.config import DATA_DIR

    return os.path.join(DATA_DIR, name)


def _hash(password: str, salt: bytes, cost: dict) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=int(cost["n"]),
                          r=int(cost["r"]), p=int(cost["p"]), dklen=_DKLEN,
                          maxmem=256 * 1024 * 1024)


def account() -> dict:
    """The stored account, ``{"name", "salt", "hash", "scrypt", "set_at"}``, or ``{}`` when
    none is set or the file cannot be read (an unreadable file signs nobody in)."""
    try:
        with open(_path(), encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError):
        return {}
    if not isinstance(doc, dict) or not all(isinstance(doc.get(k), str) and doc.get(k)
                                            for k in ("name", "salt", "hash")):
        return {}
    return doc


def key_id(acct: dict) -> str:
    """What a session is bound to: it changes when the password does. Not the hash."""
    return hashlib.sha256(("key-id:" + acct.get("salt", "") + acct.get("hash", ""))
                          .encode()).hexdigest()[:16]


def set_password(name: str, password: str) -> dict:
    """Set the one account: *name* and an scrypt hash of *password*. ``{"name", "set_at"}``.
    The file is owner-only from creation; the password is not kept."""
    from modules.config import open_secure

    name = (name or "").strip()
    if not NAME.match(name) or name.lower() == "unverified" or name.startswith("service:"):
        raise Refused(f"{name!r} is not an account name (a letter or digit, then letters, "
                      "digits and . _ @ -, at most 64)")
    if not isinstance(password, str) or len(password) < MIN_PASSWORD:
        raise Refused(f"the password is shorter than {MIN_PASSWORD} characters")
    salt = secrets.token_bytes(16)
    doc = {"name": name, "salt": salt.hex(), "hash": _hash(password, salt, SCRYPT).hex(),
           "scrypt": dict(SCRYPT), "set_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    path = _path()
    tmp = path + ".new"
    with open_secure(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, sort_keys=True)
    os.replace(tmp, path)
    _attempts_write({})
    log.info("local account: the account was set (name and hash; no value logged)")
    return {"name": name, "set_at": doc["set_at"]}


def clear() -> bool:
    """Remove the account (and so every session). True when there was one."""
    try:
        os.remove(_path())
        return True
    except FileNotFoundError:
        return False


def _loopback(host: str) -> bool:
    host = (host or "").strip().strip("[]")
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host.split("%", 1)[0]).is_loopback
    except ValueError:
        return False


def bind_host() -> str:
    """The address the server binds (`config.FLASK_HOST`: NMAS_HOST, else ``flask_host``)."""
    from modules import config

    return str(config.FLASK_HOST or "")


def state() -> dict:
    """``{"enabled", "why", "setting", "loopback", "account", "bind"}``: whether a local
    sign-in is possible on this installation now, and when it is not, the one reason, naming
    both sides of the comparison."""
    from modules.settings_schema import get_setting

    # The key by name, never `SETTING`: a parse judges a literal key against its scope
    # (host-wide, modules/settings_scope.py), and cannot judge a computed one.
    setting = bool(get_setting("local_account_enabled", False))
    bind = bind_host()
    loop = _loopback(bind)
    acct = account()
    why = ""
    try:
        from modules import identity as I
        proxied = I.is_configured()
    except Exception:                                   # noqa: BLE001 (unknown is not "none")
        proxied = True
    if not setting:
        why = f"the setting {SETTING} is off (the default)"
    elif proxied:
        # A proxy on this machine makes every proxied request's peer a loopback address.
        why = ("an access proxy is configured for this installation (its cf_access values are "
               "set), and there identity is the proxy's alone")
    elif not loop:
        why = (f"Mercury listens on {bind or '(no address)'}, and a local account is offered "
               "only where it listens on loopback only (127.0.0.1 or ::1)")
    elif not acct:
        why = ("no account is set: run scripts/nmas-local-account set-password <name> on "
               "this machine")
    return {"enabled": not why, "why": why, "setting": setting, "loopback": loop,
            "account": acct.get("name", ""), "bind": bind}


# ───────────────────────────────────────────────────────────────── the wait after a failure

def _attempts() -> dict:
    try:
        with open(_path(ATTEMPTS_FILE), encoding="utf-8") as fh:
            doc = json.load(fh)
        return doc if isinstance(doc, dict) else {}
    except (OSError, ValueError):
        return {}


def _attempts_write(doc: dict) -> None:
    from modules.config import open_secure

    path = _path(ATTEMPTS_FILE)
    tmp = path + ".new"
    with open_secure(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, sort_keys=True)
    os.replace(tmp, path)


def wait_s(now: float = None) -> int:
    """Whole seconds until the next sign-in attempt is taken; 0 when one is taken now."""
    now = time.time() if now is None else now
    until = float(_attempts().get("until") or 0)
    return max(0, int(until - now + 0.999)) if until > now else 0


def _failed(now: float) -> int:
    from modules.filestore import PathLock

    path = _path(ATTEMPTS_FILE)
    with PathLock(path):
        n = int(_attempts().get("failures") or 0) + 1
        wait = min(BACKOFF_S * 2 ** (n - 1), BACKOFF_MAX_S)
        _attempts_write({"failures": n, "until": now + wait})
    return wait


def check(name: str, password: str, now: float = None) -> dict:
    """Is *name* with *password* the account? ``{"ok", "why", "wait_s"}``. Inside the wait
    after a failure nothing is checked. The hash is computed whoever is named, so a wrong name
    and a wrong password take the same time; the comparison is constant-time."""
    now = time.time() if now is None else now
    left = wait_s(now)
    if left:
        return {"ok": False, "wait_s": left,
                "why": f"too soon after a failed sign-in: wait {left} s, then try again"}
    acct = account()
    try:
        salt = bytes.fromhex(acct.get("salt", "")) or _SALT.encode()
        cost = acct.get("scrypt") if isinstance(acct.get("scrypt"), dict) else SCRYPT
        got = _hash(password if isinstance(password, str) else "", salt, cost)
        want = bytes.fromhex(acct.get("hash", "")) or b"\0" * _DKLEN
    except (ValueError, KeyError, TypeError):
        got, want = b"\1" * _DKLEN, b"\0" * _DKLEN
    same_name = hmac.compare_digest((name or "").encode(), acct.get("name", "\0").encode())
    same = hmac.compare_digest(got, want)
    if acct and same_name and same:
        if _attempts():
            _attempts_write({})
        return {"ok": True, "why": "", "wait_s": 0}
    wait = _failed(now)
    log.warning("local account: a sign-in failed; the next attempt waits %s s", wait)
    return {"ok": False, "wait_s": wait,
            "why": f"the name or the password is not the account's; wait {wait} s before the "
                   "next attempt"}


# ───────────────────────────────────────────────────────────────────────── the session cookie

def _signer(secret):
    """Flask's own session signing, keyed on *secret* (the app's): the timed, URL-safe
    serializer `flask.sessions.SecureCookieSessionInterface` builds for the session cookie,
    under this module's salt and SHA-256. ``None`` when there is no secret to sign with."""
    import types

    from flask.sessions import SecureCookieSessionInterface

    class _Signing(SecureCookieSessionInterface):
        salt = _SALT
        digest_method = staticmethod(hashlib.sha256)

    if not secret:
        return None
    # The interface reads the app's secret (and, in later Flask, its fallback keys: none here).
    app = types.SimpleNamespace(secret_key=secret, config={"SECRET_KEY_FALLBACKS": None})
    return _Signing().get_signing_serializer(app)


def issue(acct: dict, secret, now: float = None, issued: float = None) -> str:
    """The cookie's value for *acct*, signed with *secret* (the app's)."""
    now = time.time() if now is None else now
    signer = _signer(secret)
    if signer is None:
        raise ValueError("there is no secret to sign a session with")
    return signer.dumps({"n": acct["name"], "k": key_id(acct),
                         "i": int(issued if issued is not None else now),
                         "s": int(now)})


def read(value: str, secret, now: float = None) -> dict:
    """The session a cookie *value* holds, ``{"name", "issued", "seen"}``, or ``{}`` when it is
    absent, not signed by *secret*, for another account or password, idle past `IDLE_S` or
    older than `MAX_S`."""
    signer = _signer(secret)
    if not value or signer is None:
        return {}
    now = time.time() if now is None else now
    try:
        doc = signer.loads(value)
    except Exception:                                   # noqa: BLE001 (unverifiable: no session)
        return {}
    acct = account()
    if not acct or not isinstance(doc, dict):
        return {}
    try:
        issued, seen = float(doc["i"]), float(doc["s"])
    except (KeyError, TypeError, ValueError):
        return {}
    if doc.get("n") != acct["name"] or doc.get("k") != key_id(acct):
        return {}
    if now - seen > IDLE_S or now - issued > MAX_S or seen > now + 60 or issued > now + 60:
        return {}
    return {"name": acct["name"], "issued": issued, "seen": seen}


def cookie_args(request) -> dict:
    """How the cookie is set: HttpOnly, SameSite=Strict, Secure when the request is."""
    return {"httponly": True, "samesite": "Strict", "secure": bool(request.is_secure),
            "max_age": MAX_S, "path": "/"}


def origin_refusal(request) -> str:
    """Why a sign-in or sign-out POST is refused, or "": it must show it came from this
    installation's own page (Sec-Fetch-Site, Origin or Referer), whatever
    ``require_same_origin_writes`` is set to. A request carrying none of them is refused."""
    own = request.host_url.rstrip("/").lower()
    site = (request.headers.get("Sec-Fetch-Site") or "").strip().lower()
    origin = (request.headers.get("Origin") or "").strip().lower()
    referer = (request.headers.get("Referer") or "").strip().lower()
    if site and site != "same-origin":
        return f"it came from Sec-Fetch-Site {site!r}, and only 'same-origin' is accepted"
    if origin:
        return "" if origin == own else (f"its Origin is {origin!r}, and only this "
                                         f"installation's own {own!r} is accepted")
    if referer:
        return "" if referer == own or referer.startswith(own + "/") else (
            f"its Referer is not on this installation's own {own!r}")
    if site:
        return ""
    return (f"it carries none of Origin, Referer and Sec-Fetch-Site, so it cannot be shown to "
            f"come from {own!r}")


def _peer_loopback(request) -> bool:
    """The socket peer is a loopback address AND nothing says a proxy relayed the request: a
    request holding a header a proxy writes (`identity.PROXY_WRITTEN_HEADERS`) was relayed, so
    its loopback peer is the proxy, not the person."""
    from modules import identity

    if identity.carries_proxy_header(request):
        return False
    return _loopback(identity.peer_address(request))


def session_of(request, secret=None, now: float = None) -> dict:
    """The local session *request* carries, or ``{}``: only where `state` is enabled and the
    socket peer is a loopback address."""
    if not state()["enabled"] or not _peer_loopback(request):
        return {}
    if secret is None:
        from flask import current_app
        secret = current_app.secret_key
    return read(request.cookies.get(COOKIE, ""), secret, now)


def identity(request):
    """The `identity.Identity` of a request signed in here, or None. A person, verified as
    ``local-account``; never the proxy's ``access``."""
    from modules import identity as I

    try:
        sess = session_of(request)
    except Exception as exc:                            # noqa: BLE001 (never raises: no sign-in)
        log.warning("local account: the session could not be read (%s)", type(exc).__name__)
        return None
    if not sess:
        return None
    try:
        from flask import g
        if time.time() - sess["seen"] > REFRESH_S:
            g.nmas_local_refresh = sess
    except Exception:                                   # noqa: BLE001
        pass
    return I.Identity(actor=sess["name"], kind="person", verified=True, outcome="ok",
                      peer=I.peer_address(request), peer_trusted=True,
                      verification=VERIFICATION)


def sign_in(request, name: str, password: str, secret=None, now: float = None) -> dict:
    """``{"ok", "why", "cookie", "name", "wait_s"}``: the cookie's value when *name* and
    *password* are the account's. Refused, naming why, where local sign-in is off, the request
    is not from this installation's own page, or the peer is not loopback."""
    st = state()
    if not st["enabled"]:
        return {"ok": False, "why": f"local sign-in is off: {st['why']}", "cookie": "",
                "name": "", "wait_s": 0}
    why = origin_refusal(request)
    if why:
        return {"ok": False, "why": f"refused: {why}", "cookie": "", "name": "", "wait_s": 0}
    if not _peer_loopback(request):
        return {"ok": False, "why": "refused: the request did not come from this machine",
                "cookie": "", "name": "", "wait_s": 0}
    got = check(name, password, now)
    if not got["ok"]:
        return {"ok": False, "why": got["why"], "cookie": "", "name": "",
                "wait_s": got["wait_s"]}
    if secret is None:
        from flask import current_app
        secret = current_app.secret_key
    acct = account()
    log.info("local account: signed in (the name is in the record, not here)")
    return {"ok": True, "why": "", "cookie": issue(acct, secret, now), "name": acct["name"],
            "wait_s": 0}


def view(request) -> dict:
    """What the sign-in card draws: ``{"enabled", "why", "account", "signed_in", "name",
    "idle_min", "wait_s", "min_password"}``."""
    st = state()
    sess = {}
    try:
        sess = session_of(request)
    except Exception:                                   # noqa: BLE001
        sess = {}
    return {"enabled": st["enabled"], "why": st["why"], "account": st["account"],
            "signed_in": bool(sess), "name": sess.get("name", ""), "idle_min": IDLE_S // 60,
            "wait_s": wait_s(), "min_password": MIN_PASSWORD}
