"""Stage 7 section 10, acceptance criterion 4 on v2: if a v2 route carries it, its page draws it.

`test_payload_is_rendered.py` measured today's (v1) JSON routes against today's JavaScript
renderers until today's pages went (P7-27, 2026-10-17: the index and the Bootstrap pages
removed, and that check with them, its population empty). v2 draws on the server: a route hands
its template a context, so the context is the payload and the template is the renderer (P7-04,
2026-10-15).
`tests/v2_context.py` says how both are found and what the comparison cannot see.

* **Population, by property:** every v2 page reached by following links from Needs attention and
  from a device page (tests/interface_pages.py's walk), every fragment those pages and their
  fragments ask for by `hx-get` or a GET form, and the cards no GET reaches, made by the
  providers on the same lab (a reveal, the intent check, the deploy card with a program, a
  dangerous line and a residue line). Each request's renders are recorded through Flask's
  `template_rendered` signal.
* **Forward:** a key a route's context carries that no template in the same response reads is
  a finding: draw it, or declare it in `UNDRAWN` with its reason. The list is compared exactly
  (no ghosts) and its size pinned: it only shrinks.
* **Upstream:** a card built by a server-side adapter from a preview drops what the adapter does
  not read before any template sees it (D4's failure one step up). For the deploy card, the
  preview's keys are compared with what the adapter and the template read (`UPSTREAM`).
* **Unreached:** a v2 template named in the product's code that no measured request renders is
  not examined at all; each is named in `UNREACHED`, a list that only shrinks.
* **The state the test data reaches (C1274):** every `{% for %}` in a template the walk reaches
  drew at least once (its body ran, measured by a mark compiled into it), or is declared in
  `EMPTY_IN_FIXTURE` with its reason, a list that only shrinks: a collection empty in every
  render hides every field its items carry from every check here and from every page shot.
  Today's renderers held the same rule as test_payload_is_rendered.py's `EMPTY_IN_FIXTURE`.
* **Anchors:** the deploy card's program, dangerous lines, residue and notes are carried AND
  read (D4, C27), and the plan's attribution with them (C867, 2026-10-16); the fixture carries
  the attribution, so whether the card draws it is measured, not assumed.
"""

import pytest

from tests import v2_context as V

DEPLOY = "GET /v2/device/<name>/deploy"

#: Reasons shared by several routes. A reason beginning "GAP" is a finding: a fact a person
#: needs, carried and drawn nowhere on v2 (reported with P7-04, 2026-10-15).
DEVICE_ROW = ("the inventory row passed whole for its name: the fragment draws `hostname`; the "
              "address and login are drawn in the device page's header, the type on Overview")
CARD_IP = ("a leftover: `c.ip` was added for links to today's device page, gone since; the "
           "address is drawn in the device page's header")
LISTREF = ("the network's ListRef passed whole as `ref`: its csv, data and repository paths are "
           "internal; the page draws the network's name")
GRAFANA = ("Grafana's own panel model (upstream JSON), consumed in Python by "
           "panels.render_payload and build_request; the panel is drawn from that payload")
PANELS = ("`drawn` is the input to panels.layout, which is drawn; `seconds` is drawn as the "
          "step and the range's words")
DESCRIPTION = ("GAP (minor): a Grafana panel's own description, never drawn in the panel head; "
               "today's pages never drew it either")
TRANSFORMS = ("GAP (minor): how many of a panel's transformations Mercury counts and does not "
              "apply, so a panel can differ from Grafana's unsaid")
DEFAULT_BADGE = ("the dashboard's default flag: the same template draws it as the `default` "
                 "badge by comparing uids")
VALUE_FROM = ("which device field fills the dashboard variable (a setting, drawn on Settings); "
              "the chip draws the value it produced")
COVERAGE_ROW = ("a coverage row's internals for this one device: its row key, tick-box default "
                "and the list of not-reporting cells, each cell's own words drawn instead")
COVERAGE_FACTS = ("drawn on Monitoring › Coverage (golden, profile, sections, the reading per "
                  "cell), the platform in the page header and the role on Devices")
HISTORY_SHELL = ("the History page's filter bar and identity line, drawn by "
                 "`_history_body.html` on /v2/history; the tab and the timeline redraw only the "
                 "events")
EVENT_VERIFIED = ("folded into each event's `who` words ('host login, not verified'), which are "
                  "drawn")
KIND_COUNTS = ("GAP (minor): each event kind's count, carried 'for the filters' choices'; the kind "
               "filter shows no numbers, and nothing else reads them")
ATTENTION = ("a row's plumbing: `attach_to` merges rows (the merged row draws 'Also: ...'), "
             "`clears.ways` is the machine form of `clears.when` (drawn), `triage` is always "
             "None, kept for Stage 8; the headline's count is drawn from the badge")
BADGE_TIMERS = ("the badge's timers and envelope: drawn by the sidebar count fragment "
                "(/v2/attention-count) as the data its script keeps fresh")
PROFILE_ROWS = ("a device's rotation-policy plumbing: `on` sorts devices into groups (the groups "
                "are drawn), its policy words repeat the profile row's, and an unreadable run "
                "record is its own Needs attention row")
SC_PICK = ("the fragment is handed the whole pick model; these are drawn by `_sc_pick.html` on "
           "/v2/show-commands (filters, sets, limits, the matched devices)")
RANGE_RAW = ("raw range epochs and seconds handed to the reader; drawn in words (the range's "
             "words, the answer's title, the kept-from words)")
ASK_SHELL = ("the page shell's context (tabs, filters, the remote header, the flag choosing the "
             "include, the network's ListRef), drawn by the full page through "
             "`_history_body.html`")
STEPPER = ("the stepper's and the host steps' raw numbers and bookkeeping: their words (bar, "
           "tally, elapsed, each step's sha and id) are drawn; `install` and `target_gone` are "
           "drawn as the gates' details")
SCOPE_ROW = ("a scope-picker row's internals: Python sorts and groups by them, and the picker "
             "draws the groups' headings and the row's label")
GROUP_STATE = ("a settings group's state record: the raw choice is drawn as the card's `on` "
               "segment, follows and explicit by the mode preview's 'what is kept', the URL as "
               "its own field")
INSTALL_CARD = ("the whole card record handed to the Replace form, which reads `spec`, `name` "
                "and the id; these are drawn by `_install_card.html` on the card's own route")
RECORDS_CARD = ("the whole records card handed to the Replace form, which reads only the "
                "password rule; every one of these is drawn by `_records_db_card.html`")

#: {route: [(keys, reason), ...]}: carried, drawn by no template of the same response.
#: The pending page and its fragment (C1193): measured first on 2026-10-17, when a provider
#: reached them (both were UNREACHED). The manifest's pending row and the ZTP stage are
#: passed whole; these keys feed the route's own reckoning (the stepper's took_s, the stop
#: rule) and are drawn through it, not by name (C1219: trim them or draw them).
PENDING_UNDRAWN = ("the pending row's and the ZTP stage's own reckoning (age, counts, "
                   "elapsed, identity), drawn through the stepper and the stop rule, not "
                   "by name; C1219")

