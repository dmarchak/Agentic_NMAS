/* THE stepper's script (templates/v2/_run_stepper.html; modules/run_stepper.py).
 *
 * The server draws every row and step, and each operation's page redraws the card when its job
 * announces progress (no polling). Between two redraws the running step's time would stand
 * still, so a step that has waited a minute read "3 s". This keeps that one number counting:
 * each running step carries `data-run-since` (an ISO time from the server), and its time is
 * the seconds since then, rewritten once a second. Nothing else on the card changes here; a
 * step never moves on by itself.
 *
 * A step's DECLARED wait counts down the same way (the operator, 2026-11-11: "live waits with
 * a countdown"): the server sends when the step began and the length the operation declared
 * (`data-run-wait-began`, `data-run-wait-s`; `data-run-wait-bound` when the length is the
 * longest it waits), and this draws what is left of it, in the server's own words
 * (modules/run_stepper.py `_wait`). It is a display of a declared wait, never a guess: at zero
 * it says the time is up and waits for the server's next step, which replaces it.
 *
 * ES5. `secondsSince` and `waitWords` are PURE, executed in duktape by
 * tests/test_one_stepper.py and tests/test_run_progress.py.
 */
(function () {
  'use strict';

  function secondsSince(iso, nowMs) {
    var t = Date.parse(iso);
    if (isNaN(t)) { return null; }
    return Math.max(0, Math.round((nowMs - t) / 1000));
  }

  function waitWords(iso, lengthS, bound, nowMs) {
    var t = Date.parse(iso);
    var n = Number(lengthS);
    if (isNaN(t) || !(n > 0)) { return null; }
    var left = Math.max(0, Math.round((t + n * 1000 - nowMs) / 1000));
    if (left === 0) { return 'its ' + n + ' s are up; waiting for the next step'; }
    return bound ? 'up to ' + n + ' s: ' + left + ' s left' : left + ' s left of ' + n + ' s';
  }

  function tick() {
    var els = document.querySelectorAll('[data-run-stepper] [data-run-since]');
    var now = Date.now();
    for (var i = 0; i < els.length; i++) {
      var s = secondsSince(els[i].getAttribute('data-run-since'), now);
      if (s !== null) { els[i].textContent = s + ' s'; }
    }
    var waits = document.querySelectorAll('[data-run-stepper] [data-run-wait-began]');
    for (var j = 0; j < waits.length; j++) {
      var w = waitWords(waits[j].getAttribute('data-run-wait-began'),
                        waits[j].getAttribute('data-run-wait-s'),
                        waits[j].hasAttribute('data-run-wait-bound'), now);
      if (w !== null) { waits[j].textContent = w; }
    }
  }

  if (typeof window !== 'undefined') {
    window.nmasStepper = { secondsSince: secondsSince, waitWords: waitWords };
    if (typeof document !== 'undefined' && document.addEventListener) {
      document.addEventListener('DOMContentLoaded', function () {
        tick();
        window.setInterval(tick, 1000);
      });
    }
  }
})();
