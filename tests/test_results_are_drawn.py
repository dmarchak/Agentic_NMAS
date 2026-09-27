"""7.1 step 1: an action that changes a device or the record shows its RESULT
where a person can read it again.

**The rule this encodes** (the operator, 2026-09-27): *a check that verifies
drawn fields are correct cannot see a field nobody draws.* The
payload-to-render check proves each key a renderer reads is carried. It
could not see C85: C8 fixed a partial NetBox import reading as clean, the
fix landed in the stored summary, and the sync card still reads only
`failed` and draws green. The field was drawn nowhere rather than drawn
wrongly, which is `/jobs/health`'s original shape.

**The population is the gate table, not a list somebody keeps**: every
endpoint gated `confirm` (sends to a device), `approve` (changes the record)
or `publish_remote`. A new gated route fails here until it is placed. The
result survey (NSOT_STAGE7_PLAN.md, "7.1 reshaped") read each handler by
hand: none of the 41 had a screen where its result could be read again.

Each member is in exactly one place:
- ``RESULT_COMPONENT``: drawn by the result component, re-readable through
  its record. Empty today, and every later 7.1 step moves routes into it;
- ``TOAST_ENOUGH``: the operator's bar is that the action changes nothing
  durable AND has no operands worth re-reading. Anything that writes a
  commit, touches a device or produces a record fails it by construction,
  and every gate kind in this population does one of those, so an entry
  here is REFUSED. The set exists so the bar is written down and tested,
  not as a place to put things;
- ``PENDING``: measured today, and it only shrinks;
- ``NO_GUI``: no page sends it, the same fact the reachability test records.
  The result rule applies once it has one.

**Colour is part of the result** (the operator): a green toast on a partial
success is a false statement in a different medium. ``FALSE_GREEN`` pins
the known instances by the literal they draw, so fixing one fails its entry
until it is removed. ``UNESCAPED`` pins the first XSS-shaped finding in the
tool (hostnames and reasons interpolated into toast HTML). Escaping every
field in ONE renderer closes the class rather than the instance.

What this cannot see, stated so it is not read as seen: whether a drawn
result is CORRECT (the payload-to-render check's job), and a false green
in code nobody has listed. The lists are the measured instances, and the
component is what stops new ones.
"""

import os

import pytest

from modules.route_gates import GATES

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KINDS = ("confirm", "approve", "publish_remote")

#: Drawn by the result component (7.1 step 2), with its record re-readable
#: (step 3): {endpoint: (the shipped file, the function that draws the
#: result, the route that reads the record back)}. Checked from source.
RESULT_COMPONENT = {
    "deploy.apply": ("static/js/gen/partials__deploy_wizard.1.js", "_renderDeployResult",
                     "deploy.receipts_read"),
    "golden.restore_apply": ("static/js/gen/partials__golden_repo.3.js", "_showRestoreResult",
                             "deploy.receipts_read"),
    # The import runs on a thread; its result is the stored summary, drawn on
    # the sync card whenever the NetBox tab is read (C85).
    # Capture (7.1 step 4): Save All is its whole-fleet form, and the one-click
    # route it replaced is gone. The record read back is the golden history.
    "golden.capture_apply": ("static/js/nmas_capture.js", "previewCapture", "golden.history"),
    "netbox_safety.apply_import": ("static/js/gen/index.4.js", "loadNetboxTab", "netbox_status"),
    "netbox_safety.apply_import_all": ("static/js/gen/index.4.js", "loadNetboxTab",
                                       "netbox_status"),
}

#: The bar: changes nothing durable AND has no operands worth re-reading.
TOAST_ENOUGH = {}

#: Measured 2026-09-27, each handler read by hand. Only shrinks.
PENDING = {
    # -- drawn in place, gone when the window closes or the page moves on --
    "bulk_execute": "the bulk results modal, until closed",
    "bulk_delete_file": "the bulk results modal, until closed",
    "bulk_tftp_upload": "the bulk results modal, until closed",
    "run_command": "the device page re-rendered with the output",
    "save_config": "the device page re-rendered with the output",
    "save_to_startup": "the device page re-rendered with the output",
    "delete_file": "the device page re-rendered",
    "upload_file": "the device page re-rendered",
    "ai_chat": "the chat stream (Stage 8 decides what the agent's record is)",
    "golden_configs_auto_create": "a result panel, until the next action",
    "templatize.edit_committed": "the editor's status line names the commit",
    "remote.push": "the remote panel's output box",
    "remote.auto_push": "the remote panel's output box",
    "remote.acknowledge": "the remote panel's output box",
    # -- a toast, gone in seconds --
    "onboard.verify": "a toast on success (the failure IS drawn)",
    "onboard.abandon": "a toast; what it removed is not shown",
    "onboard.create": "a toast, and a false one: 'Device onboarded.' after phase 1 (C86)",
    "bulk_reload": "a toast",
    "ai_agent_run": "nothing: the response is never read (the agent is off)",
    "ai_approval_approve": "a toast; the commit an approval makes is never shown",
    "ai_approval_reject": "a toast",
    "ai_approval_approve_all": "a toast",
    "netbox_safety.apply_removal": "a toast with a count; what was removed is not shown",
    "refresh_hostnames": "a toast, then a page reload",
    "templates.approve": "a toast carrying the per-device evidence",
    "templates.write_template": "a toast",
    "remote.verify_write": "a toast, then the panel reloads",
}

#: No page sends these (test_route_reachability.KNOWN_UNREACHABLE).
NO_GUI = {
    "freshness.authorise", "templates.revoke_approval", "templates.save_bindings",
    "templatize.bulk_apply", "templatize.commit_extraction",
    "templatize.retry_rolled_back", "templatize.revert_committed", "remote.adopt",
}

