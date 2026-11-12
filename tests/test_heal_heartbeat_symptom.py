"""The restored heartbeat is the applet heal's symptom (C3164; the operator's F1 smoke test of
r3 in Auto, 2026-11-12: "Read symptom ran 0 s ("no symptom beyond the configuration"), so F1's
heal never checked the heartbeat itself; consider making the restored heartbeat F1's symptom";
his order: "C3164: the restored heartbeat is the applet heal's symptom").

- **Which applet:** only a unit that re-applies the heartbeat applet, decided from committed
  intent's parse (a whole syslog block, the heartbeat check's own population, and a section the
  parser models as the heartbeat on its own), never by a name: the real r2 golden's applet is,
  with an IPv4 or an IPv6 syslog host; another applet, a block intent does not hold whole, and a
  missing `logging host` are not.
- **The bound:** the applet's interval from intent and the logs read's lag, 2.5 times: 1050 s
  for 300 s; one interval is what Coverage's real capture holds for each C8000v, and the
  slowest-clocked switch's longest gap is inside it.
- **The read again:** Coverage's stored arrivals (no device read), on the reader's REAL capture
  (tests/fixtures/coverage_reporting/capture.json): a heartbeat counted after the heal began
  is gone; one before it, or in the minute it began, is not; at the bound, still there, naming
  the wait and what was read; Loki unread, unreadable; a network with no store, unreadable at
  once.
- **Through the act:** the heal waits for the heartbeat after the incident's own symptoms, the
  step declaring its bound and what it waits for; healed only when it arrives, symptom remains
  (amber) when the bound passes; other missing lines keep their handling.
- **On the card:** through the real app, the Checking stage says "Waiting for edge-b's
  heartbeat" with its countdown, then "edge-b at intent; its heartbeat back".

No device, no network.
"""
import copy
import os
import re

import pytest

from tests.test_coverage_reporting import _capture, read  # noqa: F401 (the fixture)
from tests.test_heal_act import FakeAct
from tests.test_heal_decide import GOLDEN, PLATFORM, Fake, changed, settle
from tests.test_heal_decide import lab  # noqa: F401 (the fixture)
from tests.test_heal_policy import T0, auto
from tests.test_heal_triggers import _Lazy
from tests.test_in_flight import no_hold_survives_a_test  # noqa: F401 (autouse)
from tests.test_run_outcomes import heal, heal_lab, page, recorded  # noqa: F401
from tests.test_run_progress import Gated
from tests.test_sdn_connections import networks  # noqa: F401 (the labs build on it)

A, DC, DS, K = _Lazy("act"), _Lazy("decide"), _Lazy("decisions"), _Lazy("kinds")
HERE = os.path.dirname(os.path.abspath(__file__))
R2 = os.path.join(HERE, "fixtures", "committed", "r2.cfg")
MARKER = "NMAS-HEARTBEAT"
OTHER_APPLET = ("event manager applet HB\n event timer watchdog time 60\n"
                " action 1 syslog msg heartbeat\n")


def _r2() -> str:
    with open(R2, encoding="utf-8") as fh:
        return fh.read()


def _stanza(text: str, head: str) -> str:
    """*head* and the lines under it, as the real configuration holds them."""
    lines = text.splitlines()
    i = lines.index(head)
    out = [head]
    for line in lines[i + 1:]:
        if not line.startswith(" "):
            break
        out.append(line)
    return "\n".join(out) + "\n"


def _lines(text: str, *starts) -> str:
    return "".join(l + "\n" for l in text.splitlines() if l.startswith(starts))


APPLET = _stanza(_r2(), f"event manager applet {MARKER}")
#: The syslog block's other parts, from the same real golden; the host is the test's own.
BLOCK = _lines(_r2(), "logging trap ", "logging origin-id ", "logging source-interface ")
#: edge-b's golden carrying r2's real heartbeat applet and syslog block in place of its own
#: applet (minimal edits).
HB = changed((OTHER_APPLET, APPLET),
             ("logging host 192.0.2.50\n", BLOCK + "logging host 192.0.2.50\n"))
HB6 = changed(("logging host 192.0.2.50\n", "logging host 2001:db8:0:9::50\n"), base=HB)
GONE = changed((APPLET, ""), base=HB)


@pytest.fixture(autouse=True)
def no_host_addresses(monkeypatch):
    monkeypatch.setattr("modules.nsot.removal.host_addresses", lambda: ["192.0.2.60"])


def restored(golden, running, intended=None, platform=PLATFORM):
    c = K.classify(golden, running, intended or golden, platform=platform, mgmt_ip="192.0.2.6")
    return A.restored_heartbeat(c["units"], intended or golden, platform), c


