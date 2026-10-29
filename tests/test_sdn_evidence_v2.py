"""An SDN detection's evidence on Monitoring › Alerts (C1867; board AlertsSdnEvidence, a revision
of P1's AlertsExplain, signed off under the Phase 7 mode 2026-10-28): the pack's ``sdn`` section
drawn in words, never as bare references, and the source named "SDN detection".

**The data.** Every pack is built by the real code over captures, as test_sdn_detect.py's are:
- **a scan and a flood, IPv4 and IPv6,** found by the real `collect_threat_data` and
  `detect.observe` over S1's captured Ryu answers (tests/fixtures/sdn/ryu/rest_with_peer.json,
  through test_sdn_detect.py's `Sampled`), with that module's minimal edits (the captured L4
  flow copied with its destination port changed; port 1's received packets raised);
- **an unauthorised flow and the meter its effect names,** found the same way over test_sdn_v2.py's
  lab (the capture's meter flow recorded as Mercury's, its drop flow not), the SDN reader run
  over the same capture, so the switch's own name (``s1``) and meter 1's configuration and
  counters are Ryu's as captured;
- **a displaced flow and a port read by the Lab 8 walk,** each pack built by
  `evidence_pack.build_detection` from a recorded walk case's detection and section
  (tests/fixtures/ai_cases/sdn_classify/recorded_walk.json, ``walk-unauthorised-s1`` and
  ``walk-flood-1-s1``), unchanged (`walk_pack`; the board shots also build the held-out IPv6
  flood on s2, ``flood-v6-s2``, the same way).

**What is held:** each kind of piece in words (the detection with what it measured, against what,
its confidence, from and to, and what it rests on linked; a port's rates, drops and counts over
its sample; a flow's match as written, actions, packets, bytes, age, timeouts and cookie; a
displaced flow's response; the switch's flow granularity), every ``sdn`` piece drawn with more
than its reference, IPv6 addresses whole beside IPv4 ones, the switch by DPID and name, the
meters a section's flows name as the SDN reader last read them (said as not part of the pack)
and each state that read can be in, and the tab's source "SDN detection" with its unreadable
state.
"""
import json
import os
import re

import pytest

from modules import evidence_pack as EP
from modules import sdn_page
from modules.sdn import closed_loop as CL
from modules.sdn import detect as D
from tests import test_sdn_detect as TD
from tests import test_sdn_v2 as V
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CASES = os.path.join(ROOT, "tests", "fixtures", "ai_cases", "sdn_classify")


def walk_case(key: str, cases: str = "recorded_walk") -> dict:
    with open(os.path.join(CASES, f"{cases}.json"), encoding="utf-8") as fh:
        return next(c for c in json.load(fh)["cases"] if c["key"] == key)


def walk_pack(key: str, network: str = "Default", cases: str = "recorded_walk") -> dict:
    """The recorded case *key*'s pack (of *cases*, the walk's by default), built by
    `build_detection` from its detection and section as kept, and recorded."""
    case = walk_case(key, cases)
    det, sec = case["detection"], case["section"]
    at = D._epoch(det["at"])
    inst = D.instance(det, det.get("since") or at, at,
                      det["threshold"].get("window_s") or 0 if det["rule"] == "flood" else 0)
    pack = EP.build_detection(
        inst, network=network, sdn=sec, now=at,
        switch_words=f"switch {det['dpid_hex']} on {det['connection']}",
        trigger=f"Mercury's SDN detection found it in the collection of {det['at']}: "
                f"{det['words']}")
    assert EP.record(pack)["ok"]
    return pack


def client():
    import app as A
    return A.app.test_client()


def page(c, pack) -> str:
    r = c.get(f"/v2/monitoring/alerts/pack/{pack['id']}", headers={"HX-Request": "true"})
    assert r.status_code == 200, r.status_code
    return r.get_data(as_text=True)


def section_html(html: str) -> str:
    """The ``sdn`` section's own HTML (a collapsed `<details>` since board AlertsExplain's
    revision of 2026-10-29, "the answer card first")."""
    m = re.search(r'<details class="pack-section" data-ref="sdn".*?</details>\s*(?:<details '
                  r'class="pack-section"|<p class="card-foot")', html, re.S)
    assert m, "no sdn section drawn"
    return m.group(0)


def pieces(html: str) -> dict:
    """Each ``sdn`` piece's words, by its reference."""
    out = {}
    for ref, body in re.findall(r'<li data-ref="(sdn:\d+)"[^>]*>(.*?)</li>', section_html(html),
                                re.S):
        out[ref] = V.words(body)
    return out


