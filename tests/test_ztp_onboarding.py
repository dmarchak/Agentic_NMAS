"""P.6 step 3: `ztp` in the plan, in phase 1, and on the paths it shares
with `dhcp` (re-render and lease discovery).

`ztp` is `dhcp` plus two things the tool does itself: it writes the
reservation (the `reserve` step, last among the fallible) and it serves the
config (the responder). Everything the plan must know about the write is
found at plan time, where the review screen promises nothing has been
created yet. Documentation addresses (RFC 5737) throughout.
"""

import os

import pytest

from modules.nsot import onboard
from modules.nsot.onboard import ZTP_STEPS, build_plan, run_onboarding

MAC = "aa:bb:cc:00:02:50"
ADDR = "192.0.2.50"
SERVER = "192.0.2.10"


@pytest.fixture(autouse=True)
def _syslog_host(monkeypatch):
    """P.1: onboarding refuses while `syslog_host` is unset. Only that key is
    supplied; every other setting is read exactly as before (the same fixture
    as test_onboard_dhcp_source.py)."""
    import modules.settings_schema as ss
    real = ss.get_setting
    monkeypatch.setattr(ss, "get_setting", lambda k, *a, **kw: (
        "192.0.2.10" if k == "syslog_host" else real(k, *a, **kw)))


def _ok_check(mac, address, kea=None):
    return {"ok": True, "reasons": [], "server": SERVER, "subnet_id": 255,
            "dns": {"state": "silent", "measured_at": 1000.0}}


def _plan(tmp_path, monkeypatch, check=_ok_check, **kw):
    monkeypatch.setattr("modules.config.LISTS_DIR", str(tmp_path))
    monkeypatch.setattr("modules.nsot.onboard._name_in_manifest", lambda *a: (False, True))
    monkeypatch.setattr("modules.nsot.onboard._name_in_netbox", lambda *a: (False, True))
    base = dict(hostname="bp-ztp-a", platform="cisco_iosxe", list_name="probe",
                secret="Secret123", manager_interface="Gi2", mgmt_interface="Gi1",
                address_source="ztp", mgmt_mac=MAC, mgmt_ip=ADDR, ztp_check=check,
                role="router")
    base.update(kw)
    return build_plan(**base)


class TestThePlan:
    def test_a_clean_ztp_plan_is_onboardable(self, tmp_path, monkeypatch):
        """The floor: without it every refusal below is satisfied by a plan
        that refuses everything."""
        plan = _plan(tmp_path, monkeypatch)
        assert plan.onboardable, plan.blocking_reasons
        assert plan.reservation_state == "to_write"
        assert plan.ztp_server == SERVER and plan.ztp_subnet_id == 255

    def test_the_typed_address_is_the_reservation_never_a_static_one(self, tmp_path, monkeypatch):
        plan = _plan(tmp_path, monkeypatch)
        assert plan.mgmt_ip == "" and plan.reservation_address == ADDR
        assert " ip address dhcp" in plan.bootstrap_config
        assert ADDR not in plan.bootstrap_config

    def test_the_claim_says_the_tool_writes_it_and_where_the_config_comes_from(self, tmp_path, monkeypatch):
        claim = _plan(tmp_path, monkeypatch).address_claim
        assert "WRITES Kea reservation" in claim and f"{MAC} → {ADDR}" in claim
        assert f"bp-ztp-a.cfg by TFTP from {SERVER}" in claim and "(D4)" in claim

    def test_every_reason_the_write_would_refuse_blocks_the_plan(self, tmp_path, monkeypatch):
        reasons = ["D4: routers reaches a reservation in subnet 255",
                   f"{ADDR} is leased to aa:bb:cc:00:09:98 right now"]
        plan = _plan(tmp_path, monkeypatch,
                     check=lambda m, a, kea=None: {"ok": False, "reasons": reasons,
                                                   "server": "", "subnet_id": None, "dns": {}})
        assert not plan.onboardable
        for r in reasons:
            assert r in plan.blocking_reasons
        assert "cannot be yet" in plan.address_claim

    @pytest.mark.parametrize("missing,said", [("mgmt_mac", "no MAC address"),
                                              ("mgmt_ip", "no address to reserve")])
    def test_the_mac_and_the_address_are_both_required(self, tmp_path, monkeypatch, missing, said):
        plan = _plan(tmp_path, monkeypatch, **{missing: ""})
        assert any(said in r for r in plan.blocking_reasons), plan.blocking_reasons

    def test_a_check_that_raised_has_not_passed(self, tmp_path, monkeypatch):
        def boom(m, a, kea=None):
            raise OSError("Kea unreachable")
        plan = _plan(tmp_path, monkeypatch, check=boom)
        assert not plan.onboardable
        assert any("could not run" in r for r in plan.blocking_reasons)

    def test_an_unknown_source_is_refused(self, tmp_path, monkeypatch):
        plan = _plan(tmp_path, monkeypatch, address_source="bootp")
        assert any("not one of static, dhcp or ztp" in r for r in plan.blocking_reasons)

    def test_an_interface_is_still_chosen_never_defaulted(self, tmp_path, monkeypatch):
        plan = _plan(tmp_path, monkeypatch, manager_interface="")
        assert any("no interface chosen" in r for r in plan.blocking_reasons)


