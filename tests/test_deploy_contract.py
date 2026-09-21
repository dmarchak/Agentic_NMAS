"""The Phase 3c deploy contract.

Phase 3b promised three things at the boundary where a socket is about to open.
These tests are where those promises are kept:

1. Re-render from the template with **real** secrets in memory.
2. ``assert_no_mask()`` **before** the socket, not after.
3. Refuse any artifact whose ``deployable`` is False.

Plus the one that makes them enforceable: ``intended/`` is written masked, so it
is never a deploy source, and nothing on this path may read it.

No test here opens a socket.
"""

import inspect
import os

import pytest

from modules.nsot import deploy
from modules.nsot.deploy import DeployRefused, assert_deployable, prepare_device
from modules.nsot.parsers import get_parser
from modules.nsot.render_artifact import (
    MASK, MaskedContentError, build_artifact, contains_mask,
)

FLEET = os.path.join(os.path.dirname(__file__), "fixtures", "configs", "fleet")


def _config(name):
    with open(os.path.join(FLEET, f"{name}.cfg"), encoding="utf-8") as fh:
        return fh.read()


UNKNOWN = "quantum-tunnel profile ALPHA\n peer 203.0.113.9\n"


@pytest.fixture
def deployable():
    return build_artifact("s1", _config("s1"), "cisco_ios", template_approved=True)


@pytest.fixture
def blocked():
    return build_artifact("s1", _config("s1") + UNKNOWN, "cisco_ios",
                          template_approved=True)


class TestRefusalBeforeAnySocket:
    def test_non_deployable_is_refused(self, blocked):
        with pytest.raises(DeployRefused) as exc:
            assert_deployable(blocked)
        assert "quantum-tunnel" in str(exc.value)

    def test_prepare_refuses_before_rendering(self, blocked, monkeypatch):
        """Refusal must precede the render, not follow it."""
        rendered = []
        monkeypatch.setattr(deploy, "render_for_deploy",
                            lambda *a, **k: rendered.append(1) or "x")
        with pytest.raises(DeployRefused):
            prepare_device(blocked)
        assert rendered == [], "the artifact was rendered before being refused"

    def test_unapproved_template_is_refused(self):
        artifact = build_artifact("s1", _config("s1"), "cisco_ios")
        with pytest.raises(DeployRefused) as exc:
            assert_deployable(artifact)
        assert "not approved" in str(exc.value)

    def test_deployable_artifact_prepares(self, deployable):
        result = prepare_device(deployable)
        assert result["device"] == "s1"
        assert "hostname s1" in result["config"]


class TestRealSecretsNotMasks:
    def test_deploy_render_carries_the_real_secret(self, deployable):
        result = prepare_device(deployable)
        for value in (deployable.host_vars.get("secrets") or {}).values():
            assert value in result["config"], \
                "a secret was not resolved for deploy"

    def test_deploy_render_contains_no_mask(self, deployable):
        assert not contains_mask(prepare_device(deployable)["config"])

    def test_preview_and_deploy_renders_differ(self, deployable):
        """The preview is masked; the deploy render is not. Same template."""
        assert contains_mask(deployable.rendered_masked)
        assert not contains_mask(prepare_device(deployable)["config"])

    def test_mask_check_runs_before_returning(self, deployable, monkeypatch):
        """A render that somehow contains a mask must never be handed back."""
        monkeypatch.setattr(deploy, "render_for_deploy",
                            lambda *a, **k: f"hostname s1\nsnmp-server community {MASK} RO\n")
        with pytest.raises(MaskedContentError):
            prepare_device(deployable)

    def test_hashed_secret_is_emitted_verbatim(self, deployable):
        config = prepare_device(deployable)["config"]
        stored = deployable.host_vars["secrets"]["user_admin_secret"]
        assert stored.startswith("5 $1$")
        assert stored in config, "the hash was not emitted verbatim"


