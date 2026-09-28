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
    "GET /health": ("scripts/nmas-deploy",
                    "the deploy gate: waits for the RESTARTED process to "
                    "answer with the target commit"),
    "GET /identity/status": ("docs/NSOT_AUTHORIZATION.md",
                             "the end-to-end identity diagnostic, reached "
                             "directly: one that hides behind the page is "
                             "useless when identity breaks"),
    "GET /clab/sync_targets": ("scripts/nmas-clab-targets",
                               "the clab host's sync asks for its map; it "
                               "refuses rather than guessing when it cannot"),
    "POST /freshness/gate": ("scripts/nmas-oxidized-freshness",
                             "the sanitiser's pre-write gate (exit 0/1/2)"),
    "GET /favicon.ico": (None, "requested by browsers by convention; no page "
                               "references it and none needs to"),
}

A, B, C, D = "(a) no entry point", "(b) credentials", \
    "(c) never shown", "(d) superseded or dead"

#: (group, reason). Each must leave when it becomes reachable.
KNOWN_UNREACHABLE = {
    # (a) Phase 3 and later features with no entry point.
    "POST /templatize/extract/<path:hostname>": (A, "seed intent: extract, review, commit; Device, Actions (7.3)"),
    "GET /templatize/staged": (A, "seed intent: what extraction staged; Device, Actions (7.3)"),
    "POST /templatize/commit/<path:hostname>": (A, "seed intent: the reviewed commit; Device, Actions (7.3)"),
    "GET /templatize/rendered/<path:hostname>": (A, "the render, for reading; Device, Overview (7.3)"),
    "GET /templatize/committed": (A, "the list of devices with committed intent; Fleet (7.4)"),
    "GET /templatize/report": (A, "round-trip coverage for the fleet; Source of truth, Templates (7.6)"),
    "POST /templatize/report": (A, "the same coverage report with a body; Source of truth, Templates (7.6)"),
    "GET /templatize/rolled-back": (A, "rollback-blocked devices; a Needs attention row (7.2)"),
    "GET /templatize/rolled-back/retries": (A, "the retry record; Device, History (7.3)"),
    "POST /templatize/rolled-back/<path:hostname>/retry": (A, "the ONLY way to re-send a blocked change; Device, Actions (7.3)"),
    "POST /templatize/committed/<path:hostname>/revert": (A, "revert one intent commit (the documented way out of a rollback's intent); Device, Actions (7.3). Counted reachable until 2026-09-27 because the editor's own fetch shared its prefix"),
    "POST /templatize/bulk/preview": (A, "bulk intent (P.1b), a GUI-owned task; Fleet, selection (7.4)"),
    "POST /templatize/bulk/apply": (A, "bulk intent (P.1b), a GUI-owned task; Fleet, selection (7.4)"),
    "POST /templates/revoke/<path:rel_path>": (A, "withdraw an approval with a reason; Source of truth, Templates (7.6)"),
    "POST /templates/bindings": (A, "which template a device uses; Source of truth, Templates (7.6)"),
    "GET /templates/seed_status": (A, "seed status (C6); Source of truth, Templates (7.6)"),
    "GET /freshness/authorisations": (A, "see Oxidized-divergence authorisations; Source of truth (7.6)"),
    "POST /freshness/authorise": (A, "authorise one Oxidized divergence (the CLI also can); Source of truth (7.6)"),
    "GET /jobs/health": (A, "job, image and pool health; Needs attention (7.2)"),
    "POST /inventory/source/<path:list_name>": (A, "set a network's inventory source: the panel only READS it; Fleet, Networks (7.4)"),
    "POST /remote/adopt": (A, "connect a remote; Versions (7.5)"),
    # (b) Credential management: the whole resolution chain is HTTP-only.
    "GET /inventory/credentials/profiles": (B, "credential profiles; Source of truth, Credentials (7.6)"),
    "POST /inventory/credentials/profiles": (B, "credential profiles; Source of truth, Credentials (7.6)"),
    "DELETE /inventory/credentials/profiles/<path:name>": (B, "credential profiles; Source of truth, Credentials (7.6)"),
    "POST /inventory/credentials/copy-inherited/<path:list_name>": (B, "decouple a list before its source is deleted; Source of truth, Credentials (7.6)"),
    "GET /inventory/dependents/<path:list_name>": (B, "which lists depend on a credential list; Source of truth, Credentials (7.6)"),
    # (c) State that exists and is never shown.
    "GET /list/drift_status": (C, "superseded by /drift/status, which the drift panel reads; removed in 7.8"),
    "GET /backup_stats": (C, "backup statistics, never drawn; removed in 7.8 unless Versions draws them"),
    "GET /configure/audit/<config_id>": (C, "pipeline audit records, never drawn; Versions (7.5) or removed in 7.8"),
    "GET /configure/audit_latest": (C, "pipeline audit records, never drawn; Versions (7.5) or removed in 7.8"),
    "GET /list/variables": (C, "the CSV-era variable store: CUT by the feature audit; removed in 7.8"),
    "POST /list/variables": (C, "the CSV-era variable store: CUT by the feature audit; removed in 7.8"),
    "DELETE /list/variables/<key>": (C, "the CSV-era variable store: CUT by the feature audit; removed in 7.8"),
    "POST /list/variables/discover": (C, "the CSV-era variable store: CUT by the feature audit; removed in 7.8"),
    "GET /list/compliance_policy": (C, "compliance as strings: CUT, absorbed into CI (feature audit); removed in 7.8"),
    "POST /list/compliance_policy": (C, "compliance as strings: CUT, absorbed into CI (feature audit); removed in 7.8"),
    # (d) Superseded, duplicate or dead.
    "GET /list/golden_configs": (D, "the legacy enumerator's route: on the audit's CUT list; removed in 7.8"),
    "GET /ai/events": (D, "on the audit's CUT list; removed in 7.8"),
    "POST /ai/events/clear": (D, "on the audit's CUT list with /ai/events; removed in 7.8"),
    "GET /ai/tool_cache_snapshot": (D, "on the audit's CUT list; removed in 7.8"),
    "POST /bulk_clear/<operation_id>": (D, "on the audit's CUT list; removed in 7.8"),
    "POST /drift/check": (D, "the async drift run: the panel uses /drift/check/sync; on the audit's CUT list"),
    "GET /ai/report/<path:filename>": (D, "serves report files, and the AI tools that wrote them went in P.3 step 8; no caller"),
    "POST /ai/restart": (D, "no caller anywhere in the repository (measured 2026-09-27)"),
    "POST /server/restart": (D, "no caller anywhere in the repository (measured 2026-09-27); section 1.2 excluded it as non-GUI without naming a consumer"),
    "GET /drift/settings": (D, "a duplicate read: the drift panel takes its interval and toggle from /drift/status"),
    "GET /device_lists": (D, "the list of lists as JSON: the page renders it server-side; on the audit's CUT list"),
    "POST /golden/migrate/plan": (D, "the same dry-run READ as GET, with a JSON body; nothing sends it"),
    "POST /templates/preview/<path:hostname>": (D, "the same capture-only READ as GET, with a JSON body; nothing sends it"),
    # The six the GUI doc called "the AI agent's NetBox reads, need no UI".
    # Measured: nothing in the repository calls them, the agent included (it
    # calls netbox_client directly). A claimed consumer, checked and absent.
    "GET /netbox/query/device": (D, "claimed as the AI agent's, and nothing calls it (measured); removed in 7.8"),
    "GET /netbox/query/devices": (D, "claimed as the AI agent's, and nothing calls it (measured); removed in 7.8"),
    "GET /netbox/query/interfaces": (D, "claimed as the AI agent's, and nothing calls it (measured); removed in 7.8"),
    "GET /netbox/query/ip": (D, "claimed as the AI agent's, and nothing calls it (measured); removed in 7.8"),
    "GET /netbox/query/prefixes": (D, "claimed as the AI agent's, and nothing calls it (measured); removed in 7.8"),
    "GET /netbox/query/tunnels": (D, "claimed as the AI agent's, and nothing calls it (measured); removed in 7.8"),
}

