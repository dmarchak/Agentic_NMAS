/* History's two remote buttons (NSOT_GUI_BRIEF 3.4; routes/v2.py): Push now
 * (POST /remote/push, gated publish_remote) and Verify the remote
 * (POST /remote/verify, read-only). Each is busy ON ITSELF until the server
 * answers; then it says the answer beside itself in a few words. A push also
 * re-reads the remote, whose announcement (`remote`) redraws the header.
 *
 * ES5, Alpine's CSP build: getters and argument-free methods only, every
 * data-* attribute read from `$root` (C243's rule). `remoteOutcome` is PURE,
 * executed in duktape by tests/test_history_v2.py.
 */
(function (root) {
  'use strict';

  /* PURE. The words for an answer: *kind* "push" or "verify", *status* the
     HTTP status, *body* the parsed JSON (or null). */
  function remoteOutcome(kind, status, body) {
    if (!body) return {ok: false, words: 'No answer the page could read (HTTP ' + status + ')'};
    if (kind === 'verify') {
      var checks = body.checks || [];
      if (body.ok) return {ok: true, words: 'Verified: ' + checks.length + ' of ' + checks.length + ' checks passed'};
      var bad = [];
      for (var i = 0; i < checks.length; i++) {
        if (!checks[i].ok) bad.push(checks[i].name + (checks[i].detail ? ' (' + checks[i].detail + ')' : ''));
      }
      return {ok: false, words: body.error ? body.error : 'Not verified: ' + bad.join('; ')};
    }
    if (status === 200 && body.ok) return {ok: true, words: 'Pushed'};
    return {ok: false, words: 'Not pushed: ' + (body.error || body.reason || ('HTTP ' + status))};
  }

  function register() {
    root.Alpine.data('remotePost', function () {
      return {
        busy: false, said: '', good: false,
        get label() {
          return this.busy ? this.$root.getAttribute('data-busy') : this.$root.getAttribute('data-label');
        },
        get saidClass() { return this.good ? 'remote-said ok' : 'remote-said bad'; },
        go: function () {
          var self = this, el = self.$root;
          if (self.busy) return;
          self.busy = true;
          self.said = '';
          root.fetch(el.getAttribute('data-url'), {
            method: 'POST', headers: {'Content-Type': 'application/json', 'Accept': 'application/json'},
            body: '{}'
          }).then(function (r) {
            return r.json().then(function (b) { return remoteOutcome(el.getAttribute('data-kind'), r.status, b); },
                                 function () { return remoteOutcome(el.getAttribute('data-kind'), r.status, null); });
          }).then(function (o) {
            self.busy = false;
            self.good = o.ok;
            self.said = o.words;
          }, function (e) {
            self.busy = false;
            self.good = false;
            self.said = 'The request did not reach the server (' + e + ')';
          });
        }
      };
    });
  }

  root.NMAS_HISTORY = {remoteOutcome: remoteOutcome};
  if (root.document && root.document.addEventListener) {
    root.document.addEventListener('alpine:init', register);
  }
})(typeof window !== 'undefined' ? window : this);
