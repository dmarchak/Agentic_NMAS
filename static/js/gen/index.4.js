/* ------------------------------------------------------------------ */
/* Today's index page: the NetBox tab (the AI family's tabs left with   */
/* it, D15; the drift panel at 7.8, its home Settings › Installation)   */
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
