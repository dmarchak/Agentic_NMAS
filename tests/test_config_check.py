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


def test_the_report_names_the_templates_no_device_renders(lab):
    """The config repository's coverage (Lab 7): a whole-repository check says which of its
    templates some device's render reached (the template and its imports) and which none did.
    The lab has one IOS-XE device, so the IOS template is named unrendered. Information for a
    person to judge (dead, or bound to a platform no device has), never a failure; a scoped
    check, which renders only the devices a change touched, does not claim it."""
    from modules.nsot import config_check
    report = config_check.run(lab["repo"], notes=False)
    tc = report["templates"]
    assert report["ok"] and tc["total"] == len(tc["rendered"]) + len(tc["unrendered"])
    assert "templates/cisco_iosxe/base.j2" in tc["rendered"]
    assert "templates/cisco_ios/base.j2" in tc["unrendered"]
    line = next(l for l in config_check.human(report).splitlines()
                if l.startswith("Templates rendered by some device:"))
    assert f"{len(tc['rendered'])} of {tc['total']}" in line and "cisco_ios/base.j2" in line
    scoped = config_check.run(lab["repo"], touched=["host_vars/r2.yml"], notes=False)
    assert scoped["templates"] is None