UNDRAWN = {
    "GET /v2/": [("attach_to headline triage ways", ATTENTION)],
    "GET /v2/attention": [("attach_to headline triage ways", ATTENTION),
                          ("next_change_at ok stale_at", BADGE_TIMERS)],
    "GET /v2/attention-count": [
        ("unreadable", "the number of unreadable sources: Needs attention draws each by name "
                       "('N could not be read: ...')")],
    "GET /v2/credentials": [
        ("stale", "the devices a stale record cannot recover, already joined into the record "
                  "card's words, which are drawn")],
    "GET /v2/credentials/export": [
        ("explain parts titles", "the generic preview renderer's envelope; this card is bespoke, "
                                 "with its own headings, and its explain is empty"),
        ("list target", "echoes of the network's name, which the card draws throughout")],
    "GET /v2/credentials/profiles": [("on policy_words runs_error", PROFILE_ROWS)],
    "GET /v2/credentials/profiles/form": [("on policy_words runs_error", PROFILE_ROWS)],
    "GET /v2/credentials/profiles/region": [("on policy_words runs_error", PROFILE_ROWS)],
    "GET /v2/credentials/profiles/rotate-due": [("on policy_words runs_error", PROFILE_ROWS)],
    "GET /v2/device/<name>": [
        ("datasource field_mappings gridPos mappings max min no_value organize targets "
         "thresholds", GRAFANA),
        ("description", DESCRIPTION), ("transformations", TRANSFORMS),
        ("drawn seconds", PANELS), ("is_default", DEFAULT_BADGE), ("value_from", VALUE_FROM),
        ("checked not_reporting", COVERAGE_ROW), ("reporting sections", COVERAGE_FACTS),
        ("identity people", HISTORY_SHELL), ("verified", EVENT_VERIFIED),
        ("proto", "the neighbour protocol's id: its words are drawn"),
        ("age_seconds counts elapsed_s total", PENDING_UNDRAWN)],
    "GET /v2/device/<name>/pending/progress": [
        ("age_seconds counts elapsed_s identity total", PENDING_UNDRAWN)],
    "GET /v2/device/<name>/actions": [("device_type ip username", DEVICE_ROW)],
    "GET /v2/device/<name>/deploy": [("ip", CARD_IP)],
    "GET /v2/device/<name>/drained": [("device_type ip username", DEVICE_ROW)],
    "GET /v2/device/<name>/history": [
        ("device_type ip username", DEVICE_ROW), ("counts", KIND_COUNTS),
        ("identity people", HISTORY_SHELL), ("verified", EVENT_VERIFIED)],
    "GET /v2/device/<name>/intent": [("device_type ip username", DEVICE_ROW)],
    "GET /v2/device/<name>/logs": [("device_type ip username", DEVICE_ROW)],
    "GET /v2/device/<name>/monitored-by": [
        ("device_type ip username", DEVICE_ROW), ("checked host not_reporting", COVERAGE_ROW),
        ("golden platform profile reporting role", COVERAGE_FACTS)],
    "GET /v2/device/<name>/monitoring": [
        ("device_type ip username", DEVICE_ROW),
        ("datasource field_mappings gridPos mappings max min no_value organize targets "
         "thresholds", GRAFANA),
        ("description", DESCRIPTION), ("transformations", TRANSFORMS),
        ("drawn seconds", PANELS), ("is_default", DEFAULT_BADGE), ("value_from", VALUE_FROM),
        ("checked host not_reporting", COVERAGE_ROW),
        ("golden platform profile reporting role", COVERAGE_FACTS)],
    "GET /v2/device/<name>/neighbours": [
        ("device_type ip username", DEVICE_ROW),
        ("proto source", "the protocol's id (its words are drawn) and a marker set on RIP "
                         "entries that nothing reads")],
    "GET /v2/device/<name>/netbox": [("device_type ip username", DEVICE_ROW)],
    "GET /v2/device/<name>/overview": [
        ("username", "the login the tool uses: drawn in the device page's header, around this "
                     "tab"),
        ("commit", "the intent check's compared golden sha; the same golden's sha is drawn in "
                   "Overview's Golden row"),
        ("value_at", "when the reachability reader stored its value; the probe's own time "
                     "(`checked_at`) is drawn")],
    "GET /v2/device/<name>/persist": [("ip", CARD_IP)],
    "GET /v2/device/<name>/privileged": [
        ("hostname ip list_name", "the plan echoes its inputs (the address feeds its hash); the "
                                  "card draws the host and the network"),
        ("refusals", "joined by the route into the card's error and drawn as 'Refused: ...' on "
                     "Preview")],
    "GET /v2/device/<name>/restore": [("ip", CARD_IP)],
    "GET /v2/device/<name>/restore/preview": [("ip", CARD_IP)],
    "GET /v2/device/<name>/retire": [("ip", CARD_IP)],
    "GET /v2/device/<name>/seed": [
        ("ip", CARD_IP),
        ("caption", "the shared preview model's caption; the seed card says the same in its own "
                    "words")],
    "GET /v2/device/<name>/status": [
        ("device_type ip username", DEVICE_ROW),
        ("last_result", "the probe's last result: drawn on Overview as 'last probe ...'"),
        ("value_at", "when the reachability reader stored its value; the probe's own time "
                     "(`checked_at`) is drawn")],
    "GET /v2/devices/table": [
        ("counts platforms states", "the filters' choices and counts, drawn by the full page's "
                                    "filter selects; the table fragment does not redraw them")],
    "GET /v2/help/<slug>": [
        ("anchors diagrams sections", "the page's parts, already inside its HTML (drawn); "
                                      "`sections` feeds the side panel's own route"),
        ("nav_title", "the declared page title, drawn in the same response's help navigation")],
    "GET /v2/help/installation": [
        ("initials", "part of the `who` chip handed to the card; the name chip draws it")],
    "GET /v2/history": [("csv_path data_dir repo_dir", LISTREF), ("counts", KIND_COUNTS)],
    "GET /v2/history/commit/<sha>": [
        ("stat", "always empty: the --stat output is already inside the diff's text, which is "
                 "drawn")],
    "GET /v2/history/query/ask/logs": [
        ("csv_path data_dir repo_dir", LISTREF), ("end seconds start", RANGE_RAW),
        ("by_label log_query", "the selector and grouping label the query is built from; the "
                               "whole query is drawn token by token")],
    "GET /v2/history/query/ask/logs/region": [
        ("ask_logs f ref remote tab tabs", ASK_SHELL), ("end seconds start", RANGE_RAW),
        ("by_label log_query", "the selector and grouping label the query is built from; the "
                               "whole query is drawn token by token"),
        ("notes", "copies of the explain's device and severity notes, which the same region "
                  "draws"),
        ("since", "the label discovery's start epoch, drawn as its since-words")],
    "GET /v2/history/query/ask/metrics": [
        ("csv_path data_dir repo_dir", LISTREF),
        ("end kept_from now_ts seconds start", RANGE_RAW),
        ("meta", "Prometheus metadata, drawn as the metric's kind, unit and help")],
    "GET /v2/history/query/ask/metrics/region": [
        ("ask_metrics ref remote tab tabs", ASK_SHELL),
        ("end kept kept_from now_ts seconds start", RANGE_RAW),
        ("meta", "Prometheus metadata, drawn as the metric's kind, unit and help")],
    "GET /v2/history/query/metric/<key>": [
        ("csv_path data_dir repo_dir", LISTREF),
        ("by_device by_interface", "the question's PromQL templates; the query they fill in is "
                                   "drawn")],
    "GET /v2/history/query/syslog": [("csv_path data_dir repo_dir", LISTREF)],
    "GET /v2/history/timeline": [
        ("counts", KIND_COUNTS), ("identity kind_groups people", HISTORY_SHELL),
        ("verified", EVENT_VERIFIED)],
    "GET /v2/monitoring/coverage": [
        ("covered", "a count the template computes itself, as 'fully covered'"),
        ("role", "the device's role, drawn on Devices; on Coverage it only scopes sections")],
    "GET /v2/monitoring/coverage/table": [
        ("covered", "a count the template computes itself, as 'fully covered'"),
        ("role", "the device's role, drawn on Devices; on Coverage it only scopes sections")],
    "GET /v2/monitoring/dashboard": [
        ("datasource field_mappings gridPos mappings max min no_value organize row targets "
         "thresholds", GRAFANA),
        ("description", DESCRIPTION), ("transformations", TRANSFORMS),
        ("drawn seconds", PANELS), ("is_default", DEFAULT_BADGE)],
    "GET /v2/monitoring/decline": [
        ("busy", "GAP (minor): what holds the device now; the decline card does not say so "
                 "before the confirm (the apply refuses under the hold), its peer cards do")],
    "GET /v2/monitoring/heartbeat": [
        ("pending written", "the written rules file's sha and the flag deciding whether a host "
                            "step is computed; the host step is drawn")],
    "GET /v2/monitoring/profile/propose": [
        ("profile_blob", "the committed profile's blob id, folded into the proposal's hash"),
        ("receives", "GAP (minor): per changed section, how many devices' templates render it; "
                     "only the dropped are drawn")],
    "GET /v2/netbox": [
        ("at_iso", "the age of the integrations reader's value: drawn on Settings › "
                   "Installation; the NetBox page's badge shows no age")],
    "GET /v2/settings": [("bucket", SCOPE_ROW), ("choice explicit follows url", GROUP_STATE)],
    "GET /v2/settings/installation": [
        ("bucket mode", SCOPE_ROW),
        ("built", "a list equal to every tab, left from when some tabs were unbuilt; nothing "
                  "reads it"),
        ("certs_url", "the identity provider's key endpoint, derived from the team domain "
                      "(drawn); Python fetches from it"),
        ("default origin", "each identity gate cell's raw inputs, drawn as its origin words"),
        ("first_failure_at", "GAP (minor): when redaction first failed since start-up; the "
                             "card draws the count and the last time only"),
        ("group", "a settings group's internal id; its title is drawn"),
        ("rule_words", "the password rule, drawn by the records Replace form")],
    # P7-05 (2026-10-16): the Access cards read again on `posture`, the same context as the
    # page's tab.
    "GET /v2/settings/installation/access": [
        ("certs_url", "the identity provider's key endpoint, derived from the team domain "
                      "(drawn); Python fetches from it"),
        ("default origin", "each identity gate cell's raw inputs, drawn as its origin words")],
    "GET /v2/settings/installation/card/<name>": [
        ("group", "a settings group's internal id; its title is drawn"),
        ("tab", "the tab the card belongs to: the route filters cards by it, and only the "
                "Replace form's Cancel reads it")],
    "GET /v2/settings/installation/card/<name>/replace": [
        ("fields health secret_set writes", INSTALL_CARD),
        ("integration loaded secret_at", "the form echo, a layout index and the Test button's "
                                         "gate, used only by `_install_card.html`"),
        ("group", "a settings group's internal id; its title is drawn")],
    "GET /v2/settings/installation/diagnostics/redaction": [
        ("first_failure_at", "GAP (minor): when redaction first failed since start-up; the "
                             "card draws the count and the last time only")],
    "GET /v2/settings/installation/records": [
        ("rule_words", "the password rule, drawn by the records Replace form")],
    "GET /v2/settings/installation/records/replace": [
        ("config loaded record_unreadable stale steps stores test test_unreadable version",
         RECORDS_CARD)],
    "GET /v2/settings/network/<list_name>": [
        ("bucket", SCOPE_ROW), ("choice explicit follows url", GROUP_STATE)],
    "GET /v2/settings/network/<list_name>/group/<group>": [
        ("choice explicit follows url", GROUP_STATE)],
    "GET /v2/settings/network/<list_name>/group/<group>/switch": [
        ("before", "the whole before-state record: the template draws `from`, and Python words "
                   "the gate from it"),
        ("choice explicit follows url", GROUP_STATE),
        ("list", "an echo of the network's name, drawn from the top-level name")],
    "GET /v2/settings/network/<list_name>/mode": [
        ("rows", "every group's row: the card draws the moving subset, and the rest feeds what "
                 "is kept"),
        ("changes group", "the filter that builds the moving rows, and a group's id (its label "
                          "is drawn)"),
        ("follows from", "drawn in the card's 'what is kept' and the gate's words"),
        ("list", "an echo of the network's name, drawn from the top-level name")],
    "GET /v2/settings/network/<list_name>/mode/banner": [
        ("cards is_default mode_words scope tab tabs", "the whole network view handed to the "
                                                       "banner, which reads four fields; the "
                                                       "settings page draws the rest")],
    # P7-05 (2026-10-16): the scope bar alone, read again on `lists`.
    "GET /v2/settings/scope": [("bucket mode", SCOPE_ROW)],
    "GET /v2/show-commands/check": [
        ("list max_commands message platform platforms q role roles rows sets sets_unreadable "
         "site sites test_command test_wait workers", SC_PICK),
        ("shown total", "the matched devices and their count, drawn by `_sc_devices.html`"),
        ("fingerprint", "the matched devices' hash, a hidden input `_sc_devices.html` carries "
                        "and Run checks again")],
    "GET /v2/show-commands/devices": [
        ("heavy list max_commands message platforms roles rows sets sets_unreadable sites "
         "test_command test_wait workers", SC_PICK),
        ("reason", "drawn by `_sc_reason.html`, rendered by the check route and inside the pick "
                   "card")],
    "GET /v2/templates/coverage/card": [
        ("may", "the approve gate's statement, drawn in the Approve or Revoke card these buttons "
                "open")],
    "GET /v2/templates/rows": [
        ("may", "the approve gate's statement, drawn in the Approve or Revoke card these buttons "
                "open")],
    "GET /v2/topology": [
        ("proto_words", "a constant vocabulary already applied in Python to the chips and edge "
                        "words the map draws")],
    "GET /v2/topology/map": [
        ("proto_words", "a constant vocabulary already applied in Python to the chips and edge "
                        "words the map draws")],
    "GET /v2/update": [
        ("counts elapsed_s ids install superseded target_gone total when", STEPPER)],
    "GET /v2/update/panel": [
        ("counts elapsed_s ids install superseded target_gone total when", STEPPER),
        ("who", "handed to the panel fragment, which has no name chip; the page's chip draws "
                "it")],
    "GET /v2/who": [
        ("kind", "person or service: a service is already drawn by its label; the kind itself "
                 "is drawn nowhere")],
    "POST /v2/device/<name>/intent/check": [
        ("stage status", "the check's HTTP status and failing stage; the card draws its error "
                         "with line and column")],
}
#: +5 2026-10-16: P7-05's two fragments, the same plumbing as their pages. -4 2026-10-16:
#: C868 (the restore chooser draws each moment's `subject`, on both routes) and C869 (the
#: profile proposal draws `devices_read` and `skipped`).
#: +9 2026-10-17: the pending page and its fragment measured for the first time (C1193's
#: provider took them off UNREACHED, -2 there); their nine keys were carried and undrawn
#: before, unmeasured (C1219).
#: -2 2026-10-19: the Record stores card draws each store's `store` (K31 part 2a: its Move and
#: Move back buttons send it).
UNDRAWN_CEILING = 365

