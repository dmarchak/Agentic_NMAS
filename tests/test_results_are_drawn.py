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
  The result rule applies once it has one;
- ``PAGE_RECORD``: drawn by a redesigned (v2) page from the action's own
  record on its next load, the template's source as the evidence (the
  Update button, 2026-09-30).

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
from tests import source_index

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
    # Seed intent (C148): its record is the committed intent it wrote, which
    # the intent editor reads back from HEAD.
    # Retire (7.3): its record is the retire commit, which the device's golden
    # history still reads back by name after the golden is gone (C185: no
    # page links a RETIRED device's history yet).
    "retire.apply": ("static/js/nmas_retire.js", "runApply", "golden.history"),
    # Persist (7.3, C164): its record is the rotation record job health's
    # `rotation:<device>` row reads, served by the job-health route.
    "persist.apply": ("static/js/nmas_persist.js", "runApply", "jobs.jobs_health"),
    # Rotate (7.3): a job; its result is read by id, and its record is the
    # rotation record job health's `rotation:<device>` row reads.
    "rotate.apply": ("static/js/nmas_rotate.js", "runApply", "jobs.jobs_health"),
    "templatize.seed_apply": ("static/js/nmas_seed.js", "previewSeed",
                              "templatize.read_committed"),
    # The monitoring profile's proposal (P.9 step b): its record is the profile
    # commit, read back by the committed-profile reader the modal offers.
    "templatize.profile_propose_apply": ("static/js/nmas_profile.js", "previewProfilePropose",
                                         "templatize.profile_read"),
    # Revert and retry (7.3): drawn by the component. A revert's record is
    # the intent commit it wrote, which the intent editor reads back from
    # HEAD; a retry's is the retry log, served by its reader.
    "templatize.revert_apply": ("static/js/nmas_intent_ops.js", "runApply",
                                "templatize.read_committed"),
    "templatize.retry_apply": ("static/js/nmas_intent_ops.js", "runApply",
                               "templatize.rolled_back_retries"),
    # Onboarding's Create (C86): phase 1, drawn as pending; the record read
    # back is the device's pending row.
    "onboard.create": ("static/js/gen/partials__onboard_wizard.1.js", "onboardCreate",
                       "onboard.pending"),
    # Onboarding's Verify and Abandon (7.1): drawn from the row the route
    # recorded in the onboarding run record, and read back by the pending
    # banner (each row's last run; a run that took its device off the list
    # under "finished recently").
    "onboard.verify": ("static/js/gen/partials__onboard_wizard.2.js", "onboardShowRunResult",
                       "onboard.pending"),
    "onboard.abandon": ("static/js/gen/partials__onboard_wizard.2.js", "onboardShowRunResult",
                        "onboard.pending"),
    # NetBox Remove (C121): drawn from the recorded row; the record re-read
    # on the NetBox tab.
    "netbox_safety.apply_removal": ("static/js/nmas_netbox_removals.js",
                                    "showNetboxRemovalResult", "netbox_safety.removals"),
    "netbox_safety.apply_import": ("static/js/gen/index.4.js", "loadNetboxTab", "netbox_status"),
    "netbox_safety.apply_import_all": ("static/js/gen/index.4.js", "loadNetboxTab",
                                       "netbox_status"),
}

#: The bar: changes nothing durable AND has no operands worth re-reading.
TOAST_ENOUGH = {}

