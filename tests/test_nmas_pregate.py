"""scripts/nmas-pregate: the tests a change touches, chosen and run before the gate (the
operator's overnight item 9, 2026-11-12), driven in real temporary repositories with stand-ins
for `scripts/nmas-test`, CI's interpreter, the skip check and the commit-msg hook's checks.

What each test holds:
- the selection, on planted changes: a module's change chooses the files importing what it
  changed (and a name reading a changed one, inside the module), never an importer of an
  untouched name, and every importer when a statement binding no name changed; a template's
  change chooses the files naming it, the files naming a route rendering it or a template using
  it, and the browser files among them, never a file only searching a page's text for the
  route; a route function's change chooses the files naming its route, and the route tests; a
  change under docs/manual/ chooses the manual and fidelity tests; a browser file is known by
  its import of `Browser`, parsed;
- the gate: while the full-suite lock names a live process nothing runs, and it says so (at
  once with --no-wait, after its bound otherwise, saying why it waits), and a dead holder is no
  gate;
- the summary's states and the exit codes: passed (0), a failure (1), a skip the gate's skip
  check refuses (its file failed, 1), every test of a file
  skipped (not run, 4), no browser interpreter (not run, 4, never "passed"), an absent fixed
  file (not run, 4), --list (nothing run, said, 0), the working tree changed by a run (3), and
  the runs get PYTHONDONTWRITEBYTECODE=1 and `-p no:cacheprovider`;
- the message: the commit-msg hook (the real file, its checks stood in) traced, and the check
  that refused named;
- a bound that fires ends its run;
- (C3421) shared filters, macros and imports: a filter whose body (or a name it reads) changed,
  a filter removed, a context processor's names and a global registered from another module
  choose the tests naming a route that renders a template using it (through a partial too);
  a changed macro file chooses the tests rendering its users, transitively, by route or by the
  template's name; a third-party import gained or lost chooses tests/test_requirements_lock.py,
  a standard-library or local one does not;
- (C3421) a browser file is one starting a real browser by any path the suite uses: a fixture
  imported from another test module (tests/test_v2_links_stay_on_v2.py's shape, and that file
  and tests/test_live_merge.py themselves), and every file scripts/nmas-shards' rule counts;
- (C3421) the snapshot: the runs read the staged tree, never the working tree (a staged
  failure fails, an unstaged one is not tested), in a worktree outside the checkout that is
  removed, a range tests its last commit's tree, the local-only files are never copied and
  their tests run in the checkout, an edit during the run is said and decides nothing, and a
  snapshot a gone run left is removed;
- (C3421) the verdict per tree: a pass, a failure, a run that did not happen and a refused
  message recorded by the tree's id, asked by tree or commit (`--verdict`, 0 only for a pass),
  replaced by a later run, absent for --list, none for a tree never run.
"""
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import textwrap
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "nmas-pregate")
ENV = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
ENV.update(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com", GIT_COMMITTER_NAME="t",
           GIT_COMMITTER_EMAIL="t@example.com")


def _load():
    loader = importlib.machinery.SourceFileLoader("nmas_pregate", SCRIPT)
    spec = importlib.util.spec_from_loader("nmas_pregate", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


_LOADED = []


def _tool():
    """The tool, loaded once at first use, never at collection: each test is red, not the
    file, where the tool is absent."""
    if not _LOADED:
        _LOADED.append(_load())
    return _LOADED[0]


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          env=ENV, check=True).stdout


def _write(repo, rel, text, mode=None):
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text))
    if mode:
        path.chmod(mode)


#: A stand-in for scripts/nmas-test and for CI's interpreter (`-m pytest`): it writes a JUnit
#: file with one case per named test file, failed when the file holds PLANT_FAIL, skipped when
#: it holds PLANT_SKIP, and records its arguments and environment where NMAS_PREGATE_RECORD
#: says; with PLANT_WRITE in a file it writes into the repository.
RUNNER = """\
    #!/usr/bin/env python3
    import json, os, sys
    args = [a for a in sys.argv[1:] if a not in ("-m", "pytest")]
    junit = next(a.split("=", 1)[1] for a in args if a.startswith("--junitxml="))
    deselected = [b for a, b in zip(args, args[1:]) if a == "--deselect"]
    files = [a for a in args if a.startswith("tests/") and a not in deselected]
    rec = os.environ.get("NMAS_PREGATE_RECORD")
    if rec:
        with open(rec, "a") as fh:
            fh.write(json.dumps({"argv": sys.argv[1:], "bytecode":
                                 os.environ.get("PYTHONDONTWRITEBYTECODE"), "browser":
                                 os.environ.get("NMAS_REQUIRE_BROWSER"), "cwd": os.getcwd(),
                                 "deselected": deselected,
                                 "local_file": os.path.exists("data/lab_hosts.json")}) + "\\n")
    touch = os.environ.get("NMAS_PREGATE_TOUCH")
    if touch:
        open(touch, "w").write("edited while the run ran")
    cases, rc = [], 0
    for f in files:
        f, _sep, node = f.partition("::")
        text = open(f).read()
        name = f[:-3].replace("/", ".") + ("." + node.split("::")[0] if node else "")
        if "PLANT_WRITE" in text:
            open("planted-by-the-run.txt", "w").write("x")
        if "PLANT_FAIL" in text:
            cases.append(f'<testcase classname="{name}" name="test_a"><failure message="x"/></testcase>')
            rc = 1
        elif "PLANT_SKIP" in text:
            cases.append(f'<testcase classname="{name}" name="test_a"><skipped message="x"/></testcase>')
        else:
            cases.append(f'<testcase classname="{name}" name="test_a"/>')
    open(junit, "w").write("<testsuites><testsuite>" + "".join(cases) + "</testsuite></testsuites>")
    sys.exit(rc)
"""


