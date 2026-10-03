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
  var KEYS = ['reachability', 'integration_health', 'alerts', 'freshness', 'drift', 'dashboards',
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
              'device_holds', 'rotation',
              // A held device's operation reached its next step: a running card redraws its
              // stepper (C370).
              'device_progress'];

  /* PURE: the Acknowledge button's words, busy on itself. */
  function ackLabel(busy) { return busy ? 'Acknowledging…' : 'Acknowledge'; }

  /* PURE: a refused acknowledgement in words, from the status and the body. */
  function ackRefusal(status, body) {
    return 'Not acknowledged: ' + ((body && body.error) || ('HTTP ' + status));
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
  function relayAlerts() { relay('alerts'); }
  function relayFreshness() { relay('freshness'); }
  function relayDrift() { relay('drift'); }
  function relayDashboards() { relay('dashboards'); }
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
  function relayDeviceProgress() { relay('device_progress'); }

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
    NMAS.subscribe('alerts', 'v2Alerts', relayAlerts);
    NMAS.subscribe('freshness', 'v2Freshness', relayFreshness);
    NMAS.subscribe('drift', 'v2Drift', relayDrift);
    NMAS.subscribe('dashboards', 'v2Dashboards', relayDashboards);
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
    NMAS.subscribe('device_progress', 'v2DeviceProgress', relayDeviceProgress);
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
        isOpen: false, busy: false, said: '',
        get closed() { return !this.isOpen; },
        get label() { return ackLabel(this.busy); },
        open: function () {
          var box = this.$root.querySelector('input[name="why"]');
          this.isOpen = true; this.said = '';
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
            if (got[0] !== 200) { self.busy = false; self.said = ackRefusal(got[0], got[1]); }
          }, function (e) { self.busy = false; self.said = 'Not acknowledged: ' + e.message; });
        }
      };
    });
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
      wireAnnouncements();
      drawAges();
      drawLive();
      drawBadge();
      root.setInterval(function () { drawLive(); drawBadge(); }, 1000);
      root.setInterval(function () { drawAges(); }, 15000);
    });
    root.document.addEventListener('htmx:afterSettle', function (e) { drawAges(e.target); catchUpMissed(e); });
    root.document.addEventListener('htmx:beforeRequest', noteAsked);
    root.document.addEventListener('htmx:beforeRequest', markTab);
    root.document.addEventListener('keydown', function (e) {
      var t = e.target && e.target.tagName;
      if (e.key !== '/' || t === 'INPUT' || t === 'TEXTAREA' || t === 'SELECT') return;
      var box = root.document.querySelector('.jump input');
      if (box) { e.preventDefault(); box.focus(); }
    });
  }

  root.NMAS_V2 = {ageWords: ageWords, liveWords: liveWords, jumpTarget: jumpTarget, KEYS: KEYS,
                  reloadIfRestored: reloadIfRestored, ackLabel: ackLabel, ackRefusal: ackRefusal,
                  badgeDoubt: badgeDoubt, missedKeys: missedKeys};
})(typeof window !== 'undefined' ? window : this);
