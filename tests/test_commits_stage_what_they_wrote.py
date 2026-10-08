"""C175: a commit stages exactly the files it wrote, never a tree.

C104 made every READER take what is committed. The WRITERS still ran
`git add -A host_vars` (or `golden`, `templates`, `.nsot`), so another
device's uncommitted hand edit was committed under an unrelated commit's
subject, `Actor:` and `Source:`, and the deploy then read it as committed
intent and SENT it: the same defect from the other end. Measured on the host
2026-09-28, read-only: 102 commits, none yet carrying a file for a device it
does not name (a probe that found a planted one), while four hand commits of
intent on 09-24 show the trigger is practice.

Each writer is driven here with another device's edit on disk (and, for the
index, staged by hand), and the edit must stay out of its commit.
"""

import ast
import os
import subprocess

import pytest

from tests.source_index import tracked
from tests.test_intent_match import R2
from tests.test_seed_intent import LIST, build_seed_lab

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True,
                          text=True).stdout.strip()


def _files(repo, sha):
    return sorted(_git(repo, "show", "--name-only", "--format=", sha).split())


@pytest.fixture
def lab(tmp_path, monkeypatch):
    """r2 (golden, bootstrap intent) and s1 (golden, intent, a template edit
    of its own), all committed; then s1's files EDITED and left on disk."""
    from modules.nsot.repo import GoldenItem, save_golden, save_host_vars, save_templates

    lab = build_seed_lab(monkeypatch, tmp_path)
    repo = lab["repo"]
    save_golden(LIST, [GoldenItem("s1", "hostname s1\ninterface Vlan1\n", "203.0.113.21",
                                  platform="cisco_ios")],
                source="capture", actor="t", allow_new=True, baseline=False)
    with open(os.path.join(repo, "host_vars", "s1.yml"), "w", encoding="utf-8") as fh:
        fh.write("hostname: s1\ninterfaces: []\n")
    assert save_host_vars(LIST, ["s1"], actor="t")["ok"]
    for rel, text in (("host_vars/s1.yml", "description: an unreviewed edit\n"),
                      ("golden/s1.cfg", "banner motd ^an unreviewed edit^\n")):
        with open(os.path.join(repo, rel), "a", encoding="utf-8") as fh:
            fh.write(text)
    lab["planted"] = ["golden/s1.cfg", "host_vars/s1.yml"]
    lab["save_templates"] = save_templates
    return lab


def _still_uncommitted(lab):
    status = _git(lab["repo"], "status", "--porcelain")
    return all(p in status for p in lab["planted"])


def _locked_stage(repo, paths):
    """Staging is refused outside the repository lock (R1): every real caller holds it."""
    from modules.nsot.repo import repo_lock, stage_exactly

    with repo_lock(repo):
        return stage_exactly(repo, paths)


class TestStageExactly:
    @pytest.mark.parametrize("tree", ["golden", "host_vars", "templates", ".nsot", "golden/"])
    def test_a_tree_is_refused(self, lab, tree):
        from modules.nsot.repo import StagesMoreThanItWrote, stage_exactly

        with pytest.raises(StagesMoreThanItWrote, match="directory"):
            _locked_stage(lab["repo"], [tree])

    def test_any_directory_is_refused(self, lab):
        from modules.nsot.repo import StagesMoreThanItWrote, stage_exactly

        with pytest.raises(StagesMoreThanItWrote):
            _locked_stage(lab["repo"], ["templates/cisco_ios"])

    def test_a_path_staged_by_hand_refuses_and_is_left_staged(self, lab):
        from modules.nsot.repo import StagesMoreThanItWrote, stage_exactly

        _git(lab["repo"], "add", "--", "host_vars/s1.yml")
        with pytest.raises(StagesMoreThanItWrote, match="host_vars/s1.yml"):
            _locked_stage(lab["repo"], ["host_vars/r2.yml"])
        assert _git(lab["repo"], "diff", "--cached", "--name-only") == "host_vars/s1.yml"


