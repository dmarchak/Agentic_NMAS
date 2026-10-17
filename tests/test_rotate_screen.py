"""7.3's ROTATE screen, over the real route, job registry, adapters and
`rotate_op.run()`, with `credential_rotation`'s device-facing calls replaced
at `rotate()`, `persist()` and `plan()` (their own suites drive the session).

Built assuming a fourth failure mode exists (the operator): every state is
named with its one action, the apply is a job (rotate plus persist can pass
the 100 s edge limit), the device is held across rotate AND persist, and the
job carries the confirming person's VERIFIED identity into its thread.

The preview and result models are read through the v2 device page's Rotate card (its preview,
confirm and job routes; `tests/v2_card_models.py`) on test_persist_screen's inventory (Lab's
r2): today's JSON routes, POST /rotate/preview and /rotate/apply and GET /rotate/result/<job>,
left at 7.8 (2026-10-17, P7-24). What the card draws is tests/test_device_rotate_v2.py's.
"""

import os
import re
import threading

import pytest

from modules.nsot import capture_job
from modules.nsot import credential_rotation as cr
from modules.nsot import rotate_op as RO
from tests.test_persist_screen import lab as inventory  # noqa: F401 (the fixture: Lab's r2)
from tests.v2_card_models import spying, the_one

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
def lab(inventory, monkeypatch):  # noqa: F811
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
    return dict(inventory, state=state)


def _preview(lab):
    """The preview model the v2 Rotate card is drawn from (`device_actions.rotate_card`'s
    third argument, masked), through POST /v2/device/r2/rotate/preview; the card's HTML is
    kept as ``lab["preview_html"]``."""
    from modules import device_actions

    with spying(device_actions, "rotate_card") as calls:
        r = lab["client"].post("/v2/device/r2/rotate/preview", data={"list": "Lab"})
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    lab["preview_html"] = r.get_data(as_text=True)
    args, _kw = the_one(calls, "rotate_card")
    return args[2]


def _apply(lab, preview):
    """v2's confirm, POST /v2/device/r2/rotate/confirm, with the list and fingerprint the
    preview carries."""
    data = preview["what"]["targets"][0]["select_data"]
    return lab["client"].post("/v2/device/r2/rotate/confirm",
                              data={"list": data["list"], "fingerprint": data["fingerprint"]})


def _finish(lab, r):
    """The started job, waited for: its result model, the one v2's job card draws
    (`device_actions.rotate_job_card` reads the job's payload); the card's HTML is kept as
    ``lab["result_html"]``."""
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    job = re.search(r"/rotate/job/([0-9a-f]+)", r.get_data(as_text=True)).group(1)
    assert capture_job.wait(job, 30)
    got = capture_job.get(job)
    assert got["state"] == "done", got
    lab["result_html"] = lab["client"].get(f"/v2/device/r2/rotate/job/{job}").get_data(
        as_text=True)
    return got["payload"]["result"]