#: {route: [(keys, reason), ...]}: in the preview a card is built from, read by neither its
#: adapter nor its template.
UPSTREAM = {
    DEPLOY: [
        ("select_data hash secret removal prior verify",
         "today's wizard's selection data; the card reads the same facts from the plan entry "
         "and builds its confirm from the unmasked plan's hashes (routes/device_v2._deploy_card)"),
        ("explain concept parts",
         "the generic preview renderer's envelope and teaching text (`_preview_parts.html` draws "
         "it for batch previews); the deploy card is bespoke, in its own words"),
        ("selected children",
         "a removable line's tick and stanza size in the generic preview; the card builds its "
         "residue rows from the plan entry, with its own `picked` and `why_not`")]}
UPSTREAM_CEILING = 11  # -5 2026-10-16: C867, the plan's attribution carried and drawn

_A_POST = "a POST's card: no GET draws it, and no provider in tests/v2_context.py makes it yet"
_A_JOB = "a running or finished job's card: the lab starts no job, so no provider reaches it yet"
_A_STATE = "a state the lab does not hold, so no measured request renders it yet: "

#: {template: reason}: under templates/v2/, reached by no measured render (itself or through
#: what a rendered template extends, includes or imports).
UNREACHED = {
    "v2/_apply_job.html": _A_JOB,
    "v2/_breakglass_done.html": _A_POST + " (a recovery record confirmed intact)",
    "v2/_breakglass_refused.html": _A_STATE + "an export, check or drill refused",
    "v2/_bulk_intent.html": _A_STATE + "devices ticked for a bulk intent change (a form)",
    "v2/bulk_intent.html": _A_STATE + "devices ticked for a bulk intent change (a form)",
    "v2/_coverage_deploy_preview.html": _A_STATE + "Coverage's combined deploy, devices ticked",
    "v2/coverage_deploy.html": _A_STATE + "Coverage's combined deploy, devices ticked",
    "v2/_history_reveal.html": _A_POST + " (a log line revealed on History's logs question)",
    "v2/_history_views_result.html": _A_POST + " (a saved view stored or removed)",
    "v2/_install_platforms_test.html": _A_POST + " (a platform's test run)",
    "v2/_lp_result.html": _A_JOB + " (the logging-path test's result, inside a run's part)",
    "v2/_netbox_job.html": _A_JOB + " (a NetBox sync)",
    "v2/_netbox_removals.html": _A_STATE + "NetBox objects tagged and recorded as created",
    "v2/retired.html": _A_STATE + "a retired device",
    "v2/_retry.html": _A_STATE + "a deploy blocked by a rolled-back change",
    "v2/_revert.html": _A_STATE + "a change to revert (a rolled-back deploy's way out)",
    "v2/reapply.html": _A_STATE + "a History moment chosen to re-apply",
    "v2/_sc_result.html": _A_JOB + " (a show-commands run)",
    "v2/show_commands_run.html": _A_JOB + " (a show-commands run)",
    "v2/_template_check.html": _A_POST + " (a template edit checked; the lab has no library)",
    "v2/_topology_result.html": _A_JOB + " (a topology read)",
}
#: -2 2026-10-17: the pending page and _onboard_pending.html, reached by C1193's provider.
UNREACHED_CEILING = 21

# ── C1274: the loops no fixture reaches ─────────────────────────────────────────────────────
#: Reasons shared by many loops. Each names the state the walk and the providers do not hold;
#: every entry is a finding (a state no check on v2 photographs), and the list only shrinks.
_OP = ("an operation's preview, run or result, drawn after a POST (or the job it starts) that "
       "no provider in tests/v2_context.py makes")
_RESULT = ("a finished operation's result (its checks, what it did not do, what was authorised, "
           "what failed): no provider confirms the operation")
_FAILING = ("the gates that refuse the operation, listed only when one fails: every gate the "
            "lab's card reads passes")
_ERRORS = ("an error list: every read the walk makes answers, so no render holds an error to "
           "list")
_KEA = ("DHCP: the lab stores no DHCP reader value (no Kea answers), so the region draws its "
        "not-read state and none of Kea's subnets, leases, reservations or exclusions")
_KEA_OP = ("a DHCP change's form, preview or result: the lab stores no DHCP reader value and no "
           "provider posts a change")
_TOPOLOGY = ("Topology: the lab stores no topology reader value, so the map, its tables, its "
             "weak points and its path and take-out tools draw nothing")
_LOKI = ("syslog lines: the lab stores no logs reader value and no Loki answers the walk, so "
         "no line, device, severity or trend is drawn")
_LOGS_ASK = ("History › Ask your own (logs): no Loki answers the walk, so the builder has no "
             "labels or values to offer and no answer, rows or series to draw")
_METRICS_ASK = ("History › Ask your own (metrics): no Prometheus answers the walk, so the "
                "builder has no metrics, labels, operations or saved questions to offer and "
                "no answer to draw")
_LIBRARY = ("the lab's network has no template library (r3 renders through the built-in "
            "seeds), so no template row, binding, coverage measurement or check is drawn")
_ONE_NETWORK = ("the walk's installation has one network, Lab, inheriting everything: no "
                "standalone, differing, unreadable or inheriting network to list")
_NOTHING_RUNS = ("a running, held or finished operation: the walk's In progress and in-flight "
                 "reads find none")
_DEPLOY_DECLARED = ("the deploy card's declared effects (C506 phase 3): the provider's program "
                    "declares nothing, as today's fixtures did; reached in "
                    "tests/test_declared_effects.py")
_SAVE = ("Devices › Save's plan and run: the lab's devices hold no unsaved change, so no group, "
         "device or startup difference is listed")
_RUN_GROUPS = ("the one stepper's counts and groups, drawn only for a run of more than one row: "
               "every run the walk draws has one")
_PREVIEW_PARTS = ("the shared preview component's parts (targets, programs, notes, gates, what "
                  "it does not do): the walk renders it with no preview built")
_ATTENTION = ("Needs attention on the walk's fresh store: no row is merged into another, names "
              "devices, or is acknowledged, and no acknowledgement is in force")