class _Steps:
    def __init__(self, fail=""):
        self.order, self.fail = [], fail

    def step(self, name):
        def run(plan):
            self.order.append(name)
            if name == self.fail:
                raise RuntimeError(f"{name} failed for the test")
            return "sha" if name == "commit" else None
        return run

    def kwargs(self, with_reserve=True):
        kw = {n: self.step(k) for n, k in (("bind_credentials", "credentials"),
                                           ("commit", "commit"), ("render", "render"))}
        if with_reserve:
            kw["reserve"] = self.step("reserve")
        return kw


class TestPhaseOne:
    def test_the_order_is_credentials_commit_reserve_render(self, tmp_path, monkeypatch):
        steps = _Steps()
        out = run_onboarding(_plan(tmp_path, monkeypatch), **steps.kwargs())
        assert out["ok"], out
        assert tuple(steps.order) == ZTP_STEPS == ("credentials", "commit", "reserve", "render")

    def test_the_reservation_is_last_among_the_fallible(self):
        assert ZTP_STEPS[ZTP_STEPS.index("reserve") + 1:] == ("render",)
        assert ZTP_STEPS.index("reserve") > ZTP_STEPS.index("commit")

    def test_a_failed_reservation_leaves_a_pending_device_and_offers_cleanup(self, tmp_path, monkeypatch):
        steps = _Steps(fail="reserve")
        out = run_onboarding(_plan(tmp_path, monkeypatch), **steps.kwargs())
        assert not out["ok"] and out["failed_at"] == "reserve"
        assert out["cleanup_offered"] is True
        assert "committed and pending" in out["reason"] and "was NOT written" in out["reason"]
        assert "render" not in steps.order

    def test_a_ztp_run_without_a_reservation_step_cannot_complete(self, tmp_path, monkeypatch):
        steps = _Steps()
        out = run_onboarding(_plan(tmp_path, monkeypatch), **steps.kwargs(with_reserve=False))
        assert not out["ok"] and out["failed_at"] == "reserve"

    def test_other_sources_never_call_it(self, tmp_path, monkeypatch):
        steps = _Steps()
        plan = _plan(tmp_path, monkeypatch, address_source="static", mgmt_ip="192.0.2.60",
                     mgmt_mask="255.255.255.0", mgmt_mac="")
        assert plan.onboardable, plan.blocking_reasons
        out = run_onboarding(plan, **steps.kwargs())
        assert out["ok"] and "reserve" not in steps.order

    def test_real_steps_carries_it(self):
        assert "reserve" in onboard.real_steps("/repo", actor="x")


class TestTheReserveStep:
    def _plan(self):
        class P:
            mgmt_mac, reservation_address, hostname = MAC, ADDR, "bp-ztp-a"
        return P()

    def test_it_writes_the_entry_with_the_server_found_at_write_time(self):
        seen = {}

        def write(adds, kea=None):
            seen["adds"] = adds
            return {"ok": True, "outcomes": {MAC: {"outcome": "written", "detail": ""}}}
        onboard.reserve_step(self._plan(), check=_ok_check, write=write)
        entry = seen["adds"][0]
        assert entry["hw-address"] == MAC and entry["ip-address"] == ADDR
        assert {o["name"]: o["data"] for o in entry["option-data"]} == {
            "tftp-server-name": SERVER, "boot-file-name": "bp-ztp-a.cfg"}

    def test_d4_is_checked_again_at_write_time(self):
        written = []
        bad = lambda m, a, kea=None: {"ok": False, "reasons": ["D4: routers at subnet 255"],
                                      "server": SERVER}
        with pytest.raises(RuntimeError, match="D4: routers"):
            onboard.reserve_step(self._plan(), check=bad, write=lambda *a, **k: written.append(1))
        assert written == [], "a write after a failed check"

    def test_a_refused_write_raises_with_the_writers_reason(self):
        write = lambda adds, kea=None: {"ok": False, "outcomes": {
            MAC: {"outcome": "refused", "detail": f"{ADDR} is leased to someone"}}}
        with pytest.raises(RuntimeError, match="is leased to someone"):
            onboard.reserve_step(self._plan(), check=_ok_check, write=write)


