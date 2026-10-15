/* History › Query › Ask your own, the logs builder (board F3; templates/v2/_history_ask_logs.html,
 * modules/history_logq.py). The query is formed on the server; this file only:
 *  - writes the viewer's local time beside each UTC time typed in From… to… (`data-lq-local`);
 *  - closes the From… to… picker, or a line's Reveal… box, on Cancel (`data-lq-close`),
 *    changing nothing; closes a Reveal… box once the line it revealed is drawn (C818), so the
 *    box never covers it;
 *  - on a click on the counts chart, names the window and the series under the pointer and
 *    offers that window's lines (`data-lq-pick`, each series' `href` from the server).
 *
 * ES5; no inline script (the strict policy). The pure functions are exported on
 * `window.NMAS_LOGQ` and executed in duktape by tests/test_history_ask_logs.py.
 */
(function (root) {
  'use strict';

  function pad(n) { return (n < 10 ? '0' : '') + n; }

  /* PURE: "YYYY-MM-DD HH:MM" or "YYYY-MM-DD", read as UTC, to epoch seconds; null otherwise. */
  function parseUtc(text) {
    var m = /^(\d{4})-(\d{2})-(\d{2})(?: (\d{2}):(\d{2}))?$/.exec(String(text || '').replace(/^\s+|\s+$/g, ''));
    if (!m) return null;
    var t = Date.UTC(+m[1], +m[2] - 1, +m[3], m[4] ? +m[4] : 0, m[5] ? +m[5] : 0);
    return isNaN(t) ? null : t / 1000;
  }

  /* PURE: the words beside a UTC time: the viewer's local clock and its offset from UTC, given
     the offset in minutes EAST of UTC (local = UTC + offset). "00:00 local (UTC−6)". */
  function localWords(epoch, offsetMin) {
    var d = new Date((epoch + offsetMin * 60) * 1000);
    var h = Math.floor(Math.abs(offsetMin) / 60), m = Math.abs(offsetMin) % 60;
    var off = offsetMin === 0 ? 'UTC' : 'UTC' + (offsetMin < 0 ? '−' : '+') + h + (m ? ':' + pad(m) : '');
    return 'UTC · ' + pad(d.getUTCHours()) + ':' + pad(d.getUTCMinutes()) + ' local (' + off + ')';
  }

  /* PURE: epoch seconds as the address writes a time, "YYYY-MM-DD HH:MM" (UTC). */
  function stamp(epoch) {
    var d = new Date(epoch * 1000);
    return d.getUTCFullYear() + '-' + pad(d.getUTCMonth() + 1) + '-' + pad(d.getUTCDate()) + ' ' +
      pad(d.getUTCHours()) + ':' + pad(d.getUTCMinutes());
  }

  /* PURE: the window a point closes: a count at *t* covers the *step* seconds before it. */
  function windowOf(t, step) {
    return {from: stamp(t - step), to: stamp(t)};
  }

  /* PURE: a series' lines address for one window: its href with the window's From and To. */
  function pickHref(href, w) {
    if (!href) return '';
    return href + (href.indexOf('?') < 0 ? '?' : '&') + 'from=' + encodeURIComponent(w.from) +
      '&to=' + encodeURIComponent(w.to);
  }

  /* PURE: which series the pointer is on: of those with a count at *idx*, the one drawn nearest
     *top* (pixels), given each series' y position by *yOf(value)*; -1 when none has a count. */
  function nearest(data, idx, top, yOf) {
    var best = -1, gap = Infinity;
    for (var i = 1; i < data.length; i++) {
      var v = data[i][idx];
      if (v === null || v === undefined || v <= 0) continue;
      var g = Math.abs(yOf(v) - top);
      if (g < gap) { gap = g; best = i - 1; }
    }
    return best;
  }

  function local(input) {
    var out = root.document.getElementById(input.getAttribute('data-lq-local'));
    if (!out) return;
    var t = parseUtc(input.value);
    out.textContent = t === null ? '' : localWords(t, -new Date(t * 1000).getTimezoneOffset());
  }

  function refresh(scope) {
    var list = (scope || root.document).querySelectorAll('[data-lq-local]');
    for (var i = 0; i < list.length; i++) local(list[i]);
  }

  function pick(section, chart) {
    var p = section.__nmasLast, holder = section.nextElementSibling;
    if (!p || !holder || !chart) return;
    var idx = chart.cursor.idx;
    if (idx === null || idx === undefined) return;
    var i = nearest(chart.data, idx, chart.cursor.top, function (v) { return chart.valToPos(v, 'y'); });
    while (holder.firstChild) holder.removeChild(holder.firstChild);
    if (i < 0) { holder.hidden = true; return; }
    var s = p.series[i], t = chart.data[0][idx], w = windowOf(t, p.step), n = chart.data[i + 1][idx];
    var words = root.document.createElement('span');
    words.textContent = s.label + ' · ' + w.from.slice(5) + ' to ' + w.to.slice(11) + ' UTC · ' + n +
      ' line' + (n === 1 ? '' : 's') + ' in this window';
    holder.appendChild(words);
    var href = pickHref(s.href, w);
    if (href) {
      var a = root.document.createElement('a');
      a.className = 'btn btn-small';
      a.href = href;
      a.textContent = 'Show these lines';
      holder.appendChild(a);
    }
    holder.hidden = false;
  }

  if (root.document && root.document.addEventListener) {
    root.document.addEventListener('DOMContentLoaded', function () { refresh(); });
    root.document.addEventListener('htmx:afterSettle', function (e) { refresh(e.target); });
    root.document.addEventListener('htmx:afterRequest', function (e) {
      var form = e.detail && e.detail.elt;
      if (!form || !form.classList || !form.classList.contains('lq-rvpop')) return;
      if (!e.detail.successful) return;           // a refusal is drawn under the line; the box stays
      var box = form.closest('details');
      if (box) box.open = false;
    });
    root.document.addEventListener('input', function (e) {
      if (e.target && e.target.getAttribute && e.target.getAttribute('data-lq-local')) local(e.target);
    });
    root.document.addEventListener('click', function (e) {
      var t = e.target;
      if (!t || !t.closest) return;
      var close = t.closest('[data-lq-close]');
      if (close) {
        var box = close.closest('details');
        if (box) box.open = false;
        return;
      }
      var section = t.closest('[data-lq-pick]');
      if (section && t.closest('.u-over')) pick(section, section.__nmasChart);
    });
  }

  root.NMAS_LOGQ = {parseUtc: parseUtc, localWords: localWords, windowOf: windowOf,
                    pickHref: pickHref, nearest: nearest, stamp: stamp};
})(typeof window !== 'undefined' ? window : this);
