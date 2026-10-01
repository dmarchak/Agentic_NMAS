"""Changing a RUNNING IP SLA operation: delete, re-create from intent,
reschedule (2026-10-01, the operator: s3's probe to r1, every 10 s, to 60 s).

IOS refuses to modify a scheduled IP SLA entry ("Entry already running and
cannot be modified"), so the ordinary merge (`ip sla 1` / ` frequency 60`)
would be refused by the device and rolled back. On s3's REAL config:

- the computation (`modules/nsot/recreate.py`): the program, the merge that
  never sees the operation, the undo from the snapshot, the read-back, and
  each refusal (the delete not measured for the platform; configuration that
  names the operation);
- the measurement: `no ip sla N` is the removal shape
  `global.ip-sla-operation`, refused until measured, and the probe treats the
  operation's own schedule line as a companion (exact, not broader);
- the deploy path: the REAL /deploy/plan and /deploy/apply, the path that
  connects (`_deploy_one`) with the pipeline replaced by a recorder, the
  pipeline's verify, rollback, rollback read-back and rolled-back block, and
  the SHIPPED renderer drawing what the re-create replaces.
"""

import ast
import json
import os
import threading

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S3 = open(os.path.join(ROOT, "tests", "fixtures", "configs", "fleet", "s3.cfg"),
          encoding="utf-8").read()
R1 = open(os.path.join(ROOT, "tests", "fixtures", "configs", "fleet", "r1.cfg"),
          encoding="utf-8").read()
SIXTY = S3.replace(" frequency 10", " frequency 60")
assert SIXTY != S3

ECHO = " icmp-echo 10.255.1.11 source-interface Loopback0"
SCHED = "ip sla schedule 1 life forever start-time now"
PROGRAM = ["no ip sla 1", "ip sla 1", ECHO, " frequency 60", "exit", SCHED]
UNDO = ["no ip sla 1", "ip sla 1", ECHO, " frequency 10", "exit", SCHED]
MEASURED = {"state": "ok", "unmeasured": {}, "by_dialect": {"cisco_ios": {
    "global.ip-sla-operation": {"result": "exact", "device": "s4", "at": "2026-10-02T09:00:00Z"}}}}


@pytest.fixture
def measured(monkeypatch):
    monkeypatch.setattr("modules.nsot.removal.measured", lambda: MEASURED)


def _plan(intended=SIXTY, captured=S3, dialect="cisco_ios"):
    from modules.nsot import recreate
    return recreate.plan(intended, captured, dialect=dialect)


# ---------------------------------------------------------------- the computation

class TestTheProgram:
    def test_the_change_is_delete_define_reschedule(self, measured):
        p = _plan()
        assert p["refused"] == [] and [u["number"] for u in p["units"]] == ["1"]
        assert p["commands"] == PROGRAM

    def test_the_merge_never_sends_the_edit_the_device_refuses(self, measured):
        """The control: without the exclusion the ordinary merge sends exactly
        the in-place edit IOS refuses."""
        from modules.nsot import recreate
        from modules.nsot.deploy import merge_commands
        assert merge_commands(SIXTY, S3) == ["ip sla 1", " frequency 60", "exit"]
        assert merge_commands(recreate.exclude(SIXTY, _plan()["units"]), S3) == []

    def test_an_unchanged_operation_is_not_re_created(self, measured):
        assert _plan(S3, S3) == {"units": [], "commands": [], "refused": []}

    def test_a_new_operation_is_the_merges_and_a_removed_one_mode_bs(self, measured):
        no_sla = "\n".join(l for l in S3.splitlines()
                           if not l.startswith("ip sla") and l not in (ECHO, " frequency 10"))
        assert _plan(S3, no_sla)["units"] == []           # intent adds it: not running
        assert _plan(no_sla, S3)["units"] == []           # intent lacks it: Mode B

    def test_a_schedule_change_alone_re_creates(self, measured):
        later = S3.replace(SCHED, "ip sla schedule 1 life 3600 start-time now")
        p = _plan(later, S3)
        assert p["commands"][-1] == "ip sla schedule 1 life 3600 start-time now"
        assert p["commands"][0] == "no ip sla 1"

    def test_only_the_changed_operation_of_two(self, monkeypatch):
        """r1's REAL config (IOS-XE) holds two operations; changing one leaves
        the other to the merge, which has nothing to send for it. IOS-XE nests
        `frequency` under `icmp-echo`, so the definition closes two levels."""
        from modules.nsot import recreate
        both = json.loads(json.dumps(MEASURED))
        both["by_dialect"]["cisco_iosxe"] = both["by_dialect"]["cisco_ios"]
        monkeypatch.setattr("modules.nsot.removal.measured", lambda: both)
        ops = recreate.operations(R1)
        assert sorted(ops) == ["1", "2"]
        two = " icmp-echo 10.255.1.23 source-interface Loopback0\n  frequency 10"
        assert R1.count(two) == 1
        p = _plan(R1.replace(two, two.replace("frequency 10", "frequency 60")), R1,
                  dialect="cisco_iosxe")
        assert [u["number"] for u in p["units"]] == ["2"]
        assert p["commands"] == ["no ip sla 2", "ip sla 2",
                                 " icmp-echo 10.255.1.23 source-interface Loopback0",
                                 "  frequency 60", "exit", "exit",
                                 "ip sla schedule 2 life forever start-time now"]
        kept = recreate.exclude(R1, p["units"])
        assert "ip sla 1" in kept.splitlines() and "ip sla 2" not in kept.splitlines()

    def test_the_undo_is_the_old_definition_from_the_snapshot(self, measured):
        from modules.nsot import recreate
        assert recreate.undo_program(_plan()["units"], S3) == UNDO

    def test_the_read_back_names_what_it_found(self, measured):
        from modules.nsot import recreate
        units = _plan()["units"]
        assert recreate.unmatched(units, SIXTY, "new") == []
        assert recreate.unmatched(units, S3, "old") == []
        (off,) = recreate.unmatched(units, S3, "new")
        assert off["number"] == "1" and "frequency 10" in off["found"]