#: Drawn by a REDESIGNED page (option A) from the action's own record, on the
#: next load: {endpoint: (template, what the template must draw, the route
#: that reads the record back)}. The v2 pages are server-rendered under the
#: strict policy, so the evidence is the template's source, as the
#: component's is its function's.
PAGE_RECORD = {
    # The Update button: the request is answered 202, the page waits on
    # /health, and the updater's record is drawn as "The last update" (its
    # outcome and reason) on the Update page, whose panel route re-reads it.
    "update.apply": ("templates/v2/_update.html", ('id="update-last"', "o.outcome", "o.reason"),
                     "v2.update_panel"),
    # "It is done" for an AFTER host step: the record drawn back as who said
    # each step done and when, on the Update page.
    "update.step_done": ("templates/v2/_update.html", ('id="update-said-done"', "d.by", "d.at"),
                         "v2.update_panel"),
    # The monitoring profile's batch Apply (P.9 d2): a job, its result drawn
    # from the receipts the apply wrote (each device's outcome, what was sent
    # and checked, the record), and the receipts read back on each device's
    # Changes.
    "v2.profile_apply_confirm": ("templates/v2/_apply_job.html",
                                 ('id="apply-job"', "res.targets", "res.record"),
                                 "deploy.receipts_read"),
    # The IP SLA policy (P.9 d4): committed to the profile; the page redraws
    # and states the policy now in force from the committed profile.
    "v2.ip_sla_policy_set": ("templates/v2/ip_sla.html",
                             ('id="ipsla-policy"', "policy.words"), "v2.ip_sla"),
    # The IP SLA probes (P.9 d4): committed to intent, then the page goes to
    # the scoped Apply, whose preview draws each new probe in the device's
    # program FROM that committed intent; the device's Intent tab re-reads it.
    # The device page's Capture (7.3): the result drawn in place from the apply's outcome
    # (the commit, who, the outcome), and the golden read back on the device's History.
    # The device page's Persist (7.3): the result in place from the apply's answer, and the
    # record read back by job health's rotation row.
    # The device page's Rotate (7.3): a job; its result drawn by the job's card, and the
    # record read back by job health's rotation row.
    # The device page's Deploy (7.3): a job; its result drawn by the job's card from the
    # receipt, and the record read back on the device's History.
    # H, the intent editor on v2 (board H): the commit drawn in place (the commit, who, what a
    # deploy would send now), and the committed intent read back by the Intent tab.
    "intent_v2.commit": ("templates/v2/_intent_edit.html",
                         ("c.state == 'done'", "c.r.commit", "c.actor"), "device_v2.intent"),
    # Templates on v2 (7.6, boards B and C): the approval and the revocation drawn in place
    # (who, the commit, the evidence or the reason), and the row's approval read back from the
    # committed record by the page.
    "templates_v2.approve": ("templates/v2/_template_op.html",
                             ("op.state == 'approved'", "r.commit", "r.evidence.validated"),
                             "templates_v2.page"),
    "templates_v2.revoke": ("templates/v2/_template_op.html",
                            ("op.state == 'revoked'", "r.commit", "r.reason"),
                            "templates_v2.page"),
    # C566, board B: the shipped file brought in, drawn in place (the commit, as whom, the
    # approvals revoked), and the row's state read back from the library by the page.
    # C566, board A: the profile committed on v2, drawn in place (the commit, as whom), the
    # table read back from the committed profile by the page.
    "v2.profile_propose_commit": ("templates/v2/_profile_op.html",
                                  ("op.state == 'committed'", "op.r.commit", "op.actor"),
                                  "v2.monitoring_profile"),
    "templates_v2.bring": ("templates/v2/_template_op.html",
                           ("op.state == 'brought'", "r.commit", "r.revoked"),
                            "templates_v2.page"),
    "device_v2.revert_confirm": ("templates/v2/_revert.html",
                                 ('id="device-op"', "c.summary", "c.record"), "device_v2.history"),
    # Retire on v2 (board 12): the result in place; its record is what the device's address
    # then shows, read from the retire commit (C185).
    "device_v2.retire_confirm": ("templates/v2/_retire.html",
                                 ('id="device-op"', "c.summary", "c.record"), "device_v2.device"),
    "device_v2.seed_confirm": ("templates/v2/_seed.html",
                               ('id="device-op"', "c.summary", "c.record"), "device_v2.history"),
    "device_v2.retry_confirm": ("templates/v2/_retry.html",
                                ('id="device-op"', "c.summary", "c.record"), "device_v2.history"),
    "device_v2.restore_confirm": ("templates/v2/_restore.html",
                                  ('id="device-op"', "c.words", "c.record"), "device_v2.history"),
    "device_v2.deploy_confirm": ("templates/v2/_deploy.html",
                                 ('id="device-op"', "c.words", "c.record"), "device_v2.history"),
    "device_v2.rotate_confirm": ("templates/v2/_rotate.html",
                                 ('id="device-op"', "c.summary", "c.record"), "jobs.jobs_health"),
    "privileged_v2.confirm": ("templates/v2/_privileged.html",
                              ('id="device-op"', "c.record", "r.verify"), "device_v2.history"),
    "device_v2.persist_confirm": ("templates/v2/_persist.html",
                                  ('id="device-op"', "c.outcome", "c.record"), "jobs.jobs_health"),
    "device_v2.capture_confirm": ("templates/v2/_capture.html",
                                  ('id="device-op"', "c.commit", "c.outcome"), "device_v2.history"),
    "v2.ip_sla_commit": ("templates/v2/_apply_preview.html",
                         ('id="apply-preview"', "r.program"), "device_v2.intent"),
}

