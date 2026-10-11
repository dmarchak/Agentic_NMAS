"""C529 step 5, the subnet move's plan (`modules/dhcp_subnets.py`), on the host's own Kea main
files as captured 2026-10-11 (tests/fixtures/kea/kea-dhcp4.conf and kea-dhcp6.conf, after step
2: each subnet already takes its reservations from Mercury's file).

- the subnet array moves VERBATIM into Mercury's file (comments, layout and the reservation
  includes kept), and Kea's file keeps one include in its place, nothing else changed;
- a file already moved reads as done; a "shared-networks" key, a subnet key found other than
  once, or a value that is not an array is refused by name;
- a key named inside a comment or a string is not the key.
(That Kea 2.4.1 resolves the include inside an included file was measured on the host's own
kea-dhcp4 and kea-dhcp6 -t before this was relied on: docs/OPEN_FINDINGS.md, C529.)
"""

import json
import os
import re

import pytest

from modules import dhcp_subnets as S

KEA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "kea")


def _main(name):
    with open(os.path.join(KEA, name), encoding="utf-8") as fh:
        return fh.read()


def _strip(text):
    """The text as JSON: comments and include directives removed (enough to read the shape)."""
    text = re.sub(r"<\?include \"[^\"]+\"\?>", "[]", text)
    return re.sub(r"(?m)^\s*(//|#).*$", "", text)


@pytest.mark.parametrize("family, name, key, ids", [
    ("IPv4", "kea-dhcp4.conf", "subnet4", [10, 20, 255]),
    ("IPv6", "kea-dhcp6.conf", "subnet6", [10, 20, 30]),
])
def test_the_array_moves_verbatim_and_one_include_takes_its_place(family, name, key, ids):
    main = f"/etc/kea/{name}"
    text = _main(name)
    p = S.move_plan(text, main, family)
    assert p["state"] == "move" and p["refused"] == ""
    assert p["file"] == f"/etc/kea/nmas/subnets{family[-1]}.json"
    moved = p["subnets_text"].rstrip("\n")
    assert moved in text, "verbatim"
    assert moved.startswith("[") and moved.endswith("]")
    assert [s["id"] for s in json.loads(_strip(moved))] == ids
    assert moved.count("<?include") == len(ids), "every subnet's reservation include kept"
    assert p["candidate"] == text.replace(moved, f'<?include "{p["file"]}"?>')
    assert f'"{key}": <?include "{p["file"]}"?>' in p["candidate"]
    again = S.move_plan(p["candidate"], main, family)
    assert again["state"] == "done", "a file already moved is left alone"


def test_the_ipv6_file_s_comments_stay_in_kea_s_file():
    text = _main("kea-dhcp6.conf")
    p = S.move_plan(text, "/etc/kea/kea-dhcp6.conf", "IPv6")
    head = text.split('"subnet6"')[0]
    assert head.count("//") >= 10 and p["candidate"].startswith(head)


def test_shared_networks_are_refused():
    text = _main("kea-dhcp4.conf").replace('"subnet4": [', '"shared-networks": [], "subnet4": [')
    p = S.move_plan(text, "/etc/kea/kea-dhcp4.conf", "IPv4")
    assert p["state"] == "refused" and '"shared-networks"' in p["refused"]


def test_a_key_in_a_comment_or_a_string_is_not_the_key():
    text = _main("kea-dhcp4.conf")
    noisy = text.replace('"subnet4": [',
                         '// "subnet4": [ in a comment\n"comment": "\\"subnet4\\": [",\n'
                         '"subnet4": [', 1)
    p = S.move_plan(noisy, "/etc/kea/kea-dhcp4.conf", "IPv4")
    assert p["state"] == "move", p["refused"]


@pytest.mark.parametrize("change, words", [
    (lambda t: t.replace('"subnet4": [', '"subnet4": [], "x": { "subnet4": [', 1) + "}",
     "found 2 times"),
    (lambda t: t.replace('"subnet4": [', '"subnet4": { "a": [', 1), "is not an array"),
], ids=["twice", "not-an-array"])
def test_what_is_not_one_array_is_refused_by_name(change, words):
    p = S.move_plan(change(_main("kea-dhcp4.conf")), "/etc/kea/kea-dhcp4.conf", "IPv4")
    assert p["state"] == "refused" and words in p["refused"]


# --- the host step's proof: before and after, compared ----------------------------------------

