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
  // ANSWER FIRST (the operator's presentation rule, 2026-09-28): what needs
  // attention is a change nobody approved, or a device that cannot be told.
  // A poll race and an authorised divergence are evidence, one level down
  // with the counts, beside what was compared.
  const problems = (data.devices || []).filter(r => r.verdict === 'unapproved' ||
                                                    r.verdict === 'inconclusive');
  const others = (data.devices || []).filter(r => r.verdict === 'poll_race' ||
                                                  r.verdict === 'authorised');
  let html = problems.length ? _freshTable(problems)
    : '<div class="text-success small">No device holds a change nobody approved.</div>';
  for (const note of (data.errors || [])) {
    html += '<div class="text-warning small mt-1">' + _freshEscape(note) + '</div>';
  }
  html += '<details class="small text-muted mt-1" data-freshness="evidence"><summary>What was '
    + 'compared</summary><div>' + _freshEscape(data.summary || '') + '</div>'
    + (others.length ? _freshTable(others) : '') + '</details>';
  return html;
}

function _freshTable(rows) {
  let html = '<div class="table-responsive"><table class="table table-sm ' +
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
  return html;
}

let _freshLast = null;

async function loadFreshnessSignal() {
  const body = document.getElementById('freshnessBody');
  if (!body) { console.error('freshness: no container'); return; }
  let data;
  try {
    // The STORED comparison (the freshness reader, 7.2), never Oxidized: this
    // was one Oxidized fetch per device on every page load.
    const resp = await fetch('/freshness/report');
    data = await resp.json();
  } catch (err) {
    // A failed fetch is reported as a failed fetch. It is never rendered as
    // "nothing has diverged".
    data = { ok: false, error: String(err) };
  }
  _freshLast = data;
  body.innerHTML = freshnessSignalHtml(data);
  // The live-data contract: the age of the VALUE against the reader's own
  // promise, redrawn on the page's tick. The old stamp was the fetch time,
  // which made an hour-old comparison look current.
  if (window.NMAS && window.NMAS.stamp) {
    const at = data && data.value_at ? Date.parse(data.value_at) : null;
    window.NMAS.stamp('freshnessBody', isNaN(at) ? null : at,
                      data && data.stale_after_seconds, 'Freshness', function () {
      body.innerHTML = freshnessSignalHtml(_freshLast);
    });
  }
}

// Registers its own initialiser. `loadOnboardPending` shipped with its only
// callers inside the banner it drew, so the banner could appear only after
// using a control that appeared only once it had.
document.addEventListener('DOMContentLoaded', function () {
  loadFreshnessSignal();
  // The reader announces when it finishes (C58): redraw from the new value.
  if (window.NMAS && window.NMAS.subscribe) {
    NMAS.subscribe('freshness', 'freshnessSignal', loadFreshnessSignal, {panel: 'freshnessBody'});
  }
});
