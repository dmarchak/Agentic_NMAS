/* Pure, so it can be executed in a test against every shape it must draw:
   error, empty, in_flight, overdue, stale. */
function pendingAgeText(seconds) {
  const s = Math.max(0, Number(seconds) || 0);
  if (s < 90) { return 'just now'; }
  if (s < 5400) { return Math.round(s / 60) + ' minutes'; }
  if (s < 172800) { return Math.round(s / 3600) + ' hours'; }
  return Math.round(s / 86400) + ' days';
}

function pendingBannerHtml(data) {
  const esc = s => String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

  /* FIRST, and deliberately: a failed read must never fall through to the
     empty-list branch below, which says "nothing is pending" — a sentence
     that would be reassuring and false. */
  if (!data || data.ok !== true) {
    const why = esc((data && data.error) || 'the request did not complete');
    return `<div class="alert alert-danger py-2 px-3 mb-0">
      <strong>Pending devices could not be read.</strong>
      This is <em>not</em> the same as none being pending — a device may be
      waiting and invisible. ${why}</div>`;
  }

  const rows = data.pending || [];
  if (!rows.length) { return ''; }

  const worst = rows.some(r => r.state === 'stale') ? 'stale'
              : rows.some(r => r.state === 'overdue') ? 'overdue' : 'in_flight';
  const tone = worst === 'in_flight' ? 'alert-secondary' : 'alert-warning';

  const body = rows.map(r => {
    const age = pendingAgeText(r.age_seconds);
    const flag = r.state === 'stale'
      ? `<span class="badge bg-danger ms-1">stale</span>`
      : r.state === 'overdue'
      ? `<span class="badge bg-warning text-dark ms-1">overdue</span>` : '';
    /* The exit, inline, on EVERY row.
       It was offered only at `stale`, on the reasoning that a destructive
       action beside a five-minute-old device invites use. That was wrong in
       the direction that matters: **the operator who has just onboarded the
       wrong thing is the one who needs abandon**, and the window in which
       they are certain it was a mistake is minutes, not a week. Gating it at
       seven days left `curl` or waiting as the only recovery for a fresh
       mistake -- which makes the flow's own recovery path unreachable
       exactly when it is most useful.
       The confirm in `onboardAbandon()` is what stops a misclick; an age
       gate never was. */
    const abandon = ` <button class="btn btn-sm btn-outline-danger py-0 px-1"
            onclick="onboardAbandon('${esc(r.name)}', '${esc(data.list)}')">Abandon</button>`;
    /* AN EMPTY ADDRESS IS HONEST AND USELESS. A reader cannot tell a device
       with no address from one whose address is simply not known YET, and for
       a DHCP device the second is the normal state until it boots. So the row
       says what is expected and from where, rather than leaving a blank. */
    const where = r.address_source === 'dhcp'
      ? (r.reserved_address
          ? `awaiting DHCP (Kea reservation \u2192 ${esc(r.reserved_address)})`
          : `awaiting DHCP (reservation for ${esc(r.mgmt_mac || 'an unrecorded MAC')})`)
      : (r.mgmt_ip ? `<code>${esc(r.mgmt_ip)}</code>` : 'no address recorded');
    return `<li><code>${esc(r.name)}</code> at ${where}
      — pending ${esc(age)}${flag}
      <button class="btn btn-sm btn-outline-secondary py-0 px-1"
        onclick="onboardBootstrap('${esc(r.name)}', '${esc(data.list)}')"
        title="Re-rendered from the staged credential; gone once it is rotated"
        >Config</button>
      <button class="btn btn-sm btn-outline-primary py-0 px-1"
        onclick="onboardVerify('${esc(r.name)}', '${esc(data.list)}')">Verify now</button>${abandon}</li>`;
  }).join('');

  return `<div class="alert ${tone} py-2 px-3 mb-0">
    <div class="fw-semibold mb-1">${rows.length} device(s) onboarded and not
      yet reached</div>
    <div class="small mb-1"><strong>Config</strong> re-renders the file the
      node boots with, from the staged credential — it is available only
      until that credential is rotated, because after rotation the device
      holds a different one and the old file would not log in.</div>
    <div class="small mb-1">Their management interface is
      <strong>unverified</strong> until the tool reaches them — it was
      checked for spelling, never against the device. They are deliberately
      not in the inventory until then.</div>
    <ul class="mb-0 small">${body}</ul></div>`;
}

/* THE ENTRY POINT.
   `loadOnboardPending` had exactly two callers, both buttons INSIDE the
   banner it draws -- so the banner could only appear after you had used a
   control that only exists once it has appeared. The div sat in the DOM,
   empty, for ever, while the manifest held a pending device and the
   Template library listed it.

   That is the state `pending` was built to prevent, and the banner's own
   design test ("pending for ever and nobody notices") was defeated before it
   ever ran. Not client-side suppression like the agent panel, and not two
   readers disagreeing: a renderer with no caller.

   `test_onboard_phase2.py` could not see it -- it executes
   `pendingBannerHtml` directly, which tests the render and not the wiring.
   The same seam as `/onboard/create` sending `body: '{}'`. */
document.addEventListener('DOMContentLoaded', () => {
  /* The page's own notion of the active list — `#deviceListSelect` is what
     every other per-list control reads. Empty is fine: the endpoint falls
     back to the active list for a READ. */
  const run = () => loadOnboardPending(
    (document.getElementById('deviceListSelect') || {}).value || '');
  run();
  /* And again when the list changes, because pending is per list and a
     banner showing another list's devices is worse than none. */
  const sel = document.getElementById('deviceListSelect');
  if (sel) { sel.addEventListener('change', () => setTimeout(run, 250)); }
  const devicesTab = document.getElementById('devices-tab');
  if (devicesTab) { devicesTab.addEventListener('shown.bs.tab', run); }
});

async function loadOnboardPending(listName) {
  const host = document.getElementById('onboardPendingBanner');
  if (!host) { return; }
  let data;
  try {
    const r = await fetch('/onboard/pending?list_name=' +
                          encodeURIComponent(listName || ''));
    data = await r.json();
  } catch (e) {
    data = {ok: false, error: String(e)};
  }
  host.innerHTML = pendingBannerHtml(data);
}
