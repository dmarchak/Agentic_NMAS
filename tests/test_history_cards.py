"""History's rows open their run's card, and a heal reads as one finished run by Mercury (the
operator, testing 10473eaf on the NMAS host, 2026-11-12: "Stepper test blocked: r3 › History
shows the smoke heal (hd-f97d66b518b8) only as records; no row opens its card, so a finished
heal's stepper can't be reopened."):

1. "Every operation row in History (device and fleet) has "Open the card", which opens that
   run's card with the five-stage stepper. Same pattern for every operation." (C3172)
2. "The self-healing row's details still say "14. apply: running" for a heal that finished and
   verified. A finished record never shows a step as running; fix it and add a test." (C3173)
3. "One attribution for one heal: the receipt, self-healing and measured rows all read
   "Mercury's self-healing · policy set by <the operator's display name>". Not "heal to
   intent", and not "<the operator's display name> (by the policy they confirmed)"." (C3174)
4. "Step lines use display names. An email appears only under "The identity as recorded"."
   (C3175)

Through the real app over the heal's lab (tests/test_run_outcomes.py's `heal`: the real
decision and the real act over tests/test_heal_act.py's fakes, the step log the act's own
writes) and the re-subscribe's (`resub`: r2's real configuration on a box, its real intent).
Mercury restarting is its jobs forgotten (`restarted`). No device, no network.
"""
import json
import os
import re
from html import unescape

import pytest

from tests.conftest import TEST_PERSON
from tests.test_heal_act import SETTER
from tests.test_heal_decide import GOLDEN, ROUTE4, Fake, settle
from tests.test_heal_decide import lab as heal_lab  # noqa: F401
from tests.test_heal_resubscribe import NET
from tests.test_heal_resubscribe import lab as resub_lab  # noqa: F401
from tests.test_heal_stages import card_of
from tests.test_heal_policy import T0
from tests.test_in_flight import no_hold_survives_a_test  # noqa: F401 (autouse)
from tests.test_run_outcomes import (heal, heal_one, not_back, restarted, resub,  # noqa: F401
                                     run_one, stage_states)
from tests.test_sdn_connections import networks  # noqa: F401 (the labs build on it)

FIVE = ("detected", "decided", "fixing", "checking", "done")
NAME = SETTER.split("@")[0]                           # the setter's display name, none set
MERCURY = f"Mercury's self-healing · policy set by {NAME}"
FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "heal_run", "rolled_back.json")


def rows(html, kind):
    """Each History row of *kind* in *html*: its whole ``<details>``, as drawn."""
    return re.findall(rf'<details class="hist-row tl-row"[^>]*data-kind="{kind}".*?'
                      r'</div>\s*</details>', html, re.S)


def who(row):
    return unescape(re.search(r'<span class="hist-who">(.*?)</span>', row, re.S).group(1))


def card_href(row):
    m = re.search(r'<a class="btn btn-small" href="([^"]+)"[^>]*>Open the card</a>', row)
    return unescape(m.group(1)) if m else None


def device_history(c, device="edge-b", network="Default"):
    r = c.get(f"/v2/device/{device}/history?list={network}")
    assert r.status_code == 200
    return r.get_data(as_text=True)


def fleet_history(c, network="Default"):
    r = c.get(f"/v2/history?list={network}&since=")
    assert r.status_code == 200
    return r.get_data(as_text=True)


def off_record(html):
    """*html* with every "The identity as recorded" taken out: what is left is what a person
    reads without opening a person's record."""
    return re.sub(r'<details class="id-record[^"]*"[^>]*>.*?</details>', "", html, flags=re.S)


def incident_of(decision):
    return decision["incident"]


def forget(c, monkeypatch):
    """Mercury restarted (`restarted`) after its jobs ended: none is held, so the lab has none
    left to wait for."""
    restarted(monkeypatch)
    c.state["jobs"].clear()


def opened(c, href):
    """What the device page *href* opens: ``(its card's section class, the tab body)``."""
    body = c.get(href).get_data(as_text=True)
    body = body[body.index('id="tab-body"'):]
    head = re.search(r'<section class="([^"]+)" id="device-op"', body)
    return (head.group(1) if head else ""), body


