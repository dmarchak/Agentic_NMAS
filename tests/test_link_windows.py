"""C2751: the planned window of every link-affecting operation covers the far end of each link
it touches (the operator's rule of 2026-11-08: "a planned window for any link-affecting
operation must cover the far end's device and interface too"; C2749 built it for the port
bounce, the OSPF reset, the session clear and the probes).

What C2749's survey left: the Reload's window named its device and the devices it predicted
unreachable, never its neighbours' side of each link, and a deploy that shut or changed an
interface declared no window at all (its receipts explain its own device's drops only,
`attention.DEPLOY_WINDOW_S`). So a far end's logged drop, its port's transitions and
self-healing's planned-work guard (guard 3) read the operation's own effect as a fault.

The class is constrained by its shape, not by its members:

- every window a product module or host script declares names its far ends
  (`record_planned(..., far_ends=)`), an AST scan with a floor and a planted case;
- a restart's far ends are every link of each device restarted (`neighbours.restart_far_ends`),
  a port-scoped operation's those of its ports (`neighbours.window_far_ends`), both through
  `neighbours.far_ends`, the one way far ends are found;
- a deploy's ports are the confirmed program's interface sections (`expected_effects.touched`,
  derive's own section reading), and its window restarts nothing (``"restarts": false``): it
  explains the far ends only, its own device staying its receipts', unsilenced, a restart of
  it still unplanned.

IPv4 and IPv6 beside each other (a link is found on either family's network).
"""

import ast
import os
import threading
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Committed intent of three routers (made-up documentation addresses): core1's Gi2 faces
#: edge1's Gi1 and its Gi3 faces edge2's Gi1, each on an IPv4 /30 and an IPv6 /64; core1's
#: loopback is a /32 (no link).
LINKS = {
    "core1": {"interfaces": [
        {"name": "GigabitEthernet2", "ipv4": "192.0.2.1 255.255.255.252",
         "ipv6": ["2001:DB8:12::1/64", "FE80::1 link-local"]},
        {"name": "GigabitEthernet3", "ipv4": "192.0.2.5 255.255.255.252",
         "ipv6": ["2001:DB8:13::1/64"]},
        {"name": "Loopback0", "ipv4": "192.0.2.101 255.255.255.255"}]},
    "edge1": {"interfaces": [{"name": "GigabitEthernet1", "ipv4": "192.0.2.2 255.255.255.252",
                              "ipv6": ["2001:DB8:12::2/64"]}]},
    "edge2": {"interfaces": [{"name": "Gi1", "ipv4": "192.0.2.6 255.255.255.252",
                              "ipv6": ["2001:DB8:13::2/64"]}]},
}

IP = "192.0.2.50"
#: A program that shuts one interface and readdresses another (IPv6), and configures routing.
PROGRAM = ["interface GigabitEthernet2", " shutdown",
           "interface Gi3", " ipv6 address 2001:db8:13::1/64",
           "router ospf 1", " passive-interface default"]


def _only(family: str) -> dict:
    """LINKS with each interface's *family* address alone."""
    return {h: {"interfaces": [{k: v for k, v in i.items() if k in ("name", family)}
                               for i in hv["interfaces"]]} for h, hv in LINKS.items()}


@pytest.fixture
def store(tmp_path, monkeypatch):
    """This test's own planned-window store; Grafana never asked."""
    monkeypatch.setattr("modules.config.DATA_DIR", str(tmp_path))
    monkeypatch.setattr("modules.restarts._grafana",
                        lambda name: pytest.fail("a window that restarts nothing asked Grafana"))
    return tmp_path


# ── The shape: every window names its far ends ──────────────────────────────────────────────

def _sources():
    """Every product module and host script holding Python: modules/, routes/, app.py and
    each script under scripts/ whose first line names python."""
    from tests.source_index import tracked

    out = list(tracked("modules", "routes", "app.py", suffix=".py", root=ROOT))
    for path in tracked("scripts", recursive=False, root=ROOT):
        name = os.path.basename(path)
        if os.path.isfile(path):
            with open(path, encoding="utf-8", errors="replace") as fh:
                first = fh.readline()
            if name.endswith(".py") or (first.startswith("#!") and "python" in first):
                out.append(path)
    return out


