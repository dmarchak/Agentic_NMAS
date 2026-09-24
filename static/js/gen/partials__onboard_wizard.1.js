/* PURE. Takes a plan summary, returns HTML. No DOM, no network — so the
   test can execute this exact function against a plan with blocking reasons
   and assert what an operator would see. */
function onboardReviewHtml(plan, bootstrapConfig) {
  if (!plan) return '';
  const esc = s => String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const reasons = plan.blocking_reasons || [];

  /* EVERY reason, not the first. `blocking_reasons` collects them all (4C.1)
     precisely so the operator fixes them in one pass; showing one would put
     that property back in the plan object where nobody can see it. */
  const blockers = reasons.length ? `
    <div class="alert alert-danger py-2 px-3 mb-2">
      <div class="fw-semibold mb-1">
        ${reasons.length} reason${reasons.length === 1 ? '' : 's'} this device
        cannot be onboarded — all of them, so they can be fixed in one pass:
      </div>
      <ul class="mb-0">${reasons.map(r => `<li>${esc(r)}</li>`).join('')}</ul>
    </div>` : '';

  /* ADVISORIES ARE NOT REFUSALS, and are drawn so they cannot be mistaken
     for one: different colour, different heading, and BELOW the blockers so
     a real refusal is never pushed off the top of the panel by a note.
     Rendered from their own key -- concatenating the two lists would make
     an advisory look like a refusal, and one day the reverse. */
  const notes = plan.advisories || [];
  const advisories = notes.length ? `
    <div class="alert alert-warning py-2 px-3 mb-2">
      <div class="fw-semibold mb-1">Worth knowing — this does not block
        onboarding:</div>
      <ul class="mb-0">${notes.map(n => `<li>${esc(n)}</li>`).join('')}</ul>
    </div>` : '';

  const rows = [
    ['Name', plan.hostname], ['Platform', plan.platform],
    ['List', `${plan.list} (${plan.source_kind})`],
    ['Management IP', plan.mgmt_mask
        ? `${plan.mgmt_ip} ${plan.mgmt_mask} on ${plan.manager_interface || '(no interface)'}`
        : plan.mgmt_ip],
    ['Gateway', plan.manager_gateway || 'none \u2014 NMAS is on this subnet'],
    ['Template', plan.template || '(none bound)'],
    ['Credential source', plan.cred_source || '(not resolved)'],
    ['NetBox', plan.netbox_note || 'created in phase 2, from the first capture'],
    ['Adds to inventory', plan.inventory_note || 'after it answers'],
  ];

  return `
    ${blockers}
    ${advisories}
    <div class="alert alert-secondary py-2 px-3 mb-2">
      <strong>Nothing has been created yet.</strong> This is what will be.
      Every step before Create is a read — you can go Back from here without
      undoing anything.
    </div>
    <div class="table-responsive">
      <table class="table table-sm mb-2"><tbody>
        ${rows.map(([k, v]) => `<tr><td class="text-muted" style="width:12em">${esc(k)}</td>
          <td>${esc(v)}</td></tr>`).join('')}
      </tbody></table>
    </div>
    <div class="mb-1 fw-semibold">Startup config this device will boot with</div>
    <pre class="border rounded p-2 small mb-0" style="max-height:18em;overflow:auto">${esc(bootstrapConfig || '')}</pre>
    <div class="form-text">The credential shown here is a placeholder. The real
      one-time bootstrap credential is generated when you press Create and is
      never sent to the browser.</div>`;
}

/* Also pure, and deliberately separate from the HTML: the button's state is
   a decision about the plan, not a detail of how the plan is drawn. */
function onboardCanCreate(plan) {
  return !!(plan && plan.onboardable === true);
}

// The form, read ONCE. Both /onboard/plan and /onboard/create send this.
//
// `create` used to send `'{}'`, so the confirm rebuilt a plan with no
// hostname and no address and could only ever answer 409. It rebuilds
// deliberately -- the state can change between the review and the confirm --
// but a rebuild from a DIFFERENT payload is not a recomputation of the same
// plan, it is a different plan that happens to be empty.
//
// Mirrors `_plan_args()` on the server, for the reason that one exists:
// two readers of one form are two forms.
/* ONE list of fields. It is read by the payload builder AND by the loop that
   binds re-validation listeners, because keeping those two in step by hand
   failed immediately: 4C.8 added mask, management interface and gateway to
   the form and to the payload, and left the listener array as the original
   four ids. The fields were SENT correctly and nothing asked for them to be
   re-sent, so an operator filling in a mask watched the "no network mask"
   reason sit there unchanged -- a wizard that looks broken while working.

   Third instance of one shape in this feature: _plan_args() on the server,
   onboardFormPayload() here, and this binding list. The first two were
   merged and the third was left, which is what made it the one that broke. */
