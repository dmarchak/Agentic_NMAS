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

function _renderDeployPlan(plan) {
  const body = document.getElementById('deployPlanBody');
  body.innerHTML = `
    <div class="alert alert-info py-2 px-3 small">
      <strong>Merge only.</strong> Lines the template defines that are missing from
      the device are added. Lines on the device that the template does not mention
      are listed as warnings and <strong>never removed</strong> — this tool does
      not generate <code>no</code> commands.
    </div>
    ${plan.devices.map(d => _deviceCard(d)).join('')}`;
  _updateDeploySummary();
}

function _deviceCard(d) {
  const id = 'dep_' + d.device.replace(/[^a-z0-9]/gi, '_');
  const blocked = !d.deployable;
  return `
    <div class="card mb-2 ${blocked ? 'border-warning-subtle' : 'border-light-subtle'}">
      <div class="card-body py-2 px-3">
        <div class="d-flex align-items-center gap-2 flex-wrap">
          <div class="form-check">
            <input class="form-check-input" type="checkbox" id="${id}"
                   data-device="${_dEsc(d.device)}" data-hash="${_dEsc(d.capture_hash || '')}"
                   data-command-hash="${_dEsc(d.command_hash || '')}"
                   ${blocked ? 'disabled' : ''} onchange="_updateDeploySummary()">
            <label class="form-check-label fw-semibold" for="${id}">${_dEsc(d.device)}</label>
          </div>
          ${blocked
            ? '<span class="badge bg-warning text-dark">not deployable</span>'
            : '<span class="badge bg-success">deployable</span>'}
          <span class="text-muted small">${_dEsc(d.template || '')}</span>
          ${d.to_add && d.to_add.length
            ? `<span class="badge bg-primary-subtle text-primary-emphasis">+${d.to_add.length} line(s)</span>`
            : '<span class="badge bg-secondary-subtle text-secondary-emphasis">no changes</span>'}
          ${d.removal_warnings && d.removal_warnings.length
            ? `<span class="badge bg-warning-subtle text-warning-emphasis">${d.removal_warnings.length} not removed</span>`
            : ''}
        </div>

        ${blocked ? `
          <ul class="small text-warning-emphasis mt-2 mb-0">
            ${(d.blocking_reasons || []).map(r => `<li>${_dEsc(r)}</li>`).join('')}
          </ul>` : ''}

        ${d.to_add && d.to_add.length ? `
          <details class="mt-2"><summary class="small">Will add (${d.to_add.length})</summary>
            <pre class="small bg-body-tertiary p-2 rounded mt-1 mb-0"
                 style="max-height:220px;overflow:auto">${_dEsc(d.to_add.join('\n'))}</pre>
          </details>` : ''}

        ${d.removal_warnings && d.removal_warnings.length ? `
          <details class="mt-2">
            <summary class="small text-warning-emphasis">
              Will NOT remove (${d.removal_warnings.length})
            </summary>
            <p class="small text-muted mt-1 mb-1">
              On the device but absent from the template. Remove them by hand, or
              adopt them into the template.
            </p>
            <pre class="small bg-body-tertiary p-2 rounded mb-0"
                 style="max-height:180px;overflow:auto">${_dEsc(d.removal_warnings.join('\n'))}</pre>
          </details>` : ''}
      </div>
    </div>`;
}

function _updateDeploySummary() {
  const boxes = [...document.querySelectorAll('#deployPlanBody input[type=checkbox]:checked')];
  document.getElementById('deployApplyBtn').disabled = boxes.length === 0;
  document.getElementById('deployPlanSummary').innerHTML = boxes.length
    ? `Confirmed: <strong>${boxes.map(b => _dEsc(b.dataset.device)).join(', ')}</strong>. `
      + 'Each device is re-read at deploy time; one whose config changed since this '
      + 'plan is skipped and reported, not deployed against a diff you did not see.'
    : 'Tick the devices to deploy. Unticked devices are not touched.';
}

async function applyDeploy() {
  const boxes = [...document.querySelectorAll('#deployPlanBody input[type=checkbox]:checked')];
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
  const confirmations = {}, commandHashes = {};
  boxes.forEach(b => {
    confirmations[b.dataset.device] = b.dataset.hash;
    if (b.dataset.commandHash) commandHashes[b.dataset.device] = b.dataset.commandHash;
  });

  const btn = document.getElementById('deployApplyBtn');
  btn.disabled = true;
  btn.textContent = 'Deploying…';
  const body = document.getElementById('deployPlanBody');

  try {
    const r = await fetch('/deploy/apply', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({confirmations, command_hashes: commandHashes}),
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
      <thead><tr><th>Device</th><th>Outcome</th><th>Detail</th><th>Golden</th></tr></thead>
      <tbody>${report.results.map(r => `
        <tr>
          <td class="fw-semibold">${_dEsc(r.device)}</td>
          <td><span class="badge bg-${_OUTCOME_STYLE[r.outcome] || 'secondary'}">
            ${_dEsc(r.outcome.replace(/_/g, ' '))}</span></td>
          <td class="small">
            ${_dEsc(r.reason || '')}
            ${r.rolled_back ? '<span class="badge bg-info text-dark ms-1">rolled back</span>' : ''}
            ${(r.pending_convergence || []).length
              ? `<div class="text-muted">${r.pending_convergence.map(_dEsc).join('<br>')}</div>` : ''}
            ${r.outcome === 'skipped_drifted'
              ? `<button class="btn btn-outline-primary btn-sm mt-1"
                         onclick="openDeployPlan(['${_dEsc(r.device)}'])">Re-preview</button>` : ''}
          </td>
          <td class="font-monospace small">${_dEsc((r.golden_commit || '').slice(0, 8))}</td>
        </tr>`).join('')}</tbody>
    </table></div>
    <p class="small text-muted mb-0">
      ${report.total} device(s) accounted for. Every device in a batch appears here.
    </p>`;

  const deployed = (report.deployed || []).length;
  showToast(`${deployed} deployed, ${report.total - deployed} not`,
            deployed ? 'success' : 'warning');
}