# ── Which applet ────────────────────────────────────────────────────────────────────────────

class TestWhichApplet:
    def test_the_real_golden_s_applet_removed_is_the_heartbeat_with_intent_s_interval(self):
        r2 = _r2()
        assert APPLET.splitlines()[1].strip() == "event timer watchdog time 300", \
            "the premise: r2's real applet beats every 300 s"
        got, c = restored(r2, r2.replace(APPLET, ""), platform="cisco_iosxe")
        assert got == 300 and [u["op"] for u in c["units"]] == ["add"], c["units"]

    @pytest.mark.parametrize("golden", [HB, HB6], ids=["ipv4-host", "ipv6-host"])
    def test_with_an_ipv4_or_an_ipv6_syslog_host(self, golden):
        got, _c = restored(golden, golden.replace(APPLET, ""))
        assert got == 300

    def test_a_changed_watchdog_is_the_heartbeat_set_back(self):
        got, c = restored(HB, HB.replace("watchdog time 300", "watchdog time 60"))
        assert got == 300, c["units"]

    def test_another_applet_is_not_the_heartbeat(self):
        got, c = restored(GOLDEN, GOLDEN.replace(OTHER_APPLET, ""))
        assert got == 0 and c["units"] and c["units"][0]["stanza"], \
            "an applet the parser does not model as the heartbeat keeps its handling"

    def test_one_that_only_resembles_it_is_not(self):
        near = APPLET.replace("msg \"NMAS-HEARTBEAT\"", "msg \"NMAS-HEARTBEAT-2\"")
        golden = changed((APPLET, near), base=HB)
        got, c = restored(golden, golden.replace(near, ""))
        assert got == 0 and c["units"], "the applet's name alone never decides"

    def test_a_block_intent_does_not_hold_whole_is_not_in_the_check_s_population(self):
        intent = changed(("logging origin-id hostname\n", ""), base=HB)
        got, c = restored(HB, GONE, intended=intent)
        assert got == 0 and c["units"], "nmas-heartbeat-rules expects no heartbeat from it"

    def test_a_missing_logging_host_is_not_the_applet(self):
        got, c = restored(HB, changed(("logging host 192.0.2.50\n", ""), base=HB))
        assert got == 0 and c["units"]


# ── The bound ───────────────────────────────────────────────────────────────────────────────

class TestTheBound:
    def test_the_interval_and_the_lag_two_and_a_half_times(self):
        assert A.HEARTBEAT_LAG_SECONDS == 120 and A.HEARTBEAT_MARGIN == 2.5
        assert A.heartbeat_bound(300) == 1050
        assert A.heartbeat_bound(60) == 450

    def test_one_interval_is_what_the_real_capture_holds(self):
        """The measurement the bound stands on: Coverage's reader's capture of the host
        (2026-10-03), each device's heartbeats counted per minute."""
        cap = _capture()
        gaps = {}
        for s in cap["heartbeat"]["data"]["result"]:
            st = sorted(float(t) for t, v in s["values"] if float(v) > 0)
            gaps[s["metric"]["dev"]] = [b - a for a, b in zip(st, st[1:])]
        assert len(gaps) == 9 and all(len(g) > 15 for g in gaps.values()), "a floor"
        assert set(gaps["r2"]) == set(gaps["r3"]) == {300.0}, "a C8000v's, one interval apart"
        slowest = max(max(g) for g in gaps.values())
        assert slowest == 660.0 and slowest + A.HEARTBEAT_LAG_SECONDS < A.heartbeat_bound(300)

    def test_the_trigger_names_the_store_its_bound_and_what_it_waits_for(self, lab):
        t = A.heartbeat_trigger("Default", "edge-b", 300)
        assert (t["kind"], t["source"], t["bound_s"], t["interval"]) == (
            "heartbeat", "coverage-reporting", 1050, 300)
        assert t["words"] == ("no NMAS-HEARTBEAT line from edge-b since its heartbeat applet "
                              "was re-applied") and "refused" not in t
        assert A.symptom_triggers([t]) == [t] and A.symptom_bound([t]) == 1050


# ── The read again ──────────────────────────────────────────────────────────────────────────

class Clock:
    def __init__(self, at):
        self.at, self.slept = at, []

    def __call__(self):
        return self.at

    def sleep(self, s):
        self.slept.append(s)
        self.at += s


def stored(value, at=None):
    """The reader's store as `reader_job.read_cached` answers it, *value* its last good."""
    return {"state": "ok", "doc": {"last_good": {
        "read_started": value["read_at"] if at is None else at, "value": value}}}


