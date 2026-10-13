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
    assert re.search(r"10\.10\.10\.0/24<br><span class=\"faint small\">Kea id 10</span>", html)
    assert "2 of 101" in html                               # .100 to .200 inclusive
    assert re.search(r"10\.255\.0\.0/24 <span[^>]*>ZTP</span>", html)
    assert "no pool: ZTP answers only its reservations" in html and "0 asking" in html


def _e19(svc, result):
    """The capture as Kea answers after E19's host step (a minimal edit: the fixed timers gone
    from the global level and every subnet, the computed shares set, the classes added)."""
    from modules import dhcp_lifetimes as LT
    family = "IPv4" if svc == "dhcp4" else "IPv6"
    entry = result[0] if isinstance(result, list) else result
    root = entry["arguments"]["Dhcp4" if family == "IPv4" else "Dhcp6"]
    for scope in [root] + list(root.get(LT.SUBNET_KEYS[family]) or []):
        for key in ("renew-timer", "rebind-timer"):
            scope.pop(key, None)
        scope.update({"calculate-tee-times": True, "t1-percent": 0.5, "t2-percent": 0.8})
    root["client-classes"] = list(root.get("client-classes") or []) + [LT.reserved_class(family)]
    return result


def test_computed_timers_and_the_classes_lifetimes_are_said(web):
    """E19: once Kea computes renew and rebind, the cell says the shares, never a blank; the
    note under the table names each lifetime class and whom it serves."""
    _store(_value(kea=FakeKea(plant=_e19)))
    html = _get(web)
    assert "365 d · – · renew at 50% · rebind at 80% of each lease" in html
    assert "365 d · 365 d · renew at 50% · rebind at 80% of each lease" in html
    assert "182.5 d" not in html
    note = html[html.index("data-lifetime-classes"):]
    note = note[:note.index("</p>")]
    assert ("<span class=\"mono\">mercury-reserved</span> (IPv4, every client with a "
            "reservation, in every subnet) 7 d") in note
    assert ("<span class=\"mono\">mercury-reserved</span> (IPv6, every client with a "
            "reservation, in every subnet) 7 d · preferred 3.5 d") in note


def test_no_lifetime_class_draws_no_note(web):
    assert "data-lifetime-classes" not in _get(web)


def _subnet(value, prefix):
    """The reader value's subnet *prefix* (wherever the families keep it)."""
    stack = [value]
    while stack:
        x = stack.pop()
        if isinstance(x, dict):
            if x.get("prefix") == prefix and "pools" in x:
                return x
            stack.extend(x.values())
        elif isinstance(x, list):
            stack.extend(x)
    raise AssertionError(f"no subnet {prefix} in the value")


def test_a_pool_s_description_is_drawn_under_its_range(web):
    """C709 (board C revised): what a pool is for, under its range; none, nothing drawn."""
    value = _value()
    _subnet(value, "10.10.10.0/24")["pool_notes"] = ["lab hosts, VLAN 10"]
    _store(value)
    html = _get(web)
    assert ('10.10.10.100 – 10.10.10.200<br><span class="dh-pool-note">lab hosts, VLAN 10'
            '</span>') in html, html[html.find("10.10.10.100"):][:300]
    assert html.count('class="dh-pool-note"') == 1


def test_a_pool_mercury_holds_without_a_description_says_how_to_add_one(web):
    """Board C: a pool with none, on a subnet Mercury writes, says Edit… adds one; a subnet in
    Kea's own file (no Edit…) says nothing."""
    value = _value()
    value["families"]["dhcp4"]["held"] = {"10": "mercury", "20": "kea-file"}
    _subnet(value, "10.10.10.0/24")["pool_notes"] = [""]
    _store(value)
    html = _get(web)
    assert ('10.10.10.100 – 10.10.10.200<br><span class="dh-pool-note faint">no description: '
            'Edit… adds one</span>') in html, html[html.find("10.10.10.100"):][:300]
    assert html.count("no description: Edit… adds one") == 1


