"""7.3: retire closes the gaps r5's retirement left, or names who closes them.

r5's retire commit (`3592113`, 2026-09-25) is the model: its six `Not-Done:`
trailers are what the screen draws before the confirm and in the result. The
gaps that retirement left, each measured on the host afterwards:

- C139: r5's NetBox record kept its stored config context, credentials and
  all, and no import reaches a retired device again. Retire now masks it,
  FIRST, with the same implementation as `nmas-netbox-mask-context`, when
  NetBox writes are on and NMAS recorded writing the context; otherwise it
  says why it stays;
- C176: r5's file stayed in the deprecated `golden_configs/` store. Retire
  now deletes it when its content survives in the repository, and says
  where; a file whose lines exist nowhere else is kept and named;
- the heartbeat rule and the scrape targets (C168): not NMAS's to write, so
  retire READS what is still live and names who removes it.

Every NetBox case drives r5's REAL config through FakeNetBox, the shape the
live NetBox held (C139's measurement).
"""

import os

import pytest
import yaml

import modules.nsot.retire as RT
from tests.fake_netbox import FakeNetBox
from tests.test_netbox_mask_context import COMMUNITY, _context, _device, _record
from tests.test_retire import PW, _bg, world  # noqa: F401  (the fixture)


@pytest.fixture
def nb(world, monkeypatch):  # noqa: F811
    import modules.netbox_client as nbc
    from modules import netbox_guard

    fake = FakeNetBox()
    fake.seed("dcim/devices", _device(i=9, name="r5"))
    state = {"writes": True, "record": (_record(), None)}
    monkeypatch.setattr(nbc, "_nb_ready", lambda: (True, "", fake, "http://127.0.0.1:9"))
    monkeypatch.setattr(netbox_guard, "read_modified", lambda: state["record"])
    monkeypatch.setattr(netbox_guard, "writes_allowed", lambda: state["writes"])

    def facts(list_name, hostname):
        dev = next((d for d in fake.store["dcim/devices"] if d["name"] == hostname), None)
        if dev is None:
            return {"checked": True, "exists": False}
        return {"checked": True, "exists": True, "id": dev["id"], "device": dev,
                "writes": state["writes"], "tags": [], "created_by_nmas": False}

    monkeypatch.setattr(RT, "_netbox_facts", facts)
    return {"fake": fake, "state": state, "world": world}


def _pending(p):
    return [s["key"] for s in p["steps"] if not s["done"]]


def _retire(p, **kw):
    return RT.apply("Lab", "r5", reason="left management", actor="op@example.com",
                    confirmed_hash=p["hash"], breakglass=_bg(), **kw)


