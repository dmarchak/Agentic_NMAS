"""C3165 (the operator, 2026-11-12): the first live Auto heal re-applied one device's applet,
its capture equalled its golden, and its commit recorded "Baseline: denied: not every
inventory device was captured (1 of an unstated number)". Needs attention then said "The
network's last baseline was not earned (heal_to_intent)" and told the reader to "Resolve each
departure the reasons name" under a reason that named none.

The operator's fix and his decision on what it covers (C3167), each part held here on r2's
real capture and committed intent (`tests.test_intent_match`'s lab), the commits made by the
real `_commit_batch_golden` and `save_golden` in a real git repository, and the rows drawn by
the real source:

- "a) A heal's (or any one-device) commit makes no network baseline decision. Add a test: a
  one-device heal commit raises no baseline row." Decided the same day: "only heals exempt.
  Keep C1454 (2) and C2270 for a person's one-device deploy. A heal makes no network baseline
  decision (no earned baseline and no coverage denial), but a management-path cut by a heal
  still records its C2270 denial: safety records are never skipped." A heal's commit is
  still made (the heal's record links to it) and carries no `Baseline:` trailer; the same
  batch as a person's deploy decides as it always did; a heal that cut Mercury's path records
  that denial, and the row is drawn. (A person's one-device deploy earning one with the
  others at intent is tests/test_startup_source.py's, which has the fleet for it.)
- "b) The row's "What to do" must match its cause: a coverage reason says to capture the
  missing devices, not to resolve departures. And "1 of an unstated number" names the count
  ("1 of 13")."
- "c) A full capture with no departures earns the baseline, even if nothing changed." A Save
  All did; a deploy that covers the inventory does now (C2105), and the row clears with it.
- "d) Clear the current row by the corrected rule. Don't acknowledge it, and don't hand-edit
  the record." The record the host holds is written here as the old save wrote it, and the
  source passes over it and reads the decision before it; the controls are the denials it
  must never pass over: a person's deploy's, and a heal's that carries a cut path.
"""

import subprocess

import pytest

from modules import attention as A
from modules import history_sources as HS
from modules.nsot import repo as R
from modules.nsot.deploy import DEPLOYED
from tests.test_intent_match import _broken, lab  # noqa: F401 (the fixture)

#: A nine-device inventory, r2 among them (the lab's one device with a golden here).
NINE = ["r1", "r2", "r3", "r4", "r6", "s1", "s2", "s3", "s4"]
HEAL = "heal_to_intent"
#: The host's record, as the operator read it from the row (2026-11-12).
HOST_REASON = "not every inventory device was captured (1 of an unstated number)"
A_HEAL = ("a heal's commit makes no decision about the network's baseline: it repairs the "
          "devices it names (1 of 9 inventory devices); Save All captures every device and "
          "takes one")
#: What a program that cut Mercury's path leaves as its reason (`routes.deploy._reach_cut`).
CUT = ("r2's program cut Mercury's path to s3, so the network is not shown at its intent: "
       "repair the path, then Save All")
CUT_REMEDY = "Check Mercury's path to each device the reason names, and repair it where it is cut"
ROUTE = "\nip route 192.0.2.0 255.255.255.0 Null0\nend"


@pytest.fixture
def nine(lab, monkeypatch):  # noqa: F811
    monkeypatch.setattr("modules.config.get_current_list_name", lambda: "Lab")
    monkeypatch.setattr("modules.nsot.restore._devices_of",
                        lambda list_name: [{"hostname": h} for h in NINE])
    # No baseline-usability answer unless a test gives one.
    monkeypatch.setattr("modules.reader_job.read_cached", lambda name: {"state": "absent"})
    return lab


def _body(repo, sha="HEAD"):
    return subprocess.run(["git", "-C", repo, "log", "-1", "--format=%B", sha],
                          capture_output=True, text=True, check=True).stdout


def _capture(config):
    """r2's golden recorded by a capture of one device, which asks for no decision."""
    out = R.save_golden("Lab", [R.GoldenItem("r2", config, "203.0.113.12")], source="capture",
                        actor="t", allow_new=False)
    assert out["ok"] and out["commit"], out
    return out