def test_the_reader_says_what_each_pool_is_for():
    """Its description in Kea's user-context, else its client class's words (ZTP's discovery
    pools), else nothing."""
    from modules.dhcp_discovery import ANY, PNP
    assert D.pool_note({"pool": "a - b", "user-context": {"description": "lab hosts"}}) == \
        "lab hosts"
    assert D.pool_note({"pool": "a - b", "client-class": PNP}) == \
        "discovery: Cisco PnP (vendor class ciscopnp)"
    assert D.pool_note({"pool": "a - b", "client-class": ANY}) == "discovery: any other vendor"
    assert D.pool_note({"pool": "a - b", "client-class": "voip"}) == "for clients of class voip"
    assert D.pool_note({"pool": "a - b"}) == ""


def _s1_intent():
    """Intent's facts from s1's committed host_vars (tests/fixtures/committed/s1.yml): the SVIs
    for VLANs 10, 20 and 30 with their VRRP addresses, relays and RA flags."""
    import yaml
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "committed",
                           "s1.yml"), encoding="utf-8") as fh:
        return D.facts_from({"s1": yaml.safe_load(fh)})


def test_board_c_s_columns_gateway_against_intent_dns_and_who_holds_it(web):
    value = _value()
    value["intent"] = dict(_s1_intent(), error="")
    value["families"]["dhcp4"]["held"] = {"10": "mercury", "20": "mercury", "255": "ztp"}
    _store(value)
    html = _get(web)
    row10 = html.split("10.10.10.0/24<br>")[1].split("</tr>")[0]
    assert '<span class="mono">10.10.10.1</span>' in row10 and "matches intent" in row10
    assert 'title="intent: s1 Vlan10"' in row10
    assert "10.255.0.10" in row10 and "Mercury" in row10
    ztp = html.split("10.255.0.0/24 ")[1].split("</tr>")[0]
    assert "none, by design (D4)" in ztp
    assert "ZTP&#39;s posture" in ztp or "ZTP's posture" in ztp
    v6 = html.split("2001:db8:10::/64<br>")[1].split("</tr>")[0]
    assert "from the routers&#39; RAs" in v6 or "from the routers' RAs" in v6
    assert "s1 Vlan10: M set, O set" in v6 and "2001:db8:255::10" in v6


def test_a_gateway_that_differs_from_intent_says_both():
    from modules import dhcp_page as P
    sub = {"family": "IPv4", "prefix": "10.10.20.0/24", "options": {"routers": "10.10.20.254"},
           "global_options": {}}
    gw = P.gateway(sub, _s1_intent())
    assert gw["state"] == "differs" and gw["words"] == "intent says 10.10.20.1"
    gw = P.gateway(dict(sub, options={}), _s1_intent())
    assert gw["state"] == "missing" and "Kea offers none; intent says 10.10.20.1" in gw["words"]
    gw = P.gateway(dict(sub, prefix="10.10.40.0/24"), _s1_intent())
    assert gw["state"] == "none" and "no interface in intent is on it" in gw["words"]


def test_intent_s_facts_read_from_committed_host_vars():
    f = _s1_intent()
    assert [e["gateway"] for e in f["IPv4"]["10.10.10.0/24"]] == [["10.10.10.1"]]
    assert f["IPv4"]["10.10.10.0/24"][0]["relays"] == ["10.255.0.10"]
    assert f["IPv6"]["2001:db8:30::/64"][0]["managed"] is True
    assert "10.10.30.0/24" not in f["IPv4"], "VLAN 30 is IPv6-only"


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
    # C681: each IPv6 lease's IAID, from Kea's lease data (the captured lease6-get-all), and
    # the drift's cause said: h1 asked with a new IAID each time.
    with open(os.path.join(os.path.dirname(__file__), "fixtures", "kea",
                           "dhcp6-lease6-get-all.json"), encoding="utf-8") as fh:
        raw = json.load(fh)
    raw = raw[0] if isinstance(raw, list) else raw
    for lease in raw["arguments"]["leases"]:
        assert f">IAID {lease['iaid']}</span>" in html, lease["ip-address"]
    assert "with a new IAID each time (3 different)" in six
    assert "keeps using it whatever Kea's lease says" in six


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


