"""Needs attention: one list, every source, one row shape (Stage 7.2).

NSOT_STAGE7_PLAN section 1a, and NSOT_PLAN 8.6 for what Stage 8 needs left
room for. "Approvals", "Jobs" and "Drift" as places would each be one source
of needs attention, which is the four-places failure the operator named, so
each is a SOURCE here and this module is the one place that joins them.

THE ROW. Every row, from every source, has the same parts: WHAT is wrong,
which DEVICES (or none: a job is not a device), SINCE when (None when the
source does not record it, drawn as "not recorded", never as now), the CAUSE
in the source's own words, the OPERANDS it compared, the ONE ACTION that
addresses it, a LEVEL (decided here, only drawn in the browser), and an empty
TRIAGE slot that Stage 8's report fills. `row()` is the only constructor and
refuses a row with no cause or no action, as `preview_confirm` refuses a
silent part: a row that says something is wrong and not why, or not what to
do, is the complaint every other panel in this tool was rebuilt to stop
making. An action a source does not record is stated as not known
(``known: False``), never invented.

THE SOURCE. Each source is read into one result: its state (``read`` or
``unreadable``), WHEN it was read, how long the read took, and WHAT it looked
at. A source that could not be read is a ROW, never an absence, because "the
check could not run" and "the check found nothing" otherwise print the same
empty list. An empty page therefore names every source and its time: an empty
list must say what was looked at.

Nothing here does per-device work per request (section 0a). job health is
read live because its cost is per JOB, not per device; its read time is
reported beside it, so the host's measurement decides whether it moves to a
cache, rather than a guess.
"""

import logging
import re
import time
from urllib.parse import urlencode

log = logging.getLogger(__name__)

#: Worst first. The browser draws the level; it never decides it. There is no
#: information level (the operator, 2026-10-02): a fact nobody can act on
#: ("a new release is available", "a retired device's lab file is still
#: there") is true and is not wrong, so it belongs on its own page's detail,
#: and every row here names something wrong and what a person does about it.
LEVELS = ("danger", "warning", "unknown")

#: EVERY kind of row a source can emit, with what is wrong and the action a
#: person takes (the operator, 2026-10-02: "every Needs attention row must name
#: something wrong AND an action a person can take"). `row()` refuses a kind not
#: declared here, so a new kind arrives with its action or not at all; a scan
#: holds every `row(` call in this module to a declared kind, both ways. The
#: row's own action names the specifics; this is the kind's contract.
#: Source ``*`` is a kind any source emits.
ROW_KINDS = {
    ("*", "unreadable"): ("a source could not be read, so what it would show is unknown",
                          "find why it cannot be read: the cause names what failed"),
    ("job_health", "job"): ("a job or check is failing, stale, not installed or could not ask",
                            "its own remedy, or read its output on the host, or install it"),
    ("drift", "disabled"): ("drift checking is switched off", "switch it back on"),
    ("drift", "never"): ("no drift check has run yet for the network", "run a drift check"),
    ("drift", "failed"): ("the last drift check failed", "run it again and read its reason"),
    ("drift", "stale"): ("the last drift check is old", "run a drift check"),
    ("drift", "drifted"): ("a device differs from its golden", "capture it, or put it back"),
    ("drift", "skipped"): ("a device was not checked for drift",
                           "capture its golden, or clear what the reason names and run again"),
    ("drift", "unreachable"): ("a device could not be checked for drift",
                               "check it answers, then run a drift check"),
    ("approvals", "pending"): ("an approval is waiting for a person",
                               "capture the device's golden, or let it expire"),
    ("onboarding", "credential"): ("a pending device's staged credential cannot be found",
                                   "abandon it and onboard it again"),
    ("onboarding", "overdue"): ("a device onboarded long ago was never reached",
                                "verify it, or abandon it"),
    ("rollback", "record"): ("the rolled-back record cannot be read, blocking every plan",
                             "repair it from its preserved copy"),
    ("rollback", "blocked"): ("a device's next plan is blocked by a rolled-back change",
                              "revert the failed intent, or authorise a retry"),
    ("deploys", "failed"): ("the last deploy or restore to a device did not succeed",
                            "read its receipt, then plan again"),
    # C543: verified and running, and NOT in startup, so a reload loses it; Persist saves it.
    ("deploys", "unsaved"): ("a change verified and running on a device is not saved to "
                             "startup, so a reload loses it",
                             "persist it from the device's page"),
    # C1450: sent, read back and saved, with only a protocol intent declares not up after it.
    ("deploys", "unmet"): ("a deploy landed, and a protocol its intent declares was not up "
                           "after it (often a peer not built yet)",
                           "build or check the peer; read the receipt if the peer exists"),
    # C1542: sent whole, accepted and saved, with only lines verify could not read back.
    ("deploys", "read_back"): ("a deploy landed and was saved, and verify could not read back "
                               "some of the lines it sent",
                               "read those lines in the device's golden: acknowledge a line "
                               "the device prints in another form, plan again for one absent"),
    ("baseline", "denied"): ("the last baseline was not earned", "resolve each departure, then Save All"),
    ("baseline", "unusable"): ("no stored baseline can be re-applied", "take a current baseline"),
    ("authorisations", "repeated"): ("one line is authorised again and again",
                                     "read the reasons; move the line into intent, or its cause"),
    ("grafana", "stalled"): ("Grafana stopped evaluating a rule group", "check its scheduler"),
    ("grafana", "incident"): ("an alert is firing", "check its path, or read the rule"),
    ("grafana", "series"): ("an alert is firing on one series",
                            "read the rule, or acknowledge a chronic one within its band"),
    ("grafana", "rule"): ("a rule reads no data or cannot evaluate", "read its query in Grafana"),
    ("grafana", "heartbeat-floor"): ("a device has no heartbeat rule Grafana shows",
                                     "regenerate the rules, then check the reader's role"),
    ("integrations", "down"): ("an integration is down", "check it at its configured URL"),
    ("integrations", "refused"): ("an integration refuses the tool's credential",
                                  "renew it where the service issues it and put it in Settings"),
    ("credential-health", "expiry"): ("a credential expires soon, or has expired",
                                      "renew it where the service issues it and put it in Settings"),
    ("dashboards", "missing"): ("a network's fleet or device dashboard setting names a "
                                "dashboard its Grafana does not hold, so that page draws none",
                                "set it to a dashboard that Grafana holds"),
    ("dashboards", "unconfirmed"): ("a network's dashboard setting names a dashboard missing "
                                    "from its Grafana's list, and Grafana could not be asked",
                                    "check that Grafana answers, or correct the setting"),
    ("credential-health", "age"): ("a credential is older than the age it is kept",
                                   "rotate it"),
    ("credential-health", "unread"): ("a credential's expiry cannot be read",
                                      "read it where the service shows it"),
    ("redaction", "unhealthy"): ("log redaction is not working: a secret could reach a log",
                                 "read which handler and what got through, then restart Mercury"),
    ("ci", "verdict"): ("the running commit has no CI pass",
                        "update to a release CI passed, or find why CI could not be asked"),
    ("reachability", "not-answering"): ("devices are not answering", "check the path, then each"),
    # C1693: a hand-formatted document cannot be patched (Change it in words, bulk intent).
    ("intent-format", "hand"): ("a device's committed intent does not round-trip through "
                                "Mercury's serialiser, so a patch cannot change it",
                                "normalise its formatting on the device's Intent tab"),
    ("netbox-secrets", "held"): ("NetBox holds a credential in a device's context",
                                 "mask it, remove it by hand, or repair the record first"),
    # C1344: onboarding writes NetBox once, from the bootstrap golden; a deploy never does.
    ("netbox-lag", "behind"): ("a device's NetBox record holds less than its committed golden: "
                               "interfaces, addresses or LLDP cables the import would add",
                               "preview the import of that device from its NetBox tab, and "
                               "confirm it"),
    ("records", "mismatch"): ("a record store moved to the records database no longer matches "
                              "its files", "read the first differing line, then move it back "
                              "to its files or find the writer"),
    ("netbox_inventory", "unreadable"): ("a NetBox-sourced network's devices could not be read "
                                         "from NetBox, so the last good read is kept",
                                         "read NetBox's answer, then fix the network's filter "
                                         "or what it names in NetBox"),
    ("records", "unreachable"): ("a record store is on the records database and it does not "
                                 "answer, so what it records cannot be written",
                                 "make the database answer (its Test names why), or move the "
                                 "store back to its files"),
    ("freshness", "stale"): ("a source has not been read within its promise, so what it "
                             "shows may no longer be true",
                             "read why its reader has not run (Job health), then let it run"),
    ("pushed", "release"): ("the host runs a release that is wrong to keep running",
                            "update, or find where the running commit came from"),
    ("pushed", "ci_failed"): ("CI failed (or was cancelled) for the newest pushed commit, so the "
                              "Update button refuses it", "the developer fixes forward"),
    ("remote", "publication"): ("a list's history is not on its remote",
                                "push, acknowledge, repair the remote, or verify it"),
    ("host_steps", "owed"): ("a host step a release asked for is not done", "do it, then say so"),
    ("templates", "behind_drops"): ("a template behind the shipped version drops a section of the profile",
                                    "bring in the shipped version on Templates"),
    ("adjacencies", "link"): ("an adjacency intent implies is not up",
                              "check the link and both ends"),
    ("adjacencies", "unmeasured"): ("adjacencies cannot be judged", "check the Prometheus targets"),
    # C589: a drop between two scrapes, seen only in the device's own log.
    ("adjacency_log", "flap"): ("a managed device logged a routing adjacency going down, "
                                "outside any planned restart or deploy",
                                "read the device's logs and neighbours; acknowledge it within "
                                "its measured band if the cause is known"),
    ("restarts", "unplanned"): ("a device restarted and nothing planned it",
                                "read the device's reason and crash file, and check the host then"),
    ("operations", "interrupted"): ("an operation on a device did not finish: the process ended "
                                    "while it held the device",
                                    "read each device as it is now and compare it with its "
                                    "golden before changing it, then acknowledge what you found"),
    ("adjacencies", "error"): ("a list's intent could not be read for its adjacencies",
                               "fix the intent file the reason names"),
    ("scheduled_rotation", "stopped"): ("a scheduled credential rotation stopped on a failure",
                                        "read the device's rotation result and settle the "
                                        "stage it names, then run Rotate due devices now"),
    # C2000: the loop does not survive a restart, and does not start again by itself.
    # C1999: a HITL network's threat is seen without opening Responses, one row per incident
    # (one attack, however many switches saw it).
    # Escalated (danger, "unanswered for N minutes") once it has waited the network's
    # sdn_escalate_after_minutes; no on-call integration exists to notify (C1999).
    ("sdn_responses", "awaiting"): ("an SDN incident (one attack, seen on one switch or many) "
                                    "awaits a person on a network, escalated once unanswered "
                                    "past the network's escalation threshold",
                                    "open the incident on SDN › Responses and preview its "
                                    "response at the ingress switch, then confirm it, or "
                                    "dismiss the incident"),
    # C1869's, carried into C1999: a controller that does not answer leaves the network's
    # detections and responses blind, and nothing else said so outside SDN › Controllers.
    ("sdn_controllers", "not_answering"): ("a network's SDN controller does not answer the SDN "
                                           "reader, so its switches' flows and threats are not "
                                           "read on that network",
                                           "check the controller answers at its URL, then read "
                                           "its error on SDN › Controllers and correct its "
                                           "connection in the network's Settings if it moved"),
    ("sdn_loop", "restart_stopped"): ("a network's SDN loop was running and the app's restart "
                                      "stopped it, so its detections are not watched",
                                      "start the loop on SDN › Responses, or leave it stopped"),
    # C2018: a switch's restart drops a response's flows and meter before their hard timeout.
    ("sdn_mitigation", "lost"): ("a response's flows or meter are missing from their switch "
                                 "while their hard timeout has time left, so the threat it "
                                 "answered is not being mitigated",
                                 "re-apply it on SDN › Flows (a preview, then your confirm), "
                                 "or let it expire"),
    # C906: nothing was sent; every session to it is refused until a person reviews the key.
    ("host_keys", "changed"): ("a device answered with an SSH host key Mercury does not hold",
                               "re-key it on its page if it was rebuilt, or find what answers "
                               "at its address"),
    # The operator, 2026-10-16: a window took keys no person looked at, one by one.
    ("host_key_windows", "window"): ("a planned window kept new SSH host keys that no person "
                                     "has reviewed", "compare each new key with its device's, "
                                                     "then acknowledge"),
    # Out-of-band ZTP (O6a, modules/nsot/console_ztp.py): a device's latest console run.
    ("console_ztp", "not_blank"): ("a console survey or kick-start found the device not "
                                   "factory-blank, so no kick-start types on it",
                                   "return it to its factory state (erase its startup "
                                   "configuration and reload it), then survey its console "
                                   "again"),
    ("console_ztp", "failed"): ("a console survey or kick-start stopped before its end, so what "
                                "the console holds is not known",
                                "read the run's transcript, check the console server and the "
                                "device, then survey its console again"),
    # PHASE8_PLAN 18.3 rule 4 (C1843): a background AI feature's spend against its own caps.
    ("ai_spend", "warning"): ("a background AI feature has spent 50% or 80% of its day or "
                              "month cap on a network",
                              "read its spend; leave it, turn it off, or change its cap in "
                              "Settings › AI"),
    ("ai_spend", "stopped"): ("a background AI feature reached its day or month cap on a "
                              "network, so it makes no call until the period ends",
                              "leave it stopped, raise its cap, or turn it off in Settings › AI"),
    # PHASE8_PLAN 18.3 rule 10c (C2056): the installation's day cap, and a feature's estimate.
    ("ai_spend", "day_warning"): ("AI spend today has reached 50% or 80% of the installation's "
                                  "day cap",
                                  "open the spend panel to see what is spending; turn a "
                                  "background feature off there, or an admin changes the day "
                                  "cap"),
    ("ai_spend", "day_reached"): ("AI spend today reached the installation's day cap, so every "
                                  "AI call is refused until the day ends",
                                  "open the spend panel to see what spent it; leave it until "
                                  "the day ends, or an admin changes the day cap"),
    ("ai_spend", "over_estimate"): ("a background AI feature's average daily spend is at or "
                                    "above 150% of the estimate it was approved at",
                                    "open the spend panel to review its trigger, caps and "
                                    "estimate against actual; turn it off, or turn it on again "
                                    "in Settings › AI with a new estimate"),
    # Decision 5 of boards AI1 to AI5 (C1953): a background feature's 14-day approval, asked
    # for again 3 days before it ends, and said once it has ended.
    ("ai_spend", "approval"): ("a background AI feature's approval ends within 3 days, or has "
                               "ended, so the gateway refuses its calls from then until an "
                               "admin turns it on again",
                               "turn it on again in Settings › AI, accepting its current "
                               "estimate, or turn it off"),
    # C2084: the provider refused for the workspace's own usage limit, so every AI call is
    # refused until the moment it named.
    ("ai_spend", "workspace_limit"): ("the provider refused a call because its workspace "
                                      "reached the usage limit its admin set, so Mercury "
                                      "refuses every AI call until the moment the provider "
                                      "named",
                                      "an admin raises the workspace's usage limit in the "
                                      "provider's console, then presses Test on the AI "
                                      "(hosted) card; or wait until that moment"),
    # C2047: a call whose row the record of AI calls refused, its cost held against the caps
    # (`reservations.hold_unrecorded`) until the record takes it.
    ("ai_spend", "unrecorded"): ("the record of AI calls refused a sent call's row, so the "
                                 "call is missing from History and its cost is held against "
                                 "the AI caps as a call in flight until the record takes it",
                                 "find why the record of AI calls refuses writes (its disk or "
                                 "records database); Mercury asks it to take the row again at "
                                 "every AI call"),
}

#: The ways a row leaves the page (the operator, 2026-10-02): the CONDITION RESOLVING (the
#: source reads it fixed: by the action, or by itself), a person ACKNOWLEDGING it with a
#: reason, or TIME passing.
CLEAR_WAYS = ("resolves", "acknowledge", "time")

#: HOW EVERY KIND CLEARS, drawn on the row as "Clears when …" (the operator, 2026-10-02:
#: "for EVERY row kind … state how it clears"). Each entry is the ways (CLEAR_WAYS) and the
#: words; a test holds this to ROW_KINDS both ways, and the words to what each source's code
#: actually does. A row that could never clear is a defect this table makes visible: the
#: repeated authorisation's count only grows, so it was a row for ever until a person could
#: acknowledge it.
CLEARS = {
    ("*", "unreadable"): (("resolves",), "the source is read again successfully"),
    ("job_health", "job"): (("resolves",), "the job's next run or check reads ok (job health "
                            "re-reads every 5 minutes, and as soon as a host job finishes; a "
                            "root-installed helper's row is asked again at the next read of "
                            "this page)"),
    ("drift", "disabled"): (("resolves",), "drift checking is switched back on"),
    ("drift", "never"): (("resolves",), "a drift check runs for this list"),
    ("drift", "failed"): (("resolves",), "a later drift check completes"),
    ("drift", "stale"): (("resolves",), "a drift check runs"),
    ("drift", "drifted"): (("resolves",), "a later drift check finds it matching its golden, "
                           "or a golden is recorded for it (a capture answers the stored run)"),
    ("drift", "skipped"): (("resolves",), "a later drift check checks it"),
    ("drift", "unreachable"): (("resolves",), "a later drift check reaches it"),
    ("approvals", "pending"): (("resolves", "time"), "a capture records the device's golden, "
                               "which closes it, or 48 h pass and it expires (expiry executes "
                               "nothing)"),
    ("onboarding", "credential"): (("resolves",), "the device is abandoned"),
    ("onboarding", "overdue"): (("resolves",), "Verify reaches it, or it is abandoned"),
    ("rollback", "record"): (("resolves",), "the rolled-back record can be read again"),
    ("rollback", "blocked"): (("resolves",), "its intent no longer sends what was rolled back "
                              "(reverted or edited), or a retry is authorised with a reason"),
    ("deploys", "failed"): (("resolves",), "a later deploy or restore to the device finishes "
                            "clean"),
    ("deploys", "unsaved"): (("resolves",), "a save of the device after the deploy reads its "
                             "startup config back saved (its page's Persist, or Save), or a "
                             "later deploy or restore to it finishes clean"),
    ("deploys", "unmet"): (("resolves",), "the adjacency reader, reading after the deploy, sees "
                           "each protocol it names up on the device, or a later deploy or "
                           "restore to it finishes clean"),
    ("deploys", "read_back"): (("resolves", "acknowledge"), "a later deploy or restore to the "
                               "device finishes clean, or a person acknowledges this deploy "
                               "with a reason (a line the device prints in another form); a "
                               "later deploy that misses a line raises it again"),
    ("baseline", "denied"): (("resolves",), "a later save earns a baseline"),
    ("baseline", "unusable"): (("resolves",), "a stored baseline can be re-applied: a new one "
                               "is earned"),
    ("authorisations", "repeated"): (("acknowledge",), "a person acknowledges it with a reason; "
                                     "the line authorised once more raises it again"),
    ("grafana", "stalled"): (("resolves",), "Grafana evaluates the group again"),
    ("grafana", "incident"): (("resolves",), "the alert stops firing in Grafana (a silence "
                              "keeps it a row, saying who silenced it)"),
    ("grafana", "series"): (("resolves", "acknowledge"), "the alert stops firing, or a person "
                            "acknowledges it within its measured 7-day band; it comes back, "
                            "naming the band and the value, when the value leaves the band"),
    ("grafana", "rule"): (("resolves",), "the rule reads data and evaluates again"),
    ("grafana", "heartbeat-floor"): (("resolves",), "Grafana shows a heartbeat rule for the "
                                     "device"),
    ("integrations", "down"): (("resolves",), "it answers the next probe (every 60 s)"),
    ("integrations", "refused"): (("resolves",), "the next probe (every 60 s) is accepted"),
    ("credential-health", "expiry"): (("resolves",), "the reader (hourly) reads an expiry more "
                                      "than 30 days away"),
    ("dashboards", "missing"): (("resolves",), "the setting names a dashboard that Grafana holds "
                                "(the row leaves as soon as the setting changes; the reader "
                                "checks the new one within 5 minutes), or Grafana holds it again"),
    ("dashboards", "unconfirmed"): (("resolves",), "the reader's next read (every 5 minutes) "
                                    "asks Grafana and gets an answer"),
    ("credential-health", "age"): (("resolves",), "the reader (hourly) reads it set within "
                                   "180 days"),
    ("credential-health", "unread"): (("resolves",), "the reader (hourly) reads its expiry"),
    ("ci", "verdict"): (("resolves",), "the host runs a commit CI passed"),
    ("redaction", "unhealthy"): (("resolves",), "every log handler masks the canary and no "
                                 "redaction has failed: read again at each read of this page"),
    ("reachability", "not-answering"): (("resolves",), "every device answers its probe again "
                                        "(every 5 s)"),
    ("netbox-lag", "behind"): (("resolves",), "the reader reads NetBox holding the device's "
                               "committed interfaces, addresses and cables: at once when an "
                               "import, an onboarding's Verify or a golden commit wakes it, "
                               "else within 5 minutes"),
    ("intent-format", "hand"): (("resolves",), "the device's intent is committed in Mercury's "
                                "own formatting (Normalise's commit, or any edit since, which "
                                "saves in it): the reader reads it at once when the commit "
                                "announces intent, else within 5 minutes"),
    ("netbox-secrets", "held"): (("resolves",), "NetBox no longer holds the credential (masked "
                                 "or removed), at the next hourly read"),
    ("netbox_inventory", "unreadable"): (("resolves",), "the network's next refresh reads "
                                         "NetBox (a refresh of the list, or its next load)"),
    ("records", "mismatch"): (("resolves",), "the files and the table match again, or the store "
                              "is moved back to its files, at the next check (every 5 minutes)"),
    ("records", "unreachable"): (("resolves",), "the records database answers the next check "
                                 "(every 5 minutes), or the store is moved back to its files"),
    ("freshness", "stale"): (("resolves",), "the source is read again within its promise"),
    ("pushed", "release"): (("resolves",), "the host runs the commit the remote holds"),
    ("pushed", "ci_failed"): (("resolves",), "a newer commit is pushed (its update is offered "
                              "once CI passes it), or the host runs this one"),
    ("remote", "publication"): (("resolves",), "the remote holds the list's history: pushed, "
                                "after a held push is acknowledged in History's Remote "
                                "set-up"),
    ("templates", "behind_drops"): (("resolves",), "the template is brought to the shipped version, or "
                                    "the profile no longer has the section it drops"),
    ("host_steps", "owed"): (("resolves", "acknowledge"), "its check finds it done, or a person "
                             "says it is done on the Update page"),
    ("adjacencies", "link"): (("resolves",), "the next read finds the adjacency up"),
    ("adjacencies", "unmeasured"): (("resolves",), "Prometheus scrapes the protocol again"),
    ("adjacency_log", "flap"): (("resolves", "acknowledge", "time"),
                                "a day with no unexplained drop logged (by time, a day after the "
                                "last), or acknowledged within its band: the highest daily count "
                                "of the last 7 days, holding while the day's count stays at or "
                                "under it"),
    ("adjacencies", "error"): (("resolves",), "the intent file can be read"),
    ("operations", "interrupted"): (("acknowledge",), "a person acknowledges it with a reason, "
                                    "after reading the devices; the record stays in the list's "
                                    "interrupted.jsonl"),
    ("restarts", "unplanned"): (("acknowledge", "time"), "a person acknowledges it with a "
                                "reason, or 7 days after the restart; History keeps it either "
                                "way"),
    ("sdn_responses", "awaiting"): (("resolves",), "the incident's response is applied, or the "
                                    "incident is dismissed, on SDN › Responses (escalation "
                                    "never clears it: it only raises it to danger)"),
    ("sdn_controllers", "not_answering"): (("resolves",), "the SDN reader's next read (every "
                                           "30 s) finds each controller named answering, or "
                                           "the connection is removed from the network's "
                                           "Settings"),
    ("sdn_loop", "restart_stopped"): (("resolves", "time"), "the loop is started again on SDN "
                                      "› Responses, or 24 hours after the restart (the loop's "
                                      "log keeps the stop either way)"),
    ("sdn_mitigation", "lost"): (("resolves", "time"), "the SDN reader reads the response's "
                                 "flows and meter installed again (after its Re-apply… on "
                                 "SDN › Flows), or their hard timeout passes, when the "
                                 "response would have expired anyway, or a newer response "
                                 "answers the same threat on that switch (its detection fired "
                                 "again and was answered as new)"),
    ("scheduled_rotation", "stopped"): (("resolves",), "a later run (Rotate due devices now on "
                                        "Credentials › Profiles) finishes without a failure, "
                                        "or the failed device's rotation is committed (its "
                                        "device page's Rotate); until then the timer starts "
                                        "no scheduled run"),
    ("host_keys", "changed"): (("resolves",), "a session finds the device answering with the "
                               "key Mercury holds: after a re-key on its page keeps the new "
                               "one, or when the device answers with the held key again"),
    ("host_key_windows", "window"): (("acknowledge",), "a person acknowledges it with a "
                                     "reason, after comparing the keys; each key stays in "
                                     "History with the one it replaced"),
    ("console_ztp", "not_blank"): (("resolves", "acknowledge"), "a later console survey of the "
                                   "device finds it factory-blank, or a later kick-start "
                                   "completes, or a person acknowledges this run with a "
                                   "reason; a later run that finds it so raises it again"),
    ("console_ztp", "failed"): (("resolves", "acknowledge"), "a later console survey of the "
                                "device completes, or a later kick-start completes, or a "
                                "person acknowledges this run with a reason; a later run that "
                                "stops raises it again"),
    ("ai_spend", "warning"): (("resolves", "time"), "the day or month it counts ends (the cap's "
                              "day boundary), or an admin raises the cap until the spend is "
                              "under 50% of it, or turns the feature off"),
    ("ai_spend", "stopped"): (("resolves", "time"), "the day or month whose cap it reached ends "
                              "(the cap's day boundary), or an admin changes the cap, or turns "
                              "the feature off"),
    ("ai_spend", "day_warning"): (("resolves", "time"), "the day ends (the day cap's midnight), "
                                  "or an admin changes the day cap until today's spend is under "
                                  "50% of it or sets no cap, or turns hosted AI off"),
    ("ai_spend", "day_reached"): (("resolves", "time"), "the day ends (the day cap's midnight), "
                                  "or an admin changes the day cap to above today's spend or "
                                  "sets no cap, or turns hosted AI off"),
    ("ai_spend", "over_estimate"): (("resolves",), "its average daily spend falls under 150% of "
                                    "its estimate, or an admin turns it on again with a new "
                                    "estimate, or it is turned off (by an admin, or by its "
                                    "approval's end)"),
    ("ai_spend", "approval"): (("resolves",), "an admin turns the feature on again in "
                               "Settings › AI (a new 14-day approval, its estimate accepted "
                               "again), or turns it off; its end passing does not clear it: "
                               "the row then says the approval ended"),
    ("ai_spend", "workspace_limit"): (("resolves", "time"), "the moment the provider named "
                                      "passes (when it named none, 10 minutes after its "
                                      "refusal, when the next call asks again), or a call is "
                                      "answered (the AI card's Test, after an admin raised the "
                                      "limit), or an admin turns hosted AI off"),
    ("ai_spend", "unrecorded"): (("resolves",), "the record of AI calls takes the call's row: "
                                 "Mercury asks it again at every AI call, and the call is then "
                                 "counted from the record, its reservation gone"),
}

#: The kinds a person acknowledges HERE, with "Acknowledge…" on the row (modules/
#: acknowledgements.py): an event that cannot un-happen. Each row of these kinds carries
#: its *event*, so an acknowledgement covers that event and never a later one. Other kinds
#: whose CLEARS names acknowledge do it through their own control, named in their words.
ACKNOWLEDGED_HERE = frozenset({("restarts", "unplanned"), ("authorisations", "repeated"),
                               ("operations", "interrupted"),
                               # Within its measured band, never for good (C433).
                               ("grafana", "series"),
                               # A window's new host keys, once it has closed (C906).
                               ("host_key_windows", "window"),
                               # Within its measured band of daily drops (C589, C433's shape).
                               ("adjacency_log", "flap"),
                               # One deploy's lines verify could not read back, the device
                               # printing them in another form (C1542): that deploy only.
                               ("deploys", "read_back"),
                               # One console run (O6a): that run only, by its id.
                               ("console_ztp", "not_blank"), ("console_ztp", "failed")})

#: Words that say there is nothing to do: an action is a thing a person does.
NOT_AN_ACTION = ("nothing to do", "it is information", "is what is known",
                 "is all that is recorded", "no remedy is recorded", "whole of what is known")


class RowRefused(ValueError):
    """A row missing a part it must have."""


def _iso(ts) -> str:
    if ts is None:
        return None
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


def row(*, source: str, kind: str, key: str, what: str, cause: str, action: dict,
        level: str, devices=(), since=None, operands: dict = None,
        attach_to: str = None, event: str = None, clears_at=None, read_at=None) -> dict:
    """The only constructor for a Needs attention row.

    *kind* names the row's declared kind (ROW_KINDS): what is wrong and the
    action a person takes. An undeclared kind, an information level, or an
    action whose words say there is nothing to do is refused: a fact nobody
    can act on goes to its own page's detail, never here.

    *attach_to* names another row's id this one is ABOUT (a queued drift
    item is about its device's drift row). The page merges it into that row
    instead of drawing a second row about one event; it stands alone only
    when that row is absent.

    *event* names the one event a row of an ACKNOWLEDGED_HERE kind is about (a restart's
    time), which an acknowledgement is keyed on; such a row without one is refused, since
    an acknowledgement of it could not tell this event from the next."""
    missing = [n for n, v in (("source", source), ("key", key), ("what", what),
                              ("cause", cause)) if not str(v or "").strip()]
    if not isinstance(action, dict) or not str(action.get("label") or "").strip():
        missing.append("action")
    if missing:
        raise RowRefused(f"a Needs attention row without {', '.join(missing)} "
                         "says something is wrong and not why or what to do")
    # A source read for one network's own configuration ("grafana@branch", P.8 step 5) is the
    # same kind of source: its rows are declared, cleared and acknowledged as the base's.
    base = source.split("@", 1)[0]
    if (base, kind) not in ROW_KINDS and ("*", kind) not in ROW_KINDS:
        raise RowRefused(f"row kind {source}/{kind} is not declared in ROW_KINDS with what "
                         "is wrong and the action a person takes")
    if level not in LEVELS:
        raise RowRefused(f"level {level!r} is not one of {LEVELS}: a fact nobody acts on "
                         "belongs on its own page's detail, not in Needs attention")
    said = str(action["label"]).lower()
    if any(p in said for p in NOT_AN_ACTION):
        raise RowRefused(f"the action {action['label']!r} says there is nothing to do: a row "
                         "with no action belongs on its own page's detail")
    declared = (base, kind) if (base, kind) in ROW_KINDS else ("*", kind)
    ways, when = CLEARS[declared]
    acknowledgeable = declared in ACKNOWLEDGED_HERE
    if acknowledgeable and not str(event or "").strip():
        raise RowRefused(f"a {source}/{kind} row is acknowledged per event, and names none")
    return {"id": f"{source}:{key}", "source": source, "kind": kind, "what": what,
            "clears": {"ways": list(ways), "when": when},
            # When a row that clears by TIME will clear (an approval's expiry, an unplanned
            # restart's seven days): nothing announces that moment, so the page and the
            # sidebar's count re-read at it (the operator, 2026-10-02: the count must be right
            # at all times).
            "clears_at": _iso(clears_at) if clears_at else None,
            "event": str(event) if event else None, "acknowledge": acknowledgeable,
            "devices": [d for d in devices if d], "since": _iso(since),
            # When the reading behind the row was taken, for a row drawn from a stored value
            # (C439: a job-health row stayed wrong for minutes, and nothing showed its age).
            "read_at": _iso(read_at) if read_at else None,
            "cause": cause, "operands": dict(operands or {}),
            "action": {"known": True, **action}, "level": level,
            "attach_to": attach_to, "attached": [],
            # Stage 8 attaches its triage HERE, on the row, never as a row of
            # its own (NSOT_PLAN 8.6): two rows about one event is the
            # three-reports problem restated on the page.
            "triage": None}


