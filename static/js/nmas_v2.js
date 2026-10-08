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
              // The lab startup files against the goldens (modules/lab_startup.py).
              'lab_startup',
              // A device restart, planned or not (modules/restarts.py).
              'restarts',
              // A person acknowledged an event row (modules/acknowledgements.py).
              'acknowledgements',
              // What else moves a Needs attention row (attention.SOURCE_KEYS).
              'approvals', 'device_state', 'intent', 'inventory', 'pending', 'rolled_back',
              // A capture preview's reads finished (modules/nsot/capture_job.py): the
              // device page's Capture card reads its preview (7.3).
              'capture_preview',
              // An operation the app ran released a device: a card refused because it was
              // held reads again (modules/nsot/device_ops.py); and a rotation's job finished.
              'device_holds', 'rotation', 'credential_health',
              // A Tier 2 run finished (modules/nsot/privileged.py): its card reads its record.
              'privileged',
              // Coverage's not-reporting cells: when each device's data last arrived.
              'coverage_reporting',
              // A held device's operation reached its next step: a running card redraws its
              // stepper (C370).
              'device_progress',
              // A template approved or revoked anywhere: the Templates table re-reads (C516).
              'templates'];

  /* PURE: the Acknowledge button's words, busy on itself. */
  function ackLabel(busy) { return busy ? 'Acknowledging…' : 'Acknowledge'; }

  /* PURE: a refused acknowledgement in words, from the status and the body. */
  function ackRefusal(status, body) {
    return 'Not acknowledged: ' + ((body && body.error) || ('HTTP ' + status));
  }

  /* PURE: what an answer does to the Acknowledge form (C533): a refusal says why and frees the
     button; a recorded acknowledgement that hides its row stays busy until the redraw removes
     the row; one recorded and NOT hiding it (a value above the band) says so, with both
     numbers, and frees the button. Never busy with nothing said once an answer is in. */
  function ackAnswer(status, body) {
    if (status !== 200 || !body || !body.ok) {
      return {busy: false, isOpen: true, said: ackRefusal(status, body), note: ''};
    }
    if (body.hides_now === false) {
      return {busy: false, isOpen: false, said: '', note: body.words || 'Recorded; the row stays.'};
    }
    return {busy: true, isOpen: true, said: '', note: ''};
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

  /* PURE: where the jump box goes, from its base path and what was typed. */
  function jumpTarget(base, typed) {
    var name = String(typed || '').replace(/^\s+|\s+$/g, '');
    return name ? base + encodeURIComponent(name) : '';
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
    var unit = (editing.closest && (editing.closest('[x-data]') || editing.parentNode)) || region;
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
  function relayLabStartup() { relay('lab_startup'); }
  function relayRestarts() { relay('restarts'); }
  function relayAcknowledgements() { relay('acknowledgements'); }
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
  function relayDeviceProgress() { relay('device_progress'); }
  function relayTemplates() { relay('templates'); }

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
    NMAS.subscribe('lab_startup', 'v2LabStartup', relayLabStartup);
    NMAS.subscribe('restarts', 'v2Restarts', relayRestarts);
    NMAS.subscribe('acknowledgements', 'v2Acknowledgements', relayAcknowledgements);
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
    NMAS.subscribe('device_progress', 'v2DeviceProgress', relayDeviceProgress);
    NMAS.subscribe('templates', 'v2Templates', relayTemplates);
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
        get drawerClass() { return this.drawer ? 'open' : ''; },
        open: function () { this.drawer = true; },
        close: function () { this.drawer = false; this.help = false; },
        openHelp: function () { this.help = true; },
        closeHelp: function () { this.help = false; },
        jump: function () {
          var form = this.$el.closest ? this.$el.closest('form') : this.$el;
          var box = form.querySelector('input[name="name"]');
          var target = jumpTarget(form.getAttribute('data-base'), box && box.value);
          if (target) root.location.assign(target);
        }
      };
    });
    A.data('copy', function () {
      return {
        copied: false,
        get label() { return this.copied ? 'Copied' : 'Copy'; },
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
    // recorded with who and when. Busy on itself; on success the response invalidates
    // `acknowledgements`, the list redraws and the row leaves it. Words only for a refusal.
    A.data('acknowledge', function () {
      return {
        isOpen: false, busy: false, said: '', note: '',
        get closed() { return !this.isOpen; },
        get label() { return ackLabel(this.busy); },
        open: function () {
          var box = this.$root.querySelector('input[name="why"]');
          this.isOpen = true; this.said = ''; this.note = '';
          if (box && box.focus) root.setTimeout(function () { box.focus(); }, 0);
        },
        cancel: function () { this.isOpen = false; this.said = ''; },
        send: function () {
          var self = this, el = this.$root, box = el.querySelector('input[name="why"]');
          self.busy = true;
          self.said = '';
          root.fetch(el.getAttribute('data-url'), {
            method: 'POST', headers: {'Content-Type': 'application/json', 'Accept': 'application/json'},
            body: JSON.stringify({row: el.getAttribute('data-row'), event: el.getAttribute('data-event'),
                                  why: box ? box.value : ''})
          }).then(function (r) {
            return r.json().then(function (b) { return [r.status, b]; }, function () { return [r.status, null]; });
          }).then(function (got) {
            var next = ackAnswer(got[0], got[1]);
            self.busy = next.busy; self.isOpen = next.isOpen;
            self.said = next.said; self.note = next.note;
          }, function (e) { self.busy = false; self.said = 'Not acknowledged: ' + e.message; });
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

  function sayCouldnt(target, control, reason) {
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
                  ackAnswer: ackAnswer,
                  badgeDoubt: badgeDoubt, missedKeys: missedKeys, isFragment: isFragment,
                  failWords: failWords, couldntWords: couldntWords, injectedScripts: injectedScripts,
                  rewrittenWords: rewrittenWords, openKeys: openKeys};
})(typeof window !== 'undefined' ? window : this);