class TestIntendedIsNeverADeploySource:
    def test_deploy_module_performs_no_file_reads(self):
        """Checked against the parsed code, not the prose.

        The docstrings talk about "the intended config" constantly, so grepping
        the source text proves nothing. Walking the AST for actual calls does.
        """
        import ast

        tree = ast.parse(inspect.getsource(deploy))
        reads = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                name = getattr(func, "id", None) or getattr(func, "attr", None)
                if name in ("open", "read_text", "read_bytes", "loadtxt"):
                    reads.append(name)
        assert reads == [], f"the deploy module reads from disk: {reads}"

    def test_no_intended_path_is_constructed(self):
        """No string literal in the module names the masked artifact directory."""
        import ast

        tree = ast.parse(inspect.getsource(deploy))

        # Docstrings are Constants too, and these docstrings discuss
        # ``intended/`` at length. Collect and exclude them so the test looks at
        # code rather than at its own explanation.
        docstrings = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                 ast.AsyncFunctionDef)):
                doc = ast.get_docstring(node, clean=False)
                if doc:
                    docstrings.add(doc)

        offenders = [
            n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and n.value not in docstrings
            and "intended" in n.value.lower()
            and ("/" in n.value or n.value.endswith(".cfg"))
        ]
        assert offenders == [], f"a path into intended/ was constructed: {offenders}"

    def test_prepare_takes_host_vars_not_a_path(self):
        params = inspect.signature(prepare_device).parameters
        assert "artifact" in params
        assert not any("path" in p or "file" in p for p in params)

    def test_render_for_deploy_takes_host_vars(self):
        params = inspect.signature(deploy.render_for_deploy).parameters
        assert "host_vars" in params


class TestOrderOfOperations:
    def test_contract_order_is_refuse_render_check(self):
        """The order is asserted because getting it wrong is silent.

        A masked push that fails halfway is worse than one that never starts.
        """
        source = inspect.getsource(prepare_device)
        refuse = source.index("assert_deployable")
        render = source.index("render_for_deploy")
        check = source.index("assert_no_mask")
        assert refuse < render < check, \
            "prepare_device must refuse, then render, then mask-check"


def _repo_with_templates(tmp_path, devices=("s1", "s2")):
    """A repo with a seeded template library and *devices* in the manifest."""
    from modules.nsot import manifest, templates_repo

    repo = str(tmp_path / "config_repo")
    os.makedirs(repo, exist_ok=True)
    templates_repo.seed_templates(repo)
    for index, name in enumerate(devices, start=1):
        manifest.upsert_device(repo, f"uid:{name}", name,
                               f"203.0.113.{20 + index}", platform="cisco_ios")
    return repo


class TestApprovalCoversTheDeviceSetNotItsConfig:
    """Approval claims "validated against this device set" and nothing more.

    Scheme 1 also hashed each bound device's parsed host_vars, which keyed the
    gate on the *result of the work*: deploying to one device changed its
    captured config, moved its hash, and revoked approval for every device
    bound to that template — including three that had received nothing. The
    rule in NSOT_PLAN.md, broken in its own implementation.

    Whether the template still reproduces a device *now* is ``template_report``,
    computed live on every plan, per device, gating there with the lines named.
    """

    def test_a_devices_config_changing_does_not_move_the_fingerprint(self, tmp_path):
        from modules.nsot import approval

        repo = _repo_with_templates(tmp_path, devices=("s1", "s2"))
        before = approval.binding_fingerprint(repo, "cisco_ios/base.j2")
        after = approval.binding_fingerprint(
            repo, "cisco_ios/base.j2",
            {"s1": {"hostname": "s1", "changed": True}})
        assert before["fingerprint"] == after["fingerprint"]

    def test_host_vars_are_accepted_and_ignored(self, tmp_path):
        """Callers that still have them need not change."""
        from modules.nsot import approval

        repo = _repo_with_templates(tmp_path, devices=("s1", "s2"))
        assert (approval.binding_fingerprint(repo, "cisco_ios/base.j2")["fingerprint"]
                == approval.binding_fingerprint(repo, "cisco_ios/base.j2",
                                                {"s1": {"anything": 1}})["fingerprint"])

    def test_the_fingerprint_records_its_scheme(self, tmp_path):
        from modules.nsot import approval

        repo = _repo_with_templates(tmp_path, devices=("s1",))
        assert (approval.binding_fingerprint(repo, "cisco_ios/base.j2")["scheme"]
                == approval.FINGERPRINT_SCHEME)

    def test_an_approval_survives_a_deploy_to_one_bound_device(self, tmp_path):
        """The case that blocked run 3A at step 2."""
        from modules.nsot import approval

        repo = _repo_with_templates(tmp_path, devices=("s1", "s2"))
        approval._save(repo, {"cisco_ios/base.j2": approval.binding_fingerprint(
            repo, "cisco_ios/base.j2")})

        # s1 is deployed to; its captured config, and therefore its parsed
        # host_vars, are now different.
        assert approval.is_approved(repo, "cisco_ios/base.j2",
                                    {"s1": {"hostname": "s1", "deployed": True},
                                     "s2": {"hostname": "s2"}})


