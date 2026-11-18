"""Nothing that needs a person is only on Incidents (the operator, 2026-11-14: "Remove the "N
open" chip from Incidents in the sidebar. Needs attention is the one inbox and its badge the
one count. Make the rule a test: every open incident that needs a person appears on Needs
attention (healing ones as the Healing… card), so nothing is only on Incidents";
docs/UI_RULES.md, "No duplicate counts; status chips by exception"; provisional, operator
review pending).

**The rule, as a property:** for every incident whose own page says a person is needed
(`incident_page.status`'s *needs*, through `incident_page.page`), Needs attention as it is
computed now (`attention.needs_attention()`, every source, its windows as they ship) holds an
item about it: a row, or a row folded under one, whose link opens that incident's page
(`incident_page`, set by `attention._link_incident_pages` and `_link_stream_incidents`, the
one way an item names its incident).

**The population:** the planted incidents of tests/test_incidents_list_v2.py (the incident
page's fixtures, real captures: a heal rolled back, a can't-fix standing in dry run, a heal
done, a related incident watching) and of tests/test_incident_state.py (each by the heal
modules' own writers: a verified heal, a rolled-back one, a can't-fix standing, a proposal
nobody took, an incident only sighted). An incident nobody is needed for (fixed, watching)
is held to nothing here; that at least one planted incident needs a person is held, so the
rule is never vacuous.

**Measured 2026-11-14, when the rule was made a test:** a rolled-back heal and a can't-fix,
each still needing a person, were on Needs attention while new (an hour after: the test below)
and left it after `attention.CANT_FIX_DAYS` (7 days), so past that age they were only on
Incidents (the plants, dated 2026-09, are past it). C3620, decided the same day under the
Phase 7 mode: such an incident stays until it is resolved or acknowledged, with no age-out, so
the tests at any age hold.

**What it cannot see, stated:** a healing incident (its heal applying) needs nobody by the
page's state, and Needs attention's declared Healing… row is not built yet (CLAUDE.md, "A
Needs attention row names one action, except a declared healing row": not mechanised yet), so
"healing ones as the Healing… card" is not held here until that row lands; an item that
names its incident only in its words, not by the link, is not counted as about it.
"""
import pytest

from modules import incident_page as IP
from tests import test_incident_state as S
from tests import test_incidents_list_v2 as LV
from tests.test_heal_decide import lab  # noqa: F401  (the fixture `client` builds on)
from tests.test_heal_propose import measured  # noqa: F401  (a fixture)
from tests.test_incident_page import NET, client, no_host_addresses  # noqa: F401  (fixtures)
from tests.test_sdn_connections import networks  # noqa: F401  (the fixture `lab` builds on)


def items_about() -> dict:
    """{incident id: the Needs attention rows about it}, from the list computed now, every
    row and every row folded under one."""
    from modules import attention

    out = {}
    for top in attention.needs_attention()["rows"]:
        for r in [top] + list(top.get("folded") or []):
            iid = (r.get("incident_page") or {}).get("id")
            if iid:
                out.setdefault(iid, []).append(r["id"])
    return out


def needing(ids) -> list:
    """The planted incidents whose own page says a person is needed now."""
    return [i for i in ids if IP.page(NET, i, attention={})["state"] == "needs_person"]


def missing(ids) -> list:
    """Each planted incident that needs a person and has no Needs attention item, with its
    page's title and why it needs one."""
    held = items_about()
    out = []
    for iid in needing(ids):
        if iid not in held:
            found = IP.resolve(NET, iid)
            st = IP.status(found["incident"], found["entry"], found["decisions"])
            out.append((iid, IP.page(NET, iid, attention={})["title"], st["why"]))
    return out