_UPDATE = ("Update's pending commits, host steps and history: the walk's store holds no update "
           "outcome and no commit waiting, so none is listed")
_REMOTE = ("History's remote: the lab's repository has no remote connected and no uncommitted "
           "file, so set-up's probe, publication counts and the dirty list are empty")
_RECORDS = ("Record stores: the records database is off on the walk's store, so no move is "
            "previewed or run and no store's files are counted")
_HEARTBEAT = ("the heartbeat re-measure's plan: no device's heartbeat window is installed on the "
              "walk's store, so no row is measured")
_IP_SLA = ("IP SLA probes, opened from Coverage with devices chosen: the walk opens the page "
           "with none chosen, so no policy row, suggestion or skip is drawn")
_SHOW_COMMANDS = ("Show commands' pick card: the lab's devices carry no role or site, no saved "
                  "set exists, and no command is heavy")
_SETTINGS_CARD = ("a settings card's Configure… form and Test result, and Default's who-inherits "
                  "names: the walk opens no Configure… and tests nothing, and no other network "
                  "inherits")
_INTENT_CHECK = ("the intent editor's check: the provider's edit changes one value that every "
                 "parser models, from intent with no profile exclusion, so no unmodelled line, "
                 "not-from line or diff block is drawn")

#: {loop: reason}: every `{% for %}` in a reached v2 template whose body never drew in the walk
#: or a provider (C1274), named by its template and its iterable as written (tests/v2_context.py,
#: `template_loops`). Measured 2026-10-18: 557 loops, 171 drew, these 386 did not.
EMPTY_IN_FIXTURE = {
    "v2/_adopt.html (r.steps or ())": _OP + " (Adopt a device…'s run)",
    "v2/_adopt.html p.blocking": _OP + " (Adopt a device…'s preview)",
    "v2/_adopt.html p.gates": _OP + " (Adopt a device…'s preview)",
    "v2/_adopt.html p.not_doing": _OP + " (Adopt a device…'s preview)",
    "v2/_adopt.html p.program": _OP + " (Adopt a device…'s preview)",
    "v2/_adopt.html platforms": _OP + " (Adopt a device…'s form, never opened)",
    "v2/_adopt.html q.items()": _OP + " (Adopt a device…'s form, never opened)",
    "v2/_adopt.html r.remaining": _OP + " (Adopt a device…'s result)",
    "v2/_apply_preview.html held": _OP + " (the batch Apply's preview, devices ticked)",
    "v2/_apply_preview.html idle": _OP + " (the batch Apply's preview, devices ticked)",
    "v2/_apply_preview.html order": _OP + " (the batch Apply's preview, devices ticked)",
    "v2/_apply_preview.html r.blocking": _OP + " (the batch Apply's preview, devices ticked)",
    "v2/_apply_preview.html r.gates": _OP + " (the batch Apply's preview, devices ticked)",
    "v2/_apply_preview.html r.notes": _OP + " (the batch Apply's preview, devices ticked)",
    "v2/_apply_preview.html r.operands": _OP + " (the batch Apply's preview, devices ticked)",
    "v2/_apply_preview.html r.superseded": _OP + " (the batch Apply's preview, devices ticked)",
    "v2/_apply_preview.html sending": _OP + " (the batch Apply's preview, devices ticked)",
    "v2/_apply_preview.html sending #2": _OP + " (the batch Apply's preview, devices ticked)",
    "v2/_ask.html c.answers": _OP + " (Ask the device's answers: no read is run)",
    "v2/_ask.html c.compare.lines": _OP + " (Ask the device's comparison of two answers)",
    "v2/_ask.html c.recent.rows": "Ask the device's recent reads: no read has run on the walk's store",
    "v2/_ask.html c.sets": "Ask the device's saved sets: no saved set exists on the walk's store",
    "v2/_attention.html (r.attached or ())": _ATTENTION,
    "v2/_attention.html a.acknowledged": _ATTENTION,
    "v2/_attention.html a.in_force": _ATTENTION,
    "v2/_breakglass_check.html c.devices": _OP + " (a break-glass file checked)",
    "v2/_breakglass_drill.html d.errors": _OP + " (a drill's receipt refused)",
    "v2/_breakglass_export.html prog.lines": _OP + " (the break-glass export's preview)",
    "v2/_breakglass_record.html r.errors": "the break-glass record's errors: the walk's store holds no export to judge",
    "v2/_capture.html c.diff": _OP + " (Capture's preview: its read is started and not finished)",
    "v2/_capture.html c.failing": _FAILING,
    "v2/_capture.html c.gates": _OP + " (Capture's preview: its read is started and not finished)",
    "v2/_coverage.html c.declined": "Coverage's declined cells: no device declines a section on the walk's lab",
    "v2/_coverage.html c.profile.sections": "Coverage's profile line: the lab's network has no committed monitoring profile",
    "v2/_credential_profiles.html op.r.skipped": _OP + " (Rotate due devices now's result)",
    "v2/_credential_profiles.html p.chosen": _OP + " (Rotate due devices now's preview)",
    "v2/_credential_profiles.html p.waiting": _OP + " (Rotate due devices now's preview)",
    "v2/_credential_profiles.html v.rows": "Credentials › Profiles: the walk's store holds no credential profile",
    "v2/_decline.html e.checks": _OP + " (Decline…'s preview)",
    "v2/_decline.html e.diff": _OP + " (Decline…'s preview)",
    "v2/_deploy.html c.authorised": _RESULT,
    "v2/_deploy.html c.checks": _RESULT,
    "v2/_deploy.html c.did_not": _RESULT,
    "v2/_deploy.html c.failing": _FAILING,
    "v2/_deploy.html dx.declared": _DEPLOY_DECLARED,
    "v2/_deploy.html dx.ends": _DEPLOY_DECLARED,
    "v2/_deploy.html dx.moves": _DEPLOY_DECLARED,
    "v2/_deploy.html dx.to": _DEPLOY_DECLARED,
    "v2/_dhcp_exclusion.html (8 literal items)": _KEA_OP,
    "v2/_dhcp_exclusion.html p.change": _KEA_OP,
    "v2/_dhcp_exclusion.html p.checks": _KEA_OP,
    "v2/_dhcp_exclusion.html p.leases": _KEA_OP,
    "v2/_dhcp_exclusion.html p.survives": _KEA_OP,
    "v2/_dhcp_exclusion.html xop.subnets": _KEA_OP,
    "v2/_dhcp_reserve.html (3 literal items)": _KEA_OP,
    "v2/_dhcp_reserve.html (8 literal items)": _KEA_OP,
    "v2/_dhcp_reserve.html op.subnets": _KEA_OP,
    "v2/_dhcp_reserve.html p.change": _KEA_OP,
    "v2/_dhcp_reserve.html p.checks": _KEA_OP,
    "v2/_dhcp_reserve.html p.not_done": _KEA_OP,
    "v2/_dhcp_reserve.html p.not_done #2": _KEA_OP,
    "v2/_dhcp_subnet.html (10 literal items)": _KEA_OP,
    "v2/_dhcp_subnet.html (2 literal items)": _KEA_OP,
    "v2/_dhcp_subnet.html p.change": _KEA_OP,
    "v2/_dhcp_subnet.html p.checks": _KEA_OP,
    "v2/_dhcp_subnet.html p.leases": _KEA_OP,
    "v2/_dhcp_subnet.html p.leases #2": _KEA_OP,
    "v2/_dhcp_subnet.html p.survives": _KEA_OP,
    "v2/_dhcp_subnet.html sub.gateway.ra": _KEA_OP,
    "v2/_dhcp_view.html g.conflicts": _KEA,
    "v2/_dhcp_view.html g.exclusions": _KEA,
    "v2/_dhcp_view.html g.families #2": _KEA,
    "v2/_dhcp_view.html g.reservations": _KEA,
    "v2/_dhcp_view.html g.shaped": _KEA,
    "v2/_dhcp_view.html g.subnets": _KEA,
    "v2/_dhcp_view.html gw.ra": _KEA,
    "v2/_dhcp_view.html lc": _KEA,
    "v2/_dhcp_view.html m.elsewhere": _KEA,
    "v2/_dhcp_view.html x.dns.servers": _KEA,
    "v2/_dhcp_view.html x.pd_pools": _KEA,
    "v2/_dhcp_view.html x.pools": _KEA,
    "v2/_diag_inflight.html fl.recent": _NOTHING_RUNS,
    "v2/_diag_inflight.html fl.running": _NOTHING_RUNS,
    "v2/_diag_inflight.html fl.unread": _ERRORS + " (a network whose holds could not be read)",
    "v2/_diag_redaction.html red.canary_leaking_detail": "redaction's leaking handlers: every log handler masks the canary in the test process",
    "v2/_drift_detail.html g.lines": "the drift detail's syslog lines since the golden: no Loki answers the walk, so no line is drawn",
    "v2/_history_ask_logs.html a.refusals": _LOGS_ASK,
    "v2/_history_ask_logs.html a.refusals #2": _LOGS_ASK,
    "v2/_history_ask_logs.html a.rows": _LOGS_ASK,
    "v2/_history_ask_logs.html a.series": _LOGS_ASK,
    "v2/_history_ask_logs.html d['values']['job']": _LOGS_ASK,
    "v2/_history_ask_logs.html extra.items()": _LOGS_ASK,
    "v2/_history_ask_logs.html fixes": _LOGS_ASK,
    "v2/_history_ask_logs.html others": _LOGS_ASK,
    "v2/_history_ask_logs.html q.errors": _LOGS_ASK,
    "v2/_history_ask_logs.html q.roles": _LOGS_ASK,
    "v2/_history_ask_logs.html r.text | masked_parts": _LOGS_ASK,
    "v2/_history_ask_logs.html rest[…]": _LOGS_ASK,
    "v2/_history_ask_logs.html rest[…] #2": _LOGS_ASK,
    "v2/_history_ask_logs.html s.dev": _LOGS_ASK,
    "v2/_history_ask_metrics.html (held.get() or ())": _METRICS_ASK,
    "v2/_history_ask_metrics.html (held.get() or ()) #2": _METRICS_ASK,
    "v2/_history_ask_metrics.html a.refusals": _METRICS_ASK,
    "v2/_history_ask_metrics.html a.refusals #2": _METRICS_ASK,
    "v2/_history_ask_metrics.html a.series": _METRICS_ASK,
    "v2/_history_ask_metrics.html d.labels": _METRICS_ASK,
    "v2/_history_ask_metrics.html extra.items()": _METRICS_ASK,
    "v2/_history_ask_metrics.html fixes": _METRICS_ASK,
    "v2/_history_ask_metrics.html fvals[…]": _METRICS_ASK,
    "v2/_history_ask_metrics.html others": _METRICS_ASK,
    "v2/_history_ask_metrics.html q.aggs": _METRICS_ASK,
    "v2/_history_ask_metrics.html q.compare.items()": _METRICS_ASK,
    "v2/_history_ask_metrics.html q.errors": _METRICS_ASK,
    "v2/_history_ask_metrics.html q.filter_ops.items()": _METRICS_ASK,
    "v2/_history_ask_metrics.html q.notes": _METRICS_ASK,
    "v2/_history_ask_metrics.html q.op_rows": _METRICS_ASK,
    "v2/_history_ask_metrics.html q.pick.rows": _METRICS_ASK,
    "v2/_history_ask_metrics.html q.range_ops.items()": _METRICS_ASK,
    "v2/_history_ask_metrics.html q.saved.rows": _METRICS_ASK,
    "v2/_history_ask_metrics.html q.tops": _METRICS_ASK,
    "v2/_history_ask_metrics.html q.windows.items()": _METRICS_ASK,
    "v2/_history_ask_metrics.html r.args": _METRICS_ASK,
    "v2/_history_ask_metrics.html r.kinds": _METRICS_ASK,
    "v2/_history_ask_metrics.html rest": _METRICS_ASK,
    "v2/_history_ask_metrics.html rest[…]": _METRICS_ASK,
    "v2/_history_ask_metrics.html s.dev": _METRICS_ASK,
    "v2/_history_ask_metrics.html s.f": _METRICS_ASK,
    "v2/_history_ask_metrics.html s['if']": _METRICS_ASK,
    "v2/_history_ask_metrics.html s[…]": _METRICS_ASK,
    "v2/_history_body.html b.baselines": "History's baselines: the lab's repository holds no baseline tag",
    "v2/_history_body.html g": "History's kind filter's summary for exactly one kind chosen: the walk filters by no single kind",
    "v2/_history_body.html idn.others": "History's identity line with the filter on: the walk never turns the not-verified filter on",
    "v2/_history_body.html kind_groups": "History's kind filter's summary for exactly one kind chosen: the walk filters by no single kind",
    "v2/_history_metric.html lq.lines": _LOKI,
    "v2/_history_metric.html m.interfaces": "a metrics question's interface choices: no Prometheus answers the walk with the device's interfaces",
    "v2/_history_metric.html rec.rows": "a metrics question's restart record: no restart is recorded on the walk's store",
    "v2/_history_remote.html remote.dirty_items": _REMOTE,
    "v2/_history_remote.html v.failed": _REMOTE + " (and no Verify is run)",
    "v2/_history_views.html views.views": "History › Saved by your team: no view is saved on the walk's store",
    "v2/_in_progress.html ip.finished": _NOTHING_RUNS,
    "v2/_in_progress.html ip.unread": _ERRORS + " (a network whose holds could not be read)",
    "v2/_install_access.html acc.labels": "Access and identity's service tokens: none is configured on the walk's store",
    "v2/_install_access.html acc.service_ops": "Access and identity's service tokens: none is configured on the walk's store",
    "v2/_install_platforms.html r.problems": "the platform map's problems: the default map's rows are each whole",
    "v2/_install_platforms_preview.html e.changes": _OP + " (a platform map change previewed)",
    "v2/_install_platforms_preview.html e.local": _OP + " (a platform map change previewed)",
    "v2/_install_platforms_preview.html e.unread": _OP + " (a platform map change previewed)",
    "v2/_install_platforms_preview.html pv.testable": _OP + " (a platform map change previewed)",
    "v2/_intent.html iv.profile.excluded.items()": "the Intent tab's profile exclusions: r3 declines no section of the profile",
    "v2/_intent_check.html p.unmodelled": _INTENT_CHECK,
    "v2/_intent_edit.html list": "the intent editor's diff rows (what a deploy sends, how the device departs): the walk opens the editor and types nothing, so no row is drawn",
    "v2/_logs.html g.errors": _LOKI,
    "v2/_logs.html g.lines": _LOKI,
    "v2/_logs_tail.html g.devices": _LOKI,
    "v2/_logs_tail.html g.lines": _LOKI,
    "v2/_logs_tail.html g.severities.items()": _LOKI,
    "v2/_logs_view.html (6 literal items)": _LOKI,
    "v2/_logs_view.html g.ranges.items()": _LOKI,
    "v2/_logs_view.html g.rows": _LOKI,
    "v2/_logs_view.html g.severities.items()": _LOKI,
    "v2/_logs_view.html g.severities.items() #2": _LOKI,
    "v2/_logs_view.html o.errors": _LOKI,
    "v2/_logs_view.html o.lines": _LOKI,
    "v2/_logs_view.html o.mnemonics": _LOKI,
    "v2/_logs_view.html t.series": _LOKI,
    "v2/_logs_view.html t.series #2": _LOKI,
    "v2/_logs_view.html t.xticks": _LOKI,
    "v2/_monitoring.html m.folded.panels": "a dashboard's folded rows: the captured dashboards the lab's Grafana answers with fold none",
    "v2/_neighbours.html n.errors": _ERRORS,
    "v2/_neighbours.html p.rows": "the Neighbours tab's adjacency rows per protocol: no Prometheus or RIP reader answers the walk with one",
    "v2/_netbox.html nb.errors": _ERRORS,
    "v2/_network_source.html pv.would.skipped": _OP + " (the source change's preview, NetBox read with new filters)",
    "v2/_network_source.html s.credential_choices": "the source card's credentials networks: the walk's one network has no other network with its own list",
    "v2/_network_source.html to.filters.items()": _OP + " (the source change's preview)",
    "v2/_network_source.html to.filters.items() #2": _OP + " (the source change's preview)",
    "v2/_onboard_add.html ((done.result or {}).targets or ())": _OP + " (Add device…'s result)",
    "v2/_onboard_add.html f.items()": _OP + " (Add device…'s review)",
    "v2/_onboard_add.html platforms": _OP + " (Add device…'s form, never opened)",
    "v2/_onboard_add.html t.sent.lines": _OP + " (Add device…'s result)",
    "v2/_onboard_discovered.html g.groups": "Onboard › Discovered: the lab stores no discovery reader value, so no device asking is drawn",
    "v2/_onboard_discovered.html g.vendors": "Onboard › Discovered: the lab stores no discovery reader value, so no device asking is drawn",
    "v2/_onboard_discovered.html grp.rows": "Onboard › Discovered: the lab stores no discovery reader value, so no device asking is drawn",
    "v2/_onboard_discovered.html grp.rows #2": "Onboard › Discovered: the lab stores no discovery reader value, so no device asking is drawn",
    "v2/_onboard_discovered.html grp.rows #3": "Onboard › Discovered: the lab stores no discovery reader value, so no device asking is drawn",
    "v2/_onboard_discovered.html r.pools": "Onboard › Discovered: the lab stores no discovery reader value, so no device asking is drawn",
    "v2/_onboard_pending.html causes": "a pending device's likely causes, drawn when Verify is refused: no provider posts Verify for the pending s9",
    "v2/_onboard_pending.html dry.steps": _OP + " (Abandon…'s dry run)",
    "v2/_preview_parts.html ((pv.explain or {}).get() or ())": _PREVIEW_PARTS,
    "v2/_preview_parts.html (t.program.notes or ())": _PREVIEW_PARTS,
    "v2/_preview_parts.html d.lines": _PREVIEW_PARTS,
    "v2/_preview_parts.html n.lines": _PREVIEW_PARTS,
    "v2/_preview_parts.html pv.targets": _PREVIEW_PARTS,
    "v2/_preview_parts.html pv.what_not['items']": _PREVIEW_PARTS,
    "v2/_preview_parts.html r.did_not['items']": _PREVIEW_PARTS,
    "v2/_preview_parts.html t.gates": _PREVIEW_PARTS,
    "v2/_preview_parts.html t.operands": _PREVIEW_PARTS,
    "v2/_preview_parts.html t.program.lines": _PREVIEW_PARTS,
    "v2/_preview_parts.html t.program.lines #2": _PREVIEW_PARTS,
    "v2/_preview_parts.html w.lines": _PREVIEW_PARTS,
    "v2/_profile_op.html q.changes": _OP + " (Propose from the connectors' preview)",
    "v2/_profile_table.html p.rows": "Monitoring › Profile's sections: the lab's network has no committed monitoring profile",
    "v2/_recent.html recent.rows": "Needs attention's recent changes: no deploy or restore receipt is on the walk's store",
    "v2/_records_db_card.html r.steps": _RECORDS + " (and no Test is run)",
    "v2/_records_stores.html done.steps": _RECORDS,
    "v2/_records_stores.html done.switched_back.exported.items()": _RECORDS,
    "v2/_records_stores.html pv.networks": _RECORDS,
    "v2/_records_stores.html pv.steps": _RECORDS,
    "v2/_records_stores.html s.files.items()": _RECORDS,
    "v2/_records_stores.html unparsable": _RECORDS + " (and no store's lines fail to parse)",
    "v2/_rekey.html c.failing": _FAILING,
    "v2/_reload.html p.failing": _OP + " (Reload's preview: its read is started and not finished)",
    "v2/_reload.html p.gates": _OP + " (Reload's preview: its read is started and not finished)",
    "v2/_reload.html p.radius.cut": _OP + " (Reload's preview: its read is started and not finished)",
    "v2/_reload.html r.steps": _OP + " (Reload's run)",
    "v2/_remote_setup.html probed.checks": _REMOTE,
    "v2/_remote_setup.html pub.gated['values']": _REMOTE,
    "v2/_remote_setup.html pub.gated['values'].items()": _REMOTE,
    "v2/_remote_setup.html pub.reported.items()": _REMOTE,
    "v2/_remote_setup.html pub.tags_by_prefix.items()": _REMOTE,
    "v2/_remote_setup.html s.acknowledged['values']": _REMOTE,
    "v2/_restore.html c.authorised": _RESULT,
    "v2/_restore.html c.blocking": _OP + " (Restore's preview, a moment chosen)",
    "v2/_restore.html c.checks": _RESULT,
    "v2/_restore.html c.did_not": _RESULT,
    "v2/_restore.html c.failing": _FAILING,
    "v2/_restore.html c.gates": _OP + " (Restore's preview, a moment chosen)",
    "v2/_restore.html c.notes": _OP + " (Restore's preview, a moment chosen)",
    "v2/_restore.html c.operands": _OP + " (Restore's preview, a moment chosen)",
    "v2/_restore.html c.reasons": _OP + " (Restore's preview, a moment chosen)",
    "v2/_restore.html c.sent": _OP + " (Restore's preview, a moment chosen)",
    "v2/_restore.html c.what_not": _OP + " (Restore's preview, a moment chosen)",
    "v2/_retire.html c.advisories": _OP + " (Retire's preview with an advisory)",
    "v2/_retire.html c.dropped": _RESULT,
    "v2/_retire.html c.failing": _FAILING,
    "v2/_retire.html c.survives #2": _RESULT,
    "v2/_rotate.html c.did_not": _RESULT,
    "v2/_rotate.html c.failing": _FAILING,
    "v2/_rotate.html c.gates": _OP + " (Rotate's preview: its preflight read is not run)",
    "v2/_rotate.html c.operands": _OP + " (Rotate's preview: its preflight read is not run)",
    "v2/_rotate.html c.sent": _OP + " (Rotate's preview: its preflight read is not run)",
    "v2/_rotate.html c.then": _OP + " (Rotate's preview: its preflight read is not run)",
    "v2/_rotate.html c.what_not": _OP + " (Rotate's preview: its preflight read is not run)",
    "v2/_run_stepper.html g.rows": _RUN_GROUPS,
    "v2/_run_stepper.html r.groups": _RUN_GROUPS,
    "v2/_run_stepper.html r.tally": _RUN_GROUPS,
    "v2/_run_stepper.html s.tally": _RUN_GROUPS,
    "v2/_save.html g.devices #3": _SAVE,
    "v2/_save.html s.groups #4": _SAVE,
    "v2/_save.html s.groups #5": _SAVE,
    "v2/_save.html s.startup": _SAVE,
    "v2/_sc_pick.html p.heavy": _SHOW_COMMANDS,
    "v2/_sc_pick.html p.roles": _SHOW_COMMANDS,
    "v2/_sc_pick.html p.sets": _SHOW_COMMANDS,
    "v2/_sc_pick.html p.sets_unreadable": _SHOW_COMMANDS + " (and every set file reads)",
    "v2/_sc_pick.html p.sites": _SHOW_COMMANDS,
    "v2/_seed.html c.checks": _RESULT,
    "v2/_seed.html c.extra": _OP + " (Seed intent's preview naming the device's own lines)",
    "v2/_seed.html c.missing": _OP + " (Seed intent's preview naming the device's own lines)",
    "v2/_seed.html c.not_compared": _OP + " (Seed intent's preview naming the device's own lines)",
    "v2/_seed.html c.unmodeled": _OP + " (Seed intent's preview naming the device's own lines)",
    "v2/_settings_card.html (5 literal items)": _SETTINGS_CARD,
    "v2/_settings_card.html c.inputs": _SETTINGS_CARD,
    "v2/_settings_card.html tested.steps": _SETTINGS_CARD,
    "v2/_settings_card.html w[…]": _SETTINGS_CARD,
    "v2/_settings_mode.html felt": _OP + " (the mode switch's preview)",
    "v2/_settings_mode.html p.gates #2": _OP + " (the mode switch's preview, a gate failing)",
    "v2/_settings_mode.html result.moved": _OP + " (the mode switch's result)",
    "v2/_settings_mode.html result.what": _OP + " (the mode switch's result)",
    "v2/_settings_scope.html s.differs": _ONE_NETWORK,
    "v2/_settings_scope.html s.standalone": _ONE_NETWORK,
    "v2/_settings_scope.html s.unreadable": _ONE_NETWORK,
    "v2/_startup_effect.html e.missing": "a certificate file `dir nvram:` does not list: the persist provider's r1 capture lists every one",
    "v2/_strip.html bad": "the top bar's integrations that are down or refuse, drawn once the integrations reader has probed: the walk's store holds no probe",
    "v2/_template_bindings.html b.form": _LIBRARY,
    "v2/_template_bindings.html b.overrides": _LIBRARY,
    "v2/_template_bindings.html o.choices": _LIBRARY,
    "v2/_template_bindings.html p.choices": _LIBRARY,
    "v2/_template_bindings.html p.choices #2": _LIBRARY,
    "v2/_template_bindings.html pv.moves": _LIBRARY,
    "v2/_template_bindings.html pv.unapproved": _LIBRARY,
    "v2/_template_coverage.html d.extra": _LIBRARY,
    "v2/_template_coverage.html d.missing": _LIBRARY,
    "v2/_template_coverage.html g.devices": _LIBRARY,
    "v2/_template_coverage.html last.groups": _LIBRARY,
    "v2/_template_coverage.html last.groups #2": _LIBRARY,
    "v2/_template_coverage.html last.next[…]": _LIBRARY,
    "v2/_template_coverage.html last.next[…] #2": _LIBRARY,
    "v2/_template_edit.html c.governs": _LIBRARY,
    "v2/_template_edit.html c.revokes": _LIBRARY,
    "v2/_template_op.html b.devices": _LIBRARY,
    "v2/_template_op.html b.diff": _LIBRARY,
    "v2/_template_op.html b.importers": _LIBRARY,
    "v2/_template_op.html b.not_measured": _LIBRARY,
    "v2/_template_op.html c.failed": _LIBRARY,
    "v2/_template_op.html c.not_validated": _LIBRARY,
    "v2/_template_op.html c.results": _LIBRARY,
    "v2/_template_op.html d.gain_lines": _LIBRARY,
    "v2/_template_op.html d.lose_lines": _LIBRARY,
    "v2/_template_op.html op.added": _LIBRARY,
    "v2/_template_op.html r.evidence.failed": _LIBRARY,
    "v2/_template_op.html r.evidence.not_validated": _LIBRARY,
    "v2/_template_op.html r.evidence.validated": _LIBRARY,
    "v2/_template_op.html r.moves": _LIBRARY,
    "v2/_template_op.html r.revoked": _LIBRARY,
    "v2/_template_op.html r.revoked #2": _LIBRARY,
    "v2/_template_op.html r.revoked #3": _LIBRARY,
    "v2/_template_result.html r.device_owned": _LIBRARY,
    "v2/_template_result.html r.extra_lines": _LIBRARY,
    "v2/_template_result.html r.missing_lines": _LIBRARY,
    "v2/_template_result.html r.reordered_lines": _LIBRARY,
    "v2/_template_result.html r.stale_acknowledgements": _LIBRARY,
    "v2/_template_result.html r.unacknowledged": _LIBRARY,
    "v2/_templates_table.html lib.counts.items()": _LIBRARY,
    "v2/_templates_table.html lib.rows": _LIBRARY,
    "v2/_templates_table.html r.bound": _LIBRARY,
    "v2/_templates_table.html r.bound #2": _LIBRARY,
    "v2/_timeline.html (e.marks or ())": "a History event's marks (a baseline, a golden state): no event on the walk's store carries one",
    "v2/_timeline.html h.errors": _ERRORS + " (a History source that could not be read)",
    "v2/_topology_map.html (3 literal items)": _TOPOLOGY,
    "v2/_topology_map.html (3 literal items) #2": _TOPOLOGY,
    "v2/_topology_map.html (3 literal items) #3": _TOPOLOGY,
    "v2/_topology_map.html (4 literal items)": _TOPOLOGY,
    "v2/_topology_map.html (9 literal items)": _TOPOLOGY,
    "v2/_topology_map.html at.groups.apart": _TOPOLOGY,
    "v2/_topology_map.html at.groups.weak": _TOPOLOGY,
    "v2/_topology_map.html at.groups[…]": _TOPOLOGY,
    "v2/_topology_map.html b.hops": _TOPOLOGY,
    "v2/_topology_map.html d.links": _TOPOLOGY,
    "v2/_topology_map.html g.links": _TOPOLOGY,
    "v2/_topology_map.html g.links #2": _TOPOLOGY,
    "v2/_topology_map.html g.links #3": _TOPOLOGY,
    "v2/_topology_map.html g.nodes": _TOPOLOGY,
    "v2/_topology_map.html grp.devices": _TOPOLOGY,
    "v2/_topology_map.html l.chip_list": _TOPOLOGY,
    "v2/_topology_map.html l.readers": _TOPOLOGY,
    "v2/_topology_map.html l.rows": _TOPOLOGY,
    "v2/_topology_map.html n.tags": _TOPOLOGY,
    "v2/_topology_map.html n.tags #2": _TOPOLOGY,
    "v2/_topology_map.html r.lines": _TOPOLOGY,
    "v2/_topology_map.html r.lines #2": _TOPOLOGY,
    "v2/_topology_map.html sl.rows": _TOPOLOGY,
    "v2/_topology_map.html t.errors": _TOPOLOGY,
    "v2/_topology_map.html t.fleet": _TOPOLOGY,
    "v2/_topology_map.html t.list_groups": _TOPOLOGY,
    "v2/_topology_map.html t.matches": _TOPOLOGY,
    "v2/_topology_map.html t.not_read": _TOPOLOGY,
    "v2/_topology_map.html t.path_from": _TOPOLOGY,
    "v2/_topology_map.html t.path_to": _TOPOLOGY,
    "v2/_topology_map.html t.s.items()": _TOPOLOGY,
    "v2/_topology_map.html t.svg.links": _TOPOLOGY,
    "v2/_topology_map.html t.svg.nodes": _TOPOLOGY,
    "v2/_topology_map.html t.toggle_words": _TOPOLOGY,
    "v2/_topology_map.html tr.branches": _TOPOLOGY,
    "v2/_update.html (d.shas or (1 literal items))": _UPDATE,
    "v2/_update.html (o.notes or ())": _UPDATE,
    "v2/_update.html f.after_steps": _UPDATE,
    "v2/_update.html f.beyond": _UPDATE,
    "v2/_update.html f.commits": _UPDATE,
    "v2/_update.html f.host_steps": _UPDATE,
    "v2/_update.html hist.rows[…]": _UPDATE,
    "v2/_update.html owed.said_done": _UPDATE,
    "v2/heartbeat.html plan.not_expected": _HEARTBEAT,
    "v2/heartbeat.html plan.rows": _HEARTBEAT,
    "v2/ip_sla.html g.rows": _IP_SLA,
    "v2/ip_sla.html plan.by_on": _IP_SLA,
    "v2/ip_sla.html plan.skipped": _IP_SLA,
    "v2/not_found.html elsewhere": "the not-found page's other networks holding the name: the walk's installation has one network",
    "v2/show_commands.html runs.rows": "Show commands' recent runs: no run has been made on the walk's store",
}
#: 386 measured 2026-10-18 (C1274), when the list was made: it only shrinks. 382 with C1277's
#: provider (a silenced Grafana alert), which draws a row's devices and its members; 377 with
#: C1232's (Save's no-golden scope), which draws the plan's groups and their devices; 371 with
#: C1403's (DHCP › Leases' Release lease…), which draws the DHCP page's tabs and lease groups;
#: 368 with feature 7's (Change it in words, 2026-10-26), whose draft draws the intent check's
#: diff rows and pending lines.
EMPTY_IN_FIXTURE_CEILING = 368
#: The population and how many of it drew, measured 2026-10-18 (557 and 171): floors, a little
#: under the measurement, so a scan that stopped seeing loops, or a walk that stopped drawing,
#: fails.
LOOPS_FLOOR = 540
DREW_FLOOR = 160


