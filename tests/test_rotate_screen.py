"""7.3's ROTATE screen, over the real route, job registry, adapters and
`rotate_op.run()`, with `credential_rotation`'s device-facing calls replaced
at `rotate()`, `persist()` and `plan()` (their own suites drive the session).

Built assuming a fourth failure mode exists (the operator): every state is
named with its one action, the apply is a job (rotate plus persist can pass
the 100 s edge limit), the device is held across rotate AND persist, and the
job carries the confirming person's VERIFIED identity into its thread.
"""

import os
import threading

import pytest

from modules.nsot import capture_job
from modules.nsot import credential_rotation as cr
from modules.nsot import rotate_op as RO
from tests.payload_render import render_preview, render_result

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NEW = "N3w-Rotated-Value-77"


def _plan(ok=True, fingerprint="fp-abc123"):
    checks = [{"name": "helper_installed_and_matching", "ok": True, "detail": ""},
              {"name": "live_user_line_read", "ok": ok,
               "detail": "" if ok else "TCP connection to device failed"}]
    p = {"ok": ok, "preflight": {"checks": checks}, "device": "r2", "list_name": "Lab"}
    if ok:
        p.update(mgmt_ip="192.0.2.12", username="admin", privilege=15,
                 current_form="username admin privilege 15 secret 9 <redacted:secret>",
                 new_program=cr.masked_commands("admin", 15, "secret"), entry_kind="secret",
                 fingerprint=fingerprint, length=32, discrepancy="",
                 consumers=[{"name": "NMAS", "action": "updated automatically"}])
    else:
        p["error"] = "live_user_line_read: TCP connection to device failed"
    return p


@pytest.fixture
def lab(monkeypatch):
    import app as A

    state = {"plan": _plan(), "rotate_state": cr.ROTATED_PENDING_PERSIST,
             "persist_state": cr.ROTATED_PERSISTED, "password": NEW, "calls": []}
    monkeypatch.setattr(RO, "plan", lambda l, h: dict(state["plan"]))
    monkeypatch.setattr("modules.config.get_current_list_name", lambda: "Lab")

    def rotate(list_name, hostname, **kw):
        from modules.nsot import device_ops
        state["calls"].append(("rotate", device_ops.holder(list_name, hostname) is not None,
                               kw.get("confirmed_fingerprint")))
        out = {"device": hostname, "state": state["rotate_state"], "steps": [
            {"name": "push", "ok": True}, {"name": cr.VERIFY, "ok": True,
                                           "detail": "fresh login with the new credential"}],
               "new_hash": "9 $9$s$h", "mgmt_ip": "192.0.2.12", "username": "admin",
               "commit": {"ok": True, "commit": "abc1234def56"}}
        return out

    def persist(result, **kw):
        from modules.nsot import device_ops
        state["calls"].append(("persist",
                               device_ops.holder(kw["list_name"], kw["hostname"]) is not None,
                               kw.get("password") == NEW))
        return {**result, "state": state["persist_state"], "persistence": [
            {"name": "device_startup_config", "ok": state["persist_state"] ==
             cr.ROTATED_PERSISTED, "error": "" if state["persist_state"] ==
             cr.ROTATED_PERSISTED else "the startup config does not carry it"}]}

    monkeypatch.setattr(cr, "rotate", rotate)
    monkeypatch.setattr(cr, "persist", persist)
    monkeypatch.setattr(cr, "platform_of", lambda l, h: "cisco_iosxe")
    monkeypatch.setattr(RO, "_inventory_password", lambda l, h: state["password"])
    return {"client": A.app.test_client(), "state": state}


def _preview(lab):
    r = lab["client"].post("/rotate/preview", json={"device": "r2"})
    assert r.status_code == 200, r.get_data(as_text=True)
    return r.get_json()["preview"]


def _apply(lab, preview):
    data = preview["what"]["targets"][0]["select_data"]
    return lab["client"].post("/rotate/apply", json={"list_name": data["list"], "device": "r2",
                                                     "fingerprint": data["fingerprint"]})


