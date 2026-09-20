"""Parser for Cisco IOS-XE 17.x — the C8000v routers in the reference lab.

Adds what IOS 15.x does not have: ``vrf definition`` with address families,
NETCONF/RESTCONF, model-driven telemetry subscriptions, IP SLA, crypto PKI
trustpoints, and platform/licence lines.
"""

import re

from modules.nsot.parsers.base import BaseParser


class CiscoIosXeParser(BaseParser):
    platform = "cisco_iosxe"

    def _build_handlers(self):
        handlers = super()._build_handlers()
        return [
            (re.compile(r"^vrf definition\s+(\S+)"),          self._h_vrf),
            (re.compile(r"^telemetry ietf subscription\s+(\d+)"), self._h_telemetry),
            (re.compile(r"^netconf-yang\s*$"),                self._h_mgmt_flag),
            (re.compile(r"^restconf\s*$"),                    self._h_mgmt_flag),
            (re.compile(r"^netconf\s+(.*)$"),                 self._h_netconf_setting),
            (re.compile(r"^ip sla\s+(\d+)\s*$"),              self._h_ip_sla),
            (re.compile(r"^ip sla schedule\s+(.*)$"),         self._h_ip_sla_schedule),
            (re.compile(r"^crypto pki trustpoint\s+(\S+)"),   self._h_trustpoint),
            (re.compile(r"^platform\s+(.*)$"),                self._h_platform),
            (re.compile(r"^license\s+(.*)$"),                 self._h_license),
        ] + handlers

    def _h_vrf(self, block, out, m):
        entry = {"name": m.group(1), "address_families": [], "settings": []}
        current_af = None
        for child in block.children:
            text = child.strip()
            af = re.match(r"^address-family\s+(\S+)", text)
            if af:
                current_af = {"family": af.group(1), "settings": []}
                entry["address_families"].append(current_af)
                continue
            if text.startswith("exit-address-family"):
                # Recorded, not dropped: IOS-XE emits it as part of the block
                # and a config without it does not parse on the device.
                if current_af is not None:
                    current_af["terminator"] = text
                current_af = None
                continue
            if text == "!":
                continue
            if current_af is not None:
                current_af["settings"].append(text)
            else:
                entry["settings"].append(text)
        out.setdefault("vrfs", []).append(entry)

    def _h_telemetry(self, block, out, m):
        out.setdefault("telemetry", []).append({
            "subscription": m.group(1),
            "settings": [c.strip() for c in block.children],
        })

    def _h_mgmt_flag(self, block, out, m):
        # Keyed on the literal command so it renders back verbatim.
        out["flags"][block.stripped] = True

    def _h_netconf_setting(self, block, out, m):
        out.setdefault("netconf_settings", []).append(m.group(1).strip())

    def _h_ip_sla(self, block, out, m):
        out.setdefault("ip_sla", []).append({
            "id": m.group(1),
            # Probe sub-commands are ordered: `frequency` nests under the probe.
            "settings": [c.rstrip() for c in block.children],
        })

    def _h_ip_sla_schedule(self, block, out, m):
        out.setdefault("ip_sla_schedules", []).append(m.group(1).strip())

    def _h_trustpoint(self, block, out, m):
        out.setdefault("pki_trustpoints", []).append({
            "name": m.group(1),
            "settings": [c.strip() for c in block.children],
        })

    def _h_platform(self, block, out, m):
        out.setdefault("platform_settings", []).append(block.stripped)

    def _h_license(self, block, out, m):
        out.setdefault("license_settings", []).append(block.stripped)

    def _interface_child(self, entry, text: str, nested: list = None):
        if re.match(r"^no mop (enabled|sysid)\s*$", text):
            entry.setdefault("mop", []).append(text)
            return True
        return super()._interface_child(entry, text, nested)
