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
    const [bRes, mRes, rRes, lRes] = await Promise.all([
      fetch('/golden/baselines').then(r => r.json()),
      fetch('/golden/migrate/plan').then(r => r.json()),
      fetch('/golden/renames').then(r => r.json()),
      fetch('/golden/legacy_store').then(r => r.json()),
    ]);

    const baselines = (bRes.baselines || []).slice(0, 10);
    window._gBaselineCache = baselines;
    const pending = (rRes.pending || []);
    const needsMigration = mRes.ok && mRes.device_count > 0 && !mRes.already_migrated;

    host.innerHTML = `
      ${needsMigration ? _migrationCard(mRes) : ''}
      ${pending.length ? `
        <div class="alert alert-info py-2 px-3 d-flex align-items-center gap-2">
          <span>${pending.length} device rename(s) noticed but not yet in the repo:
            ${pending.map(p => `<code>${_gEsc(p.from)} → ${_gEsc(p.to)}</code>`).join(', ')}</span>
          <button class="btn btn-outline-primary btn-sm ms-auto" onclick="syncGoldenRenames()">
            Sync device names to repo
          </button>
        </div>` : ''}
      ${_gLegacyStoreCard(lRes)}
      <div class="card border-light-subtle">
        <div class="card-body py-2 px-3">
          <h6 class="text-primary fw-semibold mb-2">Baselines
            <span class="text-muted fw-normal small ms-1">(stored network-wide configuration)</span>
          </h6>
          ${baselines.length ? `
            <div class="table-responsive"><table class="table table-sm align-middle mb-0">
              <tbody>${baselines.map(b => `
                <tr>
                  <td class="font-monospace small">${_gEsc(b.tag)}</td>
                  <td class="small text-muted">${_gEsc(_gWhen(b.created))}</td>
                  <td>${_gBaselineCoverage(b)}</td>
                  <td>${_gCredWarning(b)}</td>
                  <td class="text-end">
                    <button class="btn btn-outline-warning btn-sm"
                            onclick="confirmBaselineRestore('${_gEsc(b.tag)}')"
                            title="Re-applies stored configuration. Does not remove lines devices have gained.">
                      Re-apply this baseline
                    </button>
                  </td>
                </tr>`).join('')}</tbody></table></div>`
            : '<p class="text-muted small mb-0">No baselines yet. "Save All" creates one.</p>'}
        </div>
      </div>`;
  } catch (e) { console.error('loadGoldenRepoPanel', e); }
}

/* The deprecated store's RETIREMENT CONDITION, on screen.
 *
 * `golden_configs/` has been read-only since the migration, and until Stage
 * 3.3 it was also what every reader enumerated -- so the nine devices were
 * covered by accident rather than by design. Two things still consult it: the
 * last link of `_find_golden_config_file`'s chain, and the legacy-only
 * entries in `repo.list_goldens()`.
 *
 * When nothing lives there that the manifest does not know, both can go. The
 * card says so in those words, because "deprecated" with no exit criterion is
 * a thing nobody ever gets to delete.
 */
function _gLegacyStoreCard(l) {
  if (!l || !l.ok) return '';
  if (!l.legacy_files) return '';              // already gone: say nothing
  const only = l.only_legacy || [];
  if (l.retirable) {
    return `
      <div class="card border-success-subtle mb-3">
        <div class="card-body py-2 px-3">
          <h6 class="text-success-emphasis fw-semibold mb-1">Legacy golden store can be retired</h6>
          <p class="text-muted small mb-0">
            <code>golden_configs/</code> holds ${l.legacy_files} file(s), and the
            manifest knows every device in it. Nothing here is the only copy of
            anything, so the directory and the header-scan fallback can be removed.
          </p>
        </div>
      </div>`;
  }
  return `
    <div class="card border-warning-subtle mb-3">
      <div class="card-body py-2 px-3">
        <h6 class="text-warning-emphasis fw-semibold mb-1">
          Legacy golden store still holds ${only.length} device(s)
        </h6>
        <p class="text-muted small mb-1">
          These are in <code>golden_configs/</code> and not in the repository
          manifest, so they resolve through the deprecated header scan. The
          directory can be retired once this list is empty.
        </p>
        <ul class="small mb-0">
          ${only.map(d => `<li><code>${_gEsc(d.hostname)}</code>
             <span class="text-muted">(${_gEsc(d.device_ip)} · ${_gEsc(d.file)})</span></li>`).join('')}
        </ul>
      </div>
    </div>`;
}