def _repo(tmp_path):
    """A repository holding every fixed-set test file, a stand-in suite and skip check, and a
    module, a route module and templates for the planted changes."""
    r = tmp_path / "repo"
    r.mkdir()
    _git(tmp_path, "init", "-q", str(r))
    for t in _tool().CONVENTIONS + _tool().MANUAL + _tool().ROUTES:
        _write(r, t, "def test_a():\n    assert True\n")
    _write(r, "scripts/nmas-test", RUNNER, 0o755)
    # The skip check stood in: with NMAS_PREGATE_SKIP_REFUSE it refuses that test, as the real
    # one words it.
    _write(r, "scripts/nmas-skip-check", """\
        import os, sys
        who = os.environ.get("NMAS_PREGATE_SKIP_REFUSE")
        if who:
            print(f"nmas-skip-check: REFUSED: {who}::test_a: skipped for 'x', declared for ci, not for gate")
            sys.exit(1)
        """, 0o755)
    _write(r, "modules/alpha.py", """\
        import os


        def f():
            return 1


        def g():
            return f() + 1


        def h():
            return 3
        """)
    _write(r, "templates/v2/_part.html", "<p>part</p>\n")
    _write(r, "templates/v2/page.html", '{% include "v2/_part.html" %}\n')
    _write(r, "templates/v2/shell.html", '<div hx-get="/v2/page"></div>\n')
    _write(r, "templates/v2/other.html", "<p>other</p>\n")
    _write(r, "routes/pages.py", """\
        from flask import Blueprint, render_template

        bp = Blueprint("pages", __name__, url_prefix="/v2")


        @bp.route("/page", methods=["GET"])
        def page():
            return render_template("v2/page.html")


        @bp.route("/shell", methods=["GET"])
        def shell():
            return render_template("v2/shell.html")


        @bp.route("/other", methods=["GET"])
        def other():
            return render_template("v2/other.html")
        """)
    _write(r, "tests/test_uses_f.py", """\
        from modules.alpha import f


        def test_a():
            assert f() == 1
        """)
    _write(r, "tests/test_uses_g.py", """\
        from modules import alpha


        def test_a():
            assert alpha.g() == 2
        """)
    _write(r, "tests/test_uses_h.py", """\
        import modules.alpha as A


        def test_a():
            assert A.h() == 3
        """)
    _write(r, "tests/test_names_part.py", """\
        def test_a():
            assert "v2/_part.html"
        """)
    _write(r, "tests/test_page_client.py", """\
        def test_a(client):
            client.get("/v2/page")
        """)
    _write(r, "tests/test_page_probe.py", """\
        def test_a(html):
            assert "/v2/page" in html
        """)
    _write(r, "tests/test_shell_browser.py", """\
        from tests.browser import Browser


        def test_a(srv):
            with Browser() as b:
                b.go(srv.url("/v2/shell"))
        """)
    _write(r, "tests/test_other_browser.py", """\
        from tests import browser


        def test_a(srv):
            with browser.Browser() as b:
                b.go(srv.url("/v2/other"))
        """)
    _write(r, "tests/test_port_only.py", """\
        from tests.browser import free_port


        def test_a():
            assert free_port()
        """)
    _write(r, "docs/manual/page.md", "# A page\n")
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "base")
    return r


def _edit(repo, rel, old, new):
    path = repo / rel
    path.write_text(path.read_text().replace(old, new))
    _git(repo, "add", rel)


def _chosen(repo):
    change = _tool().change(str(repo))
    return _tool().select(str(repo), change)


