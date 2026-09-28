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
async function onboardVerify(hostname, listName) {
  const list = listName || (document.getElementById('obList') || {}).value || '';
  inFlightBusy(true);          // phase two runs for minutes: the panel says what runs (C99)
  let d = null;
  try {
    const r = await fetch('/onboard/verify/' + encodeURIComponent(hostname), {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({list_name: list})});
    d = await r.json();
  } catch (e) { showToast('Verify failed: ' + e, 'danger'); }
  finally { inFlightBusy(false); }
  onboardShowRunResult(hostname, d, list);
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
