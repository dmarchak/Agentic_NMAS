"""The console host's forced command (modules/nsot/console_wrapper.py; docs/LAB9_PLAN.md section 8,
"Testing the feature", O2a).

The key's whole power is "bridge to an allowlisted console": these hold that a name not on the
allowlist, and every injected argument, is refused with NOTHING exec'd; that the one command it
builds is exactly the bridge to 127.0.0.1:5000 inside the allowlisted container; that a bad
allowlist file is refused; and that the module imports only the standard library (it runs on a
console host where Mercury is not installed)."""

import ast
import io
import os
import subprocess
import sys

import pytest

from modules.nsot import console_wrapper as W

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(ROOT, "modules", "nsot", "console_wrapper.py")


class FakeExec:
    """Records each exec instead of replacing the process."""

    def __init__(self, error=None):
        self.calls = []
        self.error = error

    def __call__(self, program, args):
        self.calls.append((program, list(args)))
        if self.error:
            raise self.error


@pytest.fixture
def allowlist(tmp_path):
    path = tmp_path / "console-allowlist"
    path.write_text("# consoles Mercury may bridge\n\nnode-a\n  node_b.2  \n# node-c\n")
    path.chmod(0o644)
    return str(path)


def run(allowlist_path, command, uid=None, argv=None):
    fake, err = FakeExec(), io.StringIO()
    env = {} if command is None else {"SSH_ORIGINAL_COMMAND": command}
    code = W.main(argv if argv is not None else ["nmas-console-bridge", allowlist_path], env,
                  execvp=fake, stderr=err, uid=uid)
    return code, fake.calls, err.getvalue()


# ── The success case: exactly one argv, exactly the bridge ────────────────────────────────

def test_an_allowlisted_name_execs_exactly_the_bridge(allowlist):
    code, calls, err = run(allowlist, "node-a")
    assert calls == [("docker", ["docker", "exec", "-i", "node-a", "nc", "127.0.0.1", "5000"])]
    assert (code, err) == (0, "")


def test_a_name_indented_in_the_file_is_still_that_name(allowlist):
    code, calls, _err = run(allowlist, "node_b.2")
    assert calls == [("docker", W.bridge_argv("node_b.2"))]
    assert code == 0


def test_bridge_argv_is_the_fixed_command_with_only_the_name_varying():
    assert W.bridge_argv("x") == ["docker", "exec", "-i", "x", "nc", "127.0.0.1", "5000"]
    assert W.bridge_argv("y")[:3] + W.bridge_argv("y")[4:] == \
        W.bridge_argv("x")[:3] + W.bridge_argv("x")[4:]


def test_main_reads_the_process_environment_and_writes_to_stderr_by_default(allowlist,
                                                                           monkeypatch, capsys):
    """As sshd runs it: no environment or stream handed in, so the process's own are used
    (the mutation run of 2026-10-22: `environ is None` and `stderr is None` made never true
    survived every other test, each of which hands both in)."""
    monkeypatch.setenv("SSH_ORIGINAL_COMMAND", "node-z")
    fake = FakeExec()
    assert W.main(["b", allowlist], execvp=fake) == 2
    assert fake.calls == []
    assert capsys.readouterr().err == (f"nmas-console-bridge: refused: 'node-z' is not on the "
                                       f"allowlist {allowlist} (2 names)\n")
    monkeypatch.setenv("SSH_ORIGINAL_COMMAND", "node-a")
    assert W.main(["b", allowlist], execvp=fake) == 0
    assert fake.calls == [("docker", W.bridge_argv("node-a"))]


def test_a_failed_exec_says_so_and_returns_one(allowlist):
    fake, err = FakeExec(error=FileNotFoundError(2, "No such file or directory")), io.StringIO()
    code = W.main(["b", allowlist], {"SSH_ORIGINAL_COMMAND": "node-a"}, execvp=fake, stderr=err)
    assert code == W.EXEC_FAILED == 1
    assert err.getvalue().startswith("nmas-console-bridge: could not run docker: ")
    assert err.getvalue().count("\n") == 1


