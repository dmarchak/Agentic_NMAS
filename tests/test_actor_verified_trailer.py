"""P.3 step 10 (register D10): every commit that names an Actor says how that
actor was established, in an ``Actor-Verified:`` trailer.

Before c5a34c1, fourteen routes recorded ``data.get("actor", "user")``, a name
the client typed, so a commit's ``Actor:`` was whatever the request body said.
After it, the actor is the verified one. The two look identical in git, and a
commit's DATE cannot tell them apart, because the host ran old code for a day
after the fix was pushed. So the trailer is written by the code that knows,
at the moment of the commit:

- ``access``: in a request whose gate verified this same actor;
- ``host-shell``: a CLI on the host, where SSH to the host authenticated it;
- ``none``: anything else (the app's background threads, a request whose
  recorded actor is not the verified one).
"""

import ast
import pathlib
import subprocess

import pytest
from flask import Flask, g

from modules import identity, route_gates
from modules.identity import Identity
from modules.nsot import repo as R

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _person(actor="ops@example.com"):
    return Identity(actor=actor, email=actor, kind="person", verified=True,
                    peer_trusted=True)


@pytest.fixture
def cli(monkeypatch):
    monkeypatch.setattr(route_gates, "_installed", False)


@pytest.fixture
def app_process(monkeypatch):
    monkeypatch.setattr(route_gates, "_installed", True)


class TestTheVerdict:
    def test_a_request_verified_as_this_actor_is_access(self):
        with Flask(__name__).test_request_context("/"):
            g.nmas_identity = _person()
            assert identity.actor_verification("ops@example.com") == "access"

    def test_a_request_verified_as_SOMEONE_ELSE_is_none(self):
        """The case the trailer exists for: a body-supplied name beside a gate
        that verified a different one."""
        with Flask(__name__).test_request_context("/"):
            g.nmas_identity = _person()
            assert identity.actor_verification("user") == "none"

    def test_an_unverified_request_is_none(self):
        with Flask(__name__).test_request_context("/"):
            assert identity.actor_verification("unauthenticated") == "none"
            g.nmas_identity = Identity(actor=identity.UNAUTHENTICATED, email="",
                                       kind="", verified=True)
            assert identity.actor_verification(identity.UNAUTHENTICATED) == "none"

    def test_a_cli_is_host_shell(self, cli):
        assert identity.actor_verification("dustin") == "host-shell"

    def test_the_apps_own_threads_are_none(self, app_process):
        """The app process outside a request (the drift scheduler, a hook) is
        not a host shell: nobody logged in to run it."""
        assert identity.actor_verification("ai-agent") == "none"

    def test_install_marks_the_app_process(self, monkeypatch):
        monkeypatch.setattr(route_gates, "_installed", False)
        route_gates.install(Flask(__name__))
        assert route_gates.installed()


class TestTheMessage:
    def test_it_is_added_after_the_actor(self, cli):
        msg = "golden: r1\n\nSource: manual\nActor: dustin\n"
        out = R.with_actor_verification(msg)
        assert out == msg + "Actor-Verified: host-shell\n"

    def test_a_message_without_a_trailing_newline(self, cli):
        out = R.with_actor_verification("x\n\nActor: dustin")
        assert out.endswith("\nActor: dustin\nActor-Verified: host-shell")

    def test_no_actor_no_trailer(self, cli):
        assert R.with_actor_verification("template: seed library") == "template: seed library"

    def test_a_message_that_already_says_is_unchanged(self, cli):
        msg = "x\n\nActor: a\nActor-Verified: access\n"
        assert R.with_actor_verification(msg) == msg


def _last_message(repo):
    return subprocess.run(["git", "-C", repo, "log", "-1", "--format=%B"],
                          capture_output=True, text=True, check=True).stdout


def _init(tmp_path):
    repo = str(tmp_path / "config_repo")
    R.init_repo(repo)
    return repo


class TestEveryCommitThroughTheChokePoint:
    def test_a_cli_commit_carries_host_shell(self, tmp_path, cli):
        repo = _init(tmp_path)
        (tmp_path / "config_repo" / "f").write_text("x\n")
        R.git(repo, "add", "f")
        rc, _, err = R.git(repo, "commit", "-m", "t\n\nSource: manual\nActor: dustin\n")
        assert rc == 0, err
        assert "Actor-Verified: host-shell" in _last_message(repo)

    def test_a_request_commit_carries_access(self, tmp_path):
        repo = _init(tmp_path)
        (tmp_path / "config_repo" / "f").write_text("x\n")
        R.git(repo, "add", "f")
        with Flask(__name__).test_request_context("/"):
            g.nmas_identity = _person()
            R.git(repo, "commit", "-m", "t\n\nActor: ops@example.com\n")
        assert "Actor-Verified: access" in _last_message(repo)

    def test_save_golden_carries_it(self, tmp_path, monkeypatch, cli):
        """The busiest writer, driven whole rather than through git()."""
        monkeypatch.setattr("modules.config.LISTS_DIR", str(tmp_path))
        monkeypatch.setattr("modules.config.get_list_data_dir",
                            lambda name: str(tmp_path / name))
        (tmp_path / "t").mkdir()
        out = R.save_golden("t", [R.GoldenItem("r1", "hostname r1\n", "192.0.2.1")],
                            source="manual", actor="dustin", allow_new=True)
        assert out.get("ok"), out
        msg = _last_message(str(tmp_path / "t" / "config_repo"))
        assert "Actor: dustin" in msg and "Actor-Verified: host-shell" in msg


