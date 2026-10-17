function _gEsc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, c =>
    ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
}

function _gWhen(iso) {
  if (!iso) return '';
  try { return new Date(iso).toLocaleString(); } catch (e) { return iso; }
}

/* ── Per-device timeline ─────────────────────────────────────────────────── */
let _goldenTimelineModal = null;

async function showGoldenHistory(hostname) {
  if (!_goldenTimelineModal) {
    _goldenTimelineModal = new bootstrap.Modal(document.getElementById('goldenTimelineModal'));
  }
  document.getElementById('goldenTimelineTitle').textContent = `Golden config history — ${hostname}`;
  const body = document.getElementById('goldenTimelineBody');
  body.innerHTML = '<div class="text-center py-4"><div class="spinner-border text-primary"></div></div>';
  _goldenTimelineModal.show();

  try {
    const r = await fetch(`/golden/history/${encodeURIComponent(hostname)}`);
    const d = await r.json();
    if (!d.ok) { body.innerHTML = `<div class="alert alert-danger mb-0">${_gEsc(d.error)}</div>`; return; }
    if (!d.history.length) {
      body.innerHTML = '<p class="text-muted mb-0">No promotions recorded yet.</p>';
      return;
    }

    const rows = d.history.map((h, i) => {
      const ci = h.ci
        ? `<span class="badge bg-${h.ci.result === 'SUCCESS' ? 'success' : 'danger'}-subtle
             text-${h.ci.result === 'SUCCESS' ? 'success' : 'danger'}-emphasis"
             title="${_gEsc(h.ci.job)} #${_gEsc(h.ci.build)}">${_gEsc(h.ci.result)}</span>`
        : '<span class="text-muted small">—</span>';
      const isRename = h.source === 'rename';
      return `<tr class="${isRename ? 'table-light' : ''}">
        <td class="small text-nowrap">${_gEsc(_gWhen(h.timestamp))}</td>
        <td><span class="badge bg-secondary-subtle text-secondary-emphasis">${_gEsc(h.source)}</span></td>
        <td class="small">${_gEsc(h.actor)}</td>
        <td class="small">${_gEsc(h.subject)}</td>
        <td>${ci}</td>
        <td class="font-monospace small">${_gEsc(h.sha.slice(0, 8))}</td>
        <td class="text-end text-nowrap">
          <input type="radio" name="gdiffA" value="${_gEsc(h.sha)}" ${i === 1 ? 'checked' : ''} title="Compare from">
          <input type="radio" name="gdiffB" value="${_gEsc(h.sha)}" ${i === 0 ? 'checked' : ''} title="Compare to">
          <button class="btn btn-outline-secondary btn-sm ms-1"
                  onclick="downloadGoldenVersion('${_gEsc(hostname)}','${_gEsc(h.sha)}')">Download</button>
        </td>
      </tr>`;
    }).join('');

    body.innerHTML = `
      <p class="small text-muted">
        Timestamps come from the commits, not from file modification times.
        Renames are their own commit, so history follows a device across a rename.
      </p>
      <div class="table-responsive"><table class="table table-sm align-middle">
        <thead><tr><th>When</th><th>Source</th><th>Actor</th><th>Message</th>
          <th>CI</th><th>Commit</th><th class="text-end">From / To</th></tr></thead>
        <tbody>${rows}</tbody></table></div>
      <button class="btn btn-primary btn-sm" onclick="diffGoldenVersions('${_gEsc(hostname)}')">
        Compare selected versions
      </button>
      <pre id="goldenDiffOut" class="mt-3 small bg-body-tertiary p-2 rounded d-none"
           style="max-height:420px;overflow:auto"></pre>`;
  } catch (e) {
    body.innerHTML = `<div class="alert alert-danger mb-0">${_gEsc(e.message)}</div>`;
  }
}

async function diffGoldenVersions(hostname) {
  const a = document.querySelector('input[name="gdiffA"]:checked');
  const b = document.querySelector('input[name="gdiffB"]:checked');
  const out = document.getElementById('goldenDiffOut');
  if (!a || !b) { showToast('Pick two versions to compare', 'warning'); return; }
  out.classList.remove('d-none');
  out.textContent = 'Comparing…';
  try {
    const r = await fetch(`/golden/diff/${encodeURIComponent(hostname)}`
      + `?a=${encodeURIComponent(a.value)}&b=${encodeURIComponent(b.value)}`);
    const d = await r.json();
    out.textContent = d.ok ? (d.diff || 'No differences between these versions.')
                           : (d.error || 'Diff failed');
  } catch (e) { out.textContent = e.message; }
}

async function downloadGoldenVersion(hostname, ref) {
  try {
    const r = await fetch(`/golden/version/${encodeURIComponent(hostname)}?ref=${encodeURIComponent(ref)}`);
    const d = await r.json();
    if (!d.ok) { showToast(d.error, 'danger'); return; }
    // The viewer sandbox blocks script-driven downloads, so show the text.
    const body = document.getElementById('goldenTimelineBody');
    const pre = document.getElementById('goldenDiffOut');
    pre.classList.remove('d-none');
    pre.textContent = d.config;
  } catch (e) { showToast(e.message, 'danger'); }
}
