"""The config repository's check (C725): one script needing no device, no secret and no data
directory; Mercury running the same code before it commits; the config repository's workflow
running the script on every push.

The world is a real one: r2's real capture as its golden, its intent as the parser extracts it,
the shipped templates seeded into the network's library, committed through Mercury's own write
paths. Each planted fault is checked twice, through the script (a subprocess, as GitHub runs
it) and through Mercury's commit, and the two must name the same check, file and line.
"""

import json
import os
import re
import subprocess
import sys
import textwrap

import pytest
import yaml

from tests.test_intent_match import R2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "nmas-config-check")
WORKFLOW = os.path.join(ROOT, "deploy", "config-repo", "nmas-config-check.yml")
LIST = "Lab"


@pytest.fixture
def lab(tmp_path, monkeypatch):
    from modules.nsot import hostvars, templates_repo
    from modules.nsot.parsers import get_parser
    from modules.nsot.repo import GoldenItem, save_golden, save_host_vars, save_templates

    list_dir = tmp_path / "lab"
    repo = str(list_dir / "config_repo")
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(list_dir))
    monkeypatch.setattr("modules.config.get_current_list_name", lambda: LIST)
    monkeypatch.setattr("modules.nsot.hooks.run_post_commit", lambda ctx: None)
    monkeypatch.setattr("modules.settings_schema.get_setting",
                        lambda key, default=None: {
                            "nsot_git_author_name": "NMAS",
                            "nsot_git_author_email": "nmas@localhost"}.get(key, default))
    os.makedirs(repo, exist_ok=True)
    seeded = templates_repo.seed_templates(repo)["copied"]
    assert save_templates(LIST, [f for f in seeded])["ok"]
    captured = open(R2, encoding="utf-8").read()
    assert save_golden(LIST, [GoldenItem("r2", captured, "203.0.113.12",
                                         platform="cisco_iosxe")],
                       source="capture", actor="t", allow_new=True, baseline=False)["ok"]
    hostvars.write_committed(repo, get_parser("cisco_iosxe").parse(captured))
    assert save_host_vars(LIST, ["r2"], actor="t")["ok"]
    return {"repo": repo, "intent": os.path.join(repo, "host_vars", "r2.yml")}


def _script(repo, *args, tmp_path=None):
    env = {k: v for k, v in os.environ.items() if k != "NMAS_DATA_DIR"}
    got = subprocess.run([sys.executable, SCRIPT, repo, *args], capture_output=True,
                         text=True, timeout=120, env=env, cwd=str(tmp_path or repo))
    return got


def _fail_lines(text):
    return [l for l in text.splitlines() if l.startswith("FAIL  ")]


def _head(repo):
    return subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"], capture_output=True,
                          text=True).stdout.strip()


def _edit_intent(lab, change):
    text = open(lab["intent"], encoding="utf-8").read()
    with open(lab["intent"], "w", encoding="utf-8") as fh:
        fh.write(change(text))


def _unrenderable(text):
    """Valid YAML and schema, and a render that fails: the template loops over `vrfs`."""
    doc = yaml.safe_load(text)
    doc["vrfs"] = 7
    return yaml.safe_dump(doc, sort_keys=True, default_flow_style=False, width=10000)


# ---------------------------------------------------------------------------
# The script
# ---------------------------------------------------------------------------

def test_a_good_repository_passes_with_no_secret_and_no_data(lab, tmp_path):
    report = tmp_path / "report.json"
    got = _script(lab["repo"], "--report", str(report), tmp_path=tmp_path)
    assert got.returncode == 0, got.stdout + got.stderr
    assert not _fail_lines(got.stdout)
    assert "Intent-Match: yes (1 of 1)" in got.stdout, got.stdout
    data = json.loads(report.read_text())
    assert data["ok"] is True and data["counts"]["fail"] == 0
    checks = {r["check"] for r in data["results"] if r["status"] == "pass"}
    assert {"yaml", "templates", "render", "intent-match", "secrets"} <= checks, checks
    render = [r for r in data["results"] if r["check"] == "render" and r["status"] == "pass"]
    assert render and "templates/cisco_iosxe/base.j2" in render[0]["message"]


def test_a_schema_violation_fails_naming_the_file_and_line(lab, tmp_path):
    _edit_intent(lab, lambda t: t.replace("\n  description:", "\n  descripton:", 1))
    want = next(n for n, l in enumerate(open(lab["intent"]).read().splitlines(), 1)
                if "descripton:" in l)
    got = _script(lab["repo"], tmp_path=tmp_path)
    assert got.returncode == 1
    fails = _fail_lines(got.stdout)
    assert any(f"yaml         host_vars/r2.yml line {want}" in f and "descripton" in f
               for f in fails), got.stdout