def windows_without_far_ends(source: str, where: str) -> tuple:
    """``(calls, missing)``: each call of `record_planned` in *source* (parsed), and those that
    pass no ``far_ends``."""
    calls, missing = [], []
    for node in ast.walk(ast.parse(source, filename=where)):
        if not isinstance(node, ast.Call):
            continue
        name = (node.func.attr if isinstance(node.func, ast.Attribute) else
                node.func.id if isinstance(node.func, ast.Name) else "")
        if name != "record_planned":
            continue
        calls.append(f"{where}:{node.lineno}")
        if not any(k.arg == "far_ends" for k in node.keywords):
            missing.append(f"{where}:{node.lineno}")
    return calls, missing


class TestEveryWindowNamesItsFarEnds:
    def test_every_window_a_product_or_script_declares_names_them(self):
        calls, missing = [], []
        for path in _sources():
            with open(path, encoding="utf-8") as fh:
                got = windows_without_far_ends(fh.read(), os.path.relpath(path, ROOT))
            calls += got[0]
            missing += got[1]
        # The floor (2026-11-08): the bounce, the session clear, the Reload, the app deploy,
        # the deploy's links, the API, the host's planned-restart command and the tier2 probe.
        assert len(calls) >= 8, f"the scan found only {calls}"
        assert missing == [], ("each planned window states the far ends of the links its "
                               "operation takes down (C2751), [] when it has none: "
                               + ", ".join(missing))

    def test_the_scan_finds_a_window_that_names_none(self):
        planted = ("from modules import restarts\n"
                   "restarts.record_planned(['x'], 0, 1, 'a', 'b', 'c', list_name='n')\n"
                   "record_planned(['x'], 0, 1, 'a', 'b', 'c', far_ends=[])\n")
        calls, missing = windows_without_far_ends(planted, "planted.py")
        assert calls == ["planted.py:2", "planted.py:3"] and missing == ["planted.py:2"]


# ── The far ends: one way to find them ──────────────────────────────────────────────────────

class TestTheFarEnds:
    @pytest.mark.parametrize("family", ["ipv4", "ipv6"])
    def test_a_restart_takes_every_link_down(self, family):
        from modules.neighbours import window_far_ends
        assert window_far_ends(_only(family), ["core1"]) == [("edge1", "GigabitEthernet1"),
                                                             ("edge2", "Gi1")]
        assert window_far_ends(_only(family), ["edge2"]) == [("core1", "GigabitEthernet3")]

    @pytest.mark.parametrize("family", ["ipv4", "ipv6"])
    def test_named_ports_take_only_their_links_down(self, family):
        from modules.neighbours import window_far_ends
        assert window_far_ends(_only(family), ["core1"], ["Gi2"]) == [
            ("edge1", "GigabitEthernet1")]
        assert window_far_ends(_only(family), ["core1"], ["Loopback0"]) == [], "a /32"

    def test_a_far_end_the_window_names_itself_is_left_out(self):
        from modules.neighbours import window_far_ends
        assert window_far_ends(LINKS, ["core1", "edge1"]) == [("edge2", "Gi1")]
        assert window_far_ends(LINKS, ["*"]) == [], "the whole network has none outside it"

    @staticmethod
    def _network(tmp_path, monkeypatch, *, listed=True, repository=True):
        from modules.nsot import listref
        repo = tmp_path / "config_repo"
        if repository:
            (repo / ".git").mkdir(parents=True)
        monkeypatch.setattr(listref, "exists", lambda name: listed)
        monkeypatch.setattr(listref, "resolve",
                            lambda name: type("Ref", (), {"repo_dir": str(repo)})())

    def test_intent_that_cannot_be_read_names_no_far_end_and_says_why(self, tmp_path,
                                                                       monkeypatch):
        from modules import neighbours
        self._network(tmp_path, monkeypatch)
        monkeypatch.setattr(neighbours, "committed_intents_of",
                            lambda network: ({}, "host_vars/edge1.yml did not parse"))
        assert neighbours.restart_far_ends("Lab", ["core1"]) == (
            None, "host_vars/edge1.yml did not parse")
        assert neighbours.restart_far_ends("Lab", ["*"]) == ([], ""), "reads nothing"

    def test_intent_read_whole_names_the_restarts_far_ends(self, tmp_path, monkeypatch):
        from modules import neighbours
        self._network(tmp_path, monkeypatch)
        monkeypatch.setattr(neighbours, "committed_intents_of", lambda network: (LINKS, ""))
        assert neighbours.restart_far_ends("Lab", ["edge1"]) == (
            [("core1", "GigabitEthernet2")], "")

    @pytest.mark.parametrize("listed,repository", [(True, False), (False, False)])
    def test_a_network_with_no_repository_yet_has_none(self, tmp_path, monkeypatch, listed,
                                                       repository):
        from modules import neighbours
        self._network(tmp_path, monkeypatch, listed=listed, repository=repository)
        monkeypatch.setattr(neighbours, "committed_intents_of",
                            lambda network: pytest.fail("read a repository that is not there"))
        assert neighbours.restart_far_ends("Lab", ["core1"]) == ([], "")

    def test_each_acts_own_intent_read_is_none_when_intent_cannot_be_read(self, monkeypatch):
        # C2795: the bounce's and the session clear's acts read through the one reader, which
        # returns None on any error, so their windows refuse rather than name no far end.
        from modules import neighbours
        from modules.heal import bounce, session_clear
        monkeypatch.setattr(neighbours, "committed_intents_of",
                            lambda network: ({}, "host_vars/edge1.yml did not parse"))
        for sources in (bounce.Sources, session_clear.Sources):
            assert sources("Lab").intents() == (None, "host_vars/edge1.yml did not parse")
        monkeypatch.setattr(neighbours, "committed_intents_of", lambda network: (LINKS, ""))
        for sources in (bounce.Sources, session_clear.Sources):
            assert sources("Lab").intents() == (LINKS, "")


