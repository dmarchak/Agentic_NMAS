/* ── Baselines + migration ───────────────────────────────────────────────── */
function _gLastPush(p) {
  // WHAT was published, not only who clicked.
  //
  // The first version showed the timestamp and the actor, and rendered `kind`
  // only when it was 'tags' -- so an ordinary commit push displayed exactly
  // "who last clicked", which is the reading that made this field misleading
  // before it recorded anything at all. Recording a fact and not showing it
  // leaves the card saying the same wrong thing.
  if (!p) return 'never';

  const how = p.by === 'auto-push'
    ? '<span class="badge bg-secondary-subtle text-secondary-emphasis">auto</span>'
    : '<span class="badge bg-info-subtle text-info-emphasis">manual</span>';
  const who = p.by ? ' by <code>' + _gEsc(p.by) + '</code>' : '';

  let what;
  if (p.kind === 'tags') {
    what = 'tag only';
  } else if (p.commit) {
    what = 'commit <code>' + _gEsc(String(p.commit).slice(0, 8)) + '</code>';
  } else {
    what = _gEsc(p.kind || 'unknown');
  }

  const tags = (p.tags || []).length
    ? ' + <code>' + _gEsc((p.tags || []).join(', ')) + '</code>'
    : '';

  return _gEsc(p.at) + ' ' + how + who + ' — ' + what + tags;
}

async function loadGoldenRepoPanel() {
  const host = document.getElementById('goldenRepoPanel');
  if (!host || !_gList()) return;
  try {
    // Renames, the legacy store's card and the one-shot migration are no longer here (7.8): a
    // pending rename is committed alone by the next golden save, and the legacy store's
    // retirement condition has held since 2026-09-28.
    const bRes = await fetch('/golden/baselines').then(r => r.json());
    if (!bRes.ok) {
      // A failed read is said, never drawn as an empty table.
      host.innerHTML = '<div class="text-danger small">The baselines could not be read: '
        + _gEsc(bRes.error || 'no reason given') + '</div>';
      return;
    }

    const baselines = bRes.baselines || [];   // all of them: the table collapses, never cuts
    window._gBaselineCache = baselines;

    host.innerHTML = `
      <div class="card border-light-subtle">
        <div class="card-body py-2 px-3">
          <h6 class="text-primary fw-semibold mb-2">Baselines
            <span class="text-muted fw-normal small ms-1">(stored network-wide configuration)</span>
          </h6>
          ${_gBaselinesHtml(baselines, bRes.last_decision)}
        </div>
      </div>`;
  } catch (e) { console.error('loadGoldenRepoPanel', e); }
}

