/* Rotate a device's login credential, from the Device page (7.3).
 *
 * The riskiest operation in the tool, built assuming a fourth failure mode
 * exists (the operator, 2026-09-27):
 *   preview  the plan: the preflight (which READS the account's line, live),
 *            the program with the new password masked, what rotation does NOT
 *            do, each check as a gate by name;
 *   confirm  bound to the plan's fingerprint and the list the preview answered
 *            for (carried, never derived), as a verified person;
 *   apply    a JOB on the server: rotate then persist can pass the edge's
 *            100 s limit, so this window may close; the job ANNOUNCES
 *            `rotation` when it finishes and the page reads the result by id;
 *   result   the state it reached, danger first, with its one action.
 */
(function (root) {
  'use strict';

  var state = {preview: null, job: null, onJob: null};

  async function fetchRotationJob(job) {
    var r = await fetch('/rotate/result/' + encodeURIComponent(job));
    return await r.json();
  }

  /* Heard an announcement: read the open job, if any. */
  function rotationHeard() {
    var job = state.job, on = state.onJob;
    if (!job || !on) return true;
    return fetchRotationJob(job).then(function (d) { on(d); return true; },
                                      function () { return false; });
  }
  if (root.NMAS && root.NMAS.subscribe) {
    NMAS.subscribe('rotation', 'rotation', rotationHeard);
  }

  /* While the job runs. PURE: {lines, live}. */
  function rotationWaitingWords(hostname, jd, liveState) {
    var lines = ['Rotating ' + hostname + ' on the server'
                 + (jd && jd.elapsed_s !== undefined ? ' (' + jd.elapsed_s + ' s so far).' : '.')];
    lines.push('The result appears here when it finishes. Closing this window does not stop '
               + 'it: the in-flight panel shows it, and Needs attention keeps the device in '
               + 'front of you until it is persisted.');
    var live = liveState === 'connected';
    if (!live) {
      lines.push('Live updates are not connected on this page, so the result will not '
                 + 'appear by itself: press Check now.');
    }
    return {lines: lines, live: live};
  }

  function rotateButton(preview) {
    if (!preview) return {disabled: true, text: 'Preview first'};
    var t = ((preview.what || {}).targets || [])[0] || {};
    return previewConfirmButton(preview, t.selectable ? 1 : 0,
                                'Rotate ' + (t.name || '') + ': refused (see the gates)');
  }

  function modal(hostname) {
    var el = document.createElement('div');
    el.className = 'modal fade';
    el.tabIndex = -1;
    el.innerHTML =
      '<div class="modal-dialog modal-xl modal-dialog-scrollable"><div class="modal-content">'
      + '<div class="modal-header"><h5 class="modal-title"></h5>'
      + '<button type="button" class="btn-close" data-bs-dismiss="modal"></button></div>'
      + '<div class="modal-body"><div data-rotate-body>Reading the account&#39;s line on the '
      + 'device…</div></div>'
      + '<div class="modal-footer">'
      + '<button type="button" class="btn btn-outline-secondary" data-bs-dismiss="modal">Close</button>'
      + '<button type="button" class="btn btn-danger" data-rotate-confirm disabled>Preview first</button>'
      + '</div></div></div>';
    el.querySelector('.modal-title').textContent = 'Rotate ' + hostname + '’s credential';
    el.addEventListener('hidden.bs.modal', function () {
      state.job = null; state.onJob = null; el.remove();
    });
    document.body.appendChild(el);
    return el;
  }

  function refresh(el) {
    var s = rotateButton(state.preview);
    var btn = el.querySelector('[data-rotate-confirm]');
    btn.disabled = s.disabled;
    btn.textContent = s.text;
  }

  async function runPreview(el, hostname) {
    var body = el.querySelector('[data-rotate-body]');
    state.preview = null;
    refresh(el);
    var d;
    try {
      var r = await fetch('/rotate/preview', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({device: hostname})});
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

  async function runApply(el, hostname) {
    var t = ((state.preview.what || {}).targets || [])[0] || {};
    var data = t.select_data || {};
    var btn = el.querySelector('[data-rotate-confirm]');
    var body = el.querySelector('[data-rotate-body]');
    btn.disabled = true;
    btn.textContent = 'Starting…';
    var d;
    try {
      var r = await fetch('/rotate/apply', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({list_name: data.list, device: hostname,
                              fingerprint: data.fingerprint})});
      d = await r.json();
    } catch (e) {
      body.insertAdjacentHTML('afterbegin', '<div class="alert alert-danger" data-rotate-failed></div>');
      body.querySelector('[data-rotate-failed]').textContent =
        'The request failed before an answer came back: ' + e.message + '. Whether the '
        + 'rotation started is unknown: the in-flight panel and the device\'s rotation row '
        + 'on Needs attention say.';
      return;
    }
    if (!d.ok || !d.job) {
      body.insertAdjacentHTML('afterbegin', '<div class="alert alert-danger" data-rotate-failed></div>');
      body.querySelector('[data-rotate-failed]').textContent = d.error || 'Not started: no reason given';
      state.preview = null;
      refresh(el);
      return;
    }
    btn.classList.add('d-none');
    function drawWaiting(jd) {
      var live = (root.NMAS && root.NMAS.live) ? root.NMAS.live().state : 'not_connected';
      var w = rotationWaitingWords(hostname, jd, live);
      body.textContent = '';
      w.lines.forEach(function (line) {
        var p = document.createElement('p');
        p.textContent = line;
        body.appendChild(p);
      });
      var check = document.createElement('button');
      check.type = 'button';
      check.className = 'btn btn-sm btn-outline-secondary';
      check.textContent = 'Check now';
      check.addEventListener('click', function () {
        if (state.job === d.job) fetchRotationJob(d.job).then(onJob);
      });
      body.appendChild(check);
    }
    function onJob(jd) {
      if (state.job !== d.job || state.onJob !== onJob) return;
      if (jd.state === 'running') { drawWaiting(jd); return; }
      state.onJob = null;
      if (jd.state !== 'done') {
        body.textContent = jd.error || ('The rotation ' + (jd.state || 'failed') + '.');
        return;
      }
      body.innerHTML = previewConfirmResultHtml(jd.result, {});
      showToast(((jd.result || {}).happened || {}).summary || 'Rotation finished',
                previewConfirmResultLevel(jd.result));
    }
    state.job = d.job;
    state.onJob = onJob;
    drawWaiting(null);
    fetchRotationJob(d.job).then(onJob, function () {});
  }

  function openRotate(hostname) {
    state.preview = null;
    var el = modal(hostname);
    el.querySelector('[data-rotate-confirm]').addEventListener('click', function () {
      runApply(el, hostname);
    });
    new bootstrap.Modal(el).show();
    runPreview(el, hostname);
  }

  root.openRotate = openRotate;
  root.rotateButton = rotateButton;
  root.rotationWaitingWords = rotationWaitingWords;
  root.rotationHeard = rotationHeard;
})(typeof window !== 'undefined' ? window : this);