def _flat(table):
    return {f"{route} {key}": reason for route, groups in table.items()
            for keys, reason in groups for key in keys.split()}


@pytest.fixture(scope="module")
def measured():
    return V.measure()


def _forward(measured):
    return {f"{route} {key}" for route, r in measured["routes"].items() for key in r.undrawn}


#: The adapters a card is built through, by route: {route: {python file: (function, ...)}}.
ADAPTERS = {DEPLOY: {"modules/device_actions.py": ("deploy_card", "_one_target",
                                                   "_declare_part", "_deploy_notes")}}


def _upstream(measured):
    """Each upstream preview's key names (identifiers; a key that is not one is data) that the
    route's adapter functions and its templates never read."""
    import app as A
    from tests.payload_render import payload_keys, python_reads

    found = set()
    for route, payloads in measured["upstream"].items():
        reads = set()
        for path, functions in ADAPTERS[route].items():
            for fn in functions:
                reads |= python_reads(path, fn)
        for name in measured["routes"][route].templates:
            reads |= V.template_reads(A.app.jinja_env, name).names
        keys = set()
        for p in payloads:
            keys |= {k for k in payload_keys(p["preview"]) if k.isidentifier()}
        found |= {f"{route} {k}" for k in keys - reads}
    return found


def _unreached(measured):
    """Every template under templates/v2/ that no measured render reaches, itself or through
    what a rendered template extends, includes or imports."""
    import os

    import app as A

    env = A.app.jinja_env
    reached = set()
    for r in measured["routes"].values():
        for name in r.templates:
            reached |= V.template_reads(env, name).templates
    folder = os.path.join(V.ROOT, "templates", "v2")
    every = {f"v2/{f}" for f in os.listdir(folder) if f.endswith(".html")}
    return every - reached, every


