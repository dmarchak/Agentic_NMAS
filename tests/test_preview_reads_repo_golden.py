"""Template preview must read the golden from the REPO, not the legacy store.

Measured on the demo path: the preview for `s1` reported "vs current golden
captured 2026-09-15 22:35" and a wall of differences, while
`config_repo/golden/s1.cfg` had been committed the same day.

    -rw-r--r-- 5819 2026-09-21_18:18:28  config_repo/golden/s1.cfg
    -rw-r--r-- 5980 2026-09-15_22:35:46  golden_configs/s1.cfg

`_captured_golden()` called `ai_assistant._list_golden_configs()`, which reads
`data/lists/<slug>/golden_configs/`. That store is a **read-only fallback**,
consulted only when the manifest has no entry for a device, and nothing has
written to it since migration — so the preview was pinned to the last
pre-migration save and drifted further every day.

The consequence was larger than a wrong date. `preview()` does
``source = golden or running``, so the stale text was also what the artifact
was BUILT from: the render, its coverage and its deployability were all
computed against a config the device had moved on from. The badges looked
right because s1 happened to still round-trip.
"""

import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

REPO_GOLDEN = """hostname s1
!
vtp mode transparent
!
lldp run
!
end
"""

LEGACY_GOLDEN = """hostname s1
!
no lldp run
!
end
"""


@pytest.fixture
def world(tmp_path, monkeypatch):
    """A list whose repo golden and legacy golden deliberately differ."""
    from modules.nsot import repo as _repo

    list_dir = tmp_path / "lab"
    (list_dir / "golden_configs").mkdir(parents=True)
    (list_dir / "golden_configs" / "s1.cfg").write_text(LEGACY_GOLDEN)

    monkeypatch.setattr("modules.config.get_list_data_dir",
                        lambda name: str(list_dir))
    monkeypatch.setattr("modules.config.get_current_list_name", lambda: "lab")
    monkeypatch.setattr("modules.settings_schema.get_setting",
                        lambda key, default=None: {
                            "nsot_git_author_name": "NMAS",
                            "nsot_git_author_email": "n@l",
                            "nsot_device_tag_retention": 50}.get(key, default))
    monkeypatch.setattr("modules.nsot.hooks.run_post_commit", lambda ctx: None)

    repo_dir = str(list_dir / "config_repo")
    _repo.init_repo(repo_dir)
    _repo.save_golden("lab", [_repo.GoldenItem("s1", REPO_GOLDEN, "10.0.0.14")],
                      source="test", actor="test", allow_new=True)
    return {"list_dir": list_dir, "repo": repo_dir}


class TestItReadsTheRepoNotTheLegacyStore:
    def test_the_two_stores_really_differ(self, world):
        """Without this the test could pass by reading either one."""
        legacy = (world["list_dir"] / "golden_configs" / "s1.cfg").read_text()
        assert "no lldp run" in legacy
        assert "no lldp run" not in REPO_GOLDEN

    def test_the_repo_version_is_returned(self, world):
        from routes.templates import _captured_golden

        content, _stamp = _captured_golden("s1", "lab")
        assert content is not None
        assert "vtp mode transparent" in content
        assert "no lldp run" not in content, (
            "this is the legacy golden_configs/ copy")

    def test_the_timestamp_comes_from_the_commit(self, world):
        """Not the file's mtime. In this repository the commit IS the record:
        the `! Saved:` header was removed so a save would not produce a diff
        on every write."""
        from routes.templates import _captured_golden

        _content, stamp = _captured_golden("s1", "lab")
        assert stamp, "no capture date"
        assert stamp[:2] == "20", stamp

    def test_an_unknown_device_returns_nothing(self, world):
        from routes.templates import _captured_golden

        content, stamp = _captured_golden("never-seen", "lab")
        assert content is None and stamp == ""

    def test_it_does_not_call_the_legacy_reader(self):
        """Structural as well as behavioural: the behavioural test would
        still pass if a future edit re-added the fallback *after* the repo
        read, and that fallback is what drifted for six days."""
        import ast
        import inspect
        import textwrap

        from routes import templates as route_module

        # The CODE, not the prose. The function's docstring explains at
        # length what it used to call, so a substring search over the source
        # matches the explanation and fails on the fix -- the same matcher
        # mistake as the break-glass key.key check.
        tree = ast.parse(textwrap.dedent(
            inspect.getsource(route_module._captured_golden)))
        body = tree.body[0].body
        if (body and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)):
            body = body[1:]
        code = "\n".join(ast.dump(node) for node in body)
        assert "_list_golden_configs" not in code
        assert "_load_golden_config_file" not in code
        assert "golden_at" in code

    def test_it_takes_the_list_rather_than_asking_which_is_active(self):
        """A function handed a list name must not go and read the active
        one. Three defects in this project had that shape."""
        import inspect

        from routes import templates as route_module

        assert "list_name" in inspect.signature(
            route_module._captured_golden).parameters


class TestBothSidesAreNormalisedTheWayRoundTripDoes:
    """`-!` for every separator is how a correct render reads as a broken one.

    The two filters do different jobs: `strip_for_roundtrip` removes what a
    template cannot render, `strip_for_diff` normalises for comparison and is
    the one that drops bare `!`. `roundtrip.configs_equivalent()` applies
    both; the preview applied only the first.
    """

    def test_bang_separators_survive_the_roundtrip_filter_alone(self):
        from modules.nsot.normalize import strip_for_roundtrip

        assert "!" in strip_for_roundtrip(REPO_GOLDEN), (
            "if this ever stops being true, the bug it caused is gone and so "
            "is the reason for the composition below")

    def test_the_composition_removes_them(self):
        from modules.nsot.normalize import strip_for_diff, strip_for_roundtrip

        lines = strip_for_diff("\n".join(strip_for_roundtrip(REPO_GOLDEN)))
        assert "!" not in lines

    def test_identical_configs_produce_no_diff_despite_separators(self):
        """The real symptom: a device matching its golden showed dozens of
        differences, every one of them a `!`."""
        import difflib

        from modules.nsot.normalize import strip_for_diff, strip_for_roundtrip

        spaced = "hostname s1\n!\n!\nvtp mode transparent\n!\nlldp run\n!\nend\n"
        tight = "hostname s1\nvtp mode transparent\nlldp run\nend\n"
        left = strip_for_diff("\n".join(strip_for_roundtrip(spaced)))
        right = strip_for_diff("\n".join(strip_for_roundtrip(tight)))
        assert list(difflib.unified_diff(left, right, lineterm="")) == []

    def test_the_route_applies_both(self):
        """Through `canonical_diff` now, but both must still be applied.

        The preview delegates to `roundtrip.canonical_diff()`, so the
        composition moved rather than disappearing -- and it is checked where
        it now lives. Dropping `strip_for_roundtrip` when the preview moved
        over would have made every unrenderable line in the capture read as a
        difference from a render that could never have contained it; this
        test caught exactly that.
        """
        import inspect

        from modules.nsot import roundtrip
        from routes import templates as route_module

        assert "canonical_diff" in inspect.getsource(route_module.preview)
        composed = inspect.getsource(roundtrip.canonical_lines)
        assert "strip_for_diff" in composed and "strip_for_roundtrip" in composed