def drawn(words, pattern) -> str:
    """The one piece's words matching *pattern*, or an assertion naming what was drawn."""
    words = list(words)
    hit = [w for w in words if re.search(pattern, w)]
    assert hit, f"no piece drawn matching {pattern!r}: {words}"
    return hit[0]


def scan_pack(src):
    out = TD.observe(TD.T0, flows=TD.scan_flows(25, src))
    assert out["ok"], out["error"]
    d = next(d for d in out["detections"] if d["rule"] == "scan")
    return EP.find(D.read_state()["doc"]["networks"]["Default"]["firing"][d["key"]]["pack"])[0]


def flood_pack(family, url):
    from modules.sdn import connections as C
    if url == TD.BASE6:
        C.save_connection("Default", {"name": "ctl-1", "kind": "ryu", "url": url}, actor="op")
    kw = {"flows": TD.without(family), "url": url}
    TD.baseline_runs(5, **kw)
    for t in (50, 70):
        TD.observe(TD.T0 + t, second=TD.rx(10000), **kw)
    out = TD.observe(TD.T0 + 80, second=TD.rx(10000), **kw)
    (d,) = [d for d in out["detections"] if d["rule"] == "flood"]
    return EP.find(D.read_state()["doc"]["networks"]["Default"]["firing"][d["key"]]["pack"])[0]


@pytest.fixture
def detect_lab(networks):  # noqa: F811 - the fixture, used
    """test_sdn_detect.py's lab: Default's ``ctl-1`` over S1's capture; no SDN reader run."""
    TD.save()
    return networks


@pytest.fixture
def reader_lab(networks, monkeypatch):  # noqa: F811 - the fixture, used
    """test_sdn_v2.py's lab with the SDN reader run, and the detection judged over the same
    capture: the unauthorised drop flow's pack, its effect naming Mercury's meter flow."""
    lab = V.make_lab(networks, monkeypatch)
    V.store_read()
    got = CL.collect_threat_data("Default", 1.0, sleep=lambda s: None, now=lambda: V.T0)
    out = D.observe("Default", got, values=TD.VALUES)
    assert out["ok"] and len(out["fired"]) == 1, out
    lab["pack"] = EP.read()["rows"][-1]
    return lab


# ───────────────────────────────────────────────────────────── the pieces

@pytest.mark.usefixtures("detect_lab")
class TestThePiecesInWords:
    @pytest.mark.parametrize("src,dst", [(TD.V4_L4, "192.0.2.2"), (TD.V6_L4, "2001:db8::2")])
    def test_a_scan_s_flows_are_drawn_with_their_match_as_written(self, src, dst):
        pack = scan_pack(src)
        got = pieces(page(client(), pack))
        flows = [w for w in got.values() if re.match(r"sdn:\d+ Flow (cited|,)", w)]
        assert len(flows) == 26, "every flow kept is drawn"
        family = "ipv6" if ":" in src[0] else "ipv4"
        one = drawn(flows, r"tcp_dst=1000\b")
        assert f"{family}_src={src[0]}" in one and f"{family}_dst={dst}" in one, one
        assert "cited by the detection" in one and "actions OUTPUT:" in one
        assert re.search(r"[\d,]+ packets, [\d,]+ bytes; installed [\d,]+ s before the read; ",
                         one), one
        assert "cookie 0x" in one
        det = got["sdn:1"]
        assert det.startswith("sdn:1 SDN scan confidence high :"), det
        assert "Measured: distinct destination ports from one source, 26 ports in 60 s" in det
        assert "Against: the scan's ports in its window, 20 ports; window 60 s " \
               "(sdn_scan_ports, sdn_scan_window_seconds)" in det
        assert f"From {src[0]} to {dst}" in det
        rests = det[det.index("Rests on: "):]
        assert len(re.findall(r"sdn:\d+ a flow, priority \d+", rests)) == 26, rests

    @pytest.mark.parametrize("family,src,url", [("v6", "192.0.2.1", TD.BASE),
                                                ("v4", "2001:db8::1", TD.BASE6)])
    def test_a_flood_s_port_is_drawn_with_its_rates_drops_and_counts(self, family, src, url):
        """IPv4 (the IPv6 flow taken away) and IPv6 (the IPv4 one taken away, the controller
        reached over IPv6), as test_sdn_detect's flood test."""
        pack = flood_pack(family, url)
        got = pieces(page(client(), pack))
        port = drawn(got.values(), r"^sdn:\d+ Port 1 ")
        assert "Port 1 cited by the detection : received 2,000.0 packets/s (" in port, port
        assert re.search(r"sent [\d,.]+ packets/s \([\d,.]+ bytes/s\); dropped [\d,]+ received, "
                         r"[\d,]+ sent\. Over 5\.0 s \(asked 5\.0 s apart\): 10,000 packets and "
                         r"[\d,]+ bytes in, [\d,]+ packets and [\d,]+ bytes out\.", port), port
        det = got["sdn:1"]
        assert "Measured: packets received a second, 2,000.0 pps, over a 5.0 s sample, held " \
               "30" in det, det
        assert "5 × a baseline of 100.0 pps over 5 collections, at least 10.0 pps; window " \
               "30 s (sdn_flood_factor, sdn_flood_window_seconds)" in det
        assert f"From {src} to " in det and ", on port 1 " in det

    def test_no_sdn_piece_is_a_bare_reference(self):
        """The C1867 defect: every piece of the section drew its reference alone."""
        pack = scan_pack(TD.V4_L4)
        got = pieces(page(client(), pack))
        assert len(got) == len(EP.resolve(pack, "sdn")["pieces"]) >= 28
        bare = {ref: w for ref, w in got.items() if len(w.split()) < 6}
        assert not bare, bare

    def test_the_coverage_piece_says_the_switch_s_granularity(self):
        got = pieces(page(client(), scan_pack(TD.V4_L4)))
        cov = drawn(got.values(), r"^sdn:\d+ Flow granularity")
        assert re.search(r"Flow granularity on this switch: L4 \(\d+ L2, \d+ L3, \d+ L4, \d+ "
                         r"none\): flows match transport ports", cov), cov