def test_reservations_kea_holds_outside_a_subnet_are_drawn(web):
    """C660: a global reservation drawn and counted, used only where a subnet turns the global
    ones on; a subnet whose reservations Kea ignores says so; a hosts database named."""
    from tests.test_dhcp_reader import plant_elsewhere
    _store(_value(kea=FakeKea(plant=plant_elsewhere)))
    head = _get(web)
    assert "<strong>1</strong> reservation<" in head
    assert "IPv4 (dhcp4) also keeps reservations in a hosts database (postgresql).</strong>" \
           in head and "only the configuration's" in head
    assert "10.10.20.0/24 <span class=\"faint\">in floor-2</span>" in head
    html = _get(web, "&tab=res")
    assert "IPv4, Kea's global level" in html and "no request yet" in html

    def off(svc, result):
        result = plant_elsewhere(svc, result)
        conf = result[0]["arguments"]["Dhcp4" if svc == "dhcp4" else "Dhcp6"]
        if svc == "dhcp4":
            conf["shared-networks"][0]["reservations-global"] = False
            conf["subnet4"][0]["reservations-in-subnet"] = False
            conf["subnet4"][0]["reservations"] = [{"hw-address": "aa:c1:ab:00:00:99",
                                                   "ip-address": "10.10.10.150"}]
        return result
    _store(_value(kea=FakeKea(plant=off)))
    html = _get(web, "&tab=res")
    assert "Kea does not use it: reservations-global is off in every subnet" in html
    assert "Kea does not use it: reservations-in-subnet is off for this subnet" in html
    assert "2 reservations Kea does not use" in _get(web)


def test_exclusions_say_what_kea_cannot_do(web):
    """Board D's tab with nothing recorded: no conflict in the lab (its SVIs sit below the
    pools), nothing excluded, Add an exclusion…, and what Kea cannot do."""
    html = _get(web, "&tab=exc")
    assert "Kea has no excluded-address setting" in html and "Nothing is excluded." in html
    assert "None found: no static address committed intent assigns" in html
    assert ">Add an exclusion…</a>" in html


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


# ---- Board B (C529 step 2): a reservation's add, change and remove, in place of the tab.

from tests.test_dhcp_reservations import FakeKea as KeaFiles, kea_dir  # noqa: E402,F401


@pytest.fixture
def board_b(web, kea_dir, monkeypatch):  # noqa: F811 (the fixture imported above)
    """The page with Kea as captured and each subnet's file of Mercury's (the host step run),
    Kea's own check passing, and the record kept here instead of committed."""
    from modules import dhcp_reservations as R
    from modules.nsot import ztp
    kea = KeaFiles(kea_dir["files"])
    monkeypatch.setattr("modules.integrations.kea.KeaIntegration", lambda **kw: kea)
    monkeypatch.setattr(ztp, "_run_kea_test", lambda path, program="kea-dhcp4": (True, "ok"))
    recorded = []
    monkeypatch.setattr(R, "record_commit", lambda list_name, p, actor, reason:
                        recorded.append((p["subject"], actor, reason)) or
                        {"ok": True, "commit": "5e7b21c0"})
    return dict(web, kea=kea, files=kea_dir["files"], recorded=recorded)


ADD = {"list": "Lab", "op": "add", "where": "IPv4:20", "key": "hw-address",
       "identity": "aa:c1:ab:5d:20:9e", "address": "10.10.20.150", "hostname": "h5"}


def _card(web, **args):
    from urllib.parse import urlencode
    return web["client"].get("/v2/dhcp/reservation?" + urlencode(args))


def test_the_tab_offers_add_and_each_row_edit_and_remove(web):
    """Board A's controls: Add a reservation… on the tab; Edit… and Remove… on each row but
    ZTP's (onboarding's) and the global level's (Kea's own file)."""
    from tests.test_dhcp_reader import plant_elsewhere

    def plant(svc, result):
        result = plant_elsewhere(svc, result)
        conf = result[0]["arguments"]["Dhcp4" if svc == "dhcp4" else "Dhcp6"]
        if svc == "dhcp4":
            conf["subnet4"][0]["reservations"] = [{"hw-address": "aa:c1:ab:00:00:99",
                                                   "ip-address": "10.10.10.150", "hostname": "h9"}]
        return result
    _store(_value(kea=FakeKea(plant=plant)))
    html = _get(web, "&tab=res")
    assert ">Add a reservation…</a>" in html and "Kea's file, by hand" in html
    assert html.count(">Edit…</a>") == html.count(">Remove…</a>") == 1
    edit = re.search(r"href=\"([^\"]*op=edit[^\"]*)\"", html).group(1)
    from urllib.parse import parse_qs, urlsplit
    q = {k: v[0] for k, v in parse_qs(urlsplit(edit.replace("&amp;", "&")).query).items()}
    assert q["was"] == "hw-address=aa:c1:ab:00:00:99" and q["subnet"] == "10" and q["family"] == "IPv4"
    assert "/v2/help/dhcp-reservation" in html


