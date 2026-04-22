"""topology.py

Network topology discovery and graph construction.

Discovers the network topology by querying devices in parallel via SSH.
Builds a graph from CDP neighbor relationships (physical links), OSPF
adjacencies, BGP peer sessions, and DMVPN/mGRE tunnel interfaces (with
hub/spoke role detection).  Returns a unified node/edge structure consumed
by the browser's vis.js topology visualizer, including interface labels,
platform info, IP addresses, and protocol-specific metadata.
"""

import re
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)


def parse_cdp_neighbors(output):
    """
    Parse 'show cdp neighbors detail' output into a list of neighbor dicts.

    Returns list of dicts with keys:
        - device_id: neighbor hostname
        - local_interface: local interface name
        - remote_interface: remote (port) interface name
        - ip_address: management IP of the neighbor
        - platform: device platform/model
    """
    neighbors = []
    # Split into per-neighbor blocks separated by dashes
    blocks = re.split(r'-{3,}', output)

    for block in blocks:
        if not block.strip():
            continue

        neighbor = {}

        # Device ID
        match = re.search(r'Device ID:\s*(\S+)', block)
        if match:
            # Strip domain name if present (e.g., "R1.lab.local" -> "R1")
            device_id = match.group(1)
            neighbor['device_id'] = device_id.split('.')[0]
        else:
            continue  # Skip blocks without a device ID

        # IP Address (management address)
        match = re.search(r'IP address:\s*(\S+)', block, re.IGNORECASE)
        if not match:
            match = re.search(r'IPv4 Address:\s*(\S+)', block, re.IGNORECASE)
        neighbor['ip_address'] = match.group(1) if match else ''

        # Local interface
        match = re.search(r'Interface:\s*(\S+)', block)
        neighbor['local_interface'] = match.group(1).rstrip(',') if match else ''

        # Remote interface (Port ID)
        match = re.search(r'Port ID\s*\(outgoing port\):\s*(\S+)', block)
        neighbor['remote_interface'] = match.group(1) if match else ''

        # Platform
        match = re.search(r'Platform:\s*(.+?)(?:,|\n)', block)
        neighbor['platform'] = match.group(1).strip() if match else ''

        neighbors.append(neighbor)

    return neighbors


def parse_ip_interfaces(output):
    """
    Parse 'show ip interface brief' output into a list of interface dicts.

    Returns list of dicts with keys:
        - interface: interface name
        - ip_address: IP address assigned (empty string for unassigned)
        - status: interface status
        - protocol: protocol status
    """
    interfaces = []
    for line in output.splitlines():
        # Match lines like: GigabitEthernet0/0   10.0.0.1   YES manual up   up
        parts = line.split()
        if len(parts) < 6:
            continue
        # Skip the header row
        if parts[0] == 'Interface':
            continue
        ip = parts[1]
        # Validate the second column is an IP or "unassigned"; skip anything else
        # (handles malformed or continuation lines)
        if ip != 'unassigned' and not re.match(r'\d+\.\d+\.\d+\.\d+', ip):
            continue
        # Protocol is the rightmost token; use parts[-1] so "administratively down"
        # (which shifts all subsequent columns) doesn't land on the wrong index.
        protocol = parts[-1].lower().rstrip('*')
        interfaces.append({
            'interface': parts[0],
            'ip_address': '' if ip == 'unassigned' else ip,
            'status':   parts[4] if len(parts) > 4 else '',
            'protocol': protocol,
        })
    return interfaces


def shorten_interface(name):
    """Shorten interface names for display (e.g., GigabitEthernet0/0 -> Gi0/0)."""
    replacements = [
        (r'^GigabitEthernet', 'Gi'),
        (r'^FastEthernet', 'Fa'),
        (r'^TenGigabitEthernet', 'Te'),
        (r'^Serial', 'Se'),
        (r'^Loopback', 'Lo'),
        (r'^Vlan', 'Vl'),
        (r'^Ethernet', 'Et'),
    ]
    for pattern, replacement in replacements:
        name = re.sub(pattern, replacement, name)
    return name


_SWITCH_PATTERNS = re.compile(
    r'(^|[^a-z])(sw|switch|cat|ws-c|nexus|nxos|csw|dsw|asw|access|dist|core)([^a-z]|$)',
    re.IGNORECASE,
)
_FIREWALL_PATTERNS = re.compile(
    r'(^|[^a-z])(fw|asa|firewall|ftd|pix|fortigate|palo)([^a-z]|$)',
    re.IGNORECASE,
)


def _infer_role(hostname: str) -> str:
    """Guess device role from hostname when no explicit role is stored."""
    if _FIREWALL_PATTERNS.search(hostname):
        return 'firewall'
    if _SWITCH_PATTERNS.search(hostname):
        return 'switch'
    return 'router'


