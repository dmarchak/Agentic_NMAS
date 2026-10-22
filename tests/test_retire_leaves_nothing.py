"""Retirement leaves nothing a new device of the same name inherits (the operator's
device-lifecycle rule, 2026-10-19: a device leaves only by retirement, which removes or archives
every per-device artefact and frees the name; Lab 8 retires a device and onboards a NEW one of the
same name by ZTP). One class per register row, C1332 to C1342, and C1345's wording; each plants
the artefact, retires the device through `retire.plan` and `retire.apply`, and reads the
artefact's own store afterwards. The last class retires a device holding EVERY artefact, onboards
a new device of the same name, and asks the readers the device page and Needs attention use.

On a real repository, CSV, manifest, template library, approval queue, receipts, Topology stores,
heartbeat rules file and created-object record in a temp tree; Kea's writers and NetBox are the
seams named where they are patched (the DHCP page's and ZTP's writers have their own tests).
"""

import json
import os
import time

import pytest
import yaml

from modules.nsot import retire as RT

HOST, OTHER = "edge1", "edge2"
IP, OTHER_IP = "192.0.2.21", "192.0.2.22"
RESERVED = "192.0.2.121"
MAC = "52:54:00:00:21:01"
PW = "edge1-only-here-7c2d"
REASON = "replaced by new hardware"
ACTOR = "op@example.com"


@pytest.fixture
def lab(tmp_path, monkeypatch):
    """Two devices in the list 'Lab', each with intent, a golden and an identity, committed;
    a credential store, settings and NetBox as small seams; nothing else planted."""
    from modules import device
    from modules.nsot import hostvars, manifest, repo as R, templates_repo

    monkeypatch.setattr("modules.config.LISTS_DIR", str(tmp_path / "lists"))
    monkeypatch.setattr("modules.device.get_device_lists",
                        lambda: [{"name": "Lab", "filename": "lab"}])
    state = {"netbox": {"checked": False, "configured": False,
                        "reason": "NetBox URL and API token are not configured"},
             "held": [], "overrides": set()}
    monkeypatch.setattr(RT, "_netbox_facts", lambda l, h: state["netbox"])
    monkeypatch.setattr(RT, "_dhcp_held", lambda l: list(state["held"]))
    monkeypatch.setattr(RT, "_heartbeat_rules_path", lambda hb: str(tmp_path / "written.yaml"))
    monkeypatch.setattr(RT, "_heartbeat_installed_path", lambda: str(tmp_path / "installed.yaml"))
    monkeypatch.setattr(RT, "_telemetry_rules_path", lambda tel: str(tmp_path / "tel-written.yaml"))
    monkeypatch.setattr(RT, "_telemetry_installed_path",
                        lambda: str(tmp_path / "tel-installed.yaml"))
    monkeypatch.setattr("modules.credentials.has_device_override",
                        lambda ip: ip in state["overrides"])
    monkeypatch.setattr("modules.credentials.clear_device_override",
                        lambda ip: state["overrides"].discard(ip) or {"ok": True})
    monkeypatch.setattr("modules.nsot.ztp.kea_home", lambda l: {
        "owner": "Lab", "fragment": state.get("fragment", ""),
        "main_config": str(tmp_path / "kea-dhcp4.conf")})
    settings = {"nsot_git_author_name": "NMAS", "nsot_git_author_email": "n@l",
                "nsot_device_tag_retention": 50}
    import modules.settings_schema as ss
    monkeypatch.setattr(ss, "get_setting",
                        lambda k, d=None: settings.get(k, ss.DEFAULTS.get(k, d)))
    monkeypatch.setattr(ss, "write_settings", lambda updates, actor="": (
        settings.update(updates) or {"ok": True}))
    list_dir = tmp_path / "lists" / "lab"
    list_dir.mkdir(parents=True)
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda n: str(list_dir))
    monkeypatch.setattr("modules.nsot.hooks.run_post_commit", lambda c: None)
    monkeypatch.setattr("modules.attention._page_network", lambda: "Lab")
    # The installation's records each test writes, its own (a record a test before it left
    # in the session's data folder is not this test's).
    from modules import heartbeat_windows, netbox_guard
    for name in ("_CREATED_IDS_FILE", "_MODIFIED_FILE", "_ADOPTED_FILE", "_REMOVALS_FILE"):
        monkeypatch.setattr(netbox_guard, name, str(tmp_path / f"{name.strip('_').lower()}.json"))
    monkeypatch.setattr(heartbeat_windows, "_record_path",
                        lambda: str(tmp_path / "heartbeat_rules.jsonl"))
    repo = str(list_dir / "config_repo")
    R.init_repo(repo)
    templates_repo.seed_templates(repo)
    f = device.fernet
    rows = [{"hostname": h, "device_type": "cisco_xe", "ip": ip, "username": "admin",
             "password": f.encrypt(pw.encode()).decode(), "secret": "",
             "platform": "cisco_iosxe"}
            for h, ip, pw in ((HOST, IP, PW), (OTHER, OTHER_IP, "other-pw-1234567"))]
    csv_path = str(list_dir / "devices.csv")
    device.write_devices_csv(rows, csv_path)
    for h, ip in ((HOST, IP), (OTHER, OTHER_IP)):
        manifest.upsert_device(repo, manifest.new_device_uid(), h, mgmt_ip=ip,
                               platform="cisco_iosxe")
        hostvars.write_committed(repo, {"hostname": h, "platform": "cisco_iosxe"})
        with open(os.path.join(repo, "golden", f"{h}.cfg"), "w") as fh:
            fh.write(f"hostname {h}\n")
    R._commit_paths("Lab", [f"{d}/{h}.{x}" for h in (HOST, OTHER)
                            for d, x in (("host_vars", "yml"), ("golden", "cfg"))]
                    + [R.MANIFEST_REL], "seed", ["Source: test"], "test")
    return {"repo": repo, "csv": csv_path, "settings": settings, "state": state,
            "R": R, "tmp": tmp_path, "list_dir": str(list_dir)}


def _bg(host=HOST, pw=PW):
    return {"list_name": "Lab", "devices": [
        {"hostname": host, "list_name": "Lab", "username": "admin", "password": pw}]}


def _step(p, key):
    return next((s for s in p["steps"] if s["key"] == key), None)


def _retire(host=HOST, reason=REASON):
    p = RT.plan("Lab", host, reason)
    assert p["ok"], p["refusals"]
    out = RT.apply("Lab", host, reason=reason, actor=ACTOR, confirmed_hash=p["hash"],
                   breakglass=_bg(host))
    assert out["ok"], out
    return p, out


def _retire_body(lab):
    return lab["R"].git(lab["repo"], "log", "-1", "--format=%B",
                        "--grep=Retired-Device: " + HOST)[1]


def _golden_commit(lab, host, text):
    """A golden committed as a save commits it (its `Source:`), and its tag."""
    R = lab["R"]
    with open(os.path.join(lab["repo"], "golden", f"{host}.cfg"), "w") as fh:
        fh.write(text)
    got = R._commit_paths("Lab", [f"golden/{host}.cfg"], f"golden: {host}", [], "capture")
    assert got["ok"] and got["commit"], got
    return got["commit"]


def _tag(lab, name, ref="HEAD"):
    rc, _o, err = lab["R"].git(lab["repo"], "tag", "-a", name, "-m", f"{name} via test", ref)
    assert rc == 0, err


def _new_device(lab, host=HOST, ip=IP):
    """Onboarding's record of a NEW device of *host*: a row, an identity, intent, a golden
    and its golden tag, after the old one's retirement."""
    from modules import device
    from modules.nsot import hostvars, manifest
    rows = device.load_saved_devices(lab["csv"])
    rows.append({"hostname": host, "device_type": "cisco_xe", "ip": ip, "username": "admin",
                 "password": device.fernet.encrypt(b"new-device-pw-55").decode(),
                 "secret": "", "platform": "cisco_iosxe"})
    device.write_devices_csv(rows, lab["csv"])
    identity = manifest.new_device_uid()
    manifest.upsert_device(lab["repo"], identity, host, mgmt_ip=ip, platform="cisco_iosxe")
    hostvars.write_committed(lab["repo"], {"hostname": host, "platform": "cisco_iosxe"})
    lab["R"]._commit_paths("Lab", [f"host_vars/{host}.yml", lab["R"].MANIFEST_REL],
                           f"onboard: {host}", [], "onboarding")
    time.sleep(1.1)              # its golden is a second after the retirement, as a real one is
    _golden_commit(lab, host, f"hostname {host}\n! the new device\n")
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    _tag(lab, f"golden/{host}/{stamp}")
    return identity, f"golden/{host}/{stamp}"


