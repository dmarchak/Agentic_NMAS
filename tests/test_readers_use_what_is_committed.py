"""C104's consumers: every reader of a golden or of committed intent uses what
is COMMITTED, and ignores or refuses by name anything else.

The finding (the operator's framing, 2026-09-27): the drift check, the NetBox
import, onboarding, the freshness gate and the agent read goldens from the
WORKING TREE, and the deploy plan, the baseline's intent comparison, bulk
intent, rotation and the editor read intent the same way. So a file nothing
had committed was already authoritative: a golden could govern the tool with
no commit, no Intent-Match trailer and nobody confirming it, and a hand edit
to host_vars/ was what got deployed. "One write path, committed immediately"
made the COMMIT atomic and said nothing about what the readers take.

Each control here writes an uncommitted change by hand, the state a failed
save or a person on the host leaves, and drives the consumer through its own
code. Structural, not incidental: the readers read git objects, so the next
writer that fails in a new way cannot make its file authoritative.
"""

import json
import logging
import os

import pytest

from modules.nsot import repo as R
from tests.intent_fixture import commit_intent
from tests.test_no_get_returns_a_stored_secret import DEVICE

HEAD_LINE = "hostname r1"
HAND = "snmp-server location HANDEDIT-NOT-COMMITTED\n"


@pytest.fixture
def lab(tmp_path, monkeypatch, intent_matches):
    monkeypatch.setattr("modules.settings_schema.get_setting",
                        lambda key, default=None: {
                            "nsot_git_author_name": "NMAS",
                            "nsot_git_author_email": "nmas@localhost",
                            "nsot_device_tag_retention": 50,
                        }.get(key, default))
    monkeypatch.setattr("modules.config.LISTS_DIR", str(tmp_path))
    list_dir = tmp_path / "lab"
    list_dir.mkdir()
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(list_dir))
    monkeypatch.setattr("modules.nsot.hooks.run_post_commit", lambda ctx: None)
    repo = str(list_dir / "config_repo")
    ip = DEVICE["ip"]
    out = R.save_golden("lab", [R.GoldenItem("r1", f"{HEAD_LINE}\n!\nend\n", ip)],
                        allow_new=True)
    assert out["ok"], out
    monkeypatch.setattr("modules.ai_assistant._nsot_repo_dir", lambda: repo)
    monkeypatch.setattr("modules.ai_assistant._identity_for_ip", lambda ip: "")
    monkeypatch.setattr("modules.ai_assistant._migrate_golden_configs", lambda: None)
    monkeypatch.setattr("modules.ai_assistant._legacy_header_scan", lambda ip: None)
    R._WORKTREE_WARNED.clear()
    return {"repo": repo, "ip": ip, "golden": os.path.join(repo, "golden", "r1.cfg")}


def _hand_edit(path, text=HAND):
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(text)


def _drift(monkeypatch, ip, running):
    from modules import drift_check

    dev = {"hostname": "r1", "ip": ip, "username": "u", "password": "p",
           "device_type": "cisco_ios"}
    monkeypatch.setattr("modules.device.get_current_device_list", lambda: ("lab", "lab.csv"))
    monkeypatch.setattr("modules.device.load_saved_devices", lambda path: [dict(dev)])
    monkeypatch.setattr("modules.connection.get_persistent_connection",
                        lambda d, pool, lock: d["ip"])
    monkeypatch.setattr("modules.commands.run_device_command", lambda conn, cmd: running)
    monkeypatch.setattr("modules.approval_queue.add_approval", lambda **kw: {"ok": True})
    return drift_check.run_drift_check("test")


def _agent_read(ip):
    from modules import ai_assistant as ai
    from tests.test_no_agent_tool_leaks_a_stored_secret import drive

    tool = next(t for t in ai.TOOLS if t.get("name") == "read_golden_config")
    return drive([tool])["read_golden_config"]