class TestTheDeploysPorts:
    def test_each_interface_section_with_a_line_and_each_removed_interface(self):
        from modules.nsot.expected_effects import touched
        program = PROGRAM + ["interface Loopback9", "!", "no interface Gi4.10",
                             "default interface GigabitEthernet5", "hostname edge9"]
        assert touched(program) == ["GigabitEthernet2", "GigabitEthernet3",
                                    "GigabitEthernet4.10", "GigabitEthernet5"]

    def test_a_program_touching_no_interface_touches_none(self):
        from modules.nsot.expected_effects import touched
        assert touched(["router ospf 1", " network 192.0.2.0 0.0.0.3 area 0",
                        "ipv6 route 2001:db8::/32 Null0"]) == []


# ── A window that restarts nothing ──────────────────────────────────────────────────────────

def _links_window(now: float) -> dict:
    from modules import restarts
    got = restarts.record_planned(["core1"], now, now + 600, "ana@example.invalid",
                                  "the deploy of core1: its program changes GigabitEthernet2",
                                  "deploy", list_name="Lab", interfaces=["GigabitEthernet2"],
                                  far_ends=[("edge1", "GigabitEthernet1")], restarts=False)
    assert got["ok"], got
    return got


class TestAWindowThatRestartsNothing:
    def test_it_explains_the_far_end_and_only_its_port(self, store):
        from modules import restarts
        from modules.heal.flaps import planned_spans
        now = time.time()
        got = _links_window(now)
        assert got["record"]["restarts"] is False
        assert got["silence"]["state"] == "not_restarting"
        assert got["silence_words"] == "no Grafana silence: the operation restarts no device"
        why = restarts.explained_by("edge1", "Lab", now + 10)
        assert why and why["how"] == "far_end", why
        assert why["words"].startswith("edge1 GigabitEthernet1 is the far end of core1 "
                                       "GigabitEthernet2, taken down on purpose (deploy"), why
        assert len(planned_spans("Lab", "edge1", "Gi1")) == 1

    def test_its_own_device_is_not_restarting(self, store):
        from modules import restarts
        now = time.time()
        _links_window(now)
        rows = restarts.planned_rows()
        assert restarts.holding("core1", "Lab", now + 10) is None
        assert restarts.explained_by("core1", "Lab", now + 10) is None, \
            "its own device is its receipts', as before"
        assert restarts.planned_for("core1", now + 10, rows, "Lab") is None, \
            "a restart of the device during the deploy is unplanned"

    def test_a_window_recorded_before_the_field_restarts_its_devices(self, store):
        from modules import restarts
        from modules.restarts import _append
        now = time.time()
        _append("planned_restarts.jsonl", {
            "devices": ["core1"], "list": "Lab", "from": restarts._iso(now),
            "until": restarts._iso(now + 600), "by": "ana@example.invalid", "why": "a reload",
            "via": "reload", "recorded_at": restarts._iso(now)})
        assert restarts.holding("core1", "Lab", now + 10) is not None

    def test_the_adjacency_log_reads_the_far_ends_drop_as_planned(self, store):
        from modules import attention as A
        from modules import restarts
        now = time.time()
        _links_window(now)
        rows = restarts.planned_rows()
        drop = {"epoch": now + 20, "at": restarts._iso(now + 20)}
        logged = {"device": "edge1", "list": "Lab", "neighbor": "192.0.2.1",
                  "protocol": "ospf"}
        got = A._drop_window(drop, logged, rows, {}, {})
        assert got and got[1] == "far_end", got
        assert A._explained(drop, logged, rows, lambda *a: [], {}, {}) == \
            "a planned operation on its link's far end"
        other = dict(logged, device="edge2")
        assert A._drop_window(drop, other, rows, {}, {}) is None
        assert A._explained(drop, other, rows, lambda *a: [], {}, {}) == ""

    def test_history_never_calls_it_a_restart(self, store):
        from modules import history_sources as H
        now = time.time()
        _links_window(now)
        ref = type("Ref", (), {"name": "Lab"})()
        got = H.restart_windows({"ref": ref, "limit": 10, "since": now - 60, "device": "",
                                 "members": None})
        (event,) = got["events"]
        assert event["what"].startswith("Planned window declared (links taken down, "
                                         "nothing restarted)"), event
        record = dict(event["record"])
        assert record["Far ends"] == "edge1 GigabitEthernet1"
        assert record["Interfaces"] == "GigabitEthernet2"


