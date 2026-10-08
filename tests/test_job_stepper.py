"""The stepper on every job-backed v2 card (C370; the operator's first real rotate on v2,
2026-10-03: only "The rotation runs as a job…" while it ran; NSOT_GUI_BRIEF 10a's stepper,
signed off 2026-10-02).

- The steps are the CODE's: every name `rotate_op.STEPS` groups is a step `credential_rotation`
  notes as it runs (`_rotate`'s and `_revert`'s `_step`, `_persist`'s `_stage`, `rotate_op.run`'s "persisting"),
  and every step those note is in a group or a named detour, read from the source by parsing.
- `device_ops.note` keeps the trail of steps with their times and announces
  `device_progress` when a device is held, and nothing when none is.
- `device_actions.stepper` turns a trail into done (with its time), running (since when, what it
  waits on, the last thing done) and waiting, including a detour and the end.
- Every job-backed card in the templates (a card that waits on a `*_job_card` route) is in
  `device_actions.JOB_STEPPERS`, declaring its steps or why it draws none, and a declared
  card's running state draws `job_stepper`; rotate's running card, through the real route
  with a real hold, draws the stepper with the current step, its waits and its time.
"""

import ast
import os
import re


from modules import device_actions as DA
from modules.nsot import credential_rotation as cr
from modules.nsot import device_ops
from modules.nsot import rotate_op as RO

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES = os.path.join(ROOT, "templates", "v2")


def _noted(path: str, functions: dict) -> set:
    """Every constant step name the named functions pass to their step recorder."""
    tree = ast.parse(open(path, encoding="utf-8").read())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in functions:
            recorder = functions[node.name]
            for call in ast.walk(node):
                if (isinstance(call, ast.Call) and isinstance(call.func, (ast.Name, ast.Attribute))
                        and getattr(call.func, "id", getattr(call.func, "attr", "")) == recorder
                        and call.args):
                    arg = call.args[0]
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        names.add(arg.value)
                    elif isinstance(arg, ast.Name) and arg.id == "VERIFY":
                        names.add(cr.VERIFY)
    return names


def _code_names() -> set:
    rotation = os.path.join(ROOT, "modules", "nsot", "credential_rotation.py")
    op = os.path.join(ROOT, "modules", "nsot", "rotate_op.py")
    return (_noted(rotation, {"_rotate": "_step", "_revert": "_step", "_persist": "_stage"})
            | _noted(op, {"run": "note"}))


class TestTheStepsAreTheCodes:
    def test_every_grouped_name_is_noted_by_the_code_and_every_noted_name_is_grouped(self):
        code = _code_names()
        assert len(code) >= 20, sorted(code)
        grouped = {n for s in RO.STEPS for n in s[3]} | set(RO.DETOURS)
        assert grouped - code == set(), "a step the code never notes"
        assert code - grouped == set(), "a step the code notes that the stepper cannot place"

    def test_the_operators_six_in_order(self):
        assert [s[0] for s in RO.STEPS] == ["read_account", "stage", "send", "fresh_login",
                                            "record", "persist"]
        assert all(len(s[2]) > 20 for s in RO.STEPS), "each says what it waits on"
        assert set(RO.DETOURS.values()) <= {s[0] for s in RO.STEPS}


class TestTheTrailAndItsAnnouncement:
    def test_a_held_device_keeps_the_trail_and_announces_each_step(self, monkeypatch):
        from modules import invalidation
        said = []
        monkeypatch.setattr(invalidation, "announce", lambda keys, who, ok: said.append(
            (tuple(keys), who)))
        device_ops.acquire("Lab", "r2", "rotate", "person@example.invalid")
        try:
            device_ops.note("preflight")
            device_ops.note("confirmation")
            trail = device_ops.holder("Lab", "r2")["progress"]["trail"]
        finally:
            device_ops.release("Lab", "r2")
        assert [t[0] for t in trail] == ["started", "preflight", "confirmation"]
        assert trail[0][1] <= trail[1][1] <= trail[2][1]
        assert said.count((("device_progress",), "device-ops")) == 2

    def test_nothing_held_announces_nothing(self, monkeypatch):
        from modules import invalidation
        said = []
        monkeypatch.setattr(invalidation, "announce", lambda *a: said.append(a))
        device_ops.note("preflight")
        assert said == []