class TestTheSharedPaths:
    def test_a_ztp_device_re_renders_like_a_dhcp_one(self, tmp_path, monkeypatch):
        from modules.nsot import hostvars, repo as _repo

        list_dir = tmp_path / "probe"
        repo = str(list_dir / "config_repo")
        os.makedirs(os.path.join(repo, "host_vars"), exist_ok=True)
        monkeypatch.setattr("modules.config.LISTS_DIR", str(tmp_path))
        monkeypatch.setattr("modules.config.get_list_data_dir", lambda _n: str(list_dir))
        monkeypatch.setattr("modules.secrets_store.KEY_FILE", str(tmp_path / "key.key"))
        _repo.init_repo(repo)
        hostvars.write_committed(repo, {"hostname": "bp-ztp-a", "bootstrap": {
            "source": "ztp", "interface": "GigabitEthernet2", "mac": MAC,
            "domain": "rcn.lab", "platform": "cisco_iosxe", "address": "", "mask": ""}})
        from tests.intent_fixture import commit_intent; commit_intent(repo)  # read from HEAD (C104)
        onboard.stage_bootstrap_credential(repo, "bp-ztp-a", "Secret123")
        out = onboard.bootstrap_artifact(repo, "bp-ztp-a")
        assert out["ok"], out["reason"]
        assert " ip address dhcp" in out["config"]

    def test_verify_discovers_the_lease_for_a_ztp_device(self, tmp_path, monkeypatch):
        from modules.integrations.kea import KeaIntegration
        from modules.nsot import manifest as _m, repo as _repo
        from modules.nsot.repo import GoldenItem, adopt_identity

        list_dir = tmp_path / "probe"
        repo = str(list_dir / "config_repo")
        os.makedirs(os.path.join(repo, "host_vars"), exist_ok=True)
        monkeypatch.setattr("modules.config.LISTS_DIR", str(tmp_path))
        monkeypatch.setattr("modules.config.get_list_data_dir", lambda _n: str(list_dir))
        monkeypatch.setattr("modules.secrets_store.KEY_FILE", str(tmp_path / "key.key"))
        _repo.init_repo(repo)
        identity = adopt_identity(repo, GoldenItem("bp-ztp-a", "", ""))
        _m.upsert_device(repo, identity, "bp-ztp-a", platform="cisco_iosxe", pending=True,
                         address_source="ztp", mgmt_mac=MAC, reserved_address=ADDR)
        kea = KeaIntegration()
        body = [{"result": 0, "arguments": {"leases": [
            {"ip-address": ADDR, "hw-address": MAC, "state": 0, "expire": 9e9}]}}]
        kea.command = lambda c, service=None: (
            {"ok": False, "error": "unsupported"} if "by-hw" in c else {"ok": True, "result": body})
        reached = {}
        out = onboard.verify_device(repo, "bp-ztp-a", "probe",
                                    online=lambda ip: bool(ip),
                                    reach=lambda ip, *a, **k: reached.setdefault("ip", ip) and "bp-ztp-a#",
                                    interface="GigabitEthernet2", kea=kea)
        assert reached.get("ip") == ADDR, out


# ── step 4: the pending row reports ZTP states from their own sources ──────

class _ProgressKea:
    def __init__(self, reservation="reserved", reserved_to=ADDR, lease="found"):
        self.res, self.to, self.lease = reservation, reserved_to, lease

    def reservation_for(self, mac):
        return {"state": self.res, "address": self.to if self.res == "reserved" else "",
                "error": "down" if self.res == "unknown" else ""}

    def lease_for(self, mac):
        return {"state": self.lease, "address": ADDR if self.lease == "found" else "",
                "error": "down" if self.lease == "unknown" else ""}


ENTRY = {"name": "bp-ztp-a", "mgmt_mac": MAC, "reserved_address": ADDR,
         "address_source": "ztp"}
SERVED = {"actor": f"ztp:{ADDR}", "what": "bootstrap_config", "target": "bp-ztp-a",
          "at": "2026-09-27T02:00:00Z", "peer": ADDR, "sha256": "ab" * 32}
REFUSED = {"actor": f"ztp:{ADDR}", "what": "bootstrap_config_refused", "target": "bp-ztp-a",
           "at": "2026-09-27T01:59:00Z", "peer": ADDR, "detail": "asked for 'network-confg'"}


