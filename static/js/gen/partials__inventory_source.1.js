let _inventoryStatus = {source: 'local'};

function _inventoryListName() {
  const host = document.getElementById('inventorySourceBanner');
  return (host && host.dataset.listName) || '';
}

function _invEsc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, c =>
    ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
}

/* Controls that edit device identity. Meaningless on a NetBox-sourced list. */
const _IDENTITY_CONTROLS = [
  {sel: '#addDeviceBtn',            label: 'Add Device'},
  {sel: '#refreshHostnamesBtn',     label: 'Refresh Hostnames'},
  {sel: '[data-bs-target="#discoverSubnetModal"]', label: 'Discover Subnet'},
];

function applyInventorySourceUI(status) {
  const isNetbox = status.source === 'netbox';

  _IDENTITY_CONTROLS.forEach(({sel}) => {
    document.querySelectorAll(sel).forEach(el => {
      el.disabled = isNetbox;
      el.classList.toggle('disabled', isNetbox);
      if (isNetbox) {
        el.setAttribute('title', 'Edit in NetBox — this list takes its inventory from NetBox');
        el.setAttribute('data-netbox-locked', '1');
      } else if (el.getAttribute('data-netbox-locked')) {
        el.removeAttribute('title');
        el.removeAttribute('data-netbox-locked');
      }
    });
  });

  // Per-row delete buttons are rendered dynamically, so tag them by attribute.
  document.querySelectorAll('[data-device-delete]').forEach(el => {
    el.disabled = isNetbox;
    el.classList.toggle('disabled', isNetbox);
    if (isNetbox) el.setAttribute('title', 'Edit in NetBox');
  });

  const form = document.getElementById('addDeviceForm');
  if (form) form.classList.toggle('opacity-50', isNetbox);
}

function renderInventoryBanner(status, staleDevices) {
  const host = document.getElementById('inventorySourceBanner');
  if (!host) return;

  if (status.source !== 'netbox') {
    host.classList.add('d-none');
    host.innerHTML = '';
    return;
  }
  host.classList.remove('d-none');

  const skipped = status.skipped || [];
  const warnings = status.warnings || [];
  const stale = Object.entries(staleDevices || {});

  const freshness = status.never_loaded
    ? '<span class="badge bg-secondary">loading…</span>'
    : status.stale
      ? `<span class="badge bg-warning text-dark" title="${_invEsc(status.stale_reason)}">stale</span>`
      : `<span class="badge bg-success">fresh</span>`;

  const rows = (items, cls) => items.map(s => `
    <tr>
      <td class="fw-semibold">${_invEsc(s.name || s.hostname)}</td>
      <td><span class="badge bg-${cls}-subtle text-${cls}-emphasis">${_invEsc(s.field || 'device')}</span></td>
      <td class="small">${_invEsc(s.reason)}</td>
    </tr>`).join('');

  host.innerHTML = `
    <div class="card border-light-subtle">
      <div class="card-body py-2 px-3">
        <div class="d-flex align-items-center gap-2 flex-wrap">
          <span class="fw-semibold">Inventory source: NetBox</span>
          ${freshness}
          <span class="text-muted small">${status.device_count || 0} device(s)</span>
          ${skipped.length ? `<span class="badge bg-warning text-dark">${skipped.length} skipped</span>` : ''}
          ${warnings.length ? `<span class="badge bg-info text-dark">${warnings.length} warning(s)</span>` : ''}
          ${stale.length ? `<span class="badge bg-secondary">${stale.length} stale</span>` : ''}
          <button class="btn btn-outline-primary btn-sm ms-auto" onclick="refreshInventory()">
            Refresh from NetBox
          </button>
        </div>
        ${status.stale_reason ? `<div class="form-text text-warning mb-0">${_invEsc(status.stale_reason)}</div>` : ''}

        ${skipped.length ? `
          <details class="mt-2">
            <summary class="small text-warning">
              ${skipped.length} device(s) skipped — the rest of the list loaded normally
            </summary>
            <div class="table-responsive mt-2">
              <table class="table table-sm mb-0"><tbody>${rows(skipped, 'warning')}</tbody></table>
            </div>
          </details>` : ''}

        ${warnings.length ? `
          <details class="mt-2">
            <summary class="small text-info">${warnings.length} device(s) loaded with a warning</summary>
            <div class="table-responsive mt-2">
              <table class="table table-sm mb-0"><tbody>${rows(warnings, 'info')}</tbody></table>
            </div>
          </details>` : ''}

        ${stale.length ? `
          <details class="mt-2">
            <summary class="small text-secondary">
              ${stale.length} device(s) no longer in NetBox
            </summary>
            <p class="small text-muted mt-2 mb-1">
              Their golden configs and backups are kept and stay browsable. NMAS will
              not act on them: pushes, drift checks and agent actions are refused.
            </p>
            <div class="table-responsive">
              <table class="table table-sm mb-0"><tbody>
                ${stale.map(([ip, e]) => `
                  <tr><td class="fw-semibold">${_invEsc(e.hostname || ip)}</td>
                      <td class="font-monospace small">${_invEsc(ip)}</td>
                      <td class="small text-muted">${_invEsc(e.reason || '')}</td></tr>`).join('')}
              </tbody></table>
            </div>
          </details>` : ''}
      </div>
    </div>`;
}

async function loadInventorySource() {
  const listName = _inventoryListName();
  if (!listName) return;
  try {
    const r = await fetch(`/inventory/source/${encodeURIComponent(listName)}`);
    const d = await r.json();
    if (!d.ok) return;
    _inventoryStatus = d.status || {source: 'local'};
    applyInventorySourceUI(_inventoryStatus);
    renderInventoryBanner(_inventoryStatus, d.stale_devices);
  } catch (e) { console.error('loadInventorySource', e); }
}

async function refreshInventory() {
  const listName = _inventoryListName();
  if (!listName) return;
  try {
    const r = await fetch(`/inventory/refresh/${encodeURIComponent(listName)}`, {method: 'POST'});
    const d = await r.json();
    if (d.ok) {
      showToast(`Refreshed from NetBox — ${d.device_count} device(s)`
        + (d.skipped && d.skipped.length ? `, ${d.skipped.length} skipped` : ''), 'success');
      if (typeof loadDevices === 'function') loadDevices();
    } else {
      showToast('Refresh failed: ' + (d.error || 'unknown'), 'danger');
    }
    loadInventorySource();
  } catch (e) { showToast('Error: ' + e.message, 'danger'); }
}

/* Persist drag-and-drop order. NetBox lists have no CSV to reorder, so the
   order lives in source.json instead. */
async function saveInventoryOrder(hostnames) {
  if (_inventoryStatus.source !== 'netbox') return false;
  const listName = _inventoryListName();
  if (!listName) return false;
  try {
    await fetch(`/inventory/order/${encodeURIComponent(listName)}`, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({order: hostnames}),
    });
    return true;
  } catch (e) { console.error('saveInventoryOrder', e); return false; }
}

document.addEventListener('DOMContentLoaded', loadInventorySource);