class TestTheSelection:
    def test_a_module_change_chooses_what_imports_the_changed_name(self, tmp_path):
        r = _repo(tmp_path)
        _edit(r, "modules/alpha.py", "    return 3", "    return 4")
        chosen = _chosen(r)
        assert any("reads A.h of modules.alpha" in w for w in chosen["tests/test_uses_h.py"])
        assert "tests/test_uses_f.py" not in chosen
        assert "tests/test_uses_g.py" not in chosen
        for t in _tool().CONVENTIONS:
            assert chosen[t] == ["the convention set"]
        assert not set(_tool().MANUAL + _tool().ROUTES) & set(chosen)

    def test_a_name_reading_a_changed_one_is_changed_too(self, tmp_path):
        r = _repo(tmp_path)
        _edit(r, "modules/alpha.py", "    return 1", "    return 5")
        chosen = _chosen(r)
        assert any("imports f from modules.alpha" in w for w in chosen["tests/test_uses_f.py"])
        assert any("reads alpha.g of modules.alpha" in w for w in chosen["tests/test_uses_g.py"])
        assert "tests/test_uses_h.py" not in chosen

    def test_a_statement_binding_no_name_chooses_every_importer(self, tmp_path):
        r = _repo(tmp_path)
        _edit(r, "modules/alpha.py", "import os\n", "import os\nimport sys\n")
        chosen = _chosen(r)
        for t in ("tests/test_uses_f.py", "tests/test_uses_g.py", "tests/test_uses_h.py"):
            assert chosen[t] == ["imports modules.alpha (modules/alpha.py)"], t

    def test_a_template_change_chooses_its_namers_and_the_browser_files_rendering_it(
            self, tmp_path):
        r = _repo(tmp_path)
        _edit(r, "templates/v2/_part.html", "part", "the part")
        chosen = _chosen(r)
        assert any("names templates/v2/_part.html" in w
                   for w in chosen["tests/test_names_part.py"])
        assert any("names the route /v2/page (renders v2/page.html, which uses v2/_part.html"
                   in w for w in chosen["tests/test_page_client.py"])
        # The shell page loads /v2/page by htmx: its browser file renders the part.
        assert any("a browser file naming /v2/shell" in w
                   for w in chosen["tests/test_shell_browser.py"])
        assert "tests/test_page_probe.py" not in chosen
        assert "tests/test_other_browser.py" not in chosen
        for t in _tool().MANUAL:
            assert any("a template changed" in w for w in chosen[t])

    def test_a_route_function_change_chooses_its_namers_and_the_route_tests(self, tmp_path):
        r = _repo(tmp_path)
        _edit(r, "routes/pages.py", 'return render_template("v2/other.html")',
              'return render_template("v2/other.html", x=1)')
        chosen = _chosen(r)
        assert any("names the route /v2/other (its function in routes/pages.py changed"
                   in w for w in chosen["tests/test_other_browser.py"])
        assert "tests/test_page_client.py" not in chosen
        for t in _tool().ROUTES:
            assert chosen[t] == ["the route tests (routes/ changed)"]

    def test_a_manual_change_chooses_the_manual_tests(self, tmp_path):
        r = _repo(tmp_path)
        _edit(r, "docs/manual/page.md", "A page", "The page")
        chosen = _chosen(r)
        for t in _tool().MANUAL:
            assert chosen[t] == ["the manual and fidelity tests (docs/manual/ changed)"]

    def test_a_changed_test_file_is_chosen(self, tmp_path):
        r = _repo(tmp_path)
        _edit(r, "tests/test_page_probe.py", "in html", "in html.lower()")
        assert _chosen(r)["tests/test_page_probe.py"] == ["a changed test file"]

    def test_a_browser_file_is_known_by_its_import_of_browser(self, tmp_path):
        r = _repo(tmp_path)
        tests = _tool().test_files(str(r))
        assert tests["tests/test_shell_browser.py"].browser
        assert tests["tests/test_other_browser.py"].browser
        assert not tests["tests/test_port_only.py"].browser
        assert not tests["tests/test_page_client.py"].browser


def _run(repo, *args, env=None):
    e = dict(ENV, NMAS_PREGATE_PYTHON=str(repo / "scripts" / "nmas-test"),
             NMAS_FULL_LOCK=str(repo.parent / "no-such-lock"))
    e.update(env or {})
    r = subprocess.run([sys.executable, SCRIPT, "--repo", str(repo), *args],
                       capture_output=True, text=True, env=e, timeout=120)
    return r.returncode, r.stdout + r.stderr


def _line(out, path):
    return next(line for line in out.splitlines() if f" {path}: " in line)


class TestTheGate:
    def test_a_live_holder_runs_nothing_and_says_so(self, tmp_path):
        r = _repo(tmp_path)
        _edit(r, "modules/alpha.py", "    return 3", "    return 4")
        lock = tmp_path / "lock"
        lock.write_text(f"nmas-gate (pid {os.getpid()})\n")
        rc, out = _run(r, "--no-wait", env={"NMAS_FULL_LOCK": str(lock)})
        assert rc == 4, out
        assert f"names live process {os.getpid()}" in out
        assert "NOT RUN: a gate was running" in _line(out, "tests/test_uses_h.py")
        assert "passed" not in out

    def test_it_waits_saying_why_then_refuses_past_its_bound(self, tmp_path):
        r = _repo(tmp_path)
        _edit(r, "modules/alpha.py", "    return 3", "    return 4")
        lock = tmp_path / "lock"
        lock.write_text(f"nmas-gate (pid {os.getpid()})\n")
        rc, out = _run(r, env={"NMAS_FULL_LOCK": str(lock), "NMAS_PREGATE_WAIT_S": "2",
                               "NMAS_PREGATE_POLL_S": "1"})
        assert rc == 4, out
        assert "waits:" in out and "a gate running" in out
        assert "still running after 2 s (the bound, 2 s)" in out

    def test_a_dead_holder_is_no_gate(self, tmp_path):
        r = _repo(tmp_path)
        _edit(r, "modules/alpha.py", "    return 3", "    return 4")
        dead = subprocess.Popen(["true"])
        dead.wait()
        lock = tmp_path / "lock"
        lock.write_text(f"nmas-gate (pid {dead.pid})\n")
        assert _tool().gate_holder(str(lock)) is None
        live = tmp_path / "live"
        live.write_text(f"nmas-gate (pid {os.getpid()})\n")
        assert _tool().gate_holder(str(live))[0] == os.getpid()
        rc, out = _run(r, "--no-wait", env={"NMAS_FULL_LOCK": str(lock)})
        assert rc == 0, out


