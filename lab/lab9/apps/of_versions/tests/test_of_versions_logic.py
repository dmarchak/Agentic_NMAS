"""of_versions_logic over plain data: what the pin offers and what /health says of the switches
that connected. Python 3.5 and Mercury's alike. The switches are the five Ryu recorded at the
bring-up (2026-11-06; tests/fixtures/lab9_captures/2026-11-06/ryu-rest.txt in Mercury's
repository), each of which negotiated 1.3 with the team's pin in force (C2598).
"""

try:
    from mercury_app.testing import covers
except ImportError:                     # run with no SDK on the path (the app gate reads the import)
    def covers(*_names):
        return lambda test: test

import of_versions_logic as L

S3, S4 = 3, 4
ARISTA_A, ARISTA_C, PROCURVE = 2214744208935, 2843895626628, 56298109234905574
RECORDED = (S3, S4, ARISTA_A, ARISTA_C, PROCURVE)
OF13, OF14 = 0x04, 0x05


@covers("every switch the bring-up recorded negotiates a version the pin offers")
def test_every_recorded_switch_on_1_3_is_healthy_and_named():
    got = L.health(dict((d, OF13) for d in RECORDED))
    assert got["ok"] is True and got["problems"] == []
    assert got["offers"] == ["1.0", "1.3"]
    assert got["switches"] == {"3": "1.3", "4": "1.3", "2214744208935": "1.3",
                               "2843895626628": "1.3", "56298109234905574": "1.3"}


@covers("a switch outside the pin is named")
def test_a_switch_on_1_4_is_the_one_problem():
    negotiated = dict((d, OF13) for d in RECORDED)
    negotiated[ARISTA_A] = OF14
    got = L.health(negotiated)
    assert got["ok"] is False
    assert got["problems"] == ["switch 2214744208935 negotiated OpenFlow 1.4, outside the pin "
                               "(1.0, 1.3)"]
    assert got["switches"]["2214744208935"] == "1.4"


def test_no_switch_connected_is_healthy_and_an_unknown_version_is_named_by_its_number():
    assert L.health({}) == {"ok": True, "offers": ["1.0", "1.3"], "problems": [],
                            "switches": {}}
    assert L.version_text(0x01) == "1.0"
    assert L.version_text(0x07) == "0x07 (not a version known)"
