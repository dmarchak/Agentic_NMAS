/* The break-glass export, from the browser (7.3; modules/breakglass_export.py).
 *
 * ONE implementation, reached three ways: the rotate result's next step,
 * Needs attention's break-glass row, and the Settings page. Each entry point
 * is an element carrying data-nmas-open="breakglass_export" (and
 * data-nmas-list); the listener below opens this, so no entry point names
 * code and the server never names a function.
 *
 *   preview  which devices the record holds and the key's fingerprint; no value;
 *   confirm  the passphrase TWICE (refused before anything is built if they
 *            differ or are short), bound to the preview's hash and its list;
 *   result   the server built, sealed and OPENED the record before sending; the
 *            bytes are handed to this browser as a download and never written
 *            on the host. The passphrase fields are cleared at once.
 */
(function (root) {
  'use strict';

  var MIN = 12;
  var state = {preview: null};

  /* The confirm button's state. PURE. */
  function breakglassButton(preview, pass, again) {
    if (!preview) return {disabled: true, text: 'Preview first'};
    var t = ((preview.what || {}).targets || [])[0] || {};
    var s = previewConfirmButton(preview, t.selectable ? 1 : 0,
                                 'Export ' + (t.name || '') + ': refused (see the gates)');
    if (s.disabled) return s;
    if ((pass || '').length < MIN) return {disabled: true, text: 'The passphrase needs '
                                            + MIN + ' characters or more'};
    if (pass !== again) return {disabled: true, text: 'The two passphrases differ'};
    return s;
  }

  /* base64 to bytes. PURE. */
  function breakglassBytes(b64) {
    var bin = atob(b64), out = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
    return out;
  }

  function modal(listName) {
    var el = document.createElement('div');
    el.className = 'modal fade';
    el.tabIndex = -1;
    el.innerHTML =
      '<div class="modal-dialog modal-xl modal-dialog-scrollable"><div class="modal-content">'
      + '<div class="modal-header"><h5 class="modal-title"></h5>'
      + '<button type="button" class="btn-close" data-bs-dismiss="modal"></button></div>'
      + '<div class="modal-body">'
      + '<div class="row g-2 mb-2"><div class="col-md-6">'
      + '<label class="form-label small fw-semibold" for="bgPass">Passphrase</label>'
      + '<input type="password" class="form-control form-control-sm" id="bgPass" '
      + 'autocomplete="new-password" data-bg-pass></div><div class="col-md-6">'
      + '<label class="form-label small fw-semibold" for="bgPass2">Again</label>'
      + '<input type="password" class="form-control form-control-sm" id="bgPass2" '
      + 'autocomplete="new-password" data-bg-again></div></div>'
      + '<div class="small text-muted mb-3">At least ' + MIN + ' characters. It seals the file; '
      + 'it is never stored, logged or sent back, and nothing can recover it.</div>'
      + '<div data-bg-body>Reading what the record would hold…</div></div>'
      + '<div class="modal-footer">'
      + '<button type="button" class="btn btn-outline-secondary" data-bs-dismiss="modal">Close</button>'
      + '<button type="button" class="btn btn-danger" data-bg-confirm disabled>Preview first</button>'
      + '</div></div></div>';
    el.querySelector('.modal-title').textContent = 'Export the break-glass record: ' + listName;
    el.addEventListener('hidden.bs.modal', function () { el.remove(); });
    document.body.appendChild(el);
    return el;
  }

  function fields(el) {
    return [el.querySelector('[data-bg-pass]'), el.querySelector('[data-bg-again]')];
  }

  function refresh(el) {
    var f = fields(el);
    var s = breakglassButton(state.preview, f[0].value, f[1].value);
    var btn = el.querySelector('[data-bg-confirm]');
    btn.disabled = s.disabled;
    btn.textContent = s.text;
  }

  async function runPreview(el, listName) {
    var body = el.querySelector('[data-bg-body]');
    var d;
    try {
      var r = await fetch('/breakglass/preview', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({list_name: listName})});
      d = await r.json();
    } catch (e) {
      body.textContent = 'The preview failed: ' + e.message;
      return;
    }
    if (!d.ok) { body.textContent = d.error || 'The preview failed'; return; }
    state.preview = d.preview;
    body.innerHTML = previewConfirmHtml(d.preview, {});
    refresh(el);
  }

  async function runExport(el) {
    var t = ((state.preview.what || {}).targets || [])[0] || {};
    var data = t.select_data || {};
    var f = fields(el);
    var btn = el.querySelector('[data-bg-confirm]');
    var body = el.querySelector('[data-bg-body]');
    var payload = JSON.stringify({list_name: data.list, hash: data.hash,
                                  passphrase: f[0].value, confirm: f[1].value});
    // Cleared at once: nothing on the page holds the passphrase after it is sent.
    f[0].value = ''; f[1].value = '';
    btn.disabled = true;
    btn.textContent = 'Building, sealing and verifying…';
    var d;
    try {
      var r = await fetch('/breakglass/export', {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: payload});
      payload = null;
      d = await r.json();
    } catch (e) {
      body.insertAdjacentHTML('afterbegin', '<div class="alert alert-danger" data-bg-failed></div>');
      body.querySelector('[data-bg-failed]').textContent =
        'The request failed before an answer came back: ' + e.message + '. Whether a record '
        + 'was built is unknown; the reveal record says, and nothing was downloaded.';
      state.preview = null;
      refresh(el);
      return;
    }
    if (!d.ok) {
      body.insertAdjacentHTML('afterbegin', '<div class="alert alert-danger" data-bg-failed></div>');
      body.querySelector('[data-bg-failed]').textContent = d.error || 'Refused: no reason given';
      state.preview = null;
      refresh(el);
      return;
    }
    if (d.file) {
      var blob = new Blob([breakglassBytes(d.file)], {type: 'application/octet-stream'});
      d.file = null;
      var url = URL.createObjectURL(blob);
      var a = document.createElement('a');
      a.href = url;
      a.download = d.filename || 'nmas-breakglass.bg';
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(function () { URL.revokeObjectURL(url); }, 10000);
    }
    body.innerHTML = previewConfirmResultHtml(d.result, {});
    btn.classList.add('d-none');
    showToast(((d.result || {}).happened || {}).summary || 'Export finished',
              previewConfirmResultLevel(d.result));
  }

  function openBreakglassExport(listName) {
    state.preview = null;
    var el = modal(listName);
    el.querySelector('[data-bg-confirm]').addEventListener('click', function () {
      runExport(el);
    });
    fields(el).forEach(function (f) { f.addEventListener('input', function () { refresh(el); }); });
    new bootstrap.Modal(el).show();
    runPreview(el, listName);
  }

  /* The three entry points: any element naming this operation opens it. */
  if (typeof document !== 'undefined' && document.addEventListener) {
    document.addEventListener('click', function (e) {
      var b = e.target && e.target.closest && e.target.closest('[data-nmas-open="breakglass_export"]');
      // Board 7 (2026-10-03): every way in opens Credentials, the export ready, for its list.
      if (b) {
        e.preventDefault();
        root.location.assign('/v2/credentials?open=export&list='
                             + encodeURIComponent(b.getAttribute('data-nmas-list') || ''));
      }
    });
    /* The fourth: ?open=breakglass_export&list=<list>, the link the redesigned pages use
       (C372: a link that only opened a page was a dead end). The list is the link's. */
    document.addEventListener('DOMContentLoaded', function () {
      var q = new URLSearchParams(root.location.search);
      // Board 7 (2026-10-03): the export lives on Credentials; an old link goes there.
      if (q.get('open') === 'breakglass_export') {
        root.location.assign('/v2/credentials?open=export&list='
                             + encodeURIComponent(q.get('list') || ''));
      }
    });
  }

  root.openBreakglassExport = openBreakglassExport;
  root.breakglassButton = breakglassButton;
  root.breakglassBytes = breakglassBytes;
})(typeof window !== 'undefined' ? window : this);