class TestAnUncommittedEditIsIgnored:
    """The committed golden is what every consumer reads; the edit is named."""

    def test_the_resolver_reads_head_and_names_the_path(self, lab, caplog):
        from modules.ai_assistant import _golden_record

        _hand_edit(lab["golden"])
        with caplog.at_level(logging.WARNING):
            rec = _golden_record(lab["ip"])
        assert rec["refused"] == "" and HEAD_LINE in rec["text"]
        assert "HANDEDIT" not in rec["text"]
        assert "golden/r1.cfg differs from its commit" in caplog.text

    def test_drift_compares_the_committed_golden(self, lab, monkeypatch):
        """Running equals the COMMITTED golden, so drift is clean: had it read
        the edited file, it would report drift nobody made on the device."""
        _hand_edit(lab["golden"])
        # From git directly, never through the reader under test: computed
        # with committed_golden(), both sides moved together under the
        # control and drift agreed with itself (the first control passed).
        head = R.git_raw(lab["repo"], "show", "HEAD:golden/r1.cfg")[1]
        r = _drift(monkeypatch, lab["ip"], head)
        assert r["clean"] == 1 and r["drifted"] == 0, r["summary"]

    def test_the_netbox_import_reads_the_committed_golden(self, lab):
        from modules.netbox_client import _scan_device_from_golden

        _hand_edit(lab["golden"])
        out = _scan_device_from_golden({"ip": lab["ip"], "hostname": "r1"})
        assert "error" not in out, out
        assert "HANDEDIT" not in json.dumps(out, default=str)

    def test_the_agent_tool_returns_the_committed_golden(self, lab):
        _hand_edit(lab["golden"])
        text = _agent_read(lab["ip"])
        assert HEAD_LINE in text and "HANDEDIT" not in text, text

    def test_the_freshness_gate_reads_the_committed_golden(self, lab):
        from modules.nsot import freshness

        _hand_edit(lab["golden"])
        entry = next(e for e in R.list_goldens("lab") if e["hostname"] == "r1")
        text, _at = freshness._read_golden(entry)
        assert HEAD_LINE in text and "HANDEDIT" not in text


class TestAGoldenNothingCommittedIsRefusedByName:
    """A file on disk that no save committed is not a golden."""

    @pytest.fixture
    def never(self, lab):
        from modules.nsot import manifest as M

        with open(os.path.join(lab["repo"], "golden", "r9.cfg"), "w") as fh:
            fh.write("hostname r9\n")
        M.upsert_device(lab["repo"], "uid:r9", "r9", "192.0.2.9", golden="golden/r9.cfg")
        return "192.0.2.9"

    def test_the_resolver_refuses_naming_the_path(self, lab, never):
        from modules.ai_assistant import _golden_record

        rec = _golden_record(never)
        assert rec["text"] is None
        assert "golden/r9.cfg" in rec["refused"] and "never been committed" in rec["refused"]

    def test_drift_names_the_refusal_not_no_golden(self, lab, never, monkeypatch):
        from modules import drift_check

        dev = {"hostname": "r9", "ip": never, "username": "u", "password": "p",
               "device_type": "cisco_ios"}
        monkeypatch.setattr("modules.device.get_current_device_list", lambda: ("lab", "lab.csv"))
        monkeypatch.setattr("modules.device.load_saved_devices", lambda path: [dict(dev)])
        r = drift_check.run_drift_check("test")
        reason = r["skipped"][0]["reason"]
        assert reason.startswith("golden refused:") and "golden/r9.cfg" in reason

    def test_the_netbox_import_names_it(self, lab, never):
        from modules.netbox_client import _scan_device_from_golden

        out = _scan_device_from_golden({"ip": never, "hostname": "r9"})
        assert "golden/r9.cfg" in out["error"]

    def test_the_agent_tool_says_refused(self, lab, never, monkeypatch):
        monkeypatch.setitem(DEVICE, "ip", never)
        text = _agent_read(never)
        assert "refused" in text and "golden/r9.cfg" in text, text

    def test_it_is_not_enumerated(self, lab, never):
        assert {e["hostname"] for e in R.list_goldens("lab")} == {"r1"}


