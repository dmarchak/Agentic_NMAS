"""configure.py

Network device configuration generator.

Generates Cisco IOS configuration commands for the supported feature types.
(The Jenkins verification scripts, the pipeline XML and the per-job metadata
the pipeline callback read were removed with Jenkins in P.4.)
"""

import logging


logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Job storage
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# IOS configuration command generators
# ---------------------------------------------------------------------------

def generate_config_commands(config_type: str, params: dict) -> list[str]:
    """
    Return Cisco IOS config-mode lines for the given config_type.

    Supports two formats:
    • Legacy: config_type = "ospf"  → uses hand-crafted Python generator
    • KB-backed: config_type = "ospf/authentication" → fills CCIE KB template
    """
    generators = {
        "interface": _gen_interface_smart,
        "snmp":      _gen_snmp,
        "netflow":   _gen_netflow,
        "netconf":   _gen_netconf,
        "user":      _gen_user,
        "ospf":      _gen_ospf,
        "eigrp":     _gen_eigrp,
        "bgp":       _gen_bgp,
        "mpls":      _gen_mpls,
        "nat":       _gen_nat,
        "dhcp":      _gen_dhcp,
        "dhcpv6":    _gen_dhcpv6,
        "ipv6pd":    _gen_ipv6pd,
        "slaac":     _gen_slaac,
        "vtp":       _gen_vtp,
        "rsvpte":    _gen_rsvpte,
        "staticroute": _gen_staticroute,
        "loopback":  _gen_loopback,
    }
    fn = generators.get(config_type)
    if fn:
        return fn(params)

    # KB-backed type: "topic/subtopic" format
    if "/" in config_type:
        topic, subtopic = config_type.split("/", 1)
        return generate_from_kb(topic, subtopic, params)

    raise ValueError(f"Unknown config type: {config_type!r}")


import re as _re
_PARAM_PATTERN = _re.compile(r'\{([^}]+)\}')


def generate_from_kb(topic: str, subtopic: str, params: dict) -> list[str]:
    """
    Fill CCIE KB command templates with user-supplied parameters.

    Parameters map field IDs (from get_fields()) to string values.
    Command lines with any unfilled placeholder are silently skipped so
    optional commands are omitted when the user leaves a field blank.
    """
    from modules.ccie_kb import get_commands_for

    cmds = get_commands_for(topic, subtopic)
    if not cmds:
        raise ValueError(f"No KB commands found for {topic}/{subtopic}")

    # Build normalised lookup: both "a_b_c_d" and "a.b.c.d" map to the value
    lookup: dict[str, str] = {}
    for k, v in params.items():
        if v is None or str(v).strip() == "":
            continue
        norm = k.lower().replace(".", "_").replace("-", "_")
        lookup[norm] = str(v)
        lookup[k.lower()] = str(v)

    result: list[str] = []
    for cmd in cmds:
        filled = cmd
        for m in _PARAM_PATTERN.finditer(cmd):
            raw  = m.group(1).strip()
            norm = raw.lower().replace(".", "_").replace("-", "_").replace("|", "_or_")
            val  = lookup.get(norm) or lookup.get(raw.lower())
            if val:
                filled = filled.replace(m.group(0), val)
        # Skip if any placeholder remains unfilled
        if _PARAM_PATTERN.search(filled):
            continue
        result.append(filled)
    return result


def _gen_interface_smart(p: dict) -> list[str]:
    """Route to multi-interface generator if params contain an 'interfaces' list."""
    if isinstance(p.get("interfaces"), list):
        cmds: list[str] = []
        for intf_params in p["interfaces"]:
            if intf_params.get("interface"):
                cmds.extend(_gen_interface(intf_params))
        return cmds
    return _gen_interface(p)


