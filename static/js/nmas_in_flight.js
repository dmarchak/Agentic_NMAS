/* What is running on this list's devices, and what finished recently (C99).

   A restore ran for fifty seconds with nothing on screen; the operator took
   the silence to mean it had staged something and started a deploy of the
   same device. The standing rule: every process says what happened or what to
   do next, and one that is RUNNING says so, since when, and what it waits on.

   ONE panel, fixed above every modal, on every page: the restore closes its
   modal before it applies, and the deploy wizard's modal covers the page, so
   a panel inside either would be the silence again. It reads C98's lock
   (every holder, the CLIs included) and the receipts (so a reload does not
   lose a result). It polls every 5 s, and every 1.5 s while this page has an
   apply outstanding (inFlightBusy). */
(function (root) {
  var fast = 0, timer = null, dismissed = {};

  function esc(s) {
    return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function ago(s) {
    s = Math.max(0, Math.round(s || 0));
    return s < 90 ? s + ' s' : Math.round(s / 60) + ' min';
  }

  /* Pure: the panel for one payload. `seen` names recent rows already
     dismissed on this page. Returns '' only when nothing runs and nothing
     finished recently: a FAILED read is never drawn as nothing running. */
  function inFlightPanelHtml(d, seen) {
    seen = seen || {};
    if (!d || d.ok !== true) {
      return '<div class="alert alert-warning mb-0 small" data-in-flight="unknown">'
        + '<strong>Could not ask which operations are running</strong>'
        + (d && d.error ? ': ' + esc(d.error) : '') + '. This is not the same as '
        + 'none running: an operation may be in progress on a device.</div>';
    }
    var running = d.running || [];
    var recent = (d.recent || []).filter(function (r) {
      return !seen[r.device + '|' + r.at];
    });
    if (!running.length && !recent.length) return '';
    var html = '';
    if (running.length) {
      html += '<div class="alert alert-info mb-1 small" data-in-flight="running">'
        + '<strong>Running now</strong> (nothing else can change these devices until it '
        + 'finishes):<ul class="mb-0 ps-3">'
        + running.map(function (r) {
            return '<li><strong>' + esc(r.device) + '</strong> is being ' + esc(r.words)
              + ' by ' + esc(r.actor || 'unknown') + ', for ' + ago(r.held_for_s)
              + (r.step_words ? '; now: ' + esc(r.step_words) + ' (' + ago(r.step_ago_s)
                 + ')' : '')
              + (r.stalled ? ' <span class="badge bg-danger">no progress: may be stuck'
                 + '</span>' : '')
              + '</li>';
          }).join('') + '</ul></div>';
    }
    if (recent.length) {
      html += '<div class="alert alert-secondary mb-0 small" data-in-flight="recent">'
        + '<button type="button" class="btn-close float-end" aria-label="Hide"'
        + ' onclick="inFlightDismiss()"></button>'
        + '<strong>Finished in the last ' + Math.round((d.window_s || 1800) / 60)
        + ' min</strong>. Each receipt is on its device\'s page, Changes tab:'
        + '<ul class="mb-0 ps-3">'
        + recent.map(function (r) {
            return '<li>' + esc(r.device) + ': ' + esc(r.action) + ' by '
              + esc(r.actor || 'unknown') + ' at ' + esc((r.at || '').slice(11, 19))
              + ' UTC: <strong>' + esc(r.outcome) + '</strong>'
              + (r.commit_state === 'pending'
                 ? ' <span class="badge bg-warning text-dark" data-commit-state="pending">'
                   + 'commit pending</span>' : '')
              + (r.reason ? ' (' + esc(r.reason) + ')' : '') + '</li>';
          }).join('') + '</ul></div>';
    }
    return html;
  }

  var last = null;

  async function loadInFlight() {
    var el = document.getElementById('inFlightPanel');
    if (!el) return;
    var d;
    try {
      var r = await fetch('/operations/in_flight', {cache: 'no-store'});
      d = await r.json();
    } catch (e) {
      d = {ok: false, error: e.message};
    }
    last = d;
    el.innerHTML = inFlightPanelHtml(d, dismissed);
  }

  function schedule() {
    if (timer) clearTimeout(timer);
    timer = setTimeout(function () {
      loadInFlight().then(schedule, schedule);
    }, fast > 0 ? 1500 : 5000);
  }

  /* Around every apply: true before the request, false when it answers. */
  function inFlightBusy(on) {
    fast = Math.max(0, fast + (on ? 1 : -1));
    loadInFlight();
    schedule();
  }

  function inFlightDismiss() {
    ((last && last.recent) || []).forEach(function (r) { dismissed[r.device + '|' + r.at] = true; });
    var el = document.getElementById('inFlightPanel');
    if (el) el.innerHTML = inFlightPanelHtml(last, dismissed);
  }

  root.inFlightPanelHtml = inFlightPanelHtml;
  root.inFlightBusy = inFlightBusy;
  root.inFlightDismiss = inFlightDismiss;
  root.loadInFlight = loadInFlight;
  if (typeof document !== 'undefined' && document.addEventListener) {
    document.addEventListener('DOMContentLoaded', function () {
      loadInFlight();
      schedule();
    });
  }
})(typeof window !== 'undefined' ? window : this);
