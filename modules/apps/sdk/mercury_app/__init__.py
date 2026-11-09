"""`mercury_app`, the app SDK's contract (C2635; the SDN platform design revision 7, section
11c.6): what a controller app imports to reach the network and to read what Mercury gave it.
Deployed beside the app by the container harness and the controller, and written for the oldest
controller Python the app check knows, 3.5 (no f-strings, no variable annotations), since it
runs on whichever the network's controller measures.

**`start_config(name, version)`** answers the app's START-TIME CONFIG, the file Mercury's
deploy compiled and staged beside the app's version (decision K9; C2707, C2760):
``APPS_ROOT/<name>/<version>.config.json``, the apply script's own `config_path` (the root
script checks its sha256 against the confirmed request before the restart, so what is read is
what was confirmed; `tests/test_app_start_config.py` holds `APPS_ROOT`, `CONFIG_SUFFIX` and
`MAX_BYTES` to the script's). An app calls it once, at load, with its own name and version, so
after the deploy's restart it serves without waiting for a push (C2729). It answers ``{"ok":
bool, "error": str, "config": dict or None, "path": str, "sha256": str}`` and raises nothing:
an absent file, one that cannot be read, one larger than `MAX_BYTES`, one that is not JSON in
UTF-8 or not a JSON object, or a name or version not of the apply script's shape (`NAME`,
`VERSION`: nothing else is ever opened) is ``ok`` false with ``error`` saying which, so the
app's `/health` can say so and never answer ok without its config. A file never holds a
secret: Mercury refuses one before it is staged (`modules/apps/channel.config_secret_refusal`).

**`egress(destination, method="GET", path="", body=None, timeout=None)`** is the app's one way
to the network (C2645). *destination* is a name its `manifest.yml` declares under `egress`,
written as a string literal in the call (`mercury app check` refuses any other call, naming
it); the address is the one the network's config carries at that entry's `from_config` key,
resolved by Mercury's compile step and staged in the app's start-time config under the reserved
key `_mercury` (`modules/apps/app_config.RESERVED`), so it is under the confirmed hash and an
app never holds an address of its own. The calling app is found by IDENTITY: the file of the
nearest caller staged at ``APPS_ROOT/<name>/<version>/``, whose own config's destinations are
the only ones it may reach. It answers `{"ok": bool, "error": str, "status": int, "body":
...}` and raises nothing for a destination that does not answer: `ok` is false and `error`
says why (a 2xx is ok; anything else, a redirect included, is not: a redirect is never
followed, so a destination cannot send the app elsewhere). `EgressRefused` is raised, naming
why, for a destination the app's config does not carry, a caller that is not a staged app, a
method outside `METHODS`, a path out of shape, a timeout outside (0, `MAX_TIMEOUT_S`] or a
body that is not JSON. No proxy from the environment is used, and an answer larger than
`MAX_BYTES` is not ok. `NotDeployed` is kept for apps written against the stub; nothing raises
it now.
"""

import hashlib
import json
import os
import re
import sys

__all__ = ["EgressRefused", "NotDeployed", "egress", "start_config"]

METHODS = ("GET", "POST", "PUT", "DELETE")
#: Where the controller's apps are staged, and the start-time config's suffix and size bound:
#: the apply script's (deploy/controller/mercury-ryu-apply APPS_ROOT, CONFIG_SUFFIX,
#: MAX_BYTES), held equal by tests/test_app_start_config.py.
APPS_ROOT = "/opt/ryu-apps"
CONFIG_SUFFIX = ".config.json"
MAX_BYTES = 64 * 1024
#: An app's name and version as the apply script accepts them (its NAME and VERSION).
NAME = re.compile(r"^[a-z][a-z0-9_]{0,40}$")
VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")


class EgressRefused(Exception):
    """A call to a destination the app's manifest does not declare."""


class NotDeployed(RuntimeError):
    """Kept for apps written against the contract stub; nothing raises it now (C2645)."""