def source_result(source: str, label: str, *, read_at: float, took_ms: int,
                  rows=None, checked: str = "", error: str = "",
                  value_at: float = None, stale_after_seconds: int = None,
                  reader: str = None, detail: str = "") -> dict:
    """One source, read. *error* makes the source a row of its own.

    *read_at* is when this request read the source; *value_at* is the time of
    the VALUE it shows (section 1a), which for a stored result (the last drift
    run) is earlier, and for a live read (job health) is the same. Collapsing
    them would draw a day-old drift run as read "just now".

    *stale_after_seconds* is how long the value stays current, by the
    source's own promise (a reader's interval times its staleness factor, a
    drift run's interval times two). Today's panel judged age against it on
    its own clock (the live-data contract, 7.2 step 13) until it left with
    today's index at 7.8 (2026-10-17, P7-27); v2's list draws each source's
    value age, and `needs_attention` does not carry the promise to the page.
    None means the value was read for this request.

    *reader* names the reader job behind a stored value (today's panel used it
    to tell that job health's row for a stopped reader already covered a stale
    source).

    *checked* says what was FOUND, for a person; *detail* is the debugger's
    part (endpoints, read costs), drawn one level down, on hover (the
    operator's presentation rule, 2026-09-28)."""
    if error:
        # Kept where it outlives the row (the operator, 2026-09-29): a transient
        # "could not be read: Approvals" cleared on the next read, and nothing
        # anywhere said which read failed or why.
        log.warning("attention: %s could not be read: %s", label, error)
        return {"source": source, "label": label, "state": "unreadable",
                "read_at": _iso(read_at), "value_at": None, "took_ms": took_ms,
                "checked": "nothing: the read failed",
                "rows": [row(source=source, kind="unreadable", key="unreadable", level="unknown",
                             what=f"{label} could not be read",
                             cause=(f"{error}. This is not the same as nothing needing "
                                    "attention: whatever this source would show is "
                                    "unknown until it can be read"),
                             action={"label": "Find why the source cannot be read: "
                                              "the cause above names what failed",
                                     "known": False})]}
    if not checked:
        raise RowRefused(f"source {source!r} read without saying what it looked at: "
                         "an empty result must say what was checked")
    return {"source": source, "label": label, "state": "read",
            "read_at": _iso(read_at),
            "value_at": _iso(read_at if value_at is None else value_at),
            "stale_after_seconds": stale_after_seconds, "reader": reader, "detail": detail,
            "took_ms": took_ms, "checked": checked, "rows": list(rows or [])}


# ---------------------------------------------------------------------------
# Source: job health (the first source; C54's rows already had the shape)
# ---------------------------------------------------------------------------

#: How each job-health state reads as WHAT is wrong, and how loud it is.
_JOB_STATES = {
    "failing": ("is failing", "danger"),
    "never_succeeded": ("has never succeeded", "danger"),
    "not_installed": ("is not installed", "danger"),
    "stale": ("has not succeeded recently", "warning"),
    "unknown": ("could not be checked", "unknown"),
    "unset_guard": ("is an empty setting that switches off a guard", "warning"),
    "contradiction": ("is declared not applicable and is also set", "warning"),
    "not_safe_to_reboot": ("would not survive a reboot", "danger"),
    # The startup check could not READ a device: not the critical finding
    # above (the operator, 2026-10-01), and a warning only once it persists.
    "unread": ("could not read a device this hour", "unknown"),
    "unread_persisting": ("has not read a device for hours", "warning"),
    # Devices reporting one serial: information, said under What was checked (EXPECTED).
    "shared": ("is reported by more than one device", "unknown"),
    # A pending onboarding's bootstrap credential, staged until Verify or Abandon clears
    # it (C1159): expected, said under What was checked (EXPECTED), never a rotation.
    "onboarding_staged": ("holds a pending onboarding's bootstrap credential", "unknown"),
    "not_recorded": ("was rotated and not recorded", "danger"),
    "revert_failed": ("failed a rotation and its revert", "danger"),
    "neither_accepted": ("accepts neither its staged nor its recorded credential", "danger"),
    "at_budget": ("has no SSH session left for the next operation", "warning"),
    "leaked": ("holds an operation's SSH session past ten minutes", "warning"),
    "mixed_version": ("is running a different commit from its checkout", "danger"),
    "socket_down": ("is not listening", "danger"),
    "mismatch": ("does not match what was declared", "warning"),
    "not_run": ("has never run on this host", "warning"),
    "not_monitored": ("is not configured for an integration the network uses", "warning"),
    "breakglass_stale": ("is out of date: it cannot recover a device rotated since its export",
                         "danger"),
    "breakglass_not_intact": ("break-glass record's last download did not arrive intact",
                              "danger"),
    "breakglass_drill_overdue": ("break-glass record has not been opened offline for 90 days",
                                 "warning"),
    # The Update button's root-owned updater (docs/UPDATE.md).
    "writable": ("is run as root and writable by someone else", "danger"),
    "cannot_run": ("cannot run: a program it needs is missing or not root's", "danger"),
    "path_inactive": ("is not watching for update requests", "danger"),
    "differs": ("differs from this release's copy", "warning"),
    # The nightly VM images' storage (B6). These four reached the page as
    # "reads will_not_fit" in danger (C288): every state job health can
    # write has its words here, held by test_job_health.
    "will_not_fit": ("has too little free space for the next run's largest image", "warning"),
    "images_missing": ("holds less than the newest images add up to: one was removed", "danger"),
    "inactive": ("is not mounted or is disabled: the next run will fail", "danger"),
    "unsized": ("has no image size yet to judge the next run against", "unknown"),
    "missing": ("no longer lists the image its last run wrote", "danger"),
    "never": ("has no backup task on record", "warning"),
    "not_configured": ("is not configured, so nothing watches it", "unknown"),
    "pool_unhealthy": ("is not ONLINE: a suspended pool stops every write", "danger"),
    "pool_will_pause": ("is near ZFS's reserve: every VM on it pauses there", "danger"),
    "pool_degrading": ("is past the fill where allocation slows", "warning"),
    "pool_filling": ("is filling: an LVM-thin pool that fills stops its VMs' writes", "danger"),
}


def _job_action(job: dict) -> dict:
    """The ONE action for a job-health row, where the source records one."""
    from modules import job_health as J

    # The row's OWN action first (C164): the builder that wrote the remedy
    # into the detail is the one place that knows it, and names it as a field.
    if isinstance(job.get("action"), dict) and job["action"].get("label"):
        return dict(job["action"])
    systemd_units = {j["unit"] for j in J.JOBS}
    unit, state = job.get("unit", ""), job.get("state", "")
    if unit in systemd_units:
        if state == "not_installed":
            return {"label": "Install and enable the unit on the host",
                    "reference": "docs/DEPLOY_LINUX.md"}
        return {"label": "Read the job's own output on the host",
                "command": f"journalctl -u {unit}.service -n 50 --no-pager"}
    # A row with no remedy of its own: the action its STATE implies, never
    # "nothing is known" (the operator, 2026-10-02: every row has an action).
    return dict(_STATE_ACTIONS.get(state, _STATE_ACTIONS["*"]), known=False)


#: The action a job-health row's state implies when its check names none.
_STATE_ACTIONS = {
    "unknown": {"label": "Find why the check could not ask: its detail above names what it "
                         "read, and it asks again on its next run"},
    "stale": {"label": "Find why the check has not run: run it by hand on the host, or read "
                       "its timer's own row"},
    "unset_guard": {"label": "Set it in Settings, or declare it not applicable on the host "
                             "(settings_not_applicable) with a reason"},
    "contradiction": {"label": "Clear the setting, or withdraw its not-applicable declaration: "
                               "only one can be true"},
    "*": {"label": "Fix what its detail above names: the file, setting or service the "
                   "check read"},
}


JOB_HEALTH_READER = "job-health"
#: Job-health states that are expected and need nothing yet: the startup check
#: missing a device for one run (it is booting, or slow; a warning once it
#: persists, as `unread_persisting`). Said in the source's finding, not a row.
#: A pending onboarding's staged bootstrap credential (C1159) likewise: Verify or
#: Abandon clears it, and the pending device's own page names both.
EXPECTED_JOB_STATES = ("unread", "shared", "onboarding_staged")


def _install_rows_asked_again(jobs: list) -> list:
    """*jobs* with every stored row about a root-installed file that reads not-ok replaced by
    its check asked now (C439, the operator, 2026-10-04: minutes after a correct install of
    the Oxidized helper, the stored reading still said it differed, while the host-step check
    of the same file, asked live, said done). Only a not-ok row is asked again: the Oxidized
    helper's check runs `sudo -n -l`, so asking an ok one on every page view would be a sudo
    query per view, and the rotation's preflight asks the helper itself, live, so a stale ok
    never lets a wrong install through. A check that raises keeps the stored row."""
    from modules import host_helpers
    from modules import job_health as J

    again = {j.get("unit") for j in jobs
             if j.get("unit") in host_helpers.INSTALL_UNITS and j.get("state") not in J.OK_STATES}
    if not again:
        return jobs
    out = [j for j in jobs if j.get("unit") not in again]
    for unit in sorted(again):
        try:
            fresh = host_helpers.ask_now(unit)
        except Exception as exc:                            # noqa: BLE001
            log.warning("attention: %s could not be asked again: %s", unit, exc)
            fresh = [j for j in jobs if j.get("unit") == unit]
        else:
            at = time.time()
            fresh = [dict(j, _read_at=at) for j in fresh]
        out += fresh
    return out


def job_health_source(health=None, now=None, cached=None, readers_now=None) -> dict:
    """Every job-health row that is not ok, as a Needs attention row.

    By default from the job-health READER's stored value, never from systemd
    (rule 1 of modules/reader_job.py): read live, it was 9.8 s of a 10 s
    page (measured on the host, 2026-09-28). *health* is a live read for a
    caller that has one (the tests; `nmas-jobs` stays live by design).

    The readers' OWN liveness is judged now, from their stores (*readers_now*,
    a file read each), never taken from the cached value: a stopped
    job-health reader would otherwise report itself ok for ever."""
    from modules import job_health as J
    from modules import reader_job

    started = time.time()
    value_at = None
    if health is not None:
        try:
            h = health()
            jobs = list(h["jobs"])
        except Exception as exc:                   # noqa: BLE001
            log.error("attention: job health could not be read: %s", exc)
            return source_result("job_health", "Job health", read_at=started,
                                 took_ms=int((time.time() - started) * 1000),
                                 error=f"it raised {type(exc).__name__}: {exc}")
        where, promise = "read now", None
    else:
        got = reader_job.read_cached(JOB_HEALTH_READER) if cached is None else cached
        doc = got.get("doc") or {}
        good = doc.get("last_good") or {}
        took = int((time.time() - started) * 1000)
        if got["state"] != "ok" or not good:
            # Never a "nothing needs attention": no value is not an empty value.
            why = (got.get("why") if got["state"] != "ok" else
                   "the job-health reader has never stored a value; its last attempt: "
                   + ((doc.get("last_attempt") or {}).get("error") or "none recorded"))
            return source_result("job_health", "Job health", read_at=started, took_ms=took,
                                 error=f"not read yet: {why} (it runs in the app, every "
                                       f"{doc.get('interval_seconds') or 'few'} s)")
        try:
            jobs = [j for j in good["value"]["health"]["jobs"]
                    if not str(j.get("unit", "")).startswith("reader:")]
        except (KeyError, TypeError) as exc:
            return source_result("job_health", "Job health", read_at=started, took_ms=took,
                                 error=f"the stored value has no job rows ({type(exc).__name__})")
        value_at = reader_job._parse_iso(good.get("value_at"))
        jobs = _install_rows_asked_again(jobs)
        promise = doc.get("stale_after_seconds")
        where = f"stored by the reader, read in {good.get('took_ms', '?')} ms"
        try:
            live = (reader_job.health_rows() if readers_now is None else list(readers_now))
        except Exception as exc:                   # noqa: BLE001
            live = [{"unit": "reader:*", "what": "the reader jobs' liveness", "state": "unknown",
                     "detail": f"the readers could not be judged: {type(exc).__name__}: {exc}"}]
        jobs += live
    took = int((time.time() - started) * 1000)
    rows, expected = [], []
    for job in jobs:
        state = job.get("state", "")
        if state in J.OK_STATES:
            continue
        if state in EXPECTED_JOB_STATES:
            # Expected and nothing to do yet (the operator, 2026-10-02): said in
            # this source's finding, never as a row.
            expected.append(job.get("headline") or f"{job.get('unit', '?')}: {state}")
            continue
        # An unmapped state is drawn LOUD with its own name: a state added
        # to job_health later must not arrive here as something quieter.
        words, level = _JOB_STATES.get(state, (f"reads {state}", "danger"))
        device = job.get("device") or job.get("address")
        ops = {"job": job.get("what", ""), "state": state}
        # The network a job's row is about, where its check says (C493), and what a
        # not-monitored device lacks (C488's one cause, folded by `_fold_known_unmonitored`).
        if job.get("list"):
            ops["list"] = job["list"]
        if job.get("missing"):
            ops["missing"] = list(job["missing"])
        rows.append(row(
            source="job_health", kind="job", key=job.get("unit", "?"),
            # A row may name its own headline, in the reader's words ("edge1 is not
            # monitored by SNMP"); otherwise the unit and its state's words.
            what=job.get("headline") or f"{job.get('unit', '?')} {words}",
            devices=list(job.get("devices") or ([device] if device else [])),
            since=job.get("since"),
            cause=job.get("detail") or f"state {state}, with no detail recorded",
            operands=ops,
            action=_job_action(job), level=level,
            read_at=job.get("_read_at") or value_at or started))
    n_ok = len(jobs) - len(rows) - len(expected)
    return source_result("job_health", "Job health", read_at=started, took_ms=took,
                         rows=rows, value_at=value_at, stale_after_seconds=promise,
                         reader=JOB_HEALTH_READER if promise else None, detail=where,
                         checked=f"{len(jobs)} job-health row(s), {n_ok} ok"
                                 + (f"; expected, nothing to do yet: {'; '.join(expected)}"
                                    if expected else ""))


# ---------------------------------------------------------------------------
# Source: drift, with coverage (C96: the checker ran, found drift, and the
# panel drew none of it)
# ---------------------------------------------------------------------------

#: A stored run older than this many intervals is itself a row: the value on
#: the page is from a run that should have been superseded.
DRIFT_STALE_INTERVALS = 2

#: A drifted device's action when nothing is queued for it: both remedies
#: are on its Device page (7.1 steps 4 and 5). A queued drift item, when
#: there is one, attaches and its action replaces this.
_DRIFT_ACTION = {"label": "Capture what the device holds as its golden, or deploy its intent "
                          "back to it"}

#: Where a drift check is run and the schedule switched: Settings › Installation ›
#: Diagnostics, its Drift checks card (board F4). Today's Drift tab, which these rows named
#: until it left at 7.8 (2026-10-15), had no address.
_DRIFT_HOME = "/v2/settings/installation?tab=diagnostics"
_CHECK_NOW = "Run a drift check with Check now in Settings › Installation › Diagnostics"


def drift_source(status=None, now=None) -> dict:
    """The LAST drift run for the list on screen, from its stored record
    (section 0a: nothing re-checks a device to draw this page). Every device
    the run did not clear is a row, and so is the checker's own state: off,
    never run, a failed run, or a stored run too old to describe the network
    now."""
    from modules import drift_check as D

    started = time.time()
    now = now or started
    try:
        st = status() if status else D.get_checker().status(_page_network())
        interval = D._get_interval()
    except Exception as exc:                       # noqa: BLE001
        log.error("attention: drift status could not be read: %s", exc)
        return source_result("drift", "Drift", read_at=started,
                             took_ms=int((time.time() - started) * 1000),
                             error=f"it raised {type(exc).__name__}: {exc}")
    took = int((time.time() - started) * 1000)
    lst = st.get("list") or "?"
    last, last_ts = st.get("last_run"), st.get("last_ts") or None
    rows = []

    def add(key, what, cause, action, level, devices=(), since=None, operands=None):
        rows.append(row(source="drift", kind=key.split(":", 1)[0], key=f"{lst}:{key}",
                        what=what, cause=cause,
                        action=action, level=level, devices=devices, since=since,
                        operands={"list": lst, **(operands or {})}))

    if st.get("disabled"):
        by = st.get("disabled_by") or "nobody recorded"
        add("disabled", f"Drift checking is switched off for {lst}",
            f"switched off by {by}; nothing compares the devices with their "
            "goldens until it is switched back on",
            {"label": f"Turn {lst}'s drift checks on in Settings › Installation › Diagnostics",
             "href": _DRIFT_HOME},
            "warning", since=_ts(st.get("disabled_at")))
    if not last:
        add("never", f"No drift check has run yet for {lst}",
            "no drift run is recorded for this list, so whether any device has "
            "drifted is unknown",
            {"label": _CHECK_NOW, "href": _DRIFT_HOME}, "unknown")
        return source_result("drift", "Drift", read_at=started, took_ms=took, rows=rows,
                             checked=f"list {lst}: no drift run recorded")
    if last.get("ok") is False:
        add("failed", f"The last drift check for {lst} failed",
            last.get("summary") or last.get("error") or "no reason recorded",
            {"label": _CHECK_NOW + " and read its reason", "href": _DRIFT_HOME},
            "unknown", since=last_ts)
    elif last_ts and now - last_ts > DRIFT_STALE_INTERVALS * interval:
        add("stale", f"The last drift check for {lst} is old",
            f"it ran {int((now - last_ts) // 3600)} h ago, over "
            f"{DRIFT_STALE_INTERVALS} intervals of {int(interval // 60)} min: "
            "what it found describes the network as it was then",
            {"label": _CHECK_NOW, "href": _DRIFT_HOME}, "warning",
            since=last_ts + DRIFT_STALE_INTERVALS * interval)
    coverage = f"checked {last.get('checked', 0)} of {last.get('inventory', 0)}"
    for d in last.get("drifted_devices") or []:
        add(f"drifted:{d['hostname']}", f"{d['hostname']} has drifted from its golden",
            f"the running config differs from the committed golden by "
            f"{d.get('diff_lines', '?')} diff line(s), seen by the drift check at "
            f"{_iso(last_ts) or 'an unrecorded time'}; since when it has differed "
            "is not recorded",
            # Both answers on the row, each opening its card on the device page (the operator's
            # overnight list, item 7: before the AI family and its approval queue go, a drift
            # is answered here): Capture accepts what the device holds, Deploy puts intent back.
            dict(_DRIFT_ACTION, open="drift", device=d["hostname"], list=lst),
            "danger", devices=[d["hostname"]],
            operands={"diff_lines": d.get("diff_lines"), "coverage": coverage})
    for d in last.get("skipped") or []:
        no_golden = d.get("reason") == "no golden config saved"
        add(f"skipped:{d['hostname']}", f"{d['hostname']} was not checked for drift",
            d.get("reason") or "no reason recorded",
            # C1153: v2's way, never today's index's no-golden capture scope. Devices filtered
            # to the state "no golden" lists every device without one; ticked, Actions › Save
            # records each as golden (and saves it to startup).
            {"label": "Capture it from its device page (Actions › Capture), or on Devices "
                      "choose the state \"no golden\", tick the devices and choose Actions › "
                      "Save…",
             "href": "/v2/devices?" + urlencode({"state": "no_golden", "list": lst})}
            if no_golden else
            {"label": "Clear what the reason names, then " + _CHECK_NOW[0].lower()
                      + _CHECK_NOW[1:], "href": _DRIFT_HOME, "known": False},
            "warning", devices=[d["hostname"]], operands={"coverage": coverage})
    for d in last.get("errors") or []:
        # During a boot the reachability reader saw the device go silent: said
        # first, so a booting device does not read as a broken one.
        from modules.readers.reachability import outage_words
        booting = outage_words(d["hostname"], _ts(last_ts) or now)
        add(f"unreachable:{d['hostname']}", f"{d['hostname']} could not be checked for drift",
            (f"{booting[0].upper()}{booting[1:]}. The check said: " if booting else "")
            + (d.get("reason") or "no reason recorded"),
            {"label": "Check the device answers (its status on Devices), then "
                      + _CHECK_NOW[0].lower() + _CHECK_NOW[1:], "href": _DRIFT_HOME,
             "known": False},
            "unknown", devices=[d["hostname"]], operands={"coverage": coverage})
    return source_result("drift", "Drift", read_at=started, took_ms=took, rows=rows,
                         value_at=last_ts,
                         stale_after_seconds=int(DRIFT_STALE_INTERVALS * interval) or None,
                         checked=f"list {lst}, the run of {_iso(last_ts) or 'an unrecorded time'}: "
                                 f"{coverage}, triggered by {last.get('triggered_by') or 'unrecorded'}")


def _page_network() -> str:
    """The network the page is about, for the sources kept per network (drift, approvals,
    onboarding, rollbacks, deploys, baselines, authorisations): on a v2 request the network its
    address or its person names, as the page's header does (`listref.active_name`), else the
    installation's current list. C487: these read the installation's current list while the
    page named another, so one network's rows were drawn under another's name."""
    from modules.nsot import listref

    return listref.active_name()


def _ts(value):
    """An epoch from a stored time that may be epoch or ISO text; None if neither."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        import calendar
        return float(calendar.timegm(time.strptime(str(value)[:19], "%Y-%m-%dT%H:%M:%S")))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Source: the approval queue
# ---------------------------------------------------------------------------

#: The action types drift queues, one item per drifted device. Each is ABOUT
#: that device's drift row and attaches to it.
_DRIFT_ITEM_TYPES = ("update_golden_config",)


def approvals_source(read=None) -> dict:
    """Every pending approval, through a read that writes nothing. A queued
    drift item attaches to its device's drift row (the page must not count
    one event twice); anything else is a row of its own."""
    from modules import approval_queue as Q

    started = time.time()
    try:
        lst = _page_network()
        pending, reason = (read or (lambda: Q.read_pending(lst)))()
    except Exception as exc:                       # noqa: BLE001
        pending, reason = None, f"it raised {type(exc).__name__}: {exc}"
    took = int((time.time() - started) * 1000)
    if reason:
        return source_result("approvals", "Approvals", read_at=started, took_ms=took,
                             error=reason)
    rows = []
    for e in pending:
        host = e.get("device_hostname") or e.get("device_ip") or ""
        drift_item = e.get("action_type") in _DRIFT_ITEM_TYPES and host
        rows.append(row(
            source="approvals", kind="pending", key=e.get("id") or "?",
            what=f"An approval is waiting: {e.get('description') or e.get('action_type')}",
            cause=(e.get("context") or "queued with no context recorded")
                  + "; nothing is done until a person approves it",
            # Today's Approvals tab left with the AI family (D15): a capture closes the item,
            # from the device's History tab; one naming no device can only expire.
            action=({"label": f"Capture {host}'s golden from its History tab, which closes "
                              "this; or let it expire",
                     "href": f"/v2/device/{host}?tab=history"} if host else
                    {"label": "Let it expire: it names no device to capture"}),
            level="warning", devices=[host] if host else [], since=e.get("created_ts"),
            clears_at=((e.get("created_ts") or 0) + Q.EXPIRY_HOURS * 3600
                       if e.get("created_ts") else None),
            operands={"kind": e.get("action_type", ""), "list": lst},
            attach_to=f"drift:{lst}:drifted:{host}" if drift_item else None))
    return source_result("approvals", "Approvals", read_at=started, took_ms=took,
                         rows=rows, checked=f"list {lst}: {len(rows)} pending approval(s)")


# ---------------------------------------------------------------------------
# Source: pending onboardings
# ---------------------------------------------------------------------------

def pending_onboarding_source(pending=None, now=None) -> dict:
    """Devices onboarded and never reached. `in_flight` (under a day) is the
    normal state of an onboarding and is counted, not listed; overdue, stale
    and a staged credential nothing can find are rows. ZTP progress is not
    asked here: it asks Kea per device (section 0a); the pending device's
    page carries it, and each row opens that page (Verify…, Abandon…; today's
    pending banner, which the rows named with no link, left at 7.8)."""
    import os
    from urllib.parse import quote

    from modules.config import get_list_data_dir
    from modules.nsot.manifest import pending_devices

    started = time.time()
    try:
        lst = _page_network()
        devices = (pending or (lambda: pending_devices(
            os.path.join(get_list_data_dir(lst), "config_repo"))))()
    except Exception as exc:                       # noqa: BLE001
        return source_result("onboarding", "Pending onboardings", read_at=started,
                             took_ms=int((time.time() - started) * 1000),
                             error=f"it raised {type(exc).__name__}: {exc}")
    took = int((time.time() - started) * 1000)
    rows = []
    for d in devices:
        name, state = d.get("name") or d.get("identity") or "?", d.get("state")
        since = _ts(d.get("onboarded_at"))
        page = f"/v2/device/{quote(name, safe='')}?list={quote(lst, safe='')}"
        if d.get("credential_findable") is False:
            rows.append(row(
                source="onboarding", kind="credential", key=f"{lst}:{name}:credential", level="danger",
                what=f"{name} cannot be verified: its staged credential cannot be found",
                cause=("the credential staged for it is not where verification looks, so "
                       "Verify would try a profile the device refuses; nothing has reached "
                       "the device, so there is nothing to undo"),
                action={"label": "Abandon it and onboard it again, from its page",
                        "href": page},
                devices=[name], since=since, operands={"list": lst, "state": state}))
        elif state in ("overdue", "stale"):
            hours = int((d.get("age_seconds") or 0) // 3600)
            rows.append(row(
                source="onboarding", kind="overdue", key=f"{lst}:{name}", level="warning",
                what=f"{name} was onboarded {hours} h ago and has never been reached",
                cause=("it is in the manifest and git and not in the inventory: nothing "
                       "polls, backs up or drift-checks it until Verify reaches it"),
                action={"label": "Verify it, or Abandon it, from its page", "href": page},
                devices=[name], since=since, operands={"list": lst, "state": state,
                                                       "address_source": d.get("address_source")}))
    quiet = sum(1 for d in devices if d.get("state") == "in_flight"
                and d.get("credential_findable") is not False)
    return source_result("onboarding", "Pending onboardings", read_at=started, took_ms=took,
                         rows=rows,
                         checked=f"list {lst}: {len(devices)} pending, {quiet} within their "
                                 "first day")


# ---------------------------------------------------------------------------
# Source: rollback blocks
# ---------------------------------------------------------------------------

def _rollback_action(lst: str, host: str) -> dict:
    """Revert intent and Retry are the remedies, each a card on the device's page since 7.3
    (C544): the row offers both, as the deploy's result card does (`open`, drawn as the two
    buttons of `v2/_attention.html`)."""
    return {"label": "Revert intent… if the change was wrong, or Retry with a reason… if it "
                     "was right and the failure was elsewhere: each opens its card on the "
                     "device's page",
            "open": "revert_retry", "device": host, "list": lst}


def rollback_source(notes=None) -> dict:
    """Devices whose rolled-back change still blocks their next plan. Uses
    the ONE classifier the listing uses (`rolled_back_notes`): a note blocks
    only while the program a fresh plan would send still contains what failed,
    so a stale note is counted, never listed as needing attention. Its work
    is per NOTED device, bounded by the rollbacks on record."""

    started = time.time()
    try:
        lst = _page_network()
        if notes is None:
            from routes.templatize import rolled_back_notes
            got = rolled_back_notes(lst)
        else:
            got = notes()
    except Exception as exc:                       # noqa: BLE001
        return source_result("rollback", "Rollback blocks", read_at=started,
                             took_ms=int((time.time() - started) * 1000),
                             error=f"it raised {type(exc).__name__}: {exc}")
    took = int((time.time() - started) * 1000)
    rows = []
    if got.get("unreadable"):
        # One row for the list: the record blocks EVERY plan, and a row per
        # device would be one event counted N times.
        rows.append(row(source="rollback", kind="record", key=f"{lst}:record", level="danger",
                        what=f"Every plan on {lst} is blocked: the rolled-back record "
                             "cannot be read",
                        cause=got["unreadable"],
                        action={"label": "Repair the record from its preserved copy; "
                                         "nothing here can rewrite it", "known": False},
                        operands={"list": lst}))
    for host, note in sorted((got.get("applies") or {}).items()):
        unknown = note.get("applicability") == "unknown"
        rows.append(row(
            source="rollback", kind="blocked", key=f"{lst}:{host}", level="unknown" if unknown else "warning",
            what=(f"{host}'s rolled-back change may still block its next plan" if unknown
                  else f"{host}'s next plan is blocked: its intent still sends what was "
                       "rolled back"),
            cause=(f"rolled back at {note.get('at') or 'an unrecorded time'}"
                   + (f" ({note['reason']})" if note.get("reason") else "")
                   + ("; whether the note still applies could not be computed"
                      if unknown else "")),
            action=_rollback_action(lst, host), devices=[host], since=_ts(note.get("at")),
            operands={"list": lst, "failed_lines": len(note.get("commands") or []),
                      "intent_commit": (note.get("intent_commit") or "")[:10]}))
    n_stale = len(got.get("stale") or {})
    return source_result("rollback", "Rollback blocks", read_at=started, took_ms=took,
                         rows=rows,
                         checked=(f"list {lst}: the rolled-back record could not be read"
                                  if got.get("unreadable") else
                                  f"list {lst}: {len(got.get('applies') or {})} standing, "
                                  f"{n_stale} no longer blocking"))


# ---------------------------------------------------------------------------
# Source: a deploy or restore that did not finish clean
# ---------------------------------------------------------------------------

def _saved_since(saves=None) -> tuple:
    """``({device: epoch}, why_not)``: when each device's latest save was read back SAFE
    (its startup config carrying what it runs), from the save record its page's Persist, Save,
    adopt and a rotation's persistence write (`onboard._record_native_persist`,
    `credential_rotation.record_outcome`). A record that cannot be read is *why_not*, and
    counts no save (C543: the unsaved row stays rather than clear on a save nobody can see)."""
    from modules.nsot import credential_rotation as cr

    try:
        records = cr.rotation_records_as_known() if saves is None else saves()
    except Exception as exc:                       # noqa: BLE001
        return {}, f"the save record could not be read ({type(exc).__name__}: {exc})"
    out = {}
    for rec in records:
        at = _ts(rec.get("at"))
        if rec.get("device") and at and rec.get("state") in (cr.SAVE_PERSISTED,
                                                              cr.ROTATED_PERSISTED):
            out[rec["device"]] = max(at, out.get(rec["device"], 0))
    return out, ""


def _only_unsaved(r: dict) -> bool:
    """A receipt row whose ONE fault is the save to startup (C511, C543): deployed, verified,
    the program it confirmed, and not saved. Judged by the result's own decision with the
    save taken as done, so the two cannot disagree about what else would make it not clean."""
    from modules.nsot import receipts
    from modules.preview_confirm import result_level

    return (r.get("outcome") == "deployed" and not receipts.is_pending(r)
            and (r.get("saved_startup") or {}).get("state") == "not_saved"
            and result_level([dict(r, saved_startup={"state": "saved"})],
                             receipt_ok=True) == "success")


def _persist_action(lst: str, host: str, label: str) -> dict:
    """Persist on the device's page (`open`, drawn as its button in `v2/_attention.html`)."""
    return {"label": label, "open": "persist", "device": host, "list": lst}


#: Verify's protocol keys (`pipeline`'s intent-declared protocols) as a person reads them.
_PROTO_WORDS = {"ospf": "OSPF", "ospfv3": "OSPFv3", "bgp": "BGP", "rip": "RIP",
                "ripng": "RIPng", "eigrp": "EIGRP", "isis": "IS-IS"}


def _unmet_protocols(unmet: list) -> list:
    """The protocol keys Verify names in its "declared by intent and is not up" lines, each
    line's first word (`pipeline`'s wording); a line of another shape names none."""
    out = []
    for line in unmet:
        m = re.match(r"^(\w+) is declared by intent and is not up after the change", line)
        if m and m.group(1).lower() in _PROTO_WORDS:
            out.append(m.group(1).lower())
    return out


def _adjacency_states(cached=None) -> dict:
    """``{"states", "at", "why"}``: the adjacency reader's stored per-device protocol states
    (C1450), when they were read, and why there are none (a read that failed is never "up")."""
    from modules import reader_job

    got = reader_job.read_cached("adjacencies") if cached is None else cached
    good = (got.get("doc") or {}).get("last_good") or {}
    if got.get("state") != "ok" or not good:
        return {"states": {}, "at": 0.0,
                "why": "the adjacency reader has no stored value: " + str(got.get("why") or "")}
    return {"states": (good.get("value") or {}).get("states") or {},
            "at": _ts(good.get("value_at")) or 0.0, "why": ""}