def _finish(lab, r):
    assert r.status_code == 202, r.get_data(as_text=True)
    job = r.get_json()["job"]
    assert capture_job.wait(job, 30)
    got = lab["client"].get(f"/rotate/result/{job}").get_json()
    assert got["state"] == "done", got
    return got["result"]


class TestThePreview:
    def test_the_program_is_what_is_sent_with_the_password_masked(self, lab):
        p = _preview(lab)
        target = p["targets"][0]
        assert target["program"]["lines"] == cr.masked_commands("admin", 15, "secret")
        assert "<generated>" in " ".join(target["program"]["lines"])
        html = render_preview(p)
        assert "will be sent" in html, "a program that IS sent keeps the deploy's sentence"
        said = " ".join(i["text"] for i in p["what_not"]["items"])
        assert "the template is not changed" in said and "DEAD credential" in said

    def test_each_preflight_check_is_a_gate_by_name(self, lab):
        lab["state"]["plan"] = _plan(ok=False)
        p = _preview(lab)
        gates = {g["name"]: g for g in p["targets"][0]["gates"]}
        assert gates["live user line read"]["state"] == "fail"
        assert "TCP connection" in gates["live user line read"]["detail"]
        assert p["what"]["targets"][0]["selectable"] is False

    def test_the_confirm_says_the_device_then_accepts_only_the_new_password(self, lab):
        confirm = _preview(lab)["confirm"]
        assert "accepts ONLY the new password" in confirm["effect"]
        assert "export it again" in confirm["effect"] and confirm["button"] == "Rotate r2"


class TestTheApplyIsAJob:
    def test_it_answers_at_once_and_the_result_is_read_by_id(self, lab):
        result = _finish(lab, _apply(lab, _preview(lab)))
        assert result["level"] == "success"
        assert result["happened"]["summary"].startswith("r2: rotated, verified, committed")
        assert "export it again" in result["happened"]["summary"], "the break-glass record"
        assert result["targets"][0]["sent"]["lines"] == cr.masked_commands("admin", 15, "secret")
        assert NEW not in str(result)
        html = render_result(result)
        assert "abc1234def56" in html

    def test_the_device_is_held_across_rotate_and_persist(self, lab):
        _finish(lab, _apply(lab, _preview(lab)))
        assert lab["state"]["calls"] == [("rotate", True, "fp-abc123"),
                                         ("persist", True, True)], lab["state"]["calls"]

    def test_a_moved_fingerprint_starts_nothing(self, lab):
        p = _preview(lab)
        lab["state"]["plan"] = _plan(fingerprint="fp-moved")
        r = _apply(lab, p)
        assert r.status_code == 409 and "fp-abc123 -> fp-moved" in r.get_json()["error"]
        assert lab["state"]["calls"] == []

    def test_a_refused_plan_starts_nothing(self, lab):
        p = _preview(lab)
        lab["state"]["plan"] = _plan(ok=False)
        r = _apply(lab, p)
        assert r.status_code == 409 and lab["state"]["calls"] == []
        assert r.get_json()["error"].startswith("Refused before anything was sent: "
                                                "live_user_line_read")

    def test_the_apply_needs_its_list(self, lab):
        r = lab["client"].post("/rotate/apply", json={"device": "r2", "fingerprint": "x"})
        assert r.status_code == 400 and "never from whichever list is active" in \
            r.get_json()["error"]

    def test_a_job_this_server_does_not_know_points_at_the_record(self, lab):
        r = lab["client"].get("/rotate/result/nope")
        assert r.status_code == 404
        assert "restarted" in r.get_json()["error"] and "rotation row" in r.get_json()["error"]