def _save_all(config, inventory_size=1, skipped=None):
    return R.save_golden("Lab", [R.GoldenItem("r2", config, "203.0.113.12")], actor="t",
                         source="save_all", inventory_size=inventory_size, skipped=skipped)


def _batch(config, source="", heal=False, reach_lost=None):
    """A batch of r2 alone, committed as the deploy (or the heal) commits it."""
    from routes.deploy import _commit_batch_golden

    pending = [{"hostname": "r2", "config_text": config, "mgmt_ip": "203.0.113.12",
                "netbox_id": None, "device_uid": ""}]
    entry = {"device": "r2", "outcome": DEPLOYED, "golden_pending": pending}
    if heal:
        entry["heal"] = {"decision": "hd-0123456789ab"}
    if reach_lost:
        entry["reach_lost"] = reach_lost
    got = _commit_batch_golden("Lab", {"batch_id": "t1", "results": [entry]}, actor="t",
                               source=source)
    assert got["ok"], got
    # The batch's commit is its record, a golden changed or not: a heal's step log and a
    # deploy's receipt link to it.
    assert got["commit"], f"the batch made no golden commit: {got.get('message')}"
    return got


def _old_record(repo, source, decision, devices="r2"):
    """A decision commit AS THE SAVE WROTE IT before 2026-11-12: the record a host already
    holds. Written through `repo.commit`, never through today's `save_golden`, which no longer
    writes one for a heal."""
    message = (f"golden: no configuration changed; decision recorded (1 device(s) measured "
               f"via {source})\n\nSource: {source}\nActor: t\nDevices-Measured: {devices}\n"
               f"Intent-Match: yes (1 of 1)\nBaseline: {decision}\n"
               "Not-Done: no golden changed: every capture equals its committed golden\n")
    with R.repo_lock(repo):
        rc, _out, err = R.commit(repo, message, list_name="Lab", allow_empty=True,
                                 publish_now=False)
    assert rc == 0, err
    return R.git(repo, "rev-parse", "HEAD")[1].strip()


def _the_row(out=None):
    """The baseline source's ONE row, asserted: a source that drew none fails here by name."""
    rows = (out or A.baseline_source())["rows"]
    assert len(rows) == 1, f"the baseline source drew {len(rows)} row(s), not one: {rows}"
    return rows[0]


def _usable_none(monkeypatch):
    value = {"usable": "", "count": 1, "baselines": [
        {"tag": "baseline/20260925T201032Z", "withdrawn": False, "stale": ["s1"]}]}
    monkeypatch.setattr("modules.reader_job.read_cached", lambda name: {
        "state": "ok", "doc": {"last_good": {"value": {"lists": {"Lab": value}},
                                             "value_at": "2026-10-16T00:57:00Z"}}})