class TestThePopulation:
    def test_floors(self, measured):
        """Measured 2026-10-15: 120 pages, 927 fragments, 117 routes, 114 templates rendered."""
        routes = measured["routes"]
        assert measured["pages"] >= 100, measured["pages"]
        assert measured["fragments"] >= 600, measured["fragments"]
        assert len(routes) >= 100, len(routes)
        assert sum(len(r.carried) for r in routes.values()) >= 2000
        assert len({t for r in routes.values() for t in r.templates}) >= 100

    def test_every_template_is_reached_or_declared(self, measured):
        unreached, _every = _unreached(measured)
        new = sorted(unreached - set(UNREACHED))
        assert new == [], (f"no measured request renders these: {new}. Reach them (a link, an "
                           "hx-get, or a provider in tests/v2_context.py), or declare them in "
                           "UNREACHED with the reason.")

    def test_unreached_no_ghosts(self, measured):
        unreached, every = _unreached(measured)
        ghosts = sorted(set(UNREACHED) - unreached)
        assert ghosts == [], f"reached now, or no such template: remove from UNREACHED: {ghosts}"
        assert set(UNREACHED) <= every

    def test_unreached_only_shrinks(self):
        assert len(UNREACHED) == UNREACHED_CEILING


class TestEveryCarriedKeyIsDrawn:
    def test_forward(self, measured):
        new = sorted(_forward(measured) - set(_flat(UNDRAWN)))
        assert new == [], ("carried to a v2 template and drawn by none in its response: "
                           f"{new}. Draw it, or record it in UNDRAWN with the reason.")

    def test_no_ghosts(self, measured):
        ghosts = sorted(set(_flat(UNDRAWN)) - _forward(measured))
        assert ghosts == [], f"drawn now, or no longer carried: remove from UNDRAWN: {ghosts}"

    def test_the_list_only_shrinks(self):
        assert len(_flat(UNDRAWN)) == UNDRAWN_CEILING

    def test_upstream(self, measured):
        new = sorted(_upstream(measured) - set(_flat(UPSTREAM)))
        assert new == [], ("in the preview the card is built from, and read by neither its "
                           f"adapter nor its template: {new}. Draw it, or record it in UPSTREAM.")

    def test_upstream_no_ghosts(self, measured):
        ghosts = sorted(set(_flat(UPSTREAM)) - _upstream(measured))
        assert ghosts == [], f"drawn now: remove from UPSTREAM: {ghosts}"

    def test_upstream_only_shrinks(self):
        assert len(_flat(UPSTREAM)) == UPSTREAM_CEILING

    def test_every_entry_is_reasoned(self):
        for key, reason in (list(_flat(UNDRAWN).items()) + list(_flat(UPSTREAM).items())
                            + list(UNREACHED.items())):
            assert len(reason) >= 30, key