# ----------------------------------------------------------------------------- C1332

class TestGoldenTagsAndBaselines:
    def _plant(self, lab):
        from modules.nsot import repo as R
        _golden_commit(lab, HOST, "hostname edge1\n! the old device\n")
        _tag(lab, f"golden/{HOST}/20261001T000000Z")
        _tag(lab, "baseline/20261001T000000Z")
        points = {p["ref"] for p in R.device_restore_points(lab["repo"], HOST)}
        assert {f"golden/{HOST}/20261001T000000Z", "baseline/20261001T000000Z"} <= points, \
            "the control: before retirement they are its restore points"

    def test_the_plan_says_where_the_tags_go_and_that_they_survive(self, lab):
        self._plant(lab)
        p = RT.plan("Lab", HOST, REASON)
        what = _step(p, "tags")["what"]
        assert not _step(p, "tags")["done"]
        assert f"archive its 1 golden tag(s) golden/{HOST}/*" in what
        assert f"retired/{HOST}/uid-" in what and "kept in git" in what
        assert "never offered as a restore point" in what

    def test_retirement_archives_them_and_a_new_device_is_offered_none(self, lab):
        from modules.nsot import repo as R
        self._plant(lab)
        old = R.git(lab["repo"], "rev-parse", f"golden/{HOST}/20261001T000000Z^{{commit}}")[1]
        _retire()
        assert R.git(lab["repo"], "tag", "--list", f"golden/{HOST}/*")[1].strip() == ""
        archived = R.git(lab["repo"], "tag", "--list", f"retired/{HOST}/*")[1].split()
        assert len(archived) == 1 and archived[0].endswith("/20261001T000000Z"), archived
        assert R.git(lab["repo"], "rev-parse", f"{archived[0]}^{{commit}}")[1] == old, \
            "the archive is the same commit"
        body = R.git(lab["repo"], "tag", "-l", "--format=%(contents)", archived[0])[1]
        assert f"Archived-From: golden/{HOST}/20261001T000000Z" in body
        _identity, new_tag = _new_device(lab)
        refs = [p["ref"] for p in R.device_restore_points(lab["repo"], HOST)]
        assert refs == ["HEAD", new_tag], refs

    def test_a_tag_fetched_back_under_its_old_name_is_still_not_offered(self, lab):
        """The remote keeps the old names (a push deletes no tag): a fetch could bring one
        back. A point at or before the name's retirement is never offered, whatever its name."""
        from modules.nsot import repo as R
        self._plant(lab)
        old = R.git(lab["repo"], "rev-parse", f"golden/{HOST}/20261001T000000Z^{{commit}}")[1]
        _retire()
        _tag(lab, f"golden/{HOST}/20261001T000000Z", old)
        refs = {p["ref"] for p in R.device_restore_points(lab["repo"], HOST)}
        assert f"golden/{HOST}/20261001T000000Z" not in refs
        assert "baseline/20261001T000000Z" not in refs


# ----------------------------------------------------------------------------- C1333

class TestRollbackBlock:
    SECRET = "S3cretOnlyHere77"

    def _plant(self, lab):
        from modules.nsot import hostvars
        hostvars.record_rolled_back(lab["repo"], HOST, "a" * 40, reason="verify failed",
                                    commands=["interface GigabitEthernet2", " shutdown",
                                              f"username op secret 0 {self.SECRET}"])

    def test_archived_in_the_retire_record_masked_then_cleared(self, lab):
        from modules.nsot import hostvars
        self._plant(lab)
        p = RT.plan("Lab", HOST, REASON)
        what = _step(p, "rolled_back")["what"]
        assert "3 command(s) rolled back" in what and "archived first" in what
        assert "survives there" in what
        _retire()
        assert hostvars.rolled_back_note(lab["repo"], HOST) is None
        body = _retire_body(lab)
        lines = [l for l in body.splitlines() if l.startswith("Rollback-Block: ")]
        assert len(lines) == 1, body
        block = json.loads(lines[0][len("Rollback-Block: "):])
        assert block["reason"] == "verify failed" and len(block["commands"]) == 3
        assert block["command_fingerprint"]
        assert self.SECRET not in body, "the archived commands are masked"

    def test_a_run_finishing_after_the_commit_archives_it_before_clearing(self, lab,
                                                                         monkeypatch):
        """The commit landed and the clear did not: the next run records the block in a
        commit of its own first, never clears it unread."""
        from modules.nsot import hostvars
        self._plant(lab)
        p = RT.plan("Lab", HOST, REASON)
        real = hostvars.clear_rolled_back
        monkeypatch.setattr(hostvars, "clear_rolled_back",
                            lambda *a: (_ for _ in ()).throw(OSError("disk full")))
        out = RT.apply("Lab", HOST, reason=REASON, actor=ACTOR, confirmed_hash=p["hash"],
                       breakglass=_bg())
        assert out.get("failed_at") == "rolled_back" and "commit" in out["done"], out
        monkeypatch.setattr(hostvars, "clear_rolled_back", real)
        # The first commit carried the block; drop its record to show the rerun's own.
        p2 = RT.plan("Lab", HOST, REASON)
        assert [s["key"] for s in p2["steps"] if not s["done"]] == ["rolled_back", "row"]
        out = RT.apply("Lab", HOST, reason=REASON, actor=ACTOR, confirmed_hash=p2["hash"],
                       breakglass=_bg())
        assert out["ok"], out
        head = lab["R"].git(lab["repo"], "log", "-1", "--format=%B")[1]
        assert "Rollback-Block: " in head and f"retire: {HOST} -- record" in head
        assert hostvars.rolled_back_note(lab["repo"], HOST) is None


# ----------------------------------------------------------------------------- C1334

def _receipt(at, outcome="failed", host=HOST, line="no ip ssh version 2"):
    """A receipt row as the deploy writes it (`receipts.rows_for`), its time set."""
    from modules.nsot import receipts
    (row,) = receipts.rows_for(
        {"results": [{"device": host, "outcome": outcome, "stage": "verify",
                      "reason": "verify found an interface down",
                      "commands": ["interface GigabitEthernet2", " shutdown", line],
                      "authorised": [{"line": line, "reason": "a lab exception"}]}],
         "golden": {}}, list_name="Lab", action="deploy", actor=ACTOR, actor_kind="person")
    return dict(row, at=at)


def _iso(offset_s: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + offset_s))


class TestReceipts:
    @property
    def OLD(self):               # written a day before the retirement
        return _iso(-86400)

    def test_a_retired_devices_receipts_pass_to_no_new_device(self, lab):
        from modules import attention
        from modules.nsot import receipts
        receipts.write("Lab", [_receipt(self.OLD), _receipt(self.OLD)])
        before = receipts.prior_authorisations("Lab", HOST)
        assert before["lines"], "the control: before retirement it has authorisations"
        rows = attention.deploy_source()["rows"]
        assert any(HOST in (r.get("devices") or []) for r in rows), "the control: a row"
        _retire()
        assert receipts.prior_authorisations("Lab", HOST)["lines"] == {}
        assert receipts.authorisations_by_device("Lab")["devices"].get(HOST) is None
        rows = attention.deploy_source()["rows"]
        assert not any(HOST in (r.get("devices") or []) for r in rows), rows
        # The record keeps them: History reads every receipt.
        assert len(receipts.read("Lab", device=HOST)["rows"]) == 2

    def test_a_new_devices_own_receipt_counts(self, lab):
        from modules import attention
        from modules.nsot import receipts
        receipts.write("Lab", [_receipt(self.OLD)])
        _retire()
        receipts.write("Lab", [_receipt(_iso(3600))])
        assert receipts.prior_authorisations("Lab", HOST)["lines"]["no ip ssh version 2"][
            "count"] == 1
        rows = attention.deploy_source()["rows"]
        assert sum(HOST in (r.get("devices") or []) for r in rows) == 1