def deploy_source(read=None, saves=None, adjacency=None) -> dict:
    """Each device's LATEST deploy or restore receipt, judged by the ONE
    decision the result screen uses (`preview_confirm.result_level`): a row
    unless it finished clean. A later clean run supersedes an earlier
    failure, so a device leaves the page by being deployed, not by aging.
    Danger when a program was SENT (the device may be part-changed), warning
    when nothing was (a refusal changed nothing, and the change it was for
    still has not landed).

    The action follows the outcome (C543): a change verified and running and NOT saved to
    startup is its own kind, `unsaved`, a warning whose action is Persist on the device's
    page, and a save read back SAFE after the receipt clears it; any other fault reads its
    receipt and plans again, offering Persist too when the change is also unsaved."""
    from modules.nsot import receipts
    from modules.preview_confirm import (OUTCOME_WORDS, SAVED_STARTUP_WORDS, read_back_missed,
                                         result_level)

    started = time.time()
    try:
        lst = _page_network()
        got = (read or (lambda: receipts.read(lst, limit=10 ** 6)))()
    except Exception as exc:                       # noqa: BLE001
        got = {"state": "unreadable", "error": f"it raised {type(exc).__name__}: {exc}"}
    took = int((time.time() - started) * 1000)
    if got.get("state") == "unreadable":
        return source_result("deploys", "Deploys and restores", read_at=started, took_ms=took,
                             error=f"the deploy receipts could not be read ({got.get('error')})")
    latest = {}
    # A retired device's receipts are not a new device's of the name (C1334): only receipts
    # after the name's newest retirement are the device's now (they stay on History).
    for r in receipts.current_rows(lst, got.get("rows") or []):       # newest first
        latest.setdefault(r.get("device") or "?", r)
    rows, pending_named, saved_later, met_later, adj = [], 0, 0, 0, None
    # Read only when a device's one fault is the save: one read of one record, not per device.
    saved_at, saves_unread = ((_saved_since(saves)) if any(
        _only_unsaved(r) for r in latest.values()) else ({}, ""))
    for host, r in sorted(latest.items()):
        if receipts.is_pending(r) and _pending_is_named(lst, host, r):
            # Written as the device finished, its batch's commit not recorded yet: its batch
            # is still running (the device is held), or its process ended and the
            # interrupted-operation row names it. Either way not clean, and not a second row.
            pending_named += 1
            continue
        if result_level([r], receipt_ok=True) == "success":
            continue
        saved = r.get("saved_startup") or {}
        unsaved_words = (SAVED_STARTUP_WORDS["not_saved"] + ": "
                         + (saved.get("detail") or "no reason was recorded")
                         if saved.get("state") == "not_saved" else "")
        if _only_unsaved(r):
            # At or after the receipt's last line, to the second both are recorded in: the
            # deploy held the device until then, so a save of it in that second came after.
            if saved_at.get(host, 0) >= (_ts(r.get("completed_at") or r.get("at"))
                                         or float("inf")):
                saved_later += 1                   # saved since, by a Persist or a Save
                continue
            rows.append(row(
                source="deploys", kind="unsaved", key=f"{lst}:{host}", level="warning",
                what=(f"The last {receipts.noun(r)} to {host} is running and NOT "
                      "saved to startup: a reload loses it"),
                cause=unsaved_words + (f"; {saves_unread}" if saves_unread else ""),
                action=_persist_action(lst, host, (
                    f"Persist {host}: Persist… on its device page saves what it runs to "
                    "startup and reads it back")),
                devices=[host], since=_ts(r.get("at")),
                operands={"list": lst, "action": r.get("action"),
                          "outcome": r.get("outcome", ""),
                          "sent_lines": r.get("program_lines") or 0, "by": r.get("actor")}))
            continue
        outcome = r.get("outcome", "")
        rb = r.get("rollback") or {}
        checks = r.get("checks") or {}
        issues = [str(i) for i in checks.get("issues") or []]
        unmet = [str(p) for p in checks.get("intent_unmet") or []]
        unread = [str(p) for p in checks.get("unreadable") or []]
        protos = _unmet_protocols(unmet)
        # C1542: the read-back's misses, masked, unless an issue already says them (Coverage's
        # combined deploy puts them in its issues and rolls back over them).
        missed = ("" if any("did not read back" in i for i in issues)
                  else read_back_missed(checks))
        landed = (outcome == "deployed" and not issues and not unread
                  and not rb.get("performed") and not r.get("stage")
                  and r.get("matches_confirmed") is not False and not receipts.is_pending(r)
                  and not unsaved_words)
        if landed and missed and not unmet:
            # C1542: sent whole (the push raised nothing and the program sent is the one
            # confirmed) and saved to startup, its golden then recorded from what the device
            # runs after it (`save_golden` runs when verify did not fail); its one fault is
            # lines verify could not find in the configuration it read back. A WARNING, not
            # danger: danger is for a device that may be part-changed in a way nothing
            # recorded (a push that stopped part-way, a rollback that did not restore). Here
            # every line was accepted, and the question left is only whether the device
            # prints those lines in another form (a router printing `line vty 0 4` as
            # `line vty 0`, `1`, `2 4`: C1541) or lacks them, which the person reads in the
            # golden. The result card draws the same deploy amber (`result_level`'s partial),
            # so the two screens agree.
            n = len(((checks.get("read_back") or {}).get("missing")) or [])
            rows.append(row(
                source="deploys", kind="read_back", key=f"{lst}:{host}", level="warning",
                what=(f"The last {receipts.noun(r)} to {host} landed; verify could not read "
                      f"back {n} line(s)"),
                cause=(missed + ". The push raised nothing, the program sent matches the one "
                       "confirmed, and it was saved to startup"),
                action={"label": (f"Read those lines in {host}'s golden on its History tab: "
                                  "if the device prints them in another form, acknowledge "
                                  "this deploy with that reason; if they are absent, plan "
                                  "the deploy again"),
                        "href": f"/v2/device/{host}?tab=history"},
                devices=[host], since=_ts(r.get("at")),
                # This deploy, never a later one: a later deploy that misses again is a new
                # row to acknowledge (acknowledgements.py).
                event=str(r.get("completed_at") or r.get("at") or ""),
                operands={"list": lst, "action": r.get("action"), "outcome": outcome,
                          "sent_lines": r.get("program_lines") or 0,
                          "not_read_back": n, "by": r.get("actor")}))
            continue
        if (outcome == "deployed" and protos and len(protos) == len(unmet) and not issues
                and not missed
                and not unread and not rb.get("performed") and not r.get("stage")
                and r.get("matches_confirmed") is not False and not receipts.is_pending(r)
                and not unsaved_words):
            # C1450: landed, read back and saved; only a protocol intent declares was not up
            # after it, often for want of a peer not built yet. It clears when the adjacency
            # reader, reading after the receipt, sees each up; until then it says what is unmet.
            if adj is None:
                adj = _adjacency_states(adjacency)
            states = adj["states"].get(f"{lst}:{host}") or {}
            if adj["at"] > (_ts(r.get("completed_at") or r.get("at")) or float("inf")) and \
                    all(states.get(p) == "up" for p in protos):
                met_later += 1
                continue
            named = ", ".join(_PROTO_WORDS.get(p, p) for p in protos)
            now_words = "; ".join(f"{_PROTO_WORDS.get(p, p)} {states.get(p, 'not read')}"
                                  for p in protos)
            rows.append(row(
                source="deploys", kind="unmet", key=f"{lst}:{host}", level="warning",
                what=(f"The last {receipts.noun(r)} to {host} landed, and {named} declared by "
                      "its intent was not up after it"),
                cause=("; ".join(unmet) + f". The adjacency reader now reads: {now_words}"
                       + (f" ({adj['why']})" if adj["why"] else "")),
                action={"label": (f"Build or check {host}'s {named} peer: this clears when the "
                                  "adjacency reader sees it up. If the peer exists, read the "
                                  "receipt on the device's History tab"),
                        "href": f"/v2/device/{host}?tab=history"},
                devices=[host], since=_ts(r.get("at")),
                operands={"list": lst, "action": r.get("action"), "outcome": outcome,
                          "unmet": protos, "by": r.get("actor")}))
            continue
        cause = "; ".join(x for x in (
            r.get("reason"),
            f"stopped at {r['stage']}" if r.get("stage") else "",
            f"verify found: {'; '.join(issues)}" if issues else "",
            f"declared by intent and not up after: {', '.join(unmet)}" if unmet else "",
            f"could not be read reliably after the change: {'; '.join(unread)}"
            if unread else "",
            # C1542: a read-back miss is said, never dropped to "no reason".
            missed,
            f"rollback: {rb.get('state')}" if rb.get("performed") else "",
            "the program sent does NOT match the one confirmed"
            if r.get("matches_confirmed") is False else "",
            # Pending, held by nothing and named by no interrupted operation: the line that
            # completes it could not be written (its result said RECEIPT NOT WRITTEN).
            "its receipt was written as the device finished and never completed with its "
            "batch's commit" if receipts.is_pending(r) else "",
            # C543: said with whatever else is wrong, never dropped from the cause.
            unsaved_words) if x) or \
            f"its receipt records {outcome or 'no outcome'} with no reason"
        words = OUTCOME_WORDS.get(outcome, outcome.replace('_', ' ') or 'no outcome')
        if receipts.is_pending(r):
            words = ("sent" if outcome == "deployed" else words) + ", " + receipts.PENDING_WORDS
        elif outcome == "deployed" and checks.get("ran") and checks.get("ok") is not True:
            # The words follow what failed (C1542): it landed, and its verify did not pass.
            words += ", and its verify did not pass"
        # The receipt is read on the device page's History tab (v2 has no Changes tab).
        read_it = "Read its receipt on the device's History tab, then plan again"
        rows.append(row(
            source="deploys", kind="failed", key=f"{lst}:{host}",
            level="danger" if r.get("sent") else "warning",
            what=f"The last {receipts.noun(r)} to {host}: {words}",
            cause=cause,
            action=(_persist_action(lst, host, read_it + f"; what {host} runs now is not "
                                    "saved to startup, and Persist… on its device page saves "
                                    "it meanwhile") if unsaved_words else
                    {"label": read_it, "href": f"/v2/device/{host}?tab=history"}),
            devices=[host], since=_ts(r.get("at")),
            operands={"list": lst, "action": r.get("action"), "outcome": outcome,
                      "sent_lines": r.get("program_lines") if r.get("sent") else 0,
                      "by": r.get("actor")}))
    return source_result("deploys", "Deploys and restores", read_at=started, took_ms=took,
                         rows=rows,
                         checked=(f"list {lst}: no deploy or restore recorded"
                                  if got.get("state") == "absent" else
                                  f"list {lst}: the latest receipt of {len(latest)} device(s), "
                                  f"{len(latest) - len(rows) - pending_named - saved_later - met_later} "
                                  "clean"
                                  + (f", {met_later} with a protocol unmet after the deploy and "
                                     "up since (the adjacency reader)" if met_later else "")
                                  + (f", {pending_named} commit PENDING (a batch still "
                                     "running, or an interrupted operation named under "
                                     "Operations that did not finish)" if pending_named
                                     else "")
                                  + (f", {saved_later} not saved to startup by the deploy "
                                     "and saved since (a save read it back)" if saved_later
                                     else "")))


def _pending_is_named(lst: str, host: str, r: dict) -> bool:
    """Whether a pending receipt is accounted for elsewhere: its device is held now (its
    batch is still running) or an interrupted operation on it started before the row.

    Holds that cannot be read (C988) name nothing: the pending receipt is drawn as its own
    row, true either way, rather than hidden on a read that failed, and the interrupted
    operations' source says the holds could not be read."""
    from modules.nsot import device_ops

    try:
        if device_ops.holder(lst, host):
            return True
        at = _ts(r.get("at")) or 0
        return any(i.get("device") == host and (i.get("started") or 0) <= at + 1
                   for i in device_ops.interrupted(lst))
    except OSError as exc:
        log.warning("attention: %s's hold could not be read (%s); its pending receipt is "
                    "drawn as its own row", host, exc)
        return False


# ---------------------------------------------------------------------------
# Source: the last baseline decision (a baseline that was not earned)
# ---------------------------------------------------------------------------

def baseline_source(log_fn=None) -> dict:
    """The NEWEST `Baseline:` decision recorded in the list's golden history
    (`save_golden()` writes it into the commit it judged). A row when that
    decision was a denial, with its reasons; a later earned baseline
    supersedes it. One `git log`, never a read per device (section 0a).
    Commits before 2026-09-28 carry no decision, and the source says so
    rather than reading their silence as either answer."""
    import os

    from modules.config import get_list_data_dir

    started = time.time()
    try:
        lst = _page_network()
        if log_fn is None:
            from modules.nsot.repo import git
            repo = os.path.join(get_list_data_dir(lst), "config_repo")
            rc, out, err = git(repo, "log", "-1", "-E", "--grep=^Baseline: ",
                               "--format=%H%x1f%ct%x1f%B")
            if rc != 0:
                raise RuntimeError(f"git log failed: {err.strip() or rc}")
        else:
            out = log_fn()
    except Exception as exc:                       # noqa: BLE001
        return source_result("baseline", "Baseline", read_at=started,
                             took_ms=int((time.time() - started) * 1000),
                             error=f"it raised {type(exc).__name__}: {exc}")
    took = int((time.time() - started) * 1000)
    if not out.strip():
        # The host's state on 2026-09-28: no decision recorded yet, and no
        # baseline usable. The usability row must not wait for a decision.
        usability = _baseline_usability_row(lst)
        return source_result("baseline", "Baseline", read_at=started, took_ms=took,
                             rows=usability["rows"],
                             checked=f"list {lst}: no baseline decision recorded yet "
                                     "(decisions are recorded from 2026-09-28); "
                                     + usability["checked"])
    sha, ct, body = out.split("\x1f", 2)
    decision = next((ln.split(":", 1)[1].strip() for ln in body.splitlines()
                     if ln.startswith("Baseline: ")), "")
    source_line = next((ln.split(":", 1)[1].strip() for ln in body.splitlines()
                        if ln.startswith("Source: ")), "")
    at = float(ct)
    rows = []
    reasons = decision.split(":", 1)[1].strip() if ":" in decision else ""
    # ONE row when the last decision was a denial AND no stored baseline is
    # usable: both say "there is no restore point", and the denial names the
    # blocker, which the usability row's remedy must name too (the operator,
    # 2026-09-28: "take a current one with Save All" was followed and could
    # not succeed while r2 departed from its intent).
    blocker = ({"reasons": reasons or "the decision recorded no reason",
                "commit": sha[:10], "at": _iso(at)}
               if decision.startswith("denied") else None)
    # A partial operation's decision is not a denied Save All (C885, walk W1: s2's Mode B
    # deploy, "8 device(s) not targeted", read as "the last Save All was denied" with "Save
    # All alone will be refused again"; all nine were at intent and the next Save All earned
    # one). Nothing was judged to depart, so its remedy is Save All alone.
    from modules.nsot.repo import not_targeted_only
    partial = not_targeted_only(reasons) if blocker else 0
    if partial:
        blocker.update(partial=partial, operation=_operation_words(source_line, body))
    usability = _baseline_usability_row(lst, blocker=blocker)
    if partial and not usability["rows"]:
        rows.append(row(
            source="baseline", kind="denied", key=f"{lst}:last", level="warning",
            what=(f"The last commit earned no baseline: {blocker['operation']} did not cover "
                  "the network"),
            cause=(f"{_not_covered_words(blocker)} That is a partial operation's decision, "
                   "not a Save All denied for departures: no device was judged to depart "
                   "from its intent"),
            action={"label": "Save All takes one: it captures every device and earns a "
                             "baseline if each is at its committed intent; if not, it records "
                             "the denial and names the device and its lines"},
            since=at, operands={"list": lst, "commit": sha[:10], "source": source_line}))
    elif decision.startswith("denied") and not usability["rows"]:
        rows.append(row(
            source="baseline", kind="denied", key=f"{lst}:last", level="warning",
            what=f"The network's last baseline was not earned ({source_line or 'a save'})",
            # The decision's OWN commit and time: a Save All that changed
            # nothing since decided without a commit to carry it, so this can
            # be older than the newest save, and the row says whose it is.
            cause=(reasons or "the decision recorded no reason")
                  + f" (decided by commit {sha[:10]} at {_iso(at)}; a save since that made "
                    "no decision, a one-device capture or a Save All that changed nothing, "
                    "leaves it standing)",
            action={"label": "Resolve each departure the reasons name, one of two ways "
                             "that mean opposite things: change the DEVICE (a line intent "
                             "has is deployed; a line only the device has is removed by hand, "
                             "since the tool never removes one) if intent is right, or Edit "
                             "INTENT if the device is right. Then Save All"},
            since=at, operands={"list": lst, "commit": sha[:10], "source": source_line}))
    rows += usability["rows"]
    return source_result("baseline", "Baseline", read_at=started, took_ms=took, rows=rows,
                         value_at=at,
                         checked=f"list {lst}: the last baseline decision, {sha[:10]}: "
                                 f"{decision.split(':', 1)[0] or 'unreadable'}; "
                                 + usability["checked"])


def _operation_words(source: str, body: str) -> str:
    """What the commit that decided was, in words: its `Source:` (`device_list.SOURCE_WORDS`)
    and the devices it named (`Devices:`, else `Devices-Measured:`), as "a deploy to s2"."""
    from modules.device_list import SOURCE_WORDS

    how = SOURCE_WORDS.get(source, (source or "").replace("_", " ") or "a save")
    named = next((ln.split(":", 1)[1].strip() for key in ("Devices: ", "Devices-Measured: ")
                  for ln in (body or "").splitlines() if ln.startswith(key)), "")
    names = [n for n in named.split(",") if n.strip()]
    if not names:
        return how
    return f"{how} to {', '.join(names[:3])}" + (f" and {len(names) - 3} more"
                                                  if len(names) > 3 else "")


def _not_covered_words(blocker: dict) -> str:
    """The sentence for a partial operation's decision (C885), naming its commit."""
    return (f"The last commit ({blocker['operation']}, commit {blocker['commit']} at "
            f"{blocker['at']}) did not cover the network ({blocker['partial']} device(s) not "
            "targeted), so it earned no baseline: Save All takes one.")


def _baseline_usability_row(lst: str, cached=None, blocker: dict = None) -> dict:
    """No stored baseline can be re-applied (the operator, 2026-09-28): every
    one predates a credential rotation (the restore's guard refuses each,
    C75) or is withdrawn. The Baselines panel said it once per row and never
    once. Read from the `baseline-usability` reader (the per-row check costs
    8 to 9 s on the host); a reader that has not answered is job health's row,
    so this says only what it read."""
    from modules import reader_job

    got = reader_job.read_cached("baseline-usability") if cached is None else cached
    good = ((got.get("doc") or {}).get("last_good") or {})
    value = ((good.get("value") or {}).get("lists") or {}).get(lst)
    if got.get("state") != "ok" or value is None:
        return {"rows": [], "checked": "whether a baseline can be re-applied: not judged yet"}
    if value.get("error"):
        return {"rows": [], "checked": f"whether a baseline can be re-applied: {value['error']}"}
    if value.get("usable"):
        return {"rows": [], "checked": f"{value['usable']} can be re-applied"}
    if not value.get("count"):
        return {"rows": [], "checked": "no baseline is stored yet"}
    newest = next((b for b in value["baselines"] if not b["withdrawn"]), None)
    withdrawn = [b["tag"] for b in value["baselines"] if b["withdrawn"]]
    # A partial operation's decision blocks nothing (C885): it is said as what it was, and
    # the remedy is Save All alone.
    partial = blocker if blocker and blocker.get("partial") else None
    blocker = None if partial else blocker
    cause = (f"all {value['count']} stored baseline(s) predate a credential rotation or are "
             "withdrawn, so the restore's credential guard (C75) refuses part of any re-apply."
             + (f" The newest, {newest['tag']}, would change the credential on "
                f"{', '.join(newest['stale'])}." if newest else "")
             + (f" Withdrawn: {', '.join(withdrawn)}." if withdrawn else "")
             + " A baseline's usefulness decays with every rotation."
             + (f" A new one cannot be earned right now: the last Save All was denied "
                f"({blocker['reasons']}; commit {blocker['commit']} at {blocker['at']})."
                if blocker else "")
             + (" " + _not_covered_words(partial) if partial else ""))
    action = ({"label": "Resolve each departure the denial names, one of two ways that mean "
                        "opposite things: change the DEVICE if intent is right (a line only the "
                        "device has is removed by hand: the tool never removes one), or Edit "
                        "INTENT if the device is right. Then Save All. Save All alone will be "
                        "refused again while it departs"}
              if blocker else
              {"label": "Take a current baseline: Save All captures every device, and earns "
                        "a baseline if each is at its committed intent; if not, it records "
                        "the denial and names the device and its lines"})
    return {"rows": [row(
        source="baseline", kind="unusable", key=f"{lst}:unusable", level="warning",
        what=("No stored baseline can be re-applied, and a new one cannot be earned yet"
              if blocker else "No stored baseline can be re-applied"),
        cause=cause,
        action=action,
        operands={"list": lst, "baselines": str(value["count"]),
                  "newest": newest["tag"] if newest else "none"},
        since=_ts(good.get("value_at")))],
        "checked": "no baseline can be re-applied"}


# ---------------------------------------------------------------------------
# Source: a line authorised again and again (C140 (1))
# ---------------------------------------------------------------------------

#: How many authorisations of ONE line on ONE device make a pattern. Twice
#: can be a retry after a failed push; a third time is a routine, and an
#: exception that is routine is what 8.8 wants seen ("ok" typed thirty
#: times is the finding, not a defeat of the control).
REPEAT_THRESHOLD = 3


def authorisation_source(counts=None) -> dict:
    """The same dangerous or secret line authorised on the same device at
    least `REPEAT_THRESHOLD` times, from ONE read of the receipts through the
    counting the preview's aggregate uses. It makes behaviour visible; it
    blocks nothing."""
    from modules.nsot import receipts

    started = time.time()
    try:
        lst = _page_network()
        got = (counts or (lambda: receipts.authorisations_by_device(lst)))()
    except Exception as exc:                       # noqa: BLE001
        got = {"state": "unreadable", "error": f"it raised {type(exc).__name__}: {exc}"}
    took = int((time.time() - started) * 1000)
    if got.get("state") == "unreadable":
        return source_result("authorisations", "Repeated authorisations", read_at=started,
                             took_ms=took,
                             error=f"the deploy receipts could not be read ({got.get('error')})")
    rows, n_lines = [], 0
    for device, lines in sorted((got.get("devices") or {}).items()):
        for line, e in sorted(lines.items()):
            n_lines += 1
            if e.get("count", 0) < REPEAT_THRESHOLD:
                continue
            rows.append(row(
                source="authorisations", kind="repeated", key=f"{lst}:{device}:{line}", level="warning",
                what=f"{line.strip()!r} has been authorised {e['count']} times on {device}",
                cause=(f"last by {e.get('last_actor') or 'an unrecorded actor'} at "
                       f"{e.get('last_at') or 'an unrecorded time'}, stated reason: "
                       f"{e.get('last_reason')}. An exception authorised again and again "
                       "is a routine, not an exception"),
                action={"label": "Read the stated reasons on the device's History tab: a line "
                                 "authorised routinely belongs in intent, or its cause does"},
                devices=[device], since=_ts(e.get("first_at")),
                event=f"{e['count']} authorisations, the last at {e.get('last_at') or 'an unrecorded time'}",
                operands={"list": lst, "count": e["count"], "threshold": REPEAT_THRESHOLD,
                          "last_at": e.get("last_at")}))
    return source_result("authorisations", "Repeated authorisations", read_at=started,
                         took_ms=took, rows=rows,
                         checked=(f"list {lst}: no deploy or restore recorded"
                                  if got.get("state") == "absent" else
                                  f"list {lst}: {n_lines} authorised line(s) across "
                                  f"{len(got.get('devices') or {})} device(s), a row from "
                                  f"{REPEAT_THRESHOLD} authorisations"))


#: Every source, in the order a person reads them. Section 1a's other
#: sources (Grafana alerts) join HERE through `source_result`,
#: through the reader-job pattern.
# ---------------------------------------------------------------------------
# Source: Grafana's alerts, from the grafana-alerts READER's cache (7.2; the
# reader-job pattern's second instance, and 8.6's constraints on 7.2)
# ---------------------------------------------------------------------------

GRAFANA_READER = "grafana-alerts"

#: Instances whose ONSETS fall within this of the previous one form one
#: incident (8.6: grouping is on the onset, never on startsAt, because
#: per-device windows fire one Loki outage up to 536 s apart). 360 s is a
#: heartbeat onset's own uncertainty: the silence began somewhere in the
#: device's last heartbeat period (300 s), and the rule notices it on its
#: next evaluation (60 s). Two onsets closer than that cannot be told apart.
INCIDENT_GAP_SECONDS = 360

_KIND_WORDS = {"condition": "is alerting", "no_data": "reads no data",
               "error": "cannot evaluate", "unknown_state": "is in a state this page does not know"}


def _onset(inst: dict):
    """(epoch or None, basis). A windowed rule fires one window after the
    silence began, so its onset is the alert's start minus the window."""
    starts, active = _ts(inst.get("starts_at")), _ts(inst.get("active_at"))
    window = inst.get("window_seconds")
    if window and (starts or active):
        return (starts or active) - window, f"the alert's start minus the rule's {window} s window"
    if active:
        return active, "when the condition first held"
    if starts:
        return starts - (inst.get("for_seconds") or 0), "the alert's start minus the rule's pending time"
    return None, "not recorded"


def _incidents(instances: list) -> list:
    """Groups of instances, each group one incident, by onset; an instance
    with no onset is an incident of its own (never merged on a guess)."""
    timed = sorted((i for i in instances if i["onset"] is not None), key=lambda i: i["onset"])
    groups, current = [], []
    for inst in timed:
        if current and inst["onset"] - current[-1]["onset"] > INCIDENT_GAP_SECONDS:
            groups.append(current)
            current = []
        current.append(inst)
    if current:
        groups.append(current)
    return groups + [[i] for i in instances if i["onset"] is None]


def _inventory():
    """(hostnames, address -> {hostnames}), over EVERY list, or (None, reason) when a list
    cannot be read. P.8 step 6: an alert names a device of any network, so resolving it
    against the ACTIVE list alone read another network's device as "NOT in the inventory".
    An address two networks both use maps to both names, and the member says so rather than
    pick one."""
    import os

    from modules.config import LISTS_DIR
    from modules.device import get_device_lists, load_saved_devices

    names, by_ip = set(), {}
    try:
        for entry in get_device_lists():
            path = os.path.join(LISTS_DIR, entry.get("filename") or "", "devices.csv")
            for d in load_saved_devices(path):
                if d.get("hostname"):
                    names.add(d["hostname"])
                    if d.get("ip"):
                        by_ip.setdefault(d["ip"], set()).add(d["hostname"])
    except Exception as exc:                       # noqa: BLE001
        return None, f"the inventory could not be read ({type(exc).__name__})"
    return (names, by_ip), ""


def _member(inst: dict, inv) -> dict:
    """One instance as an incident member, naming where its device came from."""
    names, by_ip = inv if inv else (None, None)
    source = inst.get("device_from")
    device, note = inst.get("device"), ""
    if source == "address":
        addr = inst.get("address")
        found = sorted((by_ip or {}).get(addr) or ())
        device = found[0] if len(found) == 1 else None
        if len(found) > 1:
            note = (f"the polled address {addr} is used by {len(found)} devices in different "
                    f"networks ({', '.join(found)}), so which one is not decided")
        else:
            note = (f"from the polled address {addr}" if device else
                    f"the polled address {addr} matches no device's address in any network")
    elif source in ("label", "line"):
        note = ("from the rule's device label" if source == "label" else
                "from the syslog line's origin-id")
        if names is not None and device not in names:
            note += ", and it is NOT in the inventory (a rule left behind by a device that left)"
    else:
        note = "the rule names no device"
    if inv is None:
        note += " (the inventory could not be read, so the name is unchecked)"
    return {"rule": inst.get("rule"), "kind": inst.get("kind"), "device": device,
            "device_from": source, "device_note": note, "state": inst.get("state"),
            "fingerprint": inst.get("fingerprint"), "starts_at": inst.get("starts_at"),
            "onset": _iso(inst["onset"]), "onset_basis": inst["onset_basis"],
            "silenced_by": inst.get("silenced_by") or [],
            "silences": inst.get("silences") or []}


def silence_words(silences: list) -> str:
    """"silenced in Grafana by X until T ("comment")", one clause per
    silence. An unresolved one is named by its id and said to be unresolved:
    who and until when are never guessed."""
    parts = []
    for s in silences or []:
        if s.get("unresolved"):
            parts.append(f"silenced in Grafana by silence {s.get('id')}, whose author and end "
                         "Grafana's silence list did not return")
            continue
        text = f"silenced in Grafana by {s.get('created_by') or 'an unnamed account'}"
        text += f" until {s.get('ends_at') or 'an unrecorded time'}"
        if s.get("comment"):
            text += f" (\"{s['comment']}\")"
        parts.append(text)
    return "; ".join(parts)


