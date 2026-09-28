/* The status bar, on every page (Stage 7.2; NSOT_STAGE7_PLAN section 1).

   Integration health, drawn from the integration-health READER's stored
   value (modules/readers/integration_health.py), never by probing: the bar
   and Needs attention read one value, so they cannot disagree.

   The live-data contract applies in compact form: the bar draws its own age,
   and marks itself stale past the reader's promise, because a small green
   badge that stopped updating is the most confidently wrong thing a page can
   show. A read that failed says so, and never as "everything is up". */
(function (root) {
  'use strict';

  function esc(s) {
    return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  var CLS = {up: 'bg-success', down: 'bg-danger', not_configured: 'bg-secondary'};
  var WORD = {up: 'up', down: 'DOWN', not_configured: 'not configured'};
  var last = null;

  function ago(ms) {
    var s = Math.max(0, Math.round(ms / 1000));
    return s < 90 ? s + ' s ago' : Math.round(s / 60) + ' min ago';
  }

  /* PURE: the bar for one payload at one moment. */
  function statusBarHtml(d, nowMs) {
    if (nowMs == null) nowMs = Date.now();
    if (!d || d.ok !== true) {
      return '<span class="badge bg-warning text-dark" data-status-bar="unknown">'
        + 'Integration health could not be read: ' + esc((d && d.error) || 'no answer')
        + '. This is not the same as every integration being up.</span>';
    }
    var items = (d.statuses || []).map(function (s) {
      return '<span class="badge ' + (CLS[s.state] || 'bg-danger') + '" data-integration="'
        + esc(s.name) + '" title="' + esc(s.label) + ': ' + esc(WORD[s.state] || s.state)
        + '. ' + esc(s.message) + ' (probe ' + esc(s.took_ms) + ' ms)">' + esc(s.label)
        + (s.state === 'down' ? ' down' : '') + '</span>';
    }).join(' ');
    var at = d.value_at ? Date.parse(d.value_at) : NaN;
    var age;
    if (isNaN(at)) {
      age = '<span class="text-warning" data-status-bar-age="unknown">the time of this '
        + 'value is not known</span>';
    } else if (d.stale_after_seconds && nowMs - at > d.stale_after_seconds * 1000) {
      age = '<span class="badge bg-warning text-dark" data-status-bar-age="stale">STALE: '
        + 'integration health read ' + ago(nowMs - at) + ', older than the '
        + esc(d.stale_after_seconds) + ' s its reader promises</span>';
    } else {
      age = '<span class="text-muted" data-status-bar-age="fresh">read ' + ago(nowMs - at)
        + '</span>';
    }
    return '<span class="text-muted me-1">Integrations:</span>' + items + ' ' + age;
  }

  function draw(nowMs) {
    var el = root.document && root.document.getElementById('nmasStatusBar');
    if (el && last) el.innerHTML = statusBarHtml(last, nowMs);
  }

  async function loadStatusBar() {
    var d;
    try {
      var r = await fetch('/settings/integrations/status', {cache: 'no-store'});
      d = await r.json();
    } catch (e) {
      d = {ok: false, error: e.message};
    }
    last = d;
    draw(Date.now());
    if (root.NMAS && root.NMAS.stamp) {
      var at = d && d.value_at ? Date.parse(d.value_at) : null;
      NMAS.stamp('nmasStatusBar', isNaN(at) ? null : at, d && d.stale_after_seconds,
                 'Status bar', draw, {ownAge: true});
    }
  }

  root.statusBarHtml = statusBarHtml;
  root.loadStatusBar = loadStatusBar;
  if (typeof document !== 'undefined' && document.addEventListener) {
    document.addEventListener('DOMContentLoaded', function () {
      loadStatusBar();
      if (root.NMAS && root.NMAS.subscribe) {
        NMAS.subscribe('integration_health', 'statusBar', loadStatusBar, {panel: 'nmasStatusBar'});
      }
    });
  }
})(typeof window !== 'undefined' ? window : this);