class TestAGoldenCommittedOutsideTheSavePathIsRefused:
    def test_a_hand_commit_is_refused_naming_path_and_commit(self, lab):
        from modules.ai_assistant import _golden_record

        _hand_edit(lab["golden"])
        rc, _o, err = R.git(lab["repo"], "commit", "-q", "-am", "hand edit on the host")
        assert rc == 0, err
        sha = R.git(lab["repo"], "rev-parse", "HEAD")[1].strip()
        rec = _golden_record(lab["ip"])
        assert rec["text"] is None
        assert "golden/r1.cfg" in rec["refused"] and sha[:8] in rec["refused"]
        assert "no Source: trailer" in rec["refused"]

    def test_the_control_a_save_path_commit_is_used(self, lab):
        from modules.ai_assistant import _golden_record

        assert _golden_record(lab["ip"])["source"], "the fixture's own save carries Source:"


class TestCommittedIntentIsWhatIsCommitted:
    DOC = {"hostname": "r1", "logging": {"settings": ["trap notifications"]}}

    @pytest.fixture
    def intent(self, lab):
        from modules.nsot import hostvars

        hostvars.write_committed(lab["repo"], dict(self.DOC))
        commit_intent(lab["repo"])
        hostvars._INTENT_WORKTREE_WARNED.clear()
        path = hostvars.committed_path(lab["repo"], "r1")
        _hand_edit(path, "  - HANDEDIT-intent\n")
        return path

    def test_read_committed_ignores_the_edit_and_names_it(self, lab, intent, caplog):
        from modules.nsot import hostvars

        with caplog.at_level(logging.WARNING):
            doc = hostvars.read_committed(lab["repo"], "r1")
        assert "HANDEDIT" not in json.dumps(doc)
        assert doc["logging"]["settings"] == ["trap notifications"]
        assert "host_vars/r1.yml differs from its commit" in caplog.text

    def test_the_editor_opens_what_is_committed(self, lab, intent, monkeypatch):
        import app as A

        monkeypatch.setattr("routes.templatize._repo_for", lambda name: lab["repo"])
        monkeypatch.setattr("routes.templatize._active_list", lambda *a, **k: "lab")
        body = A.app.test_client().get("/templatize/committed/r1").get_json()
        assert body["ok"] and "HANDEDIT" not in body["yaml"], body


def _trees():
    """{relative path: AST} over the program AND its scripts. The first version
    scanned modules/ and routes/ only, and missed app.py's Auto-Create, the
    deploy plan's capture (routes/deploy.py was in scope, but the rule was
    "one caller of the resolver", which the deploy capture never called),
    rotation, the vty count and three scripts: every one resolved a golden's
    path and opened it itself."""
    import ast

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = {}
    paths = [os.path.join(d, f) for base in ("modules", "routes")
             for d, _s, fs in os.walk(os.path.join(root, base)) for f in fs if f.endswith(".py")]
    paths.append(os.path.join(root, "app.py"))
    scripts = os.path.join(root, "scripts")
    paths += [os.path.join(scripts, f) for f in os.listdir(scripts)
              if os.path.isfile(os.path.join(scripts, f))]
    for full in paths:
        try:
            out[os.path.relpath(full, root)] = ast.parse(open(full, encoding="utf-8").read())
        except (SyntaxError, UnicodeDecodeError, ValueError):
            continue                          # a shell script, not Python
    return out


def _reads(call) -> bool:
    """Is this `open(...)` a READ? No mode, or a mode with no w/a/x/+. The
    rule is about reading the working tree; a writer has to open files, and
    matching the NAME `open` flagged bulk intent's put-back, which WRITES the
    committed text back (the weaker-match class, caught in this scan)."""
    import ast

    mode = call.args[1] if len(call.args) > 1 else next(
        (k.value for k in call.keywords if k.arg == "mode"), None)
    if mode is None:
        return True
    if isinstance(mode, ast.Constant) and isinstance(mode.value, str):
        return not set(mode.value) & set("wax+")
    return True                                   # unknown mode: count it


def _functions_calling(names):
    import ast

    found = {}
    for rel, tree in _trees().items():
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            calls = {getattr(n.func, "attr", getattr(n.func, "id", ""))
                     for n in ast.walk(fn) if isinstance(n, ast.Call)
                     and not (getattr(n.func, "id", "") == "open" and not _reads(n))}
            if calls & set(names):
                found[(rel, fn.name)] = calls
    return found


