"""One title per incident, the problem's (C3727; the operator's R4, 2026-11-14: "titles the
incident by it, BLUF-style ... not "alert 'Critical syslog received' firing""; and on r7's page,
2026-11-15: the heading "r7: 2 telemetry streams lost" beside the bottom line's "r7: telemetry
streams 101 and 102 lost": "the page draws one, the problem's").

Measured on the host before this change (2026-11-15 02:18 UTC, all 32 incidents): Troubleshoot ›
Incidents and the page's heading titled each incident by its signal. Here, through the real app
on the heal's lab (tests/test_incident_page.py's planted incidents, each by the heal modules' own
writers, tests/test_incident_titles.py's `PLANTS`), and two more kinds sighted by the incidents
store's own writer: a lost telemetry stream (two alerts, 101 and 102) and an alert Mercury has
not classified. No device, no network.

- **Every incident kind says one title:** its row on Troubleshoot › Incidents, its page's
  heading (and its window's title) and its bottom line's What happened are one string
  (`incident_page.title`, from `bluf.what_of`); a closed incident's heading adds only how it
  ended. A lost stream's is its problem's ("edge-b: telemetry streams 101 and 102 lost"), never
  its signal's count; an alert's never names the alert's rule.
- **The signal stays as evidence:** the alerts the problem was classified from are listed in
  the evidence's one home, under the bottom line.
- **The scan is shown able to fail:** a heading planted with the signal's words is found.
"""
import re
from html import unescape

import pytest

from modules import incident_page as IP
from tests import test_incident_page as T
from tests import test_incident_titles as TT
from tests.test_heal_decide import lab  # noqa: F401  (the fixture `client` builds on)
from tests.test_heal_diagnose_stream import stream_alert
from tests.test_heal_policy import T0
from tests.test_heal_propose import measured  # noqa: F401  (a fixture)
from tests.test_incident_page import client, no_host_addresses  # noqa: F401  (fixtures)
from tests.test_sdn_connections import networks  # noqa: F401  (the fixture `lab` builds on)

NET = T.NET


def lost_stream():
    """edge-b's lost telemetry streams 101 and 102, sighted by the incidents store's writer."""
    got = None
    for n, sub in enumerate(("101", "102")):
        t = dict(stream_alert(sub), epoch=T0 - 1000 + n, rule=f"NMAS telemetry stream lost: "
                 f"edge-b subscription {sub}", words=f"the alert fired on edge-b (subscription "
                 f"{sub})")
        got = T.I.sight(NET, "edge-b", t, now=T0 - 1000 + n)
    return got["incident"]


def unclassified_alert():
    t = {"kind": "alert", "key": "alert:crit-syslog", "epoch": T0 - 1000, "at": "",
         "rule": "Critical syslog received", "interface": "",
         "words": "the alert Critical syslog received fired on edge-b"}
    return T.I.sight(NET, "edge-b", t, now=T0 - 1000)["incident"]


KINDS = dict(TT.PLANTS, lost_stream=lost_stream, alert=unclassified_alert)


def heading(body: str) -> str:
    return T.text_of(body.split('<h1 id="inc-title">', 1)[1].split("</h1>", 1)[0])


def bluf_what(body: str) -> str:
    """The bottom line's What happened, without its since."""
    dd = body.split('data-bluf="what"', 1)[1].split("<dd>", 1)[1].split("</dd>", 1)[0]
    dd = re.sub(r'<span class="muted small">since .*?</span>', "", dd, flags=re.S)
    return T.text_of(dd)


def listed(client, iid: str) -> str:
    """The incident's row title on Troubleshoot › Incidents (its tab, open or closed)."""
    for tab in ("open", "closed"):
        body = unescape(client.get(f"/v2/incidents?list={NET}&tab={tab}").get_data(
            as_text=True))
        m = re.search(rf'<a class="inc-row-title" href="/v2/incident/{iid}[^"]*"[^>]*>(.*?)</a>',
                      body, re.S)
        if m:
            return T.text_of(m.group(1))
    return ""


def disagreements(row: str, h1: str, what: str, resolved: bool) -> list:
    """How the three titles disagree: the row and the heading are one string; the bottom line's
    What happened is it, or (a closed incident) what it begins with."""
    out = []
    if row != h1:
        out.append(f"the list says {row!r}, the heading {h1!r}")
    if not (what == h1 or (resolved and h1.startswith(what))):
        out.append(f"the bottom line says {what!r}, the heading {h1!r}")
    return out


class TestEveryKindSaysOneTitle:
    @pytest.mark.parametrize("name", sorted(KINDS))
    def test_the_list_the_heading_and_the_bottom_line_agree(self, client, measured, name):  # noqa: F811
        iid = KINDS[name]()
        body = T.page(client, iid)
        h1 = heading(body)
        assert h1 == IP.title(*T.model(iid)), (h1, name)
        resolved = 'data-inc-state="fixed"' in body or 'data-inc-state="cleared"' in body \
            or 'data-inc-state="cancelled"' in body
        assert disagreements(listed(client, iid), h1, bluf_what(body), resolved) == [], name
        assert unescape(body.split("<title>", 1)[1].split(" · ", 1)[0]) == h1

    def test_a_lost_stream_is_titled_by_its_problem_its_alerts_its_evidence(self, client):  # noqa: F811
        iid = lost_stream()
        body = T.page(client, iid)
        assert heading(body) == "edge-b: telemetry streams 101 and 102 lost"
        assert "2 telemetry streams lost" not in heading(body)
        ev = body.split('id="inc-evidence"', 1)[1].split("</details>", 1)[0]
        assert "subscription 101" in ev and "subscription 102" in ev, "the signals are evidence"

    def test_an_alert_is_never_titled_by_its_rule(self, client):  # noqa: F811
        iid = unclassified_alert()
        body = T.page(client, iid)
        assert "Critical syslog received" not in heading(body), heading(body)
        assert heading(body) == "edge-b: an alert Mercury has not classified yet"
        ev = body.split('id="inc-evidence"', 1)[1].split("</details>", 1)[0]
        assert "Critical syslog received" in unescape(ev), "the alert is the evidence"


class TestTheScanCanFail:
    def test_a_heading_with_the_signal_s_words_is_found(self):
        got = disagreements("edge-b: telemetry streams 101 and 102 lost",
                            "edge-b: 2 telemetry streams lost",
                            "edge-b: telemetry streams 101 and 102 lost", False)
        assert len(got) == 2, got
