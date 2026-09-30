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
              'job_health', 'ci_verdict', 'app_version', 'netbox', 'remote', 'baselines'];

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
  function relay(key) {
    if (root.htmx) root.htmx.trigger(root.document.body, 'nmas:' + key);
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
        get drawerClass() { return this.drawer ? 'open' : ''; },
        open: function () { this.drawer = true; },
        close: function () { this.drawer = false; },
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
  }

  if (root.document && root.document.addEventListener) {
    root.document.addEventListener('alpine:init', registerAlpine);
    root.document.addEventListener('DOMContentLoaded', function () {
      wireAnnouncements();
      drawAges();
      drawLive();
      root.setInterval(drawLive, 1000);
      root.setInterval(function () { drawAges(); }, 15000);
    });
    root.document.addEventListener('htmx:afterSettle', function (e) { drawAges(e.target); });
    root.document.addEventListener('htmx:beforeRequest', markTab);
    root.document.addEventListener('keydown', function (e) {
      var t = e.target && e.target.tagName;
      if (e.key !== '/' || t === 'INPUT' || t === 'TEXTAREA' || t === 'SELECT') return;
      var box = root.document.querySelector('.jump input');
      if (box) { e.preventDefault(); box.focus(); }
    });
  }

  root.NMAS_V2 = {ageWords: ageWords, liveWords: liveWords, jumpTarget: jumpTarget, KEYS: KEYS};
})(typeof window !== 'undefined' ? window : this);