// `unOnboard` is empty on the first pass. If the operator opts in for devices
// this ref predates, we PREVIEW AGAIN with them included rather than sending
// them straight to apply: they were skipped, so they have no command list and
// no hash, and confirming commands nobody was shown is exactly what the
// confirm hash exists to prevent.
// `from` carries an approval-queue handoff: the devices to scope to, the id to
// close on success, and the diff the agent saw. That diff is CONTEXT ONLY — it
// is displayed beside the freshly computed program and is never sent.
async function previewBaselineRestore(tag, unOnboard, from) {
  unOnboard = unOnboard || [];
  from = from || {};
  try {
    const r = await fetch('/golden/restore/preview', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ref: tag, un_onboard: unOnboard,
                            authorise: from.authorise || {},
                            devices: from.devices || null,
                            advisory_diff: from.advisoryDiff || '',
                            approval_id: from.approvalId || ''}),
    });
    const d = await r.json();
    if (!d.ok) { showToast(d.error, 'danger'); return; }

    const skipped = d.skipped || [];

    // Devices this ref predates. The default outcome is SKIP: removing a
    // device's committed intent un-does a human review, so it is never
    // something the operator gets by pressing the same button.
    const offerable = skipped.filter(s => s.un_onboardable);
    if (offerable.length) {
      const names = offerable.map(s => s.hostname).join(', ');
      if (confirm(
          `${names} — this ref predates their onboarding, so there is no `
          + `committed intent to restore.\n\nThey are SKIPPED by default.\n\n`
          + `Include them anyway AND remove their committed intent? That `
          + `un-does the onboarding review. It is a forward commit, so the `
          + `intent stays recoverable from git history.\n\n`
          + `OK = show me what that would send.  Cancel = leave them skipped.`)) {
        return previewBaselineRestore(tag, offerable.map(s => s.hostname), from);
      }
    }

    // Dangerous lines are authorised per device and per exact line BEFORE the
    // program is shown (P.3 step 4). The choice goes back to the preview, so
    // the command hashes this confirm carries cover it, and run_targets
    // recomputes both at apply. Asked once per preview chain.
    // Both classes that need an authorisation (C140, C79): a dangerous line,
    // and a secret-position line this re-apply would ADD. A device with an
    // unauthorised secret line is not deployable, so that is not the filter.
    const needAuth = (d.devices || []).filter(
      x => (x.dangerous || []).length || (x.secret_readded || []).length);
    if (needAuth.length && !from.authoriseAsked) {
      const chosen = await _authoriseDangerous(needAuth, from.authorise || {});
      if (chosen === null) return;
      return previewBaselineRestore(tag, unOnboard,
        Object.assign({}, from, {authorise: chosen, authoriseAsked: true}));
    }

    // The EXACT program per device, every line (P.3 step 3), now as the six
    // parts of the shared component (7.1). The dialog used to show counts and
    // at most three replace and three residue lines, and never the lines to
    // be added: `commands` was computed, carried to the browser, and drawn
    // nowhere, while the confirm hash covered it.
    if (!(await _confirmRestorePreview(`Re-apply ${tag}`, d, from))) return;

    const confirmations = {}, hashes = {};
    _restoreSelected(d.preview).forEach(t => {
      confirmations[t.name] = t.select_data.hash;
      hashes[t.name] = t.select_data['command-hash'];
    });
    if (!Object.keys(confirmations).length) {
      showToast('Nothing to re-apply — every device is blocked or already matches', 'warning');
      return;
    }

    // The confirm closed the modal: without this, the fifty seconds this
    // takes were silent, and the silence caused a second change (C99).
    inFlightBusy(true);
    let ad;
    try {
      const ar = await fetch('/golden/restore/apply', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ref: tag, confirmations, command_hashes: hashes,
                              un_onboard: unOnboard,
                              authorise: from.authorise || {},
                              approval_id: from.approvalId || ''}),
      });
      ad = await ar.json();
    } finally {
      inFlightBusy(false);
    }
    if (!ad.ok) {
      showToast(`Re-apply failed: ${ad.error || ''}`, 'danger');
    } else {
      // THE RESULT, drawn by the component (7.1 step 2), from the receipt
      // rows the apply wrote. It was a toast (C84): the program sent, its
      // hash against the confirmed one, and what verify checked were
      // carried and drawn nowhere.
      _showRestoreResult(`Re-applied ${tag}`, ad.result);
    }
    loadGoldenRepoPanel();
  } catch (e) { showToast(e.message, 'danger'); }
}

