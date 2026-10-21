"""Devices › Onboard devices › Discovered (board L; `routes/onboard_v2.py`, `modules/
discovery_page.py`, `templates/v2/_onboard_discovered.html`): drawn from the discovery reader's
stored value, built by the reader's own `shape` from the host's Kea as captured with the range
the host step added (pools as Kea reports them), and leases from the capture with minimal edits.

- never read, and a range Kea does not run, each say so first; nothing is drawn as empty;
- the counts lead; asking now is open, the other groups collapsed, each with its own columns;
- a device's next request is its own cadence, and one seen once says its cadence is not known;
- Pick… opens Add device in place with the MAC and the ZTP way;
- the vendor filter and the search narrow every group and the page says it shows a subset;
- the region redraws on the reader's announcement.
"""

import html
import json
import os

import pytest

from modules import reader_job
from modules.readers import ztp_discovery as Z
from tests.test_ztp_discovery_reader import (ADDRS, NOW, PLAIN, PNP, _captured, _config,
                                             _lease)

#: C1522: its tests write reader stores, or wake readers that do; each test keeps them
#: in its own folder.
pytestmark = pytest.mark.usefixtures("reader_stores_in_tmp")

QUIET = "52:54:00:77:0e:31"
PICKED = "52:54:00:51:aa:02"
OTHER = "0c:d1:9e:44:02:b0"


def value(now=NOW):
    """Board L's three groups: three asking (two sending ciscopnp, one seen with a cadence), one
    picked (reserved, still on its discovery lease), one gone quiet."""
    config = _config()
    ztp = next(s for s in config["subnet4"] if s["id"] == 255)
    ztp["reservations"] = [{"hw-address": PICKED, "ip-address": "10.255.0.18"}]
    first = Z.shape(config, _captured() + [
        _lease("10.255.0.192", PNP, now - 21 * 60), _lease("10.255.0.208", PLAIN, now - 300),
        _lease("10.255.0.193", OTHER, now - 120, "cisco-0cd1.9e44.02b0-Gi1"),
        _lease("10.255.0.194", PICKED, now - 4000), _lease("10.255.0.209", QUIET, now - 6120)],
        {}, now - 20 * 60, {PICKED: ("r9", "2026-10-11T20:52:00Z")}, ADDRS)
    return Z.shape(config, _captured() + [
        _lease("10.255.0.192", PNP, now - 7), _lease("10.255.0.208", PLAIN, now - 60),
        _lease("10.255.0.193", OTHER, now - 3, "cisco-0cd1.9e44.02b0-Gi1"),
        _lease("10.255.0.194", PICKED, now - 40), _lease("10.255.0.209", QUIET, now - 6120)],
        first, now, {PICKED: ("r9", "2026-10-11T20:52:00Z")}, ADDRS)


def store(v, ok=True, error=""):
    path = reader_job.store_path(Z.READER_NAME)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    doc = {"last_attempt": {"at": "2026-10-11T23:20:00Z", "ok": ok, "error": error}}
    if v is not None:
        doc["last_good"] = {"value": dict(v, configured=True, read_at="2026-10-11T23:20:00Z"),
                            "value_at": "2026-10-11T23:20:00Z"}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh)


@pytest.fixture
def web(tmp_path, monkeypatch):
    (tmp_path / "lab").mkdir()
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(tmp_path / "lab"))
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    monkeypatch.setattr("modules.reader_job.read_cached_for",
                        lambda name, list_name: reader_job.read_cached(name))
    monkeypatch.setattr("modules.discovery_page.time.time", lambda: NOW)
    import app as A
    return {"client": A.app.test_client()}


def _page(web, query=""):
    got = web["client"].get(f"/v2/onboard/discovered?list=Lab{query}")
    assert got.status_code == 200
    return html.unescape(got.get_data(as_text=True))


def _region(web, query=""):
    got = web["client"].get(f"/v2/onboard/discovered/view?list=Lab{query}")
    assert got.status_code == 200
    return html.unescape(got.get_data(as_text=True))


class TestTheStates:

    def test_never_read_says_so(self, web):
        store(None, ok=False, error="Kea (dhcp4) could not be asked: refused")
        text = _page(web)
        assert "The discovery reader has not read Kea yet: its last attempt failed, Kea" in text
        assert "Asking now" not in text

    def test_a_range_kea_does_not_run_says_so_first(self, web):
        v = value()
        v["range"] = dict(v["range"], state="off", pools=[], problem="")
        store(v)
        assert "Kea runs no discovery range:" in _region(web)


class TestTheGroups:

    def test_the_counts_lead_and_each_group_has_its_columns(self, web):
        store(value())
        text = _region(web)
        assert "<strong>3</strong> asking now" in text
        assert "not listed: 1 MAC already reserved, 1 pending onboarding" in text
        assert '<details class="card dv-grp" id="dv-asking" data-keep="dv-asking" open>' in text
        assert "Picked, not taken (1)" in text and "Gone quiet (1)" in text
        assert "10.255.0.192/28, 10.255.0.208/28" in text
        assert "Stopped asking 1 h 42 min ago" in text
        assert ">r9</a>" in text and "Not taken yet:" in text

    def test_next_request_is_the_device_s_own_cadence(self, web):
        store(value())
        text = _region(web)
        assert "within 4 min" in text, "the plain device's one gap: 300 s ago, then 60 s ago"
        v = value()
        v["devices"][0]["gaps"] = []
        store(v)
        assert "one request seen: its cadence is not known yet" in _region(web)

    def test_pick_opens_add_device_with_the_mac_and_the_ztp_way(self, web):
        store(value())
        text = _region(web)
        assert f'hx-get="/v2/onboard/new?list=Lab&mac={PNP}"' in text
        form = html.unescape(web["client"].get(f"/v2/onboard/new?list=Lab&mac={PNP}")
                             .get_data(as_text=True))
        assert f'value="{PNP}"' in form
        assert '<option value="ztp" selected>' in form

    def test_a_mac_that_is_not_one_is_dropped(self, web):
        form = web["client"].get("/v2/onboard/new?list=Lab&mac=x\"><b>").get_data(as_text=True)
        assert "<b>" not in form and '<option value="static" selected>' in form


class TestTheFilter:

    def test_a_vendor_narrows_every_group_and_says_so(self, web):
        store(value())
        text = _region(web, "&vendor=ciscopnp")
        assert "Showing 3 of 5: vendor class ciscopnp." in text, "two asking and the picked one"
        assert PLAIN not in text and QUIET not in text

    def test_the_search_finds_a_client_id(self, web):
        store(value())
        text = _region(web, "&q=0cd1.9e44")
        assert "Showing 1 of 5: matching “0cd1.9e44”." in text and OTHER in text


def test_the_region_redraws_on_the_reader_s_announcement(web):
    store(value())
    assert 'hx-trigger="nmas:ztp_discovery from:body"' in _page(web)
