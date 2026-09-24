// The freshness signal: is what Oxidized holds the state somebody approved?
//
// A REPORT, not a gate. It refuses nothing. Its value is timing -- the
// sanitiser's gate discovers divergence when somebody is already preparing a
// redeploy; this discovers it while the person who caused it still remembers
// what they did.
//
// `freshnessSignalHtml` is PURE so the shipped source can be executed in a
// test against a real payload. Three guards in one feature each hid the same
// data once in this project, and every server test passed at each stage.

function _freshEscape(text) {
  const d = document.createElement('div');
  d.textContent = text === null || text === undefined ? '' : String(text);
  return d.innerHTML;
}

const _FRESH_VERDICTS = {
  match:        ['bg-success',   'approved'],
  poll_race:    ['bg-info',      'poll race'],
  authorised:   ['bg-warning',   'authorised'],
  unapproved:   ['bg-danger',    'UNAPPROVED'],
  inconclusive: ['bg-secondary', 'inconclusive'],
};

function freshnessSignalHtml(data) {
  // THE ERROR BRANCH COMES FIRST, and it says what the failure is NOT.
  // A panel that renders "nothing has diverged" because the query failed is
  // this feature's own wrong-and-looks-right state -- the same correction the
  // pending banner needed, and the same one as "all 9 clean" over ten devices.
  if (!data || data.ok !== true) {
    const why = _freshEscape((data && (data.error || data.defect)) || 'no answer');
    return '<div class="alert alert-warning py-2 mb-0 small">' +
           '<strong>The comparison could not run.</strong> ' + why +
           '<div class="text-muted mt-1">This is <em>not</em> the same as ' +
           'nothing having diverged &mdash; nothing was compared.</div></div>';
  }

  const counts = data.counts || {};
  const rows = (data.devices || []).filter(r => r.verdict !== 'match');
  const head = '<div class="small text-muted mb-2">' +
        _freshEscape(data.summary || '') + '</div>';

  if (!rows.length) {
    return head + '<div class="text-success small">' +
      'Every device Oxidized holds matches the approved config.</div>';
  }

  let html = head + '<div class="table-responsive"><table class="table table-sm ' +
             'table-dark align-middle mb-0"><tbody>';
  for (const row of rows) {
    const [cls, label] = _FRESH_VERDICTS[row.verdict] || ['bg-secondary', row.verdict];
    html += '<tr><td style="width:6rem"><span class="badge ' + cls + '">' +
            _freshEscape(label) + '</span></td>' +
            '<td><strong>' + _freshEscape(row.device) + '</strong>' +
            '<div class="text-muted small">' + _freshEscape(row.reason || '') + '</div>';
    const diff = (row.only_right || []).slice(0, 4)
      .map(l => '<div class="text-danger small">+ ' + _freshEscape(l) + '</div>').join('') +
      (row.only_left || []).slice(0, 4)
      .map(l => '<div class="text-info small">- ' + _freshEscape(l) + '</div>').join('');
    html += diff;
    if (row.fingerprint) {
      // Shown because an authorisation names THIS divergence and no other.
      html += '<div class="text-muted small font-monospace">fingerprint ' +
              _freshEscape(row.fingerprint.slice(0, 16)) + '</div>';
    }
    html += '</td></tr>';
  }
  html += '</tbody></table></div>';
  for (const note of (data.errors || [])) {
    html += '<div class="text-warning small mt-1">' + _freshEscape(note) + '</div>';
  }
  return html;
}

async function loadFreshnessSignal() {
  const body = document.getElementById('freshnessBody');
  if (!body) { console.error('freshness: no container'); return; }
  body.innerHTML = '<span class="text-muted small">checking…</span>';
  let data;
  try {
    const resp = await fetch('/freshness/report');
    data = await resp.json();
  } catch (err) {
    // A failed fetch is reported as a failed fetch. It is never rendered as
    // "nothing has diverged".
    data = { ok: false, error: String(err) };
  }
  body.innerHTML = freshnessSignalHtml(data);
  const stamp = document.getElementById('freshnessStamp');
  if (stamp) stamp.textContent = new Date().toLocaleTimeString();
}

// Registers its own initialiser. `loadOnboardPending` shipped with its only
// callers inside the banner it drew, so the banner could appear only after
// using a control that appeared only once it had.
document.addEventListener('DOMContentLoaded', loadFreshnessSignal);