def trigger(bound=1050, device="r3"):
    return {"kind": "heartbeat", "source": "coverage-reporting", "interval": 300,
            "bound_s": bound,
            "words": f"no NMAS-HEARTBEAT line from {device} since its heartbeat applet was "
                     "re-applied"}


def again(value_at, since, *, device="r3", t=None, clock=None):
    """`act.read_symptom` over *value_at* (``clock -> stored doc``), from *since*."""
    clock = clock or Clock(since + 1)
    asked = []
    got = A.read_symptom("Default", device, [t or trigger(device=device)], since,
                         clock=clock, sleep=clock.sleep, read=lambda s: value_at(clock()),
                         request=lambda s: asked.append(s) or True)
    return got, clock, asked


class TestTheReadAgain:
    def test_a_heartbeat_counted_after_the_heal_began_is_the_symptom_gone(self, read):
        value, _prom, _loki = read()
        at = value["heartbeat"]["r3"]
        assert value["read_at"] - at == pytest.approx(176, abs=1), "the capture's own"
        since = at - 60 - 240
        got, clock, asked = again(lambda now: stored(value), since)
        assert got["state"] == "gone" and clock.slept == [] and asked == ["coverage-reporting"]
        assert got["words"].startswith("the symptom is gone (1 read again): r3's heartbeat "
                                       "arrived by ")
        assert f"{round(at - since)} s after the heal began" in got["words"]
        (r,) = got["reads"]
        assert r["result"] == "pass" and r["command"] == \
            "the coverage-reporting reader's stored value", "a store, never a device"

    def test_one_in_the_minute_the_heal_began_is_not_counted(self, read):
        value, _prom, _loki = read()
        at = value["heartbeat"]["r3"]
        got, clock, _a = again(lambda now: stored(value), at - 30)
        assert got["state"] == "present" and sum(clock.slept) >= 1050
        assert "in the minute the heal began, so it is not counted" in got["words"]

    def test_none_by_the_bound_is_still_there_naming_the_wait_and_what_was_read(self, read):
        value, _prom, _loki = read()
        at = value["heartbeat"]["r3"]
        got, clock, _a = again(lambda now: stored(value), at + 5)
        assert got["state"] == "present"
        assert got["words"].startswith(
            "the symptom is still there after 1050 s: no NMAS-HEARTBEAT line from r3 since "
            "its heartbeat applet was re-applied (r3's newest heartbeat was counted by ")
        assert got["words"].endswith(", before the heal began)")
        assert set(clock.slept) == {A.POLL_SECONDS} and len(got["reads"]) == 1050 // 30 + 1
        assert {r["result"] for r in got["reads"]} == {"fail"}

    def test_it_waits_until_the_next_heartbeat_arrives(self, read):
        value, _prom, _loki = read()
        since = value["heartbeat"]["r3"] + 5
        later = copy.deepcopy(value)
        later["heartbeat"]["r3"] = since + 300
        later["read_at"] = since + 330

        def at(now):
            return stored(later) if now >= since + 330 else stored(value)

        got, clock, _a = again(at, since)
        assert got["state"] == "gone" and len(got["reads"]) == 12, got["reads"]
        assert "300 s after the heal began" in got["words"]
        assert [r["result"] for r in got["reads"]][-2:] == ["fail", "pass"]

    def test_a_device_with_no_heartbeat_in_coverage_says_so(self, read):
        value, _prom, _loki = read()
        got, _c, _a = again(lambda now: stored(value), value["read_at"] - 10, device="edge-b")
        assert got["state"] == "present" and "none from edge-b in Coverage's last 3 h" \
            in got["words"]

    def test_loki_unread_is_unreadable_never_gone(self, read):
        value, _prom, _loki = read(loki_fail=("heartbeat",))
        assert not value["sources"]["heartbeat"]["ok"], "the premise: the source failed"
        got, _c, _a = again(lambda now: stored(value), value["read_at"] - 600)
        assert got["state"] == "unreadable"
        assert "Coverage's heartbeat source was not read (RuntimeError: Loki's heartbeat " \
            "lines could not be asked" in got["words"]

    def test_a_store_not_read_since_the_heal_is_stale(self, read):
        value, _prom, _loki = read()
        got, _c, _a = again(lambda now: stored(value), value["read_at"] + 1)
        assert got["state"] == "unreadable" and "coverage-reporting: stale" in got["words"]

    def test_a_network_with_no_store_is_unreadable_at_once(self):
        t = dict(trigger(), refused="Loki is not configured for Lab: nothing is set for it")
        clock = Clock(T0)
        got = A.read_symptom("Default", "r3", [t], T0 - 1, clock=clock, sleep=clock.sleep,
                             read=lambda s: pytest.fail("no store is read"),
                             request=lambda s: pytest.fail("no run is asked"))
        assert got["state"] == "unreadable" and clock.slept == []
        assert got["words"] == ("the symptom cannot be read here (no NMAS-HEARTBEAT line from r3 "
                                "since its heartbeat applet was re-applied: Loki is not "
                                "configured for Lab: nothing is set for it)")