def _gen_interface(p: dict) -> list[str]:
    intf = p.get("interface", "")
    cmds = [f"interface {intf}"]
    if p.get("description"):
        cmds.append(f" description {p['description']}")
    if p.get("ip") and p.get("mask"):
        cmds.append(f" ip address {p['ip']} {p['mask']}")
    # Legacy key names from older callers
    if p.get("ip_address") and p.get("subnet_mask"):
        cmds.append(f" ip address {p['ip_address']} {p['subnet_mask']}")
    # IPv6
    ipv6_mode = p.get("ipv6_mode", "")
    ipv6_addr = p.get("ipv6_address", "")
    if ipv6_mode == "enable":
        cmds.append(" ipv6 enable")
    elif ipv6_mode == "autoconfig":
        cmds.append(" ipv6 enable")
        cmds.append(" ipv6 address autoconfig")
    elif ipv6_mode == "dhcp":
        cmds.append(" ipv6 enable")
        cmds.append(" ipv6 address dhcp")
    elif ipv6_addr:
        cmds.append(" ipv6 enable")
        cmds.append(f" ipv6 address {ipv6_addr}")
    if p.get("speed") and p["speed"] != "auto":
        cmds.append(f" speed {p['speed']}")
    if p.get("duplex") and p["duplex"] != "auto":
        cmds.append(f" duplex {p['duplex']}")
    if p.get("mtu"):
        cmds.append(f" mtu {p['mtu']}")
    cmds.append(" shutdown" if p.get("admin_state") == "down" else " no shutdown")
    return cmds


def _gen_snmp(p: dict) -> list[str]:
    cmds      = []
    community = p.get("community", "")
    access    = p.get("access", "RO").upper()
    version   = p.get("version", "v2c")
    # IOS expects "2c" / "3", not "v2c" / "v3"
    ios_ver   = version.lstrip("v")   # "v2c"→"2c", "v3"→"3", "2c"→"2c"

    if ios_ver == "2c" and community:
        cmds.append(f"snmp-server community {community} {access}")
    if p.get("contact"):
        cmds.append(f"snmp-server contact {p['contact']}")
    if p.get("location"):
        cmds.append(f"snmp-server location {p['location']}")
    if p.get("trap_host"):
        trap_port = str(p.get("trap_port", "1162")).strip() or "1162"
        cmds.append(f"snmp-server host {p['trap_host']} traps version {ios_ver} {community} udp-port {trap_port}")
        cmds.append("snmp-server enable traps")
    if ios_ver == "3":
        user       = p.get("username",   p.get("v3_username", ""))
        auth_proto = p.get("auth_proto",  p.get("v3_auth_protocol", "sha")).lower()
        auth_pass  = p.get("auth_pass",   p.get("v3_auth_password", ""))
        priv_proto = p.get("priv_proto",  p.get("v3_priv_protocol", "aes")).lower()
        priv_pass  = p.get("priv_pass",   p.get("v3_priv_password", ""))
        if user and auth_pass:
            cmds.append("snmp-server group v3group v3 priv")
            if priv_pass:
                cmds.append(f"snmp-server user {user} v3group v3 auth {auth_proto} {auth_pass} priv {priv_proto} {priv_pass}")
            else:
                cmds.append(f"snmp-server user {user} v3group v3 auth {auth_proto} {auth_pass}")
    return cmds


def _gen_netflow(p: dict) -> list[str]:
    collector_ip   = p.get("collector_ip", "")
    collector_port = p.get("collector_port", "9996")
    source_intf    = p.get("source_interface", "")
    cmds = [
        f"ip flow-export destination {collector_ip} {collector_port}",
        "ip flow-export version 9",
    ]
    if source_intf:
        cmds.append(f"ip flow-export source {source_intf}")
    if p.get("active_timeout"):
        cmds.append(f"ip flow-cache timeout active {p['active_timeout']}")
    if p.get("inactive_timeout"):
        cmds.append(f"ip flow-cache timeout inactive {p['inactive_timeout']}")
    if source_intf:
        cmds += [f"interface {source_intf}", " ip flow ingress", " ip flow egress"]
    return cmds


def _gen_netconf(p: dict) -> list[str]:
    if p.get("enable", True):
        cmds = ["netconf-yang", "ip ssh version 2"]
        port = str(p.get("port", "830"))
        if port and port != "830":
            cmds.insert(1, f"netconf-yang ssh port {port}")
        return cmds
    return ["no netconf-yang"]


def _gen_user(p: dict) -> list[str]:
    username = p.get("username", "")
    password = p.get("password", "")
    priv     = p.get("privilege", "1")
    pwd_type = p.get("password_type", "secret")
    return [f"username {username} privilege {priv} {pwd_type} {password}"]


def _gen_ospf(p: dict) -> list[str]:
    pid  = p.get("process_id", "1")
    cmds = [f"router ospf {pid}"]
    if p.get("router_id"):
        cmds.append(f" router-id {p['router_id']}")
    for net in p.get("networks", []):
        if net.get("network") and net.get("wildcard") is not None:
            cmds.append(f" network {net['network']} {net['wildcard']} area {net.get('area', '0')}")
    for intf in p.get("passive_interfaces", []):
        if intf:
            cmds.append(f" passive-interface {intf}")
    return cmds