class TestTheRefusals:
    def test_unmeasured_is_refused_naming_the_shape_and_the_probe(self):
        p = _plan()                                       # the committed record
        assert p["units"] == [] and p["commands"] == []
        (r,) = p["refused"]
        assert "ip sla 1 is running" in r["reason"] and "refuses to modify" in r["reason"]
        assert "global.ip-sla-operation" in r["reason"]
        assert "nmas-removal-probe" in r["reason"]

    def test_measured_broader_is_refused(self, monkeypatch):
        bad = json.loads(json.dumps(MEASURED))
        bad["by_dialect"]["cisco_ios"]["global.ip-sla-operation"].update(
            result="broader", detail="also removed: track 1 ip sla 1 reachability")
        monkeypatch.setattr("modules.nsot.removal.measured", lambda: bad)
        (r,) = _plan()["refused"]
        assert "removes MORE than that line" in r["reason"]

    def test_measured_on_another_platform_is_not_this_one(self, measured):
        (r,) = _plan(dialect="cisco_iosxe")["refused"]
        assert "has not been measured on cisco_iosxe" in r["reason"]

    def test_configuration_naming_the_operation_refuses_naming_it(self, measured):
        tracked = S3.replace(SCHED, SCHED + "\ntrack 1 ip sla 1 reachability")
        (r,) = _plan(SIXTY.replace(SCHED, SCHED + "\ntrack 1 ip sla 1 reachability"),
                     tracked)["refused"]
        assert "track 1 ip sla 1 reachability" in r["reason"]


# ---------------------------------------------------------------- the measurement

