/* Phase 2, from the pending banner. Both actions live here because the
   banner renders them and the wizard owns the onboarding vocabulary. */
/* `listName` is passed IN, not read from the wizard's select.
   Both of these read `#obList` — the wizard's own control, which is empty
   until `openOnboardWizard()` populates it. From the pending banner the
   modal has never been opened, so both sent `list_name: ''` and every
   action the banner offers was refused. The banner knows the list: it came
   back in the `/onboard/pending` response that drew the row.
   `carried, never derived`, failing in the direction the rule is FOR — the
   value in hand, dropped on the way to the call. */
/* VERIFY IS A PREVIEW AND A CONFIRM (P.9 step c, the operator's decision 1):
   phase 2 sends a program (the read-write community removal and the network's
   monitoring profile), so it is read before it is sent. The preview reaches and
   reads the device; the confirm sends its fingerprint back, and phase 2 sends
   nothing at all if the device or the profile moved since. */
async function onboardVerify(hostname, listName) {
  const list = listName || (document.getElementById('obList') || {}).value || '';
  const el = document.createElement('div');
  el.className = 'modal fade';
  el.tabIndex = -1;
  el.innerHTML =
    '<div class="modal-dialog modal-xl modal-dialog-scrollable"><div class="modal-content">'
    + '<div class="modal-header"><h5 class="modal-title"></h5>'
    + '<button type="button" class="btn-close" data-bs-dismiss="modal"></button></div>'
    + '<div class="modal-body"><div data-verify-body>Reaching and reading the device…</div></div>'
    + '<div class="modal-footer">'
    + '<button type="button" class="btn btn-outline-secondary" data-bs-dismiss="modal">Close</button>'
    + '<button type="button" class="btn btn-primary" data-verify-confirm disabled>Preview first</button>'
    + '</div></div></div>';
  el.querySelector('.modal-title').textContent = 'Verify ' + hostname;
  el.addEventListener('hidden.bs.modal', function () { el.remove(); });
  document.body.appendChild(el);
  new bootstrap.Modal(el).show();
  const body = el.querySelector('[data-verify-body]');
  const btn = el.querySelector('[data-verify-confirm]');
  let preview = null;
  try {
    const r = await fetch('/onboard/verify/' + encodeURIComponent(hostname) + '/preview', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({list_name: list})});
    const d = await r.json();
    if (!d.ok) {
      body.innerHTML = onboardVerifyRefusalHtml(d);
      return;
    }
    preview = d.preview;
    body.innerHTML = previewConfirmHtml(preview, {});
    const s = previewConfirmButton(preview, 1, 'Verify ' + hostname + ': refused (see the gates)');
    btn.disabled = s.disabled;
    btn.textContent = s.text;
  } catch (e) {
    body.textContent = 'The preview failed before an answer came back: ' + e.message;
    return;
  }
  btn.addEventListener('click', async function () {
    const t = ((preview.what || {}).targets || [])[0] || {};
    const data = t.select_data || {};
    btn.disabled = true;
    btn.textContent = 'Verifying…';
    await onboardVerifyConfirm(hostname, data.list || list, data.fingerprint);
    bootstrap.Modal.getInstance(el).hide();
  });
}

/* The confirm: phase 2 with the preview's fingerprint, its result drawn and
   LEFT on screen (M4). */
async function onboardVerifyConfirm(hostname, list, fingerprint) {
  inFlightBusy(true);          // phase two runs for minutes: the panel says what runs (C99)
  let d = null;
  try {
    const r = await fetch('/onboard/verify/' + encodeURIComponent(hostname), {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({list_name: list, fingerprint: fingerprint})});
    d = await r.json();
  } catch (e) { showToast('Verify failed: ' + e, 'danger'); }
  finally { inFlightBusy(false); }
  onboardShowRunResult(hostname, d, list);
}

/* A preview that could not be made: the reason, and the causes worth checking
   when the device did not answer (verify_device's own, most likely first). PURE. */
function onboardVerifyRefusalHtml(d) {
  const esc = s => String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  const causes = (d && d.causes) || [];
  return '<div class="alert alert-danger" data-verify-refused>'
    + esc((d && d.error) || 'The preview could not be made: no reason given') + '</div>'
    + (causes.length ? '<ul class="small">' + causes.map(c =>
        '<li>' + esc(c.cause || '') + (c.why ? ': ' + esc(c.why) : '')
        + (c.command ? ' <code>' + esc(c.command) + '</code>' : '') + '</li>').join('') + '</ul>' : '');
}

/* THE RESULT, drawn by the component (7.1) from the row the route recorded,
   and LEFT on screen until the operator goes back to the list. M4: the old
   failure panel drew the reason and the next line reloaded the same element,
   so it flashed past unread. A success is left too: the row it came from is
   gone (promoted or abandoned), and the pending banner's "finished recently"
   is where it is read again. A response with no result (a refusal before the
   run, a network failure) is a toast with its reason, never a blank. */
function onboardShowRunResult(hostname, d, listName) {
  const host = document.getElementById('onboardPendingBanner');
  if (!d || !d.result) {
    showToast((d && (d.error || d.reason)) || `${hostname}: no result came back`, 'danger');
    loadOnboardPending(listName);
    return;
  }
  const esc = s => String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  showToast(d.result.happened.summary, previewConfirmResultLevel(d.result));
  if (!host) { loadOnboardPending(listName); return; }
  host.innerHTML = `<div class="border rounded p-2 mb-2" data-onboard-run>`
    + previewConfirmResultHtml(d.result, {})
    + `<button class="btn btn-sm btn-outline-secondary py-0 px-1 mt-2"
        onclick="loadOnboardPending('${esc(listName || '')}')">Back to the pending list</button></div>`;
}

async function onboardAbandon(hostname, listName) {
  if (!confirm(`Abandon ${hostname}? This removes its NetBox objects, its `
             + `committed intent and its credential, then gives the name back.`)) {
    return;
  }
  const list = listName || (document.getElementById('obList') || {}).value || '';
  let d = null;
  try {
    const r = await fetch('/onboard/abandon/' + encodeURIComponent(hostname), {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({list_name: list})});
    d = await r.json();
  } catch (e) { showToast('Abandon failed: ' + e, 'danger'); }
  onboardShowRunResult(hostname, d, list);
}