def gather_device_topology(conn, hostname):
    """
    Gather topology data from a single device connection.

    Returns dict with:
        - hostname: device hostname
        - neighbors: list of CDP neighbor dicts
        - interfaces: list of interface IP dicts
    """
    result = {
        'hostname': hostname,
        'neighbors': [],
        'interfaces': []
    }

    try:
        # Get CDP neighbors
        cdp_output = conn.send_command('show cdp neighbors detail', read_timeout=30)
        result['neighbors'] = parse_cdp_neighbors(cdp_output)
    except Exception as e:
        logger.warning(f"CDP query failed on {hostname}: {e}")

    try:
        # Get interface IPs
        ip_output = conn.send_command('show ip interface brief', read_timeout=30)
        result['interfaces'] = parse_ip_interfaces(ip_output)
    except Exception as e:
        logger.warning(f"Interface query failed on {hostname}: {e}")

    return result


def build_topology(devices_data):
    """
    Build a topology graph from gathered device data.

    Args:
        devices_data: list of dicts from gather_device_topology()

    Returns dict with:
        - nodes: list of node dicts (id, label, interfaces, type)
          interfaces is a list of {interface, ip_address} for machine use
        - edges: list of edge dicts with exact interface IPs on both ends
          local_ip  = IP on the local  device's connecting interface
          remote_ip = IP on the remote device's connecting interface
                      (NOT the management/CDP IP — looked up from remote
                       device's own show ip interface brief data)
        - interface_map: {hostname -> {interface_name -> ip}} for AI use
    """
    nodes = []
    edges = []
    seen_edges = set()
    node_ids = {}

    # Build a hostname->interface->ip lookup covering all managed devices.
    # This is used to resolve the *remote* interface IP correctly.
    hostname_iface_map = {}   # hostname.lower() -> {intf.lower() -> ip}
    for dev_data in devices_data:
        h = dev_data['hostname'].lower()
        hostname_iface_map[h] = {
            iface['interface'].lower(): iface['ip_address']
            for iface in dev_data.get('interfaces', [])
        }

    # Build node list — include machine-readable interface list on every node.
    for dev_data in devices_data:
        hostname = dev_data['hostname']
        node_id = hostname.lower()
        node_ids[node_id] = node_id

        iface_list = [
            {'interface': shorten_interface(iface['interface']),
             'full_interface': iface['interface'],
             'ip_address': iface['ip_address']}
            for iface in dev_data.get('interfaces', [])
        ]

        # HTML tooltip for the visual graph
        title = f"<b>{hostname}</b>"
        if iface_list:
            title += "<br>" + "<br>".join(
                f"{i['interface']}: {i['ip_address']}" for i in iface_list
            )

        nodes.append({
            'id':         node_id,
            'label':      hostname,
            'title':      title,
            'interfaces': iface_list,
            'type':       'managed',
            'role':       dev_data.get('role') or _infer_role(hostname),
        })

    # Build edges — resolve remote interface IP from the remote device's own data.
    for dev_data in devices_data:
        hostname = dev_data['hostname']
        src_id = hostname.lower()

        local_iface_map = hostname_iface_map.get(src_id, {})

        for neighbor in dev_data.get('neighbors', []):
            neighbor_hostname = neighbor['device_id']
            neighbor_id = neighbor_hostname.lower()

            # Add discovered-only neighbors (not in managed device list).
            if neighbor_id not in node_ids:
                node_ids[neighbor_id] = neighbor_id
                nodes.append({
                    'id':         neighbor_id,
                    'label':      neighbor_hostname,
                    'title':      f"<b>{neighbor_hostname}</b><br>{neighbor.get('ip_address', '')}",
                    'interfaces': [],
                    'type':       'discovered',
                    'role':       _infer_role(neighbor_hostname),
                })

            local_intf  = neighbor.get('local_interface', '')
            remote_intf = neighbor.get('remote_interface', '')

            edge_key = tuple(sorted([src_id, neighbor_id]))
            edge_detail_key = (
                edge_key[0], edge_key[1],
                min(local_intf.lower(), remote_intf.lower()),
                max(local_intf.lower(), remote_intf.lower()),
            )
            if edge_detail_key in seen_edges:
                continue
            seen_edges.add(edge_detail_key)

            local_short  = shorten_interface(local_intf)
            remote_short = shorten_interface(remote_intf)

            # Resolve IPs on BOTH ends of the link.
            local_ip = local_iface_map.get(local_intf.lower(), '')

            # Look up the remote device's interface IP from its own
            # show ip interface brief data — NOT from CDP's management IP.
            remote_iface_map = hostname_iface_map.get(neighbor_id, {})
            remote_ip = remote_iface_map.get(remote_intf.lower(), '')
            # Fall back to CDP management IP only if not found locally.
            if not remote_ip:
                remote_ip = neighbor.get('ip_address', '')

            # Assign from/to labels relative to the canonical edge direction.
            if src_id == edge_key[0]:
                from_ip, to_ip = local_ip, remote_ip
                from_intf, to_intf = local_short, remote_short
            else:
                from_ip, to_ip = remote_ip, local_ip
                from_intf, to_intf = remote_short, local_short

            title = (
                f"{edge_key[0]} {from_intf} ({from_ip})"
                f" <-> "
                f"{edge_key[1]} {to_intf} ({to_ip})"
            )

            edges.append({
                'from':       edge_key[0],
                'to':         edge_key[1],
                'from_intf':  from_intf,
                'to_intf':    to_intf,
                'from_label': from_intf,
                'to_label':   to_intf,
                'title':      title,
                'local_ip':   from_ip,
                'remote_ip':  to_ip,
            })

    # Build a flat interface_map {hostname -> [{intf, ip}]} for AI injection.
    interface_map = {}
    for dev_data in devices_data:
        hostname = dev_data['hostname']
        interface_map[hostname] = [
            {'intf': shorten_interface(i['interface']), 'ip': i['ip_address']}
            for i in dev_data.get('interfaces', [])
        ]

    return {
        'nodes':         nodes,
        'edges':         edges,
        'interface_map': interface_map,
    }


