"""C1344: NetBox brought up to a device's committed golden after its intent is deployed, and
cables made from both ends' LLDP, through the import's preview and confirm.

Onboarding writes NetBox once, from the bootstrap golden, and a deploy never writes it again.
The world here: a network of two managed routers, r3 and r4, on tests/fake_netbox.py (NetBox
as the existing import tests fake it). r4 was imported from its fleet golden; r3 from a golden
WITHOUT its GigabitEthernet4 block (the fleet's r3.cfg with that one block removed: the
golden before the core link's intent was deployed). r3's committed golden is then the whole
fleet r3.cfg, so it holds an interface (Gi4), an IPv4 and an IPv6 address on it, and the link
to r4's Gi4, all of which NetBox lacks.

LLDP is the real capture (tests/fixtures/topology/lldpRemEntry.json and lldpRemPortId.json,
the Topology reader's own fixtures) folded by the Topology reader's own `physical_links`, as
its stored value holds it: r3 Gi4 to r4 Gi4 reported by both ends; r3 to r5 and to s3, and r4
to r5 and to s4, whose far ends are not managed devices of this network.

Each expectation comes by a path independent of the code under test: the addresses from the
golden's own lines by a regular expression here, the cable's ends from the capture's rows.
"""

import ipaddress
import json
import os
import re
import threading
import time

import pytest

from tests.fake_netbox import FakeNetBox

HERE = os.path.dirname(os.path.abspath(__file__))
FLEET = os.path.join(HERE, "fixtures", "configs", "fleet")
TOPO = os.path.join(HERE, "fixtures", "topology")
LIST = "probe-after-intent"
BASE = "http://127.0.0.1:9"
AUTHORITY = "test: declared by the test (C155)"
DEVICES = [{"hostname": "r3", "ip": "192.0.2.13", "platform": "cisco_iosxe", "role": "router"},
           {"hostname": "r4", "ip": "192.0.2.14", "platform": "cisco_iosxe", "role": "router"}]


def _fleet(host):
    with open(os.path.join(FLEET, f"{host}.cfg"), encoding="utf-8") as fh:
        return fh.read()


def _gi4_block(text):
    m = re.search(r"^interface GigabitEthernet4\n(?:[ ].*\n)*!\n", text, re.M)
    assert m, "floor: the fleet golden has its GigabitEthernet4 block"
    return m.group(0)


def _before(text):
    """The golden before the core link's intent was deployed: one block removed."""
    return text.replace(_gi4_block(text), "")


def _gi4_addresses(text):
    """Gi4's addresses read from the golden's own lines (independent of the import's parser)."""
    block = _gi4_block(text)
    v4 = re.search(r"^ ip address (\S+) (\S+)$", block, re.M)
    v6 = re.search(r"^ ipv6 address (\S+)$", block, re.M)
    return {str(ipaddress.ip_interface(f"{v4.group(1)}/{v4.group(2)}")),
            str(ipaddress.ip_interface(v6.group(1)))}


