"""C931: every git call on a list's repository is pinned to THAT repository.

A network created on v2 had a `config_repo` folder with no `.git`, and a git command run in a
folder that is not a repository climbs to the first parent that is one. On the host `data/`
sits inside the application's checkout, so Seed's `git status` read the APPLICATION's status
(clean: `data/` is ignored there), found nothing untracked, committed nothing and said "the
network had every shipped file". Measured here with a planted parent repository, 2026-10-16: a
status read the parent, `repo.commit()` committed into the parent and a tag landed there; the
post-commit hooks' `changed_paths` and the archive's `committed_bytes` read the parent's
commits as the list's.

What is held:

- `repo.run_git` (and so `repo.git`, `git_raw`) pins git to the folder it is given
  (`GIT_CEILING_DIRECTORIES` at its parent, the repository-local variables a caller's
  environment carries removed): in a folder with no `.git` inside a parent repository, a read
  fails naming the folder and a write lands nowhere; the parent's HEAD, index, status and tags
  are unchanged. Each module that had its own git subprocess on a list's repository is driven
  the same way;
- an inherited `GIT_DIR` (a git hook's) never redirects a list's git;
- THE SHAPE, by parsing: no git argument list is built anywhere in the program or its scripts
  except inside `repo.run_git`, or at a site declared below with its reason (the application's
  own checkout, a URL with no repository, a pinned seam). An AST scan with a floor, and a
  planted unpinned call that it finds.
"""

import ast
import os
import subprocess

import pytest

from tests.test_every_commit_publishes import _enclosing, _parse, _program_files, _rel

#: THE pinned runner: the one place a git argument list for a list's repository is built.
CHOKEPOINT = ("modules/nsot/repo.py", "run_git")

#: Every other git argument list in the program and its scripts, with why it is not a list's
#: repository through `run_git`. Each must still be found by the scan (no ghosts).
DECLARED = {
    # A pinned seam: the argument list is built here and pinned by the seam's own `pin=`.
    ("modules/nsot/remote.py", "_git"): (
        "pinned through `_run(pin=repo_dir)`, which applies `repo.pinned_env`; `_run` is the "
        "one seam this module's tests replace"),
    # No repository at all: a URL.
    ("modules/nsot/remote.py", "check_read"): "`git ls-remote <url>`: a URL, no repository",
    ("modules/nsot/remote.py", "check_right_repository"): (
        "the APPLICATION's own checkout root, asked its origin to refuse it as a list's remote; "
        "and `git ls-remote <url>`, a URL"),
    ("modules/nsot/remote.py", "_push_locked"): "`git ls-remote <url>` before and after: a URL",
    # The application's own checkout, which is located by being the checkout.
    ("modules/nsot/templates_repo.py", "_git_ro"): (
        "the APPLICATION's checkout (the shipped templates' history, found by "
        "`rev-parse --show-toplevel` from the shipped folder, which must climb), and "
        "`hash-object --no-filters` of a file, which reads no repository's content; a list's "
        "repository is read through `_git_list_repo`"),
    ("modules/host_steps.py", "_log"): "the APPLICATION's checkout (the running history)",
    ("modules/job_health.py", "version_rows"): "the APPLICATION's checkout (its HEAD)",
    ("routes/health.py", "_commit_loaded"): "the APPLICATION's checkout (its HEAD)",
    ("routes/v2.py", "_subject"): "the APPLICATION's checkout (a release's subject)",
    ("scripts/check_removed_definitions.py", "_git"): "the APPLICATION's checkout (the diff)",
    ("scripts/nmas_coverage.py", "measured_files"): "the APPLICATION's checkout",
    ("scripts/nmas_mutation.py", "reach_fresh"): "the APPLICATION's checkout",
    ("scripts/nmas_mutation.py", "git"): "the APPLICATION's checkout",
    ("scripts/nmas_mutation.py", "read"): "the APPLICATION's checkout",
    ("scripts/nmas_mutation.py", "_commit_times"): "the APPLICATION's checkout",
    ("scripts/nmas_mutation.py", "moved_from"): "the APPLICATION's checkout",
    ("scripts/nmas-gate", "git"): "the APPLICATION's checkout (the developer's gate)",
    ("scripts/nmas-gate", "main"): "the APPLICATION's checkout (the developer's gate)",
    ("scripts/nmas-stage-guard", "_git"): "the APPLICATION's checkout (what is staged)",
    ("scripts/nmas-shards", "changed_paths"): "the APPLICATION's checkout (a pushed range)",
    ("scripts/nmas-deploy", "git"): "the APPLICATION's checkout on the host",
    ("scripts/nmas-deploy", "read"): "the APPLICATION's checkout on the host",
    ("scripts/nmas-deploy", "offline_verdict"): "the APPLICATION's checkout on the host",
    ("scripts/nmas-deploy", "_deploy"): "the APPLICATION's checkout on the host",
    ("scripts/nmas-ci-dispatch", "_repo_slug"): "the APPLICATION's checkout (its origin)",
    ("scripts/nmas-ci-log", "_repo_slug"): "the APPLICATION's checkout (its origin)",
    ("scripts/nmas-host-step-check", "git"): "the APPLICATION's checkout (a commit range)",
    ("scripts/nmas-test-weakening-check", "git"): (
        "the APPLICATION's checkout (a commit range, or the commit being made)"),
    # Not a command at all.
    ("modules/nsot/remote.py", "check_private"): (
        "a label: `(\"git\", <the smart-HTTP URL>)` names an endpoint asked over HTTPS"),
    # A list's repository, from a script that may run against an older checkout.
    ("scripts/nmas-config-read", "main"): (
        "the fallback when the checkout it runs against predates `repo.run_git` (it is sent "
        "to a host over stdin and imports that host's checkout); otherwise `run_git`"),
}


