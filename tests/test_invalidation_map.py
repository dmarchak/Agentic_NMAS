"""Stage 7.0 (2): an action that changes state leaves the page showing the
new state (NSOT_STAGE7_GUI.md 6b, and its 7.0 acceptance 3-5).

Three panels were measured showing a stale value on the host, each fixed as
its own bug until then: the device list after onboarding's Verify promoted a
device, the Remote card after a commit, and the drift badge after a run. The
rule is now structural:

* every mutating route DECLARES the data it changes, or `Nothing` with a
  reason (`modules/invalidation.py`), and a new one cannot be added without
  a declaration;
* its response carries the declaration;
* panels SUBSCRIBE to keys (`static/js/nmas_invalidation.js`), re-fetch on
  the response, and a failed re-fetch marks the panel stale with the time
  of the value it still shows.

The design test the GUI doc set, answered here: the wrong-and-looks-right
state is an invalidation declared and subscribed to by nothing (the
`next_ts` shape), so the check is a set difference in BOTH directions with a
floor on each, and the client is EXECUTED (duktape), never read.
"""

import os
import re

import dukpy
import pytest

from modules import invalidation as I

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLIENT = os.path.join(ROOT, "static", "js", "nmas_invalidation.js")
GEN = os.path.join(ROOT, "static", "js", "gen")

#: Keys a route declares and no panel subscribes to YET, each with the step
#: whose panel will. It only shrinks: a key that gains a subscriber must
#: leave (no ghosts), and its size is pinned.
NOT_YET_SUBSCRIBED = {
    "active_list": "switching lists reloads the page today; 7.4 (Fleet, Networks)",
    "agent": "the agent tab; 8.4 (the agent returns last)",
    "backups": "backups; 7.5 (Versions)",
    "bulk_ops": "bulk operation records; cut in 7.8",
    "breakglass": ("C539: the key wakes job health's reader, whose `job_health` announcement "
                   "redraws Needs attention; the Credentials page's record card draws its own "
                   "result in place, and subscribes with C538's Finish-the-job checklist"),
    "chat": "the chat panel draws its own stream",
    "credentials": "credential profiles; 7.6 (Source of truth, Credentials)",
    "device_files": "the device page's file list; 7.3 (Device)",
    "files": "transferred files; 7.3 (Device)",
    "lists": "the list selector; 7.4 (Fleet, Networks)",
    "monitoring": "the collectors' cards; 7.3 (Device, Monitoring)",
    "playbooks": "the chat panel's playbooks; 8.2",
    "posture": "the posture panel; 7.7 (Settings)",
    "quick_actions": "the device page's quick actions; 7.3 (Device)",
    "topology": "the topology layout is drawn by its own editor",
    "variables": "the CSV-era variable store; cut in 7.8",
}
NOT_YET_CEILING = 16  # +1 2026-10-06: breakglass (C539), declared so the export, the drill and the intact check wake job health; its own subscriber comes with C538. Before: -1 2026-10-06: templates, heard by the Templates table (C516). Before: -1 2026-10-05: settings, heard by Needs attention's dashboard settings (P.8 step 8c). Before: -2 2026-10-02: device_state and intent, heard by Needs attention and its count. Before: the redesign's landing subscribes to `netbox` (2026-09-30); C148 retired "staging" with extraction's routes (seed intent replaced them); the freshness panel and Needs attention subscribe to `freshness` (7.2 step 15); Needs attention subscribes to approvals, baselines, pending and rolled_back (7.2 step 11); the golden panel subscribes to `goldens` (C102's rename); C102 retired "discovery" with its routes; C104 "history" with the manual commit

_SUB = re.compile(r"^\s*NMAS\.subscribe\(\s*'([a-z_]+)'\s*,\s*'(\w+)'\s*,\s*(\w+)", re.M)


def shipped_subscriptions() -> list:
    """[(key, name, loader, file)] from the shipped scripts, anchored at the
    start of a line so prose quoting the call is not a subscription."""
    out = []
    # The components (static/js/nmas_*.js) subscribe too: Needs attention's
    # panel is one, and a scan of the generated scripts alone could not see
    # it (the payload check's population had the same hole, C82's era).
    comp = os.path.dirname(CLIENT)
    files = ([os.path.join(GEN, f) for f in sorted(os.listdir(GEN))]
             + sorted(os.path.join(comp, f) for f in os.listdir(comp)
                      if f.startswith("nmas_") and f.endswith(".js")))
    for path in files:
        text = open(path, encoding="utf-8").read()
        for m in _SUB.finditer(text):
            out.append((m.group(1), m.group(2), m.group(3), os.path.basename(path)))
    return out