def _loops(measured):
    """``(population, never)``: every `{% for %}` in the v2 templates the measured renders reach
    (V.loops), and the keys of those whose body never ran in the walk or a provider."""
    import app as A

    env = A.app.jinja_env
    reached = set()
    for r in measured["routes"].values():
        for name in r.templates:
            reached |= V.template_reads(env, name).templates
    population = V.loops(env, reached)
    return population, V.never_drew(population, measured["drew"])


class TestTheFixturesReachTheState:
    """C1274: a check is only as good as the state its fixture can reach (the operator's rule,
    2026-09-27; CLAUDE.md's "Test data reaches every column and state a check photographs").
    Today's renderers held it as `EMPTY_IN_FIXTURE` in test_payload_is_rendered.py, which P7-27
    deletes; on v2 the collections are the templates' loops, and a loop whose body never drew
    hid every field its items carry from every check above."""

    def test_every_loop_drew_or_is_declared(self, measured):
        _pop, never = _loops(measured)
        new = sorted(never - set(EMPTY_IN_FIXTURE))
        assert new == [], (f"a v2 loop whose body never drew in the walk or a provider: {new}. "
                           "Reach the state (a provider in tests/v2_context.py), or declare it "
                           "in EMPTY_IN_FIXTURE with the reason.")

    def test_no_ghosts(self, measured):
        population, never = _loops(measured)
        ghosts = sorted(set(EMPTY_IN_FIXTURE) - never)
        assert ghosts == [], f"drew now, or no such loop: remove from EMPTY_IN_FIXTURE: {ghosts}"
        assert set(EMPTY_IN_FIXTURE) <= set(population.values())

    def test_the_list_only_shrinks(self):
        assert len(EMPTY_IN_FIXTURE) == EMPTY_IN_FIXTURE_CEILING
        for key, reason in EMPTY_IN_FIXTURE.items():
            assert len(reason) >= 30, key

    def test_the_population_floor(self, measured):
        """A scan that saw no loop, or saw none draw, would pass both directions."""
        population, never = _loops(measured)
        assert len(population) >= LOOPS_FLOOR, len(population)
        assert len(population) - len(never) >= DREW_FLOOR, len(population) - len(never)
        assert len(set(population.values())) == len(population), "two loops share a key"

    def test_a_planted_template_iterating_what_no_provider_fills_is_found(self, measured,
                                                                          monkeypatch):
        """The control on the real environment and the real measurement: a v2 template no
        measured request renders, holding a loop, joins the population, and its loop is found
        never to have drawn."""
        from jinja2 import ChoiceLoader, DictLoader

        import app as A

        env = A.app.jinja_env
        monkeypatch.setattr(env, "loader", ChoiceLoader([
            DictLoader({"v2/_planted_loop.html": "{% for d in planted_rows %}{{ d.name }}"
                                                 "{% endfor %}"}), env.loader]))
        population, never = _loops(measured)
        reached = {t.split("#")[0] for t in population}
        planted = V.loops(env, reached | {"v2/_planted_loop.html"})
        found = V.never_drew(planted, measured["drew"])
        assert found - never == {"v2/_planted_loop.html planted_rows"}, sorted(found - never)


