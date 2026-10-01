"""Every command is read once, never re-sent on its session, and refused when
its reply cannot be trusted; verify says so rather than passing or failing on
stitched text (C272, the operator, 2026-10-01).

C271 fixed the configuration read: r2's capture was two configs stitched by a
timing re-send on the same session. The same fallback stood in front of every
other `show`: a 10 s prompt probe, then `send_command_timing` on the session
still carrying the first command's output. Verify's own reads (`show ip ospf
neighbor`, `show bgp all summary`, `show interfaces`) took it, right after a
push and a save, when the deploy's session read its prompt as `^@` (the host's
log, 2026-09-30 23:54 and 2026-10-01 01:14). And each routing read's failure
was `except: pass`, so a protocol whose read could not be trusted read before
the push as "not running" (never checked) and after it as gone.

Everything here runs the REAL `run_device_command` against a session that
answers from r3's real captures (`tests/fixtures/operational/`).
"""
import os
import re
import threading

import pytest

from modules import config_read, pipeline

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tests", "fixtures", "operational")


def capture(host, command):
    slug = re.sub(r"[^a-z0-9]+", "_", command.lower()).strip("_")
    path = os.path.join(FIX, f"{host}__{slug}.txt")
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def stitched(host, command):
    """The C271 shape for a show command: its output, the prompt and the
    echoed command, then the output again."""
    text = capture(host, command).rstrip("\n") + "\n"     # a device ends a reply with one
    return text + f"{host}#{command}\n" + text


class Device:
    """A Netmiko session answering from a host's real captures. *answers*
    overrides a command (text, or an exception raised). A timing read is
    never expected: nothing re-sends."""

    def __init__(self, host="r3", answers=None, prompt=None, reread_prompt=None):
        self.host, self.answers, self.sent = host, dict(answers or {}), []
        self.base_prompt = host if prompt is None else prompt
        self.reread_prompt = reread_prompt
        self.disconnected = False

    def send_command(self, command, **_kw):
        self.sent.append(command)
        got = self.answers.get(command, capture(self.host, command))
        if isinstance(got, Exception):
            raise got
        return got

    def send_command_timing(self, command, **_kw):
        raise AssertionError(f"re-sent {command!r} as a timing read")

    def set_base_prompt(self):
        self.sent.append("<set_base_prompt>")
        self.base_prompt = self.reread_prompt if self.reread_prompt is not None \
            else self.host
        return self.base_prompt

    def disconnect(self):
        self.disconnected = True

    def is_alive(self):
        return True


TIMEOUT = TimeoutError("Pattern not detected: 'r3\\#' in output.")


