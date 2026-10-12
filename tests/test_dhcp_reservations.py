"""C529 step 2 (board B): a reservation's add, change and remove (`modules/dhcp_reservations.py`),
on the lab's real Kea answers (tests/fixtures/kea/, captured read-only 2026-10-11: three IPv4
subnets and three IPv6, their leases, no reservation anywhere).

The fake Kea answers `config-get` from the capture and, like Kea, takes each subnet's
reservations from the file its configuration includes, read at `config-reload`; a Kea that
ignores the reload (or reads something else) is how a read-back that disagrees is planted.

- the plan: Mercury's file per subnet, refused when Kea's configuration does not include it
  (the host step not run) or the subnet is ZTP's; a hosts database refuses; the checks (inside
  the subnet and its pool, no other reservation names the client or the address, leased to no
  one or to this client); a lease held by another client refused naming both, and when; a
  stranded address refused; every reservation Kea holds read (subnets, shared networks,
  global); the hash binds the confirm;
- the apply: the hash compared again, the candidate tested by Kea's own check before the live
  file is touched, reloaded, read back (exactly the one change), the previous file restored
  when the read-back disagrees or the reload fails; the record committed with the reason.
"""

import copy
import json
import os
import re

import pytest

from modules import dhcp_reservations as D

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "kea")


