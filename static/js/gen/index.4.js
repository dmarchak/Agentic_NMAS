/* ------------------------------------------------------------------ */
/* Subnet Discovery                                                     */
/* ------------------------------------------------------------------ */

let _discoverOpId     = null;
let _discoverPollTimer = null;
let _discoverCreds    = {};   // kept for the "add" step

function startSubnetDiscovery() {
  const network    = document.getElementById('discoverNetwork').value.trim();
  const prefix     = document.getElementById('discoverPrefix').value;
  const username   = document.getElementById('discoverUsername').value.trim();
  const password   = document.getElementById('discoverPassword').value;
  const secret     = document.getElementById('discoverSecret').value;
  const deviceType = document.getElementById('discoverDeviceType').value;
  const workers    = document.getElementById('discoverWorkers').value;

  if (!network || !username || !password) {
    alert('Network address, username, and password are required.');
    return;
  }

  // Save creds for the add step
  _discoverCreds = { username, password, secret, device_type: deviceType };

  // Switch to progress view
  document.getElementById('discoverForm').style.display     = 'none';
  document.getElementById('discoverProgress').style.display = '';
  document.getElementById('discoverResults').style.display  = 'none';
  document.getElementById('discoverStartBtn').style.display = 'none';
  document.getElementById('discoverAddBtn').style.display   = 'none';
  document.getElementById('discoverStatusText').textContent = 'Starting scan…';

  fetch('/discover_subnet', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ network, prefix: parseInt(prefix), username, password,
                           secret, device_type: deviceType, max_workers: parseInt(workers) }),
  })
  .then(r => r.json())
  .then(data => {
    if (data.error) { alert('Error: ' + data.error); resetDiscoverModal(); return; }
    _discoverOpId = data.op_id;
    document.getElementById('discoverTotal').textContent = data.total;
    _discoverPollTimer = setInterval(pollDiscovery, 1500);
  })
  .catch(err => { alert('Request failed: ' + err); resetDiscoverModal(); });
}

function pollDiscovery() {
  if (!_discoverOpId) return;
  fetch('/discover_status/' + _discoverOpId)
    .then(r => r.json())
    .then(data => {
      const phase = data.phase || 'ping';

      if (phase === 'ping') {
        const pct = data.total > 0 ? Math.round((data.ping_completed / data.total) * 100) : 0;
        document.getElementById('discoverProgressBar').style.width = pct + '%';
        document.getElementById('discoverProgressLabel').textContent =
          data.ping_completed + ' / ' + data.total;
        document.getElementById('discoverPhaseLabel').textContent = 'Phase 1 of 2 — Ping sweep…';
        document.getElementById('discoverPhaseDesc').textContent =
          'Pinging all hosts to find reachable addresses before attempting SSH.';
        document.getElementById('discoverPingReachable').textContent = data.ping_reachable || 0;
        document.getElementById('discoverSshWrap').style.display = 'none';
        document.getElementById('discoverStatusText').textContent =
          'Ping sweep: ' + data.ping_completed + ' / ' + data.total + ' hosts checked…';
      } else {
        // SSH phase
        const sshTotal = data.ssh_total || 0;
        const pct = sshTotal > 0 ? Math.round((data.completed / sshTotal) * 100) : 100;
        document.getElementById('discoverProgressBar').style.width = pct + '%';
        document.getElementById('discoverProgressLabel').textContent =
          data.completed + ' / ' + sshTotal;
        document.getElementById('discoverPhaseLabel').textContent = 'Phase 2 of 2 — SSH probe…';
        document.getElementById('discoverPhaseDesc').textContent =
          'Attempting SSH on ' + sshTotal + ' reachable host(s). Unreachable addresses skipped.';
        document.getElementById('discoverPingReachable').textContent = data.ping_reachable || 0;
        document.getElementById('discoverSshWrap').style.display = '';
        document.getElementById('discoverSshFound').textContent  = data.found.length;
        document.getElementById('discoverSshTotal').textContent  = sshTotal;
        document.getElementById('discoverStatusText').textContent =
          'SSH probe: ' + data.completed + ' / ' + sshTotal + ' (' + data.found.length + ' found)…';
      }

      if (data.status === 'done') {
        clearInterval(_discoverPollTimer);
        _discoverPollTimer = null;
        showDiscoverResults(data);
      }
    })
    .catch(() => { /* transient error — keep polling */ });
}

function showDiscoverResults(data) {
  document.getElementById('discoverProgress').style.display = 'none';
  document.getElementById('discoverResults').style.display  = '';

  const found = data.found || [];
  document.getElementById('discoverFoundCount').textContent = found.length;
  const reachable = data.ping_reachable || data.total;
  const skipped   = data.total - reachable;
  const skipNote  = skipped > 0 ? ' (' + skipped + ' skipped — no ping response)' : '';
  document.getElementById('discoverStatusText').textContent =
    'Scan complete — ' + found.length + ' device(s) found. SSH attempted on ' +
    reachable + ' of ' + data.total + ' hosts' + skipNote + '.';

  const tbody = document.getElementById('discoverResultsBody');
  tbody.innerHTML = '';

  if (found.length === 0) {
    document.getElementById('discoverNoResults').style.display = '';
  } else {
    document.getElementById('discoverNoResults').style.display = 'none';
    found.forEach(dev => {
      const tr = document.createElement('tr');
      tr.innerHTML =
        '<td><input type="checkbox" class="discover-cb form-check-input" value="' + dev.ip +
        '" data-hostname="' + (dev.hostname || dev.ip) + '" checked></td>' +
        '<td><span class="badge bg-success me-1">●</span>' + (dev.hostname || '—') + '</td>' +
        '<td><code>' + dev.ip + '</code></td>';
      tbody.appendChild(tr);
    });
    document.getElementById('discoverAddBtn').style.display = '';
  }
}

function discoverSelectAll() {
  document.querySelectorAll('.discover-cb').forEach(cb => cb.checked = true);
}
function discoverSelectNone() {
  document.querySelectorAll('.discover-cb').forEach(cb => cb.checked = false);
}

function addDiscoveredDevices() {
  const selected = [];
  document.querySelectorAll('.discover-cb:checked').forEach(cb => {
    selected.push({ ip: cb.value, hostname: cb.dataset.hostname });
  });
  if (selected.length === 0) { alert('No devices selected.'); return; }

  const btn = document.getElementById('discoverAddBtn');
  btn.disabled = true;
  btn.textContent = 'Adding…';

  fetch('/add_discovered_devices', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ devices: selected, ..._discoverCreds }),
  })
  .then(r => r.json())
  .then(data => {
    if (data.error) { alert('Error: ' + data.error); btn.disabled = false; btn.textContent = '➕ Add Selected Devices'; return; }
    bootstrap.Modal.getInstance(document.getElementById('discoverSubnetModal')).hide();
    showToast(data.added + ' device(s) added successfully!', 'success');
    setTimeout(() => location.reload(), 800);
  })
  .catch(err => { alert('Failed: ' + err); btn.disabled = false; btn.textContent = '➕ Add Selected Devices'; });
}

function resetDiscoverModal() {
  if (_discoverPollTimer) { clearInterval(_discoverPollTimer); _discoverPollTimer = null; }
  document.getElementById('discoverForm').style.display     = '';
  document.getElementById('discoverProgress').style.display = 'none';
  document.getElementById('discoverResults').style.display  = 'none';
  document.getElementById('discoverStartBtn').style.display = '';
  document.getElementById('discoverAddBtn').style.display   = 'none';
}

// Reset modal state when it's closed
document.addEventListener('DOMContentLoaded', function () {
  const modalEl = document.getElementById('discoverSubnetModal');
  if (modalEl) {
    modalEl.addEventListener('hidden.bs.modal', resetDiscoverModal);
  }
});

/* ------------------------------------------------------------------ */
/* AI Assistant integration for the index page                          */
/* ------------------------------------------------------------------ */