const ONBOARD_FIELDS = {
  /* First, because it decides what every other field MEANS: the name
     collision is checked in this list's manifest, the credential comes from
     this list's resolver, and the NetBox objects are recorded against this
     list's slug. */
  list_name:         'obList',
  hostname:          'obHostname',
  platform:          'obPlatform',
  mgmt_ip:           'obMgmtIp',
  mgmt_mask:         'obMgmtMask',
  manager_interface: 'obMgrIntf',
  manager_gateway:   'obMgrGw',
  mgmt_interface:    'obMgmtIntf',
};

function onboardFormPayload() {
  const out = {};
  Object.keys(ONBOARD_FIELDS).forEach(function (key) {
    const el = document.getElementById(ONBOARD_FIELDS[key]);
    out[key] = (el && el.value) || '';
  });
  return out;
}

async function onboardRefresh() {
  const host = document.getElementById('onboardReview');
  const btn  = document.getElementById('onboardCreateBtn');
  const note = document.getElementById('onboardFooterNote');
  if (!host) return;
  try {
    const r = await fetch('/onboard/plan', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(onboardFormPayload()),
    });
    const d = await r.json();
    if (!d.ok) { host.innerHTML = `<div class="alert alert-danger py-2 px-3">${d.error}</div>`; return; }
    host.innerHTML = onboardReviewHtml(d.plan, d.bootstrap_config);
    if (btn) btn.disabled = !onboardCanCreate(d.plan);
    if (note) {
      note.textContent = onboardCanCreate(d.plan)
        ? 'Create is the only step that writes anything.'
        : `Create is disabled: ${(d.plan.blocking_reasons || []).length} blocking reason(s) above.`;
    }
  } catch (e) {
    host.innerHTML = `<div class="alert alert-danger py-2 px-3">Could not build a plan: ${e}</div>`;
  }
}

async function onboardCreate() {
  try {
    const r = await fetch('/onboard/create', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(onboardFormPayload())});
    const d = await r.json();
    showToast(d.ok ? 'Device onboarded.' : (d.error || 'Create failed'),
              d.ok ? 'success' : 'danger');
  } catch (e) { showToast('Create failed: ' + e, 'danger'); }
}

async function openOnboardWizard() {
  const sel = document.getElementById('obPlatform');
  if (sel && !sel.options.length) {
    try {
      const d = await (await fetch('/onboard/platforms')).json();
      /* A blocked platform is LISTED AND DISABLED, not omitted: an absent
         option teaches the operator the tool does not support their device,
         which is a different and wrong lesson. */
      sel.innerHTML = (d.platforms || []).map(p =>
        `<option value="${p.platform}" ${p.blocked ? 'disabled' : ''}
                 title="${p.reason || ''}">${p.platform}${p.blocked ? ' — blocked' : ''}</option>`
      ).join('');
    } catch (_) { /* the plan call will report it */ }
  }
  const lsel = document.getElementById('obList');
  if (lsel) {
    try {
      const ld = await (await fetch('/onboard/lists')).json();
      /* Repopulated on every open, not cached: a list created since the last
         open would otherwise be unselectable, and the operator's only way
         out would be to reload the page. */
      lsel.innerHTML = (ld.lists || []).map(l =>
        `<option value="${l.name}" ${l.is_current ? 'selected' : ''}>${l.name} (${l.device_count})</option>`
      ).join('');
    } catch (_) { /* the plan call will report it */ }
  }
  /* Every field the payload reads, so fixing a reason clears it. */
  Object.keys(ONBOARD_FIELDS).forEach(function (key) {
    const el = document.getElementById(ONBOARD_FIELDS[key]);
    if (el && !el._obBound) { el._obBound = true; el.addEventListener('input', onboardRefresh);
                              el.addEventListener('change', onboardRefresh); }
  });
  new bootstrap.Modal(document.getElementById('onboardWizardModal')).show();
  onboardRefresh();
}