def test_an_intent_that_does_not_render_fails_naming_its_template(lab, tmp_path):
    _edit_intent(lab, _unrenderable)
    got = _script(lab["repo"], tmp_path=tmp_path)
    assert got.returncode == 1, got.stdout
    fails = [f for f in _fail_lines(got.stdout) if " render " in f]
    assert fails and "host_vars/r2.yml" in fails[0] and "does not render through " \
        "templates/cisco_iosxe/base.j2" in fails[0], got.stdout


def test_a_template_that_does_not_parse_fails_naming_its_line(lab, tmp_path):
    path = os.path.join(lab["repo"], "templates", "cisco_iosxe", "base.j2")
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("{% if %}\n")
    lines = open(path, encoding="utf-8").read().count("\n")
    got = _script(lab["repo"], tmp_path=tmp_path)
    assert got.returncode == 1
    assert any(f"templates    templates/cisco_iosxe/base.j2 line {lines}" in f
               for f in _fail_lines(got.stdout)), got.stdout


def test_a_plaintext_secret_fails_and_is_never_printed(lab, tmp_path):
    value = "Plain7Community"
    _edit_intent(lab, lambda t: t.replace(
        "unmodeled:", f"unmodeled:\n- children: []\n  line: snmp-server community {value} RO",
        1))
    got = _script(lab["repo"], "--report", str(tmp_path / "r.json"), tmp_path=tmp_path)
    assert got.returncode == 1
    fails = [f for f in _fail_lines(got.stdout) if " secrets " in f]
    assert fails and "host_vars/r2.yml line" in fails[0] and "snmp_community" in fails[0]
    assert value not in got.stdout + got.stderr
    assert value not in (tmp_path / "r.json").read_text()


def test_a_golden_that_departs_from_intent_is_reported_never_failed(lab, tmp_path):
    golden = os.path.join(lab["repo"], "golden", "r2.cfg")
    with open(golden, "a", encoding="utf-8") as fh:
        fh.write("ip domain lookup source-interface Loopback0\n")
    got = _script(lab["repo"], tmp_path=tmp_path)
    assert got.returncode == 0, got.stdout
    assert "Intent-Match: no: r2" in got.stdout
    assert "NOTE  intent-match" in got.stdout


# ---------------------------------------------------------------------------
# Mercury's commit runs the same check
# ---------------------------------------------------------------------------

def test_mercurys_commit_refuses_with_the_scripts_words(lab, tmp_path):
    from modules.nsot.repo import save_host_vars

    _edit_intent(lab, lambda t: t.replace("\n  description:", "\n  descripton:", 1))
    script_fail = next(f for f in _fail_lines(_script(lab["repo"], tmp_path=tmp_path).stdout))
    before = _head(lab["repo"])
    got = save_host_vars(LIST, ["r2"], actor="t")
    assert got["ok"] is False
    assert "refused by the config check" in got["error"]
    # The same check, file, line and words as the script's FAIL line.
    check, rest = script_fail[len("FAIL  "):].split(None, 1)
    assert f"- {check}: {rest}" in got["error"], (script_fail, got["error"])
    assert _head(lab["repo"]) == before, "nothing was committed"


def test_mercurys_commit_refuses_an_intent_that_does_not_render(lab):
    from modules.nsot.repo import save_host_vars

    _edit_intent(lab, _unrenderable)
    got = save_host_vars(LIST, ["r2"], actor="t")
    assert got["ok"] is False and "- render: host_vars/r2.yml" in got["error"], got


def test_a_capture_is_committed_whatever_intent_says(lab):
    """A golden records what the device has: the check reports it, never refuses it."""
    from modules.nsot.repo import GoldenItem, save_golden

    captured = open(R2, encoding="utf-8").read() + "ip domain lookup source-interface Lo0\n"
    got = save_golden(LIST, [GoldenItem("r2", captured, "203.0.113.12", platform="cisco_iosxe")],
                      source="capture", actor="t", baseline=False)
    assert got["ok"], got


def test_a_fault_the_commit_did_not_make_does_not_refuse_it(lab):
    """Scoped to what the commit touches: another file's fault, on disk and uncommitted, is
    not this commit's."""
    from modules.nsot.repo import save_templates

    with open(os.path.join(lab["repo"], "host_vars", "s9.yml"), "w", encoding="utf-8") as fh:
        fh.write("hostname: s9\n  bad: [indent\n")
    path = os.path.join(lab["repo"], "templates", "cisco_ios", "base.j2")
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("! a comment line\n")
    assert save_templates(LIST, ["cisco_ios/base.j2"])["ok"]