// Per device, per exact line that needs one (dangerous, or a secret line
// this re-apply would ADD): tick to authorise, with your reason (C140). A
// reason is recorded as your statement and never judged; its minimum is
// shape. Resolves {device: [{line, reason}]} (possibly empty), or null on
// Cancel. How often the line was authorised here before is shown with it.
function _authoriseDangerous(devices, current) {
  return new Promise(resolve => {
    const el = document.createElement('div');
    el.className = 'modal fade';
    el.tabIndex = -1;
    el.innerHTML =
      '<div class="modal-dialog modal-lg modal-dialog-scrollable"><div class="modal-content">'
      + '<div class="modal-header"><h5 class="modal-title">Lines in this restore that need an authorisation</h5>'
      + '<button type="button" class="btn-close" data-bs-dismiss="modal"></button></div>'
      + '<div class="modal-body"><p class="small">Each line below is either a dangerous command or '
      + 'a secret the device does not hold, which this restore would ADD (after a rotation the '
      + 'old value lands beside the current one). It is sent only if you authorise that exact '
      + 'line for that device and say why, in a few words: your reason is recorded as yours and '
      + 'never judged. A device with an unauthorised line is refused and nothing is sent to it. '
      + 'The full program is shown next.</p>'
      + '<div data-lines></div></div>'
      + '<div class="modal-footer">'
      + '<button type="button" class="btn btn-outline-secondary" data-bs-dismiss="modal">Cancel</button>'
      + '<button type="button" class="btn btn-warning" data-continue>Continue to the program</button>'
      + '</div></div></div>';
    const box = el.querySelector('[data-lines]');
    devices.forEach(dev => {
      const head = document.createElement('div');
      head.className = 'fw-semibold mt-2';
      head.textContent = dev.device;
      box.appendChild(head);
      const prior = ((dev.prior_authorised || {}).lines) || {};
      const had = {};
      ((current || {})[dev.device] || []).forEach(a => { if (a && a.line) had[a.line] = a.reason || ''; });
      const flagged = (dev.dangerous || []).map(l => [l, 'dangerous'])
        .concat((dev.secret_readded || []).map(l => [l, 'adds a secret the device does not hold']));
      flagged.forEach(([line, kind]) => {
        const row = document.createElement('div');
        row.className = 'mb-2';
        row.dataset.authRow = '';
        const lab = document.createElement('label');
        lab.className = 'd-flex gap-2 align-items-start font-monospace small';
        const cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.className = 'form-check-input mt-0';
        cb.dataset.device = dev.device;
        cb.dataset.line = line;
        cb.checked = Object.prototype.hasOwnProperty.call(had, line);
        const span = document.createElement('span');
        span.style.whiteSpace = 'pre';
        span.textContent = line + '    (' + kind + ')';
        lab.appendChild(cb);
        lab.appendChild(span);
        const reason = document.createElement('input');
        reason.type = 'text';
        reason.className = 'form-control form-control-sm';
        reason.dataset.authReason = '';
        reason.placeholder = 'why this line is deliberate (a few words, recorded as yours)';
        reason.value = had[line] || '';
        row.appendChild(lab);
        row.appendChild(reason);
        const seen = prior[line];
        if (seen) {
          const h = document.createElement('div');
          h.className = 'small text-muted';
          h.dataset.authPrior = '';
          h.textContent = 'authorised on this device ' + seen.count + ' time(s) before; last '
            + seen.last_at + ' by ' + seen.last_actor + ', stated reason: "' + seen.last_reason + '"';
          row.appendChild(h);
        }
        box.appendChild(row);
      });
    });
    let answer = null;
    el.querySelector('[data-continue]').addEventListener('click', () => {
      answer = {};
      el.querySelectorAll('input[type=checkbox]').forEach(cb => {
        if (!cb.checked) return;
        const reason = cb.closest('[data-auth-row]').querySelector('input[data-auth-reason]');
        (answer[cb.dataset.device] = answer[cb.dataset.device] || []).push(
          {line: cb.dataset.line, reason: reason ? reason.value : ''});
      });
      modal.hide();
    });
    el.addEventListener('hidden.bs.modal', () => { el.remove(); resolve(answer); });
    document.body.appendChild(el);
    const modal = new bootstrap.Modal(el);
    modal.show();
  });
}

// The restore preview, drawn by THE preview-then-confirm component (Stage
// 7.1): the six parts come from the server's one builder (`d.preview`) and
// `previewConfirmHtml` draws them, so this path cannot drop a part the
// deploy wizard draws (C27 was this preview never drawing the lines to add;
// C73 its residue without a section). Resolves true on Confirm.
// The agent's diff goes in as TEXT above the component, labelled: context
// only, never what is sent, and never part of what the server built.
function _confirmRestorePreview(title, d, from) {
  from = from || {};
  return new Promise(resolve => {
    const el = document.createElement('div');
    el.className = 'modal fade';
    el.tabIndex = -1;
    el.innerHTML =
      '<div class="modal-dialog modal-xl modal-dialog-scrollable"><div class="modal-content">'
      + '<div class="modal-header"><h5 class="modal-title"></h5>'
      + '<button type="button" class="btn-close" data-bs-dismiss="modal"></button></div>'
      + '<div class="modal-body"><div data-advisory></div><div data-restore-preview></div></div>'
      + '<div class="modal-footer">'
      + '<button type="button" class="btn btn-outline-secondary" data-bs-dismiss="modal">Cancel</button>'
      + '<button type="button" class="btn btn-warning" data-confirm></button>'
      + '</div></div></div>';
    el.querySelector('.modal-title').textContent = title;
    if (from.advisoryDiff) {
      const box = el.querySelector('[data-advisory]');
      const head = document.createElement('div');
      head.className = 'small fw-semibold text-warning-emphasis';
      head.textContent = 'WHAT THE AGENT SAW when the drift was detected '
        + '(context only, NOT what will be sent):';
      const pre = document.createElement('pre');
      pre.className = 'small bg-body-tertiary p-2 rounded';
      pre.textContent = from.advisoryDiff.trim().split('\n').slice(0, 12).join('\n')
        + (from.advisoryNote ? '\n' + from.advisoryNote : '');
      box.appendChild(head);
      box.appendChild(pre);
    }
    // The component escapes every value it draws.
    el.querySelector('[data-restore-preview]').innerHTML = previewConfirmHtml(d.preview, {});
    const ready = _restoreSelected(d.preview).length;
    const state = previewConfirmButton(d.preview, ready, `Re-apply to ${ready} device(s)`);
    const btn = el.querySelector('[data-confirm]');
    btn.disabled = state.disabled;
    btn.textContent = state.text;
    let answer = false;
    btn.addEventListener('click', () => { answer = true; modal.hide(); });
    el.addEventListener('hidden.bs.modal', () => { el.remove(); resolve(answer); });
    document.body.appendChild(el);
    const modal = new bootstrap.Modal(el);
    modal.show();
  });
}

