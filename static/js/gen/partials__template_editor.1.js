let _tplModal = null, _previewModal = null, _cmInstance = null, _currentTemplate = null;

function _tplList() {
  const el = document.getElementById('templateLibrary');
  return (el && el.dataset.listName) || '';
}
function _tEsc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, c =>
    ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

// PURE RENDERERS, executed by tests/test_template_library_renders.py against
// the payloads the routes return (OPEN_FINDINGS D3).

function templateRowHtml(t) {
  const shared = !!t.shared;
  const bound = shared
    ? `<span class="text-muted">shared macros &mdash; imported by ${
        (t.imported_by || []).map(_tEsc).join(', ') || 'nothing'}</span>`
    : (t.bound_devices.length ? t.bound_devices.map(_tEsc).join(', ')
                              : '<span class="text-muted">none bound</span>');
  const appr = shared
    ? `<td class="small text-muted">no approval of its own &mdash; editing it
         revokes: ${(t.imported_by || []).map(_tEsc).join(', ') || 'nothing'}</td>`
    : `<td id="appr_${_tEsc(t.path).replace(/[^a-z0-9]/gi,'_')}"
           class="small text-muted">checking&hellip;</td>`;
  const actions = shared ? '' : `
        <button class="btn btn-outline-primary btn-sm"
                onclick="validateTemplate('${_tEsc(t.path)}')">Validate</button>
        <button class="btn btn-outline-success btn-sm"
                onclick="approveTemplate('${_tEsc(t.path)}')">Approve</button>`;
  return `
    <tr>
      <td class="font-monospace small">${_tEsc(t.path)}</td>
      <td class="small">${bound}</td>
      ${appr}
      <td class="text-end text-nowrap">
        <button class="btn btn-outline-secondary btn-sm"
                onclick="openTemplate('${_tEsc(t.path)}')">Edit</button>${actions}
      </td>
    </tr>`;
}

// The REASON first, then what re-approval needs. A withdrawal always carries
// a `changes` entry, and drawing `changes` in preference to `reason` meant
// the reason ("REVOKED: '_common.j2' was edited...") reached the browser and
// was drawn nowhere.
function approvalCellHtml(d) {
  if (d.approved) {
    return `<span class="badge bg-success">approved</span>
        <span class="text-muted ms-1">${_tEsc(d.approved_at || '')}</span>`;
  }
  const lines = [d.reason].concat(d.changes || []).filter(Boolean);
  return `<span class="badge bg-secondary">not approved</span>
        <div class="text-muted small">${lines.map(_tEsc).join('<br>')}</div>`;
}

// Says what HAPPENED. It used to read "approval revoked" whatever the route
// returned, so a save that withdrew nothing claimed it had.
function saveToastText(d) {
  const sha = String(d.commit || '').slice(0, 8) || '(no commit)';
  return d.approval_revoked
    ? `Saved and committed ${sha} — approval withdrawn: ${(d.revoked || []).join(', ')}`
    : `Saved and committed ${sha} — no approval was affected`;
}

async function loadTemplateLibrary() {
  const host = document.getElementById('templateLibrary');
  if (!host || !_tplList()) return;
  try {
    const d = await (await fetch('/templates')).json();
    if (!d.ok) return;
    host.innerHTML = `
      <div class="card border-light-subtle">
        <div class="card-body py-2 px-3">
          <h6 class="text-primary fw-semibold mb-2">Template library
            <span class="text-muted fw-normal small ms-1">(per platform — not per device)</span>
          </h6>
          <div class="table-responsive"><table class="table table-sm align-middle mb-0">
            <thead><tr><th>Template</th><th>Bound devices</th>
              <th>Approval</th><th class="text-end">Actions</th></tr></thead>
            <tbody>${d.templates.map(templateRowHtml).join('')}</tbody>
          </table></div>
          <div class="form-text mb-0">
            A template can only be approved once it round-trips cleanly against
            <strong>every</strong> device bound to it. Editing it, or binding a new
            device, revokes approval automatically.
          </div>
        </div>
      </div>`;
    d.templates.filter(t => !t.shared).forEach(t => _loadApproval(t.path));
  } catch (e) { console.error('loadTemplateLibrary', e); }
}

async function _loadApproval(path) {
  const cell = document.getElementById('appr_' + path.replace(/[^a-z0-9]/gi,'_'));
  if (!cell) return;
  try {
    const d = await (await fetch(`/templates/approval/${encodeURIComponent(path)}`)).json();
    cell.innerHTML = approvalCellHtml(d);
  } catch (e) { cell.textContent = 'unknown'; }
}

