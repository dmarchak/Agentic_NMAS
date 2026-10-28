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
    # Today's deploy wizard's apply (deploy.apply) left at 7.8 (2026-10-17, P7-25): the device
    # page's Deploy… and the batch Apply draw THE apply's result in place (PAGE_RECORD).
    # Today's re-apply (golden.restore_apply) left at 7.8 (2026-10-17, P7-21): v2's
    # device_v2.restore_confirm and History's Re-apply… draw a restore's result (PAGE_RECORD).
    # The import runs on a thread; its result is the stored summary, drawn on
    # the sync card whenever the NetBox tab is read (C85).
    # Capture (7.1 step 4; golden.capture_apply, drawn by `nmas_capture.js` and read back by
    # golden.history) and the monitoring profile's proposal (templatize.profile_propose_apply,
    # `nmas_profile.js`, read back by templatize.profile_read), the last two, left with today's
    # index at 7.8 (2026-10-17, P7-27): the device page's Capture and Monitoring › Profile's
    # Propose draw their results in place (PAGE_RECORD). Empty since: no script of today's draws
    # a result.
    # Today's retire, persist, rotate and seed (retire.apply, persist.apply, rotate.apply,
    # templatize.seed_apply) and revert and retry (templatize.revert_apply, retry_apply) left at
    # 7.8 (2026-10-17, P7-24) with their scripts: each device page's card draws its result and
    # History reads its record (PAGE_RECORD's device_v2 entries).
    # Revert and retry (today's templatize.revert_apply and .retry_apply, P7-24) and today's
    # onboarding Create, Verify and Abandon (onboard.create, .verify, .abandon, P7-25) left
    # with their scripts at 7.8 (2026-10-17): the v2 device page's and onboard_v2's draw their
    # results in place (PAGE_RECORD).
    # Today's NetBox Remove and imports (C121) left with today's NetBox tab at 7.8
    # (2026-10-17): v2's NetBox confirm (`netbox_v2.confirm`, below) draws them.
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
    # History (today's device page's Changes and GET /deploy/receipts left at 7.8, P7-22).
    "v2.profile_apply_confirm": ("templates/v2/_apply_job.html",
                                 ('id="apply-job"', "res.targets", "res.record"),
                                 "device_v2.history"),
    # The paired deploy (C1909): the same job card, the link's verify and what each end
    # achieved drawn from the receipts, read back on each device's History.
    "v2.pair_apply_confirm": ("templates/v2/_apply_job.html",
                              ('id="apply-pair-result"', "t.pair.verify_words", "res.record"),
                              "device_v2.history"),
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
    # Feature 7's part 2: a drafted change committed, drawn in place in the row (the commit,
    # who, Source ai-draft and its call), and the committed intent read back by the Intent tab.
    "intent_v2.words_commit": ("templates/v2/_intent_words.html",
                               ("w.committed", "c.commit", "w.actor"), "device_v2.intent"),
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
    # C718: Decline… and Undo decline… answer in place, outside the table that redraws; the
    # record is the device's intent commit, read on its History.
    "v2.decline_confirm": ("templates/v2/_decline.html",
                           ('id="decline-card"', "o.outcome", "o.save.commit"),
                           "device_v2.history"),
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
                                 ('id="device-op"', "c.summary", "c.record"), "device_v2.history"),
    # C724, Rotate due devices now: the run on the one stepper in place, then its result (what
    # it rotated, skipped and where it stopped); each device's rotation read on History.
    "credential_profiles_v2.rotate_due_confirm": (
        "templates/v2/_credential_profiles.html",
        ("op.state == 'rotate_done'", "res.rotated", "res.failed", "run_stepper(op.r.card)"),
        "v2.history_page"),
    "privileged_v2.confirm": ("templates/v2/_privileged.html",
                              ('id="device-op"', "c.record", "r.verify"), "device_v2.history"),
    "device_v2.persist_confirm": ("templates/v2/_persist.html",
                                  ('id="device-op"', "c.outcome", "c.record"), "device_v2.history"),
    # C906's re-key: the result in place of the card; the key kept, and the one it replaced,
    # read on the device's History (`history_sources.host_keys`).
    "device_v2.rekey_confirm": ("templates/v2/_rekey.html",
                                ('id="device-op"', "c.outcome", "c.record"), "device_v2.history"),
    # Devices › Save (C593): a job, its result drawn per device (each outcome and its detail)
    # with the commit it made; each persist row read back on the device's History.
    "v2.save_confirm": ("templates/v2/_save.html",
                        ('id="save-op"', "s.commit", "d.detail"), "device_v2.history"),
    "device_v2.capture_confirm": ("templates/v2/_capture.html",
                                  ('id="device-op"', "c.commit", "c.outcome"), "device_v2.history"),
    "v2.ip_sla_commit": ("templates/v2/_apply_preview.html",
                         ('id="apply-preview"', "r.program"), "device_v2.intent"),
    # History › Remote set-up (C631): each act's answer drawn in place on the card, and its
    # record (the network's remote.json) read back by the card; the write probe's by
    # History's header, which draws the last Verify.
    # History's header's Push now: its answer said beside the button, and a failure drawn from
    # the record (`last_push_failure`), which every redraw of the header reads again. Today's
    # Remote card's output box held it (PENDING) until the card left at 7.8 (2026-10-17).
    "remote.push": ("templates/v2/_history_remote.html",
                    ('id="remote-push-failed"', "remote.push_failure.reason"),
                    "v2.history_remote"),
    # The result component's parts are one macro (templates/v2/_preview_parts.html) every
    # card that confirms a 7.1 preview draws its result through.
    "netbox_v2.confirm": ("templates/v2/_netbox_job.html", ("result_parts(r)", "job.removal"),
                          "netbox_v2.job"),
    # The template editor (cutover blocker 5): the commit and what it revoked, in place, with
    # Approve… for each; the commit read again on the template's row and in History.
    "templates_v2.edit_commit": ("templates/v2/_template_op.html",
                                 ("op.state == 'edited'", "r.revoked", "r.commit"),
                                 "templates_v2.page"),
    # History's Re-apply (2026-10-10): the batch drawn in place by the Apply's job view, from
    # the receipts; each device's receipt read again on its History.
    "v2.history_reapply_confirm": ("templates/v2/_apply_job.html", ("run_stepper(run)",),
                                   "device_v2.history"),
    # Reload (P.14, cutover blocker 6): the result in place, each step's outcome; the run read
    # again on the device's History (the reloads source, with its window and its restart).
    "device_v2.reload_confirm": ("templates/v2/_reload.html",
                                 ('id="device-op"', "r.steps", "r.reason"), "device_v2.history"),
    # DHCP › Reservations (C529 step 2, board B): the result in place, read back from Kea, and
    # its commit; read again on the network's History (dhcp/reservations.yml).
    "dhcp_v2.reservation_confirm": ("templates/v2/_dhcp_reserve.html",
                                    ("op.state == 'done'", "r.read_back", "r.commit"),
                                    "v2.history_page"),
    # DHCP › Exclusions (C529 step 3, board D): the same, in dhcp/exclusions.yml.
    "dhcp_v2.exclusion_confirm": ("templates/v2/_dhcp_exclusion.html",
                                  ("xop.state == 'done'", "r.read_back", "r.commit"),
                                  "v2.history_page"),
    # DHCP › Leases' Release lease… (C1403): the same, in dhcp/released-leases.yml.
    "dhcp_v2.lease_confirm": ("templates/v2/_dhcp_lease.html",
                              ("lop.state == 'done'", "r.read_back", "r.commit"),
                              "v2.history_page"),
    # SDN (PHASE8_PLAN 17.1 S8 and S16, C1912): the flow operation's and the response's result
    # in place of their card (the outcome, Verify's checks, the rollback, the record), the run
    # read again on History (the network's flow intent, `history_sources.sdn_operations`).
    "sdn_v2.flow_confirm": ("templates/v2/_sdn_op.html",
                            ("d.state == 'result'", "d.checks", "d.rollback", "d.record"),
                            "v2.history_page"),
    "sdn_v2.response_confirm": ("templates/v2/_sdn_op.html",
                                ("d.state == 'result'", "d.checks", "d.rollback", "d.record"),
                                "v2.history_page"),
    # A lost response's re-apply (C2018): the same card, the run on History the same way.
    "sdn_v2.reapply_confirm": ("templates/v2/_sdn_op.html",
                               ("d.state == 'result'", "d.checks", "d.rollback", "d.record"),
                               "v2.history_page"),
    # DHCP › Subnets (C529 step 3, board C): the same, in dhcp/subnets.yml.
    "dhcp_v2.subnet_confirm": ("templates/v2/_dhcp_subnet.html",
                               ("sop.state == 'done'", "r.read_back", "r.commit"),
                               "v2.history_page"),
    "templates_v2.seed": ("templates/v2/_template_op.html",
                          ("op.state == 'seeded'", "op.added", "op.commit"),
                          "templates_v2.page"),
    "templates_v2.bindings_apply": ("templates/v2/_template_op.html",
                                    ("op.state == 'bound'", "r.moves", "r.commit"),
                                    "templates_v2.page"),
    # Devices › Change a setting (board D): the commit in place, its devices and the refused;
    # read again on the network's History (an intent commit).
    "bulk_intent_v2.apply": ("templates/v2/_bulk_intent.html",
                             ("c.commit", "c.refused", "c.error"), "v2.history_page"),
    # Adopt (board G): the result in place, each step and why it stopped; the run read again on
    # the network's History (Onboarding and adopt).
    "adopt_v2.confirm": ("templates/v2/_adopt.html", ("r.steps", "r.reason", "r.remaining"),
                         "v2.history_page"),
    # Onboarding on v2 (cutover blocker 3): Create's result in place, the device's pending
    # page its record read again; Verify's and Abandon's results in place on the pending
    # page, each run's row read back on the network's History. Verify's mark was
    # `record_error`, a key nothing set (C1221): the record not written is drawn by
    # `result_parts` itself, held through the real route by tests/test_record_not_written_is_drawn.py.
    "onboard_v2.create": ("templates/v2/_onboard_add.html", ("result_parts(done.result)",
                                                             "Open {{ f.hostname }}"),
                          "device_v2.device"),
    "onboard_v2.verify": ("templates/v2/_onboard_pending.html",
                          ("result_parts(done.result)", "run_stepper(done.run)"),
                          "v2.history_page"),
    "onboard_v2.abandon": ("templates/v2/_onboard_pending.html",
                           ("result_parts(done.result)", "Back to Devices"), "v2.history_page"),
    # Out-of-band ZTP (O6b): a console survey's and kick-start's result in place on its card,
    # read from the run's record (what was found, the MAC, the lines sent, the masked
    # transcript), and the run read again on the network's History (Console surveys and
    # kick-starts).
    "console_ztp_v2.survey_confirm": ("templates/v2/_console_ztp.html",
                                      ('id="console-ztp-card"', "r.reasons", "r.transcript"),
                                      "v2.history_page"),
    "console_ztp_v2.kickstart_confirm": ("templates/v2/_console_ztp.html",
                                         ('id="console-ztp-card"', "r.lines", "r.verify"),
                                         "v2.history_page"),
    # The one-decision out-of-band onboarding: its result in place on its card (what it
    # compared, the MAC, the copy's answer, what was sent and the masked transcript), read from
    # the run's record, and read again on History (Console surveys and kick-starts).
    "oob_onboard_v2.confirm": ("templates/v2/_oob_onboard.html",
                               ('id="oob-card"', "r.reason", "r.transcript"),
                               "v2.history_page"),
    # C1560: a console server's re-key, its result in place on the Console servers tab; the
    # key kept, and the one it replaced, read on History (SSH host keys).
    "console_servers_v2.rekey_confirm": ("templates/v2/_console_server_op.html",
                                         ("c.mode == 'rekey_done'", "c.detail"),
                                         "v2.history_page"),
    "remote_v2.connect": ("templates/v2/_remote_setup.html", ("Connected:", "r.owner_repo"),
                          "remote_v2.card"),
    "remote_v2.write_probe": ("templates/v2/_remote_setup.html",
                              ("The write probe", "c.name", "c.detail"), "v2.history_remote"),
    "remote_v2.acknowledge": ("templates/v2/_remote_setup.html",
                              ("Acknowledged:", "s.acknowledged.by"), "remote_v2.card"),
    "remote_v2.auto_push": ("templates/v2/_remote_setup.html",
                            ("Automatic pushing is on", "r.auto_push"), "remote_v2.card"),
}