class TestIntentComesFromCommittedHostVars:
    """Intent must not be a function of current state.

    Deriving host_vars by parsing the device's own capture makes the render
    reproduce that capture exactly, so the merge diff is empty by construction
    — the same error as validating a masked render against itself. Both sides
    come from one source, so the comparison cannot say anything.
    """

    def _artifact(self, config, host_vars=None, bootstrap=False, approved=True):
        return build_artifact("s1", config, "cisco_ios",
                              template="cisco_ios/base.j2",
                              template_approved=approved,
                              host_vars=host_vars, bootstrap=bootstrap)

    def test_no_committed_intent_is_not_deployable(self):
        art = self._artifact(_config("s1"), bootstrap=True)
        assert art.bootstrap is True
        assert art.deployable is False
        assert any("no committed intent" in r for r in art.blocking_reasons)

    def test_the_refusal_says_what_to_do(self):
        art = self._artifact(_config("s1"), bootstrap=True)
        reason = next(r for r in art.blocking_reasons if "no committed intent" in r)
        assert "review and commit extracted host_vars" in reason

    def test_bootstrap_cannot_be_overridden(self):
        """deployable stays a computed property with no backing field."""
        art = self._artifact(_config("s1"), bootstrap=True)
        with pytest.raises(Exception):
            art.deployable = True

    def test_committed_intent_equal_to_the_capture_is_deployable_and_empty(self):
        from modules.nsot.deploy import merge_diff
        from modules.nsot.parsers import get_parser

        config = _config("s1")
        intent = get_parser("cisco_ios").parse(config)
        art = self._artifact(config, host_vars=intent)

        assert art.deployable is True
        assert art.intent_drift["differs"] is False
        diff = merge_diff(prepare_device(art)["config"], config)
        assert diff["to_add"] == []

    def test_an_intent_edit_produces_exactly_that_line(self):
        """The point of the whole mechanism."""
        from modules.nsot.deploy import merge_diff
        from modules.nsot.parsers import get_parser

        config = _config("s1")
        intent = get_parser("cisco_ios").parse(config)
        target = next(i for i in intent["interfaces"] if not i.get("description"))
        target["description"] = "NSoT-managed - test"

        art = self._artifact(config, host_vars=intent)
        diff = merge_diff(prepare_device(art)["config"], config)

        assert art.deployable is True, art.blocking_reasons
        assert diff["to_add"] == [f" description NSoT-managed - test"] or any(
            "NSoT-managed - test" in line for line in diff["to_add"])
        assert art.intent_drift["differs"] is True

    def test_an_intent_edit_does_not_block_deployability(self):
        """Fidelity is judged on the template, not on intent-vs-device.

        Judging deployability on the intent render would make every non-empty
        diff self-blocking: the change you want to push is, by definition, a
        difference between intent and the device.
        """
        from modules.nsot.parsers import get_parser

        config = _config("s1")
        intent = get_parser("cisco_ios").parse(config)
        target = next(i for i in intent["interfaces"] if not i.get("description"))
        target["description"] = "NSoT-managed - test"

        art = self._artifact(config, host_vars=intent)
        assert art.deployable is True
        assert not any("invents" in r or "does not reproduce" in r
                       for r in art.blocking_reasons)

    def test_template_infidelity_still_blocks(self):
        """The half that must keep gating."""
        config = _config("s1")
        art = self._artifact(config)
        art.report.update({"missing_from_render": 3})
        art.template_report.update({"missing_from_render": 3})
        assert art.deployable is False

    def test_intent_drift_reports_the_three_way_relationship(self):
        from modules.nsot.parsers import get_parser

        config = _config("s1")
        intent = get_parser("cisco_ios").parse(config)
        target = next(i for i in intent["interfaces"] if not i.get("description"))
        target["description"] = "NSoT-managed - test"

        art = self._artifact(config, host_vars=intent)
        drift = art.intent_drift
        assert drift["adds"] >= 1
        assert drift["differs"] is True
        assert art.summary()["intent_drift"] == drift
        assert art.summary()["bootstrap"] is False