class TestOneReadNeverResent:
    def test_a_show_that_times_out_is_sent_once_and_its_session_never_read_again(self):
        from modules.commands import run_device_command
        s = Device(answers={"show ip ospf neighbor": TIMEOUT})
        with pytest.raises(TimeoutError):
            run_device_command(s, "show ip ospf neighbor")
        assert s.sent == ["show ip ospf neighbor"]
        assert "show ip ospf neighbor" in config_read.spent(s)
        with pytest.raises(config_read.UnreliableRead, match="not read again"):
            run_device_command(s, "show ip route summary")
        assert s.sent == ["show ip ospf neighbor"], "nothing more was sent"

    def test_a_stitched_reply_is_refused_naming_the_echo(self):
        from modules.commands import run_device_command
        s = Device(answers={"show ip ospf neighbor": stitched("r3", "show ip ospf neighbor")})
        with pytest.raises(config_read.UnreliableRead) as exc:
            run_device_command(s, "show ip ospf neighbor")
        assert config_read.UNRELIABLE in str(exc.value)
        assert "echoed command" in str(exc.value) and "'r3#show ip ospf neighbor'" in str(exc.value)
        assert config_read.spent(s)

    def test_a_reply_holding_the_sessions_own_prompt_is_refused(self):
        from modules.commands import run_device_command
        text = capture("r3", "show ip ospf neighbor").rstrip("\n") + "\n"
        s = Device(answers={"show ip ospf neighbor": text + "r3#\n" + text})
        with pytest.raises(config_read.UnreliableRead, match="session's own prompt"):
            run_device_command(s, "show ip ospf neighbor")

    def test_a_nul_prompt_is_read_again_before_anything_is_sent(self):
        """The host's case: after a push the prompt read as `^@`."""
        from modules.commands import run_device_command
        s = Device(prompt="\x00")
        out = run_device_command(s, "show ip ospf neighbor")
        assert s.sent == ["<set_base_prompt>", "show ip ospf neighbor"]
        assert out.strip() == capture("r3", "show ip ospf neighbor").strip()

    def test_a_prompt_still_unusable_is_refused_with_nothing_sent(self):
        from modules.commands import run_device_command
        s = Device(prompt="\x00", reread_prompt="\x00")
        with pytest.raises(config_read.UnreliableRead, match="even after reading it again"):
            run_device_command(s, "show ip ospf neighbor")
        assert s.sent == ["<set_base_prompt>"]

    def test_every_real_capture_passes_the_shape_check(self):
        """The control: no real reply is refused (floor: the fixtures)."""
        names = [n for n in os.listdir(FIX) if n.endswith(".txt") and "__" in n]
        assert len(names) >= 30
        for n in names:
            host = n.split("__")[0]
            with open(os.path.join(FIX, n), encoding="utf-8") as fh:
                assert config_read.output_problems(fh.read(), host) == [], n


class TestTheRoutingReaderSaysWhatItCouldNotRead:
    def test_r3_reads_clean(self):
        nbr = pipeline._detect_routing_neighbors(Device())
        assert nbr["unreadable"] == {}
        assert pipeline._protocol_counts(nbr) == {"bgp": 2, "ospf": 6, "ospfv3": 4}

    def test_an_untrustworthy_read_is_named_never_a_missing_protocol(self):
        s = Device(answers={"show ip ospf neighbor": stitched("r3", "show ip ospf neighbor")})
        nbr = pipeline._detect_routing_neighbors(s)
        assert "ospf" not in pipeline._protocol_counts(nbr)
        assert "UnreliableRead" in nbr["unreadable"]["show ip ospf neighbor"]
        assert "echoed command" in pipeline._unread_protocol(nbr, "ospf")

    def test_given_the_pool_each_later_read_gets_a_new_session(self):
        """One spent session does not make every later read refuse: the pool
        is asked at each read, and replaces a spent session."""
        bad = Device(answers={"show ip ospf neighbor": TIMEOUT})
        fresh = Device()
        sessions = iter([bad, bad, fresh, fresh, fresh, fresh, fresh])

        def pool():
            s = next(sessions)
            return fresh if config_read.spent(s) else s
        nbr = pipeline._detect_routing_neighbors(pool)
        assert list(nbr["unreadable"]) == ["show ip ospf neighbor"], nbr["unreadable"]
        assert "ospfv3" in pipeline._protocol_counts(nbr)

    def test_the_command_map_is_the_readers_commands(self):
        import inspect
        src = inspect.getsource(pipeline._read_routing_protocols)
        sent = set(re.findall(r'run_device_command\(_conn_of\(conn\), "([^"]+)"\)', src))
        assert sent == set(pipeline._ROUTING_READS.values()) and len(sent) == 7


def _ctx(monkeypatch, settle):
    """A one-device verify context; the settle window's re-read answers with
    *settle* (a Device)."""
    from modules.pipeline import PipelineContext
    ctx = PipelineContext(config_type="interface", device_ips=["x"], params={},
                          ip_params_map={}, selected_devices=[{"ip": "x", "hostname": "r3"}],
                          connections_pool={}, pool_lock=threading.Lock(), config_id="t",
                          settle_sleep=lambda _s: None, settle_clock=lambda: 0.0)
    held = [settle]

    def pool(*_a, **_k):                  # the real pool replaces a spent session
        if config_read.spent(held[0]):
            held[0] = Device(answers=settle.answers)
        return held[0]
    monkeypatch.setattr("modules.connection.get_persistent_connection", pool)
    return ctx