def parse_ospf_neighbors(output):
    """
    Parse 'show ip ospf neighbor detail' output into a list of neighbor dicts.

    Returns list of dicts: neighbor_id, priority, state, address, interface, area.
    """
    neighbors = []
    current   = None

    for line in output.splitlines():
        # "Neighbor 10.0.0.2, interface address 10.0.0.2"
        m = re.match(r'\s*Neighbor\s+(\d+\.\d+\.\d+\.\d+),\s*interface address\s+(\d+\.\d+\.\d+\.\d+)', line)
        if m:
            if current is not None:
                neighbors.append(current)
            current = {
                'neighbor_id': m.group(1),
                'address':     m.group(2),
                'priority':    '0',
                'state':       '',
                'interface':   '',
                'area':        '',
            }
            continue
        if current is None:
            continue
        # "    In the area 0 via interface GigabitEthernet0/0"
        m = re.match(r'\s+In the area\s+(\S+)\s+via interface\s+(\S+)', line)
        if m:
            current['area']      = m.group(1)
            current['interface'] = m.group(2)
            continue
        # "    Neighbor priority is 1, State is FULL, 6 state changes"
        m = re.match(r'\s+Neighbor priority is\s+(\d+),\s+State is\s+(\S+)', line)
        if m:
            current['priority'] = m.group(1)
            current['state']    = m.group(2).rstrip(',')
            continue

    if current is not None:
        neighbors.append(current)

    # Fallback: if detail output wasn't available, try brief table format
    if not neighbors:
        for line in output.splitlines():
            m = re.match(
                r'\s*(\d+\.\d+\.\d+\.\d+)\s+(\d+)\s+'
                r'(\w+/\S*(?:\s+-)?)\s+'
                r'\d+:\d+:\d+\s+'
                r'(\d+\.\d+\.\d+\.\d+)\s+(\S+)',
                line
            )
            if m:
                neighbors.append({
                    'neighbor_id': m.group(1),
                    'priority':    m.group(2),
                    'state':       m.group(3),
                    'address':     m.group(4),
                    'interface':   m.group(5),
                    'area':        '',
                })
    return neighbors


def parse_bgp_summary(output):
    """
    Parse 'show ip bgp summary' output.

    Returns dict with 'local_as' and 'peers' list.
    Each peer: neighbor, remote_as, state, established (bool).
    """
    local_as = ''
    peers    = []

    m = re.search(r'local AS number (\d+)', output, re.IGNORECASE)
    if m:
        local_as = m.group(1)

    in_table = False
    for line in output.splitlines():
        if re.match(r'\s*Neighbor\s+V\b', line):
            in_table = True
            continue
        if not in_table:
            continue
        # Neighbor V AS MsgRcvd MsgSent TblVer InQ OutQ Up/Down State/PfxRcd
        m = re.match(
            r'\s*(\d+\.\d+\.\d+\.\d+)\s+\d+\s+(\d+)'
            r'\s+\d+\s+\d+\s+\d+\s+\d+\s+\d+\s+\S+\s+(\S+)',
            line
        )
        if m:
            state = m.group(3)
            peers.append({
                'neighbor':    m.group(1),
                'remote_as':   m.group(2),
                'state':       state,
                'established': state.replace(',', '').isdigit(),
            })

    return {'local_as': local_as, 'peers': peers}