class TestTheWalk:
    def test_a_displaced_flow_names_its_response_and_when_installed(self, networks):  # noqa: F811
        pack = walk_pack("walk-unauthorised-s1")
        got = pieces(page(client(), pack))
        moved = drawn(got.values(), r"^sdn:\d+ Mercury.s flow, displaced")
        assert "missing" in moved and "cited by the detection" in moved
        assert "match eth_type=0x0800, ipv4_dst=192.0.2.3, ipv4_src=192.0.2.1 ; actions " \
               "METER:1, OUTPUT:3 ; hard 600 s; cookie 0x4d45997ed20d410a" in moved, moved
        assert "by a response: rate_limit_source, risk low, operation " \
               "sdnop-20261027T230520Z-12312caa" in moved
        det = got["sdn:1"]
        assert "Its effect, lifts : it lifts Mercury's flow" in det
        assert "Rests on: sdn:2 a flow, priority 300 · sdn:3 Mercury's flow, displaced" in det
        flow = got["sdn:2"]
        assert "476 packets, 749,908 bytes; installed 7 s before the read; no timeout" in flow

    def test_a_port_read_by_the_walk(self, networks):  # noqa: F811
        got = pieces(page(client(), walk_pack("walk-flood-1-s1")))
        port = drawn(got.values(), r"^sdn:\d+ Port ")
        assert re.search(r"received [\d,.]+ packets/s \([\d,.]+ bytes/s\), sent ", port), port

    def test_the_old_alert_source_is_drawn_as_sdn_detection(self, networks):  # noqa: F811
        """A pack built before C1867 says its alert was read from "the sdn reader"; a new one
        says SDN detection, and both are drawn as SDN detection."""
        pack = walk_pack("walk-flood-2-s1")
        assert EP.resolve(pack, "alert")["source"] == EP.SDN_ALERT_SOURCE
        old = json.loads(json.dumps(pack))
        old["id"] = "ep-c1867oldsource00"
        next(s for s in old["sections"] if s["name"] == "alert")["source"] = \
            "Grafana's alert state, as the sdn reader stored it"
        old.pop("hash")
        old["hash"] = EP.digest(old)
        assert EP.record(old)["ok"]
        for p in (pack, old):
            html = V.words(page(client(), p))
            assert "SDN detection: the alert as Mercury recorded it, read" in html
            assert "sdn reader" not in html and "Grafana" not in html


# ───────────────────────────────────────────────── the switch and meters

