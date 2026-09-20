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