def _capture(drop=()):
    """The Topology reader's physical layer for this network, from the captures: each LLDP
    row of r3's and r4's, *drop* naming ``(device, local port)`` rows left out."""
    from modules.readers import topology_graph as T

    results = {}
    for metric in ("lldpRemEntry", "lldpRemPortId"):
        with open(os.path.join(TOPO, f"{metric}.json"), encoding="utf-8") as fh:
            for row in json.load(fh)["data"]["result"]:
                m = row["metric"]
                port = m.get("lldpLocPortDesc", m.get("lldpLocPortNum"))
                if m["device"] in ("r3", "r4") and (m["device"], port) not in drop:
                    results.setdefault(m["device"], {}).setdefault(metric, []).append(row)
    if drop:
        # lldpRemPortId carries no port name: drop it by the entry it pairs with.
        kept = {(d, r["metric"]["lldpLocPortNum"]) for d, ms in results.items()
                for r in ms.get("lldpRemEntry", [])}
        for d, ms in results.items():
            ms["lldpRemPortId"] = [r for r in ms.get("lldpRemPortId", [])
                                   if (d, r["metric"]["lldpLocPortNum"]) in kept]
    managed = {"r3", "r4"}
    links = T.physical_links(results, managed, managed)
    nodes = {n: {"managed": n in managed} for link in links for n in (link["a"], link["b"])}
    return {"state": "ok", "doc": {"last_good": {
        "value_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "value": {"networks": {LIST: {"nodes": nodes, "layers": {"physical": links}}}}}}}


#: The fields the import reads back from an object NetBox holds as NetBox renders them: a
#: foreign key as a nested object, a choice as ``{"value", "label"}``. The shared fake stores
#: each as the import sent it (an id, a value), which no test had read back before: here an
#: earlier import's objects are read again by the next, so they are rendered as NetBox would
#: answer them (`netbox_client`: `_ensure_site`'s region, `_ensure_interface`'s vrf, lag,
#: untagged VLAN, type, mode and duplex, `_ensure_prefix`'s role, `_pick_address_object`'s
#: vrf, `_upsert_device`'s primary addresses).
NESTED = {"dcim/sites": ("region",), "dcim/devices": ("primary_ip4", "primary_ip6"),
          "dcim/interfaces": ("vrf", "lag", "untagged_vlan"), "ipam/prefixes": ("role",),
          "ipam/ip-addresses": ("vrf",)}
CHOICES = {"dcim/interfaces": ("type", "mode", "duplex")}


def _as_netbox_renders(fake):
    for endpoint, fields in NESTED.items():
        for obj in fake.objects(endpoint):
            for f in fields:
                if isinstance(obj.get(f), int) and not isinstance(obj.get(f), bool):
                    obj[f] = {"id": obj[f]}
    for endpoint, fields in CHOICES.items():
        for obj in fake.objects(endpoint):
            for f in fields:
                if isinstance(obj.get(f), str):
                    obj[f] = {"value": obj[f], "label": obj[f]}


def _ref(value):
    return value.get("id") if isinstance(value, dict) else value


@pytest.fixture
def world(monkeypatch, tmp_path):
    """The fake NetBox with r4 imported whole and r3 from its bootstrap-era golden, then r3's
    committed golden the whole fleet r3.cfg. ``w.goldens`` is what each golden reads now."""
    import modules.netbox_client as nbc
    from modules import config, netbox_guard, reader_job

    # Each test's own store (the writer locks, the job records), so an import thread one test
    # started can never hold another's network.
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    for name in ("_CREATED_IDS_FILE", "_MODIFIED_FILE", "_ADOPTED_FILE"):
        monkeypatch.setattr(netbox_guard, name, str(tmp_path / f"{name.strip('_').lower()}.json"))
    goldens = {"r3": _before(_fleet("r3")), "r4": _fleet("r4")}
    ip_host = {d["ip"]: d["hostname"] for d in DEVICES}
    monkeypatch.setattr("modules.goldens._golden_record",
                        lambda ip, list_name="": {"text": goldens[ip_host[ip]], "refused": ""})
    monkeypatch.setattr(nbc, "get_netbox_config", lambda: {"url": BASE, "token": "t"})
    monkeypatch.setattr(nbc, "_SYNC_STATUS_FILE", str(tmp_path / "netbox_sync_status.json"))
    fake = FakeNetBox()
    monkeypatch.setattr(nbc, "_session_from_config", lambda cfg: fake)
    monkeypatch.setattr(nbc, "_managed_tag_ids", {})
    writes = {"on": True}
    monkeypatch.setattr(netbox_guard, "writes_allowed", lambda: writes["on"])
    topo = {"doc": _capture()}
    real = reader_job.read_cached
    monkeypatch.setattr(reader_job, "read_cached",
                        lambda name: topo["doc"] if name == "topology-graph" else real(name))
    out = nbc.sync_list_to_netbox(LIST, DEVICES, authority=AUTHORITY)
    assert out.get("ok") and not out.get("failed") and out.get("complete"), out
    _as_netbox_renders(fake)
    goldens["r3"] = _fleet("r3")

    class W:
        pass
    w = W()
    w.fake, w.goldens, w.writes, w.topo, w.nbc = fake, goldens, writes, topo, nbc
    return w


def _lag(w):
    from modules import netbox_client as N
    from modules.readers import netbox_lag

    return netbox_lag.read(population=lambda: [(LIST, None, ["r3", "r4"])],
                           ready=lambda: (True, "", w.fake, BASE),
                           goldens_for=lambda name, ref, hosts: (dict(w.goldens), {}, ""),
                           links_for=lambda name: N.stored_lldp_links(name,
                                                                      cached=w.topo["doc"]),
                           excluded=set())


def _cached(value):
    return {"state": "ok", "doc": {"last_good": {"value": value,
                                                 "value_at": "2026-10-19T00:00:00Z"},
                                   "stale_after_seconds": 900}}


def _preview(w, device="r3"):
    from modules import netbox_ops

    return netbox_ops.dry_run("import", LIST, "p@example.invalid", device=device)


@pytest.fixture
def ops(monkeypatch):
    from modules import netbox_ops
    monkeypatch.setattr(netbox_ops, "list_devices", lambda name: (name, [dict(d) for d in
                                                                         DEVICES]))
    monkeypatch.setattr(netbox_ops, "configured", lambda: True)
    return netbox_ops


# ------------------------------------------------------------------ the fact

class TestTheLagIsCounted:
    def test_r3_lacks_its_new_interface_both_addresses_and_the_cable(self, world):
        net = _lag(world)["networks"][LIST]
        assert net["in_netbox"] and net["checked"] == 2
        r3 = net["devices"]["r3"]
        assert r3["interfaces"] == ["GigabitEthernet4"], r3
        assert set(r3["addresses"]) == _gi4_addresses(_fleet("r3")), r3
        assert {ipaddress.ip_interface(a).version for a in r3["addresses"]} == {4, 6}
        assert r3["cables"] == ["r3 Gi4 to r4 Gi4"], r3
        # r4 holds its side already; the link is a cable to add from its end too.
        assert net["devices"]["r4"] == dict(net["devices"]["r4"], interfaces=[], addresses=[],
                                            cables=["r3 Gi4 to r4 Gi4"])

    def test_control_the_bootstrap_golden_lags_by_nothing(self, world):
        """The golden NetBox was imported from: nothing to add, and the LLDP link is no cable
        the import could make (r3's Gi4 is neither in NetBox nor in its golden)."""
        world.goldens["r3"] = _before(_fleet("r3"))
        assert _lag(world)["networks"][LIST]["devices"] == {}

    def test_an_unmanaged_neighbour_is_never_a_cable(self):
        """The rule itself, on the captured r3 Gi2 to r5 Gi2 link, given as reported by both
        ends so only the managed rule decides: r5 not managed, reported and no cable; control:
        r5 managed, a cable."""
        from modules.netbox_client import lldp_cable_plan
        link = {"a": "r3", "port_a": "Gi2", "b": "r5", "port_b": "Gi2", "kind": "both",
                "reported_by": ["r3", "r5"]}
        cables, reported = lldp_cable_plan([link], {"r3": True, "r5": False}, {"r3"})
        assert cables == [] and "r5 is not a managed device" in reported[0]["why"]
        cables, reported = lldp_cable_plan([link], {"r3": True, "r5": True}, {"r3"})
        assert [(c["a"], c["b"]) for c in cables] == [("r3", "r5")] and reported == []

    def test_a_network_not_in_netbox_is_not_judged(self, world):
        world.fake.store["dcim/sites"] = []
        world.fake.store["dcim/devices"] = []
        net = _lag(world)["networks"][LIST]
        assert not net["in_netbox"] and net["devices"] == {}


class TestTheRow:
    def test_the_row_names_the_counts_and_the_scoped_import(self, world):
        from modules import attention
        res = attention.netbox_lag_source(cached=_cached(_lag(world)), writes=True)
        rows = {r["id"]: r for r in res["rows"]}
        row = rows[f"netbox-lag:{LIST}:r3"]
        assert row["what"] == ("NetBox holds less than r3's committed configuration: "
                               "1 interface, 2 addresses, 1 cable to add")
        assert row["action"]["label"].startswith("Import into NetBox…")
        assert row["action"]["href"] == f"/v2/device/r3?tab=netbox&list={LIST}"
        assert row["clears"]["ways"] == ["resolves"]
        assert attention.NETBOX_WRITES_WHERE not in row["cause"]

    def test_writes_off_says_the_import_is_off_and_where_it_comes_on(self, world):
        from modules import attention
        row = next(r for r in attention.netbox_lag_source(
            cached=_cached(_lag(world)), writes=False)["rows"] if "r3" in r["devices"])
        assert attention.NETBOX_WRITES_WHERE in row["cause"]
        assert "Settings › Installation › Connections" in row["cause"]
        assert row["operands"]["writes"] == "off"

    def test_an_unread_store_is_a_row_never_an_empty_list(self):
        from modules import attention
        res = attention.netbox_lag_source(cached={"state": "absent", "doc": None,
                                                  "why": "no store yet"})
        assert res["state"] == "unreadable" and res["rows"][0]["kind"] == "unreadable"


# ------------------------------------------------------------------ the import

class TestTheOneDevicePreview:
    def test_it_lists_the_interface_both_addresses_and_the_cable(self, world, ops):
        posts = len(world.fake.posts)
        d = _preview(world)
        assert d["device_count"] == 1 and d["device"] == "r3"
        assert len(world.fake.posts) == posts, "a preview writes nothing"
        made = {(c["endpoint"], c.get("name")) for c in d["plan"]["creates"]}
        assert ("dcim/interfaces", "GigabitEthernet4") in made, made
        for a in _gi4_addresses(_fleet("r3")):
            assert any(e == "ipam/ip-addresses" and ipaddress.ip_interface(n or "0.0.0.0/0")
                       == ipaddress.ip_interface(a) for e, n in made), (a, made)
        assert ("dcim/cables", "r3 Gi4 to r4 Gi4") in made, made
        assert not [n for e, n in made if e == "dcim/devices"], "r4 is not imported again"

    def test_the_preview_draws_the_cable_and_reports_each_unmanaged_neighbour(self, world,
                                                                              ops):
        from modules.preview_confirm import netbox_import_preview
        p = netbox_import_preview(_preview(world),
                                  {"may": True, "statement": "You are confirming as p."})
        assert p["what"]["summary"].startswith(f"Import r3 in {LIST} (1 device(s))")
        lines = p["targets"][0]["program"]["lines"]
        assert "create dcim/cables r3 Gi4 to r4 Gi4" in lines, lines
        reported = next(i for i in p["what_not"]["items"] if i["kind"] == "cables_not_made")
        far = {re.match(r"r3 \S+ to (\S+) ", ln).group(1) for ln in reported["lines"]}
        assert far == {"r5", "s3"}, reported
        assert all("is not a managed device of this network: reported, no cable" in ln
                   for ln in reported["lines"])

    def test_control_a_link_one_end_reports_is_no_cable(self, world, ops):
        world.topo["doc"] = _capture(drop={("r4", "Gi4")})
        d = _preview(world)
        assert "dcim/cables" not in {c["endpoint"] for c in d["plan"]["creates"]}
        assert any(c["a"] == "r3" and c["b"] == "r4" and "only r3 reports it" in c["why"]
                   for c in d["cables"]["not_made"]), d["cables"]

    def test_control_lldp_not_read_plans_no_cable_and_says_why(self, world, ops):
        from modules.preview_confirm import netbox_import_preview
        world.topo["doc"] = {"state": "absent", "doc": None, "why": "no store yet"}
        d = _preview(world)
        assert "dcim/cables" not in {c["endpoint"] for c in d["plan"]["creates"]}
        p = netbox_import_preview(d, {"may": True, "statement": "s"})
        said = next(i for i in p["what_not"]["items"] if i["kind"] == "cables_unread")
        assert "No cable is planned" in said["text"] and "no LLDP read yet" in said["text"]

    def test_a_device_the_network_does_not_hold_is_refused_by_name(self, world, ops):
        with pytest.raises(ops.Refused) as got:
            _preview(world, device="edge9")
        assert "edge9" in got.value.payload["error"] and LIST in got.value.payload["error"]


class TestTheConfirm:
    def _confirm(self, world, ops, data):
        done = threading.Event()
        ops.start_import("import", LIST, data, "p@example.invalid", device="r3",
                         on_end=lambda outcome: done.set())
        assert done.wait(30), "the import thread did not end within 30 s"

    def test_it_creates_them_recorded_as_created_and_the_row_clears(self, world, ops):
        from modules import attention, netbox_guard
        d = _preview(world)
        self._confirm(world, ops, {"token": d["token"]})
        cables = world.fake.objects("dcim/cables")
        assert [c.get("label") for c in cables] == ["r3 Gi4 to r4 Gi4"], cables
        ifaces = {i["id"]: i for i in world.fake.objects("dcim/interfaces")}
        devs = {x["id"]: x["name"] for x in world.fake.objects("dcim/devices")}
        ends = {(devs[_ref(ifaces[t["object_id"]]["device"])], ifaces[t["object_id"]]["name"])
                for side in ("a_terminations", "b_terminations") for t in cables[0][side]}
        assert ends == {("r3", "GigabitEthernet4"), ("r4", "GigabitEthernet4")}
        held = {a["address"] for a in world.fake.objects("ipam/ip-addresses")}
        assert {str(ipaddress.ip_interface(a)) for a in held} >= _gi4_addresses(_fleet("r3"))
        created = netbox_guard.get_created(LIST)
        assert [e["id"] for e in created.get("dcim/cables", [])] == [cables[0]["id"]]
        assert created["dcim/cables"][0]["name"] == "r3 Gi4 to r4 Gi4"
        assert created["dcim/cables"][0]["authority"].startswith("v2's NetBox page")
        # The row clears: the reader, read again, finds NetBox holding the golden.
        after = _lag(world)
        assert after["networks"][LIST]["devices"] == {}, after
        assert attention.netbox_lag_source(cached=_cached(after), writes=True)["rows"] == []

    def test_control_writes_off_refuses_the_confirm_and_writes_nothing(self, world, ops):
        d = _preview(world)
        world.writes["on"] = False
        posts = len(world.fake.posts)
        with pytest.raises(ops.Refused) as got:
            ops.start_import("import", LIST, {"token": d["token"]}, "p@example.invalid",
                             device="r3")
        assert got.value.payload.get("blocked") and len(world.fake.posts) == posts
        assert "Settings › Installation › Connections" in got.value.payload["error"]

    def test_control_a_scope_the_preview_did_not_have_is_refused(self, world, ops):
        """The token is bound to the one-device plan: confirming it over the whole network
        recomputes a different plan, and nothing is written."""
        d = _preview(world)
        posts = len(world.fake.posts)
        with pytest.raises(ops.Refused) as got:
            ops.start_import("import", LIST, {"token": d["token"]}, "p@example.invalid")
        assert got.value.payload.get("stale") and len(world.fake.posts) == posts


class TestTheTab:
    def test_stored_for_says_behind_level_and_not_judged(self, world):
        from modules.readers import netbox_lag
        value = _lag(world)
        got = netbox_lag.stored_for(LIST, "r3", cached=_cached(value))
        assert got["state"] == "behind" and got["lag"]["interfaces"] == ["GigabitEthernet4"]
        assert netbox_lag.stored_for("elsewhere", "r3", cached=_cached(value))["state"] == \
            "not_judged"
        world.goldens["r3"] = _before(_fleet("r3"))
        assert netbox_lag.stored_for(LIST, "r3", cached=_cached(_lag(world)))["state"] == \
            "level"

    def _render(self, lag, **extra):
        from flask import render_template

        import app as A
        with A.app.test_request_context("/v2/device/r3"):
            return render_template("v2/_netbox.html", device={"hostname": "r3"},
                                   list_name=LIST, lag=lag,
                                   nb={"configured": True, "errors": [], "absent": False,
                                       "record": None}, **extra)

    def test_the_tab_draws_the_lag_and_the_scoped_import(self, world):
        from modules.readers import netbox_lag
        lag = netbox_lag.stored_for(LIST, "r3", cached=_cached(_lag(world)))
        html = self._render(lag)
        assert re.search(r"NetBox holds less than r3(&#39;|')s committed configuration:", html)
        assert "1 interface, 2 addresses, 1 cable to add" in html
        assert '<input type="hidden" name="device" value="r3">' in html
        assert 'hx-target="#netbox-job"' in html and '<div id="netbox-job"></div>' in html
        again = self._render(lag, refetch=True)
        assert '<div id="netbox-job"></div>' not in again, \
            "the record's own re-fetch must not draw a second slot"

    def test_control_a_level_device_draws_no_warning(self, world):
        from modules.readers import netbox_lag
        world.goldens["r3"] = _before(_fleet("r3"))
        html = self._render(netbox_lag.stored_for(LIST, "r3", cached=_cached(_lag(world))))
        assert "NetBox holds less" not in html and "NetBox holds the interfaces" in html


from tests.test_profile_apply import lab  # noqa: E402,F401 (the fixture)


class TestTheTabRoute:
    """The tab's route draws the import card's slot when the tab is opened (htmx's target the
    tab body) and not when the record's card re-fetches itself (its target the card, `netbox`),
    so a running import's card is never replaced by an empty slot."""

    @pytest.fixture
    def get(self, lab, monkeypatch):
        from modules import device_page
        from modules.nsot import listref
        monkeypatch.setattr(device_page, "find_device", lambda name, ref=None: (
            listref.resolve("Lab"), {"hostname": name, "ip": "192.0.2.13",
                                     "platform": "cisco_iosxe"}))
        monkeypatch.setattr("modules.device_netbox.for_device", lambda ref, dev: {
            "configured": True, "errors": [], "record": None, "absent": True, "counts": {},
            "provenance": None, "mods": None, "platform_note": "", "ui_url": ""})
        monkeypatch.setattr("modules.readers.netbox_lag.stored_for", lambda list_name, host: {
            "state": "unread", "lag": None, "value_at": "", "why": "never read here"})

        def fetch(target):
            r = lab["client"].get("/v2/device/r3/netbox", headers={"HX-Request": "true",
                                                                   "HX-Target": target})
            assert r.status_code == 200, r.status_code
            return r.get_data(as_text=True)
        return fetch

    def test_opening_the_tab_draws_the_slot_and_the_scoped_import(self, get):
        html = get("tab-body")
        assert '<div id="netbox-job"></div>' in html
        assert '<input type="hidden" name="device" value="r3">' in html
        assert "is not known: never read here" in html

    def test_control_the_records_own_refetch_draws_no_slot(self, get):
        assert '<div id="netbox-job"></div>' not in get("netbox")


class TestCommittedGoldens:
    def test_one_read_returns_each_committed_golden_and_not_the_working_tree(self, tmp_path):
        import subprocess

        from modules.readers import netbox_lag
        repo = tmp_path / "repo"
        (repo / "golden").mkdir(parents=True)
        (repo / "golden" / "r3.cfg").write_text(_fleet("r3"), encoding="utf-8")
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
                   GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid")
        for cmd in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "golden"]):
            subprocess.run(["git", "-C", str(repo)] + cmd, check=True, env=env)
        (repo / "golden" / "r3.cfg").write_text("hostname edited-on-disk\n", encoding="utf-8")
        texts, err = netbox_lag.committed_goldens(str(repo))
        assert err == "" and texts == {"golden/r3.cfg": _fleet("r3")}

    def test_no_head_yet_holds_nothing(self, tmp_path):
        import subprocess

        from modules.readers import netbox_lag
        subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], check=True)
        assert netbox_lag.committed_goldens(str(tmp_path)) == ({}, "")