def test_a_template_edit_that_breaks_a_bound_device_is_refused(lab):
    from modules.nsot.repo import save_templates

    path = os.path.join(lab["repo"], "templates", "cisco_iosxe", "base.j2")
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("{{ v.no_such_key.inner }}\n")
    got = save_templates(LIST, ["cisco_iosxe/base.j2"])
    assert got["ok"] is False and "- render: host_vars/r2.yml" in got["error"], got


# ---------------------------------------------------------------------------
# B8 (the operator, 2026-10-13): goldens, top-level keys, password hashes by shape
# ---------------------------------------------------------------------------

def _stitched(lab):
    """r2's golden with a second configuration after the first, as a hand push could make."""
    golden = os.path.join(lab["repo"], "golden", "r2.cfg")
    with open(golden, "a", encoding="utf-8") as fh:
        fh.write("hostname r9\ninterface Loopback9\nend\n")
    return golden


def test_a_golden_holding_two_configurations_fails_by_save_goldens_rule(lab, tmp_path):
    _stitched(lab)
    got = _script(lab["repo"], tmp_path=tmp_path)
    assert got.returncode == 1, got.stdout
    fails = [f for f in _fail_lines(got.stdout) if " golden " in f]
    assert fails and "golden/r2.cfg" in fails[0] and "2 `end` lines" in got.stdout, got.stdout


def test_a_good_golden_passes_and_departing_from_intent_is_still_a_note(lab, tmp_path):
    report = tmp_path / "r.json"
    assert _script(lab["repo"], "--report", str(report), tmp_path=tmp_path).returncode == 0
    golden = [r for r in json.loads(report.read_text())["results"] if r["check"] == "golden"]
    assert [(r["status"], r["file"]) for r in golden] == [("pass", "golden/r2.cfg")], golden


def test_a_commit_of_goldens_alone_is_checked_and_renders_nothing(lab, monkeypatch):
    """Mercury's pre-commit, through the real commit path, on a golden committed alone: the
    golden check refuses it, and no device is rendered to do so."""
    from modules.nsot import repo as R, roundtrip

    _stitched(lab)
    rendered = []
    real = roundtrip.render
    monkeypatch.setattr(roundtrip, "render", lambda *a, **k: rendered.append(1) or real(*a, **k))
    before = _head(lab["repo"])
    with R.repo_lock(lab["repo"]):
        staged = R.stage_exactly(lab["repo"], ["golden/r2.cfg"])
        rc, _sha, err = R.commit(lab["repo"], "a hand edit\n", paths=staged, publish_now=False)
    assert rc != 0 and "- golden: golden/r2.cfg" in err, err
    assert _head(lab["repo"]) == before and rendered == []


def test_a_top_level_key_nothing_reads_fails_and_an_empty_one_passes(lab, tmp_path):
    def add(text, key, value):
        doc = yaml.safe_load(text)
        doc[key] = value
        return yaml.safe_dump(doc, sort_keys=True, default_flow_style=False, width=10000)

    _edit_intent(lab, lambda t: add(t, "ntp_sever", ["192.0.2.123"]))
    want = next(n for n, l in enumerate(open(lab["intent"]).read().splitlines(), 1)
                if l.startswith("ntp_sever:"))
    got = _script(lab["repo"], tmp_path=tmp_path)
    assert got.returncode == 1, got.stdout
    assert any(f"yaml         host_vars/r2.yml line {want}" in f and "'ntp_sever'" in f
               for f in _fail_lines(got.stdout)), got.stdout
    _edit_intent(lab, lambda t: add(add(t, "ntp_sever", []), "spare_settings", {}))
    got = _script(lab["repo"], tmp_path=tmp_path)
    assert got.returncode == 0, got.stdout          # empty: renders nothing either way


def test_the_keys_the_template_names_and_mercurys_own_are_read():
    from modules.nsot import config_check, roundtrip
    reads = config_check.template_reads(roundtrip.TEMPLATE_ROOT, "cisco_iosxe", "base.j2")
    assert {"interfaces", "vrfs", "source_interfaces"} <= reads, sorted(reads)[:20]
    assert set(config_check.MERCURY_KEYS) == {"hostname", "platform", "secret_refs",
                                              "unmodeled", "unmodeled_ack", "profile_exclude",
                                              "bootstrap"}


def test_a_profile_exclusion_is_mercurys_own_key_and_commits(lab):
    """`profile_exclude` renders nothing and is read by the profile (the gate's first run of
    C731 refused it in tests/test_coverage_page.py: the key list had missed it)."""
    from modules.nsot import hostvars
    from modules.nsot.repo import save_host_vars

    r2 = hostvars.read_committed(lab["repo"], "r2")
    r2["profile_exclude"] = [{"section": "snmp", "reason": "polled by the carrier's NMS"}]
    hostvars.write_committed(lab["repo"], r2)
    assert save_host_vars(LIST, ["r2"], actor="t")["ok"]