# ── Through the act ─────────────────────────────────────────────────────────────────────────

def hb_decided(running, *, golden=HB, triggers=None):
    """A heal decision on edge-b made in AUTO by the real decision over *golden*: its id."""
    auto("Default", now=T0 - 60, kinds=("missing_line",))
    inc = settle(running, golden=golden, triggers=triggers)
    d = DC.decide_one("Default", inc, now=T0, sources=Fake(running, golden=golden,
                                                           intended=golden))
    assert d["outcome"] == "heal", d["words"]
    return DS.record("Default", d, T0)


class Seen(FakeAct):
    """The act's fakes, keeping the triggers each symptom read was given; its read the REAL
    one (`act.read_symptom`) over *docs* when given."""

    def __init__(self, *a, docs=None, **kw):
        super().__init__(*a, **kw)
        self.given, self.docs = [], docs

    def symptom(self, device, triggers, since):
        self.given.append(list(triggers))
        if self.docs is None:
            return super().symptom(device, triggers, since)
        clock = Clock(since + 1)
        return A.read_symptom("Default", device, triggers, since, clock=clock,
                              sleep=clock.sleep, read=lambda s: self.docs(since, clock()),
                              request=lambda s: True)


def heal_with(running=GONE, golden=HB, **kw):
    src = Seen(running, golden=golden, intended=golden, post=K._stored(golden), **kw)
    d = hb_decided(running, golden=golden)
    return A.act_one("Default", d["id"], now=T0 + 5, sources=src), src, d


def beat_value(read, at):
    """Coverage's reader's value from the real capture, edge-b's newest heartbeat *at*."""
    value, _prom, _loki = read()
    value = copy.deepcopy(value)
    value["heartbeat"]["edge-b"] = at
    return value


class TestThroughTheAct:
    def test_the_heal_reads_the_heartbeat_after_the_incident_s_own(self, lab):
        got, src, _d = heal_with(symptom={"state": "gone", "words": "the symptom is gone"})
        assert got["outcome"] == "healed", got["words"]
        (given,) = src.given
        assert [t["kind"] for t in given] == ["config_change", "heartbeat"]
        assert given[-1]["bound_s"] == 1050 and given[-1]["source"] == "coverage-reporting"
        (s,) = [s for s in got["steps"] if s["step"] == "symptom"]
        assert (s["result"], s["wait_s"], s["wait_bound"], s["wait_for"]) == (
            "gone", 1050, True, "heartbeat"), s
        assert s["began"], "begun as it waits, ended in place"

    def test_healed_only_when_the_heartbeat_arrives_through_the_real_read(self, lab, read):
        def docs(since, now):
            arrived = now >= since + 330
            value = beat_value(read, since + 300 if arrived else since - 176)
            value["read_at"] = now
            return stored(value)

        got, _src, d = heal_with(docs=docs)
        assert got["outcome"] == "healed" and A.OUTCOME_WORDS["healed"] == "healed and verified"
        assert "edge-b's heartbeat arrived by " in got["words"]
        assert "300 s after the heal began" in got["words"]
        (s,) = [s for s in got["steps"] if s["step"] == "symptom"]
        assert s["result"] == "gone" and len(s["reads"]) == 12
        assert DS.find("Default", d["id"])["applied"]["outcome"] == "healed"

    def test_no_heartbeat_by_the_bound_is_symptom_remains_never_green(self, lab, read):
        from modules.heal import run_card

        def docs(since, now):
            value = beat_value(read, since - 176)
            value["read_at"] = now
            return stored(value)

        got, _src, d = heal_with(docs=docs)
        assert got["outcome"] == "symptom_remains", got["words"]
        assert run_card.level_of(got["outcome"]) == "warn"
        said = ("configuration at intent, and the symptom is still there after 1050 s: no "
                "NMAS-HEARTBEAT line from edge-b since its heartbeat applet was re-applied "
                "(edge-b's newest heartbeat was counted by ")
        assert got["words"].startswith(said) and ", before the heal began)" in got["words"]
        (rec,) = [s for s in got["steps"] if s["step"] == "record"]
        assert rec["words"].startswith("healed configuration; symptom remains: " + said)
        (s,) = [s for s in got["steps"] if s["step"] == "symptom"]
        assert s["result"] == "present" and len(s["reads"]) == 36
        assert DS.find("Default", d["id"])["applied"]["outcome"] == "symptom_remains"

    def test_another_missing_line_keeps_its_own_handling(self, lab):
        running = changed(("logging host 192.0.2.50\n", ""), base=HB)
        got, src, _d = heal_with(running)
        assert got["outcome"] == "healed", got["words"]
        assert [[t["kind"] for t in g] for g in src.given] == [["config_change"]]
        (s,) = [s for s in got["steps"] if s["step"] == "symptom"]
        assert s["result"] == "none" and "wait_for" not in s and "wait_s" not in s

    def test_an_applet_that_is_not_the_heartbeat_keeps_its_own_handling(self, lab):
        got, src, _d = heal_with(GOLDEN.replace(OTHER_APPLET, ""), golden=GOLDEN)
        assert got["outcome"] == "healed", got["words"]
        assert [[t["kind"] for t in g] for g in src.given] == [["config_change"]]