async function openTemplate(path) {
  if (!_tplModal) _tplModal = new bootstrap.Modal(document.getElementById('templateEditorModal'));
  _currentTemplate = path;
  document.getElementById('templateEditorTitle').textContent = path;
  const status = document.getElementById('templateEditorStatus');
  status.textContent = '';
  try {
    const d = await (await fetch(`/templates/file/${encodeURIComponent(path)}`)).json();
    if (!d.ok) { showToast(d.error, 'danger'); return; }

    document.getElementById('templateEditorMeta').innerHTML =
      `Bound devices: <strong>${d.bound_devices.map(_tEsc).join(', ') || 'none'}</strong>`;
    document.getElementById('templateEditorWarning').textContent =
      'Saving commits the change and revokes approval.';

    const area = document.getElementById('templateEditorArea');
    area.value = d.content;

    if (typeof window.CodeMirror !== 'undefined') {
      if (_cmInstance) { _cmInstance.toTextArea(); _cmInstance = null; }
      // A missing mode is not an error in CodeMirror — it just renders plain
      // text. Check explicitly so the two failure modes are distinguishable.
      const modeReady = !!(CodeMirror.modes && CodeMirror.modes.jinja2);
      _cmInstance = CodeMirror.fromTextArea(area, {
        lineNumbers: true, mode: modeReady ? 'jinja2' : null,
        lineWrapping: true, viewportMargin: Infinity,
      });
      if (!modeReady) {
        status.className = 'form-text text-warning';
        status.textContent = 'CodeMirror loaded but the jinja2 mode did not — '
          + 'highlighting is off. Check static/js/vendor/codemirror/jinja2.js.';
      }
    } else {
      status.textContent = 'Plain editor — CodeMirror is not vendored '
        + '(see static/js/vendor/codemirror/README.md). Editing works normally.';
    }
    _tplModal.show();
  } catch (e) { showToast('Error: ' + e.message, 'danger'); }
}

async function saveTemplate() {
  const content = _cmInstance ? _cmInstance.getValue()
                              : document.getElementById('templateEditorArea').value;
  const status = document.getElementById('templateEditorStatus');
  status.className = 'form-text';
  status.textContent = 'Saving…';
  try {
    const r = await fetch(`/templates/file/${encodeURIComponent(_currentTemplate)}`, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({content}),
    });
    const d = await r.json();
    if (!d.ok) {
      status.className = 'form-text text-danger';
      status.textContent = d.error;            // Jinja errors carry file + line
      return;
    }
    showToast(saveToastText(d), 'success');
    _tplModal.hide();
    loadTemplateLibrary();
  } catch (e) {
    status.className = 'form-text text-danger';
    status.textContent = e.message;
  }
}

async function validateTemplate(path) {
  showToast('Validating against every bound device…', 'info');
  try {
    const d = await (await fetch(`/templates/validate/${encodeURIComponent(path)}`,
                                 {method: 'POST'})).json();
    const lines = (d.results || []).map(r =>
      `${r.ok ? '✓' : '✗'} ${r.device}: ${r.missing} missing, ${r.extra} extra, `
      + `${r.reordered} reordered, ${r.unmodeled} unmodelled`
      + (r.unmodeled_acknowledged ? '' : ' (unacknowledged)'));
    alert(`${path}\n\n${d.ok ? 'PASSES on all bound devices' : 'FAILS'}\n\n`
          + lines.join('\n'));
  } catch (e) { showToast('Error: ' + e.message, 'danger'); }
}

async function approveTemplate(path) {
  try {
    const d = await (await fetch(`/templates/approve/${encodeURIComponent(path)}`, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({}),
    })).json();
    if (d.ok) {
      showToast(`Approved against ${d.validation.device_count} device(s)`, 'success');
    } else {
      const detail = (d.validation ? d.validation.results.filter(r => !r.ok)
        .map(r => `  ${r.device}: ${r.missing} missing, ${r.extra} extra`).join('\n') : '');
      alert(`Cannot approve ${path}\n\n${d.error}\n\n${detail}`);
    }
    loadTemplateLibrary();
  } catch (e) { showToast('Error: ' + e.message, 'danger'); }
}

