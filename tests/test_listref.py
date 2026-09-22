"""A device list, resolved once and carried.

Three defects in this project had one shape: a function was told which list
to work on, then asked a global which list was current.

1. The pipeline called `get_current_list_name()` at three points **after** the
   push, including the golden commit. That reads a file on disk, so switching
   lists during a 45-90s convergence window committed one network's captures
   into another's repository.
2. `plan_restore()` took `list_name`, used it for the repo, and read its
   devices from `get_current_device_list()`.
3. `check_right_repository()` compared `slug == list_name` -- `'default'`
   against `'Default'` -- so every adopted list failed its own uniqueness
   check, naming itself as the other list that already owns the repository.

The first two are "asked again later". The third is why this is a **type**
rather than a convention: a list has two names, the operator's and the
directory's, and passing "the list name" as a string leaves every caller to
decide which one it meant. A comparison between the two is always false.
"""

import os

import pytest

from modules.nsot.listref import ListRef, UnknownList, active, coerce, resolve


@pytest.fixture
def lab(tmp_path, monkeypatch):
    lists = tmp_path / "lists"
    (lists / "default").mkdir(parents=True)
    (lists / "other_net").mkdir(parents=True)
    monkeypatch.setattr("modules.config.get_list_data_dir",
                        lambda name: str(lists / _slug(name)))
    monkeypatch.setattr("modules.config.get_current_list_name",
                        lambda: "Default")
    monkeypatch.setattr("modules.nsot.listref._registry",
                        lambda: {"Default": "default", "Other Net": "other_net"})
    return lists


def _slug(name):
    from modules.config import list_slug

    return list_slug(name)


class TestBothNamesAreCarried:
    """The defect that made this a type."""

    def test_a_display_name_resolves(self, lab):
        ref = resolve("Default")
        assert ref.name == "Default"
        assert ref.slug == "default"

    def test_a_slug_resolves_to_the_same_list(self, lab):
        """A caller given only a slug still gets the name to show."""
        ref = resolve("default")
        assert ref.name == "Default"
        assert ref.slug == "default"

    def test_the_two_names_are_different_strings(self, lab):
        ref = resolve("Default")
        assert ref.name != ref.slug, (
            "if these were ever equal the original bug would be invisible")

    def test_the_display_name_and_the_slug_are_the_same_list(self, lab):
        assert resolve("Default").matches("default")
        assert resolve("default").matches("Default")

    def test_the_raw_comparison_that_failed_still_fails(self, lab):
        """Pinning the defect: `slug == list_name` is False, which is why
        identity has to be compared instead of strings."""
        assert resolve("Default").slug != "Default"

    def test_a_different_list_does_not_match(self, lab):
        assert not resolve("Default").matches("other_net")
        assert not resolve("Default").matches("Other Net")

    def test_matching_against_nothing_is_false(self, lab):
        assert not resolve("Default").matches(None)
        assert not resolve("Default").matches("")

    def test_an_unknown_name_does_not_match(self, lab):
        """`matches` must not raise on a name nobody knows."""
        assert not resolve("Default").matches("no-such-list")


class TestThePathsAreDerivedOnce:
    def test_it_carries_the_paths(self, lab):
        ref = resolve("Default")
        assert ref.data_dir.endswith("default")
        assert ref.repo_dir.endswith(os.path.join("default", "config_repo"))
        assert ref.csv_path.endswith(os.path.join("default", "devices.csv"))

    def test_the_directory_comes_from_the_app_accessor(self, lab, monkeypatch):
        """A second derivation is the thing this module removes.

        The first version joined LISTS_DIR with the registry's slug and only
        fell back to `get_list_data_dir()`. A caller that had overridden that
        accessor still got the real directory, so a uniqueness check
        enumerated the wrong parent and found no rival to refuse.
        """
        seen = []
        real = __import__("modules.config", fromlist=["x"]).get_list_data_dir
        monkeypatch.setattr("modules.config.get_list_data_dir",
                            lambda name: seen.append(name) or real(name))
        resolve("Default")
        assert seen, "the ref was built without asking the app where the list is"

    def test_it_is_frozen(self, lab):
        import dataclasses

        with pytest.raises(dataclasses.FrozenInstanceError):
            resolve("Default").name = "Something Else"