#: Measured 2026-09-27, each handler read by hand. Only shrinks.
PENDING = {
    # -- drawn in place, gone when the window closes or the page moves on --
    "bulk_execute": "the bulk results modal, until closed",
    "bulk_delete_file": "the bulk results modal, until closed",
    "bulk_tftp_upload": "the bulk results modal, until closed",
    "run_command": "the device page re-rendered with the output",
    "delete_file": "the device page re-rendered",
    "upload_file": "the device page re-rendered",
    "ai_chat": "the chat stream (Stage 8 decides what the agent's record is)",
    "templatize.edit_committed": "the editor's status line names the commit",
    "remote.push": "the remote panel's output box",
    "remote.auto_push": "the remote panel's output box",
    "remote.acknowledge": "the remote panel's output box",
    # -- a toast, gone in seconds --
    "bulk_reload": "the bulk results modal, each device polled (C152), not the result component",
    "ai_agent_run": "nothing: the response is never read (the agent is off)",
    "ai_approval_approve": "a toast; the commit an approval makes is never shown",
    "ai_approval_reject": "a toast",
    "refresh_hostnames": "a toast, then a page reload",
    "templates.approve": "a toast carrying the per-device evidence",
    "templates.write_template": "a toast",
    "remote.verify_write": "a toast, then the panel reloads",
}

#: No page sends these (test_route_reachability.KNOWN_UNREACHABLE).
NO_GUI = {
    "templates.revoke_approval", "templates.save_bindings",
    "templatize.bulk_apply",
    "remote.adopt",
}

#: (file, the literal that draws success unearned) -> reason. Only shrinks.
FALSE_GREEN = {
    # Onboarding's Create said "Device onboarded." after phase 1; it is drawn
    # by the component now, "Partly done" and pending (C86, 2026-09-27).
}