class TestAHealDecidesNothingForTheNetwork:
    """(a) and C3167: no earned baseline and no coverage denial, and so no row."""

    def test_a_one_device_heal_commit_raises_no_baseline_row(self, nine):
        """The host's case: the heal returned the device to its golden, so no golden changed,
        and eight devices are outside it. It is denied nothing for them."""
        repo, captured = nine
        _capture(captured)
        got = _batch(captured, source=HEAL, heal=True)
        body = _body(repo, got["commit"])
        assert body.startswith("golden: no configuration changed; measurement recorded "
                               "(1 device(s) measured via heal_to_intent)"), body
        assert "Source: heal_to_intent" in body and "Devices-Measured: r2" in body
        assert "Heal-Decision: r2=hd-0123456789ab" in body
        assert "Intent-Match: yes" in body
        assert "Baseline:" not in body
        assert got["baseline"] is False and got["decided"] is False
        assert got["baseline_reasons"] == [A_HEAL]
        assert not [t for t in got["tags"] if t.startswith("baseline/")]
        out = A.baseline_source()
        assert out["rows"] == []
        assert "no baseline decision recorded yet" in out["checked"]

    def test_a_heal_that_moves_the_golden_decides_nothing_either(self, nine):
        repo, captured = nine
        _capture(captured)
        got = _batch(captured.replace("\nend", ROUTE), source=HEAL, heal=True)
        body = _body(repo, got["commit"])
        assert "Devices: r2" in body and "Source: heal_to_intent" in body
        assert "Baseline:" not in body
        assert A.baseline_source()["rows"] == []

    @pytest.mark.parametrize("moved", [False, True])
    def test_a_heal_reads_no_other_device_for_a_judgement_nobody_makes(
            self, nine, monkeypatch, moved):
        # Counted, never raised: the batch reads the others inside a try that would swallow it.
        asked = []
        monkeypatch.setattr("modules.nsot.startup_source.standing",
                            lambda *a, **k: asked.append(a) or {"head": "", "devices": {}})
        repo, captured = nine
        _capture(captured)
        got = _batch(captured.replace("\nend", ROUTE) if moved else captured, source=HEAL,
                     heal=True)
        assert asked == [], "the devices outside a heal's commit were judged"
        assert "Judged-Outside:" not in _body(repo, got["commit"])

    def test_the_control_a_persons_deploy_of_the_same_batch_still_decides(self, nine):
        """C3167: "only heals exempt." The same batch as a person's deploy is judged with the
        eight outside it (none is shown at intent here), and its commit says so."""
        repo, captured = nine
        _capture(captured)
        got = _batch(captured)
        body = _body(repo, got["commit"])
        assert body.startswith("golden: no configuration changed; decision recorded"), body
        assert "Source: pipeline" in body
        assert "Baseline: denied: 8 device(s) not targeted: ['r1', 'r3', " in body
        r = _the_row()
        assert r["what"] == ("The last commit earned no baseline: a deploy to r2 did not "
                             "cover the network")

    def test_a_heal_never_earns_one_where_a_persons_deploy_does(self, nine, monkeypatch):
        """An inventory of r2 alone: the batch covers it, every capture equals its golden and
        is at its intent, so a person's deploy earns one though nothing changed (C2105, the
        operator's (c)); the same batch as a heal earns none."""
        monkeypatch.setattr("modules.nsot.restore._devices_of",
                            lambda list_name: [{"hostname": "r2"}])
        repo, captured = nine
        _capture(captured)
        healed = _batch(captured, source=HEAL, heal=True)
        assert "Baseline:" not in _body(repo, healed["commit"])
        assert not [t for t in healed["tags"] if t.startswith("baseline/")]
        assert healed["baseline"] is False
        deployed = _batch(captured)
        body = _body(repo, deployed["commit"])
        assert body.startswith("golden: no configuration changed; decision recorded"), body
        assert "Baseline: earned" in body and deployed["baseline"] is True
        assert [t for t in deployed["tags"] if t.startswith("baseline/")], deployed

    @pytest.mark.parametrize("source, decides", [
        ("heal_to_intent", False), ("pipeline", True), ("restore", True), ("save_all", True),
        ("golden_state", True), ("capture", True),
    ])
    def test_the_rule(self, source, decides):
        assert R.decides_for_network(source) is decides