# ── On the card ─────────────────────────────────────────────────────────────────────────────

def start(c, src, running=GONE):
    from modules.heal import act

    d = hb_decided(running)
    got = act.run("Default", now=T0 + 5,
                  starter=lambda network, taken: act.start(network, taken, sources=src))
    assert got["started"] and not got["failed"], got
    job = got["started"][0]["job"]
    c.state["jobs"].append(job)
    return job, d


class TestOnTheCard:
    def test_checking_says_waiting_for_the_heartbeat_and_counts_it_down(self, heal):  # noqa: F811
        from modules.heal import policy
        from modules.nsot import capture_job
        src = Gated(GONE, golden=HB, intended=HB, post=K._stored(HB),
                    symptom={"state": "gone", "words": "the symptom is gone (2 read again)"},
                    mode=lambda got: policy.current("Default", T0 + 5))
        job, d = start(heal, src)
        try:
            src.go("apply")
            src.reached("symptom")
            body = page(heal, "edge-b", "Default")
            assert ('class="run-stage run-stage-running" data-stage="checking" '
                    'data-lead="symptom" aria-current="step"') in body
            said = re.search(r'<span class="run-stage-said">([^<]*) · <span class="run-left" '
                             r'data-run-wait-began="[^"]+" data-run-wait-s="(\d+)" '
                             r'data-run-wait-bound="1">([^<]*)</span>', body)
            assert said, "the stage's sentence and its countdown"
            assert said.group(1) == "Waiting for edge-b&#39;s heartbeat"
            assert said.group(2) == "1050" and re.fullmatch(r"up to 1050 s: \d+ s left",
                                                            said.group(3))
        finally:
            src.let_go()
        assert capture_job.wait(job, 30) and recorded(d) == "healed"
        after = page(heal, "edge-b", "Default")
        assert ('data-stage="checking"' in after
                and "edge-b at intent; its heartbeat back" in after)

    @staticmethod
    def staged(**waits):
        from modules import run_stepper
        from modules.heal import run_card

        steps = [{"step": "take", "result": "ok", "words": "taken"},
                 {"step": "golden", "result": "ok", "words": "at its golden"},
                 dict({"step": "symptom", "result": "running", "words": "reading",
                       "at": "2026-11-12T03:46:18Z", "began": "2026-11-12T03:46:18Z",
                       "wait_s": 150, "wait_bound": True}, **waits)]
        card = run_stepper.record_card("edge-b", "Self-healing on edge-b", [
            run_card.act_phase(steps, ended=False, host="edge-b")], ended=False)
        got = run_card.heal_stages(card, host="edge-b", facts={}, ended=False, now=0)
        (checking,) = [g for g in got["stages"] if g["key"] == "checking"]
        return checking, got

    def test_a_wait_for_nothing_named_says_the_symptom_as_before(self):
        checking, _got = self.staged()
        assert checking["sentence"] == "Waiting for edge-b's symptom to clear"

    def test_what_it_waits_for_is_the_sentence_s_and_goes_no_further(self):
        """Every carried field is drawn (tests/test_v2_context_is_drawn.py): what a step waits
        for is drawn as its stage's sentence, so no step, row or lead carries it on."""
        checking, got = self.staged(wait_for="heartbeat")
        assert checking["sentence"] == "Waiting for edge-b's heartbeat"
        assert "wait_for" not in repr(got), "carried past the sentence that draws it"
