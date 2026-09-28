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
      return '<div class="alert alert-light border small mb-0" data-attention="none">'
        + '<strong>' + esc(d.headline) + '</strong>. Looked at: '
        + sourcesLine(d.sources) + '.</div>';
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
    el.innerHTML = attentionPanelHtml(d);
  }

  root.attentionPanelHtml = attentionPanelHtml;
  root.loadAttention = loadAttention;
  if (typeof document !== 'undefined' && document.addEventListener) {
    document.addEventListener('DOMContentLoaded', function () {
      loadAttention();
      timer = setInterval(loadAttention, 60000);
    });
  }
})(typeof window !== 'undefined' ? window : this);