# ----------------------------------------------------------------------------- C1335

class TestKeaReservations:
    def _fragment(self, lab, entries):
        path = lab["tmp"] / "ztp-fragment.json"
        path.write_text(json.dumps(entries))
        lab["state"]["fragment"] = str(path)
        return path

    def test_ztp_and_dhcp_reservations_are_removed_through_their_own_writers(self, lab,
                                                                             monkeypatch):
        from modules import dhcp_reservations as D
        from modules.nsot import ztp
        self._fragment(lab, [ztp.reservation_entry(MAC, IP, HOST, "192.0.2.1"),
                             ztp.reservation_entry("52:54:00:00:22:01", OTHER_IP, OTHER,
                                                   "192.0.2.1")])
        lab["state"]["held"] = [
            {"family": "IPv4", "subnet": 7, "by": "MAC", "identity": "52:54:00:00:21:02",
             "addresses": ["192.0.2.31"], "hostname": HOST},
            {"family": "IPv4", "subnet": 7, "by": "MAC", "identity": "52:54:00:00:22:02",
             "addresses": ["192.0.2.32"], "hostname": OTHER}]
        calls = {"ztp": [], "plan": [], "apply": []}

        def write_reservations(adds=(), removes=(), **kw):
            calls["ztp"].append((list(removes), kw["list_name"], kw["actor"]))
            return {"ok": True, "outcomes": {m: {"outcome": "removed", "detail": "gone"}
                                             for m in removes},
                    "record": {"ok": True, "commit": "c0ffee00", "owner": "Lab"}}

        monkeypatch.setattr(ztp, "write_reservations", write_reservations)
        monkeypatch.setattr(D, "plan", lambda l, v: calls["plan"].append(v) or {
            "ok": True, "hash": "h-" + v["was"], "not_done": ["192.0.2.31 is leased to no one"]})
        monkeypatch.setattr(D, "apply", lambda l, v, h, **kw: calls["apply"].append(
            (v, h, kw["actor"], kw["reason"])) or {"ok": True})
        p = RT.plan("Lab", HOST, REASON)
        what = _step(p, "reservations")["what"]
        assert f"ZTP's reservation for {MAC} ({IP})" in what
        assert "IPv4 subnet 7: MAC 52:54:00:00:21:02 -> 192.0.2.31" in what
        assert "stays in that record's history" in what
        assert calls["plan"] == [{"op": "remove", "family": "IPv4", "subnet": "7",
                                  "was": "hw-address=52:54:00:00:21:02"}]
        _retire()
        assert calls["ztp"] == [([MAC], "Lab", ACTOR)]
        assert [(v["was"], h) for v, h, _a, _r in calls["apply"]] == [
            ("hw-address=52:54:00:00:21:02", "h-hw-address=52:54:00:00:21:02")]
        assert calls["apply"][0][3] == f"{HOST} retired: {REASON}"

    def test_a_reservation_is_matched_by_address_in_either_family(self, lab):
        """IPv6 beside IPv4: an address the device was known by, written in another form."""
        for addr, held in (("192.0.2.21", "192.0.2.21"), ("2001:db8::21", "2001:DB8:0::21")):
            lab["state"]["held"] = [{"family": "IPv6" if ":" in held else "IPv4",
                                     "subnet": 9, "by": "DUID", "identity": "00:01:aa",
                                     "addresses": [held], "hostname": ""}]
            import modules.dhcp_reservations as D
            real = D.plan
            D.plan = lambda l, v: {"ok": True, "hash": "h", "not_done": []}
            try:
                got = RT._reservation_facts("Lab", HOST, None, [addr])
            finally:
                D.plan = real
            assert len((got.get("work") or {}).get("dhcp") or []) == 1, (addr, got)

    def test_none_is_a_done_step_saying_so(self, lab):
        p = RT.plan("Lab", HOST, REASON)
        s = _step(p, "reservations")
        assert s["done"] and "no Kea reservation names it" in s["what"]


# ----------------------------------------------------------------------------- C1403

class TestKeaLeases:
    """A lease outlives its reservation and refuses the address to the next device asking with
    another client identifier (0d's run 2): every lease Kea holds for the device, either family,
    by its MAC or an address it was known by, is named in the plan and released at the apply
    through the one release (`dhcp_leases.release_for_device`), read back and recorded."""

    def _leases(self):
        from modules import dhcp_leases as L
        return [L.row({"ip-address": IP, "hw-address": MAC, "client-id": "01:52:54:00:00:21:01",
                       "subnet-id": 7, "cltt": 1760911000, "valid-lft": 604800, "state": 0},
                      "IPv4"),
                L.row({"ip-address": "2001:db8::21", "duid": "00:03:00:01:52:54:00:00:21:01",
                       "hw-address": MAC, "subnet-id": 9, "type": "IA_NA", "iaid": 1,
                       "cltt": 1760911000, "valid-lft": 604800, "state": 0}, "IPv6")]

    def test_its_leases_are_named_and_released_through_the_one_release(self, lab, monkeypatch):
        from modules import dhcp_leases as L
        asked, released = [], []
        monkeypatch.setattr(RT, "_device_leases", lambda l, macs, addresses: asked.append(
            (l, macs, addresses)) or {"ok": True, "configured": True, "leases": self._leases(),
                                      "error": ""})
        monkeypatch.setattr(L, "release_for_device", lambda l, leases, **kw: released.append(
            (l, [r["address"] for r in leases], kw)) or {"ok": True, "outcomes": [],
                                                         "commit": "feed1234", "error": ""})
        p = RT.plan("Lab", HOST, REASON)
        what = _step(p, "leases")["what"]
        assert f"{IP} (IPv4, MAC {MAC})" in what and "2001:db8::21 (IPv6, DUID" in what, what
        assert asked and IP in asked[0][2]
        _p, out = _retire()
        assert "leases" in out["done"]
        assert [(l, a) for l, a, _kw in released] == [("Lab", [IP, "2001:db8::21"])], released
        assert released[0][2]["actor"] == ACTOR and REASON in released[0][2]["reason"]

    def test_kea_not_answering_refuses_the_plan_naming_the_leases(self, lab, monkeypatch):
        monkeypatch.setattr(RT, "_device_leases", lambda l, macs, addresses: {
            "ok": False, "configured": True, "leases": [], "error": "IPv4: connection refused"})
        p = RT.plan("Lab", HOST, REASON)
        assert not p["ok"]
        assert "could not read is not none" in p["refused_by"]["leases"], p["refused_by"]

    def test_none_is_a_done_step_saying_so(self, lab, monkeypatch):
        monkeypatch.setattr(RT, "_device_leases", lambda l, macs, addresses: {
            "ok": True, "configured": True, "leases": [], "error": ""})
        s = _step(RT.plan("Lab", HOST, REASON), "leases")
        assert s["done"] and "no Kea lease names it" in s["what"]