class TestTheSummary:
    def test_every_file_passing_exits_0_and_the_runs_write_no_bytecode(self, tmp_path):
        r = _repo(tmp_path)
        _edit(r, "templates/v2/_part.html", "part", "the part")
        record = tmp_path / "record.jsonl"
        rc, out = _run(r, env={"NMAS_PREGATE_RECORD": str(record)})
        assert rc == 0, out
        assert _line(out, "tests/test_page_client.py").strip().startswith("passed (1)")
        assert _line(out, "tests/test_shell_browser.py").strip().startswith("passed (1)")
        assert "every chosen file ran and passed" in out
        runs = [json.loads(x) for x in record.read_text().splitlines()]
        assert len(runs) == 3                   # confined, browser, and the checkout's own
        for run in runs:
            assert run["bytecode"] == "1"
            assert "no:cacheprovider" in run["argv"]
        browser = next(x for x in runs if x["browser"] == "1")
        assert "tests/test_shell_browser.py" in browser["argv"]
        assert "tests/test_page_client.py" not in browser["argv"]

    def test_a_failure_exits_1(self, tmp_path):
        r = _repo(tmp_path)
        _edit(r, "tests/test_page_probe.py", "in html", "in html  # PLANT_FAIL")
        rc, out = _run(r)
        assert rc == 1, out
        assert "FAILED (1 failed, 0 passed)" in _line(out, "tests/test_page_probe.py")

    def test_a_file_whose_tests_all_skipped_is_not_run(self, tmp_path):
        r = _repo(tmp_path)
        _edit(r, "tests/test_page_probe.py", "in html", "in html  # PLANT_SKIP")
        rc, out = _run(r)
        assert rc == 4, out
        assert "NOT RUN: every test skipped" in _line(out, "tests/test_page_probe.py")
        assert "every chosen file ran and passed" not in out

    def test_a_skip_the_gate_refuses_fails_its_file(self, tmp_path):
        r = _repo(tmp_path)
        _edit(r, "tests/test_page_probe.py", "in html", "in html.lower()")
        rc, out = _run(r, env={"NMAS_PREGATE_SKIP_REFUSE": "tests.test_page_probe"})
        assert rc == 1, out
        assert "FAILED: a skip the gate refuses" in _line(out, "tests/test_page_probe.py")
        assert _line(out, _tool().CONVENTIONS[0]).strip().startswith("passed")

    def test_no_browser_interpreter_is_not_run_never_passed(self, tmp_path):
        r = _repo(tmp_path)
        _edit(r, "templates/v2/_part.html", "part", "the part")
        rc, out = _run(r, env={"NMAS_PREGATE_PYTHON": str(tmp_path / "no-python")})
        assert rc == 4, out
        assert "NOT RUN: no browser interpreter" in _line(out, "tests/test_shell_browser.py")
        assert _line(out, "tests/test_page_client.py").strip().startswith("passed")
        assert "NOT EVERYTHING RAN" in out

    def test_an_absent_fixed_file_is_not_run(self, tmp_path):
        r = _repo(tmp_path)
        (r / _tool().CONVENTIONS[0]).unlink()
        _git(r, "add", "-A")
        rc, out = _run(r)
        assert rc == 4, out
        assert "NOT RUN: absent from the tested tree" in _line(out, _tool().CONVENTIONS[0])

    def test_list_runs_nothing_and_says_so(self, tmp_path):
        r = _repo(tmp_path)
        _edit(r, "modules/alpha.py", "    return 3", "    return 4")
        record = tmp_path / "record.jsonl"
        rc, out = _run(r, "--list", env={"NMAS_PREGATE_RECORD": str(record)})
        assert rc == 0, out
        assert "listed only; nothing was run" in out
        assert not record.exists()

    def test_a_run_writes_only_in_the_snapshot_and_the_working_tree_is_said_unchanged(
            self, tmp_path):
        r = _repo(tmp_path)
        _edit(r, "tests/test_page_probe.py", "in html", "in html  # PLANT_WRITE")
        rc, out = _run(r)
        assert rc == 0, out
        assert not (r / "planted-by-the-run.txt").exists()
        assert "the working tree did not change during the run" in out

    def test_nothing_staged_cannot_start(self, tmp_path):
        rc, out = _run(_repo(tmp_path))
        assert rc == 2, out
        assert "changes nothing" in out


#: The real hook's checks, stood in: each passes, but the bypass scan refuses a message without
#: a Bypass trailer.
CHECKS = ("nmas-host-step-check", "nmas-test-weakening-check", "nmas-red-green",
          "nmas-guard-check", "nmas-bypass-scan", "nmas-premise-check")


