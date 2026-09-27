function _gEsc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, c =>
    ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
}

function _gList() {
  const el = document.getElementById('goldenRepoPanel');
  return (el && el.dataset.listName) || '';
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

/**
 * "N device(s)", and whether that covers the fleet as it is NOW.
 *
 * Pure, so the shipped source can be executed against the payload the
 * endpoint returns. Written because the route was taught to compute
 * `partial` and `missing_devices` and the panel rendered NEITHER -- a value
 * carried to the browser and drawn nowhere, in the commit whose whole
 * purpose was to fix a coverage-reporting gap.
 *
 * The count alone is not a statement: an older baseline reads 9 and a newer
 * one 10, and nothing says the first covers less than the network does now.
 * A device onboarded after the tag has no golden at it, so re-applying
 * leaves that device untouched -- correct, and not what "restore the
 * network" sounds like.
 */
/* WHICH CLAIM a baseline makes (register E7): "configured" (every device's
   config captured, the only claim a baseline without an operational snapshot
   can make) or "configured and working" (every protocol each device's intent
   declares was up, read at the same moment). The weaker kind is drawn as
   that, never implying the stronger. */
function _gBaselineClaim(b) {
  const working = b.claim === 'configured and working';
  return `<span class="badge ${working ? 'bg-success' : 'bg-secondary-subtle text-secondary-emphasis'}"
      data-baseline-claim="${working ? 'working' : 'configured'}"
      title="${_gEsc(b.claim_detail || '')}">${_gEsc(b.claim || 'configured')}</span>`;
}

function _gBaselineCoverage(b) {
  const count = b.device_count;
  const total = b.inventory_size;
  const missing = b.missing_devices || [];
  if (!b.partial) {
    return `<span class="badge bg-secondary-subtle text-secondary-emphasis">
      ${count} device(s)</span>`;
  }
  const names = missing.slice(0, 4).join(', ')
              + (missing.length > 4 ? `, +${missing.length - 4} more` : '');
  return `<span class="badge bg-warning-subtle text-warning-emphasis"
      title="This baseline predates ${_gEsc(names)}. Re-applying it leaves ${missing.length > 1 ? 'those devices' : 'that device'} exactly as ${missing.length > 1 ? 'they are' : 'it is'}.">
      ${count} of ${total} &mdash; partial</span>
    <div class="small text-muted mt-1">predates ${_gEsc(names)}</div>`;
}

/* A baseline can be stale in two directions. The usual one is being behind.
   The other is that it names credentials the fleet has rotated away from —
   re-applying it would re-publish a secret that exists in history precisely
   because rotation was meant to kill it. The restore refuses such a device at
   plan time (its credential guard, C75, and validate_restored_intent()); this
   says so before the click. */
function _gCredWarning(b) {
  const stale  = b.credential_stale || [];
  const silent = b.credential_silent || [];
  const none   = b.no_intent || [];
  if (stale.length) {
    // `silent` is the set the restore would NOT refuse. Since C75 the
    // restore refuses any rewrite of a credential a device holds, so what is
    // left is an account the baseline has and the device lacks: it would be
    // ADDED back. Not a lockout, and not nothing.
    const worst = silent.length
      ? `<div class="small text-danger">would add back an account on: ${silent.map(_gEsc).join(', ')}</div>`
      : '';
    return `<span class="badge bg-danger-subtle text-danger-emphasis"
             title="These devices' username lines at this baseline differ from the ones they have now. Re-applying would change their credentials back.">
             predates credentials: ${stale.map(_gEsc).join(', ')}</span>${worst}`;
  }
  if (none.length) {
    return `<span class="badge bg-secondary-subtle text-secondary-emphasis"
             title="No golden at this ref for these devices — not the same as being safe.">
             no golden: ${none.map(_gEsc).join(', ')}</span>`;
  }
  return '<span class="badge bg-success-subtle text-success-emphasis">credentials current</span>';
}

/* Re-apply a baseline: SCOPE FIRST (7.1 step 5, C80), then the explicit
   acknowledgement for any chosen device whose credentials the fleet has
   rotated away from, then the guarded preview.

   The scope starts EMPTY. It used to be the whole fleet by default, so
   restoring one device from a baseline needed the browser console, and "the
   whole fleet" was inherited rather than chosen. Now it is a box ticked.

   The acknowledgement names only the CHOSEN devices. The restore path
   refuses a rewritten credential at plan time anyway (C75); this is so the
   operator knows BEFORE starting, rather than meeting a refusal mid-operation.

   Deliberately not folded into previewBaselineRestore(): its second parameter
   is `unOnboard`, and passing anything else there would be read as a list of
   devices to un-onboard. */
window._gBaselineCache = [];
window.confirmBaselineRestore = async function (tag) {
  const b = (window._gBaselineCache || []).find(x => x.tag === tag) || {tag};
  const scope = await chooseBaselineScope(b);
  if (!scope) return;
  const inScope = h => scope.devices === null || scope.devices.includes(h);
  const stale   = (b.credential_stale || []).filter(inScope);
  const silent  = (b.credential_silent || []).filter(inScope);
  // Refused by either guard: the intent check or the credential guard (C75).
  const refused = [...new Set([...(b.credential_refused || []),
                               ...(b.credential_guarded || [])])].filter(inScope).sort();
  if (stale.length) {
    let msg = `${tag} predates the credentials now on: ${stale.join(', ')}.\n\n`;
    if (silent.length) {
      // The dangerous case, stated as a consequence rather than a category.
      msg += `WOULD APPLY to: ${silent.join(', ')}\n` +
             `No credential those devices hold is rewritten (the restore ` +
             `refuses that), but an account this baseline has and the device ` +
             `no longer does would be ADDED back. If it was removed on ` +
             `purpose, do not re-apply.\n\n`;
    }
    if (refused.length) {
      msg += `Refused at plan time (safe): ${refused.join(', ')}\n` +
             `Re-applying would rewrite a credential they hold, so the preview ` +
             `blocks them and nothing is sent to them.\n\n`;
    }
    msg += `Type the word APPLY in the next prompt to continue to the preview.`;
    if (!confirm(msg)) return;
    const typed = prompt(`Re-apply ${tag}? Type APPLY to continue.`);
    if ((typed || '').trim() !== 'APPLY') return;
  }
  previewBaselineRestore(tag, null, {devices: scope.devices});
};
