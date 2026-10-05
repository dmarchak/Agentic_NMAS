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

    def test_a_device_the_baseline_does_not_hold_is_refused_alone(self, lab):
        out = _seed("Lab", [R.GoldenItem("r2", R2, "203.0.113.12", platform="cisco_ios")], source="save_all")
        tag = next(t for t in out["tags"] if t.startswith("baseline/"))
        _seed("Lab", [R.GoldenItem("r7", R2.replace("hostname r2", "hostname r7"),
                                   "203.0.113.17", platform="cisco_ios")])
        got = SS.build("Lab", hosts=["r2", "r7"])
        assert got["devices"]["r2"]["state"] == "ok"
        assert got["devices"]["r7"] == {"state": "refused", "why": (
            f"{tag} holds no golden for r7 (onboarded since, or renamed): earn a new baseline "
            "(Save All) to build its file")}

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
        assert rows[1] == "r2\tok\tcredentials from its current golden: SNMP communities, accounts"
        assert rows[2].startswith(f"r7\trefused\t{tag} holds no golden for r7")

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
                                                      "scripts/nmas-clab-targets")
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