class TestOpenTheCard:
    def test_a_finished_heal_s_row_opens_its_five_stage_card_after_a_restart(self, heal,
                                                                            monkeypatch):
        _job, _src, d = heal_one(heal)
        forget(heal, monkeypatch)                     # the job, and its card, are gone
        want = f"/v2/device/edge-b?list=Default&result={incident_of(d)}"
        for html in (device_history(heal), fleet_history(heal)):
            (row,) = rows(html, "heal")
            assert card_href(row) == want, row
        cls, body = opened(heal, want)
        card = card_of(body)
        assert cls == "op-card op-ok" and "Self-healing on edge-b" in card, cls
        # The card is the record's: the outcome its step log keeps, which no job holds now.
        from modules.heal import steplog
        from modules.nsot import capture_job
        entry = steplog.incident("Default", incident_of(d))
        assert entry["outcome"] == "healed" and capture_job.card_jobs() == []
        assert f'data-outcome="{entry["outcome"]}"' in card
        assert list(stage_states(card)) == list(FIVE)
        assert set(stage_states(card).values()) == {"done"}, stage_states(card)
        assert unescape(f"By {MERCURY}") in unescape(card)
        assert SETTER not in card, "no identity on the card"

    def test_a_decision_s_id_opens_the_same_card(self, heal, monkeypatch):
        _job, _src, d = heal_one(heal)
        forget(heal, monkeypatch)
        _cls, body = opened(heal, f"/v2/device/edge-b?list=Default&result={d['id']}")
        from modules.heal import steplog
        entry = steplog.incident("Default", incident_of(d))
        assert d["id"] in entry["decisions"], "the decision's id names that incident's run"
        assert f'data-outcome="{entry["outcome"]}"' in card_of(body)

    def test_a_decision_that_ran_nothing_has_no_card(self, heal):
        """A dry run is a decision, never a run: its row keeps its record and opens no card."""
        from modules.heal import decide
        settle(GOLDEN + ROUTE4, claim=False)
        got = decide.run("Default", now=T0, sources=Fake(GOLDEN + ROUTE4))
        assert [x["outcome"] for x in got["decided"]] == ["would_heal"], got
        (row,) = rows(device_history(heal), "heal")
        assert "would" in row and card_href(row) is None, row
        from modules.heal import steplog
        (entry,) = steplog.incidents("Default")["entries"]
        assert entry["state"] == "decided", "the record holds a decision and no act"

    def test_a_re_subscribe_s_row_opens_its_card_at_any_age(self, resub, monkeypatch):
        """Its record, kept two days: older than Finished keeps it (`FINISHED_KEEP_S`), opened
        from History by its id after a restart."""
        from modules.heal import run_card
        from modules.nsot import privileged
        run_one(resub, not_back())
        rec = privileged.runs(NET)["runs"][0]
        old = dict(rec, id="20261109T101500000000Z-" + "a" * 32)
        assert old["id"] < rec["id"]
        privileged._write(NET, old)
        forget(resub, monkeypatch)
        html = fleet_history(resub, NET)
        (row,) = [r for r in rows(html, "privileged") if old["id"] in r]
        want = f"/v2/device/r2?list={NET}&result={old['id']}"
        assert card_href(row) == want, row
        assert run_card.named_record(NET, "r2", old["id"]) is not None
        cls, body = opened(resub, want)
        assert cls == "op-card op-danger", cls
        assert "Re-subscribed; the stream did not come back:" in body
        assert list(stage_states(body)) == [
            "planned", "removing", "re-adding", "checking", "done"], stage_states(body)


class TestAFinishedRecord:
    def test_a_healed_run_s_details_name_no_step_running(self, heal):
        from modules.heal import steplog
        _job, _src, d = heal_one(heal)
        # The premise, measured where the host's smoke heal measured it: the act wrote its
        # apply as running and no end of it, then the steps after it.
        (act,) = [r for r in steplog.read("Default")["rows"]
                  if r.get("row") == "act" and r.get("decision") == d["id"]]
        applies = [s["result"] for s in act["steps"] if s["step"] == "apply"]
        assert applies == ["running"], applies
        (row,) = rows(device_history(heal), "heal")
        record = row[row.index("Details for the record"):]
        assert ": running" not in record and "running:" not in record.replace(
            "</dt><dd>running", "!"), record
        apply = re.search(r"<dt>\d+\. apply</dt><dd>(.*?)</dd>", record).group(1)
        assert apply.startswith("done: ") and ", when the next step began)" in apply, apply
        # Its end is the recorded start of the step after it, and the record keeps its own.
        steps = steplog.incident("Default", d["incident"])["steps"]
        k = next(i for i, s in enumerate(steps) if s["step"] == "apply")
        assert steps[k]["result"] == "running", "drawing rewrote nothing"
        # Drawn by the clock in the viewer's zone, the instant in its datetime (C3290).
        assert (f'(ended <time class="clock" datetime="{steps[k + 1]["at"]}"' in apply
                and apply.endswith(", when the next step began)")), apply

    def test_a_step_a_later_record_of_itself_ends_names_that_step(self):
        """The real rolled-back heal's steps: its apply recorded running, then its intent read,
        then its apply's outcome."""
        from modules.heal import steplog
        with open(FIXTURE, encoding="utf-8") as fh:
            steps = json.load(fh)["steps"]
        got = steplog.finished_steps({"state": "done", "steps": steps})
        assert [s["result"] for s in got].count("running") == 0
        assert (got[5]["step"], got[5]["result"]) == ("apply", "ended")
        assert got[5]["words"].endswith("its outcome is step 8's")
        assert (got[7]["step"], got[7]["result"]) == ("apply", "failed")
        assert steps[5]["result"] == "running", "a copy: the record is never rewritten"

    def test_a_record_that_ended_inside_a_step_says_so_and_one_still_applying_is_as_recorded(
            self):
        from modules.heal import steplog
        steps = [{"step": "read", "result": "ok", "at": "2026-11-12T03:42:10Z"},
                 {"step": "apply", "result": "running", "at": "2026-11-12T03:42:18Z"}]
        (_read, cut) = steplog.finished_steps({"state": "interrupted", "steps": steps})
        assert cut["result"] == "ended in this step"
        assert steplog.finished_steps({"state": "applying", "steps": steps}) == steps