#: Measured 2026-09-27, each handler read by hand. Only shrinks.
PENDING = {
    # Today's template editor's save and Approve (a toast each) and today's intent editor's
    # commit (its status line) left this list at 7.8 (2026-10-17, P7-23): Templates › Edit… and
    # Approve… and the Intent tab draw each result in place, and History reads each commit.
    # Today's Remote card's four (remote.push, auto_push, acknowledge, verify_write) left this
    # list at 7.8 (2026-10-17, P7-21): Push now is History's header's (PAGE_RECORD); the other
    # three left with the card, History › Remote set-up… doing each.
}

#: No page sends these (test_route_reachability.KNOWN_UNREACHABLE). Empty since 2026-10-15:
#: the four (today's template revoke and bindings, bulk intent's JSON apply, remote adopt)
#: left with the unreached routes at 7.8, each with a v2 home.
NO_GUI: set = set()

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
    # Today's Settings modal's "Settings saved" and its posture panel's ratification left with
    # the modal at 7.8 (2026-10-15). Today's list bar's two (index.1.js, a list created and
    # deleted) left with it (P7-26), and today's template editor's two (a save's and an
    # approval's) with it (P7-23), both at 7.8 on 2026-10-17: Settings' New network… and Delete
    # this network…, and Templates' Edit… and Approve…, draw their results in place.
    # Today's inventory source banner's "Refreshed from NetBox" (green only with nothing
    # skipped, C121), the last, left with today's index at 7.8 (2026-10-17, P7-27): no script
    # shipped draws a toast (v2 draws none: tests/test_v2_pages.py), so this holds the next one.
    # Today's bootstrap download (".cfg downloaded", a file download) left with today's
    # onboarding wizard at 7.8 (2026-10-17, P7-25): v2's Get the bootstrap config… reveals it
    # in place, recorded.
}