def _defined(name: str) -> bool:
    """Defined in a generated script or a component (the same population
    `shipped_subscriptions` scans)."""
    pat = re.compile(r"(?:^|\s)(?:async\s+)?function\s+%s\s*\(" % re.escape(name), re.M)
    comp = os.path.dirname(CLIENT)
    paths = ([os.path.join(GEN, f) for f in os.listdir(GEN)]
             + [os.path.join(comp, f) for f in os.listdir(comp)
                if f.startswith("nmas_") and f.endswith(".js")])
    return any(pat.search(open(p, encoding="utf-8").read()) for p in paths)


# ── the declarations ────────────────────────────────────────────────────────

class TestEveryMutatingRouteDeclares:
    def test_none_is_undeclared(self):
        import app as A

        assert I.undeclared(A.app) == []

    def test_no_declaration_outlives_its_route(self):
        import app as A

        assert I.ghost_declarations(A.app) == []

    def test_the_population_floor(self):
        """A map read from an app with no routes passes both checks above."""
        import app as A

        assert len(I.mutating_endpoints(A.app)) >= 100
        assert len(I.keys_in_use()) >= 20

    def test_an_undeclared_route_is_found(self):
        """Acceptance 3's control, built in: a mutating route added without
        a declaration is reported, by the same function the suite uses."""
        from flask import Flask

        probe = Flask("probe")

        @probe.route("/probe/change", methods=["POST"])
        def probe_change():
            return "ok"

        @probe.route("/probe/read")
        def probe_read():
            return "ok"

        assert I.undeclared(probe) == ["probe_change"]

    def test_every_key_is_in_the_vocabulary(self):
        assert I.keys_in_use() <= set(I.VOCABULARY)

    def test_no_vocabulary_key_is_a_ghost(self):
        assert set(I.VOCABULARY) <= I.keys_in_use()

    def test_nothing_is_a_reasoned_claim(self):
        nothing = {e: v for e, v in I.DECLARED.items() if isinstance(v, I.Nothing)}
        assert nothing, "no Nothing at all is not the measured state"
        for endpoint, value in nothing.items():
            assert len(value.reason) >= 30, endpoint

    def test_the_three_measured_cases_are_declared(self):
        assert "inventory" in I.keys_for("onboard.verify")
        for endpoint in ("deploy.apply", "golden.capture_apply",
                         "golden.restore_apply"):
            assert "remote" in I.keys_for(endpoint), endpoint
        assert "drift" in I.keys_for("drift_check_sync")


# ── the response carries it ─────────────────────────────────────────────────

@pytest.fixture
def client():
    import app as A

    return A.app.test_client()


class TestTheResponseCarriesIt:
    def test_header_and_body(self, client, monkeypatch):
        import app as A

        monkeypatch.setattr(A, "_save_topo_layout", lambda layout: None)
        r = client.post("/topology/positions", json={"positions": {}})
        assert r.headers.get(I.HEADER) == "topology"
        body = r.get_json()
        assert body["invalidates"] == ["topology"] and body["ok"] is True

    def test_the_response_is_otherwise_unchanged(self, client, monkeypatch):
        """Acceptance 7: nothing about a route changes but the added field."""
        import app as A

        monkeypatch.setattr(A, "_save_topo_layout", lambda layout: None)
        body = client.post("/topology/positions",
                           json={"positions": {"r1": {"x": 1}}}).get_json()
        assert body == {"ok": True, "saved": 1, "invalidates": ["topology"]}

    @pytest.mark.real_identity
    def test_an_identity_refusal_carries_no_header(self, client):
        """The gate refuses before any view runs, so nothing changed, and a
        refusal announcing an invalidation claims a write that did not
        happen (found when the payload check's fixture was refused and its
        refusal carried `invalidates`)."""
        r = client.post("/deploy/apply", json={})
        assert r.status_code == 403
        assert I.HEADER not in r.headers
        assert "invalidates" not in (r.get_json() or {})

    def test_a_nothing_route_carries_no_header(self, client, monkeypatch):
        import routes.templatize as rt

        monkeypatch.setattr(rt, "_repo_for", lambda name: "/nonexistent")
        r = client.post("/templatize/report", json={})
        assert I.HEADER not in r.headers

    def test_a_read_carries_no_header(self, client):
        assert I.HEADER not in client.get("/health").headers

    def test_a_read_of_a_mixed_endpoint_carries_no_header(self, client):
        """`monitoring_config` serves GET and POST from ONE endpoint. The hook
        first keyed on the endpoint alone, so every read of the panel
        announced an invalidation and carried `invalidates` in its body;
        `/health` above could not show it, having no write half."""
        import app as A

        rules = [r for r in A.app.url_map.iter_rules() if r.endpoint == "monitoring_config"]
        assert {"GET", "POST"} <= set().union(*(r.methods for r in rules))
        r = client.get("/monitoring/config")
        assert I.HEADER not in r.headers
        assert "invalidates" not in (r.get_json() or {})


