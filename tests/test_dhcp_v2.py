"""SOURCE OF TRUTH › DHCP on v2 (C529 step 1, board A), through the real routes and templates,
drawing the DHCP reader's value built from the lab's Kea answers (tests/fixtures/kea/, through
tests/test_dhcp_reader's FakeKea). What board A draws (docs/fidelity/dhcp.md compares it region
by region; this checks what each region holds):

- the sidebar's DHCP opens the page, under SOURCE OF TRUTH after NetBox;
- the header names the network; the counts and the read (each family, Kea's version);
- Subnets: each as Kea runs it, pools, lease times and "the same as Kea's global", in use of
  the pool's size, ZTP's subnet named;
- Leases: grouped by subnet, collapsed unless flagged or asked; search and the board's filters
  showing a subset and saying so; an identity holding several leases flagged; a device in the
  inventory linked; "As the host holds it" never blank;
- Reservations: what each does now (planted: the lab's Kea had none);
- Exclusions: what Kea cannot do and when Mercury's arrive;
- a family Kea did not answer: drawn as last read with its error; never read: not drawn as none;
- no read stored, an unreadable store, Kea not configured: each its own words.
"""

import json
import os
import re

import pytest

from modules import reader_job
from modules.readers import dhcp as D
from tests.test_dhcp_reader import FakeKea


def _value(**kw):
    return D.read("Lab", kea=kw.pop("kea", FakeKea()), clock=lambda: 1791680000,
                  previous=kw.pop("previous", {}), ztp_ids=[255])


def _store(value, ok=True, error=""):
    path = reader_job.store_path("dhcp")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    doc = {"last_attempt": {"at": "2026-10-11T01:38:20Z", "ok": ok, "error": error}}
    if value is not None:
        doc["last_good"] = {"value": value, "value_at": "2026-10-11T01:38:20Z"}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh)
    return path


@pytest.fixture
def web(tmp_path, monkeypatch):
    (tmp_path / "lab").mkdir()
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(tmp_path / "lab"))
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    monkeypatch.setattr("modules.dhcp_page._devices", lambda name: set())
    # The network's store, as Logs' tests do: Kea's group resolves to the plain store here.
    monkeypatch.setattr("modules.reader_job.read_cached_for",
                        lambda name, list_name: reader_job.read_cached(name))
    path = _store(_value())
    import app as A
    yield {"client": A.app.test_client(), "path": path, "monkeypatch": monkeypatch}
    if os.path.exists(path):
        os.remove(path)


def _get(web, query=""):
    return web["client"].get(f"/v2/dhcp/view?list=Lab{query}").get_data(as_text=True)


def test_the_sidebar_opens_it_under_source_of_truth(web):
    html = web["client"].get("/v2/dhcp?list=Lab").get_data(as_text=True)
    side = html[html.index("SOURCE OF TRUTH"):]
    assert side.index(">NetBox<") < side.index(">DHCP<") < side.index(">Credentials<")
    assert 'aria-current="page"' in side[:side.index(">Credentials<")]
    assert "not built yet" not in html[:html.index("SOURCE OF TRUTH")]
    assert 'hx-trigger="nmas:dhcp from:body"' in html


def test_the_header_counts_and_the_read(web):
    html = _get(web)
    assert "network: Lab" in html and "/v2/help/dhcp" in html
    assert re.search(r"<strong>6</strong> subnets <span class=\"faint\">\(3 IPv4 incl\. ZTP, "
                     r"3 IPv6\)</span>", html)
    assert "<strong>9</strong> active leases" in html
    assert "<strong>0</strong> reservations" in html
    assert re.search(r'<span class="mono">dhcp4</span> and <span class="mono">dhcp6</span>, '
                     r"Kea 2\.4\.1\) by the DHCP reader", html)


def test_subnets_as_kea_runs_them(web):
    html = _get(web)
    assert "10.10.10.100 – 10.10.10.200" in html and "2001:db8:30::/64" in html
    # The lab's lease times are set once, globally (measured): never "inherited".
    assert html.count("the same as Kea's global") == 6 and "inherited" not in html
    assert "365 d · – · 182.5 d · 319.4 d" in html          # IPv4: no preferred lifetime
    assert "365 d · 365 d · 182.5 d · 319.4 d" in html
    assert re.search(r"10\.10\.10\.0/24</td>\s*<td class=\"mono\">10</td>", html)
    assert "2 of 101" in html                               # .100 to .200 inclusive
    assert re.search(r"10\.255\.0\.0/24 <span[^>]*>ZTP</span>", html)
    assert "no pool: ZTP answers only its reservations" in html and "0 asking" in html


