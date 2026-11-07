"""T25: no job, app or code-repository tool reads the configuration repository (the operator's
decision 2, 2026-11-07; the SDN platform design revision 7, section 11c.4: code apart from
state).

**The population:** every Python module under `modules/jobs/` and `modules/apps/` (their
subpackages and the app SDK's stub included), `scripts/mercury`, and the code repository's
module, `modules/coderepo*.py`, by pattern, once it exists. A floor on its size holds the scan
to reading what it should.

**The rule, by parsing each module (ast), never by a substring of its text:**
- no string a module uses as a value (a docstring or a bare string statement is prose, and is
  not read) names the configuration repository: a path component `config_repo`, or the
  goldens', the legacy goldens', the intent's or the templates' folder (`golden`,
  `golden_configs`, `host_vars`, `templates`), or a dotted name of a reader module below;
- no import of a module that reads it: `modules.nsot.hostvars`, `modules.nsot.golden_state`,
  `modules.nsot.render_artifact`, `modules.nsot.templates_repo`, `modules.config_read`, or
  `modules.nsot.repo` whole or for any name but `REPO_ALLOWED` (`run_git`, git's runner, and
  `has_repository`, a folder test that reads nothing);
- no call of `list_data_path(...)` but one whose arguments name `code_repo`.

`EXCUSED` holds each string that matches a folder's name and is not the configuration
repository's, keyed by file and value with its reason; it only shrinks, and an entry no longer
matched fails here. A planted reader is found by each rule.

No address is parsed: the scan reads names and strings."""

import ast
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
#: The population: every tracked module under these folders, every tracked `modules/coderepo*`
#: module, and SCRIPTS.
POPULATION_FOLDERS = ("modules/jobs", "modules/apps")
POPULATION_PREFIX = "coderepo"
SCRIPTS = ("scripts/mercury",)
#: Measured 2026-11-07: 18 modules (11 under modules/jobs/, 6 under modules/apps/ with the
#: SDK's stub, and scripts/mercury). A floor, not the count: a module added raises the count,
#: and a scan reading fewer fails.
FLOOR = 18
FOLDERS = frozenset({"config_repo", "golden", "golden_configs", "host_vars", "templates"})
READER_MODULES = frozenset({"modules.nsot.hostvars", "modules.nsot.golden_state",
                            "modules.nsot.render_artifact", "modules.nsot.templates_repo",
                            "modules.config_read"})
REPO = "modules.nsot.repo"
REPO_ALLOWED = frozenset({"run_git", "has_repository"})
CODE_REPO = "code_repo"
#: `{(file, value): why}`: a string naming a folder that is not the configuration
#: repository's. Only shrinks.
EXCUSED = {
    ("modules/jobs/scaffold.py", "templates"): "the jobs' own templates folder beside the "
                                               "module (modules/jobs/templates/), which "
                                               "`mercury job new` writes from",
}


def population() -> list:
    """The files git tracks in the population (`source_index.tracked`, never a walk of the disk,
    which would read an agent's untracked worktree copy as program)."""
    from tests.source_index import tracked

    files = set(SCRIPTS)
    files.update(os.path.relpath(p, ROOT) for p in tracked(*POPULATION_FOLDERS, suffix=".py"))
    files.update(os.path.relpath(p, ROOT)
                 for p in tracked("modules", suffix=".py", recursive=False)
                 if os.path.basename(p).startswith(POPULATION_PREFIX))
    return sorted(files)


def _prose(tree) -> set:
    """The ids of the string constants that are statements on their own (docstrings and bare
    strings): prose, not values."""
    return {id(n.value) for n in ast.walk(tree)
            if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)
            and isinstance(n.value.value, str)}


def _components(value: str) -> set:
    return {part for part in value.replace("\\", "/").split("/") if part}


