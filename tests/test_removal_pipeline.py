"""Mode B through the deploy path (7.3 step 2b): a SELECTED removal, with a
stated reason, planned, confirmed by hash, carried to the pipeline, verified
gone, and undone by re-adding the device's own lines.

Built from the deploy wizard's fixture (a real artifact, the real merge, the
real authorisation code), with the device replaced by recording fakes. The
seams the map found (2026-09-29) are the subject: the program was computed
three times, merge-only refused any `no` line, and rollback read a pushed
`no X` as never applied and reported "restored" with X still gone.
"""

import threading

import pytest

from tests import test_p3_wizard_draws_the_program as W

GI03 = "interface GigabitEthernet0/3"
CAPTURE = W.CAPTURE.replace("end\n", f"{GI03}\n description retired uplink\n"
                                     "snmp-server community OLDCOMMUNITY RO\nend\n")
UNIT = {"chain": [GI03], "line": " description retired uplink"}
KEY = "no description retired uplink"
REASON = {"line": KEY, "reason": "the uplink was retired last week"}
SHUT = W.SHUT


@pytest.fixture
def client(monkeypatch):
    import app as nmas
    import routes.deploy as rd
    from modules.nsot.render_artifact import build_artifact

    def _fake(list_name, hostname, cache=None):
        artifact = build_artifact(hostname, CAPTURE, "cisco_ios", template_approved=True)
        return (artifact, CAPTURE, {"hostname": hostname, "ip": "203.0.113.24"}), ""

    monkeypatch.setattr(rd, "_artifact_for", _fake)
    monkeypatch.setattr("modules.nsot.deploy.prepare_device", lambda a: {"config": W.INTENT})
    monkeypatch.setattr(rd, "_attribute_additions", lambda *a, **k: dict(W.ATTRIBUTION))
    sent = []

    def _deploy_one(entry, list_name, device_rows, authorise=None, source_ref="", remove=None):
        from modules.nsot.deploy import DEPLOYED
        sent.append({"device": entry["artifact"].device, "remove": remove})
        return {"device": entry["artifact"].device, "outcome": DEPLOYED}

    monkeypatch.setattr(rd, "_deploy_one", _deploy_one)
    monkeypatch.setattr(rd, "_commit_batch_golden", lambda *a, **k: {"commit": ""})
    c = nmas.app.test_client()
    c.sent = sent
    return c


def _plan(client, remove=None, authorise=None):
    body = {"devices": ["s4"]}
    if remove is not None:
        body["remove"] = {"s4": remove}
    if authorise is not None:
        body["authorise"] = {"s4": authorise}
    out = client.post("/deploy/plan", json=body).get_json()
    assert out["ok"], out
    return out, out["devices"][0]


class TestThePlan:
    def test_the_removal_is_the_programs_tail_and_the_residue_is_not_promised(self, client):
        out, d = _plan(client, [UNIT], [SHUT, REASON])
        assert d["commands"][-3:] == [GI03, " no description retired uplink", "exit"]
        assert d["removals"]["removed"] == [UNIT] and d["removals"]["keys"] == [KEY]
        assert d["authorisation_ok"] is True, d.get("authorisation_error")
        t = out["preview"]["targets"][0]
        assert t["program"]["removal"] == [KEY]
        residue = [i for i in out["preview"]["what_not"]["items"] if i["kind"] == "residue"]
        lines = [l.strip() for i in residue for l in i["lines"]]
        assert "description retired uplink" not in lines, "never promised as NOT removed"
        assert "snmp-server community <redacted:snmp_community> RO" in lines, \
            "the unselected residue stays, masked on the way out"
        words = next(o["value"] for o in t["operands"] if o["name"] == "removals selected")
        assert words.startswith("1 removed by the last 3 line(s) of the program: "
                                f"{GI03} > description retired uplink")

    def test_a_removal_without_a_reason_is_not_authorised(self, client):
        _, d = _plan(client, [UNIT], [SHUT])
        assert d["authorisation_ok"] is False and repr(KEY) in d["authorisation_error"]

    def test_the_hash_binds_the_removal_and_its_reason(self, client):
        _, none = _plan(client, [], [SHUT])
        _, one = _plan(client, [UNIT], [SHUT, REASON])
        _, other = _plan(client, [UNIT], [SHUT, {**REASON, "reason": "a different stated reason"}])
        assert len({none["command_hash"], one["command_hash"], other["command_hash"]}) == 3

    def test_a_refused_selection_blocks_the_device_and_says_why(self, client):
        _, d = _plan(client, [{"chain": [], "line": "hostname s4"}], [SHUT])
        assert d["deployable"] is False and d["removals"]["refused"]
        assert any("a removal you selected is refused: hostname s4" in r
                   for r in d["blocking_reasons"])

    def test_a_secret_position_removal_is_flagged_and_never_leaves_unmasked(self, client):
        """And the constraint it shows for 2c: the plan comes back MASKED, so the
        browser can never echo a secret-position line's real text to select it.
        2c selects removals by a server-computed id, not by the line."""
        unit = {"chain": [], "line": "snmp-server community OLDCOMMUNITY RO"}
        out, d = _plan(client, [unit], [SHUT])
        masked = "snmp-server community <redacted:snmp_community> RO"
        assert d["removals"]["secret_position"] == [{"chain": [], "line": masked}]
        (key,) = d["removals"]["keys"]
        assert "OLDCOMMUNITY" not in key and "OLDCOMMUNITY" not in str(out)