class TestThePendingRow:
    from modules.nsot import ztp as _z

    @pytest.mark.parametrize("kea,fetches,stage", [
        (_ProgressKea(reservation="not_reserved"), [], "reservation_missing"),
        (_ProgressKea(reserved_to="192.0.2.77"), [], "reservation_missing"),
        (_ProgressKea(lease="none"), [], "reserved_not_leased"),
        (_ProgressKea(), [], "leased_not_fetched"),
        (_ProgressKea(), [REFUSED], "asked_not_served"),
        (_ProgressKea(), [SERVED, REFUSED], "fetched_not_reached"),
    ])
    def test_each_stage_is_derived_from_its_facts(self, kea, fetches, stage):
        from modules.nsot import ztp
        assert ztp.progress(ENTRY, kea=kea, fetches=fetches)["stage"] == stage

    def test_a_different_reserved_address_is_named(self):
        from modules.nsot import ztp
        out = ztp.progress(ENTRY, kea=_ProgressKea(reserved_to="192.0.2.77"), fetches=[])
        assert "192.0.2.77" in out["summary"]

    def test_a_refused_fetch_is_said_with_its_reason(self):
        from modules.nsot import ztp
        out = ztp.progress(ENTRY, kea=_ProgressKea(), fetches=[REFUSED])
        assert "ASKED 1 time(s)" in out["summary"] and "network-confg" in out["summary"]

    def test_the_fetch_names_its_time_and_hash(self):
        from modules.nsot import ztp
        out = ztp.progress(ENTRY, kea=_ProgressKea(), fetches=[SERVED])
        assert "2026-09-27T02:00:00Z" in out["summary"] and "abababababab" in out["summary"]

    def test_another_devices_fetch_does_not_count(self):
        from modules.nsot import ztp
        other = dict(SERVED, target="bp-ztp-b")
        assert ztp.progress(ENTRY, kea=_ProgressKea(), fetches=[other])["stage"] == "leased_not_fetched"

    @pytest.mark.parametrize("kea", [_ProgressKea(reservation="unknown"), _ProgressKea(lease="unknown")])
    def test_kea_that_cannot_be_asked_is_unknown_not_a_stage(self, kea):
        from modules.nsot import ztp
        out = ztp.progress(ENTRY, kea=kea, fetches=[])
        assert out["stage"] == "unknown" and "could not be asked" in out["summary"]


class TestThePendingRoute:
    def _get(self, monkeypatch, progress, tmp_path):
        import app as nmas
        monkeypatch.setattr("modules.config.get_list_data_dir",
                            lambda name: str(tmp_path / name))
        # The list must EXIST: a read naming a list that does not is refused
        # (register C51), and this list was only ever a patched path.
        monkeypatch.setattr("modules.config.LISTS_DIR", str(tmp_path))
        (tmp_path / "probe").mkdir(exist_ok=True)
        rows = [dict(ENTRY, age_seconds=10, state="in_flight", onboarded_at="x"),
                {"name": "r7", "address_source": "static", "mgmt_ip": "192.0.2.7",
                 "age_seconds": 10, "state": "in_flight", "onboarded_at": "x"}]
        monkeypatch.setattr("modules.nsot.manifest.pending_devices", lambda repo: rows)
        monkeypatch.setattr("modules.nsot.ztp.progress", progress)
        r = nmas.app.test_client().get("/onboard/pending?list_name=probe")
        return r.status_code, r.get_json()

    def test_only_the_ztp_row_carries_progress(self, monkeypatch, tmp_path):
        status, body = self._get(monkeypatch, lambda row: {"stage": "reserved_not_leased",
                                                          "summary": "reserved"}, tmp_path)
        assert status == 200 and body["ok"]
        by = {r["name"]: r for r in body["pending"]}
        assert by["bp-ztp-a"]["ztp"]["stage"] == "reserved_not_leased"
        assert "ztp" not in by["r7"]

    def test_a_progress_that_raised_is_carried_as_unknown(self, monkeypatch, tmp_path):
        def boom(row):
            raise OSError("Kea down")
        status, body = self._get(monkeypatch, boom, tmp_path)
        assert status == 200 and body["ok"], "one row's failure is not the list's"
        row = [r for r in body["pending"] if r["name"] == "bp-ztp-a"][0]
        assert row["ztp"]["stage"] == "unknown" and "Kea down" in row["ztp"]["summary"]


from tests.test_onboard_phase2 import _banner, banner_js  # noqa: E402,F401


class TestTheBannerDrawsIt:
    def _data(self, ztp):
        row = dict(ENTRY, age_seconds=10, state="in_flight", onboarded_at="x",
                   credential_findable=True)
        if ztp is not None:
            row["ztp"] = ztp
        return {"ok": True, "list": "probe", "pending": [row],
                "counts": {"total": 1, "overdue": 0}}

    def test_the_summary_is_drawn(self, banner_js):
        html = _banner(banner_js, self._data({"stage": "fetched_not_reached",
                                              "summary": "fetched its config at T"}))
        assert "fetched its config at T" in html
        # The stage word is drawn beside it (7.1: it was carried and not drawn).
        assert "<span data-ztp-stage>fetched_not_reached</span>" in html

    def test_a_row_with_no_progress_says_so(self, banner_js):
        html = _banner(banner_js, self._data(None))
        assert "its progress was not reported" in html


