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
to the network. *destination* is a name its `manifest.yml` declares under `egress`, written as a
string literal in the call (`mercury app check` refuses any other call, naming it); the address
is the one the network's config carries at that entry's `from_config` key, so an app never
holds an address of its own. It answers `{"ok": bool, "error": str, "status": int, "body":
...}` and raises nothing for a destination that does not answer: `ok` is false and `error`
says why. A destination the manifest does not declare is refused with `EgressRefused`.
`egress` is still the contract stub and raises `NotDeployed` (C2645): its working call needs
the compiled config's address and the harness; `start_config` reads only a local file, so it
is the working call here.
"""

import hashlib
import json
import os
import re

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
    """The contract stub was called: the harness or the controller gives the working SDK."""


def egress(destination, method="GET", path="", body=None, timeout=None):
    """A request to the declared *destination* (see the module's docstring)."""
    raise NotDeployed(
        "mercury_app.egress(%r) was called on the contract stub: the container harness and "
        "the controller deploy the working SDK beside the app, and only there does it reach "
        "the network" % (destination,))


def config_path(name, version):
    """Where *name* *version*'s start-time config is staged (the apply script's
    `config_path`)."""
    return os.path.join(APPS_ROOT, name, version + CONFIG_SUFFIX)


def _answer(ok, error, path, config=None, sha256=""):
    return {"ok": ok, "error": error, "config": config, "path": path, "sha256": sha256}


def start_config(name, version):
    """The app's start-time config (see the module's docstring)."""
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
