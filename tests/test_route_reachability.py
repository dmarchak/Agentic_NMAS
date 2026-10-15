"""Stage 7.0 (1): every route is reachable from a page, non-GUI by design
with a named consumer, or allowlisted with a reason. Exactly one each.

`test_blueprint_reachability.py` asks whether a BLUEPRINT has one route the
page reaches, so an unreachable route inside a reachable blueprint is
invisible to it: `/templatize/rolled-back/<host>/retry`, the only way out of
a state the GUI can put a device into, passed that check for as long as the
editor fetched `/templatize/committed/`. This asks per route, and per METHOD
where one path carries both a read and a write (`tests/route_references.py`
says how a reference and its method are read, and what it cannot see).

Measured 2026-09-27: 212 routes, 218 (method, route) pairs, 59 unreached.
Five are non-GUI with a consumer that references them; the other 54 are the
allowlist, each with its group from NSOT_STAGE7_GUI.md section 1.2 and the
home NSOT_STAGE7_PLAN.md section 6 gives it:

* (a) a feature with no entry point: the serious ones;
* (b) credential management;
* (c) state that exists and is never shown;
* (d) superseded, duplicate or dead: removed in 7.8, or never had a caller.

Measured 2026-10-15: the allowlist is EMPTY. 7.8 removed its last sixteen, and every
route is now reached by a page or non-GUI with a named consumer.

**The allowlist only shrinks.** It is compared with the unreachable set
EXACTLY, in both directions (a new unreachable route fails, and so does an
entry that has become reachable), and its size is pinned by `CEILING`, so
adding an entry is an edit that visibly raises a number.
"""

import os

import pytest

from tests.route_references import ROOT, reachability

#: Reached by something other than a page, BY DESIGN. Each names a file that
#: references the route, and a test checks it does, so the reason cannot go
#: stale unnoticed. ``None`` only where no file can: a browser requests
#: `/favicon.ico` by convention, and that is the reason.
NON_GUI = {
    "GET /clab/sync_targets": ("lab/clab-sync/clab-targets",
                               "the clab host's sync asks for its map; it "
                               "refuses rather than guessing when it cannot"),
    "POST /jobs/finished": ("scripts/nmas-job-finished",
                            "systemd's OnSuccess/OnFailure for each host job: read job "
                            "health now, not at the reader's next run"),
    # The operator, 2026-10-02: a script that restarts devices (the lab redeploy) declares
    # its planned window through the product's API, after its typed confirmation and before
    # it touches the lab, so the record names a verified identity. The redeploy script is
    # queued work; the host command, the same writer for a person on the host, names it.
    "POST /restarts/planned": ("scripts/nmas-planned-restart",
                               "a script that restarts devices declares its planned window "
                               "here, as a verified identity (the lab redeploy)"),
    # A GUI way in carried as DATA, which a scan of rendered pages cannot see:
    # the heartbeat check's Needs attention row, its ONE entry point (the
    # operator, 2026-10-02: never a tab), built in job_health.
    "GET /v2/monitoring/heartbeat": ("modules/job_health.py",
                                     "the heartbeat check's Needs attention action, "
                                     "built by job health; never a tab"),
    # CONCURRENCY_AUDIT R5: the terminal deploy asks before it restarts the service.
    "GET /health/operations": ("scripts/nmas-deploy",
                               "nmas-deploy refuses to restart the service while an "
                               "operation holds a device (exit 10), as Update's gate does"),
    # Today's status bar read both until it left at 7.8 (2026-10-15); kept as the operator's
    # diagnostics, a question put to the operator the same day (whether either goes).
    "GET /identity/status": ("docs/LESSONS.md",
                             "the end-to-end identity diagnostic: does the tunnel forward the "
                             "assertion and does the app verify it; not gated by identity"),
    "GET /settings/integrations/status": ("docs/DEPLOY_LINUX.md",
                                          "a new install's Verify step reads every "
                                          "integration's stored state with curl"),
    "GET /favicon.ico": (None, "requested by browsers by convention; no page "
                               "references it and none needs to"),
}

A, B, C, D = "(a) no entry point", "(b) credentials", \
    "(c) never shown", "(d) superseded or dead"

#: (group, reason). Each must leave when it becomes reachable. Empty since 2026-10-15: the
#: last sixteen, each with a v2 home or superseded, were removed at 7.8 (docs/CUTOVER.md,
#: "Removed at 7.8"). A route no page reaches is now given an entry point, declared non-GUI
#: with its consumer, or removed; an entry here is the last resort and raises CEILING.
KNOWN_UNREACHABLE: dict = {}