class TestPhaseTwoIsUnchanged:
    """Step 5: a ztp device is a dhcp device on every path phase 2 touches.
    Every comparison that singles out "dhcp" alone in onboard.py is a
    PLAN-TIME branch for the dhcp source itself, and is declared here. A new
    one, anywhere else, would be a path ztp silently does not take."""

    DECLARED = {"blocking_reasons", "address_claim", "build_plan"}

    def test_every_dhcp_only_comparison_is_a_declared_plan_branch(self):
        import ast

        tree = ast.parse(open(onboard.__file__, encoding="utf-8").read())
        found = set()
        for fn in ast.walk(tree):
            if not isinstance(fn, ast.FunctionDef):
                continue
            for node in ast.walk(fn):
                if (isinstance(node, ast.Compare)
                        and any(isinstance(op, (ast.Eq, ast.NotEq)) for op in node.ops)
                        and any(isinstance(c, ast.Constant) and c.value == "dhcp"
                                for c in [node.left, *node.comparators])):
                    found.add(fn.name)
        assert found, "the scan found nothing; it can no longer see a dhcp comparison"
        assert found == self.DECLARED, found


# ── step 6: abandon reverses it ─────────────────────────────────────────────

class TestAbandon:
    def _repo(self, tmp_path, monkeypatch, source="ztp"):
        from modules.nsot import manifest as _m, repo as _repo
        from modules.nsot.repo import GoldenItem, adopt_identity

        list_dir = tmp_path / "probe"
        repo = str(list_dir / "config_repo")
        os.makedirs(os.path.join(repo, "host_vars"), exist_ok=True)
        monkeypatch.setattr("modules.config.LISTS_DIR", str(tmp_path))
        monkeypatch.setattr("modules.config.get_list_data_dir", lambda _n: str(list_dir))
        monkeypatch.setattr("modules.secrets_store.KEY_FILE", str(tmp_path / "key.key"))
        _repo.init_repo(repo)
        identity = adopt_identity(repo, GoldenItem("bp-ztp-a", "", ""))
        _m.upsert_device(repo, identity, "bp-ztp-a", platform="cisco_iosxe", pending=True,
                         address_source=source, mgmt_mac=MAC, reserved_address=ADDR)
        return repo

    def _abandon(self, repo, remover, **kw):
        return onboard.abandon_onboarding(
            repo, "bp-ztp-a", "probe", actor="op@example.com",
            remove_netbox=lambda *a, **k: {"ok": True, "deleted": [], "skipped": []},
            remove_reservation=remover, **kw)

    def test_the_reservation_goes_first_and_the_name_is_released(self, tmp_path, monkeypatch):
        repo = self._repo(tmp_path, monkeypatch)
        calls = []
        out = self._abandon(repo, lambda mac: calls.append(mac) or {
            "ok": True, "outcomes": {MAC: {"outcome": "removed", "detail": f"{MAC} -> {ADDR}"}}})
        assert calls == [MAC]
        assert [st["step"] for st in out["steps"]] == list(onboard.ZTP_ABANDON_STEPS)
        assert out["ok"] and out["released"] == "bp-ztp-a", out

    def test_an_already_absent_reservation_is_not_a_failure(self, tmp_path, monkeypatch):
        repo = self._repo(tmp_path, monkeypatch)
        out = self._abandon(repo, lambda mac: {
            "ok": True, "outcomes": {MAC: {"outcome": "absent", "detail": "no reservation"}}})
        assert out["ok"], out

    def test_a_reservation_that_remains_keeps_the_name(self, tmp_path, monkeypatch):
        from modules.nsot import manifest as _m

        repo = self._repo(tmp_path, monkeypatch)
        out = self._abandon(repo, lambda mac: {"ok": False, "error": "Kea unreachable",
                                               "outcomes": {}})
        assert not out["ok"] and not out["released"]
        assert any(r["step"] == "reservation" for r in out["remaining"])
        assert "not released" in [s for s in out["steps"] if s["step"] == "identity"][0]["detail"]
        assert _m.find_by_name(repo, "bp-ztp-a")[0], "the name was released anyway"

    def test_a_dry_run_removes_nothing(self, tmp_path, monkeypatch):
        repo = self._repo(tmp_path, monkeypatch)
        calls = []
        self._abandon(repo, lambda mac: calls.append(mac), dry_run=True)
        assert calls == []

    def test_another_source_has_no_reservation_step(self, tmp_path, monkeypatch):
        repo = self._repo(tmp_path, monkeypatch, source="dhcp")
        calls = []
        out = self._abandon(repo, lambda mac: calls.append(mac))
        assert calls == [] and "reservation" not in [st["step"] for st in out["steps"]]

    def test_a_refused_removal_keeps_the_name_and_says_why(self, tmp_path, monkeypatch):
        """Found by a control that passed: the only failure fixture had empty
        outcomes, so a mutated check crashed into the exception branch and
        stayed correct by accident. A REFUSED removal is the real case."""
        repo = self._repo(tmp_path, monkeypatch)
        out = self._abandon(repo, lambda mac: {"ok": False, "outcomes": {
            MAC: {"outcome": "refused",
                  "detail": f"{MAC} is reserved outside the fragment"}}})
        step = [s for s in out["steps"] if s["step"] == "reservation"][0]
        assert not step["ok"] and "reserved outside the fragment" in step["detail"]
        assert not out["released"]