class TestVerifyNeitherPassesNorFailsOnWhatItCouldNotRead:
    def _snaps(self, post_device):
        """The post snapshot as the pipeline takes it: through the pool, which
        replaces a spent session with a new one (answering the same way)."""
        held = [post_device]

        def pool():
            if config_read.spent(held[0]):
                held[0] = Device(answers=post_device.answers)
            return held[0]
        pre = pipeline._capture_operational_snapshot(Device(), "x", "r3")
        post = pipeline._capture_operational_snapshot(pool, "x", "r3")
        return pre, post

    def test_unreadable_after_and_again_in_the_window_is_said_not_rolled_back(self, monkeypatch):
        st = stitched("r3", "show ip ospf neighbor")
        pre, post = self._snaps(Device(answers={"show ip ospf neighbor": st}))
        ctx = _ctx(monkeypatch, Device(answers={"show ip ospf neighbor": st}))
        ctx.pre_snapshots, ctx.post_snapshots = {"x": pre}, {"x": post}
        pipeline._stage_verify(ctx)                 # raises nothing: no rollback
        v = ctx.verify_result["x"]
        assert v["ok"] is False and v["issues"] == [], v["issues"]
        assert len(v["unreadable"]) == 1 and v["unreadable"][0].startswith("ospf: ")
        assert "echoed command" in v["unreadable"][0]

    def test_a_new_session_that_reads_cleanly_passes(self, monkeypatch):
        st = stitched("r3", "show ip ospf neighbor")
        pre, post = self._snaps(Device(answers={"show ip ospf neighbor": st}))
        ctx = _ctx(monkeypatch, Device())
        ctx.pre_snapshots, ctx.post_snapshots = {"x": pre}, {"x": post}
        pipeline._stage_verify(ctx)
        v = ctx.verify_result["x"]
        assert v["ok"] is True and v["unreadable"] == [], v

    def test_the_control_a_real_loss_still_fails(self, monkeypatch):
        """A clean read with three adjacencies gone fails and rolls back."""
        rows = capture("r3", "show ip ospf neighbor").splitlines()
        lost = "\n".join(rows[:-3])
        pre, post = self._snaps(Device(answers={"show ip ospf neighbor": lost}))
        ctx = _ctx(monkeypatch, Device(answers={"show ip ospf neighbor": lost}))
        ctx.pre_snapshots, ctx.post_snapshots = {"x": pre}, {"x": post}
        with pytest.raises(pipeline.PipelineStageError, match="ospf neighbors dropped"):
            pipeline._stage_verify(ctx)
        assert ctx.verify_result["x"]["unreadable"] == []

    def test_interfaces_unreadable_after_is_said(self, monkeypatch):
        cmd = pipeline._INTERFACES_READ
        pre, post = self._snaps(Device(answers={cmd: TIMEOUT}))
        ctx = _ctx(monkeypatch, Device())
        ctx.pre_snapshots, ctx.post_snapshots = {"x": pre}, {"x": post}
        pipeline._stage_verify(ctx)
        v = ctx.verify_result["x"]
        assert v["ok"] is False and any(u.startswith("interfaces: ") for u in v["unreadable"])

    def test_the_receipt_and_the_shipped_result_say_it(self, monkeypatch):
        import json

        import dukpy

        from modules.nsot import receipts

        st = stitched("r3", "show ip ospf neighbor")
        pre, post = self._snaps(Device(answers={"show ip ospf neighbor": st}))
        ctx = _ctx(monkeypatch, Device(answers={"show ip ospf neighbor": st}))
        ctx.pre_snapshots, ctx.post_snapshots = {"x": pre}, {"x": post}
        pipeline._stage_verify(ctx)
        checks = receipts._checks({"outcome": "deployed", "commands": ["x"],
                                   "verify": ctx.verify_result["x"]})
        assert checks["unreadable"] == ctx.verify_result["x"]["unreadable"]
        src = open(os.path.join(ROOT, "static", "js", "nmas_preview_confirm.js")).read()
        result = {"parts": ["happened", "did_not", "sent", "checks", "record", "not_watched"],
                  "action": "deploy", "level": "partial",
                  "happened": {"summary": "s", "targets": []}, "did_not": {"none": "n"},
                  "targets": [{"name": "r3", "sent": {"lines": [], "none": "x"},
                               "checks": checks}],
                  "record": {"statement": ""}, "not_watched": ""}
        html = dukpy.evaljs("var window = {};\n" + src
                            + f"\nwindow.previewConfirmResultHtml({json.dumps(result)}, {{}});")
        assert "data-pr-unreadable" in html and "could not be read reliably" in html
        assert "nothing was rolled back" in html