def _tool():
    import importlib.machinery
    import importlib.util
    path = os.path.join(os.path.dirname(KEA), "..", "..", "scripts", "nmas-kea-subnet-files")
    loader = importlib.machinery.SourceFileLoader("nmas_kea_subnet_files", path)
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(mod)
    return mod


def _snapshot():
    """A snapshot from the lab's own Kea answers (tests/fixtures/kea/), as the tool takes one."""
    def load(name):
        with open(os.path.join(KEA, name), encoding="utf-8") as fh:
            return json.load(fh)

    class FakeKea:
        def command(self, cmd, services):
            svc = services[0]
            name = {"config-get": f"{svc}-config-get.json",
                    "lease4-get-all": "dhcp4-lease4-get-all.json",
                    "lease6-get-all": "dhcp6-lease6-get-all.json"}[cmd]
            return {"ok": True, "result": load(name)}
    return _tool().snapshot(FakeKea())


def test_a_snapshot_holds_both_families_leases_and_configuration():
    snap = _snapshot()
    assert set(snap) == {"IPv4", "IPv6"}
    assert snap["IPv4"]["leases"] and snap["IPv6"]["leases"]
    assert "hash" not in snap["IPv4"]["config"] and snap["IPv4"]["config"]["subnet4"]


def test_equal_snapshots_compare_equal_and_any_move_is_named():
    tool = _tool()
    before = _snapshot()
    assert tool.compare(before, json.loads(json.dumps(before))) == []
    after = json.loads(json.dumps(before))
    after["IPv4"]["leases"].pop()
    after["IPv6"]["config"]["valid-lifetime"] = 1
    moved = tool.compare(before, after)
    assert any("IPv4: 1 leases before and not after" in m for m in moved), moved
    assert any("IPv6: Kea's configuration key 'valid-lifetime' differs" in m for m in moved)


def test_the_update_page_s_check_reads_done_only_when_both_families_moved(tmp_path, monkeypatch):
    from modules import host_steps
    files = {}
    for family, name in (("IPv4", "kea-dhcp4.conf"), ("IPv6", "kea-dhcp6.conf")):
        files[family] = tmp_path / name
        files[family].write_text(_main(name))
    monkeypatch.setattr("modules.dhcp_reservations.main_config",
                        lambda list_name, family: str(files[family]))
    got = host_steps.check_kea_subnet_files()
    assert got["state"] == "not_done" and "IPv4" in got["detail"] and "IPv6" in got["detail"]
    for family in files:
        p = S.move_plan(files[family].read_text(), str(files[family]), family)
        files[family].write_text(p["candidate"])
    assert host_steps.check_kea_subnet_files()["state"] == "done"


# --- board C: a subnet changed (C529 step 3) -------------------------------------------------

class SubnetKea:
    """Kea as captured, its subnets read from Mercury's subnet file at `config-reload` (and at
    start), each subnet's reservations from the file it includes."""

    def __init__(self, files, reloads=True):
        def load(name):
            with open(os.path.join(KEA, name), encoding="utf-8") as fh:
                return json.load(fh)
        self.base = {"dhcp4": load("dhcp4-config-get.json"),
                     "dhcp6": load("dhcp6-config-get.json")}
        self.leases = {"dhcp4": load("dhcp4-lease4-get-all.json"),
                       "dhcp6": load("dhcp6-lease6-get-all.json")}
        self.files, self.reloads, self.sent = files, reloads, []
        self.loaded = {svc: self._read(svc) for svc in self.base}

    def is_configured(self):
        return True

    def _read(self, svc):
        with open(self.files[svc], encoding="utf-8") as fh:
            subs = S.load(fh.read())
        for s in subs:
            r = s.get("reservations")
            if isinstance(r, str) and r.startswith("@@kea-include:"):
                with open(r[len("@@kea-include:"):-2], encoding="utf-8") as fh:
                    s["reservations"] = json.load(fh)
        return subs

    def command(self, cmd, service=None):
        svc = service if isinstance(service, str) else (service or ["dhcp4"])[0]
        self.sent.append((cmd, svc))
        if cmd == "config-get":
            doc = json.loads(json.dumps(self.base[svc]))
            root = doc[0]["arguments"]["Dhcp4" if svc == "dhcp4" else "Dhcp6"]
            root["subnet4" if svc == "dhcp4" else "subnet6"] = json.loads(
                json.dumps(self.loaded[svc]))
            return {"ok": True, "result": doc}
        if cmd.endswith("-get-all"):
            return {"ok": True, "result": self.leases[svc]}
        if cmd == "config-reload":
            if self.reloads:
                self.loaded[svc] = self._read(svc)
            return {"ok": True, "result": [{"result": 0}]}
        return {"ok": False, "error": f"unexpected {cmd}"}


