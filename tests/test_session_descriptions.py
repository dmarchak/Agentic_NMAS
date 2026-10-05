"""Authored intent carries no description that is a run's notes (C428, the operator,
2026-10-04).

Five leftovers of live checks sat in committed intent on the host (read-only, 2026-10-04): r2
Loopback0 "NSoT-managed - batch 4 baseline", s3 Loopback0 "NSoT-managed - route seam smoke",
s3 GigabitEthernet0/1 "NSoT-managed - run_targets check", s4 Loopback0 "NSoT-managed - batch 4
baseline", s4 GigabitEthernet0/1 "NSoT-managed - CSCI 5840 Lab 4". The operator's rule: intent
may not carry a description naming a test or a lab session ("NSoT-managed - ...", "smoke",
"check", a course code); those are a run's notes, not the network's design.

Every AUTHORED path refuses one, naming the pattern: the intent editor's gate (with the line),
its commit (`write_committed_text`), and bulk intent per device. EXTRACTED intent and a
restore's record are not judged: they record a device as it is.
"""

import pytest

from modules.nsot import hostvars

LEFTOVERS = ["NSoT-managed - batch 4 baseline", "NSoT-managed - route seam smoke",
             "NSoT-managed - run_targets check", "NSoT-managed - CSCI 5840 Lab 4"]
DECIDED = ["mgmt identity", "spare"]


def _doc(description, iface="Loopback0"):
    return {"hostname": "s3", "interfaces": [{"name": iface, "description": description}]}


def _text(description):
    return f"hostname: s3\ninterfaces:\n- name: Loopback0\n  description: {description}\n"


class TestThePatterns:
    @pytest.mark.parametrize("value", LEFTOVERS)
    def test_every_leftover_on_the_fleet_is_refused(self, value):
        (problem,) = hostvars.description_problems(_doc(value))
        assert problem.startswith(f"interfaces[0].description is {value!r}")
        assert "never a run's notes" in problem

    @pytest.mark.parametrize("value,why", [
        ("uplink smoke test", "a smoke run's note"), ("path check", "a check run's note"),
        ("CSCI 5840 lab", "a course code"), ("NETW3100 bench", "a course code")])
    def test_each_pattern_names_why(self, value, why):
        (problem,) = hostvars.description_problems(_doc(value))
        assert why in problem

    @pytest.mark.parametrize("value", DECIDED + ["VLAN 1000 users", "to r3 Gi0/2",
                                                 "uplink to core", "checkpoint fw"])
    def test_the_operators_choices_and_design_descriptions_pass(self, value):
        assert hostvars.description_problems(_doc(value)) == []

    def test_a_description_anywhere_is_read(self):
        doc = {"hostname": "s3", "description": "route seam smoke",
               "vlans": [{"id": 100, "description": "ok"}]}
        (problem,) = hostvars.description_problems(doc)
        assert problem.startswith("description is 'route seam smoke'")


class TestEveryAuthoredPathRefuses:
    def test_the_commit_refuses_and_writes_nothing(self, tmp_path):
        with pytest.raises(hostvars.SessionDescription, match="the tool's own test-run prefix"):
            hostvars.write_committed_text(str(tmp_path), "s3", _text(LEFTOVERS[1]))
        assert not (tmp_path / "host_vars").exists() or not list((tmp_path / "host_vars").iterdir())

    def test_the_decided_replacement_commits(self, tmp_path):
        assert hostvars.write_committed_text(str(tmp_path), "s3", _text("mgmt identity"))

    def test_a_restores_record_is_not_judged(self, tmp_path):
        assert hostvars.write_committed_text(str(tmp_path), "s3", _text(LEFTOVERS[1]),
                                             judge_descriptions=False)

    def test_the_restore_writes_its_record_unjudged(self):
        import inspect
        from routes import deploy
        assert ("hostvars.write_committed_text(repo, device, text, judge_descriptions=False)"
                in inspect.getsource(deploy))

    def test_extracted_intent_is_recorded_as_the_device_holds_it(self, tmp_path):
        assert hostvars.write_committed(str(tmp_path), _doc(LEFTOVERS[2], "GigabitEthernet0/1"))

    def test_the_editor_refuses_with_the_line(self):
        from modules.nsot.intent_edit import validate
        text = ("hostname: s3\ninterfaces:\n- name: Loopback0\n  description: mgmt identity\n"
                "- name: GigabitEthernet0/1\n  description: NSoT-managed - run_targets check\n")
        got = validate("s3", text)
        assert got["ok"] is False
        assert got["status"] == 400 and got["stage"] == "schema" and got["line"] == 6
        assert "the tool's own test-run prefix" in got["error"]

    def test_bulk_refuses_the_device_with_the_reason(self):
        import inspect
        from modules.nsot import bulk_intent
        src = inspect.getsource(bulk_intent)
        assert "gate += hostvars.description_problems(after)" in src
