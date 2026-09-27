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

// Drawn by THE result half of the preview-then-confirm component (7.1 step
// 2): the server builds `report.result` from the receipt rows it wrote, and
// `previewConfirmResultHtml` draws it. This wizard supplies only wiring (a
// skipped device's "Preview again" reopens the plan for it), and the toast's
// colour is the server's level, never a guess made here.
function _renderDeployResult(report) {
  const body = document.getElementById('deployPlanBody');
  document.getElementById('deployApplyBtn').classList.add('d-none');
  body.innerHTML = previewConfirmResultHtml(report.result, {repreview: 'openDeployPlan'});
  showToast((report.result && report.result.happened && report.result.happened.summary) || 'Deploy finished',
            previewConfirmResultLevel(report.result));
}
