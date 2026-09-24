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
  try {
    const r = await fetch('/onboard/verify/' + encodeURIComponent(hostname), {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({list_name: list})});
    const d = await r.json();
    if (d.ok) {
      showToast(`${hostname} answered and is now in the inventory.`, 'success');
    } else {
      /* The diagnosis, not "cannot reach". Rendered into the banner area so
         the operator can act without leaving the screen. */
      const host = document.getElementById('onboardPendingBanner');
      if (host) { host.innerHTML = verifyFailureHtml(hostname, d); }
    }
  } catch (e) { showToast('Verify failed: ' + e, 'danger'); }
  loadOnboardPending(list);
}

function verifyFailureHtml(hostname, d) {
  const esc = s => String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const v = (d && d.verify) || {};
  const causes = (v.causes || []).map((c, i) => `
    <li class="mb-1"><strong>${esc(c.cause)}</strong><br>
      <span class="text-muted">${esc(c.why)}</span><br>
      <span class="small">${esc(c.where)}</span>
      <code>${esc(c.command)}</code></li>`).join('');
  const rec = v.recovery || {};
  const recovery = rec.available
    ? `<div class="mt-2 small"><strong>Locked out?</strong>
         ${esc(rec.note)}<br><code>${esc(rec.command)}</code></div>`
    : `<div class="mt-2 small text-muted">${esc(rec.note || '')}</div>`;
  /* "did not answer" — NOT "wrong interface". Reaching the device proves
     the interface was right; failing to reach it proves nothing about why,
     so the causes below are possibilities in the order they are worth
     checking. */
  return `<div class="alert alert-warning py-2 px-3 mb-0">
    <div class="fw-semibold mb-1">${esc(hostname)} did not answer
      — nothing about it has changed.</div>
    <div class="small mb-1">${esc(v.error || '')}</div>
    <div class="small">Worth checking, in this order:</div>
    <ol class="small mb-0">${causes}</ol>${recovery}</div>`;
}

async function onboardAbandon(hostname, listName) {
  if (!confirm(`Abandon ${hostname}? This removes its NetBox objects, its `
             + `committed intent and its credential, then gives the name back.`)) {
    return;
  }
  const list = listName || (document.getElementById('obList') || {}).value || '';
  try {
    const r = await fetch('/onboard/abandon/' + encodeURIComponent(hostname), {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({list_name: list})});
    const d = await r.json();
    showToast(d.ok ? `${hostname} abandoned; the name is free.`
                   : (d.error || 'Abandon did not finish'),
              d.ok ? 'success' : 'danger');
  } catch (e) { showToast('Abandon failed: ' + e, 'danger'); }
  loadOnboardPending(list);
}