def _gen_eigrp(p: dict) -> list[str]:
    asn  = p.get("as_number", "1")
    cmds = [f"router eigrp {asn}"]
    if p.get("router_id"):
        cmds.append(f" eigrp router-id {p['router_id']}")
    for net in p.get("networks", []):
        if net.get("network"):
            wc = net.get("wildcard", "")
            cmds.append(f" network {net['network']}" + (f" {wc}" if wc else ""))
    for intf in p.get("passive_interfaces", []):
        if intf:
            cmds.append(f" passive-interface {intf}")
    cmds.append(" no auto-summary")
    return cmds


def _gen_bgp(p: dict) -> list[str]:
    asn  = p.get("local_as", "65000")
    cmds = [f"router bgp {asn}"]
    if p.get("router_id"):
        cmds.append(f" bgp router-id {p['router_id']}")
    for nbr in p.get("neighbors", []):
        if nbr.get("ip") and nbr.get("remote_as"):
            cmds.append(f" neighbor {nbr['ip']} remote-as {nbr['remote_as']}")
            if nbr.get("description"):
                cmds.append(f" neighbor {nbr['ip']} description {nbr['description']}")
    for net in p.get("networks", []):
        if net.get("network"):
            mask = net.get("mask", "")
            cmds.append(f" network {net['network']}" + (f" mask {mask}" if mask else ""))
    # IPv6 address-family
    if p.get("ipv6_af"):
        cmds.append(" !")
        cmds.append(" address-family ipv6 unicast")
        for nbr in p.get("ipv6_neighbors", []):
            if nbr.get("ip") and nbr.get("remote_as"):
                cmds.append(f"  neighbor {nbr['ip']} remote-as {nbr['remote_as']}")
                cmds.append(f"  neighbor {nbr['ip']} activate")
                if nbr.get("description"):
                    cmds.append(f"  neighbor {nbr['ip']} description {nbr['description']}")
        for prefix in p.get("ipv6_networks", []):
            if prefix:
                cmds.append(f"  network {prefix}")
        cmds.append(" exit-address-family")
    return cmds


def _gen_mpls(p: dict) -> list[str]:
    cmds = ["mpls ldp router-id Loopback0 force"]
    for intf in p.get("interfaces", []):
        if intf:
            cmds += [f"interface {intf}", " mpls ip"]
            if p.get("mtu"):
                cmds.append(f" mpls mtu {p['mtu']}")
    return cmds


def _gen_nat(p: dict) -> list[str]:
    nat_type     = p.get("type", p.get("nat_type", "overload"))
    inside_intf  = p.get("inside_interface", "")
    outside_intf = p.get("outside_interface", "")
    cmds = []

    if nat_type == "nat64":
        # NAT64 — stateful IPv6-to-IPv4 translation
        if inside_intf:
            cmds += [f"interface {inside_intf}", " nat64 enable"]
        if outside_intf:
            cmds += [f"interface {outside_intf}", " nat64 enable"]
        acl    = p.get("nat64_acl", "")
        start  = p.get("nat64_pool_start", "")
        end    = p.get("nat64_pool_end", "")
        prefix = p.get("nat64_pool_prefix", "24")
        if start and end:
            cmds.append(f"nat64 v4 pool NAT64_POOL {start} {end}")
        if acl:
            cmds.append(f"nat64 v6v4 list {acl} pool NAT64_POOL")
        return cmds

    if inside_intf:
        cmds += [f"interface {inside_intf}", " ip nat inside"]
    if outside_intf:
        cmds += [f"interface {outside_intf}", " ip nat outside"]

    if nat_type == "static":
        for mapping in p.get("static_mappings", []):
            local_ip  = mapping.get("local_ip", "")
            global_ip = mapping.get("global_ip", "")
            proto     = mapping.get("protocol", "").lower()
            port      = mapping.get("port", "")
            if not (local_ip and global_ip):
                continue
            if proto in ("tcp", "udp") and port:
                cmds.append(f"ip nat inside source static {proto} {local_ip} {port} {global_ip} {port}")
            else:
                cmds.append(f"ip nat inside source static {local_ip} {global_ip}")
        # Legacy single-mapping keys
        if not p.get("static_mappings"):
            local_ip  = p.get("inside_local", "")
            global_ip = p.get("inside_global", "")
            if local_ip and global_ip:
                cmds.append(f"ip nat inside source static {local_ip} {global_ip}")
    else:
        acl  = p.get("acl", "1")
        pool = p.get("pool_name", "")
        if nat_type == "overload" or not pool:
            cmds.append(f"ip nat inside source list {acl} interface {outside_intf} overload")
        else:
            start = p.get("pool_start", "")
            end   = p.get("pool_end", "")
            mask  = p.get("pool_netmask", "255.255.255.0")
            if start and end:
                cmds.append(f"ip nat pool {pool} {start} {end} netmask {mask}")
            cmds.append(f"ip nat inside source list {acl} pool {pool}")
    return cmds


