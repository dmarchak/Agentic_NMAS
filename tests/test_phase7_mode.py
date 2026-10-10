"""The Phase 7 operating mode's two scripts (the operator's decision, 2026-10-09):
scripts/host-steps/phase7-mode-on.sh and phase7-mode-off.sh, run end to end in a temporary copy
of the checkout (CLAUDE.md, .gitignore, the hook, the scripts, a git repository), never the
real one.

On shows the change and writes nothing unless answered y; then CLAUDE.md holds the marked
section once, unchanged outside it, the flag is owner-only, and the real hook, run from the
copy, lets nmas-deploy on a host through and still refuses a git pull. Off returns CLAUDE.md to
its bytes from before, or keeps an edit made during the mode and says so, and the hook refuses
the deploy again. The section passes CLAUDE.md's own checks (every path it names exists), so
committing CLAUDE.md with the mode on keeps CI green.
"""

import os
import shutil
import subprocess

import pytest

from tests.test_claude_md import missing_paths, unenforced

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BEGIN = "<!-- phase7-mode: begin -->"
COPIED = ["CLAUDE.md", ".gitignore", "scripts/hooks/claude-no-host-writes",
          "scripts/host-steps/lib.sh", "scripts/host-steps/phase7-mode-on.sh",
          "scripts/host-steps/phase7-mode-off.sh"]


@pytest.fixture
def checkout(tmp_path):
    for rel in COPIED:
        dest = tmp_path / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(os.path.join(ROOT, rel), dest)
    # Each copy starts with the mode off, whatever the checkout's own state: the committed
    # CLAUDE.md holds the section while the operator's mode is on.
    md = tmp_path / "CLAUDE.md"
    if BEGIN in md.read_text():
        md.write_text(strip(md.read_text()))
    (tmp_path / ".claude").mkdir()
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    return tmp_path


def run(checkout, which, answer="y"):
    env = {k: v for k, v in os.environ.items() if k != "NMAS_PHASE7_FLAG"}
    return subprocess.run(["bash", str(checkout / "scripts" / "host-steps" / f"phase7-mode-{which}.sh")],
                          input=answer + "\n", capture_output=True, text=True, timeout=60, env=env)


def strip(text):
    """The section and the blank line after it removed: an independent path from the scripts'
    awk (a Python slice on the marker lines)."""
    lines = text.split("\n")
    b = lines.index(BEGIN)
    e = lines.index("<!-- phase7-mode: end -->")
    assert lines[e + 1] == ""
    return "\n".join(lines[:b] + lines[e + 2:])


def test_on_writes_the_section_and_the_flag_and_the_hook_lets_a_deploy_through(checkout):
    before = (checkout / "CLAUDE.md").read_text()
    got = run(checkout, "on")
    assert got.returncode == 0, got.stdout + got.stderr
    assert "== RESULT: PASS (10 of 10 checks)" in got.stdout
    assert "== THE CHANGE" in got.stdout and "+## Phase 7 operating mode (in force)" in got.stdout
    after = (checkout / "CLAUDE.md").read_text()
    assert after.count(BEGIN) == 1
    assert after.index(BEGIN) < after.index("\n## Project\n")
    assert strip(after) == before
    flag = checkout / ".claude" / "phase7-mode"
    assert oct(flag.stat().st_mode & 0o777) == "0o600" and not flag.is_symlink()
    assert "PASS  the hook lets nmas-deploy on a host through" in got.stdout
    assert "PASS  the hook still refuses a git pull on a host" in got.stdout


def test_the_section_passes_claude_md_s_own_checks(checkout):
    assert run(checkout, "on").returncode == 0
    text = (checkout / "CLAUDE.md").read_text()
    section = text[text.index(BEGIN):text.index("<!-- phase7-mode: end -->")]
    found, missing = missing_paths(section)
    assert "docs/STANDING_APPROVAL_LOG.md" in found and "docs/END_OF_SESSION.md" in found
    assert missing == [], missing
    assert unenforced(text) == []
    for stop in ("any secret value", "anything outside the lab", "third-party package licence",
                 "deleting or rotating backups or snapshots"):
        assert stop in section, stop


def test_an_answer_other_than_y_changes_nothing(checkout):
    before = (checkout / "CLAUDE.md").read_bytes()
    got = run(checkout, "on", answer="n")
    assert got.returncode == 1 and "Nothing changed." in got.stdout
    assert (checkout / "CLAUDE.md").read_bytes() == before
    assert not (checkout / ".claude" / "phase7-mode").exists()


def test_on_twice_is_refused_and_changes_nothing(checkout):
    assert run(checkout, "on").returncode == 0
    during = (checkout / "CLAUDE.md").read_bytes()
    got = run(checkout, "on")
    assert got.returncode == 1 and "FAIL  the mode is off" in got.stdout
    assert (checkout / "CLAUDE.md").read_bytes() == during


def test_off_restores_the_bytes_from_before_and_the_hook_refuses_again(checkout):
    before = (checkout / "CLAUDE.md").read_bytes()
    assert run(checkout, "on").returncode == 0
    got = run(checkout, "off")
    assert got.returncode == 0, got.stdout + got.stderr
    assert "== RESULT: PASS (7 of 7 checks)" in got.stdout
    assert "returns to exactly what it was before mode-on" in got.stdout
    assert (checkout / "CLAUDE.md").read_bytes() == before
    assert not (checkout / ".claude" / "phase7-mode").exists()
    assert "PASS  the hook refuses nmas-deploy on a host again" in got.stdout


def test_off_keeps_an_edit_made_during_the_mode_and_says_so(checkout):
    assert run(checkout, "on").returncode == 0
    md = checkout / "CLAUDE.md"
    md.write_text(md.read_text().replace("## Running the App", "## Running the App\n\nAn edit."))
    got = run(checkout, "off")
    assert got.returncode == 0, got.stdout
    assert "edits made" in got.stdout and "which are kept" in got.stdout
    text = md.read_text()
    assert "An edit." in text and "phase7-mode:" not in text


def test_off_with_nothing_on_is_refused(checkout):
    before = (checkout / "CLAUDE.md").read_bytes()
    got = run(checkout, "off")
    assert got.returncode == 1 and "FAIL  the mode is on: its flag or its section" in got.stdout
    assert (checkout / "CLAUDE.md").read_bytes() == before


def test_on_puts_claude_md_back_when_a_check_after_the_answer_fails(checkout):
    """The undo: a hook that lets nothing through any more (its flag check removed) fails
    "the hook lets nmas-deploy on a host through", and CLAUDE.md and the flag are put back."""
    hook = checkout / "scripts" / "hooks" / "claude-no-host-writes"
    hook.write_text(hook.read_text().replace("in_mode = phase7_mode()", "in_mode = False"))
    before = (checkout / "CLAUDE.md").read_bytes()
    got = run(checkout, "on")
    assert got.returncode == 1 and "FAIL  the hook lets nmas-deploy on a host through" in got.stdout
    assert "== ON FAILURE: put CLAUDE.md back and remove the flag" in got.stdout
    assert (checkout / "CLAUDE.md").read_bytes() == before
    assert not (checkout / ".claude" / "phase7-mode").exists()
