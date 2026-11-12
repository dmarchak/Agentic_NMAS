"""The incident's record for AI troubleshooting, its attempts and its derivations
(modules/fixit/incident.py; board recurring-fixes v2, the fix-it build plan's first slice). No
AI call, no device, nothing drawn.

**On real records.** An attempt is an operation's own run record, so every one here is made by
running the real Re-subscribe (`modules/heal/resubscribe.py`) on tests/test_heal_resubscribe.py's
lab, as tests/test_heal_resubscribe_v2.py does: a lab router's real configuration on a box, its
real intent and receiver captures, the collector's real socket captures. A verify that reads no
data gives a real ``not_back`` record (the operator's run of 2026-11-11), the default a real
pass, a request that is no person's a real refusal. The one edit, said where it is made
(`carry`): the field the operation's confirm will carry into its record (`RUN_FIELD`), written
through the operations' own record writer. The record of AI calls is written by its own writer
(`calls.record`).

The operator's words this holds (2026-11-11): "Never retry on its own"; "Cancel: nothing more
runs, the incident stays open, attempts recorded"; "a proposal that already failed in this
incident is flagged, not silently re-proposed".
"""
import ast
import json
import os
import stat
import subprocess
import sys

import pytest

from modules.fixit import incident as F
# The operation whose runs are the attempts: nothing here can be set up where it is absent.
from modules.heal import resubscribe as R
from tests import test_ai_controls as T
from tests import test_one_home_per_action as OH
from tests.test_heal_resubscribe import (ABSENT, ACTOR, NET, Clock, Src, coll,  # noqa: F401
                                         lab, run, seq, stored)
from tests.test_heal_resubscribe_v2 import card, client, press  # noqa: F401 (the fixture)
from tests.test_sdn_connections import networks  # noqa: F401 (the fixture `lab` builds on)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
#: The lab's clock starts here (tests/test_heal_resubscribe.py's `Clock`).
T0 = 1_794_250_000.0
DETECTED = T0 - 3600
LATER = T0 + 7200
ID = "hi-3f9c1a2b7d40"
CALL_A, CALL_B, CALL_C = "ai-00000000000000aa", "ai-00000000000000bb", "ai-00000000000000cc"


def inc(incident_id=ID, device="r2", device_id="nb:7", detected=DETECTED, network=NET):
    return F.Incident(network, incident_id, device_id, device, detected)


def a_run(at, ok, subs=("101",), **src):
    """A real run of the Re-subscribe started at *at*: one whose verify reads the stream back
    (*ok*), or one that reads no data and ends ``not_back``."""
    source = Src(clock=Clock(at), **(dict(src) if ok else dict(src, series=seq([ABSENT]))))
    rec = run(source, subs=subs)
    assert rec["outcome"] == ("resubscribed" if ok else "not_back"), rec["why"]
    return rec


def carry(rec, link):
    """The one edit to a real run's record: the incident its confirm was pressed in
    (`RUN_FIELD`, the field the operation's confirm will carry), written by the operations'
    own writer."""
    from modules.nsot import privileged
    got = privileged.get(NET, rec["id"])
    got[F.RUN_FIELD] = dict(link)
    privileged.record(NET, got)
    return got


def tree(root):
    """Every file under *root*: its bytes."""
    out = {}
    for folder, _dirs, files in os.walk(root):
        for name in files:
            full = os.path.join(folder, name)
            with open(full, "rb") as fh:
                out[os.path.relpath(full, root)] = fh.read()
    return out


def doc(incident):
    with open(F.path(incident), encoding="utf-8") as fh:
        return json.load(fh)


def torn(incident, text='{"version": 1, "incident": "hi-3f9c1a2b7d40", "lines": [{"prop'):
    """*incident*'s record left as a fragment (or as *text*): its bytes."""
    os.makedirs(os.path.dirname(F.path(incident)), exist_ok=True)
    with open(F.path(incident), "w", encoding="utf-8") as fh:
        fh.write(text)
    return text.encode()


# ── The id and the device ───────────────────────────────────────────────────────────────────

class TestTheIdIsOpaque:
    @pytest.mark.parametrize("text", ["hi-3f9c1a2b7d40", "resp-0a1b2c3d4e", "al-" + "9" * 20,
                                      "al-0f3a9c2b7d4011aa22bb"])
    def test_each_stores_own_id_is_one(self, text):
        assert F.valid_id(text)

    @pytest.mark.parametrize("text", ["", None, 7, "hi-", "hi-XYZ", "HI-3f9c1a2b7d40",
                                      "watch-0a1b2c", "al-", "al-../x", "al-a/b", "al-A",
                                      "hi-3f9c1a2b7d40.json", "../hi-3f9c1a2b7d40",
                                      "al-" + "a" * 65, "incident:uid:1"])
    def test_any_other_shape_is_none_and_names_no_file(self, lab, text):
        assert not F.valid_id(text)
        with pytest.raises(F.Refused, match="is no incident's id"):
            F.path(inc(text))
        with pytest.raises(F.Refused, match="is no incident's id"):
            F.cancel(inc(text), ACTOR, "access")

    def test_the_record_is_keyed_by_the_id_under_its_networks_own_folder(self, lab):
        from modules.config import list_data_path
        assert F.path(inc()) == os.path.join(list_data_path(NET), "fixit", f"{ID}.json")
        other = "al-0f3a9c2b7d4011aa22bb"
        assert F.path(inc(other)) == os.path.join(list_data_path(NET), "fixit", f"{other}.json")

    def test_a_device_is_never_carried_by_its_name_alone(self, lab):
        with pytest.raises(F.Refused, match="by its name alone \\(r2\\)"):
            F.record_proposal(inc(device_id=""), "mercury")
        with pytest.raises(F.Refused, match="is no device identity"):
            F.read(inc(device_id="r2"))
        with pytest.raises(F.Refused, match="without its name"):
            F.read(inc(device=""))
        # An incident that names no device carries neither, and has a record all the same.
        nobody = inc("al-0f3a9c2b7d4011aa22bb", device="", device_id="")
        F.record_proposal(nobody, "mercury")
        assert doc(nobody)["device"] == {"id": "", "name": ""}
        assert F.attempts(nobody, now=LATER)["attempts"] == []
        # A device no NetBox holds is carried by its local identity.
        local = inc("hi-000000000001", device_id="uid:0b9c-11")
        F.record_proposal(local, "mercury")
        assert doc(local)["device"] == {"id": "uid:0b9c-11", "name": "r2"}

    @pytest.mark.parametrize("bad", [0, -1.0, None, "1794250000", True])
    def test_an_incident_with_no_detected_time_is_refused(self, lab, bad):
        with pytest.raises(F.Refused, match="no detected time"):
            F.attempts(inc(detected=bad))


# ── The store ───────────────────────────────────────────────────────────────────────────────

CHILD = '''
import sys
sys.path.insert(0, {root!r})
from modules.fixit import incident as F
sub, n = sys.argv[1], int(sys.argv[2])
inc = F.Incident("Default", "hi-3f9c1a2b7d40", "nb:7", "r2", 1794246400.0)
for i in range(n):
    F.record_proposal(inc, "mercury", F.RESUBSCRIBE_KEY, {{"subs": [sub]}})
'''