def grafana_source(cached=None, configuration: dict = None) -> dict:
    """Grafana's alert state, read from the reader's cache, NEVER from
    Grafana (rule 1 of modules/reader_job.py). The reader's own liveness is
    job health's row (`reader:grafana-alerts`), judged at request time.

    *configuration* (P.8 step 5) is another network's own Grafana: ``{"id", "lists"}``. Its
    source is named for it ("Grafana alerts (Branch)") and its rows are keyed apart, so two
    Grafanas' rows never collide; Default's configuration is this source as it always was."""
    from modules import reader_job

    src_name, src_label = "grafana", "Grafana alerts"
    if configuration:
        src_name = f"grafana@{configuration['id']}"
        src_label = f"Grafana alerts ({', '.join(configuration['lists'])})"
    started = time.time()
    got = reader_job.read_cached(GRAFANA_READER) if cached is None else cached
    doc = got.get("doc") or {}
    good = doc.get("last_good") or {}
    took = int((time.time() - started) * 1000)
    if got["state"] != "ok" or not good:
        why = (got.get("why") if got["state"] != "ok" else
               "the reader has never stored a value; its last attempt: "
               + ((doc.get("last_attempt") or {}).get("error") or "none recorded"))
        return source_result(src_name, src_label, read_at=started, took_ms=took,
                             error=f"not read yet: {why}")
    from modules.alert_bands import series_key

    v = good.get("value") or {}
    inv, inv_why = _inventory()
    rows = []
    rules_by_uid = {r.get("uid"): r for r in v.get("rules") or []}

    def add(key, what, cause, action, level, **kw):
        rows.append(row(source=src_name, kind=key.split(":", 1)[0], key=key, what=what,
                        cause=cause, action=action,
                        level=level, **kw))

    # Grafana answering and not evaluating reads exactly like a healthy
    # fleet (8.6: the Proxmox listing's 200 with 0 items).
    for g in v.get("stalled_groups") or []:
        add(f"stalled:{g.get('group')}", f"Grafana has stopped evaluating {g.get('group')}",
            f"its last evaluation was {g.get('last_evaluation') or 'never'}, more than three "
            f"of its {g.get('interval_seconds')} s intervals before the read; every rule in it "
            "reads as quiet whether or not its condition holds",
            {"label": "Check Grafana's alert scheduler: its log, then a restart"}, "danger")

    alerting = [dict(i) for i in v.get("instances") or [] if i.get("kind") != "pending"]
    for inst in alerting:
        inst["onset"], inst["onset_basis"] = _onset(inst)
    heartbeat_rules = {r.get("uid") for r in v.get("rules") or []
                       if (r.get("labels") or {}).get("nmas") == "heartbeat"}
    drained, drained_why = _drained_devices()
    planned_hold, planned_why = _planned_alert_hold()
    held, held_planned = [], []
    def parts_of(group):
        """The rows one onset group makes: ``[(instances, members, whole_pipeline)]``.

        Each member is judged by its OWN device, never by what began beside it (W3, the
        operator 2026-10-17: r6's alerts in its settle period were raised CRITICAL because
        s3's live discards alert began within the same 360 s). A device a person marked
        drained (modules/drained.py, the operator 2026-10-06): its traffic falling is the
        drain, so its alerts are said under What was checked, naming the drain. A device
        restarting as planned (B3): its alerts are the restart, inside its window and the
        settle margin after it, said under What was checked with the window, whose Grafana
        silence keeps them from paging anyone; after that, a row again. What is left is
        split in two: a silenced alert is never grouped with a live one, so the live one
        keeps a row of its own and the silenced one says who silenced it."""
        members = [_member(i, inv) for i in group]
        heartbeats = {i.get("rule_uid") for i in group} & heartbeat_rules
        if bool(heartbeat_rules) and heartbeats == heartbeat_rules:
            return [(group, members, True)]
        drained_here, planned_here, keep = {}, {}, []
        for inst, m in zip(group, members):
            d = m["device"]
            if d and d in drained:
                drained_here.setdefault(d, []).append(m)
            elif d and planned_hold(d):
                planned_here.setdefault(d, []).append(m)
            else:
                keep.append((inst, m))
        for d, ms in sorted(drained_here.items()):
            held.append(f"{', '.join(sorted({m['rule'] for m in ms}))} on {d} ({drained[d]})")
        for d, ms in sorted(planned_here.items()):
            held_planned.append(f"{len(ms)} alert(s) ("
                                + ", ".join(sorted({m['rule'] for m in ms})) + ") on "
                                + f"{d}: {planned_hold(d)}")
        live = [p for p in keep if not p[1]["silences"]]
        quiet = [p for p in keep if p[1]["silences"]]
        return [([p[0] for p in part], [p[1] for p in part], False)
                for part in (live, quiet) if part]

    for group, members, whole_pipeline in (p for g in _incidents(alerting)
                                           for p in parts_of(g)):
        devices = sorted({m["device"] for m in members if m["device"]})
        first = group[0]
        if whole_pipeline:
            what = "Every device's syslog heartbeat stopped at once"
            cause = ("all " + str(len(heartbeat_rules)) + " heartbeat rules are alerting with "
                     "onsets together, so no heartbeat is arriving from any device: the "
                     "subject is the path they share (rsyslog, Alloy, Loki or the route to "
                     "them), not each device")
            action = {"label": "Check the syslog pipeline first: rsyslog, Alloy and Loki on the "
                               "monitoring host"}
        elif len(members) == 1:
            m = members[0]
            what = (f"{m['rule']} {_KIND_WORDS.get(m['kind'], m['kind'])}"
                    + (f" on {m['device']}" if m["device"] else ""))
            cause = f"{m['state']}; the device is {m['device_note']}"
            action = ({"label": "Check the device's syslog path: the heartbeat cannot say which "
                                "of the device, its logging block, rsyslog, Alloy or Loki stopped"}
                      if first.get("rule_uid") in heartbeat_rules else
                      {"label": f"Read the rule \"{m['rule']}\" in Grafana: this page records that "
                                "it fired and where its device came from, not why",
                       "known": False})
        else:
            what = f"{len(members)} alerts began together"
            cause = ("; ".join(f"{m['rule']}" + (f" on {m['device']}" if m["device"] else "")
                               + f" ({m['kind']})" for m in members)
                     + f". Grouped because their onsets fall within {INCIDENT_GAP_SECONDS} s "
                       "of each other; whether they share a cause is not decided here")
            action = {"label": "Read the members together: one cause may explain them, "
                               "or none", "known": False}
        # A silence set in Grafana hides nothing here (the operator,
        # 2026-09-30): the row keeps its level and says who silenced it and
        # until when, so a silence is a visible decision, never a quiet one.
        # Each silence is said ONCE, naming the members it covers (W3: one silence printed
        # once per member it matched).
        silenced = [m for m in members if m["silences"]]
        if silenced:
            what += (" (silenced in Grafana)" if len(silenced) == len(members) else
                     f" ({len(silenced)} of {len(members)} silenced in Grafana)")
            covers = {}
            for m in silenced:
                for s in m["silences"]:
                    key = s.get("id") or silence_words([s])
                    covers.setdefault(key, (s, []))[1].append(
                        f"{m['rule']}" + (f" on {m['device']}" if m["device"] else ""))
            cause += ". " + "; ".join(
                (", ".join(dict.fromkeys(names)) + ": " if len(members) > 1 else "")
                + silence_words([s]) for s, names in covers.values())
        level = "danger" if any(m["kind"] == "condition" for m in members) else "unknown"
        operands = {"members": members, "grouped_within_seconds": INCIDENT_GAP_SECONDS,
                    "onset_basis": first["onset_basis"]}
        # The evidence gathered when it began (PHASE8_PLAN 15.9, P1), one click away: the
        # firing alert's card on Monitoring › Alerts, opened (the tab, for several). The
        # action's words are unchanged; the link is its "Open…".
        from modules import evidence_pack
        evidence = evidence_pack.card_href(group)
        # ONE series of a rule whose query can be banded (C433): keyed on the SERIES, never
        # its onset, so a chronic alert that re-fires is one row, and a person may
        # acknowledge it within its measured band.
        vexpr = ((rules_by_uid.get(first.get("rule_uid")) or {}).get("value_expr") or ""
                 if len(members) == 1 and not whole_pipeline else "")
        if vexpr and first.get("kind") == "condition":
            series = series_key(first.get("rule_uid"), first.get("labels"))
            action = {"label": f"Read the rule \"{members[0]['rule']}\" in Grafana; if it is "
                               "chronic and its cause known, acknowledge it within its "
                               "measured band", "known": False}
            if evidence:
                action["href"] = evidence
            add(f"series:{series}", what, cause, action, level, devices=devices,
                since=first["onset"], event=series,
                operands={**operands, "value_expr": vexpr, "labels": first.get("labels") or {},
                          "band_reading": (v.get("bands") or {}).get(series)})
            continue
        if evidence:
            action = dict(action, href=evidence)
        add(f"incident:{first.get('rule_uid') or first.get('rule')}:{_iso(first['onset']) or 'untimed'}",
            what, cause, action, level, devices=devices, since=first["onset"],
            operands=operands)

    # A rule that cannot see its data, or cannot evaluate, with no alerting
    # instance saying so (C166, C168: rules sat in no-data for days).
    covered = {i.get("rule_uid") for i in alerting}
    for r in v.get("rules") or []:
        health = r.get("health")
        if health in ("nodata", "error") and r.get("uid") not in covered:
            add(f"rule:{r.get('uid')}",
                f"{r.get('title')} {'reads no data' if health == 'nodata' else 'cannot evaluate'}",
                (f"its query returns nothing, so whether its condition holds is unknown "
                 f"(its no-data state is {r.get('no_data_state') or 'unrecorded'})"
                 if health == "nodata" else
                 f"its last evaluation failed: {r.get('last_error') or 'no error recorded'}"),
                {"label": f"Read the rule \"{r.get('title')}\"'s query in Grafana", "known": False},
                "warning" if health == "nodata" else "unknown")

    # The floor (8.6): every device should have a heartbeat rule the reader
    # SEES. Fewer is a permission or provisioning gap, and a monitor's
    # permissions can hide what it monitors behind a 200.
    if inv is not None:
        seen = {(r.get("labels") or {}).get("device") for r in v.get("rules") or []
                if (r.get("labels") or {}).get("nmas") == "heartbeat"}
        missing = sorted(inv[0] - seen)
        if missing:
            add("heartbeat-floor", f"{len(missing)} device(s) have no heartbeat rule Grafana shows",
                "no heartbeat rule the reader can see names " + ", ".join(missing)
                + ": the rule is missing, or the reader's account cannot see it",
                {"label": "Regenerate the heartbeat rules (NSOT_PLAN P.1 step 5), then check "
                          "the reader's Grafana role can read them"}, "warning", devices=missing)

    c = v.get("counts") or {}
    return source_result(
        src_name, src_label, read_at=started, took_ms=took, rows=rows,
        value_at=_ts(good.get("value_at")), stale_after_seconds=doc.get("stale_after_seconds"),
        reader=GRAFANA_READER, detail="read from " + ", ".join(doc.get("endpoints") or []),
        checked=(f"{c.get('rules', 0)} rule(s); "
                 f"{c.get('condition', 0)} alerting, {c.get('no_data', 0)} no data, "
                 f"{c.get('error', 0)} error, {c.get('pending', 0)} pending, "
                 f"{c.get('normal_no_data', 0)} reading no data as healthy by decision"
                 + (f"; {len(held)} alert(s) on drained devices, not raised: "
                    + "; ".join(held) if held else "")
                 + ("; restarting as planned, not raised: " + "; ".join(held_planned)
                    if held_planned else "")
                 + (f"; {drained_why}" if drained_why else "")
                 + (f"; {planned_why}" if planned_why else "")
                 + (f"; {inv_why}" if inv is None else "")))


def _planned_alert_hold(now: float = None) -> tuple:
    """``(hold, problem)``: *hold(device)* is the words of the planned window the device is
    inside, in any of its networks, counting `restarts.SETTLE_SECONDS` after its end, or "".
    An unreadable planned record, or inventories that cannot be read, hold nothing, and
    *problem* says so: a record that cannot be read never hides an alert."""
    from modules import restarts as R

    now = time.time() if now is None else now
    try:
        planned, ended = R.planned_rows(), R.ends()
    except RuntimeError as exc:
        return (lambda _d: ""), f"{exc}, so no alert was held for a planned restart"
    # Only a window open now (with its settle margin) holds anything: the record keeps every
    # window ever declared, and the inventories are read only when one is open.
    planned = [p for p in planned if R._epoch(p.get("from", "")) - 60 <= now
               <= R.window_end(p, ended) + R.SETTLE_SECONDS]
    if not planned:
        return (lambda _d: ""), ""
    where = _device_networks()
    if where is None:
        return (lambda _d: ""), ("the networks' inventories could not be read, so no alert "
                                 "was held for a planned restart")

    def hold(device: str) -> str:
        for net in where.get(device) or [""]:
            got = R.holding(device, net, now, margin=R.SETTLE_SECONDS,
                            planned=planned, ended=ended)
            if got:
                return (got["words"] + f", its alerts held {R.SETTLE_SECONDS // 60} min "
                        "after it to settle")
        return ""
    return hold, ""


def _drained_devices() -> tuple:
    """``({device: "drained by X at T: why"}, problem)`` over EVERY network: an alert names a
    device of any network (P.8 step 6). A store that cannot be read drains nothing, and says
    so, so an unreadable record never hides an alert."""
    from modules import drained as D
    from modules.device import get_device_lists

    out = {}
    try:
        for entry in get_device_lists():
            for host, event in D.current(entry.get("name") or "").items():
                out[host] = D.words(event)
    except Exception as exc:                       # noqa: BLE001
        return {}, (f"the drained record could not be read ({type(exc).__name__}), so no "
                    "alert was held back for a drained device")
    return out, ""


# ---------------------------------------------------------------------------
# Source: integration health, from the integration-health READER (7.2): the
# same stored value the status bar draws, so the two cannot disagree.
# ---------------------------------------------------------------------------

#: Where each integration's credential is renewed (P.21): the service's own page.
RENEW_AT = {
    "netbox": "NetBox: Admin > API tokens", "grafana": "Grafana: Administration > Service "
    "accounts", "proxmox": "Proxmox: Datacenter > Permissions > API Tokens",
    "prometheus": "the proxy in front of Prometheus", "loki": "the proxy in front of Loki",
    "kea": "the Kea control agent's credentials",
    "nsot_git": "the git host's tokens",
    "s3": "the S3 provider's access keys",
}
#: An expiry a person declares where the service does not let the tool read it (P.21).
DECLARED_EXPIRY = {"grafana": "grafana_token_expires", "proxmox": "proxmox_token_expires"}


def _setting(key: str) -> str:
    from modules.list_settings import default_layer   # the Default network's integrations (step 5)
    return str(default_layer(key, "") or "").strip()


def integrations_source(cached=None) -> dict:
    """A configured integration that does not answer is a row; one left
    unconfigured is a state, counted (job health names the guard it gates)."""
    from modules import installation_settings, reader_job

    started = time.time()
    got = reader_job.read_cached("integrations") if cached is None else cached
    doc = got.get("doc") or {}
    good = doc.get("last_good") or {}
    took = int((time.time() - started) * 1000)
    if got["state"] != "ok" or not good:
        why = (got.get("why") if got["state"] != "ok" else
               "the reader has never stored a value; its last attempt: "
               + ((doc.get("last_attempt") or {}).get("error") or "none recorded"))
        return source_result("integrations", "Integrations", read_at=started, took_ms=took,
                             error=f"not probed yet: {why}")
    v = good.get("value") or {}
    rows = []
    for i in v.get("integrations") or []:
        if i.get("state") == "refused":
            # P.21: the service answered and refused the credential. Danger at once, naming
            # where it is renewed, where it goes, and a declared expiry if one was given.
            name = i.get("name", "?")
            declared = _setting(DECLARED_EXPIRY.get(name, "")) if DECLARED_EXPIRY.get(name) else ""
            rows.append(row(
                source="integrations", kind="refused", key=name, level="danger",
                what=f"{i.get('label')} refuses the tool's credential",
                cause=(f"its probe was refused: {i.get('message') or 'no reason recorded'}"
                       + (f"; the expiry declared for it is {declared}" if declared else "")),
                operands={"probe_ms": i.get("took_ms")},
                action={"label": f"Renew it at {RENEW_AT.get(name, i.get('label'))} and put the "
                                 "new value in "
                                 f"{installation_settings.settings_place(name, i.get('label'))} "
                                 "(Replace…; the old one stays until then)"}))
            continue
        if i.get("state") != "down":
            continue
        rows.append(row(source="integrations", kind="down", key=i.get("name", "?"), level="danger",
                        what=f"{i.get('label')} is not answering",
                        cause=f"its health probe failed: {i.get('message') or 'no reason recorded'}",
                        operands={"probe_ms": i.get("took_ms")},
                        action={"label": f"Check {i.get('label')} at the URL set in "
                                         + installation_settings.settings_place(
                                             i.get("name", ""), i.get("label"))
                                         + "; its Test button probes it now"}))
    c = v.get("counts") or {}
    # Named, never only counted: "2 not configured" hid that one of the two
    # was the NSoT repository committing all evening (C171).
    unset = [i.get("label") for i in v.get("integrations") or []
             if i.get("state") == "not_configured"]
    return source_result(
        "integrations", "Integrations", read_at=started, took_ms=took, rows=rows,
        value_at=_ts(good.get("value_at")), stale_after_seconds=doc.get("stale_after_seconds"),
        reader="integrations",
        checked=(f"{len(v.get('integrations') or [])} integration(s): {c.get('up', 0)} up, "
                 f"{c.get('down', 0)} down, {c.get('refused', 0)} refusing the credential, "
                 f"{c.get('not_configured', 0)} not configured"
                 + (f" ({', '.join(unset)})" if unset else "")))


# ---------------------------------------------------------------------------
# Source: the running commit's CI verdict, from the ci-verdict READER (7.2):
# nmas-deploy's own gate, never a second implementation of it.
# ---------------------------------------------------------------------------

_CI_ROWS = {"failed": ("its CI run failed", "danger"),
            "cancelled": ("its CI run was cancelled, so no verdict exists", "warning"),
            "pending": ("its CI run is still going", "warning"),
            "could_not_ask": ("whether it passed CI could not be asked", "unknown")}


def redaction_source(health=None) -> dict:
    """C624: log redaction not working is a row. `redact.health()` runs the canary through every
    log handler's filters (built and filtered, never emitted: the read writes nothing) and
    counts the redactions that failed; nothing drew it before. Healthy is a state, said under
    What was checked."""
    from modules import redact

    started = time.time()
    try:
        h = redact.health() if health is None else health
    except Exception as exc:                          # noqa: BLE001
        return source_result("redaction", "Log redaction", read_at=started,
                             took_ms=int((time.time() - started) * 1000),
                             error=f"could not be measured: {type(exc).__name__}: {exc}")
    took = int((time.time() - started) * 1000)
    checked = (f"{h.get('canary_handlers_checked', 0)} log handlers, "
               f"{h.get('log_handlers_unprotected', 0)} unprotected, "
               f"{h.get('redaction_failures', 0)} redactions failed")
    if h.get("healthy"):
        return source_result("redaction", "Log redaction", read_at=started, took_ms=took,
                             checked=checked + ": healthy")
    leaks = [f"{d.get('handler')} ({', '.join(d.get('leaked_shapes') or [])})"
             for d in h.get("canary_leaking_detail") or []]
    cause = "; ".join(filter(None, [
        f"the canary got through {len(leaks)} handler(s): {', '.join(leaks)}" if leaks else "",
        (f"{h.get('log_handlers_unprotected')} handler(s) have no redacting filter: "
         f"{', '.join(h.get('unprotected_handler_types') or [])}")
        if h.get("log_handlers_unprotected") else "",
        (f"{h.get('redaction_failures')} redaction(s) failed, the last at "
         f"{h.get('last_failure_at')}: {h.get('last_error')}")
        if h.get("redaction_failures") else ""])) or "redact.health() reports unhealthy"
    rows = [row(source="redaction", kind="unhealthy", key="log", level="danger",
                what="Log redaction is not working: a secret could reach a log",
                cause=cause,
                action={"label": "Read which handler and what got through on Settings › "
                                 "Installation › Diagnostics, then restart Mercury: every "
                                 "handler gains its filter at start-up",
                         "href": "/v2/settings/installation?tab=diagnostics"})]
    return source_result("redaction", "Log redaction", read_at=started, took_ms=took,
                         rows=rows, checked=checked)


def ci_source(cached=None) -> dict:
    """A running commit CI did not pass is a row; a verified one is not."""
    from modules import reader_job
    from routes import health

    started = time.time()
    got = reader_job.read_cached("ci-verdict") if cached is None else cached
    doc = got.get("doc") or {}
    good = doc.get("last_good") or {}
    took = int((time.time() - started) * 1000)
    if got["state"] != "ok" or not good:
        why = (got.get("why") if got["state"] != "ok" else
               "the reader has never stored a value; its last attempt: "
               + ((doc.get("last_attempt") or {}).get("error") or "none recorded"))
        return source_result("ci", "Running commit's CI", read_at=started, took_ms=took,
                             error=f"not judged yet: {why}")
    v = good.get("value") or {}
    value_at, promise = _ts(good.get("value_at")), doc.get("stale_after_seconds")
    commit = str(v.get("commit") or "")
    if commit != str(health._COMMIT or ""):
        return source_result("ci", "Running commit's CI", read_at=started, took_ms=took,
                             value_at=value_at, stale_after_seconds=promise,
                             checked=f"the stored verdict is for {commit[:10]}, not the running "
                                     f"{str(health._COMMIT)[:10]}: not judged yet")
    rows = []
    if v.get("state") in _CI_ROWS:
        words, level = _CI_ROWS[v["state"]]
        rows.append(row(source="ci", kind="verdict", key=commit[:10], level=level,
                        what=f"The running commit {commit[:10]}: {words}",
                        cause=v.get("sentence") or "no sentence recorded",
                        action=({"label": "Update to a release CI passed: the Update page "
                                          "waits for CI when it is still checking",
                                 "open": "app_update"}
                                if v["state"] in ("failed", "cancelled") else
                                {"label": "Find why CI has no verdict: nmas-deploy's sentence "
                                          "above names the run and what it found",
                                 "known": False})))
    return source_result("ci", "Running commit's CI", read_at=started, took_ms=took, rows=rows,
                         value_at=value_at, stale_after_seconds=promise, reader="ci-verdict",
                         checked=f"{commit[:10]}: {v.get('state')}")


# ---------------------------------------------------------------------------
# Source: reachability, from the reachability READER (C92, 7.2): a device not
# answering over consecutive probes, never one miss.
# ---------------------------------------------------------------------------

def reachability_source(cached=None) -> dict:
    """ONE row listing every device not answering, each with its misses and
    since when: C92 measured genuine outages six to eight devices at once (the
    path from the NMAS, not each device), and nine rows would bury that. The
    claim names the probe (on the host, a TCP connection to port 22)."""
    from modules import reader_job

    started = time.time()
    got = reader_job.read_cached("reachability") if cached is None else cached
    doc = got.get("doc") or {}
    good = doc.get("last_good") or {}
    took = int((time.time() - started) * 1000)
    if got["state"] != "ok" or not good:
        why = (got.get("why") if got["state"] != "ok" else
               "the reader has never stored a value; its last attempt: "
               + ((doc.get("last_attempt") or {}).get("error") or "none recorded"))
        return source_result("reachability", "Reachability", read_at=started, took_ms=took,
                             error=f"not probed yet: {why}")
    v = good.get("value") or {}
    down = sorted((d for d in (v.get("devices") or {}).values() if not d.get("answering")),
                  key=lambda d: d.get("since") or "")
    # A device inside its planned-restart window is restarting as planned (the operator's
    # B3, W2 walk 2026-10-17): said under What was checked, as a drained device's alert is,
    # never a row. Once the window ends with it still down, it is a row naming the window.
    held, planned_why, ended_words = _planned_down(down)
    down = [d for d in down if (d.get("hostname"), d.get("list")) not in held]
    rows = []
    if down:
        names = [d.get("hostname") or d.get("address") for d in down]
        rows.append(row(
            source="reachability", kind="not-answering", key="not-answering", level="danger",
            what=(f"{names[0]} is not answering" if len(down) == 1
                  else f"{len(down)} devices are not answering"),
            devices=names, since=_ts(down[0].get("since")),
            cause="; ".join(f"{d.get('hostname') or d.get('address')} ({d.get('address')}): "
                            f"{d.get('consecutive_misses')} consecutive misses, the threshold is "
                            f"{d.get('threshold')}; {d.get('claim')}"
                            + ended_words.get((d.get("hostname"), d.get("list")), "")
                            for d in down)
                  + (". Several at once is more often the path from Mercury than each device"
                     if len(down) > 1 else ""),
            operands={"probe": "ICMP, then TCP 22"},
            action={"label": "Check the path from Mercury first when several stop together; "
                             "one alone, its own management interface",
                    "known": False}))
    c = v.get("counts") or {}
    return source_result(
        "reachability", "Reachability", read_at=started, took_ms=took, rows=rows,
        value_at=_ts(good.get("value_at")), stale_after_seconds=doc.get("stale_after_seconds"),
        reader="reachability",
        checked=(f"{c.get('answering', 0)} answering, {c.get('not_answering', 0)} not answering"
                 + (f", {c.get('missed_last_probe', 0)} missed only the last probe"
                    if c.get("missed_last_probe") else "")
                 + "".join(f"; {w}" for w in held.values())
                 + (f"; {planned_why}" if planned_why else "")))


def _planned_down(down: list, now: float = None) -> tuple:
    """``(held, problem, ended)`` for the devices not answering: *held* maps ``(hostname,
    list)`` to the words of the planned window each is inside ("edge1 is restarting as planned
    (until T, by X): open its reload on its page"); *ended* maps a device whose window ended
    while it was down to the clause its row adds. An unreadable planned record holds
    nothing, and *problem* says so."""
    from modules import restarts as R

    if not down:
        return {}, "", {}
    now = time.time() if now is None else now
    try:
        planned, ended = R.planned_rows(), R.ends()
    except RuntimeError as exc:
        return {}, f"{exc}, so no device was held as restarting as planned", {}
    held, after = {}, {}
    for d in down:
        key = (d.get("hostname"), d.get("list"))
        got = R.holding(key[0], key[1] or "", now, planned=planned, ended=ended)
        if got:
            held[key] = (got["words"] + (": open its reload on its page"
                                         if got["window"].get("via") == "reload" else
                                         f": {got['window'].get('why', '')}"))
            continue
        p = R.ended_while_down(key[0], key[1] or "", now, _ts(d.get("since")) or 0,
                               planned=planned, ended=ended)
        if p:
            after[key] = (f"; its planned-restart window (by {p.get('by') or 'an unrecorded '
                          'person'}) ended at {R._iso(R.window_end(p, ended))} and it is still "
                          "not answering")
    return held, "", after


def credential_health_source(cached=None) -> dict:
    """P.21: a credential whose exposed expiry is within 30 days (warning), 7 days or past
    (danger), one older than 180 days (warning, naming Rotate), or one whose expiry cannot be
    read: each a row naming where it is renewed and where the new value goes. One expiring
    beyond a year, or with no record of its age, is listed (on Credentials, at 7.6), no row.
    Metadata only: the reader never holds a value."""
    from modules import reader_job

    started = time.time()
    got = reader_job.read_cached("credential-health") if cached is None else cached
    doc = got.get("doc") or {}
    good = doc.get("last_good") or {}
    took = int((time.time() - started) * 1000)
    if got["state"] != "ok" or not good:
        why = (got.get("why") if got["state"] != "ok" else
               "the reader has never stored a value; its last attempt: "
               + ((doc.get("last_attempt") or {}).get("error") or "none recorded"))
        return source_result("credential-health", "Credential expiry and age", read_at=started,
                             took_ms=took, error=f"not read yet: {why}")
    v = good.get("value") or {}
    rows = []
    for c in v.get("credentials") or []:
        state = c.get("state")
        if state in ("ok", "listed"):
            continue
        where = f"Renew it at {c.get('renew_at')}; put the new value in {c.get('put_at')}"
        if c.get("kind") == "age" and state == "warning":
            rows.append(row(source="credential-health", kind="age", key=c.get("id", "?"),
                            level="warning", what=f"{c.get('label')} is {c.get('days')} days old",
                            cause=(f"last set {c.get('set_at')}, past the {MAX_CREDENTIAL_AGE} days "
                                   "a credential is kept"),
                            action={"label": f"{c.get('renew_at')}"}))
        elif state == "unknown":
            # UNKNOWN, never a Warning (C381): a Warning claims a danger the reader has seen.
            rows.append(row(source="credential-health", kind="unread", key=c.get("id", "?"),
                            level="unknown", what=f"{c.get('label')}'s expiry cannot be read",
                            cause=c.get("why") or "no reason recorded",
                            action={"label": f"Read its expiry at {c.get('renew_at')}; the "
                                             "reader asks again every hour"}))
        elif state in ("expired", "danger", "warning"):
            words = ("has EXPIRED" if state == "expired" else
                     f"expires in {c.get('days')} days")
            rows.append(row(source="credential-health", kind="expiry", key=c.get("id", "?"),
                            level="danger" if state in ("expired", "danger") else "warning",
                            what=f"{c.get('label')} {words}",
                            cause=f"it expires {c.get('expires_at')}"
                                  + (f" ({c.get('why')})" if c.get("why") else ""),
                            action={"label": where}))
    counts = {}
    for c in v.get("credentials") or []:
        counts[c.get("state")] = counts.get(c.get("state"), 0) + 1
    return source_result(
        "credential-health", "Credential expiry and age", read_at=started, took_ms=took,
        rows=rows, value_at=_ts(good.get("value_at")),
        stale_after_seconds=doc.get("stale_after_seconds"), reader="credential-health",
        checked=(f"{len(v.get('credentials') or [])} credential(s): "
                 + ", ".join(f"{n} {s}" for s, n in sorted(counts.items()))
                 + (f"; not read: {'; '.join(v.get('errors'))}" if v.get("errors") else "")))


#: P.21's signed age (days): a credential with no expiry older than this is a row.
MAX_CREDENTIAL_AGE = 180

_ROLE_FIELD = {"grafana_fleet_dashboard_uid": "Fleet dashboard UID",
               "grafana_device_dashboard_uid": "Device dashboard UID"}
_ROLE_PAGE = {"fleet": "Monitoring shows no fleet dashboard",
              "device": "a device's Monitoring tab shows no panels"}


def _names(lists: list) -> str:
    return lists[0] if len(lists) == 1 else ", ".join(lists[:-1]) + " and " + lists[-1]


def dashboard_roles_source(read=None, current=None) -> dict:
    """P.8 step 8c (board E, C): a network's fleet or device dashboard setting naming a
    dashboard its Grafana does not hold. Drawn from what the grafana-dashboards reader
    stored for each Grafana configuration, which asked Grafana LIVE about any UID its listing
    lacked (rule 11), so this page asks nothing. One row per setting's layer and UID, naming
    every network that uses it. A stored check whose setting has since changed is not drawn:
    the row leaves the moment the setting moves, and the reader checks the new UID.

    An unread store is not a row here: the reader's failure is job health's own row
    (`reader:grafana-dashboards`), and two rows about one event say it twice."""
    from modules import integration_groups as IG
    from modules import reader_job
    from modules.list_settings import value

    started = time.time()
    read = read or reader_job.read_cached
    current = current or value
    rows, unread, checked, oldest = [], [], 0, None
    try:
        configs = IG.groups(("grafana",))
    except Exception as exc:                            # noqa: BLE001
        return source_result("dashboards", "Dashboard settings", read_at=started, took_ms=0,
                             error=f"the networks' settings could not be read: {exc}")
    for c in configs:
        got = read(IG.store_name("grafana-dashboards", c["id"]))
        good = ((got.get("doc") or {}).get("last_good") or {}) if got["state"] == "ok" else {}
        if not good:
            unread.append(c["list"] if c["id"] != IG.DEFAULT_GROUP else "Default")
            continue
        v = good.get("value") or {}
        at = _ts(good.get("value_at"))
        oldest = at if oldest is None or (at and at < oldest) else oldest
        url = str(current(c["list"], "grafana_url", "") or "").strip() or "its Grafana"
        found = {}
        for r in v.get("roles") or []:
            if str(current(r["list"], r["setting"], "") or "").strip() != r["uid"]:
                continue                     # the setting moved since the check
            checked += 1
            if r["state"] in ("absent", "unknown"):
                found.setdefault((r["state"], r["from"], r["setting"], r["uid"], r["role"]),
                                 []).append(r)
        for (state, layer, setting, uid, role), rs in sorted(found.items()):
            lists = [r["list"] for r in rs]
            whose = (f"set in {layer}'s settings"
                     + (f", which {_names([n for n in lists if n != layer])} inherit"
                        if any(n != layer for n in lists) else ""))
            # C617: the v2 place, the Grafana card of the network that sets it.
            where = (f"Settings › Default, the Grafana card ({_ROLE_FIELD[setting]})"
                     if layer == "Default" else
                     f"Settings › {layer}, its own Grafana card "
                     f"({_ROLE_FIELD.get(setting, setting)})")
            key = f"{c['id']}:{layer}:{setting}:{uid}"
            if state == "absent":
                rows.append(row(
                    source="dashboards", kind="missing", key=key, level="warning",
                    what=f"{_names(lists)}'s {role} dashboard is missing from its Grafana",
                    cause=(f"{setting} names {uid} ({whose}), and {url} answered that it holds "
                           f"no such dashboard (asked {rs[0].get('asked_at') or 'at the read'}). "
                           f"Until it names one Grafana holds, {_ROLE_PAGE[role]} for "
                           f"{_names(lists)}"),
                    action={"label": f"Choose {_names(lists)}'s {role} dashboard in {where}"},
                    operands={"setting": setting, "uid": uid, "grafana": url,
                              "networks": ", ".join(lists)},
                    read_at=at))
            else:
                rows.append(row(
                    source="dashboards", kind="unconfirmed", key=key, level="unknown",
                    what=(f"Whether {_names(lists)}'s {role} dashboard exists is not known"),
                    cause=(f"{setting} names {uid} ({whose}); it is not in {url}'s list, and "
                           f"Grafana could not be asked: {rs[0].get('error') or 'no answer'}"),
                    action={"label": f"Check that {url} answers, or correct {setting} in "
                                     f"{where}"},
                    read_at=at))
    took = int((time.time() - started) * 1000)
    words = f"{checked} configured dashboard setting(s) checked against their Grafana"
    if unread:
        words += (f"; not read yet for {', '.join(unread)} (job health's "
                  "reader:grafana-dashboards row says why)")
    return source_result("dashboards", "Dashboard settings", read_at=started, took_ms=took,
                         rows=rows, value_at=oldest, checked=words)