def parse_tunnel_config(output):
    """
    Parse 'show running-config | section ^interface Tunnel' output.

    Returns list of tunnel dicts: name, ip, source, destination, mode, description,
    nhrp_maps (list of NBMA IPs from 'ip nhrp map' lines),
    nhrp_nhs (list of NBMA IPs from 'ip nhrp nhs' lines),
    nhrp_network_id.
    """
    tunnels = []
    current = None
    for line in output.splitlines():
        m = re.match(r'^interface (Tunnel\S+)', line)
        if m:
            if current is not None:
                tunnels.append(current)
            current = {
                'name':            m.group(1),
                'ip':              '',
                'source':          '',
                'destination':     '',
                'mode':            'gre',
                'description':     '',
                'nhrp_maps':       [],
                'nhrp_nhs':        [],
                'nhrp_network_id': '',
                'nhrp_hub':        False,
            }
            continue
        if current is None:
            continue
        s = line.strip()
        m = re.match(r'ip address (\d+\.\d+\.\d+\.\d+)', s)
        if m:
            current['ip'] = m.group(1)
        m = re.match(r'tunnel source (\S+)', s)
        if m:
            current['source'] = m.group(1)
        m = re.match(r'tunnel destination (\S+)', s)
        if m:
            current['destination'] = m.group(1)
        m = re.match(r'tunnel mode (\S+(?:\s+\S+)?)', s)
        if m:
            current['mode'] = m.group(1)
        m = re.match(r'description (.+)', s)
        if m:
            current['description'] = m.group(1)
        # NHRP static map: 'ip nhrp map <tunnel-ip> <nbma-ip>'
        # (skip 'ip nhrp map multicast' lines — they have no tunnel-ip)
        m = re.match(r'ip nhrp map (\d+\.\d+\.\d+\.\d+)\s+(\d+\.\d+\.\d+\.\d+)', s)
        if m:
            nbma_ip = m.group(2)
            if nbma_ip not in current['nhrp_maps']:
                current['nhrp_maps'].append(nbma_ip)
        # NHRP NHS: 'ip nhrp nhs <hub-tunnel-ip>' (may also have 'nbma <nbma-ip>')
        m = re.match(r'ip nhrp nhs (\d+\.\d+\.\d+\.\d+)', s)
        if m:
            # If there's an nbma keyword, grab that IP instead
            m2 = re.search(r'nbma\s+(\d+\.\d+\.\d+\.\d+)', s)
            nhs_ip = m2.group(1) if m2 else ''
            if not nhs_ip:
                # No nbma keyword — resolve from nhrp_maps for this NHS tunnel IP
                # We'll resolve later; for now store the tunnel IP and resolve in build
                nhs_ip = m.group(1)
            if nhs_ip not in current['nhrp_nhs']:
                current['nhrp_nhs'].append(nhs_ip)
        # NHRP network-id
        m = re.match(r'ip nhrp network-id (\d+)', s)
        if m:
            current['nhrp_network_id'] = m.group(1)
        # NHRP map multicast dynamic — indicates this device is a DMVPN hub
        if s == 'ip nhrp map multicast dynamic':
            current['nhrp_hub'] = True
    if current is not None:
        tunnels.append(current)
    return tunnels


def _extract_tunnel_sections(running_config):
    """Extract all 'interface Tunnel*' blocks from a full running-config.

    Returns a string that looks exactly like the output of
    'show running-config | section ^interface Tunnel' — one or more
    interface blocks concatenated, each starting with 'interface TunnelX'
    and ending when the next top-level command (line starting with a
    non-space character that isn't 'interface Tunnel') is encountered.
    """
    lines = running_config.splitlines()
    result_lines = []
    in_tunnel = False
    for line in lines:
        # Detect start of a tunnel interface block
        if re.match(r'^interface Tunnel\S*', line):
            in_tunnel = True
            result_lines.append(line)
            continue
        if in_tunnel:
            # Still inside the block if line starts with whitespace (or is blank)
            if line.startswith(' ') or line.startswith('\t') or line.strip() == '':
                result_lines.append(line)
            else:
                # End of tunnel block — check if it's another tunnel
                if re.match(r'^interface Tunnel\S*', line):
                    result_lines.append(line)
                else:
                    in_tunnel = False
    return '\n'.join(result_lines)


def gather_protocol_topology(conn, hostname):
    """
    Gather OSPF, BGP, and tunnel data from a single device.

    Returns dict with hostname, interfaces, ospf, bgp, tunnels.
    """
    from modules.commands import run_device_command
    result = {
        'hostname':        hostname,
        'interfaces':      [],
        'ospf':            [],
        'ospf_router_id':  '',
        'bgp':             {'local_as': '', 'peers': []},
        'tunnels':         [],
        'mgmt_ip':         '',   # filled in by discover_protocol_topologies
    }
    try:
        out = run_device_command(conn, 'show ip interface brief')
        result['interfaces'] = parse_ip_interfaces(out)
    except Exception as e:
        logger.warning("Protocol topo: interface query failed on %s: %s", hostname, e)
    try:
        out = run_device_command(conn, 'show ip ospf neighbor detail')
        result['ospf'] = parse_ospf_neighbors(out)
    except Exception as e:
        logger.warning("Protocol topo: OSPF query failed on %s: %s", hostname, e)
    try:
        out = run_device_command(conn, 'show ip ospf')
        m = re.search(r'Routing Process.*?with ID\s+([\d.]+)', out)
        if not m:
            m = re.search(r'\bwith\s+ID\s+([\d.]+)', out)
        if m:
            result['ospf_router_id'] = m.group(1)
        else:
            logger.warning("Protocol topo: OSPF router-id regex no match on %s; output=%s",
                           hostname, out[:200])
    except Exception as e:
        logger.warning("Protocol topo: OSPF router-id query failed on %s: %s", hostname, e)
    try:
        out = run_device_command(conn, 'show ip bgp summary')
        result['bgp'] = parse_bgp_summary(out)
    except Exception as e:
        logger.warning("Protocol topo: BGP query failed on %s: %s", hostname, e)
    try:
        # NOTE: IOS pipe filters (| section, | include) are unreliable on this
        # platform — they return corrupted/empty output.  Fetch the full
        # running-config and extract 'interface Tunnel' blocks in Python.
        out = run_device_command(conn, 'show running-config')
        tunnel_section = _extract_tunnel_sections(out)
        result['tunnels'] = parse_tunnel_config(tunnel_section)
        # Fallback: extract OSPF router-id from running-config if show ip ospf
        # didn't produce one (e.g. IOS format mismatch or command timeout).
        if not result['ospf_router_id']:
            m = re.search(r'^\s*router-id\s+([\d.]+)', out, re.MULTILINE)
            if m:
                result['ospf_router_id'] = m.group(1)
                logger.warning("Protocol topo: got router-id %s from running-config for %s",
                               m.group(1), hostname)
        # Fallback: extract interface IPs from running-config if show ip interface
        # brief timed out.  Loopback IPs used as OSPF router-ids must be in ip_map
        # so that ghost nodes are not created for reachable managed devices.
        if not result['interfaces']:
            result['interfaces'] = _parse_ips_from_running_config(out)
            if result['interfaces']:
                logger.warning("Protocol topo: used running-config IPs for %s "
                               "(%d interfaces)", hostname, len(result['interfaces']))
    except Exception as e:
        logger.warning("Protocol topo: tunnel query failed on %s: %s", hostname, e)
    return result


