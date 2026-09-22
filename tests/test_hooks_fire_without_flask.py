"""A commit made outside a web request must still publish.

Measured on the deployed instance. The 1.4 repair committed `2443892` from a
CLI script; local HEAD moved, remote main stayed at `3d1fbf2`, and the log
carried **no hooks line at all** for that commit. The Remote card still showed
the previous day's push -- and was right. The card was reporting accurately
and the defect was upstream of it.

`register_default_hooks()` was called from `app.py` only, so registration
followed **the app starting** rather than **the repo module being used**. Any
process without Flask -- a CLI repair, a cron job, a maintenance script --
found an empty registry, and `run_post_commit()` returned at `if not hooks`
without a word.

That is the same shape as the missing `run_post_commit` call in 1.2: a commit
that could have been published, was not, and nothing anywhere said so.

The first test runs in a **separate interpreter**. Importing `app` anywhere in
this process would register the hooks and hide exactly the thing under test.
"""

import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestRegistrationFollowsTheModuleNotTheApp:
    def test_a_fresh_process_has_no_hooks_until_something_commits(self):
        """The precondition. If this ever fails, the test below proves
        nothing, because the hooks would already be there."""
        code = ("import sys; sys.path.insert(0, %r)\n"
                "from modules.nsot import hooks\n"
                "print(hooks.registered())\n" % ROOT)
        out = subprocess.run([sys.executable, "-c", code], capture_output=True,
                             text=True, timeout=120)
        assert out.stdout.strip() == "[]", out.stdout + out.stderr

    def test_run_post_commit_registers_them_itself(self):
        """In a process that never imports Flask."""
        code = ("import sys; sys.path.insert(0, %r)\n"
                "from modules.nsot import hooks\n"
                "assert 'flask' not in sys.modules\n"
                "hooks.run_post_commit({'list_name': '', 'repo': '', 'sha': 'x'})\n"
                "assert 'flask' not in sys.modules, 'importing flask would hide the bug'\n"
                "print(sorted(hooks.registered()))\n" % ROOT)
        out = subprocess.run([sys.executable, "-c", code], capture_output=True,
                             text=True, timeout=120)
        assert out.returncode == 0, out.stderr
        assert out.stdout.strip() == "['git-push', 's3-archive']", out.stdout

    def test_app_is_no_longer_the_only_registrar(self):
        import inspect

        from modules.nsot import hooks

        source = inspect.getsource(hooks.run_post_commit)
        assert "ensure_default_hooks()" in source

    def test_registration_is_idempotent(self):
        from modules.nsot import hooks

        hooks.ensure_default_hooks()
        first = sorted(hooks.registered())
        hooks.ensure_default_hooks()
        assert sorted(hooks.registered()) == first


class TestACommitFromAScriptPushes:
    """End to end in a separate process: commit, push, record."""

    def test_a_cli_commit_reaches_the_remote(self, tmp_path):
        bare = str(tmp_path / "remote.git")
        subprocess.run(["git", "init", "-q", "-b", "main", "--bare", bare],
                       check=True)

        script = f'''
import os, sys, json
sys.path.insert(0, {ROOT!r})
list_dir = {str(tmp_path / "lab")!r}
os.makedirs(os.path.join(list_dir, "config_repo"), exist_ok=True)

import modules.config as config
config.get_list_data_dir = lambda name: list_dir
config.get_current_list_name = lambda: "lab"

import modules.settings_schema as ss
_real = ss.get_setting
ss.get_setting = lambda key, default=None: {{
    "nsot_git_author_name": "NMAS", "nsot_git_author_email": "n@l",
    "nsot_device_tag_retention": 50}}.get(key, _real(key, default))

from modules.nsot import remote as R, repo as _repo
R.load_remote = lambda name: {{"owner": "o", "repo": "r", "auto_push": True,
                              "branch": "main"}}
R.remote_url = lambda config: {bare!r}
R.auto_push_decision = lambda name, repo: {{"push": True, "reason": "ok"}}
_recorded = {{}}
R.record_push = lambda list_name, **kw: _recorded.update(kw)

assert "flask" not in sys.modules
_repo.init_repo(os.path.join(list_dir, "config_repo"))
from modules.nsot import hostvars
hostvars.write_committed(os.path.join(list_dir, "config_repo"),
                         {{"hostname": "s1", "interfaces": []}})
out = _repo.save_host_vars("lab", ["s1"], actor="dmarchak")
assert out["ok"], out

from modules.nsot import hooks
import time
for _ in range(100):
    if _recorded:
        break
    time.sleep(0.1)
print(json.dumps({{"commit": out["commit"], "recorded": _recorded}}))
'''
        out = subprocess.run([sys.executable, "-c", script],
                             capture_output=True, text=True, timeout=180)
        assert out.returncode == 0, out.stderr
        import json

        result = json.loads(out.stdout.strip().splitlines()[-1])

        remote_refs = subprocess.run(["git", "ls-remote", bare],
                                     capture_output=True, text=True)
        assert "refs/heads/main" in remote_refs.stdout, (
            "the CLI commit never reached the remote")
        assert result["recorded"], "last_push was not recorded"
        assert result["recorded"]["commit"].startswith(result["commit"][:8])