# ---------------------------------------------------------------------------
# What must not PASS (Lab 7's mutation night on _check_device, 2026-10-14: each of these
# survived, so a bad repository, or a commit, could have passed the check)
# ---------------------------------------------------------------------------

def _git(repo, *args):
    subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True)


def _fails(report, check):
    return [r for r in report["results"] if r["check"] == check and r["status"] == "fail"]


def test_a_template_that_renders_a_byte_no_cli_accepts_fails_the_lint(lab):
    """The intent is printable, so only a template can put an em dash into the render: the lint
    fails, naming the line, against the intent and the template, so a commit touching just the
    template is refused too (the night: the lint's status and its files survived)."""
    from modules.nsot import config_check
    path = os.path.join(lab["repo"], "templates", "cisco_iosxe", "base.j2")
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("! managed — by Mercury\n")
    for report in (config_check.run(lab["repo"], notes=False),
                   config_check.run(lab["repo"], touched=["templates/cisco_iosxe/base.j2"],
                                    notes=False)):
        fails = _fails(report, "lint")
        assert not report["ok"] and len(fails) == 1, report["results"]
        assert fails[0]["device"] == "r2" and fails[0]["file"] == "host_vars/r2.yml"
        assert "templates/cisco_iosxe/base.j2" in fails[0]["files"]
        assert fails[0]["message"].startswith("the render of its intent has line ")
        assert "U+2014" in fails[0]["message"]


def test_a_binding_to_a_template_that_fails_is_refused_as_the_bindings_change(lab):
    """A template committed and bound to nothing, then a device bound to it: the change touches
    only templates/bindings.yml, and the render failure counts against it, naming the template
    the device is bound to (the night: the bindings' attribution, the device's own binding and
    the bound template's name all survived)."""
    from modules.nsot import config_check, templates_repo
    broken = os.path.join(lab["repo"], "templates", "cisco_iosxe", "broken.j2")
    with open(broken, "w", encoding="utf-8") as fh:
        fh.write("{% for v in vrfs.missing.deeper %}{{ v }}{% endfor %}\n")
    _git(lab["repo"], "add", "templates/cisco_iosxe/broken.j2")
    _git(lab["repo"], "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit",
         "-qm", "an unbound template")
    assert config_check.run(lab["repo"], notes=False)["ok"], "unbound: nothing renders it"
    bindings = templates_repo.load_bindings(lab["repo"])
    bindings["overrides"]["r2"] = "cisco_iosxe/broken.j2"
    templates_repo.save_bindings(lab["repo"], bindings)
    report = config_check.run(lab["repo"], touched=["templates/bindings.yml"], notes=False)
    fails = _fails(report, "render")
    assert not report["ok"] and len(fails) == 1, report["results"]
    assert fails[0]["device"] == "r2"
    assert "does not render through templates/cisco_iosxe/broken.j2" in fails[0]["message"]
    assert "templates/bindings.yml" in fails[0]["files"]


def _profile(lab, data):
    """Commit profiles/monitoring.yml with one section for IOS-XE devices of the role `edge`."""
    from modules.nsot import profile
    path = os.path.join(lab["repo"], profile.PROFILE_REL)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        yaml.safe_dump({"version": profile.VERSION, "sections": {"lldp": {
            "platforms": ["cisco_iosxe"], "roles": ["edge"], "data": data}}}, fh)
    _git(lab["repo"], "add", profile.PROFILE_REL)
    _git(lab["repo"], "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit",
         "-qm", "the profile")
    return profile.PROFILE_REL


def test_a_profile_that_breaks_a_render_is_refused_as_the_profiles_change(lab, monkeypatch):
    """The profile is overlaid on each device's intent before it renders (the device's own value
    wins, unless it is empty). A section for this device's platform and role whose data breaks
    the render fails, and counts against a commit touching only the profile; a benign one
    passes. r2's `tracks` is empty, and `_common.j2` loops over it (the night: the profile's
    application, its arguments, and the profile file's attribution all survived)."""
    from modules.nsot import config_check
    entries = config_check._manifest_entries(lab["repo"])
    monkeypatch.setattr(config_check, "_manifest_entries",
                        lambda repo: {n: {**e, "role": "edge"} for n, e in entries.items()})
    rel = _profile(lab, {"tracks": []})
    good = config_check.run(lab["repo"], notes=False)
    assert good["ok"], good["results"]
    _profile(lab, {"tracks": 7})
    for report in (config_check.run(lab["repo"], notes=False),
                   config_check.run(lab["repo"], touched=[rel], notes=False)):
        fails = _fails(report, "render")
        assert not report["ok"] and len(fails) == 1, report["results"]
        assert fails[0]["device"] == "r2" and rel in fails[0]["files"]
    monkeypatch.setattr(config_check, "_manifest_entries",
                        lambda repo: {n: {**e, "role": "core"} for n, e in entries.items()})
    assert config_check.run(lab["repo"], notes=False)["ok"], "another role: not applied"