def test_leases_grouped_collapsed_and_flagged(web):
    html = _get(web, "&tab=lea")
    groups = re.findall(r'<details class="dh-grp"[^>]*>', html)
    assert len(groups) == 6
    # IPv6 subnet 10: four leases, three to one DUID (h1's drift, board A), so it opens.
    opened = [g for g in groups if " open" in g]
    assert len(opened) == 1 and 'data-keep="dh-dhcp6-10"' in opened[0]
    assert "3 share one DUID" in html
    # Board A: one client's leases together, "the same DUID" after the first, the drift said
    # once beside them, the DUID-LL read for the MAC it was made from.
    assert html.count("<strong>3 addresses for one client.</strong>") == 1
    assert html.count("the same DUID") == 2
    assert "DUID 00:03:00:01:aa:c1:ab:99:f6:e2 <span class=\"faint\">(DUID-LL, from MAC " \
           "aa:c1:ab:99:f6:e2)</span>" in html
    six = re.search(r'data-keep="dh-dhcp6-10".*?</details>', html, re.S).group(0)
    addresses = re.findall(r'<td class="mono dh-addr">([^<]+)</td>', six)
    assert addresses == ["2001:db8:10::101", "2001:db8:10::105", "2001:db8:10::107",
                         "2001:db8:10::103"]
    assert "not readable: a host the tool does not reach" in html


def test_a_filter_or_a_search_shows_a_subset_and_says_so(web):
    html = _get(web, "&tab=lea&show=shared")
    assert "Showing 3 of 9 leases, sharing an identity." in html and "Show all" in html
    html = _get(web, "&tab=lea&q=10.10.20.101")
    assert "Showing 1 of 9 leases matching 10.10.20.101." in html
    assert "10.10.20.101" in html and "10.10.10.100" not in html


def test_a_device_in_the_inventory_is_linked_and_its_own_lease_pending(web):
    """Planted: a lease's hostname as a device of the network (the lab's hosts are not)."""
    first = _value()["families"]["dhcp4"]["leases"][0]
    web["monkeypatch"].setattr("modules.dhcp_page._devices", lambda name: {"r9"})
    value = _value()
    value["families"]["dhcp4"]["leases"][0]["hostname"] = "r9"
    _store(value)
    html = _get(web, f"&tab=lea&q={first['address']}")
    assert '<a href="/v2/device/r9?list=Lab">r9</a>' in html
    assert "pending: reading the device’s own lease is designed, not built" in html


def test_reservations_say_what_each_does_now(web):
    """Planted (the lab's Kea had none at the capture): h1's reservation in use; h2's waiting
    for a MAC no client asks with while a client named h2 holds a pool address (board A's
    unmatched h2); one nobody has asked for."""
    leases = {l["address"]: l for l in _value()["families"]["dhcp4"]["leases"]}

    def plant(svc, result):
        conf = result[0]["arguments"]["Dhcp4" if svc == "dhcp4" else "Dhcp6"]
        if svc == "dhcp4":
            conf["subnet4"][0]["reservations"] = [
                {"hw-address": leases["10.10.10.100"]["mac"], "ip-address": "10.10.10.100",
                 "hostname": "h1"},
                {"hw-address": "aa:c1:ab:00:00:99", "ip-address": "10.10.10.150",
                 "hostname": "h9"}]
            conf["subnet4"][1]["reservations"] = [
                {"hw-address": "aa:c1:ab:3e:11:00", "ip-address": "10.10.20.110",
                 "hostname": "h2"}]
        return result
    value = _value(kea=FakeKea(plant=plant))
    value["families"]["dhcp4"]["leases"] = [
        dict(l, hostname="h2") if l["address"] == "10.10.20.101" else l
        for l in value["families"]["dhcp4"]["leases"]]
    _store(value)
    html = _get(web, "&tab=res")
    assert "in use by it" in html and "no request yet" in html
    assert ("no client has asked with this MAC; a client named h2 asked as "
            f"{leases['10.10.20.101']['mac']} and was given 10.10.20.101 from the pool") in html
    head = _get(web)
    assert "1 reservation unmatched" in head
    assert "1 from the pool where a reservation exists" in _get(web, "&tab=lea")


def test_exclusions_say_what_kea_cannot_do(web):
    html = _get(web, "&tab=exc")
    assert "Kea has no excluded-address setting" in html and "C529 step 3" in html


def test_a_family_not_answered_is_drawn_as_last_read_with_its_error(web):
    good = _value()
    _store(_value(kea=FakeKea(fail={("dhcp6", "lease6-get-all")}), previous=good))
    html = _get(web)
    assert "IPv6 (dhcp6) could not be read:</strong> Kea&#39;s dhcp6 could not be asked " \
           "(lease6-get-all)" in html and "Drawn below as last read" in html
    _store(_value(kea=FakeKea(fail={("dhcp6", "config-get")})))
    html = _get(web)
    assert "Nothing of IPv6 has been read yet" in html
    assert "<strong>3</strong> subnets <span class=\"faint\">(3 IPv4 incl. ZTP, 0 IPv6)" in html


@pytest.mark.parametrize("value,words", [
    (None, "The DHCP reader has not read Kea yet"),
    ({"configured": False}, "Kea is not configured for this network"),
])
def test_each_state_has_its_words(web, value, words):
    _store(value)
    assert words in _get(web)


def test_an_unreadable_store_draws_nothing(web):
    with open(web["path"], "w", encoding="utf-8") as fh:
        fh.write("{not json")
    html = _get(web)
    assert "store cannot be read" in html and "<table" not in html
