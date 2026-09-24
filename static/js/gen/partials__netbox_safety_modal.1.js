let _netboxSafetyModal = null;
let _netboxSafetyState = {mode: 'import', list: '', writesAllowed: false,
                          token: '', expiresIn: 0};

function _nbSafetyModal() {
  if (!_netboxSafetyModal) {
    _netboxSafetyModal = new bootstrap.Modal(document.getElementById('netboxSafetyModal'));
  }
  return _netboxSafetyModal;
}

function _nbEscape(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, c =>
    ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
}

function _nbGroupTable(title, byType, emptyMsg) {
  const rows = Object.entries(byType || {});
  if (!rows.length) return `<p class="small text-muted mb-2">${emptyMsg}</p>`;
  return `<h6 class="fw-semibold mt-3 mb-1">${title}</h6>
    <div class="table-responsive"><table class="table table-sm mb-1">
      <tbody>${rows.map(([ep, n]) =>
        `<tr><td class="font-monospace small">${_nbEscape(ep)}</td>
             <td class="text-end"><span class="badge bg-primary-subtle text-primary-emphasis">${n}</span></td></tr>`
      ).join('')}</tbody></table></div>`;
}

/* ── Import ─────────────────────────────────────────────────────────────── */
/**
 * What the DATABASE will take, beyond NMAS's own delete list.
 *
 * Pure, and separate from the modal, so the shipped source can be executed
 * against the payload the endpoint returns -- the correction that came out
 * of the agent panel, where three guards each hid the same data and every
 * server test passed while the screen said nothing.
 *
 * Three states, never two. An empty consequence and an unmeasured one look
 * identical in a preview, and the one that reads as safe is the one nobody
 * checked -- so "could not ask" gets its own banner.
 */
function nbCascadeHtml(cascade) {
  if (!cascade) return '';
  const taken = cascade.taken || [];
  const foreign = cascade.foreign || [];
  const unproven = cascade.unproven || [];
  let html = '';

  if (foreign.length) {
    html += `<div class="alert alert-danger py-2 px-3 small mt-3">
      <strong>${foreign.length} object(s) NMAS did not create will be deleted
      too.</strong> The database removes them along with the objects above.
      They carry no <code>nmas-managed</code> tag, so the provenance check
      would have left them alone &mdash; it protects an object, and this
      travels a relationship.
      <ul class="mb-0 mt-1">${foreign.slice(0, 20).map(o =>
        `<li><span class="font-monospace">${_nbEscape(o.endpoint)}</span>
           ${_nbEscape(o.name || o.id)} <em>(via ${_nbEscape(o.via)})</em></li>`
        ).join('')}</ul></div>`;
  } else if (taken.length) {
    html += `<p class="small text-muted mt-3">${taken.length} further
      object(s) will be removed by the database along with these, all of them
      NMAS's own.</p>`;
  }

  if (unproven.length) {
    html += `<div class="alert alert-warning py-2 px-3 small">
      <strong>This preview is incomplete.</strong> It could not establish
      what some of these deletions will take with them, which is
      <em>not</em> the same as nothing.
      <ul class="mb-0 mt-1">${unproven.slice(0, 10).map(u =>
        `<li>${_nbEscape(u)}</li>`).join('')}</ul></div>`;
  }
  return html;
}