function _migrationCard(m) {
  const merges = m.merges || [];
  return `
    <div class="card border-warning-subtle mb-3">
      <div class="card-body py-2 px-3">
        <h6 class="text-warning-emphasis fw-semibold mb-2">
          Configuration repository migration available
        </h6>
        <p class="small mb-2">
          ${m.device_count} device(s) would move into the versioned <code>golden/</code>
          layout. <strong>This is a preview — nothing has been changed.</strong>
        </p>
        ${merges.length ? `
          <div class="alert alert-warning py-2 px-3 small">
            <strong>${merges.length} duplicate device(s) would be merged.</strong>
            Without merging, one device would end up with two golden files.
            <div class="table-responsive mt-2">
              <table class="table table-sm mb-0"><thead><tr>
                <th>Keeping</th><th>Merging in</th><th>Why</th><th>Content differs</th>
              </tr></thead><tbody>
                ${merges.map(mg => `<tr>
                  <td class="font-monospace small">${_gEsc(mg.winner.file)}
                    <span class="text-muted">(${_gEsc(mg.winner.modified)})</span></td>
                  <td class="font-monospace small">${mg.losers.map(l =>
                      `${_gEsc(l.file)} <span class="text-muted">(${_gEsc(l.modified)})</span>`).join('<br>')}</td>
                  <td class="small">${_gEsc(mg.reason)}</td>
                  <td>${mg.content_differed
                        ? '<span class="badge bg-warning text-dark">yes</span>'
                        : '<span class="badge bg-secondary">identical</span>'}</td>
                </tr>`).join('')}
              </tbody></table>
            </div>
            <div class="form-text mb-0">
              Nothing is deleted — merged-away copies are kept under
              <code>.nsot/migration-backup/</code>.
            </div>
          </div>` : ''}
        ${m.case_insensitive_fs ? `
          <p class="small text-muted">
            This filesystem folds case, so files differing only by case are already
            the same file. Reported for accuracy rather than merged.
          </p>` : ''}
        <div class="form-check mb-2">
          <input class="form-check-input" type="checkbox" id="goldenMigrateConfirm"
                 onchange="document.getElementById('goldenMigrateBtn').disabled = !this.checked">
          <label class="form-check-label small" for="goldenMigrateConfirm">
            I have reviewed this report and want to migrate.
          </label>
        </div>
        <button class="btn btn-warning btn-sm" id="goldenMigrateBtn" disabled
                onclick="applyGoldenMigration()">Migrate repository</button>
      </div>
    </div>`;
}

async function applyGoldenMigration() {
  const btn = document.getElementById('goldenMigrateBtn');
  btn.disabled = true;
  try {
    const r = await fetch('/golden/migrate/apply', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({confirm: true}),
    });
    const d = await r.json();
    showToast(d.ok
      ? `Migrated ${d.migrated.length} device(s)`
        + (d.merges.length ? `, merged ${d.merges.length} duplicate(s)` : '')
      : `Migration failed: ${d.error}`, d.ok ? 'success' : 'danger');
    loadGoldenRepoPanel();
  } catch (e) { showToast(e.message, 'danger'); btn.disabled = false; }
}