class TestTheLinkSubnetAddDeviceAdded:
    """C1460: Retire removes the relayed ZTP subnet its Add device added for its link, through
    the subnet writer, only when nothing else is in it once its own reservation and lease go;
    a subnet still serving another device stays, said; none added is a done step."""

    LINK = "198.51.100.4/30"

    def _sub(self, reservations=(), leases=()):
        return [{"id": 41, "prefix": self.LINK, "reservations": list(reservations),
                 "leases": list(leases)}]

    def _quiet(self, monkeypatch):
        monkeypatch.setattr(RT, "_device_leases", lambda l, macs, addresses: {
            "ok": True, "configured": True, "leases": [], "error": ""})

    def test_its_subnet_is_removed_through_the_writer_bound_by_its_hash(self, lab, monkeypatch):
        from modules import dhcp_subnets as S
        self._quiet(monkeypatch)
        monkeypatch.setattr(RT, "_created_link_subnets", lambda l, h: self._sub(
            reservations=[{"hw-address": MAC, "ip-address": IP, "hostname": HOST}]))
        calls = []
        monkeypatch.setattr(S, "plan", lambda l, values, **kw: calls.append(("plan", values)) or {
            "ok": True, "before": {"subnet": self.LINK}, "hash": "h-rm", "refused": ""})
        monkeypatch.setattr(S, "apply_edit", lambda l, values, h, **kw: calls.append(
            ("apply", values["op"], values["id"], h, kw.get("actor"))) or {"ok": True})
        p = RT.plan("Lab", HOST, REASON)
        s = _step(p, "ztp_subnet")
        assert not s["done"] and f"remove Kea subnet 41 ({self.LINK})" in s["what"]
        _p, out = _retire()
        assert "ztp_subnet" in out["done"]
        assert calls[-1] == ("apply", "remove", "41", "h-rm", ACTOR), calls

    def test_a_subnet_still_serving_another_device_stays_and_is_said(self, lab, monkeypatch):
        self._quiet(monkeypatch)
        monkeypatch.setattr(RT, "_created_link_subnets", lambda l, h: self._sub(
            reservations=[{"hw-address": "aa:bb:cc:00:09:09", "ip-address": "198.51.100.6",
                           "hostname": "other-dev"}]))
        p = RT.plan("Lab", HOST, REASON)
        assert _step(p, "ztp_subnet")["done"]
        assert any("Kea subnet 41" in n and "1 other reservation(s)" in n
                   for n in p["not_doing"]), p["not_doing"]

    def test_none_added_is_a_done_step_saying_so(self, lab, monkeypatch):
        self._quiet(monkeypatch)
        monkeypatch.setattr(RT, "_created_link_subnets", lambda l, h: [])
        s = _step(RT.plan("Lab", HOST, REASON), "ztp_subnet")
        assert s["done"] and "no Kea subnet was added for its link" in s["what"]

    def test_subnets_that_cannot_be_read_refuse_the_plan(self, lab, monkeypatch):
        self._quiet(monkeypatch)

        def boom(l, h):
            raise OSError("permission denied")
        monkeypatch.setattr(RT, "_created_link_subnets", boom)
        p = RT.plan("Lab", HOST, REASON)
        assert not p["ok"] and "could not read is not none" in p["refused_by"]["ztp_subnet"]

    def test_only_a_subnet_recording_this_device_is_its_own(self, lab, monkeypatch, tmp_path):
        """The read: a person's subnet and another device's are never this device's."""
        from modules import dhcp_leases, dhcp_reservations as D, dhcp_subnets as S
        from modules.nsot import ztp_relayed
        nmas = tmp_path / "kea" / "nmas"
        nmas.mkdir(parents=True)
        main = tmp_path / "kea" / "kea-dhcp4.conf"
        main.write_text("{}\n")
        decl = ztp_relayed.declaration()
        subnets = [
            {"id": 41, "subnet": self.LINK, "user-context": dict(decl, **{
                ztp_relayed.CREATED_BY: {"device": HOST, "list": "Lab"}})},
            {"id": 42, "subnet": "198.51.100.8/30", "user-context": dict(decl)},
            {"id": 43, "subnet": "198.51.100.12/30", "user-context": dict(decl, **{
                ztp_relayed.CREATED_BY: {"device": OTHER, "list": "Lab"}})}]
        for s in subnets:
            (nmas / f"reservations4-{s['id']}.json").write_text("[]\n")
        monkeypatch.setattr(D, "main_config", lambda l, fam: str(main))
        monkeypatch.setattr(S, "subnets_file", lambda m, fam: str(nmas / "subnets4.json"))
        (nmas / "subnets4.json").write_text(S.dump(subnets))
        monkeypatch.setattr(D, "fragment", lambda m, fam, sid: str(nmas / f"reservations4-{sid}.json"))
        monkeypatch.setattr(dhcp_leases, "_kea_for", lambda l: None)
        monkeypatch.setattr(dhcp_leases, "read", lambda kea, fam: [])
        got = RT._created_link_subnets("Lab", HOST)                          # noqa: SLF001
        assert [g["id"] for g in got] == [41] and got[0]["prefix"] == self.LINK


# ----------------------------------------------------------------------------- C1336

class TestRotationPolicies:
    def _plant(self, lab):
        lab["settings"]["credential_rotation_policies"] = {
            "role:edge": {"state": "on", "days": 90, "devices": [OTHER, HOST]},
            "site:lab": {"state": "on", "days": 30, "devices": [HOST]}}

    def test_the_name_leaves_every_policy_and_a_pilot_of_one_is_turned_off(self, lab):
        from modules.nsot import scheduled_rotation as SR
        self._plant(lab)
        p = RT.plan("Lab", HOST, REASON)
        what = _step(p, "rotation_policy")["what"]
        assert "role:edge" in what and "turn off the rotation policy of site:lab" in what
        assert "would widen it" in what
        _retire()
        pols = lab["settings"]["credential_rotation_policies"]
        assert pols["role:edge"]["devices"] == [OTHER] and pols["role:edge"]["state"] == "on"
        assert pols["site:lab"]["state"] == "off" and "devices" not in pols["site:lab"]
        assert SR.policies_naming(HOST) == {}

    def test_a_retired_devices_rotation_age_is_not_inherited(self, lab):
        from modules.nsot import scheduled_rotation as SR
        old = time.time() - 30 * 86400
        kw = dict(lists=["Lab"], devices_of=lambda l: [{"hostname": HOST, "role": "edge"}],
                  rotations={HOST: (old, "2026-09-19T00:00:00Z")},
                  pols={"role:edge": {"state": "on", "days": 90}},
                  profile_names={"role:edge"})
        assert SR.device_states(**kw)[0]["never"] is False, "the control: before, its age"
        _retire()
        got = SR.device_states(**kw)[0]
        assert got["never"] is True and got["rotated_at"] == "", got

    def test_kept_while_another_network_has_a_device_of_the_name(self, lab, monkeypatch):
        from modules import device
        self._plant(lab)
        other = os.path.join(os.path.dirname(lab["list_dir"]), "other")
        os.makedirs(other)
        device.write_devices_csv([{"hostname": HOST, "device_type": "cisco_xe",
                                   "ip": "192.0.2.99", "username": "a", "password": "",
                                   "secret": "", "platform": "cisco_iosxe"}],
                                 os.path.join(other, "devices.csv"))
        monkeypatch.setattr("modules.device.get_device_lists", lambda: [
            {"name": "Lab", "filename": "lab"}, {"name": "Other", "filename": "other"}])
        p = RT.plan("Lab", HOST, REASON)
        assert _step(p, "rotation_policy") is None
        assert any("keep the name" in n and "also a device in Other" in n
                   for n in p["not_doing"]), p["not_doing"]


# ----------------------------------------------------------------------------- C1337

class TestTemplateOverride:
    def test_the_override_leaves_in_the_retire_commit(self, lab):
        from modules.nsot import templates_repo as T
        b = T.load_bindings(lab["repo"])
        b["overrides"][HOST] = "cisco_iosxe/custom.j2"
        T.save_bindings(lab["repo"], b)
        lab["R"]._commit_paths("Lab", ["templates/bindings.yml"], "bind", [], "templates")
        p = RT.plan("Lab", HOST, REASON)
        assert "its template override (cisco_iosxe/custom.j2) from templates/bindings.yml" in \
            _step(p, "commit")["what"]
        _retire()
        assert HOST not in T.load_bindings(lab["repo"])["overrides"]
        assert T.template_for_device(lab["repo"], HOST, "cisco_iosxe") != "cisco_iosxe/custom.j2"
        changed = lab["R"].git(lab["repo"], "log", "-1", "--name-only", "--format=",
                               "--grep=Retired-Device: " + HOST)[1]
        assert "templates/bindings.yml" in changed, changed
        assert lab["R"].git(lab["repo"], "status", "--porcelain", "--",
                            "templates/bindings.yml")[1].strip() == ""


# ----------------------------------------------------------------------------- C1338

def _rules(path, devices):
    doc = {"apiVersion": 1, "groups": [{"name": "nmas-heartbeat", "rules": [
        {"labels": {"device": d, "window_basis": "measured"},
         "data": [{"relativeTimeRange": {"from": 915}, "datasourceUid": "u"}]}
        for d in devices]}]}
    path.write_text(yaml.safe_dump(doc))


