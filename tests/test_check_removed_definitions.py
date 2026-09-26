"""The removed-definition checker can tell a USE from a MENTION.

Three edits in this project destroyed adjacent code, which is why the checker
exists. Stage 3.3 deleted `_scan_device` deliberately -- and hit the shape
that makes the checker unusable:

* the commit that removes a function is the same commit that pins its removal
  with ``assert not hasattr(mod, "_scan_device")``;
* the docstring explaining why it went names it too.

A word-grep counts both as references, so the gate reports GONE forever and
exits 1 on every subsequent commit. **A gate that cannot be satisfied is one
that gets run with --no-verify**, which is how a check stops existing.

It also found a second bug in the same pass: `"_scan_device" in
"_scan_device_from_golden"` is True, so a substring test reports every short
name as referenced by the longer name that replaced it.

These tests exist because the loosening must not hide a real caller.
"""

import importlib.util
import os

import pytest

SPEC = importlib.util.spec_from_file_location(
    "check_removed_definitions",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "scripts", "check_removed_definitions.py"))
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)


@pytest.fixture
def source(tmp_path, monkeypatch):
    """Write a file inside the checker's ROOT and hand back its relative path."""
    made = []

    def _write(text):
        path = tmp_path / f"m{len(made)}.py"
        path.write_text(text, encoding="utf-8")
        made.append(path)
        return str(path)

    monkeypatch.setattr(CHECK, "ROOT", "")
    return _write


class TestARealCallerIsStillFound:
    """The loosening must not cost the checker its job."""

    def test_a_plain_call(self, source):
        p = source("def f():\n    return _gone(1)\n")
        assert CHECK._code_mentions("_gone", p) is True

    def test_an_attribute_access(self, source):
        p = source("import m\n\n\ndef f():\n    return m._gone()\n")
        assert CHECK._code_mentions("_gone", p) is True

    def test_a_bare_name_with_no_call(self, source):
        p = source("handler = _gone\n")
        assert CHECK._code_mentions("_gone", p) is True

    def test_a_monkeypatch_target_string(self, source):
        """Names reach `setattr` as strings; that is a use."""
        p = source('monkeypatch.setattr("mod._gone", lambda: 1)\n')
        assert CHECK._code_mentions("_gone", p) is True

    def test_an_import(self, source):
        p = source("from mod import _gone\n")
        assert CHECK._code_mentions("_gone", p) is True

    def test_one_real_use_outweighs_any_number_of_mentions(self, source):
        p = source(
            '"""_gone is gone, see the notes."""\n'
            '# _gone was removed in 3.3\n'
            'assert not hasattr(mod, "_gone")\n'
            'result = _gone()\n')
        assert CHECK._code_mentions("_gone", p) is True


class TestProseIsNotAReference:

    def test_a_module_docstring(self, source):
        p = source('"""_gone, the SSH scanner, had no callers."""\n\nx = 1\n')
        assert CHECK._code_mentions("_gone", p) is False

    def test_a_function_docstring(self, source):
        p = source('def f():\n    """Replaces _gone."""\n    return 1\n')
        assert CHECK._code_mentions("_gone", p) is False

    def test_a_comment(self, source):
        p = source("# _gone was deleted in Stage 3.3\nx = 1\n")
        assert CHECK._code_mentions("_gone", p) is False

    def test_an_absence_assertion(self, source):
        p = source('assert not hasattr(mod, "_gone")\n')
        assert CHECK._code_mentions("_gone", p) is False

    def test_a_getattr_probe(self, source):
        p = source('if getattr(mod, "_gone", None):\n    pass\n')
        assert CHECK._code_mentions("_gone", p) is False


class TestOnlyAReferenceShapedStringIsAUse:
    """P.3 step 2: a route removed and its 404 pinned in the same commit named
    it as a PATH, and the model's prompt names it in a sentence."""

    def test_a_url_path_is_not_a_use(self, source):
        p = source('CUT = [("POST", "/_gone/192.0.2.1")]\n')
        assert CHECK._code_mentions("_gone", p) is False

    def test_a_sentence_is_not_a_use(self, source):
        p = source('PROMPT = "IF you make a change (_gone / other):"\n')
        assert CHECK._code_mentions("_gone", p) is False

    def test_a_caller_spelling_is_not_a_use(self, source):
        p = source("NEEDLES = [\"url_for('_gone'\"]\n")
        assert CHECK._code_mentions("_gone", p) is False

    def test_a_bare_name_string_is_still_a_use(self, source):
        """Control: a list of names fed to getattr in a loop is a real use."""
        p = source('for n in ["_gone"]:\n    getattr(mod, n)()\n')
        assert CHECK._code_mentions("_gone", p) is True

    def test_a_filename_is_not_a_use(self, source):
        """P.4 step 1: removing the view `_gone` was flagged by a module that
        wrote a file NAMED after it."""
        p = source('path = os.path.join(d, "_gone.json")\n')
        assert CHECK._code_mentions("_gone", p) is False

    def test_a_dotted_path_is_still_a_use(self, source):
        """Control: an extension rule must not swallow `mod._gone`."""
        p = source('monkeypatch.setattr("modules.x._gone", None)\n')
        assert CHECK._code_mentions("_gone", p) is True

    def test_an_entry_point_string_is_still_a_use(self, source):
        p = source('ep = "pkg.mod:_gone"\n')
        assert CHECK._code_mentions("_gone", p) is True


