"""Exactly two callers may create a device identity.

`adopt_identity()` was documented as "the only place a device identity is
created", and `resolve_identity()` deliberately cannot create. But the gate in
front of them — `save_golden(allow_new=...)` — defaulted to **True**, so four
of seven call sites could mint without anybody deciding they should:

    app.py                       Save All
    modules/pipeline.py:1435     a pipeline golden save
    modules/config_git.py        the manual golden save
    modules/ai_assistant.py      a path reachable from the AI agent

A device appearing in the inventory therefore got an identity as a side effect
of the next routine capture, and the caller least entitled to create one was
among those that could.

The default is now False. The legitimate minting points are the onboarding
wizard (Phase 4) and the Add Device form, both of which exist to onboard.
"""

import ast
import io
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _source(relative):
    with open(os.path.join(ROOT, relative), encoding="utf-8") as fh:
        return fh.read()


def _save_golden_calls(relative):
    """(line, whether allow_new is passed, its literal value) per call."""
    tree = ast.parse(_source(relative))
    calls = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "id", getattr(node.func, "attr", ""))
        if name != "save_golden":
            continue
        kw = {k.arg: k.value for k in node.keywords if k.arg}
        if "allow_new" in kw:
            value = kw["allow_new"]
            literal = value.value if isinstance(value, ast.Constant) else "?"
            calls.append((node.lineno, True, literal))
        else:
            calls.append((node.lineno, False, None))
    return calls


PRODUCTION = ["app.py", "modules/pipeline.py", "modules/config_git.py",
              "modules/ai_assistant.py", "modules/nsot/credential_rotation.py",
              "routes/deploy.py"]


class TestTheDefaultDoesNotMint:
    def test_save_golden_defaults_to_refusing(self):
        """The default IS the behaviour; a rule that depends on every caller
        remembering is a convention."""
        from modules.nsot import repo
        import inspect

        default = inspect.signature(repo.save_golden).parameters["allow_new"].default
        assert default is False

    def test_no_production_caller_relies_on_the_default(self):
        """Every call either names allow_new or is accounted for below."""
        relying = []
        for relative in PRODUCTION:
            for line, explicit, _value in _save_golden_calls(relative):
                if not explicit:
                    relying.append(f"{relative}:{line}")
        assert not relying, (
            f"these mint or refuse by default rather than by decision: {relying}")

    def test_no_production_caller_passes_allow_new_true(self):
        """The wizard does not exist yet; Add Device uses adopt_identity
        directly. Nothing else may onboard through save_golden."""
        minting = []
        for relative in PRODUCTION:
            for line, explicit, value in _save_golden_calls(relative):
                if explicit and value is True:
                    minting.append(f"{relative}:{line}")
        assert not minting, f"unexpected minting call sites: {minting}"


class TestTheAssistantCanNeverMint:
    """The one caller that must never create an identity."""

    def test_it_does_not_pass_allow_new(self):
        for _line, explicit, value in _save_golden_calls("modules/ai_assistant.py"):
            assert not (explicit and value is True)

    def test_it_never_calls_adopt_identity(self):
        source = _source("modules/ai_assistant.py")
        assert "adopt_identity" not in source

    def test_an_unknown_device_is_refused_with_the_reason(self, tmp_path,
                                                          monkeypatch):
        """Behavioural, not only structural."""
        from modules.nsot.repo import GoldenItem, save_golden

        list_dir = tmp_path / "lab"
        list_dir.mkdir()
        monkeypatch.setattr("modules.config.get_list_data_dir",
                            lambda name: str(list_dir))
        monkeypatch.setattr("modules.settings_schema.get_setting",
                            lambda key, default=None: {
                                "nsot_git_author_name": "NMAS",
                                "nsot_git_author_email": "n@l",
                                "nsot_device_tag_retention": 50}.get(key, default))
        monkeypatch.setattr("modules.nsot.hooks.run_post_commit", lambda ctx: None)

        out = save_golden("lab", [GoldenItem("never-seen", "hostname x\n",
                                             "203.0.113.77")],
                          source="ai", actor="assistant")
        assert out["ok"] is False
        assert "not in the manifest" in out["error"]
        assert "Onboard it first" in out["error"]


class TestAddDeviceMintsAtAddTime:
    """Adding a device IS onboarding, so the identity is created there.

    It used to be created by whichever save_golden ran first — usually an
    unrelated Save All — so "when does this device get an identity" had no
    answer anybody could point at.
    """

    def test_it_calls_adopt_identity(self):
        source = _source("app.py")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "add_device":
                assert "adopt_identity" in ast.dump(node)
                break
        else:
            raise AssertionError("no add_device route")

    def test_it_resolves_before_minting(self):
        """An existing device re-added must not get a second identity."""
        source = _source("app.py")
        tree = ast.parse(source)
        add = next(n for n in ast.walk(tree)
                   if isinstance(n, ast.FunctionDef) and n.name == "add_device")
        dumped = ast.dump(add)
        assert "find_by_name" in dumped and "find_by_ip" in dumped, (
            "minting without looking first creates duplicates for a device "
            "that is already known")

    def test_it_records_the_identity_on_the_csv_row(self):
        add = next(n for n in ast.walk(ast.parse(_source("app.py")))
                   if isinstance(n, ast.FunctionDef) and n.name == "add_device")
        assert "device_uid" in ast.dump(add), (
            "an identity nobody records is minted again next time")


class TestTheRefusalSaysWhereIdentitiesAreCreated:
    def test_the_message_names_both_legitimate_paths(self, tmp_path, monkeypatch):
        from modules.nsot.repo import GoldenItem, save_golden

        list_dir = tmp_path / "lab"
        list_dir.mkdir()
        monkeypatch.setattr("modules.config.get_list_data_dir",
                            lambda name: str(list_dir))
        monkeypatch.setattr("modules.settings_schema.get_setting",
                            lambda key, default=None: {
                                "nsot_git_author_name": "NMAS",
                                "nsot_git_author_email": "n@l",
                                "nsot_device_tag_retention": 50}.get(key, default))
        monkeypatch.setattr("modules.nsot.hooks.run_post_commit", lambda ctx: None)

        out = save_golden("lab", [GoldenItem("nope", "hostname x\n")],
                          source="manual", actor="test")
        assert "onboarding wizard" in out["error"]
        assert "Add Device" in out["error"]