class TestHeartbeatRule:
    def test_the_rule_leaves_the_generated_file_and_the_host_step_is_named(self, lab):
        from modules import heartbeat_windows as HW
        _rules(lab["tmp"] / "installed.yaml", [OTHER, HOST])
        p = RT.plan("Lab", HOST, REASON)
        what = _step(p, "heartbeat")["what"]
        assert "remove its Grafana heartbeat rule (window 915 s)" in what
        assert f"c1419-install-alert-rules.sh heartbeat {lab['tmp'] / 'written.yaml'} " in what
        assert "name it in its delete file (C1419)" in what
        _p, out = _retire()
        assert (lab["tmp"] / "written.yaml").exists(), "the rules were not written without it"
        doc = yaml.safe_load((lab["tmp"] / "written.yaml").read_text())
        devices = [r["labels"]["device"] for g in doc["groups"] for r in g["rules"]]
        assert devices == [OTHER], devices
        rec = HW.records()["rows"][-1]
        assert rec["removed"] == [HOST] and rec["actor"] == ACTOR
        assert any("Grafana deletes it once the host step installs both" in a
                   for a in out["advisories"])

    def test_a_moved_file_refuses_with_nothing_written(self, lab):
        from modules import heartbeat_windows as HW
        _rules(lab["tmp"] / "installed.yaml", [OTHER, HOST])
        got = HW.drop_device(HOST, "not-the-fingerprint", actor=ACTOR, why="x",
                             written_path=str(lab["tmp"] / "written.yaml"),
                             installed_path=str(lab["tmp"] / "installed.yaml"))
        assert not got["ok"] and "moved since the preview" in got["error"]
        assert not (lab["tmp"] / "written.yaml").exists()


# ----------------------------------------------------------------------------- C1419 part 2

def _tel_rules(path, devices):
    """A telemetry rules document as the generator writes it: subscriptions 101 and 102 per
    device, each rule labelled with its device and carrying its uid."""
    from modules import telemetry_rules as TR
    rules = [{"uid": f"{TR.device_prefix(d)}{s}", "title": f"NMAS telemetry stream lost: {d} "
              f"subscription {s}", "labels": {"device": d, "subscription": s}}
             for d in devices for s in ("101", "102")]
    path.write_text(yaml.safe_dump({"apiVersion": 1, "groups": [
        {"orgId": 1, "name": "nmas-telemetry", "folder": "NMAS", "rules": rules}]}))


class TestTelemetryRules:
    """Retire's telemetry step (C1419 part 2): a retired device's telemetry rules outlived it
    (Lab 8 step 1), since nothing ran the generator after its golden left and Grafana keeps a
    rule its file dropped. The step drops them from the generated file and names them in its
    delete file, as the heartbeat step does."""

    def test_the_rules_leave_the_file_and_are_named_for_deletion(self, lab, monkeypatch):
        from modules import grafana_rule_deletes as GD
        monkeypatch.setattr(GD, "live_uids", lambda prefix, client=None: (None, "not asked"))
        _tel_rules(lab["tmp"] / "tel-installed.yaml", [OTHER, HOST])
        p = RT.plan("Lab", HOST, REASON)
        what = _step(p, "telemetry")["what"]
        assert f"remove its 2 Grafana telemetry rule(s) (nmas-tel-{HOST}-101, " \
               f"nmas-tel-{HOST}-102)" in what
        assert f"c1419-install-alert-rules.sh telemetry {lab['tmp'] / 'tel-written.yaml'} " in what
        _p, out = _retire()
        assert "telemetry" in out["done"], out
        doc = yaml.safe_load((lab["tmp"] / "tel-written.yaml").read_text())
        assert {r["labels"]["device"] for g in doc["groups"] for r in g["rules"]} == {OTHER}
        deletes = yaml.safe_load((lab["tmp"] / "tel-written-delete.yaml").read_text())
        assert [d["uid"] for d in deletes["deleteRules"]] == [f"nmas-tel-{HOST}-101",
                                                             f"nmas-tel-{HOST}-102"]
        assert any("Grafana deletes them once the host step installs both" in a
                   for a in out["advisories"])

    def test_no_file_names_it_and_grafana_runs_none_is_no_step(self, lab, monkeypatch):
        from modules import grafana_rule_deletes as GD
        monkeypatch.setattr(GD, "live_uids", lambda prefix, client=None: (set(), ""))
        _tel_rules(lab["tmp"] / "tel-installed.yaml", [OTHER])
        p = RT.plan("Lab", HOST, REASON)
        assert not [s for s in p["steps"] if s["key"] == "telemetry" and not s["done"]]


# ----------------------------------------------------------------------------- C1339

class TestApprovalQueue:
    def test_its_items_are_withdrawn_and_a_new_device_queues_again(self, lab):
        from modules import approval_queue as Q
        old = Q.add_approval("update_golden_config", f"drift on {HOST}", IP, HOST,
                             list_name="Lab")
        keep = Q.add_approval("update_golden_config", f"drift on {OTHER}", OTHER_IP, OTHER,
                              list_name="Lab")
        p = RT.plan("Lab", HOST, REASON)
        assert "withdraw its 1 pending approval-queue item(s)" in _step(p, "approvals")["what"]
        _retire()
        pending, _err = Q.read_pending("Lab")
        assert [e["id"] for e in pending] == [keep]
        gone = next(e for e in Q._read("Lab") if e["id"] == old)
        assert gone["status"] == "withdrawn" and gone["withdrawn_by"] == f"retire ({ACTOR})"
        assert REASON in gone["withdrawn_reason"]
        assert Q.add_approval("update_golden_config", "drift on the new one", IP, HOST,
                              list_name="Lab") != old, "the address dedup no longer hides it"

    @pytest.mark.parametrize("known,queued", [("192.0.2.21", "192.0.2.21"),
                                              ("2001:db8::21", "2001:DB8:0::21")])
    def test_an_item_is_matched_by_address_in_either_family(self, lab, known, queued):
        from modules import approval_queue as Q
        Q.add_approval("update_golden_config", "drift", queued, queued, list_name="Lab")
        got = RT._approval_facts("Lab", HOST, [known])
        assert len((got.get("work") or {}).get("ids") or []) == 1, got


# ----------------------------------------------------------------------------- C1340

class TestStagedCredentialAndOverrides:
    def test_the_staged_password_the_sidecar_and_every_override_go(self, lab):
        from modules.nsot import adopt as A, credential_rotation as CR, manifest
        ident, _e = manifest.find_by_name(lab["repo"], HOST)
        manifest.upsert_device(lab["repo"], ident, HOST, mgmt_ip=IP, platform="cisco_iosxe",
                               reserved_address=RESERVED)
        lab["R"]._commit_paths("Lab", [lab["R"].MANIFEST_REL], "reserve", [], "test")
        lab["state"]["overrides"] |= {IP, RESERVED}
        CR.stage_plaintext(lab["repo"], HOST, PW)
        A.write_sidecar(lab["repo"], HOST, IP, "cisco_xe", "nmas")
        p = RT.plan("Lab", HOST, REASON)
        assert f"{IP} and {RESERVED}" in _step(p, "override")["what"]
        assert "the same password as the CSV row's" in _step(p, "staged")["what"]
        _retire()
        assert lab["state"]["overrides"] == set()
        assert CR.staged_plaintext(lab["repo"], HOST) is None
        assert not A.is_adoption_staged(lab["repo"], HOST)

    def test_a_staged_password_that_is_not_the_rows_refuses(self, lab):
        from modules.nsot import credential_rotation as CR
        CR.stage_plaintext(lab["repo"], HOST, "an-interrupted-rotation-91")
        p = RT.plan("Lab", HOST, REASON)
        assert not p["ok"]
        assert "nmas-rotation-recover" in p["refused_by"]["staged"]
        assert "an-interrupted-rotation-91" not in json.dumps(p)


# ----------------------------------------------------------------------------- C1341

