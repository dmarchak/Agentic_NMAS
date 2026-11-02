"""Board FC phase 2 (f), PHASE8_PLAN 22.2 (1) and (3): a fleet change on each ticked device's OWN
document (FC1's Change across the N ticked…), its plan (`fleet_change.plan_selection`) and its
approval (`approve_selection`), on r2's real config and committed intent
(`tests.test_capture.build_capture_lab`); and the one run both targets share. THE apply
(`routes.deploy.apply_batch`) is replaced by a recorder: no test reaches a device.

- **The seam** (`hostvars.proposed`): inside it, r2's committed intent reads as the proposed
  text, for that repository alone; outside it, as committed.
- **The plan** is bulk intent's compare-and-set and gates, then the deploy's own program:
  r2 gaining an NTP server plans that one line, nothing committed; a before r2 does not hold
  refuses r2 by name; a controller-managed switch ticked is refused in the authority's words;
  one plan is one hash, another after another.
- **The approval** commits every accepted device's document once (`Source: fleet-change`, the
  plan's hash); another hash commits nothing.
- **A change no program moves on** (a layer value r2's own document already holds) is still
  committed, and its run sends nothing: done, no batch.
"""

import subprocess

import pytest

from modules.nsot import capture_job
from modules.nsot import bulk_intent as B
from modules.nsot import fleet_change as F
from modules.nsot import hostvars
from tests.test_fleet_change_plan import NTP, _head, lab, r2  # noqa: F401 (the fixtures)
from tests.test_fleet_change_run import sent  # noqa: F401 (the fixture)
from tests.test_monitoring_profile_plan import _intent

#: r2's own document holds `ntp_servers: []` (the fixture), so its step's before is that.
OWN = [dict(NTP[0], before=[])]


@pytest.fixture
def own(r2):  # noqa: F811
    """r2 as `r2`, its committed syslog block whole: bulk intent's gate refuses a document whose
    block lacks its heartbeat (`hostvars.syslog_block_problems`), and the capture's lacks one, so
    the change is planned on a document that gate passes. The heartbeat committed first, so the
    change's lines are the NTP server's alone."""
    from modules.nsot.repo import save_host_vars
    intent = _intent(r2["repo"])
    intent["logging"]["syslog"]["heartbeat"] = 300
    hostvars.write_committed(r2["repo"], intent)
    assert save_host_vars("Lab", ["r2"], actor="t", source="extraction")["ok"]
    return r2


def _log(repo, since):
    return subprocess.run(["git", "-C", repo, "log", "--format=%B", f"{since}..HEAD"],
                          capture_output=True, text=True, check=True).stdout


class TestTheSeam:
    def test_a_proposed_document_reads_as_committed_inside_alone(self, r2, tmp_path):  # noqa: F811
        repo = r2["repo"]
        before, state = hostvars.committed_at_head(repo, "r2")
        assert before and state == hostvars.COMMITTED
        with hostvars.proposed(repo, {"r2": "hostname: proposed\n"}):
            assert hostvars.committed_at_head(repo, "r2") == ("hostname: proposed\n",
                                                               hostvars.COMMITTED)
            assert hostvars.committed_at_head(str(tmp_path), "r2")[0] is None, \
                "another repository is not stood in for"
        assert hostvars.committed_at_head(repo, "r2") == (before, state)