class TestTheShapeIsMeasured:
    def test_the_operation_is_a_measured_shape_refused_until_measured(self):
        from modules.nsot import removal
        shape = removal.shape_for((), "ip sla 1", "stanza")
        assert shape is not None and shape.key == "global.ip-sla-operation"
        assert "has not been measured on cisco_ios" in removal._unmeasured(
            [], "ip sla 1", "stanza", "cisco_ios")

    def _probe(self):
        import importlib.machinery
        import importlib.util
        path = os.path.join(ROOT, "scripts", "nmas-removal-probe")
        loader = importlib.machinery.SourceFileLoader("nmas_removal_probe_rc", path)
        spec = importlib.util.spec_from_loader(loader.name, loader)
        mod = importlib.util.module_from_spec(spec)
        loader.exec_module(mod)
        return mod

    SCRATCH = (S3.replace("logging trap critical",
                          "ip sla 9901\n icmp-echo 192.0.2.13\n frequency 60\n"
                          "ip sla schedule 9901 life forever start-time now\n"
                          "logging trap critical"))

    def test_the_probe_sends_the_delete_mode_b_would(self):
        probe = self._probe()
        plans = probe.plan_for("global.ip-sla-operation")
        assert [p["program"] for p in plans] == [["no ip sla 9901"], ["no ip sla 9902"]]
        assert plans[0]["unit"]["companions"] == ["ip sla schedule 9901 "]

    def test_the_operations_own_schedule_is_a_companion_not_broader(self):
        probe = self._probe()
        unit = probe.plan_for("global.ip-sla-operation")[0]["unit"]
        assert probe.classify(self.SCRATCH, S3, unit)["result"] == "exact"
        # The control: without the companion the same read-backs are broader.
        plain = {k: v for k, v in unit.items() if k != "companions"}
        assert probe.classify(self.SCRATCH, S3, plain)["result"] == "broader"

    def test_anything_else_gone_is_still_broader(self):
        probe = self._probe()
        unit = probe.plan_for("global.ip-sla-operation")[0]["unit"]
        lost = S3.replace("logging trap critical\n", "")
        assert probe.classify(self.SCRATCH, lost, unit)["result"] == "broader"

    def test_the_probe_carries_the_companions_to_the_classifier(self):
        """The seam: `_locate` returns a fresh unit, and the measure loop puts
        the exemplar's companions back on it (read from the script)."""
        src = open(os.path.join(ROOT, "scripts", "nmas-removal-probe"), encoding="utf-8").read()
        assert 'unit["companions"] = list(ex["unit"]["companions"])' in src


# ---------------------------------------------------------------- the deploy path

@pytest.fixture
def client(monkeypatch):
    import app as nmas
    import routes.deploy as rd
    from modules.nsot.render_artifact import build_artifact

    def _fake(list_name, hostname, cache=None):
        artifact = build_artifact(hostname, S3, "cisco_ios", template_approved=True)
        return (artifact, S3, {"hostname": hostname, "ip": "192.0.2.23"}), ""

    monkeypatch.setattr(rd, "_artifact_for", _fake)
    monkeypatch.setattr("modules.nsot.deploy.prepare_device", lambda a: {"config": SIXTY})
    monkeypatch.setattr(rd, "_attribute_additions", lambda *a, **k: {
        "attributable": True, "from_this_edit": [], "pre_existing": [], "from_profile": []})
    sent = []

    def _deploy_one(entry, list_name, device_rows, authorise=None, source_ref="", remove=None):
        from modules.nsot.deploy import DEPLOYED
        sent.append(entry["artifact"].device)
        return {"device": entry["artifact"].device, "outcome": DEPLOYED}

    monkeypatch.setattr(rd, "_deploy_one", _deploy_one)
    monkeypatch.setattr(rd, "_commit_batch_golden", lambda *a, **k: {"commit": ""})
    c = nmas.app.test_client()
    c.sent = sent
    return c


def _route_plan(client):
    out = client.post("/deploy/plan", json={"devices": ["s3"]}).get_json()
    assert out["ok"], out
    return out, out["devices"][0]


class TestThePlanRoute:
    def test_the_plan_sends_the_re_create_and_says_what_it_replaces(self, client, measured):
        out, d = _route_plan(client)
        assert d["deployable"] is True, d.get("blocking_reasons")
        assert d["commands"] == PROGRAM
        (note,) = d["recreates"]
        assert note["lines"] == ["ip sla 1", ECHO, " frequency 10", SCHED]
        t = out["preview"]["targets"][0]
        assert t["program"]["notes"][0]["title"].startswith("ip sla 1 is running")
        assert "re-creating 1 running IP SLA operation(s)" in out["preview"]["what"]["summary"]

    def test_unmeasured_blocks_the_device_and_sends_nothing(self, client):
        _out, d = _route_plan(client)
        assert d["deployable"] is False
        assert any("global.ip-sla-operation" in r for r in d["blocking_reasons"])
        assert " frequency 60" not in d["commands"], "never the edit the device refuses"

    def test_the_shipped_renderer_draws_what_it_replaces(self, client, measured):
        import dukpy
        from tests.payload_render import shipped
        out, _d = _route_plan(client)
        html = dukpy.evaljs("var window = {};\n" + shipped("nmas_preview_confirm.js")
                            + f"\nwindow.previewConfirmHtml({json.dumps(out['preview'])}, {{}})")
        assert "ip sla 1 is running, and IOS refuses to modify a running operation" in html
        assert "frequency 10" in html and "no ip sla 1" in html

    def test_the_apply_recomputes_the_same_program(self, client, measured):
        _out, d = _route_plan(client)
        res = client.post("/deploy/apply", json={
            "confirmations": {"s3": d["capture_hash"]},
            "command_hashes": {"s3": d["command_hash"]}}).get_json()
        assert "s3" in res.get("deployed", []), res
        assert client.sent == ["s3"]