class TestTheConfirmedListReachesTheTransport:
    """The seam, not the stages.

    Every other pipeline test asserts on a stage's output. Both wiring failures
    lived in the handoff *between* stages: ``_deploy_one()`` set
    ``rendered_commands`` and stage 2 overwrote it, so the list the plan
    published and the list that would have reached the wire were different
    objects and no test compared them.

    This runs the whole pipeline with a spy in place of the transport and
    asserts that what arrives at the transport equals what the plan published.
    """

    CONFIRMED = ["interface GigabitEthernet0/1",
                 " description NSoT-managed — CSCI 5840 Lab 4",
                 "exit"]

    @pytest.fixture
    def spy(self, monkeypatch):
        """Records every command list handed to the push transport."""
        from modules import pipeline as P

        seen = []

        def _fake_push(dev, cmds, pool, lock):
            seen.append({"ip": dev.get("ip"), "commands": list(cmds)})
            return "spy: accepted"

        monkeypatch.setattr(P, "_push_config", _fake_push)

        # Neutralise everything that would touch a network or a repo, so the
        # only thing under test is the command list's journey.
        monkeypatch.setattr(P, "_stage_netbox_query", lambda ctx: None)
        monkeypatch.setattr(P, "_stage_ci_gate", lambda ctx: None)
        monkeypatch.setattr(P, "_stage_pre_snapshot", lambda ctx: None)
        monkeypatch.setattr(P, "_stage_config_diff", lambda ctx: None)
        monkeypatch.setattr(P, "_stage_post_snapshot", lambda ctx: None)
        monkeypatch.setattr(P, "_stage_verify", lambda ctx: None)
        monkeypatch.setattr(P, "_stage_save_golden", lambda ctx: None)
        return seen

    def _ctx(self):
        import threading
        from modules.pipeline import PipelineContext

        ctx = PipelineContext(
            config_type="template",
            device_ips=["203.0.113.24"],
            params={}, ip_params_map={},
            selected_devices=[{"ip": "203.0.113.24", "hostname": "s4"}],
            check_devices=[], connections_pool={},
            pool_lock=threading.Lock(), config_id="tpl-s4",
            settle_sleep=lambda _s: None,
        )
        ctx.confirmed_commands = {"203.0.113.24": list(self.CONFIRMED)}
        return ctx

    def test_the_transport_receives_exactly_the_confirmed_list(self, spy):
        from modules.pipeline import PipelineRunner

        PipelineRunner(self._ctx()).run()

        assert len(spy) == 1, f"expected one push, got {len(spy)}"
        assert spy[0]["ip"] == "203.0.113.24"
        assert spy[0]["commands"] == self.CONFIRMED, (
            "the list that reached the transport is not the list that was "
            f"confirmed: {spy[0]['commands']}")

    def test_no_extra_commands_are_appended_anywhere(self, spy):
        from modules.pipeline import PipelineRunner

        PipelineRunner(self._ctx()).run()
        assert len(spy[0]["commands"]) == 3
        assert "end" not in [c.strip() for c in spy[0]["commands"]]

    def test_the_whole_rendered_config_is_not_what_arrives(self, spy):
        """The 83-line bug, asserted directly."""
        from modules.pipeline import PipelineRunner

        PipelineRunner(self._ctx()).run()
        arrived = spy[0]["commands"]
        assert not any(c.startswith("hostname ") for c in arrived)
        assert not any("snmp-server community" in c for c in arrived)

    def test_a_stage_that_tries_to_re_render_raises(self, spy, monkeypatch):
        """The convention failed twice; this is the structural backstop."""
        from modules.pipeline import ConfirmedCommandsOverwritten

        ctx = self._ctx()
        with pytest.raises(ConfirmedCommandsOverwritten):
            ctx.rendered_commands = {"203.0.113.24": ["hostname substituted"]}
        assert ctx.rendered_commands == {"203.0.113.24": self.CONFIRMED}

    def test_the_plan_and_the_transport_agree(self, spy):
        """End to end: fingerprint what the plan publishes, run, compare."""
        from modules.nsot.deploy import command_fingerprint
        from modules.pipeline import PipelineRunner

        published = command_fingerprint(self.CONFIRMED)
        PipelineRunner(self._ctx()).run()
        assert command_fingerprint(spy[0]["commands"]) == published


