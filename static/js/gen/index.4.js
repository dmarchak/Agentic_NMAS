/* ------------------------------------------------------------------ */
/* Today's index page: the NetBox tab and the drift panel (the AI       */
/* family's tabs left with it, D15)                                     */
/* ------------------------------------------------------------------ */

// Load tab data when tab becomes active for the first time
document.addEventListener('DOMContentLoaded', function () {
  const netboxTabBtn     = document.getElementById('netbox-tab');
  const gitTabBtn        = document.getElementById('git-tab');

  if (netboxTabBtn)     netboxTabBtn.addEventListener('shown.bs.tab', loadNetboxTab);
  // Unlike every other tab above, Git had no auto-load-on-switch wiring --
  // it only ever loaded via the explicit Refresh button, so re-opening the
  // tab after committing/saving elsewhere in the app showed stale data.
  if (gitTabBtn)        gitTabBtn.addEventListener('shown.bs.tab', loadGitTab);
  loadDriftStatus();                      // populate drift badge on load
});

// ========================================================================
// COMPLIANCE TAB
// ========================================================================


// ========================================================================
// NETBOX TAB
// ========================================================================

let _netboxPollTimer = null;

// The sync card's badge colour comes from the import's RESULT level (C85):
// it was green whenever `failed` was empty, while C8's `write_failures`,
// `partial` and `complete` were read by nothing.
const _NB_LEVEL_BADGE = {success: 'success', warning: 'warning text-dark',
                         danger: 'danger', secondary: 'secondary'};

async function loadNetboxTab() {
  // Every recorded Remove, the latest drawn in full (C121).
  if (typeof loadNetboxRemovals === 'function') loadNetboxRemovals();
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
                  ? `<span class="badge bg-${_NB_LEVEL_BADGE[previewConfirmResultLevel(summary.result)] || 'secondary'}" data-nb-level="${_esc((summary.result || {}).level || '')}">last sync ${_esc(summary.timestamp || '')}</span>`
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
                    <span class="badge bg-secondary me-1" title="devices whose golden config was read without error, of the list">read ${summary.synced != null ? summary.synced : '?'}/${summary.total != null ? summary.total : '?'}</span>
                    ${fails.length ? `<span class="badge bg-warning text-dark">failed ${fails.length}</span>` : ''}
                  </div>
                  <details class="small mt-1" data-nb-outcome><summary>Outcome of the last import</summary>
                    ${previewConfirmResultHtml(summary.result, {})}</details>
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
// DRIFT TAB (the drift panel; it retires with today's pages)
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
  /* ANSWER FIRST (the operator's presentation rule, 2026-09-28): what is
     wrong comes first (drifted, unreachable, not checked, pending approvals),
     and the accounting and the run that produced it come after, as the
     evidence. Nothing is dropped; only the order says which is the answer. */
  let html = '';
  (lr.drifted_devices || []).forEach(x => {
    html += `<div class="text-danger small">Drifted: ${esc(x.hostname)} — `
         +  `${esc(x.diff_lines)} diff line(s) from its golden</div>`;
  });
  /* Every device not checked, NAMED with its reason. "checked 9 of 10"
     without the tenth device's name is a number nobody can act on -- and a
     device onboarded a minute ago is exactly who lands here. */
  (lr.errors || []).forEach(x => {
    html += `<div class="text-danger small">Unreachable: `
         +  `${esc(x.hostname)} — ${esc(x.reason)}</div>`;
  });
  (lr.skipped || []).forEach(x => {
    html += `<div class="text-warning small">Not checked: `
         +  `${esc(x.hostname)} — ${esc(x.reason)}</div>`;
  });
  if (pending > 0) {
    html += `<span class="badge bg-warning text-dark">${pending} pending `
         +  `approval${pending !== 1 ? 's' : ''}</span>`;
  }
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

  /* WHEN and WHY the run happened, and WHAT it found (C96: after a run the
     panel said there was one and not what it found). */
  if (lr.timestamp || lr.triggered_by) {
    html += `<div class="text-muted small">run ${esc(lr.timestamp || 'at an unrecorded time')}`
         +  `, triggered by ${esc(lr.triggered_by || 'unrecorded')}</div>`;
  }
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

    /* CONCURRENCY_AUDIT R19: an unreadable state pauses the scheduler and is said, never
       drawn as "Not run yet"; a run another person or process started is drawn running,
       with who started it on hover. */
    const run = data.running_run || null;
    if (badge) {
      badge.title = run ? `Started ${run.started_at || '?'} (${run.triggered_by || '?'}, `
                          + `process ${run.pid || '?'})` : '';
      if (data.unreadable) {
        badge.className = 'badge bg-danger small';
        badge.textContent = 'State unreadable';
      } else if (data.disabled) {
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
      if (data.unreadable) {
        lastRun.innerHTML = `<span class="text-danger">Scheduled checks paused: ${_esc(data.unreadable)}. `
          + 'Nothing is written over it; it is preserved beside it when a write is refused.</span>';
      } else if (data.disabled) {
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
    return r.ok;
  } catch (e) {
    // It swallowed this silently, so a failed read left the last badge on
    // screen looking current. Now it reports, and a re-fetch the
    // invalidation registry started marks the card stale (Stage 7.0).
    console.error('loadDriftStatus', e);
    return false;
  }
}

/* The third measured case (Stage 7.0): after a run, the badge showed the
   previous one. Any response naming `drift` redraws it. */
NMAS.subscribe('drift', 'driftBadge', loadDriftStatus, {panel: 'driftPanel'});

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
    if (data.ok === false && (data.error || data.message)) {
      /* A refusal says why (R19: a run already in progress names who started it), and a
         run whose result could not be recorded is never drawn in the success colour. */
      showToast(data.error || data.message, r.status === 409 ? 'warning' : 'danger');
    } else if (data.summary) {
      showToast(data.summary, data.drifted > 0 ? 'warning' : (data.errors && data.errors.length ? 'danger' : 'success'));
    }
    await loadDriftStatus();
  } catch (err) {
    showToast('Drift check failed: ' + err, 'danger');
  } finally {
    if (btn) btn.disabled = false;
    if (spinner) spinner.classList.add('d-none');
    if (btnText) btnText.textContent = 'Check Now';
  }
}
