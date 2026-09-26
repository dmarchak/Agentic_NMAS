"""The harness's network rules (register C46). No side effects on import.

"No test touches a live network" was enforced for nothing a test STARTS. A
test ran the clab sync script with its default URL, which on the deployment
host IS the NMAS, and the live app logged the request on every host run
(2026-09-26). Two layers, because each covers what the other cannot:

1. **The test process.** `install()` makes a connect to anything but loopback
   raise `NetworkRefused`. Measured before it was added: the whole suite made
   NO such connect (an audit hook over every `socket.connect` and
   `getaddrinfo`, with a positive control that it sees one), so it enforces
   the rule as it already holds. It works on every machine.
2. **Every process a test starts.** Only the kernel covers those, whatever
   language they are written in: `scripts/nmas-test` runs the suite in a
   network namespace with loopback alone. `confinement()` MEASURES whether
   that holds, by asking the kernel for a route, which sends no packet.

The deployment host cannot create the namespace (Ubuntu 24.04 restricts
unprivileged user namespaces through AppArmor), so a run there reports itself
NOT confined, in words, rather than claiming a property it does not have.
"""

import errno
import ipaddress
import socket

#: Set by `scripts/nmas-test` (and so by CI): an unconfined run then stops at
#: session start instead of reporting itself.
REQUIRE_ENV = "NMAS_REQUIRE_NETWORK_CONFINEMENT"

#: Documentation addresses (RFC 5737, RFC 3849). A UDP connect to them is a
#: route lookup and sends nothing.
PROBES = ((socket.AF_INET, ("192.0.2.1", 9)), (socket.AF_INET6, ("2001:db8::1", 9)))

_real_connect = socket.socket.connect
_real_connect_ex = socket.socket.connect_ex


class NetworkRefused(ConnectionRefusedError):
    """Raised by the harness, never by a network: a test tried to leave the
    machine."""


def is_loopback(address) -> bool:
    host = address[0] if isinstance(address, tuple) else address
    if isinstance(host, bytes):
        host = host.decode()
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host == "localhost"


def _refuse(sock, address):
    if sock.family in (socket.AF_INET, socket.AF_INET6) and not is_loopback(address):
        raise NetworkRefused(
            errno.ECONNREFUSED,
            f"the test harness refused a connection to {address!r}: tests do not "
            "touch a network (C46). Mock the call, or use a loopback address.")


def _guarded_connect(self, address):
    _refuse(self, address)
    return _real_connect(self, address)


def _guarded_connect_ex(self, address):
    _refuse(self, address)
    return _real_connect_ex(self, address)


def install():
    socket.socket.connect = _guarded_connect
    socket.socket.connect_ex = _guarded_connect_ex


def confinement(connect=None):
    """``(confined, reason)``: True when the kernel has no route to any
    non-loopback address in either family, False when it has one, None when
    the question could not be answered. *connect* is replaceable for tests."""
    connect = connect or _real_connect
    for family, address in PROBES:
        try:
            sock = socket.socket(family, socket.SOCK_DGRAM)
        except OSError:
            continue                    # the family does not exist here: no route
        try:
            connect(sock, address)
        except OSError as exc:
            if exc.errno in (errno.ENETUNREACH, errno.EHOSTUNREACH, errno.EADDRNOTAVAIL):
                continue
            return None, f"could not tell: {address[0]} answered {exc!r}"
        else:
            return False, f"the kernel has a route to {address[0]}"
        finally:
            sock.close()
    return True, "no route to any non-loopback address, in either family"


def report_line(state=None):
    confined, reason = state or confinement()
    if confined:
        return f"network: CONFINED ({reason}); processes a test starts cannot reach a network"
    if confined is False:
        return (f"network: NOT CONFINED ({reason}). The test process refuses non-loopback "
                "connects; processes a test starts are NOT covered. Run through scripts/nmas-test.")
    return f"network: UNKNOWN ({reason}). Treat as not confined."
