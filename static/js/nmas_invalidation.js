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
     hears both. Never a data poll.

     THE LIVE-DATA CONTRACT (7.2 step 13, the operator's standing
     requirement: a page showing live information updates itself, and one
     that cannot tell whether it is current SAYS SO). Three parts, each for
     one way of looking current while not being:
       - the HEARTBEAT proves the channel: none for 2.5 intervals and every
         subscribed panel is marked, on its own data, as not updating;
       - AGE against the source's promise proves the SOURCE: a stamped panel
         shows how old its value is and marks itself stale past the promise,
         judged on a local tick that makes no request (a reader that died
         announces nothing, and silence must not read as "nothing changed");
       - CATCH-UP on reconnect: every subscribed panel re-fetches once,
         covering whatever was announced while the channel was down. */
  var live = {state: 'not_connected', since: null, lastBeat: null, beatSeconds: 30};
  var BEATS_MISSED = 2.5;
  var TICK_MS = 15000;   // a fifth of the tightest bound (75 s): a mark is at most 20% late

  function onAnnounce(msg) {
    var keys = (msg && msg.keys && msg.keys.length !== undefined) ? msg.keys : [];
    var names = keys.length ? invalidate(keys) : [];
    record({event: 'announced', by: (msg && msg.by) || '?', ok: !!(msg && msg.ok),
            keys: keys, panels: names});
    return names;
  }

  function setLive(state) {
    var was = live.state;
    if (live.state !== state) { live.state = state; live.since = now(); }
    record({event: 'socket', state: state});
    markPanels();
    // Catch-up: a panel that was not hearing re-fetches once on the way back.
    // Not on the first connect: a page that has just loaded is current.
    if (state === 'connected' && was !== 'connected' && was !== 'not_connected') {
      var seen = {};
      for (var i = 0; i < subs.length; i++) {
        if (seen[subs[i].name]) continue;
        seen[subs[i].name] = true;
        refresh(subs[i]);
      }
      record({event: 'caught_up', panels: Object.keys(seen)});
    }
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
      : state.state === 'silent'
        ? 'Live updates went silent at ' + clockTime(state.since)
          + ' (no heartbeat from the server)'
        : state.state === 'failed'
          ? 'Live updates could not connect (since ' + clockTime(state.since) + ')'
          : 'Live updates are not connected';
    return '<div class="small text-warning" data-nmas-live="' + state.state + '">'
      + what + ': a background read that finishes now is not shown until the '
      + 'panel is next loaded.</div>';
  }

  /* ON THE DATA, not only in a status area (the operator): every subscribed
     panel carries the mark while the channel is down, because a stale panel
     that looks current is the failure. Nothing before the first attempt. */
  function markPanels() {
    var html = (live.state === 'connected' || live.state === 'not_connected')
      ? '' : liveNoteHtml();
    var seen = {};
    for (var i = 0; i < subs.length; i++) {
      var sub = subs[i];
      if (!sub.panel || seen[sub.panel]) continue;
      seen[sub.panel] = true;
      var el = panelOf(sub);
      if (!el || !el.querySelector) continue;
      var old = el.querySelector('[data-nmas-live]');
      if (old && old.parentNode) old.parentNode.removeChild(old);
      if (html) el.insertAdjacentHTML('afterbegin', html);
    }
  }

  function onHeartbeat(msg) {
    live.lastBeat = now();
    if (msg && msg.interval_seconds) live.beatSeconds = msg.interval_seconds;
    if (live.state !== 'connected') setLive('connected');
  }

  /* A panel's value and how long it stays current. *staleAfter* in seconds,
     from the source's own promise; null when the source made none, and then
     the panel says it cannot tell rather than looking fresh. *redraw*, when
     given, re-renders the panel from what it last fetched (no request). */
  var stamps = {};

  /* *opts.ownAge*: a compact panel (the status bar) that draws its own age
     and staleness in its redraw; the tick still redraws it, and no separate
     age line is added. */
  function stamp(panel, valueAt, staleAfter, label, redraw, opts) {
    stamps[panel] = {valueAt: valueAt, staleAfter: staleAfter == null ? null : staleAfter,
                     label: label || '', redraw: redraw || null,
                     ownAge: !!(opts && opts.ownAge)};
    drawAge(panel);
  }

  function ago(ms) {
    var s = Math.max(0, Math.round(ms / 1000));
    return s < 90 ? s + ' s ago' : s < 5400 ? Math.round(s / 60) + ' min ago'
      : Math.round(s / 3600) + ' h ago';
  }

  /* PURE: the age line a stamped panel carries. */
  function ageHtml(st, nowMs) {
    if (!st || st.valueAt == null) {
      return '<div class="small text-warning" data-nmas-age="unknown">The time of this '
        + 'value is not known, so whether it is current cannot be told.</div>';
    }
    var age = nowMs - st.valueAt;
    var from = 'value from ' + clockTime(st.valueAt) + ' (' + ago(age) + ')';
    if (st.staleAfter == null) {
      return '<div class="small text-muted" data-nmas-age="no_promise">' + from
        + '; its source states no freshness, so how long it stays current is not known.</div>';
    }
    if (age > st.staleAfter * 1000) {
      return '<div class="small text-danger" data-nmas-age="stale"><strong>Stale:</strong> '
        + from + ', older than the ' + st.staleAfter + ' s its source promises. It has not '
        + 'been refreshed and may no longer be true.</div>';
    }
    return '<div class="small text-muted" data-nmas-age="fresh">' + from + '</div>';
  }

  function drawAge(panel) {
    var st = stamps[panel];
    var doc = root.document;
    var el = (doc && doc.getElementById) ? doc.getElementById(panel) : null;
    if (!st || !el) return;
    if (st.redraw) {
      try { st.redraw(now()); } catch (e) { record({event: 'redraw_failed', panel: panel}); }
    }
    if (st.ownAge || !el.querySelector) return;
    var old = el.querySelector('[data-nmas-age]');
    if (old && old.parentNode) old.parentNode.removeChild(old);
    el.insertAdjacentHTML('beforeend', ageHtml(st, now()));
  }

  /* The local tick: judges the channel and every stamped panel's age. It
     makes no request, so its cost is the same at nine devices or 900. */
  function tick() {
    var t = now();
    if (live.state === 'connected') {
      var since = live.lastBeat != null ? live.lastBeat : live.since;
      if (since != null && t - since > BEATS_MISSED * live.beatSeconds * 1000) setLive('silent');
    }
    for (var panel in stamps) {
      if (Object.prototype.hasOwnProperty.call(stamps, panel)) drawAge(panel);
    }
  }

  if (root.setInterval && root.document && !root.__nmasTick) {
    root.__nmasTick = root.setInterval(tick, TICK_MS);
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
      sock.on('nmas_heartbeat', onHeartbeat);
    } catch (e) {
      record({event: 'socket', state: 'failed', error: String(e)});
    }
  }

  /* C474: an htmx write's answer carries the same header, but htmx asks by XHR, which the
     fetch wrapper never sees, so a v2 confirm's keys never reached its own page (measured
     2026-10-05: the sidebar's count stayed stale after Retry, Persist and Finish retirement).
     The same registry hears them now, the one way keys travel. */
  function onHtmxResponse(e) {
    var xhr = e && e.detail && e.detail.xhr;
    if (!xhr || !xhr.getResponseHeader) return;
    onResponse({url: xhr.responseURL || '',
                headers: {get: function (h) { return xhr.getResponseHeader(h); }}});
  }
  if (root.document && root.document.addEventListener) {
    root.document.addEventListener('htmx:afterRequest', onHtmxResponse);
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
    onHtmxResponse: onHtmxResponse,
    onAnnounce: onAnnounce, liveNoteHtml: liveNoteHtml, onHeartbeat: onHeartbeat,
    stamp: stamp, ageHtml: ageHtml, tick: tick,
    live: function () { return {state: live.state, since: live.since}; },
    keysFrom: keysFrom, staleMarkerHtml: staleMarkerHtml, _subs: subs,
    log: function () { return log.slice(); },
  };
})(typeof window !== 'undefined' ? window : this);