#: The allowlist's size, pinned. It may only go DOWN: lower it in the same
#: commit that gives a route its entry point or removes it. The GUI doc set
#: the first ceiling at 54 by a coarser method (per path, not per method);
#: this is the measurement, and it lands on 54 by a different route: the
#: per-method split found three halves the path check counted as reached.
# 54 -> 55 on 2026-09-27, and a CORRECTION rather than a loosening: intent
# revert never had an entry point, and was counted as reached because the
# editor's `'/templatize/committed/' + host` matched its stem. A route's
# words after its converter must now appear near the reference.
# 49 -> 47 (2026-10-02): /ai/restart and /server/restart removed (CONCURRENCY_AUDIT R5).
# 47 -> 45 (2026-10-08): /freshness/authorisations and /freshness/authorise removed (Phase 3).
# 45 -> 39 (2026-10-11): the six /netbox/query routes removed (7.8, the first family).
# 39 -> 37 (2026-10-11): /templatize/report's GET and POST removed (7.8).
# 37 -> 32 (2026-10-12): the credential profile JSON routes and /inventory/dependents removed
# (7.8; Credentials › Profiles is their home).
# 32 -> 26 (2026-10-12): /list/variables (4) and /list/compliance_policy (2) removed (7.8).
# 26 -> 24 (2026-10-12): the list data routes (7.8); 24 -> 23: POST /golden/migrate/plan (7.8).
# 23 -> 21 (2026-10-12): /configure/audit_latest and /configure/audit/<id> removed with Configure (7.8).
# 21 -> 17 (2026-10-14): /ai/events (GET and POST clear), /ai/tool_cache_snapshot and
# /ai/report removed with the AI family (D15).
# 17 -> 16 (2026-10-14): GET /backup_stats removed with today's Backups (7.8, C632).
# 16 -> 0 (2026-10-15): the sixteen no page reached, removed at 7.8: /templatize/committed,
# /templatize/rolled-back and its /retries, /templatize/bulk/preview and /apply,
# /templates/revoke/<path>, POST /templates/bindings, /templates/seed_status, /jobs/health,
# POST /inventory/source/<list>, /remote/adopt, /bulk_clear/<id>, POST /drift/check,
# GET /drift/settings, GET /device_lists and POST /templates/preview/<host>.
CEILING = 0


@pytest.fixture(scope="module")
def reach():
    mp = pytest.MonkeyPatch()
    try:
        import app as A

        out = reachability(A, mp)
    finally:
        mp.undo()
    return out


def _pairs(reach):
    return {k: v for k, v in reach.items() if not k.startswith("_")}


class TestThePopulation:
    def test_the_scan_saw_the_app_and_the_pages(self, reach):
        """Floors: a scan that found nothing passes every check below. The
        GUI doc's floor was 220 routes, before P.4 removed Jenkins; there are
        212 routes (218 method pairs) now, measured."""
        assert len(_pairs(reach)) >= 210, len(_pairs(reach))
        # 450 kB: 497,320 bytes on 2026-10-15, after today's Settings modal's two scripts and
        # the status bar's left (7.8).
        assert reach["_corpus_size"] > 450_000, reach["_corpus_size"]

    def test_anchors(self, reach):
        """Known answers in each direction, including each way a reference is
        found: a fetch literal, a url_for in a form, and a per-method split."""
        pairs = _pairs(reach)
        assert pairs["POST /deploy/apply"] is True
        assert pairs["GET /onboard/pending"] is True
        assert pairs["POST /run_command/<ip>"] is True          # url_for, device page
        # A mixed path, write half (the editor's save beside its open). Before 2026-10-15
        # this anchor was POST /drift/settings, single-method since its GET left at 7.8.
        assert pairs["POST /templatize/committed/<path:hostname>"] is True
        # Unreached, the answer each way: a non-GUI route only a script posts to. The
        # unreached allowlist's own anchors (bulk intent's JSON apply, and inventory source's
        # POST, whose GET half was no proof) left at 7.8 on 2026-10-15; the per-method split
        # is driven on a planted page below.
        assert pairs["POST /jobs/finished"] is False
        # The device page's Actions menu loop (`url_for('device_v2.' ~ op)`, one row per op):
        # Seed's card is reached only from its row there (2026-10-03).
        assert pairs["GET /v2/device/<name>/seed"] is True

    def test_a_read_of_a_mixed_path_is_no_proof_of_its_write(self):
        """The per-method split on a planted page, since no shipped mixed path has an
        unreached half left: a page that READS a path reaches its GET, never its POST; the
        same fetch sent as a POST reaches the POST (the control)."""
        from tests.route_references import path_references

        rule = "/inventory/source/<path:list_name>"
        read = "fetch(`/inventory/source/${encodeURIComponent(listName)}`);"
        assert path_references(read, rule, True) == {"GET"}
        write = read.replace(");", ", {method: 'POST'});")
        assert path_references(write, rule, True) == {"POST"}