class TestNetBoxStoredCredentials:
    def test_a_held_credential_is_masked_FIRST_when_writes_are_on(self, nb):
        p = RT.plan("Lab", "r5", "left management")
        assert p["ok"], p["refusals"]
        assert _pending(p) == ["netbox_mask", "declare", "commit", "row"], _pending(p)
        step = next(s["what"] for s in p["steps"] if s["key"] == "netbox_mask")
        assert "NetBox device 9" in step and "read back" in step
        assert COMMUNITY not in str(p), "the plan names the slot kinds, never a value"

    def test_apply_masks_reads_back_and_then_retires(self, nb):
        p = RT.plan("Lab", "r5", "left management")
        out = _retire(p)
        assert out["ok"], out
        assert out["done"][0] == "netbox_mask" and "commit" in out["done"]
        assert [x[0] for x in nb["fake"].patches] == ["dcim/devices"]
        held = str(nb["fake"].store["dcim/devices"][0]["local_context_data"])
        assert COMMUNITY not in held
        # Resumable: planning again finds nothing left to mask.
        again = RT.plan("Lab", "r5", "left management")
        assert "netbox_mask" not in _pending(again)

    def test_a_failed_mask_stops_with_nothing_else_done(self, nb):
        world = nb["world"]
        nb["fake"].patch = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("NetBox 500"))
        p = RT.plan("Lab", "r5", "left management")
        head = world["R"].git(world["repo"], "rev-parse", "HEAD")[1]
        out = _retire(p)
        assert out["ok"] is False and out["failed_at"] == "netbox_mask", out
        assert out["done"] == [] and "NetBox 500" in out["error"]
        assert world["R"].git(world["repo"], "rev-parse", "HEAD")[1] == head
        assert not world["settings"]["clab_declared_unmapped"], "not declared either"

    def test_a_write_netbox_did_not_keep_stops_the_retirement(self, nb):
        nb["fake"].patch = lambda url, json=None, timeout=None: type(
            "R", (), {"ok": True, "status_code": 200, "json": lambda s: _device(),
                      "raise_for_status": lambda s: None, "text": ""})()
        p = RT.plan("Lab", "r5", "left management")
        out = _retire(p)
        assert out["ok"] is False and "STILL holds" in out["error"], out

    def test_writes_off_with_a_held_credential_REFUSES_naming_it(self, nb):
        """The operator's decision, 2026-09-29: reads work with writes off, so
        the credential is KNOWN to be there; retiring past it is C139
        recurring, because no import reaches the device afterwards."""
        nb["state"]["writes"] = False
        p = RT.plan("Lab", "r5", "left management")
        assert p["ok"] is False
        why = p["refused_by"]["netbox_mask"]
        assert "NetBox writes are off" in why and "C139" in why
        assert "nmas-netbox-mask-context --device r5 --apply" in why
        assert COMMUNITY not in str(p)

    def test_writes_off_with_nothing_to_mask_proceeds_and_says_so(self, nb):
        nb["state"]["writes"] = False
        nb["fake"].store["dcim/devices"][0]["local_context_data"] = {}
        p = RT.plan("Lab", "r5", "left management")
        assert p["ok"], p["refusals"]
        step = next(s for s in p["steps"] if s["key"] == "netbox_mask")
        assert step["done"] and "nothing to mask" in step["what"]

    def test_the_refusal_is_drawn_as_a_gate_by_name(self, nb):
        from modules.preview_confirm import RETIRE_GATES

        assert "netbox_mask" in {key for key, _t, _d in RETIRE_GATES}

    def test_a_context_nmas_never_wrote_is_somebodys_data(self, nb):
        nb["state"]["record"] = ({}, None)
        p = RT.plan("Lab", "r5", "left management")
        assert "netbox_mask" not in _pending(p)
        joined = " ".join(p["not_doing"])
        assert "context is NOT masked" in joined
        assert "NMAS has no record of writing this context" in joined

    def test_an_unreadable_record_is_unknown_never_clean(self, nb):
        nb["state"]["record"] = (None, "unreadable (JSONDecodeError)")
        p = RT.plan("Lab", "r5", "left management")
        assert "could not be checked" in " ".join(p["not_doing"])
        assert "holds no unmasked credential" not in " ".join(p["not_doing"])

    def test_a_clean_context_is_a_done_step_saying_so(self, nb):
        nb["fake"].store["dcim/devices"][0]["local_context_data"] = {}
        p = RT.plan("Lab", "r5", "left management")
        assert "netbox_mask" not in _pending(p)
        assert any(s["key"] == "netbox_mask" and s["done"] for s in p["steps"])


class TestTheLegacyFile:
    def _legacy(self, world, text):
        d = os.path.join(os.path.dirname(world["repo"]), "golden_configs")
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, "r5.cfg")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path

    def test_a_file_whose_content_survives_is_deleted_saying_where(self, world):  # noqa: F811
        path = self._legacy(world, "hostname r5\nevent manager applet NMAS-HEARTBEAT\n")
        p = RT.plan("Lab", "r5", "left management")
        step = next(s for s in p["steps"] if s["key"] == "legacy")
        assert not step["done"] and "survives in the repository" in step["what"]
        assert "golden/r5.cfg at" in step["what"]
        out = _retire(p)
        assert out["ok"] and "legacy" in out["done"], out
        assert out["done"].index("legacy") > out["done"].index("commit")
        assert not os.path.exists(path)

    def test_a_file_holding_lines_nowhere_else_is_KEPT_and_named(self, world):  # noqa: F811
        path = self._legacy(world, "hostname r5\ninterface Loopback99\n ip address "
                                   "192.0.2.99 255.255.255.255\n")
        p = RT.plan("Lab", "r5", "left management")
        assert "legacy" not in _pending(p)
        joined = " ".join(p["not_doing"])
        assert "is KEPT" in joined and "Keep a copy before deleting it by hand" in joined
        assert _retire(p)["ok"]
        assert os.path.exists(path), "the only copy of those lines survives the retirement"

    def test_no_legacy_file_is_a_done_step(self, world):  # noqa: F811
        p = RT.plan("Lab", "r5", "left management")
        assert any(s["key"] == "legacy" and s["done"] for s in p["steps"])