# ── Refusals: each one execs nothing, exits 2, and names both operands on one line ────────

INJECTED = [
    ("node-a;id", "semicolon"),
    ("node-a && id", "and-list"),
    ("node-a&&id", "and-list, no spaces"),
    ("node-a|id", "pipe"),
    ("node-a`id`", "backticks"),
    ("node-a$(id)", "command substitution"),
    ("$(id)", "command substitution alone"),
    ("'node-a'", "single quotes"),
    ('"node-a"', "double quotes"),
    ("node-a node-b", "a second word"),
    ("node-a ", "a trailing space"),
    (" node-a", "a leading space"),
    ("node-a\tx", "a tab"),
    ("node-a\n", "a trailing newline"),
    ("node-a\nid", "a newline and a second command"),
    ("--privileged", "an option"),
    ("-it", "a short option"),
    ("node--a", "an option marker inside the name"),
    ("node..a", "a parent step inside the name (refused by the shared rule, C1558's class)"),
    ("../node-a", "a path step"),
    ("node-a/../x", "a path step inside"),
    ("node-a\x00", "NUL"),
    ("", "empty"),
    ("a" * 64, "over-long: 64 characters"),
    ("a" * 200, "over-long: 200 characters"),
    ("node-a>x", "a redirect"),
    (".node-a", "a leading dot"),
    ("_node-a", "a leading underscore"),
]


@pytest.mark.parametrize("command,_what", INJECTED, ids=[w for _c, w in INJECTED])
def test_an_injected_or_malformed_command_is_refused_and_nothing_is_execd(allowlist, command,
                                                                         _what):
    """Refused by the command's own shape, before the allowlist is consulted: the allowlist is
    the second wall, never the only one (control: `fullmatch` made `match`)."""
    code, calls, err = run(allowlist, command)
    assert calls == []
    assert code == W.REFUSED == 2
    assert err.startswith("nmas-console-bridge: refused: SSH_ORIGINAL_COMMAND ")
    assert "allowlist" not in err
    assert err.count("\n") == 1 and err.endswith("\n")


def test_a_name_not_on_the_allowlist_is_refused_naming_it_the_file_and_the_count(allowlist):
    code, calls, err = run(allowlist, "node-z")
    assert (code, calls) == (2, [])
    assert err == (f"nmas-console-bridge: refused: 'node-z' is not on the allowlist {allowlist} "
                   "(2 names)\n")


def test_a_commented_name_is_not_on_the_allowlist(allowlist):
    code, calls, _err = run(allowlist, "node-c")
    assert (code, calls) == (2, [])


@pytest.mark.parametrize("command", ["node", "node-", "node-ab", "Node-a", "node-a.", "ode-a"])
def test_the_allowlist_matches_exactly_never_by_prefix_or_case(allowlist, command):
    code, calls, err = run(allowlist, command)
    assert (code, calls) == (2, [])
    assert "is not on the allowlist" in err


def test_no_command_at_all_is_refused_as_a_shell_request(allowlist):
    code, calls, err = run(allowlist, None)
    assert (code, calls) == (2, [])
    assert "SSH_ORIGINAL_COMMAND is not set" in err


def test_an_over_long_command_names_its_length_and_the_limit(allowlist):
    _code, _calls, err = run(allowlist, "a" * 64)
    assert "is 64 characters, over the 63" in err


def test_the_longest_allowed_name_passes_when_allowlisted(tmp_path):
    name = "a" * 63
    path = tmp_path / "list"
    path.write_text(name + "\n")
    code, calls, _err = run(str(path), name)
    assert (code, calls) == (0, [("docker", W.bridge_argv(name))])


