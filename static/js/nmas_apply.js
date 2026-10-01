/* The batch Apply's confirm (P.9 step d2; routes/v2.py).
 *
 * The preview is drawn by the server, and so is the body this sends: the
 * capture and command hashes of the program on the screen, the removals
 * ticked and their reasons, in the rollout order (`data-body`, built by
 * routes.v2._apply_ctx). This only POSTs it, unchanged, as the person.
 *
 * The control is busy ON ITSELF ("Starting the batch…") until the server
 * answers; then the job's progress is drawn in place below (#apply-result),
 * redrawn as each device finishes. A refusal is said beside the button, in
 * the server's words, and the button comes back.
 *
 * ES5, Alpine's CSP build: getters and argument-free methods only, every
 * data-* attribute read from `$root` (the x-data element; C243's rule).
 * `confirmOutcome` is PURE, executed in duktape by tests/test_profile_apply_v2.py.
 */
(function (root) {
  'use strict';

  /* PURE. What the page does with the server's answer: *status* the HTTP
     status, *body* the parsed JSON (or null). */
  function confirmOutcome(status, body) {
    if (status === 202 && body && body.ok && body.url) return {started: true, url: body.url, error: ''};
    var why = body && body.error ? body.error : 'refused (HTTP ' + status + ')';
    return {started: false, url: '', error: 'Nothing was sent: ' + why};
  }

  function register() {
    root.Alpine.data('applyConfirm', function () {
      return {
        busy: false, started: false, error: '',
        get locked() { return this.busy || this.started; },
        get hasError() { return !!this.error; },
        get label() {
          if (this.busy) return 'Starting the batch…';
          if (this.started) return 'Started: its progress is below';
          return this.$root.getAttribute('data-label') || 'Apply';
        },
        confirm: function () {
          var self = this;
          if (self.locked) return;
          self.busy = true;
          self.error = '';
          root.fetch(self.$root.getAttribute('data-url'), {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'Accept': 'application/json'},
            body: self.$root.getAttribute('data-body')
          }).then(function (r) {
            return r.json().then(function (b) { return confirmOutcome(r.status, b); },
                                 function () { return confirmOutcome(r.status, null); });
          }).then(function (o) {
            self.busy = false;
            self.started = o.started;
            self.error = o.error;
            if (o.started && root.htmx) {
              root.htmx.ajax('GET', o.url, {target: '#apply-result', swap: 'innerHTML'});
            }
          }, function (e) {
            self.busy = false;
            self.error = 'Nothing was sent: the request did not reach the server (' + e + ')';
          });
        }
      };
    });
  }

  if (root.document && root.document.addEventListener) {
    root.document.addEventListener('alpine:init', register);
  }
  root.NMAS_APPLY = {confirmOutcome: confirmOutcome};
})(typeof window !== 'undefined' ? window : this);
