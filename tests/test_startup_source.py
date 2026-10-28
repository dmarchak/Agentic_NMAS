"""Plan item 4 (the operator's decision, 2026-10-01): each lab startup file is
built from the list's NEWEST EARNED baseline, every credential family from the
device's CURRENT golden (C309), and the sync writes every device it can.

On r2's REAL config, committed into a real repository (test_golden_repo's
lab): a baseline earned by a Save All, then a rotation committed after it,
then the build. Every difference is a minimal edit of the real config."""

import importlib.machinery
import importlib.util
import os
import stat

import pytest

from modules.nsot import repo as R
from modules.nsot import startup_source as SS
from tests.test_golden_repo import _seed, lab  # noqa: F401  (the fixture)

R2 = open("tests/fixtures/configs/fleet/r2.cfg", encoding="utf-8").read()
OLD_ACCOUNT = "username admin privilege 15 password 0 admin"
NEW_ACCOUNT = "username admin privilege 15 secret 9 $9$Zq7rotatedhash$abcdefghijklmnopqrstuvwxyz0123"
ROTATED = R2.replace(OLD_ACCOUNT, NEW_ACCOUNT)


def _intent(monkeypatch, off=()):
    """Each save's judgement against committed intent (C89): a capture of a device in *off*
    departs (+1), every other matches. The `lab` fixture's `intent_matches` makes every capture
    match; a test about WHICH golden is recorded at intent needs both answers."""
    from modules.nsot import intent_match as im

    def judged(repo, list_name, hostname, config_text, platform=""):
        if hostname in off:
            return {"state": "differs", "adds": 1, "removes": 0, "reordered": 0,
                    "lines": ["+ ip route 192.0.2.0 255.255.255.0 Null0"], "why": ""}
        return {"state": "match", "adds": 0, "removes": 0, "reordered": 0, "lines": [],
                "why": ""}

    monkeypatch.setattr(im, "intent_match", judged)


def test_the_floor_r2_holds_the_account_and_communities_the_families_name():
    assert OLD_ACCOUNT in R2 and NEW_ACCOUNT in ROTATED
    assert any(l.startswith("snmp-server community ") for l in R2.splitlines())


class TestCompose:
    def test_a_rotation_since_the_baseline_is_never_undone(self):
        """C309's test: the baseline holds the retired password, the file the new one."""
        got = SS.compose(R2, ROTATED)
        assert NEW_ACCOUNT in got["text"] and OLD_ACCOUNT not in got["text"]
        assert "accounts" in got["replaced"]

    def test_everything_else_is_the_baseline_s(self):
        moved = ROTATED.replace("hostname r2\n", "hostname r2\nip domain lookup source-interface "
                                                 "Loopback0\n")
        got = SS.compose(R2, moved)
        assert "ip domain lookup source-interface Loopback0" not in got["text"]
        assert got["text"] == R2.replace(OLD_ACCOUNT, NEW_ACCOUNT)

    def test_a_rotated_community_is_the_current_one(self):
        old = next(l for l in R2.splitlines() if l.startswith("snmp-server community "))
        new = old.replace(old.split()[2], "Zq7NewCommunity")
        got = SS.compose(R2, R2.replace(old, new))
        assert new in got["text"] and old not in got["text"]

    def test_an_account_added_since_joins_the_block_and_one_removed_leaves_it(self):
        added = ROTATED.replace(NEW_ACCOUNT, NEW_ACCOUNT + "\nusername nmas privilege 15 secret 9 "
                                                          "$9$Zq7nmas$hashvalue")
        assert "username nmas privilege 15" in SS.compose(R2, added)["text"]
        gone = "\n".join(l for l in ROTATED.splitlines() if not l.startswith("username "))
        assert "username " not in SS.compose(R2, gone + "\n")["text"]

    def test_a_family_the_baseline_lacks_is_placed_before_end(self):
        bare = "\n".join(l for l in R2.splitlines() if not l.startswith("snmp-server community "))
        got = SS.compose(bare + "\n", R2)["text"].splitlines()
        assert got[-1] == "end" and got[-2].startswith("snmp-server community ")

    def test_a_secret_inside_a_stanza_that_differs_is_named_and_left_as_the_baseline_s(self):
        base = R2.replace("line vty 2 4\n", "line vty 2 4\n password 7 0822455D0A16\n")
        now = R2.replace("line vty 2 4\n", "line vty 2 4\n password 7 1511021F0725\n")
        got = SS.compose(base, now)
        assert got["nested"] and "0822455D0A16" not in str(got["nested"])
        assert "password 7 0822455D0A16" in got["text"]


def _tag(repo, commit, name):
    assert R.git(repo, "tag", "-a", name, commit, "-m", "x")[0] == 0