class TestAMethodOnAnotherObjectIsNotAUse:
    """P.3 D12: removing the Flask view `disconnect` from app.py was flagged as
    still used by every Netmiko `conn.disconnect()` in the tree."""

    def test_a_method_call_on_another_object_is_not_a_use(self, source):
        p = source("conn.disconnect()\n")
        assert CHECK._code_mentions("disconnect", p, defined_in="app.py") is False

    def test_the_module_attribute_is_a_use(self, source):
        p = source("import app\napp.disconnect()\n")
        assert CHECK._code_mentions("disconnect", p, defined_in="app.py") is True

    def test_an_aliased_module_is_a_use(self, source):
        p = source("import app as A\nA.disconnect()\n")
        assert CHECK._code_mentions("disconnect", p, defined_in="app.py") is True

    def test_a_dotted_module_path_is_a_use(self, source):
        p = source("import modules.nsot.restore\nmodules.nsot.restore.plan()\n")
        assert CHECK._code_mentions("plan", p, defined_in="modules/nsot/restore.py") is True

    def test_a_from_imported_module_is_a_use(self, source):
        p = source("from modules.nsot import restore as R\nR.plan()\n")
        assert CHECK._code_mentions("plan", p, defined_in="modules/nsot/restore.py") is True

    def test_without_the_defining_file_any_attribute_still_counts(self, source):
        """Control: the conservative answer stays when nothing is known."""
        p = source("conn.disconnect()\n")
        assert CHECK._code_mentions("disconnect", p) is True


class TestWholeWordsOnly:
    """`"_scan_device" in "_scan_device_from_golden"` is True."""

    def test_a_longer_name_is_not_this_name(self, source):
        p = source('calls_in(mod._impl, "_gone_from_golden")\n')
        assert CHECK._code_mentions("_gone", p) is False

    def test_a_longer_attribute_is_not_this_name(self, source):
        p = source("mod._gone_from_golden()\n")
        assert CHECK._code_mentions("_gone", p) is False

    def test_the_exact_name_still_matches(self, source):
        p = source('calls_in(mod._impl, "_gone")\n')
        assert CHECK._code_mentions("_gone", p) is True


class TestUnparseableFilesAreTreatedAsReferences:
    """The conservative answer belongs on the side that reports."""

    def test_a_syntax_error_counts_as_a_reference(self, source):
        p = source("def f(:\n")
        assert CHECK._code_mentions("_gone", p) is True

    def test_a_missing_file_counts_as_a_reference(self, tmp_path, monkeypatch):
        monkeypatch.setattr(CHECK, "ROOT", "")
        assert CHECK._code_mentions("_gone", str(tmp_path / "nope.py")) is True


class TestADeletedFileIsAttributedToItself:
    """P.4 step 1c: a deleted file ends its header with `+++ /dev/null`, and
    its definitions were reported under the previous file in the diff."""

    DIFF = ("diff --git a/modules/kept.py b/modules/kept.py\n"
            "--- a/modules/kept.py\n+++ b/modules/kept.py\n"
            "@@ -1 +0,0 @@\n-def dropped_here():\n"
            "diff --git a/modules/gone.py b/modules/gone.py\n"
            "deleted file mode 100644\n"
            "--- a/modules/gone.py\n+++ /dev/null\n"
            "@@ -1,2 +0,0 @@\n-def in_the_deleted_file():\n-class Also:\n")

    def test_each_definition_names_its_own_file(self):
        got = {name: path for path, _k, name, _i in CHECK._removed_from_diff(self.DIFF)}
        assert got == {"dropped_here": "modules/kept.py",
                       "in_the_deleted_file": "modules/gone.py",
                       "Also": "modules/gone.py"}


class TestANameThatSurvivesElsewhere:
    """P.4 step 1c: `jenkins_runner.save_config` was deleted while app.py's
    view `save_config` lived on, and the gate table's "save_config" key and
    `url_for('save_config')` were counted as uses of the deleted one."""

    def _write(self, tmp_path, files):
        for rel, text in files.items():
            (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
            (tmp_path / rel).write_text(text)

    def test_a_string_mention_of_a_surviving_name_is_not_a_use(self, tmp_path, monkeypatch):
        self._write(tmp_path, {"modules/survivor.py": "def save_it():\n    pass\n",
                               "modules/table.py": 'GATES = {"save_it": 1}\n'})
        monkeypatch.setattr(CHECK, "ROOT", str(tmp_path))
        monkeypatch.setattr(CHECK, "_top_level_definers",
                            lambda name, rev="": ["modules/survivor.py"])
        assert CHECK._imports_from("modules/table.py", "modules.gone", "save_it") is False

    def test_an_import_from_the_removed_module_is_still_a_use(self, tmp_path, monkeypatch):
        """Control: the survivor rule must not hide a real caller."""
        self._write(tmp_path, {
            "modules/caller.py": "from modules.gone import save_it\nsave_it()\n",
            "modules/attr.py": "import modules.gone as G\nG.save_it()\n"})
        monkeypatch.setattr(CHECK, "ROOT", str(tmp_path))
        assert CHECK._imports_from("modules/caller.py", "modules.gone", "save_it") is True
        assert CHECK._imports_from("modules/attr.py", "modules.gone", "save_it") is True