def _parse_ips_from_running_config(config: str) -> list:
    """Extract interface IPs from a running-config string.

    Used as a fallback when 'show ip interface brief' times out so that
    loopback IPs (used as OSPF router-ids) still make it into ip_map.
    """
    interfaces = []
    current_intf = None
    for line in config.splitlines():
        m = re.match(r'^interface\s+(\S+)', line)
        if m:
            current_intf = m.group(1)
            continue
        if current_intf:
            m = re.match(r'\s+ip address\s+(\d+\.\d+\.\d+\.\d+)\s+', line)
            if m:
                interfaces.append({
                    'interface': current_intf,
                    'ip_address': m.group(1),
                    'status': 'up',
                    'protocol': 'up',
                })
    return interfaces


def _build_ip_map(devices_data):
    """Build {ip: hostname} map from all gathered interface data.

    Management IPs are added first as a baseline; interface IPs (more
    specific) overwrite them so the correct hostname always wins.
    """
    ip_map = {}
    for dev in devices_data:
        # Seed with management IP so devices with failed SSH commands still
        # appear in the map (loopback IPs will overwrite this below).
        mgmt = dev.get('mgmt_ip', '')
        if mgmt:
            ip_map[mgmt] = dev['hostname']
        for iface in dev.get('interfaces', []):
            ip = iface.get('ip_address', '')
            if ip:
                ip_map[ip] = dev['hostname']
    return ip_map