class TestTheStore:
    def test_a_proposal_line_and_the_document_are_exactly_these(self, lab):
        line = F.record_proposal(inc(), "ai", R.KEY, {"subs": ["102", "101"]},
                                 calls=[CALL_A], prompt="fixit_troubleshoot v1", now=T0 + 5.5)
        assert line == {"proposal": "p1", "source": "ai", "calls": [CALL_A],
                        "prompt": "fixit_troubleshoot v1", "operation": R.KEY,
                        "params_hash": F.params_hash(R.KEY, {"subs": ["101", "102"]}),
                        "at": "2026-11-09T18:46:45Z", "epoch": T0 + 5.5}
        assert doc(inc()) == {"version": 1, "incident": ID, "network": NET,
                              "device": {"id": "nb:7", "name": "r2"}, "lines": [line]}
        assert F.read(inc()) == {"state": "ok", "lines": [line], "error": ""}
        second = F.record_proposal(inc(), "mercury", R.READD_KEY, {"sub": 101}, now=T0 + 9)
        assert second["proposal"] == "p2" and second["calls"] == []
        assert [x["proposal"] for x in F.read(inc())["lines"]] == ["p1", "p2"]

    def test_an_answer_that_proposed_nothing_is_a_line_so_its_calls_are_the_incidents(self, lab):
        line = F.record_proposal(inc(), "ai", calls=[CALL_A], prompt="fixit_troubleshoot v1")
        assert (line["operation"], line["params_hash"]) == ("", "")
        with pytest.raises(F.Refused, match="parameters were given with no operation"):
            F.record_proposal(inc(), "ai", "", {"subs": ["101"]}, calls=[CALL_A])

    @pytest.mark.parametrize("kw,why", [
        (dict(source="model"), "comes from one of mercury, ai, person"),
        (dict(source="ai"), "an AI proposal names the call it came from"),
        (dict(source="ai", calls="ai-1"), "calls are a list of ids"),
        (dict(source="ai", calls=["../x"]), "is no AI call's id"),
        (dict(source="person", operation="reload"), "is no catalogue operation"),
        (dict(source="person", operation=R.KEY, params={"sub": "101"}),
         "has no parameter 'sub': its parameters are subs, collector_step"),
        (dict(source="person", operation=R.KEY, params={"subs": "101"}), "subs is a list"),
        (dict(source="person", operation=R.KEY, params={"subs": ["101"],
                                                        "collector_step": "on"}),
         "collector_step is true or false"),
    ])
    def test_a_proposal_that_is_not_one_is_refused_by_name_and_nothing_is_written(self, lab, kw,
                                                                                 why):
        kw = dict(kw)
        with pytest.raises(F.Refused, match=why):
            F.record_proposal(inc(), kw.pop("source"), kw.pop("operation", ""),
                              kw.pop("params", None), **kw)
        assert F.read(inc())["state"] == "absent"

    def test_the_file_is_owner_only_and_replaced_never_truncated(self, lab):
        F.record_proposal(inc(), "mercury")
        first = os.stat(F.path(inc()))
        assert stat.S_IMODE(first.st_mode) == 0o600
        F.record_proposal(inc(), "mercury")
        assert os.stat(F.path(inc())).st_ino != first.st_ino, "a new file, replaced in one step"
        assert not [n for n in os.listdir(os.path.dirname(F.path(inc()))) if ".tmp-" in n]

    def test_a_read_creates_neither_the_folder_nor_the_file(self, lab):
        a_run(T0, ok=False)
        before = tree(str(lab))
        i = inc()
        assert F.read(i) == {"state": "absent", "lines": [], "error": ""}
        assert len(F.attempts(i, now=LATER)["attempts"]) == 1
        assert F.cost_so_far(i)["usd"] == 0.0
        assert F.repeat_of(i, R.KEY, {"subs": ["101"]}, now=LATER)["kind"] == "repeat"
        assert F.state_of(i, None, now=LATER) == "open"
        assert F.how_fixed_source(i, LATER) == ""
        assert F.run_link(i)["incident"] == ID
        assert not os.path.exists(os.path.dirname(F.path(i)))
        assert tree(str(lab)) == before, "a read wrote something"
        # Nor for a network that does not exist: no folder is made for it.
        ghost = inc(network="zz-no-such-network")
        assert F.read(ghost)["state"] == "absent" and F.state_of(ghost, None) == "open"
        assert not os.path.exists(os.path.dirname(os.path.dirname(F.path(ghost))))

    def test_a_write_creates_no_network(self, lab):
        ghost = inc(network="zz-no-such-network")
        with pytest.raises(F.Refused, match="zz-no-such-network is no network"):
            F.cancel(ghost, ACTOR, "access")
        assert not os.path.exists(os.path.dirname(os.path.dirname(F.path(ghost))))

    def test_absent_and_unreadable_are_different_answers(self, lab):
        assert F.read(inc()) == {"state": "absent", "lines": [], "error": ""}
        torn(inc())
        got = F.read(inc())
        assert got["state"] == "unreadable" and got["lines"] == []
        assert got["error"] == (f"{NET}'s troubleshooting record of {ID} cannot be read "
                                "(JSONDecodeError)")

    @pytest.mark.parametrize("write", [
        lambda i: F.record_proposal(i, "mercury"),
        lambda i: F.cancel(i, ACTOR, "access"),
        lambda i: F.record_handover(i, ACTOR, "access", teams=["Network team"]),
        lambda i: F.record_save(i, "dont_save", ACTOR, "access"),
    ], ids=["proposal", "cancel", "handover", "save"])
    def test_an_unreadable_record_refuses_every_write_and_is_kept(self, lab, write):
        from modules.filestore import StoreUnreadable
        before = torn(inc())
        with pytest.raises(StoreUnreadable, match="nothing was written"):
            write(inc())
        with open(F.path(inc()), "rb") as fh:
            assert fh.read() == before, "the damaged record was replaced"
        assert [n for n in os.listdir(os.path.dirname(F.path(inc()))) if ".corrupt-" in n]
        # And what is derived from it says so, never "open" or nothing spent.
        assert F.state_of(inc(), None, now=LATER) == "unreadable"
        assert F.how_fixed_source(inc(), LATER) == "unreadable"
        cost = F.cost_so_far(inc())
        assert (cost["state"], cost["usd"]) == ("unreadable", None)
        assert F.attempts(inc(), now=LATER)["state"] == "incomplete"
        with pytest.raises(F.Refused, match="cannot be read"):
            F.run_link(inc(), "p1")

    @pytest.mark.parametrize("text,why", [
        ('[]', "it holds a JSON list, not a record"),
        ('{"version": 2, "incident": "hi-3f9c1a2b7d40", "lines": []}',
         "it is version 2, and this release reads version 1"),
        ('{"version": 1, "incident": "hi-000000000009", "lines": []}',
         "it names the incident 'hi-000000000009', not hi-3f9c1a2b7d40"),
        ('{"version": 1, "incident": "hi-3f9c1a2b7d40", "lines": [{"note": "x", "epoch": 1}]}',
         "its line 1 is neither a proposal nor a choice"),
        ('{"version": 1, "incident": "hi-3f9c1a2b7d40", "lines": [{"choice": "retry", '
         '"epoch": 1}]}', "its line 1 is a choice this release does not know \\('retry'\\)"),
    ])
    def test_a_document_that_is_not_this_incidents_record_is_unreadable_too(self, lab, text, why):
        from modules.filestore import StoreUnreadable
        torn(inc(), text)
        assert F.read(inc())["state"] == "unreadable"
        with pytest.raises(StoreUnreadable, match=why):
            F.cancel(inc(), ACTOR, "access")
        with open(F.path(inc()), encoding="utf-8") as fh:
            assert fh.read() == text

    def test_every_text_is_masked_at_rest(self, lab):
        from modules import redact
        secret = "Zq-fixit-7731xq-not-in-any-file"
        with redact.transient_secret(secret, "planted"):
            F.record_proposal(inc(), "ai", calls=[CALL_A], prompt=f"fixit v1 {secret}")
            F.record_handover(inc(), ACTOR, "access", teams=[f"Team {secret}"])
        F.record_proposal(inc(), "person", prompt="snmp-server community Wc9-planted-comm RO")
        with open(F.path(inc()), encoding="utf-8") as fh:
            raw = fh.read()
        assert secret not in raw and "Wc9-planted-comm" not in raw
        lines = F.read(inc())["lines"]
        assert lines[0]["prompt"].startswith("fixit v1 ") and lines[0]["prompt"] != "fixit v1 "
        assert lines[1]["teams"][0].startswith("Team ") and lines[1]["by"] == ACTOR
        assert lines[2]["prompt"].startswith("snmp-server community ")
        assert lines[2]["prompt"].endswith(" RO")

    def test_two_processes_appending_at_once_both_land(self, lab, tmp_path):
        script = tmp_path / "child.py"
        script.write_text(CHILD.format(root=ROOT), encoding="utf-8")
        # The children write the same store: this test's own temporary one.
        child_env = dict(os.environ)
        child_env["NMAS_DATA_DIR"] = str(lab)
        procs = [subprocess.Popen([sys.executable, str(script), sub, "30"], env=child_env,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                 for sub in ("101", "102")]
        for p in procs:
            _out, err = p.communicate(timeout=120)
            assert p.returncode == 0, err.decode()[-2000:]
        lines = F.read(inc())["lines"]
        assert len(lines) == 60, len(lines)
        assert [x["proposal"] for x in lines] == [f"p{n}" for n in range(1, 61)]
        by_hash = {}
        for x in lines:
            by_hash[x["params_hash"]] = by_hash.get(x["params_hash"], 0) + 1
        assert by_hash == {F.params_hash(R.KEY, {"subs": ["101"]}): 30,
                           F.params_hash(R.KEY, {"subs": ["102"]}): 30}


# ── The attempts ────────────────────────────────────────────────────────────────────────────

class TestAttemptsAreDerived:
    def test_a_run_a_person_pressed_is_attempt_1_with_no_backfill(self, client):
        """The operator's run of 2026-11-11, as the card's own route records one: the verify
        reads no data, the run ends not_back, and the incident's page reads it as attempt 1
        from the run's own record, with nothing written for it."""
        from modules.nsot import privileged
        from tests.conftest import TEST_PERSON
        client.state["src"] = Src(series=seq([ABSENT]), clock=Clock(T0))
        _r, html = card(client, subs="101")
        assert press(client, html, subs=("101",)).status_code == 200
        (record,) = privileged.runs(NET)["runs"]
        got = F.attempts(inc(), now=LATER)
        assert (got["state"], got["refused"], got["unreadable"], got["truncated"]) == (
            "ok", 0, [], False)
        (a,) = got["attempts"]
        assert a == {"n": 1, "run": record["id"], "operation": R.KEY, "device": "r2",
                     "started_at": T0, "finished_at": record["finished_at"],
                     "at": "2026-11-09T18:46:40Z", "actor": TEST_PERSON,
                     "actor_verified": record["actor_verified"], "outcome": "not_back",
                     "state": "failed", "passed": False, "words": record["why"],
                     "params": {"subs": ["101"], "collector_step": False},
                     "params_hash": F.params_hash(R.KEY, {"subs": ["101"]}), "proposal": "",
                     "source": "", "linked": "window"}
        assert "the stream did not come back within 290 s" in a["words"]
        assert a["actor_verified"] in ("access", "local-account")
        assert F.read(inc())["state"] == "absent", "an attempt is derived, never copied"
        assert F.state_of(inc(), None, now=LATER) == "open"

    def test_in_the_order_they_started_each_from_its_own_record(self, lab):
        second = a_run(T0 + 900, ok=True, subs=("101", "102"))
        first = a_run(T0, ok=False)
        got = F.attempts(inc(), now=LATER)["attempts"]
        assert [(a["n"], a["run"], a["outcome"], a["passed"]) for a in got] == [
            (1, first["id"], "not_back", False), (2, second["id"], "resubscribed", True)]
        assert got[1]["params"] == {"subs": ["101", "102"], "collector_step": False}
        assert [a["words"] for a in got] == [stored(first)["why"], stored(second)["why"]]

    def test_one_before_the_incident_and_one_on_another_device_are_left_out(self, lab):
        before = a_run(DETECTED - 600, ok=False)
        inside = a_run(T0, ok=False)
        mine = F.attempts(inc(), now=LATER)["attempts"]
        assert [a["run"] for a in mine] == [inside["id"]] and before["id"] != inside["id"]
        # The same two real runs, asked for an incident of another device in the same window:
        # neither is its attempt.
        other = inc("hi-0000000000ee", device="edge9", device_id="nb:9")
        assert F.attempts(other, now=LATER) == {
            "state": "ok", "attempts": [], "refused": 0, "unreadable": [], "truncated": False,
            "cut": None, "error": ""}

    def test_one_after_the_resolution_is_left_out(self, lab):
        a_run(T0, ok=False)
        late = a_run(T0 + 3000, ok=True)
        assert len(F.attempts(inc(), T0 + 2000)["attempts"]) == 1
        assert [a["run"] for a in F.attempts(inc(), T0 + 4000)["attempts"]][-1] == late["id"]

    def test_a_refused_run_sent_nothing_and_is_no_attempt(self, lab):
        refused = run(Src(clock=Clock(T0)), subs=("101",), actor_verified="none")
        assert stored(refused)["state"] == "refused"
        got = F.attempts(inc(), now=LATER)
        assert (got["attempts"], got["refused"], got["state"]) == ([], 1, "ok")

    def test_a_record_naming_the_incident_is_honoured_over_the_window(self, lab):
        """A run from before the incident was detected is its attempt when the run's record
        names it; one inside the window that names ANOTHER incident is not."""
        named = a_run(DETECTED - 600, ok=False)
        elsewhere = a_run(T0, ok=False)
        plain = a_run(T0 + 600, ok=False)
        assert [a["run"] for a in F.attempts(inc(), now=LATER)["attempts"]] == [
            elsewhere["id"], plain["id"]]
        carry(named, {"incident": ID, "attempt": 1, "proposal": ""})
        carry(elsewhere, {"incident": "hi-0000000000ee", "attempt": 1, "proposal": ""})
        got = F.attempts(inc(), now=LATER)["attempts"]
        assert [(a["n"], a["run"], a["linked"]) for a in got] == [
            (1, named["id"], "record"), (2, plain["id"], "window")]
        # And for the incident it names, on another device and outside its window too.
        other = inc("hi-0000000000ee", device="edge9", device_id="nb:9", detected=LATER - 5)
        assert [a["run"] for a in F.attempts(other, now=LATER)["attempts"]] == [elsewhere["id"]]

    def test_the_proposal_a_run_names_gives_the_attempt_its_source(self, lab):
        line = F.record_proposal(inc(), "ai", R.KEY, {"subs": ["101"]}, calls=[CALL_A])
        link = F.run_link(inc(), line["proposal"])
        assert link == {"incident": ID, "attempt": 1, "proposal": "p1"}
        carry(a_run(T0, ok=False), link)
        (a,) = F.attempts(inc(), now=LATER)["attempts"]
        assert (a["proposal"], a["source"], a["linked"]) == ("p1", "ai", "record")
        with pytest.raises(F.Refused, match="holds no proposal 'p9'"):
            F.run_link(inc(), "p9")
        # A run naming a proposal this record does not hold has no source, never a guessed one.
        carry(a_run(T0 + 900, ok=True), {"incident": ID, "attempt": 2, "proposal": "p9"})
        assert [(a["proposal"], a["source"]) for a in F.attempts(inc(), now=LATER)["attempts"]] \
            == [("p1", "ai"), ("p9", "")]

    def test_a_run_record_that_cannot_be_read_is_said_never_read_as_no_attempt(self, lab):
        from modules.config import list_data_path
        from modules.nsot import reads
        a_run(T0, ok=False)
        folder = os.path.join(list_data_path(NET), "privileged")
        inside, outside = reads.new_id(T0 + 50), reads.new_id(DETECTED - 86400)
        for name in (inside, outside):
            with open(os.path.join(folder, f"{name}.json"), "w", encoding="utf-8") as fh:
                fh.write('{"id": "' + name + '", "key": "telemetry-resub')
        got = F.attempts(inc(), now=LATER)
        assert got["state"] == "incomplete" and got["unreadable"] == [f"{inside}.json"]
        assert got["error"] == f"1 run record(s) of {NET} could not be read ({inside}.json)"
        assert len(got["attempts"]) == 1, "what was read is still given"
        assert F.repeat_of(inc(), R.KEY, {"subs": ["102"]}, now=LATER)["complete"] is False
        assert F.state_of(inc(), None, now=LATER) == "open", "no cancel: nothing to tell"
        assert F.how_fixed_source(inc(), LATER) == "unreadable"

    def test_more_runs_than_were_read_is_said(self, lab):
        a_run(T0, ok=False)
        a_run(T0 + 900, ok=False)
        got = F.attempts(inc(), now=LATER, limit=1)
        assert got["truncated"] is True and got["state"] == "incomplete"
        assert "more than the 1 newest run records read" in got["error"]
        assert F.attempts(inc(), now=LATER)["truncated"] is False

    def test_a_later_device_of_the_same_name_gives_an_earlier_incident_no_attempt(self, lab):
        """The name passed on: the incident's device was retired and a new device took its
        name (a real repository holding both lives, tests/test_retire_leaves_nothing.py's
        `plant_name_history`). The new device's run is not the old incident's attempt."""
        from modules.config import list_data_path
        from tests.test_retire_leaves_nothing import plant_name_history
        old = a_run(T0, ok=False)
        a_run(T0 + 3000, ok=True)
        assert len(F.attempts(inc(), now=LATER)["attempts"]) == 2
        plant_name_history(os.path.join(list_data_path(NET), "config_repo"),
                           retired=[("r2", int(T0) + 1000)], created=[("r2", int(T0) + 2000)])
        got = F.attempts(inc(), now=LATER)
        assert [a["run"] for a in got["attempts"]] == [old["id"]]
        assert (got["cut"]["why"], got["cut"]["epoch"]) == ("created", int(T0) + 2000)
        # The new device's own incident, detected in its own life, has its run.
        new = inc("hi-0000000000aa", device_id="nb:8", detected=T0 + 2500)
        assert [a["outcome"] for a in F.attempts(new, now=LATER)["attempts"]] == ["resubscribed"]

    @pytest.mark.parametrize("remote", ["192.0.2.6", "2001:db8::6"])
    def test_an_address_in_a_runs_words_is_read_as_recorded_ipv4_and_ipv6(self, lab, remote):
        stale = (remote, 60235, "ESTABLISHED", 5966281)
        rec = a_run(T0, ok=False, collector=seq([coll(stale)]))
        (a,) = F.attempts(inc(), now=LATER)["attempts"]
        assert f"the session from {remote} port 60235, there before the operation" in a["words"]
        assert a["words"] == stored(rec)["why"]
        flag = F.repeat_of(inc(), R.KEY, {"subs": ["101"]}, now=LATER)
        assert flag["kind"] == "repeat"
        assert f"the session from {remote} port 60235" in flag["words"]


# ── A repeated proposal is flagged ──────────────────────────────────────────────────────────

class TestARepeatedProposalIsFlagged:
    def test_identical_parameters_are_a_repeat_naming_the_attempt_and_its_words(self, lab):
        rec = a_run(T0, ok=False, subs=("101", "102"))
        got = F.repeat_of(inc(), R.KEY, {"subs": [102, "101"], "collector_step": False},
                          now=LATER)
        assert got == {"kind": "repeat", "attempt": 1, "run": rec["id"], "outcome": "not_back",
                       "words": stored(rec)["why"],
                       "at": R._iso(stored(rec)["finished_at"]),
                       "params_hash": F.params_hash(R.KEY, {"subs": ["101", "102"]}),
                       "changed": [], "complete": True, "error": ""}
        assert "the stream did not come back" in got["words"]
        (a,) = F.attempts(inc(), now=LATER)["attempts"]
        assert a["params_hash"] == got["params_hash"]

    def test_the_collector_step_turned_on_is_a_variation_naming_it(self, lab):
        rec = a_run(T0, ok=False)
        got = F.repeat_of(inc(), R.KEY, {"subs": ["101"], "collector_step": True}, now=LATER)
        assert (got["kind"], got["attempt"], got["run"]) == ("variation", 1, rec["id"])
        assert got["changed"] == [{"name": "collector_step", "before": False, "after": True}]
        assert got["words"] == stored(rec)["why"]

    def test_one_changed_parameter_is_a_variation_naming_only_it(self, lab):
        a_run(T0, ok=False)
        got = F.repeat_of(inc(), R.KEY, {"subs": ["101", "102"]}, now=LATER)
        assert got["kind"] == "variation"
        assert got["changed"] == [{"name": "subs", "before": ["101"], "after": ["101", "102"]}]

    def test_a_passed_attempt_is_no_repeat(self, lab):
        a_run(T0, ok=True)
        got = F.repeat_of(inc(), R.KEY, {"subs": ["101"]}, now=LATER)
        assert (got["kind"], got["attempt"], got["words"], got["changed"]) == (
            "new", None, "", [])

    def test_a_changed_reason_is_no_variation(self, lab):
        a_run(T0, ok=False)
        one = F.repeat_of(inc(), R.KEY, {"subs": ["101"], "reason": "it stays lost"}, now=LATER)
        two = F.repeat_of(inc(), R.KEY, {"subs": ["101"], "reason": "try once more",
                                         "device": "r2"}, now=LATER)
        assert one["kind"] == two["kind"] == "repeat"
        assert one["params_hash"] == two["params_hash"] == F.params_hash(R.KEY,
                                                                         {"subs": ["101"]})

    def test_the_failure_stays_flagged_after_a_later_pass_and_the_newest_is_named(self, lab):
        a_run(T0, ok=False)
        second = a_run(T0 + 900, ok=False)
        a_run(T0 + 1800, ok=True)
        got = F.repeat_of(inc(), R.KEY, {"subs": ["101"]}, now=LATER)
        assert (got["kind"], got["attempt"], got["run"]) == ("repeat", 2, second["id"])

    def test_another_operation_or_another_incident_is_new(self, lab):
        a_run(T0, ok=False)
        assert F.repeat_of(inc(), R.READD_KEY, {"sub": "101"}, now=LATER)["kind"] == "new"
        other = inc("hi-0000000000ee", device="edge9", device_id="nb:9")
        assert F.repeat_of(other, R.KEY, {"subs": ["101"]}, now=LATER)["kind"] == "new"

    def test_a_real_re_add_is_compared_by_its_own_parameter(self, lab):
        """A run that left the receiver removed, then the real one-step re-add failing its
        verify: proposing that re-add again is a repeat, another subscription's a variation."""
        from tests.test_heal_resubscribe import Box
        box = Box(readd_fails=2)
        left = run(Src(box=box, clock=Clock(T0)), subs=("101",))
        assert left["outcome"] == "removed"
        again = run(Src(box=box, clock=Clock(T0 + 900), series=seq([ABSENT])), subs=("101",),
                    readd=True)
        assert (again["key"], again["outcome"]) == (R.READD_KEY, "not_back")
        got = F.repeat_of(inc(), R.READD_KEY, {"sub": "101"}, now=LATER)
        assert (got["kind"], got["attempt"], got["run"]) == ("repeat", 2, again["id"])
        other = F.repeat_of(inc(), R.READD_KEY, {"sub": "102"}, now=LATER)
        assert other["kind"] == "variation"
        assert other["changed"] == [{"name": "sub", "before": "101", "after": "102"}]

    def test_what_is_no_proposal_is_refused_by_name(self, lab):
        with pytest.raises(F.Refused, match="'bounce' is no catalogue operation"):
            F.repeat_of(inc(), "bounce", {})
        with pytest.raises(F.Refused, match="has no parameter 'command'"):
            F.repeat_of(inc(), R.KEY, {"subs": ["101"], "command": "reload"})


# ── Cancel runs nothing ─────────────────────────────────────────────────────────────────────

def count_starters(monkeypatch):
    """Counters in place of everything that would start something: the AI gateway and its
    adapter, the device hold, the job starter and the notification relay. From here on (a
    real run made before it held the device as it does)."""
    n = {"gateway": 0, "adapter": 0, "hold": 0, "job": 0, "relay": 0}

    def counting(name):
        def call(*_a, **_kw):
            n[name] += 1
            raise AssertionError(f"{name} was called")
        return call
    monkeypatch.setattr("modules.ai.gateway.ask", counting("gateway"))
    monkeypatch.setattr("modules.ai.anthropic_adapter.send", counting("adapter"))
    monkeypatch.setattr("modules.nsot.device_ops.hold", counting("hold"))
    monkeypatch.setattr("modules.nsot.capture_job.start", counting("job"))
    monkeypatch.setattr("modules.notify.delivery.deliver_event", counting("relay"))
    return n


@pytest.fixture
def starters(monkeypatch):
    return count_starters(monkeypatch)


class TestCancelRunsNothing:
    def test_one_line_appended_and_nothing_else_called_or_changed(self, lab, monkeypatch):
        from modules.nsot import device_ops, privileged
        rec = a_run(T0, ok=False)
        F.record_proposal(inc(), "mercury", R.KEY, {"subs": ["101"]}, now=T0 + 400)
        before, runs = tree(str(lab)), privileged.runs(NET)["runs"]
        was = doc(inc())
        n = count_starters(monkeypatch)
        line = F.cancel(inc(), ACTOR, "access", now=T0 + 500)
        assert n =={"gateway": 0, "adapter": 0, "hold": 0, "job": 0, "relay": 0}
        assert line == {"choice": "cancel", "by": ACTOR, "verified": "access",
                        "at": "2026-11-09T18:55:00Z", "epoch": T0 + 500, "attempts": 1,
                        "ai_usd": 0.0}
        now = doc(inc())
        assert now["lines"] == was["lines"] + [line], "exactly one line, appended"
        after = tree(str(lab))
        mine = os.path.relpath(F.path(inc()), str(lab))
        assert {k for k in after if after[k] != before.get(k)} == {mine}
        assert set(after) == set(before), "no file made or removed"
        # The record but for its last line is byte for byte what it was.
        assert json.dumps(dict(now, lines=now["lines"][:-1]), indent=1,
                          sort_keys=True).encode() == before[mine]
        # Nothing ran: the same runs, the device not held, the attempt where it was.
        assert privileged.runs(NET)["runs"] == runs
        assert device_ops.holder(NET, "r2") is None
        assert [a["run"] for a in F.attempts(inc(), now=LATER)["attempts"]] == [rec["id"]]

    def test_the_first_line_of_a_record_can_be_the_cancel(self, lab, starters):
        F.cancel(inc(), ACTOR, "local-account", now=T0 + 500)
        assert [(x["choice"], x["verified"], x["attempts"]) for x in doc(inc())["lines"]] == [
            ("cancel", "local-account", 0)]
        assert sum(starters.values()) == 0

    @pytest.mark.parametrize("actor,how", [(ACTOR, ""), (ACTOR, "none"), (ACTOR, None),
                                           ("", "access"), (None, "access")])
    def test_an_unverified_request_is_refused_naming_what_was_compared(self, lab, actor, how):
        F.record_proposal(inc(), "mercury")
        before = tree(str(lab))
        for write in (lambda: F.cancel(inc(), actor, how),
                      lambda: F.record_handover(inc(), actor, how),
                      lambda: F.record_save(inc(), "dont_save", actor, how)):
            with pytest.raises(F.NotAPerson) as said:
                write()
            assert (f"its actor is {actor or 'none'} and its verification is {how or 'none'}, "
                    'and a verification of "" or "none" is no person\'s') in str(said.value)
        assert tree(str(lab)) == before


# ── Nothing here starts anything ────────────────────────────────────────────────────────────

TOP = "<top level>"
#: What starts something, beside the device-changing sends: the device hold, the two job
#: starters, the session opener, the AI gateway's one call and the notification relay.
STARTERS = (("modules.nsot.device_ops", "hold"), ("modules.nsot.capture_job", "start"),
            ("modules.deploy_job", "start"), ("modules.connection", "open_ssh"),
            T.SEED, ("modules.notify.delivery", "deliver_event"))
_FUNCS = (ast.FunctionDef, ast.AsyncFunctionDef)
_DEFS = _FUNCS + (ast.ClassDef,)


def module_names(sources: dict) -> set:
    """The dotted name of every module in *sources*, and of each package holding one."""
    mods = {T._dotted(rel) for rel in sources}
    return mods | {m.rsplit(".", 1)[0] for m in mods if "." in m}


def references(sources: dict, modules: set = None) -> dict:
    """``{(module, top-level definition or TOP): the (module, name) pairs it names}`` over
    *sources*, by tests/test_ai_controls.py's own reference reader; a class is one
    definition, its methods' references its own. *modules*: the names an import may resolve
    to, when *sources* is a part of the program."""
    trees = {T._dotted(rel): ast.parse(text) for rel, text in sources.items()}
    modules = module_names(sources) if modules is None else modules
    out = {}
    for mod, parsed in trees.items():
        defs = [n for n in parsed.body if isinstance(n, _DEFS)]
        local = {n.name for n in defs}
        imports = T._imports([n for n in parsed.body
                              if isinstance(n, (ast.Import, ast.ImportFrom))], modules)
        for n in defs:
            out[(mod, n.name)] = T._refs(n, mod, imports, local, modules)
        rest = [n for n in parsed.body
                if not isinstance(n, _DEFS + (ast.Import, ast.ImportFrom))]
        out[(mod, TOP)] = T._refs(ast.Module(body=rest, type_ignores=[]), mod, imports, local,
                                  modules)
    return out


def effect_homes(sources: dict) -> set:
    """Every home of a device effect, by tests/test_one_home_per_action.py's own definition
    (`implementations`: each function sending a command the read-only allowlist refuses), as
    the top-level definition that holds it. A host script's is not in *sources*."""
    out = set()
    for homes in OH.implementations().values():
        for home in homes:
            rel, name = home.rsplit(":", 1)
            if rel not in sources:
                continue
            for node in ast.parse(sources[rel]).body:
                if isinstance(node, _DEFS) and any(
                        isinstance(n, _FUNCS) and n.name == name for n in ast.walk(node)):
                    out.add((T._dotted(rel), node.name))
    return out


def starting(refs: dict, seeds: set) -> set:
    """Every definition in *refs* (`references`) that reaches one of *seeds* through any
    chain of references."""
    reached, grew = set(seeds), True
    while grew:
        grew = False
        for key, named in refs.items():
            if key not in reached and named & reached:
                reached.add(key)
                grew = True
    return reached


_PROGRAM = {}


def program() -> dict:
    """The program as git tracks it, read once a process (each scan of it takes seconds): its
    sources, each definition's references, the device effects' homes, and the seeds (those
    homes and `STARTERS`)."""
    if not _PROGRAM:
        sources = T._sources()
        homes = effect_homes(sources)
        _PROGRAM.update(sources=sources, refs=references(sources), homes=homes,
                        seeds=homes | set(STARTERS))
    return _PROGRAM


RELAY = ("modules.notify.delivery", "deliver_event")
#: The one way from modules/fixit/ to the relay (the fix-it plan's S3: "the relay is called
#: only by the send function"): the hand-over's send, and the hand-over through it.
RELAY_CALLERS = [("modules.fixit.handover", "hand_over"), ("modules.fixit.handover", "send")]


def fixit_starters(planted: str = "", without=()) -> list:
    """The definitions of modules/fixit/ that reach something that starts something; with
    *planted*, a module's text, as if modules/fixit/planted.py held it; *without*, seeds left
    out (the relay, to ask what reaches anything else)."""
    got = program()
    refs = dict(got["refs"])
    if planted:
        one = {"modules/fixit/planted.py": planted}
        refs.update(references(one, module_names(dict(got["sources"], **one))))
    reached = starting(refs, got["seeds"] - set(without))
    return sorted(k for k in reached if k[0].startswith("modules.fixit"))


PLANTED = {
    "the operation's start": ("from modules.heal import resubscribe\n\n"
                              "def retry(i):\n"
                              "    return resubscribe.start(i.network, i.device, [])\n"),
    "the operation's apply": ("def retry(i):\n"
                              "    from modules.heal.resubscribe import apply\n"
                              "    return apply(i.network, i.device, [])\n"),
    "a device hold": ("from modules.nsot import device_ops\n\n"
                      "def retry(i):\n"
                      "    with device_ops.hold(i.network, i.device, 'x', 'y'):\n"
                      "        pass\n"),
    "the job starter": ("from modules.nsot import capture_job\n\n"
                        "def retry(i):\n"
                        "    return capture_job.start(i.network, 'x', 'y', None)\n"),
    "a session": ("from modules import connection\n\n"
                  "def retry(i):\n    return connection.open_ssh({})\n"),
    "the gateway": ("def retry(i):\n    from modules.ai import gateway\n"
                    "    return gateway.ask('x', (), None, {})\n"),
    "the relay": ("from modules.notify.delivery import deliver_event\n\n"
                  "def retry(i):\n    return deliver_event({}, [])\n"),
    "through its own helper": ("from modules.heal import resubscribe\n\n"
                               "def _go(i):\n"
                               "    return resubscribe.start(i.network, i.device, [])\n\n"
                               "def retry(i):\n    return _go(i)\n"),
}


class TestNothingHereStartsAnything:
    """The operator's "no path retries without a person", as far as this slice goes: no
    function of modules/fixit/ reaches an operation's apply, a device hold, a job start, a
    session or the AI gateway, so nothing recorded here can start anything; the relay is
    reached by the hand-over's send alone (`RELAY_CALLERS`), a person's press."""

    def test_the_scans_population_and_seeds_are_there(self):
        sources, refs = program()["sources"], program()["refs"]
        mine = [rel for rel in sources if rel.startswith("modules/fixit/")]
        assert "modules/fixit/incident.py" in mine and len(sources) >= 400
        homes = program()["homes"]
        assert len(homes) >= 8, sorted(homes)
        assert {("modules.device_reload", "reload_device"), ("modules.heal.bounce", "Session"),
                ("modules.nsot.privileged", "apply")} <= homes
        assert all(s in refs for s in STARTERS), [s for s in STARTERS if s not in refs]
        assert len([k for k in refs if k[0] == "modules.fixit.incident"]) >= 20
        reached = starting(refs, program()["seeds"])
        # The operation the attempts are runs of starts something; reading its records does
        # not, nor does the record of AI calls' read.
        assert {("modules.heal.resubscribe", "apply"), ("modules.heal.resubscribe", "start"),
                ("modules.nsot.privileged", "apply")} <= reached
        assert ("modules.nsot.privileged", "runs") not in reached
        assert ("modules.ai.calls", "rows_since") not in reached

    def test_no_function_of_the_package_starts_anything(self):
        # The relay is reached by the hand-over's send alone (and the hand-over through it),
        # and with the relay left out of the seeds nothing of the package reaches anything.
        assert fixit_starters() == RELAY_CALLERS
        assert fixit_starters(without=[RELAY]) == []

    @pytest.mark.parametrize("how", sorted(PLANTED))
    def test_a_planted_starter_is_found(self, how):
        assert ("modules.fixit.planted", "retry") in fixit_starters(PLANTED[how])

    def test_a_planted_reader_is_not(self):
        # A planted reader adds nothing to what the package reaches (the hand-over's send).
        assert fixit_starters("from modules.nsot import privileged\n\n"
                              "def tried(i):\n    return privileged.runs(i.network)\n") == \
            RELAY_CALLERS


# ── Hand over and the save choice: the line only ────────────────────────────────────────────

class TestTheOtherChoices:
    def test_each_hand_over_is_a_new_version_never_overwritten(self, lab, starters):
        F.record_proposal(inc(), "mercury")
        one = F.record_handover(inc(), ACTOR, "access", teams=["Network team"], now=T0 + 400)
        two = F.record_handover(inc(), ACTOR, "access", now=T0 + 800)
        assert one == {"choice": "handover", "version": 1, "teams": ["Network team"],
                       "by": ACTOR, "verified": "access", "at": "2026-11-09T18:53:20Z",
                       "epoch": T0 + 400, "attempts": 0, "ai_usd": 0.0}
        assert (two["version"], two["teams"]) == (2, [])
        assert [x.get("version") for x in F.read(inc())["lines"]] == [None, 1, 2]
        assert sum(starters.values()) == 0, "the line only: nothing is sent"
        with pytest.raises(F.Refused, match="a list of names"):
            F.record_handover(inc(), ACTOR, "access", teams="Network team")

    @pytest.mark.parametrize("choice", F.SAVE_CHOICES)
    def test_the_save_choice_is_recorded_and_changes_nothing_else(self, lab, starters, choice):
        F.record_proposal(inc(), "mercury")
        before = tree(str(lab))
        line = F.record_save(inc(), choice, ACTOR, "access", now=T0 + 400)
        assert line == {"choice": "save", "saved": choice, "by": ACTOR, "verified": "access",
                        "at": "2026-11-09T18:53:20Z", "epoch": T0 + 400, "attempts": 0,
                        "ai_usd": 0.0}
        after = tree(str(lab))
        mine = os.path.relpath(F.path(inc()), str(lab))
        assert {k for k in after if after[k] != before.get(k)} == {mine}
        assert sum(starters.values()) == 0

    def test_a_save_choice_that_is_not_one_is_refused(self, lab):
        assert F.SAVE_CHOICES == ("apply_alone", "propose", "dont_save")
        with pytest.raises(F.Refused, match="one of apply_alone, propose, dont_save"):
            F.record_save(inc(), "always", ACTOR, "access")
        assert F.read(inc())["state"] == "absent"


# ── The cost ────────────────────────────────────────────────────────────────────────────────

def a_call(call_id, usd, **more):
    """One row in the record of AI calls, by its own writer."""
    from modules.ai import calls
    row = calls.record(dict({"id": call_id, "feature": "fixit_troubleshoot", "verdict": "ok",
                             "cost_usd": usd}, **more))
    assert row["recorded"]
    return row


class TestTheCost:
    def test_only_this_incidents_calls_are_summed_each_once(self, lab):
        from modules.ai import calls
        joined = "ai-00000000000000dd"
        a_call(CALL_A, 0.05)
        a_call(CALL_B, 0.07)
        a_call(CALL_C, 0.50)                              # another incident's
        a_call(joined, 0, verdict=calls.JOINED, joined=CALL_A)
        F.record_proposal(inc(), "ai", R.KEY, {"subs": ["101"]}, calls=[CALL_A])
        F.record_proposal(inc(), "ai", calls=[CALL_B, CALL_A, joined])
        F.record_proposal(inc("hi-0000000000ee"), "ai", calls=[CALL_C])
        got = F.cost_so_far(inc())
        assert got == {"state": "ok", "usd": pytest.approx(0.12), "calls": 2, "missing": [],
                       "error": ""}
        assert F.cost_so_far(inc("hi-0000000000ee"))["usd"] == pytest.approx(0.50)
        # Summed each time: a call recorded afterwards is in the next sum.
        a_call("ai-00000000000000ee", 0.25)
        F.record_proposal(inc(), "ai", calls=["ai-00000000000000ee"])
        assert F.cost_so_far(inc())["usd"] == pytest.approx(0.37)
        assert F.cancel(inc(), ACTOR, "access")["ai_usd"] == pytest.approx(0.37)

    def test_no_call_named_is_nothing_spent_with_nothing_read(self, lab, monkeypatch):
        from modules.ai import calls
        asked = []
        monkeypatch.setattr(calls, "rows_since", lambda start: asked.append(start) or {
            "state": "unreadable", "rows": [], "error": "planted"})
        F.record_proposal(inc(), "mercury", R.KEY, {"subs": ["101"]})
        assert F.cost_so_far(inc()) == {"state": "ok", "usd": 0.0, "calls": 0, "missing": [],
                                       "error": ""}
        assert F.cost_so_far(inc("hi-0000000000ee"))["usd"] == 0.0 and asked == []

    def test_the_record_of_calls_is_read_from_the_incidents_start_never_whole(self, lab,
                                                                             monkeypatch):
        import datetime
        from modules.ai import calls
        real, asked = calls.rows_since, []
        monkeypatch.setattr(calls, "rows_since",
                            lambda start: asked.append(start) or real(start))
        monkeypatch.setattr(calls, "read", lambda: pytest.fail("the whole record was read"))
        a_call(CALL_A, 0.05)
        F.record_proposal(inc(), "ai", calls=[CALL_A])
        assert F.cost_so_far(inc())["usd"] == pytest.approx(0.05)
        assert asked == [datetime.datetime.fromtimestamp(DETECTED, datetime.timezone.utc)]

    def test_an_unreadable_record_of_calls_is_said_never_guessed(self, lab):
        from modules.ai import calls
        F.record_proposal(inc(), "ai", calls=[CALL_A])
        os.makedirs(calls._path())          # a folder where the file should be: unreadable
        got = F.cost_so_far(inc())
        assert (got["state"], got["usd"], got["calls"]) == ("unreadable", None, 0)
        assert got["error"].startswith("the record of AI calls could not be read "
                                       "(IsADirectoryError: ")
        assert got["error"].endswith(f"so what {ID}'s 1 call(s) cost is not known")
        line = F.cancel(inc(), ACTOR, "access")
        assert line["ai_usd"] is None and line["ai_unread"] == got["error"]

    def test_a_call_the_record_does_not_hold_is_named_and_the_rest_summed(self, lab):
        a_call(CALL_A, 0.05)
        F.record_proposal(inc(), "ai", calls=[CALL_A, CALL_B])
        got = F.cost_so_far(inc())
        assert (got["state"], got["usd"], got["missing"]) == (
            "partial", pytest.approx(0.05), [CALL_B])
        assert got["error"] == (f"the record of AI calls holds no row for 1 of the 2 call(s) "
                                f"{ID} names ({CALL_B}): the sum is of the rest")


# ── What the incidents list derives ─────────────────────────────────────────────────────────

class TestCancelledIsDerived:
    def test_it_holds_while_nothing_is_pressed_or_run_after_the_cancel(self, lab):
        a_run(T0, ok=False)
        assert F.state_of(inc(), None, now=LATER) == "open"
        F.cancel(inc(), ACTOR, "access", now=T0 + 500)
        assert F.state_of(inc(), None, now=LATER) == "cancelled"
        assert F.state_of(inc(), None, now=LATER + 86400) == "cancelled", "it stays"
        assert len(F.attempts(inc(), now=LATER)["attempts"]) == 1, "the attempt stays recorded"

    def test_a_later_proposal_ends_it(self, lab):
        F.cancel(inc(), ACTOR, "access", now=T0 + 500)
        assert F.state_of(inc(), None, now=LATER) == "cancelled"
        F.record_proposal(inc(), "mercury", R.KEY, {"subs": ["101"]}, now=T0 + 600)
        assert F.state_of(inc(), None, now=LATER) == "open"

    def test_a_later_run_ends_it_and_a_refused_one_does_not(self, lab):
        a_run(T0, ok=False)
        F.cancel(inc(), ACTOR, "access", now=T0 + 500)
        run(Src(clock=Clock(T0 + 600)), subs=("101",), actor_verified="none")   # refused
        assert F.state_of(inc(), None, now=LATER) == "cancelled"
        a_run(T0 + 700, ok=False)
        assert F.state_of(inc(), None, now=LATER) == "open"

    def test_a_later_hand_over_ends_it_and_a_second_cancel_brings_it_back(self, lab):
        F.cancel(inc(), ACTOR, "access", now=T0 + 500)
        F.record_handover(inc(), ACTOR, "access", now=T0 + 600)
        assert F.state_of(inc(), None, now=LATER) == "open"
        F.cancel(inc(), ACTOR, "access", now=T0 + 700)
        assert F.state_of(inc(), None, now=LATER) == "cancelled"

    def test_it_is_resolved_once_the_alert_clears_and_the_cancel_stays(self, lab):
        a_run(T0, ok=False)
        F.cancel(inc(), ACTOR, "access", now=T0 + 500)
        assert F.state_of(inc(), T0 + 5000) == "resolved"
        assert [x["choice"] for x in F.read(inc())["lines"]] == ["cancel"]
        assert F.how_fixed_source(inc(), T0 + 5000) == "", "cleared; no fix is claimed"

    def test_a_run_that_cannot_be_read_after_the_cancel_is_not_read_as_cancelled(self, lab):
        from modules.config import list_data_path
        from modules.nsot import reads
        a_run(T0, ok=False)
        F.cancel(inc(), ACTOR, "access", now=T0 + 500)
        name = reads.new_id(T0 + 600) + ".json"
        with open(os.path.join(list_data_path(NET), "privileged", name), "w",
                  encoding="utf-8") as fh:
            fh.write("{torn")
        assert F.state_of(inc(), None, now=LATER) == "unreadable"

    def test_neither_word_is_ever_stored(self, lab):
        line = F.record_proposal(inc(), "ai", R.KEY, {"subs": ["101"]}, calls=[CALL_A])
        carry(a_run(T0, ok=True), F.run_link(inc(), line["proposal"]))
        F.cancel(inc(), ACTOR, "access", now=T0 + 500)
        assert F.state_of(inc(), None, now=LATER) == "cancelled"
        assert F.how_fixed_source(inc(), T0 + 5000) == "ai"
        for name, raw in tree(str(lab)).items():
            low = raw.lower()
            assert b"cancelled" not in low and b"assisted" not in low, name


class TestHowFixedIsDerived:
    def fixed_by(self, source, **proposal):
        line = F.record_proposal(inc(), source, R.KEY, {"subs": ["101"]}, **proposal)
        link = F.run_link(inc(), line["proposal"])
        return carry(a_run(T0 + 100 * link["attempt"], ok=True), link)

    def test_ai_only_when_the_passing_run_names_an_ai_proposal(self, lab):
        self.fixed_by("ai", calls=[CALL_A])
        assert F.how_fixed_source(inc(), T0 + 5000) == "ai"
        assert F.how_fixed_source(inc(), None) == "", "not resolved: nothing is fixed yet"
        assert F.state_of(inc(), T0 + 5000) == "resolved"

    def test_a_pass_mercury_proposed_is_not_ai(self, lab):
        F.record_proposal(inc(), "ai", calls=[CALL_A])    # an AI answer was given, and not run
        self.fixed_by("mercury")
        assert F.how_fixed_source(inc(), T0 + 5000) == "mercury"

    def test_a_pass_a_person_chose_or_one_naming_no_proposal_is_not_ai(self, lab):
        F.record_proposal(inc(), "ai", R.KEY, {"subs": ["101"]}, calls=[CALL_A])
        a_run(T0 + 100, ok=True)                          # the same fix, from the card
        assert F.how_fixed_source(inc(), T0 + 5000) == ""
        self.fixed_by("person")
        assert F.how_fixed_source(inc(), T0 + 5000) == "person"

    def test_a_pass_followed_by_a_later_failing_attempt_is_not_fixed(self, lab):
        self.fixed_by("ai", calls=[CALL_A])
        assert F.how_fixed_source(inc(), T0 + 5000) == "ai"
        a_run(T0 + 2000, ok=False)
        assert F.how_fixed_source(inc(), T0 + 5000) == ""
        # Resolved before that failing attempt began, the pass is still the last one before it.
        assert F.how_fixed_source(inc(), T0 + 1500) == "ai"

    def test_only_the_last_attempts_own_proposal_counts(self, lab):
        """An AI-proposed pass, then a later pass a person ran from the card with no proposal:
        the fix that resolved it is the last one, and it names no AI proposal."""
        self.fixed_by("ai", calls=[CALL_A])
        a_run(T0 + 900, ok=True)
        assert [a["source"] for a in F.attempts(inc(), T0 + 5000)["attempts"]] == ["ai", ""]
        assert F.how_fixed_source(inc(), T0 + 5000) == ""
        assert F.how_fixed_source(inc(), T0 + 500) == "ai", "resolved before the second ran"

    def test_a_failed_ai_attempt_and_no_attempt_are_not_fixed(self, lab):
        assert F.how_fixed_source(inc(), T0 + 5000) == ""
        line = F.record_proposal(inc(), "ai", R.KEY, {"subs": ["101"]}, calls=[CALL_A])
        carry(a_run(T0, ok=False), F.run_link(inc(), line["proposal"]))
        assert F.how_fixed_source(inc(), T0 + 5000) == ""

    def test_a_run_naming_a_proposal_the_record_does_not_hold_is_not_ai(self, lab):
        carry(a_run(T0, ok=True), {"incident": ID, "attempt": 1, "proposal": "p7"})
        assert F.how_fixed_source(inc(), T0 + 5000) == ""
