"""C104: nothing commits into the network's repository except the operation
that wrote it, and a failed commit leaves nothing behind.

Measured 2026-09-27 before the fix: a `save_golden()` whose commit failed
returned `ok: False, changed: []` with the golden it had written still on disk
AND staged; the Git tab's manual commit then committed it under whatever
message was typed ("tidy up"), `Source: manual`, with no Intent-Match
trailer, no Device-Id, no tag and no push. The manual commit is removed (never
used on the host, in 100 commits); each writer undoes what it wrote when its
commit fails; History's header names anything left uncommitted (today's Git tab's
status bar did, with what to do, until it left at 7.8, 2026-10-17).
"""

import ast
import json
import os
import subprocess

import pytest

from modules.nsot import repo as R
from tests.source_index import tracked

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def lab(tmp_path, monkeypatch, intent_matches):
    monkeypatch.setattr("modules.settings_schema.get_setting",
                        lambda key, default=None: {
                            "nsot_git_author_name": "NMAS",
                            "nsot_git_author_email": "nmas@localhost",
                            "nsot_device_tag_retention": 50,
                        }.get(key, default))
    monkeypatch.setattr("modules.config.LISTS_DIR", str(tmp_path))
    list_dir = tmp_path / "lab"
    list_dir.mkdir()
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(list_dir))
    monkeypatch.setattr("modules.nsot.hooks.run_post_commit", lambda ctx: None)
    return str(list_dir / "config_repo")


def _g(repo, *a):
    return subprocess.run(["git", "-C", repo, *a], capture_output=True,
                          text=True).stdout


def _refuse_commits(repo):
    """A pre-commit hook that refuses: the commit fails AFTER the files are
    written and staged, which is the window the defect lived in."""
    hook = os.path.join(repo, ".git", "hooks", "pre-commit")
    with open(hook, "w") as fh:
        fh.write("#!/bin/sh\necho refused-by-hook >&2\nexit 1\n")
    os.chmod(hook, 0o755)
    return hook


def _seed(lab):
    out = R.save_golden("lab", [R.GoldenItem("r1", "hostname r1\n", "203.0.113.1", platform="cisco_ios")],
                        allow_new=True)
    assert out["ok"], out
    return os.path.join(lab, "golden", "r1.cfg")


class TestAFailedSaveLeavesNothing:
    def test_an_existing_golden_is_put_back_and_nothing_is_staged(self, lab):
        path = _seed(lab)
        committed = open(path, "rb").read()
        _refuse_commits(lab)
        out = R.save_golden("lab", [R.GoldenItem("r1", "hostname r1\n changed\n",
                                                 "203.0.113.1", platform="cisco_ios")])
        assert out["ok"] is False and "refused-by-hook" in out["error"]
        assert _g(lab, "diff", "--cached", "--name-only") == ""
        assert open(path, "rb").read() == committed
        assert _g(lab, "status", "--porcelain", "--", "golden") == ""

    def test_a_new_golden_is_removed(self, lab):
        _seed(lab)
        _refuse_commits(lab)
        out = R.save_golden("lab", [R.GoldenItem("r2", "hostname r2\n", "203.0.113.2", platform="cisco_ios")],
                            allow_new=True)
        assert out["ok"] is False
        assert not os.path.exists(os.path.join(lab, "golden", "r2.cfg"))
        assert _g(lab, "diff", "--cached", "--name-only") == ""

    def test_the_control_a_successful_save_still_commits(self, lab):
        path = _seed(lab)
        out = R.save_golden("lab", [R.GoldenItem("r1", "hostname r1\n changed\n",
                                                 "203.0.113.1", platform="cisco_ios")])
        assert out["ok"] and out["changed"]
        assert "changed" in open(path).read()
        assert "Intent-Match:" in _g(lab, "log", "-1", "--format=%B")


class TestAFailedRenameStaysPending:
    def test_the_move_and_the_manifest_are_put_back(self, lab):
        from modules.nsot import manifest as M
        _seed(lab)
        identity = next(iter(json.load(open(M.manifest_path(lab)))["devices"]))
        M.record_pending_rename(lab, identity, "r1-new")
        _refuse_commits(lab)
        out = R.apply_pending_renames(lab)
        assert out["renamed"] == []
        assert os.path.exists(os.path.join(lab, "golden", "r1.cfg"))
        assert not os.path.exists(os.path.join(lab, "golden", "r1-new.cfg"))
        assert _g(lab, "diff", "--cached", "--name-only") == ""
        assert M.pending_renames(lab), "the rename must stay pending, to retry alone"