def build_ospf_topology(devices_data):
    """Build OSPF neighbor graph from gathered device data."""
    ip_map        = _build_ip_map(devices_data)
    # router-id → hostname map: lets us resolve neighbors whose interface IP
    # isn't in ip_map (e.g. device timed out on show ip interface brief).
    router_id_map = {
        dev['ospf_router_id']: dev['hostname']
        for dev in devices_data
        if dev.get('ospf_router_id')
    }
    nodes  = {}
    edges  = []
    seen   = set()

    for dev in devices_data:
        h = dev['hostname'].lower()
        nodes[h] = {
            'id':    h,
            'label': dev['hostname'],
            'title': f"<b>{dev['hostname']}</b>",
            'type':  'managed',
        }

    # First pass: collect all neighbor claims and candidate edges.
    # Key: (src, dst) — directed claim that src sees dst as a neighbor.
    claims          = set()
    candidate_edges = {}  # edge_key → edge dict (first reporter wins for metadata)
    managed_ids     = {dev['hostname'].lower() for dev in devices_data}

    for dev in devices_data:
        src = dev['hostname'].lower()
        for nbr in dev.get('ospf', []):
            state_full = 'FULL' in nbr['state'].upper()
            peer_ip    = nbr['address']
            nbr_id     = nbr['neighbor_id']
            # Prefer nbr_id (OSPF router-id) as the primary lookup key.
            # Router-IDs are loopback IPs in well-designed networks and are
            # unique within a single OSPF domain.  The interface address
            # (peer_ip) is a last resort because shared subnets can map to
            # the wrong device when multiple managed hosts have the same IP.
            peer_host  = (ip_map.get(nbr_id, '')
                          or router_id_map.get(nbr_id, '')
                          or ip_map.get(peer_ip, ''))

            if peer_host:
                dst = peer_host.lower()
            else:
                dst = f"ospf-{nbr_id}"
                if dst not in nodes:
                    nodes[dst] = {
                        'id':    dst,
                        'label': nbr_id,
                        'title': f"<b>OSPF Router</b><br>{nbr_id}<br><em>Unknown Router-ID</em>",
                        'type':  'discovered',
                    }

            claims.add((src, dst))
            # If dst resolved to an ospf-X placeholder, also record a claim
            # against the real managed hostname (if we can derive it via
            # router_id_map or ip_map).  This prevents the bidirectional check
            # from falsely suppressing a valid edge when one side couldn't
            # resolve the peer's IP but the peer's router-id IS known.
            if dst.startswith('ospf-'):
                alt = router_id_map.get(nbr_id, '') or ip_map.get(nbr_id, '')
                if alt:
                    claims.add((src, alt.lower()))
            area     = nbr.get('area', '')
            edge_key = tuple(sorted([src, dst]))
            if edge_key in candidate_edges:
                continue
            area_label = f"Area {area}" if area else ''
            title_parts = [f"OSPF: {src} {shorten_interface(nbr['interface'])} ↔ {dst}",
                           f"State: {nbr['state']}"]
            if area_label:
                title_parts.append(area_label)
            candidate_edges[edge_key] = {
                'from':        edge_key[0],
                'to':          edge_key[1],
                'state':       nbr['state'],
                'established': state_full,
                'interface':   nbr['interface'],
                'area':        area,
                'title':       ' | '.join(title_parts),
            }

    # Post-process: merge any ospf-{X} ghost nodes into managed nodes.
    # Covers the case where resolution failed during the first pass because
    # ospf_router_id was empty (show ip ospf timed out) but we can match the
    # ghost ID to a managed device via its ospf_router_id, interface IPs, or
    # by matching the ghost ID against a device whose interface has that address.
    ospf_ghost_to_real: dict = {}
    for ghost_id in list(nodes.keys()):
        if not ghost_id.startswith('ospf-'):
            continue
        ghost_addr = ghost_id[5:]  # strip 'ospf-' prefix
        real_h = (router_id_map.get(ghost_addr, '')
                  or ip_map.get(ghost_addr, ''))
        if not real_h:
            # Last resort: check every device's interface list
            for dev in devices_data:
                for iface in dev.get('interfaces', []):
                    if iface.get('ip_address') == ghost_addr:
                        real_h = dev['hostname']
                        break
                if real_h:
                    break
        if real_h:
            real_id = real_h.lower()
            if real_id in nodes:
                logger.warning("OSPF build: merging ghost %s → %s", ghost_id, real_id)
                ospf_ghost_to_real[ghost_id] = real_id
                del nodes[ghost_id]

    if ospf_ghost_to_real:
        new_candidates: dict = {}
        for key, edge in candidate_edges.items():
            a, b = key
            a = ospf_ghost_to_real.get(a, a)
            b = ospf_ghost_to_real.get(b, b)
            if a == b:
                continue
            new_key = tuple(sorted([a, b]))
            edge = dict(edge)
            edge['from'] = new_key[0]
            edge['to']   = new_key[1]
            if new_key not in new_candidates:
                new_candidates[new_key] = edge
        candidate_edges = new_candidates
        claims = {
            (ospf_ghost_to_real.get(s, s), ospf_ghost_to_real.get(d, d))
            for s, d in claims
        }

    # Build a set of managed devices that returned at least one OSPF neighbor.
    # A device with an empty OSPF list may have simply failed to respond — that is
    # not evidence against an adjacency.  Only treat it as a contradiction when the
    # device was successfully queried AND returned neighbors but didn't include us.
    devices_with_ospf = {
        dev['hostname'].lower()
        for dev in devices_data
        if dev.get('ospf')
    }

    # Second pass: suppress an edge only when we have positive evidence of asymmetry:
    # both endpoints returned OSPF data, but one of them didn't list the other.
    for edge_key, edge in candidate_edges.items():
        a, b = edge_key
        if (a in managed_ids and b in managed_ids
                and a in devices_with_ospf and b in devices_with_ospf):
            if (a, b) not in claims or (b, a) not in claims:
                logger.debug("OSPF build: suppressing edge %s — missing claim(s): fwd=%s rev=%s",
                             edge_key, (a,b) in claims, (b,a) in claims)
                continue  # confirmed contradiction — stale/ghost adjacency
        edges.append(edge)

    return {'nodes': list(nodes.values()), 'edges': edges}


def build_bgp_topology(devices_data):
    """Build BGP adjacency graph from gathered device data."""
    ip_map = _build_ip_map(devices_data)
    nodes  = {}
    edges  = []
    seen   = set()

    for dev in devices_data:
        h      = dev['hostname'].lower()
        loc_as = dev.get('bgp', {}).get('local_as', '')
        nodes[h] = {
            'id':       h,
            'label':    dev['hostname'],
            'title':    (f"<b>{dev['hostname']}</b><br>AS {loc_as}"
                         if loc_as else f"<b>{dev['hostname']}</b>"),
            'local_as': loc_as,
            'type':     'managed',
        }

    for dev in devices_data:
        src    = dev['hostname'].lower()
        src_as = dev.get('bgp', {}).get('local_as', '')
        for peer in dev.get('bgp', {}).get('peers', []):
            peer_ip   = peer['neighbor']
            peer_host = ip_map.get(peer_ip, '')
            rem_as    = peer['remote_as']

            if peer_host:
                dst = peer_host.lower()
            else:
                dst = f"as{rem_as}-{peer_ip}"
                if dst not in nodes:
                    nodes[dst] = {
                        'id':    dst,
                        'label': f"AS{rem_as}\n{peer_ip}",
                        'title': (f"<b>External BGP Peer</b><br>"
                                  f"AS {rem_as}<br>{peer_ip}"),
                        'type':  'external',
                    }

            edge_key = tuple(sorted([src, dst]))
            if edge_key in seen:
                continue
            seen.add(edge_key)
            edges.append({
                'from':        edge_key[0],
                'to':          edge_key[1],
                'established': peer['established'],
                'state':       peer['state'],
                'local_as':    src_as,
                'remote_as':   rem_as,
                'title':       (f"BGP: {src} (AS{src_as}) ↔ {peer_ip} (AS{rem_as})"
                               f" | {peer['state']}"),
            })

    return {'nodes': list(nodes.values()), 'edges': edges}