def test_a_malformed_command_names_itself_escaped_on_one_line(allowlist):
    _code, _calls, err = run(allowlist, "node-a\nid")
    assert "'node-a\\nid' is not one container name" in err


def test_an_option_marker_inside_a_name_is_named(allowlist):
    _code, _calls, err = run(allowlist, "node--a")
    assert err == ("nmas-console-bridge: refused: SSH_ORIGINAL_COMMAND 'node--a' holds '--', "
                   "which a name may not hold\n")


def test_a_shape_refusal_happens_before_the_allowlist_is_read(tmp_path):
    """A malformed command is refused on its own: even a missing allowlist is not reached."""
    code, calls, err = run(str(tmp_path / "absent"), "node-a;id")
    assert (code, calls) == (2, [])
    assert "is not one container name" in err


@pytest.mark.parametrize("argv", [["b"], ["b", "x", "y"], []], ids=["none", "two", "no-argv0"])
def test_the_allowlist_path_is_exactly_one_argument(allowlist, argv):
    code, calls, err = run(allowlist, "node-a", argv=argv)
    assert (code, calls) == (2, [])
    assert "1 expected: the allowlist's path" in err


def test_the_argument_count_is_named(allowlist):
    _code, _calls, err = run(allowlist, "node-a", argv=["b", "x", "y"])
    assert "2 arguments given, 1 expected" in err


# ── The allowlist file ────────────────────────────────────────────────────────────────────

def test_a_missing_allowlist_is_refused_and_nothing_is_execd(tmp_path):
    path = str(tmp_path / "absent")
    code, calls, err = run(path, "node-a")
    assert (code, calls) == (2, [])
    assert f"the allowlist {path} could not be read" in err


def test_an_unreadable_allowlist_is_refused(tmp_path, monkeypatch):
    """Opening it fails as a mode-000 file's does for a user who is not root."""
    path = tmp_path / "list"
    path.write_text("node-a\n")

    def denied(*_a, **_k):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(W, "open", denied, raising=False)
    code, calls, err = run(str(path), "node-a")
    assert (code, calls) == (2, [])
    assert f"the allowlist {path} could not be read: [Errno 13] Permission denied" in err


def test_a_non_ascii_allowlist_is_refused(tmp_path):
    path = tmp_path / "list"
    path.write_bytes("node-a\nnöde\n".encode("utf-8"))
    code, calls, err = run(str(path), "node-a")
    assert (code, calls) == (2, [])
    assert err == f"nmas-console-bridge: refused: the allowlist {path} holds a byte outside ASCII\n"


def test_a_world_writable_allowlist_is_refused_naming_its_mode(tmp_path):
    path = tmp_path / "list"
    path.write_text("node-a\n")
    path.chmod(0o646)
    code, calls, err = run(str(path), "node-a")
    assert (code, calls) == (2, [])
    assert f"the allowlist {path} is writable by others (mode 0646)" in err


def test_a_group_writable_allowlist_owned_by_the_user_is_accepted(tmp_path):
    """The control for the world-writable refusal: only the others' write bit refuses."""
    path = tmp_path / "list"
    path.write_text("node-a\n")
    path.chmod(0o664)
    code, calls, _err = run(str(path), "node-a")
    assert (code, len(calls)) == (0, 1)


def test_an_allowlist_owned_by_another_user_is_refused_naming_both_uids(allowlist):
    owner = os.stat(allowlist).st_uid
    assert owner != 0, "this test needs a file owned by someone other than root"
    other = owner + 1
    code, calls, err = run(allowlist, "node-a", uid=other)
    assert (code, calls) == (2, [])
    assert (f"is owned by uid {owner}, neither root (0) nor the invoking user ({other})"
            in err)


def test_an_allowlist_owned_by_the_invoking_user_is_accepted_by_default(allowlist):
    code, calls, _err = run(allowlist, "node-a")
    assert (code, len(calls)) == (0, 1)