async function netboxPreviewImport(listName, allLists) {
  _netboxSafetyState = {mode: allLists ? 'import_all' : 'import',
                        list: listName || '', writesAllowed: false};
  document.getElementById('netboxSafetyTitle').textContent =
    allLists ? 'Import all device lists to NetBox' : 'Import to NetBox (discovery)';
  document.getElementById('netboxSafetyBody').classList.add('d-none');
  document.getElementById('netboxSafetyLoading').classList.remove('d-none');
  document.getElementById('netboxSafetyConfirmBtn').disabled = true;
  document.getElementById('netboxSafetyForgetBtn').classList.add('d-none');
  document.getElementById('netboxSafetyConsent').classList.add('d-none');
  _nbSafetyModal().show();

  try {
    const previewUrl = allLists
      ? '/netbox/safety/import_all/preview'
      : '/netbox/safety/import/preview';
    const r = await fetch(previewUrl, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({list_name: listName || ''}),
    });
    const d = await r.json();
    const body = document.getElementById('netboxSafetyBody');
    document.getElementById('netboxSafetyLoading').classList.add('d-none');
    body.classList.remove('d-none');

    if (!d.ok) {
      body.innerHTML = `<div class="alert alert-danger mb-0">${_nbEscape(d.error)}</div>`;
      return;
    }

    _netboxSafetyState.list = d.list;
    _netboxSafetyState.writesAllowed = d.writes_allowed;
    _netboxSafetyState.token = d.token || '';
    _netboxSafetyState.expiresIn = d.expires_in || 0;
    const p = d.plan || {};

    body.innerHTML = `
      <p class="mb-2">Importing <strong>${_nbEscape(d.list)}</strong>
         (${d.device_count} device(s)) would:</p>
      <div class="alert alert-info py-2 px-3 small">${_nbEscape(d.summary)}</div>
      ${_nbGroupTable('Create', p.creates_by_type, 'Nothing new to create.')}
      ${_nbGroupTable('Update', p.updates_by_type, 'Nothing to update.')}
      <p class="small text-muted mt-3 mb-0">
        This preview was read-only. Everything NMAS creates is tagged
        <code>nmas-managed</code> so it can be told apart from records you curated by hand.
      </p>
      <p class="small text-muted mb-0">
        Confirmation is valid for ${Math.round((d.expires_in || 300) / 60)} minute(s) and
        applies only to these changes. If NetBox changes in the meantime the import is
        refused and you will be asked to preview again.
      </p>`;

    if (!d.writes_allowed) {
      document.getElementById('netboxSafetyConsent').classList.remove('d-none');
      document.getElementById('netboxSafetyEnableWrites').checked = false;
      const confirmBtn = document.getElementById('netboxSafetyConfirmBtn');
      confirmBtn.disabled = true;
      document.getElementById('netboxSafetyEnableWrites').onchange = e => {
        confirmBtn.disabled = !e.target.checked;
      };
    } else {
      document.getElementById('netboxSafetyConfirmBtn').disabled = false;
    }
  } catch (e) {
    document.getElementById('netboxSafetyLoading').classList.add('d-none');
    const body = document.getElementById('netboxSafetyBody');
    body.classList.remove('d-none');
    body.innerHTML = `<div class="alert alert-danger mb-0">${_nbEscape(e.message)}</div>`;
  }
}

