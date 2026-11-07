"""fabric_forwarding's path choice: THE TEAM'S PURE LOGIC, behind its published contract (the SDN
platform design revision 6, section 14: "shortest path with reroute"). This file is v0's
REFERENCE implementation, small on purpose: the team's implementation replaces this file, and
`tests/test_fabric_paths.py` is the contract any replacement passes, unchanged.

**The contract.** `shortest_path(graph, src, dst)`:
- *graph* is `{dpid: {neighbour_dpid: out_port}}`: each switch's neighbours, with the port it
  reaches each one on (`fabric_logic.graph_of` builds it from the links both ends confirm and
  the ports that are up). Datapath ids are ints; a switch with no neighbours maps to `{}`.
- It answers the list of datapath ids from *src* to *dst*, both included (`[src]` when they are
  the same switch), or None when *dst* cannot be reached, or either is not in *graph*.
- The path is SIMPLE (no switch twice) and SHORTEST in hops.
- It is DETERMINISTIC: among equal-length paths it answers the same one every time, on any
  Python (3.5's dicts have no order, so nothing may depend on iteration order). v0 takes the
  path whose switches, compared in order, are lowest.

**Reroute** is not a second function: the app calls `shortest_path` again on the graph without
the link that went down (`fabric_logic.next_hops`), and installs the difference. So a
replacement that answers the contract reroutes too.

**Loop safety does not rest on this file:** `fabric_logic.forwarding_loop` walks the next hops
the answers give and refuses a table that loops, naming it, before anything is installed.

Python 3.5 (the controller's interpreter, C2646): no f-strings, no variable annotations, the
standard library alone; it imports nothing.
"""


def shortest_path(graph, src, dst):
    """The shortest path from *src* to *dst* over *graph*, as a list of datapath ids, or None
    (see the module's docstring)."""
    if src not in graph or dst not in graph:
        return None
    if src == dst:
        return [src]
    # Breadth first, neighbours in ascending order, so the first path found to each switch is
    # the lowest of the shortest ones (the tie-break the contract states).
    parent = {src: None}
    frontier = [src]
    while frontier:
        following = []
        for node in frontier:
            for neighbour in sorted(graph[node]):
                if neighbour in parent or neighbour not in graph:
                    continue
                parent[neighbour] = node
                if neighbour == dst:
                    path = [dst]
                    while parent[path[-1]] is not None:
                        path.append(parent[path[-1]])
                    path.reverse()
                    return path
                following.append(neighbour)
        frontier = following
    return None
