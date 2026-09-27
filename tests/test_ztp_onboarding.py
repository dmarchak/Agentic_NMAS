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
                address_source="ztp", mgmt_mac=MAC, mgmt_ip=ADDR, ztp_check=check)
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
