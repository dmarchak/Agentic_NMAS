"""Stage 7 section 10, acceptance criterion 4 on v2: if a v2 route carries it, its page draws it.

`test_payload_is_rendered.py` measures today's (v1) JSON routes against today's JavaScript
renderers; it stays until today's pages go, and shrinks to nothing at P7-27 (the index and the
Bootstrap pages removed). v2 draws on the server: a route hands its template a context, so the
context is the payload and the template is the renderer (P7-04, 2026-10-15).
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
        ("proto", "the neighbour protocol's id: its words are drawn")],
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
        ("rule_words", "the password rule, drawn by the records Replace form"),
        ("store", "a store's internal id; its words and backend are drawn")],
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
    "GET /v2/settings/installation/records/stores": [
        ("store", "a store's internal id; its words and backend are drawn")],
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
UNDRAWN_CEILING = 358

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
    "v2/_onboard_pending.html": _A_STATE + "a device pending onboarding",
    "v2/pending.html": _A_STATE + "a device pending onboarding",
    "v2/retired.html": _A_STATE + "a retired device",
    "v2/_retry.html": _A_STATE + "a deploy blocked by a rolled-back change",
    "v2/_revert.html": _A_STATE + "a change to revert (a rolled-back deploy's way out)",
    "v2/reapply.html": _A_STATE + "a History moment chosen to re-apply",
    "v2/_sc_result.html": _A_JOB + " (a show-commands run)",
    "v2/show_commands_run.html": _A_JOB + " (a show-commands run)",
    "v2/_template_check.html": _A_POST + " (a template edit checked; the lab has no library)",
    "v2/_topology_result.html": _A_JOB + " (a topology read)",
}
UNREACHED_CEILING = 23


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