#: EVERY green toast the shipped pages draw, each with why green is EARNED
#: there (C121). FALSE_GREEN held the instances a survey found, and NetBox
#: Remove's partial removal and a bulk run with failed devices were both
#: green and on no list: the class was not zero, the list was. Keyed by
#: (file, a literal from the call); a scan finds them all, both ways.
GREEN_TOASTS = {
    ("static/js/gen/index.3.js", "Topology updated"): "topology read with nodes (0 nodes is a warning)",
    ("static/js/gen/index.3.js", "topology: ${n} node(s)"): "green only when nodes were found",
    ("static/js/gen/index.4.js", "Deleted \"${pbName}\""): "one playbook deleted after an HTTP ok",
    ("static/js/gen/index.4.js", "Monitoring config saved"): "one settings write, ok checked",
    ("static/js/gen/index.4.js", "data.drifted > 0 ? 'warning'"): "level from drifted and errors",
    ("static/js/gen/index.4.js", "Approved and executed"): "one item; failure and note have their own",
    ("static/js/gen/index.1.js", "showToast(data.message, 'success')"): "single-request actions (list create/delete, TFTP server, bulk STARTED): the per-device outcome is the bulk modal's",
    ("static/js/gen/index.1.js", "Bulk operation finished"): "level from the failed and succeeded counts (C121)",
    ("templates/device.html", "Output copied to clipboard"): "a clipboard copy",
    ("templates/device.html", "showToast(data.message, 'success')"): "one TFTP server setting",
    ("static/js/gen/partials__template_editor.1.js", "saveToastText(d)"): "one template save, ok checked",
    ("static/js/gen/partials__template_editor.1.js", "Approved: ${approvalEvidenceText"): "the approval, with its evidence named",
    ("templates/index.html", "'Settings saved'"): "saved with no errors (warnings have their own)",
    ("static/js/gen/partials__security_posture.1.js", "is now set explicitly"): "one ratification, ok checked",
    ("static/js/gen/partials__netbox_safety_modal.1.js", "Import started for"): "says STARTED; the outcome is the sync card's (C85)",
    ("static/js/gen/partials__inventory_source.1.js", "Refreshed from NetBox"): "green only with nothing skipped (C121)",
    ("static/js/gen/partials__golden_repo.3.js", "Renames synced"): "one rename commit, ok checked",
    ("static/js/gen/partials__golden_repo.3.js", "Migrated ${d.migrated.length}"): "the one-shot migration, ok checked",
    ("templates/partials/onboard_wizard.html", ".cfg downloaded"): "a file download",
}

#: (file, the unescaped interpolation) -> where. Only shrinks.
UNESCAPED = {
    # Auto-Create's result toast (hostnames and failure reasons into HTML)
    # left with the route: it is a scope of the capture operation now, drawn
    # by the component, which escapes every value (C102, 2026-09-27).
}

# PENDING 23 -> 21: onboarding's Verify and Abandon drawn by the component (7.1).
CEILINGS = {"PENDING": 19, "FALSE_GREEN": 0, "UNESCAPED": 0}


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
        assert len(pop) >= 38, len(pop)           # measured 41 on 2026-09-27; C104 removed the manual commit, C102 Auto-Create, C105 approve-all records nothing
        assert {GATES[e].kind for e in pop} == set(KINDS)

    def test_every_member_is_in_exactly_one_place(self):
        places = {"RESULT_COMPONENT": set(RESULT_COMPONENT), "TOAST_ENOUGH": set(TOAST_ENOUGH),
                  "PENDING": set(PENDING), "NO_GUI": set(NO_GUI),
                  "PAGE_RECORD": set(PAGE_RECORD)}
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
                           ("PENDING", PENDING), ("NO_GUI", NO_GUI), ("PAGE_RECORD", PAGE_RECORD)):
            assert set(keys) <= pop, (name, sorted(set(keys) - pop))

    def test_the_lists_only_shrink(self):
        # EQUAL, not at most (C125): the ceiling lagged the list by two when it
        # was lowered by hand, and "25" was reported as the count while the
        # list held 23. Equal means removing an entry lowers the ceiling in
        # the same commit, so the ceiling IS the count.
        assert len(PENDING) == CEILINGS["PENDING"], (len(PENDING), CEILINGS["PENDING"])
        assert len(FALSE_GREEN) == CEILINGS["FALSE_GREEN"]
        assert len(UNESCAPED) == CEILINGS["UNESCAPED"]


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
        assert len(NO_GUI) >= 4   # 5 -> 4: freshness.authorise left in Phase 3