class TestTheApply:
    def _apply(self, client, d, remove, authorise):
        return client.post("/deploy/apply", json={
            "confirmations": {"s4": d["capture_hash"]},
            "command_hashes": {"s4": d["command_hash"]},
            "remove": {"s4": remove}, "authorise": {"s4": authorise}}).get_json()

    def test_the_confirmed_removal_reaches_the_pipeline(self, client):
        _, d = _plan(client, [UNIT], [SHUT, REASON])
        out = self._apply(client, d, [UNIT], [SHUT, REASON])
        assert "s4" in out.get("deployed", []), out
        assert client.sent == [{"device": "s4", "remove": {"s4": [UNIT]}}]

    def test_dropping_the_removal_at_apply_is_refused(self, client):
        """The removal is part of what was confirmed: an apply without it
        computes another program, and the hash says so."""
        _, d = _plan(client, [UNIT], [SHUT, REASON])
        out = self._apply(client, d, [], [SHUT])
        assert "s4" not in out.get("deployed", []) and client.sent == []


class TestDeployOne:
    """The path that connects, with the pipeline replaced by a recorder."""

    def _run(self, monkeypatch, remove, authorise, captured=CAPTURE):
        import modules.pipeline as P
        import routes.deploy as rd
        from modules.nsot.render_artifact import build_artifact

        monkeypatch.setattr("modules.nsot.deploy.prepare_for_deploy",
                            lambda a: {"config": W.INTENT})
        seen = {}

        class _Runner:
            def __init__(self, ctx):
                seen["ctx"] = ctx

            def run(self):
                raise RuntimeError("stopped after the context was built")

        monkeypatch.setattr(P, "PipelineRunner", _Runner)
        artifact = build_artifact("s4", CAPTURE, "cisco_ios", template_approved=True)
        out = rd._deploy_one({"artifact": artifact, "fresh": captured}, "Lab",
                             {"s4": {"hostname": "s4", "ip": "203.0.113.24"}},
                             {"s4": authorise}, remove={"s4": remove})
        return out, seen.get("ctx")

    def test_the_removal_is_the_confirmed_tail_and_the_pipeline_knows_it(self, monkeypatch):
        out, ctx = self._run(monkeypatch, [UNIT], [SHUT, REASON])
        assert out["stage"] == "pipeline", out           # reached the runner
        sent = ctx.confirmed_commands["203.0.113.24"]
        assert sent[-3:] == [GI03, " no description retired uplink", "exit"]
        assert ctx.removals["203.0.113.24"] == {
            "units": [UNIT], "commands": [GI03, " no description retired uplink", "exit"]}

    def test_no_reason_fails_before_the_pipeline(self, monkeypatch):
        out, ctx = self._run(monkeypatch, [UNIT], [SHUT])
        assert out["stage"] == "authorisation" and ctx is None and KEY in out["reason"]

    def test_a_unit_gone_from_the_capture_fails_before_the_pipeline(self, monkeypatch):
        out, ctx = self._run(monkeypatch, [UNIT], [SHUT, REASON], captured=W.CAPTURE)
        assert out["stage"] == "removal" and ctx is None and "not on the device" in out["reason"]


def _ctx(**kw):
    from modules.pipeline import PipelineContext
    base = dict(config_type="template", device_ips=["10.0.0.1"], params={}, ip_params_map={},
                selected_devices=[{"ip": "10.0.0.1", "hostname": "s4"}], connections_pool={},
                pool_lock=threading.Lock(), config_id="t", settle_sleep=lambda _s: None)
    base.update(kw)
    return PipelineContext(**base)