class TestAHealThatCutThePathRecordsIt:
    """C3167: "a management-path cut by a heal still records its C2270 denial: safety
    records are never skipped." By the save, and by the reader."""

    @pytest.mark.parametrize("moved", [False, True])
    def test_a_heal_that_cut_mercurys_path_records_the_denial_and_the_row_is_drawn(
            self, nine, moved):
        repo, captured = nine
        _capture(captured)
        got = _batch(captured.replace("\nend", ROUTE) if moved else captured, source=HEAL,
                     heal=True, reach_lost={"state": "known", "cut": ["s3"], "why": "x"})
        body = _body(repo, got["commit"])
        assert "Source: heal_to_intent" in body
        assert f"Baseline: denied: {CUT}" in body
        # The cut, and nothing else: no coverage denial rides with it.
        assert "not targeted" not in body and "not every inventory device" not in body
        assert got["baseline"] is False and got["decided"] is True
        assert got["baseline_reasons"] == [CUT] and got["baseline_denied"] == [CUT]
        r = _the_row()
        assert r["what"] == "The network's last baseline was not earned (heal_to_intent)"
        assert CUT in r["cause"] and f"decided by commit {got['commit'][:10]}" in r["cause"]
        assert r["action"]["label"].startswith(CUT_REMEDY)
        assert "Resolve each departure" not in r["action"]["label"]

    def test_a_cut_that_could_not_be_computed_is_recorded_too(self, nine):
        repo, captured = nine
        _capture(captured)
        got = _batch(captured, source=HEAL, heal=True,
                     reach_lost={"state": "unknown", "cut": [], "why": "no committed intent"})
        assert ("Baseline: denied: whether r2's program cut Mercury's path to a device is not "
                "known (no committed intent)") in _body(repo, got["commit"])
        assert len(A.baseline_source()["rows"]) == 1

    def test_the_save_keeps_only_the_safety_record_of_what_a_heals_caller_passes(self, nine):
        """The save is the rule's owner: a heal's caller that passed a coverage reason
        beside the cut has the cut recorded and the coverage reason left out."""
        repo, captured = nine
        _capture(captured)
        out = R.save_golden("Lab", [R.GoldenItem("r2", captured, "203.0.113.12")], source=HEAL,
                            actor="t", allow_new=False, baseline=False,
                            baseline_reasons=["8 device(s) not targeted: ['r1']", CUT])
        body = _body(repo, out["commit"])
        assert f"Baseline: denied: {CUT}\n" in body and "not targeted" not in body
        assert out["baseline_denied"] == [CUT]

    @pytest.mark.parametrize("reason, safety", [
        (CUT, True),
        ("whether r2's program cut Mercury's path to a device is not known (x), so the "
         "network is not shown at its intent: Save All", True),
        (f"denied: 8 device(s) not targeted: ['r1']; {CUT}", True),
        (HOST_REASON, False), ("8 device(s) not targeted: ['r1']", False),
        ("r2 does not match its committed intent (+1 -1)", False), ("", False),
    ])
    def test_what_a_safety_record_is(self, reason, safety):
        assert R.safety_record(reason) is safety


