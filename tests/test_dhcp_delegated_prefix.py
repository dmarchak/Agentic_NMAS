"""C2090: a delegated prefix (DHCPv6 IA_PD) is drawn with its length, ``<address>/<prefix_len>``,
wherever DHCP › Leases names a lease, and found by that form.

Kea answers an IA_PD lease with the prefix's first address in ``ip-address`` and its length in
``prefix-len`` (an IA_NA lease carries no ``prefix-len``: the lab's captured lease6-get-all,
tests/fixtures/kea/). The Leases tab drew ``ip-address`` alone, so a delegated /56 read as one
address. The lab's Kea delegates nothing (its subnets' ``pd-pools`` are empty at the capture),
so the delegation is PLANTED, as a minimal edit of a captured lease: the IPv6 client of subnet 30
(its DUID, IAID and times as captured) given an IA_PD lease of ``2001:db8:8000:100::/56`` in
subnet 20, from a pd-pool planted on subnet 20 (``2001:db8:8000::/48`` by /56). Every other lease
is the capture, unchanged, both families.

What is held, each through the real reader, page and routes:

- the reader carries a length for an IA_PD lease only (`dhcp_leases.delegated_len`, the one rule);
- the Leases tab draws the prefix with its length, an IA_NA address and every IPv4 lease as
  before, and Release lease…'s label names the prefix;
- Find matches the prefix by the form it is drawn in;
- the release card names the prefix with its length (title, the lease, the confirm), sends
  ``lease6-del`` with the address and type IA_PD as Kea takes it, and records the prefix;
- a delegated prefix's length is bound by the preview's hash; an address's hash binds what it
  bound before.
"""

import copy
import json
import os
import re
from urllib.parse import urlencode

import pytest

from modules import dhcp_leases as L
from modules.readers import dhcp as D
from tests.test_dhcp_leases import LeaseKea, _as_person, _recorder
from tests.test_dhcp_reader import FakeKea as ReaderKea
from tests.test_dhcp_reservations import kea_dir  # noqa: F401 (the fixture)
from tests.test_dhcp_v2 import _store, _value, web  # noqa: F401 (the fixture)

#: C1522: its tests write reader stores; each test keeps them in its own folder.
pytestmark = pytest.mark.usefixtures("reader_stores_in_tmp")

KEA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "kea")
PREFIX, LENGTH = "2001:db8:8000:100::", 56
SHOWN = f"{PREFIX}/{LENGTH}"
PD = {"family": "IPv6", "address": PREFIX}
NA = {"family": "IPv6", "address": "2001:db8:10::103"}


def _captured(name):
    with open(os.path.join(KEA, name), encoding="utf-8") as fh:
        return json.load(fh)


def _pd_lease() -> dict:
    """The captured lease of subnet 30's client, made a delegation in subnet 20: three edits."""
    leases = _captured("dhcp6-lease6-get-all.json")[0]["arguments"]["leases"]
    lease = copy.deepcopy(next(x for x in leases if x["ip-address"] == "2001:db8:30::103"))
    lease.update({"type": "IA_PD", "ip-address": PREFIX, "prefix-len": LENGTH, "subnet-id": 20})
    return lease


def _with_pd(answer: dict) -> dict:
    """A lease6-get-all answer with the delegation added after the captured leases."""
    answer = copy.deepcopy(answer)
    entry = answer[0] if isinstance(answer, list) else answer
    entry["arguments"]["leases"].append(_pd_lease())
    entry["text"] = f"{len(entry['arguments']['leases'])} IPv6 lease(s) found."
    return answer


def _pd_pool(svc, result):
    """Subnet 20's pd-pool, planted (the capture's are empty)."""
    if svc == "dhcp6":
        for s in result[0]["arguments"]["Dhcp6"]["subnet6"]:
            if s["id"] == 20:
                s["pd-pools"] = [{"prefix": "2001:db8:8000::", "prefix-len": 48,
                                  "delegated-len": LENGTH, "option-data": []}]
    return result


class DelegatingKea(ReaderKea):
    """The reader's Kea as captured, delegating the planted prefix."""

    def __init__(self):
        super().__init__(plant=_pd_pool)

    def command(self, cmd, svc):
        got = super().command(cmd, svc)
        if got.get("ok") and cmd == "lease6-get-all":
            got = dict(got, result=_with_pd(got["result"]))
        return got


# ── the reader ──────────────────────────────────────────────────────────────────────────────

