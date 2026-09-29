/* Persist a device's running config, from the Device page (7.3, C164).
 *
 * Save the running config to startup on the device, then read the startup
 * config back: persisted only if it carries every `username` line the running
 * config holds. The remedy the worst Needs attention rows name
 * (`not_safe_to_reboot`). An operation like every other change:
 *   preview  every step, what persist does NOT do, and each gate; it does not
 *            contact the device, so it opens at once;
 *   confirm  bound to the plan's hash, and the list the preview answered for
 *            (carried, never derived: this saves a device of that list);
 *   result   drawn by the result component from what the device answered.
 */
(function (root) {
  'use strict';

  var state = {preview: null};

  function modal(hostname) {
    var el = document.createElement('div');
    el.className = 'modal fade';
    el.tabIndex = -1;
    el.innerHTML =
      '<div class="modal-dialog modal-xl modal-dialog-scrollable"><div class="modal-content">'
      + '<div class="modal-header"><h5 class="modal-title"></h5>'
      + '<button type="button" class="btn-close" data-bs-dismiss="modal"></button></div>'
      + '<div class="modal-body"><div data-persist-body>Planning…</div></div>'
      + '<div class="modal-footer">'
      + '<button type="button" class="btn btn-outline-secondary" data-bs-dismiss="modal">Close</button>'
      + '<button type="button" class="btn btn-primary" data-persist-confirm disabled>Preview first</button>'
      + '</div></div></div>';
    el.querySelector('.modal-title').textContent = 'Persist ' + hostname;
    el.addEventListener('hidden.bs.modal', function () { el.remove(); });
    document.body.appendChild(el);
    return el;
  }

  /* The confirm button's state. PURE. */
  function persistButton(preview) {
    if (!preview) return {disabled: true, text: 'Preview first'};
    var t = ((preview.what || {}).targets || [])[0] || {};
    return previewConfirmButton(preview, t.selectable ? 1 : 0,
                                'Persist ' + (t.name || '') + ': refused (see the gates)');
  }

  function refresh(el) {
    var s = persistButton(state.preview);
    var btn = el.querySelector('[data-persist-confirm]');
    btn.disabled = s.disabled;
    btn.textContent = s.text;
  }

  async function runPreview(el, hostname) {
    var body = el.querySelector('[data-persist-body]');
    state.preview = null;
    refresh(el);
    var d;
    try {
      var r = await fetch('/persist/preview', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({device: hostname})});
      d = await r.json();
    } catch (e) {
      body.textContent = 'The preview failed: ' + e.message;
      return;
    }
    if (!d.ok) { body.textContent = d.error || 'The preview failed'; return; }
    state.preview = d.preview;
    // The component escapes every value it draws.
    body.innerHTML = previewConfirmHtml(d.preview, {});
    refresh(el);
  }

  async function runApply(el, hostname) {
    var t = ((state.preview.what || {}).targets || [])[0] || {};
    var data = t.select_data || {};
    var btn = el.querySelector('[data-persist-confirm]');
    var body = el.querySelector('[data-persist-body]');
    btn.disabled = true;
    btn.textContent = 'Saving and reading back…';
    var ad;
    inFlightBusy(true);        // the panel says what runs meanwhile (C99)
    try {
      var ar = await fetch('/persist/apply', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({list_name: data.list, device: hostname, hash: data.hash})});
      ad = await ar.json();
    } catch (e) {
      body.insertAdjacentHTML('afterbegin', '<div class="alert alert-danger" data-persist-failed></div>');
      body.querySelector('[data-persist-failed]').textContent =
        'The persist request failed before an answer came back: ' + e.message
        + '. Whether the device saved is unknown: the hourly startup check will say, or persist again.';
      state.preview = null;
      refresh(el);
      return;
    } finally {
      inFlightBusy(false);
    }
    if (!ad.ok) {
      body.insertAdjacentHTML('afterbegin', '<div class="alert alert-danger" data-persist-failed></div>');
      body.querySelector('[data-persist-failed]').textContent = ad.error || 'Persist failed: no reason given';
      state.preview = null;
      refresh(el);
      return;
    }
    body.innerHTML = previewConfirmResultHtml(ad.result, {});
    btn.classList.add('d-none');
    showToast(((ad.result || {}).happened || {}).summary || 'Persist finished',
              previewConfirmResultLevel(ad.result));
  }

  function openPersist(hostname) {
    state.preview = null;
    var el = modal(hostname);
    el.querySelector('[data-persist-confirm]').addEventListener('click', function () {
      runApply(el, hostname);
    });
    new bootstrap.Modal(el).show();
    runPreview(el, hostname);
  }

  root.openPersist = openPersist;
  root.persistButton = persistButton;
})(typeof window !== 'undefined' ? window : this);