class TestColourAndEscaping:
    """Pinned by the literal each draws: fixing one fails its entry until the
    entry is removed, so the lists cannot keep ghosts."""

    def test_each_false_green_is_still_there(self):
        """A loop, not a parametrisation, for UNESCAPED's reason: the list is
        empty since onboarding's Create was drawn (C86), and an empty
        parametrisation reports a SKIP, which reads as something that did not
        run."""
        gone = [lit for (rel, lit) in sorted(FALSE_GREEN) if lit not in _read(rel)]
        assert not gone, f"fixed? remove it from FALSE_GREEN: {gone}"

    def test_the_false_onboarding_toast_is_gone(self):
        """The one FALSE_GREEN entry, fixed: its literal is absent from the
        shipped file (a removed entry cannot come back unnoticed)."""
        assert "'Device onboarded.'" not in _read("static/js/gen/partials__onboard_wizard.1.js")

    def test_each_unescaped_interpolation_is_still_there(self):
        """A loop, not a parametrisation: with the list empty (the last entry
        left with Auto-Create's route), pytest reported a SKIP, which reads as
        something that did not run."""
        gone = [lit for (rel, lit) in sorted(UNESCAPED) if lit not in _read(rel)]
        assert not gone, f"fixed? remove it from UNESCAPED: {gone}"


class TestEveryGreenToastIsDeclared:
    """C121: the constraint, not the survey. Every showToast whose arguments
    carry a literal 'success' is declared in GREEN_TOASTS with its reason;
    a new one fails until someone says why green is earned there."""

    FILES = ("static/js", "templates")

    def _calls(self, root=ROOT):
        import re
        out = []
        for path in source_index.tracked(*self.FILES, root=root):
            f = os.path.basename(path)
            if not f.endswith((".js", ".html")) or ".min." in f or "bootstrap" in f:
                continue
            rel = os.path.relpath(path, root)
            text = open(path, encoding="utf-8").read()
            for m in re.finditer(r"showToast\(", text):
                depth, i = 0, m.end() - 1
                while i < len(text):
                    depth += {"(": 1, ")": -1}.get(text[i], 0)
                    if depth == 0:
                        break
                    i += 1
                call = text[m.start():i + 1]
                if "'success'" in call:
                    out.append((rel, call))
        return out

    def test_every_green_toast_is_declared_and_no_declaration_is_a_ghost(self):
        calls = self._calls()
        assert len(calls) >= 18, len(calls)          # the scan can see them
        undeclared = [(rel, call[:90]) for rel, call in calls
                      if not any(rel == f and lit in call for (f, lit) in GREEN_TOASTS)]
        assert undeclared == [], undeclared
        ghosts = [k for k in GREEN_TOASTS
                  if not any(rel == k[0] and k[1] in call for rel, call in calls)]
        assert ghosts == [], ghosts

    def test_the_scan_finds_a_planted_one(self, tmp_path):
        """A multi-line call too: the first line-based count missed six."""
        (tmp_path / "static" / "js").mkdir(parents=True)
        (tmp_path / "templates").mkdir()
        (tmp_path / "static" / "js" / "x.js").write_text(
            "showToast(`done ${n}`,\n    'success');\nshowToast('no', 'danger');")
        assert [c[0] for c in self._calls(source_index.track_all(tmp_path))] == \
            ["static/js/x.js"]


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

    def test_each_page_entry_draws_its_record_and_can_be_read_again(self):
        import app as A

        endpoints = {r.endpoint for r in A.app.url_map.iter_rules()}
        assert PAGE_RECORD
        for ep, (rel, marks, reader) in PAGE_RECORD.items():
            src = _read(rel)
            assert all(m in src for m in marks), (ep, [m for m in marks if m not in src])
            assert reader in endpoints, (ep, reader)

    def test_the_restore_flow_draws_its_apply_result(self):
        from tests.payload_render import lift

        flow = lift(_read("static/js/gen/partials__golden_repo.3.js"), "previewBaselineRestore")
        assert "_showRestoreResult(" in flow and "ad.result" in flow