def build_tunnel_topology(devices_data):
    """Build tunnel connection graph from gathered device data.

    Handles both point-to-point tunnels (tunnel destination X.X.X.X) and
    DMVPN / multipoint GRE tunnels (no tunnel destination; peers discovered
    via NHRP map and NHS entries in the running-config).
    """
    ip_map = _build_ip_map(devices_data)
    nodes  = {}
    edges  = []
    seen   = set()

    # Build a tunnel-IP-to-hostname map so we can resolve NHRP NHS tunnel IPs
    # (e.g. 10.100.0.1 → Core-1) to the device that owns that tunnel address.
    tunnel_ip_map = {}  # tunnel_ip -> hostname
    for dev in devices_data:
        for tun in dev.get('tunnels', []):
            tip = tun.get('ip', '')
            if tip:
                tunnel_ip_map[tip] = dev['hostname']

    for dev in devices_data:
        h = dev['hostname'].lower()
        nodes[h] = {
            'id':    h,
            'label': dev['hostname'],
            'title': f"<b>{dev['hostname']}</b>",
            'type':  'managed',
        }

    def _ensure_node(ident, label, title_html):
        if ident not in nodes:
            nodes[ident] = {
                'id':    ident,
                'label': label,
                'title': title_html,
                'type':  'discovered',
            }

    def _add_edge(src, dst, tun_name, mode, src_ip, dst_ip, extra_label=''):
        intf_key = (tuple(sorted([src, dst])), tun_name)
        if intf_key in seen:
            return
        seen.add(intf_key)
        mode_label = mode
        if extra_label:
            mode_label = f"{mode} ({extra_label})"
        edges.append({
            'from':   src,
            'to':     dst,
            'tunnel': tun_name,
            'mode':   mode_label,
            'src_ip': src_ip,
            'dst_ip': dst_ip,
            'title':  (f"{src} {tun_name} ({src_ip}) "
                       f"→ {dst} ({dst_ip}) | {mode_label}"),
        })

    for dev in devices_data:
        src = dev['hostname'].lower()
        for tun in dev.get('tunnels', []):
            mode   = tun.get('mode', 'gre').lower()
            src_ip = tun.get('ip', '')

            # --- Point-to-point tunnel (has tunnel destination) ---
            dst_ip = tun.get('destination', '')
            if dst_ip and re.match(r'\d+\.\d+\.\d+\.\d+', dst_ip):
                peer_host = ip_map.get(dst_ip, '')
                if peer_host:
                    dst = peer_host.lower()
                else:
                    dst = f"tep-{dst_ip}"
                    _ensure_node(dst, dst_ip,
                                 f"<b>Tunnel Endpoint</b><br>{dst_ip}")
                _add_edge(src, dst, tun['name'], mode, src_ip, dst_ip)
                continue

            # --- Multipoint / DMVPN tunnel (no tunnel destination) ---
            # Collect unique peer NBMA IPs from nhrp_maps and resolve nhrp_nhs
            peer_nbma_ips = set()

            # NHRP static maps give us NBMA IPs directly
            for nbma in tun.get('nhrp_maps', []):
                peer_nbma_ips.add(nbma)

            # NHRP NHS entries may be tunnel IPs — resolve to NBMA via
            # the tunnel_ip_map → ip_map chain.
            for nhs_entry in tun.get('nhrp_nhs', []):
                # nhs_entry could be a tunnel IP (e.g. 10.100.0.1) or NBMA IP
                # First check if it's an NBMA IP we already know
                if ip_map.get(nhs_entry):
                    peer_nbma_ips.add(nhs_entry)
                elif tunnel_ip_map.get(nhs_entry):
                    # It's a tunnel IP — find the host, then find its NBMA
                    nhs_host = tunnel_ip_map[nhs_entry]
                    # Find the NBMA IP: look at the tunnel source interface
                    # and resolve it from the device's interface data
                    for peer_dev in devices_data:
                        if peer_dev['hostname'] == nhs_host:
                            for peer_tun in peer_dev.get('tunnels', []):
                                tun_src = peer_tun.get('source', '')
                                # Resolve source interface to IP
                                peer_iface_map = {
                                    i['interface'].lower(): i['ip_address']
                                    for i in peer_dev.get('interfaces', [])
                                }
                                nbma = peer_iface_map.get(tun_src.lower(), '')
                                if nbma:
                                    peer_nbma_ips.add(nbma)
                                    break
                            break

            # Remove our own NBMA IP from the set (if present)
            own_iface_map = {
                i['interface'].lower(): i['ip_address']
                for i in dev.get('interfaces', [])
            }
            own_source = tun.get('source', '')
            own_nbma   = own_iface_map.get(own_source.lower(), '')
            peer_nbma_ips.discard(own_nbma)

            # Determine DMVPN role label
            is_hub   = tun.get('nhrp_hub', False)
            nhrp_nid = tun.get('nhrp_network_id', '')
            role_str = 'Hub' if is_hub else 'Spoke'
            dmvpn_label = f"DMVPN {role_str}"
            if nhrp_nid:
                dmvpn_label = f"DMVPN {role_str} nid:{nhrp_nid}"

            if not peer_nbma_ips:
                # Hub with only dynamic spokes — no static maps.
                # Still show the tunnel as a node with no edges for now.
                continue

            for nbma_ip in peer_nbma_ips:
                peer_host = ip_map.get(nbma_ip, '')
                if peer_host:
                    dst = peer_host.lower()
                else:
                    dst = f"tep-{nbma_ip}"
                    _ensure_node(dst, nbma_ip,
                                 f"<b>DMVPN Peer</b><br>NBMA: {nbma_ip}")
                _add_edge(src, dst, tun['name'], mode, src_ip, nbma_ip,
                          extra_label=dmvpn_label)

    return {'nodes': list(nodes.values()), 'edges': edges}


