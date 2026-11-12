"""The actions' records, rows and notices (board H's amendment, part H23; docs/HEAL_TO_INTENT.md
19.4, "Records and History" and "Record"): the port bounce, the OSPF reset through it, the BGP
session clear and the dampening proposal. No network and no device: the step log and the
notifier's store are the test's (tests/test_sdn_connections.py's networks), and each decision
and act row is written as the act writes it. The end-to-end records of each act are in its own
file's `TestTheRecords` (tests/test_heal_bounce.py, test_heal_session_clear.py,
test_heal_dampening.py).

- **The marks** (`steplog.mark`): an action is named as an action (a dry-run bounce "would
  bounce", a clear's or a dampening's end never "bounced"); a heal's marks are unchanged; a
  row written before the action's fields folds as before.
- **The change record** (`change_record.build_action`): board CR's sections in order, the
  program masked, each family's rollback, deterministic, none without a program, a failure
  said.
- **Needs attention** (`attention._heal_clear_rows`): a held clear and every end but cleared
  is one row; cleared is none; a later clear of the neighbour replaces it; each row's action
  is its notice's What to do (`heal_notice.action_todo`), as the bounce's and the dampening's.
- **The notices** (`heal_notice.run_actions`): each action end told once, on its incident's
  thread, as the event its row needs (``cant_fix``, ``halted``; a success ``action`` only when
  automatic), What to do the row's own words, the program's lines withheld; the success under
  the team's "every automatic heal".
"""

import time

import pytest

from modules import heal_notice as _NOTICE  # noqa: F401 (the module under test, at import)
from tests.test_heal_policy import T0
from tests.test_sdn_connections import networks  # noqa: F401 (the fixture)

NET = "Default"
GI4 = "GigabitEthernet4"
PEER = "198.51.100.3"
BOUNCE = ["configure terminal revert timer 2", f"interface {GI4}", "shutdown", "no shutdown",
          "end"]


def N():
    from modules import heal_notice
    return heal_notice


def bounce_decision(did="hd-1", outcome="heal", incident="hi-1", kind="port_bounce"):
    return {"id": did, "incident": incident, "device": "r3", "mode": "auto", "kind": kind,
            "tier": 1, "outcome": outcome, "words": f"bounce now: r3 {GI4}",
            "policy": {"fingerprint": "fp-1", "by": "op@example.invalid",
                       "reason": "the bounce under test"},
            "program": list(BOUNCE), "program_hash": "a" * 16, "triggers": ["r3 Gi4 down"],
            "bounce": {"timer": 2},
            "action": {"kind": kind, "device": "r3", "interface": GI4, "peer": "",
                       "far_device": "r4", "far_interface": GI4}}


def clear_decision(did="hd-2", outcome="heal", incident="hi-2"):
    return {"id": did, "incident": incident, "device": "r4", "mode": "auto",
            "kind": "session_clear", "tier": 1, "outcome": outcome,
            "words": f"clear now: a hard clear of r4's BGP neighbour {PEER}",
            "policy": {"fingerprint": "fp-1", "by": "op@example.invalid", "reason": "r"},
            "program": [f"clear ip bgp {PEER}"], "program_hash": "b" * 16,
            "action": {"kind": "session_clear", "device": "r4", "interface": "", "peer": PEER,
                       "variant": "hard"}}


def act_result(outcome, sent=True, words="", records=None):
    return {"outcome": outcome, "words": words or f"{outcome} for the test", "sent": sent,
            "steps": [{"step": "take", "result": "ok", "words": "taken"},
                      {"step": "verify", "result": "ok" if outcome in ("bounced", "cleared")
                       else "failed", "words": "read for the test"}],
            "records": dict(records or {})}


def write(decision, result=None, now=T0):
    """The decision row, and the act row when *result* is given, as the act writes them."""
    from modules.heal import steplog
    steplog.record_decision(NET, decision, now)
    if result is not None:
        steplog.record_act(NET, decision, result, by="self-healing (policy set by op)",
                           now=now + 5)


# ── The marks ──────────────────────────────────────────────────────────────────────────────

