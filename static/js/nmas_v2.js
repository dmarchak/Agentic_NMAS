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
              // C2347's reader: the scheduled quality jobs' runs.
              'scheduled_jobs',
              // Workstream 0's reader: the two CI runners on each commit.
              'ci_agreement',
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
              // A diagnosis Diagnose… ran finished (modules/heal/diagnose_page.py): its card
              // reads it by id (board H, H16).
              'diagnosis',
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
              // The SDN reader read a network's controllers again, or a connection was saved
              // or removed (PHASE8_PLAN 17.1 S11): SDN › Controllers and Flows re-read.
              'sdn',
              // A controller app deploy moved a step or ended (P6, modules/apps/deploy_op.py):
              // its running card and SDN › Apps re-read.
              'controller_deploy',
              // A network's NSOT export committed (C2777): SDN › Apps' export card and its
              // controllers re-read.
              'nsot_export',
              // A network's code repository saved or fetched: its Settings card and SDN › Apps
              // re-read.
              'code_repo',
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

  /* The focus a form's box takes once it is DRAWN (C3092). Alpine shows an `x-show` element in
     a timer of its own, so a focus asked in one timer raced it: measured with a real browser,
     2026-11-11, in 4 of 16 opens of the Acknowledge form the focus was asked of a box not yet
     shown, which takes no focus, and the person had to click the box. The box is asked again,
     one timer at a time, until it is shown, at most FOCUS_TRIES times (the show is one timer
     away, so the second ask finds it; the bound is for a form that never shows). *later*
     defers one call (the page's own timer by default; a test hands its own). */
  var FOCUS_TRIES = 20;
  function focusWhenShown(box, tries, later) {
    if (!box || !box.focus) return;
    if (box.offsetParent) { box.focus(); return; }
    if (tries > 0) {
      (later || function (f) { root.setTimeout(f, 0); })(function () {
        focusWhenShown(box, tries - 1, later);
      });
    }
  }

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

  /* A REFRESH NEVER DISRUPTS A PERSON MID-TASK (C1852, the operator's Walk 2, 2026-10-27: on
     Monitoring › Alerts › History each announcement redrew the list, closing the entry a person
     had open and dropping an Explain in flight, whose answer then had nowhere to land). Two
     more states hold a live redraw, as editing does:

     - SENDING: an action in the region is in flight (a request that is not a GET, marked on
       its element from the request's start to its end, `noteSending`). Its answer swaps into
       the region; replacing the region first leaves it nowhere. The hold ends with the answer.
     - OPEN: an entry in the region that loaded its own body when opened (`details[hx-get]`,
       open) is open. What the person reads and pressed there came by its own requests, which
       a redraw of the list cannot draw again. The entry says "Paused while you work" with
       Show it now (the redraw at once; open entries are opened again and load their bodies
       again); closing every such entry lets the redraw happen by itself.

     Paused, not kept: keeping a live entry through a swap means moving its nodes, with their
     requests in flight, through htmx's swap, then racing the reopened entry's own load. */
  var PAUSED_WORDS = 'Paused while you work: newer data is waiting.';
  var SENDING_WORDS = 'Newer data is waiting; it shows when this answers.';
  /* REVIEW (C2001, the operator's Lab 8 walk, 2026-10-27: on SDN › Responses each
     announcement redrew the region and took away the open preview and its Send, the step HITL
     exists for). A card in the region marked `data-holds-live` (an operation's preview, its
     refusal or its result, drawn in place by the person's own request) holds a live redraw as
     an open entry does: what it shows came by the person's request, which a redraw of the list
     cannot draw again. It says so with Show it now, which closes the card and redraws. */
  var REVIEW_WORDS = 'Paused while you review this: newer data is waiting.';

  /* PURE over the DOM: an element in *region* whose action is in flight, or null. */
  function sendingIn(region) {
    return region && region.querySelector ? region.querySelector('[data-nmas-sending]') : null;
  }

  /* PURE over the DOM: an open entry in *region* that loaded its own body, or null. */
  function openedIn(region) {
    return region && region.querySelector ? region.querySelector('details[hx-get][open]') : null;
  }

  /* PURE over the DOM: a card in *region* the person is reviewing (C2001), or null. */
  function reviewedIn(region) {
    return region && region.querySelector ? region.querySelector('[data-holds-live]') : null;
  }

  /* PURE: why a live redraw of *region* is held now ("editing", "sending", "open",
     "review"), or ''. */
  function holdReason(region) {
    if (editingIn(region)) return 'editing';
    if (sendingIn(region)) return 'sending';
    if (openedIn(region)) return 'open';
    if (reviewedIn(region)) return 'review';
    return '';
  }

  function isWrite(verb) {
    return !!verb && String(verb).toLowerCase() !== 'get';
  }

  function noteSending(e) {
    var d = (e && e.detail) || {}, el = d.elt;
    if (el && el.setAttribute && isWrite((d.requestConfig || {}).verb)) el.setAttribute('data-nmas-sending', '1');
  }

  function noteSent(e) {
    var el = e && e.detail && e.detail.elt;
    if (el && el.removeAttribute) el.removeAttribute('data-nmas-sending');
    if (el && el.removeAttribute) el.removeAttribute('data-nmas-live');
  }

  /* A live redraw's request is marked on its region (`data-nmas-live`) while it is in flight,
     so a busy style meant for a person's own press (Topology dimming, a tab fading) is not
     drawn on every announcement (C2810: the map dimmed on each step of a run). */
  function noteLiveAsk(e) {
    var d = (e && e.detail) || {}, el = d.elt;
    var ev = d.requestConfig && d.requestConfig.triggeringEvent;
    if (el && el.setAttribute && ev && typeof ev.type === 'string' && ev.type.indexOf('nmas:') === 0) {
      el.setAttribute('data-nmas-live', '1');
    }
  }

  /* ONE PRESS, ONE KEY (C1854): every request that is not a GET carries a key made for that
     press (`X-NMAS-Press`); an AI call already made under it is returned, never made again
     (modules/ai/presses.py). PURE but for the randomness it is handed. */
  function pressKey(crypto) {
    try {
      if (crypto && crypto.randomUUID) return crypto.randomUUID().replace(/-/g, '');
    } catch (err) { /* below */ }
    var bytes = null, out = '';
    try {
      if (crypto && crypto.getRandomValues) { bytes = new Uint8Array(16); crypto.getRandomValues(bytes); }
    } catch (err) { bytes = null; }
    for (var i = 0; i < 16; i++) {
      var b = bytes ? bytes[i] : Math.floor(Math.random() * 256);
      out += (b < 16 ? '0' : '') + b.toString(16);
    }
    return out;
  }

  function keyThePress(e) {
    var d = e && e.detail;
    if (!d || !d.headers || !isWrite(d.verb)) return;
    d.headers['X-NMAS-Press'] = pressKey(root.crypto);
  }

  /* Was this swap caused by a LIVE update (a reader's or a job's announcement, `nmas:<key>`)?
     Only those are held: a person's own submission swaps the region it was sent from,
     typed reason and all, because that answer is what they asked for. */
  function isLiveUpdate(d) {
    var ev = d && d.requestConfig && d.requestConfig.triggeringEvent;
    return !!(ev && typeof ev.type === 'string' && ev.type.indexOf('nmas:') === 0);
  }

  /* The part of *region* a person editing *editing* is working in, where its note goes: its
     form or Alpine component when that is the region's own, else the field's parent. `<body>`
     carries x-data (the frame), so a field with no nearer component put the note on the page
     grid as a new column (Topology's Find box, the operator 2026-10-12). */
  function editUnit(editing, region) {
    var unit = editing.closest && editing.closest('form, [x-data]');
    if (!unit || unit === region || !region.contains(unit)) unit = editing.parentNode || region;
    return unit;
  }

  /* Every part of *region* a person is working in, which a merge leaves as it is (C2810): what
     is being edited, an entry open with the body it loaded, a card under review. */
  function heldParts(region) {
    var out = [], i;
    var fields = region.querySelectorAll('input, textarea, [data-editing="true"]');
    for (i = 0; i < fields.length; i++) {
      if (isEditing(fields[i])) out.push(fields[i].getAttribute('data-editing') === 'true'
                                          ? fields[i] : editUnit(fields[i], region));
    }
    var more = region.querySelectorAll('details[hx-get][open], [data-holds-live]');
    for (i = 0; i < more.length; i++) out.push(more[i]);
    var at = pointedAt(region);
    if (at) out.push(at);
    return out.filter(function (u) { return u !== region; });
  }

  /* C2841: the control a person is pointing at, or a button they have focused, in *region*:
     a part they are working in (a Right about to be pressed). A merge leaves it, and the row
     holding it, where it is, and holds a new row that would land above it (`mergeChildren`),
     so the press lands on what was aimed at. Two of the operator's four Right marks never
     posted: a later decision's row was drawn above the record, in the window, and the press
     landed on the line Right had moved down from. */
  var POINTED = 'button, a[href], summary, label, input, select, textarea';
  function pointedAt(region) {
    var el = null;
    try {
      var hovered = region.querySelectorAll(':hover');
      if (hovered.length) el = hovered[hovered.length - 1].closest(POINTED);
    } catch (x) { el = null; }
    if (el && region.contains(el)) return el;
    var a = root.document.activeElement;
    return a && a.tagName === 'BUTTON' && a !== region && region.contains(a) ? a : null;
  }

  /* Whether a part a person is working in is at or after *ref* among its siblings, in the
     window: a node drawn before *ref* would push it down. */
  function heldAfter(ref, ctx) {
    var at = shownAt(ref);
    if (!at || !ctx.keep.length || at.getBoundingClientRect().top >= root.innerHeight) return false;
    for (var n = at; n; n = n.nextSibling) {
      if (n.nodeType === 1 && holdsPart(n, ctx)) return true;
    }
    return false;
  }

  function holdWhileEditing(e) {
    var region = e.detail && e.detail.target;
    if (!e.detail || !e.detail.shouldSwap || !region || !isLiveUpdate(e.detail)) return;
    var why = holdReason(region);
    if (!why) return;
    // C2810: a region the merge can redraw is no longer held whole while a person edits, has
    // an entry open or reviews a card there. The merge leaves exactly that part as it is
    // (`heldParts`) and draws the rest, new rows above the window counted; the part says
    // newer data is waiting, and is drawn once the person is done, as before. An action in
    // flight still holds the whole region: its answer needs the place it was sent from.
    if (why === 'sending' || !mergeSpec(e.detail)) e.detail.shouldSwap = false;
    region.setAttribute('data-held', '1');
    // The skipped redraw's open entries are the person's own, still open: nothing to reopen.
    delete keptOpen[region.id];
    if (why !== 'editing') { notePaused(region, why); return; }
    var editing = editingIn(region);
    var unit = editUnit(editing, region);
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
    // What is open NOW: an entry closed since an earlier skipped redraw is not opened again.
    if (keys.length) keptOpen[region.id] = keys;
    else delete keptOpen[region.id];
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

  /* Board NA-R: a section's open or closed state as this viewer last left it
     (`<details data-remember="…">`), kept in this browser only: a convenience, so a store the
     browser refuses forgets it and the section draws as its template says. */
  /* Only a person's own press on the section's summary is remembered (a click, which Enter and
     Space on it make too): a `toggle` cannot tell a person from a redraw, and a redrawn
     section drawn open fired one that overwrote what the person chose. */
  function rememberToggle(e) {
    var s = e.target && e.target.closest ? e.target.closest('summary') : null;
    var d = s ? s.parentNode : null;
    if (!d || d.tagName !== 'DETAILS' || !d.hasAttribute('data-remember')) return;
    try {
      // The press is about to flip it: what it will be is what is kept.
      root.localStorage.setItem('nmas-open:' + d.getAttribute('data-remember'), d.open ? '0' : '1');
    } catch (x) { /* storage refused: nothing kept */ }
  }
  /* Over the whole document after every swap: an outerHTML swap settles on the element it
     replaced, so its target holds none of the new sections (found by
     tests/test_attention_sections.py in a real browser). */
  function applyRemembered(scope) {
    var at = scope && scope.querySelectorAll ? scope : root.document;
    var all = at.querySelectorAll('details[data-remember]');
    for (var i = 0; i < all.length; i++) {
      var v = null;
      try { v = root.localStorage.getItem('nmas-open:' + all[i].getAttribute('data-remember')); }
      catch (x) { v = null; }
      if (v === '0') all[i].open = false;
      else if (v === '1') all[i].open = true;
    }
  }

  /* A LIVE REDRAW MERGES WHAT CHANGED INTO THE PAGE; IT NEVER REPLACES THE REGION (C2810, the
     operator, 2026-11-08: "Live refresh never interrupts the person. A refresh keeps scroll
     position, focus, open or closed disclosures, text in inputs, and marks (Right/Wrong). It
     doesn't flash, and nothing above the reader shifts: new items above the viewport show as
     'N new, show them' instead of pushing the page."). Each live region replaced itself whole
     on every announcement (outerHTML or innerHTML), so a focused button, an open entry with no
     key, a body loaded into a row and the reader's place went with it, and Needs attention was
     caught half drawn between the swap and the settle that reopened its rows.

     How: every element a region drew is remembered with the server's own copy of it
     (`drawnFrom`, the page's regions as parsed, before Alpine or htmx touched them, and each
     redraw's answer after). A live answer is compared with that copy, not with the page: an
     element whose copy equals its new version is left exactly as it is, whatever the person
     did to it (opened, typed in, focused, scrolled, marked). One that changed has only the
     attributes the server changed set, and its children merged the same way, matched by their
     key (`id`, `data-key`, or a disclosure's `data-keep`; a list's rows carry one) and
     otherwise by their place among their unkeyed siblings. What the page made itself (a body
     a person loaded into a row, Load more's rows, Alpine's parts, a held note) has no copy,
     so the merge keeps it where it is. A new keyed row that would land above the top of the
     window is drawn hidden, and "N new, show them" says so instead of pushing the page down.

     Mercury's own merge, not a library's (idiomorph, htmx's morph extension): anything that
     ships in Mercury has its licence decided by the operator, and this needs only what the
     page already holds. */
  var drawnFrom = typeof root.WeakMap === 'function' ? new root.WeakMap() : null;
  var MERGE_OUTER = 'nmas-merge-outer', MERGE_INNER = 'nmas-merge-inner';
  var NEW_WORDS = ' new, show them';

  function isRegion(el) {
    return !!(el && el.nodeType === 1 && (el.getAttribute('hx-trigger') || '').indexOf('nmas:') >= 0);
  }

  /* htmx's own passing classes, and the marks this file puts on a region while it holds or
     asks (a hold, an action in flight, a live request), are never part of what the server
     drew. */
  var PAGE_MARKS = ['data-held', 'data-nmas-sending', 'data-nmas-live'];
  function scrub(el) {
    if (!el || el.nodeType !== 1) return;
    var marked = [el].concat(Array.prototype.slice.call(
      el.querySelectorAll('[data-held], [data-nmas-sending], [data-nmas-live]')));
    for (var m = 0; m < marked.length; m++) {
      for (var p = 0; p < PAGE_MARKS.length; p++) marked[m].removeAttribute(PAGE_MARKS[p]);
    }
    var all = [el].concat(Array.prototype.slice.call(el.querySelectorAll('[class*="htmx-"]')));
    for (var i = 0; i < all.length; i++) {
      var c = all[i].getAttribute('class');
      if (c === null || c.indexOf('htmx-') < 0) continue;
      var kept = c.split(/\s+/).filter(function (t) { return t && t.indexOf('htmx-') !== 0; });
      if (kept.length) all[i].setAttribute('class', kept.join(' '));
      else all[i].removeAttribute('class');
    }
  }

  /* Pair each node under *live* with its copy under *copy* (the same shape, node for node). */
  function remember(live, copy) {
    if (!drawnFrom || !live || !copy) return;
    drawnFrom.set(live, copy);
    var a = live.childNodes, b = copy.childNodes;
    if (a.length !== b.length) return;
    for (var i = 0; i < a.length; i++) remember(a[i], b[i]);
  }

  /* Remember *el* as the server drew it: a copy taken before anything on the page changed it. */
  function capture(el) {
    if (!drawnFrom || !el || el.nodeType !== 1) return;
    var copy = el.cloneNode(true);
    scrub(copy);
    remember(el, copy);
  }

  /* Every outermost region under *scope* (or *scope* itself). */
  function captureRegions(scope) {
    if (!drawnFrom || !scope || !scope.querySelectorAll) return;
    if (isRegion(scope)) { capture(scope); return; }
    var all = scope.querySelectorAll('[hx-trigger*="nmas:"]');
    for (var i = 0; i < all.length; i++) {
      var up = all[i].parentNode, inner = false;
      while (up && up !== scope && up.nodeType === 1) {
        if (isRegion(up)) { inner = true; break; }
        up = up.parentNode;
      }
      if (!inner) capture(all[i]);
    }
  }

  /* A swap that was not a merge drew a region afresh (its first load, a person's own request,
     a hold's redraw): remember it as drawn. Content a person loaded INTO a region (a row's
     body, Load more's page) is the page's own and stays unremembered, so a merge keeps it. */
  var merging = false;
  function captureSwapped(e) {
    if (merging || !drawnFrom) return;
    var t = e.detail && e.detail.target;
    if (!t || t.nodeType !== 1) return;
    // A merge's own swap: its region already holds the server's copy, and the page's changes
    // must not be taken for the server's.
    if (t.nmasMerged) { delete t.nmasMerged; return; }
    var now = t.isConnected ? t : (t.id ? root.document.getElementById(t.id) : null);
    if (!now) return;
    if (isRegion(now)) { capture(now); return; }
    var up = now.parentNode;
    while (up && up.nodeType === 1) {
      if (isRegion(up)) return;                     // loaded into a region: the page's own
      up = up.parentNode;
    }
    captureRegions(now);
  }

  /* An out-of-band part the server sent with another answer (Monitoring's Firing count with
     its list, C2251) is the server's drawing too: remembered as drawn, so the region around it
     merges it rather than keeping it as the page's own. */
  function captureOob(e) {
    if (merging || !drawnFrom) return;
    var t = e.detail && e.detail.target;
    if (!t || t.nodeType !== 1) return;
    if (t.nmasOobMerged) { delete t.nmasOobMerged; return; }
    var now = t.isConnected ? t : (t.id ? root.document.getElementById(t.id) : null);
    if (now) capture(now);
  }

  /* An out-of-band part the page holds the server's copy of, sent again whole (its own
     element, the same id), merges as a region does: replaced, it was drawn again on every
     answer that carried it (Monitoring's Firing count, measured by tests/test_live_merge.py). */
  function mergeOob(e) {
    var d = e.detail, t = d && d.target, f = d && d.fragment;
    if (!d || !d.shouldSwap || !t || !f || !drawnFrom) return;
    var els = Array.prototype.filter.call(f.childNodes, function (n) { return n.nodeType === 1; });
    if (els.length !== 1 || els[0].tagName !== t.tagName || (els[0].id || '') !== (t.id || '')) return;
    if (!drawnFrom.get(t)) {
      // Outside any region, so never remembered: the same drawing again is left alone (and
      // remembered from now on); a different one is htmx's to replace.
      var now = t.cloneNode(true);
      scrub(now);
      if (!now.isEqualNode(els[0])) return;
      d.shouldSwap = false;
      remember(t, els[0]);
      t.nmasOobMerged = true;
      return;
    }
    d.shouldSwap = false;
    mergeRegion(true, t, f);
    delete t.nmasMerged;
    t.nmasOobMerged = true;       // its `htmx:oobAfterSwap` is not a fresh drawing to capture
  }

  /* PURE over a node: its key among its siblings, or '' (matched by its place). */
  function keyOf(n) {
    if (!n || n.nodeType !== 1) return '';
    var v = n.getAttribute('id');
    if (v) return '#' + v;
    v = n.getAttribute('data-key');
    if (v) return 'k:' + v;
    v = n.getAttribute('data-keep');
    return v ? 'p:' + v : '';
  }

  function tokens(s) { return String(s || '').split(/\s+/).filter(function (t) { return !!t; }); }

  /* Set on *live* only what the server changed between *was* and *next*: an attribute the
     server left alone keeps what the page made of it (a disclosure's open, Alpine's style). */
  function mergeAttrs(live, was, next) {
    var i, name, a, b;
    for (i = 0; i < next.attributes.length; i++) {
      name = next.attributes[i].name; b = next.attributes[i].value; a = was.getAttribute(name);
      if (a === b || name === 'open') continue;
      if (name === 'class') {
        var ta = tokens(a), tb = tokens(b), j;
        for (j = 0; j < ta.length; j++) if (tb.indexOf(ta[j]) < 0) live.classList.remove(ta[j]);
        for (j = 0; j < tb.length; j++) if (ta.indexOf(tb[j]) < 0) live.classList.add(tb[j]);
      } else {
        live.setAttribute(name, b);
      }
    }
    for (i = 0; i < was.attributes.length; i++) {
      name = was.attributes[i].name;
      if (name === 'open' || next.hasAttribute(name)) continue;
      if (name === 'class') {
        var gone = tokens(was.attributes[i].value);
        for (var k = 0; k < gone.length; k++) live.classList.remove(gone[k]);
      } else {
        live.removeAttribute(name);
      }
    }
  }

  function sameChildren(a, b) {
    var x = a.childNodes, y = b.childNodes;
    if (x.length !== y.length) return false;
    for (var i = 0; i < x.length; i++) if (!x[i].isEqualNode(y[i])) return false;
    return true;
  }

  /* Bring *live* (drawn from its copy) to *next*, keeping everything the server left alone. */
  /* PURE over two elements: whether *next* asks for something as it is drawn (an htmx `load`,
     `revealed` or `intersect` trigger) where *was* did not ask the same. */
  function startsAgain(was, next) {
    if (!was || was.nodeType !== 1 || !next || next.nodeType !== 1) return false;
    var a = was.getAttribute('hx-trigger') || '', b = next.getAttribute('hx-trigger') || '';
    return a !== b && /(^|[\s,])(load|revealed|intersect)([\s,]|$)/.test(b);
  }

  /* Returns the node that stands for *next* afterwards: *live* itself, or what replaced it. */
  function morph(live, next, ctx) {
    var was = drawnFrom.get(live);
    if (!was) return live;                           // the page's own: kept as it is
    if (was.isEqualNode(next)) return live;          // unchanged: untouched
    if (ctx.keep.indexOf(live) >= 0) return live;    // a person is working in it: drawn later
    if (live.nodeType !== 1) {
      if (live.nodeValue !== next.nodeValue) live.nodeValue = next.nodeValue;
      drawnFrom.set(live, next);
      return live;
    }
    // An Alpine component the server drew differently starts again from what it drew, as a
    // redraw always made it: its state (busy, a late answer's words) belongs to the drawing it
    // came with. One the server left alone keeps its state (an open menu, a form's choices).
    // So does an element whose new triggers fire as it is drawn (`load`, `revealed`): htmx
    // fires those on an element's first wiring only.
    if (live !== ctx.root && (live.hasAttribute('x-data') || startsAgain(was, next)) && live.parentNode) {
      var made = root.document.importNode(next, true);
      live.parentNode.replaceChild(made, live);
      remember(made, next);
      return made;
    }
    mergeAttrs(live, was, next);
    if (!sameChildren(was, next)) mergeChildren(live, next, ctx);
    drawnFrom.set(live, next);
    return live;
  }

  /* The node a new one is placed before: hidden rows waiting to be shown are skipped. */
  function shownAt(node) {
    while (node && (node.nodeType !== 1 || node.hasAttribute('data-nmas-new'))) node = node.nextSibling;
    return node;
  }

  /* Whether a node placed before *ref* in *parent* lands above the top of the window, where
     drawing it would push down what the person is reading. */
  function landsAbove(ref, parent) {
    var at = shownAt(ref);
    if (at) return at.getBoundingClientRect().top < 0;
    return parent.getBoundingClientRect().bottom < 0;
  }

  function holdsPart(node, ctx) {
    for (var i = 0; i < ctx.keep.length; i++) {
      if (node === ctx.keep[i] || (node.contains && node.contains(ctx.keep[i]))) return true;
    }
    return false;
  }

  /* PURE over nodes: the ids drawn in *node* (itself and every element under it). */
  function idsIn(node) {
    var out = [];
    if (!node || node.nodeType !== 1) return out;
    if (node.id) out.push(node.id);
    var all = node.querySelectorAll('[id]');
    for (var i = 0; i < all.length; i++) out.push(all[i].id);
    return out;
  }

  /* A new row that draws an id a kept row holds is that row's successor (the same record,
     drawn again under a new key: C2841's incident decided again, its dry run's Right in both).
     It goes right after the row the person is working in, never above it: drawn above, it was
     the page's first element of that id, so the Right the person pressed sent its answer into
     the new row (`hx-target="#heal-mark-…"`) and the row they aimed at never drew it, and the
     row above was hidden behind "N new, show them" though nothing new was there. Where it
     lands depended on the rows between them: none (a test alone) put it after; any (rows the
     same network's other records drew, measured 2026-11-09) put it above. */
  function successorsAfter(order, kept) {
    if (!kept.length) return order;
    var held = kept.map(function (k) { return idsIn(k); });
    var moved = [], out = [], i, j;
    for (i = 0; i < order.length; i++) {
      var o = order[i], owner = -1;
      if (o && o.fresh) {
        var ids = idsIn(o.fresh);
        for (j = 0; j < kept.length && owner < 0; j++) {
          for (var n = 0; n < ids.length; n++) if (held[j].indexOf(ids[n]) >= 0) { owner = j; break; }
        }
      }
      if (owner >= 0) moved.push({o: o, after: kept[owner]});
      else out.push(o);
    }
    for (i = 0; i < moved.length; i++) {
      for (j = 0; j < out.length; j++) {
        if ((out[j] && (out[j].node || out[j])) === moved[i].after) { out.splice(j + 1, 0, moved[i].o); break; }
      }
      if (j === out.length) out.push(moved[i].o);
    }
    return out;
  }

  /* Merge *next*'s children into *live*'s (see the comment above `drawnFrom`). */
  function mergeChildren(live, next, ctx) {
    var kids = Array.prototype.slice.call(live.childNodes);
    var mine = kids.filter(function (n) { return !drawnFrom.get(n); });
    // Every child the page's own (a body a person loaded in): it stays whole.
    if (kids.length && mine.length === kids.length) return;
    var byKey = {}, ownByKey = {}, loose = [], used = [], i, k;
    for (i = 0; i < kids.length; i++) {
      var was = drawnFrom.get(kids[i]);
      if (!was) { k = keyOf(kids[i]); if (k) ownByKey[k] = kids[i]; continue; }
      k = keyOf(was);
      if (k && !byKey[k]) byKey[k] = kids[i]; else loose.push(kids[i]);
    }
    var plan = [], from = 0, wanted = Array.prototype.slice.call(next.childNodes);
    for (i = 0; i < wanted.length; i++) {
      var n = wanted[i], m = null;
      k = keyOf(n);
      if (k) {
        m = byKey[k] || null;
        if (!m && ownByKey[k] && used.indexOf(ownByKey[k]) < 0) {
          // The page's own version of this keyed part (a person's answer drawn in its place).
          used.push(ownByKey[k]); plan.push({node: ownByKey[k]}); continue;
        }
      } else {
        for (var j = from; j < loose.length; j++) {
          var w = drawnFrom.get(loose[j]);
          if (used.indexOf(loose[j]) < 0 && w.nodeType === n.nodeType && w.nodeName === n.nodeName) {
            m = loose[j]; from = j + 1; break;
          }
        }
      }
      if (m && used.indexOf(m) < 0) { used.push(m); plan.push({node: morph(m, n, ctx), was: m}); }
      else plan.push({fresh: n});
    }
    // What the server no longer draws leaves, except a row a person loaded more rows after
    // (Load more's page follows it): it moved down a page, it did not end.
    var lastOwn = -1;
    for (i = 0; i < kids.length; i++) if (!drawnFrom.get(kids[i]) && keyOf(kids[i])) lastOwn = i;
    // And a part a person is working in stays until they are done.
    var keptBefore = [];
    for (i = 0; i < kids.length; i++) {
      var c = kids[i];
      if (used.indexOf(c) >= 0 || !drawnFrom.get(c)) continue;
      if (i < lastOwn && keyOf(drawnFrom.get(c))) { keptBefore.push(c); continue; }
      if (holdsPart(c, ctx)) { keptBefore.push(c); continue; }
      if (c.parentNode === live) live.removeChild(c);
    }
    // The page's own children, and rows kept so, stay after the child they followed.
    var after = {}, lead = [], anchor = null;
    for (i = 0; i < kids.length; i++) {
      var kid = kids[i];
      var stays = (!drawnFrom.get(kid) && used.indexOf(kid) < 0) || keptBefore.indexOf(kid) >= 0;
      if (stays) {
        if (anchor === null) lead.push(kid);
        else (after[anchor] = after[anchor] || []).push(kid);
      } else if (used.indexOf(kid) >= 0) {
        anchor = used.indexOf(kid);
      }
    }
    var order = lead.slice();
    for (i = 0; i < plan.length; i++) {
      order.push(plan[i]);
      var at = plan[i].node ? used.indexOf(plan[i].was || plan[i].node) : -1;
      if (at >= 0 && after[at]) order = order.concat(after[at]);
    }
    order = successorsAfter(order, keptBefore);
    var cur = live.firstChild;
    for (i = 0; i < order.length; i++) {
      var o = order[i];
      if (o && o.fresh) {
        var made = root.document.importNode(o.fresh, true);
        if (ctx.hold && keyOf(o.fresh) && (landsAbove(cur, live) || heldAfter(cur, ctx))) {
          made.setAttribute('data-nmas-new', '1');
          made.setAttribute('hidden', '');
        }
        live.insertBefore(made, cur);
        remember(made, o.fresh);
        continue;
      }
      var node = o.node || o;
      if (node === cur) cur = cur.nextSibling;
      else live.insertBefore(node, cur);
    }
  }

  /* The focused element before a merge, to give its focus back if the merge moved it. */
  function focusIn(region) {
    var a = root.document.activeElement;
    return a && a !== root.document.body && region.contains(a) ? {el: a, id: a.id} : null;
  }
  function giveFocusBack(was, region) {
    if (!was || root.document.activeElement === was.el) return;
    var el = was.el.isConnected ? was.el : (was.id ? root.document.getElementById(was.id) : null);
    if (el && region.contains(el) && el.focus) {
      try { el.focus({preventScroll: true}); } catch (x) { el.focus(); }
    }
  }

  /* "N new, show them": the rows a merge drew hidden above the window, counted in one quiet
     control fixed at the top of the window, which moves nothing on the page. Pressed, they are
     drawn and the window goes to the first of them. */
  function drawNewNote(region) {
    var waiting = region.querySelectorAll('[data-nmas-new]');
    var note = null;
    for (var i = 0; i < region.children.length; i++) {
      if (region.children[i].classList.contains('live-new')) { note = region.children[i]; break; }
    }
    if (!waiting.length) { if (note) region.removeChild(note); return; }
    if (!note) {
      note = root.document.createElement('div');
      note.className = 'live-new';
      note.setAttribute('role', 'status');
      var b = root.document.createElement('button');
      b.type = 'button';
      b.className = 'btn btn-small live-new-show';
      b.title = 'Drawn above where you are reading; shown when you ask, so the page does not move';
      note.appendChild(b);
      region.insertBefore(note, region.firstChild);
    }
    note.firstChild.textContent = waiting.length + NEW_WORDS;
  }
  function showNew(e) {
    var b = e.target && e.target.closest ? e.target.closest('.live-new-show') : null;
    if (!b) return;
    var region = b.parentNode.parentNode;
    var waiting = region.querySelectorAll('[data-nmas-new]');
    for (var i = 0; i < waiting.length; i++) {
      waiting[i].removeAttribute('data-nmas-new');
      waiting[i].removeAttribute('hidden');
    }
    region.removeChild(b.parentNode);
    if (waiting.length && waiting[0].scrollIntoView) waiting[0].scrollIntoView({block: 'start'});
  }

  /* htmx wires what a merge added (its hx- attributes) here, at once: handed back to htmx's
     settle instead, its `[autofocus]` step would take the focus from the person on every
     redraw. Elements left as they were are not wired twice (htmx compares their attributes). */
  function wire(els) {
    if (!root.htmx || !root.htmx.process) return;
    for (var i = 0; i < els.length; i++) if (els[i].isConnected) root.htmx.process(els[i]);
  }

  /* Merge an answer into its region: *outer* the region itself redrawn (its outerHTML), else
     its children (innerHTML). A region the page holds no copy of, or an answer that is not
     one element of the same kind, is replaced as htmx would have. Returns [] (htmx's settle has
     nothing left to wire). */
  function mergeRegion(outer, target, fragment, hold) {
    target.nmasMerged = true;
    var done = mergeInto(outer, target, fragment, hold);
    // Wired once the answer's own request has ended: a merged region is the element that
    // asked, and htmx drops a request (a redrawn card's `load`) from an element still asking.
    root.setTimeout(function () { wire(done); }, 0);
    return [];
  }

  function mergeInto(outer, target, fragment, hold) {
    var ctx = {hold: hold !== false, keep: heldParts(target), root: target};
    var kept = focusIn(target);
    var els = Array.prototype.filter.call(fragment.childNodes, function (n) { return n.nodeType === 1; });
    var next = els.length === 1 ? els[0] : null;
    merging = true;
    try {
      if (outer && (!next || !drawnFrom.get(target) || next.tagName !== target.tagName ||
                    (next.id || '') !== (target.id || '') ||
                    startsAgain(drawnFrom.get(target), next))) {
        var parent = target.parentNode, made = [];
        Array.prototype.slice.call(fragment.childNodes).forEach(function (n) {
          parent.insertBefore(n, target);
          if (n.nodeType === 1) { capture(n); made.push(n); }
        });
        parent.removeChild(target);
        return made;
      }
      if (outer) {
        morph(target, next, ctx);
      } else if (!drawnFrom.get(target)) {
        while (target.firstChild) target.removeChild(target.firstChild);
        target.appendChild(fragment);
        capture(target);
        return [target];
      } else {
        var copy = drawnFrom.get(target).cloneNode(false);
        Array.prototype.slice.call(fragment.childNodes).forEach(function (n) { copy.appendChild(n); });
        mergeChildren(target, copy, ctx);
        drawnFrom.set(target, copy);
      }
    } finally {
      merging = false;
    }
    // Ages and clocks are the page's to draw: drawn before the browser paints the merge.
    drawAges(target);
    drawClock(target);
    giveFocusBack(kept, target);
    drawNewNote(target);
    return [target];
  }

  /* A live answer merges (`htmx:beforeSwap`, after the holds have had their say). */
  /* PURE over a swap's detail: the merge's swap for a live answer to a region the page holds
     the server's copy of, or '' (any other swap is htmx's own). */
  function mergeSpec(d) {
    if (!d || !d.target || !drawnFrom || !isLiveUpdate(d) || !drawnFrom.get(d.target)) return '';
    var src = (d.requestConfig && d.requestConfig.elt) || d.elt || d.target;
    var holder = src.closest ? src.closest('[hx-swap]') : null;
    var spec = d.swapOverride || (holder ? holder.getAttribute('hx-swap') : '') || 'innerHTML';
    var parts = String(spec).split(/\s+/);
    if (parts[0] === 'outerHTML') parts[0] = MERGE_OUTER;
    else if (parts[0] === 'innerHTML') parts[0] = MERGE_INNER;
    else return '';
    return parts.join(' ');
  }
  function mergeLive(e) {
    var d = e.detail, spec = d && d.shouldSwap ? mergeSpec(d) : '';
    if (spec) d.swapOverride = spec;
  }

  function defineMerge() {
    if (!root.htmx || !root.htmx.defineExtension || !drawnFrom) return;
    root.htmx.defineExtension('nmas-merge', {
      handleSwap: function (style, target, fragment) {
        if (style !== MERGE_OUTER && style !== MERGE_INNER) return false;
        return mergeRegion(style === MERGE_OUTER, target, fragment);
      }
    });
    // The extension is asked for by the page's <body>: every swap starts from inside it.
    var b = root.document.body, ext = b.getAttribute('hx-ext');
    if (!ext || tokens(ext.replace(/,/g, ' ')).indexOf('nmas-merge') < 0) {
      b.setAttribute('hx-ext', ext ? ext + ',nmas-merge' : 'nmas-merge');
    }
  }

  /* The page's regions as the server drew them, before Alpine (the last deferred script) or
     htmx (at DOMContentLoaded) touches them: this file runs between the two. */
  if (root.document && root.document.body && drawnFrom) {
    captureRegions(root.document.body);
    defineMerge();
  }

  /* Boards AI1 and AI2 (C1843): the spend panel under the top bar's AI chip is read when it
     opens, and again on each recorded call (`ai_calls`) while it is open: never while it is
     closed (every page carries it) and never on a timer. A Turn off pressed in it is answered
     in it, and its `settings` re-reads the chip alone, so the answer stays to be read. */
  /* Opened by a person, it reads at once (`nmas-ai-open`); re-read on a recorded call while
     open, it is a live redraw (`nmas:ai_spend`), which the page-wide hold keeps from replacing
     what a person is typing in it (C2268: with no `nmas:` prefix the hold never applied). */
  function aiSpendPanel(e) {
    var doc = root.document, d = doc.getElementById('ai-spend');
    var panel = d && d.open ? doc.getElementById('nmas-ai-panel') : null;
    var live = !!(e && typeof e.type === 'string' && e.type.indexOf('nmas:') === 0);
    if (panel && root.htmx) root.htmx.trigger(panel, live ? 'nmas:ai_spend' : 'nmas-ai-open');
    return !!panel;
  }
  /* Board P7 (card P7, stage 1): the assistant's box takes the focus when its panel opens, and
     on the first opening once its head and body are drawn. */
  function focusAssistant() {
    var box = root.document.getElementById('asst-q');
    if (box && !box.disabled && box.offsetParent) box.focus();
  }
  function assistantDrawn(e) {
    if (e.target && e.target.id === 'asst-body') focusAssistant();
  }
  function aiSpendToggled(e) {
    if (e.target && e.target.id === 'ai-spend') aiSpendPanel();
  }
  /* C2056 (board AI2): a Needs attention row's "Open the spend panel" (`data-ai-open`, its href
     the panel's own fragment) opens the panel in place, as the chip does, and so does a page
     loaded with that fragment (the link opened in a new tab). Opening the <details> fires its
     `toggle`, which reads the panel (aiSpendPanel): one way in. Already open, there is no
     `toggle` to come, so it reads the panel itself: Firefox opens a <details> holding the
     fragment's target on its own, and that `toggle` can fire before htmx has wired the panel,
     its read lost (C2067). */
  var AI_PANEL_HASH = '#nmas-ai-panel';
  function aiSpendOpen() {
    var d = root.document.getElementById('ai-spend');
    if (!d) return false;
    if (d.open) return aiSpendPanel();
    d.open = true;
    return true;
  }
  function aiSpendOpenClicked(e) {
    var a = e.target && e.target.closest && e.target.closest('[data-ai-open]');
    if (!a) return;
    e.preventDefault();
    aiSpendOpen();
  }
  /* Esc, or the panel's own close, closes it and gives the chip its focus back. */
  function aiSpendClose(e) {
    var d = root.document.getElementById('ai-spend');
    if (!d || !d.open) return;
    var closing = e.type === 'keydown' ? e.key === 'Escape'
      : !!(e.target && e.target.closest && e.target.closest('[data-ai-close]'));
    if (!closing) return;
    d.open = false;
    var s = d.querySelector('summary');
    if (s && s.focus) s.focus();
  }

  /* The pause's words where the person is: in the open entry, under its summary (with Show it
     now), or beside the action in flight. One note per region; the reason it names is the
     current one. */
  function notePaused(region, why) {
    var old = region.querySelectorAll('.held-note');
    for (var i = 0; i < old.length; i++) old[i].parentNode.removeChild(old[i]);
    var note = root.document.createElement('p');
    note.className = 'held-note';
    note.setAttribute('role', 'status');
    note.setAttribute('data-held-why', why);
    var words = root.document.createElement('span');
    words.textContent = why === 'open' ? PAUSED_WORDS : (why === 'review' ? REVIEW_WORDS
                                                                           : SENDING_WORDS);
    note.appendChild(words);
    if (why === 'open' || why === 'review') {
      var button = root.document.createElement('button');
      button.type = 'button';
      button.className = 'btn btn-small btn-outline held-resume';
      button.textContent = 'Show it now';
      button.title = why === 'open'
        ? 'Redraws the list now; the entries open now stay open and load again'
        : 'Redraws the page now: this card closes, and nothing is sent';
      note.appendChild(root.document.createTextNode(' '));
      note.appendChild(button);
    }
    if (why === 'open') {
      var entry = openedIn(region);
      var summary = entry.querySelector('summary');
      if (summary && summary.nextSibling) entry.insertBefore(note, summary.nextSibling);
      else entry.appendChild(note);
    } else if (why === 'review') {
      var card = reviewedIn(region);
      card.insertBefore(note, card.firstChild);
    } else {
      var at = sendingIn(region);
      (at.parentNode || region).insertBefore(note, at.nextSibling);
    }
  }

  /* Ask a held region again: the redraw it skipped. Its open entries are noted first, so the
     redraw opens them again. */
  function redrawHeld(region, pressed) {
    region.removeAttribute('data-held');
    var notes = region.querySelectorAll('.held-note');
    for (var j = 0; j < notes.length; j++) {
      // The note whose Show it now was pressed stays, busy on itself, until the redraw lands.
      if (pressed && notes[j].contains(pressed)) continue;
      notes[j].parentNode.removeChild(notes[j]);
    }
    var url = region.getAttribute('hx-get');
    if (url && root.htmx) {
      // A hold that ended by itself merges, as a live redraw does (C2810); Show it now redraws
      // the region whole, as its words say (the card under review closes).
      var swap = region.getAttribute('hx-swap') || 'outerHTML';
      if (!pressed && drawnFrom && drawnFrom.get(region)) {
        swap = swap.replace(/^outerHTML/, MERGE_OUTER).replace(/^innerHTML/, MERGE_INNER);
      }
      var asked = root.htmx.ajax('GET', url, {target: region, swap: swap});
      if (pressed && asked && asked.then) {
        // A redraw that did not land (the region is still this one) leaves the hold as it
        // was and the button pressable again; the failure is said by `neverSilent`.
        var settle = function () {
          if (!pressed.isConnected) return;
          pressed.disabled = false;
          pressed.removeAttribute('aria-busy');
          pressed.textContent = 'Show it now';
          if (holdReason(region)) region.setAttribute('data-held', '1');
        };
        asked.then(settle, settle);
      }
    }
  }

  /* Once nothing holds a held region (no editing, no action in flight, no entry open), ask
     for it again; while a reason remains, its note says the current one. */
  function releaseHeld() {
    var held = root.document.querySelectorAll('[data-held="1"]');
    for (var i = 0; i < held.length; i++) {
      var region = held[i], why = holdReason(region);
      if (!why) { redrawHeld(region); continue; }
      var note = region.querySelector('.held-note');
      var noted = note ? (note.getAttribute('data-held-why') || 'editing') : '';
      if (noted !== why && why !== 'editing') notePaused(region, why);
    }
  }

  /* Show it now: the person asks for the newer list while an entry is open. Refused while an
     action in the region is in flight: its answer would have nowhere to land. */
  function resumeHeld(e) {
    var b = e.target && e.target.closest ? e.target.closest('.held-resume') : null;
    if (!b) return;
    var region = b.closest('[data-held="1"]');
    if (!region || sendingIn(region) || editingIn(region)) return;
    // Busy on itself until the redraw answers (C2001).
    b.disabled = true;
    b.setAttribute('aria-busy', 'true');
    b.textContent = 'Showing…';
    redrawHeld(region, b);
  }

  function drawAges(scope) {
    var list = (scope || root.document).querySelectorAll('time[data-age]');
    var now = Date.now();
    for (var i = 0; i < list.length; i++) {
      var t = Date.parse(list[i].getAttribute('data-age'));
      if (t === t) list[i].textContent = ageWords(t, now);
    }
  }

  /* The AI day cap's reset (`calls.reset_info`, `resets()` in _macros.html): the one instant
     the counter turns over at, in the viewer's own time and zone ("18:00 MDT"); the server's
     words (the boundary zone's time) stay until this runs. */
  /* A moment in the viewer's own time: "19:00 MDT", or with its date ("Oct 31 19:00 MDT")
     when the element says data-clock="date" (a moment days away: C2084's provider limit). */
  function clockWords(t, withDate) {
    var opts = {hour: '2-digit', minute: '2-digit', hour12: false, timeZoneName: 'short'};
    if (withDate) { opts.month = 'short'; opts.day = 'numeric'; }
    try {
      return new Intl.DateTimeFormat('en-US', opts).format(new Date(t)).replace(',', '');
    } catch (e) {
      return null;
    }
  }

  function drawClock(scope) {
    var list = (scope || root.document).querySelectorAll('time[data-clock]');
    for (var i = 0; i < list.length; i++) {
      var t = Date.parse(list[i].getAttribute('datetime'));
      var words = t === t ? clockWords(t, list[i].getAttribute('data-clock') === 'date') : null;
      if (words) list[i].textContent = words;
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

  /* PURE: the keys the regions drawn IN FLIGHT listen for, each once, from their hx-trigger
     values. A region in flight is one the server drew busy with a listener (`aria-busy="true"`
     and an `nmas:` trigger: a run still reading, a job still working). */
  function inFlightKeys(triggers) {
    var out = [], seen = {}, re = /nmas:([a-z_]+) from:body/g, m;
    for (var i = 0; i < (triggers || []).length; i++) {
      re.lastIndex = 0;
      while ((m = re.exec(triggers[i] || '')) !== null) {
        if (!seen[m[1]]) { seen[m[1]] = true; out.push(m[1]); }
      }
    }
    return out;
  }

  /* A page that loads holding a region IN FLIGHT is current only until that work ends, and
     its end is announced once. Announced before this page's channel first connected, it was
     never heard, and the region stayed "running" until a reload (C2988: a Show commands run
     that ended in the moment between its page being drawn and the channel connecting). So on
     the FIRST connect each key such a region listens for is relayed once: one re-read, made
     after the channel is hearing, so nothing later is missed. A page with nothing in flight
     asks nothing: a page just loaded is current (nmas_invalidation.js). Never a timer's read:
     it runs once, when the page's own tick first sees the channel connected. */
  var firstConnectSeen = false;
  function catchUpInFlight() {
    if (firstConnectSeen || !root.NMAS || !root.NMAS.live) return;
    if ((root.NMAS.live().state || '') !== 'connected') return;
    firstConnectSeen = true;
    var all = root.document.querySelectorAll('[aria-busy="true"][hx-trigger*="nmas:"]'), t = [];
    for (var i = 0; i < all.length; i++) t.push(all[i].getAttribute('hx-trigger'));
    var keys = inFlightKeys(t);
    for (var k = 0; k < keys.length; k++) relay(keys[k]);
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
  function relayScheduledJobs() { relay('scheduled_jobs'); }
  function relayCiAgreement() { relay('ci_agreement'); }
  function relayAppVersion() { relay('app_version'); }
  function relayNetbox() { relay('netbox'); }
  function relayRemote() { relay('remote'); }
  function relayBaselines() { relay('baselines'); }
  function relayDeployJob() { relay('deploy_job'); }
  function relayGoldens() { relay('goldens'); }
  function relayAdjacencies() { relay('adjacencies'); }
  function relayRestarts() { relay('restarts'); }
  // A fault drill declared (modules/fault_drills.py): History draws each declaration.
  function relayFaultDrills() { relay('fault_drills'); }
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
  function relayDiagnosis() { relay('diagnosis'); }
  function relayPersistRead() { relay('persist_read'); }
  function relayFleetChange() { relay('fleet_change'); }
  function relayDeviceProgress() { relay('device_progress'); }
  function relayTemplates() { relay('templates'); }
  function relaySave() { relay('save'); }
  function relayCredentials() { relay('credentials'); }
  function relayTopology() { relay('topology'); }
  function relayLogs() { relay('logs'); }
  function relayDhcp() { relay('dhcp'); }
  function relaySdn() { relay('sdn'); }
  function relayControllerDeploy() { relay('controller_deploy'); }
  function relayNsotExport() { relay('nsot_export'); }
  function relayCodeRepo() { relay('code_repo'); }
  function relaySavedViews() { relay('saved_views'); }
  function relayDiscovery() { relay('ztp_discovery'); }
  function relayPathTrace() { relay('path_trace'); }
  function relayReveals() { relay('reveals'); }
  function relayAiCalls() { relay('ai_calls'); }
  function relayAiFeedback() { relay('ai_feedback'); }
  function relayNotifications() { relay('notifications'); }
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

  /* NEVER A FROZEN PAGE SHOWN AS CURRENT (C2003, the operator's Lab 8 walk, 2026-10-28: SDN ›
     Responses stopped updating and looked current). A live region's `.stale-note` carries the
     moment its drawing passes its promise (data-stale-at) and the promise (data-promise, in
     seconds), as the sidebar's count does; the page's one-second tick judges it, asking
     nothing. Not live yet (the first connect) is not a doubt: a page just loaded is current. */
  var NOT_LIVE = {disconnected: 1, silent: 1, failed: 1};
  /* What holds a redraw (`holdReason`), and what the person does to let it through. */
  var HELD_FOR = {review: ['the card open below', 'Send or close it'],
                  editing: ['what you are typing', 'Send or clear it'],
                  sending: ['the action in flight', 'Wait for its answer'],
                  open: ['the entry open below', 'Close it']};

  /* PURE: what a live region's note says after its "Last updated <age>", from the live
     channel's state, the moment its drawing passes its promise, the promise in seconds, now,
     why a redraw of it is held (`holdReason`, '' when nothing holds it), and whether a redraw
     already arrived and was held (the region's data-held). null when it is current; otherwise
     {words, reload}. Reload is offered only when nothing holds the region: a reload would
     close what holds it, the step HITL exists for (C2001). */
  function staleNote(liveState, staleAtMs, promiseS, nowMs, holdWhy, skipped) {
    var down = !!NOT_LIVE[liveState];
    var late = staleAtMs === staleAtMs && staleAtMs !== null && nowMs > staleAtMs;
    if (!down && !late) return null;
    var held = holdWhy ? HELD_FOR[holdWhy] || HELD_FOR.review : null;
    if (held && skipped && !down) {
      return {words: ': newer data is waiting, held for ' + held[0] + '. ' + held[1]
                + ' to see it.', reload: false};
    }
    var cause = down ? liveWords(liveState).toLowerCase()
      : 'no update has arrived in ' + (promiseS > 0 ? 'the ' + promiseS + ' s it promises'
                                                    : 'the time it promises');
    if (held) {
      return {words: ': ' + cause + ', so this page may be out of date; a reload would close '
                + held[0] + '. ' + held[1] + ' first.', reload: false};
    }
    return {words: ': ' + cause + ', so this page may be out of date.', reload: true};
  }

  /* This tab's own id, kept for the tab's life (sessionStorage), so the stalls of one tab can
     be told from another's; '' when storage is refused (a private window). */
  function tabId() {
    try {
      var id = root.sessionStorage.getItem('nmas-tab');
      if (!id) {
        id = Math.random().toString(36).slice(2, 10) + Date.now().toString(36);
        root.sessionStorage.setItem('nmas-tab', id);
      }
      return id;
    } catch (e) { return ''; }
  }

  /* PURE: a stall's record as the page sends it (C2003; `stall_capture.PAGE_FIELDS` and
     `LIVE_FIELDS`): the page, the tab, when the note was shown, the drawing's time and
     promise, what the note says, the region and whether a redraw is held, the live
     connection's detail, and the last 20 live events (`NMAS.log()`). */
  function stallBody(page, tab, nowMs, drawnAt, staleAt, promiseS, words, regionId, held,
                     live, events) {
    return {page: {page: page, tab: tab, shown_at: new Date(nowMs).toISOString(),
                   drawn_at: drawnAt || '', stale_at: staleAt || '', promise_s: promiseS,
                   words: words, region: regionId || '', held: held || ''},
            live: live, events: (events || []).slice(-20)};
  }

  /* THE STALL CAPTURES ITSELF (C2003, the operator, 2026-11-02: "no live catching by me"):
     posted the moment a stale note is shown, to the record History's "Page stalls" reads.
     Fire and forget: a post that fails is said in the console, never on the page. */
  function reportStall(note, said, region, nowMs) {
    var N = root.NMAS;
    if (!root.fetch || !N || !N.liveDetail) return;
    var time = note.querySelector ? note.querySelector('time') : null;
    var body = stallBody(root.location.pathname + root.location.search, tabId(), nowMs,
                         time ? time.getAttribute('datetime') : '',
                         note.getAttribute('data-stale-at'),
                         parseInt(note.getAttribute('data-promise') || '0', 10),
                         said.words, region ? region.id : '', region ? holdReason(region) : '',
                         N.liveDetail(), N.log ? N.log() : []);
    root.fetch('/v2/diagnostics/stall', {
      method: 'POST', keepalive: true,
      headers: {'Content-Type': 'application/json', 'Accept': 'application/json'},
      body: JSON.stringify(body)
    }).then(function (r) {
      if (!r.ok && root.console) root.console.warn('NMAS: the stall was not recorded: ' + r.status);
    }, function (e) {
      if (root.console) root.console.warn('NMAS: the stall was not recorded: ' + e);
    });
  }

  /* Each live region's stale note, drawn from `staleNote`; the DOM is touched only when what
     it says changes. Run on the frame's one-second tick. */
  function drawStale() {
    var notes = root.document.querySelectorAll('.stale-note[data-stale-at]');
    if (!notes.length) return;
    var now = Date.now();
    var live = root.NMAS && root.NMAS.live ? (root.NMAS.live().state || '') : '';
    for (var i = 0; i < notes.length; i++) {
      var note = notes[i];
      var region = note.parentNode && note.parentNode.closest
        ? note.parentNode.closest('[hx-trigger]') : null;
      var at = Date.parse(note.getAttribute('data-stale-at') || '');
      var said = staleNote(live, at === at ? at : null,
                           parseInt(note.getAttribute('data-promise') || '0', 10), now,
                           region ? holdReason(region) : '',
                           !!region && region.getAttribute('data-held') === '1');
      var key = said ? said.words + (said.reload ? ' |reload' : '') : '';
      if ((note.getAttribute('data-said') || '') === key) continue;
      note.setAttribute('data-said', key);
      // C2003: the moment it is SHOWN (hidden until now), the stall records itself, once.
      if (said && note.hidden) reportStall(note, said, region, now);
      note.hidden = !said;
      if (!said) continue;
      var why = note.querySelector('.stale-why');
      if (why) why.textContent = said.words;
      var reload = note.querySelector('.stale-reload');
      if (reload) reload.hidden = !said.reload;
    }
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
    NMAS.subscribe('scheduled_jobs', 'v2ScheduledJobs', relayScheduledJobs);
    NMAS.subscribe('ci_agreement', 'v2CiAgreement', relayCiAgreement);
    NMAS.subscribe('app_version', 'v2AppVersion', relayAppVersion);
    NMAS.subscribe('netbox', 'v2Netbox', relayNetbox);
    NMAS.subscribe('remote', 'v2Remote', relayRemote);
    NMAS.subscribe('baselines', 'v2Baselines', relayBaselines);
    NMAS.subscribe('deploy_job', 'v2DeployJob', relayDeployJob);
    NMAS.subscribe('goldens', 'v2Goldens', relayGoldens);
    NMAS.subscribe('adjacencies', 'v2Adjacencies', relayAdjacencies);
    NMAS.subscribe('restarts', 'v2Restarts', relayRestarts);
    NMAS.subscribe('fault_drills', 'v2FaultDrills', relayFaultDrills);
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
    NMAS.subscribe('diagnosis', 'v2Diagnosis', relayDiagnosis);
    NMAS.subscribe('persist_read', 'v2PersistRead', relayPersistRead);
    NMAS.subscribe('fleet_change', 'v2FleetChange', relayFleetChange);
    NMAS.subscribe('device_progress', 'v2DeviceProgress', relayDeviceProgress);
    NMAS.subscribe('templates', 'v2Templates', relayTemplates);
    NMAS.subscribe('save', 'v2Save', relaySave);
    NMAS.subscribe('credentials', 'v2Credentials', relayCredentials);
    NMAS.subscribe('topology', 'v2Topology', relayTopology);
    NMAS.subscribe('logs', 'v2Logs', relayLogs);
    NMAS.subscribe('dhcp', 'v2Dhcp', relayDhcp);
    NMAS.subscribe('sdn', 'v2Sdn', relaySdn);
    NMAS.subscribe('controller_deploy', 'v2ControllerDeploy', relayControllerDeploy);
    NMAS.subscribe('nsot_export', 'v2NsotExport', relayNsotExport);
    NMAS.subscribe('code_repo', 'v2CodeRepo', relayCodeRepo);
    NMAS.subscribe('saved_views', 'v2SavedViews', relaySavedViews);
    NMAS.subscribe('ztp_discovery', 'v2Discovery', relayDiscovery);
    NMAS.subscribe('path_trace', 'v2PathTrace', relayPathTrace);
    NMAS.subscribe('reveals', 'v2Reveals', relayReveals);
    NMAS.subscribe('ai_calls', 'v2AiCalls', relayAiCalls);
    NMAS.subscribe('ai_feedback', 'v2AiFeedback', relayAiFeedback);
    NMAS.subscribe('notifications', 'v2Notifications', relayNotifications);
    NMAS.subscribe('lists', 'v2Lists', relayLists);
    NMAS.subscribe('active_list', 'v2ActiveList', relayActiveList);
    NMAS.subscribe('posture', 'v2Posture', relayPosture);
    NMAS.subscribe('breakglass', 'v2Breakglass', relayBreakglass);
    NMAS.subscribe('in_progress', 'v2InProgress', relayInProgress);
    NMAS.subscribe('console_ztp', 'v2ConsoleZtp', relayConsoleZtp);
    NMAS.subscribe('console_servers', 'v2ConsoleServers', relayConsoleServers);
  }

  /* One click on the device page's Deploy (C1434, the operator's bar of 2026-10-26: a Why
     typed and Deploy pressed at once must send that Why). A reason field re-planned on its
     change, and the press itself caused that change (the field's blur on the button's
     mousedown): the redrawn card replaced the button before its click, or the click posted
     the authorisations planned before the Why. Now a reason field marked
     `data-sent-by-deploy` plans nothing as it changes; Deploy (`button[data-needs]`) is
     offered once every reason field it names holds text, and pressed it carries the card's
     form, so the server plans again with the reasons as typed and sends only the program the
     card drew (routes/device_v2.py `deploy_confirm`). The card is never redrawn while a
     person types, so their focus and caret stay where they are. */
  function reasonPlansAtDeploy(e) {
    var d = (e && e.detail) || {}, ev = d.triggeringEvent, t = ev && ev.target;
    if (ev && ev.type === 'change' && t && t.hasAttribute && t.hasAttribute('data-sent-by-deploy')) {
      e.preventDefault();
    }
  }
  /* PURE over the DOM: whether every field *button*'s `data-needs` names, inside *card*, holds
     text. A field the card does not draw is missing, never given. */
  function reasonsTyped(button, card) {
    var names = (button.getAttribute('data-needs') || '').split(/\s+/);
    for (var i = 0; i < names.length; i++) {
      if (!names[i]) continue;
      var f = card.querySelector('[name="' + names[i].replace(/"/g, '') + '"]');
      if (!f || !(f.value || '').trim()) return false;
    }
    return true;
  }
  /* A Deploy drawn waiting (`data-waits`) is already the confirm pattern, disabled: offered,
     it is marked the confirm (`op-confirm`) as the server marks an offered one. */
  function offerDeploy(b) {
    b.classList.add('op-confirm');
  }
  /* PURE over the DOM: whether *card* draws a check that blocks its Deploy: one failing, or
     one that could not be read again (C1847: a failing check and an enabled Deploy never
     appear together). */
  function checksBlock(card) {
    return !!card.querySelector('#deploy-checks [data-gate="fail"], #deploy-checks [data-gate="unread"]');
  }
  function drawDeploys(scope) {
    if (!scope || !scope.querySelectorAll) return;
    var list = scope.querySelectorAll('button[data-needs]');
    for (var i = 0; i < list.length; i++) {
      var b = list[i], card = b.closest('.op-card');
      if (!card || b.classList.contains('htmx-request')) continue;
      var typed = reasonsTyped(b, card), waits = b.hasAttribute('data-waits');
      var offered = typed && !checksBlock(card);
      if (offered && waits) offerDeploy(b);
      if (!offered && waits) b.classList.remove('op-confirm');
      if (waits || !b.hasAttribute('data-refused')) b.disabled = !offered;
      var ready = card.querySelector('#deploy-ready'), wait = card.querySelector('#deploy-waits');
      if (waits && ready && wait) {
        ready.hidden = !offered;
        wait.hidden = offered;
        b.setAttribute('aria-describedby', offered ? 'deploy-ready' : 'deploy-waits');
      }
    }
  }

  /* The checks follow the reasons as they are typed (C1847, the operator's Mode B re-walk of
     2026-10-27: "lines needing a reason: fail" and "Authorised lines 0" were drawn beside an
     enabled Deploy). A reason typed plans the card again REPLAN_MS after the last key, and
     only what the reasons decide is drawn again: the checks, the operands and the
     authorisation note. The fields keep their focus and caret and Deploy stays the same
     element, so a press is never lost (C1434). Until that plan answers, the reason's check
     and "authorised lines" read "checking", never the fail or pass drawn before the key: a
     press then plans again with the reasons as typed and sends only the program drawn (the
     guard, routes/device_v2.py `deploy_confirm`). A plan whose program moved since the card
     drew it, or that is not this card's shape, draws the whole card again, as a ticked box
     does. A plan that does not answer says so on the check, and Deploy waits. */
  var REPLAN_MS = 300;
  var REPLAN_REGIONS = ['deploy-checks', 'deploy-operands', 'deploy-auth-note'];
  var replans = [];
  function replanOf(card) {
    for (var i = 0; i < replans.length; i++) if (replans[i].card === card) return replans[i];
    var r = {card: card, timer: null, ctl: null, seq: 0};
    replans.push(r);
    return r;
  }
  function stopReplan(card) {
    for (var i = 0; i < replans.length; i++) {
      var r = replans[i];
      if (card && r.card !== card) continue;
      if (r.timer) root.clearTimeout(r.timer);
      if (r.ctl) r.ctl.abort();
      r.timer = null; r.ctl = null; r.seq++;
    }
    replans = replans.filter(function (r) { return r.card.isConnected && r.card !== card; });
  }
  function drawGate(li, state, kind, words, why) {
    li.setAttribute('data-gate', state);
    var badge = li.querySelector('.badge');
    if (badge) { badge.className = 'badge badge-' + kind; badge.textContent = words; }
    if (why !== undefined) li.title = why;
  }
  function markChecking(card) {
    var li = card.querySelector('#deploy-checks [data-reason-gate]');
    if (li) drawGate(li, 'checking', 'info', 'checking', 'Checked again with your reasons as typed');
    var dd = card.querySelector('#deploy-operands [data-operand="authorised lines"]');
    if (dd) dd.textContent = 'checking';
    var note = card.querySelector('#deploy-auth-note');
    if (note) note.hidden = true;
  }
  function programOf(card) {
    var b = card && card.querySelector('button[data-op="deploy"][hx-vals]');
    try {
      var shown = JSON.parse(JSON.parse(b.getAttribute('hx-vals')).shown || '{}');
      return shown.program_hash || '';
    } catch (x) { return ''; }
  }
  function replanReasons(card) {
    var form = card.querySelector('.op-form'), r = replanOf(card);
    if (!form || !root.fetch) return;
    var seq = ++r.seq, ctl = root.AbortController ? new root.AbortController() : null;
    r.ctl = ctl;
    // The form's own values joined to its URL's query as htmx joins them for a GET.
    var url = form.getAttribute('hx-get'), q = new root.URLSearchParams(new root.FormData(form)).toString();
    root.fetch(url + (url.indexOf('?') >= 0 ? '&' : '?') + q, {
      headers: {'HX-Request': 'true', 'HX-Target': 'device-op', 'Accept': 'text/html'},
      signal: ctl ? ctl.signal : undefined
    }).then(function (resp) {
      return resp.text().then(function (body) { return [resp, body]; });
    }).then(function (got) {
      if (seq !== r.seq || !card.isConnected) return;
      r.ctl = null;
      var resp = got[0], body = got[1];
      if (!resp.ok || !isFragment(body, resp.headers.get('Content-Type'))) {
        throw new Error(failWords(resp.status, resp.statusText, body, resp.headers.get('Content-Type')) ||
                        ('the server answered ' + resp.status));
      }
      var next = new root.DOMParser().parseFromString(body, 'text/html').getElementById('device-op');
      var whole = !next || REPLAN_REGIONS.some(function (id) {
        return !card.querySelector('#' + id) || !next.querySelector('#' + id);
      });
      var was = programOf(card), now = programOf(next);
      if (whole || (was && now && was !== now)) {
        // Not this card's shape, or its program moved: the whole card, as a ticked box plans.
        if (root.htmx) root.htmx.trigger(form, 'change');
        return;
      }
      REPLAN_REGIONS.forEach(function (id) {
        card.querySelector('#' + id).replaceWith(card.ownerDocument.importNode(next.querySelector('#' + id), true));
      });
      drawDeploys(card);
    }).catch(function (e) {
      if (seq !== r.seq || !card.isConnected || (e && e.name === 'AbortError')) return;
      r.ctl = null;
      var li = card.querySelector('#deploy-checks [data-reason-gate]');
      if (li) {
        drawGate(li, 'unread', 'warn', "couldn't check");
        var span = li.querySelector('span:not(.badge)');
        if (span) span.textContent = "Couldn't load: the checks with your reasons (" +
          ((e && e.message) || 'no answer') + '). Type again to check again.';
      }
      drawDeploys(card);
    });
  }
  function reasonTyped(e) {
    var t = e && e.target;
    if (!t || !t.hasAttribute || !t.hasAttribute('data-sent-by-deploy')) return;
    var card = t.closest && t.closest('.op-card');
    if (!card || !card.querySelector('#deploy-checks')) return;
    var r = replanOf(card);
    if (r.timer) root.clearTimeout(r.timer);
    if (r.ctl) { r.ctl.abort(); r.ctl = null; }
    r.seq++;
    markChecking(card);
    r.timer = root.setTimeout(function () { r.timer = null; replanReasons(card); }, REPLAN_MS);
  }
  /* Deploy pressed, or the card replaced: a plan of the reasons still to come is dropped, so
     it never draws over the press's own answer. */
  function replanStops(e) {
    var elt = e && e.detail && e.detail.elt, card = elt && elt.closest && elt.closest('.op-card');
    if (card) stopReplan(card);
  }
  function drawDeployOf(e) {
    var card = e && e.target && e.target.closest && e.target.closest('.op-card');
    if (card) drawDeploys(card);
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
        // The toolbar assistant's panel (board P7, card P7 stage 1), in the help panel's place:
        // one of the two side panels at a time.
        asst: false,
        // At phone width the go-to box is its button (board B, C537): open or not.
        jumpOpen: false,
        get drawerClass() { return this.drawer ? 'open' : ''; },
        get jumpClass() { return this.jumpOpen ? 'open' : ''; },
        get jumpExpanded() { return this.jumpOpen ? 'true' : 'false'; },
        open: function () { this.drawer = true; },
        close: function () { this.drawer = false; this.help = false; this.asst = false; },
        openHelp: function () { this.asst = false; this.help = true; },
        closeHelp: function () { this.help = false; this.jumpOpen = false; },
        // Esc closes whichever side panel is open (one handler: the CSP build of Alpine runs a
        // method by name, never two calls in one expression).
        closeSides: function () { this.closeHelp(); this.asst = false; },
        // The panel's head and body are asked the first time it opens on a page (`once` on
        // #asst-body); its box takes the focus once drawn (assistantDrawn, below).
        openAssistant: function () {
          this.help = false;
          this.asst = true;
          this.$nextTick(function () {
            var body = root.document.getElementById('asst-body');
            if (body && root.htmx) root.htmx.trigger(body, 'nmas-asst-open');
            focusAssistant();
          });
        },
        closeAssistant: function () { this.asst = false; },
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
    // Topology › Path…'s Flow tables form (docs/boards/sdn-trace.html, artboard A): Port is
    // off while the protocol is an ICMP echo, which has no port, so a disabled field sends
    // nothing. The server draws the same state first (no script: the field as drawn).
    A.data('ofproto', function () {
      return {
        proto: 'icmp',
        init: function () { this.proto = this.$el.getAttribute('data-proto') || 'icmp'; },
        get noPort() { return this.proto === 'icmp'; },
        get portHint() { return this.proto === 'icmp' ? 'no port' : '1 to 65535'; }
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
          focusWhenShown(box, FOCUS_TRIES);
        },
        cancel: function () { if (this.busy) return; this.isOpen = false; this.said = ''; },
        send: function () {
          var self = this, el = this.$root, box = el.querySelector('input[name="why"]');
          // A disposition, where the row asks one (C2295: lines withheld as instructions).
          var pick = el.querySelector('select[name="disposition"]');
          // A planned quiet period's hours, where a band row offers one (C2316).
          var hours = el.querySelector('select[name="hours"]');
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
                                  why: box ? box.value : '', disposition: pick ? pick.value : '',
                                  hours: hours ? hours.value : ''}),
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
      // C2267: a LIVE redraw (an announcement's) that is answered with an error keeps what the
      // region shows and says it could not be read: swapping in the error's fragment would
      // replace the region with a notice that has no listener, so it would never update again.
      // A person's own request still swaps its error, since that answer is what they asked.
      if (!isFragment(body, type) || isLiveUpdate(d)) {
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

  /* Explain's citations as chips (_explain.html's `cited`; board AlertsExplain revised
     2026-10-29, "the answer card first"): a chip is a link to its pack piece's id, so it
     works with no script; with it, pressing the chip (a click, or Enter on it) opens every
     collapsed section holding the piece, scrolls to it, highlights it (the piece highlighted
     before loses it) and gives it the focus. PURE: the id a chip's href names, '' for any
     href that is not this page's own fragment. */
  function citeTarget(href) {
    if (!href || href.charAt(0) !== '#' || href.length < 2) return '';
    try { return decodeURIComponent(href.slice(1)); } catch (e) { return href.slice(1); }
  }

  /* Over *doc* (the page, or a stand-in in the tests): the piece with id *id* shown, as
     above. False, with nothing changed, when no such piece is on the page. */
  function jumpToCite(doc, id) {
    var el = id ? doc.getElementById(id) : null;
    if (!el) return false;
    for (var p = el; p && p !== doc; p = p.parentNode) {
      if (p.tagName === 'DETAILS' && !p.open) p.open = true;
    }
    var was = doc.querySelectorAll('.cite-hit');
    for (var i = 0; i < was.length; i++) was[i].classList.remove('cite-hit');
    el.classList.add('cite-hit');
    if (!el.getAttribute('tabindex')) el.setAttribute('tabindex', '-1');
    if (el.scrollIntoView) el.scrollIntoView({block: 'center'});
    if (el.focus) el.focus({preventScroll: true});
    return true;
  }

  function citeClicked(e) {
    // An SDN piece's own references (_evidence_pack.html's `cite`) jump the same way, and so
    // does a Needs attention row's Review the fix… (`att-jump`, board H artboard D): its row
    // opened, which loads the proposal's card, and the card focused.
    var a = e.target && e.target.closest ? e.target.closest('a.cite-chip, a.pack-cite, a.att-jump') : null;
    if (!a) return;
    if (jumpToCite(root.document, citeTarget(a.getAttribute('href')))) e.preventDefault();
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
      if (root.location && root.location.hash === AI_PANEL_HASH) aiSpendOpen();
      wireAnnouncements();
      drawAges();
      drawClock();
      drawLive();
      drawBadge();
      drawStale();
      drawDeploys(root.document);
      applyRemembered(root.document);
      root.setInterval(function () { drawLive(); catchUpInFlight(); drawBadge(); releaseHeld(); drawStale(); }, 1000);
      root.setInterval(function () { drawAges(); }, 15000);
    });
    root.document.addEventListener('htmx:afterSettle', function (e) { drawAges(e.target); drawClock(e.target); drawDeploys(e.target); catchUpMissed(e); reopenKept(); applyRemembered(root.document); });
    root.document.addEventListener('click', rememberToggle);
    root.document.addEventListener('htmx:confirm', reasonPlansAtDeploy);
    root.document.addEventListener('input', reasonTyped);   // before: it marks the checks drawDeployOf reads
    root.document.addEventListener('input', drawDeployOf);
    root.document.addEventListener('htmx:beforeRequest', replanStops);
    root.document.addEventListener('change', drawDeployOf);
    root.document.addEventListener('htmx:beforeSwap', rememberOpen);
    root.document.addEventListener('htmx:beforeRequest', noteAsked);
    root.document.addEventListener('htmx:beforeRequest', markTab);
    root.document.addEventListener('htmx:beforeRequest', noteSending);
    root.document.addEventListener('htmx:afterRequest', noteSent);
    root.document.addEventListener('htmx:configRequest', keyThePress);
    root.document.addEventListener('click', resumeHeld);
    root.document.addEventListener('click', citeClicked);
    // `toggle` does not bubble: heard in the capture phase.
    root.document.addEventListener('toggle', aiSpendToggled, true);
    root.document.addEventListener('nmas:ai_calls', aiSpendPanel);
    root.document.addEventListener('keydown', aiSpendClose);
    root.document.addEventListener('click', aiSpendClose);
    root.document.addEventListener('click', aiSpendOpenClicked);
    root.document.addEventListener('htmx:afterSettle', assistantDrawn);
    root.document.addEventListener('htmx:beforeSend', holdSubmitter);
    root.document.addEventListener('htmx:afterRequest', releaseSubmitter);
    root.document.addEventListener('htmx:beforeSwap', neverSilent);
    root.document.addEventListener('htmx:beforeSwap', holdWhileEditing);  // after: the last word on a swap
    root.document.addEventListener('htmx:beforeSwap', mergeLive);         // a swap the holds let through merges
    root.document.addEventListener('htmx:afterSwap', captureSwapped);
    root.document.addEventListener('htmx:oobAfterSwap', captureOob);
    root.document.addEventListener('htmx:oobBeforeSwap', mergeOob);
    root.document.addEventListener('htmx:beforeRequest', noteLiveAsk);
    root.document.addEventListener('click', showNew);
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
                  focusWhenShown: focusWhenShown, FOCUS_TRIES: FOCUS_TRIES,
                  badgeDoubt: badgeDoubt, staleNote: staleNote, missedKeys: missedKeys,
                  inFlightKeys: inFlightKeys,
                  stallBody: stallBody,
                  isFragment: isFragment,
                  failWords: failWords, couldntWords: couldntWords, injectedScripts: injectedScripts,
                  rewrittenWords: rewrittenWords, openKeys: openKeys, submitterOf: submitterOf,
                  reasonsTyped: reasonsTyped, holdReason: holdReason, pressKey: pressKey,
                  citeTarget: citeTarget, jumpToCite: jumpToCite,
                  // C2810's merge, for its tests in a real browser.
                  keyOf: keyOf, capture: capture, mergeInto: mergeInto};
})(typeof window !== 'undefined' ? window : this);