class TestWhatStillWatchesIt:
    def _rules(self, tmp_path, monkeypatch, devices):
        doc = {"apiVersion": 1, "groups": [{"name": "nmas-heartbeat", "rules": [
            {"labels": {"device": d, "window_basis": "measured"},
             "data": [{"relativeTimeRange": {"from": 915}, "datasourceUid": "u"}]}
            for d in devices]}]}
        path = tmp_path / "nmas-heartbeat.yaml"
        path.write_text(yaml.safe_dump(doc))
        monkeypatch.setattr(RT, "_heartbeat_rules_path", lambda hb: str(path))

    def test_a_live_heartbeat_rule_is_named_with_the_command(self, world, tmp_path,  # noqa: F811
                                                            monkeypatch):
        self._rules(tmp_path, monkeypatch, ["r4", "r5"])
        joined = " ".join(RT.plan("Lab", "r5", "x y z")["not_doing"])
        assert "heartbeat rule (window 915 s) stays until the rules are regenerated" in joined
        assert "EXTRA meanwhile" in joined

    def test_no_rule_is_said_as_read(self, world, tmp_path, monkeypatch):  # noqa: F811
        self._rules(tmp_path, monkeypatch, ["r4"])
        assert "no Grafana heartbeat rule names it" in " ".join(
            RT.plan("Lab", "r5", "x y z")["not_doing"])

    def test_a_missing_rules_file_is_unknown_not_none(self, world, tmp_path,  # noqa: F811
                                                      monkeypatch):
        monkeypatch.setattr(RT, "_heartbeat_rules_path", lambda hb: str(tmp_path / "absent"))
        joined = " ".join(RT.plan("Lab", "r5", "x y z")["not_doing"])
        assert "whether one exists is unknown" in joined

    def _prom(self, monkeypatch, targets=None, fail=""):
        from modules.integrations import prometheus as P

        class Resp:
            def json(self):
                return {"data": {"activeTargets": targets or []}}

        monkeypatch.setattr(P.PrometheusIntegration, "is_configured", lambda self: True)
        monkeypatch.setattr(P.PrometheusIntegration, "_get", lambda self, path, **kw: (
            {"ok": False, "error": fail} if fail else {"ok": True, "response": Resp()}))

    def test_scrape_targets_still_polling_it_are_named_with_their_job(self, world,  # noqa: F811
                                                                      monkeypatch):
        self._prom(monkeypatch, [
            {"labels": {"instance": "192.0.2.15", "job": "snmp"}},
            {"labels": {"instance": "x", "job": "snmp_if"},
             "discoveredLabels": {"__param_target": "192.0.2.15"}},
            {"labels": {"instance": "192.0.2.14:161", "job": "snmp"}}])
        joined = " ".join(RT.plan("Lab", "r5", "x y z")["not_doing"])
        assert "Prometheus still scrapes 192.0.2.15 (2 target(s), job snmp, snmp_if)" in joined
        assert "hand-kept on the host" in joined and "C168" in joined

    def test_nothing_scraped_is_said_as_read(self, world, monkeypatch):  # noqa: F811
        self._prom(monkeypatch, [{"labels": {"instance": "192.0.2.14:9116", "job": "snmp"}}])
        assert "Prometheus scrapes nothing at 192.0.2.15" in " ".join(
            RT.plan("Lab", "r5", "x y z")["not_doing"])

    def test_prometheus_not_answering_is_may_still_poll(self, world, monkeypatch):  # noqa: F811
        self._prom(monkeypatch, fail="connection refused")
        joined = " ".join(RT.plan("Lab", "r5", "x y z")["not_doing"])
        assert "could not be asked (connection refused)" in joined
        assert "may still poll 192.0.2.15" in joined


def test_the_screen_draws_the_new_steps_and_statements(world, tmp_path,  # noqa: F811
                                                       monkeypatch):
    """Through the REAL preview route: each new step is a program line and each
    statement a what-will-NOT-happen item, as r5's list is. No credential
    value leaves in the payload."""
    from tests.test_retire_screen import _preview, screen  # noqa: F401

    TestTheLegacyFile()._legacy(world, "hostname r5\nevent manager applet NMAS-HEARTBEAT\n")
    import app as A

    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr("modules.config.DATA_DIR", str(data))
    monkeypatch.setattr("modules.config.get_current_list_name", lambda: "Lab")
    pv = _preview({**world, "client": A.app.test_client(), "data": str(data)})
    program = " ".join(l.get("text", "") if isinstance(l, dict) else str(l)
                       for l in pv["targets"][0]["program"]["lines"])
    assert "golden_configs" in program and "survives in the repository" in program
    what_not = " ".join(i["text"] for i in pv["what_not"]["items"])
    assert "heartbeat rule" in what_not and "Prometheus" in what_not


def test_every_step_retire_can_do_has_words_in_the_result(nb):
    """A step key drawn raw in the result is a record nobody can read: every
    key the plan can produce has its words, and the real result says them."""
    from modules.preview_confirm import RETIRE_STEP_WORDS, retire_result

    TestTheLegacyFile()._legacy(nb["world"], "hostname r5\nevent manager applet NMAS-HEARTBEAT\n")
    p = RT.plan("Lab", "r5", "left management")
    keys = {s["key"] for s in p["steps"]}
    assert {"netbox_mask", "override", "declare", "commit", "legacy", "row"} <= keys
    assert keys <= set(RETIRE_STEP_WORDS)
    out = _retire(p)
    sent = retire_result(out, p)["targets"][0]["sent"]["lines"]
    assert sent[0].startswith("masked the credentials NetBox held") and any(
        "golden_configs" in l for l in sent), sent