# ── The deploy: the window before the push ──────────────────────────────────────────────────

def _ctx(link_window):
    from modules.pipeline import PipelineContext
    ctx = PipelineContext(config_type="template", device_ips=[IP], params={}, ip_params_map={},
                          selected_devices=[{"ip": IP, "hostname": "core1"}],
                          connections_pool={}, pool_lock=threading.Lock(),
                          config_id="tpl-core1", list_name="Lab")
    ctx.confirmed_commands = {IP: list(PROGRAM)}
    ctx.link_window = {IP: link_window} if link_window is not None else None
    return ctx


LINK_WINDOW = {"device": "core1", "interfaces": ["GigabitEthernet2", "GigabitEthernet3"],
               "far_ends": [("edge1", "GigabitEthernet1"), ("edge2", "Gi1")],
               "by": "ana@example.invalid", "error": "",
               "why": "the deploy of core1: its program changes GigabitEthernet2, "
                      "GigabitEthernet3"}


@pytest.fixture
def runner(store, monkeypatch):
    """The real runner and its real `config_diff` (which declares the window last); every
    other stage stubbed, the push recording the windows recorded at that moment."""
    import modules.pipeline as P
    from modules import restarts
    pushed = []
    for name in P.STAGE_NAMES:
        if name == "config_diff":
            continue

        def stage(ctx, _n=name):
            if _n == "deploy":
                pushed.append([dict(w) for w in restarts.planned_rows()])
                ctx.push_results = {IP: {"ok": True, "output": ""}}
        monkeypatch.setattr(P, f"_stage_{name}", stage)
    monkeypatch.setattr(P, "_stage_rollback", lambda ctx: pytest.fail("rolled back"))
    return pushed