class TestTheNewestEarnedBaseline:
    def test_a_save_all_earns_one(self, lab):
        out = _seed("Lab", [R.GoldenItem("r2", R2, "203.0.113.12", platform="cisco_ios")], source="save_all")
        tag = next(t for t in out["tags"] if t.startswith("baseline/"))
        assert SS.newest_earned(lab)["tag"] == tag

    def test_withdrawn_and_unrecorded_are_skipped(self, lab, monkeypatch):
        first = _seed("Lab", [R.GoldenItem("r2", R2, "203.0.113.12", platform="cisco_ios")], source="save_all")
        older = next(t for t in first["tags"] if t.startswith("baseline/"))
        second = _seed("Lab", [R.GoldenItem("r2", ROTATED, "203.0.113.12", platform="cisco_ios")], source="save_all")
        newer = next(t for t in second["tags"] if t.startswith("baseline/"))
        assert SS.newest_earned(lab)["tag"] == newer
        sha = R.git(lab, "rev-parse", f"{newer}^{{commit}}")[1].strip()
        monkeypatch.setattr("modules.nsot.record_exceptions.withdrawn_baseline",
                            lambda s: {"reason": "x"} if s == sha else None)
        assert SS.newest_earned(lab)["tag"] == older
        # A tag on a commit that recorded nothing (taken before 7.2) earns nothing.
        manual = _seed("Lab", [R.GoldenItem("r2", ROTATED + "!\n", "203.0.113.12", platform="cisco_ios")],
                       source="manual")
        assert "Baseline:" not in R.git(lab, "log", "-1", "--format=%B", manual["commit"])[1]
        _tag(lab, manual["commit"], "baseline/29991231T000000Z")
        assert [b["decision"] for b in R.list_baselines(lab)][0] == "unrecorded"
        assert SS.newest_earned(lab)["tag"] == older


class TestTheBuild:
    def test_rotate_then_build_carries_the_new_credential(self, lab):
        _seed("Lab", [R.GoldenItem("r2", R2, "203.0.113.12", platform="cisco_ios")], source="save_all")
        assert R.save_golden("Lab", [R.GoldenItem("r2", ROTATED, "203.0.113.12", platform="cisco_ios")],
                             source="rotation", actor="t", allow_new=False)["ok"]
        got = SS.build("Lab", hosts=["r2"])
        assert got["ok"] and got["baseline"]["tag"].startswith("baseline/")
        text = got["devices"]["r2"]["text"]
        assert NEW_ACCOUNT in text and OLD_ACCOUNT not in text

    def test_a_device_the_baseline_does_not_hold_is_refused_alone(self, lab, monkeypatch):
        """C1454: r7, onboarded after the baseline with a capture that departs from its intent,
        has no golden recorded at intent and none in the baseline: it is refused, named, and
        r2 is still built."""
        out = _seed("Lab", [R.GoldenItem("r2", R2, "203.0.113.12", platform="cisco_ios")], source="save_all")
        tag = next(t for t in out["tags"] if t.startswith("baseline/"))
        _intent(monkeypatch, off={"r7"})
        _seed("Lab", [R.GoldenItem("r7", R2.replace("hostname r2", "hostname r7"),
                                   "203.0.113.17", platform="cisco_ios")])
        got = SS.build("Lab", hosts=["r2", "r7"])
        assert got["devices"]["r2"]["state"] == "ok"
        assert got["devices"]["r7"] == {"state": "refused", "why": (
            f"no golden of r7 is recorded at its committed intent, and {tag} holds no golden "
            "of it since its current golden was created (onboarded or renamed since): bring it "
            "to its intent and Save All to build its file")}

    def test_a_rotation_after_a_baseline_starts_the_sync_and_never_boots_the_old_credential(
            self, lab, tmp_path, monkeypatch):
        """C663 (the operator, 2026-10-11: "the lab's sync listens to both, so a lab redeploy
        after a rotation never boots with the old credential (test that sequence)"). A Save All
        earns a baseline; a rotation commits r2's new account and earns NONE, so only the
        golden-committed event can start the sync (lab/clab-sync/clab-sync.path watches it);
        the build the sync then runs carries the new account, never the old."""
        import json

        from modules.nsot import baseline_event as BE
        monkeypatch.setattr("modules.config.DATA_DIR", str(tmp_path / "data"))
        _seed("Lab", [R.GoldenItem("r2", R2, "203.0.113.12", platform="cisco_ios")],
              source="save_all")
        rotated = R.save_golden("Lab", [R.GoldenItem("r2", ROTATED, "203.0.113.12",
                                                     platform="cisco_ios")],
                                source="rotation", actor="t", allow_new=False)
        assert rotated["ok"] and not [t for t in rotated.get("tags") or []
                                      if t.startswith("baseline/")]
        # The hooks the post-commit runner calls, on the rotation's commit.
        ctx = {"list_name": "Lab", "repo": lab, "sha": rotated["commit"],
               "tags": rotated.get("tags") or []}
        assert BE.hook(ctx) == {"ok": True, "message": "no baseline earned"}
        assert BE.golden_hook(ctx)["ok"]
        with open(BE.path("Lab", BE.GOLDEN_EVENTS), encoding="utf-8") as fh:
            event = json.load(fh)
        assert event["devices"] == ["r2"] and event["commit"] == rotated["commit"]
        text = SS.build("Lab", hosts=["r2"])["devices"]["r2"]["text"]
        assert NEW_ACCOUNT in text and OLD_ACCOUNT not in text

    def test_no_earned_baseline_builds_nothing_and_says_why(self, lab):
        _seed("Lab", [R.GoldenItem("r2", R2, "203.0.113.12", platform="cisco_ios")])
        got = SS.build("Lab", hosts=["r2"])
        assert got["ok"] is False and "has no earned baseline" in got["error"]


