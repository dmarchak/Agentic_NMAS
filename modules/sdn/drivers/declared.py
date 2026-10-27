"""Controller drivers declared but not built (PHASE8_PLAN 17.1, "Integrated, after the slice").

A declaration only: each names its kind, label and status, declares no capability (Mercury
offers only what a driver declares, and these can do nothing yet), and says what it is meant
to offer once built (`planned`, informational). Every call refuses, naming that the driver is
not built (base.py, `ControllerDriver._refusal`).
- **later:** ONOS, the second driver, reads and writes.
- **later, read-first:** OpenDaylight (its OpenFlow plugin's reads), and the fabric managers
  (ACI, NSX, Apstra, CloudVision), whose state is not OpenFlow flow tables: their reads are
  their topology, until a design says what else.
- **unmaintained:** Floodlight, whose project is no longer maintained; nothing planned.
"""

from modules.sdn.drivers.base import CAPABILITIES, READS, ControllerDriver


class _Declared(ControllerDriver):
    capabilities = frozenset()


class OnosDriver(_Declared):
    kind, label, status = "onos", "ONOS", "later"
    planned = CAPABILITIES


class OpenDaylightDriver(_Declared):
    kind, label, status, read_first = "opendaylight", "OpenDaylight", "later", True
    planned = READS


class AciDriver(_Declared):
    kind, label, status, read_first = "aci", "Cisco ACI", "later", True
    planned = frozenset({"read_topology"})


class NsxDriver(_Declared):
    kind, label, status, read_first = "nsx", "VMware NSX", "later", True
    planned = frozenset({"read_topology"})


class ApstraDriver(_Declared):
    kind, label, status, read_first = "apstra", "Juniper Apstra", "later", True
    planned = frozenset({"read_topology"})


class CloudVisionDriver(_Declared):
    kind, label, status, read_first = "cloudvision", "Arista CloudVision", "later", True
    planned = frozenset({"read_topology"})


class FloodlightDriver(_Declared):
    kind, label, status = "floodlight", "Floodlight", "unmaintained"


DECLARED = (OnosDriver, OpenDaylightDriver, AciDriver, NsxDriver, ApstraDriver,
            CloudVisionDriver, FloodlightDriver)
