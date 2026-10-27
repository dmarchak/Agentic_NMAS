"""The controller drivers' registry, by kind (PHASE8_PLAN 17.2).

`DRIVERS` maps each kind to its driver class: `ryu` is built; `onos` is later; `opendaylight`,
`aci`, `nsx`, `apstra` and `cloudvision` are later and read-first; `floodlight` is
unmaintained. `make(kind, connection)` answers a driver for a connection, or a refusal naming
the kinds there are; `declarations()` is every driver's declaration, for a page to draw.
"""

from modules.sdn.drivers.base import Connection, ControllerDriver
from modules.sdn.drivers.declared import DECLARED
from modules.sdn.drivers.ryu import RyuDriver

DRIVERS = {cls.kind: cls for cls in (RyuDriver,) + DECLARED}


def make(kind: str, connection: Connection, **kwargs) -> dict:
    """`{"ok": True, "driver": ControllerDriver}` for *kind*, or `{"ok": False, "error"}`."""
    cls = DRIVERS.get(kind)
    if cls is None:
        return {"ok": False, "error": f"there is no controller driver of kind {kind!r}; the "
                                      f"kinds are {', '.join(sorted(DRIVERS))}"}
    return {"ok": True, "error": "", "driver": cls(connection, **kwargs)}


def declarations() -> list:
    """Every driver's declaration, built first, then by label."""
    return [cls.declaration() for cls in
            sorted(DRIVERS.values(), key=lambda c: (c.status != "built", c.label))]


__all__ = ["DRIVERS", "make", "declarations", "ControllerDriver", "Connection"]