def _gen_dhcp(p: dict) -> list[str]:
    pool    = p.get("pool_name", "DHCP_POOL")
    network = p.get("network", "")
    mask    = p.get("mask", "")
    cmds    = []
    # Excluded addresses before the pool declaration
    for excl in p.get("excluded", []):
        start = excl.get("start", "")
        end   = excl.get("end", "").strip()
        if start:
            cmds.append(f"ip dhcp excluded-address {start}" + (f" {end}" if end else ""))
    if not (network and mask):
        return cmds
    cmds.append(f"ip dhcp pool {pool}")
    cmds.append(f" network {network} {mask}")
    if p.get("gateway"):
        cmds.append(f" default-router {p['gateway']}")
    if p.get("dns"):
        cmds.append(f" dns-server {p['dns']}")
    if p.get("domain"):
        cmds.append(f" domain-name {p['domain']}")
    days  = str(p.get("lease_days", "")).strip()
    hours = str(p.get("lease_hours", "")).strip()
    if days or hours:
        cmds.append(f" lease {days or '1'} {hours or '0'}")
    return cmds


def _gen_dhcpv6(p: dict) -> list[str]:
    pool      = p.get("pool_name", "DHCPv6_POOL")
    mode      = p.get("mode", "stateful")
    prefix    = p.get("prefix", "")
    preferred = p.get("preferred", "86400")
    valid     = p.get("valid", "172800")
    cmds      = [f"ipv6 dhcp pool {pool}"]
    if mode == "stateful" and prefix:
        cmds.append(f" address prefix {prefix} lifetime {valid} {preferred}")
    if p.get("dns"):
        for dns_srv in p["dns"].split():
            cmds.append(f" dns-server {dns_srv}")
    if p.get("domain"):
        cmds.append(f" domain-name {p['domain']}")
    for intf in p.get("interfaces", []):
        cmds += [f"interface {intf}", f" ipv6 dhcp server {pool}"]
        if mode == "stateful":
            cmds.append(" ipv6 nd managed-config-flag")
            cmds.append(" ipv6 nd other-config-flag")
        else:
            cmds.append(" ipv6 nd other-config-flag")
    return cmds


def _gen_ipv6pd(p: dict) -> list[str]:
    role     = p.get("role", "server")
    pool     = p.get("pool_name", "PD_POOL")
    cmds     = []
    if role == "server":
        global_pfx  = p.get("global_prefix", "")
        assign_len  = p.get("assign_len", "48")
        preferred   = p.get("preferred", "86400")
        valid       = p.get("valid", "172800")
        local_pool  = f"{pool}_LOCAL"
        if global_pfx:
            cmds.append(f"ipv6 local pool {local_pool} {global_pfx} {assign_len}")
        cmds.append(f"ipv6 dhcp pool {pool}")
        cmds.append(f" prefix-delegation pool {local_pool} lifetime {valid} {preferred}")
        if p.get("dns"):
            cmds.append(f" dns-server {p['dns']}")
        for intf in p.get("server_intfs", []):
            cmds += [f"interface {intf}", f" ipv6 dhcp server {pool}"]
    else:
        upstream = p.get("upstream_intf", "")
        hint_len = p.get("hint_len", "")
        hint     = f" hint ::{f'/{hint_len}' if hint_len else ''}" if hint_len else ""
        if upstream:
            cmds += [f"interface {upstream}",
                     f" ipv6 dhcp client pd {pool}{hint}"]
        downstream = p.get("downstream_intf", "")
        if downstream:
            cmds += [f"interface {downstream}",
                     f" ipv6 address {pool} ::1/64 eui-64"]
    return cmds