// The result of a restore, in a modal, drawn by the shared component. The
// toast's colour is the server's level (a partial restore is never green).
function _showRestoreResult(title, result) {
  const el = document.createElement('div');
  el.className = 'modal fade';
  el.tabIndex = -1;
  el.innerHTML =
    '<div class="modal-dialog modal-xl modal-dialog-scrollable"><div class="modal-content">'
    + '<div class="modal-header"><h5 class="modal-title"></h5>'
    + '<button type="button" class="btn-close" data-bs-dismiss="modal"></button></div>'
    + '<div class="modal-body" data-restore-result></div>'
    + '<div class="modal-footer"><button type="button" class="btn btn-secondary" '
    + 'data-bs-dismiss="modal">Close</button></div></div></div>';
  el.querySelector('.modal-title').textContent = title;
  // The component escapes every value it draws.
  el.querySelector('[data-restore-result]').innerHTML = previewConfirmResultHtml(result, {});
  el.addEventListener('hidden.bs.modal', () => el.remove());
  document.body.appendChild(el);
  new bootstrap.Modal(el).show();
  showToast(((result || {}).happened || {}).summary || 'Re-apply finished',
            previewConfirmResultLevel(result));
}

// The devices this confirm covers: exactly the targets the preview marks
// selectable, with the hashes it drew beside them. One source, so the
// button's count, the screen and the apply's confirmations cannot differ.
// It used to confirm every `deployable` device, including one whose
// dangerous line was not authorised or whose program failed to build.
function _restoreSelected(preview) {
  return ((preview || {}).what || {}).targets
    ? preview.what.targets.filter(t => t.selectable) : [];
}

// The device page's and bulk ops' "Restore Golden Config" (P.3 step 3, D5)
// arrive here as ?restore_head=<hostname>[,<hostname>...]: the guarded
// preview at HEAD (or at ?restore_ref=<ref>, from "Restore from…"), scoped to those devices, exactly as an approval-queue
// handoff opens it. The parameter is removed first, so a reload cannot
// re-open a preview nobody asked for.
function _restoreHeadFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const raw = params.get('restore_head');
  if (!raw) return;
  // The Device page's "Restore from…" (C80) names the ref; HEAD otherwise.
  const ref = params.get('restore_ref') || 'HEAD';
  params.delete('restore_head');
  params.delete('restore_ref');
  const q = params.toString();
  history.replaceState(null, '', window.location.pathname + (q ? '?' + q : ''));
  const devices = raw.split(',').map(x => x.trim()).filter(Boolean);
  if (devices.length) previewBaselineRestore(ref, null, {devices});
}

document.addEventListener('DOMContentLoaded', loadGoldenRepoPanel);
document.addEventListener('DOMContentLoaded', _restoreHeadFromUrl);

/* Any response naming `goldens` redraws the golden panel: its pending
   renames, baselines and legacy store (Refresh Hostnames records a pending
   rename there, and the panel is where it is committed). */
NMAS.subscribe('goldens', 'goldenRepoPanel', loadGoldenRepoPanel, {panel: 'goldenRepoPanel'});