class TestTheReader:
    def test_an_ia_pd_lease_carries_its_length_and_an_address_none(self):
        v = D.read("Lab", kea=DelegatingKea(), clock=lambda: 1791680000, previous={},
                   ztp_ids=[255])
        six = v["families"]["dhcp6"]["leases"]
        pd = [x for x in six if x["address"] == PREFIX]
        assert len(pd) == 1 and pd[0]["prefix_len"] == LENGTH and pd[0]["type"] == "IA_PD"
        assert [x["prefix_len"] for x in six if x["type"] == "IA_NA"] == [None] * 6
        assert {x["prefix_len"] for x in v["families"]["dhcp4"]["leases"]} == {None}
        assert v["families"]["dhcp6"]["subnets"][1]["pd_pools"] == ["2001:db8:8000::/48 by /56"]

    def test_only_an_ia_pd_lease_is_a_prefix(self):
        """The one rule (`delegated_len`): a length on any other lease is not a delegation."""
        na = _captured("dhcp6-lease6-get-all.json")[0]["arguments"]["leases"][0]
        v4 = _captured("dhcp4-lease4-get-all.json")[0]["arguments"]["leases"][0]
        assert L.delegated_len(_pd_lease()) == LENGTH
        assert L.delegated_len(na) is None
        assert L.delegated_len(dict(na, **{"prefix-len": 128})) is None
        assert L.delegated_len(v4) is None
        assert L.delegated_len(dict(_pd_lease(), **{"prefix-len": None})) is None


# ── DHCP › Leases ───────────────────────────────────────────────────────────────────────────

def _leases_tab(web, query=""):  # noqa: F811 (the fixture imported above)
    _store(_value(kea=DelegatingKea()))
    return web["client"].get(f"/v2/dhcp/view?list=Lab&tab=lea{query}").get_data(as_text=True)


def _cells(html, group):
    part = re.search(rf'data-keep="dh-{group}".*?</details>', html, re.S).group(0)
    return re.findall(r'<td class="mono dh-addr"[^>]*>([^<]+)</td>', part)


def test_a_delegated_prefix_is_drawn_with_its_length(web):  # noqa: F811
    html = _leases_tab(web)
    assert _cells(html, "dhcp6-20") == ["2001:db8:20::101", SHOWN]
    cell = re.search(rf'<td class="mono dh-addr"[^>]*>{re.escape(SHOWN)}</td>', html).group(0)
    assert 'title="A prefix delegated to the client (DHCPv6 IA_PD)"' in cell
    assert f'aria-label="Release the lease on {SHOWN}"' in html


def test_an_ipv6_address_and_an_ipv4_lease_are_drawn_as_before(web):  # noqa: F811
    html = _leases_tab(web)
    assert _cells(html, "dhcp6-10") == ["2001:db8:10::101", "2001:db8:10::105",
                                        "2001:db8:10::107", "2001:db8:10::103"]
    assert _cells(html, "dhcp6-30") == ["2001:db8:30::103"]
    assert _cells(html, "dhcp4-10") == ["10.10.10.100", "10.10.10.102"]
    assert _cells(html, "dhcp4-20") == ["10.10.20.101"]
    assert html.count("A prefix delegated to the client") == 1
    assert 'aria-label="Release the lease on 2001:db8:10::103"' in html
    assert 'aria-label="Release the lease on 10.10.10.102"' in html


@pytest.mark.parametrize("q", [SHOWN, f"/{LENGTH}", "2001:DB8:8000:100::/56"],
                         ids=["the-prefix", "its-length", "upper-case"])
def test_find_matches_a_delegated_prefix_by_its_drawn_form(web, q):  # noqa: F811
    html = _leases_tab(web, "&" + urlencode({"q": q}))
    assert f"Showing 1 of 10 leases matching {q}." in html, re.findall(r"Showing[^<]+", html)
    assert re.findall(r'<td class="mono dh-addr"[^>]*>([^<]+)</td>', html) == [SHOWN]


def test_find_still_matches_an_address(web):  # noqa: F811
    html = _leases_tab(web, "&q=2001:db8:10::103")
    assert "Showing 1 of 10 leases matching 2001:db8:10::103." in html
    assert re.findall(r'<td class="mono dh-addr"[^>]*>([^<]+)</td>', html) == ["2001:db8:10::103"]


# ── Release lease… ──────────────────────────────────────────────────────────────────────────

@pytest.fixture
def kea(kea_dir):  # noqa: F811 (the fixture imported above)
    k = LeaseKea(kea_dir["files"])
    k.leases["dhcp6"] = _with_pd(k.leases["dhcp6"])
    return k