class TestTheRecordAlreadyWritten:
    """(d): the host's denial stands in its history; the source passes over it."""

    def test_the_hosts_heal_denial_is_passed_over_for_the_earned_one_before_it(self, nine):
        repo, captured = nine
        assert _save_all(captured)["baseline"].startswith("baseline/")
        sha = _old_record(repo, HEAL, f"denied: {HOST_REASON}")
        assert HOST_REASON in _body(repo), "the record is as the old save wrote it"
        out = A.baseline_source()
        assert out["rows"] == []
        assert ": earned; 1 newer denial(s) passed over" in out["checked"], out["checked"]
        assert sha[:10] in out["checked"]

    def test_a_real_denial_before_it_is_the_row(self, nine):
        """The decision before it, whatever it was: a Save All denied for a departure."""
        repo, captured = nine
        denied = _save_all(_broken(captured))
        _old_record(repo, HEAL, f"denied: {HOST_REASON}")
        r = _the_row()
        assert r["what"] == "The network's last baseline was not earned (save_all)"
        assert "r2 does not match its committed intent" in r["cause"]
        assert f"decided by commit {denied['commit'][:10]}" in r["cause"]
        assert HOST_REASON not in r["cause"]

    def test_a_heals_recorded_cut_is_never_passed_over(self, nine):
        """C3167: "safety records are never skipped", whatever else the denial says."""
        repo, captured = nine
        assert _save_all(captured)["baseline"].startswith("baseline/")
        sha = _old_record(repo, HEAL, f"denied: 8 device(s) not targeted: ['r1']; {CUT}")
        out = A.baseline_source()
        r = _the_row(out)
        assert CUT in r["cause"] and f"decided by commit {sha[:10]}" in r["cause"]
        assert r["action"]["label"].startswith(CUT_REMEDY)
        assert "passed over" not in out["checked"]

    def test_a_persons_one_device_deploy_denial_is_never_passed_over(self, nine):
        """C3167: "only heals exempt." The same record as a person's deploy is the row it
        always was (C885's)."""
        repo, captured = nine
        assert _save_all(captured)["baseline"].startswith("baseline/")
        _old_record(repo, "pipeline", "denied: 8 device(s) not targeted: ['r1', 'r3']")
        out = A.baseline_source()
        r = _the_row(out)
        assert r["what"].startswith("The last commit earned no baseline: a deploy to r2")
        assert "passed over" not in out["checked"]

    def test_only_passed_over_denials_is_no_decision_and_no_row(self, nine):
        repo, captured = nine
        _capture(captured)
        _old_record(repo, HEAL, f"denied: {HOST_REASON}")
        out = A.baseline_source()
        assert out["rows"] == []
        assert "no baseline decision about the network is recorded" in out["checked"]
        assert "older ones were not read" not in out["checked"]

    def test_a_read_filled_by_passed_over_denials_says_older_ones_were_not_read(
            self, nine, monkeypatch):
        """A read that returns its whole page is cut: it never reads silence as "none"."""
        repo, captured = nine
        _save_all(_broken(captured))
        for _ in range(2):
            _old_record(repo, HEAL, f"denied: {HOST_REASON}")
        monkeypatch.setattr(A, "BASELINE_DECISIONS_READ", 2)
        out = A.baseline_source()
        assert out["rows"] == []
        assert "the read takes the newest 2 decisions, and older ones were not read" in \
            out["checked"]

    @pytest.mark.parametrize("source, decision, networks", [
        # Passed over: a heal's denial with no safety record, whatever it says.
        (HEAL, f"denied: {HOST_REASON}", False),
        (HEAL, "denied: 8 device(s) not targeted: ['r1']", False),
        (HEAL, "denied: r2 does not match its committed intent (+1 -1)", False),
        # Never passed over: a heal's cut, an earned one, and every other workflow's.
        (HEAL, f"denied: {CUT}", True),
        (HEAL, f"denied: 8 device(s) not targeted: ['r1']; {CUT}", True),
        (HEAL, "earned", True),
        ("pipeline", "earned", True),
        ("pipeline", "denied: 8 device(s) not targeted: ['r1']", True),
        ("pipeline", f"denied: {HOST_REASON}", True),
        ("restore", "denied: 1 device(s) did not succeed: ['s3']; 7 device(s) not targeted: "
                    "['r1']", True),
        ("save_all", "denied: not every inventory device was captured (1 of 9)", True),
        ("pipeline", "denied: r2 does not match its committed intent (+1 -1)", True),
    ])
    def test_which_recorded_decisions_are_the_networks(self, source, decision, networks):
        assert R.network_decision(source, decision) is networks

    def test_history_reads_it_the_same_way(self):
        heal = HS.baseline_words(f"denied: {HOST_REASON}", [], HEAL)
        assert heal == {"state": "not_taken", "tag": "",
                        "words": "not taken: a heal decides nothing for the network"}
        cut = HS.baseline_words(f"denied: {CUT}", [], HEAL)
        assert cut["state"] == "denied" and "cut Mercury's path to s3" in cut["words"]
        person = HS.baseline_words("denied: 8 device(s) not targeted: ['r1']", [], "pipeline")
        assert person["words"] == "not taken: 8 not targeted"
        kept = HS.baseline_words("denied: not every inventory device was captured (s3 skipped)",
                                 [], "save_all")
        assert kept["state"] == "denied" and kept["words"] == "denied: s3 skipped"