def git_argument_lists(tree):
    """Every list or tuple literal whose first element is the string "git"."""
    return [n for n in ast.walk(tree)
            if isinstance(n, (ast.List, ast.Tuple)) and n.elts
            and isinstance(n.elts[0], ast.Constant) and n.elts[0].value == "git"]


@pytest.fixture(scope="module")
def sites():
    found = {}
    for path in _program_files():
        tree = _parse(path)
        for node in git_argument_lists(tree):
            found.setdefault((_rel(path), _enclosing(tree, node).split(".")[-1]), []).append(
                node.lineno)
    return found


class TestTheShape:
    def test_the_scan_has_a_population(self, sites):
        # Floor: measured 2026-10-16, 35 git argument lists at 29 sites (the chokepoint and
        # the 28 declared); a scan that stopped reading scripts or nested functions falls below.
        assert CHOKEPOINT in sites, "the scan does not see the one runner"
        assert sum(len(v) for v in sites.values()) >= 30, sites

    def test_no_git_argument_list_outside_the_runner_undeclared(self, sites):
        stray = {k: v for k, v in sites.items() if k != CHOKEPOINT and k not in DECLARED}
        assert not stray, (
            "git is run outside `repo.run_git` at " + "; ".join(
                f"{f}:{fn or '<module>'} line(s) {lines}" for (f, fn), lines in stray.items())
            + ". A list's repository goes through run_git (pinned to it, C931); anything else "
            "is declared in DECLARED with why it is not a list's repository")

    def test_every_declared_site_is_still_there(self, sites):
        assert not [k for k in DECLARED if k not in sites], "a declared site no longer exists"

    def test_a_planted_unpinned_call_is_found(self):
        tree = ast.parse("import subprocess\n"
                         "def status(repo):\n"
                         "    return subprocess.run(['git', '-C', repo, 'status'])\n")
        nodes = git_argument_lists(tree)
        assert len(nodes) == 1 and _enclosing(tree, nodes[0]) == "status"


# ---------------------------------------------------------------------------
# For real: a folder with no .git inside a parent repository.
# ---------------------------------------------------------------------------

def _sh(cwd, *args):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    p = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, env=env)
    return p.returncode, p.stdout.strip(), p.stderr.strip()


