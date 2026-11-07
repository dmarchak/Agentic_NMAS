"""THE PATH CONTRACT: `fabric_paths.shortest_path`, as any replacement must answer it (the module's
docstring). The team's implementation replaces fabric_paths.py and passes these, unchanged.

The ring is the one Ryu recorded at the bring-up (tests/fixtures/lab9_captures/2026-11-06/
ryu-rest.txt, `### links`, its datapath ids masked there): two Open vSwitch hosts (3 and 4),
two Aristas and the ProCurve, the four of 3, 4, the ProCurve and one Arista in a ring, the other
Arista hanging off 4. Plain functions and asserts, Python 3.5 and Mercury's alike.
"""

try:
    from mercury_app.testing import covers
except ImportError:                     # run with no SDK on the path (the app gate reads the import)
    def covers(*_names):
        return lambda test: test

from fabric_paths import shortest_path

S3, S4 = 3, 4
ARISTA_A, ARISTA_C, PROCURVE = 2214744208935, 2843895626628, 56298109234905574
#: The recorded links, one direction each: (switch, port, switch, port).
RECORDED = [(S4, 3, PROCURVE, 3), (S3, 2, S4, 2), (ARISTA_A, 19, PROCURVE, 2),
            (ARISTA_A, 18, S3, 1), (ARISTA_C, 18, S4, 1)]


def ring(without=()):
    graph = dict((d, {}) for d in (S3, S4, ARISTA_A, ARISTA_C, PROCURVE))
    for (a, pa, b, pb) in RECORDED:
        if (a, b) in without or (b, a) in without:
            continue
        graph[a][b] = pa
        graph[b][a] = pb
    return graph


def distances(graph):
    """Every pair's distance in hops, by Floyd-Warshall: a path independent of the BFS."""
    inf = len(graph) + 1
    nodes = sorted(graph)
    dist = dict(((a, b), 0 if a == b else (1 if b in graph[a] else inf))
                for a in nodes for b in nodes)
    for k in nodes:
        for a in nodes:
            for b in nodes:
                if dist[(a, k)] + dist[(k, b)] < dist[(a, b)]:
                    dist[(a, b)] = dist[(a, k)] + dist[(k, b)]
    return dist, inf


@covers("a host is reached on the shortest path of the recorded ring")
def test_the_recorded_ring_takes_its_one_link_between_the_two_open_vswitch_hosts():
    assert shortest_path(ring(), S3, S4) == [S3, S4]
    assert shortest_path(ring(), S4, S3) == [S4, S3]
    assert shortest_path(ring(), S3, ARISTA_C) == [S3, S4, ARISTA_C]


@covers("a ring link going down reroutes the other way round")
def test_with_the_link_down_the_path_goes_the_other_way_round():
    graph = ring(without=[(S3, S4)])
    assert shortest_path(graph, S3, S4) == [S3, ARISTA_A, PROCURVE, S4]
    assert shortest_path(graph, S4, S3) == [S4, PROCURVE, ARISTA_A, S3]


def test_every_answer_is_a_simple_path_as_short_as_any():
    for graph in (ring(), ring(without=[(S3, S4)]), ring(without=[(ARISTA_A, PROCURVE)])):
        dist, inf = distances(graph)
        for src in graph:
            for dst in graph:
                path = shortest_path(graph, src, dst)
                if dist[(src, dst)] >= inf:
                    assert path is None, (src, dst, path)
                    continue
                assert path[0] == src and path[-1] == dst, (src, dst, path)
                assert len(set(path)) == len(path), path
                assert all(path[i + 1] in graph[path[i]] for i in range(len(path) - 1)), path
                assert len(path) - 1 == dist[(src, dst)], (src, dst, path)


def test_equal_paths_tie_to_the_lowest_and_the_same_every_time():
    # Arista A to switch 4: through 3 or through the ProCurve, two hops each.
    assert shortest_path(ring(), ARISTA_A, S4) == [ARISTA_A, S3, S4]
    reordered = dict((d, dict(sorted(n.items(), reverse=True)))
                     for d, n in sorted(ring().items(), reverse=True))
    assert shortest_path(reordered, ARISTA_A, S4) == [ARISTA_A, S3, S4]


def test_one_switch_unknown_or_unreachable():
    assert shortest_path(ring(), S3, S3) == [S3]
    assert shortest_path(ring(), S3, 99) is None
    assert shortest_path(ring(), 99, S3) is None
    cut = ring(without=[(ARISTA_C, S4)])
    assert shortest_path(cut, S3, ARISTA_C) is None
    assert shortest_path({S3: {}}, S3, S3) == [S3]