class TestThePopulation:
    """The RULE, over readers not yet written, which the controls above
    cannot reach: a function that resolves a golden's path or the intent
    file's path never opens a file itself; it reads through the committed
    readers. Each exception is named with its reason."""

    GOLDEN_OPENERS = {
        ("modules/ai_assistant.py", "_golden_record"):
            "opens only the LEGACY store's file (golden_configs/, outside git, "
            "never written since the migration); repo goldens go through git",
        ("scripts/nsot_verify_migration.py", "verify"):
            "verifies the migration: reads the migration COMMIT through git and "
            "compares it with the legacy file",
    }
    INTENT_OPENERS = {
        ("scripts/nsot_fix_description_ifnames.py", "main"):
            "a one-off repair run on the host by a person; it rewrites intent "
            "and commits it",
    }

    def test_the_scan_finds_the_resolvers(self):
        found = _functions_calling({"golden_path_for", "_find_golden_config_file"})
        # Measured 5 after the fix: the readers now call committed_golden_for,
        # which is the one place that resolves a path to READ it.
        assert len(found) >= 4, sorted(found)
        assert ("modules/nsot/repo.py", "committed_golden_for") in found
        assert ("modules/ai_assistant.py", "_golden_record") in found

    def test_no_function_resolving_a_golden_opens_a_file(self):
        found = _functions_calling({"golden_path_for", "_find_golden_config_file"})
        opening = sorted(k for k, calls in found.items() if "open" in calls)
        assert set(opening) <= set(self.GOLDEN_OPENERS), (
            "resolves a golden's path and opens it itself; read it through "
            f"repo.committed_golden_for(): {sorted(set(opening) - set(self.GOLDEN_OPENERS))}")

    def test_no_golden_exception_is_a_ghost(self):
        found = _functions_calling({"golden_path_for", "_find_golden_config_file"})
        opening = {k for k, calls in found.items() if "open" in calls}
        assert set(self.GOLDEN_OPENERS) <= opening, set(self.GOLDEN_OPENERS) - opening

    def test_no_function_resolving_the_intent_path_opens_it(self):
        found = _functions_calling({"committed_path"})
        opening = sorted(k for k, calls in found.items()
                         if "open" in calls and k[0] != "modules/nsot/hostvars.py")
        assert set(opening) <= set(self.INTENT_OPENERS), sorted(
            set(opening) - set(self.INTENT_OPENERS))
        assert set(self.INTENT_OPENERS) <= set(opening), "a ghost exception"
        assert len(found) >= 5, sorted(found)


class TestTheDeployPlanNamesARefusal:
    def test_a_hand_committed_golden_blocks_the_plan_by_name(self, lab, monkeypatch):
        """The deploy plan diffs against the capture and binds its hash to it,
        and it read the working file until the second pass of C104's fix. A
        refused golden is said as refused, never as 'no golden config'."""
        import routes.deploy as D

        _hand_edit(lab["golden"])
        assert R.git(lab["repo"], "commit", "-q", "-am", "hand edit")[0] == 0
        monkeypatch.setattr(D, "_repo_for", lambda name: lab["repo"])
        artifact, reason = D._artifact_for("lab", "r1")
        assert artifact is None
        assert reason.startswith("golden refused:") and "golden/r1.cfg" in reason, reason

    def test_the_control_the_committed_golden_is_the_capture(self, lab, monkeypatch):
        import routes.deploy as D

        _hand_edit(lab["golden"])                       # uncommitted: ignored
        head = R.git_raw(lab["repo"], "show", "HEAD:golden/r1.cfg")[1]
        assert D._captured_config(lab["repo"], "r1") == head



def test_the_rule_counts_a_read_and_not_a_write():
    """Control for the refinement: a read-mode open still counts."""
    import ast

    read = ast.parse("open(p)").body[0].value
    read_r = ast.parse("open(p, 'r', encoding='utf-8')").body[0].value
    write = ast.parse("open(p, 'w', encoding='utf-8')").body[0].value
    assert _reads(read) and _reads(read_r) and not _reads(write)