class TestThePathThatConnects:
    def test_the_pipeline_is_handed_the_re_create(self, monkeypatch, measured):
        import modules.pipeline as P
        import routes.deploy as rd
        from modules.nsot.render_artifact import build_artifact

        monkeypatch.setattr("modules.nsot.deploy.prepare_for_deploy",
                            lambda a: {"config": SIXTY})
        seen = {}

        class _Runner:
            def __init__(self, ctx):
                seen["ctx"] = ctx

            def run(self):
                raise RuntimeError("stopped after the context was built")

        monkeypatch.setattr(P, "PipelineRunner", _Runner)
        artifact = build_artifact("s3", S3, "cisco_ios", template_approved=True)
        out = rd._deploy_one({"artifact": artifact, "fresh": S3}, "Lab",
                             {"s3": {"hostname": "s3", "ip": "192.0.2.23"}}, {"s3": []})
        assert out["stage"] == "pipeline", out
        ctx = seen["ctx"]
        assert ctx.confirmed_commands["192.0.2.23"] == PROGRAM
        rm = ctx.removals["192.0.2.23"]
        assert rm["recreate_commands"] == PROGRAM and rm["recreates"][0]["number"] == "1"
        assert rm["commands"] == []

    def test_unmeasured_fails_before_the_pipeline(self, monkeypatch):
        import routes.deploy as rd
        from modules.nsot.render_artifact import build_artifact

        monkeypatch.setattr("modules.nsot.deploy.prepare_for_deploy",
                            lambda a: {"config": SIXTY})
        artifact = build_artifact("s3", S3, "cisco_ios", template_approved=True)
        out = rd._deploy_one({"artifact": artifact, "fresh": S3}, "Lab",
                             {"s3": {"hostname": "s3", "ip": "192.0.2.23"}}, {"s3": []})
        assert out["stage"] == "recreate" and "global.ip-sla-operation" in out["reason"]


def _ctx(**kw):
    from modules.pipeline import PipelineContext
    base = dict(config_type="template", device_ips=["192.0.2.31"], params={}, ip_params_map={},
                selected_devices=[{"ip": "192.0.2.31", "hostname": "s3"}], connections_pool={},
                pool_lock=threading.Lock(), config_id="t", settle_sleep=lambda _s: None)
    base.update(kw)
    return PipelineContext(**base)


def _units():
    from modules.nsot import recreate
    import modules.nsot.removal as removal
    real = removal.measured
    removal.measured = lambda: MEASURED
    try:
        return recreate.plan(SIXTY, S3, dialect="cisco_ios")["units"]
    finally:
        removal.measured = real


class TestVerifyReadsTheOperationBack:
    def _verify(self, post_cfg):
        import modules.pipeline as P
        ctx = _ctx()
        ctx.removals = {"192.0.2.31": {"units": [], "commands": [], "recreates": _units(),
                                     "recreate_commands": PROGRAM}}
        ctx.pre_snapshots = {"192.0.2.31": {}}
        ctx.post_snapshots = {"192.0.2.31": {"running_config": post_cfg}}
        try:
            P._stage_verify(ctx)
            return ctx, None
        except P.PipelineStageError as exc:
            return ctx, str(exc)

    def test_the_new_definition_passes(self):
        ctx, err = self._verify(SIXTY)
        assert err is None and ctx.verify_result["192.0.2.31"]["recreates_checked"] == ["1"]

    def test_the_old_definition_fails_naming_both(self):
        ctx, err = self._verify(S3)
        assert "ip sla 1 did not read back as intent defines it" in err
        assert "frequency 60" in err and "frequency 10" in err
        assert ctx.verify_result["192.0.2.31"]["recreates_off"] == ["1"]

    def test_unreadable_is_not_a_pass(self):
        _ctx_, err = self._verify("")
        assert "Re-created IP SLA operation not verified" in err


