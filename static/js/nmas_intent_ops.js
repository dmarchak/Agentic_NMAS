/* Revert and retry, from the Device page (7.3): the two ways out of a
 * rollback, and they mean opposite things.
 *
 *   revert  the change was WRONG: undo one intent commit's change, keeping
 *           every later commit. The preview draws the document after the
 *           revert against what is committed now; a commit chooser previews
 *           another commit. The rollback block is measured AFTER the commit
 *           and cleared only if it no longer blocks (C214).
 *   retry   the change was RIGHT and the failure was elsewhere: lift the
 *           block with a stated reason, recorded in the retry log. The
 *           preview says how often this device was retried before.
 *
 * Both: preview, confirm by hash with the list carried from the preview
 * (never derived), result drawn by the one component.
 */
(function (root) {
  'use strict';

  var state = {kind: '', preview: null, commits: []};

  /* Literal paths, so the reachability check reads each (a concatenated path
     is only a prefix to it). */
  var ROUTES = {revert: {preview: '/templatize/revert/preview', apply: '/templatize/revert/apply'},
                retry: {preview: '/templatize/retry/preview', apply: '/templatize/retry/apply'}};
  var TITLES = {revert: 'Revert an intent change on ', retry: 'Retry the rolled-back change on '};

  function esc(s) {
    return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  /* The revert's commit chooser. PURE: HTML, every value escaped; the commit
     the rollback note names is marked. */
  function revertCommitChooser(commits, chosen) {
    if (!commits || !commits.length) return '';
    return '<label class="form-label small fw-semibold" for="intentOpCommit">Commit to revert'
      + '</label><select class="form-select form-select-sm mb-3" id="intentOpCommit" '
      + 'data-intent-op-commit>'
      + commits.map(function (c) {
        return '<option value="' + esc(c.sha) + '"' + (c.sha === chosen ? ' selected' : '') + '>'
          + esc(c.sha) + ' ' + esc(c.date) + ' ' + esc(c.subject)
          + (c.rolled_back ? ' (the change a rollback undid)' : '') + '</option>';
      }).join('') + '</select>';
  }

  /* The confirm button's state. PURE: a retry needs a reason typed. */
  function intentOpButton(kind, preview, reasonNow) {
    if (!preview) return {disabled: true, text: 'Preview first'};
    var t = ((preview.what || {}).targets || [])[0] || {};
    var s = previewConfirmButton(preview, t.selectable ? 1 : 0,
                                 (kind === 'retry' ? 'Retry' : 'Revert') + ' '
                                 + (t.name || '') + ': refused (see the gates)');
    if (!s.disabled && kind === 'retry' && !(reasonNow || '').trim()) {
      return {disabled: true, text: 'State a reason first'};
    }
    return s;
  }

  function modal(kind, hostname) {
    var el = document.createElement('div');
    el.className = 'modal fade';
    el.tabIndex = -1;
    el.innerHTML =
      '<div class="modal-dialog modal-xl modal-dialog-scrollable"><div class="modal-content">'
      + '<div class="modal-header"><h5 class="modal-title"></h5>'
      + '<button type="button" class="btn-close" data-bs-dismiss="modal"></button></div>'
      + '<div class="modal-body"><div data-intent-op-choose></div>'
      + (kind === 'retry'
         ? '<label class="form-label small fw-semibold" for="intentOpReason">Why is this '
           + 'change right after all?</label><input type="text" class="form-control '
           + 'form-control-sm mb-1" id="intentOpReason" data-intent-op-reason>'
           + '<div class="small text-muted mb-3">Recorded in the retry log as said, beside '
           + 'the block it lifts.</div>'
         : '')
      + '<div data-intent-op-body>Reading the record…</div></div>'
      + '<div class="modal-footer">'
      + '<button type="button" class="btn btn-outline-secondary" data-bs-dismiss="modal">Close</button>'
      + '<button type="button" class="btn btn-primary" data-intent-op-confirm disabled>Preview first</button>'
      + '</div></div></div>';
    el.querySelector('.modal-title').textContent = TITLES[kind] + hostname;
    el.addEventListener('hidden.bs.modal', function () { el.remove(); });
    document.body.appendChild(el);
    return el;
  }

  function reasonOf(el) {
    var r = el.querySelector('[data-intent-op-reason]');
    return r ? r.value : '';
  }

  function refresh(el) {
    var s = intentOpButton(state.kind, state.preview, reasonOf(el));
    var btn = el.querySelector('[data-intent-op-confirm]');
    btn.disabled = s.disabled;
    btn.textContent = s.text;
  }

  async function runPreview(el, hostname, sha) {
    var body = el.querySelector('[data-intent-op-body]');
    state.preview = null;
    refresh(el);
    var d;
    try {
      var r = await fetch(ROUTES[state.kind].preview, {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({device: hostname, sha: sha || ''})});
      d = await r.json();
    } catch (e) {
      body.textContent = 'The preview failed: ' + e.message;
      return;
    }
    if (!d.ok) { body.textContent = d.error || 'The preview failed'; return; }
    state.preview = d.preview;
    if (state.kind === 'revert') {
      var t = ((d.preview.what || {}).targets || [])[0] || {};
      var choose = el.querySelector('[data-intent-op-choose]');
      choose.innerHTML = revertCommitChooser(d.commits || [], (t.select_data || {}).sha);
      var sel = choose.querySelector('[data-intent-op-commit]');
      if (sel) sel.addEventListener('change', function () { runPreview(el, hostname, sel.value); });
    }
    body.innerHTML = previewConfirmHtml(d.preview, {});
    refresh(el);
  }

  async function runApply(el, hostname) {
    var t = ((state.preview.what || {}).targets || [])[0] || {};
    var data = t.select_data || {};
    var btn = el.querySelector('[data-intent-op-confirm]');
    var body = el.querySelector('[data-intent-op-body]');
    btn.disabled = true;
    btn.textContent = state.kind === 'retry' ? 'Authorising…' : 'Reverting…';
    var payload = {list_name: data.list, device: hostname, hash: data.hash};
    if (state.kind === 'revert') payload.sha = data.sha;
    else payload.reason = reasonOf(el).trim();
    var d;
    try {
      var r = await fetch(ROUTES[state.kind].apply, {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload)});
      d = await r.json();
    } catch (e) {
      body.insertAdjacentHTML('afterbegin', '<div class="alert alert-danger" data-intent-op-failed></div>');
      body.querySelector('[data-intent-op-failed]').textContent =
        'The request failed before an answer came back: ' + e.message + '. Whether it was '
        + 'recorded is unknown: the device\'s intent history and Needs attention say.';
      return;
    }
    if (!d.ok) {
      body.insertAdjacentHTML('afterbegin', '<div class="alert alert-danger" data-intent-op-failed></div>');
      body.querySelector('[data-intent-op-failed]').textContent = d.error || 'Refused: no reason given';
      state.preview = null;
      refresh(el);
      return;
    }
    body.innerHTML = previewConfirmResultHtml(d.result, {});
    btn.classList.add('d-none');
    showToast(((d.result || {}).happened || {}).summary || 'Finished',
              previewConfirmResultLevel(d.result));
  }

  function open(kind, hostname) {
    state.kind = kind;
    state.preview = null;
    var el = modal(kind, hostname);
    el.querySelector('[data-intent-op-confirm]').addEventListener('click', function () {
      runApply(el, hostname);
    });
    var reason = el.querySelector('[data-intent-op-reason]');
    if (reason) reason.addEventListener('input', function () { refresh(el); });
    new bootstrap.Modal(el).show();
    runPreview(el, hostname, '');
  }

  root.openRevert = function (hostname) { open('revert', hostname); };
  root.openRetry = function (hostname) { open('retry', hostname); };
  root.intentOpButton = intentOpButton;
  root.revertCommitChooser = revertCommitChooser;
})(typeof window !== 'undefined' ? window : this);
