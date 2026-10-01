/* Capture: recording running configs as goldens, as an operation (7.1 step 4).
 *
 * Register C82 (there was no per-device capture) and C89 (Save All promoted
 * whatever a device held to golden, a baseline tag and the remote, asking
 * nothing). A capture is now previewed and confirmed like every other change
 * to the record:
 *   preview  each device read NOW: what its golden would become, and how it
 *            compares with its committed INTENT (the comparison that survives
 *            a capture, since the capture becomes the golden);
 *   confirm  bound to each device's capture hash;
 *   apply    each device READ AGAIN, one that moved refused, one commit with
 *            a computed `Intent-Match:` trailer, a baseline only for the
 *            whole fleet at its committed intent;
 *   result   drawn by the result component.
 * No devices is the whole fleet: what Save All opens.
 */
(function (root) {
  'use strict';

  var state = {preview: null, fleet: false, job: null, onJob: null};

  /* C188 step 2: the preview's device reads run as a JOB on the server. The
     POST answers at once with its id; the job ANNOUNCES `capture_preview`
     (C58) when it finishes, and the page reads the result by the id. No
     request waits on a device, so no edge limit can end one (a series read
     of nine devices took 107 s, past Cloudflare's 100 s). */
  async function fetchCaptureJob(job) {
    var r = await fetch('/golden/capture/preview/' + encodeURIComponent(job));
    return await r.json();
  }

  /* Heard an announcement: read the open job, if any. Every open page hears
     every capture's announcement (it carries key names only), so a page with
     no job open, or one already drawn, does nothing. */
  function capturePreviewHeard() {
    var job = state.job, on = state.onJob;
    if (!job || !on) return true;
    return fetchCaptureJob(job).then(function (d) { on(d); return true; },
                                     function () { return false; });
  }
  if (root.NMAS && root.NMAS.subscribe) {
    NMAS.subscribe('capture_preview', 'capturePreview', capturePreviewHeard);
  }

  /* While the reads run: what is being read, what it is doing now, and a way
     to ask. PURE over the job's answer; the caller escapes nothing because
     it builds text nodes. Returns {lines: [...], live: bool}. */
  function captureWaitingWords(devices, jd, liveState) {
    var lines = ['Reading ' + devices.length + ' device(s) at once, on the server: '
                 + devices.join(', ') + '.'];
    lines.push(jd && jd.step_words ? 'Now: ' + jd.step_words
               + (jd.elapsed_s !== undefined ? ' (' + jd.elapsed_s + ' s so far).' : '.')
               : 'Started.');
    lines.push('The preview appears here when the reads finish; the in-flight panel '
               + 'shows them meanwhile. Closing this window does not stop them.');
    var live = liveState === 'connected';
    if (!live) {
      lines.push('Live updates are not connected on this page, so the preview will not '
                 + 'appear by itself: press Check now.');
    }
    return {lines: lines, live: live};
  }

  function modal(titleText) {
    var el = document.createElement('div');
    el.className = 'modal fade';
    el.tabIndex = -1;
    el.innerHTML =
      '<div class="modal-dialog modal-xl modal-dialog-scrollable"><div class="modal-content">'
      + '<div class="modal-header"><h5 class="modal-title"></h5>'
      + '<button type="button" class="btn-close" data-bs-dismiss="modal"></button></div>'
      + '<div class="modal-body" data-capture-body></div>'
      + '<div class="modal-footer">'
      + '<button type="button" class="btn btn-outline-secondary" data-bs-dismiss="modal">Close</button>'
      + '<button type="button" class="btn btn-warning" data-capture-confirm disabled></button>'
      + '</div></div></div>';
    el.querySelector('.modal-title').textContent = titleText;
    el.addEventListener('hidden.bs.modal', function () { el.remove(); });
    document.body.appendChild(el);
    return el;
  }

  /* The devices this confirm covers: the ticked boxes, with the hashes the
     preview drew beside them. PURE over the boxes it is given. */
  function captureSelection(boxes) {
    var out = {};
    (boxes || []).forEach(function (b) {
      if (b.checked && !b.disabled) out[b.dataset.device] = b.dataset.hash || '';
    });
    return out;
  }

  /* PURE over the drawn fields: each device's stated reason for a shrink
     committed intent does not explain (C310). Empty fields are not sent. */
  function captureAcknowledged(el) {
    var out = {};
    Array.prototype.slice.call(el.querySelectorAll('input[data-ack-device]')).forEach(function (i) {
      var v = (i.value || '').trim();
      if (v) out[i.dataset.ackDevice] = v;
    });
    return out;
  }

  function refreshButton(el) {
    var boxes = Array.prototype.slice.call(el.querySelectorAll('input[data-pc-select]'));
    var n = Object.keys(captureSelection(boxes)).length;
    var s = previewConfirmButton(state.preview, n, 'Record ' + n + ' device(s)');
    var btn = el.querySelector('[data-capture-confirm]');
    btn.disabled = s.disabled;
    btn.textContent = s.text;
  }

  // opts.scope 'no_golden': every device with no committed golden, chosen
  // by the server from git (what Auto-Create was, as a scope of this one
  // operation: NSOT_STAGE7_PLAN section 6a).
  async function previewCapture(devices, opts) {
    devices = (devices || []).filter(Boolean);
    var scope = (opts && opts.scope) || '';
    // Queue items handed to this capture ({host: [ids]}), closed by the apply
    // only for devices it records.
    var approvals = (opts && opts.approvals) || null;
    state.fleet = !devices.length && !scope;
    var el = modal(scope ? 'Record a first golden for every device without one'
                   : state.fleet ? 'Record every device as its golden'
                   : 'Record as golden: ' + devices.join(', '));
    var body = el.querySelector('[data-capture-body]');
    body.textContent = 'Starting the reads…';
    var m = new bootstrap.Modal(el);
    m.show();
    el.addEventListener('hidden.bs.modal', function () { state.job = null; state.onJob = null; });
    var d;
    try {
      var r = await fetch('/golden/capture/preview', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(scope ? {scope: scope} : {devices: devices})});
      d = await r.json();
    } catch (e) {
      body.textContent = 'The preview failed: ' + e.message;
      return;
    }
    if (!d.ok) { body.textContent = d.error || 'The preview failed'; return; }
    // Nothing to capture is a result, and it says what was looked at.
    if (!d.job) {
      body.textContent = d.nothing || 'Nothing to capture.';
      el.querySelector('[data-capture-confirm]').classList.add('d-none');
      return;
    }
    var names = d.devices || [];
    function drawWaiting(jd) {
      var live = (root.NMAS && root.NMAS.live) ? root.NMAS.live().state : 'not_connected';
      var w = captureWaitingWords(names, jd, live);
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
        if (state.job === d.job) fetchCaptureJob(d.job).then(onJob);
      });
      body.appendChild(check);
    }
    function onJob(jd) {
      if (state.job !== d.job || state.onJob !== onJob) return;       // closed, or drawn
      if (jd.state === 'running') { drawWaiting(jd); return; }
      state.onJob = null;
      if (jd.state !== 'done') {
        body.textContent = jd.error || ('The preview ' + (jd.state || 'failed') + '.');
        return;
      }
      drawPreview(jd);
    }
    state.job = d.job;
    state.onJob = onJob;
    drawWaiting(null);
    // One read now: the job may have finished before this page subscribed.
    fetchCaptureJob(d.job).then(onJob, function () {});

    function drawPreview(jd) {
      if (!jd.preview) {
        body.textContent = jd.nothing || 'Nothing to capture.';
        el.querySelector('[data-capture-confirm]').classList.add('d-none');
        return;
      }
      state.preview = jd.preview;
      // The component escapes every value it draws.
      body.innerHTML = previewConfirmHtml(jd.preview, {selectable: true, onSelect: '_captureSelectionChanged'});
      body.querySelectorAll('input[data-pc-select]').forEach(function (b) {
        if (!b.disabled) b.checked = true;
      });
      root._captureSelectionChanged = function () { refreshButton(el); };
      refreshButton(el);
      el.querySelector('[data-capture-confirm]').addEventListener('click', async function () {
        var btn = this;
        var boxes = Array.prototype.slice.call(el.querySelectorAll('input[data-pc-select]'));
        var conf = (state.preview && state.preview.confirm) || {};
        btn.disabled = true;
        // The work, not only the outcome: a denial record still reads every device.
        btn.textContent = conf.working || 'Reading and recording…';
        var ad;
        inFlightBusy(true);        // the panel says what runs meanwhile (C99)
        try {
          var ar = await fetch('/golden/capture/apply', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(Object.assign(
              {confirmations: captureSelection(boxes), fleet: state.fleet,
               mode: conf.mode || 'record', acknowledge: captureAcknowledged(el)},
              approvals ? {approvals: approvals} : {}))});
          ad = await ar.json();
        } catch (e) {
          showToast('Recording failed: ' + e.message, 'danger');
          btn.disabled = false;
          return;
        } finally {
          inFlightBusy(false);
        }
        if (!ad.ok) { showToast(ad.error || 'Recording failed', 'danger'); btn.disabled = false; return; }
        body.innerHTML = previewConfirmResultHtml(ad.result, {});
        btn.classList.add('d-none');
        var summary = ((ad.result || {}).happened || {}).summary || 'Recorded';
        var q = ad.approvals || {};
        if (approvals) {
          summary += ' Queue: ' + (q.closed || []).length + ' item(s) closed, '
                   + (q.left_pending || []).length + ' left pending (their device was not recorded).';
        }
        showToast(summary, previewConfirmResultLevel(ad.result));
        if (typeof loadGoldenRepoPanel === 'function') loadGoldenRepoPanel();
        if (approvals && typeof loadApprovalsTab === 'function') loadApprovalsTab();
      });
    }
  }

  root.previewCapture = previewCapture;
  root.captureSelection = captureSelection;
  root.captureAcknowledged = captureAcknowledged;
  root.captureWaitingWords = captureWaitingWords;
  root.capturePreviewHeard = capturePreviewHeard;
})(typeof window !== 'undefined' ? window : this);
