let _deployModal = null, _deployPlan = null;

function _dEsc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, c =>
    ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

async function openDeployPlan(hostnames) {
  if (!_deployModal) _deployModal = new bootstrap.Modal(document.getElementById('deployPlanModal'));
  const body = document.getElementById('deployPlanBody');
  body.innerHTML = '<div class="text-center py-4"><div class="spinner-border text-primary"></div>'
    + '<div class="small text-muted mt-2">Building the plan from captured configs…</div></div>';
  document.getElementById('deployApplyBtn').disabled = true;
  _deployModal.show();

  try {
    const r = await fetch('/deploy/plan', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({devices: hostnames}),
    });
    const d = await r.json();
    if (!d.ok) { body.innerHTML = `<div class="alert alert-danger mb-0">${_dEsc(d.error)}</div>`; return; }
    _deployPlan = d;
    _renderDeployPlan(d);
  } catch (e) {
    body.innerHTML = `<div class="alert alert-danger mb-0">${_dEsc(e.message)}</div>`;
  }
}

// Drawn by THE preview-then-confirm component (Stage 7.1): the six parts
// come from the server's one builder (`plan.preview`) and are drawn by
// `previewConfirmHtml`, the one renderer. This wizard supplies only wiring:
// which function a tick calls, and which a dangerous line's box calls.
function _renderDeployPlan(plan) {
  const body = document.getElementById('deployPlanBody');
  body.innerHTML = previewConfirmHtml(plan.preview, {
    selectable: true, onSelect: '_updateDeploySummary', authorise: '_reauthoriseDevice'});
  _updateDeploySummary();
}

// Authorising a line RE-PLANS the batch: the authorisation is folded into
// the command hash server-side, so the hash on screen must be the one for
// the program and the authorisation now shown. A device whose command hash
// changed is UNTICKED, so the operator confirms what they are now looking
// at; the others keep their ticks. Nothing is confirmed here, and the
// result is SHOWN before anyone can confirm it.
async function _reauthoriseDevice(device) {
  const authorise = {};
  document.querySelectorAll('#deployPlanBody input[data-auth-device]').forEach(b => {
    if (!b.checked) return;
    (authorise[b.dataset.authDevice] = authorise[b.dataset.authDevice] || []).push(b.dataset.line);
  });
  const kept = {};
  document.querySelectorAll('#deployPlanBody input[data-pc-select]:checked').forEach(b => {
    kept[b.dataset.device] = b.dataset.commandHash;
  });
  try {
    const r = await fetch('/deploy/plan', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({devices: (_deployPlan.devices || []).map(x => x.device), authorise}),
    });
    const d = await r.json();
    if (!d.ok) { showToast(d.error, 'danger'); return; }
    _deployPlan = d;
    _renderDeployPlan(d);
    document.querySelectorAll('#deployPlanBody input[data-pc-select]').forEach(b => {
      if (b.dataset.device !== device && !b.disabled
          && kept[b.dataset.device] === b.dataset.commandHash) b.checked = true;
    });
    _updateDeploySummary();
  } catch (e) { showToast(e.message, 'danger'); }
}

function _updateDeploySummary() {
  const boxes = [...document.querySelectorAll('#deployPlanBody input[data-pc-select]:checked')];
  const btn = document.getElementById('deployApplyBtn');
  const state = previewConfirmButton((_deployPlan || {}).preview, boxes.length,
                                     'Deploy confirmed devices');
  btn.disabled = state.disabled;
  btn.textContent = state.text;
  document.getElementById('deployPlanSummary').innerHTML = boxes.length
    ? `Confirmed: <strong>${boxes.map(b => _dEsc(b.dataset.device)).join(', ')}</strong>. `
      + 'Each device\'s stored capture is re-read at deploy time; one whose capture '
      + 'changed since this plan is skipped and reported, not deployed against a diff '
      + 'you did not see. A change made on the device itself since its capture is NOT '
      + 'detected: save its golden first.'
    : 'Tick the devices to deploy. Unticked devices are not touched.';
}

async function applyDeploy() {
  const boxes = [...document.querySelectorAll('#deployPlanBody input[data-pc-select]:checked')];
  // BOTH HASHES, CARRIED FROM THE PLAN THAT WAS RENDERED — never re-fetched.
  //
  // `command_hashes` is what makes /deploy/apply recompute the exact program
  // and compare it; without it the branch never runs, and this wizard sent
  // only `confirmations` from the day it was written. So a plan left open
  // while the device changed, or two people planning the same device, applied
  // against a program nobody had read.
  //
  // The values live in the DOM because they must be the ones the operator was
  // shown. Re-fetching the plan at confirm time would recompute against
  // whatever is current and agree with itself — the comparison would pass by
  // construction, which is the failure the confirm hash exists to prevent.
  const confirmations = {}, commandHashes = {}, authorise = {};
  boxes.forEach(b => {
    confirmations[b.dataset.device] = b.dataset.hash;
    if (b.dataset.commandHash) commandHashes[b.dataset.device] = b.dataset.commandHash;
    // The authorisation the RENDERED plan's hash covers, from the plan
    // payload, never re-read from checkboxes: a box changed without a
    // re-plan would send lines the hash does not cover, and apply refuses.
    const entry = ((_deployPlan || {}).devices || []).find(x => x.device === b.dataset.device);
    if (entry && (entry.authorised || []).length) authorise[b.dataset.device] = entry.authorised;
  });

  const btn = document.getElementById('deployApplyBtn');
  btn.disabled = true;
  btn.textContent = 'Deploying…';
  const body = document.getElementById('deployPlanBody');

  try {
    const r = await fetch('/deploy/apply', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({confirmations, command_hashes: commandHashes, authorise}),
    });
    const d = await r.json();
    if (!d.ok) { showToast(d.error, 'danger'); btn.disabled = false; return; }
    _renderDeployResult(d);
  } catch (e) {
    body.innerHTML = `<div class="alert alert-danger mb-0">${_dEsc(e.message)}</div>`;
  } finally {
    btn.textContent = 'Deploy confirmed devices';
  }
}