class TestTheMessage:
    def _hooked(self, tmp_path):
        r = _repo(tmp_path)
        with open(os.path.join(ROOT, "scripts", "hooks", "commit-msg"), encoding="utf-8") as fh:
            (r / "scripts" / "hooks").mkdir(parents=True)
            (r / "scripts" / "hooks" / "commit-msg").write_text(fh.read())
        for c in CHECKS:
            body = ("import sys\nmsg = open(sys.argv[sys.argv.index('--message') + 1]).read()\n"
                    "sys.exit(0 if 'Bypass:' in msg else 1)\n" if c == "nmas-bypass-scan"
                    else "import sys\nsys.exit(0)\n")
            (r / "scripts" / c).write_text(body)
        # The hook and its checks are the tested tree's own: committed, so the snapshot has
        # them.
        _git(r, "add", "-A")
        _git(r, "commit", "-q", "-m", "the hook")
        _edit(r, "modules/alpha.py", "    return 3", "    return 4")
        return r

    def test_the_check_that_refused_is_named(self, tmp_path):
        r = self._hooked(tmp_path)
        msg = tmp_path / "msg"
        msg.write_text("A change\n\nNot-Done: nothing\n")
        rc, out = _run(r, "--message", str(msg))
        assert rc == 1, out
        assert "REFUSED: the commit-msg hook, by nmas-bypass-scan" in out

    def test_a_message_every_check_passes(self, tmp_path):
        r = self._hooked(tmp_path)
        msg = tmp_path / "msg"
        msg.write_text("A change\n\nBypass: a.py:1 — a reason\n")
        rc, out = _run(r, "--message", str(msg))
        assert rc == 0, out
        assert "passed: the commit-msg hook" in out

    def test_a_refused_message_records_the_tree_failed(self, tmp_path):
        r = self._hooked(tmp_path)
        msg = tmp_path / "msg"
        msg.write_text("A change\n\nNot-Done: nothing\n")
        rc, out = _run(r, "--message", str(msg))
        assert rc == 1, out
        rec = _record(r)
        assert rec["verdict"] == "failed"
        assert rec["message"].startswith("REFUSED: the commit-msg hook, by nmas-bypass-scan")


# --- C3421: shared filters, macros and imports ------------------------------------------------

def _jinja_repo(tmp_path):
    """_repo, with filters, a context processor and a global registered in routes/, the
    templates using each, a macro file and its users, a route for each and a test naming it
    (the shape of CI run #1673: routes/v2.py's `times` filter, its templates' tests)."""
    r = _repo(tmp_path)
    _write(r, "modules/beta.py", "X = 1\n")
    _write(r, "routes/filters.py", """\
        from flask import Blueprint

        from modules import alpha

        bp = Blueprint("filters", __name__)


        @bp.app_template_filter("shout")
        def shout(text):
            return _upper(text)


        def _upper(text):
            return text.upper()


        @bp.app_template_filter("whisper")
        def whisper(text):
            return text.lower()


        @bp.app_context_processor
        def _brand():
            return {"brandname": "M"}


        def install(app):
            app.jinja_env.globals["gate"] = alpha.h
        """)
    pages = {"loud": "<p>{{ x | shout }}</p>\n",
             "wrap": '{% include "v2/_loud_part.html" %}\n',
             "quiet": "<p>{{ x|whisper }}</p>\n",
             "branded": "<p>{{ brandname }}</p>\n",
             "gated": "<button {{ gate('x') }}>go</button>\n",
             "macro": '{% extends "v2/uses_macro.html" %}\n'}
    for name, text in pages.items():
        _write(r, f"templates/v2/{name}.html", text)
    _write(r, "templates/v2/_loud_part.html", "<p>{{ y|shout }}</p>\n")
    _write(r, "templates/v2/_macros.html", "{% macro m() %}m{% endmacro %}\n")
    _write(r, "templates/v2/uses_macro.html",
           '{% from "v2/_macros.html" import m %}{{ m() }}\n')
    route_src = ["from flask import Blueprint, render_template", "",
                 'bp = Blueprint("jpages", __name__, url_prefix="/v2")', ""]
    for name in pages:
        route_src += ["", f'@bp.route("/{name}", methods=["GET"])', f"def {name}():",
                      f'    return render_template("v2/{name}.html")', ""]
        _write(r, f"tests/test_{name}_route.py",
               f'def test_a(client):\n    client.get("/v2/{name}")\n')
    (r / "routes" / "jpages.py").write_text("\n".join(route_src))
    _write(r, "tests/test_renders_uses_macro.py", """\
        def test_a(env):
            env.get_template("v2/uses_macro.html")
        """)
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "filters")
    return r


