/* THE stepper's script (templates/v2/_run_stepper.html; modules/run_stepper.py).
 *
 * The server draws every row and step, and each operation's page redraws the card when its job
 * announces progress (no polling). Between two redraws the running step's time would stand
 * still, so a step that has waited a minute read "3 s". This keeps that one number counting:
 * each running step carries `data-run-since` (an ISO time from the server), and its time is
 * the seconds since then, rewritten once a second. Nothing else on the card changes here; a
 * step never moves on by itself.
 *
 * ES5. `secondsSince` is PURE, executed in duktape by tests/test_one_stepper.py.
 */
(function () {
  'use strict';

  function secondsSince(iso, nowMs) {
    var t = Date.parse(iso);
    if (isNaN(t)) { return null; }
    return Math.max(0, Math.round((nowMs - t) / 1000));
  }

  function tick() {
    var els = document.querySelectorAll('[data-run-stepper] [data-run-since]');
    var now = Date.now();
    for (var i = 0; i < els.length; i++) {
      var s = secondsSince(els[i].getAttribute('data-run-since'), now);
      if (s !== null) { els[i].textContent = s + ' s'; }
    }
  }

  if (typeof window !== 'undefined') {
    window.nmasStepper = { secondsSince: secondsSince };
    if (typeof document !== 'undefined' && document.addEventListener) {
      document.addEventListener('DOMContentLoaded', function () {
        tick();
        window.setInterval(tick, 1000);
      });
    }
  }
})();
