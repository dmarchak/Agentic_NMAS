"""`mercury_app`, the app SDK's contract (C2635; the SDN platform design revision 7, section
11c.6): what a controller app imports to reach the network. Deployed beside the app by the
container harness and the controller; this is the stub that fixes the contract, and it parses
as Python 3.9, the controller's interpreter.

**`egress(destination, method="GET", path="", body=None, timeout=None)`** is the app's one way
to the network. *destination* is a name its `manifest.yml` declares under `egress`, written as a
string literal in the call (`mercury app check` refuses any other call, naming it); the address
is the one the network's config carries at that entry's `from_config` key, so an app never
holds an address of its own. It answers `{"ok": bool, "error": str, "status": int, "body":
...}` and raises nothing for a destination that does not answer: `ok` is false and `error`
says why. A destination the manifest does not declare is refused with `EgressRefused`.

The stub raises `NotDeployed` from every call: an app's tests run in the container harness,
which gives the working package, never in Mercury's job sandbox.
"""

__all__ = ["EgressRefused", "NotDeployed", "egress"]

METHODS = ("GET", "POST", "PUT", "DELETE")


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