def netbox_secrets_source(cached=None) -> dict:
    """A credential NetBox holds in a device's stored config context is a live
    exposure in a shared system (the operator, 2026-09-29): one row per device,
    naming the slot kinds and never a value, with the action that can clear it.
    Where NMAS recorded writing the context it may mask it; where it did not,
    it is somebody's data, and the row says to remove it in NetBox."""
    from modules import reader_job

    started = time.time()
    got = reader_job.read_cached("netbox-secrets") if cached is None else cached
    doc = got.get("doc") or {}
    good = doc.get("last_good") or {}
    took = int((time.time() - started) * 1000)
    if got["state"] != "ok" or not good:
        why = (got.get("why") if got["state"] != "ok" else
               "the reader has never stored a value; its last attempt: "
               + ((doc.get("last_attempt") or {}).get("error") or "none recorded"))
        return source_result("netbox-secrets", "NetBox stored credentials", read_at=started,
                             took_ms=took, error=f"not read yet: {why}")
    v = good.get("value") or {}
    value_at, promise = _ts(good.get("value_at")), doc.get("stale_after_seconds")
    if not v.get("configured"):
        return source_result("netbox-secrets", "NetBox stored credentials", read_at=started,
                             took_ms=took, value_at=value_at, stale_after_seconds=promise,
                             reader="netbox-secrets",
                             checked=f"no NetBox configured ({v.get('why') or 'no reason'}): "
                                     "nothing to hold one")
    rows = []
    for d in v.get("devices") or []:
        name = d.get("name") or f"device {d.get('id')}"
        held = ", ".join(d.get("slots") or []) or "a credential"
        comm = d.get("communities") or 0
        cause = (f"NetBox device {d.get('id')} ({name}) holds {held} unmasked in its stored "
                 f"config context" + (f", and {comm} structured SNMP community value(s)"
                                      if comm else "")
                 + ": readable by everyone who can read NetBox")
        if d.get("record_unreadable"):
            cause += (f". Whether Mercury wrote it cannot be told: the modification record is "
                      f"unreadable ({d['record_unreadable']})")
            action = {"label": "Repair data/netbox_modified.json from its preserved "
                               ".corrupt- copy: until it reads, Mercury will not mask NetBox's "
                               "context", "known": False}
        elif d.get("wrote"):
            cause += f". Mercury wrote this context ({d['wrote']}), so it may mask it"
            action = {"label": "Mask it with the import's own masking, read back",
                      "command": f"nmas-netbox-mask-context --device {name} --apply"}
        else:
            cause += ". Mercury has no record of writing it, so it is somebody's data and Mercury "
            cause += "will not change it"
            action = {"label": f"Remove the credential lines from {name}'s config context in "
                               "NetBox by hand"}
        rows.append(row(source="netbox-secrets", kind="held", key=f"netbox:{d.get('id')}", level="danger",
                        what=f"NetBox holds a credential for {name}", devices=[name],
                        cause=cause, operands={"netbox_id": d.get("id")}, action=action))
    return source_result(
        "netbox-secrets", "NetBox stored credentials", read_at=started, took_ms=took,
        rows=rows, value_at=value_at, stale_after_seconds=promise, reader="netbox-secrets",
        checked=f"{v.get('scanned', 0)} NetBox device(s) scanned, "
                f"{len(v.get('devices') or [])} holding a credential")


def intent_format_source(cached=None) -> dict:
    """A device whose committed intent does not round-trip through Mercury's serialiser
    (C1693): Change it in words and bulk intent refuse to patch it, so one row per device,
    naming it and its network, with Normalise on its Intent tab as the action. Read from the
    intent-format reader's stored value (one ls-tree per network per cycle), never per
    request."""
    from modules import reader_job

    started = time.time()
    label = "Intent formatting"
    got = reader_job.read_cached("intent-format") if cached is None else cached
    doc = got.get("doc") or {}
    good = doc.get("last_good") or {}
    took = int((time.time() - started) * 1000)
    if got["state"] != "ok" or not good:
        why = (got.get("why") if got["state"] != "ok" else
               "the reader has never stored a value; its last attempt: "
               + ((doc.get("last_attempt") or {}).get("error") or "none recorded"))
        return source_result("intent-format", label, read_at=started, took_ms=took,
                             error=f"not read yet: {why}")
    v = good.get("value") or {}
    value_at, promise = _ts(good.get("value_at")), doc.get("stale_after_seconds")
    rows, judged, files, failed = [], 0, 0, []
    for name, net in sorted((v.get("lists") or {}).items()):
        if net.get("error"):
            failed.append(f"{name} ({net['error']})")
            continue
        judged += 1
        files += len(net.get("files") or [])
        for host in net.get("hand") or []:
            rows.append(row(
                source="intent-format", kind="hand", key=f"{name}:{host}", level="warning",
                what=f"{host}'s committed intent is hand-formatted, so a patch cannot change it",
                devices=[host], read_at=value_at,
                cause=(f"host_vars/{host}.yml in {name}'s repository at "
                       f"{str(net.get('head', ''))[:8]} does not round-trip through Mercury's "
                       "serialiser (its comments or layout are not Mercury's own), so Change "
                       "it in words and bulk intent refuse it rather than drop them"),
                operands={"network": name, "head": net.get("head", "")},
                action={"label": (f"Normalise the formatting… on {host}'s Intent tab: the "
                                  "editor proves it changes formatting only, then commit it"),
                        "href": f"/v2/device/{host}?" + urlencode(
                            {"tab": "intent", "normalise": 1, "list": name})}))
    if failed and not judged:
        return source_result("intent-format", label, read_at=started, took_ms=took,
                             error="no network's intent could be read: " + "; ".join(failed))
    for which in failed:
        # One network unreadable is not "nothing hand-formatted" there (C1693): said as a row.
        rows.append(row(
            source="intent-format", kind="unreadable", key=f"unreadable:{which}",
            level="unknown", read_at=value_at,
            what=f"Intent formatting could not be read for {which.split(' (', 1)[0]}",
            cause=(f"{which}. Whether its devices' intent round-trips is unknown until it "
                   "can be read"),
            action={"label": "Find why the repository cannot be read: the cause above names "
                             "what git answered", "known": False}))
    return source_result(
        "intent-format", label, read_at=started, took_ms=took, rows=rows, value_at=value_at,
        stale_after_seconds=promise, reader="intent-format",
        checked=(f"{files} committed intent document(s) in {judged} network(s), {len(rows)} "
                 "hand-formatted"
                 + (f"; not read: {'; '.join(failed)}" if failed else "")))


def _n(count: int, one: str, many: str) -> str:
    return f"{count} {one if count == 1 else many}"


#: Where NetBox writes are turned on, said on a row while they are off (C1344).
NETBOX_WRITES_WHERE = ("NetBox writes are off for every network: the import's confirm turns "
                       "them on with your permission (its box), or Settings › Installation › "
                       "Connections, the NetBox connection card")


def netbox_lag_source(cached=None, writes=None) -> dict:
    """A device whose NetBox record holds less than its committed golden (C1344): the
    interfaces, addresses and LLDP cables the import would add, counted by the reader
    (`readers/netbox_lag`) from the committed goldens and NetBox, never per request. One row
    per device, its action the import scoped to it (its NetBox tab's Import into NetBox…);
    it resolves when the import lands, which wakes the reader. With writes off the row says the
    import is off and where it comes on."""
    from modules import reader_job
    from modules.netbox_guard import writes_allowed

    started = time.time()
    label = "NetBox against the committed goldens"
    got = reader_job.read_cached("netbox-lag") if cached is None else cached
    doc = got.get("doc") or {}
    good = doc.get("last_good") or {}
    took = int((time.time() - started) * 1000)
    if got["state"] != "ok" or not good:
        why = (got.get("why") if got["state"] != "ok" else
               "the reader has never stored a value; its last attempt: "
               + ((doc.get("last_attempt") or {}).get("error") or "none recorded"))
        return source_result("netbox-lag", label, read_at=started, took_ms=took,
                             error=f"not read yet: {why}")
    v = good.get("value") or {}
    value_at, promise = _ts(good.get("value_at")), doc.get("stale_after_seconds")
    if not v.get("configured"):
        return source_result("netbox-lag", label, read_at=started, took_ms=took,
                             value_at=value_at, stale_after_seconds=promise, reader="netbox-lag",
                             checked=f"no NetBox configured ({v.get('why') or 'no reason'}): "
                                     "nothing to compare")
    off = not (writes_allowed() if writes is None else writes)
    rows, checked, judged = [], 0, 0
    for name, net in sorted((v.get("networks") or {}).items()):
        if net.get("error"):
            rows.append(row(source="netbox-lag", kind="unreadable", key=f"{name}:unreadable",
                            level="unknown", what=f"{name}'s goldens could not be compared with "
                                                  "NetBox",
                            cause=(f"{net['error']}. Whether NetBox holds {name}'s committed "
                                   "configuration is unknown until it can be read"),
                            operands={"network": name},
                            action={"label": "Find why the repository cannot be read: the "
                                             "cause above names what failed", "known": False}))
            continue
        if not net.get("in_netbox"):
            continue
        judged += 1
        checked += int(net.get("checked") or 0)
        for host, lag in sorted((net.get("devices") or {}).items()):
            ni, na, nc = (len(lag.get(k) or []) for k in ("interfaces", "addresses", "cables"))
            counts = (f"{_n(ni, 'interface', 'interfaces')}, {_n(na, 'address', 'addresses')}, "
                      f"{_n(nc, 'cable', 'cables')} to add")
            shown = [f"{k}: " + ", ".join((lag.get(k) or [])[:5])
                     + (f" and {len(lag[k]) - 5} more" if len(lag.get(k) or []) > 5 else "")
                     for k in ("interfaces", "addresses", "cables") if lag.get(k)]
            cause = ((f"NetBox holds no record of {host}" if lag.get("absent") else
                      f"NetBox's record of {host} (device {lag.get('netbox_id')}) lacks what "
                      "its committed golden holds")
                     + ": " + "; ".join(shown)
                     + (f". Cables are not counted: {net['lldp_error']}"
                        if net.get("lldp_error") else "")
                     + (f". {NETBOX_WRITES_WHERE}" if off else ""))
            rows.append(row(
                source="netbox-lag", kind="behind", key=f"{name}:{host}", level="warning",
                what=f"NetBox holds less than {host}'s committed configuration: {counts}",
                devices=[host], cause=cause, read_at=value_at,
                operands={"network": name, "interfaces": ni, "addresses": na, "cables": nc,
                          "writes": "off" if off else "on"},
                action={"label": (f"Import into NetBox…: {host}'s NetBox tab previews the "
                                  f"import of {host} alone, then confirm it"
                                  + (" with writes turned on" if off else "")),
                        "href": f"/v2/device/{host}?" + urlencode({"tab": "netbox",
                                                                   "list": name})}))
    return source_result(
        "netbox-lag", label, read_at=started, took_ms=took, rows=rows, value_at=value_at,
        stale_after_seconds=promise, reader="netbox-lag",
        checked=(f"{checked} device(s) in {judged} network(s) in NetBox compared with their "
                 f"committed goldens, {len([r for r in rows if r['kind'] == 'behind'])} "
                 "holding more than NetBox"))


def netbox_inventory_source(names=None) -> dict:
    """A NetBox-sourced list whose last refresh failed (C1259): its devices are the last good
    read, kept and flagged stale, and before this row that was said only on its network's
    source card. Read from the refresh's recorded outcome (`inventory.last_attempt`, on disk,
    the same in every process), never NetBox per request."""
    from modules import inventory
    from modules.inventory.source_config import is_netbox_sourced

    started = time.time()
    label = "NetBox-sourced networks"
    if names is None:
        try:
            from modules.device import _load_device_lists_config
            names = sorted(n for n, s in ((_load_device_lists_config() or {}).get("lists")
                                          or {}).items()
                           if isinstance(s, str) and not s.endswith(".csv"))
        except Exception as exc:                  # noqa: BLE001 - the source's own row
            return source_result("netbox_inventory", label, read_at=started,
                                 took_ms=int((time.time() - started) * 1000),
                                 error=f"the networks could not be listed: {exc}")
    sourced = [n for n in names if is_netbox_sourced(n)]
    rows = []
    for name in sourced:
        got = inventory.last_attempt(name)
        if not got or got.get("ok") is True:
            continue
        good = inventory.last_good(name)
        kept = good.get("devices") or []
        filters = got.get("filters") or {}
        filter_words = ", ".join(f"{k}={v}" for k, v in sorted(filters.items()) if v) or \
            "no filter"
        why = got.get("unreadable") and f"its last refresh's record is unreadable: " \
                                         f"{got['unreadable']}" or got.get("error") or \
            "no answer recorded"
        shown = ", ".join(kept[:10]) + (f" and {len(kept) - 10} more" if len(kept) > 10 else "")
        rows.append(row(
            source="netbox_inventory", kind="unreadable", key=name, level="warning",
            what=(f"{name}'s devices could not be read from NetBox: "
                  f"{len(kept)} kept from the last good read"),
            cause=(f"NetBox answered {name}'s filter ({filter_words}) with: {why}. Kept: "
                   f"{shown or 'none'}"),
            since=got.get("at"), read_at=good.get("fetched_at") or None,
            operands={"network": name, "filter": filter_words, "kept": len(kept)},
            action={"label": f"Read NetBox's answer, then fix {name}'s filter on Settings › "
                             f"{name} › Network, or restore what it names in NetBox"}))
    took = int((time.time() - started) * 1000)
    if not sourced:
        return source_result("netbox_inventory", label, read_at=started, took_ms=took,
                             checked="no network takes its devices from NetBox: nothing to "
                                     "read")
    return source_result("netbox_inventory", label, read_at=started, took_ms=took, rows=rows,
                         checked=f"{len(sourced)} NetBox-sourced network(s), each by its last "
                                 "refresh")


def records_source(cached=None) -> dict:
    """Mercury's record stores moved to the records database (Phase 4): a store that no longer
    matches its files, naming the network, both counts and the first differing line; and a
    store on a database that does not answer, since what it records cannot be written. From
    the records-check reader's stored check, never the database per request. Nothing on the
    database: nothing to judge, and it says so."""
    from modules import reader_job, records_db

    started = time.time()
    got = reader_job.read_cached("records-check") if cached is None else cached
    doc = got.get("doc") or {}
    good, attempt = doc.get("last_good") or {}, doc.get("last_attempt") or {}
    took = int((time.time() - started) * 1000)
    label = "Records database stores"
    moved = records_db.stores()
    if not moved:
        return source_result("records", label, read_at=started, took_ms=took,
                             checked="every record store is on its files: nothing to compare")
    if got["state"] != "ok" or (not good and attempt.get("ok") is not False):
        why = got.get("why") if got["state"] != "ok" else "the reader has not run yet"
        return source_result("records", label, read_at=started, took_ms=took,
                             error=f"not read yet: {why}")
    value_at, promise = _ts(good.get("value_at")), doc.get("stale_after_seconds")
    rows = []
    if attempt.get("ok") is False:
        rows.append(row(source="records", kind="unreachable", key="database", level="danger",
                        what=f"{', '.join(moved)} cannot be written: the records database does "
                             "not answer",
                        cause=f"{', '.join(moved)} {'is' if len(moved) == 1 else 'are'} on the "
                              f"records database, and its last check could not ask it: "
                              f"{attempt.get('error') or 'no error recorded'}",
                        since=_ts(attempt.get("at")),
                        action={"label": "Test the records database on Settings › Installation "
                                         "› Connections: its failing check names why"}))
    value = good.get("value") or {}
    # A value stored before K31 is receipts' alone, its fields at the top.
    per = value.get("stores") or ({"receipts": value} if "check" in value else {})
    checked = []
    for store, got_store in sorted(per.items()):
        check = (got_store or {}).get("check") or {}
        if check.get("words"):
            checked.append(f"{records_db.STORE_WORDS.get(store, store)}: {check['words']}")
        for n in check.get("networks") or []:
            if n.get("ok"):
                continue
            where = n.get("network") or "the installation"
            words = records_db.STORE_WORDS.get(store, store)
            rows.append(row(source="records", kind="mismatch", key=f"{store}:{n.get('network')}",
                            level="danger",
                            what=f"{words} in {where} no longer match their file",
                            cause=f"{where}: file {n.get('file')} lines, table "
                                  f"{n.get('table')}: {n.get('differs')}",
                            read_at=value_at,
                            operands={"store": store, "network": n.get("network"),
                                      "file": n.get("file"), "table": n.get("table")},
                            action={"label": "Read the differing line; if a writer is still on "
                                             f"files, move {words.lower()} back to their files "
                                             "on Settings › Installation › Connections"}))
    return source_result("records", label, read_at=started, took_ms=took, rows=rows,
                         value_at=value_at, stale_after_seconds=promise,
                         reader="records-check",
                         checked="; ".join(checked) or "checked")


# ---------------------------------------------------------------------------
# Source: the scheduled credential rotation (C724)
# ---------------------------------------------------------------------------

def scheduled_rotation_source(found=None) -> dict:
    """The scheduled credential rotation's last run that ran (`scheduled_rotation.runs`): one
    that STOPPED on a failure is a CRITICAL row naming the device and the stage, standing
    until a later run finishes clean or the failed device's rotation is committed after the
    stop (`scheduled_rotation.halted`; the timer starts none while it stands). A file read,
    never a device."""
    from modules.nsot import scheduled_rotation as SR

    started = time.time()
    label = "Scheduled credential rotation"
    got = SR.runs() if found is None else found
    took = int((time.time() - started) * 1000)
    if got["state"] == "unreadable":
        return source_result("scheduled_rotation", label, read_at=started, took_ms=took,
                             error=f"its run record could not be read: {got.get('error')}")
    last = SR.last_decisive(got["rows"])
    if not last:
        return source_result("scheduled_rotation", label, read_at=started, took_ms=took,
                             checked="no scheduled rotation run is recorded")
    rows = []
    # The row is about the stop that halts the timer, which a later run that clears nothing (a
    # nothing-due run, C1168) leaves standing: never the last decisive run's own failure.
    stop = SR.halted(got["rows"])
    ran = last
    if stop:
        last = stop
    f = last.get("failed") or {}
    if stop and f:
        rows.append(row(
            source="scheduled_rotation", kind="stopped", key=f"run:{last.get('run')}",
            level="danger", devices=[f.get("device", "?")], since=_ts(last.get("finished")),
            what=(f"Scheduled credential rotation stopped: {f.get('device', '?')} failed at "
                  f"{f.get('stage', '?')}"),
            cause=(f"Run {last.get('run')} ({last.get('trigger')}, started "
                   f"{last.get('started')}) rotated {len(last.get('rotated') or [])} device(s), "
                   f"then {f.get('device', '?')} in {f.get('list', '?')} ended "
                   f"{str(f.get('state') or '?').replace('_', ' ')} at {f.get('stage', '?')}"
                   + (f" ({f['detail']})" if f.get("detail") else "")
                   + f"; {len(last.get('not_reached') or [])} device(s) were not reached. "
                   "The timer starts no scheduled run while this stands"
                   + ("; this is the timer's second halt with no clean run between, so "
                      "settling the device no longer clears it: only a clean run does (C1168)"
                      if SR.second_strike(got["rows"]) else
                      "; settling the device clears it")),
            operands={"device": f.get("device", ""), "stage": f.get("stage", ""),
                      "run": last.get("run", "")},
            action={"label": f"Open {f.get('device', '?')}'s page and read its rotation "
                             "result (a staged credential or an unpersisted rotation is named "
                             "there with its button); settle it, then run Rotate due devices "
                             "now on Credentials › Profiles",
                    "href": f"/v2/device/{f.get('device', '')}"}))
    return source_result("scheduled_rotation", label, read_at=started, took_ms=took, rows=rows,
                         checked=(f"the last run ({ran.get('finished')}): "
                                  f"{str(ran.get('state')).replace('_', ' ')}, "
                                  f"{len(ran.get('rotated') or [])} rotated, "
                                  f"{len(ran.get('skipped') or [])} skipped"))


#: How long a restart's stop of an SDN loop stands as a row when nobody starts it (C2000).
SDN_LOOP_ROW_S = 24 * 3600


def sdn_loop_source(found=None, now: float = None) -> dict:
    """Each network's SDN loop that the app's restart stopped (`loop.stopped_by_restart`,
    C2000): a WARNING row naming the network, the restart's time and the loop's last line,
    standing until the loop is started again or 24 hours pass. One small file read per
    network, never a controller. *found* is ``{network: stop row or None}`` (tests)."""
    from modules.nsot import listref
    from modules.sdn import loop as LP

    started = time.time() if now is None else now
    label = "SDN closed loop"
    try:
        stops = found if found is not None else {n: LP.stopped_by_restart(n)
                                                 for n in listref.names()}
    except Exception as exc:                          # noqa: BLE001 (said as the source's error)
        return source_result("sdn_loop", label, read_at=started, took_ms=0,
                             error=f"the loops' logs could not be read: {type(exc).__name__}")
    rows = []
    for network, stop in sorted(stops.items()):
        at = _ts((stop or {}).get("at"))
        if not stop or at is None or started - at >= SDN_LOOP_ROW_S:
            continue
        rows.append(row(
            source="sdn_loop", kind="restart_stopped", key=f"{network}:{stop.get('at')}",
            level="warning", since=at, clears_at=at + SDN_LOOP_ROW_S,
            what=f"The SDN loop on {network} was stopped by the app's restart",
            cause=(f"It was running when the app restarted (its last line at "
                   f"{stop.get('last_at') or '?'} UTC, the stop recorded at {stop.get('at')}); "
                   "the loop does not start again by itself, so no detection on "
                   f"{network} is found or proposed until a person starts it"),
            operands={"network": network, "stopped_at": stop.get("at") or "",
                      "last_at": stop.get("last_at") or ""},
            action={"label": f"Start the loop on {network}'s SDN › Responses (or leave it "
                             "stopped; this clears 24 hours after the restart)",
                    "href": f"/v2/sdn/responses?list={network}"}))
    took = int((time.time() - started) * 1000) if now is None else 0
    return source_result("sdn_loop", label, read_at=started, took_ms=took, rows=rows,
                         checked=f"{len(stops)} network(s)' loops: {len(rows)} stopped by a "
                                 "restart within 24 hours")


#: The setting an unanswered SDN incident escalates after (C1999), and its default.
SDN_ESCALATE_SETTING, SDN_ESCALATE_DEFAULT = "sdn_escalate_after_minutes", 15
#: What the escalation's second step would notify, said on every escalated row: Mercury has no
#: on-call integration (no paging, chat or webhook notifier), so the row is the only notice.
SDN_NO_ON_CALL = ("no on-call integration is configured for this network (Mercury has none to "
                  "notify), so this row is the only notice")


def _sdn_escalate_after(network: str) -> tuple:
    """``(minutes, why)``: *network*'s `sdn_escalate_after_minutes`, or ``(None, why)`` when it
    cannot be read or is not a whole number from 1 to 1440 (said on the row, never guessed)."""
    from modules import list_settings

    try:
        got = list_settings.value(network, SDN_ESCALATE_SETTING, SDN_ESCALATE_DEFAULT)
    except Exception as exc:                          # noqa: BLE001 (said on the row)
        return None, f"{network}'s {SDN_ESCALATE_SETTING} could not be read " \
                     f"({type(exc).__name__})"
    if isinstance(got, bool) or not isinstance(got, int) or not 1 <= got <= 1440:
        return None, (f"{network}'s {SDN_ESCALATE_SETTING} is {got!r}, not a whole number of "
                      "minutes from 1 to 1440")
    return got, ""


def sdn_responses_source(found=None, now: float = None) -> dict:
    """The SDN incidents awaiting a person (`loop.awaiting`, one response per incident;
    C1999): one row per incident, never one per detection or per switch, naming its network,
    rule, source, how many switches saw it, its severity, its age and the ingress switch its
    response is proposed at; WARNING, DANGER when classified high or critical. It replaces the
    one row per network this source drew before incidents (a count of responses): each
    incident is one attack a person decides on its own, and its row opens that incident.
    Standing until its response is applied or it is dismissed. One small file read per
    network, never a controller. *found* is ``{network: awaiting rows}`` (tests); *now* the
    clock the escalation is judged by (tests).

    **Escalation** (C1999): an incident awaiting a person for the network's
    `sdn_escalate_after_minutes` or longer (15 by default) is escalated: the same row, DANGER
    whatever its classification, its words "unanswered for N minutes", N counted on Mercury's
    clock from the time its response was proposed (the response store's ``at``, never a
    device's). Its second step, the network's on-call integration, does not exist (Mercury has
    no paging, chat or webhook notifier), so an escalated row says no on-call integration is
    configured. A threshold that cannot be read is said on the row, and the row is drawn
    escalated: a threshold not known is never read as not reached. Nothing announces the
    moment an incident crosses it; the SDN reader announces `sdn` at each read (every 30 s),
    and this source is re-read then."""
    from modules.nsot import listref
    from modules.sdn import incidents
    from modules.sdn import loop as LP

    started = time.time()
    clock = started if now is None else now
    label = "SDN responses awaiting a person"
    try:
        waiting = found if found is not None else {
            n: LP.awaiting(n) for n in listref.names()}
    except Exception as exc:                          # noqa: BLE001 (said as the source's error)
        return source_result("sdn_responses", label, read_at=started, took_ms=0,
                             error=f"the responses could not be read: {type(exc).__name__}")
    rows, unread, escalated = [], [], 0
    for network, got in sorted(waiting.items()):
        if got.get("state") == "unreadable":
            unread.append(f"{network} ({got.get('error')})")
            continue
        listed = incidents.order(got.get("rows") or [])
        after, after_why = _sdn_escalate_after(network) if listed else (None, "")
        for r in listed:
            d = r.get("detection") or {}
            inc = r.get("incident") or {}
            sev = incidents.severity(r)
            switches = len(r.get("members") or [d.get("key")])
            title = d.get("title") or d.get("rule") or "SDN detection"
            src = d.get("source") or ""
            where = d.get("dpid_hex") or "?"
            ingress = inc.get("ingress_words") or ("kept before incidents were grouped: "
                                                   f"proposed at {where}, the switch that saw it")
            since = _ts(r.get("at"))
            waited = int(max(0.0, clock - since) // 60) if since is not None else None
            # Escalated past the threshold, or when the threshold or the wait is not known.
            up = after is None or waited is None or waited >= after
            escalated += up
            mins = f"{waited} minute{'' if waited == 1 else 's'}"
            if not up:
                escalation = ""
            elif after is None:
                escalation = (f"; escalated, since its escalation threshold is not known "
                              f"({after_why}); {SDN_NO_ON_CALL}")
            elif waited is None:
                escalation = (f"; escalated, since the time it was proposed is not recorded "
                              f"({r.get('at')!r}); {SDN_NO_ON_CALL}")
            else:
                escalation = (f"; escalated: unanswered for {mins}, at or past "
                              f"{network}'s {SDN_ESCALATE_SETTING} ({after}), whatever its "
                              f"classification; {SDN_NO_ON_CALL}")
            waits = ("awaits a person" + (f", unanswered for {mins}"
                                          if up and waited is not None else
                                          ", escalated" if up else ""))
            rows.append(row(
                source="sdn_responses", kind="awaiting", key=f"{network}:{r.get('id')}",
                level="danger" if up or sev in ("high", "critical") else "warning",
                since=since,
                what=(f"{title}{' from ' + src if src else ''} on {network}, seen on "
                      f"{switches} switch{'es' if switches != 1 else ''}, {waits}"),
                cause=(f"Incident {r.get('id')}, since {r.get('at')} (last seen "
                       f"{r.get('last_seen') or r.get('at')}): "
                       + (f"severity {sev} by its AI classification" if sev != "unclassified"
                          else "not classified")
                       + f"; proposed {r.get('action') or 'no action'} at {where} ({ingress})"
                       # AUTO decided to act and its own preview failed (C2159): said, so the
                       # row names why AUTO left it to a person.
                       + (f"; {r.get('auto_failed')}, so AUTO sent nothing"
                          if r.get("auto_failed") else "")
                       + (f"; no switch shows it since {r.get('inactive_since')}"
                          if r.get("inactive_since") else "")
                       + escalation
                       + ". Nothing is sent to a switch until a person confirms"),
                operands={"network": network, "incident": r.get("id") or "",
                          "rule": d.get("rule") or "", "source": src, "switches": switches,
                          "severity": sev, "since": r.get("at") or "",
                          "inactive": bool(r.get("inactive_since")),
                          "escalated": bool(up), "unanswered_minutes": waited,
                          "escalate_after_minutes": after},
                action={"label": (f"Open the incident on {network}'s SDN › Responses: preview "
                                  f"{r.get('action') or 'a response'} at {where} and confirm "
                                  "it, or dismiss the incident with a reason"),
                        "href": (f"/v2/sdn/responses?list={network}&incident="
                                 f"{r.get('id')}#sdn-i-{r.get('id')}")}))
    took = int((time.time() - started) * 1000)
    if unread:
        return source_result("sdn_responses", label, read_at=started, took_ms=took,
                             rows=rows, error="the responses awaiting could not be read on "
                                              + "; ".join(unread))
    return source_result("sdn_responses", label, read_at=started, took_ms=took, rows=rows,
                         checked=f"{len(waiting)} network(s): {len(rows)} incident(s) "
                                 f"awaiting a person, {escalated} escalated (unanswered past "
                                 f"its network's {SDN_ESCALATE_SETTING}); no on-call "
                                 "integration exists to notify")
def sdn_mitigation_source(found=None, now: float = None) -> dict:
    """Each response whose flows or meter the SDN reader last read missing from their switch
    while their hard timeout has time left (`modules/sdn/reapply.py` `lost`, C2018): a WARNING
    row naming the network, the switch (its DPID and the name it reports), the response (its
    action, source and operation), what is missing and the time left, its action the switch on
    SDN › Flows where Re-apply… is; it clears when the reader reads them installed again, at
    their hard timeout (``clears_at``), or once a newer response in force answers the same
    threat on that switch (C2070: `reapply.answered_by`, by the loop's own test of what holds
    a detection off, `loop.holds` and `loop.covering`; named under What was checked). The
    reader's stored value and the network's flow intent only, never a controller.
    *found* is ``{network: reader_job.read_cached_for's answer}`` (tests)."""
    from modules import reader_job
    from modules.nsot import listref
    from modules.readers import sdn_controllers as R
    from modules.sdn import loop, reapply

    started = time.time() if now is None else now
    label = "SDN responses in force"
    try:
        got = found if found is not None else {
            n: reader_job.read_cached_for(R.READER_NAME, n) for n in listref.names()}
    except Exception as exc:                          # noqa: BLE001 (said as the source's error)
        return source_result("sdn_mitigation", label, read_at=started, took_ms=0,
                             error=f"the SDN reader's stores could not be read: "
                                   f"{type(exc).__name__}")
    rows, read, unreadable, oldest, answered, unjudged = [], 0, [], None, [], []
    for network, cached in sorted(got.items()):
        state = (cached or {}).get("state")
        if state in ("not_applicable", "not_configured"):
            continue
        if state == "unreadable":
            unreadable.append(f"{network} ({cached.get('why') or 'no reason given'})")
            continue
        good = (((cached or {}).get("doc") or {}).get("last_good") or {})
        if not good:
            continue
        read += 1
        value_at = _ts(good.get("value_at"))
        if value_at is not None:
            oldest = value_at if oldest is None else min(oldest, value_at)
        judged = None
        for x in reapply.lost(good.get("value") or {}, now=started):
            # C2070: a newer response in force answers the same threat on that switch (its
            # detection fired again and was answered as new, C2005): nothing to re-apply.
            if judged is None:
                judged = loop.holds(network, reapply.as_collected(good.get("value") or {}),
                                    started, cached=cached)
                if judged["state"] != "ok":
                    unjudged.append(f"{network} ({judged['error']})")
            newer = reapply.answered_by(x, judged)
            if newer is not None:
                answered.append(f"{network}'s {x['key']} by {newer['id']}")
                continue
            switch = x["dpid_hex"] + (f" ({x['name']})" if x["name"] else "")
            resp = x["response"]
            as_read = (f"as the SDN reader read it at {good.get('value_at')}"
                       + (f" (its controller {x['connection']} has not answered since; this is "
                          "its last good read)" if x["controller_state"] == "not_answering"
                          else ""))
            rows.append(row(
                source="sdn_mitigation", kind="lost",
                key=f"{network}:{x['connection']}:{x['dpid_hex']}:{x['key']}",
                level="warning", clears_at=x["expires_at"], read_at=value_at,
                what=(f"{x['label']} on {network} is not in force on switch {switch}: "
                      f"{x['missing_words']} missing, {reapply.left_words(x['left'])} left"),
                cause=(f"Operation {x['key']} (installed {x['installed'] or 'at a time not '
                                                                       'recorded'}, answering "
                       f"{(resp.get('detection') or {}).get('words') or 'its detection'}) is "
                       f"recorded as in force on {x['connection']}'s switch {switch} until "
                       f"{_iso(x['expires_at'])}, and the switch does not hold "
                       f"{x['missing_words']}, {as_read}. A switch that restarts or reboots "
                       "drops its flows and meters before their hard timeout, so the threat "
                       "this response answered is not being mitigated"),
                operands={"network": network, "connection": x["connection"],
                          "dpid": x["dpid_hex"], "switch": x["name"], "operation": x["key"],
                          "action": resp.get("action") or "", "missing": x["missing_words"],
                          "expires_at": _iso(x["expires_at"]), "left_s": int(x["left"])},
                action={"label": (f"Re-apply it on {network}'s SDN › Flows, switch "
                                  f"{x['dpid_hex']}: preview putting back exactly what is "
                                  "missing with the time its hard timeout has left, then "
                                  "confirm (or let it expire)"),
                        "href": "/v2/sdn/flows?" + urlencode({"list": network,
                                                             "q": x["dpid_hex"]})}))
    if unreadable:
        return source_result("sdn_mitigation", label, read_at=started, took_ms=0,
                             error=("the SDN reader's store could not be read for "
                                    + ", ".join(unreadable)))
    took = int((time.time() - started) * 1000) if now is None else 0
    return source_result("sdn_mitigation", label, read_at=started, took_ms=took, rows=rows,
                         value_at=oldest, reader=R.READER_NAME,
                         checked=(f"{read} network(s)' last SDN read: {len(rows)} response(s) "
                                  "with a flow or meter missing before its hard timeout"
                                  + (f"; {len(answered)} more missing and answered by a newer "
                                     f"response in force ({', '.join(answered)})"
                                     if answered else "")
                                  + ("; whether a newer response answers them could not be "
                                     f"read for {', '.join(unjudged)}" if unjudged else "")))