def _gen_slaac(p: dict) -> list[str]:
    intf       = p.get("interface", "")
    address    = p.get("address", "")
    ra_mode    = p.get("ra_mode", "slaac")
    ra_intv    = p.get("ra_interval", "")
    ra_life    = p.get("ra_lifetime", "")
    rdnss      = p.get("rdnss", "")
    dnssl      = p.get("dnssl", "")
    cmds       = [f"interface {intf}"]
    cmds.append(" ipv6 enable")
    if address:
        cmds.append(f" ipv6 address {address}")
    if ra_intv:
        cmds.append(f" ipv6 nd ra-interval {ra_intv}")
    if ra_life:
        cmds.append(f" ipv6 nd ra-lifetime {ra_life}")
    if ra_mode in ("stateful", "stateless"):
        cmds.append(" ipv6 nd other-config-flag")
    if ra_mode == "stateful":
        cmds.append(" ipv6 nd managed-config-flag")
    if rdnss:
        cmds.append(f" ipv6 nd dns-server {rdnss}")
    if dnssl:
        cmds.append(f" ipv6 nd dns-search-list {dnssl}")
    cmds.append(" no ipv6 nd suppress-ra")
    return cmds



def _gen_vtp(p: dict) -> list[str]:
    mode    = p.get("mode", "server")
    version = p.get("version", "2")
    domain  = p.get("domain", "")
    cmds    = []
    if domain:
        cmds.append(f"vtp domain {domain}")
    cmds.append(f"vtp version {version}")
    cmds.append(f"vtp mode {mode}")
    if p.get("password"):
        cmds.append(f"vtp password {p['password']}")
    if p.get("pruning") == "enable" and mode == "server":
        cmds.append("vtp pruning")
    # VLAN definitions (server or transparent)
    if mode in ("server", "transparent"):
        for vlan in p.get("vlans", []):
            vid  = str(vlan.get("id", "")).strip()
            name = vlan.get("name", "").strip()
            if vid:
                cmds.append(f"vlan {vid}")
                if name:
                    cmds.append(f" name {name}")
    # Trunk interfaces
    for trunk in p.get("trunks", []):
        intf  = trunk.get("interface", "")
        encap = trunk.get("encap", "dot1q")
        if intf:
            cmds += [f"interface {intf}"]
            if encap in ("dot1q", "isl"):
                cmds.append(f" switchport trunk encapsulation {encap}")
            cmds.append(" switchport mode trunk")
    return cmds


def _gen_rsvpte(p: dict) -> list[str]:
    cmds = []
    # Per-interface RSVP + MPLS TE
    for entry in p.get("rsvp_interfaces", []):
        intf = entry.get("interface", "")
        bw   = entry.get("bandwidth", "")
        flow = entry.get("max_flow", "")
        if not intf:
            continue
        cmds.append(f"interface {intf}")
        cmds.append(" mpls traffic-eng tunnels")
        rsvp_cmd = f" ip rsvp bandwidth {bw}" if bw else " ip rsvp bandwidth"
        if bw and flow:
            rsvp_cmd += f" {flow}"
        cmds.append(rsvp_cmd)
    # MPLS TE tunnel
    path_option = p.get("path_option", "")
    tunnel_num  = str(p.get("tunnel_num", "0")).strip()
    dest_ip     = p.get("dest_ip", "")
    if path_option and dest_ip:
        cmds.append(f"interface Tunnel{tunnel_num}")
        src_intf = p.get("src_intf", "")
        if src_intf:
            cmds.append(f" ip unnumbered {src_intf}")
        else:
            cmds.append(" ip unnumbered Loopback0")
        cmds.append(" tunnel mode mpls traffic-eng")
        cmds.append(f" tunnel destination {dest_ip}")
        bw = str(p.get("bandwidth", "")).strip()
        if bw:
            cmds.append(f" tunnel mpls traffic-eng bandwidth {bw}")
        priority = str(p.get("priority", "7")).strip()
        cmds.append(f" tunnel mpls traffic-eng priority {priority} {priority}")
        affinity = p.get("affinity", "")
        if affinity:
            cmds.append(f" tunnel mpls traffic-eng affinity {affinity}")
        if path_option == "dynamic":
            cmds.append(" tunnel mpls traffic-eng path-option 10 dynamic")
        elif path_option == "explicit":
            path_name = p.get("path_name", "EXPLICIT_PATH")
            # Build explicit-path definition first (insert before tunnel)
            path_cmds = [f"ip explicit-path name {path_name} enable"]
            for i, hop in enumerate(p.get("path_hops", []), 1):
                ip       = hop.get("ip", "")
                hop_type = hop.get("type", "strict")
                if ip:
                    path_cmds.append(f" next-address {'strict' if hop_type == 'strict' else 'loose'} {ip}")
            # Prepend path definition before the Tunnel interface block
            tunnel_idx = next((i for i, c in enumerate(cmds) if c.startswith("interface Tunnel")), len(cmds))
            for j, cmd in enumerate(path_cmds):
                cmds.insert(tunnel_idx + j, cmd)
            cmds.append(f" tunnel mpls traffic-eng path-option 10 explicit name {path_name}")
    # Routing protocol TE extension
    rt_proto = p.get("rt_proto", "")
    if rt_proto == "ospf":
        pid      = p.get("ospf_pid", "1")
        area     = p.get("ospf_area", "0")
        rid_intf = p.get("ospf_rid_intf", "") or "Loopback0"
        cmds += [
            f"router ospf {pid}",
            f" mpls traffic-eng router-id {rid_intf}",
            f" mpls traffic-eng area {area}",
        ]
    elif rt_proto == "isis":
        tag   = p.get("isis_tag", "")
        level = p.get("isis_level", "level-2-only")
        base  = f"router isis{' ' + tag if tag else ''}"
        cmds += [base, f" metric-style wide", f" mpls traffic-eng {level}",
                 f" mpls traffic-eng router-id Loopback0"]
    return cmds