#: The allowlist's size, pinned. It may only go DOWN: lower it in the same
#: commit that gives a route its entry point or removes it. The GUI doc set
#: the first ceiling at 54 by a coarser method (per path, not per method);
#: this is the measurement, and it lands on 54 by a different route: the
#: per-method split found three halves the path check counted as reached.
# 54 -> 55 on 2026-09-27, and a CORRECTION rather than a loosening: intent
# revert never had an entry point, and was counted as reached because the
# editor's `'/templatize/committed/' + host` matched its stem. A route's
# words after its converter must now appear near the reference.
CEILING = 55


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
        assert reach["_corpus_size"] > 500_000, reach["_corpus_size"]

    def test_anchors(self, reach):
        """Known answers in each direction, including each way a reference is
        found: a fetch literal, a url_for in a form, and a per-method split."""
        pairs = _pairs(reach)
        assert pairs["POST /deploy/apply"] is True
        assert pairs["GET /onboard/pending"] is True
        assert pairs["POST /add_quick_action"] is True          # url_for, device page
        assert pairs["POST /drift/settings"] is True            # a mixed path, write half
        assert pairs["POST /templatize/rolled-back/<path:hostname>/retry"] is False
        assert pairs["POST /list/variables"] is False           # its GET half is no proof


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

    def test_intent_revert_is_not_reached(self, reach):
        assert reach["POST /templatize/committed/<path:hostname>/revert"] is False

    def test_an_assembled_url_still_reaches_its_route(self, reach):
        """Control: `/ai/approvals/${id}/${action}` reaches both actions."""
        for pair in ("POST /ai/approvals/<entry_id>/approve",
                     "POST /ai/approvals/<entry_id>/reject",
                     "POST /templatize/committed/<path:hostname>"):
            assert reach[pair] is True, pair