class TestTheReleaseCard:
    def test_the_preview_names_the_prefix_with_its_length(self, kea):
        p = L.plan("Lab", PD, kea=kea)
        assert p["ok"], p["refused"]
        assert p["address"] == PREFIX and p["shown"] == SHOWN
        assert p["title"] == f"Release {SHOWN}"
        assert p["change"][0][1].startswith(f"lease {SHOWN} (IPv6, DUID "
                                            "00:03:00:01:aa:c1:ab:12:c6:03, ends ")
        assert p["subject"] == (f"dhcp: IPv6 lease {SHOWN} released "
                                "(00:03:00:01:aa:c1:ab:12:c6:03)")

    def test_an_address_s_preview_is_as_before(self, kea):
        p = L.plan("Lab", NA, kea=kea)
        assert p["ok"], p["refused"]
        assert p["shown"] == p["address"] == "2001:db8:10::103"
        assert p["title"] == "Release 2001:db8:10::103"
        assert p["change"][0][1].startswith("lease 2001:db8:10::103 (IPv6, DUID ")
        v4 = L.plan("Lab", {"family": "IPv4", "address": "10.10.10.102"}, kea=kea)
        assert v4["shown"] == "10.10.10.102" and v4["title"] == "Release 10.10.10.102"

    def test_its_checks_speak_of_the_prefix_and_its_delegation_pool(self, kea):
        p = L.plan("Lab", PD, kea=kea)
        texts = [t for _s, t in p["checks"]]
        assert "whether the client still uses the prefix" in texts[0]
        assert texts[1] == (f"no reservation names {SHOWN}: the prefix returns to the subnet's "
                            "delegation pool, if it lies in one")
        na = [t for _s, t in L.plan("Lab", NA, kea=kea)["checks"]]
        assert "whether the client still uses the address" in na[0]
        assert na[1] == ("no reservation names 2001:db8:10::103: the address returns to the "
                         "subnet's pool, if it lies in one")

    def test_a_reserved_prefix_is_found_by_kea_s_prefixes_in_any_spelling(self, kea):
        """Planted: subnet 20 reserving the prefix for its client, as Kea's `prefixes` holds
        it (written in another spelling); an address reservation of the prefix's first address
        does not reserve the prefix."""
        duid = "00:03:00:01:aa:c1:ab:12:c6:03"
        kea.loaded["dhcp6"][20] = [{"duid": duid, "ip-addresses": [PREFIX]}]
        p = L.plan("Lab", PD, kea=kea)
        assert p["checks"][1][1].startswith(f"no reservation names {SHOWN}")
        kea.loaded["dhcp6"][20] = [{"duid": duid, "prefixes": ["2001:DB8:8000:100:0::/56"]}]
        p = L.plan("Lab", PD, kea=kea)
        assert p["checks"][1] == ("note", f"reserved for DUID {duid} (this client): the "
                                          "reservation stays, and Kea gives the prefix to that "
                                          "client at its next request"), p["checks"]

    def test_the_hash_binds_a_prefix_s_length_and_an_address_s_as_before(self, kea):
        pd = L.plan("Lab", PD, kea=kea)
        assert L.bound(pd["lease"])["prefix_len"] == LENGTH
        na = L.plan("Lab", NA, kea=kea)
        assert sorted(L.bound(na["lease"])) == sorted(
            ("family", "address", "by", "identity", "mac", "type", "iaid", "subnet_id"))
        # The same prefix delegated again with another length is another lease: refused.
        lease = next(x for x in kea._leases("dhcp6") if x["ip-address"] == PREFIX)  # noqa: SLF001
        lease["prefix-len"] = 60
        got = L.apply("Lab", PD, pd["hash"], actor="op", reason="gone", kea=kea,
                      record_with=_recorder([]))
        assert not got["ok"] and f"Kea's lease on {PREFIX}/60 moved since" in got["error"]
        assert kea.dels == []

    def test_the_release_sends_the_address_and_type_and_records_the_prefix(self, kea):
        kept = []
        h = L.plan("Lab", PD, kea=kea)["hash"]
        got = L.apply("Lab", PD, h, actor="op@example.invalid", reason="router replaced",
                      kea=kea, record_with=_recorder(kept))
        assert got["ok"], got["error"]
        assert kea.dels == [("lease6-del", {"ip-address": PREFIX, "type": "IA_PD"})]
        assert got["read_back"] == f"Kea holds no lease on {SHOWN} for " \
                                   "00:03:00:01:aa:c1:ab:12:c6:03"
        assert kept[0][2]["subject"] == f"dhcp: IPv6 lease {SHOWN} released " \
                                        "(00:03:00:01:aa:c1:ab:12:c6:03)"


@pytest.fixture
def page(web, kea, monkeypatch):  # noqa: F811 (the fixtures above)
    monkeypatch.setattr("modules.integrations.kea.KeaIntegration", lambda **kw: kea)
    monkeypatch.setattr(L, "record", _recorder([]))
    return dict(web, kea=kea)


def _card(page, values):
    return page["client"].get("/v2/dhcp/lease?" + urlencode(dict(values, list="Lab"))) \
        .get_data(as_text=True)


def test_the_card_names_the_prefix_where_it_names_the_lease(page, monkeypatch):
    _as_person(monkeypatch)
    html = _card(page, PD)
    assert f'<h2 id="dh-op-h">Release {SHOWN}</h2>' in html
    assert f"- lease {SHOWN} (IPv6, DUID " in html
    assert f'<span class="op-idle">Release {SHOWN}</span>' in html
    # The command as Kea takes it: the prefix's address (its type sent beside it).
    assert f'<span class="mono">lease6-del {PREFIX}</span>' in html


def test_an_address_s_card_is_as_before(page, monkeypatch):
    _as_person(monkeypatch)
    html = _card(page, NA)
    assert '<h2 id="dh-op-h">Release 2001:db8:10::103</h2>' in html
    assert '<span class="op-idle">Release 2001:db8:10::103</span>' in html
    assert "/56" not in html and "IA_PD" not in html
