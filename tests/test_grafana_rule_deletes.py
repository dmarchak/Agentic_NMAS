"""C1419: Grafana keeps a provisioned alert rule its file has dropped unless a file names it
under ``deleteRules`` (r6's retirement, Lab 8 step 1: 11 rules outlived it). Each generated rules
file gets a delete file beside it naming the rules in its own range that Grafana or the
installed file holds and the new file no longer generates (`modules/grafana_rule_deletes.py`);
the one install step consumes it (`scripts/host-steps/c1419-install-alert-rules.sh`).

- the computation: Grafana's live rules and the installed file's, less the new file's, in the
  writer's own uid range only; computed afresh, so a rule generated again leaves the list;
- the delete file written beside the rules, removed when there is nothing to delete;
- Grafana unread: the installed file alone decides, and the writer says so;
- the heartbeat drop (Retire, C1338): a rule the file names is dropped AND named for deletion;
  a rule no file names that Grafana still runs (r6's state on 2026-10-20) is a step of its own;
- the install step's helper reads a file's rule uids and a delete file's uids.
"""

import os
import subprocess
import sys

import pytest
import yaml

from modules import grafana_rule_deletes as GD

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _rule(device, uid=None, window=915):
    return {"uid": uid or f"nmas-hb-{device}", "title": f"NMAS heartbeat missing: {device}",
            "labels": {"device": device, "window_basis": "measured"},
            "data": [{"relativeTimeRange": {"from": window}, "datasourceUid": "u"}]}


def _doc(*rules):
    return {"apiVersion": 1, "groups": [{"orgId": 1, "name": "nmas-heartbeat",
                                         "folder": "NMAS", "rules": list(rules)}]}


def _write(path, doc):
    path.write_text(yaml.safe_dump(doc))
    return str(path)


class TestTheComputation:
    def test_live_and_installed_less_the_new_file_in_its_own_range(self, tmp_path):
        installed = _write(tmp_path / "installed.yaml",
                           _doc(_rule("r1"), _rule("r6"), _rule("zz", uid="other-zz")))
        new = _doc(_rule("r1"))
        live = {"nmas-hb-r1", "nmas-hb-r9", "nmas-tel-r6-101"}
        assert GD.deletions(new, "nmas-hb-", installed, live) == ["nmas-hb-r6", "nmas-hb-r9"]

    def test_a_rule_generated_again_leaves_the_list(self, tmp_path):
        installed = _write(tmp_path / "installed.yaml", _doc(_rule("r1"), _rule("r6")))
        assert GD.deletions(_doc(_rule("r1"), _rule("r6")), "nmas-hb-", installed,
                            {"nmas-hb-r6"}) == []

    def test_grafana_unread_the_installed_file_decides_and_it_is_said(self, tmp_path):
        installed = _write(tmp_path / "installed.yaml", _doc(_rule("r1"), _rule("r6")))
        got = GD.plan(_doc(_rule("r1")), "nmas-hb-", installed, live=None)
        assert got["uids"] == ["nmas-hb-r6"] and got["live_read"] is False
        assert "Grafana's own rules were not read" in got["said"]
        read = GD.plan(_doc(_rule("r1")), "nmas-hb-", installed, live={"nmas-hb-r7"})
        assert read["uids"] == ["nmas-hb-r6", "nmas-hb-r7"] and read["said"] == ""

    def test_no_installed_file_is_no_rule(self, tmp_path):
        assert GD.deletions(_doc(), "nmas-hb-", str(tmp_path / "absent.yaml"), set()) == []