class TestOneAttribution:
    def test_every_row_of_one_heal_reads_mercury_s_self_healing(self, heal):
        """The heal's row, its deploy receipt (written by the deploy path's own writers as the
        heal writes it, as the policy) and its commits (a golden recorded, then a measurement
        that found it unchanged, each `Source: heal_to_intent`, as the policy): one actor."""
        from modules import identity
        from modules.nsot import repo as R
        from routes.deploy import _pending_receipts, _write_receipts
        from modules.nsot.deploy import command_fingerprint
        from tests.test_deploy_receipts import _sent

        heal_one(heal)
        program = ["no ip route 192.0.2.128 255.255.255.128 192.0.2.10"]
        hashes = {"edge-b": command_fingerprint(program, [])}
        record, pending = _pending_receipts("Default", "deploy", {}, hashes, actor=SETTER,
                                            actor_kind="policy")
        result = record(_sent(device="edge-b", commands=program, authorised=[],
                              program_hash=command_fingerprint(program, [])))
        assert _write_receipts("Default", {"results": [result], "golden": {
            "commit": "", "batch_id": "b-1", "devices": ["edge-b"]}}, "deploy", {}, hashes,
            actor=SETTER, actor_kind="policy", pending=pending)["ok"]
        # edge-b's golden as a person captured it, then the heal's commits on it, as
        # tests/test_heal_records.py makes them (the heal's deploy commits as the policy).
        assert R.save_golden("Default", [R.GoldenItem("edge-b", GOLDEN, "192.0.2.6",
                                                      platform="cisco_xe")],
                             source="capture", actor=TEST_PERSON, allow_new=True)["ok"]
        item = R.GoldenItem("edge-b", GOLDEN + "! healed\n", "192.0.2.6",
                            platform="cisco_xe")
        from modules.config import get_list_data_dir
        with identity.carried_policy(SETTER, "fp-1"):
            assert R.save_golden("Default", [item], source="heal_to_intent",
                                 actor=SETTER)["ok"]
            # The smoke heal's measured row (the host, 2026-11-12, before C3165 left a heal's
            # commit no baseline decision): an empty commit measuring edge-b, as `save_golden`
            # wrote it, its Actor-Verified the policy's (`repo.commit` adds it).
            repo = os.path.join(get_list_data_dir("Default"), "config_repo")
            with R.repo_lock(repo):
                rc, _out, err = R.commit(
                    repo, "golden: no configuration changed; decision recorded (1 device(s) "
                    "measured via heal_to_intent)\n\nSource: heal_to_intent\nActor: " + SETTER
                    + "\nDevices-Measured: edge-b\n", list_name="Default", allow_empty=True,
                    publish_now=False)
            assert rc == 0, err
        html = device_history(heal)
        heals = {kind: [r for r in rows(html, kind) if kind in ("heal", "receipt")
                        or "(heal_to_intent)" in r]
                 for kind in ("heal", "receipt", "golden", "measured")}
        assert {k: [who(r) for r in v] for k, v in heals.items()} == {
            "heal": [MERCURY], "receipt": [MERCURY], "golden": [MERCURY],
            "measured": [MERCURY]}, heals
        for kind, (row,) in heals.items():
            assert ("<summary>The identity as recorded</summary>"
                    f"Mercury&#39;s self-healing · policy set by {SETTER}</details>") in row, \
                f"{kind}: the identity kept, closed"
            # Each row's By says the same; neither of the words the operator named is a who.
            said = unescape(off_record(row))
            assert f"By {MERCURY}</p>" in said, (kind, said)
            assert "By heal to intent" not in said and "by the policy they confirmed" not in \
                said, kind
        (person,) = [r for r in rows(html, "golden") if "(capture)" in r]
        assert who(person) == TEST_PERSON.split("@")[0], "a person's commit is still theirs"
        # The records keep the setter as the actor: the words are drawn, nothing rewritten.
        from modules.nsot import receipts
        (kept,) = receipts.read("Default", device="edge-b")["rows"]
        assert (kept["actor"], kept["actor_kind"]) == (SETTER, "policy")


class TestDisplayNamesInSteps:
    def test_a_heal_s_step_lines_name_the_setter_by_display_name(self, heal):
        heal_one(heal)
        (row,) = rows(device_history(heal), "heal")
        record = row[row.index("Details for the record"):]
        assert f"taken by heal to intent (policy set by {NAME})" in unescape(record)
        assert f"as the policy set by {NAME}, holding edge-b" in unescape(record)
        assert SETTER not in off_record(row), "an identity only under its record"
        # The step log keeps the identity beside those words (`policy_by`), and the policy's
        # own record names its setter by identity: the screen draws the name.
        from modules.heal import steplog
        (entry,) = steplog.incidents("Default")["entries"]
        assert entry["policy_by"] == SETTER and entry["policy"]["by"] == SETTER
        assert f"confirmed by {NAME}</dd>" in record, "the policy's line by display name"
