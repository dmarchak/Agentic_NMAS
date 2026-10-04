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
    if (unit === 'dtdurations') return duration(n);
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
  /* PURE: seconds as the two largest units ("7 d 19 h", "3 h 4 min"). */
  function duration(s) {
    s = Math.max(0, Math.floor(Number(s)));
    var parts = [[86400, 'd'], [3600, 'h'], [60, 'min'], [1, 's']], out = [];
    for (var i = 0; i < parts.length && out.length < 2; i++) {
      var q = Math.floor(s / parts[i][0]);
      if (q || out.length) { out.push(q + ' ' + parts[i][1]); s -= q * parts[i][0]; }
    }
    return out.length ? out.join(' ') : '0 s';
  }

  /* PURE: a Grafana colour name as a kind the page draws. */
  function colourKind(colour) {
    colour = String(colour || '').toLowerCase();
    if (colour.indexOf('green') >= 0) return 'ok';
    if (colour.indexOf('red') >= 0) return 'danger';
    if (colour.indexOf('orange') >= 0 || colour.indexOf('yellow') >= 0) return 'warn';
    return '';
  }

  function thresholdKind(value, steps) {
    if (value === null || value === undefined || !steps || !steps.length) return '';
    var colour = '';
    for (var i = 0; i < steps.length; i++) {
      var s = steps[i];
      if (s.value === null || s.value === undefined || value >= s.value) colour = s.color || '';
    }
    return colourKind(colour);
  }

  /* PURE: a value through the panel's VALUE MAPPINGS (Grafana's value, range
   * and special kinds), as {text, kind}, or null when none applies. The
   * operator (2026-09-30): "Yes" and "up", never a bare 1. */
  function mapValue(v, mappings) {
    if (!mappings || !mappings.length) return null;
    var isNull = v === null || v === undefined || v === '';
    var n = isNull ? NaN : Number(v);
    for (var i = 0; i < mappings.length; i++) {
      var m = mappings[i] || {}, o = m.options || {}, r = null;
      if (m.type === 'value' && !isNull) {
        r = o[String(v)] || (n === n ? o[String(n)] : null);
      } else if (m.type === 'range' && n === n) {
        var from = o.from === null || o.from === undefined ? -Infinity : Number(o.from);
        var to = o.to === null || o.to === undefined ? Infinity : Number(o.to);
        if (n >= from && n <= to) r = o.result;
      } else if (m.type === 'special') {
        var match = o.match;
        if ((match === 'null' && isNull) || (match === 'nan' && !isNull && n !== n)
            || (match === 'null+nan' && (isNull || n !== n))) r = o.result;
      }
      if (r && (r.text !== undefined && r.text !== null && r.text !== '' || r.color)) {
        return {text: (r.text === undefined || r.text === null || r.text === '') ? String(v) : String(r.text),
                kind: colourKind(r.color)};
      }
    }
    return null;
  }

  /* PURE: a chart's height in pixels from the panel's gridPos h (Grafana's
     30 px rows, less the panel's title and legend), never below 120. */
  function chartHeight(h) {
    var n = parseInt(h, 10);
    if (!(n > 0)) n = 8;
    return Math.max(120, n * 30 - 70);
  }

  /* PURE: the words under a panel: the range, the step and any cut. */
  function footWords(p) {
    var words = [p.range + ', step ' + p.step + ' s'];
    if (p.note) words.push(p.note);
    return words.join(' · ');
  }

  /* PURE: what an empty answer says. */
  function askedWords(p) {
    return 'No series matched ' + p.asked.join(' or ') + ' in the last ' + p.range + '.';
  }

  function emptyHover(p) {
    if (p.no_value_kind === 'danger' || !(p.asked && p.asked.length)) return '';
    // A known platform limit leads with its reason; what was asked goes one level down (C429).
    if (p.limit && p.no_value) return askedWords(p);
    // The panel's own sentence, one level down, when the line says what was measured (C412).
    if (p.no_value) return 'The dashboard says: ' + p.no_value;
    return '';
  }

  function emptyWords(p) {
    // A stopped stream is the failure itself, in the server's words.
    if (p.no_value_kind === 'danger') return p.no_value;
    // A declared platform limit (the page marks its cell, panels.known_limit): its reason.
    if (p.limit && p.no_value) return p.no_value;
    // What was measured, never a cause guessed from an empty answer (C412: "No interface
    // counters from telemetry or SNMP" claimed an absence nobody measured): the selectors
    // asked and the range. The panel's own sentence goes on hover (emptyHover).
    if (p.asked && p.asked.length) {
      return askedWords(p);
    }
    // The panel's own words for no value (Grafana's noValue), when it has
    // them: it knows why its query can be empty for a device (the operator:
    // a panel says what it means, never a bare blank).
    if (p.no_value) return p.no_value;
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

  /* The chart's colours are the page's tokens (nmas-v2.css), so a chart is
   * drawn in the theme on screen; the constants are the light theme's, for a
   * page with no stylesheet (and the duktape tests). */
  function token(name, fallback) {
    try {
      var v = root.getComputedStyle(root.document.documentElement).getPropertyValue(name);
      v = v && String(v).replace(/^\s+|\s+$/g, '');
      return v || fallback;
    } catch (e) { return fallback; }
  }

  function palette() {
    var series = [];
    for (var i = 0; i < COLOURS.length; i++) series.push(token('--series-' + i, COLOURS[i]));
    return {series: series, axis: token('--ink-2', '#4A5260'), grid: token('--line-2', '#EEF0EC'),
            ticks: token('--line', '#DADDE2')};
  }

  function drawSeries(section, body, p) {
    var pal = palette();
    var unit = section.getAttribute('data-panel-unit') || p.unit || '';
    var stepped = p.type === 'state-timeline';
    var width = Math.max(200, body.clientWidth || section.clientWidth - 24);
    var opts = {
      width: width, height: chartHeight(section.getAttribute('data-panel-h')), legend: {show: false}, cursor: {drag: {x: false, y: false}},
      scales: {x: {time: true}},
      axes: [{stroke: pal.axis, grid: {stroke: pal.grid}, ticks: {stroke: pal.ticks}},
             {stroke: pal.axis, grid: {stroke: pal.grid}, ticks: {stroke: pal.ticks}, size: 64,
              values: function (u, vals) {
                return vals.map(function (v) { var m = mapValue(v, p.mappings); return m ? m.text : formatValue(v, unit); });
              }}],
      series: [{}]
    };
    for (var i = 0; i < p.series.length; i++) {
      var s = {label: p.series[i].label, stroke: pal.series[i % pal.series.length], width: 1.5, spanGaps: false};
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

  /* PURE: what a stat shows, {text, cls}. A reading outside the panel's
     valid range is drawn as words, never as a number (the server decides,
     sending `implausible`; the operator, 2026-10-01: a clock rate of -2475%). */
  function statText(p, unit) {
    if (p.implausible) {
      return {text: p.implausible.words || 'Not a valid reading: measuring', cls: 'stat-value stat-measuring'};
    }
    var mapped = mapValue(p.value, p.mappings);
    var kind = mapped && mapped.kind ? mapped.kind : thresholdKind(p.value, p.thresholds);
    return {text: mapped ? mapped.text : formatValue(p.value, unit),
            cls: 'stat-value' + (kind ? ' stat-' + kind : '')};
  }

  function drawStat(body, p, unit) {
    var box = el('div', 'stat');
    var shown = statText(p, unit);
    box.appendChild(el('span', shown.cls, shown.text));
    // Which source the value came from, when the panel says (its legend):
    // "via gRPC telemetry" or "via SNMP", so two devices' values from two
    // collectors are never compared unawares (the operator, 2026-09-30).
    if (p.label) box.appendChild(el('span', 'stat-caption', p.label));
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
        var mapped = mapValue(p.rows[i][j], (p.column_mappings || [])[j]);
        if (mapped) {
          tr.appendChild(el('td', mapped.kind ? 'stat-' + mapped.kind : '', mapped.text));
        } else {
          tr.appendChild(el('td', last ? 'mono' : '', last ? formatValue(p.rows[i][j], unit) : p.rows[i][j]));
        }
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
    section.__nmasLast = p;
    // The page marks a panel a declared platform limit explains (C429).
    p.limit = section.getAttribute('data-panel-limit') === '1';
    clear(body);
    var empty = p.series ? p.series.length === 0 : (p.rows ? p.rows.length === 0 : p.value === null);
    if (p.errors && p.errors.length) body.appendChild(el('p', 'panel-error', p.errors.join('; ')));
    if (empty) {
      // A stopped stream on a device that should stream is the failure,
      // drawn as one (the operator: visible and red), never neutral.
      var note = el('p', p.no_value_kind === 'danger' ? 'panel-error' : 'panel-note', emptyWords(p));
      var hover = emptyHover(p);
      if (hover) note.title = hover;
      body.appendChild(note);
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
      if (s.__nmasChart && body) {
        s.__nmasChart.setSize({width: Math.max(200, body.clientWidth),
                               height: chartHeight(s.getAttribute('data-panel-h'))});
      }
    }
  }

  if (root.document && root.document.addEventListener) {
    root.document.addEventListener('DOMContentLoaded', function () { scan(); schedule(); });
    root.document.addEventListener('htmx:afterSettle', function (e) { scan(e.target); schedule(); });
    root.document.addEventListener('visibilitychange', refreshVisible);
    // A theme change redraws each drawn panel from its last answer, in the
    // new colours: nothing is fetched again.
    root.document.addEventListener('nmas:theme', function () {
      var list = root.document.querySelectorAll('[data-panel-src]');
      for (var i = 0; i < list.length; i++) if (list[i].__nmasLast) draw(list[i], list[i].__nmasLast);
    });
    var pending = null;
    root.addEventListener('resize', function () {
      if (pending) root.clearTimeout(pending);
      pending = root.setTimeout(resize, 150);
    });
  }

  root.NMAS_PANELS = {statText: statText, palette: palette, duration: duration, emptyWords: emptyWords, mapValue: mapValue, colourKind: colourKind, formatValue: formatValue, alignSeries: alignSeries, thresholdKind: thresholdKind,
                      chartHeight: chartHeight,
                      footWords: footWords, emptyWords: emptyWords, emptyHover: emptyHover, scan: scan};
})(typeof window !== 'undefined' ? window : this);