def _trail(*steps, t0=1000.0):
    return {"trail": [["started", t0]] + [[n, t] for n, t in steps]}


class TestTheStepper:
    def test_nothing_noted_yet_runs_the_first_step(self):
        rows = DA.stepper(RO.STEPS, _trail(), now=1003.0)
        assert [r["state"] for r in rows] == ["running"] + ["waiting"] * 5
        assert rows[0]["took_s"] == 3 and "account line" in rows[0]["waits"]

    def test_mid_send_the_two_before_are_done_with_their_times(self):
        rows = DA.stepper(RO.STEPS, _trail(("preflight", 1002), ("confirmation", 1004),
                                           ("generate", 1005), ("stage", 1005.5),
                                           ("invalidate_redaction_cache", 1006),
                                           ("original_session", 1010)), now=1012.0)
        assert [r["state"] for r in rows] == ["done", "done", "running", "waiting",
                                              "waiting", "waiting"]
        assert [rows[0]["took_s"], rows[1]["took_s"]] == [4, 2]
        assert rows[2]["took_s"] == 6 and rows[2]["last"] == "original_session"
        assert rows[2]["since"] == "1970-01-01T00:16:46Z"

    def test_the_persist_chain_names_its_stage(self):
        rows = DA.stepper(RO.STEPS, _trail(("commit", 1030), ("persisting", 1031),
                                           ("device_startup_config", 1040)), now=1050.0)
        assert rows[5]["state"] == "running" and rows[5]["last"] == "device_startup_config"
        assert [r["state"] for r in rows[:5]] == ["done"] * 5

    def test_a_revert_is_drawn_on_the_fresh_login(self):
        rows = DA.stepper(RO.STEPS, _trail(("push", 1010), (cr.VERIFY, 1020),
                                           ("revert", 1025)), detours=RO.DETOURS, now=1026.0)
        assert rows[3]["state"] == "running" and rows[3]["last"] == "revert"

    def test_the_deploy_steps_are_the_pipelines_stages_noted_as_they_start(self):
        from modules import pipeline
        assert [s[0] for s in pipeline.STEPS] == pipeline.STAGE_NAMES
        assert all(len(s[1]) >= 4 and all(len(w) > 15 for w in (
            s[2].values() if isinstance(s[2], dict) else [s[2]])) for s in pipeline.STEPS)
        assert DA.JOB_STEPPERS["deploy"][3] == "starts"
        rows = DA.stepper(pipeline.STEPS, _trail(("netbox_query", 1001), ("template_render", 1002),
                                                 ("ci_gate", 1003), ("pre_snapshot", 1004),
                                                 ("config_diff", 1009), ("deploy", 1010),
                                                 ("post_snapshot", 1014), ("verify", 1020)),
                          now=1050.0, starts=True)
        # Verify running; save_startup (C501), save_golden and audit_log waiting.
        assert [r["state"] for r in rows] == ["done"] * 7 + ["running"] + ["waiting"] * 3
        assert rows[7]["took_s"] == 30 and "settle window" in rows[7]["waits"]
        assert rows[3]["took_s"] == 5, "read before ran from its start to the compare's"

    def test_a_quick_verify_says_it_reads_back_never_settle_windows(self):
        """The operator, 2026-10-08: the words match the verify chosen. A program of management
        lines only is QUICK, noted `verify_quick` by the pipeline (one classifier,
        `verify_scope.classify`), and the running step says what it does."""
        from modules import pipeline
        rows = DA.stepper(pipeline.STEPS, _trail(("netbox_query", 1001), ("template_render", 1002),
                                                 ("ci_gate", 1003), ("pre_snapshot", 1004),
                                                 ("config_diff", 1009), ("deploy", 1010),
                                                 ("post_snapshot", 1014), ("verify_quick", 1020)),
                          now=1050.0, starts=True)
        assert rows[7]["state"] == "running" and rows[7]["key"] == "verify"
        assert "read back" in rows[7]["waits"] and "settle window is waited" in rows[7]["waits"]
        assert "BGP" not in rows[7]["waits"]

    def test_the_pipeline_notes_the_verify_its_programs_get(self):
        from types import SimpleNamespace as NS

        from modules import pipeline
        quick = NS(rendered_commands={"192.0.2.12": ["ip ssh source-interface Loopback0",
                                                     "ip tftp source-interface Loopback0"]})
        full = NS(rendered_commands={"192.0.2.12": ["router ospf 1", " network 192.0.2.0 0.0.0.255 area 0"]})
        assert pipeline._verify_note(quick) == "verify_quick"
        assert pipeline._verify_note(full) == "verify"
        assert "read back" in pipeline.stage_doing("verify_quick")
        assert "settle window" in pipeline.stage_doing("verify")

    def test_the_last_stage_done_leaves_nothing_running(self):
        rows = DA.stepper(RO.STEPS, _trail(("commit", 1030), ("startup_safe", 1080)),
                          now=1081.0)
        assert [r["state"] for r in rows] == ["done"] * 6