class TestTheDeploysWindow:
    def test_it_is_recorded_before_the_push_and_ends_with_the_run(self, runner):
        from modules import restarts
        from modules.pipeline import PipelineRunner
        ctx = PipelineRunner(_ctx(dict(LINK_WINDOW))).run()
        assert ctx.final_status == "success", ctx.error
        (at_push,) = runner
        (w,) = at_push
        assert w["devices"] == ["core1"] and w["restarts"] is False and w["via"] == "deploy"
        assert w["interfaces"] == ["GigabitEthernet2", "GigabitEthernet3"]
        assert restarts.far_ends_of(w) == [{"device": "edge1", "interface": "GigabitEthernet1"},
                                           {"device": "edge2", "interface": "Gi1"}]
        assert w["by"] == "ana@example.invalid"
        rec = ctx.link_window_record[IP]
        assert rec["declared"] is True and rec["ended"], rec
        assert restarts.window_id(w) in restarts.ends(), "ended as the run ended"
        assert "its far ends: edge1 GigabitEthernet1, edge2 Gi1" in rec["words"]

    def test_intent_that_cannot_be_read_stops_the_run_before_the_send(self, runner):
        from modules import restarts
        from modules.nsot import receipts
        from modules.pipeline import PipelineRunner
        lw = dict(LINK_WINDOW, far_ends=[], error="host_vars/edge1.yml did not parse")
        ctx = PipelineRunner(_ctx(lw)).run()
        assert runner == [], "nothing was pushed"
        assert ctx.final_status == "failed" and ctx.stages_failed == ["config_diff"]
        assert "committed intent could not be read (host_vars/edge1.yml did not parse)" \
            in ctx.error and "Nothing was sent." in ctx.error, ctx.error
        assert restarts.planned_rows() == []
        assert receipts.was_sent({"commands": PROGRAM, "outcome": "failed",
                                  "stage": ctx.stages_failed[-1]}) is False

    def test_a_window_that_cannot_be_recorded_stops_the_run_before_the_send(
            self, runner, monkeypatch):
        from modules import restarts
        from modules.pipeline import PipelineRunner
        monkeypatch.setattr(restarts, "record_planned", lambda *a, **k: {
            "ok": False, "error": "the restart record could not be read"})
        ctx = PipelineRunner(_ctx(dict(LINK_WINDOW))).run()
        assert runner == [] and ctx.stages_failed == ["config_diff"]
        assert "the window could not be recorded (the restart record could not be read)" \
            in ctx.error, ctx.error

    def test_no_far_end_in_intent_needs_no_window_and_says_so(self, runner):
        from modules import restarts
        from modules.pipeline import PipelineRunner
        ctx = PipelineRunner(_ctx(dict(LINK_WINDOW, far_ends=[]))).run()
        assert ctx.final_status == "success" and runner == [[]]
        assert ctx.link_window_record[IP]["declared"] is False
        assert ctx.link_window_record[IP]["words"] == (
            "no window: committed intent names no far end for core1 GigabitEthernet2, "
            "GigabitEthernet3")
        assert restarts.planned_rows() == []

    def test_a_program_touching_no_interface_declares_none(self, runner):
        from modules.pipeline import PipelineRunner
        ctx = PipelineRunner(_ctx({})).run()
        assert ctx.final_status == "success" and runner == [[]]
        assert ctx.link_window_record == {}


class TestTheDeployCarriesIt:
    def test_the_ports_far_ends_and_person_come_from_the_program_intent_and_hold(
            self, monkeypatch):
        from modules.pipeline import link_window
        monkeypatch.setattr("modules.nsot.device_ops.holder", lambda network, host: {
            "actor": "ana@example.invalid", "operation": "restore"})
        got = link_window("Lab", "core1", PROGRAM, (_only("ipv6"), ""))
        assert got == {"device": "core1", "interfaces": ["GigabitEthernet2", "GigabitEthernet3"],
                       "far_ends": [("edge1", "GigabitEthernet1"), ("edge2", "Gi1")],
                       "by": "ana@example.invalid", "error": "",
                       "why": "the restore of core1: its program changes GigabitEthernet2, "
                              "GigabitEthernet3"}

    def test_intent_that_cannot_be_read_is_carried_to_refuse(self, monkeypatch):
        from modules.pipeline import link_window
        monkeypatch.setattr("modules.nsot.device_ops.holder", lambda network, host: None)
        got = link_window("Lab", "core1", PROGRAM, ({}, "the committed intent could not be "
                                                        "listed (128)"))
        assert got["far_ends"] == [] and got["by"] == ""
        assert got["error"] == "the committed intent could not be listed (128)"
        assert link_window("Lab", "core1", ["router ospf 1"], (LINKS, "")) == {}

    def test_the_real_deploy_hands_the_pipeline_its_window(self, tmp_path, monkeypatch):
        """Through the real `_deploy_one` and runner (tests/test_attention_actions_follow_outcome's
        harness, its stages stubbed, in its own store): the run's context carries the
        program's ports and the person holding the device."""
        import modules.pipeline as P
        monkeypatch.setattr("modules.config.list_data_path",
                            lambda name: str(tmp_path / "lists" / name))
        monkeypatch.setattr("modules.config.DATA_DIR", str(tmp_path))
        from tests.test_attention_actions_follow_outcome import NO_STARTUP, _apply
        seen = []
        real = P._end_link_windows
        monkeypatch.setattr(P, "_end_link_windows",
                            lambda ctx, **k: (seen.append(ctx.link_window), real(ctx, **k)))
        _apply(monkeypatch, startup=NO_STARTUP)
        (carried,) = [c for c in seen if c]
        (lw,) = carried.values()
        assert lw["device"] == "s4" and lw["interfaces"], lw
        assert lw["by"], "the run's hold names its person"