/* ------------------------------------------------------------------ */
/* Shared helper                                                         */
/* ------------------------------------------------------------------ */
function _escHtml(str) {
  if (!str) return '';
  return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

/* ------------------------------------------------------------------ */
/* Ansible Tab                                                           */
/* ------------------------------------------------------------------ */
async function loadPlaybooks() {
  const container = document.getElementById('ansiblePlaybookList');
  if (!container) return;

  container.innerHTML = '<div class="text-center text-muted py-4"><div class="spinner-border spinner-border-sm me-2" role="status"></div>Loading&hellip;</div>';

  try {
    const r = await fetch('/ai/playbooks');
    if (!r.ok) throw new Error('Request failed');
    const data = await r.json();
    const playbooks = data.playbooks || [];

    if (playbooks.length === 0) {
      container.innerHTML = `
        <div class="card">
          <div class="card-body text-center text-muted py-5">
            <p class="mb-1 fs-5">No playbooks saved yet.</p>
            <p class="small mb-0">Ask the AI assistant to configure your devices and it will save the task as a reusable playbook.</p>
          </div>
        </div>`;
      return;
    }

    container.innerHTML = playbooks.map(pb => `
      <div class="card mb-3">
        <div class="card-body">
          <div class="d-flex justify-content-between align-items-start gap-3">
            <div class="flex-grow-1 min-w-0">
              <h5 class="card-title mb-1">${_escHtml(pb.name)}</h5>
              ${pb.description ? `<p class="text-muted small mb-1">${_escHtml(pb.description)}</p>` : ''}
              <div class="d-flex flex-wrap gap-3 text-muted small">
                <span>${pb.play_count || 0} device(s)</span>
                ${pb.saved_at ? `<span>Saved ${_escHtml(pb.saved_at)}</span>` : ''}
              </div>
            </div>
            <div class="d-flex gap-2 flex-shrink-0">
              <button class="btn btn-outline-danger btn-sm pb-del-btn"
                      data-id="${_escHtml(pb.id)}" data-name="${_escHtml(pb.name)}">
                Delete
              </button>
            </div>
          </div>
        </div>
      </div>`).join('');

    container.querySelectorAll('.pb-del-btn').forEach(btn => {
      btn.addEventListener('click', function () {
        _deletePlaybookFromTab(this.dataset.id, this.dataset.name);
      });
    });
  } catch (err) {
    container.innerHTML = `<div class="alert alert-danger">Failed to load playbooks: ${_escHtml(err.message)}</div>`;
  }
}

async function _deletePlaybookFromTab(pbId, pbName) {
  if (!confirm(`Delete playbook "${pbName}"?`)) return;
  try {
    const r = await fetch(`/ai/playbooks/${encodeURIComponent(pbId)}`, { method: 'DELETE' });
    if (!r.ok) throw new Error('Delete failed');
    showToast(`Deleted "${pbName}"`, 'success');
    loadPlaybooks();
  } catch {
    showToast('Failed to delete playbook', 'danger');
  }
}

/* ------------------------------------------------------------------ */
/* Jenkins Tab                                                           */
/* ------------------------------------------------------------------ */

function _updateRunBtnState() {
  const sel = document.getElementById('jenkinsPipelineSelect');
  const btn = document.getElementById('runChecksBtn');
  if (!sel || !btn) return;
  btn.disabled = (sel.value === '');
}

// Populate the pipeline dropdown from /jenkins/pipelines
async function _loadJenkinsPipelineSelect() {
  const sel = document.getElementById('jenkinsPipelineSelect');
  if (!sel) return;
  try {
    const r    = await fetch('/jenkins/pipelines');
    const data = await r.json();
    const jobs = data.pipelines || [];
    // Rebuild options, keeping current selection if still valid
    const cur = sel.value;
    sel.innerHTML = '<option value="">All pipelines</option>';
    jobs.forEach(j => {
      const opt = document.createElement('option');
      opt.value       = j;
      opt.textContent = j;
      if (j === cur) opt.selected = true;
      sel.appendChild(opt);
    });
    if (jobs.length === 0) {
      sel.innerHTML = '<option value="">No pipelines registered</option>';
    }
  } catch { /* ignore */ }
  _updateRunBtnState();
}

function _renderJenkinsPipelineCard(jobName, p) {
  const pending   = p.jenkins_pending;
  const result    = p.jenkins_result || (pending ? 'BUILDING' : null);
  let badgeClass, badgeText;
  if (pending) {
    badgeClass = 'warning text-dark'; badgeText = 'BUILDING';
  } else if (result === 'SUCCESS') {
    badgeClass = 'success'; badgeText = 'SUCCESS';
  } else if (result) {
    badgeClass = 'danger'; badgeText = result;
  } else {
    badgeClass = 'secondary'; badgeText = 'NO DATA';
  }
  const buildInfo = p.jenkins_build ? `<span class="text-muted fw-normal ms-1">#${p.jenkins_build}</span>` : '';
  const ranAt     = p.jenkins_ran_at || p.jenkins_triggered_at || '';
  const dur       = p.jenkins_duration ? ` &middot; ${Math.round(p.jenkins_duration / 1000)}s` : '';
  return `
    <div class="card mb-2">
      <div class="card-body py-2 px-3 d-flex align-items-center gap-3 flex-wrap">
        <span class="badge bg-${badgeClass}" style="min-width:5.5rem;text-align:center;font-size:.8rem">
          ${pending ? '<span class="spinner-border spinner-border-sm me-1" role="status" style="width:.7rem;height:.7rem;border-width:2px"></span>' : ''}${_escHtml(badgeText)}
        </span>
        <div class="flex-grow-1">
          <div class="fw-semibold">${_escHtml(jobName)}${buildInfo}</div>
          ${ranAt ? `<div class="small text-muted">${_escHtml(ranAt)}${dur}</div>` : ''}
        </div>
        ${p.jenkins_url ? `<a href="${_escHtml(p.jenkins_url)}" target="_blank" class="btn btn-outline-secondary btn-sm">View &rarr;</a>` : ''}
      </div>
    </div>`;
}

function _renderJenkinsResults(data) {
  const container = document.getElementById('jenkinsResultsPanel');
  if (!container) return;

  const selJob = (document.getElementById('jenkinsPipelineSelect') || {}).value || '';
  const pipes  = data && data.pipelines ? data.pipelines : null;

  // Filter to selected pipeline if one is chosen
  const visible = pipes
    ? (selJob ? Object.fromEntries(Object.entries(pipes).filter(([k]) => k === selJob)) : pipes)
    : null;
  const hasPipes = visible && Object.keys(visible).length > 0;

  if (!hasPipes) {
    container.innerHTML = `
      <div class="text-center text-muted py-4">
        <p class="mb-1">No results yet for ${selJob ? `<strong>${_escHtml(selJob)}</strong>` : 'this list'}.</p>
        <p class="small mb-0">Click <strong>Run</strong> to trigger the pipeline.</p>
      </div>`;
    return;
  }

  const anyPending = Object.values(visible).some(p => p.jenkins_pending);
  const done       = Object.values(visible).filter(p => p.jenkins_result);
  const allOk      = done.length > 0 && done.every(p => p.jenkins_ok);
  const anyFail    = done.some(p => !p.jenkins_ok);
  const sumClass   = anyPending ? 'warning text-dark' : (allOk ? 'success' : (anyFail ? 'danger' : 'secondary'));
  const sumText    = anyPending ? 'Building\u2026'
                   : allOk     ? `${done.length} pipeline${done.length > 1 ? 's' : ''} passed`
                   : anyFail   ? `${done.filter(p => !p.jenkins_ok).length} failed`
                   : 'No results yet';

  const summaryHtml = `
    <div class="alert alert-${sumClass} py-2 mb-3 d-flex align-items-center gap-2">
      ${anyPending ? '<div class="spinner-border spinner-border-sm" role="status"></div>' : ''}
      <strong>${sumText}</strong>
      <span class="ms-auto small text-muted">${Object.keys(visible).length} pipeline(s)</span>
    </div>`;

  const cards = Object.entries(visible).map(([name, p]) => _renderJenkinsPipelineCard(name, p)).join('');
  container.innerHTML = summaryHtml + cards;
}

async function _renderBuildHistory(jobs) {
  const panel = document.getElementById('jenkinsBuildHistory');
  if (!panel || !jobs || jobs.length === 0) { if (panel) panel.innerHTML = ''; return; }

  const selJob = (document.getElementById('jenkinsPipelineSelect') || {}).value || '';
  const targets = selJob ? [selJob] : jobs;

  let html = `<h5 class="text-secondary mb-3">Build History</h5>`;

  for (const job of targets) {
    let builds = [];
    try {
      const r = await fetch(`/jenkins/history/${encodeURIComponent(job)}?limit=15`);
      const d = await r.json();
      builds = d.builds || [];
    } catch { /* ignore */ }

    html += `<div class="mb-4">`;
    if (targets.length > 1) html += `<div class="fw-semibold mb-2">${_escHtml(job)}</div>`;

    if (builds.length === 0) {
      html += `<div class="text-muted small">No builds found.</div>`;
    } else {
      html += `<div class="table-responsive"><table class="table table-sm table-hover mb-0" style="font-size:.85rem">
        <thead><tr><th>#</th><th>Result</th><th>Started</th><th>Duration</th><th></th></tr></thead><tbody>`;
      builds.forEach(b => {
        const res  = b.result || 'IN PROGRESS';
        const cls  = res === 'SUCCESS' ? 'success' : res === 'FAILURE' ? 'danger' : res === 'ABORTED' ? 'secondary' : 'warning text-dark';
        const ts   = b.timestamp ? new Date(b.timestamp).toLocaleString() : '—';
        const dur  = b.duration  ? `${Math.round(b.duration / 1000)}s` : '—';
        const link = b.url ? `<a href="${_escHtml(b.url)}" target="_blank" class="small">Console &rarr;</a>` : '';
        html += `<tr>
          <td>#${b.number}</td>
          <td><span class="badge bg-${cls}">${_escHtml(res)}</span></td>
          <td>${ts}</td>
          <td>${dur}</td>
          <td>${link}</td>
        </tr>`;
      });
      html += `</tbody></table></div>`;
    }
    html += `</div>`;
  }

  panel.innerHTML = html;
}

async function loadJenkinsTab() {
  await _loadJenkinsPipelineSelect();
  // Sync from Jenkins first (no AI needed — pure API), then load history in parallel.
  const syncReq      = fetch('/jenkins/sync').then(r => r.json()).catch(() => null);
  const pipelinesReq = fetch('/jenkins/pipelines').then(r => r.json()).catch(() => ({ pipelines: [] }));
  const [rData, pData] = await Promise.all([syncReq, pipelinesReq]);
  _renderJenkinsResults(rData || {});
  await _renderBuildHistory(pData.pipelines || []);
  loadJenkinsSchedules();
  // If any build is still running, poll again in 10s to catch completion
  _scheduleJenkinsAutoPoll(rData);
}

let _jenkinsPollTimer = null;
function _scheduleJenkinsAutoPoll(data) {
  if (_jenkinsPollTimer) { clearTimeout(_jenkinsPollTimer); _jenkinsPollTimer = null; }
  const anyPending = data && (data.jenkins_pending ||
    Object.values((data.pipelines || {})).some(p => p.jenkins_pending));
  if (!anyPending) return;
  const jenkinsTabBtn = document.getElementById('jenkins-tab');
  _jenkinsPollTimer = setTimeout(function () {
    if (jenkinsTabBtn && jenkinsTabBtn.classList.contains('active')) loadJenkinsTab();
  }, 10000);
}

// ── Schedule presets shown in the editor dropdown ──
const CRON_PRESETS = [
  { label: 'Not scheduled (manual only)', value: '' },
  { label: 'Every 5 minutes',   value: 'H/5 * * * *' },
  { label: 'Every 15 minutes',  value: 'H/15 * * * *' },
  { label: 'Every 30 minutes',  value: 'H/30 * * * *' },
  { label: 'Hourly',            value: 'H * * * *' },
  { label: 'Every 4 hours',     value: 'H H/4 * * *' },
  { label: 'Every 6 hours',     value: 'H H/6 * * *' },
  { label: 'Every 12 hours',    value: 'H H/12 * * *' },
  { label: 'Daily at midnight', value: 'H 0 * * *' },
  { label: 'Daily at ~6am',     value: 'H 6 * * *' },
  { label: 'Daily at ~8am',     value: 'H 8 * * *' },
  { label: 'Weekly (Monday)',   value: 'H 0 * * 1' },
  { label: 'Custom…',           value: '__custom__' },
];

async function loadJenkinsSchedules() {
  const el = document.getElementById('jenkinsSchedulesPanel');
  if (!el) return;
  try {
    const r    = await fetch('/jenkins/schedules');
    const data = await r.json();
    const schedules = data.schedules || {};
    const jobs = Object.keys(schedules);

    if (jobs.length === 0) {
      el.innerHTML = `<div class="text-muted small py-2">No pipelines registered to this list yet.</div>`;
      return;
    }

    const rows = jobs.map(job => {
      const info  = schedules[job];
      const cron  = info.cron || '';
      const desc  = info.description || (cron ? cron : 'Not scheduled');
      const opts  = CRON_PRESETS.map(p => {
        const sel = (p.value === cron || (p.value === '__custom__' && cron && !CRON_PRESETS.find(x => x.value === cron && x.value !== '__custom__'))) ? 'selected' : '';
        return `<option value="${_esc(p.value)}" ${sel}>${_esc(p.label)}</option>`;
      }).join('');

      return `
        <div class="card mb-2" style="background:#1e293b;border:1px solid #334155" id="sched-card-${_esc(job)}">
          <div class="card-body p-3">
            <div class="d-flex flex-wrap align-items-center gap-2">
              <strong class="text-light me-auto" style="font-size:.9rem">${_esc(job)}</strong>
              <span class="badge ${cron ? 'bg-success' : 'bg-secondary'} me-1">${_esc(desc)}</span>
              <select class="form-select form-select-sm" style="width:auto;min-width:200px"
                      id="sched-select-${_esc(job)}"
                      onchange="onSchedulePresetChange('${_esc(job)}')">
                ${opts}
              </select>
              <input id="sched-custom-${_esc(job)}" type="text" class="form-control form-control-sm"
                     placeholder="cron expression" style="width:160px;${cron && !CRON_PRESETS.slice(0,-1).find(p=>p.value===cron) ? '' : 'display:none'}"
                     value="${_esc(cron)}">
              <button class="btn btn-primary btn-sm" onclick="saveSchedule('${_esc(job)}')">Save</button>
            </div>
          </div>
        </div>`;
    }).join('');

    el.innerHTML = rows;
  } catch (err) {
    el.innerHTML = `<div class="text-danger small">Could not load schedules: ${_esc(String(err))}</div>`;
  }
}

function onSchedulePresetChange(job) {
  const sel    = document.getElementById(`sched-select-${job}`);
  const custom = document.getElementById(`sched-custom-${job}`);
  if (!sel || !custom) return;
  if (sel.value === '__custom__') {
    custom.style.display = '';
    custom.focus();
  } else {
    custom.style.display = 'none';
  }
}

async function saveSchedule(job) {
  const sel    = document.getElementById(`sched-select-${job}`);
  const custom = document.getElementById(`sched-custom-${job}`);
  if (!sel) return;

  let cron = sel.value === '__custom__' ? (custom ? custom.value.trim() : '') : sel.value;

  const btn = document.querySelector(`#sched-card-${CSS.escape(job)} .btn-primary`);
  if (btn) { btn.disabled = true; btn.textContent = 'Saving…'; }

  try {
    const r = await fetch(`/jenkins/schedules/${encodeURIComponent(job)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cron }),
    });
    const data = await r.json();
    if (data.error) { showToast(data.error, 'danger'); return; }
    if (data.warning) {
      showToast(`⚠️ ${data.warning}`, 'warning');
    } else {
      showToast(`Schedule saved: ${data.description}`, 'success');
    }
    loadJenkinsSchedules();
  } catch (err) {
    showToast('Failed to save schedule', 'danger');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Save'; }
  }
}

// Re-render when dropdown changes
document.addEventListener('DOMContentLoaded', function () {
  const sel = document.getElementById('jenkinsPipelineSelect');
  if (sel) {
    sel.addEventListener('change', async function () {
      _updateRunBtnState();
      const r = await fetch('/jenkins/results').catch(() => null);
      const data = r ? await r.json() : {};
      _renderJenkinsResults(data);
      const pr = await fetch('/jenkins/pipelines').then(x => x.json()).catch(() => ({ pipelines: [] }));
      await _renderBuildHistory(pr.pipelines || []);
    });
  }
});

async function runJenkinsChecks() {
  const btn     = document.getElementById('runChecksBtn');
  const btnText = btn.querySelector('.btn-text');
  const spinner = btn.querySelector('.spinner-border');
  const selJob  = (document.getElementById('jenkinsPipelineSelect') || {}).value || '';

  btnText.textContent = '\u2026';
  spinner.classList.remove('d-none');
  btn.disabled = true;

  try {
    const body = selJob ? { job_name: selJob } : { startup_delay: 0 };
    const r = await fetch('/jenkins/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error('Run failed');
    const data = await r.json();
    showToast(data.triggered ? `Triggered ${selJob || 'all pipelines'}` : (data.error || 'Triggered'), 'success');

    // Poll for build completion then auto-troubleshoot failures
    if (selJob) {
      _pollJenkinsJobUntilDone(selJob);
    } else {
      setTimeout(() => loadJenkinsTab(), 3000);
    }
  } catch (err) {
    showToast('Failed to trigger pipeline', 'danger');
    btn.disabled = (selJob === '');
  } finally {
    btnText.textContent = 'Run';
    spinner.classList.add('d-none');
    // Keep button disabled while polling (re-enabled inside _pollJenkinsJobUntilDone)
    if (!selJob) btn.disabled = false;
  }
}

// Poll /jenkins/results every 4s until selJob is no longer pending.
// If it failed, auto-send an AI troubleshoot request.
async function _pollJenkinsJobUntilDone(jobName, maxWaitMs = 300000) {
  const started = Date.now();
  const interval = 4000;

  async function poll() {
    if (Date.now() - started > maxWaitMs) {
      // Timed out — just reload
      loadJenkinsTab();
      _enableRunBtn();
      return;
    }
    try {
      const r = await fetch('/jenkins/results');
      const data = await r.json();
      const pipelines = data.pipelines || {};
      const entry = pipelines[jobName];

      // Still pending — keep polling
      if (!entry || entry.jenkins_pending) {
        setTimeout(poll, interval);
        return;
      }

      // Build finished — reload tab
      loadJenkinsTab();
      _enableRunBtn();

      if (!entry.jenkins_ok) {
        // Set a pending fix that base.html's interval will pick up and send to the AI
        window._pendingJenkinsFix = {
          jobName: jobName,
          buildNum: entry.jenkins_build || null,
        };
      }
    } catch {
      setTimeout(poll, interval);
    }
  }

  // Start first poll after a short delay to let Jenkins queue the build
  setTimeout(poll, 5000);
}

function _enableRunBtn() {
  const btn = document.getElementById('runChecksBtn');
  const sel = document.getElementById('jenkinsPipelineSelect');
  if (btn && sel) btn.disabled = (sel.value === '');
}

// ── Agent badge "seen" tracking ──────────────────────────────────────────
// Module-level so loadAgentTab() and the refresh timer can both access these.
let _agentSeenIds = new Set(
  JSON.parse(localStorage.getItem('agentSeenFailureIds') || '[]')
);

function _markAgentEntriesSeen(entries) {
  entries.filter(e => !e.success).forEach(e => { if (e.id) _agentSeenIds.add(e.id); });
  // Cap stored set at 500 IDs to avoid unbounded growth
  const trimmed = [..._agentSeenIds].slice(-500);
  _agentSeenIds = new Set(trimmed);
  try { localStorage.setItem('agentSeenFailureIds', JSON.stringify(trimmed)); } catch (_) {}
}

function _hasUnseenFailures(entries) {
  return entries.some(e => !e.success && !_agentSeenIds.has(e.id));
}

// Load tab data when tab becomes active for the first time
document.addEventListener('DOMContentLoaded', function () {
  const ansibleTabBtn    = document.getElementById('ansible-tab');
  const jenkinsTabBtn    = document.getElementById('jenkins-tab');
  const historyTabBtn    = document.getElementById('history-tab');
  const netboxTabBtn     = document.getElementById('netbox-tab');
  const agentTabBtn      = document.getElementById('agent-tab');
  const approvalsTabBtn  = document.getElementById('approvals-tab');
  const monitoringTabBtn = document.getElementById('monitoring-tab');
  const gitTabBtn        = document.getElementById('git-tab');

  if (ansibleTabBtn)    ansibleTabBtn.addEventListener('shown.bs.tab', loadPlaybooks);
  if (jenkinsTabBtn)    jenkinsTabBtn.addEventListener('shown.bs.tab', loadJenkinsTab);
  if (historyTabBtn)    historyTabBtn.addEventListener('shown.bs.tab', loadHistoryTab);
  if (netboxTabBtn)     netboxTabBtn.addEventListener('shown.bs.tab', loadNetboxTab);

  if (agentTabBtn) {
    agentTabBtn.addEventListener('shown.bs.tab', () => {
      loadAgentTab();
    });
  }
  if (approvalsTabBtn)  approvalsTabBtn.addEventListener('shown.bs.tab', loadApprovalsTab);
  if (monitoringTabBtn) monitoringTabBtn.addEventListener('shown.bs.tab', loadMonitoringTab);
  // Unlike every other tab above, Git had no auto-load-on-switch wiring --
  // it only ever loaded via the explicit Refresh button, so re-opening the
  // tab after committing/saving elsewhere in the app showed stale data.
  if (gitTabBtn)        gitTabBtn.addEventListener('shown.bs.tab', loadGitTab);

  // Auto-refresh Jenkins panel every 30s while tab is visible (uses /jenkins/sync — no AI)
  setInterval(function () {
    if (jenkinsTabBtn && jenkinsTabBtn.classList.contains('active')) loadJenkinsTab();
  }, 30000);

  // Refresh Agent tab — 3s while a task is running, 15s otherwise
  let _agentRefreshTimer = null;
  function _scheduleAgentRefresh() {
    if (_agentRefreshTimer) clearTimeout(_agentRefreshTimer);
    const liveRunning = !!document.getElementById('agentLiveTask');
    const interval = liveRunning ? 3000 : 15000;
    _agentRefreshTimer = setTimeout(async function () {
      if (agentTabBtn && agentTabBtn.classList.contains('active')) {
        await loadAgentTab();
      } else if (window._aiEnabled !== false) {
        // Keep failure badge current even when tab is not open (skip when AI disabled)
        fetch('/ai/agent_log?limit=5').then(r => r.json()).then(data => {
          const agentBadgeEl = document.getElementById('agentBadge');
          if (agentBadgeEl) {
            agentBadgeEl.style.display = _hasUnseenFailures(data.entries || []) ? 'inline' : 'none';
          }
        }).catch(() => {});
      }
      _scheduleAgentRefresh();
    }, interval);
  }
  _scheduleAgentRefresh();

  // Poll approval count every 30s — keep badge updated regardless of which tab is open
  // If approvals tab is open, refresh the full list too
  function _pollApprovals() {
    // Drift approvals are Python-generated — always poll regardless of AI state
    fetch('/ai/approvals').then(r => r.json()).then(data => {
      _updateApprovalsBadge(data.pending_count || 0);
      if (approvalsTabBtn && approvalsTabBtn.classList.contains('active')) {
        loadApprovalsTab();
      }
    }).catch(() => {});
  }
  _pollApprovals();                        // run once at page load
  setInterval(_pollApprovals, 30000);     // then every 30s
  loadDriftStatus();                      // populate drift badge on load (AI-independent)
});

// ========================================================================
// COMPLIANCE TAB
// ========================================================================


// ========================================================================
// HISTORY TAB
// ========================================================================

async function loadHistoryTab() {
  const panel = document.getElementById('changeLogPanel');
  if (!panel) return;
  panel.innerHTML = '<div class="text-muted small py-2"><div class="spinner-border spinner-border-sm me-2"></div>Loading…</div>';
  try {
    const r    = await fetch('/list/change_log?limit=50');
    const data = await r.json();
    const changes = data.changes || [];
    if (changes.length === 0) {
      panel.innerHTML = '<div class="text-muted small py-4 text-center">No changes logged yet. Changes are recorded after every AI config push.</div>';
      return;
    }
    const badge = r => ({ SUCCESS:'success', FAILURE:'danger', SKIPPED:'secondary', '':'secondary' }[r] || 'secondary');
    const icon  = r => ({ SUCCESS:'✓', FAILURE:'✗', SKIPPED:'~', '':'—' }[r] || '?');
    const typeColor = t => ({ config_push:'primary', rollback:'warning', restore:'warning', playbook:'info', compliance_fix:'success' }[t] || 'secondary');
    panel.innerHTML = `
      <div class="list-group">
        ${changes.map(c => `
          <div class="list-group-item" style="background:#1e293b;border-color:#334155;color:#e2e8f0">
            <div class="d-flex justify-content-between align-items-center mb-1">
              <span class="badge bg-${badge(c.jenkins_result)} me-2">${icon(c.jenkins_result)} ${c.jenkins_result || 'NO CI'}</span>
              <span class="badge bg-${typeColor(c.change_type)} me-auto">${c.change_type || ''}</span>
              ${c.golden_config_saved ? '<span class="badge bg-success ms-1">golden saved</span>' : ''}
              <small class="text-muted ms-2">${c.timestamp || ''}</small>
            </div>
            <div class="fw-semibold">${_esc(c.description || '')}</div>
            <div class="text-muted small mt-1">
              Devices: ${(c.devices || []).join(', ') || 'none'}
              ${c.jenkins_pipeline ? ' &middot; Pipeline: ' + _esc(c.jenkins_pipeline) : ''}
              ${c.playbook_id      ? ' &middot; Playbook: ' + _esc(c.playbook_id) : ''}
            </div>
          </div>`).join('')}
      </div>`;
  } catch { panel.innerHTML = '<div class="text-danger small">Failed to load change history.</div>'; }
}

// ========================================================================
// NETBOX TAB
// ========================================================================

let _netboxPollTimer = null;

async function loadNetboxTab() {
  const statusPanel = document.getElementById('netboxStatusPanel');
  if (!statusPanel) return;

  try {
    const r   = await fetch('/netbox/status');
    const nbs = await r.json();

    const badge          = document.getElementById('netboxConnBadge');
    const notConfigured  = document.getElementById('netboxNotConfigured');
    const syncControls   = document.getElementById('netboxSyncControls');
    const configuredArea = document.getElementById('netboxConfiguredArea');
    const openLink       = document.getElementById('netboxOpenLink');

    if (badge) {
      if (nbs.configured) {
        badge.textContent = 'Configured';
        badge.className   = 'badge bg-success';
      } else {
        badge.textContent = 'Not configured';
        badge.className   = 'badge bg-secondary';
      }
    }

    if (openLink) {
      if (nbs.url) {
        openLink.href = nbs.url;
        openLink.classList.remove('disabled');
      } else {
        openLink.href = '#';
        openLink.classList.add('disabled');
      }
    }

    // Toggle the "not configured" banner vs the sync/status UI.
    if (nbs.configured) {
      if (notConfigured)  notConfigured.classList.add('d-none');
      if (syncControls)   syncControls.classList.remove('d-none');
      if (configuredArea) configuredArea.classList.remove('d-none');
    } else {
      if (notConfigured)  notConfigured.classList.remove('d-none');
      if (syncControls)   syncControls.classList.add('d-none');
      if (configuredArea) configuredArea.classList.add('d-none');
      return;  // Nothing more to render until configured.
    }

    const byList = (nbs.status && nbs.status.lists) || {};
    const running = (nbs.status && nbs.status.running) || {};
    const lists = nbs.lists || [];

    if (lists.length === 0) {
      statusPanel.innerHTML = '<div class="text-muted small py-3 text-center">No device lists available.</div>';
    } else {
      statusPanel.innerHTML = `
        <div class="list-group">
          ${lists.map(l => {
            const summary = byList[l.name];
            const isRunning = !!running[l.name];
            const hdrBadge = isRunning
              ? '<span class="badge bg-info"><span class="spinner-border spinner-border-sm me-1" role="status" style="width:.8rem;height:.8rem"></span>syncing…</span>'
              : (summary
                  ? `<span class="badge bg-${summary.failed && summary.failed.length ? 'warning text-dark' : 'success'}">last sync ${_esc(summary.timestamp || '')}</span>`
                  : '<span class="badge bg-secondary">never synced</span>');
            const fails = (summary && summary.failed) || [];
            const ipam = (summary && summary.ipam) || {};
            const siteLink = (summary && summary.netbox_url && nbs.url)
              ? `<a href="${_esc(summary.netbox_url)}" target="_blank" rel="noopener" class="small ms-2">open region ↗</a>`
              : '';
            const ipamLink = (summary && summary.ipam_url && nbs.url)
              ? `<a href="${_esc(summary.ipam_url)}" target="_blank" rel="noopener" class="small ms-2">open IPAM ↗</a>`
              : '';
            return `
              <div class="list-group-item" style="background:#1e293b;border-color:#334155;color:#e2e8f0">
                <div class="d-flex justify-content-between align-items-center mb-1">
                  <div>
                    <span class="fw-semibold">${_esc(l.name)}</span>
                    <span class="text-muted small ms-2">${l.device_count} device(s)${l.is_current ? ' · current' : ''}</span>
                    ${siteLink}${ipamLink}
                  </div>
                  <div class="d-flex gap-2">
                    ${hdrBadge}
                    <button class="btn btn-outline-primary btn-sm py-0 px-2"
                            onclick="netboxSyncList('${_esc(l.name)}')"
                            ${isRunning ? 'disabled' : ''}>
                      Sync
                    </button>
                    ${summary ? `<button class="btn btn-outline-danger btn-sm py-0 px-2"
                            onclick="netboxRemoveList('${_esc(l.name)}')"
                            ${isRunning ? 'disabled' : ''}>
                      Remove
                    </button>` : ''}
                  </div>
                </div>
                ${summary ? `
                  <div class="small mt-1">
                    <span class="badge bg-primary me-1">devices created ${summary.created || 0}</span>
                    <span class="badge bg-info me-1">devices updated ${summary.updated || 0}</span>
                    <span class="badge bg-secondary me-1">scanned ${summary.scanned || 0}/${summary.total || 0}</span>
                    ${fails.length ? `<span class="badge bg-warning text-dark">failed ${fails.length}</span>` : ''}
                  </div>
                  <div class="small mt-1">
                    <span class="text-muted me-2">IPAM:</span>
                    <span class="badge bg-dark border border-secondary me-1">interfaces ${ipam.interfaces || 0}</span>
                    <span class="badge bg-dark border border-secondary me-1">prefixes ${ipam.prefixes || 0}</span>
                    <span class="badge bg-dark border border-secondary me-1">IPs ${ipam.ips || 0}</span>
                    ${(ipam.vrfs || 0)  > 0 ? `<span class="badge bg-dark border border-secondary me-1">VRFs ${ipam.vrfs}</span>` : ''}
                    ${(ipam.vlans || 0) > 0 ? `<span class="badge bg-dark border border-secondary me-1">VLANs ${ipam.vlans}</span>` : ''}
                    ${(ipam.cables || 0) > 0 ? `<span class="badge bg-dark border border-secondary me-1">cables ${ipam.cables}</span>` : ''}
                    ${(ipam.tunnels || 0) > 0 ? `<span class="badge bg-dark border border-secondary me-1">tunnels ${ipam.tunnels}</span>` : ''}
                  </div>
                  ${fails.length ? `
                    <details class="mt-2">
                      <summary class="text-muted small" style="cursor:pointer">${fails.length} device(s) had issues</summary>
                      <ul class="small text-muted mt-1 mb-0">
                        ${fails.map(f => `<li><code>${_esc(f.hostname || f.ip)}</code> — ${_esc(f.error)}</li>`).join('')}
                      </ul>
                    </details>` : ''}
                ` : '<div class="text-muted small mt-1">Not yet synced to NetBox.</div>'}
              </div>`;
          }).join('')}
        </div>`;
    }

    // Keep polling while any sync is running.
    if (_netboxPollTimer) clearTimeout(_netboxPollTimer);
    const anyRunning = Object.values(running).some(Boolean);
    if (anyRunning) {
      _netboxPollTimer = setTimeout(loadNetboxTab, 4000);
    }
  } catch {
    statusPanel.innerHTML = '<div class="text-danger small">Failed to load NetBox status.</div>';
  }
}

// Test NetBox connection using the values currently in the Settings modal
// (so the user can test before saving). Falls back to stored values for blanks.
async function netboxTestFromSettings() {
  const url        = (document.getElementById('settingsNetboxUrl')?.value   || '').trim();
  const token      = (document.getElementById('settingsNetboxToken')?.value || '').trim();
  const verify_tls = document.getElementById('settingsNetboxVerifyTls')?.checked ?? true;
  const btn     = document.getElementById('settingsNetboxTestBtn');
  const status  = document.getElementById('settingsNetboxTestStatus');
  if (btn)    btn.disabled = true;
  if (status) { status.textContent = 'Testing…'; status.className = 'form-text text-muted'; }
  try {
    const r = await fetch('/netbox/test_connection', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, token, verify_tls }),
    });
    const data = await r.json();
    if (status) {
      status.textContent = data.message || (data.ok ? 'OK' : 'Failed');
      status.className = 'form-text ' + (data.ok ? 'text-success' : 'text-danger');
    }
  } catch (e) {
    if (status) { status.textContent = 'Error: ' + e.message; status.className = 'form-text text-danger'; }
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function netboxSyncCurrent() {
  // Shows a read-only preview first, then asks for confirmation.
  // See templates/partials/netbox_safety_modal.html.
  netboxPreviewImport('');
}

async function netboxSyncList(listName) {
  netboxPreviewImport(listName);
}

async function netboxSyncAll() {
  netboxPreviewImport('', true);
}

async function netboxRemoveList(listName) {
  // Replaces the old blind confirm(): the modal lists exactly which objects
  // are eligible for deletion and which are left alone.
  netboxPreviewRemoval(listName);
}

function _esc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ========================================================================
// MONITORING TAB
// ========================================================================

async function loadMonitoringTab() {
  try {
    const r    = await fetch('/monitoring/config');
    const cfg  = await r.json();
    const ip   = cfg.collector_ip || '';
    const src  = cfg.collector_ip_source || 'none';

    const ipInput = document.getElementById('collectorIpInput');
    const roInput = document.getElementById('snmpCommunityRo');
    const trapPort = document.getElementById('snmpTrapPort');
    const nfPort   = document.getElementById('netflowPort');
    const srcLabel = document.getElementById('collectorIpSource');

    if (ipInput)  ipInput.value  = ip;
    if (roInput)  roInput.value  = cfg.snmp_community_ro || 'public';
    // Pre-fill the quick-poll community with the collector community if blank
    const pollCommunity = document.getElementById('snmpPollCommunity');
    if (pollCommunity && !pollCommunity.value)
      pollCommunity.value = cfg.snmp_community_ro || 'public';
    // Pre-fill Configure tab SNMP trap fields with collector settings
    const cfgTrapHost = document.getElementById('cfg_snmp_trap_host');
    const cfgTrapPort = document.getElementById('cfg_snmp_trap_port');
    if (cfgTrapHost && !cfgTrapHost.value && ip) cfgTrapHost.value = ip;
    if (cfgTrapPort && !cfgTrapPort.value) cfgTrapPort.value = cfg.snmp_trap_port || 1162;
    if (trapPort) trapPort.value = cfg.snmp_trap_port || 1162;
    if (nfPort)   nfPort.value   = cfg.netflow_port   || 9996;
    if (srcLabel) srcLabel.textContent = ip
      ? `Detected source: ${src}  — devices should send to ${ip}`
      : 'Not configured. Click Auto-detect or enter manually.';

    // Device config snippets
    if (ip) {
      const snip = document.getElementById('deviceConfigSnippets');
      const cont = document.getElementById('snippetsContent');
      if (snip) snip.style.display = '';
      if (cont) cont.innerHTML = `
        <div class="mb-2">
          <span class="text-muted small">SNMP traps (IOS):</span>
          <pre class="mb-0" style="background:#0f172a;padding:8px;border-radius:4px;font-size:12px">snmp-server host ${_esc(ip)} traps version 2c ${_esc(cfg.snmp_community_ro || 'public')}
snmp-server enable traps
snmp-server host ${_esc(ip)} version 2c ${_esc(cfg.snmp_community_ro || 'public')} udp-port ${cfg.snmp_trap_port || 1162}</pre>
        </div>
        <div class="mb-2">
          <span class="text-muted small">NetFlow export (IOS):</span>
          <pre class="mb-0" style="background:#0f172a;padding:8px;border-radius:4px;font-size:12px">ip flow-export destination ${_esc(ip)} ${cfg.netflow_port || 9996}
ip flow-export version 9
ip flow-export source Loopback0
!  -- on each interface:
interface &lt;name&gt;
 ip flow ingress
 ip flow egress</pre>
        </div>`;
    }
  } catch (e) {
    console.error('loadMonitoringTab:', e);
  }

  // Load traps and NetFlow
  _loadSnmpTraps();
  _loadNetflowSummary();
}

async function detectCollectorIp() {
  try {
    const r    = await fetch('/monitoring/interfaces');
    const list = await r.json();
    const panel = document.getElementById('localInterfacesPanel');
    const items = document.getElementById('localInterfacesList');
    if (!panel || !items) return;
    if (!list.length) {
      items.innerHTML = '<span class="text-muted small">No interfaces found</span>';
    } else {
      items.innerHTML = list.map(i =>
        `<button class="btn btn-outline-secondary btn-sm me-1 mb-1"
                 onclick="document.getElementById('collectorIpInput').value='${_esc(i.ip)}'">
           ${_esc(i.name)}: ${_esc(i.ip)}
         </button>`
      ).join('');
    }
    panel.style.display = '';
  } catch (e) {
    showToast('Error detecting interfaces: ' + e.message, 'danger');
  }
}

async function saveMonitoringConfig() {
  const ip  = (document.getElementById('collectorIpInput')?.value || '').trim();
  const ro  = (document.getElementById('snmpCommunityRo')?.value  || 'public').trim();
  const trap = parseInt(document.getElementById('snmpTrapPort')?.value || '1162');
  const nf   = parseInt(document.getElementById('netflowPort')?.value  || '9996');
  try {
    const r = await fetch('/monitoring/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ collector_ip: ip, snmp_community_ro: ro,
                             snmp_trap_port: trap, netflow_port: nf })
    });
    const data = await r.json();
    if (data.ok) {
      showToast('Monitoring config saved', 'success');
      loadMonitoringTab();
    } else {
      showToast('Save failed', 'danger');
    }
  } catch (e) {
    showToast('Error: ' + e.message, 'danger');
  }
}

async function snmpPollDevice() {
  const ip  = (document.getElementById('snmpPollIp')?.value || '').trim();
  const res = document.getElementById('snmpPollResult');
  if (!ip) { showToast('Enter a device IP', 'warning'); return; }
  if (res) res.textContent = 'Polling…';
  try {
    // Use the explicit community field; fall back to the collector's configured RO community
    const communityField = document.getElementById('snmpPollCommunity');
    const community = (communityField?.value || '').trim()
                      || document.getElementById('snmpCommunityRo')?.value
                      || 'public';
    const version = parseInt(document.getElementById('snmpPollVersion')?.value || '2', 10);
    const r = await fetch('/monitoring/snmp/poll', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ device_ip: ip, community, version,
        oids: ['sysName', 'sysDescr', 'sysUpTime', 'sysLocation'] })
    });
    const data = await r.json();
    if (data.error) {
      if (res) res.textContent = 'Error: ' + data.error;
    } else {
      const label = `Community: ${community}  Version: v${version === 1 ? '1' : '2c'}\n\n`;
      if (res) res.textContent = label + data.results.map(x => `${x.oid}\n  = ${x.value}`).join('\n\n');
    }
  } catch (e) {
    if (res) res.textContent = 'Error: ' + e.message;
  }
}

// Map OID prefix to short label for varbind chips
const _OID_LABELS_JS = {
  '1.3.6.1.2.1.2.2.1.1':   'ifIndex',
  '1.3.6.1.2.1.2.2.1.2':   'ifDescr',
  '1.3.6.1.2.1.2.2.1.7':   'ifAdminStatus',
  '1.3.6.1.2.1.2.2.1.8':   'ifOperStatus',
  '1.3.6.1.2.1.14.10.1.3': 'ospfNbrIpAddr',
  '1.3.6.1.2.1.14.10.1.6': 'ospfNbrState',
  '1.3.6.1.2.1.15.3.1.1':  'bgpPeerAddr',
  '1.3.6.1.2.1.15.3.1.2':  'bgpPeerState',
  '1.3.6.1.4.1.9.9.43.1.1.6.1.2': 'configSource',
};
function _shortOidLabel(oid) {
  for (const [prefix, label] of Object.entries(_OID_LABELS_JS)) {
    if (oid.startsWith(prefix)) {
      const suffix = oid.slice(prefix.length);
      return suffix ? `${label}${suffix}` : label;
    }
  }
  // Fall back: last 2 components
  const parts = oid.split('.');
  return parts.slice(-2).join('.');
}

const _TRAP_DESCRIPTIONS = {
  // Standard SNMPv1/v2c
  'coldStart':                  'Device Rebooted (Cold)',
  'warmStart':                  'Device Restarted (Warm)',
  'linkDown':                   'Interface Down',
  'linkUp':                     'Interface Up',
  'authenticationFailure':      'Auth Failure',
  'egpNeighborLoss':            'EGP Neighbor Lost',
  // OSPF
  'ospfNbrStateChange':         'OSPF Neighbor State Changed',
  'ospfVirtNbrStateChange':     'OSPF Virtual Neighbor Changed',
  'ciscoOspfNbrStateChange':    'OSPF Neighbor State Changed',
  // BGP
  'bgpEstablished':             'BGP Session Established',
  'bgpBackwardTransition':      'BGP Session Down',
  // Cisco config
  'ciscoConfigChangeTrap':      'Config Changed',
  'ciscoConfigSaveTrap':        'Config Saved',
  // Cisco environment
  'ciscoPowerSupplyFailed':     'Power Supply Failed',
  'ciscoPowerSupplyOk':         'Power Supply Restored',
  'ciscoFanFailed':             'Fan Failed',
  // Cisco syslog
  'clogMessageGenerated':       'Syslog Message',
  // Cisco enterprise link traps
  'ciscoLinkDown':              'Interface Down',
  'ciscoLinkUp':                'Interface Up',
  // Enterprise-specific fallbacks (when raw OID not looked up)
  'enterpriseSpecific':         'Enterprise Trap',
};

function _trapDescription(trapType) {
  if (!trapType) return 'Unknown';
  const known = _TRAP_DESCRIPTIONS[trapType];
  if (known) return known;
  // Raw OID — try to identify by suffix or show shortened OID
  if (/^[\d.]+$/.test(trapType)) {
    // Check for known OID suffix patterns
    if (trapType.endsWith('.3') && trapType.includes('1.1.5')) return 'Interface Down';
    if (trapType.endsWith('.4') && trapType.includes('1.1.5')) return 'Interface Up';
    if (trapType.endsWith('.1') && trapType.includes('1.1.5')) return 'Cold Start';
    if (trapType.endsWith('.2') && trapType.includes('1.1.5')) return 'Warm Start';
    // Show last 3 OID components as a short identifier
    const parts = trapType.split('.');
    return 'Trap …' + parts.slice(-3).join('.');
  }
  // Strip camelCase into words: "ospfNbrStateChange" → "Ospf Nbr State Change"
  return trapType
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .replace(/([A-Z]+)([A-Z][a-z])/g, '$1 $2')
    .replace(/^./, s => s.toUpperCase());
}

function _trapSeverity(trapType) {
  const t = (trapType || '').toLowerCase();
  if (t.includes('down') || t.includes('fail') || t.includes('cold') || t.includes('backward'))
    return { cls: 'bg-danger' };
  if (t.includes('up') || t.includes('established') || t.includes('ok') || t.includes('restored'))
    return { cls: 'bg-success' };
  if (t.includes('warm') || t.includes('auth') || t.includes('change') || t.includes('save') || t.includes('syslog'))
    return { cls: 'bg-warning text-dark' };
  return { cls: 'bg-secondary' };
}

async function _loadSnmpTraps() {
  try {
    const r    = await fetch('/monitoring/snmp/traps?limit=20');
    const data = await r.json();
    const traps = data.traps || [];
    const panel = document.getElementById('snmpTrapsPanel');
    const badge = document.getElementById('trapCountBadge');
    if (badge) badge.textContent = traps.length;
    if (!panel) return;
    if (!traps.length) {
      panel.innerHTML = '<div class="text-muted small text-center py-3">No traps received yet</div>';
      return;
    }
    panel.innerHTML = traps.map(t => {
      const trapType = t.trap_type || '';
      const severity = _trapSeverity(trapType);
      // Varbinds: prefer Python pre-humanized labels, fall back to raw OID parsing
      let vbChips = '';
      if (t.varbind_labels && t.varbind_labels.length) {
        vbChips = t.varbind_labels.map(s => {
          const eq = s.indexOf('=');
          const lbl = eq >= 0 ? s.slice(0, eq) : s;
          const val = eq >= 0 ? s.slice(eq + 1) : '';
          return `<span class="badge bg-secondary me-1" style="font-weight:normal">${_esc(lbl)}=<strong>${_esc(val)}</strong></span>`;
        }).join('');
      } else {
        vbChips = (t.varbinds || [])
          .filter(([n]) => !n.includes('1.3.6.1.2.1.1.3') && !n.includes('1.3.6.1.6.3.1.1.4.1'))
          .map(([n, v]) => `<span class="badge bg-secondary me-1" style="font-weight:normal">${_esc(_shortOidLabel(n))}=<strong>${_esc(v)}</strong></span>`)
          .join('');
      }
      return `<div class="border-bottom border-secondary py-1 px-1 small">
        <div class="d-flex align-items-center gap-2 flex-wrap">
          <span class="text-muted" style="white-space:nowrap;min-width:135px">${_esc(t.received_at || '')}</span>
          <span class="text-warning fw-semibold" style="min-width:100px">${_esc(t.source_ip || '')}</span>
          <span class="badge ${severity.cls}" style="min-width:110px;text-align:center">${_esc(_trapDescription(trapType))}</span>
          ${vbChips}
        </div>
      </div>`;
    }).join('');
  } catch (e) { /* silent */ }
}

async function _loadNetflowSummary() {
  try {
    const r    = await fetch('/monitoring/netflow');
    const data = await r.json();
    const stats = data.stats || {};
    const panel = document.getElementById('netflowPanel');
    if (!panel) return;
    if (!stats.total_flows) {
      panel.innerHTML = '<div class="text-muted small text-center py-3">No flow data received yet. Configure devices to export NetFlow to the collector IP.</div>';
      return;
    }
    const topSrc = (stats.top_sources || []).slice(0, 5)
      .map(s => `<tr><td class="text-light">${_esc(s.ip)}</td><td class="text-end text-info">${_fmtBytes(s.bytes)}</td></tr>`).join('');
    const topDst = (stats.top_destinations || []).slice(0, 5)
      .map(d => `<tr><td class="text-light">${_esc(d.ip)}</td><td class="text-end text-info">${_fmtBytes(d.bytes)}</td></tr>`).join('');
    const protos = (stats.by_protocol || [])
      .map(p => `<span class="badge bg-secondary me-1">${_esc(p.proto)}: ${_fmtBytes(p.bytes)}</span>`).join('');
    panel.innerHTML = `
      <div class="text-muted small mb-2">Total flows in buffer: <strong class="text-light">${stats.total_flows}</strong></div>
      <div class="row g-2">
        <div class="col-md-6">
          <div class="text-muted small mb-1">Top Sources</div>
          <table class="table table-sm table-dark mb-0 small"><tbody>${topSrc}</tbody></table>
        </div>
        <div class="col-md-6">
          <div class="text-muted small mb-1">Top Destinations</div>
          <table class="table table-sm table-dark mb-0 small"><tbody>${topDst}</tbody></table>
        </div>
      </div>
      <div class="mt-2">${protos}</div>`;
  } catch (e) { /* silent */ }
}

function _fmtBytes(n) {
  if (!n) return '0 B';
  const units = ['B','KB','MB','GB','TB'];
  let i = 0;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return n.toFixed(1) + ' ' + units[i];
}

async function clearSnmpTraps() {
  if (!confirm('Clear all SNMP traps from the buffer?')) return;
  await fetch('/monitoring/snmp/traps/clear', {method: 'POST'});
  document.getElementById('trapCountBadge').textContent = '0';
  document.getElementById('snmpTrapsPanel').innerHTML =
    '<div class="text-muted small text-center py-3">Trap buffer cleared</div>';
}

async function clearNetflowBuffer() {
  if (!confirm('Clear all NetFlow data from the buffer?')) return;
  await fetch('/monitoring/netflow/clear', {method: 'POST'});
  document.getElementById('netflowPanel').innerHTML =
    '<div class="text-muted small text-center py-3">NetFlow buffer cleared</div>';
}

// ========================================================================
// AGENT ACTIVITY TAB
// ========================================================================

let _agentPaused = false;

/* THE RENDER, AS A PURE FUNCTION.
 *
 * Extracted so it can be executed in a test with a payload rather than only
 * grepped for. Every test in this feature passed at each stage while the
 * screen said nothing, because the boundary kept being drawn above the last
 * remaining guard: the route guard, then the success flag, then this one.
 * A test that asserts the endpoint carries the data cannot see a client that
 * refuses to draw it.
 *
 * Returns the banner HTML for a status block, or '' when there is nothing to
 * say. It takes no DOM and no network, so `test_agent_panel_renders.py` can
 * call it directly through dukpy, against the shipped source.
 */
function agentHealthBanner(status) {
  const health = (status && status.health) || {};
  if (!health.failing && !health.never_succeeded) return '';

  const esc = s => String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const n    = health.consecutive_failures || 0;
  const off  = status.enabled === false || status.ai_enabled === false;
  const same = health.same_error
    ? ' <strong>The same error every time</strong> — this is a configuration'
      + ' problem, not a transient one.' : '';

  return `
    <div class="alert ${off ? 'alert-warning' : 'alert-danger'} py-2 px-3 small mb-2">
      <div class="fw-semibold mb-1">
        Background agent: ${n} consecutive failed run${n === 1 ? '' : 's'}
        ${health.last_failure_at ? `— last ${esc(health.last_failure_at)}` : ''}
      </div>
      ${off ? `<div class="mb-1">It is <strong>disabled</strong>, so these
        will not retry. The failures are what happened before it was switched
        off — kept on screen because the reason a thing was switched off is
        the part that goes missing.</div>` : ''}
      <div class="font-monospace small">${esc(health.last_error || 'no error recorded')}</div>
      <div class="mt-1">${same}</div>
      ${health.never_succeeded ? `<div class="mt-1">
        <strong>It has never completed a run.</strong>
        ${health.runs_recorded} recorded, none successful.</div>` : ''}
      ${health.tool_calls_total === 0 && health.runs_recorded ? `<div class="mt-1">
        <strong>No tool has ever executed</strong> — zero tool calls across all
        ${health.runs_recorded} runs. Nothing in the agent's tool library has
        run in production.</div>` : ''}
    </div>`;
}

/* The badge, also pure. `disabled` outranks `failing` -- it is the current
 * state -- but carries the count, because the history is why it is off. */
function agentBadgeState(status) {
  const health = (status && status.health) || {};
  if (status && status.current_task)
    return {cls: 'badge bg-warning text-dark', text: 'Running…'};
  if (status && status.ai_enabled === false)
    return {cls: health.failing ? 'badge bg-secondary border border-danger'
                                : 'badge bg-secondary',
            text: health.failing ? `AI off · ${health.consecutive_failures} failed`
                                 : 'AI disabled'};
  if (status && status.enabled === false)
    return {cls: health.failing ? 'badge bg-secondary border border-danger'
                                : 'badge bg-secondary',
            text: health.failing ? `Disabled · ${health.consecutive_failures} failed`
                                 : 'Disabled'};
  if (health.failing)
    return {cls: 'badge bg-danger',
            text: health.consecutive_failures > 1
              ? `Failing (${health.consecutive_failures})` : 'Last run failed'};
  if (status && status.paused)
    return {cls: 'badge bg-secondary', text: 'Paused (until restart)'};
  if (status && status.user_active)
    return {cls: 'badge bg-info text-dark', text: 'Idle (user active)'};
  return {cls: 'badge bg-success', text: 'Active'};
}

async function loadAgentTab() {
  const logEl    = document.getElementById('agentActivityLog');
  const badgeEl  = document.getElementById('agentStatusBadge');
  const pauseBtn = document.getElementById('agentPauseBtn');
  if (!logEl) return;

  /* NO "AI is disabled, show nothing" BRANCH.
   *
   * It used to return here, so the panel said "enable it in Settings" while
   * the endpoint was returning 26 failures and the workspace-id rejection.
   * Disabled is a state to render, not a reason to stop rendering -- the same
   * correction made at the route, one layer further out, and the third guard
   * in this one feature to have hidden the same data.
   *
   * The controls are disabled; the history is not. */
  if (pauseBtn && window._aiEnabled === false) pauseBtn.disabled = true;

  try {
    const r    = await fetch('/ai/agent_log?limit=50');
    const data = await r.json();
    const status  = data.status  || {};
    const entries = data.entries || [];

    // Update status badge and live task panel
    const ct     = status.current_task;
    const health = status.health || {};

    /* One producer: `agentBadgeState` decides, here and in the test. An
       inline copy of this chain is how the badge and the banner came to
       disagree about what "disabled" means. */
    if (badgeEl) {
      const state = agentBadgeState(status);
      badgeEl.className = state.cls;
      badgeEl.textContent = state.text;
    }

    /* The tab badge, so a failure is visible without opening the tab -- the
       whole point is that nobody had reason to look. */
    const tabBadge = document.getElementById('agentBadge');
    if (tabBadge) {
      if (health.failing) {
        tabBadge.style.display = '';
        /* Amber when disabled: the failures are history, not an ongoing
           incident, and a red badge on something that cannot run any more is
           an alarm nobody can act on. */
        tabBadge.className = status.enabled === false
          ? 'badge bg-warning text-dark ms-1' : 'badge bg-danger ms-1';
        tabBadge.textContent = String(health.consecutive_failures);
        tabBadge.title = status.enabled === false
          ? 'Background agent is disabled; its last runs had failed'
          : 'Background agent runs are failing';
      } else {
        tabBadge.style.display = 'none';
      }
    }

    /* The banner: what failed, how many times, and whether it is the SAME
       failure each time. One failure is an incident; a dozen identical ones
       is a configuration problem that will not fix itself. */
    let failEl = document.getElementById('agentFailureBanner');
    if (!failEl && logEl && logEl.parentNode) {
      failEl = document.createElement('div');
      failEl.id = 'agentFailureBanner';
      logEl.parentNode.insertBefore(failEl, logEl);
    }
    if (failEl) failEl.innerHTML = agentHealthBanner(status);
    _agentPaused = !!status.paused;
    if (pauseBtn) pauseBtn.textContent = _agentPaused ? 'Resume' : 'Pause';

    // Live task detail panel — shown only while a task is running
    let livePanel = document.getElementById('agentLiveTask');
    if (ct) {
      const triggerLabels = {
        jenkins_failure: '⚡ Jenkins failure', missing_golden_configs: '📁 Missing golden configs',
        config_drift: '🔄 Drift check', scheduled_drift_check: '🕐 Scheduled drift check',
        manual: '👤 Manual trigger',
        snmp_trap_alert: '🚨 SNMP Trap Alert', snmp_trap: '📡 SNMP Trap',
      };
      const triggerLabel = triggerLabels[ct.trigger] || ct.trigger || 'Running';
      const elapsed = ct.elapsed_s != null ? `${ct.elapsed_s}s elapsed` : '';
      const toolBadges = (ct.tools_called || [])
        .map(t => `<span class="badge bg-secondary me-1" style="font-size:0.7rem">${_esc(t)}</span>`)
        .join('');
      const currentToolHtml = ct.current_tool
        ? `<span class="badge bg-warning text-dark me-1" style="font-size:0.7rem">
             <span class="spinner-grow spinner-grow-sm me-1" style="width:.5rem;height:.5rem"></span>
             ${_esc(ct.current_tool)}
           </span>` : '';
      const lastTextHtml = ct.last_text
        ? `<div class="text-muted mt-2" style="font-size:0.75rem;font-style:italic;max-height:60px;overflow:hidden">
             "${_esc(ct.last_text.slice(-180))}"
           </div>` : '';

      const html = `
        <div class="card mb-3" style="background:#1e293b;border:1px solid #f59e0b55" id="agentLiveTask">
          <div class="card-body p-3">
            <div class="d-flex align-items-center gap-2 mb-2">
              <div class="spinner-border spinner-border-sm text-warning me-1" role="status"></div>
              <strong class="text-warning">Task in progress</strong>
              <span class="text-muted small ms-auto">${_esc(elapsed)}</span>
            </div>
            <div class="small text-muted mb-1">${_esc(triggerLabel)}</div>
            <div class="text-light small mb-2" style="line-height:1.4">${_esc(ct.task || '')}</div>
            <div class="mb-1">
              ${currentToolHtml}${toolBadges}
            </div>
            <div class="text-muted" style="font-size:0.72rem">
              ${ct.tool_call_count || 0} tool call${ct.tool_call_count !== 1 ? 's' : ''}
              ${ct.cost_usd ? ` · $${(ct.cost_usd).toFixed(4)}` : ''}
            </div>
            ${lastTextHtml}
          </div>
        </div>`;

      if (livePanel) {
        livePanel.outerHTML = html;
      } else {
        logEl.insertAdjacentHTML('beforebegin', html);
      }
    } else {
      if (livePanel) livePanel.remove();
    }

    // Update badge on tab button (show ! if there are unseen failed tasks in last 5 entries)
    const agentBadgeEl = document.getElementById('agentBadge');
    if (agentBadgeEl) {
      // If the tab is currently active, mark visible entries as seen
      const _agentTab = document.getElementById('agent-tab');
      if (_agentTab && _agentTab.classList.contains('active')) {
        _markAgentEntriesSeen(entries.slice(0, 5));
      }
      agentBadgeEl.style.display = _hasUnseenFailures(entries.slice(0, 5)) ? 'inline' : 'none';
    }

    if (entries.length === 0) {
      logEl.innerHTML = `<div class="text-muted small py-4 text-center">No background tasks have run yet.</div>`;
      return;
    }

    const rows = entries.map(e => {
      const toolList = (e.tools_used || []).map(t => `<span class="badge bg-secondary me-1">${_esc(t)}</span>`).join('');
      const errHtml  = (e.errors || []).length
        ? `<div class="text-danger small mt-1">${e.errors.map(_esc).join('<br>')}</div>` : '';
      const triggerLabel = {
        jenkins_failure: '⚡ Jenkins failure', missing_golden_configs: '📁 Missing golden configs',
        config_drift: '🔄 Drift detected', manual: '👤 Manual trigger',
        snmp_trap_alert: '🚨 SNMP Trap Alert', snmp_trap: '📡 SNMP Trap',
        scheduled: '🕐 Scheduled',
      }[e.trigger] || e.trigger;
      const summary = e.summary
        ? `<div class="text-muted small mt-2" style="max-height:120px;overflow:auto;white-space:pre-wrap;font-size:0.75rem">${_esc(e.summary.slice(0, 800))}</div>` : '';

      return `
        <div class="card mb-2" style="background:#1e293b;border:1px solid ${e.success ? '#22c55e44' : '#ef444444'}">
          <div class="card-body p-3">
            <div class="d-flex justify-content-between align-items-start gap-2 mb-1">
              <span class="badge ${e.success ? 'bg-success' : 'bg-danger'}">${e.success ? 'SUCCESS' : 'FAILED'}</span>
              <span class="text-muted small">${_esc(e.started_at)}</span>
            </div>
            <div class="small mb-1"><strong>Trigger:</strong> ${_esc(triggerLabel)}</div>
            <div class="small text-light mb-1"><strong>Task:</strong> ${_esc((e.task || '').slice(0, 200))}</div>
            <div class="small mb-1">
              <strong>${e.tool_call_count || 0} tool calls:</strong> ${toolList || '<span class="text-muted">none</span>'}
            </div>
            ${e.cost_usd ? `<div class="text-muted small">Cost: $${(e.cost_usd || 0).toFixed(4)}</div>` : ''}
            ${errHtml}
            ${summary}
          </div>
        </div>`;
    }).join('');

    logEl.innerHTML = rows;
  } catch (err) {
    if (logEl) logEl.innerHTML = `<div class="text-danger small">Failed to load agent log: ${_esc(String(err))}</div>`;
  }
  // Load timer config alongside the activity log
  loadAgentTimers();
}

async function toggleAgentPause() {
  if (window._aiEnabled === false) { showToast('AI is disabled', 'warning'); return; }
  const endpoint = _agentPaused ? '/ai/agent_resume' : '/ai/agent_pause';
  await fetch(endpoint, { method: 'POST' });
  loadAgentTab();
}

async function triggerAgentTask() {
  if (window._aiEnabled === false) { showToast('AI is disabled — enable it in Settings to run agent tasks.', 'warning'); return; }
  const input = document.getElementById('agentTaskInput');
  const task  = (input ? input.value : '').trim();
  if (!task) return;
  const btn = document.querySelector('[onclick="triggerAgentTask()"]');
  if (btn) { btn.disabled = true; btn.textContent = 'Queuing…'; }
  try {
    await fetch('/ai/agent_run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task }),
    });
    if (input) input.value = '';
    setTimeout(loadAgentTab, 1500);
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Run'; }
  }
}

// -----------------------------------------------------------------------
// Agent Timer Configuration
// -----------------------------------------------------------------------

let _agentTimersData = [];

async function loadAgentTimers() {
  const panel = document.getElementById('agentTimersPanel');
  if (!panel) return;
  /* Not `panel.innerHTML = ''`. The schedule is configuration, and blanking
     it when AI is off means you cannot see what the agent WOULD do, or that
     a timer was left at some value — the same "disabled means show nothing"
     instinct as the agent panel, one card over. The route returns the timers
     regardless now; this renders them with the state said plainly. */
  const off = window._aiEnabled === false;
  try {
    const r = await fetch('/ai/agent_timers');
    const j = await r.json();
    _agentTimersData = j.timers || [];
    const note = off
      ? '<div class="alert alert-secondary py-2 px-3 small mb-2">AI is '
        + 'disabled, so none of these will fire. They are shown because a '
        + 'schedule you cannot see is one you cannot check.</div>'
      : '';
    panel.innerHTML = note + _agentTimersData.map(t => `
      <div class="row g-2 align-items-center mb-2">
        <div class="col-sm-3">
          <label class="form-label text-white small mb-0" for="timer_${t.key}">${t.label}</label>
          <div class="text-muted" style="font-size:0.72rem">${t.description}</div>
        </div>
        <div class="col-sm-2">
          <div class="input-group input-group-sm">
            <input id="timer_${t.key}" type="number" class="form-control"
                   value="${t.value}" min="${t.min}" max="${t.max}" step="1">
            <span class="input-group-text text-muted">${t.unit}</span>
          </div>
          <div class="text-muted" style="font-size:0.7rem">default: ${t.default} · range: ${t.min}–${t.max}</div>
        </div>
      </div>`).join('');
  } catch(e) {
    panel.innerHTML = `<div class="text-danger small">Failed to load timers.</div>`;
  }
}

async function saveAgentTimers() {
  if (window._aiEnabled === false) { showToast('AI is disabled', 'warning'); return; }
  const status = document.getElementById('agentTimersSaveStatus');
  const payload = {};
  for (const t of _agentTimersData) {
    const el = document.getElementById('timer_' + t.key);
    if (el) payload[t.key] = parseInt(el.value, 10);
  }
  try {
    const r = await fetch('/ai/agent_timers', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const j = await r.json();
    if (j.ok) {
      if (status) { status.textContent = 'Saved.'; setTimeout(() => { if(status) status.textContent = ''; }, 3000); }
      await loadAgentTimers();
    } else {
      if (status) status.textContent = 'Save failed.';
    }
  } catch(e) {
    if (status) status.textContent = 'Error saving.';
  }
}

// ========================================================================
// APPROVALS TAB
// ========================================================================

async function saveDriftSettings() {
  const sel     = document.getElementById('driftIntervalSelect');
  const toggle  = document.getElementById('driftEnabledToggle');
  const payload = {};
  if (sel)    payload.interval_s = parseInt(sel.value, 10);
  if (toggle) payload.disabled   = !toggle.checked;
  try {
    const r = await fetch('/drift/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    // The RESPONSE is checked. `fetch` rejects only on a network failure, so
    // a 500 -- or, before the error handlers were fixed, a 302 to the index
    // page -- resolved happily and the only visible effect was the toggle
    // snapping back after the refetch. A control that silently reverts is a
    // failure the operator is left to diagnose from a log.
    let body = null;
    try { body = await r.json(); } catch (_) { body = null; }
    if (!r.ok || !body || body.ok === false) {
      const why = (body && (body.error || body.detail)) || `HTTP ${r.status}`;
      showToast('Could not save drift settings: ' + why, 'danger');
    }
    await loadDriftStatus();
  } catch (err) {
    showToast('Could not save drift settings: ' + err, 'danger');
  }
}

/* PURE: a /drift/status payload in, HTML out. No DOM, no network.
 *
 * Extracted so `test_onboard_drift_enrolment.py` can EXECUTE it and assert
 * what an operator sees -- specifically that a newly onboarded device with
 * no capture yet is NAMED, with its reason. "Not yet captured" and
 * "invisible" are different states and only one of them is acceptable; a
 * test against the payload cannot tell them apart on screen.
 *
 * Third renderer extracted for this reason, after the agent panel and the
 * onboarding wizard. */
function driftDetailHtml(data) {
  const lr = (data && data.last_run) || null;
  if (!lr) return '';
  const esc = s => String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

  const inventory = lr.inventory || 0;
  const checked   = lr.checked || 0;
  const pending   = (data && data.pending_approvals) || 0;

  /* The ACCOUNTING is rendered from the fields, not read out of the summary
     sentence. A stored result from before 3.3b has no `inventory`, and a
     sentence is not a place to keep numbers: "All 9 device(s) clean" reads
     identically for 9 of 9 and for 9 of 10. */
  let html = '';
  if (inventory > 0) {
    const bits = [`<strong>checked ${checked} of ${inventory}</strong>`];
    if (lr.drifted)                bits.push(`${lr.drifted} drifted`);
    if (lr.clean)                  bits.push(`${lr.clean} clean`);
    if ((lr.skipped || []).length) bits.push(`${lr.skipped.length} not checked`);
    if ((lr.errors  || []).length) bits.push(`${lr.errors.length} unreachable`);
    html += `<div class="text-secondary">${bits.join(' · ')}</div>`;
  } else if (lr.summary) {
    html += `<div class="text-secondary">${esc(lr.summary)}</div>`
         +  `<div class="text-muted small">Recorded before per-device`
         +  ` accounting; run a check to get coverage.</div>`;
  }

  if (pending > 0) {
    html += `<span class="badge bg-warning text-dark mt-1">${pending} pending `
         +  `approval${pending !== 1 ? 's' : ''}</span>`;
  }
  /* Every device not checked, NAMED with its reason. "checked 9 of 10"
     without the tenth device's name is a number nobody can act on -- and a
     device onboarded a minute ago is exactly who lands here. */
  (lr.skipped || []).forEach(x => {
    html += `<div class="text-warning small mt-1">Not checked: `
         +  `${esc(x.hostname)} — ${esc(x.reason)}</div>`;
  });
  (lr.errors || []).forEach(x => {
    html += `<div class="text-danger small mt-1">Unreachable: `
         +  `${esc(x.hostname)} — ${esc(x.reason)}</div>`;
  });
  return html;
}

async function loadDriftStatus() {
  try {
    const r    = await fetch('/drift/status');
    const data = await r.json();

    const badge   = document.getElementById('driftStatusBadge');
    const lastRun = document.getElementById('driftLastRun');
    const sel     = document.getElementById('driftIntervalSelect');
    const toggle  = document.getElementById('driftEnabledToggle');

    if (sel && data.interval_s) {
      // Snap to the nearest option value
      const opts = Array.from(sel.options).map(o => parseInt(o.value, 10));
      const closest = opts.reduce((a, b) => Math.abs(b - data.interval_s) < Math.abs(a - data.interval_s) ? b : a);
      sel.value = String(closest);
      sel.disabled = !!data.disabled;
    }
    if (toggle) {
      toggle.checked = !data.disabled;
    }

    // A partial check must not be able to look like a full one. The badge
    // used to read "Clean" whenever nothing drifted, including when nothing
    // was CHECKED -- which is what a nine-device fleet enumerated from an
    // empty store reports.
    const lr        = data.last_run || null;
    const inventory = lr ? (lr.inventory || 0) : 0;
    const checked   = lr ? (lr.checked || 0) : 0;
    const partial   = inventory > 0 && checked < inventory;
    const coverage  = inventory > 0 ? ` ${checked}/${inventory}` : '';

    if (badge) {
      if (data.disabled) {
        badge.className = 'badge bg-secondary small';
        badge.textContent = 'Disabled';
      } else if (data.running) {
        badge.className = 'badge bg-primary small';
        badge.textContent = 'Running…';
      } else if (!lr) {
        badge.className = 'badge bg-secondary small';
        badge.textContent = 'Not run yet';
      } else {
        const drifted = lr.drifted || 0;
        const errors  = (lr.errors || []).length;
        if (drifted > 0) {
          badge.className = 'badge bg-warning text-dark small';
          badge.textContent = `${drifted} drifted${coverage}`;
        } else if (checked === 0) {
          badge.className = 'badge bg-danger small';
          badge.textContent = `Nothing checked${coverage}`;
        } else if (errors > 0 && (lr.clean || 0) === 0) {
          badge.className = 'badge bg-danger small';
          badge.textContent = 'Errors';
        } else if (partial) {
          badge.className = 'badge bg-warning text-dark small';
          badge.textContent = `Clean${coverage}`;
        } else {
          badge.className = 'badge bg-success small';
          badge.textContent = `Clean${coverage}`;
        }
      }
    }

    if (lastRun) {
      // A disabled checker shows WHEN it was switched off and what the last
      // run said. Blanking the line is how a silenced check becomes
      // invisible: the reason it was switched off gets fixed, and nothing
      // anywhere prompts a re-evaluation.
      if (data.disabled) {
        const since = data.disabled_at ? ` since ${_esc(data.disabled_at)}` : '';
        const by    = data.disabled_by ? ` by ${_esc(data.disabled_by)}` : '';
        const last  = data.last_at ? ` · last ran ${data.last_at}` : ' · never ran';
        lastRun.innerHTML = `<span class="text-warning">Scheduled checks off${since}${by}</span>${_esc(last)}`;
      } else if (data.last_at) {
        // The next-run time is held in memory, not in drift_state.json. The
        // title says so: `disabled` in that file is live and re-read every
        // pass, while the schedule is not read from it at all, and an
        // operator who edits the file and watches nothing happen has hit the
        // same confusion as the toggle that silently reverted.
        const next = data.next_at
          ? ` · next <span title="Held in memory. Editing drift_state.json`
            + ` does not move it — use Check now.">${_esc(data.next_at)}</span>`
          : '';
        lastRun.innerHTML = `Last: ${_esc(data.last_at)}${next}`;
      } else if (data.next_at) {
        lastRun.textContent = `Enabled, first check at ${data.next_at}`;
      } else {
        lastRun.textContent = 'Enabled, idle';
      }
    }

    const detail = document.getElementById('driftResultDetail');
    if (detail && lr) {
      detail.style.display = '';
      detail.innerHTML = driftDetailHtml(data);
    } else if (detail) {
      detail.style.display = 'none';
    }
  } catch (_) {}
}