class TestEveryReferencedHelperExists:
    """A whole function was deleted and 1133 tests passed.

    `_deploy_one` — the only path that connects to a device — was removed by an
    over-wide slice, and the suite did not notice because every test exercises
    the pieces it calls rather than the wiring that calls it. It reached the
    live host and sat there through a read-only preview, which does not touch
    it.

    Import-time errors are the cheapest class of bug to catch and the most
    embarrassing to ship, so they get a test of their own rather than relying
    on some other test happening to import the right thing.
    """

    ROUTE_MODULES = ["routes.deploy", "routes.golden", "routes.templatize",
                     "routes.templates", "routes.inventory",
                     "routes.netbox_safety", "routes.settings_integrations"]

    @pytest.mark.parametrize("module_name", ROUTE_MODULES)
    def test_module_imports(self, module_name):
        import importlib
        importlib.import_module(module_name)

    @pytest.mark.parametrize("module_name", ROUTE_MODULES)
    def test_every_name_it_calls_is_defined(self, module_name):
        """Catches a deleted helper that nothing happens to exercise."""
        import ast
        import importlib
        import inspect

        module = importlib.import_module(module_name)
        tree = ast.parse(inspect.getsource(module))

        defined = {node.name for node in ast.walk(tree)
                   if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                        ast.ClassDef))}
        # Module-level names bound by assignment or import.
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                defined.add(node.id)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    defined.add(alias.asname or alias.name.split(".")[0])
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for arg in node.args.args + node.args.kwonlyargs:
                    defined.add(arg.arg)

        called = {node.func.id for node in ast.walk(tree)
                  if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}

        import builtins
        missing = sorted(name for name in called
                         if name.startswith("_")
                         and name not in defined
                         and not hasattr(builtins, name)
                         and not hasattr(module, name))
        assert missing == [], (
            f"{module_name} calls undefined helper(s): {missing}")