@pytest.fixture
def moved(tmp_path, monkeypatch):
    """Kea's folder after the subnet move: the captured main files, their subnets in Mercury's
    files (reservation includes pointed at empty files beside them), the main files including
    them."""
    from modules import dhcp_reservations as D
    (tmp_path / "nmas").mkdir()
    mains, files = {}, {}
    for family, svc, name in (("IPv4", "dhcp4", "kea-dhcp4.conf"),
                              ("IPv6", "dhcp6", "kea-dhcp6.conf")):
        main = str(tmp_path / name)
        text = _main(name).replace("/etc/kea/nmas/", str(tmp_path / "nmas") + "/")
        for path in re.findall(r'<\?include "([^"]+)"\?>', text):
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("[]\n")
        p = S.move_plan(text, main, family)
        with open(p["file"], "w", encoding="utf-8") as fh:
            fh.write(p["subnets_text"])
        with open(main, "w", encoding="utf-8") as fh:
            fh.write(p["candidate"])
        mains[family], files[svc] = main, p["file"]
    monkeypatch.setattr(D, "main_config", lambda list_name, family: mains[family])
    monkeypatch.setattr("modules.readers.dhcp._ztp_ids", lambda config: [255])
    return {"mains": mains, "files": files, "kea": SubnetKea(files)}


def _intent():
    import yaml
    from modules.readers.dhcp import facts_from
    with open(os.path.join(os.path.dirname(KEA), "committed", "s1.yml"), encoding="utf-8") as fh:
        return facts_from({"s1": yaml.safe_load(fh)})


EDIT = {"op": "edit", "family": "IPv4", "id": "10", "pool": "10.10.10.101 - 10.10.10.149"}


class TestTheSubnetPlan:
    def test_a_pool_change_names_the_lease_it_strands_and_how_long_it_keeps_it(self, moved):
        p = S.plan("Lab", EDIT, kea=moved["kea"], intent=_intent())
        assert p["ok"], p["refused"]
        assert ("+", 'pools: [{"pool": "10.10.10.101 - 10.10.10.149"}]') in p["change"]
        stranded = [n for n in p["leases"] if n.startswith("10.10.10.100 ")]
        assert stranded and "keeps it until its lease ends 2027-10-" in stranded[0]
        assert "Kea answers its renewals with silence: measured on Kea 2.4.1" in stranded[0]
        assert not any(n.startswith("10.10.10.102") for n in p["leases"]), "inside the pool"
        assert ("pass", "the gateway equals intent's VRRP address (10.10.10.1)") in p["checks"]

    def test_a_lifetime_sets_both_timers_and_says_who_it_applies_to(self, moved):
        p = S.plan("Lab", dict(EDIT, pool="", valid="1 d"), kea=moved["kea"])
        assert ("+", "valid-lifetime: 86400") in p["change"]
        assert ("+", "renew-timer: 43200") in p["change"] and ("+", "rebind-timer: 75600") in \
            p["change"]
        assert any("applies to leases granted or renewed after" in n for n in p["leases"])

    def test_a_gateway_other_than_intent_s_is_said(self, moved):
        p = S.plan("Lab", dict(EDIT, pool="", gateway="10.10.10.254"), kea=moved["kea"],
                        intent=_intent())
        assert ("warn", "the gateway 10.10.10.254 is not intent's VRRP address (10.10.10.1)") \
            in p["checks"]

    @pytest.mark.parametrize("values, words", [
        (dict(EDIT, pool="10.10.20.1 - 10.10.20.9"), "does not lie inside 10.10.10.0/24"),
        (dict(EDIT, pool="10.10.10.9 - 10.10.10.1"), "ends before it starts"),
        (dict(EDIT, id="255"), "subnet 255 is ZTP's"),
        (dict(EDIT, pool="", gateway="10.10.20.1"), "is not in 10.10.10.0/24"),
        (dict(EDIT, pool="", dns="dns.example"), "is not an address"),
        (dict(EDIT, pool="10.10.10.100 - 10.10.10.200"), "nothing would change"),
        (dict(EDIT, pool="", valid="soon"), "is not a time"),
    ], ids=["outside", "backwards", "ztp", "gateway-outside", "dns-name", "no-change", "time"])
    def test_what_it_cannot_do_is_refused_by_name(self, moved, values, words):
        p = S.plan("Lab", values, kea=moved["kea"])
        assert not p["ok"] and words in p["refused"], p["refused"]

    def test_before_the_move_it_is_refused_naming_the_step(self, moved):
        os.remove(moved["files"]["dhcp4"])
        p = S.plan("Lab", EDIT, kea=moved["kea"])
        assert not p["ok"] and "c529-step5-subnet-files.sh" in p["refused"]