def _job_cards() -> dict:
    """{op: template text} for every card waiting on a `<op>_job_card` route."""
    out = {}
    for name in os.listdir(TEMPLATES):
        text = open(os.path.join(TEMPLATES, name), encoding="utf-8").read()
        for op in re.findall(r"url_for\('device_v2\.(\w+)_job_card'", text):
            out[op] = text
    return out


class TestEveryJobCard:
    def test_every_job_card_declares_its_steps_or_why_it_draws_none(self):
        cards = _job_cards()
        assert {"capture", "rotate"} <= set(cards), sorted(cards)
        assert set(cards) == set(DA.JOB_STEPPERS)
        for op, ref in DA.JOB_STEPPERS.items():
            if isinstance(ref, str):
                assert len(ref.split()) >= 8, (op, "a reason, said")
                continue
            import importlib
            mod = importlib.import_module(ref[0])
            assert getattr(mod, ref[1]), op
            assert "job_stepper(" in cards[op], f"{op}'s running card draws no stepper"

    def test_rotates_running_card_draws_the_stepper_from_the_hold(self, rot, monkeypatch):  # noqa: F811
        from modules.nsot import capture_job
        monkeypatch.setattr(capture_job, "get", lambda job: {"state": "running", "elapsed_s": 4})
        device_ops.acquire("Lab", "r2", "rotate", "person@example.invalid")
        try:
            for n in ("preflight", "confirmation", "generate", "stage",
                      "invalidate_redaction_cache", "original_session"):
                device_ops.note(n)
            html = rot["client"].get("/v2/device/r2/rotate/job/x").get_data(as_text=True)
        finally:
            device_ops.release("Lab", "r2")
        assert "data-stepper" in html
        current = re.search(r'<li class="step step-current" data-step="(\w+)" '
                            r'aria-current="step">(.*?)</li>', html, re.S)
        assert current and current.group(1) == "send"
        assert "waits on a held session to the device" in current.group(2)
        assert "last done: original_session" in current.group(2)
        assert 'data-age="' in current.group(2), "its time, kept current by the page"
        assert html.count("step step-done") == 2
        assert 'nmas:device_progress from:body' in html



from tests.test_device_rotate_v2 import rot  # noqa: E402,F401 (the fixture, and its lab)
from tests.test_persist_screen import lab  # noqa: E402,F401
