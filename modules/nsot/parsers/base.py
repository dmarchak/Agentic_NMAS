"""nsot/parsers/base.py

Shared machinery for turning a running config into structured ``host_vars``.

An IOS config is a list of top-level lines, each optionally followed by an
indented body. The parser splits on that structure, dispatches each block to a
handler, and puts anything with no handler into ``unmodeled`` **verbatim, with
its section context**. Nothing is dropped — that is what makes the coverage
number honest rather than flattering.

Secrets are stored as **hash strings**, never plaintext. ``enable secret 9 $9$…``
carries a per-hash salt and cannot be regenerated, so a template must emit the
original string verbatim or the round trip fails permanently on that line.
"""

import logging
import re

from modules.nsot import ifnames

log = logging.getLogger(__name__)


class ConfigBlock:
    """A top-level config line plus its indented body."""

    __slots__ = ("line", "children", "lineno")

    def __init__(self, line: str, lineno: int = 0):
        self.line = line
        self.children: list = []
        self.lineno = lineno

    @property
    def stripped(self) -> str:
        return self.line.strip()

    def all_lines(self) -> list:
        return [self.line] + self.children

    def __repr__(self):
        return f"<ConfigBlock {self.stripped!r} +{len(self.children)}>"


def split_blocks(config: str) -> list:
    """Split a config into top-level blocks, preserving indented bodies."""
    blocks = []
    current = None
    for lineno, raw in enumerate((config or "").splitlines(), start=1):
        if not raw.strip():
            continue
        if raw.startswith((" ", "\t")):
            if current is not None:
                current.children.append(raw)
            continue
        if current is not None:
            blocks.append(current)
        current = ConfigBlock(raw, lineno)
    if current is not None:
        blocks.append(current)
    return blocks


