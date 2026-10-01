let _deployModal = null, _deployPlan = null;
// P.9 step (b): 'profile' scopes the plan to the network's monitoring
// profile's lines; the list, when the opener names one, is carried to the
// plan and the apply (a write never derives its list).
let _deployScope = '', _deployList = '';

// The body every plan and apply request carries besides its own fields.
function _deployCommon() {
  const c = {};
  if (_deployScope) c.scope = _deployScope;
  if (_deployList) c.list_name = _deployList;
  return c;
}

function _dEsc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, c =>
    ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

async function openDeployPlan(hostnames, opts) {
  opts = opts || {};
  _deployScope = opts.scope || '';
  _deployList = opts.list || '';
  if (!_deployModal) _deployModal = new bootstrap.Modal(document.getElementById('deployPlanModal'));
  document.getElementById('deployPlanTitle').textContent =
    _deployScope === 'profile' ? 'Apply monitoring profile' : 'Deploy from template';
  document.getElementById('deployApplyBtn').classList.remove('d-none');
  const body = document.getElementById('deployPlanBody');
  body.innerHTML = '<div class="text-center py-4"><div class="spinner-border text-primary"></div>'
    + '<div class="small text-muted mt-2">Building the plan from captured configs…</div></div>';
  document.getElementById('deployApplyBtn').disabled = true;
  _deployModal.show();

  try {
    const r = await fetch('/deploy/plan', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(Object.assign(_deployCommon(), {devices: hostnames})),
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
    selectable: true, onSelect: '_updateDeploySummary', authorise: '_reauthoriseDevice',
    remove: '_reauthoriseDevice'});
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
  // Each authorisation carries the person's stated reason (C140), read from
  // the reason field beside its box; the server refuses one without.
  document.querySelectorAll('#deployPlanBody input[type=checkbox][data-auth-device]').forEach(b => {
    if (!b.checked) return;
    const reasonEl = Array.from(
      document.querySelectorAll('#deployPlanBody input[data-auth-reason]')).find(
      r => r.dataset.authDevice === b.dataset.authDevice && r.dataset.line === b.dataset.line);
    (authorise[b.dataset.authDevice] = authorise[b.dataset.authDevice] || []).push(
      {line: b.dataset.line, reason: reasonEl ? reasonEl.value : ''});
  });
  // A removal's line has no box: its tick was made where it was selected, and
  // a reason given here is what authorises it (Mode B).
  document.querySelectorAll('#deployPlanBody input[data-auth-reason][data-auth-removal]').forEach(r => {
    if (!r.value.trim()) return;
    (authorise[r.dataset.authDevice] = authorise[r.dataset.authDevice] || []).push(
      {line: r.dataset.line, reason: r.value});
  });
  // Mode B: the lines ticked for removal, BY ID, per device.
  const remove = {};
  document.querySelectorAll('#deployPlanBody input[type=checkbox][data-remove-id]').forEach(b => {
    if (b.checked) (remove[b.dataset.removeDevice] = remove[b.dataset.removeDevice] || []).push(
      b.dataset.removeId);
  });
  const kept = {};
  document.querySelectorAll('#deployPlanBody input[data-pc-select]:checked').forEach(b => {
    kept[b.dataset.device] = b.dataset.commandHash;
  });
  try {
    const r = await fetch('/deploy/plan', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(Object.assign(_deployCommon(), {
        devices: (_deployPlan.devices || []).map(x => x.device), authorise, remove})),
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
                                     _deployScope === 'profile'
                                       ? 'Apply the profile to confirmed devices'
                                       : 'Deploy confirmed devices');
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
  const confirmations = {}, commandHashes = {}, authorise = {}, remove = {};
  boxes.forEach(b => {
    confirmations[b.dataset.device] = b.dataset.hash;
    if (b.dataset.commandHash) commandHashes[b.dataset.device] = b.dataset.commandHash;
    // The authorisation the RENDERED plan's hash covers, from the plan
    // payload, never re-read from checkboxes: a box changed without a
    // re-plan would send lines the hash does not cover, and apply refuses.
    const entry = ((_deployPlan || {}).devices || []).find(x => x.device === b.dataset.device);
    if (entry && (entry.authorised || []).length) authorise[b.dataset.device] = entry.authorised;
    // The removals the RENDERED plan's hash covers, by ID, from the payload.
    const ids = ((entry || {}).removals || {}).ids || [];
    if (ids.length) remove[b.dataset.device] = ids;
  });

  const btn = document.getElementById('deployApplyBtn');
  btn.disabled = true;
  btn.textContent = 'Deploying…';
  const body = document.getElementById('deployPlanBody');

  inFlightBusy(true);          // the panel says what runs meanwhile (C99)
  try {
    const r = await fetch('/deploy/apply', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(Object.assign(_deployCommon(), {
        confirmations, command_hashes: commandHashes, authorise, remove})),
    });
    const d = await r.json();
    if (!d.ok) { showToast(d.error, 'danger'); btn.disabled = false; return; }
    _renderDeployResult(d);
  } catch (e) {
    body.innerHTML = `<div class="alert alert-danger mb-0">${_dEsc(e.message)}</div>`;
  } finally {
    inFlightBusy(false);
    btn.textContent = _deployScope === 'profile' ? 'Apply the profile to confirmed devices'
                                                 : 'Deploy confirmed devices';
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
  body.innerHTML = previewConfirmResultHtml(report.result, {repreview: '_deployRepreview'});
  showToast((report.result && report.result.happened && report.result.happened.summary) || 'Deploy finished',
            previewConfirmResultLevel(report.result));
}

// "Preview again" keeps what the plan was: scoped to the profile stays scoped.
function _deployRepreview(hostnames) {
  openDeployPlan(hostnames, {scope: _deployScope, list: _deployList});
}

// APPLY MONITORING PROFILE (P.9 step b): the deploy plan scoped to the
// network's monitoring profile's lines. Opened by any element carrying
// data-nmas-open="profile_apply" (Needs attention's "not monitored" row, the
// Device page), and by the URL ?open=profile_apply&device=<name>&list=<list>
// the redesigned pages link to, since they do not carry this wizard yet.
// *device*: one name, or several separated by commas (a proposal's result
// opens it for every device that inherits).
function openProfileApply(device, listName) {
  const devices = String(device || '').split(',').map(s => s.trim()).filter(Boolean);
  openDeployPlan(devices, {scope: 'profile', list: listName || ''});
}

if (typeof document !== 'undefined' && document.addEventListener) {
  document.addEventListener('click', e => {
    const b = e.target && e.target.closest && e.target.closest('[data-nmas-open="profile_apply"]');
    if (b) openProfileApply(b.dataset.nmasDevice, b.dataset.nmasList);
  });
  document.addEventListener('DOMContentLoaded', () => {
    const q = new URLSearchParams(window.location.search);
    // Several devices arrive as repeated `device` parameters (Monitoring >
    // Coverage's form) or one comma-separated value (a proposal's result).
    if (q.get('open') === 'profile_apply' && q.get('device')) {
      openProfileApply(q.getAll('device').join(','), q.get('list') || '');
    }
    // The v2 Devices list's selection bar ("Plan a deploy…"): the devices
    // ticked there, planned here until v2 carries the deploy.
    if (q.get('open') === 'deploy' && q.get('device')) {
      openDeployPlan(q.getAll('device'), {list: q.get('list') || ''});
    }
  });
}