def _gen_staticroute(p: dict) -> list[str]:
    cmds = []
    for route in p.get("routes", []):
        prefix = route.get("prefix", "").strip()
        mask   = route.get("mask", "").strip()
        if not prefix:
            continue
        nexthop = route.get("nexthop", "").strip()
        intf    = route.get("interface", "").strip()
        ad      = route.get("ad", "").strip()
        tag     = route.get("tag", "").strip()
        track   = route.get("track", "").strip()
        perm    = route.get("permanent", "").strip()
        desc    = route.get("desc", "").strip()
        # Detect IPv6 (colon in prefix or mask starts with /)
        is_v6 = ":" in prefix or (mask.startswith("/"))
        if is_v6:
            # IPv6: combine prefix/len, e.g. "2001:db8::/32" or separate "2001:db8::" + "/32"
            if "/" not in prefix and mask:
                pfx_len = mask.lstrip("/")
                dest    = f"{prefix}/{pfx_len}"
            else:
                dest = prefix
            cmd = f"ipv6 route {dest}"
            if intf:
                cmd += f" {intf}"
            if nexthop:
                cmd += f" {nexthop}"
            if ad:
                cmd += f" {ad}"
            if tag:
                cmd += f" tag {tag}"
            if track:
                cmd += f" track {track}"
        else:
            cmd = f"ip route {prefix} {mask}"
            if intf:
                cmd += f" {intf}"
            if nexthop:
                cmd += f" {nexthop}"
            if ad:
                cmd += f" {ad}"
            if tag:
                cmd += f" tag {tag}"
            if track:
                cmd += f" track {track}"
            if perm == "permanent":
                cmd += " permanent"
        cmds.append(cmd)
        if desc:
            # IOS doesn't attach descriptions to static routes; emit a remark comment
            cmds.append(f"! route remark: {desc}")
    return cmds


def _gen_loopback(p: dict) -> list[str]:
    cmds = []
    for lb in p.get("loopbacks", []):
        num  = str(lb.get("number", "0")).strip()
        ipv4 = lb.get("ipv4", "").strip()
        mask = lb.get("mask", "").strip()
        ipv6 = lb.get("ipv6", "").strip()
        desc = lb.get("desc", "").strip()
        cmds.append(f"interface Loopback{num}")
        if desc:
            cmds.append(f" description {desc}")
        if ipv4 and mask:
            cmds.append(f" ip address {ipv4} {mask}")
        if ipv6:
            cmds.append(" ipv6 enable")
            cmds.append(f" ipv6 address {ipv6}")
        cmds.append(" no shutdown")
    return cmds


# ---------------------------------------------------------------------------
# Jenkins declarative pipeline XML
# ---------------------------------------------------------------------------

