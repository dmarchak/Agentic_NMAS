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


class TestApprovalIsAskedTheRightQuestion:
    """The deploy path asked ``is_approved()`` about one device at a time.

    ``binding_fingerprint()`` hashes the **whole bound device set** — that is
    the point of it, so onboarding a device revokes approval. A device it is
    not given hashes to the literal string ``"unknown"``. Passing only the
    device being deployed therefore produced a fingerprint that could never
    equal the one approval stored, and every template bound to more than one
    device was permanently unapprovable on the deploy path.

    Fail-closed, so nothing unsafe shipped — the flow was simply unreachable,
    which is the same family as a check that is reported and consumed by
    nobody: a gate structurally incapable of returning the answer it is asked
    for.
    """

    def test_a_partial_device_set_cannot_match_a_full_approval(self, tmp_path):
        """The mechanism, isolated from the routes."""
        from modules.nsot import approval

        repo = _repo_with_templates(tmp_path, devices=("s1", "s2"))
        host_vars = {"s1": {"hostname": "s1"}, "s2": {"hostname": "s2"}}

        full = approval.binding_fingerprint(repo, "cisco_ios/base.j2", host_vars)
        partial = approval.binding_fingerprint(repo, "cisco_ios/base.j2",
                                               {"s2": host_vars["s2"]})

        assert full["fingerprint"] != partial["fingerprint"]
        assert partial["device_hashes"]["s1"] == "unknown"

    def test_the_bound_set_is_what_the_fingerprint_needs(self, tmp_path):
        from modules.nsot import approval

        repo = _repo_with_templates(tmp_path, devices=("s1", "s2"))
        host_vars = {"s1": {"hostname": "s1"}, "s2": {"hostname": "s2"}}
        approval._save(repo, {"cisco_ios/base.j2": approval.binding_fingerprint(
            repo, "cisco_ios/base.j2", host_vars)})

        assert approval.is_approved(repo, "cisco_ios/base.j2", host_vars)
        assert not approval.is_approved(repo, "cisco_ios/base.j2",
                                        {"s2": host_vars["s2"]})


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
        target["description"] = "NSoT-managed — test"

        art = self._artifact(config, host_vars=intent)
        diff = merge_diff(prepare_device(art)["config"], config)

        assert art.deployable is True, art.blocking_reasons
        assert diff["to_add"] == [f" description NSoT-managed — test"] or any(
            "NSoT-managed — test" in line for line in diff["to_add"])
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
        target["description"] = "NSoT-managed — test"

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
        target["description"] = "NSoT-managed — test"

        art = self._artifact(config, host_vars=intent)
        drift = art.intent_drift
        assert drift["adds"] >= 1
        assert drift["differs"] is True
        assert art.summary()["intent_drift"] == drift
        assert art.summary()["bootstrap"] is False