def _commit_calls(path):
    """(function name, call) for every ``*git(..., "commit", ...)`` in a file."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for call in ast.walk(fn):
            if not isinstance(call, ast.Call):
                continue
            f = call.func
            callee = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
            # direct arguments only, or the elements of a command list: a
            # keyword such as kind="commit" is a label, not a git subcommand
            args = [e for a in call.args
                    for e in (a.elts if isinstance(a, (ast.List, ast.Tuple)) else [a])]
            consts = [a.value for a in args if isinstance(a, ast.Constant)]
            # a git transport: a *git* helper, or a command list naming git
            if "commit" in consts and ("git" in callee.lower() or "git" in consts):
                yield fn.name, callee


class TestNoWriterGoesAround:
    """A writer that commits through its own transport never gets the trailer.
    Population by proxy: this lists every commit call in modules/ and scripts/
    and requires each to be NSoT's git() or a named exception."""

    #: (file, function) → why it may commit without git().
    EXEMPT = {
        ("modules/config_git.py", "commit_configs"):
            "the legacy Git tab: its own _git, and it calls with_actor_verification itself",
        ("modules/config_git.py", "init_config_repo"):
            "the repository's empty first commit, which names no actor",
    }

    def _all(self):
        files = list((ROOT / "modules").rglob("*.py")) + [
            p for p in (ROOT / "scripts").iterdir()
            if p.is_file() and (p.suffix == ".py" or b"python" in p.read_bytes()[:40])]
        for p in files:
            for fn, callee in _commit_calls(p):
                yield str(p.relative_to(ROOT)), fn, callee

    def test_the_scan_finds_something(self):
        found = list(self._all())
        assert len(found) >= 3, found
        assert any(f == "modules/nsot/repo.py" for f, _, _ in found)
        assert any(f == "modules/config_git.py" for f, _, _ in found)

    def test_every_commit_goes_through_git_or_is_named(self):
        bad = [(f, fn, c) for f, fn, c in self._all()
               if c != "git" and (f, fn) not in self.EXEMPT]
        assert not bad, bad

    def test_every_exemption_still_exists(self):
        """No ghosts: an exemption for a call that is gone is a gap waiting."""
        seen = {(f, fn) for f, fn, _ in self._all()}
        assert set(self.EXEMPT) <= seen, set(self.EXEMPT) - seen

    def test_the_legacy_tab_names_its_actor(self):
        src = (ROOT / "modules" / "config_git.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == "commit_configs")
        names = {n.id if isinstance(n, ast.Name) else getattr(n, "attr", "")
                 for n in ast.walk(fn)}
        assert {"request_actor", "with_actor_verification"} <= names


class TestAbandonNamesItsActor:
    def test_the_abandon_commit_carries_an_actor(self):
        """It committed with no Actor while holding one, so it would have been
        the only NSoT commit the trailer could not reach."""
        src = (ROOT / "modules" / "nsot" / "onboard.py").read_text(encoding="utf-8")
        i = src.index("onboarding withdrawn")
        assert "Actor: {actor" in src[i:i + 200]


class TestThroughTheApp:
    """End to end: a gated route in the real app, the harness's verified
    person, and the commit read back from git. The unit tests above construct
    the request context themselves, which is the seam this closes: nothing
    there shows the gate puts on ``g`` what ``actor_verification`` reads."""

    def test_a_gated_route_commits_access(self, tmp_path, monkeypatch):
        import app as app_module
        from tests.conftest import TEST_PERSON

        monkeypatch.setattr("modules.config.LISTS_DIR", str(tmp_path))
        monkeypatch.setattr("modules.config.get_list_data_dir",
                            lambda name: str(tmp_path / name))
        (tmp_path / "t" / "config_repo" / "templates").mkdir(parents=True)
        client = app_module.app.test_client()
        resp = client.post("/templates/bindings", json={"list_name": "t"})
        assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
        msg = _last_message(str(tmp_path / "t" / "config_repo"))
        assert f"Actor: {TEST_PERSON}" in msg, msg
        assert "Actor-Verified: access" in msg, msg
