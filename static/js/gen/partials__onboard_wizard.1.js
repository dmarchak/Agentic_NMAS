/* PURE. Takes a plan summary, returns HTML. No DOM, no network — so the
   test can execute this exact function against a plan with blocking reasons
   and assert what an operator would see. */
/* The review is drawn by the preview component (7.1): `/onboard/plan` carries
   `preview`, built by `preview_confirm.onboard_preview()`. It replaced
   `onboardReviewHtml`, a second renderer of the same six parts. */

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
  role:              'obRole',
  mgmt_ip:           'obMgmtIp',
  mgmt_mask:         'obMgmtMask',
  manager_interface: 'obMgrIntf',
  manager_gateway:   'obMgrGw',
  mgmt_interface:    'obMgmtIntf',
  /* Phase 2. ORDINARY ENTRIES, so they re-validate like everything else --
     the binding list is what the change listeners iterate, and a field read
     and sent but watched by nothing is what left "no network mask" on screen
     while the payload was already correct. */
  address_source:    'obAddrSource',
  mgmt_mac:          'obMgmtMac',
};

/* The MAC matters only for DHCP, and a field that is always visible invites
   filling it in for a static device where nothing reads it. Revealed rather
   than disabled, so the form does not carry a control whose purpose is
   unexplained. */
/* DRIVEN BY THE SELECT'S CURRENT VALUE, and called on OPEN as well as on
   change. It only ran on `change`, and a select's initial value is set without
   firing one -- so a browser that remembered "dhcp" from a previous session
   showed DHCP selected beside a visible Management IP and Mask and no MAC
   field. **It therefore only appeared on the SECOND use**, which is why
   building and testing the fields did not reveal it.
   The form then SAID dhcp and COLLECTED static: two sources disagreeing about
   one fact. `onboardFormPayload()` reads every field unconditionally, so the
   select won and the typed address rode along -- see `build_plan`, which now
   drops it. */
function onboardAddressSourceChanged() {
  const source = document.getElementById('obAddrSource');
  const value = (source && source.value) || 'static';
  const dhcp = value === 'dhcp', ztp = value === 'ztp';
  const row = document.getElementById('obMacRow');
  const staticRows = document.querySelectorAll('.ob-static-only');
  const addressRows = document.querySelectorAll('.ob-address');
  const show = function (el, on) { if (el) el.style.display = on ? '' : 'none'; };
  const clear = function (id) {
    const el = document.getElementById(id);
    if (el) el.value = '';
  };
  /* THREE SOURCES, three shapes. static: address and mask, no MAC. dhcp: a
     MAC only, since the address is a reservation somebody else made. ztp: a
     MAC AND the address the tool will reserve, and no mask, because the
     device takes the subnet's from Kea. */
  show(row, dhcp || ztp);
  staticRows.forEach(function (el) { show(el, !dhcp && !ztp); });
  addressRows.forEach(function (el) { show(el, !dhcp); });
  show(document.getElementById('obMacHelpDhcp'), dhcp);
  show(document.getElementById('obMacHelpZtp'), ztp);
  const label = document.getElementById('obMgmtIpLabel');
  if (label) label.textContent = ztp ? 'Address to reserve' : 'Management IP';
  /* CLEARED, not just hidden. A hidden field still has a value, and browser
     autofill puts one there -- so hiding alone leaves the payload carrying an
     address the operator cannot see and did not choose for this device. */
  if (dhcp) { clear('obMgmtIp'); clear('obMgmtMask'); }
  if (ztp) { clear('obMgmtMask'); }
  if (!dhcp && !ztp) { clear('obMgmtMac'); }
}

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
    host.innerHTML = previewConfirmHtml(d.preview, {});
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
    // THE RESULT, drawn by the component in place of the review (7.1, C86).
    // The toast said "Device onboarded." after phase 1, which leaves the
    // device PENDING: the outcome of phase 2, claimed before it happened.
    const host = document.getElementById('onboardReview');
    if (d.result && host) {
      host.innerHTML = previewConfirmResultHtml(d.result, {});
      const btn = document.getElementById('onboardCreateBtn');
      if (btn) btn.disabled = true;
      const note = document.getElementById('onboardFooterNote');
      if (note) note.textContent = d.ok
        ? 'Created. The device is pending until Verify reaches it.'
        : 'Nothing more was written. Fix the reason above, or Abandon what exists.';
      showToast(d.result.happened.summary, previewConfirmResultLevel(d.result));
    } else {
      showToast(d.error || 'Create failed', 'danger');
    }
    // The pending row is where this device's state is read again later.
    if (typeof loadOnboardPending === 'function') loadOnboardPending(onboardFormPayload().list_name);
  } catch (e) { showToast('Create failed: ' + e, 'danger'); }
}

/* The platform select's options, and each blocked platform's REASON drawn
   beside it (C222, C109's rule): the reason rode in the option's `title`,
   which a disabled option does not show, so the screen said only "blocked".
   PURE: {options, blocked} as HTML, every value escaped. */
function onboardPlatformOptions(platforms) {
  const esc = s => String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  const options = platforms.map(p =>
    `<option value="${esc(p.platform)}"${p.blocked ? ' disabled' : ''}>`
    + `${esc(p.platform)}${p.blocked ? ' (blocked: see below)' : ''}</option>`).join('');
  const blocked = platforms.filter(p => p.blocked).map(p =>
    `<div data-platform-blocked="${esc(p.platform)}"><strong>${esc(p.platform)}</strong> `
    + `is blocked: ${esc(p.reason || 'no reason was given (a defect: a refusal names its cause)')}</div>`
  ).join('');
  return {options, blocked};
}

async function openOnboardWizard() {
  /* ON OPEN, from the select's CURRENT value. A select's initial value is set
     without firing `change`, so a remembered "dhcp" left the form saying one
     thing and collecting another -- visible on the SECOND use and never the
     first. Reading the value rather than assuming it starts at the default is
     the whole fix. */
  onboardAddressSourceChanged();
  const sel = document.getElementById('obPlatform');
  if (sel && !sel.options.length) {
    try {
      const d = await (await fetch('/onboard/platforms')).json();
      /* A blocked platform is LISTED AND DISABLED, not omitted: an absent
         option teaches the operator the tool does not support their device,
         which is a different and wrong lesson. */
      const built = onboardPlatformOptions(d.platforms || []);
      sel.innerHTML = built.options;
      const why = document.getElementById('obPlatformBlocked');
      if (why) why.innerHTML = built.blocked;
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