@pytest.fixture
def nested(tmp_path, monkeypatch):
    """A parent repository (the application's checkout, its store ignored) holding a list
    folder with no `.git`."""
    parent = tmp_path / "checkout"
    child = parent / "store" / "lists" / "net" / "config_repo"
    child.mkdir(parents=True)
    _sh(parent, "init", "-q", "-b", "main")
    (parent / ".gitignore").write_text("store/\n")
    (parent / "README").write_text("the application\n")
    _sh(parent, "add", ".gitignore", "README")
    _sh(parent, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", "app")
    monkeypatch.setattr("modules.settings_schema.get_setting",
                        lambda key, default=None: default)
    monkeypatch.setattr("modules.nsot.hooks.run_post_commit", lambda ctx: None)
    (child / "templates").mkdir()
    (child / "templates" / "base.j2").write_text("hostname {{ hostname }}\n")

    def state():
        return {"head": _sh(parent, "rev-parse", "HEAD")[1],
                "log": _sh(parent, "log", "--oneline", "--all")[1],
                "index": _sh(parent, "ls-files", "--stage")[1],
                "status": _sh(parent, "status", "--porcelain", "--ignored")[1],
                "tags": _sh(parent, "tag", "-l")[1],
                "notes": _sh(parent, "notes", "list")[1]}
    return {"parent": parent, "child": str(child), "state": state, "before": state(),
            "sha": _sh(parent, "rev-parse", "HEAD")[1]}


class TestARepositoryLessFolderNeverReachesItsParent:
    def test_a_read_fails_naming_the_folder(self, nested):
        from modules.nsot import repo as R
        rc, out, err = R.git(nested["child"], "status", "--porcelain")
        assert rc != 0 and out == ""
        assert f"{nested['child']} is not a git repository (it has no .git)" in err
        rc, top, _err = R.git(nested["child"], "rev-parse", "--show-toplevel")
        assert rc != 0 and top == "", "git found the parent's top level"

    def test_a_commit_and_a_tag_land_nowhere(self, nested):
        from modules.nsot import repo as R
        with R.repo_lock(nested["child"]):
            rc, sha, err = R.commit(nested["child"], "C931 planted\n", allow_empty=True,
                                    publish_now=False)
        assert rc != 0 and sha == "" and "not a git repository" in err
        assert R.git(nested["child"], "tag", "c931-planted")[0] != 0
        assert R.git(nested["child"], "add", "-f", "templates/base.j2")[0] != 0
        assert nested["state"]() == nested["before"], "the parent repository was written"

    def test_each_module_with_its_own_git_reads_nothing_of_the_parent(self, nested):
        from modules import config_git, network_admin
        from modules.nsot import archive, config_check, hooks, remote, templates_repo
        from modules.readers import remote_publication
        child, sha = nested["child"], nested["sha"]
        assert config_git._git(child, "rev-parse", "--show-toplevel")[0] != 0
        assert remote_publication._git(child, "rev-parse", "--show-toplevel")[0] != 0
        assert templates_repo._git_list_repo(child, "rev-parse", "--show-toplevel")[0] != 0
        assert remote._git(child, "rev-parse", "--show-toplevel").returncode != 0
        assert remote._have_commit(child, sha) is False, "the parent's commit read as the list's"
        assert archive.committed_bytes(child, sha, "README") is None
        paths, error = hooks.changed_paths({"repo": child, "sha": sha})
        assert paths == [] and error, "the parent's commit read as the list's"
        assert config_check.touched_paths(child, ["templates/base.j2"]) == []
        assert network_admin._git_count(child, "rev-list", "--count", "HEAD") == 0
        assert nested["state"]() == nested["before"]

    def test_an_inherited_git_dir_never_redirects_a_lists_git(self, nested, monkeypatch, tmp_path):
        """A git hook exports GIT_DIR and GIT_INDEX_FILE for ITS repository; a list's git run
        under one (a suite or a CLI started from a hook) must still answer for the list."""
        from modules.nsot import repo as R
        own = tmp_path / "own"
        R.init_repo(str(own))
        monkeypatch.setenv("GIT_DIR", str(nested["parent"] / ".git"))
        monkeypatch.setenv("GIT_INDEX_FILE", str(nested["parent"] / ".git" / "index"))
        rc, top, _err = R.git(str(own), "rev-parse", "--show-toplevel")
        assert rc == 0 and os.path.realpath(top) == os.path.realpath(own)
        rc, _out, _err = R.git(nested["child"], "status")
        assert rc != 0, "GIT_DIR made a folder with no .git read as the parent"
        assert nested["state"]() == nested["before"]