class TestTopology:
    def test_its_declaration_and_place_are_removed_and_recorded(self, lab):
        from modules import topology_expected as TE, topology_positions as TP
        assert TE.declare("Lab", HOST, "apart on purpose: its own segment", "op")["ok"]
        assert TP.save("Lab", {HOST: [100, 100], OTHER: [300, 100]}, "op", moved=HOST)["ok"]
        p = RT.plan("Lab", HOST, REASON)
        what = _step(p, "topology")["what"]
        assert "withdraw its expected-island declaration" in what and "arranged" in what
        _retire()
        assert HOST not in TE.read("Lab")["islands"]
        assert TP.read("Lab")["positions"] == {OTHER: [300, 100]}
        assert TE.history(lab["list_dir"])["rows"][-1]["action"] == "withdrew"
        last = TP.history(lab["list_dir"])["rows"][-1]
        assert last["action"] == "forgot" and last["device"] == HOST


# ----------------------------------------------------------------------------- C1342

@pytest.fixture
def netbox(lab, monkeypatch):
    import modules.netbox_client as nbc
    from modules import netbox_guard
    from tests.fake_netbox import FakeNetBox

    fake = FakeNetBox()
    fake.seed("dcim/devices", {"id": 31, "name": HOST, "local_context_data": {},
                               "status": {"value": "active", "label": "Active"},
                               "tags": [{"slug": "nmas-managed", "name": "nmas-managed"}]})
    state = {"writes": True}
    monkeypatch.setattr(nbc, "_nb_ready", lambda: (True, "", fake, "http://127.0.0.1:9"))
    monkeypatch.setattr(netbox_guard, "read_modified", lambda: ({}, None))
    monkeypatch.setattr(netbox_guard, "writes_allowed", lambda: state["writes"])
    monkeypatch.setattr(RT, "_netbox_facts", _REAL_FACTS)        # NetBox read, through the fake
    with netbox_guard.for_list("Lab", actor="op", authority="test"):
        netbox_guard.record_created("Lab", "dcim/devices", 31, HOST)
    return {"fake": fake, "state": state}


_REAL_FACTS = RT._netbox_facts


class TestNetBoxRecord:
    def test_decommissioned_renamed_kept_and_its_entry_marked(self, lab, netbox):
        from modules import netbox_guard
        from modules.nsot import onboard
        p = RT.plan("Lab", HOST, REASON)
        what = _step(p, "netbox_record")["what"]
        assert f"set NetBox device 31 to Decommissioning and rename it {HOST}-retired-31" in what
        assert "KEPT" in what and "retired: kept with its id" in what
        _retire()
        rec = next(d for d in netbox["fake"].store["dcim/devices"] if d["id"] == 31)
        assert rec["name"] == f"{HOST}-retired-31" and \
            (rec["status"] == "decommissioning"
             or (rec["status"] or {}).get("value") == "decommissioning")
        (entry,) = netbox_guard.get_created("Lab", "dcim/devices")["dcim/devices"]
        assert entry["id"] == 31 and (entry.get("retired") or {}).get("device") == HOST
        assert onboard._device_id_from(netbox_guard.get_created("Lab"), HOST) is None
        # A new device of the name gets a NEW record, and only it is matched by name.
        with netbox_guard.for_list("Lab", actor="op", authority="test"):
            netbox_guard.record_created("Lab", "dcim/devices", 32, HOST)
        assert onboard._device_id_from(netbox_guard.get_created("Lab"), HOST) == 32

    def test_writes_off_says_what_was_not_done_and_still_marks_the_entry(self, lab, netbox):
        from modules import netbox_guard
        netbox["state"]["writes"] = False
        p = RT.plan("Lab", HOST, REASON)
        assert any("NOT set to Decommissioning or renamed: NetBox writes are off" in n
                   for n in p["not_doing"]), p["not_doing"]
        survives = next(w["how"] for w in p["survives"] if w["what"].startswith("the NetBox"))
        assert "NOT set to Decommissioning" in survives
        _retire()
        assert netbox["fake"].patches == []
        (entry,) = netbox_guard.get_created("Lab", "dcim/devices")["dcim/devices"]
        assert entry.get("retired")

    def test_a_new_identity_is_not_held_back_by_the_retired_entry(self, lab, netbox):
        from modules.nsot import manifest
        _retire()
        identity, _tag = _new_device(lab)
        assert not [r for r in manifest.references(lab["repo"], identity, "Lab")
                    if r["kind"] == "netbox"]

    def test_abandon_deletes_by_id_never_by_name(self, lab, netbox, monkeypatch):
        """Two records named edge1 (two sites; the first a retired device's, created by
        Mercury and tagged): abandoning the NEW onboarding deletes its record, by its id."""
        import modules.netbox_client as nbc
        from modules import netbox_guard
        fake = netbox["fake"]
        netbox_guard.mark_created_retired("Lab", "dcim/devices", [31], device=HOST, by="op")
        fake.seed("dcim/devices", {"id": 32, "name": HOST, "local_context_data": {},
                                   "status": {"value": "planned", "label": "Planned"},
                                   "tags": [{"slug": "nmas-managed", "name": "nmas-managed"}]})
        with netbox_guard.for_list("Lab", actor="op", authority="test"):
            netbox_guard.record_created("Lab", "dcim/devices", 32, HOST)
        monkeypatch.setattr(nbc, "get_netbox_config",
                            lambda: {"url": "http://127.0.0.1:9", "token": "t"})
        monkeypatch.setattr(nbc, "_session_from_config", lambda cfg: fake)
        got = nbc.remove_device_from_netbox("Lab", HOST, actor="op", authority="abandon")
        assert got["ok"], got
        assert [d for d in fake.deletes if d[0] == "dcim/devices"] == [("dcim/devices", 32)]
        assert [d["id"] for d in fake.store["dcim/devices"]] == [31]


# ----------------------------------------------------------------------------- C1553

def _console_path(fake, *, ours: bool, cable_ours: bool = None):
    """A console path on device 31 to port 5 of console server cons-1; the console port and
    the cable recorded as Mercury's when *ours* (*cable_ours*, default the same)."""
    from modules import netbox_guard
    cs = fake.seed("dcim/devices", {"name": "cons-1", "status": "active"})
    port = fake.seed("dcim/console-ports", {"device": 31, "name": "con 0"})
    sport = fake.seed("dcim/console-server-ports", {"device": cs["id"], "name": "port 5"})
    cable = fake.seed("dcim/cables", {
        "a_terminations": [{"object_type": "dcim.consoleport", "object_id": port["id"]}],
        "b_terminations": [{"object_type": "dcim.consoleserverport", "object_id": sport["id"]}],
        "status": "connected", "label": ""})
    tag = [{"slug": "nmas-managed", "name": "nmas-managed"}]
    with netbox_guard.for_list("Lab", actor="op", authority="test"):
        if ours:
            port["tags"] = tag
            netbox_guard.record_created("Lab", "dcim/console-ports", port["id"], "con 0")
        if ours if cable_ours is None else cable_ours:
            cable["tags"] = tag
            netbox_guard.record_created("Lab", "dcim/cables", cable["id"], "")
    return port, sport, cable


def _console_runs(lab, device_id=31):
    """A blank survey of edge1 and a stopped one of edge2, recorded and indexed as runs are."""
    from modules.nsot import console_ztp as Z, reads
    recs = []
    for host, dev_id, blank in ((HOST, device_id, True), (OTHER, 77, False)):
        rec = {"id": reads.new_id(), "kind": Z.KIND_SURVEY, "list": "Lab",
               "device_id": dev_id, "device": host, "actor": "op", "outcome": "surveyed",
               "blank": blank, "at": "2026-10-22T10:00:00Z", "port_id": 5}
        recs.append(Z.record("Lab", rec))
    return recs


