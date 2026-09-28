/* NMAS invalidation: panels re-fetch when an action changes their data.
 *
 * Stage 7.0 (NSOT_STAGE7_GUI.md 6b). Every mutating route's response names
 * the DATA it changed, in the X-NMAS-Invalidates header
 * (modules/invalidation.py). A panel subscribes to the keys it draws, and
 * re-fetches when a response names one. That is ON THE RESPONSE, never on a
 * timer: a response means the write is done, and a poll interval is a
 * window in which the screen is wrong.
 *
 * A re-fetch that fails leaves the old value on screen, and a panel that
 * says nothing about that is confidently wrong: worse than the stale panel
 * this exists to fix. So a failure marks the panel STALE, with the time of
 * the value it still shows.
 *
 * A loader reports its outcome: `false`, a throw, or a rejected promise is a
 * failure, and anything else is success. The core is synchronous where the
 * loader is, so the shipped code is executed in duktape
 * (tests/test_invalidation_map.py), which has no event loop.
 *
 * Loaded in <head>, before any page script subscribes.
 */
(function (root) {
  'use strict';

  var subs = [];

  /* What fired, when, and what it refreshed (Stage 7.0 acceptance 6).
     Without it, "the panel did not change" cannot tell a mechanism that did
     not fire from one that fired and redrew an identical value: a test whose
     pass and fail render the same (the operator's reading of the drift
     case). Read it in the browser console with NMAS.log(). */
  var log = [];

  function record(entry) {
    entry.at = new Date(now()).toISOString();
    log.push(entry);
    if (log.length > 100) log.shift();
    if (root.console && root.console.info) {
      root.console.info('NMAS: ' + JSON.stringify(entry));
    }
  }

  function now() { return (root.NMAS && root.NMAS._clock) ? root.NMAS._clock() : Date.now(); }

  function pad(n) { return (n < 10 ? '0' : '') + n; }

  function clockTime(ms) {
    var d = new Date(ms);
    return pad(d.getHours()) + ':' + pad(d.getMinutes()) + ':' + pad(d.getSeconds());
  }

  /* PURE: the words the stale marker shows. */
  function staleMarkerHtml(lastGood) {
    var what = lastGood
      ? 'showing the value from ' + clockTime(lastGood)
      : 'this panel has not loaded since the page opened';
    return '<div class="alert alert-warning py-1 px-2 small mb-1" data-nmas-stale="1">'
      + '<strong>Stale:</strong> a refresh after a change failed, so this is '
      + what + '. Reload the page to retry.</div>';
  }

  function panelOf(sub) {
    var doc = root.document;
    return (sub.panel && doc && doc.getElementById) ? doc.getElementById(sub.panel) : null;
  }

  function clearStale(sub) {
    var el = panelOf(sub);
    if (!el || !el.querySelector) return;
    var old = el.querySelector('[data-nmas-stale]');
    if (old && old.parentNode) old.parentNode.removeChild(old);
  }

  function markStale(sub) {
    var el = panelOf(sub);
    if (!el) {
      if (root.console) root.console.error('NMAS: stale panel "' + sub.panel + '" is missing');
      return;
    }
    clearStale(sub);
    el.insertAdjacentHTML('afterbegin', staleMarkerHtml(sub.lastGood));
  }

  function settle(sub, ok) {
    sub.refreshing = false;
    record({event: 'refreshed', panel: sub.name, key: sub.key, ok: !!ok});
    if (ok) {
      sub.lastGood = now();
      clearStale(sub);
    } else {
      markStale(sub);
    }
  }

  function refresh(sub) {
    var result;
    sub.refreshing = true;
    try {
      result = sub.load();
    } catch (e) {
      settle(sub, false);
      return;
    }
    if (result && typeof result.then === 'function') {
      result.then(function (v) { settle(sub, v !== false); },
                  function () { settle(sub, false); });
    } else {
      settle(sub, result !== false);
    }
  }

  /* Register `load` to run when a response invalidates `key`. `name` makes a
     panel subscribed to several keys refresh once per response. */
  function subscribe(key, name, load, opts) {
    opts = opts || {};
    if (!key || !name || typeof load !== 'function') {
      throw new Error('NMAS.subscribe(key, name, load): all three are required');
    }
    subs.push({key: key, name: name, load: load, panel: opts.panel || '',
               lastGood: opts.loadedAt === undefined ? now() : opts.loadedAt,
               refreshing: false});
  }

  /* PURE: keys from a header value. */
  function keysFrom(value) {
    if (!value) return [];
    return String(value).split(',').map(function (k) { return k.replace(/^\s+|\s+$/g, ''); })
      .filter(function (k) { return k.length > 0; });
  }

  function invalidate(keys) {
    var seen = {};
    var hit = [];
    for (var i = 0; i < subs.length; i++) {
      var sub = subs[i];
      if (keys.indexOf(sub.key) === -1 || seen[sub.name]) continue;
      seen[sub.name] = true;
      hit.push(sub);
    }
    for (var j = 0; j < hit.length; j++) refresh(hit[j]);
    return hit.map(function (s) { return s.name; });
  }

  /* The response is what triggers the re-fetch. */
  function onResponse(resp) {
    var value = resp && resp.headers && resp.headers.get
      ? resp.headers.get('X-NMAS-Invalidates') : null;
    var keys = keysFrom(value);
    if (keys.length) {
      var names = invalidate(keys);
      record({event: 'invalidated', url: (resp && resp.url) || '', keys: keys,
              panels: names});
    }
    return resp;
  }

  /* C58: a change the server makes AFTER a response, or on its own schedule
     (a reader job finishing), is ANNOUNCED over the socket with the same
     keys, and dispatched by the same registry: a panel subscribes once and
     hears both. Never a timer. */
  var live = {state: 'not_connected', since: null};

  function onAnnounce(msg) {
    var keys = (msg && msg.keys && msg.keys.length !== undefined) ? msg.keys : [];
    var names = keys.length ? invalidate(keys) : [];
    record({event: 'announced', by: (msg && msg.by) || '?', ok: !!(msg && msg.ok),
            keys: keys, panels: names});
    return names;
  }

  function setLive(state) {
    if (live.state !== state) { live.state = state; live.since = now(); }
    record({event: 'socket', state: state});
    // Drawn in ONE place every page has (base.html), so no panel has to
    // remember it. Nothing is drawn before the first connect: a page that
    // has just loaded holds fresh values, and a warning at every load would
    // teach the reader to skip it.
    var doc = root.document;
    var el = (doc && doc.getElementById) ? doc.getElementById('nmasLiveNote') : null;
    if (el) el.innerHTML = liveNoteHtml();
  }

  /* PURE: what a page says while announcements cannot reach it. A panel that
     stopped hearing looks exactly like one with nothing new, so the dropped
     connection is drawn, with the time it dropped. Empty while connected. */
  function liveNoteHtml(state) {
    state = state || live;
    if (state.state === 'connected') return '';
    var what = state.state === 'disconnected'
      ? 'Live updates stopped at ' + clockTime(state.since)
      : state.state === 'failed'
        ? 'Live updates could not connect (since ' + clockTime(state.since) + ')'
        : 'Live updates are not connected';
    return '<div class="small text-warning" data-nmas-live="' + state.state + '">'
      + what + ': a background read that finishes now is not shown until the '
      + 'panel is next loaded.</div>';
  }

  if (root.io && !root.__nmasSocket) {
    try {
      var sock = root.io();
      root.__nmasSocket = sock;
      sock.on('connect', function () { setLive('connected'); });
      sock.on('disconnect', function () { setLive('disconnected'); });
      sock.on('connect_error', function () {
        if (live.state !== 'disconnected') setLive('failed');
      });
      sock.on('nmas_invalidate', onAnnounce);
    } catch (e) {
      record({event: 'socket', state: 'failed', error: String(e)});
    }
  }

  if (root.fetch && !root.fetch.__nmas) {
    var original = root.fetch;
    var wrapped = function () {
      return original.apply(this, arguments).then(onResponse);
    };
    wrapped.__nmas = true;
    root.fetch = wrapped;
  }

  root.NMAS = {
    subscribe: subscribe, invalidate: invalidate, onResponse: onResponse,
    onAnnounce: onAnnounce, liveNoteHtml: liveNoteHtml,
    live: function () { return {state: live.state, since: live.since}; },
    keysFrom: keysFrom, staleMarkerHtml: staleMarkerHtml, _subs: subs,
    log: function () { return log.slice(); },
  };
})(typeof window !== 'undefined' ? window : this);