class TestAskedAndNotServed:
    """M4: a ZTP device's patience is finite (AutoInstall gave up after about
    2.5 minutes and nine requests), so "it asked and we did not answer" is a
    state of its own, and it names the consequence."""

    UNATTRIBUTED = {"actor": "ztp:::ffff:192.0.2.50", "what": "bootstrap_config_refused",
                    "target": "?", "peer": "::ffff:192.0.2.50", "at": "2026-09-27T02:50:00Z",
                    "detail": "192.0.2.50 holds no reservation the tool wrote"}

    def test_a_refusal_recorded_as_unattributed_is_still_this_device(self):
        from modules.nsot import ztp
        first = dict(self.UNATTRIBUTED, at="2026-09-27T02:48:23Z")
        out = ztp.progress(ENTRY, kea=_ProgressKea(), fetches=[self.UNATTRIBUTED, first])
        assert out["stage"] == "asked_not_served", out
        assert "ASKED 2 time(s) between 2026-09-27T02:48:23Z and 2026-09-27T02:50:00Z" in out["summary"]
        assert "needs a reload" in out["summary"]

    def test_a_request_from_another_address_is_not_this_device(self):
        from modules.nsot import ztp
        other = dict(self.UNATTRIBUTED, peer="192.0.2.99", actor="ztp:192.0.2.99")
        out = ztp.progress(ENTRY, kea=_ProgressKea(), fetches=[other])
        assert out["stage"] == "leased_not_fetched"

    def test_a_serve_after_refusals_is_fetched(self):
        from modules.nsot import ztp
        out = ztp.progress(ENTRY, kea=_ProgressKea(), fetches=[SERVED, self.UNATTRIBUTED])
        assert out["stage"] == "fetched_not_reached"


class TestTheResponderRow:
    """Its own job-health row: a responder that cannot serve fails an
    onboarding rather than delaying it."""

    def _run(self, socket_props, journal, journal_ok=True):
        def run(cmd):
            if cmd[:2] == ["systemctl", "show"]:
                return (0, socket_props) if socket_props is not None else (1, "")
            if cmd[0] == "journalctl":
                return (0, journal) if journal_ok else (1, "")
            raise AssertionError(cmd)
        return run

    def _rows(self, props, journal="", journal_ok=True, fragment="/etc/kea/nmas/r.json"):
        from modules import job_health
        return job_health.ztp_responder_rows(run=self._run(props, journal, journal_ok),
                                             get=lambda k, d="": fragment)

    ACTIVE = "LoadState=loaded\nActiveState=active\nListen=[::]:69 (Datagram)\n"

    def test_nothing_while_ztp_is_not_configured(self):
        assert self._rows(self.ACTIVE, fragment="") == []

    def test_not_installed_and_socket_down(self):
        assert self._rows("LoadState=not-found\n")[0]["state"] == "not_installed"
        assert self._rows("LoadState=loaded\nActiveState=inactive\n")[0]["state"] == "socket_down"

    def test_listening_and_never_started_is_ok_and_says_so(self):
        row = self._rows(self.ACTIVE, "")[0]
        assert row["state"] == "ok" and "not started yet" in row["detail"]

    def test_a_handler_failure_since_the_last_start_is_failing(self):
        journal = ("1000.0 host nmas-ztp-responder: INFO serving ZTP bootstrap configs on ('::', 69)\n"
                   "1010.0 host nmas-ztp-responder: ERROR ztp responder: handler FAILED for 192.0.2.50\n")
        row = self._rows(self.ACTIVE, journal)[0]
        assert row["state"] == "failing" and "needs a reload" in row["detail"]

    def test_failures_before_the_last_start_do_not_count(self):
        journal = ("1000.0 host x: Exception in thread Thread-15 (handle):\n"
                   "1100.0 host x: INFO serving ZTP bootstrap configs on ('::', 69)\n")
        assert self._rows(self.ACTIVE, journal)[0]["state"] == "ok"

    def test_an_unreadable_journal_is_unknown(self):
        assert self._rows(self.ACTIVE, journal_ok=False)[0]["state"] == "unknown"