class TestTheLoopMarks:
    """The marks themselves, on template strings: a loop that drew is recorded, one that did
    not is not, and a mark draws nothing."""

    @staticmethod
    def _env(**templates):
        from jinja2 import DictLoader, Environment

        return Environment(loader=DictLoader(templates))

    def _render(self, ctx, **templates):
        env = self._env(**templates)
        with V.recording_loops(env) as drew:
            html = env.get_template("v2/t.html").render(**ctx)
        return html, V.never_drew(V.loops(env, templates), drew)

    def test_an_empty_collection_is_found_and_a_filled_one_is_not(self):
        html, never = self._render(
            {"full": [{"n": "a"}], "empty": []},
            **{"v2/t.html": "{% for r in full %}{{ r.n }}{% endfor %}"
                            "{% for r in empty %}{{ r.n }}{% endfor %}"})
        assert html == "a" and never == {"v2/t.html empty"}

    def test_two_loops_on_one_line_are_two_loops(self):
        """A position names a loop, never a line: this codebase's templates hold several loops
        on one line, and a line would merge them."""
        _html, never = self._render(
            {"rows": [1]},
            **{"v2/t.html": "{% for r in rows %}{{ r }}{% endfor %}"
                            "{% for r in rows if r > 5 %}{{ r }}{% endfor %}"})
        assert never == {"v2/t.html rows #2"}

    def test_a_branch_never_taken_is_found(self):
        _html, never = self._render(
            {"rows": [1], "show": False},
            **{"v2/t.html": "{% if show %}{% for r in rows %}{{ r }}{% endfor %}{% endif %}"})
        assert never == {"v2/t.html rows"}

    def test_a_loop_in_an_included_macro_counts(self):
        _html, never = self._render(
            {"rows": [1]},
            **{"v2/t.html": "{% from 'v2/m.html' import each %}{{ each(rows) }}",
               "v2/m.html": "{% macro each(xs) %}{% for x in xs %}{{ x }}{% endfor %}"
                            "{% endmacro %}"})
        assert never == set()

    def test_the_marks_leave_no_template_marked(self):
        env = self._env(**{"v2/t.html": "{% for r in rows %}{{ r }}{% endfor %}"})
        with V.recording_loops(env):
            env.get_template("v2/t.html").render(rows=[1])
        assert not hasattr(env, V.LOOP_HOOK)
        assert env.get_template("v2/t.html").render(rows=[2]) == "2"


class TestAnchors:
    """D4 (the deploy wizard dropped `commands`, `dangerous` and `attribution`) and C27 (the
    restore preview never drew the lines to be added), on v2's deploy card."""

    @pytest.mark.parametrize("key", ["sent", "dangerous", "residue", "notes", "what_not",
                                     "confirm", "command_hash",
                                     # C867 (2026-10-16): the plan's attribution, in its note.
                                     "attribution", "intent_commit", "intent_subject", "note",
                                     "from_profile", "from_this_edit", "pre_existing"])
    def test_carried_and_read(self, measured, key):
        import app as A

        route = measured["routes"][DEPLOY]
        assert key in route.carried, f"the fixture's deploy card cannot carry {key!r}"
        reads = set()
        for name in route.templates:
            reads |= V.template_reads(A.app.jinja_env, name).names
        assert key in reads, f"{DEPLOY} carries {key!r} and no template reads it"

    def test_the_fixture_carries_the_attribution(self, measured):
        """The plan's attribution reaches the preview the card is built from, so whether the
        card draws it is measured (UPSTREAM), never assumed from a fixture without one."""
        from tests.payload_render import payload_keys

        keys = set()
        for p in measured["upstream"][DEPLOY]:
            keys |= payload_keys(p["preview"])
        assert {"from_this_edit", "intent_commit", "pre_existing"} <= keys, sorted(keys)


class TestTheCheckCanFail:
    """The parser and the walk, each on a planted case."""

    @staticmethod
    def _env(**templates):
        from jinja2 import DictLoader, Environment

        return Environment(loader=DictLoader(templates))

    def _undrawn(self, ctx, **templates):
        V._READS.clear()
        try:
            return V.carried(ctx, V.template_reads(self._env(**templates), "t.html"))[1]
        finally:
            V._READS.clear()

    def test_a_planted_undrawn_key_is_found(self):
        assert self._undrawn({"c": {"shown": 1, "planted": 2}},
                             **{"t.html": "{{ c.shown }}"}) == {"planted"}

    def test_prose_and_comments_are_not_reads(self):
        """Matched by parsing: a key named in the page's text or a comment is not drawn."""
        assert self._undrawn({"c": {"shown": 1, "planted": 2}},
                             **{"t.html": "planted {# c.planted #}{{ c.shown }}"}) == {"planted"}

    def test_a_read_in_an_included_template_counts(self):
        assert self._undrawn({"c": {"shown": 1, "planted": 2}},
                             **{"t.html": "{{ c.shown }}{% include 'p.html' %}",
                                "p.html": "{{ c.planted }}"}) == set()

    def test_an_undrawn_key_hides_nothing_beneath_it_as_drawn(self):
        """A key never read is one entry; nothing under it is examined (so a key with a common
        name beneath it cannot read as drawn)."""
        assert self._undrawn({"c": {"shown": 1, "planted": {"shown": 2}}},
                             **{"t.html": "{{ c.shown }}"}) == {"planted"}

    def test_keys_of_an_iterated_dict_are_data(self):
        assert self._undrawn({"counts": {"ok": 1, "failed": 2}},
                             **{"t.html": "{% for k, v in counts.items() %}{{ k }}{{ v }}"
                                          "{% endfor %}"}) == set()

    def test_an_alias_iterated_iterates_what_it_names(self):
        """Needs attention's `{% set ops = (r.operands or {}) %}` then `ops.items()`: the
        first build read `operands`' keys as undrawn (a measurement error, found by survey)."""
        assert self._undrawn({"r": {"operands": {"check": 1}}},
                             **{"t.html": "{% set ops = (r.operands or {}) %}"
                                          "{% for k, v in ops.items() %}{{ k }}{{ v }}"
                                          "{% endfor %}"}) == set()

    def test_values_under_data_keys_are_still_examined(self):
        assert self._undrawn({"by": {"r1": {"shown": 1, "planted": 2}}},
                             **{"t.html": "{% for k, v in by.items() %}{{ v.shown }}"
                                          "{% endfor %}"}) == {"planted"}

    def test_a_planted_key_in_a_real_route_is_found(self, monkeypatch):
        """The whole path, signal to verdict, on a real route: the name chip's fragment handed
        one key more than it draws."""
        from flask import template_rendered

        import app as A
        import routes.device_v2 as d

        real = d._who
        monkeypatch.setattr(d, "_who", lambda: dict(real(), planted_undrawn_key="x"))
        recorder = V._Recorder(A.app)
        client = V.RecordingClient(A.app.test_client(), recorder)
        template_rendered.connect(recorder, A.app)
        try:
            r = client.get("/v2/who")
        finally:
            template_rendered.disconnect(recorder, A.app)
        assert r.status_code == 200
        assert "planted_undrawn_key" in recorder.routes["GET /v2/who"].undrawn