def readers(text: str, file: str, excused=None) -> list:
    """One line per way *text* (module *file*'s source) names or reaches the configuration
    repository, each with its line; the excused strings answered in *excused* (a set)."""
    tree = ast.parse(text, filename=file)
    prose = _prose(tree)
    out = []
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and id(node) not in prose:
            named = _components(node.value) & FOLDERS
            dotted = {m for m in READER_MODULES | {REPO} if m in node.value}
            if named and (file, node.value) in EXCUSED:
                if excused is not None:
                    excused.add((file, node.value))
            elif named:
                out.append(f"{file} line {line}: the string {node.value!r} names "
                           f"{', '.join(sorted(named))}, the configuration repository's")
            elif dotted:
                out.append(f"{file} line {line}: the string {node.value!r} names "
                           f"{', '.join(sorted(dotted))}, which reads it")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in READER_MODULES or alias.name == REPO:
                    out.append(f"{file} line {line}: `import {alias.name}`")
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = {a.name for a in node.names}
            if node.module in READER_MODULES:
                out.append(f"{file} line {line}: `from {node.module} import ...`")
            elif node.module == REPO and names - REPO_ALLOWED:
                out.append(f"{file} line {line}: `from {REPO} import "
                           f"{', '.join(sorted(names - REPO_ALLOWED))}`: of it only "
                           f"{', '.join(sorted(REPO_ALLOWED))}")
            else:
                for name in names:
                    if f"{node.module}.{name}" in READER_MODULES | {REPO}:
                        out.append(f"{file} line {line}: `from {node.module} import {name}`")
        elif isinstance(node, ast.Call):
            func = node.func
            called = func.id if isinstance(func, ast.Name) else \
                func.attr if isinstance(func, ast.Attribute) else ""
            if called == "list_data_path" and not any(
                    isinstance(a, ast.Constant) and isinstance(a.value, str)
                    and CODE_REPO in _components(a.value)
                    for a in ast.walk(node) if a is not node):
                out.append(f"{file} line {line}: list_data_path(...) reaching something but "
                           f"{CODE_REPO}/")
    return out


def read(path: str) -> str:
    with open(os.path.join(ROOT, path), encoding="utf-8") as fh:
        return fh.read()


def test_the_population_is_every_job_app_and_code_repository_module():
    files = population()
    assert len(files) >= FLOOR, f"the scan reads {len(files)} modules, under its floor {FLOOR}"
    for expected in ("scripts/mercury", "modules/jobs/gate.py", "modules/jobs/runner.py",
                     "modules/apps/gate.py", "modules/apps/allowlist.py",
                     "modules/apps/sdk/mercury_app/__init__.py"):
        assert expected in files, expected


def test_no_job_app_or_code_repository_module_reads_the_configuration_repository():
    excused, found = set(), []
    for file in population():
        found.extend(readers(read(file), file, excused))
    assert found == []
    assert excused == set(EXCUSED), f"stale exemptions: {set(EXCUSED) - excused}"


PLANTED = {
    "a golden's path": ('import os\nGOLDEN = os.path.join(root, "config_repo", "golden")\n',
                        "the string 'config_repo' names config_repo"),
    "intent by a relative path": ('PATH = "host_vars/r1.yml"\n',
                                  "the string 'host_vars/r1.yml' names host_vars"),
    "a reader of goldens": ("from modules.nsot.repo import list_goldens, run_git\n",
                            "`from modules.nsot.repo import list_goldens`: of it only"),
    "the repo module whole": ("from modules.nsot import repo\n",
                              "`from modules.nsot import repo`"),
    "import the repo module": ("import modules.nsot.repo\n", "`import modules.nsot.repo`"),
    "the intent reader": ("from modules.nsot import hostvars\n",
                          "`from modules.nsot import hostvars`"),
    "the config reader": ("from modules.config_read import read_config\n",
                          "`from modules.config_read import ...`"),
    "a reader by name": ('mod = importlib.import_module("modules.nsot.golden_state")\n',
                         "names modules.nsot.golden_state, which reads it"),
    "the data path": ('p = config.list_data_path(net, "config_repo")\n',
                      "list_data_path(...) reaching something but code_repo/"),
}


@pytest.mark.parametrize("text, words", list(PLANTED.values()), ids=list(PLANTED))
def test_a_planted_reader_is_found(text, words):
    found = readers(text, "modules/jobs/planted.py")
    assert any(words in f for f in found), found
    assert all(f.startswith("modules/jobs/planted.py line ") for f in found)


@pytest.mark.parametrize("text", [
    '"""The goldens live in config_repo/golden/; a job never reads them."""\n',
    "from modules.nsot.repo import has_repository, run_git\n",
    'p = config.list_data_path(net, "code_repo")\n',
    'x = "golden ratio"\n',
])
def test_prose_git_runner_and_the_code_repository_are_not_readers(text):
    assert readers(text, "modules/jobs/planted.py") == []