def _load(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as fh:
        return json.load(fh)


class FakeKea:
    """Kea as captured, with each subnet's reservations from the file its configuration
    includes, read at `config-reload` (and at start)."""

    def __init__(self, files, reloads=True):
        self.base = {"dhcp4": _load("dhcp4-config-get.json"),
                     "dhcp6": _load("dhcp6-config-get.json")}
        self.leases = {"dhcp4": _load("dhcp4-lease4-get-all.json"),
                       "dhcp6": _load("dhcp6-lease6-get-all.json")}
        self.files, self.reloads, self.sent = files, reloads, []
        self.loaded = {svc: self._read(svc) for svc in self.base}

    def is_configured(self):
        return True

    def _read(self, svc):
        out = {}
        for (s, sid), path in self.files.items():
            if s == svc and os.path.exists(path):
                with open(path, encoding="utf-8") as fh:
                    out[sid] = json.load(fh)
        return out

    def command(self, cmd, service=None):
        # As the Control Agent client takes it: a name or a list of one.
        svc = service if isinstance(service, str) else (service or ["dhcp4"])[0]
        self.sent.append((cmd, svc))
        if cmd == "config-get":
            doc = copy.deepcopy(self.base[svc])
            root = doc[0]["arguments"]["Dhcp4" if svc == "dhcp4" else "Dhcp6"]
            for s in root["subnet4" if svc == "dhcp4" else "subnet6"]:
                if s["id"] in self.loaded[svc]:
                    s["reservations"] = self.loaded[svc][s["id"]]
            return {"ok": True, "result": doc}
        if cmd.endswith("-get-all"):
            return {"ok": True, "result": self.leases[svc]}
        if cmd == "version-get":
            return {"ok": True, "result": _load(f"{svc}-version-get.json")}
        if cmd == "config-reload":
            if self.reloads:
                self.loaded[svc] = self._read(svc)
            return {"ok": True, "result": [{"result": 0}]}
        return {"ok": False, "error": f"unexpected {cmd}"}


@pytest.fixture
def kea_dir(tmp_path, monkeypatch):
    """Kea's folder as the host step leaves it: each subnet but ZTP's taking its reservations
    from Mercury's file, every file an empty list; the main configurations name them."""
    nmas = tmp_path / "nmas"
    nmas.mkdir()
    files = {}
    texts = {}
    for family, svc, ids in (("IPv4", "dhcp4", (10, 20, 255)), ("IPv6", "dhcp6", (10, 20, 30))):
        main = str(tmp_path / f"kea-{svc}.conf")
        lines = []
        for sid in ids:
            path = D.fragment(main, family, sid)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("[]\n")
            files[(svc, sid)] = path
            lines.append(f'"id": {sid},\n"reservations": {D.directive(path)},')
        with open(main, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
        texts[family] = main
    monkeypatch.setattr(D, "main_config", lambda list_name, family: texts[family])
    monkeypatch.setattr(D, "_ztp_fragment", lambda list_name: files[("dhcp4", 255)])
    return {"files": files, "main": texts, "dir": tmp_path}


def ADD(**kw):
    return dict({"op": "add", "family": "IPv4", "subnet": "20", "key": "hw-address",
                 "identity": "aa:c1:ab:5d:20:9e", "address": "10.10.20.150",
                 "hostname": "h5"}, **kw)


class TestThePlan:
    def test_an_add_inside_the_pool_with_its_checks(self, kea_dir):
        p = D.plan("Lab", ADD(), kea=FakeKea(kea_dir["files"]))
        assert p["ok"], p["refused"]
        assert p["title"] == "Reserve an address on 10.10.20.0/24"
        assert p["change"] == [("+", "reservation h5: hw-address aa:c1:ab:5d:20:9e, address "
                                     "10.10.20.150")]
        states = [s for s, _t in p["checks"]]
        assert states == ["pass", "pass", "pass", "apply", "pass", "pass"]
        assert "inside its pool" in p["checks"][0][1] and "leased to no one" in p["checks"][2][1]
        assert len(p["hash"]) == 64 and p["version"] and p["after"]["hw-address"] == \
            "aa:c1:ab:5d:20:9e"

    def test_an_address_leased_to_another_client_is_refused_naming_both(self, kea_dir):
        p = D.plan("Lab", ADD(address="10.10.20.101"), kea=FakeKea(kea_dir["files"]))
        assert not p["ok"]
        assert p["refused"].startswith("Not reserved: 10.10.20.101 is leased to another client.")
        assert "aa:c1:ab:5d:20:9e" in p["refused"] and "MAC aa:c1:ab:3e:11:70" in p["refused"]
        assert " until " in p["refused"]

    def test_its_own_lease_is_no_conflict(self, kea_dir):
        p = D.plan("Lab", ADD(identity="aa:c1:ab:3e:11:70", address="10.10.20.101"),
                   kea=FakeKea(kea_dir["files"]))
        assert p["ok"] and ("pass", "10.10.20.101 is leased only to this client now") in \
            p["checks"]

    def test_outside_the_subnet_is_stranded_and_refused(self, kea_dir):
        p = D.plan("Lab", ADD(address="10.10.10.150"), kea=FakeKea(kea_dir["files"]))
        assert "would be stranded" in p["refused"]

    def test_a_subnet_kea_does_not_take_from_mercury_s_file_is_refused(self, kea_dir):
        text = open(kea_dir["main"]["IPv4"], encoding="utf-8").read()
        # Reservations kept inline in Kea's file: the cause said (C701: asked of the files'
        # shape, the subnet move's job, not the host step's).
        p = D.plan("Lab", ADD(), kea=FakeKea(kea_dir["files"]),
                   main_text=text.replace(D.directive(kea_dir["files"][("dhcp4", 20)]), "[]"))
        assert "does not take subnet 20's reservations" in p["refused"]
        assert "the subnet move (C529 step 5)" in p["refused"]
        # No include at all: the one-time host step has not run for it.
        bare = re.sub(r'\s*"reservations":\s*' + re.escape(
            D.directive(kea_dir["files"][("dhcp4", 20)])) + ",?", "", text)
        p = D.plan("Lab", ADD(), kea=FakeKea(kea_dir["files"]), main_text=bare)
        assert "does not take subnet 20's reservations" in p["refused"]
        assert "c529-step2-reservation-files.sh" in p["refused"]

    def test_ztp_s_subnet_is_onboarding_s(self, kea_dir):
        p = D.plan("Lab", ADD(subnet="255", address="10.255.0.50"), kea=FakeKea(kea_dir["files"]))
        assert "ZTP's" in p["refused"]

    def test_a_hosts_database_refuses(self, kea_dir):
        kea = FakeKea(kea_dir["files"])
        kea.base["dhcp4"][0]["arguments"]["Dhcp4"]["hosts-database"] = {"type": "mysql"}
        assert "a hosts database (mysql)" in D.plan("Lab", ADD(), kea=kea)["refused"]

    def test_an_identity_kea_does_not_match_on_is_not_offered(self, kea_dir):
        kea = FakeKea(kea_dir["files"])
        kea.base["dhcp4"][0]["arguments"]["Dhcp4"]["host-reservation-identifiers"] = ["duid"]
        assert "reserves by DUID" in D.plan("Lab", ADD(), kea=kea)["refused"]

    def test_another_reservation_naming_the_address_is_refused(self, kea_dir):
        with open(kea_dir["files"][("dhcp4", 20)], "w", encoding="utf-8") as fh:
            json.dump([{"hw-address": "aa:c1:ab:77:02:10", "ip-address": "10.10.20.150",
                        "hostname": "h7"}], fh)
        p = D.plan("Lab", ADD(), kea=FakeKea(kea_dir["files"]))
        assert "already holds a reservation for MAC aa:c1:ab:77:02:10 -> 10.10.20.150 (h7)" in \
            p["refused"]

    def test_every_place_kea_holds_reservations_is_read(self, kea_dir):
        kea = FakeKea(kea_dir["files"])
        root = kea.base["dhcp4"][0]["arguments"]["Dhcp4"]
        root["reservations"] = [{"hw-address": "aa:aa:aa:aa:aa:aa", "ip-address": "192.0.2.9"}]
        moved = root["subnet4"].pop(0)
        root["shared-networks"] = [{"name": "edge", "subnet4": [moved]}]
        got = D.every_reservation(D.kea_config(kea, "IPv4"), "IPv4")
        assert [r["where"] for r in got] == ["global"]
        moved["reservations"] = [{"hw-address": "bb:bb:bb:bb:bb:bb", "ip-address": "10.10.10.5"}]
        got = D.every_reservation(D.kea_config(kea, "IPv4"), "IPv4")
        assert sorted(r["where"] for r in got) == ["global", "shared network edge, subnet 10"]
        assert D.stranded(D.kea_config(kea, "IPv4"), "IPv4") == [
            "global: MAC aa:aa:aa:aa:aa:aa -> 192.0.2.9, which no subnet contains"]
        moved["reservations"][0]["ip-address"] = "10.10.20.5"
        assert D.stranded(D.kea_config(kea, "IPv4"), "IPv4")[0] == (
            "shared network edge, subnet 10: MAC bb:bb:bb:bb:bb:bb -> 10.10.20.5, which its "
            "subnet 10.10.10.0/24 does not contain")

    def test_an_ipv6_add_by_duid(self, kea_dir):
        p = D.plan("Lab", {"op": "add", "family": "IPv6", "subnet": "10", "key": "duid",
                           "identity": "00:03:00:01:aa:c1:ab:99:f6:e2",
                           "address": "2001:db8:10::101", "hostname": "h1"},
                   kea=FakeKea(kea_dir["files"]))
        assert p["ok"], p["refused"]
        assert p["after"] == {"duid": "00:03:00:01:aa:c1:ab:99:f6:e2",
                              "ip-addresses": ["2001:db8:10::101"], "hostname": "h1"}
        # h1 holds ::105 and ::107 too: named, not removed (board B's note).
        assert sorted(n.split()[2] for n in p["not_done"]) == ["2001:db8:10::105",
                                                                "2001:db8:10::107"]


def _with(kea_dir, family, sid, entries):
    svc = "dhcp4" if family == "IPv4" else "dhcp6"
    with open(kea_dir["files"][(svc, sid)], "w", encoding="utf-8") as fh:
        json.dump(entries, fh)


class TestEditAndRemove:
    H2 = {"hw-address": "aa:c1:ab:3e:11:70", "ip-address": "10.10.20.101", "hostname": "h2"}

    def test_edit_h2_s_mac_as_board_b_draws_it(self, kea_dir):
        _with(kea_dir, "IPv4", 20, [self.H2])
        p = D.plan("Lab", {"op": "edit", "family": "IPv4", "subnet": "20", "key": "hw-address",
                           "identity": "aa:c1:ab:5d:20:9e", "address": "10.10.20.101",
                           "hostname": "", "was": "hw-address=aa:c1:ab:3e:11:70"},
                   kea=FakeKea(kea_dir["files"]))
        assert p["ok"], p["refused"]
        assert p["change"] == [("-", "hw-address aa:c1:ab:3e:11:70"),
                               ("+", "hw-address aa:c1:ab:5d:20:9e")]
        assert p["after"] == dict(self.H2, **{"hw-address": "aa:c1:ab:5d:20:9e"})
        assert any(s == "note" and "old MAC aa:c1:ab:3e:11:70" in t for s, t in p["checks"])
        assert p["subject"] == "dhcp: h2 reserved by MAC aa:c1:ab:5d:20:9e -> 10.10.20.101 " \
                               "(was aa:c1:ab:3e:11:70)"

    def test_remove_says_what_survives(self, kea_dir):
        _with(kea_dir, "IPv4", 20, [self.H2])
        p = D.plan("Lab", {"op": "remove", "family": "IPv4", "subnet": "20",
                           "was": "hw-address=aa:c1:ab:3e:11:70"}, kea=FakeKea(kea_dir["files"]))
        assert p["ok"] and p["after"] is None
        assert p["not_done"][0].startswith("h2 keeps 10.10.20.101 until its lease ends")
        assert "stays in the repository's history (dhcp/reservations.yml)" in p["not_done"][1]

    def test_only_mercury_s_reservations_are_changed(self, kea_dir):
        p = D.plan("Lab", {"op": "remove", "family": "IPv4", "subnet": "20",
                           "was": "hw-address=aa:c1:ab:3e:11:70"}, kea=FakeKea(kea_dir["files"]))
        assert "has 0 reservations in Mercury's file for subnet 20" in p["refused"]


def _apply(kea_dir, kea, values, h=None, run_test=None, reason="h5 is the printer"):
    recorded = []
    p = D.plan("Lab", values, kea=kea)
    out = D.apply("Lab", values, h if h is not None else p["hash"], actor="person@example.invalid",
                  reason=reason, kea=kea, run_test=run_test or (lambda path: (True, "ok")),
                  record=lambda ln, p, actor, reason: recorded.append((p["subject"], actor,
                                                                       reason)) or
                  {"ok": True, "commit": "abc1234"})
    return out, recorded


class TestTheApply:
    def test_written_reloaded_read_back_and_recorded(self, kea_dir):
        kea = FakeKea(kea_dir["files"])
        out, recorded = _apply(kea_dir, kea, ADD())
        assert out["ok"], out["error"]
        assert out["outcome"] == "added" and out["commit"] == "abc1234"
        assert "exactly the change shown; nothing else changed" in out["read_back"]
        with open(kea_dir["files"][("dhcp4", 20)], encoding="utf-8") as fh:
            assert json.load(fh) == [{"hw-address": "aa:c1:ab:5d:20:9e",
                                      "ip-address": "10.10.20.150", "hostname": "h5"}]
        assert ("config-reload", "dhcp4") in kea.sent
        assert recorded == [("dhcp: h5 reserved 10.10.20.150 by MAC aa:c1:ab:5d:20:9e",
                             "person@example.invalid", "h5 is the printer")]

    def test_a_moved_preview_writes_nothing(self, kea_dir):
        kea = FakeKea(kea_dir["files"])
        out, recorded = _apply(kea_dir, kea, ADD(), h="0" * 64)
        assert not out["ok"] and "what the preview showed has changed" in out["error"]
        assert not recorded and ("config-reload", "dhcp4") not in kea.sent

    def test_kea_s_own_check_refusing_leaves_the_file_untouched(self, kea_dir):
        kea = FakeKea(kea_dir["files"])
        out, _r = _apply(kea_dir, kea, ADD(), run_test=lambda path: (False, "syntax error"))
        assert "kea-dhcp4 -t refused the candidate: syntax error" in out["error"]
        assert open(kea_dir["files"][("dhcp4", 20)], encoding="utf-8").read() == "[]\n"
        assert ("config-reload", "dhcp4") not in kea.sent

    def test_a_read_back_that_disagrees_restores_the_file(self, kea_dir):
        kea = FakeKea(kea_dir["files"], reloads=False)
        out, recorded = _apply(kea_dir, kea, ADD())
        assert not out["ok"] and not recorded
        assert "does not hold what was written" in out["error"]
        assert out["rolled_back"] == "Mercury's previous file restored and Kea reloaded"
        assert open(kea_dir["files"][("dhcp4", 20)], encoding="utf-8").read() == "[]\n"

    def test_no_reason_writes_nothing(self, kea_dir):
        out, _r = _apply(kea_dir, FakeKea(kea_dir["files"]), ADD(), reason=" ")
        assert "a reason is recorded" in out["error"]

    def test_a_removal_reads_back_gone(self, kea_dir):
        _with(kea_dir, "IPv4", 20, [TestEditAndRemove.H2])
        kea = FakeKea(kea_dir["files"])
        out, recorded = _apply(kea_dir, kea, {"op": "remove", "family": "IPv4", "subnet": "20",
                                              "was": "hw-address=aa:c1:ab:3e:11:70"})
        assert out["ok"], out["error"]
        assert open(kea_dir["files"][("dhcp4", 20)], encoding="utf-8").read() == "[]\n"
        assert recorded[0][0] == "dhcp: h2's reservation on 10.10.20.0/24 removed (was " \
                                 "10.10.20.101)"


#: Kea's IPv4 file as laid out on the host (measured 2026-10-11: each subnet's `"id": N,` on its
#: own line; ZTP's subnet already taking its reservations from Mercury's file; addresses are
#: documentation ones).
MAIN4 = """{ "Dhcp4": {
    "subnet4": [
        {
            "id": 10,
            "subnet": "192.0.2.0/26",
            "pools": [ { "pool": "192.0.2.10 - 192.0.2.20" } ]
        },
        {
            "id": 20,
            "subnet": "192.0.2.64/26"
        },
        {
            "id": 255,
            "subnet": "192.0.2.128/26",
            "reservations": <?include "/etc/kea/nmas/reservations-255.json"?>
        }
    ]
} }
"""


class TestTheHostStepsPlan:
    def test_each_subnet_but_one_that_has_its_file_gets_one(self):
        got = D.subnet_files(MAIN4, "/etc/kea/kea-dhcp4.conf", "IPv4", [10, 20, 255])
        assert got["refused"] == "" and got["add"] == [10, 20] and got["have"] == [255]
        lines = got["candidate"].splitlines()
        at = lines.index('            "id": 10,')
        assert lines[at + 1] == \
            '            "reservations": <?include "/etc/kea/nmas/reservations-10.json"?>,'
        assert got["candidate"].count("<?include") == 3
        # Nothing else moves: the candidate without the two new lines is the original.
        assert "\n".join(l for l in lines if "reservations-10" not in l and
                         "reservations-20" not in l) + "\n" == MAIN4

    def test_ipv6_files_are_named_apart(self):
        got = D.subnet_files(MAIN4.replace("Dhcp4", "Dhcp6"), "/etc/kea/kea-dhcp6.conf", "IPv6",
                             [10])
        assert '"reservations": <?include "/etc/kea/nmas/reservations6-10.json"?>,' in \
            got["candidate"]

    def test_a_subnet_listing_its_own_reservations_is_the_subnet_move_s(self):
        text = MAIN4.replace('"subnet": "192.0.2.64/26"',
                             '"subnet": "192.0.2.64/26", "reservations": []')
        got = D.subnet_files(text, "/etc/kea/kea-dhcp4.conf", "IPv4", [10, 20, 255])
        assert "subnet 20 lists reservations" in got["refused"] and "step 5" in got["refused"]

    def test_an_id_not_found_exactly_once_is_refused(self):
        got = D.subnet_files(MAIN4, "/etc/kea/kea-dhcp4.conf", "IPv4", [10, 30])
        assert "subnet 30's" in got["refused"] and "found 0 times" in got["refused"]


def test_the_host_step_s_check_reads_done_only_when_every_subnet_has_its_file(kea_dir):
    """The Update page's check for `[kea-reservation-files]` (modules/host_steps.py)."""
    from modules import host_steps
    kea = FakeKea(kea_dir["files"])
    got = host_steps.check_kea_reservation_files(kea=kea)
    assert got["state"] == "done", got
    main = kea_dir["main"]["IPv6"]
    text = open(main, encoding="utf-8").read()
    with open(main, "w", encoding="utf-8") as fh:
        fh.write(text.replace('"reservations": ' + D.directive(kea_dir["files"][("dhcp6", 30)])
                              + ",", ""))
    got = host_steps.check_kea_reservation_files(kea=kea)
    assert got == {"state": "not_done",
                   "detail": "still without Mercury's file: IPv6 subnet 30"}


def test_the_record_holds_mercury_s_reservations_but_not_ztp_s(kea_dir):
    _with(kea_dir, "IPv4", 20, [TestEditAndRemove.H2])
    _with(kea_dir, "IPv4", 255, [{"hw-address": "aa:aa:aa:aa:aa:aa", "ip-address": "10.255.0.9"}])
    assert D.held_by_mercury("Lab") == [
        {"family": "IPv4", "subnet": 20, "by": "MAC", "identity": "aa:c1:ab:3e:11:70",
         "addresses": ["10.10.20.101"], "hostname": "h2"}]