def _cli():
    loader = importlib.machinery.SourceFileLoader("nmas_startup_source",
                                                  "scripts/nmas-startup-source")
    spec = importlib.util.spec_from_loader("nmas_startup_source", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class TestTheHelperTheSyncCalls:
    def test_it_writes_each_file_owner_only_and_a_row_per_device(self, lab, tmp_path,
                                                                 monkeypatch):
        out = _seed("Lab", [R.GoldenItem("r2", R2, "203.0.113.12", platform="cisco_ios")], source="save_all")
        tag = next(t for t in out["tags"] if t.startswith("baseline/"))
        _intent(monkeypatch, off={"r7"})
        _seed("Lab", [R.GoldenItem("r7", R2.replace("hostname r2", "hostname r7"),
                                   "203.0.113.17", platform="cisco_ios")])
        monkeypatch.setattr("modules.device.load_saved_devices",
                            lambda path: [{"hostname": "r2"}, {"hostname": "r7"}])
        dest = tmp_path / "src"
        assert _cli().main(["--out", str(dest), "--list", "Lab"]) == 0
        assert stat.S_IMODE(os.stat(dest / "r2.cfg").st_mode) == 0o600
        assert not (dest / "r7.cfg").exists()
        rows = (dest / "sources.tsv").read_text().splitlines()
        assert rows[0].startswith(f"# baseline\t{tag}\t")
        assert rows[1] == (f"r2\tok\tsource {out['commit'][:10]} (recorded at its committed "
                           f"intent by Save All, which earned {tag}); credentials from its "
                           "current golden: SNMP communities, accounts")
        assert rows[2].startswith("r7\trefused\tno golden of r7 is recorded at its committed "
                                  f"intent, and {tag} holds no golden of it")

    def test_no_baseline_is_exit_2_writing_nothing(self, lab, tmp_path, capsys):
        _seed("Lab", [R.GoldenItem("r2", R2, "203.0.113.12", platform="cisco_ios")])
        dest = tmp_path / "src"
        assert _cli().main(["--out", str(dest), "--list", "Lab"]) == 2
        assert not dest.exists() and "has no earned baseline" in capsys.readouterr().err


class TestTheMappingCheckCountsANotBuiltDevice:
    ROWS = [("r1", "labs/lab/configs", "default", "user@clab", "cisco_iosxe", "r1"),
            ("r7", "labs/lab/configs", "default", "user@clab", "cisco_iosxe", "r7")]

    def _helper(self):
        loader = importlib.machinery.SourceFileLoader("nmas_clab_targets",
                                                      "lab/clab-sync/clab-targets")
        spec = importlib.util.spec_from_loader("nmas_clab_targets", loader)
        mod = importlib.util.module_from_spec(spec)
        loader.exec_module(mod)
        return mod

    def test_a_device_named_not_built_does_not_block_the_others(self, tmp_path, capsys):
        h = self._helper()
        (tmp_path / "r1.cfg").write_text("x")
        assert h._reconcile(str(tmp_path), self.ROWS) == h.EXIT_MISSING_OUTPUT
        assert h._reconcile(str(tmp_path), self.ROWS, not_built={"r7"}) == h.EXIT_OK
        assert "not built: 1 — r7" in capsys.readouterr().out


#: r2's real config with Mercury's heartbeat applet added (r2's capture predates it): the one
#: edit, so every line the pre-flight looks for is in the file. The file's configuration is the
#: BASELINE's, so the baseline carries the applet too.
APPLET = "event manager applet NMAS-HEARTBEAT\n event timer watchdog time 60\n action 1.0 syslog msg \"NMAS heartbeat\"\n"
R2_APPLET = R2.replace("\nend", "\n" + APPLET + "end")
WITH_APPLET = ROTATED.replace("\nend", "\n" + APPLET + "end")


class TestThePreflightCheck:
    """The redeploy's pre-flight (the operator, 2026-10-19): per device, facts about the built
    file, never a value; any failing fact fails the device."""

    def _ready(self, lab, monkeypatch, rotated_at=None, drift=None, rotation_at_intent=True):
        """A Save All earns the baseline, then a rotation commits r2's new account: recorded
        at its intent, or (*rotation_at_intent* False) not, so the baseline stays the
        source and the rotation is only a commit after it."""
        _seed("Lab", [R.GoldenItem("r2", R2_APPLET, "203.0.113.12", platform="cisco_ios")],
              source="save_all")
        if not rotation_at_intent:
            _intent(monkeypatch, off={"r2"})
        assert R.save_golden("Lab", [R.GoldenItem("r2", WITH_APPLET, "203.0.113.12",
                                                  platform="cisco_ios")],
                             source="rotation", actor="t", allow_new=False)["ok"]
        _intent(monkeypatch)
        rot = {} if rotated_at is None else {"r2": (rotated_at, "2026-10-19T12:00:00Z")}
        monkeypatch.setattr("modules.nsot.scheduled_rotation.last_rotations", lambda: rot)
        state = {"last_check_ts": 1760000000,
                 "last_result": {"checked": 1, "errors": [], "skipped": []}}
        monkeypatch.setattr("modules.drift_check._load_state",
                            lambda list_name="": state if drift is None else drift)

    def test_a_file_built_after_a_rotation_passes_every_fact(self, lab, monkeypatch):
        self._ready(lab, monkeypatch, rotated_at=1)
        got = SS.check("Lab", hosts=["r2"])
        r = got["devices"]["r2"]
        assert got["ok"] and r["built"] and r["credentials_current"] is True
        assert r["families"]["accounts"] == {"equal": True, "lines": 1}
        assert r["placeholders"] == 0 and r["golden_after_rotation"] is True
        assert r["read_by_drift"] is True and r["lacks"] == [] and r["drifted"] is False
        # C1454 (1): the rotation's capture is recorded at r2's intent, so it is the source:
        # no golden commit after it.
        latest = R.git(lab, "log", "-1", "--format=%H", "HEAD", "--", "golden/r2.cfg")[1].strip()
        assert r["source_commit"] == latest[:10] and latest.startswith(r["latest_golden"])
        assert r["source_how"] == "recorded at its committed intent by a rotation"
        assert r["commits_since"] == 0 and r["config_current"] is True

    def test_a_credential_line_that_is_not_the_current_one_fails_its_family(self, lab, monkeypatch):
        self._ready(lab, monkeypatch)
        built = SS.build("Lab", hosts=["r2"])
        built["devices"]["r2"]["text"] = built["devices"]["r2"]["text"].replace(NEW_ACCOUNT, OLD_ACCOUNT)
        r = SS.check("Lab", hosts=["r2"], built=built)["devices"]["r2"]
        assert r["credentials_current"] is False
        assert r["families"]["accounts"]["equal"] is False
        assert r["families"]["SNMP communities"]["equal"] is True

    def test_a_masked_placeholder_is_counted(self, lab, monkeypatch):
        self._ready(lab, monkeypatch)
        built = SS.build("Lab", hosts=["r2"])
        built["devices"]["r2"]["text"] = built["devices"]["r2"]["text"].replace(
            "snmp-server community public RO", "snmp-server community <redacted:community> RO")
        r = SS.check("Lab", hosts=["r2"], built=built)["devices"]["r2"]
        assert r["placeholders"] == 1 and r["credentials_current"] is False

    def test_a_banners_row_of_asterisks_is_not_a_placeholder(self, lab, monkeypatch):
        """The first run on the host (2026-10-19) failed every switch on its banners' borders:
        s1's real capture holds four such rows, and none is Mercury's mask."""
        self._ready(lab, monkeypatch)
        s1 = open("tests/fixtures/configs/fleet/s1.cfg", encoding="utf-8").read()
        assert sum(1 for l in s1.splitlines() if l.startswith("******")) == 4
        built = SS.build("Lab", hosts=["r2"])
        built["devices"]["r2"]["text"] = s1
        assert SS.check("Lab", hosts=["r2"], built=built)["devices"]["r2"]["placeholders"] == 0

    def test_a_file_without_the_heartbeat_applet_lacks_it(self, lab, monkeypatch):
        self._ready(lab, monkeypatch)
        built = SS.build("Lab", hosts=["r2"])
        built["devices"]["r2"]["text"] = built["devices"]["r2"]["text"].replace(APPLET, "")
        r = SS.check("Lab", hosts=["r2"], built=built)["devices"]["r2"]
        assert r["lacks"] == ["heartbeat applet"]

    def test_a_golden_older_than_the_last_rotation_fails(self, lab, monkeypatch):
        self._ready(lab, monkeypatch, rotated_at=4102444800)       # 2100: after every commit
        r = SS.check("Lab", hosts=["r2"])["devices"]["r2"]
        assert r["golden_after_rotation"] is False and r["rotated_at"] == "2026-10-19T12:00:00Z"

    def test_the_rotation_s_own_commit_passes_though_its_record_is_a_second_later(
            self, lab, monkeypatch):
        """C1472 (B3 of the one-file redeploy, 2026-10-21): s4's golden IS its rotation's commit
        (ed5d3ca, 01:13:19) and the rotation's record says 01:13:20, so a comparison of times
        failed it. Compared by identity, the record's commit stage naming that commit, it
        passes; a record dated after every commit, as the time check reads it, fails it."""
        self._ready(lab, monkeypatch, rotated_at=4102444800)
        golden_sha = R.git(lab, "log", "-1", "--format=%H", "HEAD", "--",
                           "golden/r2.cfg")[1].strip()
        monkeypatch.setattr("modules.nsot.scheduled_rotation.last_rotation_commits",
                            lambda: {"r2": golden_sha})
        assert SS.check("Lab", hosts=["r2"])["devices"]["r2"]["golden_after_rotation"] is True

    def test_a_golden_older_than_the_rotation_s_commit_fails_by_identity(self, lab, monkeypatch):
        """The identity check's other side: the rotation committed AFTER the golden's last
        change, so the golden's commit is neither the rotation's nor descends from it."""
        self._ready(lab, monkeypatch, rotated_at=1)
        assert R.git(lab, "-c", "user.email=t@example.invalid", "-c", "user.name=t", "commit",
                     "--allow-empty", "-q", "-m", "a rotation's later commit")[0] == 0
        later = R.git(lab, "rev-parse", "HEAD")[1].strip()
        monkeypatch.setattr("modules.nsot.scheduled_rotation.last_rotation_commits",
                            lambda: {"r2": later})
        assert SS.check("Lab", hosts=["r2"])["devices"]["r2"]["golden_after_rotation"] is False

    def test_the_record_s_commit_stage_names_the_sha(self, monkeypatch):
        """`last_rotation_commits` reads the newest successful rotate row's commit stage."""
        from modules.nsot import scheduled_rotation as S
        rows = [{"phase": "rotate", "device": "s4", "at": "2026-10-13T01:46:40Z",
                 "stages": [{"name": "commit", "ok": True, "reason": "1" * 40}]},
                {"phase": "rotate", "device": "s4", "at": "2026-10-21T01:13:20Z",
                 "stages": [{"name": "commit", "ok": True, "reason": "e" * 40}]},
                {"phase": "rotate", "device": "r9", "at": "2026-10-21T01:00:00Z",
                 "stages": [{"name": "commit", "ok": True, "reason": "no sha here"}]}]
        monkeypatch.setattr("modules.nsot.credential_rotation.rotation_records_as_known",
                            lambda: rows)
        monkeypatch.setattr("modules.nsot.credential_rotation.rotation_succeeded", lambda r: True)
        assert S.last_rotation_commits() == {"s4": "e" * 40}

    def test_a_device_the_last_drift_run_could_not_read_fails(self, lab, monkeypatch):
        self._ready(lab, monkeypatch, drift={"last_check_ts": 1760000000, "last_result": {
            "checked": 1, "errors": [{"hostname": "r2", "reason": "authentication failed"}]}})
        assert SS.check("Lab", hosts=["r2"])["devices"]["r2"]["read_by_drift"] is False

    def test_no_drift_run_is_not_read(self, lab, monkeypatch):
        self._ready(lab, monkeypatch, drift={})
        assert SS.check("Lab", hosts=["r2"])["devices"]["r2"]["read_by_drift"] is False

    def test_the_helper_prints_facts_never_a_value_and_exits_by_the_result(
            self, lab, monkeypatch, capsys):
        self._ready(lab, monkeypatch, rotated_at=1)
        monkeypatch.setattr("modules.device.load_saved_devices",
                            lambda path: [{"hostname": "r2"}])
        assert _cli().main(["--check", "--list", "Lab"]) == 0
        out = capsys.readouterr().out
        assert "r2: ok | source " in out and out.rstrip().endswith("1 of 1 pass")
        assert "$9$" not in out and "public" not in out and "admin" not in out
        monkeypatch.setattr("modules.nsot.scheduled_rotation.last_rotations",
                            lambda: {"r2": (4102444800, "2100-01-01T00:00:00Z")})
        assert _cli().main(["--check", "--list", "Lab"]) == 1
        out = capsys.readouterr().out
        assert "r2: FAILS: its golden is older than its last rotation" in out
        assert out.rstrip().endswith("0 of 1 pass; failing: r2")

    def test_a_rotation_only_since_the_baseline_leaves_the_configuration_current(
            self, lab, monkeypatch):
        """C1454's control: r2's one commit after its source (the baseline: the rotation's
        capture is not recorded at intent here) is a rotation, which the build already
        carries, so nothing is undone."""
        self._ready(lab, monkeypatch, rotated_at=1, rotation_at_intent=False)
        r = SS.check("Lab", hosts=["r2"])["devices"]["r2"]
        assert r["commits_since"] == 1 and "Save All" in r["source_how"]
        assert r["config_current"] is True and r["undoes"] == [] and r["lines_undone"] == 0

    def test_a_deploy_after_the_baseline_is_named_as_what_a_redeploy_would_undo(
            self, lab, monkeypatch, capsys):
        """C1454 (Lab 8, 2026-10-20): r4's Gi5 and s3's removed route were verified and
        committed after the newest earned baseline, and the pre-flight said "9 of 9 pass".
        Since part (1) a deploy recorded at intent is the source; a golden committed after the
        source that is NOT recorded at its intent (here neither the rotation nor the deploy is)
        FAILS the device, naming the commits and the count of lines, never a line."""
        self._ready(lab, monkeypatch, rotated_at=1, rotation_at_intent=False)
        changed = WITH_APPLET.replace("\nend", "\nip route 192.0.2.0 255.255.255.0 Null0\nend")
        _intent(monkeypatch, off={"r2"})
        got = R.save_golden("Lab", [R.GoldenItem("r2", changed, "203.0.113.12",
                                                 platform="cisco_ios")],
                            source="deploy", actor="t", allow_new=False)
        assert got["ok"]
        _intent(monkeypatch)
        r = SS.check("Lab", hosts=["r2"])["devices"]["r2"]
        assert r["commits_since"] == 2 and r["config_current"] is False
        assert r["lines_undone"] == 1
        assert len(r["undoes"]) == 2 and r["undoes"][0].split()[0] == got["commit"][:len(
            r["undoes"][0].split()[0])]
        monkeypatch.setattr("modules.device.load_saved_devices",
                            lambda path: [{"hostname": "r2"}])
        assert _cli().main(["--check", "--list", "Lab"]) == 1
        out = capsys.readouterr().out
        assert ("r2: FAILS: a redeploy would undo 1 configuration line(s) its golden gained "
                f"after its source {r['source_commit']}, not recorded at its committed "
                "intent: ") in out
        assert got["commit"][:7] in out and "192.0.2.0" not in out
        assert out.rstrip().endswith("0 of 1 pass; failing: r2")

    def test_check_writes_nothing_and_out_is_required_without_it(self, lab, monkeypatch, tmp_path):
        self._ready(lab, monkeypatch, rotated_at=1)
        monkeypatch.setattr("modules.device.load_saved_devices",
                            lambda path: [{"hostname": "r2"}])
        cli = _cli()
        here = tmp_path / "cwd"
        here.mkdir()
        monkeypatch.chdir(here)
        assert cli.main(["--check", "--list", "Lab"]) == 0
        assert list(here.iterdir()) == []
        with pytest.raises(SystemExit):
            cli.main(["--list", "Lab"])

    def test_a_device_the_last_drift_run_found_departing_fails(self, lab, monkeypatch, capsys):
        """C1454 (1), "no drift since": the file boots the golden, so a change the drift run
        found on the device and nobody recorded would be undone, and the pre-flight says so."""
        self._ready(lab, monkeypatch, rotated_at=1, drift={
            "last_check_ts": 1760000000, "last_result": {
                "checked": 1, "errors": [], "skipped": [],
                "drifted_devices": [{"hostname": "r2", "diff_lines": 3}]}})
        r = SS.check("Lab", hosts=["r2"])["devices"]["r2"]
        assert r["drifted"] is True and r["read_by_drift"] is True
        monkeypatch.setattr("modules.device.load_saved_devices",
                            lambda path: [{"hostname": "r2"}])
        assert _cli().main(["--check", "--list", "Lab"]) == 1
        out = capsys.readouterr().out
        assert ("r2: FAILS: the last drift run (2025-10-09T08:53Z) found it departing from its "
                "golden: a redeploy would undo that unrecorded change") in out


R7_APPLET = WITH_APPLET.replace("hostname r2", "hostname r7")
#: r7 with one line more: a capture whose golden moves.
R7_MOVED = R7_APPLET.replace("\nend", "\nlogging buffered 8192\nend")


class TestTheSourceIsTheNewestGoldenAtIntent:
    """C1454 (1): each device's source is its newest golden recorded at its committed intent
    (a save's `Intent-Match:` for it), the newest earned baseline only as the fallback, and
    every credential family still from its current golden (C309)."""

    _ready = TestThePreflightCheck._ready

    def _save(self, host, text, source, off=False, monkeypatch=None):
        if off:
            _intent(monkeypatch, off={host})
        got = R.save_golden("Lab", [R.GoldenItem(host, text, "203.0.113.12",
                                                 platform="cisco_ios")],
                            source=source, actor="t", allow_new=False)
        assert got["ok"] and got["commit"], got
        _intent(monkeypatch)
        return got

    def test_a_verified_deploy_at_intent_after_the_baseline_is_the_source(
            self, lab, monkeypatch, capsys):
        """The C1454 case: r2's deploy, captured and recorded at its intent after the newest
        earned baseline, is in the file; the pre-flight passes and names that commit."""
        self._ready(lab, monkeypatch, rotated_at=1, rotation_at_intent=False)
        route = "ip route 192.0.2.0 255.255.255.0 Null0"
        deployed = self._save("r2", WITH_APPLET.replace("\nend", f"\n{route}\nend"),
                              "pipeline", monkeypatch=monkeypatch)
        got = SS.build("Lab", hosts=["r2"])
        assert route in got["devices"]["r2"]["text"]
        assert got["devices"]["r2"]["source"] == {
            "commit": deployed["commit"],
            "how": "recorded at its committed intent by a deploy"}
        r = SS.check("Lab", hosts=["r2"])["devices"]["r2"]
        assert r["config_current"] is True and r["commits_since"] == 0
        monkeypatch.setattr("modules.device.load_saved_devices",
                            lambda path: [{"hostname": "r2"}])
        assert _cli().main(["--check", "--list", "Lab"]) == 0
        out = capsys.readouterr().out
        assert (f"r2: ok | source {deployed['commit'][:10]} (recorded at its committed intent "
                "by a deploy) / golden ") in out
        assert route not in out and out.rstrip().endswith("1 of 1 pass")

    def test_a_golden_recorded_off_its_intent_is_never_the_source(self, lab, monkeypatch):
        """C306 kept: a capture that departs from intent (a change nobody approved) is
        committed, and the file stays the newest golden that was at intent."""
        self._ready(lab, monkeypatch, rotated_at=1)
        rotation = R.git(lab, "log", "-1", "--format=%H", "HEAD", "--",
                         "golden/r2.cfg")[1].strip()
        route = "ip route 192.0.2.0 255.255.255.0 Null0"
        self._save("r2", WITH_APPLET.replace("\nend", f"\n{route}\nend"), "capture",
                   off=True, monkeypatch=monkeypatch)
        got = SS.build("Lab", hosts=["r2"])["devices"]["r2"]
        assert route not in got["text"] and got["source"]["commit"] == rotation
        r = SS.check("Lab", hosts=["r2"])["devices"]["r2"]
        assert r["config_current"] is False and r["lines_undone"] == 1

    def test_credentials_come_from_the_current_golden_when_the_source_is_older(
            self, lab, monkeypatch):
        """C309 kept: the source is a deploy recorded at intent, then a rotation commits the
        new account and is NOT recorded at intent. The file carries the deploy's route and the
        rotation's account, never the retired one, and passes: a rotation-only commit since its
        source undoes no configuration."""
        _seed("Lab", [R.GoldenItem("r2", R2_APPLET, "203.0.113.12", platform="cisco_ios")],
              source="save_all")
        route = "ip route 192.0.2.0 255.255.255.0 Null0"
        deployed = self._save("r2", R2_APPLET.replace("\nend", f"\n{route}\nend"), "pipeline",
                              monkeypatch=monkeypatch)
        self._save("r2", WITH_APPLET.replace("\nend", f"\n{route}\nend"), "rotation",
                   off=True, monkeypatch=monkeypatch)
        monkeypatch.setattr("modules.nsot.scheduled_rotation.last_rotations", lambda: {})
        monkeypatch.setattr("modules.drift_check._load_state", lambda list_name="": {
            "last_check_ts": 1760000000,
            "last_result": {"checked": 1, "errors": [], "skipped": []}})
        got = SS.build("Lab", hosts=["r2"])["devices"]["r2"]
        assert got["source"]["commit"] == deployed["commit"]
        assert route in got["text"] and NEW_ACCOUNT in got["text"]
        assert OLD_ACCOUNT not in got["text"]
        r = SS.check("Lab", hosts=["r2"])["devices"]["r2"]
        assert r["commits_since"] == 1 and r["credentials_current"] is True
        assert r["config_current"] is True and r["undoes"] == []

    def test_the_check_names_each_device_s_source_commit(self, lab, monkeypatch, capsys):
        """Two devices, two sources: r2's rotation and r7's onboarding, each recorded at its
        intent after the baseline, each named on its own line."""
        self._ready(lab, monkeypatch, rotated_at=1)
        r2 = R.git(lab, "log", "-1", "--format=%H", "HEAD", "--", "golden/r2.cfg")[1].strip()
        r7 = _seed("Lab", [R.GoldenItem("r7", R7_APPLET, "203.0.113.17",
                                        platform="cisco_ios")])["commit"]
        monkeypatch.setattr("modules.device.load_saved_devices",
                            lambda path: [{"hostname": "r2"}, {"hostname": "r7"}])
        assert _cli().main(["--check", "--list", "Lab"]) == 0
        out = capsys.readouterr().out
        assert (f"r2: ok | source {r2[:10]} (recorded at its committed intent by a rotation)"
                in out)
        assert f"r7: ok | source {r7[:10]} (recorded at its committed intent by a save)" in out
        assert out.rstrip().endswith("2 of 2 pass")

    def test_beyond_the_read_the_newest_earned_baseline_is_the_fallback(self, lab, monkeypatch):
        """The fallback: when the read of measurements (here bounded to one) reaches no
        record of r2 at intent, the newest earned baseline holding its golden is the source,
        and it says so."""
        out = _seed("Lab", [R.GoldenItem("r2", R2_APPLET, "203.0.113.12",
                                         platform="cisco_ios")], source="save_all")
        tag = next(t for t in out["tags"] if t.startswith("baseline/"))
        self._save("r2", WITH_APPLET, "capture", off=True, monkeypatch=monkeypatch)
        monkeypatch.setattr("modules.device_list.LOG_BOUND", 1)
        got = SS.build("Lab", hosts=["r2"])["devices"]["r2"]
        assert got["source"] == {"commit": out["commit"], "how": (
            f"the newest earned baseline {tag}, the fallback: no newer record of it at its "
            "committed intent in the last 1 measurements")}

    def test_a_retired_device_s_golden_never_sources_the_new_device_of_its_name(
            self, lab, monkeypatch):
        """The device's life bounds the walk: r7 was at intent and in the earned baseline,
        then its golden was removed (retired), then a new r7 was captured off its intent. The
        old r7's goldens are older than the new file, so r7 is refused, never booted as the
        retired device."""
        out = _seed("Lab", [R.GoldenItem("r2", R2_APPLET, "203.0.113.12", platform="cisco_ios"),
                            R.GoldenItem("r7", R7_APPLET, "203.0.113.17", platform="cisco_ios")],
                    source="save_all")
        tag = next(t for t in out["tags"] if t.startswith("baseline/"))
        with R.repo_lock(lab):
            assert R.git(lab, "rm", "-q", "--", "golden/r7.cfg")[0] == 0
            rc, _o, err = R.commit(lab, "retire: r7\n\nSource: retire\nActor: t\n",
                                   list_name="Lab", paths=["golden/r7.cfg"], publish_now=False)
        assert rc == 0, err
        _intent(monkeypatch, off={"r7"})
        assert R.save_golden("Lab", [R.GoldenItem("r7", R7_APPLET + "!\n", "203.0.113.17",
                                                  platform="cisco_ios")],
                             source="capture", actor="t", allow_new=True)["ok"]
        got = SS.build("Lab", hosts=["r2", "r7"])["devices"]
        assert got["r2"]["state"] == "ok"
        assert got["r7"]["state"] == "refused"
        assert got["r7"]["why"].startswith(
            f"no golden of r7 is recorded at its committed intent, and {tag} holds no golden "
            "of it since its current golden was created"), got["r7"]["why"]


def _commit_intent(lab, host):
    """A committed intent for *host* (what `device_list.intent_state` needs to judge it)."""
    rel = f"host_vars/{host}.yml"
    path = os.path.join(lab, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with R.repo_lock(lab):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(f"hostname: {host}\n")
        assert R.git(lab, "add", "--", rel)[0] == 0
        rc, _o, err = R.commit(lab, f"intent: {host}\n\nSource: test\nActor: t\n",
                               list_name="Lab", paths=[rel], publish_now=False)
    assert rc == 0, err


class TestABaselineAfterAScopedDeploy:
    """C1454 (2): a verified deploy to r2 earns a baseline when every device outside it (r7)
    stands at its committed intent by its record (its committed golden's measurement and the
    last drift run), rather than being refused as "not targeted"."""

    LATER = 4102444800                     # a drift run after every commit here (2100)

    def _fleet(self, lab, monkeypatch, drift_at=LATER, errors=(), drifted=()):
        R.init_repo(lab)
        for h in ("r2", "r7"):
            _commit_intent(lab, h)
        _seed("Lab", [R.GoldenItem("r2", R2_APPLET, "203.0.113.12", platform="cisco_ios"),
                      R.GoldenItem("r7", R7_APPLET, "203.0.113.17", platform="cisco_ios")],
              source="save_all")
        monkeypatch.setattr("modules.nsot.restore._devices_of",
                            lambda list_name: [{"hostname": "r2"}, {"hostname": "r7"}])
        state = {"last_check_ts": drift_at, "last_result": {
            "checked": 2, "errors": [{"hostname": h, "reason": "x"} for h in errors],
            "skipped": [], "drifted_devices": [{"hostname": h, "diff_lines": 1}
                                               for h in drifted]}}
        monkeypatch.setattr("modules.drift_check._load_state", lambda list_name="": state)

    ROUTE = "ip route 192.0.2.0 255.255.255.0 Null0"

    def _pending(self):
        return [{"hostname": "r2", "config_text": R2_APPLET.replace("\nend", f"\n{self.ROUTE}\nend"),
                 "mgmt_ip": "203.0.113.12", "netbox_id": None, "device_uid": "r2"}]

    def _earned(self):
        from routes.deploy import _baseline_earned
        return _baseline_earned({}, self._pending(), [], source_ref="", list_name="Lab")

    def test_a_deploy_to_one_device_earns_a_baseline_when_the_rest_stand_at_intent(
            self, lab, monkeypatch):
        from modules.nsot.deploy import DEPLOYED
        from routes.deploy import _commit_batch_golden

        self._fleet(lab, monkeypatch)
        r7 = R.git(lab, "log", "-1", "--format=%H", "HEAD", "--", "golden/r7.cfg")[1].strip()
        report = {"batch_id": "t1", "results": [
            {"device": "r2", "outcome": DEPLOYED, "golden_pending": self._pending()}]}
        got = _commit_batch_golden("Lab", report, actor="t")
        assert got["baseline"] is True and got["ok"], got
        assert [t for t in got["tags"] if t.startswith("baseline/")], got.get("baseline_denied")
        body = R.git(lab, "log", "-1", "--format=%B", got["commit"])[1]
        assert "Baseline: earned" in body
        assert f"Judged-Outside: r7 (golden {r7[:10]}, drift run 2100-01-01T00:00Z)" in body
        assert got["baseline_reasons"] == [
            "every inventory device is in this commit, or outside it and shown at its "
            "committed intent by its golden and the last drift run: r7"]

    def test_a_device_outside_off_its_intent_denies_it_as_a_partial_operation(
            self, lab, monkeypatch):
        """The control: r7's newest capture departs from its intent, so the deploy to r2
        does not cover the network, said as C885's coverage reason."""
        from modules.nsot.repo import not_targeted_only

        self._fleet(lab, monkeypatch)
        _intent(monkeypatch, off={"r7"})
        assert R.save_golden("Lab", [R.GoldenItem("r7", R7_MOVED, "203.0.113.17",
                                                  platform="cisco_ios")],
                             source="capture", actor="t")["ok"]
        _intent(monkeypatch)
        out = self._earned()
        assert out["baseline"] is False and out["standing"] == {}
        (why,) = out["baseline_reasons"]
        assert why.startswith("1 device(s) not targeted: ['r7'], not shown at intent (r7: its "
                              "intent state is departs (+1))"), why
        assert not_targeted_only(why) == 1

    @pytest.mark.parametrize("errors, drifted, words", [
        (("r7",), (), "the last drift run could not read it"),
        ((), ("r7",), "the last drift run found it departing from its golden"),
    ])
    def test_the_last_drift_run_decides_for_a_device_it_read_after_its_capture(
            self, lab, monkeypatch, errors, drifted, words):
        self._fleet(lab, monkeypatch, errors=errors, drifted=drifted)
        out = self._earned()
        assert out["baseline"] is False
        assert out["baseline_reasons"] == [
            f"1 device(s) not targeted: ['r7'], not shown at intent (r7: {words})"]

    def test_a_capture_newer_than_the_last_drift_run_is_the_newest_read(self, lab, monkeypatch):
        """A drift run before r7's capture that could not read it says nothing about now:
        the capture read it since, at its intent."""
        self._fleet(lab, monkeypatch, drift_at=1, errors=("r7",))
        out = self._earned()
        assert out["baseline"] is True, out["baseline_reasons"]
        assert sorted(out["standing"]["devices"]) == ["r7"]

    def test_a_judged_golden_that_moves_before_the_commit_refuses_the_baseline(
            self, lab, monkeypatch):
        """The judgement is read before the save takes the repository's lock; a commit to r7's
        golden in between (another operation) means the baseline would rest on a judgement of
        another moment, so the save refuses it, naming the file."""
        self._fleet(lab, monkeypatch)
        out = self._earned()
        assert out["baseline"] is True
        assert R.save_golden("Lab", [R.GoldenItem("r7", R7_MOVED, "203.0.113.17",
                                                  platform="cisco_ios")],
                             source="capture", actor="t")["ok"]
        p = self._pending()[0]
        got = R.save_golden("Lab", [R.GoldenItem("r2", p["config_text"], p["mgmt_ip"])],
                            source="pipeline", actor="t", baseline=True,
                            standing=out["standing"])
        assert got["ok"] and not got["baseline"]
        assert got["baseline_denied"] == [
            "what the devices outside this deploy were judged by moved after the judgement "
            "(golden/r7.cfg), so it is not of this commit's moment: Save All"]

    def test_a_judged_device_another_operation_holds_refuses_the_baseline(
            self, lab, monkeypatch):
        """C2030 extended to the devices judged outside the batch: r7 held for a rotation by
        another process may be changing its record, so no baseline rests on it."""
        pytest.importorskip("fcntl")
        from modules import config
        from tests.test_scheduled_rotation import _held_by_another_process

        self._fleet(lab, monkeypatch)
        out = self._earned()
        assert out["baseline"] is True
        p = self._pending()[0]
        child = _held_by_another_process(config.DATA_DIR, "r7", "rotate",
                                         "rotation@example.invalid", detail="")
        try:
            got = R.save_golden("Lab", [R.GoldenItem("r2", p["config_text"], p["mgmt_ip"])],
                                source="pipeline", actor="t", baseline=True,
                                standing=out["standing"])
        finally:
            child.kill()
            child.wait(5)
        assert got["ok"] and not got["baseline"]
        (why,) = got["baseline_denied"]
        assert why.startswith("r7 is being rotated by rotation@example.invalid"), why
