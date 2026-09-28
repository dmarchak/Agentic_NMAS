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

/* The preview, drawn by the shared component (7.1): the server builds it
 * (modules/preview_confirm.py netbox_import_preview / netbox_removal_preview),
 * including what the database takes with a delete, so this modal draws
 * nothing itself. The Confirm button's state comes from the component too;
 * the only thing added here is the separate, saved write switch. */
function _nbShowPreview(d) {
  const body = document.getElementById('netboxSafetyBody');
  body.innerHTML = previewConfirmHtml(d.preview, {});
  const target = ((d.preview.what || {}).targets || [])[0] || {};
  const btn = document.getElementById('netboxSafetyConfirmBtn');
  const st = previewConfirmButton(d.preview, target.selectable ? 1 : 0, 'Confirm');
  btn.textContent = st.text;
  const consent = document.getElementById('netboxSafetyEnableWrites');
  if (!d.writes_allowed && !st.disabled) {
    document.getElementById('netboxSafetyConsent').classList.remove('d-none');
    consent.checked = false;
    btn.disabled = true;
    consent.onchange = e => { btn.disabled = !e.target.checked; };
  } else {
    btn.disabled = st.disabled;
  }
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
    _nbShowPreview(d);
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
    // "Just stop tracking" deletes nothing, so it is offered with or
    // without anything to delete.
    document.getElementById('netboxSafetyForgetBtn').classList.remove('d-none');
    _nbShowPreview(d);
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
    if (mode === 'remove' && d.result) {
      // THE RESULT, drawn by the component from the recorded row (C121). The
      // toast said "Removed N object(s)" in green whenever the request
      // succeeded, including when NetBox refused some of the deletes.
      showNetboxRemovalResult(d.result);
      if (typeof loadNetboxRemovals === 'function') loadNetboxRemovals();
    } else if (d.ok) {
      showToast(d.message
        || `Import started for ${_nbEscape(d.list)} (${d.device_count} device(s))`, 'success');
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