# ── subscriptions, both directions ──────────────────────────────────────────

class TestSubscriptions:
    def test_the_scan_finds_the_three_cases(self):
        """Floor, and the three measured cases wired by name."""
        subs = {(k, loader) for k, _, loader, _ in shipped_subscriptions()}
        assert ("inventory", "refreshDeviceRegions") in subs
        assert ("remote", "loadRemotePanel") in subs
        assert ("drift", "loadDriftStatus") in subs

    def test_every_subscription_names_a_declared_key(self):
        """A panel subscribed to a key no route sends is a panel that never
        refreshes, wearing the code that says it does."""
        bad = sorted({k for k, _, _, _ in shipped_subscriptions()} - I.keys_in_use())
        assert bad == []

    def test_every_loader_exists(self):
        missing = [loader for _, _, loader, _ in shipped_subscriptions()
                   if not _defined(loader)]
        assert missing == []

    def test_every_declared_key_has_a_subscriber_or_a_reason(self):
        subscribed = {k for k, _, _, _ in shipped_subscriptions()}
        orphans = sorted(I.keys_in_use() - subscribed - set(NOT_YET_SUBSCRIBED))
        assert orphans == [], (
            f"declared and subscribed to by nothing: {orphans}. Subscribe a "
            "panel, or record the step that will in NOT_YET_SUBSCRIBED.")

    def test_no_ghost_in_the_waiting_list(self):
        subscribed = {k for k, _, _, _ in shipped_subscriptions()}
        ghosts = sorted(set(NOT_YET_SUBSCRIBED) & subscribed)
        gone = sorted(set(NOT_YET_SUBSCRIBED) - I.keys_in_use())
        assert ghosts == [] and gone == [], (ghosts, gone)

    def test_the_waiting_list_only_shrinks(self):
        assert len(NOT_YET_SUBSCRIBED) == NOT_YET_CEILING


# ── the client, executed ────────────────────────────────────────────────────

HARNESS = r"""
var window = {document: null, console: {error: function () {}}};
var doc = {
  els: {},
  getElementById: function (id) { return this.els[id] || null; }
};
function panel(id) {
  var el = {id: id, inserted: [], removed: 0, marker: null,
    insertAdjacentHTML: function (where, html) { this.inserted.push(html);
      this.marker = {parentNode: this}; },
    querySelector: function (sel) { return this.marker; },
    removeChild: function (m) { this.removed++; this.marker = null; }};
  doc.els[id] = el;
  return el;
}
window.document = doc;
"""


def _run(body, **kwargs):
    client = open(CLIENT, encoding="utf-8").read()
    script = (HARNESS + "(function () {\n" + client.replace(
        "})(typeof window !== 'undefined' ? window : this);",
        "})(window);") + "\n})();\nvar NMAS = window.NMAS;\n" + body)
    return dukpy.evaljs(script, **kwargs)