# ── M4, second attempt: fetched and applied, and SSH never came up ──────────

class TestAZtpDeviceGeneratesItsOwnSshKey:
    """vrnetlab's day-0 config was the only thing that ever generated a
    C8000v's SSH key (the reason it is not in GENERATES_SSH_KEY). A ZTP device
    has no day-0 config from vrnetlab, so M4's node applied its config, had no
    key, and refused TCP 22 in 3 ms."""

    def test_the_ztp_render_generates_a_key_after_the_hostname_and_domain(self, tmp_path, monkeypatch):
        cfg = _plan(tmp_path, monkeypatch).bootstrap_config.splitlines()
        key = [i for i, l in enumerate(cfg) if l.startswith("crypto key generate rsa modulus")]
        assert len(key) == 1, cfg
        assert cfg.index("hostname bp-ztp-a") < key[0]
        assert [i for i, l in enumerate(cfg) if l.startswith("ip domain name")][0] < key[0]
        assert "ip ssh version 2" in cfg

    def test_no_other_c8000v_render_changes(self, tmp_path, monkeypatch):
        """The floor: vrnetlab still generates the key for those, and a second
        generation would replace a key the device is using."""
        plan = _plan(tmp_path, monkeypatch, address_source="dhcp", mgmt_ip="",
                     ztp_check=None, kea=_NoKea())
        assert "crypto key generate" not in plan.bootstrap_config

    def test_the_re_render_is_byte_identical_to_the_plan(self, tmp_path, monkeypatch):
        from modules.nsot import hostvars, repo as _repo

        plan = _plan(tmp_path, monkeypatch, manager_interface="GigabitEthernet2")
        list_dir = tmp_path / "probe"
        repo = str(list_dir / "config_repo")
        os.makedirs(os.path.join(repo, "host_vars"), exist_ok=True)
        monkeypatch.setattr("modules.config.get_list_data_dir", lambda _n: str(list_dir))
        monkeypatch.setattr("modules.secrets_store.KEY_FILE", str(tmp_path / "key.key"))
        _repo.init_repo(repo)
        hostvars.write_committed(repo, {"hostname": "bp-ztp-a", "bootstrap": {
            "source": "ztp", "interface": "GigabitEthernet2", "mac": MAC,
            "domain": "rcn.lab", "platform": "cisco_iosxe", "address": "", "mask": ""}})
        from tests.intent_fixture import commit_intent; commit_intent(repo)  # read from HEAD (C104)
        onboard.stage_bootstrap_credential(repo, "bp-ztp-a", "Secret123")
        out = onboard.bootstrap_artifact(repo, "bp-ztp-a")
        assert out["ok"], out["reason"]
        assert out["config"] == plan.bootstrap_config


class _NoKea:
    def reservation_for(self, mac):
        return {"state": "reserved", "address": "192.0.2.40", "source": "config", "error": ""}


def test_a_phase_two_stop_is_logged_with_its_step_and_reason(tmp_path, monkeypatch, caplog):
    """M4: the reason lived only in a response body the browser overwrote,
    and the app log held the status and nothing else."""
    import logging

    from modules.nsot import repo as _repo

    repo = str(tmp_path / "config_repo")
    os.makedirs(repo)
    _repo.init_repo(repo)
    with caplog.at_level(logging.WARNING, logger="modules.nsot.onboard"):
        out = onboard.run_phase_two(repo, "bp-nobody", "probe")
    assert not out["ok"]
    assert any("phase 2 for bp-nobody stopped at verify" in r.getMessage() for r in caplog.records)


