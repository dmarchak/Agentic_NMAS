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
- a bound that fires ends its run.
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
    files = [a for a in args if a.startswith("tests/")]
    rec = os.environ.get("NMAS_PREGATE_RECORD")
    if rec:
        with open(rec, "a") as fh:
            fh.write(json.dumps({"argv": sys.argv[1:], "bytecode":
                                 os.environ.get("PYTHONDONTWRITEBYTECODE"), "browser":
                                 os.environ.get("NMAS_REQUIRE_BROWSER")}) + "\\n")
    cases, rc = [], 0
    for f in files:
        text = open(f).read()
        name = f[:-3].replace("/", ".")
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
        assert len(runs) == 2
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
        assert "NOT RUN: absent from the checkout" in _line(out, _tool().CONVENTIONS[0])

    def test_list_runs_nothing_and_says_so(self, tmp_path):
        r = _repo(tmp_path)
        _edit(r, "modules/alpha.py", "    return 3", "    return 4")
        record = tmp_path / "record.jsonl"
        rc, out = _run(r, "--list", env={"NMAS_PREGATE_RECORD": str(record)})
        assert rc == 0, out
        assert "listed only; nothing was run" in out
        assert not record.exists()

    def test_a_run_writing_the_working_tree_exits_3(self, tmp_path):
        r = _repo(tmp_path)
        _edit(r, "tests/test_page_probe.py", "in html", "in html  # PLANT_WRITE")
        rc, out = _run(r)
        assert rc == 3, out
        changed = next(x for x in out.splitlines() if "THE WORKING TREE CHANGED" in x)
        assert "'planted-by-the-run.txt'" in changed

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


def test_a_bound_that_fires_ends_its_run(tmp_path):
    start = time.monotonic()
    rc, fired = _tool()._bounded(["sleep", "30"], str(tmp_path), dict(os.environ), 1)
    assert fired and rc != 0
    assert time.monotonic() - start < 20