class TestTheClientExecutes:
    def test_the_shipped_file_ends_as_the_harness_expects(self):
        """The harness binds the IIFE to its stub window by replacing the
        file's last line; if that line changes, every test below would run
        against nothing."""
        assert open(CLIENT, encoding="utf-8").read().rstrip().endswith(
            "})(typeof window !== 'undefined' ? window : this);")

    def test_a_response_naming_a_key_runs_the_subscriber(self, client, monkeypatch):
        """Against a REAL response's header, not a hand-typed one."""
        import app as A

        monkeypatch.setattr(A, "_save_topo_layout", lambda layout: None)
        header = client.post("/topology/positions", json={}).headers[I.HEADER]
        out = _run("""
          var calls = 0;
          NMAS.subscribe('topology', 'layout', function () { calls++; return true; });
          NMAS.subscribe('drift', 'badge', function () { calls += 100; return true; });
          var resp = {marker: 'the response', headers: {get: function (h) {
            return h === 'X-NMAS-Invalidates' ? dukpy['header'] : null; }}};
          var back = NMAS.onResponse(resp);
          [calls, back.marker];
        """, header=header)
        # One subscriber ran, the other did not, and the response passes
        # through unchanged (the fetch wrapper hands it to the caller).
        assert out == [1, "the response"]

    def test_an_htmx_answer_runs_the_subscriber_too(self, client, monkeypatch):
        """C474 (2026-10-05): htmx asks by XHR, which the fetch wrapper never sees, so a v2
        confirm's keys never reached its own page. Its answer's header now reaches the same
        registry, against a REAL response's header."""
        import app as A

        monkeypatch.setattr(A, "_save_topo_layout", lambda layout: None)
        header = client.post("/topology/positions", json={}).headers[I.HEADER]
        out = _run("""
          var calls = 0;
          NMAS.subscribe('topology', 'layout', function () { calls++; return true; });
          NMAS.subscribe('drift', 'badge', function () { calls += 100; return true; });
          NMAS.onHtmxResponse({detail: {xhr: {responseURL: '/topology/positions',
            getResponseHeader: function (h) {
              return h === 'X-NMAS-Invalidates' ? dukpy['header'] : null; }}}});
          NMAS.onHtmxResponse({detail: {}});
          calls;
        """, header=header)
        assert out == 1

    def test_the_htmx_answer_is_heard_where_htmx_announces_it(self):
        src = open(CLIENT, encoding="utf-8").read()
        assert "addEventListener('htmx:afterRequest', onHtmxResponse)" in src

    def test_a_response_with_no_header_runs_nothing(self):
        out = _run("""
          var calls = 0;
          NMAS.subscribe('drift', 'badge', function () { calls++; });
          NMAS.onResponse({headers: {get: function () { return null; }}});
          calls;
        """)
        assert out == 0

    def test_one_panel_on_two_keys_refreshes_once(self):
        out = _run("""
          var calls = 0;
          var f = function () { calls++; return true; };
          NMAS.subscribe('goldens', 'card', f);
          NMAS.subscribe('remote', 'card', f);
          NMAS.invalidate(['goldens', 'remote']);
          calls;
        """)
        assert out == 1

    def test_a_failed_refetch_marks_the_panel_with_the_time_shown(self):
        """Acceptance 5: confidently wrong is worse than behind, so a failure
        says so, with the time of the value still on screen."""
        loaded = 1700000000000
        out = _run("""
          var el = panel('driftPanel');
          NMAS.subscribe('drift', 'badge', function () { return false; },
                         {panel: 'driftPanel', loadedAt: dukpy['loaded']});
          NMAS.invalidate(['drift']);
          var d = new Date(dukpy['loaded']);
          function p(n) { return (n < 10 ? '0' : '') + n; }
          [el.inserted.join(''), p(d.getHours()) + ':' + p(d.getMinutes()) + ':' + p(d.getSeconds())];
        """, loaded=loaded)
        html, shown = out
        assert "Stale" in html and "data-nmas-stale" in html
        assert f"showing the value from {shown}" in html

    def test_a_throwing_loader_is_a_failure_too(self):
        out = _run("""
          var el = panel('p');
          NMAS.subscribe('drift', 'x', function () { throw new Error('boom'); }, {panel: 'p'});
          NMAS.invalidate(['drift']);
          el.inserted.length;
        """)
        assert out == 1

    def test_a_later_success_clears_the_marker(self):
        out = _run("""
          var el = panel('p');
          var ok = false;
          NMAS.subscribe('drift', 'x', function () { return ok; }, {panel: 'p'});
          NMAS.invalidate(['drift']);
          ok = true;
          NMAS.invalidate(['drift']);
          [el.inserted.length, el.removed, el.marker === null];
        """)
        assert out == [1, 1, True]

    def test_the_log_says_what_fired_and_what_it_refreshed(self):
        """Acceptance 6's observable: "no visible change" must be able to tell
        a mechanism that did not fire from one that redrew an identical
        value. The log records the response, its keys, the panels it
        refreshed, and each refresh's outcome."""
        out = _run("""
          NMAS._clock = function () { return 1700000000000; };
          NMAS.subscribe('drift', 'driftBadge', function () { return true; });
          NMAS.subscribe('remote', 'remoteCard', function () { return false; });
          NMAS.onResponse({url: '/drift/check/sync', headers: {get: function () {
            return 'drift,remote'; }}});
          JSON.stringify(NMAS.log());
        """)
        entries = __import__("json").loads(out)
        fired = [e for e in entries if e["event"] == "invalidated"]
        assert fired == [{"event": "invalidated", "url": "/drift/check/sync",
                          "keys": ["drift", "remote"],
                          "panels": ["driftBadge", "remoteCard"],
                          "at": "2023-11-14T22:13:20.000Z"}]
        refreshed = {e["panel"]: e["ok"] for e in entries if e["event"] == "refreshed"}
        assert refreshed == {"driftBadge": True, "remoteCard": False}

    def test_nothing_fired_is_an_empty_log(self):
        """The other half: a response with no header leaves no entry, so an
        empty log after an action means the mechanism did not fire."""
        out = _run("""
          NMAS.subscribe('drift', 'x', function () { return true; });
          NMAS.onResponse({url: '/drift/status', headers: {get: function () { return null; }}});
          NMAS.log().length;
        """)
        assert out == 0

    def test_a_missing_panel_is_said_not_silent(self):
        out = _run("""
          var said = [];
          window.console.error = function (m) { said.push(m); };
          NMAS.subscribe('drift', 'x', function () { return false; }, {panel: 'gone'});
          NMAS.invalidate(['drift']);
          said.join('');
        """)
        assert "gone" in out