class BaseParser:
    """Base config parser. Platform subclasses add or override handlers.

    A handler is ``_handle_<name>(block, out) -> bool``. Returning True claims
    the block; returning False (or not matching) leaves it for ``unmodeled``.
    """

    #: Settings platform slug this parser serves.
    platform = "cisco_ios"

    #: Lines that are IOS defaults or noise, claimed but not modelled. They are
    #: excluded from the coverage denominator because a template is not expected
    #: to reproduce them and their absence is not a modelling gap.
    IGNORED_PREFIXES = (
        "!",
        "end",
        "Building configuration",
        "Current configuration",
        "version ",
        "Last configuration change",
    )

    def __init__(self):
        self.handlers = self._build_handlers()

    # ── handler registry ────────────────────────────────────────────────────

    def _build_handlers(self) -> list:
        """``(matcher, method)`` pairs, tried in order."""
        return [
            (re.compile(r"^hostname\s+(\S+)"),               self._h_hostname),
            (re.compile(r"^ip domain[- ]name\s+(\S+)"),      self._h_domain),
            (re.compile(r"^interface\s+(\S+)"),              self._h_interface),
            (re.compile(r"^vlan\s+(\d[\d,\-]*)\s*$"),        self._h_vlan),
            (re.compile(r"^router ospf\s+(\d+)"),            self._h_ospf),
            (re.compile(r"^router rip\s*$"),                 self._h_rip),
            (re.compile(r"^router bgp\s+(\d+)"),             self._h_bgp),
            (re.compile(r"^ipv6 router ospf\s+(\d+)"),       self._h_ospfv3),
            (re.compile(r"^ipv6 router rip\s+(\S+)"),        self._h_ripng),
            (re.compile(r"^username\s+(\S+)\s+(.*)$"),       self._h_username),
            (re.compile(r"^enable secret\s+(.*)$"),          self._h_enable_secret),
            (re.compile(r"^enable password\s+(.*)$"),        self._h_enable_secret),
            (re.compile(r"^snmp-server\s+(.*)$"),            self._h_snmp),
            (re.compile(r"^logging\s+(.*)$"),                self._h_logging),
            (re.compile(r"^ntp server\s+(.*)$"),             self._h_ntp),
            (re.compile(r"^ip route\s+(.*)$"),               self._h_static_route),
            (re.compile(r"^ipv6 route\s+(.*)$"),             self._h_static_route_v6),
            (re.compile(r"^ip access-list\s+(\S+)\s+(\S+)"), self._h_acl),
            (re.compile(r"^line\s+(.*)$"),                   self._h_line),
            (re.compile(r"^track\s+(\d+)\s+(.*)$"),          self._h_track),
            (re.compile(r"^spanning-tree\s+(.*)$"),          self._h_spanning_tree),
            (re.compile(r"^ipv6 unicast-routing\s*$"),       self._h_flag),
            (re.compile(r"^ip cef\s*$"),                     self._h_flag),
            (re.compile(r"^ipv6 cef\s*$"),                   self._h_flag),
            (re.compile(r"^lldp run\s*$"),                   self._h_flag),
            (re.compile(r"^cdp run\s*$"),                    self._h_flag),
            (re.compile(r"^no aaa new-model\s*$"),           self._h_flag),
            (re.compile(r"^aaa new-model\s*$"),              self._h_flag),
            (re.compile(r"^service\s+(.*)$"),                self._h_service),
            (re.compile(r"^no service\s+(.*)$"),             self._h_service),
            (re.compile(r"^vtp mode\s+(\S+)"),               self._h_vtp),
            (re.compile(r"^fhrp version vrrp\s+(\S+)"),      self._h_fhrp),
            # Present on both reference platforms, so modelled per the
            # 2-or-more-devices rule rather than left to `unmodeled`.
            (re.compile(r"^ip ssh\s+(.*)$"),                 self._h_ssh),
            (re.compile(r"^(no )?ip http\s+(.*)$"),          self._h_http),
            (re.compile(r"^ip forward-protocol\s+(.*)$"),    self._h_forward_protocol),
            (re.compile(r"^control-plane\s*$"),              self._h_control_plane),
            (re.compile(r"^mgcp\s+(.*)$"),                   self._h_mgcp),
            (re.compile(r"^(no )?logging console\s*$"),      self._h_logging_console),
        ]

    # ── entry point ─────────────────────────────────────────────────────────

    def parse(self, config: str, pre_stripped: bool = False) -> dict:
        """Parse *config* into host_vars. Never raises.

        The config is first passed through
        :func:`modules.nsot.normalize.strip_for_roundtrip` unless the caller has
        already done so. Unrenderable content — certificate bodies, banners,
        boot markers, the show-version preamble — must never reach ``unmodeled``,
        because it would count against modelled coverage for a reason that has
        nothing to do with modelling.
        """
        if not pre_stripped:
            from modules.nsot.normalize import strip_for_roundtrip
            config = "\n".join(strip_for_roundtrip(config))
        out = {
            "hostname": "", "platform": self.platform,
            "interfaces": [], "vlans": [], "users": [],
            "routing": {}, "static_routes": [], "acls": [],
            "snmp": {}, "logging": {}, "ntp_servers": [], "lines": [],
            "tracks": [], "services": [], "flags": {}, "spanning_tree": {},
            "secrets": {},          # ref name -> hash string (moved to the store)
            "unmodeled": [],
        }

        for block in split_blocks(config):
            stripped = block.stripped
            if any(stripped.startswith(p) for p in self.IGNORED_PREFIXES):
                continue

            claimed = False
            for matcher, handler in self.handlers:
                match = matcher.match(stripped)
                if match:
                    try:
                        claimed = handler(block, out, match) is not False
                    except Exception as exc:       # noqa: BLE001
                        log.debug("parser: %s failed on %r: %s",
                                  handler.__name__, stripped[:60], exc)
                        claimed = False
                    break

            if not claimed:
                out["unmodeled"].append({
                    "line": block.line,
                    "children": list(block.children),
                    "lineno": block.lineno,
                })

        out = self._apply_schema_defaults(out)
        return self._redact_secret_echoes(out)

    #: Optional top-level keys and their empty values. Emitted even when absent
    #: so host_vars has a stable schema: templates render with StrictUndefined,
    #: which catches a typo'd variable name but also means every key a template
    #: may reference has to exist.
    SCHEMA_DEFAULTS = {
        "domain_name": "", "vtp_mode": "", "fhrp_version_vrrp": "",
        "enable_secret_ref": "", "enable_secret_keyword": "",
        "vtp": [], "platform_settings": [], "license_settings": [],
        "vrfs": [], "pki_trustpoints": [], "ip_sla": [], "ip_sla_schedules": [],
        "netconf_settings": [], "telemetry": [], "ssh": [], "http": {},
        "forward_protocol": [], "mgcp": [], "control_plane": {"settings": []},
    }

    #: The same, per interface.
    INTERFACE_DEFAULTS = {
        "description": "", "ipv4": "", "vrf": "", "mtu": "", "negotiation": "",
        "encapsulation": "", "channel_group": "",
        "switchport_mode": "", "switchport_access_vlan": "",
        "switchport_trunk_encapsulation": "",
        "no_switchport": False, "shutdown": False, "no_shutdown": False,
        "ipv6_enable": False, "no_ip_address": False, "vrrp_groups": [],
        "ipv6": [], "switchport": [], "switchport_trunk_vlans": [],
        "helper_addresses": [], "dhcpv6_relay": [], "ipv6_nd": [],
        "ospf": [], "ospfv3": [], "ripng": [], "vrrp": [], "mop": [],
    }

    #: Marker for a secret substituted into an otherwise opaque string. The
    #: template resolves it through ``secret()``.
    SECRET_MARKER = "__secret__:"

    def _redact_secret_echoes(self, out: dict) -> dict:
        """Replace secret values echoed in other lines with a reference.

        A community string appears twice in an IOS config: once in
        ``snmp-server community`` and again inside ``snmp-server host … public``.
        Capturing only the first leaves the value sitting in plaintext YAML.
        """
        secrets = out.get("secrets") or {}
        if not secrets:
            return out
        # Longest first, so a short value cannot partially mask a longer one.
        ordered = sorted(secrets.items(), key=lambda kv: len(kv[1]), reverse=True)

        def _redact(text: str) -> str:
            for ref, value in ordered:
                if value and value in text:
                    text = text.replace(value, f"{self.SECRET_MARKER}{ref}")
            return text

        for host in out.get("snmp", {}).get("hosts", []):
            host["options"] = _redact(host.get("options", ""))
        out["snmp"]["settings"] = [_redact(x) for x in out["snmp"].get("settings", [])]
        return out

    def _apply_schema_defaults(self, out: dict) -> dict:
        for key, default in self.SCHEMA_DEFAULTS.items():
            out.setdefault(key, default.copy() if hasattr(default, "copy") else default)
        for vlan in out["vlans"]:
            vlan.setdefault("name", "")
            vlan.setdefault("extra", [])
        for user in out["users"]:
            user.setdefault("secret_ref", "")
            user.setdefault("secret_kind", "")
        for entry in out["unmodeled"]:
            entry.setdefault("children", [])
        for iface in out["interfaces"]:
            for key, default in self.INTERFACE_DEFAULTS.items():
                iface.setdefault(key, default.copy() if hasattr(default, "copy") else default)
        out["routing"].setdefault("ospf", [])
        out["routing"].setdefault("ospfv3", [])
        out["routing"].setdefault("ripng", [])
        out["routing"].setdefault("rip", None)
        out["routing"].setdefault("bgp", None)
        out["logging"].setdefault("settings", [])
        out["logging"].setdefault("hosts", [])
        out["snmp"].setdefault("communities", [])
        out["snmp"].setdefault("settings", [])
        out["snmp"].setdefault("hosts", [])
        return out

    # ── handlers ────────────────────────────────────────────────────────────

    def _h_hostname(self, block, out, m):
        out["hostname"] = m.group(1)

    def _h_domain(self, block, out, m):
        out["domain_name"] = m.group(1)

    def _h_flag(self, block, out, m):
        """A boolean global, stored under its positive form.

        The key is the command without a leading ``no``, and the value says
        whether it is enabled — so ``no aaa new-model`` becomes
        ``{"aaa new-model": False}`` and renders back correctly. Keying on the
        literal line instead would render "no no aaa new-model".
        """
        line = block.stripped
        enabled = not line.startswith("no ")
        command = line[3:].strip() if not enabled else line
        out["flags"][command] = enabled

    def _h_service(self, block, out, m):
        out["services"].append(block.stripped)

    def _h_vtp(self, block, out, m):
        out["vtp_mode"] = m.group(1)

    def _h_fhrp(self, block, out, m):
        out["fhrp_version_vrrp"] = m.group(1)

    def _h_spanning_tree(self, block, out, m):
        out["spanning_tree"].setdefault("lines", []).append(block.stripped)

    def _h_track(self, block, out, m):
        out["tracks"].append({"id": int(m.group(1)),
                              "spec": ifnames.canonicalise_line(m.group(2))})

    def _h_vlan(self, block, out, m):
        entry = {"id": m.group(1).strip()}
        for child in block.children:
            name = re.match(r"\s+name\s+(.+)$", child)
            if name:
                entry["name"] = name.group(1).strip()
            else:
                entry.setdefault("extra", []).append(child.strip())
        out["vlans"].append(entry)

    def _h_username(self, block, out, m):
        name, rest = m.group(1), m.group(2).strip()
        entry = {"name": name}
        priv = re.search(r"privilege\s+(\d+)", rest)
        if priv:
            entry["privilege"] = int(priv.group(1))

        # The secret is a HASH (or a type-0 plaintext). Either way it is stored
        # verbatim and emitted verbatim: a type-5/8/9 hash carries a per-hash
        # salt and cannot be regenerated from plaintext.
        secret = re.search(r"\b(secret|password)\s+(\d+\s+\S+|\S+)\s*$", rest)
        if secret:
            ref = f"user_{name}_{secret.group(1)}"
            entry["secret_kind"] = secret.group(1)
            entry["secret_ref"] = ref
            out["secrets"][ref] = secret.group(2).strip()
        out["users"].append(entry)

    def _h_enable_secret(self, block, out, m):
        out["secrets"]["enable_secret"] = m.group(1).strip()
        out["enable_secret_ref"] = "enable_secret"
        out["enable_secret_keyword"] = block.stripped.split()[1]   # secret | password

    def _h_ssh(self, block, out, m):
        """``ip ssh …`` settings. Semi-structured: the key is modelled, the
        value is carried opaquely so a template can emit and an operator edit."""
        out.setdefault("ssh", []).append(m.group(1).strip())

    def _h_http(self, block, out, m):
        setting = m.group(2).strip()
        out.setdefault("http", {})[setting.replace("-", "_")] = not bool(m.group(1))

    def _h_forward_protocol(self, block, out, m):
        out.setdefault("forward_protocol", []).append(m.group(1).strip())

    def _h_control_plane(self, block, out, m):
        out["control_plane"] = {"settings": [c.strip() for c in block.children]}

    def _h_mgcp(self, block, out, m):
        out.setdefault("mgcp", []).append(block.stripped)

    def _h_logging_console(self, block, out, m):
        out["logging"]["console"] = not bool(m.group(1))

    def _h_snmp(self, block, out, m):
        rest = m.group(1).strip()
        community = re.match(r"community\s+(\S+)\s*(\S*)$", rest)
        if community:
            ref = f"snmp_community_{community.group(2).lower() or 'ro'}"
            out["secrets"][ref] = community.group(1)
            out["snmp"].setdefault("communities", []).append(
                {"ref": ref, "access": community.group(2) or "RO"})
            return
        host = re.match(r"host\s+(\S+)\s+(.*)$", rest)
        if host:
            out["snmp"].setdefault("hosts", []).append(
                {"address": host.group(1), "options": host.group(2).strip()})
            return
        out["snmp"].setdefault("settings", []).append(
            ifnames.canonicalise_line(rest))

    def _h_logging(self, block, out, m):
        rest = ifnames.canonicalise_line(m.group(1).strip())
        host = re.match(r"host\s+(\S+)$", rest)
        if host:
            out["logging"].setdefault("hosts", []).append(host.group(1))
            return
        out["logging"].setdefault("settings", []).append(rest)

    def _h_ntp(self, block, out, m):
        out["ntp_servers"].append(m.group(1).strip())

    def _h_static_route(self, block, out, m):
        out["static_routes"].append({"family": "ipv4", "spec": m.group(1).strip()})

    def _h_static_route_v6(self, block, out, m):
        rest = m.group(1).strip()
        if rest.startswith("vrf ") or re.match(r"^[0-9A-Fa-f:]+", rest):
            out["static_routes"].append({"family": "ipv6", "spec": rest})
            return
        return False          # `ipv6 route` is also a prefix for other commands

    def _h_acl(self, block, out, m):
        out["acls"].append({
            "type": m.group(1), "name": m.group(2),
            # ACL entries are ORDER-SIGNIFICANT — kept as an ordered list.
            "entries": [c.strip() for c in block.children],
        })

    def _h_line(self, block, out, m):
        out["lines"].append({"spec": m.group(1).strip(),
                             "settings": [c.strip() for c in block.children]})

    # ── interfaces ──────────────────────────────────────────────────────────

    def _h_interface(self, block, out, m):
        entry = {"name": ifnames.canonical(m.group(1)), "unmodeled": []}

        # An interface body can itself nest: a `vrrp N address-family X` line is
        # followed by more deeply indented settings. Group by indentation first
        # so those settings reach the VRRP handler instead of being scattered
        # into `unmodeled` as orphaned lines.
        base_indent = min((len(c) - len(c.lstrip()) for c in block.children
                           if c.strip()), default=1)
        groups = []
        for child in block.children:
            if not child.strip():
                continue
            indent = len(child) - len(child.lstrip())
            text = ifnames.canonicalise_line(child.strip())
            if indent > base_indent and groups:
                groups[-1][1].append(text)
            else:
                groups.append((text, []))

        for text, nested in groups:
            if self._interface_child(entry, text, nested) is False:
                entry["unmodeled"].append(text)
                entry["unmodeled"].extend(nested)
        out["interfaces"].append(entry)

    def _interface_child(self, entry, text: str, nested: list = None):
        """Claim a line inside an interface block. Return False to leave it unmodeled.

        *nested* carries any more deeply indented settings under this line —
        VRRP address-family groups being the case that needs it.
        """
        nested = nested or []

        vrrp = re.match(r"^vrrp\s+(\d+)\s+address-family\s+(\S+)\s*$", text)
        if vrrp:
            # Settings are ordered within a group but the terminator is kept so
            # the block renders back exactly as IOS reports it.
            settings = [n for n in nested if n != "exit-vrrp"]
            entry.setdefault("vrrp_groups", []).append({
                "group": vrrp.group(1), "family": vrrp.group(2),
                "settings": settings,
                "terminator": "exit-vrrp" if "exit-vrrp" in nested else "",
            })
            return True

        if re.match(r"^no ip address\s*$", text):
            entry["no_ip_address"] = True
            return True

        patterns = (
            (r"^description\s+(.+)$",                    "description"),
            (r"^ip address\s+(.+)$",                     "ipv4"),
            (r"^ipv6 address\s+(.+)$",                   "ipv6"),
            (r"^ip helper-address\s+(\S+)",              "helper_addresses"),
            (r"^ipv6 dhcp relay destination\s+(\S+)",    "dhcpv6_relay"),
            (r"^vrf forwarding\s+(\S+)",                 "vrf"),
            (r"^ip vrf forwarding\s+(\S+)",              "vrf"),
            (r"^switchport\s+(.+)$",                     "switchport"),
            (r"^no switchport\s*$",                      "no_switchport"),
            (r"^shutdown\s*$",                           "shutdown"),
            (r"^no shutdown\s*$",                        "no_shutdown"),
            (r"^ip ospf\s+(.+)$",                        "ospf"),
            (r"^ipv6 ospf\s+(.+)$",                      "ospfv3"),
            (r"^ipv6 rip\s+(.+)$",                       "ripng"),
            (r"^ipv6 nd\s+(.+)$",                        "ipv6_nd"),
            (r"^ipv6 enable\s*$",                        "ipv6_enable"),
            (r"^vrrp\s+(.+)$",                           "vrrp"),
            (r"^negotiation\s+(\S+)",                    "negotiation"),
            (r"^mtu\s+(\d+)",                            "mtu"),
            (r"^channel-group\s+(.+)$",                  "channel_group"),
            (r"^encapsulation\s+(.+)$",                  "encapsulation"),
        )
        for pattern, key in patterns:
            match = re.match(pattern, text)
            if match:
                value = match.group(1) if match.groups() else True
                if key in ("helper_addresses", "ipv6", "switchport", "ipv6_nd",
                           "vrrp", "dhcpv6_relay", "ospf", "ospfv3", "ripng"):
                    entry.setdefault(key, []).append(value)
                else:
                    entry[key] = value
                return True
        return False

    # ── routing ─────────────────────────────────────────────────────────────

    def _routing_block(self, block, key: str, extra: dict = None) -> dict:
        proto = {"raw": [], **(extra or {})}
        for child in block.children:
            proto["raw"].append(ifnames.canonicalise_line(child.strip()))
        return proto

    def _h_ospf(self, block, out, m):
        entry = self._routing_block(block, "ospf", {"process": m.group(1)})
        entry.update(self._split_routing(entry.pop("raw"), network_key="network"))
        out["routing"].setdefault("ospf", []).append(entry)

    def _h_ospfv3(self, block, out, m):
        entry = self._routing_block(block, "ospfv3", {"process": m.group(1)})
        out["routing"].setdefault("ospfv3", []).append(entry)

    def _h_rip(self, block, out, m):
        entry = self._routing_block(block, "rip")
        entry.update(self._split_routing(entry.pop("raw"), network_key="network"))
        out["routing"]["rip"] = entry

    def _h_ripng(self, block, out, m):
        entry = self._routing_block(block, "ripng", {"name": m.group(1)})
        out["routing"].setdefault("ripng", []).append(entry)

    def _h_bgp(self, block, out, m):
        entry = self._routing_block(block, "bgp", {"asn": m.group(1)})
        entry.update(self._split_routing(entry.pop("raw"), network_key="network",
                                         neighbor_key="neighbor"))
        out["routing"]["bgp"] = entry

    @staticmethod
    def _split_routing(raw: list, network_key: str = "", neighbor_key: str = "") -> dict:
        """Separate order-insensitive statements from the rest.

        BGP neighbors and OSPF/RIP networks are order-insensitive; everything
        else in a routing block stays in document order.

        The caller pops ``raw`` rather than keeping it alongside the split
        lists. Keeping both would store document order that the template does
        not reproduce (it emits settings then networks), so a second extraction
        would yield different YAML and the fixed-point property would fail.
        """
        result = {"networks": [], "neighbors": [], "settings": []}
        for line in raw:
            if network_key and line.startswith(f"{network_key} "):
                result["networks"].append(line)
            elif neighbor_key and line.startswith(f"{neighbor_key} "):
                result["neighbors"].append(line)
            else:
                result["settings"].append(line)
        return result