@pytest.mark.parametrize("only", ["inventory", "intent"])
def test_the_platform_from_either_source_alone_still_renders(lab, monkeypatch, only):
    """A device's dialect comes from the inventory entry, else its intent: with it in only one
    of them the device is still rendered, so its render failure is found, never "not rendered:
    no known platform" (the night: dropping either source survived, since the lab names it in
    both)."""
    from modules.nsot import config_check
    _edit_intent(lab, _unrenderable)
    if only == "inventory":
        _edit_intent(lab, lambda t: "\n".join(l for l in t.splitlines()
                                              if not l.startswith("platform:")) + "\n")
        assert "platform:" not in open(lab["intent"], encoding="utf-8").read()
    else:
        entries = config_check._manifest_entries(lab["repo"])
        assert entries["r2"].get("platform") == "cisco_iosxe", "the lab names it in both"
        monkeypatch.setattr(config_check, "_manifest_entries",
                            lambda repo: {n: {k: v for k, v in e.items() if k != "platform"}
                                          for n, e in entries.items()})
    report = config_check.run(lab["repo"], notes=False)
    fails = _fails(report, "render")
    assert len(fails) == 1 and fails[0]["device"] == "r2", report["results"]


# ---------------------------------------------------------------------------
# What the check reports, record by record (the mutation night's VERDICT survivors, 2026-10-14:
# a note's level, its check, the file or device it blames, which approval it names)
# ---------------------------------------------------------------------------

def _rec(check, status, file, device, message, files=None):
    return {"check": check, "status": status, "file": file, "device": device,
            "message": message, "files": files or [file]}


def _records(results, *checks):
    return [{k: r[k] for k in ("check", "status", "file", "device", "message", "files")}
            for r in results if r["check"] in checks]


def test_the_lab_reports_exactly_these_records(lab):
    """The render's pass names every file its render depends on; the template's approval is a
    note against the template; Intent-Match passes against the golden, saying how many secret
    values it did not compare."""
    from modules.nsot import config_check
    report = config_check.run(lab["repo"], notes=True)
    assert _records(report["results"], "render", "lint", "intent-match") == [
        _rec("render", "pass", "host_vars/r2.yml", "r2",
             "renders through templates/cisco_iosxe/base.j2",
             ["host_vars/r2.yml", "templates/_common.j2", "templates/bindings.yml",
              "templates/cisco_iosxe/base.j2"]),
        _rec("render", "note", "templates/cisco_iosxe/base.j2", "r2",
             "templates/cisco_iosxe/base.j2 is NOT approved: a deploy refuses until it is"),
        _rec("intent-match", "pass", "golden/r2.cfg", "r2",
             "the golden matches its rendered intent (3 secret value(s) not compared)")]


@pytest.mark.parametrize("answer, words", [
    (lambda repo, rel: True, "templates/cisco_iosxe/base.j2 is approved"),
    (lambda repo, rel: (_ for _ in ()).throw(OSError("unreadable")),
     "templates/cisco_iosxe/base.j2 is of unknown approval (unreadable)"),
])
def test_the_templates_approval_is_said_whichever_it_is(lab, monkeypatch, answer, words):
    from modules.nsot import approval, config_check
    asked = []
    monkeypatch.setattr(approval, "is_approved",
                        lambda repo, rel: asked.append((repo, rel)) or answer(repo, rel))
    report = config_check.run(lab["repo"], notes=True)
    notes = [r for r in _records(report["results"], "render") if r["status"] == "note"]
    assert notes == [_rec("render", "note", "templates/cisco_iosxe/base.j2", "r2", words)]
    assert asked == [(os.path.abspath(lab["repo"]), "cisco_iosxe/base.j2")]


def test_lines_a_deploy_asks_a_reason_for_are_noted_five_then_counted(lab, monkeypatch):
    from modules.nsot import authorisation, config_check
    seen = []
    monkeypatch.setattr(authorisation, "flagged",
                        lambda lines: seen.append(len(lines)) or [f"line {n}" for n in range(7)])
    report = config_check.run(lab["repo"], notes=True)
    assert seen and seen[0] > 10, "the render's lines, each"
    assert [r for r in _records(report["results"], "lint")] == [_rec(
        "lint", "note", "host_vars/r2.yml", "r2",
        "7 line(s) a deploy sending them asks an authorisation with a reason for: "
        "line 0; line 1; line 2; line 3; line 4; and 2 more")]
    monkeypatch.setattr(authorisation, "flagged", lambda lines: ["only one"])
    assert _records(config_check.run(lab["repo"], notes=True)["results"], "lint") == [_rec(
        "lint", "note", "host_vars/r2.yml", "r2",
        "1 line(s) a deploy sending them asks an authorisation with a reason for: only one")]


