/* NMAS panel island (the spike, NSOT_GUI_BRIEF 9b): draws a device page's
 * Grafana panels from /v2/device/<name>/panel/<uid>/<id>, with uPlot for a
 * series and the DOM (textContent, never innerHTML with data) for a stat or a
 * table. ES5 on purpose: the pure helpers below are executed in duktape by
 * tests/test_device_v2.py, which has no event loop and no ES2015.
 *
 * A panel says what it could not do: a failed read keeps the last chart and
 * names the error with its time; an empty answer says it is empty, never a
 * blank box. Refreshes run only while the page is visible, at the rate the
 * panel grid declares (data-refresh, seconds).
 */
(function (root) {
  'use strict';

  var COLOURS = ['#1E5E8C', '#D97706', '#0B6B45', '#6B4C9A', '#4A5260', '#0E7490'];

  /* PURE: one number in the panel's unit, short enough for an axis. */
  function formatValue(v, unit) {
    if (v === null || v === undefined || v !== v) return '-';
    var n = Number(v);
    if (unit === 'percent') return trim(n) + '%';
    if (unit === 'percentunit') return trim(n * 100) + '%';
    var scaled = scale(n);
    if (unit === 'bps') return scaled + 'b/s';
    if (unit === 'Bps' || unit === 'binBps') return scaled + 'B/s';
    if (unit === 'pps') return scaled + ' p/s';
    if (unit === 'bytes' || unit === 'decbytes') return scaled + 'B';
    if (unit === 's') return trim(n) + ' s';
    if (unit === 'ms') return trim(n) + ' ms';
    return scaled;
  }

  function trim(n) {
    var a = Math.abs(n);
    if (a >= 100 || a === 0) return String(Math.round(n));
    if (a >= 10) return (Math.round(n * 10) / 10).toString();
    return (Math.round(n * 100) / 100).toString();
  }

  function scale(n) {
    var a = Math.abs(n), units = [[1e12, 'T'], [1e9, 'G'], [1e6, 'M'], [1e3, 'k']];
    for (var i = 0; i < units.length; i++) {
      if (a >= units[i][0]) return trim(n / units[i][0]) + ' ' + units[i][1];
    }
    return trim(n);
  }

  /* PURE: uPlot's aligned data from the payload's series. Every series of
     one query shares its times; series from different queries are aligned on
     the union of times, a missing point left null (a gap, never a zero). */
  function alignSeries(series) {
    var seen = {}, times = [], i, j;
    for (i = 0; i < series.length; i++) {
      for (j = 0; j < series[i].times.length; j++) {
        var t = series[i].times[j];
        if (!seen[t]) { seen[t] = true; times.push(t); }
      }
    }
    times.sort(function (a, b) { return a - b; });
    var index = {};
    for (i = 0; i < times.length; i++) index[times[i]] = i;
    var data = [times];
    for (i = 0; i < series.length; i++) {
      var col = [];
      for (j = 0; j < times.length; j++) col.push(null);
      for (j = 0; j < series[i].times.length; j++) {
        var v = series[i].values[j];
        col[index[series[i].times[j]]] = (v === undefined ? null : v);
      }
      data.push(col);
    }
    return data;
  }

  /* PURE: which kind a stat's value is, from Grafana's threshold steps: the
     last step whose value the number reaches (the first step's null is the
     base). Named colours map onto the page's three kinds. */
  function thresholdKind(value, steps) {
    if (value === null || value === undefined || !steps || !steps.length) return '';
    var colour = '';
    for (var i = 0; i < steps.length; i++) {
      var s = steps[i];
      if (s.value === null || s.value === undefined || value >= s.value) colour = s.color || '';
    }
    colour = String(colour).toLowerCase();
    if (colour.indexOf('green') >= 0) return 'ok';
    if (colour.indexOf('red') >= 0) return 'danger';
    if (colour.indexOf('orange') >= 0 || colour.indexOf('yellow') >= 0) return 'warn';
    return '';
  }

  /* PURE: the words under a panel: the range, the step and any cut. */
  function footWords(p) {
    var words = [p.range + ', step ' + p.step + ' s'];
    if (p.note) words.push(p.note);
    return words.join(' · ');
  }

  /* PURE: what an empty answer says. */
  function emptyWords(p) {
    return 'Grafana answered with no data for this device over ' + p.range
      + '. The query ran; nothing matched it.';
  }

  // ----------------------------------------------------------------- DOM

  function el(tag, cls, text) {
    var e = root.document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) e.textContent = String(text);
    return e;
  }

  function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }

  function clock(iso) {
    var d = iso ? new Date(iso) : new Date();
    function pad(n) { return (n < 10 ? '0' : '') + n; }
    return pad(d.getHours()) + ':' + pad(d.getMinutes()) + ':' + pad(d.getSeconds());
  }

  function drawSeries(section, body, p) {
    var unit = section.getAttribute('data-panel-unit') || p.unit || '';
    var stepped = p.type === 'state-timeline';
    var width = Math.max(200, body.clientWidth || section.clientWidth - 24);
    var opts = {
      width: width, height: 180, legend: {show: false}, cursor: {drag: {x: false, y: false}},
      scales: {x: {time: true}},
      axes: [{stroke: '#4A5260', grid: {stroke: '#EEF0EC'}, ticks: {stroke: '#DADDE2'}},
             {stroke: '#4A5260', grid: {stroke: '#EEF0EC'}, ticks: {stroke: '#DADDE2'}, size: 64,
              values: function (u, vals) { return vals.map(function (v) { return formatValue(v, unit); }); }}],
      series: [{}]
    };
    for (var i = 0; i < p.series.length; i++) {
      var s = {label: p.series[i].label, stroke: COLOURS[i % COLOURS.length], width: 1.5, spanGaps: false};
      if (stepped && root.uPlot.paths && root.uPlot.paths.stepped) s.paths = root.uPlot.paths.stepped({align: 1});
      opts.series.push(s);
    }
    var holder = el('div', 'chart');
    body.appendChild(holder);
    var chart = new root.uPlot(opts, alignSeries(p.series), holder);
    section.__nmasChart = chart;
    var foot = el('div', 'panel-foot');
    for (i = 0; i < p.series.length && i < 12; i++) {
      var item = el('span', 'legend-item');
      item.appendChild(el('span', 'swatch s' + (i % COLOURS.length)));
      item.appendChild(el('span', '', p.series[i].label));
      foot.appendChild(item);
    }
    if (p.series.length > 12) foot.appendChild(el('span', '', '+' + (p.series.length - 12) + ' more'));
    body.appendChild(foot);
  }

  function drawStat(body, p, unit) {
    var box = el('div', 'stat');
    var kind = thresholdKind(p.value, p.thresholds);
    box.appendChild(el('span', 'stat-value' + (kind ? ' stat-' + kind : ''), formatValue(p.value, unit)));
    body.appendChild(box);
  }

  function drawTable(body, p, unit) {
    var wrap = el('div', 'table-wrap'), table = el('table', 'table');
    var head = el('thead'), tr = el('tr'), i, j;
    for (i = 0; i < p.columns.length; i++) tr.appendChild(el('th', '', p.columns[i]));
    head.appendChild(tr);
    table.appendChild(head);
    var tb = el('tbody');
    for (i = 0; i < p.rows.length; i++) {
      tr = el('tr');
      for (j = 0; j < p.rows[i].length; j++) {
        var last = j === p.rows[i].length - 1;
        tr.appendChild(el('td', last ? 'mono' : '', last ? formatValue(p.rows[i][j], unit) : p.rows[i][j]));
      }
      tb.appendChild(tr);
    }
    table.appendChild(tb);
    wrap.appendChild(table);
    body.appendChild(wrap);
  }

  function draw(section, p) {
    var body = section.querySelector('.panel-body');
    var unit = section.getAttribute('data-panel-unit') || p.unit || '';
    if (section.__nmasChart) { section.__nmasChart.destroy(); section.__nmasChart = null; }
    clear(body);
    var empty = p.series ? p.series.length === 0 : (p.rows ? p.rows.length === 0 : p.value === null);
    if (p.errors && p.errors.length) body.appendChild(el('p', 'panel-error', p.errors.join('; ')));
    if (empty) {
      body.appendChild(el('p', 'panel-note', emptyWords(p)));
    } else if (p.rows) {
      drawTable(body, p, unit);
    } else if (p.series) {
      drawSeries(section, body, p);
    } else {
      drawStat(body, p, unit);
    }
    body.appendChild(el('p', 'panel-note', footWords(p) + ' · read ' + clock(p.read_at)));
  }

  function fail(section, why) {
    var body = section.querySelector('.panel-body');
    var old = body.querySelector('.panel-error[data-fetch]');
    if (old) old.parentNode.removeChild(old);
    var msg = el('p', 'panel-error', 'Could not read this panel at ' + clock() + ': ' + why
      + (section.__nmasLoaded ? '. The chart below is the last good read.' : '.'));
    msg.setAttribute('data-fetch', '1');
    body.insertBefore(msg, body.firstChild);
    var wait = body.querySelector('.panel-wait');
    if (wait) wait.parentNode.removeChild(wait);
  }

  function load(section) {
    var src = section.getAttribute('data-panel-src');
    if (!src || section.__nmasBusy) return;
    section.__nmasBusy = true;
    root.fetch(src, {headers: {Accept: 'application/json'}, credentials: 'same-origin'})
      .then(function (r) {
        return r.json().then(function (body) { return {status: r.status, body: body}; },
                             function () { return {status: r.status, body: null}; });
      })
      .then(function (got) {
        section.__nmasBusy = false;
        if (!got.body || got.body.ok === false) {
          fail(section, (got.body && got.body.error) || ('HTTP ' + got.status));
          return;
        }
        draw(section, got.body);
        section.__nmasLoaded = true;
      }, function (e) {
        section.__nmasBusy = false;
        fail(section, String(e && e.message || e));
      });
  }

  function scan(scope) {
    var list = (scope || root.document).querySelectorAll('[data-panel-src]');
    for (var i = 0; i < list.length; i++) load(list[i]);
  }

  function refreshVisible() {
    if (root.document.visibilityState && root.document.visibilityState !== 'visible') return;
    scan(root.document);
  }

  var timer = null;
  function schedule() {
    if (timer) root.clearInterval(timer);
    var grid = root.document.querySelector('.panels[data-refresh]');
    if (!grid) { timer = null; return; }
    var secs = parseInt(grid.getAttribute('data-refresh'), 10) || 30;
    timer = root.setInterval(refreshVisible, Math.max(10, secs) * 1000);
  }

  function resize() {
    var list = root.document.querySelectorAll('[data-panel-src]');
    for (var i = 0; i < list.length; i++) {
      var s = list[i], body = s.querySelector('.panel-body');
      if (s.__nmasChart && body) s.__nmasChart.setSize({width: Math.max(200, body.clientWidth), height: 180});
    }
  }

  if (root.document && root.document.addEventListener) {
    root.document.addEventListener('DOMContentLoaded', function () { scan(); schedule(); });
    root.document.addEventListener('htmx:afterSettle', function (e) { scan(e.target); schedule(); });
    root.document.addEventListener('visibilitychange', refreshVisible);
    var pending = null;
    root.addEventListener('resize', function () {
      if (pending) root.clearTimeout(pending);
      pending = root.setTimeout(resize, 150);
    });
  }

  root.NMAS_PANELS = {formatValue: formatValue, alignSeries: alignSeries, thresholdKind: thresholdKind,
                      footWords: footWords, emptyWords: emptyWords, scan: scan};
})(typeof window !== 'undefined' ? window : this);