class TestThePlan:
    def test_r2s_own_document_gaining_a_server_plans_that_line_and_commits_nothing(self, own):
        head = _head(own["repo"])
        got = F.plan_selection("Lab", ["r2"], OWN)
        assert got["ok"], got["error"]
        assert [d["device"] for d in got["devices"]] == ["r2"]
        assert got["devices"][0]["change"] == ["ntp server 192.0.2.123"]
        assert got["groups"] == [{"lines": ["ntp server 192.0.2.123"], "left": [],
                                  "devices": ["r2"]}]
        assert got["target"] == {"kind": "devices", "devices": ["r2"],
                                 "label": "1 device's own intent"}
        assert "192.0.2.123" in got["texts"]["r2"] and got["layer"] == {}
        assert _head(own["repo"]) == head, "a plan commits nothing"
        assert hostvars.committed_at_head(own["repo"], "r2")[0] != got["texts"]["r2"]

    def test_a_before_r2_does_not_hold_refuses_it_by_name(self, r2):  # noqa: F811
        got = F.plan_selection("Lab", ["r2"], [dict(NTP[0], before=["192.0.2.1"])])
        assert got["ok"] and got["devices"] == []
        [refused] = got["refused"]
        assert refused["device"] == "r2"
        assert "its current intent is not what the change expects" in refused["reasons"][0]

    def test_a_controller_managed_switch_ticked_is_refused_in_the_authoritys_words(
            self, r2, monkeypatch):  # noqa: F811
        """17.1 S12: the plan refuses it whatever bulk intent made of it."""
        accepted = {"device": "of1", "blob": "b", "text": "hostname: of1\n", "was": ""}
        real = B.plan

        def plan(repo, devices, steps, **kw):
            report = real(repo, [d for d in devices if d != "of1"], steps, **kw)
            return dict(report, accepted=report["accepted"] + [accepted])
        monkeypatch.setattr(B, "plan", plan)
        r2["rows"].append({"hostname": "of1", "platform": "openflow via lab-ctl", "_tags": []})
        got = F.plan_selection("Lab", ["r2", "of1"], OWN)
        assert got["ok"], got["error"]
        [refused] = [r for r in got["refused"] if r["device"] == "of1"]
        assert "managed by its controller, lab-ctl" in refused["reasons"][0]
        assert "of1" not in got["texts"] and "of1" not in [d["device"] for d in got["devices"]]

    def test_one_plan_is_one_hash_and_another_after_another(self, own):
        a, b = F.plan_selection("Lab", ["r2"], OWN), F.plan_selection("Lab", ["r2"], OWN)
        assert a["hash"] and a["hash"] == b["hash"]
        other = F.plan_selection("Lab", ["r2"], [dict(OWN[0], after=["192.0.2.124"])])
        assert other["ok"] and other["hash"] != a["hash"]

    def test_the_documents_move_the_hash_when_no_program_does(self, own, monkeypatch):
        """Two changes whose programs are the same (the comparison stood in for) but whose
        documents differ are two hashes: the approval commits the documents, so one approval
        never covers another change."""
        def same(list_name, hosts, proposing, out):
            out["devices"] = [{"device": h, "change": ["x"], "left": [], "pending": 0,
                               "command_hash": "same"} for h in hosts]
            return ""
        monkeypatch.setattr(F, "_plan_programs", same)
        a = F.plan_selection("Lab", ["r2"], OWN)
        # The same steps; only the document bulk intent hands back differs.
        real = B.plan

        def other_text(repo, devices, steps, **kw):
            report = real(repo, devices, steps, **kw)
            return dict(report, accepted=[dict(x, text=x["text"] + "# another\n")
                                          for x in report["accepted"]])
        monkeypatch.setattr(B, "plan", other_text)
        b = F.plan_selection("Lab", ["r2"], OWN)
        assert a["devices"] == b["devices"] and a["steps"] == b["steps"]
        assert a["hash"] != b["hash"]

    def test_a_ticked_device_not_in_the_inventory_is_refused_by_name(self, r2):  # noqa: F811
        got = F.plan_selection("Lab", ["r2", "r99"], [dict(NTP[0], before=["192.0.2.1"])])
        assert got["ok"]
        [r99] = [r for r in got["refused"] if r["device"] == "r99"]
        assert r99["reasons"] == ["not in this list's inventory (stale, or a typo)"]

    def test_nothing_ticked_is_refused(self):
        got = F.plan_selection("Lab", [], NTP)
        assert not got["ok"] and got["error"] == "no device is ticked"