async function runDriftCheck() {
  const btn     = document.getElementById('driftCheckBtn');
  const spinner = btn && btn.querySelector('.spinner-border');
  const btnText = btn && btn.querySelector('.btn-text');

  if (btn) btn.disabled = true;
  if (spinner) spinner.classList.remove('d-none');
  if (btnText) btnText.textContent = 'Checking…';

  try {
    const r    = await fetch('/drift/check/sync', { method: 'POST' });
    const data = await r.json();
    if (data.summary) {
      showToast(data.summary, data.drifted > 0 ? 'warning' : (data.errors && data.errors.length ? 'danger' : 'success'));
    }
    await loadDriftStatus();
    // Refresh the approvals list if there are new drift findings
    if (data.drifted > 0) await loadApprovalsTab();
  } catch (err) {
    showToast('Drift check failed: ' + err, 'danger');
  } finally {
    if (btn) btn.disabled = false;
    if (spinner) spinner.classList.add('d-none');
    if (btnText) btnText.textContent = 'Check Now';
  }
}

async function loadApprovalsTab() {
  const el      = document.getElementById('approvalsPanel');
  const showAll = document.getElementById('approvalsShowAll');
  if (!el) return;

  // Drift check is AI-independent — always load its status
  loadDriftStatus();

  const url = '/ai/approvals' + (showAll && showAll.checked ? '?all=1' : '');
  try {
    const r    = await fetch(url);
    const data = await r.json();
    const entries   = data.entries || [];
    const aiEnabled = data.ai_enabled !== false;

    _updateApprovalsBadge(data.pending_count || 0);

    // Approve All only shown when AI is on (agent-driven approvals) and multiple pending
    const approveAllBtn = document.getElementById('approveAllBtn');
    const pendingEntries = entries.filter(e => e.status === 'pending');
    if (approveAllBtn) approveAllBtn.style.display = (aiEnabled && pendingEntries.length > 1) ? '' : 'none';

    if (entries.length === 0) {
      el.innerHTML = `<div class="text-muted small py-4 text-center">
        ${showAll && showAll.checked ? 'No approvals found.' : 'No pending approvals — all devices are up to date.'}
      </div>`;
      return;
    }

    el.innerHTML = entries.map(e => _renderApprovalCard(e)).join('');
  } catch (err) {
    el.innerHTML = `<div class="text-danger small">Failed to load approvals: ${_esc(String(err))}</div>`;
  }
}

