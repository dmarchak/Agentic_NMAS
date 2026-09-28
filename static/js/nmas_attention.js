/* Needs attention (Stage 7.2): every source, one row shape, one list.

   The server decides each row's level and the order; this only draws. Three
   states, never two: the list could not be asked (a warning that says it is
   NOT the same as nothing wrong), rows, or "Nothing needs attention" WITH
   every source and the time it was read, because an empty list must say what
   was looked at. A source that could not be read arrives as a row of its
   own, so it is drawn like any other. */
(function (root) {
  var timer = null;

  function esc(s) {
    return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  var BADGE = {danger: 'bg-danger', warning: 'bg-warning text-dark',
               unknown: 'bg-secondary'};
  var LEVEL_WORDS = {danger: 'needs action', warning: 'check',
                     unknown: 'cannot tell'};

  function when(iso) {
    return iso ? esc(iso.replace('T', ' ').replace('Z', ' UTC')) : 'not recorded';
  }

  function sourcesLine(sources) {
    return (sources || []).map(function (s) {
      return esc(s.label) + ': ' + (s.state === 'read'
        ? (s.value_at && s.value_at !== s.read_at
           ? 'value from ' + when(s.value_at) + ', read ' : 'read ')
          + when(s.read_at) + ' in ' + esc(s.took_ms) + ' ms, ' + esc(s.checked)
          + ', ' + esc(s.count) + ' row(s) here'
        : '<strong>could not be read</strong> (' + when(s.read_at) + ')');
    }).join('; ');
  }

  /* PURE: the collapsed claim. The OLDEST value is named, with its source,
     because a summary is only as fresh as its weakest source, and a value
     that is old for a reason (a baseline decided days ago) reads as that
     source's age rather than as the page's. */
  function summaryLine(d, sources) {
    var readAt = sources.map(function (s) { return s.read_at || ''; }).sort().pop();
    var oldest = sources.filter(function (s) { return s.value_at; })
      .sort(function (a, b) { return a.value_at < b.value_at ? -1 : a.value_at > b.value_at ? 1 : 0; })[0];
    return '<strong>' + esc(d.headline) + '</strong> &middot; ' + sources.length + ' of '
      + sources.length + ' sources answered, read ' + when(readAt)
      + (oldest ? ' &middot; oldest value: ' + esc(oldest.label) + ', from '
         + when(oldest.value_at) : '');
  }

  function actionHtml(a) {
    a = a || {};
    var html = a.known === false
      ? '<span class="text-muted">' + esc(a.label) + '</span>'
      : '<strong>' + esc(a.label) + '</strong>';
    if (a.command) html += ': <code>' + esc(a.command) + '</code>';
    if (a.reference) html += ' (' + esc(a.reference) + ')';
    return html;
  }

  function rowHtml(r) {
    var ops = Object.keys(r.operands || {}).map(function (k) {
      return esc(k) + ': ' + esc(r.operands[k]);
    }).join(', ');
    return '<li class="list-group-item small" data-attention-row="' + esc(r.id)
      + '" data-attention-source="' + esc(r.source) + '">'
      + '<span class="badge ' + (BADGE[r.level] || 'bg-danger') + ' me-2">'
      + esc(LEVEL_WORDS[r.level] || r.level) + '</span>'
      + '<strong>' + esc(r.what) + '</strong>'
      + ((r.devices || []).length ? ' on ' + r.devices.map(esc).join(', ') : '')
      + '<div class="text-muted">since ' + when(r.since) + '</div>'
      + '<div>' + esc(r.cause) + '</div>'
      + (ops ? '<div class="text-muted">' + ops + '</div>' : '')
      // A row about ANOTHER row is folded into it (one event, one row); one
      // that still stands alone says why, because its target is not here.
      + ((r.attached || []).map(function (a) {
          return '<div class="text-muted">Also: ' + esc(a.what) + ' (' + esc(a.source)
            + ', since ' + when(a.since) + ')</div>';
        }).join(''))
      + (r.attach_to ? '<div class="text-muted">It is about ' + esc(r.attach_to)
         + ', which is not on this page: the last run no longer reports it</div>' : '')
      + '<div>Action: ' + actionHtml(r.action) + '</div>'
      // Stage 8's triage attaches HERE, on the row it answers (NSOT_PLAN 8.6).
      + (r.triage ? '<div class="border-start ps-2 mt-1">Triage: ' + esc(r.triage.summary)
         + '</div>' : '')
      + '</li>';
  }

  /* Pure: the panel for one payload. */
  function unreadableNote(d) {
    var u = d.unreadable || [];
    return u.length ? ' <span class="badge bg-secondary">' + u.length
      + ' source(s) could not be read: ' + u.map(esc).join(', ') + '</span>' : '';
  }

  function attentionPanelHtml(d) {
    if (!d || d.ok !== true) {
      return '<div class="alert alert-warning small mb-0" data-attention="unknown">'
        + '<strong>Could not ask what needs attention</strong>'
        + (d && d.error ? ': ' + esc(d.error) : '') + '. This is not the same as '
        + 'nothing needing attention.</div>';
    }
    var rows = d.rows || [];
    if (!rows.length) {
      var sources = d.sources || [];
      var allRead = sources.length > 0 && sources.every(function (s) {
        return s.state === 'read'; });
      // The full list whenever any source did not answer: that is when the
      // provenance matters, so it is never behind a click. (An unreadable
      // source is a row of its own too; this holds even if one forgot.)
      if (!allRead) {
        return '<div class="alert alert-light border small mb-0" data-attention="none">'
          + '<strong>' + esc(d.headline) + '</strong>. Looked at: '
          + sourcesLine(sources) + '.</div>';
      }
      // The healthy, common case: ONE line that still makes the positive
      // claim (every source answered, and how old the oldest value is), with
      // the full list one click away (the operator's (a), 2026-09-28).
      return '<details class="alert alert-light border small mb-0 py-1" data-attention="none">'
        + '<summary>' + summaryLine(d, sources) + '</summary>'
        + '<div class="mt-1">Looked at: ' + sourcesLine(sources) + '.</div></details>';
    }
    return '<div class="card border-warning" data-attention="rows">'
      + '<div class="card-header py-1 small"><strong>' + esc(d.headline) + '</strong>'
      + unreadableNote(d) + '</div>'
      + '<ul class="list-group list-group-flush">' + rows.map(rowHtml).join('')
      + '</ul><div class="card-footer py-1 small text-muted">Looked at: '
      + sourcesLine(d.sources) + '.</div></div>';
  }

  async function loadAttention() {
    var el = document.getElementById('needsAttentionPanel');
    if (!el) return;
    var d;
    try {
      var r = await fetch('/attention', {cache: 'no-store'});
      d = await r.json();
    } catch (e) {
      d = {ok: false, error: e.message};
    }
    // A person who opened the list keeps it open across the minute's redraw.
    var was = el.querySelector && el.querySelector('details[data-attention="none"]');
    var open = !!(was && was.open);
    el.innerHTML = attentionPanelHtml(d);
    var now = open && el.querySelector && el.querySelector('details[data-attention="none"]');
    if (now) now.open = true;
  }

  root.attentionPanelHtml = attentionPanelHtml;
  root.loadAttention = loadAttention;
  if (typeof document !== 'undefined' && document.addEventListener) {
    document.addEventListener('DOMContentLoaded', function () {
      loadAttention();
      timer = setInterval(loadAttention, 60000);
      // An action, or a background job's announcement (C58), that changes
      // what a source reads redraws the panel at once; the minute's poll
      // remains for the sources nothing announces (the receipts and records
      // written by another process).
      if (root.NMAS && root.NMAS.subscribe) {
        NMAS.subscribe('drift', 'attention', loadAttention, {panel: 'needsAttentionPanel'});
        NMAS.subscribe('approvals', 'attention', loadAttention, {panel: 'needsAttentionPanel'});
        NMAS.subscribe('pending', 'attention', loadAttention, {panel: 'needsAttentionPanel'});
        NMAS.subscribe('rolled_back', 'attention', loadAttention, {panel: 'needsAttentionPanel'});
        NMAS.subscribe('goldens', 'attention', loadAttention, {panel: 'needsAttentionPanel'});
        NMAS.subscribe('baselines', 'attention', loadAttention, {panel: 'needsAttentionPanel'});
        NMAS.subscribe('job_health', 'attention', loadAttention, {panel: 'needsAttentionPanel'});
      }
    });
  }
})(typeof window !== 'undefined' ? window : this);