class TestSharedFiltersMacrosAndImports:
    def test_a_changed_filter_chooses_the_tests_rendering_a_template_using_it(self, tmp_path):
        r = _jinja_repo(tmp_path)
        # `_upper` is no filter: `shout` reads it, so `shout` changed.
        _edit(r, "routes/filters.py", "return text.upper()", 'return text.upper() + "!"')
        chosen = _chosen(r)
        assert any("names the route /v2/loud (renders v2/loud.html, which uses the filter "
                   "shout (shout in routes/filters.py changed)" in w
                   for w in chosen["tests/test_loud_route.py"]), chosen["tests/test_loud_route.py"]
        # Through a partial that uses it.
        assert any("names the route /v2/wrap (renders v2/wrap.html, which uses "
                   "v2/_loud_part.html, which uses the filter shout" in w
                   for w in chosen["tests/test_wrap_route.py"])
        for other in ("quiet", "branded", "gated", "macro"):
            assert f"tests/test_{other}_route.py" not in chosen, other

    def test_a_removed_filter_chooses_the_tests_of_the_templates_still_using_it(self, tmp_path):
        r = _jinja_repo(tmp_path)
        _edit(r, "routes/filters.py",
              '@bp.app_template_filter("whisper")\ndef whisper(text):\n    return text.lower()\n',
              "")
        chosen = _chosen(r)
        assert any("uses the filter whisper" in w for w in chosen["tests/test_quiet_route.py"])
        assert "tests/test_loud_route.py" not in chosen

    def test_a_changed_context_processor_chooses_the_templates_reading_its_names(
            self, tmp_path):
        r = _jinja_repo(tmp_path)
        _edit(r, "routes/filters.py", '{"brandname": "M"}', '{"brandname": "Mercury"}')
        chosen = _chosen(r)
        assert any("uses the context brandname" in w
                   for w in chosen["tests/test_branded_route.py"])
        assert "tests/test_loud_route.py" not in chosen

    def test_a_global_registered_from_another_module_is_changed_with_it(self, tmp_path):
        r = _jinja_repo(tmp_path)
        _edit(r, "modules/alpha.py", "    return 3", "    return 4")
        chosen = _chosen(r)
        assert any("uses the global gate (modules.alpha.h (modules/alpha.py) changed)" in w
                   for w in chosen["tests/test_gated_route.py"])
        assert "tests/test_branded_route.py" not in chosen

    def test_a_changed_macro_file_chooses_the_tests_of_its_users_transitively(self, tmp_path):
        r = _jinja_repo(tmp_path)
        _edit(r, "templates/v2/_macros.html", "m{% endmacro", "mm{% endmacro")
        chosen = _chosen(r)
        # A test rendering a template that imports the macro file, by the template's name.
        assert any("names a template that renders it: v2/uses_macro.html, which uses "
                   "v2/_macros.html" in w for w in chosen["tests/test_renders_uses_macro.py"])
        # A route rendering a template that extends that one.
        assert any("names the route /v2/macro (renders v2/macro.html, which uses "
                   "v2/_macros.html" in w for w in chosen["tests/test_macro_route.py"])
        assert "tests/test_loud_route.py" not in chosen

    def test_a_third_party_import_gained_or_lost_chooses_the_lock_test(self, tmp_path):
        r = _jinja_repo(tmp_path)
        lock = _tool().LOCK_TEST
        _edit(r, "modules/alpha.py", "def f():\n", "def f():\n    import requests\n")
        assert _chosen(r)[lock] == [
            "modules/alpha.py changes its imports outside the product (+requests)"]
        _git(r, "commit", "-q", "-m", "gained")
        _edit(r, "modules/alpha.py", "    import requests\n", "")
        assert _chosen(r)[lock] == [
            "modules/alpha.py changes its imports outside the product (-requests)"]

    def test_a_standard_library_or_local_import_leaves_the_lock_test(self, tmp_path):
        r = _jinja_repo(tmp_path)
        _edit(r, "modules/alpha.py", "def f():\n",
              "def f():\n    import json\n    from modules import beta\n    import routes\n")
        assert _tool().LOCK_TEST not in _chosen(r)


# --- C3421 (the coordinator, 2026-11-13): a browser started by any path the suite uses ----------

class TestTheBrowserFiles:
    def test_a_fixture_imported_from_another_test_module_starts_a_browser(self, tmp_path):
        r = _repo(tmp_path)
        # The shape of tests/test_v2_links_stay_on_v2.py: `served` imported from the layout
        # file, which asks `browser.available()`, and asked for by argument. (Written so that
        # scripts/nmas-shards' text rule does not count this file as a browser file.)
        _write(r, "tests/test_layout_like.py", """\
            import pytest

            from tests import browser

            PAGES = ("/v2/page",)


            @pytest.fixture
            def served():
                return browser.available()[0]


            def test_a(served):
                assert served
            """)
        _write(r, "tests/test_links_like.py", """\
            from tests.test_layout_like import PAGES, served  # noqa: F401 (the fixture)


            def test_a(served):
                assert PAGES
            """)
        _write(r, "tests/test_pages_only.py", """\
            from tests.test_layout_like import PAGES


            def test_a():
                assert PAGES
            """)
        tests = _tool().test_files(str(r))
        assert tests["tests/test_layout_like.py"].browser
        assert tests["tests/test_links_like.py"].browser
        assert not tests["tests/test_pages_only.py"].browser
        assert not tests["tests/test_port_only.py"].browser

    def test_the_files_run_confined_on_2026_11_13_are_browser_files(self):
        # The measured cases: each ran confined, where Firefox cannot start, and its real
        # browser tests skipped.
        found = _tool().browser_modules(ROOT)
        for planted in ("tests/test_v2_links_stay_on_v2.py", "tests/test_live_merge.py"):
            assert planted in found, planted

    def test_every_file_ci_counts_as_starting_a_browser_is_one(self):
        import re
        marked = set()
        for name in os.listdir(os.path.join(ROOT, "tests")):
            if name.startswith("test_") and name.endswith(".py"):
                with open(os.path.join(ROOT, "tests", name), encoding="utf-8") as fh:
                    if re.search(r"=\s*browser\.available\(\)", fh.read()):
                        marked.add(f"tests/{name}")
        assert len(marked) >= 40, "scripts/nmas-shards' rule found too few to compare"
        assert marked <= _tool().browser_modules(ROOT), sorted(
            marked - _tool().browser_modules(ROOT))