class TestConsolePathAndRuns:
    """C1553: the console port and cable Mercury made for it leave NetBox, its console runs
    move aside and leave the index; the console server's port and Mercury's record of how to
    reach it stay (they are the console server's)."""

    @pytest.fixture(autouse=True)
    def own_data(self, tmp_path, monkeypatch):
        """The installation's console ZTP index and console-server store, this test's own."""
        data = tmp_path / "install-data"
        data.mkdir()
        monkeypatch.setattr("modules.config.DATA_DIR", str(data))

    def test_the_plan_names_it_and_retirement_removes_it(self, lab, netbox, monkeypatch):
        from modules.nsot import console_servers, console_ztp as Z
        port, sport, cable = _console_path(netbox["fake"], ours=True)
        assert console_servers.set_port(sport["id"], {"driver": "raw_tcp", "host": "::1",
                                                      "tcp_port": 5000}, actor="op")["ok"]
        mine, other = _console_runs(lab)
        p = RT.plan("Lab", HOST, REASON)
        what = _step(p, "console")["what"]
        assert "remove its console port(s) 'con 0'" in what
        assert "the console server's port and Mercury's record of how to reach it are KEPT" \
            in what
        assert "move its 1 console survey and kick-start record(s) aside" in what
        _retire()
        fake = netbox["fake"]
        assert [o["id"] for o in fake.store["dcim/console-ports"]] == []
        assert fake.store["dcim/cables"] == []
        assert [o["id"] for o in fake.store["dcim/console-server-ports"]] == [sport["id"]]
        assert console_servers.get_port(sport["id"])["state"] == "read"
        assert [r["id"] for r in Z.runs("Lab")["runs"]] == [other["id"]]
        assert os.path.exists(os.path.join(lab["list_dir"], Z.FOLDER, Z.RETIRED,
                                           f"{mine['id']}.json"))
        assert Z.latest_survey("Lab", 31)[0] is None
        assert Z.latest_survey("Lab", 77)[0]["id"] == other["id"]

    def test_a_persons_cable_on_its_port_keeps_both_and_says_so(self, lab, netbox):
        port, _sport, cable = _console_path(netbox["fake"], ours=True, cable_ours=False)
        p = RT.plan("Lab", HOST, REASON)
        assert any(f"its console port 'con 0' (NetBox {port['id']}) and its cable "
                   f"{cable['id']} are KEPT: Mercury did not create cable {cable['id']}" in n
                   for n in p["not_doing"]), p["not_doing"]
        assert _step(p, "console")["done"] is True
        _retire()
        assert [o["id"] for o in netbox["fake"].store["dcim/console-ports"]] == [port["id"]]

    def test_a_persons_port_is_not_read_when_mercury_made_none(self, lab, netbox, monkeypatch):
        """No console port in Mercury's created-object record: nothing in NetBox can be ours,
        so it is not read, and nothing is removed."""
        import modules.nsot.console_path as CP
        port, _sport, _cable = _console_path(netbox["fake"], ours=False)
        read, real = [], CP.read_console_path
        monkeypatch.setattr(CP, "read_console_path",
                            lambda *a, **k: read.append(a) or real(*a, **k))
        p = RT.plan("Lab", HOST, REASON)
        assert read == [] and _step(p, "console")["done"] is True
        _retire()
        assert [o["id"] for o in netbox["fake"].store["dcim/console-ports"]] == [port["id"]]

    def test_writes_off_keeps_the_port_and_still_moves_the_runs(self, lab, netbox):
        from modules.nsot import console_ztp as Z
        _console_path(netbox["fake"], ours=True)
        _console_runs(lab)
        netbox["state"]["writes"] = False
        p = RT.plan("Lab", HOST, REASON)
        assert any("are NOT removed: NetBox writes are off" in n for n in p["not_doing"])
        _retire()
        assert len(netbox["fake"].store["dcim/console-ports"]) == 1
        assert Z.latest_survey("Lab", 31)[0] is None

    def test_by_name_when_netbox_is_not_configured(self, lab):
        """No NetBox (the lab fixture's): its runs are found by its name, and moved."""
        from modules.nsot import console_ztp as Z
        _console_runs(lab)
        _retire()
        assert [r["device"] for r in Z.runs("Lab")["runs"]] == [OTHER]

    def test_an_unreadable_index_refuses_the_plan(self, lab):
        from modules.nsot import console_ztp as Z
        os.makedirs(os.path.dirname(Z.index_path()), exist_ok=True)
        with open(Z.index_path(), "w", encoding="utf-8") as fh:
            fh.write("{not json")
        p = RT.plan("Lab", HOST, REASON)
        assert not p["ok"] and "could not be read" in p["refused_by"]["console"]

    def test_none_is_a_done_step_saying_so(self, lab):
        p = RT.plan("Lab", HOST, REASON)
        s = _step(p, "console")
        assert s["done"] and s["what"].startswith("no console port Mercury made")


# ----------------------------------------------------------------------------- C1345

class TestTheWordsMatchTheSteps:
    def test_every_step_has_its_words_and_no_word_names_a_step_retire_lacks(self):
        from modules.preview_confirm import RETIRE_STEP_WORDS
        from modules.route_gates import GATES
        assert set(RT.STEP_WORDS) == set(RT.STEPS)
        assert set(RETIRE_STEP_WORDS) == set(RT.STEPS)
        text = str(GATES["device_v2.retire_confirm"])
        assert "unmapped" not in text and "declares its startup" not in text


# ----------------------------------------------------------------------------- end to end