#: (file, the unescaped interpolation) -> where. Only shrinks.
UNESCAPED = {
    # Auto-Create's result toast (hostnames and failure reasons into HTML)
    # left with the route: it is a scope of the capture operation now, drawn
    # by the component, which escapes every value (C102, 2026-09-27).
}

# PENDING 23 -> 21: onboarding's Verify and Abandon drawn by the component (7.1).
CEILINGS = {"PENDING": 0, "FALSE_GREEN": 0, "UNESCAPED": 0}  # 0 since today's template editor and intent editor left (7.8, P7-23, 2026-10-17: its save, Approve and the intent commit); 3 since today's /run_command left with today's device page (7.8, P7-22, 2026-10-17); 4 since today's Remote card left (7.8, P7-21, 2026-10-17: its push, auto-push, acknowledge and write probe); 8 since today's bulk commands left (7.8, 2026-10-15); 9 since the AI family left (D15, 2026-10-14: the chat, agent run, approve and reject); 13 since Bulk file actions left; 15 since Device files (7.8, D16, 2026-10-13)


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
        refused = toast_refusals({"device_v2.deploy_confirm": "the toast says how many devices"})  # deploy.apply until 7.8
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
        # 5 -> 4: freshness.authorise left in Phase 3; 4 -> 0 2026-10-15: the rest at 7.8.
        # The population this compares is still found: the gated endpoints (floor below).
        assert len(_population()) >= 30, len(_population())


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
        # Today's wizard, the file it was held in, left at 7.8 (2026-10-17, P7-25): every
        # shipped script and template is held now, and v2's Create says PENDING
        # (tests/test_onboard_wizard_renders.py, `TestCreateDrawsItsResult`).
        paths = source_index.tracked("static/js", "templates", root=ROOT)
        assert len(paths) > 50
        for path in paths:
            if path.endswith((".js", ".html")) and ".min." not in path:
                assert "Device onboarded." not in open(path, encoding="utf-8").read(), path

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
        # The scan's population is empty since today's inventory banner's toast, the last, left
        # with today's index (7.8, P7-27, 2026-10-17); its floor went with it, and the planted
        # case below shows the scan still finds one. Before: 1 since today's onboarding wizard's bootstrap download left, 7.8, P7-25, 2026-10-17; 2 since today's list bar's create and delete (P7-26) and today's template editor's save and approval toasts (P7-23) left, 7.8, 2026-10-17; 6 since today's device page's "Output copied to clipboard" left, 7.8, P7-22, 2026-10-17; 7 since today's NetBox dialog's "Import started for" left, 7.8, 2026-10-17; 8 since today's Settings modal left, 7.8, 2026-10-15; 10 since today's drift panel's Check Now left, 7.8, 2026-10-15; 13 since the AI family left, D15; 18 before the file actions left at 7.8)
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

    # Each RESULT_COMPONENT entry's script drew today's `previewConfirmResultHtml` and its record
    # had a reader (`test_each_entry_draws_the_component_and_can_be_read_again`, its floor two)
    # until the last two left with today's index at 7.8 (2026-10-17, P7-27); each is
    # PAGE_RECORD's now, held below.

    def test_each_page_entry_draws_its_record_and_can_be_read_again(self):
        import app as A

        endpoints = {r.endpoint for r in A.app.url_map.iter_rules()}
        assert PAGE_RECORD
        for ep, (rel, marks, reader) in PAGE_RECORD.items():
            src = _read(rel)
            assert all(m in src for m in marks), (ep, [m for m in marks if m not in src])
            assert reader in endpoints, (ep, reader)

    # Today's re-apply dialog drawing its apply's result left at 7.8 (2026-10-17, P7-21): the
    # v2 restore card's (`device_v2.restore_confirm` in PAGE_RECORD) is held above.