class TestTheVerifyFailureStaysOnScreen:
    """Executed in duktape: the shipped functions, with the asynchrony
    stripped and nothing else changed. Since 7.1 the route returns a result
    built by `onboard_verify_result` from the recorded row, drawn by the
    result component; the payloads here are built by that real builder."""

    @staticmethod
    def _js():
        from tests.js_source import read_shipped
        return read_shipped("static/js/gen/partials__onboard_wizard.2.js")

    @staticmethod
    def _payload(run):
        from modules.nsot.onboard import PHASE_TWO_STEPS
        from modules.preview_confirm import onboard_verify_result

        steps = run.pop("steps")
        ran = {st["step"] for st in steps}
        steps += [{"step": st, "ok": False, "detail": "did not run"}
                  for st in PHASE_TWO_STEPS if st not in ran]
        row = dict({"at": "2026-09-28T10:00:00Z", "kind": "verify", "device": "bp-ztp-a",
                    "actor": "p@example.com", "mgmt_ip": "192.0.2.50", "steps": steps}, **run)
        return dict(run, steps=steps, result=onboard_verify_result(row))

    def _run(self, payload):
        import dukpy

        from tests.js_source import read_shipped

        js = self._js()
        start = js.index("async function onboardVerify")
        end = js.index("async function onboardAbandon")
        code = js[start:end].replace("async function", "function").replace("await ", "")
        assert "await" not in code
        harness = ("var window = {};\n" + read_shipped("static/js/nmas_preview_confirm.js") + """
        var previewConfirmResultHtml = window.previewConfirmResultHtml;
        var previewConfirmResultLevel = window.previewConfirmResultLevel;
        var calls = [], banner = {innerHTML: ''};
        var document = {getElementById: function (id) {
            return id === 'onboardPendingBanner' ? banner : null; }};
        function fetch(url, opts) { return {json: function () { return dukpy.payload; }}; }
        function showToast(t, k) { calls.push('toast:' + k); }
        function loadOnboardPending(l) { calls.push('reload:' + l); }
        function inFlightBusy(on) { calls.push('busy:' + on); }
        """ + code + """
        onboardVerify('bp-ztp-a', 'ztp-a');
        ({calls: calls, html: banner.innerHTML})
        """)
        return dukpy.evaljs(harness, payload=payload)

    def test_a_failure_is_left_on_screen_not_reloaded_over(self):
        out = self._run(self._payload({"ok": False, "reason": "did not answer", "steps": [
            {"step": "verify", "ok": False, "detail": "did_not_answer"}],
            "verify": {"state": "did_not_answer", "error": "tcp/22 refused", "causes": [
                {"cause": "not booted", "why": "nothing answers", "where": "console",
                 "command": "show version"}]}}))
        assert "reload:ztp-a" not in out["calls"], out["calls"]
        assert "toast:danger" in out["calls"], "a failure drawn in the failure colour"
        assert "did not answer" in out["html"] and "Back to the pending list" in out["html"]
        assert "nothing about it has changed" in out["html"]
        assert "tcp/22 refused" in out["html"] and "1. not booted" in out["html"]

    def test_a_stop_after_verify_names_the_step_and_the_reason(self):
        out = self._run(self._payload({"ok": False, "reason": "the capture timed out", "steps": [
            {"step": "verify", "ok": True, "detail": "answered"},
            {"step": "capture", "ok": False, "detail": "timeout"}],
            "verify": {"state": "answered"}}))
        assert "stopped at capture" in out["html"]
        assert "the capture timed out" in out["html"]
        assert "nothing about it has changed" not in out["html"]
        assert "toast:warning" in out["calls"], "some steps ran: partly done, never green"

    def test_a_success_is_drawn_and_left_too(self):
        """The row it came from is gone once promoted, so the result stays
        until the operator goes back; the pending banner reads it again under
        "finished recently"."""
        from modules.nsot.onboard import PHASE_TWO_STEPS

        out = self._run(self._payload({"ok": True, "golden": {"commit": "0123456789ab"},
                                       "steps": [{"step": st, "ok": True, "detail": ""}
                                                 for st in PHASE_TWO_STEPS],
                                       "verify": {"state": "answered"}}))
        assert "toast:success" in out["calls"]
        assert "is onboarded" in out["html"] and "Back to the pending list" in out["html"]

    def test_no_result_is_a_toast_with_its_reason_never_a_blank(self):
        out = self._run({"ok": False, "error": "requires a verified person"})
        assert out["calls"][-2:] == ["toast:danger", "reload:ztp-a"]


class TestAZtpRenderUsesTheStrongerCredentialForm:
    """C52: `password 0` exists because vrnetlab injects its own user line
    first and a `secret` line for the same user is refused. On a ZTP device
    nothing injects one, so the render uses `secret 0`."""

    def test_ztp_gets_secret_0(self, tmp_path, monkeypatch):
        cfg = _plan(tmp_path, monkeypatch).bootstrap_config
        assert "username admin privilege 15 secret 0 " in cfg
        assert "password 0" not in cfg

    def test_every_other_c8000v_render_is_unchanged(self, tmp_path, monkeypatch):
        """The floor: vrnetlab still injects for those."""
        plan = _plan(tmp_path, monkeypatch, address_source="dhcp", mgmt_ip="",
                     ztp_check=None, kea=_NoKea())
        assert "username admin privilege 15 password 0 " in plan.bootstrap_config