class TestTheDetailsByTheCorrectedRule:
    """C3400 (the operator, 2026-11-13): "The C3165 decision row's details still say "Baseline
    denied … 1 of an unstated number" under the title "Baseline not taken": draw the details
    by the corrected rule too." History's decision row for the host's record (a heal's commit,
    the recorded shape he read) and every reader of a decision's reasons say the title's cause
    and the count as the save writes it now; the record is not changed."""

    @staticmethod
    def _decision_rows(repo):
        import types
        ctx = {"ref": types.SimpleNamespace(name="Lab", repo_dir=repo), "device": "",
               "limit": 50, "since": None, "until": None, "members": None,
               "inventory": set()}
        return [e for e in HS.decisions(ctx)["events"] if e["kind"] == "decision"]

    def test_the_hosts_record_its_details_say_the_titles_cause_and_no_unstated_number(
            self, nine):
        repo, captured = nine
        assert _save_all(captured)["baseline"].startswith("baseline/")
        sha = _old_record(repo, HEAL, f"denied: {HOST_REASON}")
        assert HOST_REASON in _body(repo), "the record is as the old save wrote it"
        (row,) = [e for e in self._decision_rows(repo) if dict(e["record"])["Commit"] ==
                  sha[:12]]
        title_cause = "not taken: a heal decides nothing for the network"
        assert row["what"] == f"Baseline {title_cause} ({HEAL})", row["what"]
        details = " ".join(str(v) for _k, v in row["record"])
        assert "unstated number" not in details and "unstated" not in row["what"]
        line = dict(row["record"])["Baseline"]
        assert line.startswith(title_cause), line
        assert "1 captured; the save was given no inventory size" in line, line
        assert not line.startswith("denied"), "never the opposite of its title"

    @pytest.mark.parametrize("source, decision, title, line", [
        # Another workflow's old coverage denial is the network's: denied, the count reworded.
        ("pipeline", f"denied: {HOST_REASON}",
         "denied: not every inventory device was captured (1 captured; the save was given no "
         "inven",
         "denied: not every inventory device was captured (1 captured; the save was given no "
         "inventory size)"),
        # The counts a save names now are as written.
        ("save_all", "denied: not every inventory device was captured (1 of 9)",
         "denied: not every inventory device was captured (1 of 9)",
         "denied: not every inventory device was captured (1 of 9)"),
        ("pipeline", "denied: 8 device(s) not targeted: ['r1']", "not taken: 8 not targeted",
         "not taken: 8 not targeted (8 device(s) not targeted: ['r1'])"),
        ("save_all", "earned", "earned", "earned"),
    ])
    def test_every_decisions_details_read_as_its_title(self, source, decision, title, line):
        assert HS.baseline_words(decision, [], source)["words"] == title
        assert HS.baseline_detail(decision, [], source) == line

    def test_needs_attention_says_the_count_as_the_save_writes_it_now(self, nine):
        """A person's deploy recorded before the save stated the inventory's size: its row,
        never passed over (C3167), names the count in today's words."""
        repo, captured = nine
        assert _save_all(captured)["baseline"].startswith("baseline/")
        _old_record(repo, "pipeline", f"denied: {HOST_REASON}")
        r = _the_row()
        assert "unstated" not in r["cause"], r["cause"]
        assert ("not every inventory device was captured (1 captured; the save was given no "
                "inventory size)") in r["cause"]
        assert r["action"]["label"].startswith("Capture the missing devices")

    def test_the_usability_row_says_it_too(self, nine, monkeypatch):
        repo, captured = nine
        assert _save_all(captured)["baseline"].startswith("baseline/")
        _old_record(repo, "pipeline", f"denied: {HOST_REASON}")
        _usable_none(monkeypatch)
        r = _the_row()
        assert r["what"].startswith("No stored baseline can be re-applied")
        assert "unstated" not in r["cause"] and "1 captured; the save was given no " \
            "inventory size" in r["cause"], r["cause"]

    def test_the_words_are_the_record_s_but_for_the_count(self):
        assert R.reason_words(HOST_REASON) == ("not every inventory device was captured (1 "
                                               "captured; the save was given no inventory "
                                               "size)")
        assert R.reason_words("not every inventory device was captured (12 of an unstated "
                              "number); r2 does not match") == (
            "not every inventory device was captured (12 captured; the save was given no "
            "inventory size); r2 does not match")
        for kept in ("not every inventory device was captured (1 of 13)", CUT, ""):
            assert R.reason_words(kept) == kept


