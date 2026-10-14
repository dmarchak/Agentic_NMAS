"""THE one BGP summary reader. Moved out of modules/topology.py unchanged (2026-10-14): the
deploy's verify reads BGP through it (`pipeline._parse_bgp_summary`), and today's topology page
that held it retires (Phase 7's order: the AI family's shared pieces out first). topology
imports it back for its own use until it goes."""
import re


def parse_bgp_summary(output):
    """
    Parse 'show ip bgp summary' output: THE one BGP summary reader.

    Returns ``{"local_as", "peers"}``; each peer is ``{neighbor, remote_as,
    up_down, state, established}``.

    A real row has TEN fields (measured on r3, 2026-09-27;
    tests/fixtures/operational/r3__show_ip_bgp_summary.txt)::

        198.51.100.1    4  65002  7255  7244   4   0   0 4d13h      3

    The last is the PREFIX COUNT when established, and a state word (Idle,
    Active, Connect, OpenSent, OpenConfirm, "Idle (Admin)") when not. A long
    neighbour address (IPv6) wraps the rest of its row onto the next line,
    and the two are joined (measured on r4's IPv6 peer). The deploy's verify
    had its own copy, which expected eight fields and counted nothing (C64);
    one reader is how two cannot come to disagree again.

    **Both address families** (`show bgp all summary`): each "For address
    family:" section is its own table, and every peer records its family.
    A row is an ADDRESS (it has "." or ":") followed by BGP version 4. Without
    that, the lines between two tables read as peers: measured on r3,
    "0 BGP route-map cache entries using 0 bytes of memory" and "4 networks
    peaked at ... (4d14h ago)" both have ten fields and start with a digit,
    and the looser rule returned three phantom down peers.
    """
    local_as = ''
    peers    = []

    m = re.search(r'local AS number (\d+)', output or '', re.IGNORECASE)
    if m:
        local_as = m.group(1)

    def is_address(token):
        return bool(re.match(r'^[0-9a-fA-F:.]+$', token)) and ('.' in token or ':' in token)

    in_table, pending, family = False, None, ''
    for line in (output or '').splitlines():
        m = re.match(r'\s*For address family:\s*(.+?)\s*$', line)
        if m:
            in_table, pending, family = False, None, m.group(1)
            continue
        if re.match(r'\s*Neighbor\s+V\b', line):
            in_table = True
            continue
        if not in_table:
            continue
        fields = line.split()
        if not fields:
            continue
        if pending is not None:
            fields, pending = [pending] + fields, None
        elif len(fields) == 1 and is_address(fields[0]):
            pending = fields[0]         # a wrapped row: the address alone
            continue
        if not is_address(fields[0]) or len(fields) < 10 or fields[1] != '4':
            continue
        state = ' '.join(fields[9:])
        peers.append({
            'neighbor':       fields[0],
            'remote_as':      fields[2],
            'up_down':        fields[8],
            'state':          state,
            'address_family': family,
            'established':    len(fields) == 10 and fields[9].replace(',', '').isdigit(),
        })

    return {'local_as': local_as, 'peers': peers}
