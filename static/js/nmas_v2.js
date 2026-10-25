/* NMAS redesign frame (the spike, NSOT_GUI_BRIEF 9b): Alpine components for
 * the menus and the phone drawer, the jump box, ages drawn locally, and the
 * live channel wired to htmx. Alpine's CSP build evaluates no expressions, so
 * every directive names a property or a method registered here.
 *
 * Live updates: a background reader ANNOUNCES its data key over the socket
 * (C58, nmas_invalidation.js). Each key a fragment draws becomes an htmx
 * event on <body> (`nmas:<key>`), and the fragment re-fetches itself with
 * `hx-trigger="nmas:<key> from:body"`. No polling: every change has a sender.
 * ES5 with pure helpers, executed in duktape by tests/test_device_v2.py.
 */
(function (root) {
  'use strict';

  /* The data keys a v2 fragment can listen for (modules/invalidation.py's
     vocabulary; the readers that announce them). */
  var KEYS = ['reachability', 'integration_health', 'alerts', 'drift', 'dashboards', 'reads',
              'job_health', 'ci_verdict', 'app_version', 'netbox', 'remote', 'baselines',
              // A batch deploy run as a job (P.9 d2), and the goldens it commits.
              'deploy_job', 'goldens',
              // C38's reader: the routing adjacencies intent implies.
              'adjacencies',
              // A device restart, planned or not (modules/restarts.py).
              'restarts',
              // A person acknowledged an event row (modules/acknowledgements.py).
              'acknowledgements',
              // A device's SSH host key kept, refused or re-keyed (modules/host_keys.py, C906).
              'host_keys',
              // What else moves a Needs attention row (attention.SOURCE_KEYS).
              'approvals', 'device_state', 'intent', 'inventory', 'pending', 'rolled_back',
              // A capture preview's reads finished (modules/nsot/capture_job.py): the
              // device page's Capture card reads its preview (7.3).
              'capture_preview',
              // An operation the app ran released a device: a card refused because it was
              // held reads again (modules/nsot/device_ops.py); and a rotation's job finished.
              'device_holds', 'rotation', 'credential_health',
              // Where each record store is and whether a moved one still matches its files
              // (the records-check reader): the Records database card's stores.
              'records',
              // A Tier 2 run finished (modules/nsot/privileged.py): its card reads its record.
              'privileged',
              // A Reload's preview or run finished (modules/nsot/reload_op.py): its card
              // reads it by id (P.14, cutover blocker 6).
              'reload',
              // Coverage's not-reporting cells: when each device's data last arrived.
              'coverage_reporting',
              // A held device's operation reached its next step: a running card redraws its
              // stepper (C370).
              'device_progress',
              // A template approved or revoked anywhere: the Templates table re-reads (C516).
              'templates',
              // A credential profile saved or deleted: Credentials › Profiles re-reads.
              'credentials',
              // The topology reader's graph moved, or an island was declared (P.11).
              'topology',
              // The fleet's syslog counts moved (the Logs view, C652).
              'logs',
              // The network's Kea read again: subnets, reservations, leases (C529).
              'dhcp',
              // A History › Query view saved, pinned or removed (C667).
              'saved_views',
              // A device asked anew, was picked or went quiet on the ZTP segment (board L).
              'ztp_discovery',
              // A Topology path trace read a hop, or finished (board D, C693).
              'path_trace',
              // A log line revealed, its record written: History's timeline re-reads (C818).
              'reveals',
              // An AI call recorded (Phase 8): History's timeline re-reads.
              'ai_calls',
              // A network created or deleted (Settings): the top bar's network picker and
              // Settings' scope bar draw the list again (P7-05).
              'lists',
              // A person chose a network, or the one they were on was deleted: the picker
              // marks which is theirs again (P7-05).
              'active_list',
              // An access or identity decision recorded (Record this decision): Settings ›
              // Installation › Access and identity, at rest, reads again (P7-05).
              'posture',
              // A break-glass export, its intact check or a drill logged: Credentials' record
              // card reads the log again at once; job health's judgement follows (P7-05).
              'breakglass',
              // A job started or finished, or a result was opened (C537): the top bar's In
              // progress chip reads again.
              'in_progress',
              // A console survey or kick-start ended (out-of-band ZTP, O6b): its card reads
              // its record by id.
              'console_ztp',
              // A console-server port record or key saved, or a console server re-keyed (O8):
              // Settings › Installation › Console servers reads again.
              'console_servers'];

  /* PURE: the Acknowledge button's words, busy on itself. */
  function ackLabel(busy) { return busy ? 'Acknowledging…' : 'Acknowledge'; }

  /* PURE: a refused acknowledgement in words, from the status and the body. */
  function ackRefusal(status, body) {
    return 'Not acknowledged: ' + ((body && body.error) || ('HTTP ' + status));
  }

  /* PURE: what an answer does to the Acknowledge form (C533): a refusal says why, frees the
     button and keeps the form open; one recorded and NOT hiding its row (a value above the
     band) says so, with both numbers, and frees the button. One recorded that hides its row
     says so AT ONCE, closes the form and frees the button (`done`: no Acknowledge… and no
     Cancel are offered again); the row leaves at the list's next redraw. It once stayed busy
     waiting for that redraw, which the hold (C459) kept back because the sent reason was still
     shown: on the host, 2026-10-19, four rows sat on "Acknowledging…" for minutes after their
     acknowledgements were recorded. Never busy once an answer is in. */
  function ackAnswer(status, body) {
    if (status !== 200 || !body || !body.ok) {
      return {busy: false, isOpen: true, said: ackRefusal(status, body), note: ''};
    }
    if (body.hides_now === false) {
      return {busy: false, isOpen: false, said: '', note: body.words || 'Recorded; the row stays.'};
    }
    return {busy: false, isOpen: false, said: '', note: 'Acknowledged.', done: true};
  }

  /* The bound on an acknowledgement's answer: the POST answered in under 50 ms on the host
     (its app log, 2026-10-19, 20:36:40 to 20:37:01, four acknowledgements) and in 0.7 to
     1.6 ms in the app itself (ten recorded through the test client, 2026-10-19); the slowest
     step a person waited on that evening was the reader's announcement, about 2 s after the
     answer. 2.5 x that 2 s, rounded up: 6 s, past which the request is abandoned and the form
     says so. */
  var ACK_BOUND_MS = 6000;

  /* PURE: the Acknowledge form when no answer came within *ms*: the button freed and the
     form closed (its reason no longer holds the list's redraw), saying honestly that whether
     it was recorded is not known and that the list's next redraw shows it. */
  function ackNoAnswer(ms) {
    return {busy: false, isOpen: false, note: '',
            said: 'No answer within ' + Math.round(ms / 1000) + ' s, so whether it was ' +
                  'recorded is not known: the list\'s next redraw shows it (the row leaves ' +
                  'if it was, and stays with Acknowledge… if not).'};
  }

  /* PURE: an age in words, from two times in milliseconds. */
  function ageWords(thenMs, nowMs) {
    if (thenMs !== thenMs || thenMs === null) return '';
    var s = Math.round((nowMs - thenMs) / 1000);
    if (s < 0) s = 0;
    if (s < 45) return 'just now';
    if (s < 90) return '1 min ago';
    var m = Math.round(s / 60);
    if (m < 60) return m + ' min ago';
    var h = Math.round(m / 60);
    if (h < 36) return h + ' h ago';
    return Math.round(h / 24) + ' d ago';
  }

  /* PURE: the words for the live channel's state (the dot beside them is CSS). */
  function liveWords(state) {
    return {connected: 'Live', disconnected: 'Live updates stopped', silent: 'Live updates silent',
            failed: 'Live updates could not connect'}[state] || 'Connecting';
  }

  /* PURE: where the jump box goes, from its base path, what was typed, and the query its form's
     address carries (the page's network, written in by routes/page_network: a device opened
     from a page about one network is that network's device, W2's A1). */
  function jumpTarget(base, typed, query) {
    var name = String(typed || '').replace(/^\s+|\s+$/g, '');
    return name ? base + encodeURIComponent(name) + (query || '') : '';
  }

  /* The query of a form's drawn address ('?list=…'), or ''. */
  function addressQuery(form) {
    var action = (form && form.getAttribute && form.getAttribute('action')) || '';
    var at = action.indexOf('?');
    return at < 0 ? '' : action.slice(at);
  }

  /* A LIVE REDRAW NEVER REPLACES WHAT A PERSON IS EDITING (C459, the operator, 2026-10-05: on
     Needs attention, each refresh closed the open Acknowledge form and took the cursor). A
     region about to be swapped that holds an element being edited (a focused text field, a
     text field with unsent text, or anything marked `data-editing="true"`, as an open
     form is) is HELD: the swap is skipped, the element says newer data is waiting, and the
     region is asked again once the editing ends (the form sent, cancelled or emptied). The
     whole region holds, not just the row: moving a live Alpine component out of a swap
     re-creates it, which is the very thing that closed the form. */
  var TEXTY = /^(text|search|email|url|tel|password|number|)$/i;

  function isEditing(el) {
    if (!el || el.disabled) return false;
    if (el.getAttribute && el.getAttribute('data-editing') === 'true') return true;
    // A component that says it is NOT being edited (`data-editing="false"`: its form answered
    // or closed) holds nothing, whatever its fields still show: a form that has been answered
    // never keeps back the redraw that would show its result (the operator, 2026-10-19).
    if (el.closest && el.closest('[data-editing="false"]')) return false;
    var tag = (el.tagName || '').toLowerCase();
    if (tag === 'textarea' || (tag === 'input' && TEXTY.test(el.type || ''))) {
      if (el === root.document.activeElement) return true;
      // Unsent text counts only while the field is shown: a form closed by Cancel keeps its
      // text hidden, and holding a region for it would never let the redraw happen.
      return el.offsetParent !== null && (el.value || '') !== (el.defaultValue || '');
    }
    return false;
  }

  /* PURE over the DOM: the first element inside *region* a person is editing, or null. */
  function editingIn(region) {
    if (!region || !region.querySelectorAll) return null;
    var marked = region.querySelector('[data-editing="true"]');
    if (marked) return marked;
    var fields = region.querySelectorAll('input, textarea');
    for (var i = 0; i < fields.length; i++) if (isEditing(fields[i])) return fields[i];
    return null;
  }

  var HELD_WORDS = 'Newer data is waiting; it shows when you send or cancel.';

  /* Was this swap caused by a LIVE update (a reader's or a job's announcement, `nmas:<key>`)?
     Only those are held: a person's own submission swaps the region it was sent from,
     typed reason and all, because that answer is what they asked for. */
  function isLiveUpdate(d) {
    var ev = d && d.requestConfig && d.requestConfig.triggeringEvent;
    return !!(ev && typeof ev.type === 'string' && ev.type.indexOf('nmas:') === 0);
  }

  function holdWhileEditing(e) {
    var region = e.detail && e.detail.target;
    if (!e.detail || !e.detail.shouldSwap || !region || !isLiveUpdate(e.detail)) return;
    var editing = editingIn(region);
    if (!editing) return;
    e.detail.shouldSwap = false;
    region.setAttribute('data-held', '1');
    // The note stays INSIDE the region, beside the field: its form or Alpine component when
    // that is the region's own, else the field's parent. `<body>` carries x-data (the frame),
    // so a field with no nearer component put the note on the page grid as a new column
    // (Topology's Find box, the operator 2026-10-12).
    var unit = editing.closest && editing.closest('form, [x-data]');
    if (!unit || unit === region || !region.contains(unit)) unit = editing.parentNode || region;
    if (!unit.querySelector('.held-note')) {
      var note = root.document.createElement('span');
      note.className = 'held-note';
      note.setAttribute('role', 'status');
      note.textContent = HELD_WORDS;
      unit.appendChild(note);
    }
  }

  /* PURE over the DOM: the keys of the open `<details data-keep="…">` inside *region*. A
     details a person opened is their state, as a ticked box is (C472). */
  function openKeys(region) {
    var out = [];
    if (!region || !region.querySelectorAll) return out;
    var open = region.querySelectorAll('details[data-keep][open]');
    for (var i = 0; i < open.length; i++) out.push(open[i].getAttribute('data-keep'));
    return out;
  }

  /* Before ANY swap that replaces a region by its id (a live redraw, a person's own request,
     or the redraw a released hold asks for), note what was open; after it settles, open the
     same keys again in the region that replaced it. A key the new region no longer draws is
     simply not there. */
  var keptOpen = {};
  function rememberOpen(e) {
    var region = e.detail && e.detail.target;
    if (!region || !region.id) return;
    var keys = openKeys(region);
    if (keys.length) keptOpen[region.id] = keys;
  }
  function reopenKept() {
    for (var id in keptOpen) {
      if (!Object.prototype.hasOwnProperty.call(keptOpen, id)) continue;
      var region = root.document.getElementById(id);
      var keys = keptOpen[id];
      delete keptOpen[id];
      if (!region) continue;
      var all = region.querySelectorAll('details[data-keep]');
      for (var i = 0; i < all.length; i++) {
        if (keys.indexOf(all[i].getAttribute('data-keep')) >= 0) all[i].open = true;
      }
    }
  }

  /* Once a held region is no longer being edited, ask for it again: the redraw it skipped. */
  function releaseHeld() {
    var held = root.document.querySelectorAll('[data-held="1"]');
    for (var i = 0; i < held.length; i++) {
      var region = held[i];
      if (editingIn(region)) continue;
      region.removeAttribute('data-held');
      var notes = region.querySelectorAll('.held-note');
      for (var j = 0; j < notes.length; j++) notes[j].parentNode.removeChild(notes[j]);
      var url = region.getAttribute('hx-get');
      if (url && root.htmx) {
        root.htmx.ajax('GET', url, {target: region, swap: region.getAttribute('hx-swap') || 'outerHTML'});
      }
    }
  }

  function drawAges(scope) {
    var list = (scope || root.document).querySelectorAll('time[data-age]');
    var now = Date.now();
    for (var i = 0; i < list.length; i++) {
      var t = Date.parse(list[i].getAttribute('data-age'));
      if (t === t) list[i].textContent = ageWords(t, now);
    }
  }

  function drawLive() {
    var dot = root.document.getElementById('nmas-live');
    if (!dot || !root.NMAS || !root.NMAS.live) return;
    var st = root.NMAS.live().state || 'not_connected';
    if (dot.getAttribute('data-live') === st) return;
    dot.setAttribute('data-live', st);
    var word = dot.querySelector('.live-word');
    if (word) word.textContent = liveWords(st);
    dot.setAttribute('title', liveWords(st) + (st === 'connected' ? ': panels update as their readers announce'
      : ': a background read that finishes now is not shown until the panel is next loaded'));
  }

  /* An announcement becomes an htmx event on <body>; the fragment that draws
     that key names it in its hx-trigger. One loader per key, written out, so
     the subscription scan (tests/test_invalidation_map.py) reads each one. */
  var relayedAt = {}, askedAt = {};
  function relay(key) {
    relayedAt[key] = Date.now();
    if (root.htmx) root.htmx.trigger(root.document.body, 'nmas:' + key);
  }

  /* PURE: the keys a fragment listens for (its hx-trigger) that were relayed AFTER its
     request began, so the answer it just drew may predate them. Measured 2026-10-02 in a
     real browser: an announcement relayed 18 ms after the sidebar's count began loading
     was dropped (a fragment's listener is not attached while it is fetching and settling),
     and the count stayed wrong until the next one. */
  function missedKeys(trigger, relayed, asked) {
    var out = [], re = /nmas:([a-z_]+) from:body/g, m;
    while ((m = re.exec(trigger || '')) !== null) {
      // Strictly later: a relay starts its own request in the same millisecond.
      if (relayed[m[1]] !== undefined && relayed[m[1]] > asked) out.push(m[1]);
    }
    return out;
  }

  function noteAsked(e) {
    var el = e.detail && e.detail.elt, target = e.detail && e.detail.target, now = Date.now();
    if (el && el.id) askedAt[el.id] = now;
    // And under the TARGET's id: a button that swaps a fragment into another element (a
    // card's confirm into the card) begins the request the new fragment answers; a job
    // announcing while it is in flight was lost (2026-10-03, the rotate card in a real browser).
    if (target && target.id && target !== el) askedAt[target.id] = now;
  }

  function catchUpMissed(e) {
    var el = e.detail && e.detail.elt;
    if (!el || !el.id || askedAt[el.id] === undefined) return;
    var asked = askedAt[el.id];
    delete askedAt[el.id];
    var now = root.document.getElementById(el.id);
    var missed = missedKeys(now ? now.getAttribute('hx-trigger') : '', relayedAt, asked);
    if (missed.length) relay(missed[0]);       // one re-read covers every key it listens to
  }
  function relayReachability() { relay('reachability'); }
  function relayIntegrationHealth() { relay('integration_health'); }
  function relayCredentialHealth() { relay('credential_health'); }
  function relayRecords() { relay('records'); }
  function relayCoverageReporting() { relay('coverage_reporting'); }
  function relayAlerts() { relay('alerts'); }
  function relayDrift() { relay('drift'); }
  function relayReads() { relay('reads'); }
  function relayDashboards() { relay('dashboards'); }
  function relaySettings() { relay('settings'); }
  function relayJobHealth() { relay('job_health'); }
  function relayCiVerdict() { relay('ci_verdict'); }
  function relayAppVersion() { relay('app_version'); }
  function relayNetbox() { relay('netbox'); }
  function relayRemote() { relay('remote'); }
  function relayBaselines() { relay('baselines'); }
  function relayDeployJob() { relay('deploy_job'); }
  function relayGoldens() { relay('goldens'); }
  function relayAdjacencies() { relay('adjacencies'); }
  function relayRestarts() { relay('restarts'); }
  function relayAcknowledgements() { relay('acknowledgements'); }
  function relayHostKeys() { relay('host_keys'); }
  // What else moves a Needs attention row (attention.SOURCE_KEYS, the operator,
  // 2026-10-02): the page and the sidebar's count could not hear these.
  function relayApprovals() { relay('approvals'); }
  function relayDeviceState() { relay('device_state'); }
  function relayIntent() { relay('intent'); }
  function relayInventory() { relay('inventory'); }
  function relayPending() { relay('pending'); }
  function relayRolledBack() { relay('rolled_back'); }
  function relayCapturePreview() { relay('capture_preview'); }
  function relayDeviceHolds() { relay('device_holds'); }
  function relayRotation() { relay('rotation'); }
  function relayPrivileged() { relay('privileged'); }
  function relayReload() { relay('reload'); }
  function relayPersistRead() { relay('persist_read'); }
  function relayDeviceProgress() { relay('device_progress'); }
  function relayTemplates() { relay('templates'); }
  function relaySave() { relay('save'); }
  function relayCredentials() { relay('credentials'); }
  function relayTopology() { relay('topology'); }
  function relayLogs() { relay('logs'); }
  function relayDhcp() { relay('dhcp'); }
  function relaySavedViews() { relay('saved_views'); }
  function relayDiscovery() { relay('ztp_discovery'); }
  function relayPathTrace() { relay('path_trace'); }
  function relayReveals() { relay('reveals'); }
  function relayAiCalls() { relay('ai_calls'); }
  function relayLists() { relay('lists'); }
  function relayActiveList() { relay('active_list'); }
  function relayPosture() { relay('posture'); }
  function relayBreakglass() { relay('breakglass'); }
  function relayInProgress() { relay('in_progress'); }
  function relayConsoleZtp() { relay('console_ztp'); }
  function relayConsoleServers() { relay('console_servers'); }

  /* PURE: whether the sidebar's count may be out of date, and why, from the live channel's
     state and the moment its oldest source passes its promise (data-stale-at). '' when it
     is current. */
  function badgeDoubt(liveState, staleAtMs, nowMs) {
    if (liveState && liveState !== 'connected') {
      return 'May be out of date: ' + liveWords(liveState).toLowerCase()
        + '. It catches up when they reconnect.';
    }
    if (staleAtMs === staleAtMs && staleAtMs !== null && nowMs > staleAtMs) {
      return 'May be out of date: a source it counts has not been read within its promise.';
    }
    return '';
  }

  /* The sidebar's count (on every v2 page): marked while it may be out of date, and read
     again at the moment a row clears by time (data-next-change-at), once per moment.
     Run on the frame's one-second tick; it asks nothing unless a row is due. */
  function drawBadge() {
    var el = root.document.getElementById('attention-count');
    if (!el) return;
    var now = Date.now();
    var stale = Date.parse(el.getAttribute('data-stale-at') || '');
    var live = root.NMAS && root.NMAS.live ? (root.NMAS.live().state || '') : '';
    var doubt = badgeDoubt(live, stale === stale ? stale : null, now);
    if (doubt) {
      el.classList.add('count-maybe');
      if (!el.hasAttribute('data-title')) el.setAttribute('data-title', el.getAttribute('title') || '');
      el.setAttribute('title', doubt);
    } else if (el.classList.contains('count-maybe')) {
      el.classList.remove('count-maybe');
      el.setAttribute('title', el.getAttribute('data-title') || '');
      el.removeAttribute('data-title');
    }
    var due = Date.parse(el.getAttribute('data-next-change-at') || '');
    if (due === due && now >= due && el.getAttribute('data-due-fired') !== String(due)) {
      el.setAttribute('data-due-fired', String(due));
      if (root.htmx) root.htmx.trigger(root.document.body, 'nmas:attention_due');
    }
  }

  function wireAnnouncements() {
    var NMAS = root.NMAS;
    if (!NMAS || !NMAS.subscribe) return;
    NMAS.subscribe('reachability', 'v2Reachability', relayReachability);
    NMAS.subscribe('integration_health', 'v2IntegrationHealth', relayIntegrationHealth);
    NMAS.subscribe('credential_health', 'v2CredentialHealth', relayCredentialHealth);
    NMAS.subscribe('records', 'v2Records', relayRecords);
    NMAS.subscribe('coverage_reporting', 'v2CoverageReporting', relayCoverageReporting);
    NMAS.subscribe('alerts', 'v2Alerts', relayAlerts);
    NMAS.subscribe('drift', 'v2Drift', relayDrift);
    NMAS.subscribe('reads', 'v2Reads', relayReads);
    NMAS.subscribe('dashboards', 'v2Dashboards', relayDashboards);
    NMAS.subscribe('settings', 'v2Settings', relaySettings);
    NMAS.subscribe('job_health', 'v2JobHealth', relayJobHealth);
    NMAS.subscribe('ci_verdict', 'v2CiVerdict', relayCiVerdict);
    NMAS.subscribe('app_version', 'v2AppVersion', relayAppVersion);
    NMAS.subscribe('netbox', 'v2Netbox', relayNetbox);
    NMAS.subscribe('remote', 'v2Remote', relayRemote);
    NMAS.subscribe('baselines', 'v2Baselines', relayBaselines);
    NMAS.subscribe('deploy_job', 'v2DeployJob', relayDeployJob);
    NMAS.subscribe('goldens', 'v2Goldens', relayGoldens);
    NMAS.subscribe('adjacencies', 'v2Adjacencies', relayAdjacencies);
    NMAS.subscribe('restarts', 'v2Restarts', relayRestarts);
    NMAS.subscribe('acknowledgements', 'v2Acknowledgements', relayAcknowledgements);
    NMAS.subscribe('host_keys', 'v2HostKeys', relayHostKeys);
    NMAS.subscribe('approvals', 'v2Approvals', relayApprovals);
    NMAS.subscribe('device_state', 'v2DeviceState', relayDeviceState);
    NMAS.subscribe('intent', 'v2Intent', relayIntent);
    NMAS.subscribe('inventory', 'v2Inventory', relayInventory);
    NMAS.subscribe('pending', 'v2Pending', relayPending);
    NMAS.subscribe('rolled_back', 'v2RolledBack', relayRolledBack);
    NMAS.subscribe('capture_preview', 'v2CapturePreview', relayCapturePreview);
    NMAS.subscribe('device_holds', 'v2DeviceHolds', relayDeviceHolds);
    NMAS.subscribe('rotation', 'v2Rotation', relayRotation);
    NMAS.subscribe('privileged', 'v2Privileged', relayPrivileged);
    NMAS.subscribe('reload', 'v2Reload', relayReload);
    NMAS.subscribe('persist_read', 'v2PersistRead', relayPersistRead);
    NMAS.subscribe('device_progress', 'v2DeviceProgress', relayDeviceProgress);
    NMAS.subscribe('templates', 'v2Templates', relayTemplates);
    NMAS.subscribe('save', 'v2Save', relaySave);
    NMAS.subscribe('credentials', 'v2Credentials', relayCredentials);
    NMAS.subscribe('topology', 'v2Topology', relayTopology);
    NMAS.subscribe('logs', 'v2Logs', relayLogs);
    NMAS.subscribe('dhcp', 'v2Dhcp', relayDhcp);
    NMAS.subscribe('saved_views', 'v2SavedViews', relaySavedViews);
    NMAS.subscribe('ztp_discovery', 'v2Discovery', relayDiscovery);
    NMAS.subscribe('path_trace', 'v2PathTrace', relayPathTrace);
    NMAS.subscribe('reveals', 'v2Reveals', relayReveals);
    NMAS.subscribe('ai_calls', 'v2AiCalls', relayAiCalls);
    NMAS.subscribe('lists', 'v2Lists', relayLists);
    NMAS.subscribe('active_list', 'v2ActiveList', relayActiveList);
    NMAS.subscribe('posture', 'v2Posture', relayPosture);
    NMAS.subscribe('breakglass', 'v2Breakglass', relayBreakglass);
    NMAS.subscribe('in_progress', 'v2InProgress', relayInProgress);
    NMAS.subscribe('console_ztp', 'v2ConsoleZtp', relayConsoleZtp);
    NMAS.subscribe('console_servers', 'v2ConsoleServers', relayConsoleServers);
  }

  /* A form's submit button is busy on itself (C1023, the operator's B1 on walk W2). htmx
     reads `hx-disabled-elt`, and puts its `htmx-request` class, on the element that ISSUES the
     request: for a <form hx-post> that is the form, so the button's own
     `hx-disabled-elt="this"` was never read and its `op-busy` words never showed. NetBox's
     Import looked dead, and a second run was started. The button that submitted the form is
     held as htmx holds a button that posts itself: disabled, `htmx-request` and aria-busy,
     from the send until the answer has been drawn (htmx fires afterRequest after the swap,
     and on an error, an abort or a timeout). No timer. Only a button declaring
     `hx-disabled-elt="this"` is held; tests/test_v2_busy_on_itself.py requires it of every
     button that posts. */
  function declaresBusy(el) {
    return !!(el && el.tagName === 'BUTTON' && el.getAttribute('hx-disabled-elt') === 'this');
  }
  function submitterOf(form, evt) {
    if (!form || form.tagName !== 'FORM') return null;
    var s = evt && evt.submitter;
    if (s) return declaresBusy(s) ? s : null;
    // No submitter (a script submitted the form): its one declaring submit button, or none
    // when two could have sent it, rather than a guess.
    var found = null, els = form.elements || [];
    for (var i = 0; i < els.length; i++) {
      if (!declaresBusy(els[i]) || (els[i].type && els[i].type !== 'submit')) continue;
      if (found) return null;
      found = els[i];
    }
    return found;
  }
  var heldSubmitters = [];
  function holdSubmitter(e) {
    var d = (e && e.detail) || {};
    var b = submitterOf(d.elt, (d.requestConfig || {}).triggeringEvent);
    if (!b || b.disabled) return;
    b.disabled = true;
    b.classList.add('htmx-request');
    b.setAttribute('aria-busy', 'true');
    heldSubmitters.push({xhr: d.xhr, el: b});
  }
  function releaseSubmitter(e) {
    var xhr = e && e.detail && e.detail.xhr, keep = [];
    // An answer that sends the browser to another page (the network picker's choice): the
    // answer is that page, so the button stays busy until it replaces this one.
    if (xhr && xhr.getResponseHeader && (xhr.getResponseHeader('HX-Redirect')
                                         || xhr.getResponseHeader('HX-Refresh') === 'true')) return;
    for (var i = 0; i < heldSubmitters.length; i++) {
      var h = heldSubmitters[i];
      // Its own answer, or one whose answer came while its form was off the page (htmx then
      // fires afterRequest where this listener may not hear it).
      if (h.xhr === xhr || !h.xhr || h.xhr.readyState === 4) {
        h.el.disabled = false;
        h.el.classList.remove('htmx-request');
        h.el.removeAttribute('aria-busy');
      } else {
        keep.push(h);
      }
    }
    heldSubmitters = keep;
  }

  /* The tab that asked is drawn chosen at once, before the fragment arrives. */
  function markTab(e) {
    var tab = e.target;
    if (!tab || !tab.classList || !tab.classList.contains('tab')) return;
    var all = tab.parentNode.querySelectorAll('.tab');
    for (var i = 0; i < all.length; i++) {
      all[i].classList.remove('on');
      if (all[i].getAttribute('role') === 'tab' && !all[i].classList.contains('off')) {
        all[i].setAttribute('aria-selected', 'false');
      }
    }
    tab.classList.add('on');
    tab.setAttribute('aria-selected', 'true');
  }

  /* No clipboard (an http page, an old browser): select the command beside
     the button, so a person copies it by hand, never nothing. */
  function selectText(button) {
    var code = button && button.parentNode ? button.parentNode.querySelector('code') : null;
    if (!code || !root.getSelection || !root.document.createRange) return;
    var range = root.document.createRange();
    range.selectNodeContents(code);
    var sel = root.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
  }

  function registerAlpine() {
    var A = root.Alpine;
    A.data('frame', function () {
      return {
        drawer: false,
        // The side help panel (NSOT_GUI_BRIEF 10a): an info link loads its
        // manual section into it (htmx) and opens it here.
        help: false,
        // At phone width the go-to box is its button (board B, C537): open or not.
        jumpOpen: false,
        get drawerClass() { return this.drawer ? 'open' : ''; },
        get jumpClass() { return this.jumpOpen ? 'open' : ''; },
        get jumpExpanded() { return this.jumpOpen ? 'true' : 'false'; },
        open: function () { this.drawer = true; },
        close: function () { this.drawer = false; this.help = false; },
        openHelp: function () { this.help = true; },
        closeHelp: function () { this.help = false; this.jumpOpen = false; },
        toggleJump: function () {
          var self = this;
          this.jumpOpen = !this.jumpOpen;
          if (this.jumpOpen) {
            this.$nextTick(function () { if (self.$refs.jumpbox) self.$refs.jumpbox.focus(); });
          }
        },
        jump: function () {
          var form = this.$el.closest ? this.$el.closest('form') : this.$el;
          var box = form.querySelector('input[name="name"]');
          var target = jumpTarget(form.getAttribute('data-base'), box && box.value,
                                  addressQuery(form));
          if (target) root.location.assign(target);
        }
      };
    });
    A.data('copy', function () {
      return {
        copied: false,
        // A button that names what it copies keeps its words (data-label), Logs' "Copy the link".
        get label() { return this.copied ? 'Copied' : (this.$el.getAttribute('data-label') || 'Copy'); },
        copy: function () {
          var self = this, text = this.$el.getAttribute('data-copy') || '';
          var done = function () { self.copied = true; root.setTimeout(function () { self.copied = false; }, 1500); };
          if (root.navigator && root.navigator.clipboard && root.navigator.clipboard.writeText) {
            root.navigator.clipboard.writeText(text).then(done, function () { selectText(self.$el); });
          } else {
            selectText(self.$el);
          }
        }
      };
    });
    // The theme menu (the operator, 2026-09-30): System, Light or Dark, kept
    // per browser by nmas_theme.js. Getters and argument-free methods only,
    // as Alpine's CSP build evaluates.
    A.data('theme', function () {
      var T = root.NMAS_THEME;
      function words(c) { return c === 'dark' ? 'Dark' : (c === 'light' ? 'Light' : 'System'); }
      return {
        isOpen: false,
        choice: T ? T.get() : 'system',
        get expanded() { return this.isOpen ? 'true' : 'false'; },
        get label() { return 'Theme: ' + words(this.choice); },
        get systemClass() { return this.choice === 'system' ? 'menu-item on' : 'menu-item'; },
        get lightClass() { return this.choice === 'light' ? 'menu-item on' : 'menu-item'; },
        get darkClass() { return this.choice === 'dark' ? 'menu-item on' : 'menu-item'; },
        get systemChecked() { return this.choice === 'system' ? 'true' : 'false'; },
        get lightChecked() { return this.choice === 'light' ? 'true' : 'false'; },
        get darkChecked() { return this.choice === 'dark' ? 'true' : 'false'; },
        toggle: function () { this.isOpen = !this.isOpen; },
        close: function () { this.isOpen = false; },
        pick: function (c) { this.choice = T ? T.set(c) : c; this.isOpen = false; },
        chooseSystem: function () { this.pick('system'); },
        chooseLight: function () { this.pick('light'); },
        chooseDark: function () { this.pick('dark'); }
      };
    });
    A.data('menu', function () {
      return {
        isOpen: false,
        get expanded() { return this.isOpen ? 'true' : 'false'; },
        toggle: function () { this.isOpen = !this.isOpen; },
        close: function () { this.isOpen = false; }
      };
    });
    // Acknowledge an EVENT row on Needs attention (the operator, 2026-10-02): a reason,
    // recorded with who and when. Busy on itself until the answer, bounded (ACK_BOUND_MS);
    // the answer is drawn in place at once ("Acknowledged.", a refusal's reason, or no answer
    // in time), and the response invalidates `acknowledgements`, so the list redraws and the
    // row leaves it. Cancel is offered only on an open, unsent form: once sent it would
    // suggest an undo that does not happen (the operator, 2026-10-19).
    A.data('acknowledge', function () {
      return {
        isOpen: false, busy: false, done: false, said: '', note: '',
        get closed() { return !this.isOpen && !this.done; },
        get label() { return ackLabel(this.busy); },
        get cancellable() { return this.isOpen && !this.busy; },
        // The hold's marker (C459): an open form, typing or in flight, holds the list's
        // redraw (in flight for at most ACK_BOUND_MS, so a redraw cannot take the answer's
        // place); an answered or closed one never does.
        get editing() { return this.isOpen ? 'true' : 'false'; },
        open: function () {
          var box = this.$root.querySelector('input[name="why"]');
          this.isOpen = true; this.said = ''; this.note = '';
          if (box && box.focus) root.setTimeout(function () { box.focus(); }, 0);
        },
        cancel: function () { if (this.busy) return; this.isOpen = false; this.said = ''; },
        send: function () {
          var self = this, el = this.$root, box = el.querySelector('input[name="why"]');
          var ctl = root.AbortController ? new root.AbortController() : null;
          var timer = root.setTimeout(function () {
            if (ctl) ctl.abort();
            drawn(ackNoAnswer(ACK_BOUND_MS));
          }, ACK_BOUND_MS);
          var answered = false;
          function drawn(next) {
            if (answered) return;
            answered = true;
            root.clearTimeout(timer);
            self.busy = next.busy; self.isOpen = next.isOpen; self.done = !!next.done;
            self.said = next.said; self.note = next.note;
          }
          self.busy = true;
          self.said = '';
          self.note = '';
          root.fetch(el.getAttribute('data-url'), {
            method: 'POST', headers: {'Content-Type': 'application/json', 'Accept': 'application/json'},
            body: JSON.stringify({row: el.getAttribute('data-row'), event: el.getAttribute('data-event'),
                                  why: box ? box.value : ''}),
            signal: ctl ? ctl.signal : undefined
          }).then(function (r) {
            return r.json().then(function (b) { return [r.status, b]; }, function () { return [r.status, null]; });
          }).then(function (got) {
            drawn(ackAnswer(got[0], got[1]));
          }, function (e) {
            drawn((e && e.name === 'AbortError') ? ackNoAnswer(ACK_BOUND_MS)
              : {busy: false, isOpen: true, said: 'Not acknowledged: ' + e.message, note: ''});
          });
        }
      };
    });
  }

  /* C388: a swap that yields nothing, or a request that fails, is never silent. htmx 2 swaps
     nothing on a 4xx or 5xx, and swaps an EMPTY slot when the selection (hx-select, passed
     down from an ancestor unless one disinherits it) matches nothing in the answer: C385, the
     break-glass record's buttons, did nothing on the host. A drawn refusal (an HTML fragment,
     whatever its status) is the server's answer and is drawn; anything else says
     "Couldn't load <what>." in the region that was meant to update, keeping what it showed,
     the technical reason on hover and Try again beside it (C409: it was inserted beside the
     control, pushing its row apart). */
  function isFragment(body, contentType) {
    return /text\/html/i.test(contentType || '') && !!(body || '').replace(/\s+/g, '') &&
      !/^\s*<(!doctype|html)\b/i.test(body);
  }

  function failWords(status, statusText, body, contentType) {
    var why = '';
    if (/json/i.test(contentType || '')) {
      try { var got = JSON.parse(body); why = (got && typeof got.error === 'string') ? got.error : ''; }
      catch (x) { why = ''; }
    } else if (/text\/html/i.test(contentType || '')) {
      var title = /<title>([^<]*)<\/title>/i.exec(body || '');
      why = title ? title[1].replace(/\s+/g, ' ').trim() : '';
    } else if (body && body.length <= 200) {
      why = body.trim();
    }
    var code = 'HTTP ' + status + (statusText ? ' ' + statusText : '');
    return why ? why + ' (' + code + ')' : 'the server answered ' + code;
  }

  /* hx-select as htmx 2 resolves it for the element that asked: its own only, since the v2
     pages turn inheritance off (C409; "unset" is none). */
  function selectFor(el) {
    var v = el && el.getAttribute ? (el.getAttribute('hx-select') || el.getAttribute('data-hx-select')) : '';
    return v && v !== 'unset' ? v : null;
  }

  var COULDNT = 'data-couldnt';
  var INLINE = /^(A|BUTTON|INPUT|SELECT|TEXTAREA|SPAN|LABEL|IMG)$/;

  /* The region that was meant to update: the target, when it is on the page and can hold a
     notice; else the control's own card or section (its target is gone: C409's case). */
  function regionFor(target, control) {
    var r = (target && target.ownerDocument && target.ownerDocument.contains(target)) ? target : null;
    var BLOCK = '[role=menu], .op-card, .card, section, .tab-body, main';
    if (!r && control && control.closest) r = control.closest(BLOCK);
    // A control that is its own target (a menu row asking for itself): the notice goes in its
    // menu or card, below its row, never beside it.
    if (r && INLINE.test(r.tagName || '')) r = (r.parentElement && r.parentElement.closest(BLOCK)) || r.parentElement;
    return r;
  }

  /* What the control would have loaded, in a person's words: its own `data-what` ("the 6-hour
     view"), else what its region is. PURE. */
  function couldntWords(what, inCard) {
    return "Couldn't load " + (what || (inCard ? 'this card' : 'this view')) + '.';
  }

  /* An inline target outside every card and section (the frame's sidebar or top bar: the Needs
     attention count) holds no notice: a box there pushed the sidebar apart (the operator,
     2026-10-12). The failure is said ON the element: the count its own unreadable "?", anything
     else marked, the words and the reason on hover. It keeps its listener, so the next update
     tries again. */
  function sayCouldntInline(target, reason) {
    var words = couldntWords(target.getAttribute('data-what'), false);
    target.setAttribute(COULDNT, '');
    if (target.classList.contains('count')) {
      target.className = 'count count-unreadable';
      target.textContent = '?';
      target.title = 'Needs attention could not be read (' + reason + '): this is not the ' +
        'same as nothing needing attention. It is read again at the next update.';
    } else {
      target.classList.add('couldnt-inline');
      target.title = words + ' ' + reason;
    }
  }

  function sayCouldnt(target, control, reason) {
    if (target && target.ownerDocument && target.ownerDocument.contains(target) &&
        INLINE.test(target.tagName || '') && target.closest &&
        !target.closest('[role=menu], .op-card, .card, section, .tab-body, main')) {
      sayCouldntInline(target, reason);
      return;
    }
    var region = regionFor(target, control);
    if (!region) return;
    var doc = region.ownerDocument, box = null;
    for (var c = region.firstElementChild; c; c = c.nextElementSibling) {
      if (c.hasAttribute(COULDNT)) { box = c; break; }
    }
    if (!box) {
      box = doc.createElement('div');
      box.className = 'notice notice-warn couldnt';
      box.setAttribute(COULDNT, '');
      box.setAttribute('role', 'alert');
      var p = doc.createElement('p'), again = doc.createElement('button');
      again.type = 'button';
      again.className = 'btn btn-small';
      again.textContent = 'Try again';
      box.appendChild(p);
      box.appendChild(again);
      // After the part of the region that holds the control, never above or beside it, so the
      // control's own row does not move.
      var holder = null;
      if (control && control !== region && region.contains(control)) {
        holder = control;
        while (holder.parentElement && holder.parentElement !== region) holder = holder.parentElement;
      }
      region.insertBefore(box, holder ? holder.nextSibling : region.firstChild);
    }
    var what = control && control.getAttribute ? control.getAttribute('data-what') : '';
    box.firstChild.textContent = couldntWords(what, !!(region.closest && region.closest('.op-card, .card')));
    box.firstChild.title = reason;
    box.lastChild.onclick = function () {
      if (box.parentNode) box.parentNode.removeChild(box);
      if (control && doc.contains(control)) control.click();
      else if (root.location) root.location.reload();
    };
  }

  function clearCouldnt(target) {
    if (!target || !target.firstElementChild) return;
    for (var c = target.firstElementChild; c; c = c.nextElementSibling) {
      if (c.hasAttribute(COULDNT)) { target.removeChild(c); return; }
    }
  }

  function askedBy(d, e) {
    return (d.requestConfig && d.requestConfig.elt) || d.elt || (e && e.target) || null;
  }

  function neverSilent(e) {
    var d = e.detail || {}, xhr = d.xhr, target = d.target;
    if (!xhr || !target) return;
    var type = xhr.getResponseHeader('Content-Type') || '', body = d.serverResponse;
    if (d.isError) {
      if (!isFragment(body, type)) {
        d.shouldSwap = false;
        sayCouldnt(target, askedBy(d, e), failWords(xhr.status, xhr.statusText, body, type));
        return;
      }
      d.shouldSwap = true;
    }
    if (!d.shouldSwap) return;
    // htmx's order: the HX-Reselect header, the request's own select, the override, the
    // element's (inherited) hx-select.
    var sel = xhr.getResponseHeader('HX-Reselect') || d.select || d.selectOverride ||
      selectFor(d.requestConfig ? d.requestConfig.elt : d.elt);
    if (sel && sel !== 'unset' && typeof body === 'string' && body.replace(/\s+/g, '') &&
        root.DOMParser) {
      var doc = new root.DOMParser().parseFromString(body, 'text/html'), found = false;
      try { found = !!doc.querySelector(sel); } catch (x) { found = false; }
      if (!found) {
        d.shouldSwap = false;
        sayCouldnt(target, askedBy(d, e), "the answer held nothing matching " + sel +
                   ' (HTTP ' + xhr.status + ')');
        return;
      }
    }
    clearCouldnt(target);
  }

  function noAnswer(words) {
    return function (e) {
      var d = e.detail || {}, path = d.pathInfo ? d.pathInfo.requestPath : '';
      sayCouldnt(d.target, askedBy(d, e), words + (path ? ' (' + path + ')' : ''));
    };
  }

  /* C389: the page as this browser received it, against what the tool sends. Every script a v2
     page loads is the tool's own, from /static/ (the strict policy, vendored libraries); any
     other was added between the tool and this browser: a proxy rewriting pages (an email
     decoder and an analytics beacon, measured on the host), or an extension. PURE: the added
     ones, from each script's [src, type] (a data block, typed JSON, is not a script). */
  function injectedScripts(scripts, origin) {
    var out = [];
    for (var i = 0; i < scripts.length; i++) {
      var src = scripts[i][0] || '', type = (scripts[i][1] || '').toLowerCase();
      if (type && !/javascript|ecmascript|module/.test(type)) continue;
      if (src && src.indexOf(origin + '/static/') === 0) continue;
      out.push(src || '(an inline script)');
    }
    return out;
  }

  function rewrittenWords(added) {
    return 'This page arrived changed: ' + added.length + ' script' + (added.length === 1 ? '' : 's') +
      ' the tool did not send (' + added.join(', ') + ') ' + (added.length === 1 ? 'was' : 'were') +
      ' added on the way, so what you see is not what the tool served and its tests check. ' +
      'Turn off page rewriting at the proxy in front of the tool (email obfuscation, analytics ' +
      'injection), or the browser extension adding ' + (added.length === 1 ? 'it' : 'them') + '.';
  }

  function checkServedPage(doc, origin) {
    var list = [], els = doc.getElementsByTagName('script');
    for (var i = 0; i < els.length; i++) list.push([els[i].src, els[i].getAttribute('type')]);
    var added = injectedScripts(list, origin);
    if (!added.length || doc.querySelector('[data-rewritten]')) return added;
    var box = doc.createElement('div'), p = doc.createElement('p');
    box.className = 'notice notice-warn';
    box.setAttribute('data-rewritten', '');
    box.setAttribute('role', 'alert');
    p.textContent = rewrittenWords(added);
    box.appendChild(p);
    var main = doc.querySelector('main') || doc.body;
    main.insertBefore(box, main.firstChild);
    return added;
  }

  /* A page the browser RESTORES from its back/forward cache comes back with its
     script state as it was left, and its live channel closed: a wait that
     ended hours ago still reads "waiting", with Stop waiting beside it (the
     operator, 2026-10-01). Every v2 page draws live state, so a restored one
     is loaded again rather than shown as it was. */
  function reloadIfRestored(e, loc) {
    if (e && e.persisted) { loc.reload(); return true; }
    return false;
  }
  if (root.addEventListener && root.location) {
    root.addEventListener('pageshow', function (e) { reloadIfRestored(e, root.location); });
  }

  if (root.document && root.document.addEventListener) {
    root.document.addEventListener('alpine:init', registerAlpine);
    root.document.addEventListener('DOMContentLoaded', function () {
      if (root.location) checkServedPage(root.document, root.location.origin);
      wireAnnouncements();
      drawAges();
      drawLive();
      drawBadge();
      root.setInterval(function () { drawLive(); drawBadge(); releaseHeld(); }, 1000);
      root.setInterval(function () { drawAges(); }, 15000);
    });
    root.document.addEventListener('htmx:afterSettle', function (e) { drawAges(e.target); catchUpMissed(e); reopenKept(); });
    root.document.addEventListener('htmx:beforeSwap', rememberOpen);
    root.document.addEventListener('htmx:beforeRequest', noteAsked);
    root.document.addEventListener('htmx:beforeRequest', markTab);
    root.document.addEventListener('htmx:beforeSend', holdSubmitter);
    root.document.addEventListener('htmx:afterRequest', releaseSubmitter);
    root.document.addEventListener('htmx:beforeSwap', neverSilent);
    root.document.addEventListener('htmx:beforeSwap', holdWhileEditing);  // after: the last word on a swap
    root.document.addEventListener('focusout', function () { root.setTimeout(releaseHeld, 0); });
    root.document.addEventListener('htmx:sendError', noAnswer('the server did not answer'));
    root.document.addEventListener('htmx:timeout', noAnswer('no answer in time'));
    root.document.addEventListener('htmx:targetError', function (e) {
      sayCouldnt(null, e.target, "no " + (e.detail && e.detail.target) + " on this page");
    });
    root.document.addEventListener('keydown', function (e) {
      var t = e.target && e.target.tagName;
      if (e.key !== '/' || t === 'INPUT' || t === 'TEXTAREA' || t === 'SELECT') return;
      var box = root.document.querySelector('.jump input');
      if (box) { e.preventDefault(); box.focus(); }
    });
  }

  root.NMAS_V2 = {ageWords: ageWords, liveWords: liveWords, jumpTarget: jumpTarget, KEYS: KEYS,
                  reloadIfRestored: reloadIfRestored, ackLabel: ackLabel, ackRefusal: ackRefusal,
                  ackAnswer: ackAnswer, ackNoAnswer: ackNoAnswer, ACK_BOUND_MS: ACK_BOUND_MS,
                  badgeDoubt: badgeDoubt, missedKeys: missedKeys, isFragment: isFragment,
                  failWords: failWords, couldntWords: couldntWords, injectedScripts: injectedScripts,
                  rewrittenWords: rewrittenWords, openKeys: openKeys, submitterOf: submitterOf};
})(typeof window !== 'undefined' ? window : this);