class TestTheThreeStates:
    def test_every_unreachable_pair_is_classified(self, reach):
        unreached = {k for k, v in _pairs(reach).items() if not v}
        new = sorted(unreached - set(KNOWN_UNREACHABLE) - set(NON_GUI))
        assert new == [], (
            f"no page reaches these, and they are not declared: {new}. Give "
            "each an entry point, or declare it non-GUI with its consumer, or "
            "(last) allowlist it with its group and a reason.")

    def test_no_ghosts(self, reach):
        """An entry that is now reachable must leave, or the list stops
        describing anything."""
        pairs = _pairs(reach)
        ghosts = sorted(k for k in KNOWN_UNREACHABLE if pairs.get(k) is not False)
        assert ghosts == [], f"reachable now, or gone: remove from KNOWN_UNREACHABLE: {ghosts}"

    def test_no_route_is_in_two_states(self, reach):
        pairs = _pairs(reach)
        assert not set(KNOWN_UNREACHABLE) & set(NON_GUI)
        both = sorted(k for k in NON_GUI if pairs.get(k))
        assert both == [], f"a page reaches these, so they are not non-GUI: {both}"

    def test_the_allowlist_is_at_its_ceiling(self):
        assert len(KNOWN_UNREACHABLE) <= CEILING
        assert len(KNOWN_UNREACHABLE) == CEILING, (
            f"the allowlist shrank to {len(KNOWN_UNREACHABLE)}: lower CEILING "
            "to match in the same commit, so the next addition is visible")

    def test_every_entry_has_a_group_and_a_reason(self):
        for key, (group, reason) in KNOWN_UNREACHABLE.items():
            assert group in (A, B, C, D), key
            assert len(reason) >= 30, key


class TestNonGuiConsumers:
    def test_each_named_consumer_references_its_route(self):
        """The reason cannot go stale unnoticed: a consumer that stops
        calling the route turns this red."""
        from tests.route_references import stem

        for key, (consumer, reason) in NON_GUI.items():
            assert len(reason) >= 30, key
            if consumer is None:
                continue
            path = key.split(" ", 1)[1]
            text = open(os.path.join(ROOT, consumer), encoding="utf-8").read()
            assert stem(path) in text, f"{consumer} does not reference {path}"

    def test_only_one_consumer_cannot_be_checked(self):
        assert sum(1 for c, _ in NON_GUI.values() if c is None) <= 1


class TestTailWordsAfterAConverter:
    """A reference to a route's STEM is not a reference to every route under
    it: `/templatize/committed/<h>/revert` was counted reached by the
    editor's `'/templatize/committed/' + host` (found by the result survey,
    2026-09-27). Anchored both ways, from the shipped pages."""

    def test_a_stem_alone_does_not_reach_a_route_with_tail_words(self):
        """The shipped example is gone (the revert route was replaced by
        `/templatize/revert/*` in 7.3, and every route left under the
        editor's stem is genuinely reached), so the property is driven on a
        planted page: the editor's own fetch shape, and the same with its
        tail word (the control)."""
        from tests.route_references import path_references

        rule = "/templatize/committed/<path:hostname>/revert"
        stem_only = "fetch('/templatize/committed/' + encodeURIComponent(h), {method: 'POST'})"
        assert path_references(stem_only, rule, True) == set()
        with_tail = stem_only.replace("(h)", "(h) + '/revert'")
        assert path_references(with_tail, rule, True), "the control: the tail word is read"

    def test_an_assembled_url_still_reaches_its_route(self, reach):
        """Control: a URL assembled from placeholders reaches each action its tail word names
        nearby, in the shape of the approval card's `/ai/approvals/${id}/${action}` (it left
        with the AI family, D15, and no page assembles one like it now): 'approve' a few
        lines above, 'reject' about 2,500 characters away."""
        from tests.route_references import path_references

        corpus = ("act('approve');\nfetch(`/queue/${id}/${action}`, {method: 'POST'});\n"
                  + " " * 2500 + "act('reject');")
        for rule in ("/queue/<entry_id>/approve", "/queue/<entry_id>/reject"):
            assert path_references(corpus, rule, True) == {"POST"}, rule
        assert path_references(corpus, "/queue/<entry_id>/revert", True) == set()
        assert reach["POST /templatize/committed/<path:hostname>"] is True
