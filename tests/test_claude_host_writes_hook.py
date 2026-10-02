"""The agent guards in `.claude/settings.json` (the operator, 2026-10-02; rules_audit check 5).

1. `scripts/hooks/claude-no-host-writes`, driven as Claude Code drives it (JSON on stdin,
   exit 2 refuses): deploying, or any git verb that writes, in the part of a command run ON
   A LAB HOST is refused, naming what; reading on a host and git on the laptop's own
   checkout run; an unreadable input is a visible hook error, never a silent pass.
2. The personal-data connectors (email, calendar, cloud files) are denied by permission
   rule, so asking for one cannot happen by accident (CLAUDE.md: no personal-data
   connectors).
3. Both are wired in the COMMITTED settings, for every Bash call.
"""

import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(ROOT, "scripts", "hooks", "claude-no-host-writes")
SETTINGS = os.path.join(ROOT, ".claude", "settings.json")


def run(command, raw=None):
    payload = raw if raw is not None else json.dumps(
        {"tool_name": "Bash", "tool_input": {"command": command}})
    return subprocess.run([sys.executable, HOOK], input=payload, capture_output=True, text=True)


REFUSED = [
    ("scripts/nmas-host nmas -- nmas-deploy --wait", "nmas-deploy"),
    ("scripts/nmas-host nmas -- 'cd ~/app && git pull'", "git pull"),
    ("scripts/nmas-host nmas -- git -C /srv/app push origin main", "git push"),
    ("scripts/nmas-host clab -- bash -lc 'cd labs/lab; git commit -am x'", "git commit"),
    ("nmas-host nmas -- git checkout -- data/x", "git checkout"),
    ("ssh -p 22 someone@host 'git reset --hard'", "git reset"),
    ("ssh host ~/bin/nmas-deploy", "nmas-deploy"),
    ("echo x && scripts/nmas-host nmas -- git fetch origin", "git fetch"),
]

ALLOWED = [
    "scripts/nmas-host nmas -- git -C /srv/app log --oneline -3",
    "scripts/nmas-host nmas -- 'git status --short; cat /srv/app/VERSION'",
    "scripts/nmas-host pve -- pvesh get /nodes",
    "git push -q",                                   # the laptop's own checkout
    "git commit -q -F msg.txt && git push -q",
    "scripts/nmas-deploy --help",                    # not on a host
    "ssh -V",
]


class TestTheHook:
    @pytest.mark.parametrize("command,what", REFUSED, ids=[c[1] + str(i) for i, c in
                                                            enumerate(REFUSED)])
    def test_a_write_on_a_host_is_refused_naming_it(self, command, what):
        r = run(command)
        assert r.returncode == 2, (command, r.stderr)
        assert f"runs {what} on a lab host" in r.stderr and "operator" in r.stderr

    @pytest.mark.parametrize("command", ALLOWED)
    def test_reading_on_a_host_and_git_here_run(self, command):
        r = run(command)
        assert r.returncode == 0, (command, r.stderr)

    def test_an_unreadable_input_is_a_visible_hook_error(self):
        r = run("", raw="not json")
        assert r.returncode == 1 and "could not read the tool call" in r.stderr


class TestTheSettings:
    def _settings(self):
        return json.load(open(SETTINGS, encoding="utf-8"))

    def test_the_hook_is_wired_to_every_bash_call(self):
        hooks = [h["command"] for entry in self._settings()["hooks"]["PreToolUse"]
                 if entry.get("matcher") == "Bash" for h in entry["hooks"]]
        assert any(c.endswith("/scripts/hooks/claude-no-host-writes") for c in hooks), hooks
        assert any(c.endswith("/scripts/hooks/claude-no-heredoc-interpreter") for c in hooks)

    def test_the_personal_data_connectors_are_denied(self):
        deny = set(self._settings()["permissions"]["deny"])
        for server in ("Gmail", "Google_Calendar", "Google_Drive"):
            assert f"mcp__claude_ai_{server}" in deny, server