class TestEveryStateIsNamedWithItsAction:
    @pytest.mark.parametrize("state", [cr.ROTATED_PERSISTED, cr.ROTATED_PENDING_PERSIST,
                                       cr.ROTATED_UNVERIFIED, cr.ROTATED_NOT_RECORDED,
                                       cr.REVERTED, cr.REVERT_FAILED, cr.REVERTED_UNPROVEN,
                                       cr.NOT_STARTED])
    def test_each_state_has_its_own_next_step(self, state):
        from modules.preview_confirm import rotate_result

        result = rotate_result({"device": "r2", "state": state, "steps": []}, _plan())
        nxt = result["next"]
        assert nxt["text"] and "The state above is what is known" not in nxt["text"], state
        # C219: the next step has its own slot, never "What did not happen".
        assert not [i for i in result["did_not"]["items"] if "Next" in i["text"]]
        opens = state in (cr.ROTATED_PERSISTED, cr.ROTATED_PENDING_PERSIST)
        assert (nxt["open"] == "breakglass_export") is opens, state
        assert not opens or nxt["args"] == {"list": "Lab"}
        assert result["happened"]["summary"] == cr.summarise(
            {"device": "r2", "state": state, "steps": []})

    def test_not_recorded_names_the_recovery_command(self):
        from modules.preview_confirm import rotate_result

        result = rotate_result({"device": "r2", "state": cr.ROTATED_NOT_RECORDED, "steps": []},
                               _plan())
        assert "nmas-rotation-recover r2 --list Lab" in result["next"]["text"]

    def test_a_persist_that_did_not_finish_is_said_and_never_green(self, lab):
        lab["state"]["persist_state"] = cr.ROTATED_UNVERIFIED
        result = _finish(lab, _apply(lab, _preview(lab)))
        assert result["level"] == "failed"
        assert result["happened"]["summary"].startswith("r2: NOT SAFE TO REBOOT")
        assert "persistence stopped at device_startup_config" in str(result["did_not"])

    def test_no_recorded_password_skips_persist_and_says_so(self, lab):
        lab["state"]["password"] = ""
        result = _finish(lab, _apply(lab, _preview(lab)))
        assert result["level"] == "partial"
        assert "persist did not run" in str(result["did_not"])
        assert [c[0] for c in lab["state"]["calls"]] == ["rotate"]


class TestTheJobCarriesTheVerifiedPerson:
    def test_a_commit_in_the_job_reads_access_only_for_that_actor(self, monkeypatch):
        from modules import identity

        class Ident:
            is_identified, actor = True, "op@example.com"

        seen = {}

        def work(list_name, hostname, *, actor, fingerprint):
            seen["same"] = identity.actor_verification("op@example.com")
            seen["other"] = identity.actor_verification("someone@else.com")
            return {"ok": True}

        job = RO.start("Lab", "r2", actor="op@example.com", fingerprint="f",
                       ident=Ident(), work=work)
        assert capture_job.wait(job, 10)
        assert seen == {"same": "access", "other": "none"}

    def test_nothing_carried_reads_none_in_a_job(self):
        from modules import identity

        seen = {}

        def work(list_name, hostname, *, actor, fingerprint):
            seen["v"] = identity.actor_verification("op@example.com")
            return {"ok": True}

        job = RO.start("Lab", "r2", actor="op@example.com", fingerprint="f", ident=None,
                       work=work)
        assert capture_job.wait(job, 10)
        assert seen["v"] == "none"


class TestABusyDevice:
    def test_a_held_device_is_refused_with_nothing_sent(self, lab):
        from modules.nsot import device_ops

        held, done = threading.Event(), threading.Event()

        def _other():
            with device_ops.hold("Lab", "r2", "deploy", "someone@example.com"):
                held.set()
                done.wait(10)

        t = threading.Thread(target=_other)
        t.start()
        try:
            assert held.wait(10)
            out = RO.run("Lab", "r2", actor="op", fingerprint="fp-abc123")
        finally:
            done.set()
            t.join(10)
        assert out["state"] == cr.NOT_STARTED and "Nothing was sent" in out["reason"]
        assert lab["state"]["calls"] == []


class TestTheDevicePageOffersIt:
    def test_the_button_and_the_client_are_shipped(self):
        page = open(os.path.join(ROOT, "templates", "device.html")).read()
        assert 'onclick="openRotate(this.dataset.hostname)"' in page
        assert "js/nmas_rotate.js" in open(os.path.join(ROOT, "templates", "base.html")).read()
