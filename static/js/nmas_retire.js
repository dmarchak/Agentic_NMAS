/* Retire a device from management, from the Device page (7.3; C11, C102).
 *
 * Retire is the whole exit: the credential override cleared, the startup
 * config declared deliberately unmapped, intent and golden removed and the
 * identity released in ONE commit (history keeps both), and the CSV row, the
 * only stored copy of its credential, deleted LAST. An operation like every
 * other change to the record:
 *   reason   required, and part of the plan's hash: a reason changed after
 *            the preview needs a new preview;
 *   preview  every step, everything retire does NOT do, and each gate;
 *   confirm  bound to the plan's hash, and the list the preview answered for
 *            (carried, never derived: this ends in a commit and a deleted row);
 *   result   drawn by the result component, the Not-Done list again.
 * The break-glass check here trusts the EXPORT LOG, and the screen says so:
 * the command line opens the record itself.
 */
(function (root) {
  'use strict';

  var state = {preview: null, reason: ''};

  function modal(hostname) {
    var el = document.createElement('div');
    el.className = 'modal fade';
    el.tabIndex = -1;
    el.innerHTML =
      '<div class="modal-dialog modal-xl modal-dialog-scrollable"><div class="modal-content">'
      + '<div class="modal-header"><h5 class="modal-title"></h5>'
      + '<button type="button" class="btn-close" data-bs-dismiss="modal"></button></div>'
      + '<div class="modal-body">'
      + '<label class="form-label fw-semibold" for="retireReason">Why is it leaving management?</label>'
      + '<div class="input-group mb-2">'
      + '<input type="text" class="form-control" id="retireReason" data-retire-reason'
      + ' placeholder="e.g. ISP device outside our administrative boundary">'
      + '<button type="button" class="btn btn-outline-secondary" data-retire-preview>Preview</button>'
      + '</div>'
      + '<div class="small text-muted mb-3">The reason goes into the commit, the startup'
      + ' config\'s unmapped declaration and the history. "retired" on its own tells the next'
      + ' reader nothing.</div>'
      + '<div data-retire-body></div></div>'
      + '<div class="modal-footer">'
      + '<button type="button" class="btn btn-outline-secondary" data-bs-dismiss="modal">Close</button>'
      + '<button type="button" class="btn btn-danger" data-retire-confirm disabled>Preview first</button>'
      + '</div></div></div>';
    el.querySelector('.modal-title').textContent = 'Retire ' + hostname;
    el.addEventListener('hidden.bs.modal', function () { el.remove(); });
    document.body.appendChild(el);
    return el;
  }

  /* The confirm button's state. PURE: a reason edited after the preview is
     not the reason the plan's hash covers, so it cannot be confirmed. */
  function retireButton(preview, reasonNow) {
    if (!preview) return {disabled: true, text: 'Preview first'};
    var t = ((preview.what || {}).targets || [])[0] || {};
    var data = t.select_data || {};
    if ((reasonNow || '').trim() !== (data.reason || '')) {
      return {disabled: true, text: 'Preview again: the reason changed'};
    }
    return previewConfirmButton(preview, t.selectable ? 1 : 0,
                                'Retire ' + (t.name || '') + ': refused (see the gates)');
  }

  function refresh(el) {
    var s = retireButton(state.preview, el.querySelector('[data-retire-reason]').value);
    var btn = el.querySelector('[data-retire-confirm]');
    btn.disabled = s.disabled;
    btn.textContent = s.text;
  }

  async function runPreview(el, hostname) {
    var body = el.querySelector('[data-retire-body]');
    var reason = el.querySelector('[data-retire-reason]').value.trim();
    state.preview = null;
    refresh(el);
    body.textContent = 'Planning the retirement…';
    var d;
    try {
      var r = await fetch('/retire/preview', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({device: hostname, reason: reason})});
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
    var btn = el.querySelector('[data-retire-confirm]');
    var body = el.querySelector('[data-retire-body]');
    btn.disabled = true;
    btn.textContent = 'Retiring…';
    var ad;
    inFlightBusy(true);        // the panel says what runs meanwhile (C99)
    try {
      var ar = await fetch('/retire/apply', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({list_name: data.list, device: hostname,
                              reason: data.reason, hash: data.hash})});
      ad = await ar.json();
    } catch (e) {
      body.insertAdjacentHTML('afterbegin', '<div class="alert alert-danger" data-retire-failed></div>');
      body.querySelector('[data-retire-failed]').textContent =
        'The retire request failed before an answer came back: ' + e.message
        + '. Whether anything was done is unknown: preview again, which shows each step done or not.';
      state.preview = null;
      refresh(el);
      return;
    } finally {
      inFlightBusy(false);
    }
    if (!ad.ok) {
      body.insertAdjacentHTML('afterbegin', '<div class="alert alert-danger" data-retire-failed></div>');
      body.querySelector('[data-retire-failed]').textContent = ad.error || 'Retire failed: no reason given';
      state.preview = null;
      refresh(el);
      return;
    }
    body.innerHTML = previewConfirmResultHtml(ad.result, {});
    btn.classList.add('d-none');
    el.querySelector('[data-retire-preview]').disabled = true;
    el.querySelector('[data-retire-reason]').disabled = true;
    showToast(((ad.result || {}).happened || {}).summary || 'Retire finished',
              previewConfirmResultLevel(ad.result));
  }

  function openRetire(hostname) {
    state.preview = null;
    var el = modal(hostname);
    var reason = el.querySelector('[data-retire-reason]');
    el.querySelector('[data-retire-preview]').addEventListener('click', function () {
      runPreview(el, hostname);
    });
    reason.addEventListener('input', function () { refresh(el); });
    el.querySelector('[data-retire-confirm]').addEventListener('click', function () {
      runApply(el, hostname);
    });
    new bootstrap.Modal(el).show();
    reason.focus();
  }

  root.openRetire = openRetire;
  root.retireButton = retireButton;
})(typeof window !== 'undefined' ? window : this);