class TestARequestReachesTheWire:
    """The seam one layer up: HTTP request → route → `_deploy_one` → transport.

    ``TestTheConfirmedListReachesTheTransport`` follows a command list from a
    ``PipelineContext`` to the wire. It starts *after* the route has already
    built the context, so it says nothing about whether any route still calls
    the code it exercises — which is how ``_deploy_one()`` could be deleted
    outright with 1133 tests green.

    An AST presence test catches that deletion. It does not catch a function
    that exists but is no longer called, is called with the wrong arguments, or
    is bypassed by a second path someone added. This does, because it makes the
    request the test subject: POST /deploy/plan for a real command list and
    hash, POST /deploy/apply with that hash, and assert the exact program
    arrives at the transport.

    Only the transport and the stages that would open a socket are replaced.
    Everything between the route and them — artifact build, `prepare_device`,
    `merge_commands`, `assert_merge_only`, `plan_batch`, `run_batch`,
    `_deploy_one`, `PipelineRunner` — is the real code.
    """

    DEVICE = "s1"
    IP = "203.0.113.21"
    EDIT = "NSoT-managed route seam"

    @pytest.fixture
    def wired(self, tmp_path, monkeypatch):
        import flask
        from modules.nsot import hostvars, manifest, templates_repo
        from modules.nsot.parsers import get_parser
        from modules import pipeline as P
        import routes.deploy as RD

        list_dir = tmp_path / "lab"
        repo = str(list_dir / "config_repo")
        os.makedirs(os.path.join(repo, "golden"), exist_ok=True)
        os.makedirs(os.path.join(repo, "host_vars"), exist_ok=True)
        templates_repo.seed_templates(repo)
        manifest.upsert_device(repo, f"uid:{self.DEVICE}", self.DEVICE, self.IP,
                               platform="cisco_ios")

        captured = _config(self.DEVICE)
        with open(os.path.join(repo, "golden", f"{self.DEVICE}.cfg"), "w",
                  encoding="utf-8") as fh:
            fh.write(captured)

        # Committed intent = the capture's own parse plus ONE edit, so the
        # program is exactly the lines that edit produces.
        intent = get_parser("cisco_ios").parse(captured)
        target = next(i for i in intent["interfaces"]
                      if i["name"].startswith("GigabitEthernet"))
        target["description"] = self.EDIT
        # write_committed() refuses a `secrets:` mapping, so the committed file
        # holds refs only. The credential store is what puts values back at
        # deploy time; here the capture's own parsed values stand in for it.
        secrets = dict(intent.get("secrets") or {})
        hostvars.write_committed(repo, intent)

        row = {"hostname": self.DEVICE, "ip": self.IP,
               "device_type": "cisco_ios", "username": "u", "password": "p",
               "secret": "s", "device_uid": self.DEVICE}
        monkeypatch.setattr("modules.config.get_list_data_dir",
                            lambda name: str(list_dir))
        monkeypatch.setattr("modules.config.get_current_list_name", lambda: "Lab")
        monkeypatch.setattr("modules.device.get_current_device_list",
                            lambda: ("Lab", str(list_dir / "devices.csv")))
        monkeypatch.setattr("modules.device.load_saved_devices",
                            lambda path=None: [row])
        monkeypatch.setattr("modules.nsot.approval.is_approved",
                            lambda *a, **k: True)
        monkeypatch.setattr("modules.nsot.hostvars.hydrate_secrets",
                            lambda hv, host: {**hv, "secrets": dict(secrets)})
        # The batch commit is a different seam, covered elsewhere.
        monkeypatch.setattr(RD, "_commit_batch_golden",
                            lambda *a, **k: {"ok": True, "commit": ""})

        seen = []

        def _spy_push(dev, cmds, pool, lock):
            seen.append({"ip": dev.get("ip"), "commands": list(cmds)})
            return "spy: accepted"

        monkeypatch.setattr(P, "_push_config", _spy_push)
        for stage in ("_stage_netbox_query", "_stage_ci_gate",
                      "_stage_pre_snapshot", "_stage_config_diff",
                      "_stage_post_snapshot", "_stage_verify",
                      "_stage_save_golden"):
            monkeypatch.setattr(P, stage, lambda ctx: None)

        app = flask.Flask(__name__)
        app.register_blueprint(RD.bp)
        return app.test_client(), seen

    def _plan(self, client):
        response = client.post("/deploy/plan", json={"devices": [self.DEVICE]})
        assert response.status_code == 200, response.data
        body = response.get_json()
        return next(d for d in body["devices"] if d["device"] == self.DEVICE)

    def test_the_plans_program_is_what_arrives_at_the_transport(self, wired):
        client, seen = wired

        planned = self._plan(client)
        assert planned["deployable"] is True, planned.get("blocking_reasons")
        assert planned["commands"], "the plan published no program to follow"

        response = client.post("/deploy/apply", json={
            "confirmations": {self.DEVICE: planned["capture_hash"]},
            "command_hashes": {self.DEVICE: planned["command_hash"]}})
        assert response.status_code == 200, response.data

        assert len(seen) == 1, (
            f"expected exactly one push from one request, got {len(seen)}. "
            "Zero means nothing on the route reaches the transport at all.")
        assert seen[0]["ip"] == self.IP
        assert seen[0]["commands"] == planned["commands"], (
            "the program that reached the wire is not the program the plan "
            f"published: {seen[0]['commands']} != {planned['commands']}")

    def test_the_edit_is_in_the_program_that_reached_the_wire(self, wired):
        """Guards against a seam that passes an empty list end to end."""
        client, seen = wired

        planned = self._plan(client)
        client.post("/deploy/apply", json={
            "confirmations": {self.DEVICE: planned["capture_hash"]},
            "command_hashes": {self.DEVICE: planned["command_hash"]}})

        arrived = "\n".join(seen[0]["commands"])
        assert self.EDIT in arrived
        assert "end" not in [c.strip() for c in seen[0]["commands"]]

    def test_a_stale_hash_stops_the_request_before_the_wire(self, wired):
        """The refusal is part of the route's job, so it is part of this test."""
        client, seen = wired

        planned = self._plan(client)
        response = client.post("/deploy/apply", json={
            "confirmations": {self.DEVICE: planned["capture_hash"]},
            "command_hashes": {self.DEVICE: "not-the-hash-you-confirmed"}})

        body = response.get_json()
        assert seen == [], "a refused device must never reach the transport"
        assert body["refused"][0]["device"] == self.DEVICE
        assert "changed since you confirmed" in body["refused"][0]["reason"]

    def test_an_unconfirmed_device_reaches_nothing(self, wired):
        client, seen = wired
        response = client.post("/deploy/apply", json={"confirmations": {}})
        assert response.status_code == 400
        assert seen == []