class TestTheDeleteFile:
    def test_written_beside_the_rules_and_removed_when_empty(self, tmp_path):
        rules = str(tmp_path / "nmas-heartbeat.yaml")
        path = GD.write(rules, ["nmas-hb-r6"])
        assert path == str(tmp_path / "nmas-heartbeat-delete.yaml")
        doc = yaml.safe_load(open(path, encoding="utf-8"))
        assert doc == {"apiVersion": 1, "deleteRules": [{"orgId": 1, "uid": "nmas-hb-r6"}]}
        assert GD.write(rules, []) == "" and not os.path.exists(path)

    def test_the_scripts_lines_name_the_install_step(self, tmp_path, monkeypatch):
        monkeypatch.setattr(GD, "ALERTING", str(tmp_path))
        _write(tmp_path / "nmas-telemetry.yaml",
               _doc(_rule("r6", uid="nmas-tel-r6-101"), _rule("r1", uid="nmas-tel-r1-101")))
        out_dir = tmp_path / "written"
        out_dir.mkdir()
        rules = str(out_dir / "nmas-telemetry.yaml")
        lines = GD.write_beside(_doc(_rule("r1", uid="nmas-tel-r1-101")), "nmas-tel-", rules,
                                "telemetry", live=set())
        assert lines[0].startswith("wrote 1 rule(s) for Grafana to delete to ")
        assert lines[0].endswith(": nmas-tel-r6-101")
        assert lines[-1] == (f"Install with: bash {GD.INSTALL_STEP} telemetry {rules} "
                             f"{tmp_path / 'nmas-telemetry.yaml'}")


@pytest.fixture
def hb():
    from modules import heartbeat_windows as HW
    return HW, HW._script()                                   # noqa: SLF001 - the one loader


class TestTheHeartbeatDrop:
    def test_a_rule_the_file_names_is_dropped_and_named_for_deletion(self, tmp_path, hb):
        HW, H = hb
        installed = _write(tmp_path / "installed.yaml", _doc(_rule("r1"), _rule("r6")))
        written = str(tmp_path / "written.yaml")
        p = HW.drop_plan("r6", H, written, installed, live=set())
        assert p["state"] == "names"
        out = HW.drop_device("r6", p["fingerprint"], actor="op@example.com", why="retired",
                             H=H, written_path=written, installed_path=installed)
        assert out["ok"] and out["deletes"] == ["nmas-hb-r6"]
        doc = yaml.safe_load(open(GD.delete_path(written), encoding="utf-8"))
        assert [d["uid"] for d in doc["deleteRules"]] == ["nmas-hb-r6"]
        assert out["host_step"] == f"bash {HW.INSTALL_STEP} heartbeat {written} {installed}"

    def test_a_rule_grafana_still_runs_that_no_file_names_is_a_step(self, tmp_path, hb):
        """r6 on 2026-10-20: the heartbeat host step had installed a file without it, and
        Grafana kept its rule."""
        HW, H = hb
        installed = _write(tmp_path / "installed.yaml", _doc(_rule("r1"), _rule("r2")))
        written = str(tmp_path / "written.yaml")
        p = HW.drop_plan("r6", H, written, installed, live={"nmas-hb-r6", "nmas-hb-r1"})
        assert p["state"] == "grafana" and p["uid"] == "nmas-hb-r6"
        assert HW.drop_plan("r6", H, written, installed, live={"nmas-hb-r1"})["state"] == "none"

    def test_its_uid_is_the_generators(self, hb):
        HW, H = hb
        m = H.measure([300.0, 301.0, 299.5, 300.2, 300.4, 299.8, 300.1, 300.3], 300)
        rule = H.rule_for("r6", "u", 300, m, 'job="site_syslog"')
        assert rule["uid"] == HW.device_uid("r6") == "nmas-hb-r6"


def _helper(*args):
    return subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "nmas-grafana-rules"),
                           *args], capture_output=True, text=True, timeout=60, cwd=ROOT)


class TestTheInstallStepsHelper:
    def test_a_files_rule_uids_and_a_delete_files_uids(self, tmp_path):
        rules = _write(tmp_path / "nmas-heartbeat.yaml", _doc(_rule("r6"), _rule("r1")))
        got = _helper("rules", rules)
        assert got.returncode == 0 and got.stdout.split() == ["nmas-hb-r1", "nmas-hb-r6"]
        path = GD.write(rules, ["nmas-hb-r9"])
        assert _helper("deletes", path).stdout.split() == ["nmas-hb-r9"]
        assert _helper("deletes", str(tmp_path / "none.yaml")).stdout == ""