def sdn_controllers_source(found=None, now: float = None) -> dict:
    """Each network whose SDN controller does not answer the SDN reader (C1869's row, carried
    into C1999): one DANGER row per network, naming each controller not answering (its name,
    driver and URL), the failure, since when and how many reads in a row, and the last good
    read its switches are drawn from; its action the controller, then SDN › Controllers and
    the network's Settings. It clears when the reader's next read finds each one answering.

    **Why a row of its own.** A controller that does not answer is not a failed read: the SDN
    reader stores the network's read as good, with that connection ``not_answering``
    (`readers/sdn_controllers.py` `_carried`, reader_job's rule 3 per connection), so job
    health's reader row stays ok and said nothing; only SDN › Controllers showed it. A read
    that fails whole (the network's connection list unreadable) IS job health's row (the
    reader's ``failing`` state, `reader_job.health_rows`), so it is not drawn here again.

    Only a network with an SDN controller set is in scope: a network with none has no store
    (``not_configured``) and no row. A driver not built is a configuration, said on SDN ›
    Controllers, never a row here. The reader's stored value only, never a controller.
    *found* is ``{network: reader_job.read_cached_for's answer}`` (tests)."""
    from modules import reader_job
    from modules.nsot import listref
    from modules.readers import sdn_controllers as R

    started = time.time() if now is None else now
    label = "SDN controllers"
    try:
        got = found if found is not None else {
            n: reader_job.read_cached_for(R.READER_NAME, n) for n in listref.names()}
    except Exception as exc:                          # noqa: BLE001 (said as the source's error)
        return source_result("sdn_controllers", label, read_at=started, took_ms=0,
                             error=f"the SDN reader's stores could not be read: "
                                   f"{type(exc).__name__}")
    rows, unreadable, never, oldest, counted, down_n = [], [], [], None, 0, 0
    for network, cached in sorted(got.items()):
        state = (cached or {}).get("state")
        if state in ("not_applicable", "not_configured"):
            continue
        if state == "unreadable":
            unreadable.append(f"{network} ({cached.get('why') or 'no reason given'})")
            continue
        good = (((cached or {}).get("doc") or {}).get("last_good") or {})
        if not good:
            never.append(network)
            continue
        value_at = _ts(good.get("value_at"))
        if value_at is not None:
            oldest = value_at if oldest is None else min(oldest, value_at)
        controllers = (good.get("value") or {}).get("controllers") or []
        counted += len(controllers)
        down = [c for c in controllers if c.get("state") == "not_answering"]
        if not down:
            continue
        down_n += len(down)
        since = min((t for t in (_ts(c.get("failing_since")) for c in down) if t is not None),
                    default=None)
        names = ", ".join(str(c.get("name")) for c in down)
        each = "; ".join(
            f"{c.get('name')} ({c.get('label') or c.get('kind') or 'driver not recorded'}, "
            f"{c.get('url') or 'no URL recorded'}): {c.get('error') or 'no answer'}, not "
            f"answering since {c.get('failing_since') or 'a time not recorded'} "
            f"({c.get('failures') or 1} read{'' if (c.get('failures') or 1) == 1 else 's'} in "
            f"a row), its switches as last read at {c.get('last_good_at') or 'no time: never'}"
            for c in down)
        first = down[0]
        rows.append(row(
            source="sdn_controllers", kind="not_answering", key=network, level="danger",
            since=since, read_at=value_at,
            what=(f"SDN controller {first.get('name')} on {network} is not answering "
                  f"({first.get('url') or 'no URL recorded'})" if len(down) == 1 else
                  f"{len(down)} SDN controllers on {network} are not answering ({names})"),
            cause=(f"As the SDN reader read {network} at {good.get('value_at')}: {each}. "
                   "While a controller does not answer, the switches behind it are not read: "
                   "the closed loop finds no threat on them, no response reaches them, and SDN "
                   "› Controllers and Flows draw them as last read"),
            operands={"network": network, "controllers": [c.get("name") for c in down],
                      "urls": [c.get("url") or "" for c in down],
                      "errors": [c.get("error") or "" for c in down],
                      "since": _iso(since) or "",
                      "failures": max(int(c.get("failures") or 1) for c in down)},
            action={"label": (f"Check {names} answer{'s' if len(down) == 1 else ''} at "
                              f"{', '.join(c.get('url') or '?' for c in down)}, then read the "
                              f"error on {network}'s SDN › Controllers; if the controller "
                              f"moved, correct its connection in {network}'s Settings, "
                              "Integrations tab"),
                    "href": "/v2/sdn?" + urlencode({"list": network})}))
    if unreadable:
        return source_result("sdn_controllers", label, read_at=started, took_ms=0,
                             error=("the SDN reader's store could not be read for "
                                    + ", ".join(unreadable)))
    took = int((time.time() - started) * 1000) if now is None else 0
    return source_result("sdn_controllers", label, read_at=started, took_ms=took, rows=rows,
                         value_at=oldest, reader=R.READER_NAME,
                         checked=(f"{counted} SDN controller(s) in the last read of each "
                                  f"network with one set: {down_n} not answering"
                                  + (f"; not read yet on {', '.join(never)} (job health's "
                                     "reader row says why)" if never else "")))


# ---------------------------------------------------------------------------
# Source: history committed and not on its remote (C223)
# ---------------------------------------------------------------------------

_PUSHED_LEVEL = {"behind": "info", "behind_unfetched": "info", "not_on_remote": "warning"}

#: How long the host may run behind the pushed tip before that is itself
#: something wrong: 2.5x the slowest push-to-deploy wait measured on the host
#: (115 deploys to 2026-10-01: median 0.1 h, 90th percentile 0.2 h, slowest 8.0 h).
BEHIND_TOO_LONG_S = 20 * 3600


def pushed_level(v: dict, now: float = None) -> tuple:
    """``(level, why)`` for the app-pushed row. An update being available is
    INFORMATION, and makes no row (``"info"``: said on About and the Update
    page); it is a WARNING only when something is actually wrong: CI
    failed for the release, the tip could not be fetched, the host has run
    behind for longer than BEHIND_TOO_LONG_S, or the running commit is not on
    the remote at all. *why* names the reason ("" for information)."""
    now = time.time() if now is None else now
    state = v.get("state")
    if state == "not_on_remote":
        return "warning", "the running commit is not on the remote"
    ci = v.get("ci") or {}
    if ci.get("tip") == v.get("tip") and ci.get("state") in ("failed", "cancelled"):
        return "warning", f"CI {ci['state']} for {str(v.get('tip') or '')[:7]}"
    if state == "behind_unfetched" and v.get("fetch_error"):
        return "warning", f"the new release could not be fetched: {v['fetch_error']}"
    since = _ts(v.get("behind_since"))
    if since is not None and now - since > BEHIND_TOO_LONG_S:
        return "warning", (f"the host has run behind for {int((now - since) // 3600)} h, longer "
                           f"than the {BEHIND_TOO_LONG_S // 3600} h a release here has ever "
                           "waited (2.5x the slowest of 115 measured)")
    return "info", ""


#: An update that was asked for and did not happen (update_op's outcomes).
_UPDATE_NOT_DONE = ("refused", "rolled_back", "rollback_failed", "failed")


def release_level(v: dict, last: dict = None, now: float = None) -> tuple:
    """``(level, why)`` for the release: pushed_level, raised when the last
    update asked FROM this commit did not happen (a failed rollback is danger).
    The ONE decision the Needs attention row and the top bar's "Update
    available" both read, so the quiet indicator turns into the row exactly
    when the row appears, and never shows beside it."""
    level, why = pushed_level(v, now)
    if last is None:
        from modules import update_op
        last = update_op.outcome().get("value") or {}
    if last.get("outcome") in _UPDATE_NOT_DONE and last.get("from") == v.get("running"):
        level = "danger" if last["outcome"] == "rollback_failed" else "warning"
    return level, why


def update_available(v: dict, last: dict = None, now: float = None):
    """The top bar's quiet "Update available" (the operator, 2026-10-02: an
    update is news, not a problem, and should be noticeable): a dict when
    origin/main is ahead, CI PASSED for its tip, and nothing makes it a Needs
    attention row; None otherwise. CI still checking, or a tip never fetched,
    shows nothing: an update not yet installable is not news to act on."""
    if v.get("state") != "behind":
        return None
    target = installable(v)
    if not target:
        return None
    if release_level(v, last, now)[0] != "info":
        return None
    n = _upto(v, target)
    behind = (f"{n} commit{'' if n == 1 else 's'} to install" if n is not None
              else "a number of commits not yet counted to install")
    since = str(v.get("behind_since") or "")
    since = f"{since[:16].replace('T', ' ')} UTC" if len(since) >= 16 else since
    from modules.readers import app_pushed
    later = app_pushed.beyond_words(app_pushed.beyond(v, target))
    return {"tip": target[:7], "running": str(v.get("running") or "")[:7],
            "behind": n, "since": since,
            "title": (f"{behind} from origin/{v.get('branch') or 'main'} "
                      f"({str(v.get('running') or '')[:7]} → {target[:7]}), "
                      f"CI passed; ahead since {since or 'unknown'}"
                      + (f"; {later}, not offered" if later else ""))}


def installable(v: dict) -> str:
    """The commit the Update operation offers: the newest since the running one that CI
    passed (the reader's ``target``, C436), or ""."""
    target = str(v.get("target") or "")
    verdict = (v.get("verdicts") or {}).get(target) or {}
    return target if target and verdict.get("state") == "verified" else ""


def _upto(v: dict, target: str):
    """How many commits an update to *target* runs, or None when not counted."""
    shas = [c.get("sha") for c in v.get("commits") or []]
    return len(shas) - shas.index(target) if target in shas else v.get("behind")


def update_words(v: dict) -> str:
    """The row's headline, in a person's words: "Update available — 1a587a6 →
    2986b5c (2 new commits)", to the commit the Update operation offers."""
    target = installable(v) or str(v.get("tip") or "")
    run = str(v.get("running") or "")[:7]
    n = _upto(v, target)
    count = (f"{n} new commit{'' if n == 1 else 's'}" if n is not None else
             "how many new commits is not known until it is fetched")
    return f"Update available — {run} → {target[:7]} ({count})"


def ci_refused(v: dict) -> bool:
    """CI's final verdict for the pushed tip is not a pass, so the Update button refuses it
    (C418): the row is about the commit, never an update offer."""
    ci = v.get("ci") or {}
    return (v.get("state") != "not_on_remote" and ci.get("tip") == v.get("tip")
            and ci.get("state") in ("failed", "cancelled"))


def ci_refused_words(v: dict) -> tuple:
    """``(headline, action)`` for a tip CI refused: "CI failed on the newest commit, 74a7013 —
    run #373: promtool for the PromQL tests, in test (a), test (b)", and the developer's
    fix-forward, linking the run when the verdict names it."""
    from modules.readers import ci_verdict as CV

    ci, tip = v.get("ci") or {}, str(v.get("tip") or "")[:7]
    run = CV.run_of(ci.get("sentence"))
    named = f" — run #{run['number']}" if run["number"] else ""
    if ci.get("state") == "cancelled":
        what = f"CI was cancelled for the newest commit, {tip}{named}: no verdict"
        label = (f"The developer re-runs CI for {tip} or fixes forward with a newer commit; "
                 "nothing to update until CI passes one")
    else:
        where = CV.failed_words(ci)
        what = f"CI failed on the newest commit, {tip}{named}" + (f": {where}" if where else "")
        label = "The developer fixes forward; nothing to update until CI passes a newer commit"
    older = installable(v)
    if older:
        # An older commit CI passed is still installable (C436): the row must not say there
        # is nothing to update.
        label = (label.split(";")[0] + f"; meanwhile {older[:7]}, which CI passed, can be "
                 "installed from the Update page")
    action = {"label": label}
    if run["url"]:
        action.update(run_url=run["url"], run=run["number"] or "")
    return what, action


def pushed_source(cached=None) -> dict:
    """The host running something other than what is pushed (the operator,
    2026-09-30: the commit left the top bar, so when it is wrong it is here),
    from the `app-pushed` reader: this process's commit against origin/main,
    asked by `git ls-remote`. Quiet at the tip; a row when behind or off it."""
    from modules import reader_job
    from modules.readers import app_pushed
    from routes import health

    started = time.time()
    got = reader_job.read_cached("app-pushed") if cached is None else cached
    doc = got.get("doc") or {}
    good = doc.get("last_good") or {}
    took = int((time.time() - started) * 1000)
    label = "Running commit against origin/main"
    if got["state"] != "ok" or not good:
        why = (got.get("why") if got["state"] != "ok" else
               "the reader has never stored a value; its last attempt: "
               + ((doc.get("last_attempt") or {}).get("error") or "none recorded"))
        return source_result("pushed", label, read_at=started, took_ms=took,
                             error=f"not compared yet: {why}")
    v = good.get("value") or {}
    value_at, promise = _ts(good.get("value_at")), doc.get("stale_after_seconds")
    running = str(v.get("running") or "")
    if running != str(health._COMMIT or ""):
        return source_result("pushed", label, read_at=started, took_ms=took,
                             value_at=value_at, stale_after_seconds=promise,
                             checked=f"the stored comparison is for {running[:10]}, not the running "
                                     f"{str(health._COMMIT)[:10]}: not compared yet")
    rows = []
    if v.get("state") in _PUSHED_LEVEL:
        from modules import update_op

        sentence = app_pushed.words(v)
        # THE UPDATE BUTTON (the operator, 2026-09-30): the app knows it is out
        # of date, so its action is the Update operation, never a terminal.
        offer = installable(v) or str(v.get("tip") or "")
        action = ({"label": f"Preview the commits and CI's verdict for {offer[:7]}, then "
                            "confirm", "open": "app_update"}
                  if v["state"] != "not_on_remote" else
                  {"label": "The host should run only pushed commits: find where this one came "
                            "from before updating over it", "known": False})
        # How and when it was checked: the evidence, drawn behind a disclosure
        # for information (the operator, 2026-10-01), in the row for a warning.
        cause = (f"origin/{v.get('branch') or 'main'} was asked with git ls-remote at "
                 f"{good.get('value_at') or '?'}; the host moves only when a person updates it")
        last = (update_op.outcome().get("value") or {})
        # An update tried and not done is wrong (the host stays behind what a
        # person asked for); a failed rollback is worse. release_level decides
        # it, the one decision the top bar's indicator also reads.
        level, why = release_level(v, last)
        if why:
            cause = f"{why[0].upper()}{why[1:]}. {cause}"
        if last.get("outcome") in _UPDATE_NOT_DONE and last.get("from") == running:
            # One event, one row: the update that did not happen is this row's
            # cause, not a second row beside it.
            cause += (f". The last update, to {str(last.get('to') or '?')[:10]} by "
                      f"{last.get('requested_by') or '?'}, "
                      f"{update_op.OUTCOME_WORDS.get(last['outcome'], last['outcome'])} "
                      f"({last.get('ended_at') or last.get('at') or '?'}): {last.get('reason')}")
        wait = update_op.deferred()
        if wait.get("target"):
            # Update when CI passes: the row says the update is coming, and
            # its action is still the page, where the wait can be stopped.
            cause += (f". An update to {str(wait["target"])[:10]} is waiting for CI, asked by "
                      f"{wait.get("requested_by") or "?"} at {wait.get("requested_at") or "?"}: "
                      "it starts when CI passes")
            action = dict(action, label=f"Waiting for CI to pass {str(wait["target"])[:10]}: "
                                        "open the Update page to follow it or stop waiting")
        what = (update_words(v) if v["state"] in ("behind", "behind_unfetched")
                else sentence[0].upper() + sentence[1:])
        if ci_refused(v):
            # A commit CI refused is not an update on offer (C418: the row said "Update
            # available ... preview then confirm" for a commit the button refuses). The
            # failure leads; the action is the developer's.
            ci = v.get("ci") or {}
            what, action = ci_refused_words(v)
            cause += (f". CI's verdict, asked at {ci.get('asked_at') or '?'}: "
                      f"{ci.get('sentence') or 'no sentence recorded'}"
                      + (f". Where it failed could not be read: {ci['failed_at_error']}"
                         if ci.get("failed_at_error") else ""))
            rows.append(row(source="pushed", kind="ci_failed",
                            key=str(v.get("tip") or "")[:10], level=level,
                            what=what, cause=cause, action=action,
                            since=_ts(ci.get("asked_at")) or _ts(v.get("behind_since"))))
        # A release being available is not wrong (the operator, 2026-10-02):
        # it is said on Help > About and the Update page, and here only once
        # something is (pushed_level names what).
        elif level != "info":
            rows.append(row(source="pushed", kind="release", key=running[:10], level=level,
                            what=what,
                            since=_ts(v.get("behind_since")),
                            cause=cause, action=action))
    return source_result("pushed", label, read_at=started, took_ms=took, rows=rows,
                         value_at=value_at, stale_after_seconds=promise, reader="app-pushed",
                         checked=app_pushed.words(v))


def remote_source(cached=None) -> dict:
    """A list whose commits are not on its remote, from the `remote-publication`
    reader: HEAD against the remote's own branch, asked by `git ls-remote`,
    never the push hook's record (C223: abandon's commit never reached the
    hook, and the hook's record said nothing). Its sentence is
    `remote_publication.describe()`, the one History's header draws. An
    unreadable remote record (C172) is named on the row."""
    from modules import reader_job
    from modules.readers import remote_publication as P

    started = time.time()
    got = reader_job.read_cached(P.READER.name) if cached is None else cached
    doc = got.get("doc") or {}
    good = doc.get("last_good") or {}
    took = int((time.time() - started) * 1000)
    if got["state"] != "ok" or not good:
        why = (got.get("why") if got["state"] != "ok" else
               "the reader has never stored a value; its last attempt: "
               + ((doc.get("last_attempt") or {}).get("error") or "none recorded"))
        return source_result("remote", "Publication to the remote", read_at=started,
                             took_ms=took, error=f"not read yet: {why}")
    value_at, promise = _ts(good.get("value_at")), doc.get("stale_after_seconds")
    lists = (good.get("value") or {}).get("lists") or {}
    rows, fine = [], []
    for name, pub in sorted(lists.items()):
        said = P.describe(pub, now=started)
        if said["state"] in ("in_sync", "no_remote") and said["level"] == "success":
            fine.append(name)
            continue
        if said["state"] == "no_remote":
            continue
        remote = pub.get("remote") or "its remote"
        # Every act here is History's (its header's Push now and Verify the remote, and its
        # Remote set-up…), for this row's own network. Today's Remote card, which these rows
        # named until it left at 7.8 (2026-10-17), was on today's Devices tab.
        from urllib.parse import quote

        history = "/v2/history?list=" + quote(name)
        if said["state"] == "held":
            what = (f"{pub.get('ahead', 0)} commit(s) on {name} held back from {remote}: "
                    "auto-push needs a person")
            since = _ts((pub.get("held") or {}).get("since")) or pub.get("oldest_at")
            action = {"label": (
                "Push now, in History's header: publication was acknowledged since the hold"
                if pub.get("acknowledged_since_hold") else
                "In History's Remote set-up…, read what would be published, acknowledge it, "
                "then Push now in History's header. Until then nothing is pushed, by design: "
                "auto-push never widens what is published"), "href": history}
        elif said["state"] == "tags_not_pushed":
            what = f"{len(pub.get('tags_not_pushed') or [])} tag(s) on {name} not on {remote}"
            since = None
            action = {"label": "Push now, in History's header: it sends every tag with the "
                               "branch", "href": history}
        elif said["state"] == "ahead":
            what = f"{pub.get('ahead', 0)} commit(s) on {name} not pushed to {remote}"
            since = pub.get("oldest_at")
            action = {"label": "Push now, in History's header. The next commit's push also "
                               "sends every commit before it. If it does not go, the header "
                               "names the failure", "href": history}
        elif said["state"] == "in_sync":
            # In step today, and the record the push hook reads cannot be read,
            # so the NEXT commit will not be pushed (C172).
            what = f"{name}'s remote record cannot be read, so its next commit will not be pushed"
            since = None
            action = {"label": "Repair the list's remote record on the host "
                               "(data/lists/<list>/remote.json), or connect the remote again "
                               "in History's Remote set-up…, which names why it cannot be "
                               "read", "href": history}
        elif said["state"] in ("remote_ahead", "diverged"):
            what = f"{name}'s history and {remote} do not match"
            since = None
            action = {"label": "Resolve it by hand on the host: Mercury never force-pushes, so "
                               "compare the two histories and decide which is the record"}
        else:
            what = f"Whether {name}'s history is on {remote} is not known"
            since = None
            action = {"label": "Verify the remote from History's header: it names what "
                               "could not be asked. A remote that cannot be asked also "
                               "cannot be pushed to", "href": history}
        rows.append(row(
            source="remote", kind="publication", key=f"{name}:{said['state']}", level=(
                "danger" if said["level"] == "danger" else "warning"),
            what=what, cause=f"{name}: {said['clause']}. {said['detail']}".strip(),
            action=action, since=since,
            operands={"list": name, "head": str(pub.get("head", ""))[:7],
                      "remote_head": str(pub.get("remote_head", ""))[:7],
                      "not_pushed": str(pub.get("ahead", "")), "record": pub.get("record", "")}))
    return source_result(
        "remote", "Publication to the remote", read_at=started, took_ms=took, rows=rows,
        value_at=value_at, stale_after_seconds=promise, reader=P.READER.name,
        checked=(f"{len(lists)} list repository(ies) compared with their remote's branch; "
                 f"published: {', '.join(fine) or 'none'}"))


def host_steps_source(owed=None) -> dict:
    """AFTER host steps a release that runs now still owes (modules/host_steps.py:
    the operator, 2026-09-30, a step that can only be done once the release has
    landed must never block the update, and must not be forgotten after it).
    The tool's check answers where there is one; otherwise a person says it is
    done on the Update page."""
    from modules import host_steps
    from routes import health

    started = time.time()
    label = "Host steps a running release owes"
    if not health._COMMIT:
        return source_result("host_steps", label, read_at=started, took_ms=0,
                             error="the running commit is unknown, so its history cannot be read")
    got = host_steps.owed(health._COMMIT) if owed is None else owed
    took = int((time.time() - started) * 1000)
    if not got["ok"]:
        return source_result("host_steps", label, read_at=started, took_ms=took,
                             error=got["error"])
    rows = [row(source="host_steps", kind="owed", key=s["id"], level="warning",
                what=(f"A host step for {', '.join(x[:10] for x in s.get('shas') or [s['sha']])}"
                      f" is still to do: {s['step']}"),
                cause=((f"checked: {s['check_detail']}" if s["check_state"] != "not_checkable"
                        else "it is done after the update, and nothing can check it")
                       # One artifact, one row (C442): the newest step's words lead.
                       + (f". It supersedes the step of "
                          f"{', '.join(x[:10] for x in s['superseded'])}: one check, one "
                          "artifact, so doing this one does each" if s.get("superseded")
                          else "")),
                operands={"check": s.get("check") or "", "state": s["check_state"]},
                action={"label": ("Open the Update page and say it is done"
                                  if s["check_state"] == "not_checkable"
                                  else "Do it on the host; this row goes when the check reads done"),
                        "open": "app_update"})
            for s in got["steps"]]
    return source_result("host_steps", label, read_at=started, took_ms=took, rows=rows,
                         checked=f"the last {host_steps.HISTORY} commits of {health._COMMIT[:10]}")


def template_behind_source(ref=None) -> dict:
    """A template BEHIND the shipped version that drops a section of the profile (C566, board
    C): the profile's section reaches every device's intent and no device's configuration, and
    every plan says so only per device (C565). One row per such template, with the way out,
    Bring in the shipped version on Templates. Measured per TEMPLATE, never per device: one
    bound device of each template that imports it, through the cached render pair
    (`profile_apply.unrendered_for_device`)."""
    from modules.nsot import approve_op, hostvars, listref, profile as _p, profile_apply
    from modules.nsot import template_bring, templates_repo
    from modules.preview_confirm import PROFILE_SECTION_WORDS

    started = time.time()
    label = "Templates behind the shipped version"
    try:
        ref = ref or listref.active()
        repo = ref.repo_dir
        stale = [p for p, s in approve_op._shipped_states(repo).items() if s["state"] == "stale"]
        doc = _p.read_for(ref.name, repo)["doc"] if stale else None   # inherited (K11)
    except Exception as exc:                            # noqa: BLE001
        return source_result("templates", label, read_at=started, took_ms=0,
                             error=f"{type(exc).__name__}: {exc}")
    rows, signatures = [], {}
    for path in stale if doc else []:
        dropped, devices = set(), set()
        for template in template_bring.importers(repo, path):
            bound = templates_repo.devices_for_template(repo, template)
            devices |= {e["device"] for e in bound}
            for entry in bound:
                intent = hostvars.read_committed(repo, entry["device"])
                if intent is None or hostvars.is_bootstrap_only(intent):
                    continue
                role = _p.role_of(ref.name, entry["device"])
                sections = _p.sections_for(doc, entry["platform"], role, intent)
                missing, _t = profile_apply.unrendered_for_device(
                    ref.name, repo, entry["device"], entry["platform"], role, intent, sections,
                    signatures)
                dropped |= set(missing)
                break                                   # one device measures the template
        if not dropped:
            continue
        words = ", ".join(PROFILE_SECTION_WORDS.get(s, s) for s in sorted(dropped))
        rows.append(row(source="templates", kind="behind_drops", key=path, level="warning",
                        what=(f"The profile's {words} section reaches no device it applies to: "
                              f"{ref.name}'s {path} is an older shipped version that does not "
                              f"render it ({len(devices)} devices bound through it)"),
                        cause=(f"templates/{path} is behind the shipped version, unedited; "
                               "the shipped one renders it"),
                        operands={"template": path, "sections": sorted(dropped)},
                        action={"label": "Bring in the shipped version on Templates",
                                "open": "template_bring", "list": ref.name, "path": path}))
    return source_result("templates", label, read_at=started,
                         took_ms=int((time.time() - started) * 1000), rows=rows,
                         checked=f"{ref.name}'s templates against the shipped ones")


def restart_source(cached=None) -> dict:
    """An UNPLANNED restart (the operator, 2026-10-02: five passed silently): one row per
    restart for `restarts.ATTENTION_DAYS` days, DANGER when the device saved a crash file,
    naming the device's own reason. A planned one (the tool's reload, or a window it was
    told) is in the device's History and is no row."""
    from modules import reader_job
    from modules import restarts as R

    started = time.time()
    got = reader_job.read_cached("restarts") if cached is None else cached
    doc = got.get("doc") or {}
    good = doc.get("last_good") or {}
    took = int((time.time() - started) * 1000)
    label = "Device restarts"
    if got["state"] != "ok" or not good:
        why = (got.get("why") if got["state"] != "ok" else
               "the reader has never stored a value; its last attempt: "
               + ((doc.get("last_attempt") or {}).get("error") or "none recorded"))
        return source_result("restarts", label, read_at=started, took_ms=took,
                             error=f"not read yet: {why}")
    v = good.get("value") or {}
    value_at, promise = _ts(good.get("value_at")), doc.get("stale_after_seconds")
    if not v.get("configured"):
        return source_result("restarts", label, read_at=started, took_ms=took,
                             value_at=value_at, stale_after_seconds=promise, reader="restarts",
                             checked="no Prometheus configured: a restart cannot be seen")
    # Judged again against the planned windows recorded NOW (a file read), so a correction
    # recorded a moment ago clears its rows without waiting for the reader's next run.
    try:
        unplanned = [r for r in R.judged(v.get("recent_unplanned") or [], R.planned_rows())
                     if not r.get("planned")]
    except RuntimeError as exc:
        return source_result("restarts", label, read_at=started, took_ms=took, error=str(exc))
    rows = []
    for r in unplanned:
        crash = r.get("crash_file", "")
        action = (f"Read the crash file ({crash}) and check the host at that time" if crash else
                  "Read the device's log around then and check the host at that time")
        rows.append(row(source="restarts", kind="unplanned",
                        key=f"{r.get('list', '')}|{r['device']}|{r['at']}",
                        level="danger" if crash else "warning", what=R.words(r),
                        devices=[r["device"]], since=_ts(r.get("at")), event=r["at"],
                        clears_at=(_ts(r.get("at")) + R.ATTENTION_DAYS * 86400
                                   if _ts(r.get("at")) else None),
                        cause=(f"Its uptime counter reset (found {r.get('seen_at', '?')} in "
                               "Prometheus's sysUpTime), and no reload by the tool and no planned "
                               "window covers it."),
                        operands={"list": r.get("list"), "reason": r.get("reason"),
                                  "crash_file": crash},
                        action={"label": action,
                                "href": f"/v2/device/{r['device']}?tab=history"}))
    cut = " (the read window was cut at 48 h)" if v.get("cut") else ""
    return source_result(
        "restarts", label, read_at=started, took_ms=took, rows=rows, value_at=value_at,
        stale_after_seconds=promise, reader="restarts",
        checked=(f"sysUpTime of {v.get('devices', 0)} device(s) over the last "
                 f"{int(v.get('window', 0)) // 60} min{cut}"
                 + (f"; not managed, not judged: {', '.join(v['unmanaged'])}"
                    if v.get("unmanaged") else "")))


def interrupted_source(found=None) -> dict:
    """An operation whose PROCESS ENDED while it held its devices (CONCURRENCY_AUDIT R5): a
    restart, an update or a crash in the middle of a deploy, restore, capture or rotation.
    The kernel released every hold, so nothing else says it happened, and what reached each
    device, and whether a receipt or a golden was recorded, is unknown. ONE row per
    interrupted operation (the process, the operation and who started it), naming its
    devices and the last step it recorded, until a person acknowledges it."""
    from modules.nsot import device_ops

    started = time.time()
    label = "Operations that did not finish"
    try:
        recs = device_ops.interrupted_anywhere() if found is None else found
    except OSError as exc:
        return source_result("operations", label, read_at=started,
                             took_ms=int((time.time() - started) * 1000),
                             error=f"the device holds could not be read: {exc}")
    groups = {}
    for r in recs:
        key = (str(r.get("list") or ""), r.get("pid"), r.get("operation") or "?",
               r.get("actor") or "")
        groups.setdefault(key, []).append(r)
    rows, pending_by_list = [], {}
    for (lst, pid, op, actor), members in sorted(groups.items(), key=lambda kv: str(kv[0])):
        devices = sorted({m.get("device") or "?" for m in members})
        first = min((m.get("started") or 0) for m in members)
        last = max(members, key=lambda m: ((m.get("progress") or {}).get("at") or 0))
        step = (last.get("progress") or {}).get("step") or "started"
        step_at = (last.get("progress") or {}).get("at") or first
        words = device_ops.STEP_WORDS.get(step, step)
        if lst not in pending_by_list:
            pending_by_list[lst] = _pending_receipts_of(lst)
        # The devices this operation finished before it ended: each has its receipt row,
        # written as it finished, whose batch commit never came (CONCURRENCY_AUDIT R5).
        finished = sorted({p.get("device") for p in pending_by_list[lst]
                           if p.get("device") in devices
                           and (_ts(p.get("at")) or 0) + 1 >= first})
        known = (f" {', '.join(finished)} finished before it ended: each has a receipt, "
                 "commit PENDING, naming the program sent and the checks that ran; their "
                 "golden was not recorded." if finished else "")
        unknown = [d for d in devices if d not in finished]
        rows.append(row(
            source="operations", kind="interrupted",
            key=f"{lst}|{pid}|{op}|{first}", event=str(first),
            level="warning", devices=devices, since=first or None,
            what=(f"A {op} on {', '.join(devices)} did not finish: the process ended while it "
                  "held the device" + ("s" if len(devices) > 1 else "")),
            cause=(f"Started by {actor or 'someone'} at {_iso(first)} (process {pid}, list "
                   f"{lst}); its last recorded step was {words} at {_iso(step_at)}. A process "
                   "that ends (a restart, an update, a crash) releases every hold, so nothing "
                   "else says this happened." + known
                   + (f" What reached {', '.join(unknown)}, and whether a golden was "
                      "recorded, is not known." if unknown else "")),
            operands={"list": lst, "operation": op, "pid": pid, "step": step,
                      **({"pending_receipts": finished} if finished else {})},
            action={"label": (f"Read {devices[0]} as it is now and compare it with its golden "
                              "before changing it" + (", and each other device" if
                                                      len(devices) > 1 else "")
                              + "; then acknowledge what you found"),
                    "href": f"/v2/device/{devices[0]}?tab=history"}))
    return source_result(
        "operations", label, read_at=started, took_ms=int((time.time() - started) * 1000),
        rows=rows,
        checked=(f"every device lock in every list: {len(recs)} hold(s) left by a process "
                 "that ended" if recs else
                 "every device lock in every list: none left by a process that ended"))


