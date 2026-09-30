/* The Update button's page (modules/update_op.py; docs/UPDATE.md).
 *
 * Confirm posts the preview's hash; the app writes a request and the
 * root-owned updater does the rest. The page then waits on FACTS, never a
 * timer: /health's commit, and the updater's own record (/update/status). A
 * terminal outcome reloads the page, which draws "The last update".
 *
 * ES5, Alpine's CSP build (getters and argument-free methods only). The
 * waiting logic is `waitState`, PURE, executed in duktape by
 * tests/test_update_button.py.
 */
(function (root) {
  'use strict';

  var TERMINAL = ['updated', 'refused', 'rolled_back', 'rollback_failed', 'failed'];

  /* PURE. What the waiting page says and whether it reloads, from what it
     last read. *health*: /health's body or null (the app is restarting);
     *status*: /update/status's body or null; *id*: the request made here. */
  function waitState(target, id, health, status, elapsedS, timeoutS) {
    var s = Math.round(elapsedS);
    var o = status && status.outcome && status.outcome.state === 'ok' ? status.outcome.value : null;
    var mine = o && o.id === id;
    if (mine && TERMINAL.indexOf(o.outcome) >= 0) {
      var words = (status.outcome_words && status.outcome_words[o.outcome]) || o.outcome;
      return {reload: true, stop: true, words: 'The updater finished: ' + words + '. Reloading…'};
    }
    if (health && health.commit === target) {
      return {reload: true, stop: true,
              words: 'The app runs ' + String(target).slice(0, 10) + ' now. Reloading…'};
    }
    if (s >= timeoutS) {
      return {reload: false, stop: true,
              words: 'The updater has not reported in ' + Math.round(timeoutS / 60) + ' min, its '
                + 'unit\'s own limit. On the host: journalctl -u nmas-update.service -n 50'};
    }
    if (mine && o.outcome === 'running') {
      return {reload: false, stop: false,
              words: 'The updater is ' + (o.step || 'running') + ' (' + s + ' s)…'};
    }
    if (!health) {
      return {reload: false, stop: false,
              words: 'The app is restarting; waiting for it to answer (' + s + ' s)…'};
    }
    var queued = status && status.pending && status.pending.length;
    return {reload: false, stop: false,
            words: (queued ? 'Requested; waiting for the updater to take it'
                    : 'Waiting for the updater') + ' (' + s + ' s)…'
              + (queued && s >= 60 ? ' It has not started in a minute: is nmas-update.path '
                 + 'active on the host (Job health says)?' : '')};
  }

  function getJson(url) {
    return root.fetch(url, {headers: {'Accept': 'application/json'}, cache: 'no-store'})
      .then(function (r) { return r.ok ? r.json() : null; }, function () { return null; })
      .then(function (b) { return b; }, function () { return null; });
  }

  function register() {
    var A = root.Alpine;
    A.data('update', function () {
      return {
        phase: 'idle', words: '', started: 0,
        get idle() { return this.phase === 'idle'; },
        get waiting() { return this.phase !== 'idle'; },
        get blocked() { return this.$el.getAttribute('data-selectable') !== 'yes'; },
        confirm: function () {
          var self = this, el = this.$el;
          var boxes = root.document.querySelectorAll('input[data-host-step]');
          var ack = [];
          for (var i = 0; i < boxes.length; i++) {
            if (boxes[i].checked) ack.push(boxes[i].getAttribute('data-host-step'));
          }
          self.phase = 'asking';
          self.words = 'Asking the updater…';
          root.fetch(el.getAttribute('data-apply-url'), {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({hash: el.getAttribute('data-hash'), acknowledged: ack})
          }).then(function (r) { return r.json().then(function (b) { return [r.status, b]; }); })
            .then(function (got) {
              if (got[0] !== 202) {
                self.words = 'Not requested: ' + ((got[1] && got[1].error) || ('HTTP ' + got[0]));
                return;
              }
              self.phase = 'waiting';
              self.started = Date.now();
              self.poll(el.getAttribute('data-target'), got[1].id);
            }, function (e) { self.words = 'Not requested: ' + e.message; });
        },
        poll: function (target, id) {
          var self = this, el = this.$el;
          var timeout = parseInt(el.getAttribute('data-timeout'), 10) || 900;
          Promise.all([getJson(el.getAttribute('data-health-url')),
                       getJson(el.getAttribute('data-status-url'))]).then(function (got) {
            var st = waitState(target, id, got[0], got[1], (Date.now() - self.started) / 1000,
                               timeout);
            self.words = st.words;
            if (st.reload) { root.setTimeout(function () { root.location.reload(); }, 1200); }
            else if (!st.stop) { root.setTimeout(function () { self.poll(target, id); }, 2000); }
          });
        }
      };
    });
    // "Check again": ask origin and CI now instead of at the reader's next run.
    A.data('check', function () {
      return {
        busy: false,
        get label() { return this.busy ? 'Checking…' : 'Check again'; },
        run: function () {
          var self = this;
          self.busy = true;
          root.fetch(this.$el.getAttribute('data-url'), {method: 'POST'})
            .then(function () { root.setTimeout(function () { self.busy = false; }, 5000); },
                  function () { self.busy = false; });
        }
      };
    });
  }

  if (root.document && root.document.addEventListener) {
    root.document.addEventListener('alpine:init', register);
  }
  root.NMAS_UPDATE = {waitState: waitState, TERMINAL: TERMINAL};
})(typeof window !== 'undefined' ? window : this);