class TestTheRowMatchesItsCause:
    """(b): a coverage reason says to capture the missing devices, and names the count."""

    def test_a_save_all_that_read_part_names_the_count(self, nine):
        repo, captured = nine
        out = _save_all(captured, inventory_size=9)
        body = _body(repo, out["commit"])
        assert "Baseline: denied: not every inventory device was captured (1 of 9)" in body
        assert "unstated" not in body
        r = _the_row()
        assert "not every inventory device was captured (1 of 9)" in r["cause"]
        assert r["action"]["label"] == (
            "Capture the missing devices: Save All captures every device in the inventory "
            "and earns a baseline if each is read and at its committed intent")

    def test_a_skipped_device_is_named_in_what_to_do(self, nine):
        _repo, captured = nine
        _save_all(captured, inventory_size=9, skipped=[{"hostname": "s3", "reason": "x"}])
        r = _the_row()
        assert "not every inventory device was captured (s3 skipped)" in r["cause"]
        label = r["action"]["label"]
        assert label.startswith("Capture the missing devices: that save could not read s3 "
                                "(its result says why for each); once each answers, Save All")
        assert "Resolve each departure" not in label and "departure" not in label

    def test_a_denial_for_both_says_both(self, nine):
        _repo, captured = nine
        _save_all(_broken(captured), inventory_size=9,
                  skipped=[{"hostname": "s3", "reason": "x"}])
        r = _the_row()
        assert "s3 skipped" in r["cause"] and "does not match its committed intent" in r["cause"]
        label = r["action"]["label"]
        assert label.startswith("Capture the missing devices: that save could not read s3")
        assert "The reasons also name a departure: resolve each first" in label

    def test_with_no_baseline_usable_the_usability_row_matches_its_cause_too(
            self, nine, monkeypatch):
        _repo, captured = nine
        _save_all(captured, inventory_size=9, skipped=[{"hostname": "s3", "reason": "x"}])
        _usable_none(monkeypatch)
        r = _the_row()
        assert r["what"].startswith("No stored baseline can be re-applied")
        assert r["action"]["label"].startswith("Capture the missing devices: that save could "
                                               "not read s3")
        assert "refused again" not in r["action"]["label"]

    def test_the_control_a_departure_alone_keeps_its_remedy(self, nine):
        _repo, captured = nine
        _save_all(_broken(captured))
        r = _the_row()
        assert r["action"]["label"].startswith("Resolve each departure the reasons name")
        assert "Capture the missing devices" not in r["action"]["label"]

    def test_the_row_says_what_leaves_it_standing_and_what_replaces_it(self, nine):
        _repo, captured = nine
        _save_all(_broken(captured))
        r = _the_row()
        assert ("a capture of one device or a heal since makes no decision about the network "
                "and leaves it standing; the next Save All decides again, even when no "
                "configuration changed") in r["cause"]

    @pytest.mark.parametrize("reasons, want", [
        ("not every inventory device was captured (1 of 13)",
         {"any": True, "only": True, "skipped": [], "detail": "1 of 13"}),
        ("not every inventory device was captured (r2, s3 skipped)",
         {"any": True, "only": True, "skipped": ["r2", "s3"], "detail": "r2, s3 skipped"}),
        ("not every inventory device was captured (s3 skipped); r2 does not match its "
         "committed intent (+1 -1: load-interval 30)",
         {"any": True, "only": False, "skipped": ["s3"], "detail": "s3 skipped"}),
        ("r2 does not match its committed intent (+1 -1)",
         {"any": False, "only": False, "skipped": [], "detail": ""}),
        ("", {"any": False, "only": False, "skipped": [], "detail": ""}),
    ])
    def test_what_the_reasons_say_about_coverage(self, reasons, want):
        assert R.uncaptured(reasons) == want


class TestAFullCaptureEarnsEvenIfNothingChanged:
    """(c), and how a standing row clears: the next full capture with no departures."""

    def test_a_save_all_that_changes_nothing_earns_one_and_clears_the_row(self, nine):
        repo, captured = nine
        _save_all(captured, inventory_size=9)                 # denied: 1 of 9
        assert len(A.baseline_source()["rows"]) == 1
        again = _save_all(captured)                           # every device, nothing changed
        assert again["changed"] == [] and again["decision_only"], again
        assert again["baseline"].startswith("baseline/")
        assert "Baseline: earned" in _body(repo, again["commit"])
        assert A.baseline_source()["rows"] == []

    def test_a_departure_is_the_reason_it_does_not(self, nine):
        _repo, captured = nine
        _capture(_broken(captured))
        again = _save_all(_broken(captured))
        assert again["changed"] == [] and not again["baseline"]
        assert any("r2 does not match its committed intent" in why
                   for why in again["baseline_denied"])