class TestANewDeviceOfTheNameInheritsNothing:
    """Every artefact planted for edge1, edge1 retired, a NEW edge1 onboarded, and every
    reader the device page and Needs attention use asked about it."""

    def test_end_to_end(self, lab, netbox, monkeypatch):
        from modules import approval_queue as Q, attention, dhcp_reservations as D
        from modules import heartbeat_windows as HW, netbox_guard
        from modules import topology_expected as TE, topology_positions as TP
        from modules.nsot import (adopt as A, credential_rotation as CR, hostvars, manifest,
                                  onboard, receipts, repo as R, scheduled_rotation as SR,
                                  templates_repo as T, ztp)
        repo = lab["repo"]
        # -- everything a device collects, planted
        _golden_commit(lab, HOST, "hostname edge1\n! the old device\n")
        _tag(lab, f"golden/{HOST}/20261001T000000Z")
        _tag(lab, "baseline/20261001T000000Z")
        hostvars.record_rolled_back(repo, HOST, "b" * 40, reason="verify failed",
                                    commands=["interface GigabitEthernet2", " shutdown"])
        receipts.write("Lab", [_receipt(_iso(-86400))])
        frag = lab["tmp"] / "ztp-fragment.json"
        frag.write_text(json.dumps([ztp.reservation_entry(MAC, IP, HOST, "192.0.2.1")]))
        lab["state"]["fragment"] = str(frag)
        monkeypatch.setattr(ztp, "write_reservations", lambda adds=(), removes=(), **kw: (
            frag.write_text("[]") and {"ok": True, "record": {"ok": True, "commit": "c1"},
                                       "outcomes": {m: {"outcome": "removed"}
                                                    for m in removes}}))
        lab["state"]["held"] = [{"family": "IPv4", "subnet": 7, "by": "MAC",
                                 "identity": "52:54:00:00:21:02", "addresses": [IP],
                                 "hostname": HOST}]
        monkeypatch.setattr(D, "plan", lambda l, v: {"ok": True, "hash": "h", "not_done": []})
        monkeypatch.setattr(D, "apply", lambda l, v, h, **kw: lab["state"].update(held=[])
                            or {"ok": True})
        lab["settings"]["credential_rotation_policies"] = {
            "role:edge": {"state": "on", "days": 90, "devices": [OTHER, HOST]}}
        b = T.load_bindings(repo)
        b["overrides"][HOST] = "cisco_iosxe/custom.j2"
        T.save_bindings(repo, b)
        R._commit_paths("Lab", ["templates/bindings.yml"], "bind", [], "templates")
        _rules(lab["tmp"] / "installed.yaml", [OTHER, HOST])
        Q.add_approval("update_golden_config", "drift", IP, HOST, list_name="Lab")
        ident, _e = manifest.find_by_name(repo, HOST)
        manifest.upsert_device(repo, ident, HOST, mgmt_ip=IP, platform="cisco_iosxe",
                               reserved_address=RESERVED, mgmt_mac=MAC)
        R._commit_paths("Lab", [R.MANIFEST_REL], "reserve", [], "test")
        lab["state"]["overrides"] |= {IP, RESERVED}
        CR.stage_plaintext(repo, HOST, PW)
        A.write_sidecar(repo, HOST, IP, "cisco_xe", "nmas")
        TE.declare("Lab", HOST, "apart on purpose: its own segment", "op")
        TP.save("Lab", {HOST: [100, 100], OTHER: [300, 100]}, "op", moved=HOST)
        # Its console path and console runs (C1553), in this test's own installation folder.
        from modules.nsot import console_ztp as Z
        (lab["tmp"] / "install-data").mkdir()
        monkeypatch.setattr("modules.config.DATA_DIR", str(lab["tmp"] / "install-data"))
        _console_path(netbox["fake"], ours=True)
        _console_runs(lab)

        p, out = _retire()
        assert set(out["done"]) >= {"override", "staged", "reservations", "commit", "tags",
                                    "rolled_back", "approvals", "rotation_policy", "topology",
                                    "heartbeat", "console", "netbox_record", "row"}, out["done"]

        # -- a NEW edge1, onboarded at the same address
        identity, new_tag = _new_device(lab)
        assert identity != ident
        # The device page: restore points, its rollback note, its template, its overrides.
        assert [x["ref"] for x in R.device_restore_points(repo, HOST)] == ["HEAD", new_tag]
        assert hostvars.rolled_back_note(repo, HOST) is None
        assert T.template_for_device(repo, HOST, "cisco_iosxe") == "cisco_iosxe/base.j2"
        assert lab["state"]["overrides"] == set()
        assert CR.staged_plaintext(repo, HOST) is None and not A.is_adoption_staged(repo, HOST)
        assert receipts.prior_authorisations("Lab", HOST)["lines"] == {}
        # Needs attention: no deploy row, no authorisation row, no queued item, no block.
        assert not any(HOST in (r.get("devices") or [])
                       for r in attention.deploy_source()["rows"])
        assert not any(HOST in (r.get("devices") or [])
                       for r in attention.authorisation_source()["rows"])
        assert [e for e in Q.read_pending("Lab")[0] if e["device_hostname"] == HOST] == []
        # Its policies, its age, its heartbeat rule, its Topology entries, its reservations.
        assert SR.policies_naming(HOST) == {}
        state = SR.device_states(lists=["Lab"], devices_of=lambda l: [{"hostname": HOST}],
                                 rotations={HOST: (time.time() - 86400 * 40, "x")},
                                 pols={}, profile_names=set())
        assert state[0]["never"] is True
        assert HW.drop_plan(HOST, written_path=str(lab["tmp"] / "written.yaml"),
                            installed_path=str(lab["tmp"] / "installed.yaml"))["state"] == "none"
        assert HOST not in TE.read("Lab")["islands"]
        assert HOST not in TP.read("Lab")["positions"]
        assert json.loads(frag.read_text()) == [] and lab["state"]["held"] == []
        # No console survey of the old device stands for it, and no console port of the old.
        assert Z.latest_survey("Lab", 31)[0] is None
        assert [r for r in Z.runs("Lab")["runs"] if r["device"] == HOST] == []
        assert Z.device_entries("Lab", HOST) == ([], "")
        assert netbox["fake"].store["dcim/console-ports"] == []
        # NetBox: the old record kept and renamed; the new device matched by id only.
        assert onboard._device_id_from(netbox_guard.get_created("Lab"), HOST) is None
        assert not [r for r in manifest.references(repo, identity, "Lab")
                    if r["kind"] == "netbox"]
        names = sorted(d["name"] for d in netbox["fake"].store["dcim/devices"])
        # The console server stays: it is the console server's, never the device's (C1553).
        assert names == ["cons-1", f"{HOST}-retired-31"], names


# ----------------------------------------------------------------------------- C1476

def plant_name_history(repo: str, *, retired=(), abandoned=(), created=()) -> str:
    """A real repository at *repo* holding a name's earlier lives, each at its own time: a
    retire commit per ``(name, epoch)`` in *retired* (its `Retired-Device:` trailer, as
    `retire.apply` writes it), an abandon commit per ``(name, epoch)`` in *abandoned*
    (onboarding's own subject, `onboard._abandon_onboarding`), and the manifest holding a
    PENDING device per ``(name, epoch)`` in *created* (its Create's ``onboarded_at``).
    The commits are made in time order with those dates. Returns *repo*."""
    import subprocess

    os.makedirs(repo, exist_ok=True)

    def git(*args, when=None):
        env = dict(os.environ)
        if when is not None:
            env.update(GIT_COMMITTER_DATE=f"@{int(when)} +0000",
                       GIT_AUTHOR_DATE=f"@{int(when)} +0000")
        subprocess.run(["git", "-C", repo, "-c", "user.email=t@example.invalid",
                        "-c", "user.name=t", *args], check=True, capture_output=True, env=env)

    git("init", "-q")
    events = ([(at, f"retire: {n} -- {REASON}\n\nActor: {ACTOR}\nRetired-Device: {n}\n"
                    f"Reason: {REASON}\n") for n, at in retired]
              + [(at, f"abandon: {n} - onboarding withdrawn\n\nSource: onboarding\n"
                      f"Actor: {ACTOR}\n") for n, at in abandoned])
    git("commit", "-q", "--allow-empty", "-m", "start",
        when=min([at for at, _m in events] or [time.time()]) - 60)
    for at, message in sorted(events):
        git("commit", "-q", "--allow-empty", "-m", message, when=at)
    devices = {f"uid-{n}": {"name": n, "verified_at": None, "address_source": "static",
                            "onboarded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                          time.gmtime(at))}
               for n, at in created}
    os.makedirs(os.path.join(repo, ".nsot"), exist_ok=True)
    with open(os.path.join(repo, ".nsot", "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump({"schema_version": 1, "devices": devices}, fh)
    return repo


class TestTheNameCut:
    """C1476: ONE cut per name (`retire.name_cuts_in`), the newest of its retirement, its
    abandoned onboarding and its current device's Create, so a record keyed by the name from
    before it is an earlier device's. Planted on a real repository with each life dated."""

    NOW = 1_790_000_000

    def test_the_newest_of_retirement_abandon_and_create_wins(self, tmp_path):
        repo = plant_name_history(str(tmp_path / "r"),
                                  retired=[(HOST, self.NOW - 7200)],
                                  abandoned=[(OTHER, self.NOW - 5400)],
                                  created=[(HOST, self.NOW - 600)])
        cuts = RT.name_cuts_in(repo)
        assert (cuts[HOST]["why"], cuts[HOST]["epoch"]) == ("created", self.NOW - 600)
        assert (cuts[OTHER]["why"], cuts[OTHER]["epoch"]) == ("abandoned", self.NOW - 5400)

    def test_an_abandon_after_the_retirement_moves_the_cut_to_it(self, tmp_path):
        repo = plant_name_history(str(tmp_path / "r"), retired=[(HOST, self.NOW - 7200)],
                                  abandoned=[(HOST, self.NOW - 3600)])
        assert RT.name_cuts_in(repo)[HOST]["why"] == "abandoned"
        assert RT.retirements_in(repo)[HOST]["epoch"] == self.NOW - 7200, \
            "the retirement alone is still the receipts' cut (C1334)"

    def test_a_half_run_abandon_of_the_device_itself_moves_nothing(self, tmp_path):
        """Its entry is still in the manifest: the abandon is the current device's own."""
        repo = plant_name_history(str(tmp_path / "r"), abandoned=[(HOST, self.NOW - 60)],
                                  created=[(HOST, self.NOW - 600)])
        assert RT.name_cuts_in(repo)[HOST]["why"] == "created"

    def test_a_record_before_the_cut_is_the_earlier_devices(self, tmp_path):
        repo = plant_name_history(str(tmp_path / "r"), retired=[(HOST, self.NOW - 7200)],
                                  created=[(HOST, self.NOW - 600)])
        cuts = RT.name_cuts_in(repo)
        assert RT.before_retirement(cuts, HOST, self.NOW - 3600)
        assert not RT.before_retirement(cuts, HOST, self.NOW - 60)
        assert not RT.before_retirement(cuts, "edge9", self.NOW - 3600), "an uncut name"

    def test_a_name_with_no_earlier_life_has_no_cut_but_its_create(self, tmp_path):
        repo = plant_name_history(str(tmp_path / "r"), created=[(HOST, self.NOW - 600)])
        assert set(RT.name_cuts_in(repo)) == {HOST}