def _pending_receipts_of(list_name: str) -> list:
    """The receipt rows of *list_name* still waiting for their batch's commit; none when the
    record cannot be read (the deploy source says that it cannot)."""
    from modules.nsot import receipts

    got = receipts.read(list_name, limit=10 ** 6)
    # A retired device's are not a new device's of the name (C1334).
    return [r for r in receipts.current_rows(list_name, got.get("rows") or [])
            if receipts.is_pending(r)]


def adjacency_source(cached=None) -> dict:
    """C38: a routing adjacency committed intent implies and the device does
    not report up, held for two reads (a deploy's settle window passes
    first). ONE row per link, naming the pair and each side's report; a peer
    outside management is seen from one side and says so. A protocol nothing
    scrapes is one unknown row naming the devices, never "all up"."""
    from modules import reader_job
    from modules.readers.adjacencies import PERSIST_READS

    started = time.time()
    got = reader_job.read_cached("adjacencies") if cached is None else cached
    doc = got.get("doc") or {}
    good = doc.get("last_good") or {}
    took = int((time.time() - started) * 1000)
    label = "Routing adjacencies"
    if got["state"] != "ok" or not good:
        why = (got.get("why") if got["state"] != "ok" else
               "the reader has never stored a value; its last attempt: "
               + ((doc.get("last_attempt") or {}).get("error") or "none recorded"))
        return source_result("adjacencies", label, read_at=started, took_ms=took,
                             error=f"not read yet: {why}")
    v = good.get("value") or {}
    value_at, promise = _ts(good.get("value_at")), doc.get("stale_after_seconds")
    if not v.get("configured") and not v.get("adjacencies"):
        return source_result("adjacencies", label, read_at=started, took_ms=took,
                             value_at=value_at, stale_after_seconds=promise, reader="adjacencies",
                             checked="no Prometheus configured: what the devices report about "
                                     "their neighbours cannot be read")
    rows, settling = [], 0
    for key, a in sorted((v.get("adjacencies") or {}).items()):
        if int(a.get("reads") or 0) < PERSIST_READS:
            settling += 1
            continue
        devs = a.get("devices") or []
        # A side judged on a failed scrape's last good value says when it was read (C690).
        rip = a.get("source") == "reader"
        sides = "; ".join(
            (f"{s['device']}{(' ' + s['via']) if s.get('via') else ''}: {s.get('words')}"
             if rip else
             f"{s['device']}{(' ' + s['via']) if s.get('via') else ''} reports "
             + ("it " + s["words"] if s["state"] == "down" else "no such neighbour")
             + (f" (as of {s['as_of'][11:16]} UTC, its last good scrape)" if s.get("as_of")
                else ""))
            for s in a.get("sides") or [])
        if a.get("managed") and len(devs) == 2:
            what = f"{a['protocol']} between {devs[0]} and {devs[1]} is not up"
        else:
            addr = next((s.get("address") for s in a.get("sides") or [] if s.get("address")), "")
            what = (f"{a['protocol']} from {devs[0] if devs else '?'} to {addr or 'a peer'} "
                    "(outside management) is not up")
        cause = (f"Committed intent implies this adjacency ({a.get('network') or a['protocol']}); "
                 + (f"{sides}, as the RIP reader read what each device hears. Not heard on "
                    f"{a.get('reads')} of its reads, five minutes apart, so it is not a "
                    "deploy's settle window" if rip else
                    f"{sides}, as Prometheus last scraped them. Held for {a.get('reads')} reads "
                    "a minute apart, so it is not a deploy's settle window"))
        first = devs[0] if devs else ""
        rows.append(row(source="adjacencies", kind="link", key=key, level="danger", what=what, devices=devs,
                        since=_ts(a.get("since")), cause=cause,
                        operands={"list": a.get("list"), "sides": a.get("sides")},
                        action={"label": f"Open {first}'s Neighbours and check the link and both "
                                         "ends' routing configuration",
                                "href": f"/v2/device/{first}?tab=neighbours"}))
    un = v.get("unmeasured") or []
    if un:
        names = ", ".join(sorted({f"{u['device']} ({u['protocol']})" for u in un}))
        rows.append(row(source="adjacencies", kind="unmeasured", key="unmeasured", level="unknown",
                        what=f"{len(un)} protocol(s) whose adjacencies cannot be judged",
                        devices=sorted({u["device"] for u in un}),
                        cause=f"Intent implies adjacencies Prometheus does not measure: {names}. "
                              + (un[0].get("why") or ""),
                        action={"label": "Check the Prometheus targets row: the routing jobs' "
                                         "files are generated from the goldens"}))
    for e in v.get("errors") or []:
        rows.append(row(source="adjacencies", kind="error", key=f"error:{e[:40]}",
                        level="unknown",
                        what="A list's committed intent could not be read for its adjacencies",
                        cause=e, action={"label": "Fix the intent file the reason names: "
                                                  "it must parse for its links to be judged",
                                         "known": False}))
    return source_result(
        "adjacencies", label, read_at=started, took_ms=took, rows=rows, value_at=value_at,
        stale_after_seconds=promise, reader="adjacencies",
        checked=(f"{v.get('checked', 0)} adjacency report(s) over {v.get('devices', 0)} device(s)"
                 + (f"; {settling} not up for less than {PERSIST_READS} reads, not raised yet"
                    if settling else "")))


#: A drop within this long BEFORE a deploy's receipt (written as the deploy ends), or a minute
#: after it, is the deploy's own: verify's longest settle wait is BGP's hold time, 180 s
#: (tests/test_bgp_hold_watch.py), times 2.5, plus the deploy itself. An estimate from that
#: bound, not a measured deploy length; it errs toward counting a drop as the deploy's.
DEPLOY_WINDOW_S = 600


def _explained(drop: dict, a: dict, planned: list, receipts) -> str:
    """Why a logged drop needs no row, or ``""``: a planned restart's window covering the
    logging device, or a deploy to it around that time. Its peer is named by an address or a
    router id, not a device, so a restart of the peer is not looked up: that drop is raised,
    and its row says the peer may have restarted only by the reason the device gave."""
    from modules import restarts

    at = drop["epoch"]
    if restarts.planned_for(a["device"], at, planned, a.get("list", "")):
        return "planned restart"
    for r in receipts(a.get("list", ""), a["device"]):
        t = _ts(r.get("at"))
        if t and t - DEPLOY_WINDOW_S <= at <= t + 60:
            return "deploy"
    return ""


def adjacency_log_source(cached=None, planned=None, receipts=None) -> dict:
    """C589 (Core 1.0's K2): routing adjacencies a managed device LOGGED going down in the last
    day, which a drop between two scrapes leaves only in the log (the `adjacency-log` reader).
    ONE row per adjacency, its unexplained drops counted. A drop a planned restart's window or a
    deploy explains is counted on `checked`, never on a row. A person may acknowledge an
    adjacency within its measured BAND (C433's pattern): the highest daily count of the reader's
    week. It stays quiet while its day's count stays at or under that, and returns above it."""
    from modules import reader_job
    from modules import restarts

    started = time.time()
    label = "Adjacencies logged down"
    got = reader_job.read_cached("adjacency-log") if cached is None else cached
    doc = got.get("doc") or {}
    good = doc.get("last_good") or {}
    took = int((time.time() - started) * 1000)
    if got["state"] != "ok" or not good:
        why = (got.get("why") if got["state"] != "ok" else
               "the reader has never stored a value; its last attempt: "
               + ((doc.get("last_attempt") or {}).get("error") or "none recorded"))
        return source_result("adjacency_log", label, read_at=started, took_ms=took,
                             error=f"not read yet: {why}")
    v = good.get("value") or {}
    value_at, promise = _ts(good.get("value_at")), doc.get("stale_after_seconds")
    try:
        planned = restarts.planned_rows() if planned is None else planned
    except RuntimeError as exc:
        return source_result("adjacency_log", label, read_at=started, took_ms=took,
                             error=f"{exc}: a drop a planned restart explains cannot be told "
                                   "from one it does not")
    if receipts is None:
        from modules.nsot import receipts as R

        def receipts(list_name, device):
            got_r = R.read(list_name or "Default", device, limit=50)
            if got_r["state"] == "unreadable":
                raise RuntimeError(f"{list_name}'s deploy receipts could not be read: "
                                   f"{got_r.get('error')}")
            return got_r["rows"]
    rows, explained, adjacencies = [], 0, v.get("adjacencies") or {}
    try:
        for k, a in sorted(adjacencies.items()):
            drops = a.get("drops") or []
            kept = [d for d in drops if not _explained(d, a, planned, receipts)]
            explained += len(drops) - len(kept)
            if not kept:
                continue
            last = kept[0]
            n = len(kept)
            reasons = sorted({d.get("reason") or "no reason given" for d in kept})
            where = f" on {a['interface']}" if a.get("interface") else ""
            what = (f"{a['device']}'s {a['protocol']} adjacency to {a['neighbor']} went down "
                    f"{n} time{'' if n == 1 else 's'} in the last day")
            cause = (f"{a['device']} logged it down{where} {n} time{'' if n == 1 else 's'}, the "
                     f"last at {last['at'][11:16]} UTC ({'; '.join(reasons)}), outside any "
                     "planned restart or deploy. Prometheus scrapes once a minute and cannot "
                     "see a drop that recovers between two scrapes, so only the device's log "
                     f"shows it. Its highest daily count in the last {v.get('window_days', 7)} "
                     f"days: {a.get('band', n)}")
            rows.append(row(
                source="adjacency_log", kind="flap", key=k, level="warning", what=what,
                devices=[a["device"]], since=last["epoch"], cause=cause, event=k,
                clears_at=last["epoch"] + 86400, read_at=value_at,
                operands={"list": a.get("list"), "band": a.get("band"),
                          "band_reading": {"value": n, "at": good.get("value_at")}},
                action={"label": (f"Read {a['device']}'s Logs around {last['at'][11:16]} UTC "
                                  "and its Neighbours; if the cause is known, acknowledge it "
                                  "within its measured band"),
                        "href": (f"/v2/device/{a['device']}?tab=logs"
                                 f"&list={a.get('list') or ''}")}))
    except RuntimeError as exc:
        return source_result("adjacency_log", label, read_at=started, took_ms=took,
                             value_at=value_at, stale_after_seconds=promise,
                             reader="adjacency-log", error=str(exc))
    return source_result(
        "adjacency_log", label, read_at=started, took_ms=took, rows=rows, value_at=value_at,
        stale_after_seconds=promise, reader="adjacency-log",
        checked=(f"{v.get('lines', 0)} adjacency line(s) in Loki over the last "
                 f"{v.get('window_days', 7)} days, from {v.get('devices', 0)} managed "
                 f"device(s); {len(adjacencies)} adjacency(ies) logged down"
                 + (f"; {explained} drop(s) inside a planned restart or a deploy, not raised"
                    if explained else "")))


# ---------------------------------------------------------------------------
# Source: SSH host keys refused (C906)
# ---------------------------------------------------------------------------

def host_key_source(refused=None) -> dict:
    """Each device whose last connection was REFUSED because it answered with an SSH host key
    Mercury does not hold (`modules/host_keys.py`): nothing was sent to it, and every
    operation and reader on it is refused until the key is reviewed. One file read; a record
    that cannot be read is this source's error, which is itself a row."""
    from modules import host_keys as hk

    started = time.time()
    label = "SSH host keys"
    try:
        keys = hk.read()["keys"] if refused is None else {}
        got = (sorted((ip, dict(r)) for ip, r in keys.items() if r.get("refused"))
               if refused is None else refused())
    except hk.HostKeyStoreUnreadable as exc:
        return source_result("host_keys", label, read_at=started,
                             took_ms=int((time.time() - started) * 1000), error=str(exc))
    rows = []
    for ip, rec in got:
        r = rec.get("refused") or {}
        names = hk.names_for(ip)
        hosts = sorted({h for _l, h in names})
        lst = names[0][0] if len(names) == 1 else ""
        who = ", ".join(hosts) or ip
        action = {"label": (f"If {who} was rebuilt or its key generated anew, review the new "
                            "key with Re-key… on its page; if not, find what answers at "
                            f"{ip} before anything signs in to it")}
        if len(hosts) == 1:
            action["href"] = (f"/v2/device/{hosts[0]}?op=rekey"
                              + (f"&list={lst}" if lst else ""))
        rows.append(row(
            source="host_keys", kind="changed", key=ip, level="danger",
            what=(f"{who} answered with a different SSH host key: Mercury sent it nothing, and "
                  "refuses every session to it until the key is reviewed"),
            cause=(f"It answered with {r.get('fingerprint', '?')} ({r.get('type') or '?'}) on "
                   f"port {r.get('port', '?')}, last at {r.get('at', '?')} "
                   f"({r.get('count', 1)} time(s) since {r.get('first_at') or r.get('at', '?')},"
                   f" last for {r.get('by') or 'an unrecorded caller'}); Mercury holds "
                   f"{hk.held_words(rec)}."),
            action=action, devices=hosts, since=_ts(r.get("first_at") or r.get("at")),
            operands={"address": ip, "offered": r.get("fingerprint", ""),
                      "held": rec.get("fingerprint", ""), "list": lst}))
    return source_result("host_keys", label, read_at=started,
                         took_ms=int((time.time() - started) * 1000), rows=rows,
                         # A record whose key was forgotten (C940) holds none.
                         checked=(f"{sum(1 for r in keys.values() if r.get('fingerprint'))} "
                                  "device key(s) held, " if refused is None else "")
                         + f"{len(rows)} refused at their last connection")


def host_key_window_source(found=None) -> dict:
    """Each CLOSED planned window that kept new SSH host keys (the operator, 2026-10-16): one
    row, "<n> new host keys accepted during '<reason>'", until a person acknowledges it. The
    summaries are written once, by a reader that sees the window close
    (`host_keys.close_windows`); this only reads them, so a page read writes nothing. A
    window that kept no key is in History and is no row: nothing was taken unreviewed. One
    file read; a summaries file that cannot be read is this source's error, itself a row."""
    from modules import host_keys as hk

    started = time.time()
    label = "SSH host keys kept under a planned window"
    got = hk.summaries() if found is None else found()
    took = int((time.time() - started) * 1000)
    if got["state"] == "unreadable":
        return source_result("host_key_windows", label, read_at=started, took_ms=took,
                             error=(f"the windows' summaries ({hk.SUMMARIES}) could not be "
                                    f"read: {got.get('error')}"))
    rows = []
    # One row per window, from its LATEST summary: a correction (C1389) appends one counting
    # the keys by the window each is credited to now, so a window whose keys were moved to a
    # later one claims none, and the later one's row is a new event to acknowledge.
    windows = hk.latest_summaries(got["rows"])
    for s in windows:
        keys = s.get("keys") or []
        if not int(s.get("count") or 0):
            continue
        named = "; ".join(f"{k.get('device') or k.get('ip')} {k.get('fingerprint')} (was "
                          f"{k.get('replaced') or 'none recorded'})" for k in keys[:10])
        more = f"; and {len(keys) - 10} more" if len(keys) > 10 else ""
        c = s.get("corrected") or {}
        fixed = (f" Corrected {c.get('at', '?')} by {c.get('by') or 'an unrecorded person'} "
                 f"({c.get('finding', '')}): it said {c.get('was_count', '?')}, because "
                 f"{c.get('why', '')}." if c else "")
        rows.append(row(
            source="host_key_windows", kind="window", key=s["window"], level="warning",
            what=hk.summary_words(s),
            cause=(f"The planned window declared by {s.get('by') or 'an unrecorded person'} "
                   f"({hk.window_words(s)}; closed {hk.clock_words(s.get('closed_at'))} UTC) "
                   f"expected new SSH host keys, so Mercury kept each new key it met without a "
                   f"person reviewing it: {named}{more}.{fixed}"),
            action={"label": ("Review each device's new key and the one it replaced in "
                              "History, then acknowledge with what you found"),
                    "href": "/v2/history?kind=hostkeys&since=30"},
            devices=sorted({k.get("device") for k in keys if k.get("device")}),
            since=_ts(s.get("closed_at")), event=hk.summary_event(s),
            # The window by its own times (C1389: the raw id read as a start and an equal
            # end); the id stays the row's key and its event, never drawn.
            operands={"window": hk.window_words(s), "list": s.get("list", ""),
                      "count": int(s.get("count") or 0)}))
    return source_result("host_key_windows", label, read_at=started, took_ms=took, rows=rows,
                         checked=(f"{len(windows)} closed window(s) that expected new "
                                  f"keys, {len(rows)} of them kept one or more"))


def console_ztp_source(found=None) -> dict:
    """Each device whose LATEST console run (out-of-band ZTP, modules/nsot/console_ztp.py)
    needs a person: a survey or kick-start that found it not factory-blank, or one that stopped
    before its end (an abort, a closed console, its bound, an unverified end). One row per
    device, about that run (its event is the run's id), until a later run ends well or a person
    acknowledges it. One file read (the installation's index); an index that cannot be read
    is this source's error, itself a row."""
    from modules.nsot import console_ztp as Z
    from modules.redact import redact_text

    started = time.time()
    label = "Console surveys and kick-starts"
    got = Z.read_index() if found is None else found()
    took = int((time.time() - started) * 1000)
    if got["state"] == "unreadable":
        return source_result("console_ztp", label, read_at=started, took_ms=took,
                             error=(f"the console ZTP index ({Z.INDEX}) could not be read: "
                                    f"{got.get('error')}"))
    rows = []
    for key, entry in sorted(got["devices"].items()):
        kind = Z.problem(entry)
        if kind is None:
            continue
        latest = entry.get("latest") or {}
        dev = entry.get("device") or "?"
        run = {Z.KIND_SURVEY: "console survey", "onboard": "out-of-band onboarding"}.get(
            latest.get("kind"), "console kick-start")
        said = redact_text("; ".join(latest.get("reasons") or [])
                           or latest.get("reason") or "no reason was recorded")
        cause = (f"The {run} of {latest.get('at', '?')} by {latest.get('actor') or 'someone'} "
                 f"(network {entry.get('list')}, NetBox device {entry.get('device_id')}, over "
                 f"console-server port {latest.get('port_id')}) ended "
                 f"{latest.get('outcome', '?')}: {said}")
        operands = {"list": entry.get("list", ""), "device_id": entry.get("device_id"),
                    "run": latest.get("id", ""), "outcome": latest.get("outcome", ""),
                    "port_id": latest.get("port_id")}
        if kind == "not_blank":
            rows.append(row(
                source="console_ztp", kind="not_blank", key=key, level="warning",
                event=latest.get("id"), devices=[dev], since=_ts(latest.get("at")),
                what=f"{dev}'s {run} found it not factory-blank: no kick-start types on it",
                cause=cause, operands=operands,
                action={"label": (f"Return {dev} to its factory state (erase its startup "
                                  "configuration and reload it), then survey its console "
                                  "again")}))
        else:
            rows.append(row(
                source="console_ztp", kind="failed", key=key,
                level="danger" if latest.get("kind") == Z.KIND_KICKSTART else "warning",
                event=latest.get("id"), devices=[dev], since=_ts(latest.get("at")),
                what=f"{dev}'s {run} stopped before its end ({latest.get('outcome', '?')})",
                cause=cause, operands=operands,
                action={"label": (f"Read the run's transcript, check console-server port "
                                  f"{latest.get('port_id')} and {dev}, then "
                                  + ("onboard it again (Devices › Add device…, Out-of-band "
                                     "(console))" if latest.get("kind") == "onboard"
                                     else "survey its console again"))}))
    return source_result("console_ztp", label, read_at=started, took_ms=took, rows=rows,
                         checked=(f"{len(got['devices'])} device(s) with a console survey or "
                                  f"kick-start, {len(rows)} whose latest run needs a person"))


# ---------------------------------------------------------------------------
# Source: AI spend against the day cap, and background AI features against their caps and
# estimates (PHASE8_PLAN 18.3 rules 4 and 10c; C1843, C2056)
# ---------------------------------------------------------------------------

#: Where an admin changes a background feature: Settings › Installation › AI (board AI3,
#: PHASE8_PLAN 18.6; routes/settings_v2.py).
AI_SETTINGS_HREF = "/v2/settings/installation?tab=ai"
#: Every AI spend row's action opens the top bar's spend panel (board AI2's "Open the spend
#: panel"), in place on whatever page draws the row: ``"open": "ai_spend_panel"``, written as a
#: literal at each row so tests/test_next_steps_act.py's scan finds it (`_attention.html`,
#: nmas_v2.js `aiSpendOpen`).
#: Where the day cap is changed: Settings › Installation › AI, the AI (hosted) card.
AI_DAY_CAP_WORDS = "Settings › Installation › AI, the AI (hosted) card"


def _ai_period_end(which: str, today: str, zone: str) -> float:
    """When the cap's day or month holding *today* ends, as an epoch."""
    import datetime as _dt

    from modules.ai import calls

    d = _dt.date.fromisoformat(today)
    nxt = (d + _dt.timedelta(days=1) if which == "day" else
           (d.replace(day=1) + _dt.timedelta(days=32)).replace(day=1))
    return calls.day_start(nxt.isoformat(), zone).timestamp()


def _ai_day_cap_rows(usd: float, cap: float, today: str, zone: str) -> list:
    """Today's AI spend against the installation's day cap (rule 10c, C2056; the chip's
    thresholds, `spend.WARN_AT`): one DAY_WARNING row at 50% (warning) or 80% (danger), or one
    DAY_REACHED row (danger) once today's spend is at or over the cap; none under 50%."""
    from modules.ai import spend

    ratio = spend._ratio(usd, cap)
    warned = spend.warning_of(ratio)
    if not warned:
        return []
    pct = spend.whole_pct(ratio)
    operands = {"spent_usd": round(usd, 6), "cap_usd": cap, "cap": "day (installation)",
                "day": today}
    if ratio >= 1.0:
        return [row(
            source="ai_spend", kind="day_reached", key=f"day_cap:{today}", level="danger",
            clears_at=_ai_period_end("day", today, zone), operands=operands,
            what=f"AI spend reached the day cap (${usd:.2f} of ${cap:.2f})",
            cause=(f"${usd:.4f} spent today (since midnight {zone}, the day cap's boundary), "
                   f"{pct}% of the installation's day cap ${cap:.4f}: every AI call is "
                   "refused until the day ends, people's presses and background features "
                   "alike"),
            action={"label": ("Open the spend panel to see what spent it; leave it until the "
                              f"day ends, or an admin changes the day cap on {AI_DAY_CAP_WORDS}"),
                    "open": "ai_spend_panel"})]
    return [row(
        source="ai_spend", kind="day_warning", key=f"day_cap:{today}",
        level="danger" if warned == "80" else "warning",
        clears_at=_ai_period_end("day", today, zone), operands=operands,
        what=f"AI spend is at {pct}% of the day cap (${usd:.2f} of ${cap:.2f})",
        cause=(f"${usd:.4f} spent today (since midnight {zone}, the day cap's boundary), {pct}% "
               f"of the installation's day cap ${cap:.4f} (warned at {warned}%). At the cap "
               "every AI call is refused until the day ends, people's presses and background "
               "features alike; a call is refused sooner when its worst case would pass what "
               "is left"),
        action={"label": ("Open the spend panel to see what is spending, and turn a background "
                          "feature off there if it should stop; an admin may change the day "
                          f"cap on {AI_DAY_CAP_WORDS}"),
                "open": "ai_spend_panel"})]


def _ai_over_estimate_row(f: dict):
    """A background feature whose average daily spend since it was turned on is at or above
    `spend.OVER_ESTIMATE_AT` of the estimate it was approved at (rule 10c, C2056): one
    OVER_ESTIMATE row (warning), else None."""
    from modules.ai import spend

    if not f.get("over_estimate"):
        return None
    name, net = f["words"], f["network"]
    actual, est = f["actual_usd_per_day"], f["estimate"]["usd_per_day"]
    pct, n = spend.whole_pct(f["ratio"]), f["actual_days"]
    return row(
        source="ai_spend", kind="over_estimate", key=f"{net}:{f['feature']}:estimate",
        level="warning",
        what=(f"{name} on {net} is running at {pct}% of the estimate it was approved at "
              f"(${actual:.4f} a day against ${est:.4f})"),
        cause=(f"{name} averaged ${actual:.4f} a day on {net} over the {n} complete "
               f"day{'' if n == 1 else 's'} since {f['on_by'] or 'an admin'} turned it on "
               f"({f['on_at'] or 'time not recorded'}), against the estimate ${est:.4f} a day "
               f"shown then: {pct}% of it, and a row is raised from "
               f"{spend.whole_pct(spend.OVER_ESTIMATE_AT)}%"),
        operands={"actual_usd_per_day": round(actual, 6), "estimate_usd_per_day": est,
                  "days": n, "network": net, "feature": f["feature"]},
        action={"label": (f"Open the spend panel to review {name}'s trigger, caps and estimate "
                          f"against actual on {net}; turn it off there, or turn it on again in "
                          "Settings › AI with a new estimate"),
                "open": "ai_spend_panel", "href": AI_SETTINGS_HREF})


#: Where the AI card's Test is, which asks the provider again after an admin raised its limit.
AI_CARD_HREF = "/v2/settings/installation?tab=ai#card-ai"


def _ai_workspace_limit_row():
    """The provider's workspace usage limit while it is held (C2084, `provider_limit`): one
    WORKSPACE_LIMIT row (danger) naming the provider's words and the moment, clearing at it by
    time, or when a call is answered (the hold cleared); else None."""
    from modules.ai import provider_limit

    hold = provider_limit.holding()
    if not hold:
        return None
    said = provider_limit.said(hold)
    when = (f"until {said['until']['utc']} UTC" if said["until"] else
            f"until {said['recheck']['utc']} UTC, when Mercury asks the provider again (it "
            "named no moment)")
    return row(
        source="ai_spend", kind="workspace_limit", key="workspace_limit", level="danger",
        since=_ts(hold["since"]), clears_at=_ts(hold["recheck_at"]),
        what=said["words"],
        cause=(f"The provider refused call {hold.get('call_id') or '(not recorded)'} at "
               f"{hold['since']}"
               + (f" (HTTP {hold['status']})" if hold.get("status") else "")
               + f": “{said['provider']}”. Mercury refuses every AI call {when}, without "
               "asking the provider: people's presses and background features alike; the AI "
               "(hosted) card's Test still asks, and an answer clears it"),
        operands={"since": hold["since"], "until": hold.get("until"),
                  "recheck_at": hold["recheck_at"], "provider": said["provider"]},
        action={"label": ("An admin raises the workspace's usage limit in the provider's "
                          "console, then presses Test on Settings › Installation › AI, "
                          f"the AI (hosted) card, which asks the provider again; or wait {when}"),
                "open": "ai_spend_panel", "href": AI_CARD_HREF})


def _ai_unrecorded_rows() -> list:
    """One ``unrecorded`` row (danger) per call whose row the record of AI calls refused
    (C2047, `reservations.unrecorded`): its cost is held against the caps until the record takes
    the row, which Mercury asks again at every AI call; it clears then (resolves). Read whatever
    AI's state: such a call was sent while AI was on. An unreadable reservations store makes no
    row here (it refuses every call itself, said on the refusal)."""
    from modules.ai import reservations

    got = reservations.unrecorded()
    rows = []
    for c in got["calls"]:
        many = f" ({c['rows']} requests of a batch)" if c["rows"] > 1 else ""
        rows.append(row(
            source="ai_spend", kind="unrecorded", key=f"unrecorded:{c['id']}", level="danger",
            since=_ts(c["at"]),
            what=f"AI call {c['id']}'s cost could not be recorded",
            cause=(f"The record of AI calls refused the row of {c['id']}{many}"
                   + (f" ({c['feature']})" if c["feature"] else "")
                   + f", sent at {c['at']}: the call is missing from History, and its cost "
                   f"${c['usd']:.4f} is held against the AI caps as a call in flight, today "
                   "and every day until the record takes the row"),
            operands={"call_id": c["id"], "usd": round(c["usd"], 6), "at": c["at"],
                      "rows": c["rows"]},
            action={"label": ("Find why the record of AI calls refuses writes (its disk or "
                              "records database); Mercury asks it to take the row again at "
                              "every AI call, and this row clears when it does"),
                    "open": "ai_spend_panel"}))
    return rows


