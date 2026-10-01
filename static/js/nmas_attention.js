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
               unknown: 'bg-secondary', info: 'bg-info text-dark'};
  var LEVEL_WORDS = {danger: 'needs action', warning: 'check',
                     unknown: 'cannot tell', info: 'information'};

  function when(iso) {
    return iso ? esc(iso.replace('T', ' ').replace('Z', ' UTC')) : 'not recorded';
  }

  /* A source is STALE when its value is older than the source's own promise
     (`stale_after_seconds`), judged on the page's clock (the live-data
     contract): a producer that stopped announces nothing, and the page must
     say so without another request. */
  function isStale(s, nowMs) {
    if (!s || s.state !== 'read' || !s.stale_after_seconds || !s.value_at) return false;
    var at = Date.parse(s.value_at);
    return !isNaN(at) && nowMs - at > s.stale_after_seconds * 1000;
  }

  function ago(ms) {
    var s = Math.max(0, Math.round(ms / 1000));
    return s < 90 ? s + ' s ago' : s < 5400 ? Math.round(s / 60) + ' min ago'
      : s < 172800 ? Math.round(s / 3600) + ' h ago' : Math.round(s / 86400) + ' d ago';
  }

  function ageOf(iso, nowMs) {
    var at = iso ? Date.parse(iso) : NaN;
    return isNaN(at) ? 'not recorded' : ago(nowMs - at);
  }

  /* THE EVIDENCE, one level down (the operator's presentation rule for Stage
     7, 2026-09-28: the screen answers the question the person came with, and
     the evidence for the answer is one level down). One row per source: what
     it found and how old its value is, scannable down a column. The debugger's
     detail (absolute times, the read's cost, the endpoints) is on hover, not
     in the reader's way. */
  function sourcesTable(sources, nowMs) {
    var body = (sources || []).map(function (s) {
      var stale = isStale(s, nowMs);
      var debug = 'value ' + (s.value_at || 'not recorded') + '; read ' + (s.read_at || '?')
        + ' in ' + s.took_ms + ' ms' + (s.stale_after_seconds
          ? '; promised current for ' + s.stale_after_seconds + ' s' : '')
        + (s.detail ? '; ' + s.detail : '');
      return '<tr data-attention-source-row="' + esc(s.source) + '" title="' + esc(debug) + '">'
        + '<td>' + esc(s.label) + '</td>'
        + (s.state === 'read'
          ? '<td>' + esc(s.checked) + '</td><td class="text-nowrap' + (stale ? ' text-danger' : '')
            + '">' + ageOf(s.value_at, nowMs) + (stale ? ' (stale)' : '') + '</td>'
          : '<td colspan="2" class="text-danger">could not be read</td>')
        + '</tr>';
    }).join('');
    return '<table class="table table-sm small mb-0" data-attention="sources">'
      + '<thead><tr><th>Source</th><th>Found</th><th>Value</th></tr></thead>'
      + '<tbody>' + body + '</tbody></table>';
  }

  /* A source that is stale, or did not answer, is something needing
     attention, so it is a ROW, never only a line in the evidence (the
     operator). The server already makes rows for a reader that stopped
     (job health's reader row) and a drift run past its bound: those are
     not drawn twice. */
  function sourceRows(sources, rows, nowMs) {
    var ids = {};
    (rows || []).forEach(function (r) { ids[r.id] = true; });
    var covered = function (s) {
      if (s.reader && ids['job_health:reader:' + s.reader]) return true;
      return (rows || []).some(function (r) {
        return r.source === s.source && /:(stale|unreadable)$/.test(r.id || '');
      });
    };
    var out = [];
    (sources || []).forEach(function (s) {
      if (covered(s)) return;
      if (s.state !== 'read') {
        out.push({id: 'page:unread:' + s.source, source: s.source, level: 'unknown',
                  what: s.label + ' could not be read', devices: [], since: s.read_at,
                  cause: 'This is not the same as nothing needing attention: whatever '
                    + 'this source would show is unknown.',
                  action: {label: 'Find why the source cannot be read', known: false}});
      } else if (isStale(s, nowMs)) {
        out.push({id: 'page:stale:' + s.source, source: s.source, level: 'warning',
                  what: s.label + "'s value is older than its source promises",
                  devices: [], since: null,
                  cause: 'Its value is ' + ageOf(s.value_at, nowMs) + ', and it promises to be '
                    + 'current for ' + s.stale_after_seconds + ' s: what produces it has '
                    + 'stopped, or this page has stopped hearing it.',
                  action: {label: 'Reload the page to ask again; if it stays, the reader has '
                                  + 'stopped (see job health)', known: false}});
      }
    });
    return out;
  }

  /* PURE: the collapsed claim. The OLDEST value is named, with its source,
     because a summary is only as fresh as its weakest source, and a value
     that is old for a reason (a baseline decided days ago) reads as that
     source's age rather than as the page's. */
  function summaryLine(d, sources, nowMs) {
    if (nowMs == null) nowMs = Date.now();
    var readAt = sources.map(function (s) { return s.read_at || ''; }).sort().pop();
    var oldest = sources.filter(function (s) { return s.value_at; })
      .sort(function (a, b) { return a.value_at < b.value_at ? -1 : a.value_at > b.value_at ? 1 : 0; })[0];
    return '<strong>' + esc(d.headline) + '</strong> &middot; ' + sources.length + ' of '
      + sources.length + ' sources answered, read <span title="' + esc(readAt) + '">'
      + ageOf(readAt, nowMs) + '</span>'
      + (oldest ? ' &middot; oldest value: ' + esc(oldest.label) + ', <span title="'
         + esc(oldest.value_at) + '">' + ageOf(oldest.value_at, nowMs) + '</span>' : '');
  }

  function actionHtml(a) {
    a = a || {};
    var html = a.known === false
      ? '<span class="text-muted">' + esc(a.label) + '</span>'
      : '<strong>' + esc(a.label) + '</strong>';
    // An action that is an operation of the tool opens it (the break-glass
    // export, 7.3); the command beside it is the host-side way.
    if (a.open === 'breakglass_export') {
      html += ' <button type="button" class="btn btn-sm btn-outline-danger py-0 ms-1" '
        + 'data-nmas-open="breakglass_export" data-nmas-list="' + esc(a.list || '') + '">'
        + 'Export…</button>';
    }
    // The Update button (the operator, 2026-09-30): one page, on the redesign.
    if (a.open === 'app_update') {
      html += ' <a class="btn btn-sm btn-outline-primary py-0 ms-1" data-nmas-update href="/v2/update">Update…</a>';
    }
    // The monitoring profile (P.9 step b): apply it, or propose it first.
    if (a.open === 'profile_apply') {
      html += ' <button type="button" class="btn btn-sm btn-outline-primary py-0 ms-1" '
        + 'data-nmas-open="profile_apply" data-nmas-device="' + esc(a.device || '') + '" '
        + 'data-nmas-list="' + esc(a.list || '') + '">Preview…</button>';
    }
    if (a.open === 'profile_propose') {
      html += ' <button type="button" class="btn btn-sm btn-outline-primary py-0 ms-1" '
        + 'data-nmas-open="profile_propose" data-nmas-list="' + esc(a.list || '') + '">Propose…</button>';
    }
    // A page on the redesign that shows the evidence (C38: a device's Neighbours).
    if (a.href && /^\/v2\//.test(a.href)) {
      html += ' <a class="btn btn-sm btn-outline-primary py-0 ms-1" href="' + esc(a.href) + '">Open…</a>';
    }
    if (a.command) html += (a.open ? ' or on the host' : '') + ': <code>' + esc(a.command) + '</code>';
    if (a.reference) html += ' (' + esc(a.reference) + ')';
    return html;
  }

  /* One incident member (a Grafana alert instance): the rule, its kind,
     WHERE its device came from (8.6: from a label, the line or an
     address, and the reader says which), and its onset with the basis. */
  function memberHtml(m) {
    return '<li>' + esc(m.rule) + ' (' + esc(m.kind) + ')'
      + (m.device ? ' on <strong>' + esc(m.device) + '</strong>' : '')
      + ': device ' + esc(m.device_note) + '; onset ' + when(m.onset)
      + ' (' + esc(m.onset_basis) + ')'
      + silencesHtml(m)
      + '</li>';
  }

  /* A silence set in Grafana, with who and until when (the operator,
     2026-09-30); an id the silence list did not return is named as that. */
  function silencesHtml(m) {
    var list = (m.silences || []).length ? m.silences
      : (m.silenced_by || []).map(function (i) { return { id: i, unresolved: true }; });
    return list.map(function (s) {
      if (s.unresolved) {
        return '; <strong>silenced in Grafana</strong> by silence ' + esc(s.id)
          + ', whose author and end Grafana did not return';
      }
      return '; <strong>silenced in Grafana</strong> by ' + esc(s.created_by || 'an unnamed account')
        + ' until ' + when(s.ends_at)
        + (s.comment ? ' (&ldquo;' + esc(s.comment) + '&rdquo;)' : '');
    }).join('');
  }

  function operandValue(v) {
    if (v && typeof v === 'object' && v.length !== undefined) {
      return v.map(function (x) { return typeof x === 'object' ? JSON.stringify(x) : x; })
        .map(esc).join(', ');
    }
    return esc(typeof v === 'object' && v !== null ? JSON.stringify(v) : v);
  }

  function rowHtml(r, nowMs) {
    r = r || {};
    if (nowMs == null) nowMs = Date.now();
    var members = (r.operands || {}).members || [];
    var ops = Object.keys(r.operands || {}).filter(function (k) { return k !== 'members'; })
      .map(function (k) { return esc(k) + ': ' + operandValue(r.operands[k]); }).join(', ');
    return '<li class="list-group-item small" data-attention-row="' + esc(r.id)
      + '" data-attention-source="' + esc(r.source) + '">'
      + '<span class="badge ' + (BADGE[r.level] || 'bg-danger') + ' me-2">'
      + esc(LEVEL_WORDS[r.level] || r.level) + '</span>'
      + '<strong>' + esc(r.what) + '</strong>'
      + ((r.devices || []).length ? ' on ' + r.devices.map(esc).join(', ') : '')
      + '<div class="text-muted">since ' + (r.since ? '<span title="' + esc(r.since) + '">'
         + ageOf(r.since, nowMs) + '</span>' : 'not recorded') + '</div>'
      + '<div>' + esc(r.cause) + '</div>'
      + (ops ? '<div class="text-muted">' + ops + '</div>' : '')
      + (members.length ? '<ul class="small mb-0">' + members.map(memberHtml).join('') + '</ul>' : '')
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

  function attentionPanelHtml(d, nowMs) {
    if (nowMs == null) nowMs = Date.now();
    if (!d || d.ok !== true) {
      return '<div class="alert alert-warning small mb-0" data-attention="unknown">'
        + '<strong>Could not ask what needs attention</strong>'
        + (d && d.error ? ': ' + esc(d.error) : '') + '. This is not the same as '
        + 'nothing needing attention.</div>';
    }
    var sources = d.sources || [];
    // What needs attention: the server's rows, and any source that is stale
    // or did not answer, as a row of its own (never only in the evidence).
    var rows = (d.rows || []).concat(sourceRows(sources, d.rows, nowMs));
    if (!rows.length) {
      // The healthy, common case: ONE line that still makes the positive
      // claim (every source answered, how old the oldest value is), with the
      // evidence one level down (the operator's (a), 2026-09-28).
      return '<details class="alert alert-light border small mb-0 py-1" data-attention="none">'
        + '<summary>' + summaryLine(d, sources, nowMs) + '</summary>'
        + '<div class="mt-1">' + sourcesTable(sources, nowMs) + '</div></details>';
    }
    var headline = rows.length === (d.rows || []).length ? d.headline
      : rows.length + ' thing(s) need attention';
    return '<div class="card border-warning" data-attention="rows">'
      + '<div class="card-header py-1 small"><strong>' + esc(headline) + '</strong>'
      + unreadableNote(d) + '</div>'
      + '<ul class="list-group list-group-flush">' + rows.map(function (r) { return rowHtml(r, nowMs); }).join('')
      + '</ul><details class="card-footer py-1 small text-muted" data-attention="evidence">'
      + '<summary>What was checked: ' + sources.length + ' source(s)</summary>'
      + sourcesTable(sources, nowMs) + '</details></div>';
  }

  //: The panel's own promise: it re-fetches every minute (for the sources
  //: nothing announces yet), so a value older than 2.5 minutes means the
  //: fetches stopped. The page marks itself stale past it.
  var PANEL_STALE_AFTER = 150;
  var last = null;

  function draw(nowMs) {
    var el = document.getElementById('needsAttentionPanel');
    if (!el || !last) return;
    // A person who opened the list keeps it open across every redraw.
    var was = el.querySelector && el.querySelector('details[data-attention="none"]');
    var open = !!(was && was.open);
    el.innerHTML = attentionPanelHtml(last, nowMs);
    var again = open && el.querySelector && el.querySelector('details[data-attention="none"]');
    if (again) again.open = true;
  }

  function newestRead(d) {
    var reads = ((d && d.sources) || []).map(function (s) { return s.read_at || ''; }).sort();
    var at = reads.length ? Date.parse(reads[reads.length - 1]) : NaN;
    return isNaN(at) ? null : at;
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
    last = d;
    draw(Date.now());
    // The live-data contract: the panel shows its own age and marks itself
    // stale, and the tick redraws it from `last` so each source's age is
    // judged again without a request.
    if (root.NMAS && root.NMAS.stamp) {
      NMAS.stamp('needsAttentionPanel', newestRead(d), PANEL_STALE_AFTER,
                 'Needs attention', draw, {ownAge: true});
    }
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
        NMAS.subscribe('alerts', 'attention', loadAttention, {panel: 'needsAttentionPanel'});
        NMAS.subscribe('freshness', 'attention', loadAttention, {panel: 'needsAttentionPanel'});
        NMAS.subscribe('adjacencies', 'attention', loadAttention, {panel: 'needsAttentionPanel'});
        NMAS.subscribe('lab_startup', 'attention', loadAttention, {panel: 'needsAttentionPanel'});
        NMAS.subscribe('integration_health', 'attention', loadAttention, {panel: 'needsAttentionPanel'});
        NMAS.subscribe('ci_verdict', 'attention', loadAttention, {panel: 'needsAttentionPanel'});
        NMAS.subscribe('reachability', 'attention', loadAttention, {panel: 'needsAttentionPanel'});
      }
    });
  }
})(typeof window !== 'undefined' ? window : this);