def _ok_test(path):
    return True, "ok"


class TestTheSubnetApply:
    def _apply(self, moved, h=None, **kw):
        p = S.plan("Lab", EDIT, kea=moved["kea"])
        recorded = []
        got = S.apply_edit("Lab", EDIT, h or p["hash"], actor="p@example.invalid",
                           reason="narrow the pool", kea=moved["kea"], run_test=_ok_test,
                           record=lambda l, plan, **k: recorded.append(plan) or
                           {"ok": True, "commit": "abc1234"}, **kw)
        return got, recorded

    def test_it_writes_reloads_reads_back_and_records(self, moved):
        got, recorded = self._apply(moved)
        assert got["ok"], got["error"]
        assert "holds subnet 10 as written" in got["read_back"] and recorded
        text = open(moved["files"]["dhcp4"], encoding="utf-8").read()
        assert "10.10.10.101 - 10.10.10.149" in text
        assert text.count("<?include") == 3, "every subnet's reservation file still included"
        assert ("config-reload", "dhcp4") in moved["kea"].sent

    def test_a_moved_preview_writes_nothing(self, moved):
        before = open(moved["files"]["dhcp4"], encoding="utf-8").read()
        got, recorded = self._apply(moved, h="0" * 64)
        assert not got["ok"] and "Preview again" in got["error"] and not recorded
        assert open(moved["files"]["dhcp4"], encoding="utf-8").read() == before

    def test_a_read_back_that_disagrees_puts_the_file_back(self, moved):
        before = open(moved["files"]["dhcp4"], encoding="utf-8").read()
        moved["kea"].reloads = False
        got, recorded = self._apply(moved)
        assert not got["ok"] and "subnet 10 did not change" in got["error"]
        assert "previous subnet file restored" in got["rolled_back"] and not recorded
        assert open(moved["files"]["dhcp4"], encoding="utf-8").read() == before

    def test_a_change_needs_a_reason(self, moved):
        got = S.apply_edit("Lab", EDIT, "x", actor="p", reason=" ", kea=moved["kea"])
        assert not got["ok"] and "a reason is recorded" in got["error"]


def _vlan30():
    """s1's intent with VLAN 30 given an IPv4 SVI and VRRP group, as a new VLAN would be."""
    import yaml
    from modules.readers.dhcp import facts_from
    with open(os.path.join(os.path.dirname(KEA), "committed", "s1.yml"), encoding="utf-8") as fh:
        hv = yaml.safe_load(fh)
    for i in hv["interfaces"]:
        if i.get("name") == "Vlan30":
            i["ipv4"] = "10.10.30.2 255.255.255.0"
            i["helper_addresses"] = ["10.255.0.10"]
            i["vrrp_groups"].append({"family": "ipv4", "group": "30",
                                     "settings": ["address 10.10.30.1 primary"]})
    return facts_from({"s1": hv})


ADD = {"op": "add", "family": "IPv4", "prefix": "10.10.30.0/24",
       "pool": "10.10.30.100 - 10.10.30.199"}