def test_an_intent_that_departs_from_its_golden_shows_both_sides(lab, monkeypatch):
    """The first three of each side, each `section / line`, or the section alone."""
    from modules.nsot import config_check, roundtrip
    _edit_intent(lab, lambda t: t.replace("hostname: r2", "hostname: r2x", 1))
    report = config_check.run(lab["repo"], notes=True)
    assert _records(report["results"], "intent-match") == [_rec(
        "intent-match", "note", "golden/r2.cfg", "r2",
        "differs (-1 +1): a `-` line is in the golden and not in intent, a `+` line in intent "
        "and not in the golden: - (global) / hostname r2; + (global) / hostname r2x")]
    monkeypatch.setattr(roundtrip, "change_rows", lambda golden, rendered: {
        "removed": [("a", "1"), ("b", ""), ("c", "3"), ("d", "4")],
        "added": [("e", ""), ("f", "6"), ("g", "7"), ("h", "8")], "masked": 0})
    report = config_check.run(lab["repo"], notes=True)
    assert _records(report["results"], "intent-match")[0]["message"].endswith(
        "golden: - a / 1; - b; - c / 3; + e; + f / 6; + g / 7")


def _check(lab, device, intent, entry=None):
    from modules.nsot import config_check
    run = config_check._Run(lab["repo"], mask_values=False, notes=True)
    config_check._check_device(run, device, intent, entry or {}, None, "", {})
    return [{k: r[k] for k in ("check", "status", "file", "device", "message", "files")}
            for r in run.results]


def test_a_bootstrap_intent_is_noted_and_never_rendered(lab):
    assert _check(lab, "r9", {"hostname": "r9", "bootstrap": True}) == [_rec(
        "render", "note", "host_vars/r9.yml", "r9",
        "bootstrap intent (onboarding's): nothing to render yet")]


def test_a_device_with_no_known_platform_is_noted_and_never_rendered(lab):
    from modules.nsot import hostvars
    intent = hostvars.read_committed(lab["repo"], "r2")
    intent.pop("platform", None)
    assert _check(lab, "r2", intent, {"platform": "an-unknown-os"}) == [_rec(
        "render", "note", "host_vars/r2.yml", "r2",
        "not rendered: no known platform (neither the inventory, its manifest entry nor its "
        "intent names a config dialect)")]


def test_intent_match_reads_the_golden_its_entry_names_else_the_devices_own(lab):
    from modules.nsot import hostvars
    intent = hostvars.read_committed(lab["repo"], "r2")
    named = _check(lab, "r2", intent, {"platform": "cisco_iosxe", "golden": "golden/other.cfg"})
    assert named[-1] == _rec("intent-match", "note", "golden/other.cfg", "r2",
                             "no golden: nothing captured to compare")
    own = _check(lab, "r2", intent, {"platform": "cisco_iosxe"})
    assert own[-1]["file"] == "golden/r2.cfg" and own[-1]["status"] == "pass"


def test_a_password_hash_anywhere_fails_by_its_shape_and_is_never_printed(lab, tmp_path):
    value = "$9$AAAAAAAAAAAAAA$" + "B" * 43
    path = os.path.join(lab["repo"], "templates", "cisco_iosxe", "base.j2")
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(f"! kept from the old router: {value}\n")
    got = _script(lab["repo"], "--report", str(tmp_path / "r.json"), tmp_path=tmp_path)
    assert got.returncode == 1, got.stdout
    fails = [f for f in _fail_lines(got.stdout) if " secrets " in f]
    assert fails and "templates/cisco_iosxe/base.j2" in fails[0] and "password hash" in fails[0]
    assert value not in got.stdout + got.stderr
    assert value not in (tmp_path / "r.json").read_text()


# ---------------------------------------------------------------------------
# The config repository's workflow
# ---------------------------------------------------------------------------