class TestTheSwitchAndItsMeters:
    def test_the_switch_by_dpid_and_name_and_the_meter_as_the_reader_read_it(self, reader_lab):
        html = page(reader_lab["client"], reader_lab["pack"])
        text = V.words(section_html(html))
        assert "Switch 0000000000000001 , s1 (the name it reports, as the SDN reader last read " \
               "it) , on controller lab-controller ." in text, text
        meters = V.words(re.search(r'<div class="pack-meters">.*?</div>', html, re.S).group(0))
        assert "not part of the pack: the collection reads flows and port counters" in meters
        assert re.search(r"Meter 1, named by sdn:3 \(METER:1\): as the SDN reader read it .*, "
                         r"after the pack was built: 1,000 kbit/s, drop above; its drop band, "
                         r"burst 100 kbit, 1,200 packets \(1,800,000 bytes\) dropped; 5,000 "
                         r"packets \(7,500,000 bytes\) in; 1 flow uses it\.", meters), meters
        assert 'href="#%s-sdn:3"' % reader_lab["pack"]["id"] in html
        head = V.words(re.search(r'<p class="pack-meta">.*?</p>', html, re.S).group(0))
        assert "SDN unauthorised flow on switch 0000000000000001 (s1) on lab-controller in " \
               "Default" in head and "SDN detection" in head

    @pytest.mark.parametrize("edit,said", [
        (lambda sw: sw.update(meters=[]),
         "switch s1 held no meter 1 when the SDN reader last read it"),
        (lambda sw: sw.update(meters=None, meters_read=False,
                              meters_error="HTTP 501: the switch's OpenFlow version does not "
                                           "support this request"),
         "not read: its meters were not read on this switch: HTTP 501"),
        (lambda sw: sw.update(dpid_hex="0000000000000009"),
         "not read: the SDN reader's read holds no switch 0000000000000001 on lab-controller"),
    ])
    def test_each_state_of_the_meter_s_read_is_said(self, reader_lab, monkeypatch, edit, said):
        real = sdn_page.stored

        def stored(network):
            got = json.loads(json.dumps(real(network)))
            edit(got["value"]["controllers"][0]["switches"][0])
            return got
        monkeypatch.setattr(sdn_page, "stored", stored)
        html = V.words(page(reader_lab["client"], reader_lab["pack"]))
        assert said in html, html

    @pytest.mark.parametrize("state,said", [
        ({"state": "never", "failed": ""}, "the SDN reader has not read this network yet"),
        ({"state": "unreadable", "why": "sdn-controllers.json could not be read"},
         "the SDN reader's store could not be read (sdn-controllers.json could not be read)"),
    ])
    def test_a_reader_with_nothing_to_say_names_why(self, reader_lab, monkeypatch, state, said):
        monkeypatch.setattr(sdn_page, "stored", lambda network: state)
        html = V.words(page(reader_lab["client"], reader_lab["pack"]))
        assert f"Switch 0000000000000001 , on controller lab-controller , its name not known: " \
               f"{said} ." in html, html
        assert f"Meter 1, named by sdn:3 (METER:1): not read: {said}." in html

    def test_a_grafana_pack_has_no_sdn_view(self):
        assert EP.sdn_view({"store": "grafana-alerts", "sections": []}) == {}


# ──────────────────────────────────────────────────────────────── the tab

@pytest.mark.usefixtures("detect_lab")
class TestTheSource:
    def test_the_tab_names_the_source_sdn_detection_and_the_card_its_switch(self):
        TD.observe(TD.T0)
        html = V.words(client().get("/v2/monitoring/alerts/list").get_data(as_text=True))
        assert "SDN detection Mercury's SDN detections as last judged" in html, html
        assert "switch 0000000000000001 on ctl-1 in Default · SDN unauthorised flow SDN " \
               "detection" in html
        assert "sdn reader" not in html and "(sdn)" not in html and "no one device" not in html

    def test_an_unreadable_sdn_detection_is_said_as_such(self, detect_lab):
        (detect_lab / D.STATE_FILE).write_text("{torn", encoding="utf-8")
        html = V.words(client().get("/v2/monitoring/alerts/list").get_data(as_text=True))
        assert "SDN detection could not be read. sdn_detect.json could not be read" in html
        assert "What it has found is not known, so no SDN detection is listed." in html
        assert "Grafana's alerts (sdn)" not in html

    def test_an_earlier_pack_names_its_switch(self):
        TD.observe(TD.T0)
        gone = [f for f in TD.captured_flows() if f["cookie"] != 0x4D45524300000002]
        TD.observe(TD.T0 + 10, flows=gone)
        html = V.words(client().get("/v2/monitoring/alerts/list").get_data(as_text=True))
        earlier = html[html.index("Earlier"):]
        assert "switch 0000000000000001 on ctl-1 in Default · SDN unauthorised flow" in earlier
