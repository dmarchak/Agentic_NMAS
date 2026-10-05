"""C104: nothing commits into the network's repository except the operation
that wrote it, and a failed commit leaves nothing behind.

Measured 2026-09-27 before the fix: a `save_golden()` whose commit failed
returned `ok: False, changed: []` with the golden it had written still on disk
AND staged; the Git tab's manual commit then committed it under whatever
message was typed ("tidy up"), `Source: manual`, with no Intent-Match
trailer, no Device-Id, no tag and no push. The manual commit is removed (never
used on the host, in 100 commits); each writer undoes what it wrote when its
commit fails; the status bar names anything left uncommitted and what to do.
"""

import ast
import json
import os
import subprocess

import dukpy
import pytest

from modules.nsot import repo as R

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
        assert any(rule.startswith("/git/commit/") for rule, _m in rules), (
            "the commit DIFF view stays; a floor that the scan saw the git routes")

    def test_no_page_offers_it(self):
        from tests.js_source import read_shipped
        page = read_shipped("templates/index.html")
        assert "gitCommitCard" not in page and "gitDoCommit" not in page
        # The request itself, not only the names around it: the first removal
        # cut the function at an inner `};` and left its fetch behind, which
        # the name checks passed and the page's parse check caught.
        assert "'/git/commit'" not in page and '"/git/commit"' not in page
        assert "_renderGitStatus" in page


class TestTheStatusNamesWhatIsLeft:
    def test_an_uncommitted_golden_is_reported_with_its_remedy(self, lab):
        from modules import config_git
        path = _seed(lab)
        with open(path, "a") as fh:
            fh.write(" edited on the host\n")
        st = config_git.get_repo_status("lab")
        assert st["ok"] and st["uncommitted"], st
        row = st["uncommitted"][0]
        assert row["path"] == "golden/r1.cfg"
        assert "Capture the device" in row["means"]

    def test_clean_is_clean(self, lab):
        from modules import config_git
        _seed(lab)
        assert config_git.get_repo_status("lab")["uncommitted"] == []

    def _render(self, payload):
        from tests.js_source import read_shipped
        from tests.payload_render import lift
        page = read_shipped("templates/index.html")
        js = """
        var els = {gitStatusBar: {className: '', classList: {remove: function () {}}},
                   gitStatusText: {textContent: '', innerHTML: ''}};
        var document = {getElementById: function (id) { return els[id] || null; }};
        """ + lift(page, "escHtml") + "\n" + lift(page, "gitLevel") + "\n" + lift(page, "_renderGitStatus") + f"""
        _renderGitStatus({json.dumps(payload)});
        [els.gitStatusBar.className, els.gitStatusText.innerHTML || els.gitStatusText.textContent];
        """
        return dukpy.evaljs(js)

    def test_the_shipped_bar_draws_each_path_and_what_it_means(self):
        cls, html = self._render({"initialised": True, "ok": True, "last_commit": "abc",
                                  "uncommitted": [{"path": "golden/r1.cfg", "state": "M",
                                                   "means": "Capture the device"}]})
        assert "alert-warning" in cls
        assert "golden/r1.cfg" in html and "Capture the device" in html
        assert "Nothing on this page commits them" in html

    def test_the_bar_never_says_clean_over_an_uncommitted_path(self):
        _cls, html = self._render({"initialised": True, "ok": True,
                                   "uncommitted": [{"path": "golden/r1.cfg", "state": "M",
                                                    "means": "x"}]})
        assert "committed." not in html.split("uncommitted")[0]
        # Green needs the remote too since C223: committed AND pushed.
        cls, html = self._render({"initialised": True, "ok": True, "last_commit": "abc",
                                  "uncommitted": [], "publication": {
                                      "level": "success", "state": "in_sync",
                                      "clause": "and pushed to a/b", "detail": ""}})
        assert "alert-success" in cls and "Everything is committed" in html

    def test_a_status_that_could_not_be_read_says_so(self):
        cls, html = self._render({"initialised": True, "ok": False,
                                  "error": "could not read the repository's status: x"})
        assert "alert-danger" in cls and "could not read" in html


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
        files = ["app.py"] + [os.path.join(d, f) for base in ("modules", "routes", "scripts")
                              for d, _s, fs in os.walk(os.path.join(ROOT, base)) for f in fs]
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