def _workflow():
    with open(WORKFLOW, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def test_the_workflow_runs_on_the_governed_paths():
    from modules.nsot.config_check import GOVERNED

    wf = _workflow()
    on = wf[True] if True in wf else wf["on"]       # YAML 1.1 reads `on` as true
    want = {f"{g}**" for g in GOVERNED}
    for event in ("push", "pull_request"):
        assert want <= set(on[event]["paths"]), on[event]
    # Branch pushes run, tag pushes do not: GitHub runs a push trigger naming ONLY tags or
    # tags-ignore for no branch push at all (2026-10-13: the rotation run's push started
    # nothing), so both filters are named.
    assert on["push"]["branches"] == ["**"] and on["push"]["tags-ignore"] == ["**"]
    assert "workflow_dispatch" in on, "the check can be run by hand"


def test_the_workflow_checks_out_the_pinned_mercury_and_runs_the_script():
    steps = _workflow()["jobs"]["check"]["steps"]
    checkouts = [s for s in steps if str(s.get("uses", "")).startswith("actions/checkout@")]
    pinned = [s for s in checkouts if "repository" in (s.get("with") or {})]
    assert len(pinned) == 1
    w = pinned[0]["with"]
    assert w["repository"] == "${{ steps.pin.outputs.repository }}"
    assert w["ref"] == "${{ steps.pin.outputs.sha }}"
    assert "token" not in w, "a public repository needs no token"
    pin = next(s for s in steps if s.get("id") == "pin")["run"]
    assert ".nsot/nmas-pin" in pin and "[0-9a-f]{40}" in pin
    runs = "\n".join(s.get("run", "") for s in steps)
    assert "scripts/nmas-config-check config --report nmas-config-check.json" in runs
    assert "--require-hashes" in runs
    upload = next(s for s in steps if str(s.get("uses", "")).startswith("actions/upload-artifact"))
    assert upload["with"]["path"] == "nmas-config-check.json" and upload.get("if") == "always()"


def test_a_scheduled_rotation_commits_through_the_real_commit_path(lab):
    """The host, 2026-10-12 23:56 UTC: the first unattended rotation (s1) was refused at its
    commit ("source 'scheduled-rotation' is not a workflow name") and no test had seen it, since
    every rotation test stubbed `_commit`. Here the rotation's OWN commit runs for real, with
    the words a scheduled run passes (`scheduled_rotation.SOURCE`, the policy's setter as
    actor): save_golden's source rule, repo.commit's config check and the trailers."""
    from modules.nsot import credential_rotation as cr
    from modules.nsot import scheduled_rotation as SR

    captured = open(R2, encoding="utf-8").read()
    before = _head(lab["repo"])
    out = cr._commit(LIST, lab["repo"], "r2", {"ip": "203.0.113.12", "hostname": "r2"},
                     "admin", 15, "N3wR0tatedValue", "$9$planted", captured + "!\n",
                     "setter@example.invalid", record="override", source=SR.SOURCE)
    assert out["ok"], out
    assert _head(lab["repo"]) != before, "the rotation committed nothing"
    msg = subprocess.run(["git", "-C", lab["repo"], "log", "-1", "--format=%B"],
                         capture_output=True, text=True).stdout
    assert msg.startswith("credential: r2 rotated to a device-generated type-9 secret"), msg
    assert f"Source: {SR.SOURCE}" in msg and "Actor: setter@example.invalid" in msg, msg
    files = subprocess.run(["git", "-C", lab["repo"], "show", "--name-only", "--format=",
                            "HEAD"], capture_output=True, text=True).stdout.split()
    assert "golden/r2.cfg" in files, files


@pytest.mark.parametrize("url", ["https://github.com/o/n.git", "https://<token>@github.com/o/n",
                                 "git@github-alias:o/n.git",
                                 # the NMAS host's origin is an ssh alias (measured 2026-10-12)
                                 "github-alias:o/n.git"])
def test_the_host_step_reads_owner_and_name_from_every_origin_form(url):
    text = open(os.path.join(ROOT, "scripts", "host-steps", "c725-config-pipeline.sh"),
                encoding="utf-8").read()
    expr = re.search(r"^REPOSITORY=\$\(git .* \| sed -E '(.*)'\)$", text, re.M).group(1)
    got = subprocess.run(["sed", "-E", expr], input=url + "\n", capture_output=True, text=True)
    assert got.stdout.strip() == "o/n", (url, got.stdout)


def test_the_report_names_each_base_templates_devices_and_each_partials_importers(lab):
    """The config repository's coverage (Lab 7): the BASE templates, each with the devices
    that render it, the headline counting them only; the PARTIALS, each with what imports it.
    The lab's one device is IOS-XE, so the IOS base is flagged NOT RENDERED, and `_common.j2`
    is a partial both bases import, never "not rendered" (C768: it read so on the host).
    Information, never a failure; a scoped check, which renders only the devices a change
    touched, does not claim it."""
    from modules.nsot import config_check
    report = config_check.run(lab["repo"], notes=False)
    tc = report["templates"]
    assert report["ok"]
    assert tc["bases"] == {"templates/cisco_ios/base.j2": [],
                           "templates/cisco_iosxe/base.j2": ["r2"]}
    assert tc["partials"] == {"templates/_common.j2": ["templates/cisco_ios/base.j2",
                                                       "templates/cisco_iosxe/base.j2"]}
    assert (tc["total"], tc["rendered"], tc["unrendered"], tc["unimported"]) == (
        2, ["templates/cisco_iosxe/base.j2"], ["templates/cisco_ios/base.j2"], [])
    human = config_check.human(report).splitlines()
    at = human.index("Base templates rendered by some device: 1 of 2")
    assert human[at + 1:at + 4] == [
        "  cisco_ios/base.j2: NOT RENDERED by any device",
        "  cisco_iosxe/base.j2: 1 device(s): r2",
        "Partial _common.j2: imported by cisco_ios/base.j2, cisco_iosxe/base.j2"]
    scoped = config_check.run(lab["repo"], touched=["host_vars/r2.yml"], notes=False)
    assert scoped["templates"] is None


def test_a_partial_nothing_imports_is_flagged_and_a_fleet_is_counted(tmp_path):
    """A partial is one another template imports, or one named with a leading underscore;
    an underscore file nothing imports is flagged, never miscounted as an unrendered base. A
    base's devices are named up to NAMED_DEVICES and the rest counted."""
    from modules.nsot import config_check
    texts = {"templates/_common.j2": "{% macro m() %}x{% endmacro %}\n",
             "templates/_orphan.j2": "{% macro o() %}y{% endmacro %}\n",
             "templates/macros.j2": "{% macro n() %}z{% endmacro %}\n",
             "templates/ios/base.j2": "{% import '_common.j2' as c %}\n"
                                      "{%- include 'macros.j2' %}\n"}
    for rel, text in texts.items():
        os.makedirs(os.path.dirname(tmp_path / rel), exist_ok=True)
        (tmp_path / rel).write_text(text)
    fleet = [f"sw{n:03d}" for n in range(12)]
    tc = config_check.template_coverage(str(tmp_path), sorted(texts),
                                        {"templates/ios/base.j2": set(fleet)})
    assert tc["partials"] == {"templates/_common.j2": ["templates/ios/base.j2"],
                              "templates/_orphan.j2": [],
                              "templates/macros.j2": ["templates/ios/base.j2"]}
    assert tc["unimported"] == ["templates/_orphan.j2"] and tc["total"] == 1
    lines = config_check.template_lines(tc)
    assert lines[1] == ("  ios/base.j2: 12 device(s): " + ", ".join(fleet[:10])
                        + ", and 2 more")
    assert "Partial _orphan.j2: NOT IMPORTED by any template" in lines


def test_the_job_summary_draws_the_template_section(tmp_path):
    """The config repository's summary step, run as GitHub runs it (its Python, from the
    workflow file) over a real report of the lab: the base templates with their devices and
    the partial with its importers."""
    import yaml
    with open(WORKFLOW, encoding="utf-8") as fh:
        steps = yaml.safe_load(fh)["jobs"]
    run = next(s["run"] for job in steps.values() for s in job["steps"]
               if s.get("name") == "The summary")
    program = run.split("<<'PY'", 1)[1].split("\n", 1)[1].rsplit("\nPY", 1)[0]
    report = {"ok": True, "counts": {"fail": 0}, "scope": "whole repository",
              "devices": ["r2"], "intent_match_trailer": "Intent-Match: yes (1 of 1)",
              "templates": {"total": 2, "rendered": ["templates/cisco_iosxe/base.j2"],
                            "unrendered": ["templates/cisco_ios/base.j2"],
                            "bases": {"templates/cisco_ios/base.j2": [],
                                      "templates/cisco_iosxe/base.j2": ["r2"]},
                            "partials": {"templates/_common.j2": [
                                "templates/cisco_ios/base.j2",
                                "templates/cisco_iosxe/base.j2"]},
                            "unimported": []}}
    (tmp_path / "nmas-config-check.json").write_text(json.dumps(report))
    got = subprocess.run([sys.executable, "-c", textwrap.dedent(program)], cwd=tmp_path,
                         capture_output=True, text=True, timeout=60)
    assert got.returncode == 0, got.stderr
    assert "**Base templates rendered by some device: 1 of 2.**" in got.stdout
    assert "- `cisco_ios/base.j2`: **NOT RENDERED** by any device" in got.stdout
    assert "- `cisco_iosxe/base.j2`: 1 device(s): r2" in got.stdout
    assert ("- partial `_common.j2`: imported by `cisco_ios/base.j2`, `cisco_iosxe/base.j2`"
            in got.stdout)