class TestEveryWriterCommitsOnlyItsOwn:
    def test_an_intent_commit(self, lab):
        from modules.nsot.repo import save_host_vars

        with open(os.path.join(lab["repo"], "host_vars", "r2.yml"), "a",
                  encoding="utf-8") as fh:
            fh.write("# an edit to r2\n")
        out = save_host_vars(LIST, ["r2"], actor="t")
        assert out["ok"] and _files(lab["repo"], out["commit"]) == ["host_vars/r2.yml"]
        assert _still_uncommitted(lab)

    def test_a_golden_commit(self, lab):
        from modules.nsot.repo import GoldenItem, save_golden

        text = open(R2, encoding="utf-8").read() + "\n! a later capture\n"
        out = save_golden(LIST, [GoldenItem("r2", text.replace("hostname r2",
                                                               "hostname r2\nbanner exec ^x^"),
                                            "203.0.113.12", platform="cisco_iosxe")],
                          source="capture", actor="t", allow_new=False, baseline=False)
        assert out["ok"] and "golden/r2.cfg" in _files(lab["repo"], out["commit"])
        assert set(_files(lab["repo"], out["commit"])) <= {"golden/r2.cfg", ".nsot/manifest.json"}
        assert _still_uncommitted(lab)

    def test_a_golden_commit_carrying_intent_carries_only_that_intent(self, lab):
        """The restore and rotation path: intent named by FILE."""
        from modules.nsot.repo import GoldenItem, save_golden

        with open(os.path.join(lab["repo"], "host_vars", "r2.yml"), "a",
                  encoding="utf-8") as fh:
            fh.write("# restored\n")
        out = save_golden(LIST, [GoldenItem("r2", open(R2, encoding="utf-8").read(),
                                            "203.0.113.12", platform="cisco_iosxe")],
                          source="restore", actor="t", allow_new=False, baseline=False,
                          extra_paths=["host_vars/r2.yml"])
        assert out["ok"] and "host_vars/r2.yml" in _files(lab["repo"], out["commit"])
        assert _still_uncommitted(lab)

    def test_a_template_commit(self, lab):
        path = os.path.join(lab["repo"], "templates", "cisco_ios", "base.j2")
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("{# an unreviewed template edit #}\n")
        bindings = os.path.join(lab["repo"], "templates", "bindings.yml")
        with open(bindings, "a", encoding="utf-8") as fh:
            fh.write("# bindings edit\n")
        out = lab["save_templates"](LIST, ["bindings.yml"], actor="t")
        assert out["ok"] and _files(lab["repo"], out["commit"]) == ["templates/bindings.yml"]
        assert "templates/cisco_ios/base.j2" in _git(lab["repo"], "status", "--porcelain",
                                                     "-uall")

    def test_a_rename_commit(self, lab):
        from modules.nsot import manifest as _m
        from modules.nsot.repo import apply_pending_renames

        ident = _m.find_by_name(lab["repo"], "r2")[0]
        _m.record_pending_rename(lab["repo"], ident, "r2-new")
        out = apply_pending_renames(lab["repo"], actor="t")
        assert out["renamed"], out
        files = _files(lab["repo"], "HEAD")
        assert set(files) <= {"golden/r2.cfg", "golden/r2-new.cfg", ".nsot/manifest.json"}
        assert _still_uncommitted(lab)

    def test_a_seed(self, lab):
        d = lab["client"].post("/templatize/seed/preview",
                               json={"list_name": LIST, "devices": ["r2"]}).get_json()
        h = d["preview"]["what"]["targets"][0]["select_data"]["hash"]
        out = lab["client"].post("/templatize/seed/apply", json={
            "list_name": LIST, "confirmations": {"r2": h}}).get_json()
        assert out["result"]["targets"][0]["outcome"] == "seeded"
        assert _files(lab["repo"], "HEAD") == ["host_vars/r2.yml"]
        assert _still_uncommitted(lab)

    def test_a_hand_staged_path_refuses_the_commit_and_names_it(self, lab):
        from modules.nsot.repo import save_host_vars

        head = _git(lab["repo"], "rev-parse", "HEAD")
        _git(lab["repo"], "add", "--", "golden/s1.cfg")
        out = save_host_vars(LIST, ["r2"], actor="t")
        assert out["ok"] is False and "golden/s1.cfg" in out["error"]
        assert _git(lab["repo"], "rev-parse", "HEAD") == head