def test_the_form_offers_every_subnet_but_ztp_s(board_b):
    html = _card(board_b, list="Lab", op="add").get_data(as_text=True)
    assert 'id="dh-op"' in html and "Reserve an address" in html
    subnets = re.findall(r'<option value="(IPv[46]:\d+)"', html)
    assert subnets == ["IPv4:10", "IPv4:20", "IPv6:10", "IPv6:20", "IPv6:30"]
    assert "hash" not in re.findall(r'name="(\w+)"', html)


def test_the_preview_draws_the_change_its_checks_and_its_hash(board_b):
    html = _card(board_b, **ADD).get_data(as_text=True)
    assert "Reserve an address on 10.10.20.0/24" in html
    assert "+ reservation h5: hw-address aa:c1:ab:5d:20:9e, " \
           "address 10.10.20.150" in html
    assert "inside its pool, so no other client may be given it while reserved" in html
    assert "at confirm" in html and re.search(r'name="hash" value="[0-9a-f]{64}"', html)
    assert 'name="reason"' in html and "Reserve 10.10.20.150 for h5" in html


def test_a_refused_preview_names_both_operands_and_offers_no_confirm(board_b):
    html = _card(board_b, **dict(ADD, address="10.10.20.101")).get_data(as_text=True)
    assert "Not reserved: 10.10.20.101 is leased to another client." in html
    assert 'name="hash"' not in html


@pytest.mark.real_identity
def test_the_confirm_needs_a_verified_person(board_b):
    p = _card(board_b, **ADD).get_data(as_text=True)
    h = re.search(r'name="hash" value="([0-9a-f]{64})"', p).group(1)
    r = board_b["client"].post("/v2/dhcp/reservation?list=Lab", data=dict(ADD, hash=h, reason="printer"))
    assert r.status_code in (401, 403)
    assert open(board_b["files"][("dhcp4", 20)], encoding="utf-8").read() == "[]\n"


def test_the_confirm_writes_reads_back_and_records_in_place(board_b, monkeypatch):
    import types
    from modules import identity
    who = types.SimpleNamespace(actor="operator@example.invalid", kind="person",
                                peer="192.0.2.5", is_identified=True)
    monkeypatch.setattr(identity, "require", lambda *a, **k: (who, None))
    monkeypatch.setattr(identity, "request_actor", lambda: who.actor)
    p = _card(board_b, **ADD).get_data(as_text=True)
    h = re.search(r'name="hash" value="([0-9a-f]{64})"', p).group(1)
    r = board_b["client"].post("/v2/dhcp/reservation?list=Lab",
                               data=dict(ADD, hash=h, reason="h5 is the printer"))
    html = r.get_data(as_text=True)
    assert r.status_code == 200, html
    assert "h5's reservation added" in html
    assert "exactly the change shown" in html
    assert "5e7b21c" in html and "Actor: operator@example.invalid" in html
    assert board_b["recorded"] == [("dhcp: h5 reserved 10.10.20.150 by MAC aa:c1:ab:5d:20:9e",
                                    "operator@example.invalid", "h5 is the printer")]
    assert json.load(open(board_b["files"][("dhcp4", 20)], encoding="utf-8")) == [
        {"hw-address": "aa:c1:ab:5d:20:9e", "ip-address": "10.10.20.150", "hostname": "h5"}]
    # A second confirm of the same preview: the file moved, so nothing is written again.
    again = board_b["client"].post("/v2/dhcp/reservation?list=Lab",
                                   data=dict(ADD, hash=h, reason="twice")).get_data(as_text=True)
    assert "Nothing was changed" in again

