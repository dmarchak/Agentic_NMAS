/* Propose the network's monitoring profile (NSOT_PLAN P.9 step b;
 * modules/nsot/profile_propose.py).
 *
 *   preview  the profile the fleet's committed intent agrees on, against what
 *            is committed, each section's basis and who inherits it, and every
 *            section NOT proposed with why (two versions are never reconciled
 *            by the tool);
 *   confirm  bound to the proposal's hash, and the list the preview answered
 *            for (carried, never derived: this ends in a commit);
 *   apply    computed again, one that moved refused, one commit;
 *   result   drawn by the result component, whose next step opens "Apply
 *            monitoring profile" (the scoped deploy) for the devices that
 *            inherit.
 * Nothing is sent to any device. Opened by any element carrying
 * data-nmas-open="profile_propose", and by ?open=profile_propose&list=<list>,
 * the link the redesigned pages use.
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
      + '<div class="modal-body" data-profile-body></div>'
      + '<div class="modal-footer">'
      + '<button type="button" class="btn btn-outline-secondary me-auto" data-profile-committed>'
      + 'Show the committed profile</button>'
      + '<button type="button" class="btn btn-outline-secondary" data-bs-dismiss="modal">Close</button>'
      + '<button type="button" class="btn btn-warning" data-profile-confirm disabled></button>'
      + '</div></div></div>';
    el.querySelector('.modal-title').textContent = titleText;
    el.addEventListener('hidden.bs.modal', function () { el.remove(); });
    document.body.appendChild(el);
    return el;
  }

  /* {hash, list} of the ticked proposal, or null. PURE over the boxes: the
     list is the one the preview drew beside the box, never the page's. */
  function profileSelection(boxes) {
    var picked = (boxes || []).filter(function (b) { return b.checked && !b.disabled; })[0];
    return picked ? {hash: picked.dataset.hash || '', list: picked.dataset.list || ''} : null;
  }

  function refreshButton(el) {
    var boxes = Array.prototype.slice.call(el.querySelectorAll('input[data-pc-select]'));
    var n = profileSelection(boxes) ? 1 : 0;
    var s = previewConfirmButton(state.preview, n, 'Commit the profile');
    var btn = el.querySelector('[data-profile-confirm]');
    btn.disabled = s.disabled;
    btn.textContent = s.text;
  }

  /* The record, read back: the committed document and its last commit. */
  async function showCommitted(el, listName) {
    var body = el.querySelector('[data-profile-body]');
    var r, d;
    try {
      r = await fetch('/templatize/profile?list_name=' + encodeURIComponent(listName || ''));
      d = await r.json();
    } catch (e) {
      body.textContent = 'The committed profile could not be read: ' + e.message;
      return;
    }
    var pre = document.createElement('pre');
    pre.className = 'small border rounded p-2';
    pre.textContent = !d.ok ? (d.error || 'The committed profile could not be read')
      : !d.profile ? d.list + ' has no committed monitoring profile.'
      : (d.commit ? 'Last commit ' + d.commit.sha.slice(0, 12) + ' by ' + d.commit.author
         + ', ' + d.commit.at + ': ' + d.commit.subject + '\n\n' : '')
        + JSON.stringify(d.profile, null, 2);
    body.appendChild(pre);
  }

  /* A section whose devices hold different versions of its SHARED fields:
     the tool never picks one; a person may (the operator, 2026-09-30). Each
     version is a button that previews again with it chosen. PURE: HTML. */
  function choicesHtml(choices, esc) {
    return (choices || []).filter(function (c) { return !c.chosen; }).map(function (c) {
      return '<div class="alert alert-secondary py-2" data-profile-choice="' + esc(c.section) + '">'
        + '<strong>Choose a version of ' + esc(c.section) + '</strong>: its devices hold '
        + c.versions.length + ' versions of its shared fields. '
        + c.versions.map(function (v) {
          return '<button type="button" class="btn btn-sm btn-outline-primary ms-1" '
            + 'data-profile-section="' + esc(c.section) + '" data-profile-version="' + esc(v.id)
            + '">Use the version held by ' + esc(v.devices.join(', ')) + '</button>';
        }).join('') + '</div>';
    }).join('');
  }

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c];
    });
  }

  async function previewProfilePropose(listName, choose) {
    choose = choose || {};
    var el = modal('Propose the monitoring profile' + (listName ? ': ' + listName : ''));
    var body = el.querySelector('[data-profile-body]');
    body.textContent = 'Reading every device\'s committed intent…';
    new bootstrap.Modal(el).show();
    el.querySelector('[data-profile-committed]').addEventListener('click', function () {
      showCommitted(el, listName);
    });
    var d;
    try {
      var r = await fetch('/templatize/profile/propose/preview', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({list_name: listName || '', choose: choose})});
      d = await r.json();
    } catch (e) {
      body.textContent = 'The preview failed: ' + e.message;
      return;
    }
    if (!d.ok) { body.textContent = d.error || 'The preview failed'; return; }
    state.preview = d.preview;
    // The component escapes every value it draws.
    body.innerHTML = choicesHtml(d.choices, esc)
      + previewConfirmHtml(d.preview, {selectable: true, onSelect: '_profileSelectionChanged'});
    body.querySelectorAll('[data-profile-version]').forEach(function (b) {
      b.addEventListener('click', function () {
        var next = Object.assign({}, choose);
        next[b.dataset.profileSection] = b.dataset.profileVersion;
        bootstrap.Modal.getInstance(el).hide();
        previewProfilePropose(listName, next);
      });
    });
    body.querySelectorAll('input[data-pc-select]').forEach(function (b) {
      if (!b.disabled) b.checked = true;
    });
    root._profileSelectionChanged = function () { refreshButton(el); };
    refreshButton(el);
    el.querySelector('[data-profile-confirm]').addEventListener('click', async function () {
      var btn = this;
      var sel = profileSelection(Array.prototype.slice.call(
        el.querySelectorAll('input[data-pc-select]')));
      if (!sel) return;
      btn.disabled = true;
      btn.textContent = 'Committing…';
      var ad;
      try {
        var ar = await fetch('/templatize/profile/propose/apply', {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({hash: sel.hash, list_name: sel.list || d.list, choose: choose})});
        ad = await ar.json();
      } catch (e) {
        body.insertAdjacentHTML('afterbegin', '<div class="alert alert-danger">'
          + 'The request did not reach the app: ' + e.message.replace(/[<>&]/g, '') + '</div>');
        btn.disabled = false;
        return;
      }
      if (!ad.ok) {
        // A refusal stays where it can be read (C84), never only a toast.
        var p = document.createElement('div');
        p.className = 'alert alert-danger';
        p.textContent = ad.error || 'Nothing was committed';
        body.insertBefore(p, body.firstChild);
        btn.disabled = false;
        return;
      }
      body.innerHTML = previewConfirmResultHtml(ad.result, {});
      btn.classList.add('d-none');
    });
  }

  if (root.document && root.document.addEventListener) {
    root.document.addEventListener('click', function (e) {
      var b = e.target && e.target.closest && e.target.closest('[data-nmas-open="profile_propose"]');
      if (b) previewProfilePropose(b.dataset.nmasList || '');
    });
    root.document.addEventListener('DOMContentLoaded', function () {
      var q = new URLSearchParams(root.location.search);
      if (q.get('open') === 'profile_propose') previewProfilePropose(q.get('list') || '');
    });
  }

  root.previewProfilePropose = previewProfilePropose;
  root.profileSelection = profileSelection;
  root.profileChoicesHtml = function (c) { return choicesHtml(c, esc); };
})(typeof window !== 'undefined' ? window : this);