def _ai_approval_rows(due, now=None) -> list:
    """One ``approval`` row per background feature switched on whose 14-day approval ends within
    3 days or has ended (`background.approvals_due`, decision 5 of boards AI1 to AI5; C1953):
    warning while it is still in force, danger once it has ended (the gateway refuses its
    calls). It clears when an admin turns it on again (a new approval) or off, never by time,
    since an ended approval still needs that decision."""
    from modules.ai import background

    at = background.epoch_of(now)
    rows = []
    for net, feature, entry, ends in due:
        name = background.FEATURES.get(feature, {}).get("words", feature)
        ends_iso = _iso(ends)
        ends_words = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(ends))
        ended = at >= ends
        left = ends - at
        days = int(left // 86400)
        when = ("" if ended else
                f"in {days} day{'' if days == 1 else 's'}" if days >= 1 else "in under a day")
        rows.append(row(
            source="ai_spend", kind="approval", key=f"{net}:{feature}:approval",
            level="danger" if ended else "warning", since=_ts(entry.get("at")),
            what=(f"The approval of {name} on {net} ended {ends_words}" if ended else
                  f"The approval of {name} on {net} ends {when}"),
            cause=(f"{name} was turned on for {net} by {entry.get('by') or 'an admin'} at "
                   f"{entry.get('at')}, approved for {background.APPROVAL_DAYS} days with the "
                   f"estimate shown then; its approval "
                   + (f"ended {ends_iso}, so the gateway refuses its calls until an admin "
                      "turns it on again" if ended else
                      f"ends {ends_iso}, and from then the gateway refuses its calls until an "
                      "admin turns it on again")),
            operands={"network": net, "feature": feature, "approved_at": entry.get("at"),
                      "ends_at": ends_iso, "approval_days": background.APPROVAL_DAYS,
                      "renew_days": background.RENEW_DAYS},
            action={"label": (f"Turn {name} on again for {net} in Settings › AI, accepting "
                              f"its current estimate (a new {background.APPROVAL_DAYS} days), "
                              "or turn it off"
                              + ("" if ended else f"; else it stops {ends_words}")),
                    "open": "ai_spend_panel", "href": AI_SETTINGS_HREF}))
    return rows


def ai_spend_source(now=None) -> dict:
    """AI spend where someone should act (PHASE8_PLAN 18.3 rules 4 and 10c; there is no
    standing spend row):

    - while AI is on (`spend.hosted_on`, as the chip reads it) and a day cap is set, today's
      spend against the installation's day cap (`_ai_day_cap_rows`): a row at 50% and 80% of
      it, and once it is reached;
    - each background AI feature on, on each network, against its own day and month caps
      (`spend.feature_summaries`): one STOPPED row (danger) for a cap a refusal shows it
      reached this period, else one WARNING row at 50% (warning) or 80% (danger) of its nearer
      cap; and, apart from those, one OVER_ESTIMATE row while it runs at or above 150% of its
      estimate (`_ai_over_estimate_row`).

    - while AI is on and the provider's workspace usage limit is held (C2084,
      `_ai_workspace_limit_row`): one WORKSPACE_LIMIT row (danger), the provider's words and
      the moment, clearing at it or when a call is answered.

    - each background feature switched on whose approval ends within 3 days, or has ended
      (`background.approvals_due`, `_ai_approval_rows`; C1953): one APPROVAL row, warning
      before its end and danger after, read from the switches alone, whatever the spend.

    Every row opens the spend panel. The read is bounded (CLAUDE.md, enterprise scale): with a
    feature on, the month's window of the record of AI calls, today's spend summed from it;
    else, with AI on and a day cap, today's window alone (`calls.spent_usd`); else nothing."""
    from modules.ai import background, calls, gateway, spend

    started = time.time()
    label = "AI spend: the day cap and background features"
    try:
        on = background.enabled()
        due = background.approvals_due(now)
        cap = gateway.day_cap()
        hosted = spend.hosted_on()
    except Exception as exc:                                    # noqa: BLE001 (said, a row)
        return source_result("ai_spend", label, read_at=started, took_ms=0,
                             error=f"the AI settings could not be read: {exc}")
    # An approval ending within 3 days, or ended (C1953, decision 5): read from the switches
    # alone, whatever the spend, and whether or not AI is on now.
    approval_rows = _ai_approval_rows(due, now)
    approval_said = (f"{len(due)} background feature approval(s) ending within "
                     f"{background.RENEW_DAYS} days or ended")
    why_no_day = ("" if hosted and cap is not None else
                  "AI is off (hosted AI is not allowed, or no provider key is set), so the day "
                  "cap was not judged" if not hosted else
                  "no day cap is set (an admin chose no cap), so today's spend was not judged "
                  "against one")
    # The provider's workspace usage limit (C2084), while AI is on: with AI off no call is made
    # whatever the provider would answer, and the chip says "AI off".
    limit = _ai_workspace_limit_row() if hosted else None
    # A call whose row the record refused (C2047), whatever AI's state now.
    unrecorded_rows = _ai_unrecorded_rows()
    limit_rows = ([limit] if limit else []) + approval_rows + unrecorded_rows
    limit_said = ("the provider's workspace usage limit is held" if limit else
                  "no provider workspace usage limit is held" if hosted else
                  "AI is off, so the provider's workspace usage limit was not read")
    limit_said = f"{limit_said}; {approval_said}" + (
        f"; {len(unrecorded_rows)} call(s) whose row the record of AI calls refused, their "
        "cost held against the caps" if unrecorded_rows else "")
    if not on and why_no_day:
        return source_result("ai_spend", label, read_at=started,
                             took_ms=int((time.time() - started) * 1000), rows=limit_rows,
                             checked=(f"no background AI feature is on for any network, and "
                                      f"{why_no_day}: no spend was read; {limit_said}"))
    zone = calls.boundary()
    today = calls.today(now, zone)
    got = (calls.rows_since(spend.month_start(today, zone)) if on else
           calls.spent_usd(today, zone))
    if got["state"] == "unreadable":
        return source_result("ai_spend", label, read_at=started,
                             took_ms=int((time.time() - started) * 1000),
                             error=f"the record of AI calls could not be read: {got['error']}")
    usd = spend.day_usd(got["rows"], today, zone) if on else float(got["usd"] or 0.0)
    rows = limit_rows + ([] if why_no_day else _ai_day_cap_rows(usd, cap, today, zone))
    day_said =why_no_day or (f"today's spend ${usd:.2f} against the day cap ${cap:.2f}: "
                              f"{len(rows)} row(s)")
    for f in (spend.feature_summaries(got["rows"], today, zone, now) if on else []):
        over = _ai_over_estimate_row(f)
        if over:
            rows.append(over)
        name, net = f["words"], f["network"]
        key = f"{net}:{f['feature']}"
        spent = {"day": f["spent"]["day_usd"], "month": f["spent"]["month_usd"]}
        period = {"day": "today", "month": "this month"}
        stopped = [w for w in ("month", "day") if f["stopped"][w]]
        if stopped:
            w = stopped[0]
            rows.append(row(
                source="ai_spend", kind="stopped", key=f"{key}:{w}", level="danger",
                since=_ts(f["stopped_at"][w]),
                clears_at=_ai_period_end(w, today, zone),
                what=f"{name} on {net} stopped: it reached its {w} cap",
                cause=(f"{name} spent ${spent[w]:.4f} on {net} {period[w]} against its {w} cap "
                       f"${f['caps'][w]:.4f}, and the gateway refused its next call "
                       f"({f['stopped_at'][w]}); it makes no call until the {w} ends"),
                operands={"spent_usd": round(spent[w], 6), "cap_usd": f["caps"][w], "cap": w,
                          "network": net, "feature": f["feature"]},
                action={"label": (f"Leave {name} stopped until the {w} ends, raise its {w} "
                                  f"cap, or turn it off for {net} in Settings › AI"),
                        "open": "ai_spend_panel", "href": AI_SETTINGS_HREF}))
            continue
        if not f["warning"]:
            continue
        w = max(("day", "month"), key=lambda k: f["fractions"][k] or 0.0)
        pct = spend.whole_pct(f["fractions"][w])
        rows.append(row(
            source="ai_spend", kind="warning", key=f"{key}:{w}",
            level="danger" if f["warning"] == "80" else "warning",
            clears_at=_ai_period_end(w, today, zone),
            what=f"{name} on {net} has spent {pct}% of its {w} cap",
            cause=(f"{name} spent ${spent[w]:.4f} on {net} {period[w]}, {pct}% of its {w} cap "
                   f"${f['caps'][w]:.4f} (warned at {f['warning']}%); at its cap it stops "
                   f"until the {w} ends"),
            operands={"spent_usd": round(spent[w], 6), "cap_usd": f["caps"][w], "cap": w,
                      "network": net, "feature": f["feature"]},
            action={"label": (f"Read {name}'s spend on {net}; leave it, turn it off, or "
                              f"change its {w} cap in Settings › AI"),
                    "open": "ai_spend_panel", "href": AI_SETTINGS_HREF}))
    features = len([r for r in rows if not r["kind"].startswith("day_")
                    and r["kind"] not in ("workspace_limit", "approval")])
    return source_result("ai_spend", label, read_at=started,
                         took_ms=int((time.time() - started) * 1000), rows=rows,
                         checked=(f"{len(on)} background feature switch(es) on, against their "
                                  f"day and month caps and estimates: {features} near or at a "
                                  f"cap or over its estimate; {day_said}; {limit_said}"))


SOURCES = (job_health_source, drift_source, approvals_source, pending_onboarding_source,
           rollback_source, deploy_source, baseline_source, authorisation_source,
           grafana_source, integrations_source, ci_source, redaction_source,
           reachability_source, netbox_secrets_source, credential_health_source,
           remote_source, pushed_source,
           host_steps_source, adjacency_source, restart_source,
           interrupted_source, dashboard_roles_source, template_behind_source,
           records_source, scheduled_rotation_source, host_key_source,
           host_key_window_source, netbox_inventory_source, adjacency_log_source,
           netbox_lag_source, console_ztp_source, intent_format_source,
           ai_spend_source, sdn_loop_source, sdn_responses_source, sdn_mitigation_source,
           sdn_controllers_source)


#: What can move each source's rows: the data keys (modules/invalidation.VOCABULARY) whose
#: announcement, or a response's invalidation, means it must be read again. The ONE list
#: the page, the sidebar's count and the client's relays are built from (the operator,
#: 2026-10-02: the count was a hand-kept list, short of keys the page heard); a test holds
#: it to SOURCES both ways and every key to a relay.
SOURCE_KEYS = {
    "job_health_source": ("job_health",),
    "drift_source": ("drift",),
    "approvals_source": ("approvals", "drift"),
    "pending_onboarding_source": ("pending", "inventory"),
    "rollback_source": ("rolled_back", "intent"),
    # device_state: a Persist (its route invalidates it) clears an unsaved row (C543).
    "deploy_source": ("deploy_job", "goldens", "device_state"),
    "baseline_source": ("baselines", "goldens"),
    "authorisation_source": ("deploy_job", "goldens"),
    "grafana_source": ("alerts", "inventory"),   # inventory: a device marked drained
    "integrations_source": ("integration_health",),
    "ci_source": ("ci_verdict",),
    # Redaction changes only inside this process (a handler added unfiltered); it is measured
    # at each read of the page, and a settings change is the nearest a change announces.
    "redaction_source": ("settings",),
    "reachability_source": ("reachability",),
    "netbox_secrets_source": ("netbox",),
    # Its reader announces netbox (C1344); a NetBox write switch changed is a settings write.
    "netbox_lag_source": ("netbox", "settings"),
    "credential_health_source": ("credential_health",),
    "remote_source": ("remote", "goldens"),
    "pushed_source": ("app_version",),
    "host_steps_source": ("app_version",),
    "adjacency_source": ("adjacencies",),
    # The adjacency-log reader announces the same key (C589).
    "adjacency_log_source": ("adjacencies",),
    "restart_source": ("restarts",),
    # A hold left by a process that ended is found at the next read; the page's catch-up on
    # reconnect (the process that ended was this app) is what re-reads it.
    "interrupted_source": ("deploy_job", "device_state"),
    # The reader's stored check, and a setting changed in Settings, which removes a row.
    "dashboard_roles_source": ("dashboards", "settings"),
    # A template brought in, or a profile committed (C566).
    "template_behind_source": ("templates", "intent"),
    # The reader's stored check, and a move or move back (which changes the settings).
    "records_source": ("records", "settings"),
    # A list refreshed by hand (its route invalidates the inventory) or its source changed.
    "netbox_inventory_source": ("inventory", "settings"),
    # A scheduled run's end (or a device in it) announces both (C724).
    "scheduled_rotation_source": ("rotation", "credentials"),
    # A loop started or stopped (`sdn_v2.loop_set` invalidates sdn) moves its row (C2000).
    "sdn_loop_source": ("sdn",),
    # A response proposed (the loop announces sdn, C2003), confirmed or dismissed (routes).
    # A network's escalation threshold changed in Settings is a settings write (C1999).
    "sdn_responses_source": ("sdn", "settings"),
    # The SDN reader announces sdn at each read, and a re-apply's confirm invalidates it (C2018).
    "sdn_mitigation_source": ("sdn",),
    # The SDN reader announces sdn at each read; a connection changed in Settings wakes it
    # (reader_wakes), so its read, then its announcement, moves the row (C1999, C1869's row).
    "sdn_controllers_source": ("sdn",),
    # A key kept, refused or replaced by any session or a re-key announces it (C906).
    "host_key_source": ("host_keys",),
    # A window's summary written by its reader announces the same key (C906).
    "host_key_window_source": ("host_keys",),
    # A console survey's or kick-start's end announces these (console_ztp.ANNOUNCE_KEYS).
    "console_ztp_source": ("device_state", "pending", "console_ztp"),
    # C1693: the intent-format reader announces intent; an intent commit wakes it (reader_wakes).
    "intent_format_source": ("intent",),
    # Every AI call's route announces its record; a switch or a cap changed is a settings write.
    "ai_spend_source": ("ai_calls", "settings"),
}

#: Every key that can move a row, and a person's acknowledgement.
ATTENTION_KEYS = tuple(sorted({k for ks in SOURCE_KEYS.values() for k in ks}
                              | {"acknowledgements"}))

#: The event the page and the count also re-read on: the moment a row clears by TIME.
DUE_EVENT = "attention_due"


def badge_of(rows: list, results: list) -> dict:
    """The sidebar's count, from the SAME rows the page draws, after attaching, folding and
    acknowledgements (the operator, 2026-10-02: the count was computed apart and left out
    rows the page showed): how many, the worst level, when a row next clears by time, and
    when the oldest source's value passes its promise. The page's own count is this one."""
    worst = min((LEVELS.index(r["level"]) for r in rows), default=None)
    due = [_ts(r["clears_at"]) for r in rows if r.get("clears_at")]
    stale = [_ts(res["value_at"]) + res["stale_after_seconds"] for res in results
             if res.get("value_at") and res.get("stale_after_seconds")]
    unreadable = [res["label"] for res in results if res.get("state") != "read"]
    return {"n": len(rows), "level": LEVELS[worst] if worst is not None else "",
            "next_change_at": _iso(min(due)) if due else None,
            "stale_at": _iso(min(stale)) if stale else None,
            "unreadable": len(unreadable)}


def _attach(rows: list) -> list:
    """Fold each row that is ABOUT another row into it (NSOT_PLAN 8.6: two
    rows about one event is the three-reports problem). The target keeps its
    own cause and takes the attached row's action, since a queued item is the
    prepared path to the fix; an attached row whose target is absent stands
    alone."""
    by_id = {r["id"]: r for r in rows}
    kept = []
    for r in rows:
        target = by_id.get(r.get("attach_to") or "")
        if target is None or target is r:
            kept.append(r)
            continue
        # Its id and kind kept, so Needs attention's record (C1192) sees a folded row as
        # still present, never as cleared.
        target["attached"].append({"id": r["id"], "kind": r["kind"], "source": r["source"],
                                   "what": r["what"], "since": r["since"],
                                   "devices": r["devices"]})
        if r.get("attach_action", True):
            target["action"] = r["action"]
    return kept


def _fold_one_cause(rows: list) -> list:
    """Rows from two sources about ONE cause, folded by the attach rule (the operator,
    2026-10-02). The updater's installed copy of `nmas-deploy` differing produced two
    warnings, the host step's ("A host step for ... is still to do") and job health's
    ("updater differs from this release's copy"), cleared together by one re-install. While
    an owed host step is checked by the updater's own check, job health's `differs` row
    attaches to it, and the host step's row keeps its action: it is the one that says what
    to do. Any other updater state (writable, cannot run) is its own danger and stays.

    For EVERY root-installed helper, not the updater alone (C419, the operator, 2026-10-04:
    the Oxidized helper's drift was the host step's row and job health's): the registry
    (`host_helpers.folds`) names each helper's check, its job-health row and the states one
    install clears."""
    from modules import host_helpers

    owed = {}
    for r in rows:
        check = (r.get("operands") or {}).get("check") if r["source"] == "host_steps" else None
        if check and check not in owed:
            owed[check] = r
    if not owed:
        return rows
    for check, (unit_id, states) in host_helpers.folds().items():
        step = owed.get(check)
        if step is None:
            continue
        for r in rows:
            if r["id"] == unit_id and (r.get("operands") or {}).get("state") in states:
                r["attach_to"] = step["id"]
                r["attach_action"] = False
    return rows


def _fold_known_unmonitored(rows: list) -> list:
    """One cause, one row (C493, with C488's Needs attention half; the operator, 2026-10-05):
    a device whose committed configuration has no heartbeat is job health's ONE "not
    monitored" row, and Grafana's heartbeat floor naming the same device is the same cause
    said again (no heartbeat configured, so no rule was made). The floor row leaves that
    device out, saying so; a floor row left naming none attaches to the not-monitored row,
    which keeps its own action. Matched by the device's name and network where the floor
    row's network is known: the floor reads every network's inventory."""
    known = {}
    for r in rows:
        ops = r.get("operands") or {}
        if (r["source"], r["kind"]) == ("job_health", "job") and \
                ops.get("state") == "not_monitored" and "heartbeat" in (ops.get("missing") or ()):
            for d in r["devices"]:
                known.setdefault(d, r)
    if not known:
        return rows
    for r in rows:
        if (r["source"].split("@", 1)[0], r["kind"]) != ("grafana", "heartbeat-floor"):
            continue
        folded = [d for d in r["devices"] if d in known]
        if not folded:
            continue
        rest = [d for d in r["devices"] if d not in known]
        if not rest:
            r["attach_to"] = known[folded[0]]["id"]
            r["attach_action"] = False
            continue
        r["devices"] = rest
        r["what"] = f"{len(rest)} device(s) have no heartbeat rule Grafana shows"
        r["cause"] = ("no heartbeat rule the reader can see names " + ", ".join(rest)
                      + ": the rule is missing, or the reader's account cannot see it. Not "
                      "counted here: " + ", ".join(folded) + ", whose committed configuration "
                      "has no heartbeat, each said on its own not-monitored row")
    return rows


def _device_networks():
    """``{hostname: [network, ...]}`` over EVERY network's inventory, or None when one cannot
    be read (C493). A row naming a device and no network of its own is placed by this: two
    networks may each hold a device of one name, and then both are named."""
    import os

    from modules.config import LISTS_DIR
    from modules.device import get_device_lists, load_saved_devices

    out = {}
    try:
        for entry in get_device_lists():
            path = os.path.join(LISTS_DIR, entry.get("filename") or "", "devices.csv")
            for d in load_saved_devices(path):
                if d.get("hostname"):
                    out.setdefault(d["hostname"], set()).add(entry["name"])
    except Exception as exc:                       # noqa: BLE001
        log.warning("attention: the networks' inventories could not be read: %s", exc)
        return None
    return {h: sorted(n) for h, n in out.items()}


def _stated_network(r: dict, names: set) -> str:
    """The network a row's source says it is about (its operands' or its action's ``list``),
    when that is a network the installation holds."""
    for got in ((r.get("operands") or {}).get("list"), (r.get("action") or {}).get("list")):
        if isinstance(got, str) and got in names:
            return got
    return ""


def _with_networks(rows: list) -> list:
    """Every row naming a device names each device's network (C493, the operator, 2026-10-05:
    tw-ztp-a's rows read as Default's): ``networks`` maps each device to its network, from the
    row's own source where it says, else from every network's inventory (a name two networks
    hold maps to both; a name none holds to none, drawn as such). A row about ONE network keeps
    it in its action's address, so following it lands in that network, never the active one."""
    from urllib.parse import quote

    from modules.nsot import listref

    if not any(r["devices"] for r in rows):
        for r in rows:
            r["networks"] = {}
        return rows
    try:
        names = set(listref._registry())
    except Exception:                              # noqa: BLE001
        names = set()
    where = None
    for r in rows:
        stated = _stated_network(r, names)
        if stated or not r["devices"]:
            r["networks"] = {d: [stated] for d in r["devices"]}
        else:
            if where is None:
                where = _device_networks() or {}
            r["networks"] = {d: list(where.get(d) or []) for d in r["devices"]}
        one = {n for ns in r["networks"].values() for n in ns}
        if len(one) != 1 or not all(len(ns) == 1 for ns in r["networks"].values()):
            continue
        (net,) = one
        href = (r.get("action") or {}).get("href") or ""
        if href.startswith("/v2/") and not re.search(r"[?&]list=", href):
            r["action"] = dict(r["action"],
                               href=href + ("&" if "?" in href else "?") + "list=" + quote(net))
    return rows


def _standing_acknowledgements(hiding: list) -> list:
    """The band acknowledgements IN FORCE that hide nothing now (C433, the operator,
    2026-10-05: s3's discards were acknowledged, the alert stopped, and the acknowledgement
    showed nowhere). Each holds while its series stays at or under its band, firing or not,
    so a person can find and review it. One already listed as hiding a row is not repeated.
    An unreadable record lists nothing here: the row that says so is `_without_acknowledged`'s."""
    from modules import acknowledgements as ACK

    got = ACK.read()
    if got["state"] == "unreadable":
        return []
    shown = {k.get("id") for k in hiding}
    out = []
    # One made for an earlier device of the name is in force for nothing (C1476).
    for a in ACK.standing_bands(ACK.current(got["rows"])):
        if a.get("row") in shown:
            continue
        value = a.get("value")
        out.append({"id": a.get("row"), "what": a.get("what") or a.get("kind") or "an alert",
                    "by": a.get("by"), "why": a.get("why"), "at": a.get("at"),
                    "band": (f"holds while its value stays at or under {float(a['band']):.3g}"
                             + (f"; {float(value):.3g} when acknowledged" if value is not None
                                else ""))})
    return out


def band_words(ack: dict, judged: dict) -> str:
    """Both numbers, and which governs (C533, the operator, 2026-10-06: the row showed two band
    values and said neither which applied): the band recorded with the acknowledgement, when,
    and the value it is judged against, when and by whom it was read."""
    from modules.alert_bands import words

    at = (ack.get("at") or "")[11:16]
    band = (f"Acknowledged by {ack.get('by')}{' at ' + at + ' UTC' if at else ''} within a "
            f"band of {words(judged['band'])}, the band that governs")
    if judged["value"] is None:
        return f"{band}; its value now could not be read ({judged.get('why')})"
    when = (judged.get("value_at") or "")[11:16]
    side = "at or under it" if judged["in_band"] else "above it"
    return (f"{band}; its value is {judged['value']:.3g}"
            + (f" (read by {judged['value_from']} at {when} UTC)" if when else "")
            + f", {side}")


def _without_acknowledged(rows: list):
    """``(rows, acknowledged, problem)``: the rows a person has not acknowledged, the ones
    they have (each with who, why and when, for the page's evidence), and a source result
    naming the record when it cannot be read. Unreadable hides NOTHING: every row stays,
    and the page says the record could not be read."""
    from modules import acknowledgements as ACK

    if not any(r.get("acknowledge") for r in rows):
        return rows, [], None
    started = time.time()
    got = ACK.read()
    if got["state"] == "unreadable":
        return rows, [], source_result(
            "acknowledgements", "Acknowledgements", read_at=started,
            took_ms=int((time.time() - started) * 1000),
            error=(f"the acknowledgement record could not be read ({got.get('error')}): every "
                   "row is shown, acknowledged or not"))
    kept, gone = [], []
    # An acknowledgement made for an earlier device of a name hides none of the new one's rows
    # (C1476, `acknowledgements.current`): it can only hide less.
    acks = ACK.current(got["rows"])
    for r in rows:
        a = ACK.covering(r["id"], r.get("event"), acks) if r.get("acknowledge") else None
        if a and a.get("band") is not None:
            # WITHIN ITS BAND ONLY (C433): hidden while the reader's reading is inside the
            # band recorded with the acknowledgement; outside it, or unread, the row stays and
            # says why, naming the band and the value.
            # The acknowledgement's own band GOVERNS, against the newest value (C533,
            # `acknowledgements.within_band`): the reader's stored reading can carry an older
            # acknowledgement's band until it runs again.
            judged = ACK.within_band(a, (r.get("operands") or {}).get("band_reading"))
            if judged["in_band"]:
                gone.append({"id": r["id"], "what": r["what"], "by": a.get("by"),
                             "why": a.get("why"), "at": a.get("at"),
                             "band": f"within its band: {judged['value']:.3g} at or under "
                                     f"{judged['band']:.3g}"})
                continue
            r = dict(r)
            r["cause"] = f"{r['cause']}. {band_words(a, judged)}, so it is shown"
            kept.append(r)
        elif a:
            gone.append({"id": r["id"], "what": r["what"], "by": a.get("by"),
                         "why": a.get("why"), "at": a.get("at")})
        else:
            kept.append(r)
    return kept, gone, None


#: The source each acknowledgeable row comes from, so an acknowledgement checks the row
#: exists NOW (computed again, never taken from the browser).
_ACK_SOURCES = {"restarts": "restart_source", "authorisations": "authorisation_source",
                "operations": "interrupted_source", "grafana": "grafana_source",
                "host_key_windows": "host_key_window_source",
                "adjacency_log": "adjacency_log_source", "deploys": "deploy_source",
                "console_ztp": "console_ztp_source"}


def acknowledge(row_id: str, event: str, why: str, *, by: str, verified: str) -> dict:
    """A person acknowledges ONE event row. Refused unless the row is on the page now, of a
    kind acknowledged here, about this same event, and the reason has the shape of one."""
    from modules import acknowledgements as ACK
    from modules.nsot.authorisation import reason_problem

    source = (row_id or "").split(":", 1)[0]
    fn = _ACK_SOURCES.get(source.split("@", 1)[0])
    if not fn:
        return {"ok": False, "error": f"{row_id!r} is not a row a person acknowledges: it "
                                      "clears when its condition resolves (its row says how)"}
    if "@" in source:
        # Another network's own configuration (P.8 step 5): its source as the page draws it.
        mine = [s for s in _with_every_configuration([globals()[fn]])
                if getattr(s, "__name__", "") == f"{fn}@{source.split('@', 1)[1]}"]
        rows = mine[0]()["rows"] if mine else []
    else:
        rows = globals()[fn]()["rows"]
    found = next((r for r in rows if r["id"] == row_id), None)
    if found is None:
        return {"ok": False, "error": f"{row_id!r} is not on Needs attention now: nothing to "
                                      "acknowledge"}
    if not found.get("acknowledge"):
        return {"ok": False, "error": f"{row_id!r} clears when its condition resolves (its row "
                                      "says how), not by a person's acknowledgement"}
    if str(found.get("event")) != str(event or ""):
        return {"ok": False, "error": (f"the row is now about {found.get('event')!r}, not "
                                       f"{event!r}: a later event is acknowledged on its own")}
    # The authorisation rule's shape check (not empty, three words, eight characters),
    # with no line to compare against: its messages then begin with the empty line's repr.
    if reason_problem({"line": "", "reason": (why or "").strip()}):
        from modules.nsot.authorisation import MIN_CHARS, MIN_WORDS
        return {"ok": False, "error": (
            f"an acknowledgement needs a reason: at least {MIN_WORDS} words and {MIN_CHARS} "
            "characters saying why this needs nothing more (what you found, or why it was "
            "expected); its quality is never judged")}
    if not by:
        return {"ok": False, "error": "an acknowledgement names the person who made it"}
    got = ACK.read()
    if got["state"] == "unreadable":
        return {"ok": False, "error": "the acknowledgement record could not be read, so "
                                      f"nothing was added to it ({got.get('error')})"}
    extra = {}
    if (found["source"], found["kind"]) == ("grafana", "series"):
        # WITHIN A BAND (C433): the series' 7-day p95, measured now, and its value now; the
        # acknowledgement holds only while the value stays at or under the band.
        from modules.alert_bands import band, current

        ops = found.get("operands") or {}
        b, why_not = band(ops.get("value_expr", ""), ops.get("labels") or {})
        if b is None:
            return {"ok": False, "error": f"Not acknowledged: its band could not be measured "
                                          f"({why_not}), and an acknowledgement here holds only "
                                          "within one"}
        now, _why = current(ops.get("value_expr", ""), ops.get("labels") or {})
        extra = {"band": b, "value": now}
    elif (found["source"], found["kind"]) == ("adjacency_log", "flap"):
        # WITHIN A BAND (C589, C433's shape): the adjacency's highest daily count of drops in the
        # reader's week, and its count in the last day; it holds while that stays at or under.
        ops = found.get("operands") or {}
        if ops.get("band") is None:
            return {"ok": False, "error": "Not acknowledged: its band (the highest daily count "
                                          "of the last week) was not read, and an "
                                          "acknowledgement here holds only within one"}
        extra = {"band": ops["band"], "value": (ops.get("band_reading") or {}).get("value")}
    try:
        entry = ACK.record(row_id, found["event"], why=why, by=by, verified=verified,
                           kind=f"{found['source']}/{found['kind']}", what=found["what"],
                           devices=found.get("devices") or [], **extra)
    except Exception as exc:                          # noqa: BLE001 (refused, with its why)
        first = (str(exc).strip().splitlines() or [type(exc).__name__])[0]
        log.error("acknowledge %s: the record could not be written: %s", row_id, first)
        return {"ok": False, "error": f"Not acknowledged: the acknowledgement could not be "
                                      f"recorded ({type(exc).__name__}: {first}); the row "
                                      "stays"}
    out = {"ok": True, "acknowledged": entry, "hides_now": True, "words": ""}
    if extra:
        # An acknowledgement within a band that cannot hide its row NOW says so (C533, the
        # operator, 2026-10-06: three acknowledgements recorded, each above its band, and the
        # button stayed "Acknowledging…" saying nothing).
        judged = ACK.within_band(entry)
        if not judged["in_band"]:
            out["hides_now"] = False
            out["words"] = (f"Recorded. {band_words(entry, judged)}, so the row stays until "
                            "its value falls within the band; acknowledging again measures "
                            "the same 7-day band.")
    return out


def _with_every_configuration(sources) -> list:
    """*sources*, with the Grafana alerts source once more for each OTHER network's own
    Grafana (P.8 step 5): the reader stores each configuration apart, and a page that read
    only Default's would drop another network's alerts while every check passed. Listing the
    configurations failing keeps Default's and adds a source saying so."""
    import functools

    from modules import reader_job

    out = list(sources)
    if grafana_source not in out:
        return out
    try:
        others = [v for v in reader_job.configuration_readers(_alerts_reader())
                  if v.name != GRAFANA_READER]
    except Exception as exc:                        # noqa: BLE001
        def unread(why=f"{type(exc).__name__}: {exc}"):
            return source_result("grafana@networks", "Grafana alerts (other networks)",
                                 read_at=time.time(), took_ms=0,
                                 error=f"the networks' Grafana configurations could not be "
                                       f"listed ({why}), so only Default's alerts are shown")
        return out + [unread]
    from modules import integration_groups as IG

    by_store = {IG.store_name(GRAFANA_READER, g["id"]): g
                for g in IG.groups(tuple(_alerts_reader().per_group))}
    for v in others:
        g = by_store.get(v.name) or {"id": v.name.split("@", 1)[-1], "lists": []}
        fn = functools.partial(grafana_source, reader_job.read_cached(v.name),
                               configuration={"id": g["id"], "lists": g["lists"]})
        fn.__name__ = f"grafana_source@{g['id']}"
        out.append(fn)
    return out


def _alerts_reader():
    from modules.readers import grafana_alerts

    return grafana_alerts.READER


def _span_words(seconds: float) -> str:
    seconds = max(int(seconds), 0)
    if seconds < 120:
        return f"{seconds} s"
    if seconds < 7200:
        return f"{seconds // 60} min"
    if seconds < 172800:
        return f"{seconds // 3600} h"
    return f"{seconds // 86400} d"


def _past_promise_rows(results: list, now: float) -> list:
    """C1271: each source whose value is older than its own promise (`stale_after_seconds`)
    is a row of its own, so a page whose readers stopped never reads as nothing needing
    attention (CLAUDE.md: a stale or unreadable source is itself a row)."""
    out = []
    # A source that judges its own staleness, with a row kind of its own (drift's "the last
    # drift check is old", on its own clock), is never judged twice.
    own = {s for (s, k) in ROW_KINDS if k == "stale" and s != "freshness"}
    for res in results:
        if res.get("source") in own:
            continue
        value_at, promise = _ts(res.get("value_at")), res.get("stale_after_seconds")
        if res.get("state") != "read" or not value_at or not promise:
            continue
        # How old the value was when this read took it (the source's own read time; a live
        # read's is now), never another clock's.
        age = (_ts(res.get("read_at")) or now) - value_at
        if age <= promise:
            continue
        out.append(row(
            source="freshness", kind="stale", key=res["source"], level="warning",
            what=f"{res['label']} has not been read within its promise",
            cause=(f"its value is {_span_words(age)} old and is promised every "
                   f"{_span_words(promise)}, so what it shows may no longer be true"
                   + (f" ({res['reader']} reader)" if res.get("reader") else "")),
            read_at=value_at,
            action={"label": "Open Job health on Settings › Installation and read why its "
                             "reader has not run"}))
    return out


def needs_attention(sources=None) -> dict:
    """The page: every row from every source, worst first, and every source
    with its read time, so an empty page says what it looked at."""
    results = []
    for src in (_with_every_configuration(SOURCES) if sources is None else sources):
        try:
            results.append(src())
        except Exception as exc:                   # noqa: BLE001
            # A source whose ADAPTER raised is still a row, never an absence.
            name = getattr(src, "__name__", "source")
            log.error("attention: source %s raised: %s", name, exc)
            results.append(source_result(name, name, read_at=time.time(), took_ms=0,
                                         error=f"its adapter raised {type(exc).__name__}: {exc}"))
    # C539 (3): every row shows the age of its reading. A row that names none is as old as
    # the value its source shows (a stored reader's value, or this request's live read).
    for res in results:
        for r in res["rows"]:
            if not r.get("read_at"):
                r["read_at"] = res.get("value_at") or res.get("read_at")
    rows = _with_networks(_attach(_fold_known_unmonitored(_fold_one_cause(
        [r for res in results for r in res["rows"]]
        + _past_promise_rows(results, time.time())))))
    rows, acknowledged, ack_result = _without_acknowledged(rows)
    if ack_result:
        results.append(ack_result)
    in_force = _standing_acknowledgements(acknowledged)
    rows.sort(key=lambda r: (LEVELS.index(r["level"]), r["source"], r["id"]))
    unreadable = [res["label"] for res in results if res["state"] != "read"]
    if rows:
        headline = f"{len(rows)} thing(s) need attention"
    else:
        headline = "Nothing needs attention"
    return {"ok": True, "headline": headline, "rows": rows,
            "unreadable": unreadable, "acknowledged": acknowledged, "in_force": in_force,
            "badge": badge_of(rows, results),
            "sources": [{k: res[k] for k in ("source", "label", "state", "read_at",
                                             "value_at", "took_ms", "checked")}
                        | {"count": len(res["rows"])} for res in results]}