async function approveAll() {
  const btn = document.getElementById('approveAllBtn');
  if (btn) { btn.disabled = true; btn.textContent = 'Approving…'; }
  try {
    const r = await fetch('/ai/approvals/approve_all', { method: 'POST' });
    const j = await r.json();
    if (j.failed > 0) {
      showToast(`Approved ${j.approved} — ${j.failed} failed`, 'warning');
    } else {
      showToast(`Approved all ${j.approved} pending action${j.approved !== 1 ? 's' : ''}`, 'success');
    }
    await loadApprovalsTab();
  } catch (err) {
    showToast('Approve all failed: ' + err, 'danger');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Approve All'; }
  }
}

function _renderApprovalCard(e) {
  const statusColors = { pending: 'warning', approved: 'success', rejected: 'secondary', expired: 'dark' };
  const statusColor  = statusColors[e.status] || 'secondary';
  const isPending    = e.status === 'pending';

  const typeLabels = {
    update_golden_config: '📁 Update Golden Config',
    revert_to_golden:     '↩ Revert to Golden',
  };
  const typeLabel = typeLabels[e.action_type] || _esc(e.action_type);

  const diffHtml = e.diff
    ? `<details class="mt-2">
        <summary class="text-muted small" style="cursor:pointer">View diff</summary>
        <pre class="mt-1 p-2 rounded small" style="background:#0f172a;color:#94a3b8;max-height:300px;overflow:auto;font-size:0.72rem;white-space:pre">${_esc(e.diff.slice(0, 8000))}</pre>
      </details>` : '';

  const contextHtml = e.context
    ? `<div class="text-muted small mt-1"><em>${_esc(e.context.slice(0, 300))}</em></div>` : '';

  const actionBtns = isPending
    ? `<div class="d-flex gap-2 mt-3">
        <button class="btn btn-success btn-sm px-3" onclick="resolveApproval('${e.id}','approve')">
          Approve
        </button>
        <button class="btn btn-outline-danger btn-sm px-3" onclick="resolveApproval('${e.id}','reject')">
          Reject
        </button>
      </div>`
    : `<div class="text-muted small mt-2">
        ${e.status.charAt(0).toUpperCase() + e.status.slice(1)}
        ${e.resolved_at ? ' at ' + _esc(e.resolved_at) : ''}
      </div>`;

  return `
    <div class="card mb-3" id="approval-card-${e.id}"
         style="background:#1e293b;border:1px solid ${isPending ? '#f59e0b55' : '#33415588'}">
      <div class="card-body p-3">
        <div class="d-flex justify-content-between align-items-start gap-2 mb-2">
          <div>
            <span class="badge bg-${statusColor} me-2">${e.status.toUpperCase()}</span>
            <strong class="text-light">${typeLabel}</strong>
          </div>
          <span class="text-muted small">${_esc(e.created_at)}</span>
        </div>

        <div class="text-light mb-1">${_esc(e.device_hostname || e.device_ip)}
          <span class="text-muted small ms-1">(${_esc(e.device_ip)})</span>
        </div>
        <div class="small text-muted mb-1">${_esc(e.description)}</div>
        ${contextHtml}
        ${diffHtml}

        ${isPending
          ? `<div class="text-muted" style="font-size:0.72rem;margin-top:6px">
              Expires: ${_esc(e.expires_at)}
            </div>` : ''}

        ${actionBtns}
      </div>
    </div>`;
}