class TestTheMarks:
    @pytest.mark.parametrize("outcome,kind,mark", [
        ("would_heal", "port_bounce", "would bounce"),
        ("would_heal", "ospf_reset", "would bounce"),
        ("heal", "port_bounce", "bouncing"),
        ("would_heal", "session_clear", "would clear"),
        ("unverified", "port_bounce", "bounced, not verified"),
        ("unverified", "session_clear", "cleared, not verified"),
        ("unverified", "dampening_proposal", "dampened, not verified"),
        ("rolled_back", "dampening_proposal", "dampening rolled back"),
        ("propose", "dampening_proposal", "dampening proposed"),
        ("still_flapping", "port_bounce", "bounced, still flapping"),
        ("not_back", "session_clear", "cleared, session not back"),
        # A heal to intent keeps its marks.
        ("would_heal", "security_acl", "would heal"),
        ("rolled_back", "physical", "rolled back"),
        ("heal", "", "healing")])
    def test_an_action_is_named_as_an_action(self, outcome, kind, mark):
        from modules.heal import steplog
        assert steplog.mark(outcome, kind) == mark

    def test_every_family_mark_is_an_outcome_its_act_or_decision_ends_with(self):
        from modules.heal import bounce, dampening, session_clear, steplog
        ends = {"bounce": set(bounce.OUTCOMES), "clear": set(session_clear.OUTCOMES),
                "dampening": set(dampening.OUTCOMES)}
        decided = {"heal", "would_heal", "propose"}
        for fam, marks in steplog.ACTION_MARKS.items():
            assert set(marks) <= ends[fam] | decided, (fam, set(marks) - ends[fam] - decided)

    def test_rows_keep_the_action_and_a_row_from_before_folds_as_before(self, networks):
        from modules.heal import steplog
        write(bounce_decision(), act_result("bounced"))
        old = dict(bounce_decision(did="hd-9", incident="hi-9"))
        old.pop("action")
        write(old, act_result("bounced"))
        new, before = steplog.incidents(NET)["entries"]
        assert new["action"]["interface"] == GI4 and new["sent"] is True
        assert steplog.subject(new) == f"r3 {GI4}"
        assert "action" not in before and steplog.subject(before) == "r3"
        assert steplog.far_ends(before) == [], "no window, no decision's far end: none"


# ── The change record ──────────────────────────────────────────────────────────────────────

class TestTheChangeRecord:
    def test_board_crs_sections_in_order_the_program_masked(self):
        from modules.heal import change_record as CR
        d = dict(bounce_decision(), program=BOUNCE + [" description key secret-v4lue"])
        got = CR.build_action(NET, d, act_result("bounced", records={"window": {
            "from": "a", "until": "b", "via": "heal-bounce", "interfaces": [GI4],
            "far_ends": [{"device": "r4", "interface": GI4}]}}), at="2026-11-08T06:00:00Z")
        assert got["state"] == "made" and got["risk"] == "medium"
        heads = [x[3:] for x in got["markdown"].splitlines() if x.startswith("## ")]
        assert heads == list(CR.SECTIONS)
        assert "no AI call" in got["markdown"] and "its far end: r4 GigabitEthernet4" in \
            got["markdown"]
        assert got == CR.build_action(NET, d, act_result("bounced", records={"window": {
            "from": "a", "until": "b", "via": "heal-bounce", "interfaces": [GI4],
            "far_ends": [{"device": "r4", "interface": GI4}]}}), at="2026-11-08T06:00:00Z"), \
            "deterministic"

    @pytest.mark.parametrize("outcome,rec,said", [
        ("repaired", {"repair": {"restored": True, "steps": [
            {"step": "no shutdown", "achieved": "the port administratively up"}]}},
         "Repaired: no shutdown: the port administratively up"),
        ("failed", {"repair": {"restored": False, "steps": []}}, "NOT RESTORED: "),
        ("reverted", {}, "No confirm was sent, and the device's revert timer reverted it.")])
    def test_a_bounces_rollback_says_what_it_did(self, outcome, rec, said):
        from modules.heal import change_record as CR
        text = CR.build_action(NET, bounce_decision(), act_result(outcome, records=rec))[
            "markdown"]
        assert "The device's own revert timer (2 minute(s)" in text and said in text

    def test_nothing_sent_says_so_and_no_program_is_no_record(self):
        from modules.heal import change_record as CR
        text = CR.build_action(NET, clear_decision(), act_result(
            "refused", sent=False, words="13c: the route. Nothing was sent"))["markdown"]
        assert "NOT sent: 13c: the route. Nothing was sent" in text
        assert "Nothing was verified" not in text, "its steps are still named"
        assert CR.build_action(NET, dict(clear_decision(), program=[]), act_result("cleared"))[
            "state"] == "none"

    def test_a_record_that_cannot_be_made_is_said_never_raised(self, monkeypatch):
        from modules.heal import change_record as CR

        def broken(*a, **k):
            raise RuntimeError("the test broke it")
        monkeypatch.setattr(CR, "action_markdown", broken)
        got = CR.build_action(NET, bounce_decision(), act_result("bounced"))
        assert got["state"] == "failed" and "the test broke it" in got["words"]


