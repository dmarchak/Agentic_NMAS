/* Seed intent: a device's first full intent, from its committed golden (C148).
 *
 * Onboarding commits only a bootstrap intent, and a deploy needs full intent;
 * the path between them (extract, review, commit) had no screen. A seed is an
 * operation like every other change to the record:
 *   preview  each device's committed golden parsed now: the intent document
 *            to commit, against what is committed, with what the template
 *            cannot reproduce;
 *   confirm  bound to each device's seed hash, and the list the preview
 *            answered for (carried, never derived: this ends in a commit);
 *   apply    each golden parsed AGAIN, one that moved refused, one commit;
 *   result   drawn by the result component.
 * Nothing is sent to a device.
 */
(function (root) {
  'use strict';

  var state = {preview: null};

  function modal(titleText) {
    var el = document.createElement('div');
    el.className = 'modal fade';
    el.tabIndex = -1;
    el.innerHTML =
      '<div class="modal-dialog modal-xl modal-dialog-scrollable"><div class="modal-content">'
      + '<div class="modal-header"><h5 class="modal-title"></h5>'
      + '<button type="button" class="btn-close" data-bs-dismiss="modal"></button></div>'
      + '<div class="modal-body" data-seed-body></div>'
      + '<div class="modal-footer">'
      + '<button type="button" class="btn btn-outline-secondary" data-bs-dismiss="modal">Close</button>'
      + '<button type="button" class="btn btn-warning" data-seed-confirm disabled></button>'
      + '</div></div></div>';
    el.querySelector('.modal-title').textContent = titleText;
    el.addEventListener('hidden.bs.modal', function () { el.remove(); });
    document.body.appendChild(el);
    return el;
  }

  /* {devices: {host: hash}, list} for the ticked boxes. PURE over the boxes:
     the list is the one the preview drew beside each box, never the page's. */
  function seedSelection(boxes) {
    var out = {devices: {}, list: ''};
    (boxes || []).forEach(function (b) {
      if (b.checked && !b.disabled) {
        out.devices[b.dataset.device] = b.dataset.hash || '';
        out.list = out.list || b.dataset.list || '';
      }
    });
    return out;
  }

  function refreshButton(el) {
    var boxes = Array.prototype.slice.call(el.querySelectorAll('input[data-pc-select]'));
    var n = Object.keys(seedSelection(boxes).devices).length;
    var s = previewConfirmButton(state.preview, n, 'Seed ' + n + ' device(s)');
    var btn = el.querySelector('[data-seed-confirm]');
    btn.disabled = s.disabled;
    btn.textContent = s.text;
  }

  // No devices: every device in the list with no intent or only the bootstrap.
  async function previewSeed(devices) {
    devices = (devices || []).filter(Boolean);
    var el = modal(devices.length ? 'Seed intent: ' + devices.join(', ')
                   : 'Seed intent for every device without full intent');
    var body = el.querySelector('[data-seed-body]');
    body.textContent = 'Parsing the committed golden' + (devices.length === 1 ? '' : 's') + '…';
    var m = new bootstrap.Modal(el);
    m.show();
    var d;
    try {
      var r = await fetch('/templatize/seed/preview', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({devices: devices})});
      d = await r.json();
    } catch (e) {
      body.textContent = 'The preview failed: ' + e.message;
      return;
    }
    if (!d.ok) { body.textContent = d.error || 'The preview failed'; return; }
    // Nothing to seed is a result, and it says what was looked at.
    if (!d.preview) {
      body.textContent = d.nothing || 'Nothing to seed.';
      el.querySelector('[data-seed-confirm]').classList.add('d-none');
      return;
    }
    state.preview = d.preview;
    // The component escapes every value it draws.
    body.innerHTML = previewConfirmHtml(d.preview, {selectable: true, onSelect: '_seedSelectionChanged'});
    body.querySelectorAll('input[data-pc-select]').forEach(function (b) {
      if (!b.disabled) b.checked = true;
    });
    root._seedSelectionChanged = function () { refreshButton(el); };
    refreshButton(el);
    el.querySelector('[data-seed-confirm]').addEventListener('click', async function () {
      var btn = this;
      var sel = seedSelection(Array.prototype.slice.call(el.querySelectorAll('input[data-pc-select]')));
      btn.disabled = true;
      btn.textContent = 'Seeding…';
      var ad;
      inFlightBusy(true);        // the panel says what runs meanwhile (C99)
      try {
        var ar = await fetch('/templatize/seed/apply', {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({confirmations: sel.devices, list_name: sel.list || d.list})});
        ad = await ar.json();
      } catch (e) {
        showToast('Seeding failed: ' + e.message, 'danger');
        btn.disabled = false;
        return;
      } finally {
        inFlightBusy(false);
      }
      if (!ad.ok) { showToast(ad.error || 'Seeding failed', 'danger'); btn.disabled = false; return; }
      body.innerHTML = previewConfirmResultHtml(ad.result, {});
      btn.classList.add('d-none');
      showToast(((ad.result || {}).happened || {}).summary || 'Seeded',
                previewConfirmResultLevel(ad.result));
    });
  }

  root.previewSeed = previewSeed;
  root.seedSelection = seedSelection;
})(typeof window !== 'undefined' ? window : this);