class TestAddAndRemove:
    def test_an_add_takes_its_id_relay_and_gateway_from_intent(self, moved):
        p = S.plan("Lab", ADD, kea=moved["kea"], intent=_vlan30())
        assert p["ok"], p["refused"]
        assert p["id"] == 30 and p["after"]["relay"] == {"ip-addresses": ["10.10.30.2"]}
        assert {"name": "routers", "data": "10.10.30.1", "space": "dhcp4"} in \
            p["after"]["option-data"]
        assert ("pass", "relayed to 10.255.0.10 by s1 Vlan30 (intent)") in p["checks"]
        assert ("pass", "the gateway equals intent's VRRP address (10.10.30.1)") in p["checks"]

    def test_an_add_writes_a_fresh_reservations_file_and_kea_holds_the_new_subnet(self, moved):
        p = S.plan("Lab", ADD, kea=moved["kea"], intent=_vlan30())
        got = S.apply_edit("Lab", ADD, p["hash"], actor="p", reason="VLAN 30 servers",
                           kea=moved["kea"], run_test=_ok_test, intent=_vlan30(),
                           record=lambda l, plan, **k: {"ok": True, "commit": "abc"})
        assert got["ok"], got["error"]
        assert "holds the new subnet 30" in got["read_back"] and got["outcome"] == "added"
        fresh = os.path.join(os.path.dirname(moved["files"]["dhcp4"]), "reservations-30.json")
        assert open(fresh, encoding="utf-8").read() == "[]\n"
        assert [s["id"] for s in moved["kea"].loaded["dhcp4"]] == [10, 20, 255, 30]

    @pytest.mark.parametrize("values, words", [
        (dict(ADD, prefix="10.10.10.0/25"), "overlaps Kea's subnet 10"),
        (dict(ADD, prefix="10.10.30.5/24"), "has host bits set"),
        (dict(ADD, family="IPv6"), "is not an IPv6 prefix"),
        (dict(ADD, pool=""), "needs its pool"),
    ], ids=["overlap", "host-bits", "family", "no-pool"])
    def test_an_add_it_cannot_make_is_refused_by_name(self, moved, values, words):
        p = S.plan("Lab", values, kea=moved["kea"], intent=_vlan30())
        assert not p["ok"] and words in p["refused"], p["refused"]

    def test_an_add_no_interface_reaches_is_said(self, moved):
        p = S.plan("Lab", ADD, kea=moved["kea"], intent={})
        assert any(state == "warn" and "no interface in intent is on this prefix" in text
                   for state, text in p["checks"])

    def test_a_removal_with_leases_needs_their_acknowledgement(self, moved):
        rm = {"op": "remove", "family": "IPv4", "id": "10"}
        p = S.plan("Lab", rm, kea=moved["kea"])
        assert p["ok"] and p["ack"] is True
        assert "2 active lease(s)" in p["leases"][0] and "keeps its address until its lease " \
            "ends" in p["leases"][0]
        assert "stay in the repository's history" in p["survives"][0]
        kwargs = dict(actor="p", reason="VLAN 10 retired", kea=moved["kea"], run_test=_ok_test,
                      record=lambda l, plan, **k: {"ok": True, "commit": "abc"})
        refused = S.apply_edit("Lab", rm, p["hash"], **kwargs)
        assert not refused["ok"] and "was not acknowledged" in refused["error"]
        got = S.apply_edit("Lab", dict(rm, ack="1"), p["hash"], **kwargs)
        assert got["ok"], got["error"]
        assert [s["id"] for s in moved["kea"].loaded["dhcp4"]] == [20, 255]

    def test_zt_p_s_subnet_is_never_removed_here(self, moved):
        p = S.plan("Lab", {"op": "remove", "family": "IPv4", "id": "255"}, kea=moved["kea"])
        assert not p["ok"] and "ZTP's: onboarding's, never removed here" in p["refused"]

    def test_the_read_back_expects_what_the_operation_does(self):
        before = {"subnet4": [{"id": 10}, {"id": 20}]}
        assert S._moved(before, {"subnet4": [{"id": 10}, {"id": 20}, {"id": 30}]}, "IPv4", 30,
                        "add") == []
        assert S._moved(before, {"subnet4": [{"id": 20}]}, "IPv4", 10, "remove") == []
        assert S._moved(before, before, "IPv4", 10, "remove") == \
            ["the subnets are [10, 20] after; expected [20]"]

    def test_an_ipv6_lease_s_empty_hostname_is_no_name(self, moved):
        """Kea stores an absent IPv6 FQDN as "." (every IPv6 lease in the lab's capture): the
        removal names the client by its MAC or DUID, never "."."""
        p = S.plan("Lab", {"op": "remove", "family": "IPv6", "id": "30"}, kea=moved["kea"])
        assert p["ok"], p["refused"]
        assert "(.)" not in p["leases"][0]
        assert "1 active lease(s) (aa:c1:ab:12:c6:03)" in p["leases"][0]