/* ── Render preview ────────────────────────────────────────────────────── */
async function showRenderPreview(hostname) {
  if (!_previewModal) _previewModal = new bootstrap.Modal(document.getElementById('renderPreviewModal'));
  const body = document.getElementById('renderPreviewBody');
  document.getElementById('renderPreviewTitle').textContent = `Render preview — ${hostname}`;
  body.innerHTML = '<div class="text-center py-4"><div class="spinner-border text-primary"></div></div>';
  _previewModal.show();

  try {
    const d = await (await fetch(`/templates/preview/${encodeURIComponent(hostname)}`)).json();
    if (!d.ok) { body.innerHTML = `<div class="alert alert-danger mb-0">${_tEsc(d.error)}</div>`; return; }

    const gate = d.deployable
      ? '<span class="badge bg-success">Deployable</span>'
      : '<span class="badge bg-warning text-dark">Incomplete — not deployable</span>';

    const blockers = d.blocking_reasons.length ? `
      <div class="alert alert-warning py-2 px-3">
        <strong>This render cannot be deployed.</strong>
        <ul class="mb-1 small">${d.blocking_reasons.map(r => `<li>${_tEsc(r)}</li>`).join('')}</ul>
        ${d.unacknowledged.length ? `
          <div class="small">Unmodelled lines needing acknowledgement:
            <ul class="font-monospace">${d.unacknowledged.slice(0,10)
              .map(l => `<li>${_tEsc(l)}</li>`).join('')}</ul>
            An acknowledgement lists these exact lines in <code>host_vars</code>,
            is committed to git, and is invalidated the moment a new unmodelled
            line appears.</div>` : ''}
      </div>` : '';

    /* A clean preview is only as strong as what it compared.

       The render masks secrets and the capture holds the real values, so a
       secret-bearing line can never be compared -- it is neutralised rather
       than reported, or every such line would show as drift for ever and
       train people to scroll past the section where real drift appears.

       Saying so is the point. A gap that is NAMED is a finding; one that is
       implied by masking is a clean panel that quietly means less than it
       looks like it means. */
    const _tMaskedNote = (obj) => {
      if (!obj.available || !obj.masked_not_compared) return '';
      const n = obj.masked_not_compared;
      return `<p class="small text-warning-emphasis mb-0 mt-1">
        ${n} secret-bearing line${n === 1 ? '' : 's'} could not be compared —
        the render masks the value and the capture holds the real one, so only
        the <em>rest</em> of each line was checked. A value changed by hand on
        the device would not show here.
        <span class="text-muted">Drift check compares the real values; this
        preview cannot.</span></p>`;
    };

    const diffPane = (label, obj) => `
      <h6 class="fw-semibold mt-3 mb-1">vs ${label}
        ${obj.captured_at ? `<span class="text-muted fw-normal small">captured ${_tEsc(obj.captured_at)}</span>` : ''}
      </h6>
      ${obj.available
        ? (obj.changed
            ? `<pre class="small bg-body-tertiary p-2 rounded" style="max-height:300px;overflow:auto">${_tEsc(obj.diff)}</pre>`
            : '<p class="small text-success mb-0">No differences.</p>')
        : `<p class="small text-muted mb-0">${_tEsc(obj.message)}
             <button class="btn btn-outline-secondary btn-sm ms-2"
                     onclick="refreshCapture('${_tEsc(hostname)}')">Refresh capture</button></p>`}
      ${_tMaskedNote(obj)}`;

    body.innerHTML = `
      <div class="d-flex align-items-center gap-2 flex-wrap mb-2">
        ${gate}
        <span class="badge bg-secondary-subtle text-secondary-emphasis">
          template ${_tEsc(d.template)}</span>
        <span class="text-muted small">modelled ${d.modeled_coverage}% ·
          fidelity ${d.round_trip_fidelity}%</span>
        <button class="btn btn-outline-secondary btn-sm ms-auto"
                onclick="refreshCapture('${_tEsc(hostname)}')">Refresh capture</button>
      </div>
      ${blockers}
      <div class="alert alert-info py-2 px-3 small">
        Secrets are masked in this preview and in anything written to
        <code>intended/</code>. Masked output is never a deploy source — a deploy
        re-renders from the template with real secrets at push time.
      </div>
      ${diffPane('current golden', d.diff_vs_golden)}
      ${diffPane('last captured running config', d.diff_vs_running)}
      <h6 class="fw-semibold mt-3 mb-1">Rendered (secrets masked)</h6>
      <pre class="small bg-body-tertiary p-2 rounded"
           style="max-height:360px;overflow:auto">${_tEsc(d.rendered)}</pre>`;
  } catch (e) {
    body.innerHTML = `<div class="alert alert-danger mb-0">${_tEsc(e.message)}</div>`;
  }
}

async function refreshCapture(hostname) {
  try {
    const d = await (await fetch(`/templates/refresh-capture/${encodeURIComponent(hostname)}`,
                                 {method: 'POST'})).json();
    if (!d.ok) { showToast(d.error, 'danger'); return; }
    showToast('Capturing…', 'info');
    // 3b owns no connection code — call the route that does, then reload.
    await fetch(d.delegate_to, {method: d.method});
    showRenderPreview(hostname);
  } catch (e) { showToast('Error: ' + e.message, 'danger'); }
}

document.addEventListener('DOMContentLoaded', loadTemplateLibrary);