async function resolveApproval(id, action) {
  const card = document.getElementById(`approval-card-${id}`);
  if (card) {
    const btns = card.querySelectorAll('button');
    btns.forEach(b => { b.disabled = true; });
    btns[0] && (btns[0].textContent = action === 'approve' ? 'Approving…' : 'Rejecting…');
  }

  try {
    const r    = await fetch(`/ai/approvals/${id}/${action}`, { method: 'POST' });
    const data = await r.json();

    if (!data.ok) {
      showToast(data.error || 'Failed', 'danger');
      return;
    }

    const exec = data.execution || {};
    if (action === 'approve') {
      // A confirm-ending action is not finished by approving it. Approving
      // opens the preview; the exact program is computed NOW, from the device
      // as it is now, and the operator confirms that. The queued diff — what
      // the agent saw when the drift was detected — is passed along as
      // context and never reaches a device.
      if (exec.needs_confirmation && exec.restore) {
        showToast(exec.message || 'Confirmation required', 'info');
        loadApprovalsTab();
        return previewBaselineRestore(exec.restore.ref, null, {
          devices: exec.restore.devices,
          approvalId: exec.restore.approval_id,
          advisoryDiff: exec.advisory_diff || '',
          advisoryNote: exec.advisory_note || '',
        });
      }
      if (exec.error) {
        showToast(`Approved but execution failed: ${exec.error}`, 'warning');
      } else if (exec.note) {
        showToast(exec.note, 'info');
      } else {
        showToast(`Approved and executed for ${exec.hostname || exec.device || id}`, 'success');
      }
    } else {
      showToast('Rejected — no action taken.', 'secondary');
    }

    loadApprovalsTab();
  } catch (err) {
    showToast('Request failed', 'danger');
    if (card) card.querySelectorAll('button').forEach(b => b.disabled = false);
  }
}