def discover_protocol_topologies(devices, connection_factory, connections_pool, pool_lock,
                                  status_cache=None, max_workers=5):
    """
    Discover OSPF, BGP, and tunnel topologies from all online devices in parallel.

    Returns dict with 'ospf', 'bgp', 'tunnel' sub-dicts (each: nodes, edges).
    """
    empty = {'nodes': [], 'edges': []}
    target = [
        dev for dev in devices
        if status_cache is None or status_cache.get(dev['ip'], False)
    ]
    if not target:
        return {'ospf': empty, 'bgp': empty, 'tunnel': empty}

    devices_data = []

    def query_device(dev):
        try:
            conn = connection_factory(dev, connections_pool, pool_lock)
            result = gather_protocol_topology(conn, dev['hostname'])
            result['mgmt_ip'] = dev.get('ip', '')
            return result
        except Exception as e:
            logger.warning("Protocol topo query failed for %s: %s", dev['hostname'], e)
            return {
                'hostname':       dev['hostname'],
                'interfaces':     [],
                'ospf':           [],
                'ospf_router_id': '',
                'bgp':            {'local_as': '', 'peers': []},
                'tunnels':        [],
                'mgmt_ip':        dev.get('ip', ''),
            }

    with ThreadPoolExecutor(max_workers=min(max_workers, len(target))) as executor:
        futures = {executor.submit(query_device, dev): dev for dev in target}
        for future in as_completed(futures):
            try:
                devices_data.append(future.result())
            except Exception as e:
                dev = futures[future]
                logger.error("Protocol topo thread error for %s: %s", dev['hostname'], e)

    return {
        'ospf':   build_ospf_topology(devices_data),
        'bgp':    build_bgp_topology(devices_data),
        'tunnel': build_tunnel_topology(devices_data),
    }


def discover_topology(devices, connection_factory, connections_pool, pool_lock,
                      status_cache=None, max_workers=5):
    """
    Discover network topology by querying all online devices in parallel.

    Args:
        devices: list of device dicts from inventory
        connection_factory: function to get a device connection
        connections_pool: shared connection pool
        pool_lock: threading lock for pool
        status_cache: optional dict of ip -> online status
        max_workers: max parallel connections

    Returns:
        Topology dict with nodes and edges
    """
    devices_data = []

    # Filter to only online devices if status cache is available
    target_devices = []
    for dev in devices:
        if status_cache is not None:
            if not status_cache.get(dev['ip'], False):
                continue
        target_devices.append(dev)

    if not target_devices:
        return {'nodes': [], 'edges': []}

    def query_device(dev):
        try:
            conn = connection_factory(dev, connections_pool, pool_lock)
            result = gather_device_topology(conn, dev['hostname'])
            result['role'] = dev.get('role') or _infer_role(dev['hostname'])
            return result
        except Exception as e:
            logger.warning(f"Topology query failed for {dev['hostname']} ({dev['ip']}): {e}")
            return {
                'hostname': dev['hostname'],
                'neighbors': [],
                'interfaces': [],
                'role': dev.get('role') or _infer_role(dev['hostname']),
            }

    # Query devices in parallel
    with ThreadPoolExecutor(max_workers=min(max_workers, len(target_devices))) as executor:
        futures = {executor.submit(query_device, dev): dev for dev in target_devices}
        for future in as_completed(futures):
            try:
                result = future.result()
                devices_data.append(result)
            except Exception as e:
                dev = futures[future]
                logger.error(f"Topology thread error for {dev['hostname']}: {e}")

    return build_topology(devices_data)