class TestTheManualCommitIsGone:
    def test_the_route_is_not_served(self, monkeypatch):
        import app as app_module
        rules = {(r.rule, m) for r in app_module.app.url_map.iter_rules()
                 for m in r.methods}
        assert ("/git/commit", "POST") not in rules
        # The commit view stays, on v2 (today's /git/commit/<sha> left with the Git tab at 7.8,
        # 2026-10-17): a floor that the scan saw the routes.
        assert any(rule.startswith("/v2/history/commit/") for rule, _m in rules)

    def test_no_page_offers_it(self):
        """No template of either interface asks for a manual commit; History's header is where
        a path left uncommitted is said (today's Git tab's status bar said it until 7.8)."""
        from tests.source_index import tracked as _tracked
        pages = [p for p in _tracked("templates", suffix=".html")]
        assert len(pages) > 50 and any(p.endswith("_history_remote.html") for p in pages)
        for path in pages:
            page = open(os.path.join(ROOT, path) if not os.path.isabs(path) else path,
                        encoding="utf-8").read()
            assert "gitDoCommit" not in page and "'/git/commit'" not in page, path
            assert '"/git/commit"' not in page, path


class TestTheStatusNamesWhatIsLeft:
    """History's header (`routes/v2._history_remote`), driven on the real repository: what is
    left uncommitted is named, and the remote's sentence is never "in sync" beside it. Today's
    Git tab's status bar named each path with what it meant until it left at 7.8 (2026-10-17);
    the header names the paths, not yet what each means (the removal's report)."""

    @staticmethod
    def _header(lab, monkeypatch):
        import types

        import app as A
        from modules.nsot import remote as NR
        from modules.readers import remote_publication as RP
        from routes.v2 import _history_remote

        monkeypatch.setattr(RP, "status_for", lambda name: {"state": "in_sync",
                                                             "remote": "a/b"})
        monkeypatch.setattr(NR, "config_or_refusal", lambda name: ({}, ""))
        with A.app.test_request_context("/v2/history"):
            return _history_remote(types.SimpleNamespace(name="lab", repo_dir=lab))

    def test_an_uncommitted_golden_is_named(self, lab, monkeypatch):
        path = _seed(lab)
        with open(path, "a") as fh:
            fh.write(" edited on the host\n")
        h = self._header(lab, monkeypatch)
        assert h["dirty"] == 1 and h["dirty_paths"] == ["golden/r1.cfg"], h
        assert h["d"]["state"] == "uncommitted" and h["d"]["level"] == "warning", h["d"]

    def test_clean_is_clean(self, lab, monkeypatch):
        _seed(lab)
        h = self._header(lab, monkeypatch)
        assert h["dirty"] == 0 and h["dirty_paths"] == [] and h["d"]["state"] == "in_sync"

    def test_a_status_that_could_not_be_read_says_so(self, lab, monkeypatch):
        _seed(lab)
        monkeypatch.setattr(R, "git", lambda repo, *a, **k: (128, "", "fatal: x"))
        h = self._header(lab, monkeypatch)
        assert h["dirty"] is None and "fatal: x" in h["unreadable"], h


class TestTheSourceIsRecordedAsGiven:
    def test_rotation_is_recorded_as_rotation(self, lab):
        _seed(lab)
        out = R.save_golden("lab", [R.GoldenItem("r1", "hostname r1\n x\n", "203.0.113.1", platform="cisco_ios")],
                            source="rotation")
        assert out["ok"], out
        assert "Source: rotation" in _g(lab, "log", "-1", "--format=%B")

    def test_a_malformed_source_is_refused_before_anything_is_written(self, lab):
        path = _seed(lab)
        before = open(path, "rb").read()
        out = R.save_golden("lab", [R.GoldenItem("r1", "hostname r1\n y\n", "203.0.113.1", platform="cisco_ios")],
                            source="Not A Slug")
        assert out["ok"] is False and "nothing was saved" in out["error"]
        assert open(path, "rb").read() == before

    def test_every_literal_source_in_the_program_is_a_slug(self):
        """A coercion is invisible at the call site, so the population is every
        save_golden call in the program, with a floor."""
        found = []
        files = ["app.py"] + tracked("modules", "routes", "scripts")
        for path in files:
            full = path if os.path.isabs(path) else os.path.join(ROOT, path)
            try:
                tree = ast.parse(open(full, encoding="utf-8").read())
            except (SyntaxError, UnicodeDecodeError):
                continue
            for n in ast.walk(tree):
                if isinstance(n, ast.Call) and getattr(
                        n.func, "attr", getattr(n.func, "id", "")) == "save_golden":
                    for kw in n.keywords:
                        if kw.arg == "source":
                            for c in ast.walk(kw.value):
                                if isinstance(c, ast.Constant) and isinstance(c.value, str):
                                    found.append(c.value)
        assert len(found) >= 7 and "rotation" in found, found
        bad = [s for s in found if not R.SOURCE_SLUG.match(s)]
        assert not bad, bad


class TestAbandonCommitsOnlyItsPath:
    def test_the_abandon_step_stages_one_path(self):
        src = open(os.path.join(ROOT, "modules", "nsot", "onboard.py"),
                   encoding="utf-8").read()
        tree = ast.parse(src)
        adds = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                and any(isinstance(a, ast.Constant) and a.value == "add" for a in n.args)]
        assert adds, "the scan found no git add in onboard.py"
        for call in adds:
            consts = [a.value for a in call.args if isinstance(a, ast.Constant)]
            assert "--" in consts, f"line {call.lineno}: a git add with no pathspec"
