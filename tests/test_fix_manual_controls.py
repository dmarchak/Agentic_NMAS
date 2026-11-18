"""A saved fix's manual controls (da740aa1, C3849; the operator, 2026-11-16): New fix and Edit
take the right a fix takes (self-healing with a match, admin without, the AI none); a fix's
lines are net-zero or refused in the operator's words (`command_policy.judge`: only shutdown /
no shutdown is known to undo itself, from a port checked not administratively down); a change
to its commands, checks or verify is a new version, the old kept; an Automatic fix whose match,
fills, lines, checks or verify change drops to Manual only until a verified run of the version
it runs then; Set Automatic needs that run; a run that sent nothing is never a verified one.

The store through tests/test_saved_plans.py's `store` fixture (the test's own data folder, the
runner's record shape written by `privileged.record`). Paid for docs/FAST_LANE_DEBT.md's row for
da740aa1 ("C3849's manual controls"), the debt pass, 2026-11-18; the confirm case for Set
Automatic… is tests/test_confirm_buttons_drawn.py's (another agent's, the same pass).

Each test holds one purpose:
- the net-zero rule: a declared pair, its port precondition, an unproven pair, a global line
  under an interface, a line nothing undoes (the operator's words), a negation undoing nothing,
  a global line, and a pair an admin approved;
- a verified run is one that sent and verified, never one that sent nothing;
- a version: a change to checks is a new version, the old kept; a change of words alone is not;
  an edit opened on an old version is refused naming both; the version a run ran;
- Automatic: an edit of an Automatic fix's checks drops it to Manual only; Set Automatic is
  refused until a verified run of the new version, never on a run that sent nothing;
- the rights: the AI writes and changes no fix; a fix with a match takes the self-healing
  right, one without the admin right.
"""
import copy

import pytest

from modules import identity
from modules.nsot import command_policy as POL
from modules.nsot import privileged
from modules.nsot import saved_plans as S
from tests.test_saved_plans import MATCH, NET, OTHER, PERSON, WHO, script, store  # noqa: F401

HEAD = "interface {interface}"
LATER = "2099-01-01T00:00:00Z"


def lines(*under, head=HEAD) -> list:
    return [head] + [" " + u for u in under]


def run_at(at: str, key: str, outcome: str = "done") -> str:
    """A command plan's run of *key* at *at*, as the runner records it: its id."""
    from modules.nsot import reads
    rec = {"id": reads.new_id(), "list": NET, "device": "s1", "key": key,
           "kind": "command_plan", "state": "done", "outcome": outcome, "actor": PERSON,
           "at": at}
    privileged.record(NET, rec)
    return rec["id"]


def stored(key: str) -> dict:
    return S.read()["plans"][key]


def with_pair_check(template: dict) -> dict:
    """*template* with the declared pair's port precondition added (a change to its checks)."""
    t = copy.deepcopy(template)
    t["preconditions"] = list(t.get("preconditions") or []) + [dict(POL.PAIR_PRECONDITION)]
    return t


def edit(e: dict, *, version: int = None, template: dict = None, words: str = None,
         who: dict = None) -> dict:
    raw = stored(e["key"])
    return S.edit_fix(e["key"], network=NET,
                      version=version or S.versions(raw)[-1]["version"],
                      name=raw["name"], words=raw.get("words") if words is None else words,
                      match=raw.get("match") or {}, fills=raw.get("fills") or {},
                      template=template, **(who or WHO))