class TestReadingAmbientStateIsVisible:
    """The three defects all looked like ordinary calls."""

    def test_active_reads_the_current_list(self, lab):
        assert active().name == "Default"

    def test_coerce_passes_a_ref_through(self, lab):
        ref = resolve("Default")
        assert coerce(ref) is ref

    def test_coerce_resolves_a_string(self, lab):
        assert coerce("other_net").name == "Other Net"

    def test_coerce_falls_back_to_active_only_when_given_nothing(self, lab):
        assert coerce("").name == "Default"
        assert coerce(None).name == "Default"

    def test_resolve_refuses_an_empty_name(self, lab):
        with pytest.raises(UnknownList):
            resolve("   ")


class TestAnUnregisteredListStillResolves:
    """A list can exist on disk before the registry catches up. That is not
    an error -- but it is worth a log line, because a silently derived slug
    is how two directories for one list appear."""

    def test_it_derives_a_slug(self, lab):
        ref = resolve("Brand New")
        assert ref.slug == "brand_new"
        assert ref.name == "Brand New"

    def test_it_is_logged(self, lab, caplog):
        with caplog.at_level("INFO"):
            resolve("Brand New")
        assert any("not in the device-list registry" in r.message
                   for r in caplog.records)


class TestTheRemoteCheckUsesIt:
    """The site of defect 3, now answering identity rather than strings."""

    def test_check_right_repository_resolves_rather_than_compares_strings(self):
        """Checked on the CODE, not the source text.

        The first version asserted `"slug == list_name" not in source` and
        failed -- on the fix -- because that string is in the **comment**
        explaining the defect. Fourth instance of that mistake in one stage,
        and the first inside a test written to confirm the mistake was fixed.
        """
        from tests.astcheck import calls_in, code_of

        from modules.nsot import remote

        assert calls_in(remote.check_right_repository, "matches") >= 1
        assert "slug == list_name" not in code_of(remote.check_right_repository)


class TestNoNsotPathReDerivesAListItAlreadyHas:
    """The guard the plan asked for.

    A function handed a list must not go and read the active one. Checked on
    the parsed tree, not the source text -- `restore.py` and `remote.py` both
    EXPLAIN this defect in their docstrings, and a text search matches the
    explanation.
    """

    MODULES = ["modules/nsot/restore.py", "modules/nsot/remote.py",
               "modules/nsot/repo.py", "modules/nsot/deploy.py"]
    AMBIENT = {"get_current_list_name", "get_current_device_list"}

    def _offenders(self, relative):
        import ast

        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, relative), encoding="utf-8") as handle:
            tree = ast.parse(handle.read())

        found = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            args = {a.arg for a in node.args.args + node.args.kwonlyargs}
            if not (args & {"list_name", "list_ref", "ref"}):
                continue
            for inner in ast.walk(node):
                if (isinstance(inner, ast.Call)
                        and getattr(inner.func, "attr",
                                    getattr(inner.func, "id", "")) in self.AMBIENT):
                    found.append(f"{relative}:{node.name}")
        return found

    def test_none_of_them_does(self):
        offenders = []
        for relative in self.MODULES:
            offenders.extend(self._offenders(relative))
        assert not offenders, (
            f"these take a list and then ask which one is current: {offenders}")

    def test_the_check_can_actually_find_one(self):
        """Otherwise it passes because it is looking for nothing."""
        import ast

        tree = ast.parse(
            "def f(list_name):\n"
            "    from modules.config import get_current_list_name\n"
            "    return get_current_list_name()\n")
        node = tree.body[0]
        calls = [n for n in ast.walk(node)
                 if isinstance(n, ast.Call)
                 and getattr(n.func, "id", "") in self.AMBIENT]
        assert calls