# ── Needs attention: the session clear's rows ──────────────────────────────────────────────

class TestTheClearsRows:
    def row(self, outcome="heal", applied=None, guard=None, epoch=T0, did="hd-1", peer=PEER):
        d = {"id": did, "device": "r4", "outcome": outcome, "epoch": epoch,
             "action": {"kind": "session_clear", "device": "r4", "interface": "", "peer": peer,
                        "variant": "hard"},
             "guard": guard or {}}
        if applied:
            d["applied"] = {"outcome": applied, "words": f"{applied} for the test"}
        return d

    def rows(self, decisions, now=T0 + 60):
        from modules import attention
        return attention._heal_clear_rows(NET, decisions, now)

    @pytest.mark.parametrize("applied,level", [("not_back", "danger"), ("reset", "danger"),
                                               ("unverified", "warning"),
                                               ("rejected", "warning"),
                                               ("refused", "warning")])
    def test_every_end_but_cleared_is_one_row(self, applied, level):
        from modules import attention, heal_notice
        (r,) = self.rows([self.row(applied=applied)])
        assert (r["kind"], r["level"]) == ("clear", level)
        assert r["action"]["href"] == "/v2/device/r4?tab=history"
        assert r["action"]["label"] == heal_notice.action_todo("session_clear", applied, "r4",
                                                               peer=PEER)
        assert r["action"]["label"] == (
            f"Read the clear's steps on r4's History, check the BGP session to {PEER} and the "
            "neighbour's own device, then acknowledge with what you found")
        assert PEER in r["what"] and r["clears_at"] == attention._iso(T0 + 7 * 86400)
        assert ("halted (guard 14)" in r["cause"]) is (applied == "reset")

    def test_cleared_is_no_row_and_a_later_clear_replaces_one(self):
        assert self.rows([self.row(applied="cleared")]) == []
        assert self.rows([self.row(applied="not_back"),
                          self.row(applied="cleared", epoch=T0 + 30, did="hd-2")]) == []
        assert len(self.rows([self.row(applied="not_back"),
                              self.row(applied="not_back", did="hd-3",
                                       peer="2001:db8:51:1::2")])) == 2, "one per neighbour"

    def test_a_held_clear_is_a_row_and_a_proposal_or_dry_run_is_not(self):
        (r,) = self.rows([self.row("held", guard={"guard": 3, "name": "planned work",
                                                  "words": "a window on r4"})])
        assert "not tried again by itself" in r["cause"]
        assert self.rows([self.row("would_heal")]) == []
        assert self.rows([self.row("propose")]) == [], "its own proposal row"
        assert self.rows([self.row(applied="not_back")], now=T0 + 8 * 86400) == []

    def test_the_network_source_draws_it(self, networks, monkeypatch):
        from modules import attention
        monkeypatch.setattr(attention, "_page_network", lambda: NET)
        got = attention.heal_source(got=[self.row(applied="not_back")], now=T0 + 60)
        assert [r["kind"] for r in got["rows"]] == ["clear"], got
        assert "1 BGP session clear(s) held or not ended cleared" in got["checked"]

    def test_the_bounces_and_dampenings_rows_draw_their_notices_words(self):
        from modules import attention, heal_notice
        d = {"id": "hd-1", "device": "r3", "outcome": "heal", "epoch": T0,
             "action": {"kind": "port_bounce", "device": "r3", "interface": GI4,
                        "far_device": "r4", "far_interface": GI4},
             "applied": {"outcome": "failed", "words": "x"}}
        (r,) = attention._heal_bounce_rows(NET, [d], T0 + 60)
        assert r["action"]["label"] == (
            f"Read the bounce's steps on r3's History, check {GI4} and its far end (r4 {GI4}), "
            "then acknowledge with what you found")
        assert r["action"]["label"] == heal_notice.action_todo(
            "port_bounce", "failed", "r3", interface=GI4, far_device="r4", far_interface=GI4)


# ── The notices ────────────────────────────────────────────────────────────────────────────

def told(record):
    def deliver(network, event):
        record.append(event)
        return {"ok": True, "sent": 1, "failed": 0, "error": ""}
    return deliver


def inline(events):
    """A starter that tells the action end at once, into *events*."""
    return lambda network, one: N().action_notice(network, one, deliver=told(events))