class TestEveryIncidentThatNeedsAPersonIsOnNeedsAttention:
    def test_the_incidents_list_s_planted_incidents(self, client):  # noqa: F811
        docs = {n: LV._load(n) for n in ("healed", "failed", "busy")}
        LV.plant(list(docs.values()))
        ids = [docs["healed"]["page"], docs["failed"]["page"], docs["busy"]["page"],
               docs["busy"]["related"]]
        assert len(needing(ids)) >= 2, "the population holds an incident that needs a person"
        assert missing(ids) == [], ("an incident that needs a person is only on Incidents, "
                                    "not on Needs attention")

    def test_a_store_closed_incident_its_fix_never_confirmed(self, client):  # noqa: F811
        """C4084 (the operator, 2026-11-18: "an incident closes only on a healed outcome.
        'Closed but not confirmed' stays open and needs a person. Fix whichever page says
        otherwise, with a test"): the rolled-back heal its store closed before C3870
        (closed_unconfirmed.json, a real capture) read Needs a person by its page's rule, yet
        the Incidents list put it on Closed, "Closed, not confirmed", its page's header said so
        and Needs attention held no row for it. Now all three show it open and needing a
        person: on Open under Needs a person, its header Needs a person, and a row here."""
        from modules import incidents_list as L
        doc = LV._load("closed_unconfirmed")
        LV.plant([doc])
        iid = doc["page"]
        assert doc["incidents"][0]["state"] == "closed", "the store holds it closed"
        assert needing([iid]) == [iid]
        found = IP.resolve(NET, iid)
        st = IP.status(found["incident"], found["entry"], found["decisions"])
        assert (st["state"], st["words"], st["needs"]) == ("needs_person", "Needs a person",
                                                           True), st
        open_rows = {r["id"]: (g["key"], r) for g in L.page(NET, "open")["groups"]
                     for r in g["rows"]}
        assert open_rows.get(iid, ("",))[0] == "needs_person", sorted(open_rows)
        assert iid not in {r["id"] for g in L.page(NET, "closed")["groups"] for r in g["rows"]}
        assert missing([iid]) == [], ("an incident that needs a person is only on Incidents, "
                                      "not on Needs attention")

    def test_an_incident_at_a_golden_that_departs_from_intent(self, client):  # noqa: F811
        """C3910 (the operator's ruling 0, 2026-11-18: "Keep the interim (c)", a departing
        golden is a Tier 3 can't-fix the AI investigates): an incident settled at its golden,
        that golden departing from committed intent and no symptom, was decided "nothing to
        heal" and closed. Decided by the heal's own decision job now, it is a can't-fix that
        stands open, and its page, the Incidents list's Open tab and Needs attention all show
        it needing a person (C4084's rule: only a healed outcome closes an incident)."""
        from modules import incidents_list as L
        from tests import test_incident_page as T
        from tests.test_heal_policy import T0

        T.settle(T.GOLDEN, triggers=[T.CFG], how="at_golden", claim=False)
        from modules.heal import decisions

        (ran,) = T.DC.run(NET, now=T0, sources=T.Fake(T.GOLDEN, state="departs"))["decided"]
        iid = ran["incident"]
        d = decisions.find(NET, ran["decision"])
        assert (d["outcome"], d["tier"]) == ("cant_fix", 3), d
        assert needing([iid]) == [iid]
        open_rows = {r["id"]: g["key"] for g in L.page(NET, "open")["groups"]
                     for r in g["rows"]}
        assert open_rows.get(iid) == "needs_person", open_rows
        assert missing([iid]) == [], ("an incident that needs a person is only on Incidents, "
                                      "not on Needs attention")

    @pytest.mark.parametrize("name", sorted(S.PLANTS))
    def test_the_incident_state_tests_planted_incidents(self, client, measured, name):  # noqa: F811
        plant, state = S.PLANTS[name]
        iid = plant()
        # The population as its records put it (test_incident_state's own table): a plant that
        # needs a person is found as needing one, so the rule is never held over nothing.
        assert (needing([iid]) == [iid]) == (state == "needs_person"), (name, state)
        assert missing([iid]) == [], ("an incident that needs a person is only on Incidents, "
                                      "not on Needs attention")

    @pytest.mark.parametrize("name", sorted(n for n, (_p, s) in S.PLANTS.items()
                                            if s == "needs_person"))
    def test_an_hour_after_it_was_planted(self, client, measured, monkeypatch, name):  # noqa: F811
        """The same rule an hour after each plant (Needs attention's clock moved there; the
        plants are dated 2026-09): an item that needs a person is there while it is new. The
        tests above hold it at every age, as the incident still needs a person."""
        from modules import attention
        from tests.test_heal_policy import T0

        iid = S.PLANTS[name][0]()
        assert needing([iid]) == [iid], name
        monkeypatch.setattr(attention.time, "time", lambda: T0 + 3600)
        assert missing([iid]) == [], ("an incident that needs a person is only on Incidents, "
                                      "not on Needs attention")