function _updateApprovalsBadge(count) {
  const badge = document.getElementById('approvalsBadge');
  if (!badge) return;
  if (count > 0) {
    badge.textContent = count;
    badge.style.display = 'inline';
  } else {
    badge.style.display = 'none';
  }
}

/* Ask AI about currently selected devices */
function askAiAboutSelection() {
  const checkboxes = document.querySelectorAll('.device-checkbox:checked');
  const hostnames  = [];
  checkboxes.forEach(function (cb) {
    const row      = cb.closest('tr');
    const hostname = row ? (row.querySelector('.device-hostname')  || {}).textContent : '';
    const ip       = cb.value;
    if (ip) hostnames.push((hostname ? hostname.trim() + ' (' + ip + ')' : ip));
  });

  let prompt;
  if (hostnames.length === 0) {
    prompt = 'Show me the status of all devices in the network.';
  } else if (hostnames.length === 1) {
    prompt = 'Diagnose and summarise the status of ' + hostnames[0] + '.';
  } else {
    prompt = 'Show the interface and routing status of these devices: ' + hostnames.join(', ') + '.';
  }

  /* Open panel then pre-fill the input */
  document.getElementById('aiOpenBtn').click();
  setTimeout(function () {
    const input = document.getElementById('ai-input');
    if (input) {
      input.value = prompt;
      input.dispatchEvent(new Event('input'));
      input.focus();
    }
  }, 350);
}
