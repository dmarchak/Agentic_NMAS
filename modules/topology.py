"""
Topology Discovery Module

Gathers CDP neighbor data and interface IP information from devices
to build a network topology map.
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
        - ip_address: IP address assigned
        - status: interface status
        - protocol: protocol status
    """
    interfaces = []
    for line in output.splitlines():
        # Match lines like: GigabitEthernet0/0   10.0.0.1   YES manual up   up
        parts = line.split()
        if len(parts) >= 6 and parts[1] != 'Interface':
            # Skip unassigned interfaces
            ip = parts[1]
            if ip == 'unassigned':
                continue
            # Validate it looks like an IP
            if not re.match(r'\d+\.\d+\.\d+\.\d+', ip):
                continue
            interfaces.append({
                'interface': parts[0],
                'ip_address': ip,
                'status': parts[4] if len(parts) > 4 else '',
                'protocol': parts[5] if len(parts) > 5 else ''
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
            return gather_device_topology(conn, dev['hostname'])
        except Exception as e:
            logger.warning(f"Topology query failed for {dev['hostname']} ({dev['ip']}): {e}")
            return {
                'hostname': dev['hostname'],
                'neighbors': [],
                'interfaces': []
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