class TestRollbackRestoresTheOldDefinition:
    def _run(self, monkeypatch, readback):
        import modules.ai_assistant as A
        import modules.connection as C
        import modules.pipeline as P

        ctx = _ctx()
        ctx.push_results = {"192.0.2.31": {"ok": False}}
        ctx.confirmed_commands = {"192.0.2.31": list(PROGRAM)}
        ctx.removals = {"192.0.2.31": {"units": [], "commands": [], "recreates": _units(),
                                     "recreate_commands": list(PROGRAM)}}
        sent = []
        monkeypatch.setattr(A, "_load_pre_change_file", lambda ip: S3)
        monkeypatch.setattr(C, "get_persistent_connection", lambda *a: object())
        monkeypatch.setattr(P, "_restore_config", lambda conn, cmds: sent.append(list(cmds)))

        def temp(dev, func):
            class _Back:
                def send_command(self, _c, read_timeout=None):
                    return readback
            return func(_Back())
        monkeypatch.setattr(C, "with_temp_connection", temp)
        P._stage_rollback(ctx)
        return ctx, sent

    def test_the_undo_is_the_old_definition_and_reads_back_restored(self, monkeypatch):
        ctx, sent = self._run(monkeypatch, readback=S3)
        assert sent == [UNDO]
        assert ctx.rollback_outcome["192.0.2.31"]["state"] == "restored"

    def test_still_the_new_definition_after_the_undo_is_incomplete(self, monkeypatch):
        ctx, _sent = self._run(monkeypatch, readback=SIXTY)
        out = ctx.rollback_outcome["192.0.2.31"]
        assert out["state"] == "incomplete" and "no ip sla 1" in out["remaining"]
        assert ctx.final_status == "rollback_failed"


class TestTheBlockHoldsTheReCreate:
    def test_the_rolled_back_record_keeps_the_re_create(self, monkeypatch, tmp_path):
        """A plan's program holds its re-creates (`_current_program` builds it
        with `_program`), so the record keeps them, or the block lifts at once."""
        import modules.pipeline as P
        from modules.nsot import hostvars

        repo = tmp_path / "lab" / "config_repo"
        repo.mkdir(parents=True)
        monkeypatch.setattr("modules.config.get_list_data_dir", lambda n: str(tmp_path / "lab"))
        monkeypatch.setattr(hostvars, "intent_commits", lambda *a, **k: [{"sha": "abc"}])
        recorded = {}
        monkeypatch.setattr(hostvars, "record_rolled_back",
                            lambda repo, host, sha, **kw: recorded.update(kw))
        ctx = _ctx(list_name="Lab")
        ctx.confirmed_commands = {"192.0.2.31": list(PROGRAM)}
        ctx.removals = {"192.0.2.31": {"units": [], "commands": [], "recreates": _units(),
                                     "recreate_commands": list(PROGRAM)}}
        ctx.rolled_back_ips = ["192.0.2.31"]
        P._note_rolled_back_intent(ctx)
        assert recorded["commands"] == PROGRAM

    def test_a_fresh_plans_program_holds_the_re_create(self, monkeypatch, measured):
        import routes.deploy as rd
        from modules.nsot.render_artifact import build_artifact

        monkeypatch.setattr("modules.nsot.deploy.render_for_deploy", lambda *a, **k: SIXTY)
        artifact = build_artifact("s3", S3, "cisco_ios", template_approved=True)
        assert rd._current_program(artifact, S3) == PROGRAM


class TestOneComputation:
    def test_no_route_builds_a_program_but_program(self):
        """Plan, apply, the pipeline's run, the restore's preview and its apply
        all take the program from `routes.deploy._program`: a route that calls
        `merge_commands` itself would send the in-place edit the device refuses
        while its preview showed the re-create (the restore did, until this)."""
        calls = []
        for name in sorted(os.listdir(os.path.join(ROOT, "routes"))):
            if not name.endswith(".py"):
                continue
            tree = ast.parse(open(os.path.join(ROOT, "routes", name), encoding="utf-8").read())
            for fn in ast.walk(tree):
                if not isinstance(fn, ast.FunctionDef):
                    continue
                for node in ast.walk(fn):
                    if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "merge_commands":
                        calls.append(f"{name}:{fn.name}")
        assert calls == ["deploy.py:_program"], calls