const _OUTCOME_STYLE = {
  deployed: 'success', skipped_drifted: 'warning', refused: 'warning',
  failed: 'danger', unattempted: 'secondary', skipped_not_selected: 'secondary',
};

// What was SENT is recorded per device (C60). A receipt that could not be
// written is drawn in red, because the deploy happened and its record did not:
// a silent failure here is a deploy nobody can later account for.
function _receiptLine(receipts) {
  if (!receipts) {
    return '<p class="small text-warning mb-0" data-receipt="absent">No receipt was reported for this deploy.</p>';
  }
  if (!receipts.ok) {
    return `<p class="small text-danger mb-0" data-receipt="failed"><strong>Receipt not written:</strong> ${_dEsc(receipts.error)}</p>`;
  }
  return `<p class="small text-muted mb-0" data-receipt="ok">Receipt: ${receipts.written} device row(s) recorded, each with the program sent and the checks that ran.</p>`;
}

// Which checks RAN on this device, from verify's own record (C62): a device
// with no routing protocol is a real state, and a device verify never
// reached says so, so neither can read as "checked and fine".
function _checkedCell(r) {
  const v = r.verify;
  if (!v || !Object.keys(v).length) {
    return r.outcome === 'refused' ? '<span class="text-muted">nothing sent</span>'
                                   : '<span class="text-warning">not verified</span>';
  }
  const names = v.checked_protocols || [];
  const what = names.length ? names.map(_dEsc).join(', ')
                            : 'no routing protocol on this device';
  const issues = (v.issues || []).map(i => `<div class="text-danger">${_dEsc(i)}</div>`).join('');
  return `${v.ok ? '' : '<span class="badge bg-danger me-1">failed</span>'}${what}${issues}`;
}

function _renderDeployResult(report) {
  const body = document.getElementById('deployPlanBody');
  document.getElementById('deployApplyBtn').classList.add('d-none');

  body.innerHTML = `
    ${report.breaker_tripped ? `
      <div class="alert alert-danger py-2 px-3">
        <strong>Stopped early.</strong> ${_dEsc(report.breaker_reason)}
        Repeated verify failures suggest something systemic rather than one
        device having been touched.
      </div>` : ''}
    <div class="table-responsive"><table class="table table-sm align-middle">
      <thead><tr><th>Device</th><th>Outcome</th><th>Detail</th><th>Checked</th><th>Golden</th></tr></thead>
      <tbody>${report.results.map(r => `
        <tr>
          <td class="fw-semibold">${_dEsc(r.device)}</td>
          <td><span class="badge bg-${_OUTCOME_STYLE[r.outcome] || 'secondary'}">
            ${_dEsc(r.outcome.replace(/_/g, ' '))}</span></td>
          <td class="small">
            ${_dEsc(r.reason || '')}
            ${r.stage ? `<div class="text-muted">stopped at: ${_dEsc(r.stage)}</div>` : ''}
            ${(r.commands || []).length
              ? `<div class="text-muted" data-sent>sent ${r.commands.length} line(s), program ${_dEsc((r.program_hash || '').slice(0, 8))}</div>` : ''}
            ${r.rolled_back ? '<span class="badge bg-info text-dark ms-1">rolled back</span>' : ''}
            ${(r.pending_convergence || []).length
              ? `<div class="text-muted">${r.pending_convergence.map(_dEsc).join('<br>')}</div>` : ''}
            ${r.outcome === 'skipped_drifted'
              ? `<button class="btn btn-outline-primary btn-sm mt-1"
                         onclick="openDeployPlan(['${_dEsc(r.device)}'])">Re-preview</button>` : ''}
          </td>
          <td class="small" data-checked>${_checkedCell(r)}</td>
          <td class="font-monospace small">${_dEsc((r.golden_commit || '').slice(0, 8))}</td>
        </tr>`).join('')}</tbody>
    </table></div>
    <p class="small text-muted mb-0">
      ${report.total} device(s) accounted for. Every device in a batch appears here.
    </p>
    ${_receiptLine(report.receipts)}`;

  const deployed = (report.deployed || []).length;
  showToast(`${deployed} deployed, ${report.total - deployed} not`,
            deployed ? 'success' : 'warning');
}