/* ── Removal ────────────────────────────────────────────────────────────── */
async function netboxPreviewRemoval(listName) {
  _netboxSafetyState = {mode: 'remove', list: listName, writesAllowed: false};
  document.getElementById('netboxSafetyTitle').textContent = `Remove "${listName}" from NetBox`;
  document.getElementById('netboxSafetyBody').classList.add('d-none');
  document.getElementById('netboxSafetyLoading').classList.remove('d-none');
  document.getElementById('netboxSafetyConfirmBtn').disabled = true;
  document.getElementById('netboxSafetyConsent').classList.add('d-none');
  _nbSafetyModal().show();

  try {
    const r = await fetch('/netbox/safety/remove/preview', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({list_name: listName}),
    });
    const d = await r.json();
    const body = document.getElementById('netboxSafetyBody');
    document.getElementById('netboxSafetyLoading').classList.add('d-none');
    body.classList.remove('d-none');

    if (!d.ok) {
      body.innerHTML = `<div class="alert alert-danger mb-0">${_nbEscape(d.error)}</div>`;
      return;
    }

    _netboxSafetyState.writesAllowed = d.writes_allowed;
    _netboxSafetyState.token = d.token || '';
    _netboxSafetyState.expiresIn = d.expires_in || 0;
    const deleted = d.deleted || [];
    const skipped = d.skipped || [];

    if (d.message && !deleted.length) {
      body.innerHTML = `<div class="alert alert-secondary mb-0">${_nbEscape(d.message)}</div>`;
      document.getElementById('netboxSafetyForgetBtn').classList.remove('d-none');
      return;
    }

    body.innerHTML = `
      <div class="alert alert-danger py-2 px-3 small">
        <strong>${deleted.length} object(s) would be permanently deleted.</strong>
        Only objects NMAS created and tagged <code>nmas-managed</code> are eligible.
      </div>
      <div class="table-responsive"><table class="table table-sm">
        <thead><tr><th>Type</th><th>Name</th></tr></thead>
        <tbody>${deleted.map(o =>
          `<tr><td class="font-monospace small">${_nbEscape(o.endpoint)}</td>
               <td>${_nbEscape(o.name || o.id)}</td></tr>`).join('')}</tbody>
      </table></div>
      ${skipped.length ? `
        <h6 class="fw-semibold mt-3 mb-1">Left alone (${skipped.length})</h6>
        <p class="small text-muted">These are not tracked as NMAS-created, so they are
           treated as yours and will not be touched.</p>
        <ul class="small text-muted">${skipped.slice(0, 20).map(o =>
          `<li>${_nbEscape(o.endpoint)} — ${_nbEscape(o.name || o.id)}
             <em>(${_nbEscape(o.reason)})</em></li>`).join('')}</ul>` : ''}
      ${nbCascadeHtml(d.cascade)}`;

    document.getElementById('netboxSafetyForgetBtn').classList.remove('d-none');
    if (!d.writes_allowed) {
      document.getElementById('netboxSafetyConsent').classList.remove('d-none');
      document.getElementById('netboxSafetyEnableWrites').checked = false;
      const confirmBtn = document.getElementById('netboxSafetyConfirmBtn');
      confirmBtn.disabled = true;
      document.getElementById('netboxSafetyEnableWrites').onchange = e => {
        confirmBtn.disabled = !e.target.checked;
      };
    } else {
      document.getElementById('netboxSafetyConfirmBtn').disabled = false;
    }
  } catch (e) {
    document.getElementById('netboxSafetyLoading').classList.add('d-none');
    const body = document.getElementById('netboxSafetyBody');
    body.classList.remove('d-none');
    body.innerHTML = `<div class="alert alert-danger mb-0">${_nbEscape(e.message)}</div>`;
  }
}

/* ── Apply ──────────────────────────────────────────────────────────────── */
async function netboxSafetyApply(forgetOnly) {
  const {mode, list} = _netboxSafetyState;
  const enable = document.getElementById('netboxSafetyEnableWrites').checked;
  const btn = document.getElementById('netboxSafetyConfirmBtn');
  btn.disabled = true;

  const url = {
    import:     '/netbox/safety/import/apply',
    import_all: '/netbox/safety/import_all/apply',
    remove:     '/netbox/safety/remove/apply',
  }[mode];
  const payload = {list_name: list, permit_writes: enable,
                   token: _netboxSafetyState.token};
  if (forgetOnly) payload.forget_only = true;

  try {
    const r = await fetch(url, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload),
    });
    const d = await r.json();
    _nbSafetyModal().hide();
    if (d.ok) {
      showToast(d.message
        || (mode === 'remove'
            ? `Removed ${(d.deleted || []).length} object(s) from NetBox`
            : `Import started for ${_nbEscape(d.list)} (${d.device_count} device(s))`), 'success');
    } else if (d.stale) {
      // The plan changed, the token expired, or it was already used.
      showToast(d.error || 'Confirmation no longer valid — preview again', 'warning');
      if (mode === 'remove') netboxPreviewRemoval(list);
      else netboxPreviewImport(mode === 'import_all' ? '' : list, mode === 'import_all');
      return;
    } else {
      showToast(d.error || 'Operation failed', 'danger');
    }
    if (typeof loadNetboxTab === 'function') loadNetboxTab();
  } catch (e) {
    showToast('Error: ' + e.message, 'danger');
  } finally {
    btn.disabled = false;
  }
}