#: The start-time config's reserved key (modules/apps/app_config.RESERVED, held equal by
#: tests/test_app_egress.py): Mercury's, never the app's, stripped before the app reads it.
RESERVED = "_mercury"
#: The bound on one egress call, and its default (the dns_blacklist contract's verdict service
#: allows at most 10 s; NOT MEASURED against a real destination).
MAX_TIMEOUT_S = 10.0
DEFAULT_TIMEOUT_S = 5.0
#: A path the call may add to its destination's address: absolute, printable, no "..", no
#: doubled slash, no fragment.
PATH = re.compile(r"^(/[A-Za-z0-9._~!$&'()*+,;=:@%/-]*(\?[A-Za-z0-9._~!$&'()*+,;=:@%/?-]*)?)?$")


def _caller_app():
    """``(name, version)`` of the nearest caller staged at APPS_ROOT/<name>/<version>/, or
    None. By the caller's own file (identity), never by a name it gives."""
    root = os.path.realpath(APPS_ROOT) + os.sep
    frame = sys._getframe(2)  # noqa: SLF001 - the caller's frames are the identity
    while frame is not None:
        f = frame.f_globals.get("__file__")
        if isinstance(f, str):
            real = os.path.realpath(f)
            if real.startswith(root):
                parts = real[len(root):].split(os.sep)
                if len(parts) >= 3 and NAME.match(parts[0]) and VERSION.match(parts[1]):
                    return parts[0], parts[1]
        frame = frame.f_back
    return None


def _destinations(name, version):
    """``(urls by destination, error)`` from *name* *version*'s start-time config."""
    got = _read_config(name, version)
    if not got["ok"]:
        return None, got["error"]
    section = got["config"].get(RESERVED)
    urls = section.get("egress") if isinstance(section, dict) else None
    return (urls if isinstance(urls, dict) else {}), ""


def _refuse(why):
    raise EgressRefused("mercury_app.egress refused: " + why)


def _no_redirects():
    import urllib.request

    class _Refuse(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    return urllib.request.build_opener(urllib.request.ProxyHandler({}), _Refuse)


def _answer_body(raw, content_type):
    text = raw.decode("utf-8", "replace")
    if "json" in (content_type or ""):
        try:
            return json.loads(text)
        except ValueError:
            return text
    return text


def egress(destination, method="GET", path="", body=None, timeout=None):
    """A request to the declared *destination* (see the module's docstring)."""
    import socket
    import urllib.error
    import urllib.request

    app = _caller_app()
    if app is None:
        _refuse("it was called from no app staged at %s/<name>/<version>/, so no manifest's "
                "destinations apply" % APPS_ROOT)
    name, version = app
    urls, error = _destinations(name, version)
    if urls is None:
        _refuse("%s %s's start-time config could not be read (%s), so its destinations are "
                "not known" % (name, version, error))
    if not isinstance(destination, str) or destination not in urls:
        _refuse("%r is not a destination %s %s's config carries (it carries: %s)"
                % (destination, name, version, ", ".join(sorted(urls)) or "none"))
    method = method.upper() if isinstance(method, str) else method
    if method not in METHODS:
        _refuse("the method %r is not one of %s" % (method, ", ".join(METHODS)))
    if not isinstance(path, str) or not PATH.match(path) or "/../" in path + "/" \
            or path.startswith("//"):
        _refuse("the path %r is not an absolute path of the shape %s, without .. or a doubled "
                "slash" % (path, PATH.pattern))
    if timeout is None:
        timeout = DEFAULT_TIMEOUT_S
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) \
            or not 0 < timeout <= MAX_TIMEOUT_S:
        _refuse("the timeout %r is not a number of seconds in (0, %s]" % (timeout,
                                                                        MAX_TIMEOUT_S))
    data, headers = None, {"Accept": "application/json"}
    if body is not None:
        try:
            data = json.dumps(body, sort_keys=True).encode("utf-8")
        except (TypeError, ValueError) as exc:
            _refuse("the body is not JSON (%s)" % exc)
        headers["Content-Type"] = "application/json"
    url = urls[destination].rstrip("/") + path
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with _no_redirects().open(req, timeout=timeout) as resp:
            raw = resp.read(MAX_BYTES + 1)
            status = resp.status
            ctype = resp.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        raw = exc.read(MAX_BYTES + 1) if exc.fp is not None else b""
        return {"ok": False, "status": exc.code, "body": _answer_body(raw[:MAX_BYTES],
                exc.headers.get("Content-Type", "") if exc.headers else ""),
                "error": "%s answered %s %s" % (destination, exc.code, exc.reason)}
    except (urllib.error.URLError, socket.timeout, OSError, ValueError) as exc:
        reason = getattr(exc, "reason", exc)
        return {"ok": False, "status": 0, "body": None,
                "error": "%s did not answer (%s)" % (destination, reason)}
    if len(raw) > MAX_BYTES:
        return {"ok": False, "status": status, "body": None,
                "error": "%s's answer is more than %d bytes" % (destination, MAX_BYTES)}
    ok = 200 <= status < 300
    return {"ok": ok, "status": status, "body": _answer_body(raw, ctype),
            "error": "" if ok else "%s answered %s" % (destination, status)}


