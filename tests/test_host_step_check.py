"""A commit that changes a file a person installs on the host says what the
host needs (the operator, 2026-09-30): `Host-Step:` or `Host-Step-None:`,
refused by the commit-msg hook and by CI over the pushed range.

Driven against REAL git repositories. The rule's first run, over the
operator's range af8630a..e7b80c7, named 7551c2a (scripts/nmas-deploy changed,
no step said): the case it exists for.
"""
import importlib.machinery
import importlib.util
import os
import subprocess
from pathlib import Path

import re

import pytest
import yaml

from tests.source_index import tracked

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "nmas-host-step-check"


@pytest.fixture(scope="module")
def hs():
    loader = importlib.machinery.SourceFileLoader("nmas_host_step_check", str(SCRIPT))
    spec = importlib.util.spec_from_loader("nmas_host_step_check", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def _git(repo, *args):
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com")
    return subprocess.run(["git", "-C", str(repo), *args], check=True, env=env,
                          capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    _git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "README").write_text("x\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "start")
    return tmp_path


def _commit(repo, path, message):
    p = repo / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(p.read_text() + "y\n" if p.exists() else "y\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _run(repo, *args):
    return subprocess.run(["python3", str(SCRIPT), *args], cwd=repo,
                          capture_output=True, text=True)


class TestTheRange:
    def test_a_host_file_with_nothing_said_is_refused_by_name(self, repo):
        sha = _commit(repo, "scripts/nmas-deploy", "change the gate")
        p = _run(repo, "--range", "HEAD~1..HEAD")
        assert p.returncode == 1
        assert sha[:12] in p.stderr and "scripts/nmas-deploy" in p.stderr
        assert "Host-Step-None" in p.stderr

    @pytest.mark.parametrize("path", ["deploy/update/nmas-update", "deploy/systemd/x.service",
                                      "deploy/topology/rcn-topology.py", "scripts/nmas-deploy"])
    def test_a_step_said_passes(self, repo, path):
        check = {"deploy/update/nmas-update": "[updater] ", "scripts/nmas-deploy": "[updater] ",
                 "deploy/topology/rcn-topology.py": "[topology-renderer] "}.get(path, "")
        _commit(repo, path, f"change\n\nHost-Step: {check}re-install it as root")
        assert _run(repo, "--range", "HEAD~1..HEAD").returncode == 0

    def test_none_with_its_reason_passes(self, repo):
        _commit(repo, "deploy/update/nmas-update", "a comment\n\nHost-Step-None: a comment only")
        assert _run(repo, "--range", "HEAD~1..HEAD").returncode == 0

    def test_an_empty_trailer_is_not_a_statement(self, repo):
        _commit(repo, "deploy/update/nmas-update", "change\n\nHost-Step:")
        assert _run(repo, "--range", "HEAD~1..HEAD").returncode == 1

    def test_a_file_not_installed_on_the_host_needs_nothing(self, repo):
        _commit(repo, "modules/x.py", "change")
        _commit(repo, "scripts/nmas-deploy-notes", "a sibling name, not the gate")
        assert _run(repo, "--range", "HEAD~2..HEAD").returncode == 0

    def test_every_commit_in_the_range_is_asked(self, repo):
        bad = _commit(repo, "deploy/systemd/a.timer", "first")
        _commit(repo, "deploy/systemd/b.timer", "second\n\nHost-Step: install b")
        p = _run(repo, "--range", "HEAD~2..HEAD")
        assert p.returncode == 1 and bad[:12] in p.stderr and p.stderr.count("REFUSED") == 1

    def test_a_range_git_cannot_read_is_not_a_pass(self, repo):
        p = _run(repo, "--range", "nosuch..HEAD")
        assert p.returncode == 2 and "COULD NOT ASK" in p.stderr


class TestAStepNamesTheCheckThatMeasuresIt:
    """C416 (the operator, 2026-10-04): c2440a6's step for the Oxidized helper asked the
    operator to say it was done, while C375's check already measured it. A commit changing a
    path a check answers for names that check in its step."""

    def test_the_helpers_step_without_its_check_is_refused_naming_it(self, repo):
        sha = _commit(repo, "scripts/nmas-oxidized-cred",
                      "change\n\nHost-Step-After: re-install the Oxidized helper")
        p = _run(repo, "--range", "HEAD~1..HEAD")
        assert p.returncode == 1 and sha[:12] in p.stderr
        assert "scripts/nmas-oxidized-cred (check [oxidized-cred])" in p.stderr

    def test_with_its_check_it_passes(self, repo):
        _commit(repo, "scripts/nmas-oxidized-cred",
                "change\n\nHost-Step-After: [oxidized-cred] re-install the Oxidized helper")
        assert _run(repo, "--range", "HEAD~1..HEAD").returncode == 0

    def test_another_checks_name_does_not_cover_it(self, repo):
        _commit(repo, "scripts/nmas-oxidized-cred",
                "change\n\nHost-Step-After: [updater] re-install the Oxidized helper")
        assert _run(repo, "--range", "HEAD~1..HEAD").returncode == 1

    def test_none_needs_no_check(self, repo):
        _commit(repo, "scripts/nmas-oxidized-cred", "a comment\n\nHost-Step-None: a comment only")
        assert _run(repo, "--range", "HEAD~1..HEAD").returncode == 0

    def test_two_helpers_need_both_checks(self, hs):
        msg = "x\n\nHost-Step-After: [updater] re-install the updater"
        why = hs.unnamed_check(["scripts/nmas-deploy", "scripts/nmas-oxidized-cred"], msg)
        assert "scripts/nmas-oxidized-cred (check [oxidized-cred])" in why
        assert "scripts/nmas-deploy" not in why

    def test_a_path_no_check_answers_for_needs_none(self, hs):
        assert hs.unnamed_check(["deploy/systemd/x.service"], "x\n\nHost-Step: install x") == ""


class TestAValueFromTheAppsSettingsIsConfirmed:
    """C424 (the operator, 2026-10-04, installing 487b1da's pin): the step read the router.db
    path from the app's own settings and installed it unseen; the app can write its settings,
    so the step shows the value and installs only on the operator's "y"."""

    READ = ("p=$(python3 -c 'import json; print(json.load(open(\"data/user_settings.json\"))"
            ".get(\"oxidized_router_db\"))')")

    def test_487b1das_step_is_refused_naming_why(self, hs):
        why = hs.unsafe_step(f"x\n\nHost-Step-After: [oxidized-cred] {self.READ} && "
                             "d=$(mktemp -d) && sudo install -m 0644 \"$d/a\" /etc/nmas/a")
        assert "installs a value read from the app's own settings without showing it" in why

    def test_shown_and_confirmed_it_passes(self, hs):
        assert hs.unsafe_step(f"x\n\nHost-Step-After: [oxidized-cred] {self.READ} && printf "
                              "'Pin %s? [y/N] ' \"$p\" && read -r ok && [ \"$ok\" = y ] && "
                              "d=$(mktemp -d) && sudo install -m 0644 \"$d/a\" /etc/nmas/a") == ""

    def test_a_read_that_does_not_gate_on_y_is_not_a_confirmation(self, hs):
        assert hs.unsafe_step(f"x\n\nHost-Step: {self.READ} && read -r ok; d=$(mktemp -d)") != ""


class TestTheCommitBeingMade:
    def test_the_staged_files_and_the_message_are_read(self, repo, tmp_path_factory):
        (repo / "deploy" / "update").mkdir(parents=True)
        (repo / "deploy" / "update" / "nmas-update").write_text("z\n")
        _git(repo, "add", "-A")
        msg = tmp_path_factory.mktemp("m") / "MSG"
        msg.write_text("change\n\n# Host-Step: in git's comment template, not said\n")
        assert _run(repo, "--message", str(msg)).returncode == 1
        msg.write_text("change\n\nHost-Step: [updater] re-install the updater\n")
        assert _run(repo, "--message", str(msg)).returncode == 0

    def test_the_hook_runs_the_check(self):
        hook = (ROOT / "scripts" / "hooks" / "commit-msg").read_text()
        assert 'nmas-host-step-check" --message "$1"' in hook
        assert os.access(ROOT / "scripts" / "hooks" / "commit-msg", os.X_OK)


class TestOneList:
    def test_every_updater_source_needs_a_word_about_the_host(self, hs):
        from modules.readers.app_pushed import UPDATER_SOURCES
        assert len(UPDATER_SOURCES) >= 4
        assert hs.host_paths(UPDATER_SOURCES) == list(UPDATER_SOURCES)

    def test_none_is_never_listed_as_a_step_to_do(self):
        from modules.readers.app_pushed import HOST_STEP
        assert HOST_STEP.findall("x\n\nHost-Step-None: a comment only\n") == []
        assert HOST_STEP.findall("x\n\nHost-Step: do it\n") == ["do it"]

    def test_ci_runs_it_over_the_pushed_range(self):
        doc = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text())
        runs = [s.get("run", "") for s in doc["jobs"]["test"]["steps"]]
        assert any('nmas-host-step-check --range "$RANGE"' in r for r in runs)


#: 404db02's own step, verbatim: it installed `/tmp/nmas-units/*.service`, and
#: that shared folder still held units rendered for the updater's earlier
#: install (the operator, 2026-10-01).
STEP_404DB02 = ("Host-Step-After: Install the job units so a finished job wakes job health: "
                "scripts/nmas-render-units --out /tmp/nmas-units deploy/systemd/nmas-job-finished@.service "
                "deploy/systemd/nmas-startup-check.service deploy/systemd/nmas-heartbeat-check.service "
                "deploy/systemd/nmas-netbox-backup.service deploy/systemd/nmas-netbox-restore-test.service "
                "&& sudo install -m 0644 /tmp/nmas-units/*.service /etc/systemd/system/ "
                "&& sudo systemctl daemon-reload")
FRESH = ('Host-Step-After: Install the job units: d=$(mktemp -d) && scripts/nmas-render-units '
         '--out "$d" deploy/systemd/a.service && sudo install -m 0644 "$d/a.service" '
         '/etc/systemd/system/ && sudo systemctl daemon-reload')


class TestAStepInstallsOnlyWhatItNames:
    def test_the_404db02_step_is_refused_for_its_fixed_folder(self, hs):
        why = hs.unsafe_step("x\n\n" + STEP_404DB02 + "\n")
        assert why.startswith("Host-Step-After renders into a fixed folder (/tmp/nmas-units)")
        assert hs.problem(["deploy/systemd/x.service"], "x\n\n" + STEP_404DB02) == why

    def test_a_glob_install_is_refused_even_from_a_fresh_folder(self, hs):
        step = FRESH.replace('"$d/a.service"', '"$d"/*.service')
        why = hs.unsafe_step("x\n\n" + step)
        assert why.startswith("Host-Step-After installs by a glob") and "*.service" in why

    def test_a_fresh_folder_and_named_files_pass(self, hs):
        assert hs.unsafe_step("x\n\n" + FRESH) == ""
        assert hs.problem(["deploy/systemd/a.service"], "x\n\n" + FRESH) == ""
        assert hs.unsafe_step("x\n\nHost-Step: restart nmas-topology (`sudo systemctl "
                              "restart nmas-topology`)") == ""

    def test_the_range_check_refuses_it_on_a_pushed_commit(self, repo):
        sha = _commit(repo, "deploy/systemd/x.service", "units\n\n" + STEP_404DB02)
        p = _run(repo, "--range", "HEAD~1..HEAD")
        assert p.returncode == 1 and sha[:12] in p.stderr and "fixed folder" in p.stderr


class TestAStepCarriesEveryValue:
    """The operator, 2026-10-01: the telemetry rules' step said
    `--datasource-uid <...>`, a value the person then had to go and find."""

    TELEMETRY = ("Host-Step-After: scripts/nmas-telemetry-rules --datasource-uid <loki-uid> "
                 "--write")

    def test_a_placeholder_is_refused_naming_it(self, hs):
        why = hs.unsafe_step("x\n\n" + self.TELEMETRY)
        assert why.startswith("Host-Step-After carries a placeholder (<loki-uid>)")
        assert hs.problem(["deploy/systemd/x.service"], "x\n\n" + self.TELEMETRY) == why

    def test_the_filled_in_step_passes_and_a_redirect_is_not_a_placeholder(self, hs):
        assert hs.unsafe_step("x\n\n" + self.TELEMETRY.replace("<loki-uid>",
                                                                "efwpn8hr7sfeob")) == ""
        assert hs.unsafe_step("x\n\nHost-Step: sudo tee /etc/x < /tmp/y 2>&1 && "
                              "cat <<EOF >/dev/null") == ""

    def test_a_none_trailer_is_never_read_as_a_step(self, hs):
        assert hs.unsafe_step("x\n\nHost-Step-None: nothing to fill in (<none>)") == ""


#: Records of what HAPPENED, which quote the old command as the finding
#: (C284), never a recipe anybody follows: the register and the writeup.
HISTORY = {"docs/OPEN_FINDINGS.md", "docs/NSOT_WRITEUP.md", "docs/NSOT_WRITEUP_NOTES.md"}


def _recipe_lines():
    """Every line in the repository that renders units or installs what was
    rendered: the docs, the unit headers, the scripts, and the Update button's
    commands (modules/update_op.py)."""
    out = []
    for p in map(Path, tracked("docs", "deploy", "scripts", "modules", root=ROOT)):
        if not p.is_file() or p.suffix in (".pyc", ".json", ".png") or "__pycache__" in p.parts:
            continue
        if p.relative_to(ROOT).as_posix() in HISTORY:
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if "nmas-render-units --out" in line or re.search(r"\binstall\b.*(/tmp/|\$d)", line):
                out.append((f"{p.relative_to(ROOT)}:{i}", line))
    return out


def test_every_recipe_renders_into_a_fresh_folder_and_installs_by_name():
    lines = _recipe_lines()
    renders = [l for _w, l in lines if "nmas-render-units --out" in l]
    assert len(renders) >= 12, renders                      # the floor: the scan finds them
    bad = [w for w, l in lines
           if re.search(r"--out\s+(?![\"']?\$)/", l)
           or re.search(r"\binstall\b[^&;]*(/tmp/nmas-units|\S*\*\S*)", l)]
    assert bad == [], bad