class TestTheNetZeroRule:
    def test_shutdown_then_no_shutdown_is_the_declared_pair(self):
        got = POL.judge(lines("shutdown", "no shutdown"))
        assert got == {"lasting": [], "unproven": [], "declared": [" shutdown", " no shutdown"]}

    def test_the_declared_pair_needs_its_port_precondition(self):
        cmds = lines("shutdown", "no shutdown")
        why = POL.pair_refusal(cmds, [])
        assert "checks first that the port is not administratively down" in why, why
        assert POL.PAIR_PRECONDITION["name"] in why
        assert POL.pair_refusal(cmds, [dict(POL.PAIR_PRECONDITION)]) == ""
        assert POL.pair_refusal(lines("description a", "no description a"), []) == ""

    def test_another_pair_is_unproven_never_net_zero_by_resemblance(self):
        got = POL.judge(lines("description uplink", "no description uplink"))
        assert got["unproven"] == [" description uplink", " no description uplink"]
        assert got["lasting"] == [] and got["declared"] == []

    def test_a_global_command_under_an_interface_is_refused(self):
        got = POL.judge(lines("ip routing", "no ip routing"))
        assert [raw for raw, _ in got["lasting"]] == [" ip routing", " no ip routing"]
        assert "`ip routing` configures the device as a whole" in got["lasting"][0][1]

    def test_a_line_nothing_undoes_is_refused_in_the_operators_words(self):
        why = POL.lasting_refusal(lines("switchport access vlan 10"), device="s1")
        assert why.startswith("`switchport access vlan 10`: This line would change s1's "
                              "configuration permanently; a fix must leave it as it was. "
                              "Make lasting changes in Intent."), why
        assert "its own negation, `no switchport access vlan 10`, would" in why

    def test_a_negation_that_undoes_nothing_set_before_it_lasts(self):
        (raw, why), = POL.lasting(lines("no shutdown"))
        assert raw == " no shutdown" and "undoes nothing this fix set before it" in why

    def test_a_global_line_and_a_line_under_no_interface_last(self):
        got = POL.lasting(["hostname s9", " shutdown"])
        assert [raw for raw, _ in got] == ["hostname s9", " shutdown"]
        assert "global configuration" in got[0][1]
        assert "under no interface" in got[1][1]

    def test_a_pair_an_admin_approved_is_declared_and_one_held_provisional_is_not(
            self, monkeypatch):
        on = f"{HEAD} > spanning-tree portfast"
        off = f"{HEAD} > no spanning-tree portfast"
        shapes = {"on": {"shape": on, "state": "approved", "pair_of": off},
                  "off": {"shape": off, "state": "approved"}}
        monkeypatch.setattr(POL, "read_store", lambda network: {"shapes": shapes})
        cmds = lines("spanning-tree portfast", "no spanning-tree portfast")
        assert (on, off) in POL.declared_pairs(NET)
        assert POL.judge(cmds, NET)["declared"] == cmds[1:]
        shapes["off"]["state"] = "provisional"
        assert (on, off) not in POL.declared_pairs(NET)
        assert POL.judge(cmds, NET)["unproven"] == cmds[1:]


class TestAVerifiedRun:
    @pytest.mark.parametrize("rec,verified", [
        ({"kind": "command_plan", "state": "done", "outcome": "done"}, True),
        ({"kind": "command_plan", "state": "done", "outcome": "not_needed"}, False),
        ({"kind": "command_plan", "state": "rolled_back", "outcome": "rolled_back"}, False),
        ({"kind": "command_plan", "state": "refused", "outcome": "refused"}, False),
        ({"kind": "reload", "state": "done", "outcome": "done"}, False),
        (None, False)])
    def test_only_a_run_that_sent_and_verified(self, rec, verified):
        assert S.run_verified(rec) is verified


class TestVersions:
    def test_a_change_to_its_checks_is_a_new_version_the_old_kept(self, store):
        e = script(store)
        v1 = S.versions(stored(e["key"]))[0]
        got = edit(e, template=with_pair_check(stored(e["key"])["template"]))
        assert got["new_version"] is True
        vs = S.versions(stored(e["key"]))
        assert [v["version"] for v in vs] == [1, 2]
        assert vs[0]["digest"] == v1["digest"] != vs[1]["digest"]
        assert vs[1]["why"] == "commands, checks or verify changed"

    def test_its_words_alone_are_the_same_version_and_keep_it_automatic(self, store):
        e = script(store)
        got = edit(e, words="Recovers a port BPDU guard shut")
        assert got["new_version"] is False
        raw = stored(e["key"])
        assert [v["version"] for v in S.versions(raw)] == [1]
        assert raw["mode"] == "auto" and not raw.get("held_manual")

    def test_an_edit_opened_on_an_older_version_is_refused_naming_both(self, store):
        e = script(store)
        edit(e, template=with_pair_check(stored(e["key"])["template"]))
        with pytest.raises(S.Refused) as got:
            edit(e, version=1, words="again")
        assert "opened version 1, version 2 now" in str(got.value)

    def test_a_new_template_without_the_port_check_is_refused(self, store):
        e = script(store)
        t = copy.deepcopy(stored(e["key"])["template"])
        t["verify"] = t["verify"][:1]
        with pytest.raises(S.Refused) as got:
            edit(e, template=t)
        assert POL.PAIR_PRECONDITION["name"] in str(got.value)
        assert [v["version"] for v in S.versions(stored(e["key"]))] == [1]

    def test_a_run_names_the_version_current_when_it_started(self, store):
        e = script(store)
        edit(e, template=with_pair_check(stored(e["key"])["template"]))
        raw = stored(e["key"])
        assert S.version_at(raw, "2000-01-01T00:00:00Z") == 1
        assert S.version_at(raw, LATER) == 2