async function syncGoldenRenames() {
  try {
    const r = await fetch('/golden/renames/sync', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({}),
    });
    const d = await r.json();
    showToast(d.message || (d.ok ? 'Renames synced' : 'Sync failed'),
              d.ok ? 'success' : 'danger');
    loadGoldenRepoPanel();
  } catch (e) { showToast(e.message, 'danger'); }
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
                            devices: from.devices || null,
                            advisory_diff: from.advisoryDiff || '',
                            approval_id: from.approvalId || ''}),
    });
    const d = await r.json();
    if (!d.ok) { showToast(d.error, 'danger'); return; }

    // Three categories, because "re-apply" and "restore" differ exactly here:
    // residue is what stays behind, and it is the only thing the old label
    // implied would be removed.
    const lines = [];
    (d.devices || []).forEach(dev => {
      const adds = (dev.add || []).length, reps = (dev.replace || []).length;
      const res  = (dev.residue || []).length;
      if (!dev.deployable) {
        lines.push(`  • ${dev.device} — BLOCKED: ${(dev.blocking_reasons || []).join('; ')}`);
        return;
      }
      lines.push(`  • ${dev.device} — ${adds} to add, ${reps} to replace, ${res} left in place`);
      (dev.replace || []).slice(0, 3).forEach(rp =>
        lines.push(`      replace: ${rp.old.trim()}  →  ${rp.new.trim()}`));
      (dev.residue || []).slice(0, 3).forEach(rs =>
        lines.push(`      stays:   ${rs.trim()}`));
      // The intent half of the same unit. A device restored with its committed
      // intent left behind would have the next plan offer to undo the restore.
      const it = dev.intent || {};
      if (it.action === 'restore')  lines.push(`      intent:  restored to this ref`);
      if (it.action === 'un_onboard') lines.push(`      intent:  REMOVED (un-onboard)`);
    });

    const skipped = d.skipped || [];
    const skippedText = skipped.length
      ? '\n\nSkipped:\n' + skipped.map(s => `  • ${s.hostname} — ${s.reason}`).join('\n')
      : '';

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

    // What the agent saw, when it saw it — shown above the program so the
    // operator can compare, and labelled so it cannot be mistaken for what
    // will be sent.
    const advisory = from.advisoryDiff
      ? `WHAT THE AGENT SAW when the drift was detected (context only, NOT `
        + `what will be sent):\n${from.advisoryDiff.trim().split('\n').slice(0, 12)
            .map(l => '  ' + l).join('\n')}\n\n`
        + `${from.advisoryNote || ''}\n\n${'-'.repeat(60)}\n\n`
      : '';

    if (!confirm(
        advisory + `${d.summary}\n\n${lines.join('\n')}${skippedText}\n\n`
        + `SCOPE: ${d.scope}\n\n`
        + `This ADDS and REPLACES. It does not remove lines a device has gained.\n\nContinue?`)) return;

    const confirmations = {}, hashes = {};
    (d.devices || []).filter(x => x.deployable).forEach(x => {
      confirmations[x.device] = x.capture_hash;
      hashes[x.device] = x.command_hash;
    });
    if (!Object.keys(confirmations).length) {
      showToast('Nothing to re-apply — every device is blocked or already matches', 'warning');
      return;
    }

    const ar = await fetch('/golden/restore/apply', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ref: tag, confirmations, command_hashes: hashes,
                            un_onboard: unOnboard,
                            approval_id: from.approvalId || ''}),
    });
    const ad = await ar.json();
    const done = (ad.deployed || []).length;
    const intent = (ad.golden || {}).intent || {};
    const extra = (intent.restored || []).length
      ? `, intent restored for ${(intent.restored || []).length}` : '';
    showToast(ad.ok ? `Re-applied to ${done} device(s)${extra}`
                    : `Re-apply failed: ${ad.error || ''}`,
              ad.ok ? 'success' : 'danger');
    loadGoldenRepoPanel();
  } catch (e) { showToast(e.message, 'danger'); }
}

document.addEventListener('DOMContentLoaded', loadGoldenRepoPanel);