class TestTheNotices:
    @pytest.mark.parametrize("decision,outcome,event", [
        (bounce_decision, "still_flapping", "cant_fix"),
        (bounce_decision, "failed", "halted"),
        (bounce_decision, "bounced", "action"),
        (clear_decision, "not_back", "cant_fix"),
        (clear_decision, "reset", "halted"),
        (clear_decision, "cleared", "action")])
    def test_each_end_is_told_once_as_the_event_its_row_needs(self, networks, decision,
                                                              outcome, event):
        from modules.notify import message
        d = decision()
        write(d, act_result(outcome))
        events = []
        got = N().run(NET, now=T0 + 30, action_starter=inline(events),
                      starter=lambda *a, **k: pytest.fail("no can't-fix here"))
        assert got["told"] == [d["id"]]
        (ev,) = events
        assert ev["event"] == event and ev["incident"] == d["incident"]
        a = d["action"]
        assert ev["todo"] == N().action_todo(
            d["kind"], outcome, d["device"], interface=a.get("interface") or "",
            peer=a.get("peer") or "", far_device=a.get("far_device") or "",
            far_interface=a.get("far_interface") or "")
        # Premise corrected (the operator, 2026-11-12, objective 2: the email "links to the
        # incident"): the incident's address, its card on the device's page, on History.
        assert ev["link"] == f"/v2/incident/{d['incident']}?list={NET}"
        message.check_event(ev)
        assert N().actions_due(NET, now=T0 + 60) == [], "a told end is no longer due"
        assert N().run(NET, now=T0 + 60, action_starter=inline(events))["told"] == [], \
            "told once"

    def test_the_program_is_withheld_from_the_message(self, networks):
        d = bounce_decision()
        write(d, act_result("failed", words=f"NOT RESTORED: shutdown on interface {GI4}"))
        events = []
        N().run(NET, now=T0 + 30, action_starter=inline(events))
        (ev,) = events
        assert "shutdown" not in ev["outcome"] and "withheld" in ev["outcome"], ev["outcome"]
        assert ev["outcome"].startswith(f"r3 {GI4} bounced, NOT RESTORED")

    def test_the_program_is_withheld_from_the_decision_and_every_step(self, networks):
        # The irreversible tier's hand check (2026-11-08): a configuration line in the
        # decision's words or in a step's words never leaves the host either.
        d = dict(bounce_decision(), words=f"bounce now: shutdown on interface {GI4}")
        res = act_result("failed", words="failed for the test")
        res["steps"][1]["words"] = f"read back: shutdown on interface {GI4}"
        write(d, res)
        events = []
        N().run(NET, now=T0 + 30, action_starter=inline(events))
        (ev,) = events
        assert "shutdown" not in ev["detected"] and "withheld" in ev["detected"], ev["detected"]
        whats = [s["what"] for s in ev["steps"]]
        assert not [w for w in whats if "shutdown" in w], whats
        assert any("withheld" in w for w in whats), whats

    def test_a_persons_approved_success_and_the_past_are_not_told(self, networks):
        write(clear_decision(outcome="propose"), act_result("cleared"))
        write(bounce_decision(did="hd-5", incident="hi-5"), act_result("failed"),
              now=T0 - N().NEW_WITHIN_S - 60)
        assert N().actions_due(NET, now=T0 + 30) == []

    def test_an_automatic_success_goes_under_every_automatic_heal(self, networks, monkeypatch):
        from modules import heal_notify
        from modules.notify import delivery
        asked = []
        monkeypatch.setattr(heal_notify, "teams_for",
                            lambda network, event: asked.append(event) or ["team-1"])
        monkeypatch.setattr(delivery, "deliver_event",
                            lambda event, teams: {"ok": True, "sent": 1, "failed": 0,
                                                  "error": ""})
        for which in ("action", "cant_fix", "halted", "analysis"):
            N()._deliver(NET, {"event": which})
        assert asked == ["healed", "cant_fix", "halted", "cant_fix"]

    def test_a_store_that_cannot_be_read_tells_nothing(self, networks, monkeypatch):
        from modules.ai import heal_analysis as HA
        write(bounce_decision(), act_result("failed"))
        monkeypatch.setattr(HA, "read", lambda network: {"state": "unreadable", "rows": [],
                                                         "error": "the test"})
        assert N().actions_due(NET, now=T0 + 30) == []

    def test_taken_once_across_callers(self, networks):
        from modules.ai import heal_analysis as HA
        assert HA.claim_told(NET, "hd-1", incident="hi-1", event="cant_fix", now=time.time())
        assert not HA.claim_told(NET, "hd-1", incident="hi-1", event="cant_fix",
                                 now=time.time())