class TestThePreview:
    def test_the_program_is_what_is_sent_with_the_password_masked(self, lab):
        p = _preview(lab)
        target = p["targets"][0]
        assert target["program"]["lines"] == cr.masked_commands("admin", 15, "secret")
        assert "<generated>" in " ".join(target["program"]["lines"])
        # v2's card heads the program "What is sent" (a program that IS sent; today's renderer
        # said "will be sent" until it left with the routes, P7-24), its password masked.
        html = lab["preview_html"]
        sent = html[html.index("What is sent"):html.index("Operands")]
        assert "&lt;generated&gt;" in sent
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
        html = lab["result_html"]
        assert "abc1234def56" in html and NEW not in html

    def test_the_device_is_held_across_rotate_and_persist(self, lab):
        _finish(lab, _apply(lab, _preview(lab)))
        assert lab["state"]["calls"] == [("rotate", True, "fp-abc123"),
                                         ("persist", True, True)], lab["state"]["calls"]

    def test_a_moved_fingerprint_starts_nothing(self, lab):
        p = _preview(lab)
        lab["state"]["plan"] = _plan(fingerprint="fp-moved")
        r = _apply(lab, p)
        assert r.status_code == 409 and "fp-abc123 -&gt; fp-moved" in r.get_data(as_text=True)
        assert lab["state"]["calls"] == []

    def test_a_refused_plan_starts_nothing(self, lab):
        p = _preview(lab)
        lab["state"]["plan"] = _plan(ok=False)
        r = _apply(lab, p)
        assert r.status_code == 409 and lab["state"]["calls"] == []
        assert ("Refused before anything was sent: live_user_line_read"
                in r.get_data(as_text=True))

    # test_the_apply_needs_its_list (POST /rotate/apply with no list, 400) left with the route
    # (P7-24): v2's confirm refuses a write naming no list or an unknown one, with nothing sent,
    # in tests/test_device_rotate_v2.py (TestTheConfirm.test_a_write_naming_no_list_or_no_plan_
    # is_refused).

    def test_a_job_this_server_does_not_know_points_at_the_record(self, lab):
        """v2's job card for a job this server has no record of (today's GET
        /rotate/result/<job> said the same until it left, P7-24)."""
        html = lab["client"].get("/v2/device/r2/rotate/job/0123abcd").get_data(as_text=True)
        assert "restarted" in html and "rotation row" in html


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
        # C541: persistence not attempted or failed opens PERSIST (the words' first action, the
        # device unsafe to reload until then; since C663 the device's own save is the whole
        # persistence); persisted opens the export; nothing else opens.
        expected = {cr.ROTATED_PERSISTED: "breakglass_export",
                    cr.ROTATED_PENDING_PERSIST: "persist",
                    cr.ROTATED_UNVERIFIED: "persist"}.get(state, "")
        assert nxt["open"] == expected, state
        assert nxt["args"] == {"list": "Lab", "devices": ["r2"]}
        assert result["happened"]["summary"] == cr.summarise(
            {"device": "r2", "state": state, "steps": []}, where="browser")
        # C371: a browser's result names the browser's export, never a terminal command.
        assert "nmas-breakglass" not in result["happened"]["summary"]

    def test_what_stays_true_follows_the_state_reached(self):
        """C373: one fixed sentence said the rotation row stays until a persist reads SAFE,
        beside a result whose own persistence had just read it SAFE."""
        from modules.preview_confirm import rotate_result

        def still(state):
            return rotate_result({"device": "r2", "state": state, "steps": []},
                                 _plan())["not_watched"]
        assert "reads SAFE now" in still(cr.ROTATED_PERSISTED)
        assert "stays until a persist reads SAFE" not in still(cr.ROTATED_PERSISTED)
        for state in (cr.ROTATED_PENDING_PERSIST, cr.ROTATED_UNVERIFIED):
            assert "stays until a persist reads SAFE" in still(state), state
        assert "unchanged" in still(cr.REVERTED)

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
            seen["other"] = identity.actor_verification("someone@example.com")
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
        """v2's device page's Actions menu (today's device page's Rotate credential… button
        until it left at 7.8, P7-22)."""
        menu = open(os.path.join(ROOT, "templates", "v2", "_actions_menu.html"),
                    encoding="utf-8").read()
        assert "('Rotate credential…', 'rotate', 'rotation')" in menu


def shown_strings_naming(text: str, phrase: str) -> list:
    """The string literals of *text* (Python, parsed, so comments are not read) that name
    *phrase*."""
    import ast
    return [n.value for n in ast.walk(ast.parse(text))
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and phrase in n.value]


class TestNoScreenNamesTheRemovedBootFileChain:
    """C760: the rotation preview's order note ended "then the boot-file chain", which C663
    removed; the persist is the device's save and its read-back. No string a module can show,
    and no v2 template, names it (comments about the removal may)."""

    def test_no_module_string_or_template_names_it(self):
        from tests.source_index import tracked
        found = [p for p in tracked("modules", "routes", suffix=".py")
                 if shown_strings_naming(open(p, encoding="utf-8").read(), "boot-file chain")]
        found += [p for p in tracked(os.path.join("templates", "v2"))
                  if "boot-file chain" in open(p, encoding="utf-8").read()]
        assert len(tracked("modules", "routes", suffix=".py")) > 100, "the scan's population"
        assert found == []

    def test_the_scan_finds_the_old_note_and_skips_a_comment(self):
        old = '"persist: save on the device and read the startup config back, then the boot-file chain"'
        assert shown_strings_naming(f"x = [{old}]\n", "boot-file chain")
        assert shown_strings_naming("# the boot-file chain went with C663\nx = 1\n",
                                    "boot-file chain") == []