# ── the first case: the device list, redrawn from the index's own templates ──

@pytest.fixture
def one_device(monkeypatch):
    import modules.device as D

    dev = {"ip": "192.0.2.40", "hostname": "bp-new", "device_type": "cisco_ios",
           "username": "admin", "password": "", "secret": ""}
    monkeypatch.setattr(D, "load_saved_devices", lambda *a, **k: [dict(dev)])
    return dev


class TestTheDeviceListRedraws:
    def test_the_route_renders_a_new_device(self, client, one_device):
        body = client.get("/devices/regions").get_json()
        assert body["ok"] is True and body["count"] == 1
        assert "bp-new" in body["table_html"] and "192.0.2.40" in body["table_html"]
        assert "1 device(s)" in body["toolbar_html"]

    def test_an_empty_list_renders_its_empty_state(self, client, monkeypatch):
        """The measured case started from a list with NO table at all."""
        import modules.device as D

        monkeypatch.setattr(D, "load_saved_devices", lambda *a, **k: [])
        body = client.get("/devices/regions").get_json()
        assert "No devices in this list yet" in body["table_html"]
        assert "deviceSearch" not in body["toolbar_html"]

    def test_the_index_and_the_route_render_the_same_rows(self, client, one_device,
                                                           monkeypatch):
        """One template, two callers: the redraw is the index's own rows."""
        import app as A

        monkeypatch.setattr(A, "load_saved_devices", lambda *a, **k: [dict(one_device)])
        page = client.get("/").get_data(as_text=True)
        body = client.get("/devices/regions").get_json()
        rows = re.findall(r'<tr data-ip="[^"]+"[^>]*>', body["table_html"])
        assert rows and all(row in page for row in rows)

    def test_the_shipped_redraw_applies_the_real_payload(self, client, one_device):
        """`applyDeviceRegions`, executed against what the route returns."""
        payload = client.get("/devices/regions").get_json()
        src = open(os.path.join(GEN, "index.1.js"), encoding="utf-8").read()
        start = src.index("function applyDeviceRegions(")
        end = src.index("async function refreshDeviceRegions(")
        out = dukpy.evaljs(src[start:end] + """
          var els = {deviceToolbarRegion: {innerHTML: 'old'},
                     deviceTableRegion: {innerHTML: 'No devices in this list yet'},
                     deviceListSelect: {options: [
                       {value: dukpy['list'], textContent: 'x (0 devices)'}]}};
          var doc = {getElementById: function (id) { return els[id] || null; }};
          var ok = applyDeviceRegions(dukpy['payload'], doc);
          [ok, els.deviceTableRegion.innerHTML, els.deviceListSelect.options[0].textContent];
        """, payload=payload, list=payload["list"])
        ok, table, label = out
        assert ok is True and "bp-new" in table
        assert label == f"{payload['list']} (1 devices)"

    def test_a_failed_payload_is_a_failure_not_an_empty_list(self):
        src = open(os.path.join(GEN, "index.1.js"), encoding="utf-8").read()
        start = src.index("function applyDeviceRegions(")
        end = src.index("async function refreshDeviceRegions(")
        out = dukpy.evaljs(src[start:end] + """
          var els = {deviceToolbarRegion: {innerHTML: 'kept'}, deviceTableRegion: {innerHTML: 'kept'}};
          var doc = {getElementById: function (id) { return els[id] || null; }};
          [applyDeviceRegions({ok: false, error: 'x'}, doc), els.deviceTableRegion.innerHTML];
        """)
        assert out == [False, "kept"]