#: (file, the literal that draws success unearned) -> reason. Only shrinks.
FALSE_GREEN = {
    ("static/js/gen/partials__onboard_wizard.1.js",
     "showToast(d.ok ? 'Device onboarded.'"):
        "Create: a success toast asserting the outcome of phase 2, which "
        "has not happened (C86)",
}

#: (file, the unescaped interpolation) -> where. Only shrinks.
UNESCAPED = {
    ("templates/index.html", "${x.hostname}: ${x.reason}"):
        "Auto-Create's result: hostnames and failure reasons into HTML",
}

CEILINGS = {"PENDING": 28, "FALSE_GREEN": 1, "UNESCAPED": 1}


def _population():
    return {ep for ep, g in GATES.items() if g.kind in KINDS}


def _read(rel):
    return open(os.path.join(ROOT, rel), encoding="utf-8").read()


def toast_refusals(toast_enough: dict) -> list:
    """Every TOAST_ENOUGH entry the bar refuses, with why."""
    out = []
    for ep, reason in toast_enough.items():
        kind = getattr(GATES.get(ep), "kind", "")
        if kind in KINDS:
            out.append(f"{ep}: a `{kind}` action writes a commit, touches a device "
                       "or produces a record, so a toast is never enough")
        elif len((reason or "").strip()) < 20:
            out.append(f"{ep}: no reason stated")
    return out


class TestEveryResultIsPlaced:
    def test_the_population_is_the_gate_table(self):
        pop = _population()
        assert len(pop) >= 40, len(pop)           # measured 41 on 2026-09-27
        assert {GATES[e].kind for e in pop} == set(KINDS)

    def test_every_member_is_in_exactly_one_place(self):
        places = {"RESULT_COMPONENT": set(RESULT_COMPONENT), "TOAST_ENOUGH": set(TOAST_ENOUGH),
                  "PENDING": set(PENDING), "NO_GUI": set(NO_GUI)}
        pop = _population()
        unplaced = sorted(pop - set().union(*places.values()))
        assert unplaced == [], f"a gated action with no result placement: {unplaced}"
        for a in places:
            for b in places:
                if a < b:
                    assert not places[a] & places[b], (a, b, places[a] & places[b])

    def test_no_ghosts(self):
        """A placed endpoint that is no longer gated (or no longer exists)
        must leave its list."""
        pop = _population()
        for name, keys in (("RESULT_COMPONENT", RESULT_COMPONENT), ("TOAST_ENOUGH", TOAST_ENOUGH),
                           ("PENDING", PENDING), ("NO_GUI", NO_GUI)):
            assert set(keys) <= pop, (name, sorted(set(keys) - pop))

    def test_the_lists_only_shrink(self):
        assert len(PENDING) <= CEILINGS["PENDING"]
        assert len(FALSE_GREEN) <= CEILINGS["FALSE_GREEN"]
        assert len(UNESCAPED) <= CEILINGS["UNESCAPED"]


class TestTheToastBar:
    def test_no_member_of_this_population_may_be_toast_enough(self):
        assert toast_refusals(TOAST_ENOUGH) == []

    def test_the_bar_refuses_a_gated_action(self):
        """Control: the bar is live, not an empty dict passing vacuously."""
        refused = toast_refusals({"golden.restore_apply": "the toast says how many devices"})
        assert refused and "never enough" in refused[0]


class TestNoGuiIsTheReachabilityFact:
    def test_each_no_gui_route_is_unreachable_there_and_back(self):
        import app as A
        from tests.test_route_reachability import KNOWN_UNREACHABLE

        by_endpoint = {}
        for rule in A.app.url_map.iter_rules():
            for m in rule.methods - {"HEAD", "OPTIONS", "GET"}:
                by_endpoint.setdefault(rule.endpoint, set()).add(f"{m} {rule.rule}")
        unreachable_gated = {ep for ep in _population()
                             if by_endpoint.get(ep, set()) & set(KNOWN_UNREACHABLE)}
        assert unreachable_gated == NO_GUI, (sorted(unreachable_gated ^ NO_GUI))
        assert len(NO_GUI) >= 7


class TestColourAndEscaping:
    """Pinned by the literal each draws: fixing one fails its entry until the
    entry is removed, so the lists cannot keep ghosts."""

    @pytest.mark.parametrize("rel,literal", sorted(FALSE_GREEN))
    def test_each_false_green_is_still_there(self, rel, literal):
        assert literal in _read(rel), f"fixed? remove it from FALSE_GREEN: {literal}"

    @pytest.mark.parametrize("rel,literal", sorted(UNESCAPED))
    def test_each_unescaped_interpolation_is_still_there(self, rel, literal):
        assert literal in _read(rel), f"fixed? remove it from UNESCAPED: {literal}"


class TestTheComponentDrawsTheseResults:
    """Evidence, from source, for each RESULT_COMPONENT entry: the function
    draws the component's result, and the record has a reader."""

    def test_each_entry_draws_the_component_and_can_be_read_again(self):
        import app as A
        from tests.payload_render import lift

        endpoints = {r.endpoint for r in A.app.url_map.iter_rules()}
        assert len(RESULT_COMPONENT) >= 2
        for ep, (rel, fn, reader) in RESULT_COMPONENT.items():
            body = lift(_read(rel), fn)
            assert "previewConfirmResultHtml(" in body, (ep, fn)
            assert reader in endpoints, (ep, reader)

    def test_the_restore_flow_draws_its_apply_result(self):
        from tests.payload_render import lift

        flow = lift(_read("static/js/gen/partials__golden_repo.3.js"), "previewBaselineRestore")
        assert "_showRestoreResult(" in flow and "ad.result" in flow