class TestTheDeployRefusesBeforeThePush:
    def _run(self, monkeypatch, device):
        from modules.pipeline import PipelineContext
        ctx = PipelineContext(config_type="interface", device_ips=["x"], params={},
                              ip_params_map={}, selected_devices=[{"ip": "x", "hostname": "r3"}],
                              connections_pool={}, pool_lock=threading.Lock(), config_id="t")
        monkeypatch.setattr("modules.connection.get_persistent_connection",
                            lambda *a, **k: device)
        monkeypatch.setattr("modules.ai_assistant._get_running_config_for_golden",
                            lambda *a, **k: capture("r3", "show ip ospf neighbor") and "cfg")
        monkeypatch.setattr("modules.ai_assistant._save_pre_change_file", lambda *a, **k: None)
        pipeline._stage_pre_snapshot(ctx)
        return ctx

    def test_an_untrustworthy_baseline_read_sends_nothing(self, monkeypatch):
        st = stitched("r3", "show ip ospf neighbor")
        with pytest.raises(pipeline.PipelineStageError) as exc:
            self._run(monkeypatch, Device(answers={"show ip ospf neighbor": st}))
        assert "could not be read reliably before the change, so nothing was sent" \
            in str(exc.value)
        assert "show ip ospf neighbor" in str(exc.value)

    def test_the_control_a_clean_baseline_proceeds(self, monkeypatch):
        ctx = self._run(monkeypatch, Device())
        assert pipeline._protocol_counts(ctx.pre_snapshots["x"]["routing_neighbors"]) == \
            {"bgp": 2, "ospf": 6, "ospfv3": 4}


class TestPostPushReadsUseANewSession:
    def test_the_pushs_session_is_closed_before_the_post_snapshot(self, monkeypatch):
        from modules.pipeline import PipelineContext
        push_session = Device(prompt="\x00", reread_prompt="\x00")
        ctx = PipelineContext(config_type="interface", device_ips=["x"], params={},
                              ip_params_map={}, selected_devices=[{"ip": "x", "hostname": "r3"}],
                              connections_pool={"x": push_session},
                              pool_lock=threading.Lock(), config_id="t")
        fresh = Device()
        monkeypatch.setattr("modules.connection.get_persistent_connection",
                            lambda dev, pool, lock: pool.setdefault("x", fresh))
        pipeline._stage_post_snapshot(ctx)
        assert push_session.disconnected and push_session.sent == []
        assert pipeline._unreadable(ctx.post_snapshots["x"]) == []

    def test_the_pool_replaces_a_spent_session(self, monkeypatch):
        from modules import connection
        spent, fresh = Device(), Device()
        config_read.spend(spent, "a test")
        pool = {"x": spent}
        monkeypatch.setattr(connection, "open_ssh", lambda *a, **k: fresh)
        monkeypatch.setattr(connection, "stored_connection_params", lambda dev: {})
        fresh.enable = lambda: None
        got = connection.get_persistent_connection({"ip": "x"}, pool, threading.Lock())
        assert spent.disconnected
        assert object.__getattribute__(got, "_conn") is fresh