# ── The other restarts: a person's window and the controller app deploy ─────────────────────

class _NoGrafana:
    def is_configured(self):
        return False


@pytest.fixture
def restarts_store(tmp_path, monkeypatch):
    """A window that restarts its devices, in this test's own store; Grafana not configured."""
    monkeypatch.setattr("modules.config.DATA_DIR", str(tmp_path))
    monkeypatch.setattr("modules.restarts._grafana", lambda name: _NoGrafana())
    return tmp_path


class TestTheOtherRestartsName:
    def test_a_persons_window_names_its_devices_far_ends(self, restarts_store, monkeypatch):
        from app import app
        from modules import neighbours
        monkeypatch.setattr(neighbours, "restart_far_ends", lambda network, devices: (
            neighbours.window_far_ends(LINKS, devices), ""))
        app.config["TESTING"] = True
        got = app.test_client().post("/restarts/planned", json={
            "list": "Default", "devices": ["edge2"], "minutes": 20, "why": "a line card swap"})
        assert got.status_code == 200, got.get_json()
        assert got.get_json()["record"]["expected"]["far_ends"] == [
            {"device": "core1", "interface": "GigabitEthernet3"}]

    def test_a_persons_window_with_intent_unread_is_refused_naming_why(
            self, restarts_store, monkeypatch):
        from app import app
        from modules import neighbours, restarts
        monkeypatch.setattr(neighbours, "restart_far_ends",
                            lambda network, devices: (None, "host_vars/core1.yml did not parse"))
        app.config["TESTING"] = True
        got = app.test_client().post("/restarts/planned", json={
            "list": "Default", "devices": ["edge2"], "minutes": 20, "why": "a line card swap"})
        assert got.status_code == 409
        assert got.get_json()["error"] == (
            "committed intent of Default could not be read (host_vars/core1.yml did not "
            "parse), so the far ends of edge2's links cannot be told: no window was recorded")
        assert restarts.planned_rows() == []

    def test_the_controller_app_deploys_window_names_the_switches_far_ends(
            self, restarts_store, monkeypatch):
        from modules import neighbours, restarts
        from modules.apps import deploy_op
        monkeypatch.setattr(neighbours, "restart_far_ends", lambda network, devices: (
            neighbours.window_far_ends(LINKS, devices), ""))
        into = {}
        now = time.time()
        got = deploy_op._declare("Lab", into)(["edge1"], now, now + 300, "ana@example.invalid",
                                              "controller app deploy 0123456789ab", [])
        assert got["ok"], got
        assert restarts.far_ends_of(into["window"]) == [
            {"device": "core1", "interface": "GigabitEthernet2"}]

    def test_the_controller_app_deploy_with_intent_unread_records_nothing(
            self, restarts_store, monkeypatch):
        from modules import neighbours, restarts
        from modules.apps import deploy_op
        monkeypatch.setattr(neighbours, "restart_far_ends",
                            lambda network, devices: (None, "no network is named 'Lab'"))
        now = time.time()
        got = deploy_op._declare("Lab", {})(["edge1"], now, now + 300, "ana@example.invalid",
                                            "controller app deploy 0123456789ab", [])
        assert got["ok"] is False and "no network is named 'Lab'" in got["error"]
        assert restarts.planned_rows() == []


# ── A far end that must not be disturbed (the operator, 2026-11-08, decision 6; C2805) ──────