def config_path(name, version):
    """Where *name* *version*'s start-time config is staged (the apply script's
    `config_path`)."""
    return os.path.join(APPS_ROOT, name, version + CONFIG_SUFFIX)


def _answer(ok, error, path, config=None, sha256=""):
    return {"ok": ok, "error": error, "config": config, "path": path, "sha256": sha256}


def start_config(name, version):
    """The app's start-time config (see the module's docstring), without Mercury's reserved
    key: the app reads the config its manifest's schema declares, nothing else."""
    got = _read_config(name, version)
    if got["ok"]:
        got["config"] = dict((k, v) for k, v in got["config"].items() if k != RESERVED)
    return got


def _read_config(name, version):
    """The staged start-time config file as it is, the reserved key included."""
    if not isinstance(name, str) or not NAME.match(name) or "\n" in name:
        return _answer(False, "the app's name %r is not of the shape the apply script stages "
                              "(%s), so no file was opened" % (name, NAME.pattern), "")
    if not isinstance(version, str) or not VERSION.match(version) or "\n" in version:
        return _answer(False, "the version %r is not of the shape the apply script stages "
                              "(%s), so no file was opened" % (version, VERSION.pattern), "")
    path = config_path(name, version)
    try:
        fh = open(path, "rb")
    except OSError as exc:
        if not os.path.lexists(path):
            return _answer(False, "no start-time config at %s: the deploy staged none for %s "
                                  "%s" % (path, name, version), path)
        return _answer(False, "the start-time config %s cannot be read (%s)"
                       % (path, exc.strerror or exc), path)
    try:
        data = fh.read(MAX_BYTES + 1)
    except OSError as exc:
        return _answer(False, "the start-time config %s cannot be read (%s)"
                       % (path, exc.strerror or exc), path)
    finally:
        fh.close()
    if len(data) > MAX_BYTES:
        return _answer(False, "the start-time config %s is more than %d bytes, the apply "
                              "script's bound" % (path, MAX_BYTES), path)
    sha256 = hashlib.sha256(data).hexdigest()
    try:
        config = json.loads(data.decode("utf-8"))
    except ValueError as exc:
        return _answer(False, "the start-time config %s is not JSON in UTF-8 (%s)"
                       % (path, exc), path, sha256=sha256)
    if not isinstance(config, dict):
        return _answer(False, "the start-time config %s is a JSON %s, not an object"
                       % (path, type(config).__name__), path, sha256=sha256)
    return _answer(True, "", path, config, sha256)