class TestAnEmptyRegistryIsReported:
    """Reached only when registration itself fails. Silence there would
    recreate the defect exactly: a repository with a remote, a commit made,
    and nothing recording that it never went out."""

    def test_a_configured_remote_with_no_hooks_is_an_error(self, monkeypatch,
                                                           caplog):
        from modules.nsot import hooks, remote as R

        monkeypatch.setattr(hooks, "ensure_default_hooks", lambda: [])
        monkeypatch.setattr(hooks, "_hooks", [])
        monkeypatch.setattr(R, "load_remote",
                            lambda name: {"owner": "o", "repo": "r"})
        failures = []
        monkeypatch.setattr(R, "record_push_failure",
                            lambda name, **kw: failures.append(kw))

        with caplog.at_level("ERROR"):
            hooks.run_post_commit({"list_name": "lab", "repo": "/tmp/x",
                                   "sha": "abc123def456"})

        assert failures, "nothing recorded the missed push"
        assert "NOT pushed" in failures[0]["reason"]
        assert "abc123def456"[:12] in failures[0]["reason"]
        assert any("hooks" in r.message for r in caplog.records)

    def test_it_says_this_is_a_defect_not_a_choice(self, monkeypatch):
        from modules.nsot import hooks, remote as R

        monkeypatch.setattr(hooks, "ensure_default_hooks", lambda: [])
        monkeypatch.setattr(hooks, "_hooks", [])
        monkeypatch.setattr(R, "load_remote",
                            lambda name: {"owner": "o", "repo": "r"})
        failures = []
        monkeypatch.setattr(R, "record_push_failure",
                            lambda name, **kw: failures.append(kw))
        hooks.run_post_commit({"list_name": "lab", "repo": "/x", "sha": "s"})
        assert "defect, not a configuration choice" in failures[0]["reason"]

    def test_no_remote_configured_is_silent(self, monkeypatch):
        """A list that deliberately has no remote must not cry wolf, or the
        error stops meaning anything."""
        from modules.nsot import hooks, remote as R

        monkeypatch.setattr(hooks, "ensure_default_hooks", lambda: [])
        monkeypatch.setattr(hooks, "_hooks", [])
        monkeypatch.setattr(R, "load_remote", lambda name: None)
        failures = []
        monkeypatch.setattr(R, "record_push_failure",
                            lambda name, **kw: failures.append(kw))
        hooks.run_post_commit({"list_name": "lab", "repo": "/x", "sha": "s"})
        assert failures == []

    def test_a_registration_failure_is_logged_not_swallowed(self, monkeypatch,
                                                            caplog):
        import builtins

        from modules.nsot import hooks

        real_import = builtins.__import__

        def _explode(name, *args, **kwargs):
            if name == "modules.nsot.archive":
                raise ImportError("boom")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _explode)
        with caplog.at_level("ERROR"):
            hooks.ensure_default_hooks()
        assert any("could not register" in r.message for r in caplog.records)