class TestAutomatic:
    def test_an_edit_of_its_checks_drops_it_to_manual_only_until_its_next_verified_run(
            self, store):
        e = script(store)
        assert stored(e["key"])["mode"] == "auto"
        edit(e, template=with_pair_check(stored(e["key"])["template"]))
        raw = stored(e["key"])
        assert raw["mode"] == S.MANUAL and raw["held_manual"]["version"] == 2
        assert raw["changes"][-1]["words"].endswith("Manual only until its next verified run")

    def test_an_edit_of_its_match_drops_it_to_manual_only_at_the_same_version(self, store):
        e = script(store)
        raw = stored(e["key"])
        got = S.edit_fix(e["key"], network=NET, version=1, name=raw["name"],
                         words=raw.get("words"), match=dict(MATCH, cause="port security"),
                         fills=raw["fills"], template=None, **WHO)
        assert got["new_version"] is False
        raw = stored(e["key"])
        assert raw["mode"] == S.MANUAL and raw["held_manual"]["version"] == 1
        assert "its match changed" in raw["changes"][-1]["words"]

    def test_set_automatic_waits_for_a_verified_run_of_the_new_version(self, store):
        e = script(store)
        edit(e, template=with_pair_check(stored(e["key"])["template"]))
        with pytest.raises(S.Refused) as got:
            S.promote(e["key"], **WHO)
        assert "version 2 has no verified run yet" in str(got.value)
        run_at(LATER, e["key"], outcome="not_needed")
        with pytest.raises(S.Refused):
            S.promote(e["key"], **WHO)
        run_at(LATER, e["key"])
        got = S.promote(e["key"], **WHO)
        raw = stored(e["key"])
        assert raw["mode"] == "auto" and "held_manual" not in raw
        assert raw["changes"][-1]["words"].startswith("set Automatic on version 2's verified run")
        assert got["key"] == e["key"]


class TestTheRights:
    def test_the_ai_changes_no_fix(self, store):
        e = script(store)
        with identity.as_ai("fixit-troubleshoot"), pytest.raises(S.Refused) as got:
            edit(e, words="the AI's words")
        assert "may not change a fix" in str(got.value)

    def test_a_fix_with_a_match_takes_the_self_healing_right(self, store):
        e = script(store)
        store["rights"].update(self_healing=[OTHER], admin=[PERSON])
        with pytest.raises(S.Refused):
            edit(e, words="a person without self-healing")
        store["rights"].update(self_healing=[PERSON], admin=[OTHER])
        assert edit(e, words="a person with self-healing")["new_version"] is False

    def test_a_new_fix_with_no_match_takes_the_admin_right(self, store):
        e = script(store)
        template = with_pair_check(stored(e["key"])["template"])
        kw = dict(name="Bounce a port", words="", match={}, fills={}, template=template)
        store["rights"].update(self_healing=[PERSON], admin=[OTHER])
        with pytest.raises(S.Refused):
            S.new_fix(NET, **kw, **WHO)
        store["rights"].update(admin=[PERSON])
        with identity.as_ai("assistant"), pytest.raises(S.Refused) as got:
            S.new_fix(NET, **kw, **WHO)
        assert "may not write a fix" in str(got.value)
        got = S.new_fix(NET, **kw, **WHO)
        assert stored(got["key"]).get("mode") is None, "no match: nothing fires it"

    def test_a_new_fix_with_a_match_starts_manual_only(self, store):
        e = script(store)
        template = with_pair_check(stored(e["key"])["template"])
        got = S.new_fix(NET, name="Recover BPDU ports", words="", match=MATCH,
                        fills=stored(e["key"])["fills"], template=template, **WHO)
        assert stored(got["key"])["mode"] == S.MANUAL