class TestTheApproval:
    def test_the_confirmed_hash_commits_each_document_once(self, own):
        head = _head(own["repo"])
        plan = F.plan_selection("Lab", ["r2"], OWN)
        got = F.approve_selection("Lab", ["r2"], OWN, plan["hash"], summary="r2's NTP server",
                                  reason="its time source", actor="op@example.com")
        assert got["ok"], got["error"]
        log = _log(own["repo"], head)
        assert log.count("r2's NTP server") == 1, "one commit"
        assert "Source: fleet-change" in log and f"Plan: {plan['hash']}" in log
        assert "Devices: r2" in log and "op@example.com" in log
        assert "192.0.2.123" in hostvars.committed_at_head(own["repo"], "r2")[0]

    def test_an_uncommitted_edit_in_host_vars_commits_nothing(self, own):
        """The commit stages host_vars/, so an edit nobody committed would ride in under this
        change's name: refused, naming it."""
        import os
        plan = F.plan_selection("Lab", ["r2"], OWN)
        head = _head(own["repo"])
        with open(os.path.join(own["repo"], "host_vars", "stray.yml"), "w") as fh:
            fh.write("hostname: stray\n")
        got = F.approve_selection("Lab", ["r2"], OWN, plan["hash"], summary="s", reason="r",
                                  actor="op@example.com")
        assert not got["ok"] and "host_vars/ has uncommitted changes" in got["error"]
        assert "stray.yml" in got["error"] and _head(own["repo"]) == head

    def test_another_hash_commits_nothing(self, r2):  # noqa: F811
        head = _head(r2["repo"])
        got = F.approve_selection("Lab", ["r2"], OWN, "0" * 64, summary="s", reason="r",
                                  actor="op@example.com")
        assert not got["ok"] and "the plan moved since you read it" in got["error"], got
        assert _head(r2["repo"]) == head


def test_a_change_no_program_moves_on_is_committed_and_its_run_sends_nothing(r2, sent):  # noqa: F811
    """The operator's first fleet change, step 1: a layer value r2's own document already holds
    plans no line; the approval commits the layer, and the run sends nothing."""
    intent = _intent(r2["repo"])
    intent["ntp_servers"] = ["192.0.2.123"]
    hostvars.write_committed(r2["repo"], intent)
    from modules.nsot.repo import save_host_vars
    assert save_host_vars("Lab", ["r2"], actor="t", source="extraction")["ok"]
    plan = F.plan_layer("Lab", "tag-blind-lab", NTP)
    assert plan["ok"] and plan["devices"] == [] and plan["unchanged"], plan
    head = _head(r2["repo"])
    job = F.approve_and_run_start("Lab", "tag-blind-lab", NTP, plan["hash"],
                                  summary="the layer holds r2's server", reason="one home",
                                  canary="r2", batch=1, after_canary="pause",
                                  actor="op@example.com", actor_kind="person")
    assert capture_job.wait(job, 60)
    payload = capture_job.get(job)["payload"]
    assert payload["state"] == "done" and payload["results"] == [] and payload["commit"]
    assert sent["calls"] == [], "nothing sent"
    assert _log(r2["repo"], head).count("the layer holds r2's server") == 1


def test_a_change_that_leaves_the_layer_as_it_is_commits_nothing(r2):  # noqa: F811
    from tests.test_intent_from_column import _commit_layer
    _commit_layer(r2["repo"], "tag-blind-lab.yml", {"ntp_servers": ["192.0.2.123"]})
    steps = [{"path": ["ntp_servers"], "before": ["192.0.2.123"], "after": ["192.0.2.123"]}]
    plan = F.plan_layer("Lab", "tag-blind-lab", steps)
    head = _head(r2["repo"])
    got = F.approve("Lab", "tag-blind-lab", steps, plan["hash"], summary="s", reason="r",
                    actor="op@example.com")
    assert not got["ok"] and "leaves the layer as it is" in got["error"]
    assert _head(r2["repo"]) == head