# --- C3421: the snapshot of the staged tree ---------------------------------------------------

def _runs(record):
    return [json.loads(x) for x in record.read_text().splitlines()]


def _worktrees(repo):
    return [x for x in _git(repo, "worktree", "list", "--porcelain").splitlines()
            if x.startswith("worktree ")]


class TestTheSnapshot:
    def test_the_runs_read_the_staged_tree_never_the_working_tree(self, tmp_path):
        r = _repo(tmp_path)
        _edit(r, "tests/test_page_probe.py", "in html", "in html.lower()")
        # A failure the working tree holds and the index does not: never tested.
        path = r / "tests" / "test_page_probe.py"
        path.write_text(path.read_text() + "# PLANT_FAIL\n")
        record = tmp_path / "record.jsonl"
        rc, out = _run(r, env={"NMAS_PREGATE_RECORD": str(record)})
        assert rc == 0, out
        assert "are not in the tested tree: tests/test_page_probe.py" in out
        runs = _runs(record)
        there = [x for x in runs if x["cwd"] == str(r)]
        # Only the checkout-only tests run in the checkout; every file runs in the snapshot.
        assert len(there) == 1
        assert all("::" in a for a in there[0]["argv"] if a.startswith("tests/"))
        assert all(not x["cwd"].startswith(str(r)) for x in runs if x not in there)

    def test_a_staged_failure_fails_whatever_the_working_tree_holds(self, tmp_path):
        r = _repo(tmp_path)
        _edit(r, "tests/test_page_probe.py", "in html", "in html  # PLANT_FAIL")
        path = r / "tests" / "test_page_probe.py"
        path.write_text(path.read_text().replace("  # PLANT_FAIL", ""))
        rc, out = _run(r)
        assert rc == 1, out
        assert "FAILED (1 failed, 0 passed)" in _line(out, "tests/test_page_probe.py")

    def test_the_snapshot_is_outside_the_checkout_and_removed(self, tmp_path):
        r = _repo(tmp_path)
        _edit(r, "modules/alpha.py", "    return 3", "    return 4")
        record = tmp_path / "record.jsonl"
        rc, out = _run(r, env={"NMAS_PREGATE_RECORD": str(record)})
        assert rc == 0, out
        snap = next(run["cwd"] for run in _runs(record) if run["cwd"] != str(r))
        assert os.path.basename(os.path.dirname(snap)).startswith(_tool().SNAPSHOT_PREFIX)
        assert not snap.startswith(str(r))
        assert not os.path.exists(snap)
        assert _worktrees(r) == [f"worktree {r}"]

    def test_the_local_only_files_stay_in_the_checkout_and_their_tests_run_there(
            self, tmp_path):
        r = _repo(tmp_path)
        _write(r, ".gitignore", "data/\n")
        _git(r, "add", ".gitignore")
        _write(r, "data/lab_hosts.json", "{}\n")
        record = tmp_path / "record.jsonl"
        rc, out = _run(r, env={"NMAS_PREGATE_RECORD": str(record)})
        assert rc == 0, out
        ids = [f"{t}::{i}" for t, i_s in _tool().CHECKOUT_ONLY.items() for i in i_s]
        runs = _runs(record)
        there = [x for x in runs if x["cwd"] == str(r)]
        snapped = [x for x in runs if x["cwd"] != str(r)]
        assert len(there) == 1 and there[0]["local_file"]
        assert [a for a in there[0]["argv"] if a.startswith("tests/")] == ids
        assert snapped and not any(x["local_file"] for x in snapped)
        confined = next(x for x in snapped if x["browser"] is None)
        assert confined["deselected"] == ids
        assert "not run in the snapshot: " + ids[0] in out
        assert "reading the working tree's files" in out

    def test_an_edit_during_the_run_is_said_and_decides_nothing(self, tmp_path):
        r = _repo(tmp_path)
        _edit(r, "modules/alpha.py", "    return 3", "    return 4")
        rc, out = _run(r, env={"NMAS_PREGATE_TOUCH": str(r / "edited-meanwhile.txt")})
        assert rc == 0, out
        line = next(x for x in out.splitlines() if "the working tree changed during" in x)
        assert "not part of the verdict" in line and "'edited-meanwhile.txt'" in line

    def test_a_range_tests_its_last_commit_s_tree(self, tmp_path):
        r = _repo(tmp_path)
        _edit(r, "tests/test_page_probe.py", "in html", "in html  # PLANT_FAIL")
        _git(r, "commit", "-q", "-m", "a failure")
        path = r / "tests" / "test_page_probe.py"
        path.write_text(path.read_text().replace("  # PLANT_FAIL", ""))
        _git(r, "add", "-A")
        rc, out = _run(r, "--range", "HEAD~1..HEAD")
        assert rc == 1, out
        assert _record(r, "HEAD")["base"] == _git(r, "rev-parse", "HEAD~1").strip()

    def test_a_snapshot_a_gone_run_left_is_removed(self, tmp_path):
        r = _repo(tmp_path)
        snap, _remove, why = _tool().make_snapshot(str(r), _git(r, "write-tree").strip(),
                                                   _git(r, "rev-parse", "HEAD").strip())
        assert snap, why
        dead = subprocess.Popen(["true"])
        dead.wait()
        with open(os.path.join(os.path.dirname(snap), "owner.pid"), "w") as fh:
            fh.write(str(dead.pid))
        _edit(r, "modules/alpha.py", "    return 3", "    return 4")
        rc, out = _run(r, "--list")
        assert rc == 0, out
        assert f"removed a snapshot a run that is gone left behind: {os.path.dirname(snap)}" in out
        assert not os.path.exists(snap)