#: The one declared exception: the migration's first commit, one-shot and
#: guarded by `.nsot/migrated.json`, commits the legacy store's files whole.
DECLARED = {"modules/nsot/migrate.py"}
TREES = {"golden", "host_vars", "templates", ".nsot", "intended", "infra"}
WRITERS = {"_commit_paths", "save_golden", "save_templates", "save_host_vars", "stage_exactly"}


def _tree_staging(src: str) -> list:
    """Each `git(..., "add", ..., <tree>)` and each writer call passing a
    tree literal (positionally or as `paths=` / `extra_paths=`)."""
    found = []
    for node in ast.walk(ast.parse(src)):
        # A path list built first and passed later: restore built
        # `extra_paths = ["host_vars"]` and handed over the name, which a scan
        # of call literals alone did not see (its control passed).
        if isinstance(node, ast.Assign) and isinstance(node.value, (ast.List, ast.Tuple)):
            names = {getattr(t, "id", "") for t in node.targets}
            if names & {"paths", "extra_paths"}:
                for e in node.value.elts:
                    if isinstance(e, ast.Constant) and str(e.value).rstrip("/") in TREES:
                        found.append((node.lineno, f"{sorted(names)[0]} = [... {e.value!r} ...]"))
        if not isinstance(node, ast.Call):
            continue
        fn = getattr(node.func, "attr", getattr(node.func, "id", ""))
        strs = [a.value for a in node.args if isinstance(a, ast.Constant)
                and isinstance(a.value, str)]
        if fn == "git" and "add" in strs and TREES & {s.rstrip("/") for s in strs}:
            found.append((node.lineno, "git add " + " ".join(strs)))
        if fn in WRITERS:
            lists = [a for a in node.args if isinstance(a, (ast.List, ast.Tuple))]
            lists += [k.value for k in node.keywords
                      if k.arg in ("paths", "extra_paths") and isinstance(k.value, (ast.List, ast.Tuple))]
            for lst in lists:
                for e in lst.elts:
                    if isinstance(e, ast.Constant) and str(e.value).rstrip("/") in TREES:
                        found.append((node.lineno, f"{fn}(... {e.value!r} ...)"))
    return found


def _sources():
    for top in ("modules", "routes", "scripts"):
        for path in tracked(top):
            f = os.path.basename(path)
            rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
            if f.endswith(".py") or (top == "scripts" and "." not in f):
                try:
                    text = open(path, encoding="utf-8").read()
                    ast.parse(text)
                except (SyntaxError, UnicodeDecodeError, ValueError):
                    continue
                yield rel, text
    yield "app.py", open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()


class TestNoWriterStagesATree:
    def test_nothing_stages_a_tree_but_the_declared_migration(self):
        offenders = [(rel, hit) for rel, text in _sources() if rel not in DECLARED
                     for hit in _tree_staging(text)]
        assert offenders == []

    def test_the_scan_finds_something(self):
        """Floors: the migration's own staging is seen, and a planted writer
        call passing a tree is seen (the shape every writer had)."""
        migrate = open(os.path.join(ROOT, "modules", "nsot", "migrate.py"),
                       encoding="utf-8").read()
        assert _tree_staging(migrate), "the declared exception is visible to the scan"
        planted = ('R._commit_paths(list_name, ["host_vars", "golden", ".nsot"], s, t, "x")\n'
                   'save_golden(ln, items, extra_paths=["host_vars"])\n'
                   'git(repo, "add", "-A", "golden", ".nsot")\n'
                   'extra_paths = ["host_vars"]\n')
        assert {line for line, _hit in _tree_staging(planted)} == {1, 2, 3, 4}
        files = sum(1 for _ in _sources())
        assert files > 150, files
