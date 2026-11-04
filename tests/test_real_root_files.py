"""C2455: the tests of root's REAL files (`real_root_files`) cannot run where root's files read as
another uid (the confined runner's user namespace), and a skip there ran them nowhere automated.
There they are deselected (tests/conftest.py), never skipped; the gate's step 4c runs them
unconfined on every gate (the operator's ruling), where one that cannot read them fails. CI runs
its suite confined only (tests/test_ci_workflow.py), so CI deselects them."""
import types

from tests import conftest


class _Item:
    def __init__(self, name, marked):
        self.name, self._marked = name, marked

    def get_closest_marker(self, name):
        return object() if self._marked and name == "real_root_files" else None


def _config(seen):
    return types.SimpleNamespace(
        hook=types.SimpleNamespace(pytest_deselected=lambda items: seen.extend(items)))


def test_where_root_s_files_read_as_another_uid_the_marked_tests_are_deselected(monkeypatch):
    monkeypatch.setattr(conftest, "root_files_read_as_another_uid", lambda: True)
    items, seen = [_Item("a", False), _Item("real", True), _Item("b", False)], []
    conftest.pytest_collection_modifyitems(_config(seen), items)
    assert [i.name for i in items] == ["a", "b"] and [i.name for i in seen] == ["real"]


def test_where_they_read_as_root_s_every_test_runs(monkeypatch):
    monkeypatch.setattr(conftest, "root_files_read_as_another_uid", lambda: False)
    items, seen = [_Item("a", False), _Item("real", True)], []
    conftest.pytest_collection_modifyitems(_config(seen), items)
    assert [i.name for i in items] == ["a", "real"] and seen == []


def test_the_three_tests_of_root_s_real_files_carry_the_marker():
    """The marker's population: the three that skipped in every confined run (#1418)."""
    import ast
    import os
    src = open(os.path.join(os.path.dirname(__file__), "test_update_button.py"),
               encoding="utf-8").read()
    marked = sorted(f.name for f in ast.walk(ast.parse(src)) if isinstance(f, ast.FunctionDef)
                    and any(isinstance(d, ast.Attribute) and d.attr == "real_root_files"
                            for d in f.decorator_list))
    assert marked == ["test_the_self_test_names_each_problem",
                      "test_the_self_test_passes_on_this_machine_for_the_real_table",
                      "test_this_releases_updater_passes_its_own_self_test_as_installed"]