# --- C3421: the verdict per tree --------------------------------------------------------------

def _record(repo, what=None):
    tree = _git(repo, "rev-parse", f"{what}^{{tree}}").strip() if what else \
        _git(repo, "write-tree").strip()
    with open(os.path.join(repo, ".git", "nmas-pregate", "verdicts", f"{tree}.json")) as fh:
        return json.load(fh)


class TestTheVerdict:
    def test_a_pass_is_recorded_for_the_tree_and_asked_by_tree_or_commit(self, tmp_path):
        r = _repo(tmp_path)
        _edit(r, "modules/alpha.py", "    return 3", "    return 4")
        tree = _git(r, "write-tree").strip()
        rc, out = _run(r)
        assert rc == 0, out
        rec = _record(r)
        assert rec["tree"] == tree and rec["verdict"] == "pass" and rec["exit"] == 0
        assert rec["change"] == "staged" and rec["message"] == "not given"
        assert rec["base"] == _git(r, "rev-parse", "HEAD").strip()
        assert rec["files"]["tests/test_uses_h.py"]["state"].startswith("passed")
        assert rec["at"].endswith("Z")
        folder = r / ".git" / "nmas-pregate" / "verdicts"
        assert sorted(p.name for p in folder.iterdir()) == [f"{tree}.json"]
        rc, out = _run(r, "--verdict", tree)
        assert rc == 0, out
        _git(r, "commit", "-q", "-m", "the change")
        rc, out = _run(r, "--verdict", "HEAD")
        assert rc == 0 and f"tree {tree}: pass" in out, out

    def test_a_failure_is_recorded_failed_and_is_no_pass(self, tmp_path):
        r = _repo(tmp_path)
        _edit(r, "tests/test_page_probe.py", "in html", "in html  # PLANT_FAIL")
        rc, out = _run(r)
        assert rc == 1, out
        rec = _record(r)
        assert rec["verdict"] == "failed" and rec["exit"] == 1
        assert rec["files"]["tests/test_page_probe.py"]["state"].startswith("FAILED")
        tree = rec["tree"]
        rc, out = _run(r, "--verdict", tree)
        assert rc == 1, out
        assert "FAILED (1 failed, 0 passed): tests/test_page_probe.py" in out

    def test_a_run_that_did_not_happen_is_recorded_not_run_and_is_no_pass(self, tmp_path):
        r = _repo(tmp_path)
        _edit(r, "templates/v2/_part.html", "part", "the part")
        rc, out = _run(r, env={"NMAS_PREGATE_PYTHON": str(tmp_path / "no-python")})
        assert rc == 4, out
        assert _record(r)["verdict"] == "not run"
        rc, out = _run(r, "--verdict", _record(r)["tree"])
        assert rc == 1, out

    def test_a_later_run_of_the_same_tree_replaces_its_verdict(self, tmp_path):
        r = _repo(tmp_path)
        _edit(r, "tests/test_page_probe.py", "in html", "in html.lower()")
        tree = _git(r, "write-tree").strip()
        assert _run(r, env={"NMAS_PREGATE_SKIP_REFUSE": "tests.test_page_probe"})[0] == 1
        assert _record(r)["verdict"] == "failed"
        assert _run(r)[0] == 0
        assert _record(r)["tree"] == tree and _record(r)["verdict"] == "pass"

    def test_no_verdict_is_no_pass_and_an_unknown_tree_cannot_be_asked(self, tmp_path):
        r = _repo(tmp_path)
        rc, out = _run(r, "--verdict", "HEAD")
        assert rc == 1 and "NO VERDICT recorded" in out, out
        rc, out = _run(r, "--verdict", "no-such-ref")
        assert rc == 2, out

    def test_list_records_no_verdict(self, tmp_path):
        r = _repo(tmp_path)
        _edit(r, "modules/alpha.py", "    return 3", "    return 4")
        rc, out = _run(r, "--list")
        assert rc == 0 and "no verdict recorded" in out, out
        assert not (r / ".git" / "nmas-pregate").exists()


def test_a_bound_that_fires_ends_its_run(tmp_path):
    start = time.monotonic()
    rc, fired = _tool()._bounded(["sleep", "30"], str(tmp_path), dict(os.environ), 1)
    assert fired and rc != 0
    assert time.monotonic() - start < 20