def test_an_allowlist_owned_by_root_is_accepted(allowlist, monkeypatch):
    """Root (uid 0) owning the file is accepted whoever invokes: the fstat says uid 0."""
    real = os.fstat

    class RootOwned:
        def __init__(self, st):
            self._st = st

        def __getattr__(self, name):
            return 0 if name == "st_uid" else getattr(self._st, name)

    monkeypatch.setattr(W.os, "fstat", lambda fd: RootOwned(real(fd)))
    code, calls, _err = run(allowlist, "node-a", uid=os.getuid() + 1)
    assert (code, len(calls)) == (0, 1)


def test_a_directory_as_the_allowlist_is_refused(tmp_path):
    code, calls, err = run(str(tmp_path), "node-a")
    assert (code, calls) == (2, [])
    assert "the allowlist" in err


def test_a_fifo_as_the_allowlist_is_refused_as_not_a_regular_file(tmp_path, monkeypatch):
    real = os.fstat

    class Fifo:
        def __init__(self, st):
            self._st = st

        def __getattr__(self, name):
            return 0o010644 if name == "st_mode" else getattr(self._st, name)

    path = tmp_path / "list"
    path.write_text("node-a\n")
    monkeypatch.setattr(W.os, "fstat", lambda fd: Fifo(real(fd)))
    code, calls, err = run(str(path), "node-a")
    assert (code, calls) == (2, [])
    assert f"the allowlist {path} is not a regular file" in err


def test_a_malformed_allowlist_line_refuses_the_whole_file_naming_the_line(tmp_path):
    path = tmp_path / "list"
    path.write_text("node-a\nnode b\n")
    code, calls, err = run(str(path), "node-a")
    assert (code, calls) == (2, [])
    assert f"the allowlist {path} line 2 'node b' is not one container name" in err


def test_comments_and_blank_lines_are_ignored_and_names_kept_in_order(allowlist):
    assert W.read_allowlist(allowlist) == ["node-a", "node_b.2"]


def test_an_empty_allowlist_admits_nothing(tmp_path):
    path = tmp_path / "list"
    path.write_text("# nothing yet\n\n")
    code, calls, err = run(str(path), "node-a")
    assert (code, calls) == (2, [])
    assert "(0 names)" in err


def test_a_hash_inside_a_line_is_not_a_comment(tmp_path):
    """Only a line STARTING with # is a comment; `node-a # x` is a malformed entry, refused."""
    path = tmp_path / "list"
    path.write_text("node-a # the first\n")
    code, calls, err = run(str(path), "node-a")
    assert (code, calls) == (2, [])
    assert "line 1" in err


# ── It runs where Mercury is not installed ────────────────────────────────────────────────

def test_the_module_imports_only_the_standard_library():
    tree = ast.parse(open(SOURCE, encoding="utf-8").read())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "a relative import needs the package around it"
            names.add(node.module.split(".")[0])
    assert names, "the scan found no import at all (floor)"
    assert names <= set(sys.stdlib_module_names), sorted(names - set(sys.stdlib_module_names))


def test_the_stdlib_scan_sees_a_non_stdlib_import():
    """The scan's planted case: an import of Mercury's own package is outside the set."""
    assert "modules" not in sys.stdlib_module_names
    assert "flask" not in sys.stdlib_module_names


def test_it_runs_as_a_script_alone_and_refuses(tmp_path):
    """Run by path in an isolated interpreter (no Mercury on the path): a refusal, exit 2."""
    path = tmp_path / "list"
    path.write_text("node-a\n")
    env = {"PATH": os.environ.get("PATH", ""), "SSH_ORIGINAL_COMMAND": "node-z"}
    r = subprocess.run([sys.executable, "-I", SOURCE, str(path)], env=env, cwd=str(tmp_path),
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 2
    assert r.stdout == ""
    assert r.stderr == (f"nmas-console-bridge: refused: 'node-z' is not on the allowlist {path} "
                        "(1 names)\n")
