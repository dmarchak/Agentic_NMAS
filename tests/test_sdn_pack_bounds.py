"""Every section of an SDN detection's pack is bounded (`modules/sdn/detect.py` `section`;
C2006): the walk's re-fired scan (2026-10-28 00:26:20 UTC) carried its earlier sightings
unbounded, and its classify request (about 30,316 estimated tokens) passed the task's 24,000
bound, so it was refused before sending and nothing was classified.

- A scan with 1,000 earlier sightings and 1,200 evidence ids sends the newest 50 sightings
  (`SECTION_SIGHTINGS`), says how many there were and how many were sent, and marks the
  section a subset; the detection piece's evidence list names only ids sent, the rest counted.
- The request it makes fits the task's prompt bound, where the unbounded one did not.
- A section under the bounds is unchanged: no count of what was not sent.

The scan is the real rule's over tests/test_sdn_detect.py's collection (the captured L4 flow
copied per destination port); the sightings and ids are the one edit, as a long re-fire leaves.
"""
import pytest

from modules.ai import gateway, profiles
from modules.sdn import closed_loop as CL
from modules.sdn import detect as D
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture
from tests.test_sdn_detect import T0, VALUES, collect, save, scan_flows


@pytest.fixture
def scan(networks):  # noqa: F811 - the fixture, used
    save()
    collected = collect(T0, flows=scan_flows(25))
    (d,) = D.scan(collected, VALUES)["detections"]
    (_ctl, sw), = list(D._switches(collected))
    return d, collected, sw


#: A re-fire's size: unbounded, its request is past the task's 24,000-token bound, as the walk's
#: was (about 30,316); the control with the bounds removed shows it.
SIGHTINGS, IDS = 1000, 1200


def _refired(d):
    sightings = [{"id": f"sdn:flow:ctl-1:0000000000000001:old{n}", "port": 2000 + n,
                  "dst": "192.0.2.3", "at": T0 - 60 + n * 0.05} for n in range(SIGHTINGS)]
    ids = list(d["evidence"]) + [f"sdn:flow:ctl-1:0000000000000001:gone{n}"
                                 for n in range(IDS - len(d["evidence"]))]
    return dict(d, sightings=sightings, evidence=ids)


def test_a_refired_scan_sends_its_newest_sightings_and_counts_the_rest(scan):
    d, collected, sw = scan
    got = D.section(_refired(d), collected, sw)
    sightings = [p for p in got["pieces"] if p["kind"] == "sighting"]
    assert len(sightings) == D.SECTION_SIGHTINGS == 50
    assert sightings[0]["port"] == 2000 + SIGHTINGS - 1, "newest first"
    assert got["counts"]["earlier_sightings"] == SIGHTINGS
    assert got["counts"]["earlier_sightings_sent"] == 50 and got["subset"] is True
    det = got["pieces"][0]
    sent = {p.get("id") for p in got["pieces"] if p.get("id")}
    assert det["evidence"] and set(det["evidence"]) <= sent
    assert det["evidence_not_sent"] == IDS - len(det["evidence"])


def test_its_request_fits_the_task_s_bound(scan):
    d, collected, sw = scan
    from modules.sdn import flow_ops

    section = D.section(_refired(d), collected, sw)
    # The data blocks as classify_pack builds them (its sent evidence, the network's limits).
    data = CL.request_blocks(CL.sent_evidence(section), section,
                             flow_ops.settings_of("Default")["values"])
    body = {"max_tokens": profiles.TASKS[CL.CLASSIFY_FEATURE]["max_tokens"], "data": data}
    assert gateway.prompt_tokens(body) <= profiles.TASKS[CL.CLASSIFY_FEATURE]["max_prompt_tokens"]


def test_a_section_under_the_bounds_counts_nothing_not_sent(scan):
    d, collected, sw = scan
    got = D.section(d, collected, sw)
    assert "earlier_sightings_sent" not in got["counts"]
    assert "evidence_not_sent" not in got["pieces"][0]
    assert got["pieces"][0]["evidence"] == d["evidence"]