@pytest.fixture
def netbox_lab(monkeypatch):
    """'Lab' as a NetBox-sourced network whose inventory (NetBox's shape, `_tags` the tags'
    slugs) holds core1, edge1 and edge2, edge2 tagged `mercury-hands-off`; the inventory is
    held in the returned dict, so a test can change it or make it unreadable."""
    from modules.inventory import source_config
    held = {"devices": [{"hostname": "core1", "ip": IP, "_tags": []},
                        {"hostname": "edge1", "ip": "192.0.2.51", "_tags": ["lab-a"]},
                        {"hostname": "edge2", "ip": "2001:db8:13::2",
                         "_tags": ["lab-a", "mercury-hands-off"]}]}
    monkeypatch.setattr(source_config, "load", lambda name: {
        "source": source_config.SOURCE_NETBOX if name == "Lab" else "local"})

    def devices(path):
        if held.get("error"):
            raise OSError(held["error"])
        return [dict(d) for d in held["devices"]]
    monkeypatch.setattr("modules.device.load_saved_devices", devices)
    return held


class TestAHandsOffFarEnd:
    def _record(self, far, devices=("core1",), **kw):
        from modules import restarts
        now = time.time()
        return restarts.record_planned(list(devices), now, now + 300, "ana@example.invalid",
                                       "a port bounce of core1 Gi3", "test", list_name="Lab",
                                       far_ends=far, restarts=False, **kw)

    def test_a_window_naming_a_tagged_far_end_is_refused_naming_it(self, store, netbox_lab):
        from modules import restarts
        got = self._record([("edge1", "GigabitEthernet1"), ("edge2", "Gi1")])
        assert got["ok"] is False
        assert got["error"] == (
            "this window names edge2 Gi1 as a far end, and it carries NetBox's tag "
            "mercury-hands-off on Lab, so no operation on another device may take its link "
            "down or reset its adjacency (the operator, 2026-11-08): nothing was sent")
        assert restarts.planned_rows() == []

    def test_untagged_far_ends_are_recorded(self, store, netbox_lab):
        got = self._record([("edge1", "GigabitEthernet1")])
        assert got["ok"], got

    def test_the_tagged_device_aimed_at_itself_is_its_persons_choice(self, store, netbox_lab):
        """Only a far end is refused: the device's own window (a Reload of it, the lab's
        redeploy) names it among its devices, never as a far end."""
        got = self._record([("core1", "GigabitEthernet3")], devices=("edge2",))
        assert got["ok"], got

    def test_a_far_end_not_in_the_inventory_is_refused(self, store, netbox_lab):
        from modules import restarts
        netbox_lab["devices"] = netbox_lab["devices"][:2]
        got = self._record([("edge2", "Gi1")])
        assert got["ok"] is False and got["error"].startswith(
            "this window names edge2 as a far end, and it is not in Lab's inventory as read "
            "now, so whether it carries NetBox's tag mercury-hands-off cannot be told")
        assert restarts.planned_rows() == []

    def test_an_inventory_that_cannot_be_read_refuses(self, store, netbox_lab):
        netbox_lab["error"] = "the cache is not filled yet"
        got = self._record([("edge1", "GigabitEthernet1")])
        assert got["ok"] is False and got["error"] == (
            "Lab's inventory could not be read (the cache is not filled yet), so whether a far "
            "end carries NetBox's tag mercury-hands-off cannot be told: nothing was sent")

    def test_a_correction_records_what_happened(self, store, netbox_lab):
        """A correction records a window that already ran: refusing it would lose the record
        of what was done, not stop anything."""
        got = self._record([("edge2", "Gi1")],
                           correction="recorded late after the probe already ran on core1")
        assert got["ok"], got

    def test_the_deploy_naming_it_stops_before_the_send(self, runner, netbox_lab):
        from modules import restarts
        from modules.pipeline import PipelineRunner
        ctx = PipelineRunner(_ctx(dict(LINK_WINDOW))).run()
        assert runner == [], "nothing was pushed"
        assert ctx.final_status == "failed" and ctx.stages_failed == ["config_diff"]
        assert ("the window could not be recorded (this window names edge2 Gi1 as a far end, "
                "and it carries NetBox's tag mercury-hands-off on Lab") in ctx.error, ctx.error
        assert restarts.planned_rows() == []
