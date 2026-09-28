/* Restore scope, chosen rather than inherited (7.1 step 5, register C80).
 *
 * From the interface a baseline could be re-applied only to the whole fleet,
 * and the scoped paths all restored at HEAD. So restoring ONE device from a
 * baseline needed the browser console (C70's step 3). Two choosers fix that,
 * and both end in the same guarded restore preview:
 *
 *   Device page, "Restore from…"   this device's golden now, its own golden
 *                                  tags, and every baseline that holds it,
 *                                  each with its credential state;
 *   Baselines panel, "Re-apply"    a device selection that starts EMPTY, so
 *                                  "the whole fleet" is ticked, never assumed.
 *
 * Every value drawn is escaped. The decisions (which scope, where to go) are
 * pure functions over what they are given, so the tests execute them.
 */
(function (root) {
  'use strict';

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c];
    });
  }

  var KIND_WORDS = {
    head: 'golden now',
    device: 'this device\'s golden',
    baseline: 'baseline'
  };

  // What re-applying this point would do to the device's credentials, as the
  // Baselines panel measures it. `silent` was the one that mattered: an
  // account the ref has and the device lacks was ADDED back and nothing
  // refused it. Since C79 the restore's own check refuses it (the line may
  // be authorised with a stated reason), so it reads `refused`; `silent` is
  // kept for the state a removed guard would produce.
  var CRED_WORDS = {
    current: ['bg-success-subtle text-success-emphasis', 'credentials current'],
    refused: ['bg-secondary-subtle text-secondary-emphasis',
              'predates its credentials: the preview blocks it, nothing is sent'],
    silent: ['bg-danger-subtle text-danger-emphasis',
             'would ADD BACK an account this device no longer has'],
    no_golden: ['bg-secondary-subtle text-secondary-emphasis', 'no golden at this ref']
  };

  function credBadge(state) {
    var w = CRED_WORDS[state] || ['bg-warning-subtle text-warning-emphasis',
                                  'credential state unknown: ' + state];
    return '<span class="badge ' + w[0] + '" data-rs-cred="' + esc(state) + '">'
      + esc(w[1]) + '</span>';
  }

  /* The Device page's restore points, one row each, newest first after the
     golden now. PURE over the /golden/restore_points payload. */
  function restorePointsHtml(d) {
    if (!d || d.ok !== true) {
      return '<div class="alert alert-danger small mb-0">Could not list restore points: '
        + esc((d && d.error) || 'no answer')
        + '. This is not the same as there being none.</div>';
    }
    var rows = (d.points || []).map(function (p) {
      var claim = p.kind === 'baseline'
        ? ' <span class="badge bg-secondary-subtle text-secondary-emphasis" title="'
          + esc(p.claim_detail || '') + '">' + esc(p.claim || 'configured') + '</span>'
        : '';
      return '<tr data-rs-ref="' + esc(p.ref) + '">'
        + '<td class="small">' + esc(KIND_WORDS[p.kind] || p.kind) + claim + '</td>'
        + '<td class="small"><span class="font-monospace">' + esc(p.ref) + '</span>'
        + '<div class="text-muted">' + esc(p.subject || '') + '</div></td>'
        + '<td class="small text-muted">' + esc(p.created || '') + '</td>'
        + '<td>' + credBadge(p.credential) + '</td>'
        + '<td class="text-end"><button type="button" class="btn btn-outline-warning btn-sm"'
        + ' data-rs-choose data-ref="' + esc(p.ref) + '" data-credential="' + esc(p.credential)
        + '">Preview</button></td></tr>';
    }).join('');
    return '<p class="small">Each point opens the guarded restore preview for '
      + '<strong>' + esc(d.hostname) + '</strong> alone, in list <strong>' + esc(d.list)
      + '</strong>: the exact program, what stays '
      + 'behind, then a confirm. Nothing is sent from this list.</p>'
      + '<div class="table-responsive"><table class="table table-sm align-middle mb-0"><tbody>'
      + rows + '</tbody></table></div>';
  }

  /* Where choosing a point goes: the index page's restore flow, scoped to
     this device at that ref. PURE. */
  function restoreFromUrl(hostname, ref) {
    return '/?restore_head=' + encodeURIComponent(hostname)
      + '&restore_ref=' + encodeURIComponent(ref);
  }

  async function openRestoreFrom(hostname) {
    var el = document.createElement('div');
    el.className = 'modal fade';
    el.tabIndex = -1;
    el.innerHTML =
      '<div class="modal-dialog modal-xl modal-dialog-scrollable"><div class="modal-content">'
      + '<div class="modal-header"><h5 class="modal-title"></h5>'
      + '<button type="button" class="btn-close" data-bs-dismiss="modal"></button></div>'
      + '<div class="modal-body" data-rs-body>Listing restore points…</div>'
      + '<div class="modal-footer"><button type="button" class="btn btn-secondary" '
      + 'data-bs-dismiss="modal">Close</button></div></div></div>';
    el.querySelector('.modal-title').textContent = 'Restore ' + hostname + ' from…';
    el.addEventListener('hidden.bs.modal', function () { el.remove(); });
    document.body.appendChild(el);
    new bootstrap.Modal(el).show();
    var body = el.querySelector('[data-rs-body]');
    var d;
    try {
      var r = await fetch('/golden/restore_points/' + encodeURIComponent(hostname));
      d = await r.json();
    } catch (e) {
      d = {ok: false, error: e.message};
    }
    // The component escapes every value it draws.
    body.innerHTML = restorePointsHtml(d);
    body.querySelectorAll('[data-rs-choose]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var ref = btn.dataset.ref;
        if (btn.dataset.credential === 'silent') {
          var typed = prompt(ref + ' would ADD BACK an account ' + hostname
            + ' no longer has. If it was removed on purpose, do not restore from here.'
            + '\n\nType APPLY to continue to the preview.');
          if ((typed || '').trim() !== 'APPLY') return;
        }
        window.location.href = restoreFromUrl(hostname, ref);
      });
    });
  }

  /* The Baselines panel's scope: the devices this baseline holds, NONE ticked,
     and the whole fleet as its own explicit choice. PURE. */
  function baselineScopeHtml(b) {
    var stale = b.credential_stale || [];
    var silent = b.credential_silent || [];
    var boxes = (b.devices || []).map(function (host) {
      var note = silent.indexOf(host) >= 0 ? credBadge('silent')
        : (stale.indexOf(host) >= 0 ? credBadge('refused') : '');
      return '<label class="d-flex gap-2 align-items-center small">'
        + '<input type="checkbox" class="form-check-input mt-0" data-rs-device="'
        + esc(host) + '"> <span class="font-monospace">' + esc(host) + '</span> ' + note
        + '</label>';
    }).join('');
    var missing = b.missing_devices || [];
    return '<p class="small">Choose what this re-apply covers. Nothing is chosen until you '
      + 'choose it.</p>'
      + '<div data-rs-devices>' + boxes + '</div><hr class="my-2">'
      + '<label class="d-flex gap-2 align-items-center small fw-semibold">'
      + '<input type="checkbox" class="form-check-input mt-0" data-rs-fleet> The whole fleet</label>'
      + '<div class="small text-muted">Every device in the inventory'
      + (missing.length ? ('; this baseline predates ' + esc(missing.join(', '))
         + ', which will be left exactly as they are') : '')
      + '. Only the whole fleet can earn a baseline tag.</div>';
  }

  /* What the boxes choose: null (nothing yet), {devices: null} (the whole
     fleet) or {devices: [...]}. PURE over the boxes it is given. */
  function baselineScopeSelection(deviceBoxes, fleetBox) {
    if (fleetBox && fleetBox.checked) return {devices: null};
    var chosen = (deviceBoxes || []).filter(function (b) { return b.checked; })
      .map(function (b) { return b.dataset.rsDevice; });
    return chosen.length ? {devices: chosen} : null;
  }

  function chooseBaselineScope(b) {
    return new Promise(function (resolve) {
      var el = document.createElement('div');
      el.className = 'modal fade';
      el.tabIndex = -1;
      el.innerHTML =
        '<div class="modal-dialog modal-lg modal-dialog-scrollable"><div class="modal-content">'
        + '<div class="modal-header"><h5 class="modal-title"></h5>'
        + '<button type="button" class="btn-close" data-bs-dismiss="modal"></button></div>'
        + '<div class="modal-body" data-rs-scope></div>'
        + '<div class="modal-footer">'
        + '<button type="button" class="btn btn-outline-secondary" data-bs-dismiss="modal">Cancel</button>'
        + '<button type="button" class="btn btn-warning" data-rs-continue disabled>Choose a scope</button>'
        + '</div></div></div>';
      el.querySelector('.modal-title').textContent = 'Re-apply ' + b.tag + ' to…';
      var body = el.querySelector('[data-rs-scope]');
      // The component escapes every value it draws.
      body.innerHTML = baselineScopeHtml(b);
      var btn = el.querySelector('[data-rs-continue]');
      var fleet = body.querySelector('[data-rs-fleet]');
      var boxes = Array.prototype.slice.call(body.querySelectorAll('[data-rs-device]'));
      function refresh() {
        boxes.forEach(function (x) { x.disabled = fleet.checked; });
        var s = baselineScopeSelection(boxes, fleet);
        btn.disabled = !s;
        btn.textContent = !s ? 'Choose a scope'
          : (s.devices === null ? 'Preview the whole fleet'
             : 'Preview ' + s.devices.length + ' device(s)');
      }
      fleet.addEventListener('change', refresh);
      boxes.forEach(function (x) { x.addEventListener('change', refresh); });
      var answer = null;
      btn.addEventListener('click', function () {
        answer = baselineScopeSelection(boxes, fleet);
        modal.hide();
      });
      el.addEventListener('hidden.bs.modal', function () { el.remove(); resolve(answer); });
      document.body.appendChild(el);
      var modal = new bootstrap.Modal(el);
      modal.show();
    });
  }

  root.openRestoreFrom = openRestoreFrom;
  root.restorePointsHtml = restorePointsHtml;
  root.restoreFromUrl = restoreFromUrl;
  root.baselineScopeHtml = baselineScopeHtml;
  root.baselineScopeSelection = baselineScopeSelection;
  root.chooseBaselineScope = chooseBaselineScope;
})(typeof window !== 'undefined' ? window : this);