class TestVerifyReadsItGone:
    def _verify(self, post_cfg):
        import modules.pipeline as P
        ctx = _ctx()
        ctx.removals = {"10.0.0.1": {"units": [UNIT], "commands": []}}
        ctx.pre_snapshots = {"10.0.0.1": {}}
        ctx.post_snapshots = {"10.0.0.1": {"running_config": post_cfg}}
        try:
            P._stage_verify(ctx)
            return ctx, None
        except P.PipelineStageError as exc:
            return ctx, str(exc)

    def test_gone_passes(self):
        ctx, err = self._verify(W.CAPTURE)
        assert err is None and ctx.verify_result["10.0.0.1"]["removals_checked"] == 1

    def test_still_there_fails_naming_it(self):
        ctx, err = self._verify(CAPTURE)
        assert "Removal did not take" in err and "description retired uplink" in err
        assert ctx.verify_result["10.0.0.1"]["removals_left"] == ["description retired uplink"]

    def test_unreadable_is_not_a_pass(self):
        _ctx_, err = self._verify("")
        assert "Removal not verified" in err


class TestRollbackPutsTheLineBack:
    """The map's worst seam: `no X` read as never applied, left undone, and
    the read-back saying restored with X still gone."""

    PUSHED = [GI03, " no description retired uplink", "exit"]

    def _run(self, monkeypatch, readback, pushed=None):
        import modules.ai_assistant as A
        import modules.connection as C
        import modules.pipeline as P

        ctx = _ctx()
        ctx.push_results = {"10.0.0.1": {"ok": False}}
        ctx.confirmed_commands = {"10.0.0.1": list(pushed or self.PUSHED)}
        ctx.removals = {"10.0.0.1": {"units": [UNIT], "commands": list(self.PUSHED)}}
        sent = []
        monkeypatch.setattr(A, "_load_pre_change_file", lambda ip: CAPTURE)
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

    def test_the_undo_re_adds_the_line_verbatim_and_nothing_is_called_never_applied(
            self, monkeypatch):
        ctx, sent = self._run(monkeypatch, readback=CAPTURE)
        assert sent == [[GI03, " description retired uplink", "exit"]]
        assert ctx.rollback_not_undone.get("10.0.0.1") in (None, [])
        assert ctx.rollback_outcome["10.0.0.1"]["state"] == "restored"

    def test_still_missing_after_the_undo_is_incomplete(self, monkeypatch):
        ctx, _sent = self._run(monkeypatch, readback=W.CAPTURE)
        out = ctx.rollback_outcome["10.0.0.1"]
        assert out["state"] == "incomplete" and " description retired uplink" in out["remaining"]
        assert ctx.final_status == "rollback_failed"

    def test_a_program_whose_tail_is_not_its_removals_builds_no_undo(self, monkeypatch):
        ctx, sent = self._run(monkeypatch, readback=CAPTURE,
                              pushed=[GI03, " description other", "exit"])
        assert sent == [] and ctx.rollback_outcome["10.0.0.1"]["state"] == "failed"
        assert "cannot be told apart" in ctx.rollback_outcome["10.0.0.1"]["detail"]


class TestTheBlockHoldsTheAdditionsOnly:
    def test_the_rolled_back_record_leaves_the_removal_tail_out(self, monkeypatch, tmp_path):
        """A plan's additions never hold a removal line, so a recorded tail
        would make the block's containment fail and the block lift at once."""
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
        adds = ["interface GigabitEthernet0/2", " shutdown", "exit"]
        tail = [GI03, " no description retired uplink", "exit"]
        ctx.confirmed_commands = {"10.0.0.1": adds + tail}
        ctx.removals = {"10.0.0.1": {"units": [UNIT], "commands": tail}}
        ctx.rolled_back_ips = ["10.0.0.1"]
        P._note_rolled_back_intent(ctx)
        assert recorded["commands"] == adds


class TestThePreviewSaysWhatThisProgramDoes:
    def test_merge_only_is_said_only_when_nothing_is_removed(self, client):
        with_rm, _ = _plan(client, [UNIT], [SHUT, REASON])
        without, _ = _plan(client, [], [SHUT])
        assert "merge-only plus the removals you selected" in with_rm["preview"]["what"]["summary"]
        assert "removed ONLY where you selected it" in \
            with_rm["preview"]["explain"]["what_not"][0]["text"]
        assert "merge-only plus" not in without["preview"]["what"]["summary"]
        assert "is never removed" in without["preview"]["explain"]["what_not"][0]["text"]
