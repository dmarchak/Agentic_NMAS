"""Parser for Cisco IOS 15.x — the vIOS-L2 switches in the reference lab.

Differs from IOS-XE in VLAN/switchport handling, the absence of NETCONF and
telemetry, and its running-config defaults.
"""

import re

from modules.nsot.parsers.base import BaseParser


class CiscoIosParser(BaseParser):
    platform = "cisco_ios"

    def _build_handlers(self):
        handlers = super()._build_handlers()
        # Prepended so they win over the base patterns.
        return [
            (re.compile(r"^vtp\s+(.*)$"),            self._h_vtp_generic),
            (re.compile(r"^snmp ifmib\s+(.*)$"),     self._h_snmp_ifmib),
            (re.compile(r"^netconf-yang\s*$"),       self._h_netconf_yang),
        ] + handlers

    def _h_vtp_generic(self, block, out, m):
        out.setdefault("vtp", []).append(block.stripped)

    def _h_snmp_ifmib(self, block, out, m):
        out["snmp"].setdefault("settings", []).append(block.stripped)

    def _h_netconf_yang(self, block, out, m):
        # Present on vIOS-L2 images but non-functional; still part of the config.
        # Keyed on the literal command: flags render back verbatim.
        out["flags"]["netconf-yang"] = True

    def _interface_child(self, entry, text: str, nested: list = None):
        """L2 switchport handling is richer here than on IOS-XE."""
        trunk = re.match(r"^switchport trunk allowed vlan\s+(.+)$", text)
        if trunk:
            entry.setdefault("switchport_trunk_vlans", []).append(trunk.group(1).strip())
            return True
        mode = re.match(r"^switchport mode\s+(\S+)$", text)
        if mode:
            entry["switchport_mode"] = mode.group(1)
            return True
        access = re.match(r"^switchport access vlan\s+(\d+)$", text)
        if access:
            entry["switchport_access_vlan"] = access.group(1)
            return True
        encap = re.match(r"^switchport trunk encapsulation\s+(\S+)$", text)
        if encap:
            entry["switchport_trunk_encapsulation"] = encap.group(1)
            return True
        return super()._interface_child(entry, text, nested)
