/* The Update button's page (modules/update_op.py; docs/UPDATE.md).
 *
 * Every stage is visible (the operator, 2026-09-30, after the first real run
 * failed without a word):
 *   click     the button disables and reads "Sending the request…";
 *   refused   the reason, on the page, and the button back;
 *   accepted  a STEPPER drawn from the updater's own steps (its record names
 *             the step it is on), with the seconds on the step running;
 *   outcome   the last step done or failed with its reason, then a reload
 *             that draws "The last update".
 * It waits on FACTS, never a timer: /health's commit and the updater's record.
 *
 * WIRING, the first run's defect: a component's data-* attributes are read
 * from `$root` (the x-data element). `$el` is the element carrying the
 * directive, so the button's `x-bind:disabled` read `data-selectable` from the
 * button, found nothing, and disabled it: a click that did nothing and said
 * nothing. tests/test_update_button.py holds the rule for every v2 component
 * and clicks the shipped button in a real browser where one is available.
 *
 * ES5, Alpine's CSP build (getters and argument-free methods only). The logic
 * is `stepStates`, PURE, executed in duktape by the tests.
 */
(function (root) {
  'use strict';

  var TERMINAL = ['updated', 'refused', 'rolled_back', 'rollback_failed', 'failed'];

  /* PURE. Each step's state (done, current, failed, pending) and its note,
     from what the page last read. *keys*: the stepper's steps in order, from
     'request' to 'running'; *health*: /health's body or null (restarting);
     *status*: /update/status's body or null; *id*: the request made here. */
  function stepStates(keys, target, id, health, status, elapsedS, timeoutS) {
    var s = Math.round(elapsedS);
    var o = status && status.outcome && status.outcome.state === 'ok' ? status.outcome.value : null;
    var mine = !!(o && o.id === id);
    var words = (status && status.outcome_words) || {};
    var st = {};
    var i;
    for (i = 0; i < keys.length; i++) st[keys[i]] = {state: 'pending', note: ''};
    st.request = {state: 'done', note: ''};
    function upTo(key, state, note) {
      var k = keys.indexOf(key);
      for (var j = 0; j < keys.length; j++) {
        if (j < k) st[keys[j]] = {state: 'done', note: ''};
      }
      if (k >= 0) st[key] = {state: state, note: note || ''};
    }
    // After a failure every later step is NOT REACHED, never a bare pending
    // line: the first real run listed 'Running 4e40bd05b4' under a failure at
    // step 3 with nothing saying it never happened (C246).
    function failAt(key, note) {
      upTo(key, 'failed', 'failed: ' + (note || 'no reason recorded'));
      var k = keys.indexOf(key);
      for (var j = k + 1; j < keys.length; j++) st[keys[j]] = {state: 'not_reached', note: 'not reached'};
    }
    var short = String(target || '').slice(0, 10);
    if (health && health.commit === target && (!mine || o.outcome !== 'rolled_back')) {
      upTo('running', 'done', 'running ' + short);
      return {steps: st, done: true, reload: true, failed: false,
              words: 'Updated: the app runs ' + short + '. Reloading…'};
    }
    if (mine && TERMINAL.indexOf(o.outcome) >= 0) {
      var at = o.step && keys.indexOf(o.step) >= 0 ? o.step : 'started';
      if (o.outcome === 'updated') {
        upTo('running', 'done', 'running ' + short);
        return {steps: st, done: true, reload: true, failed: false,
                words: 'Updated: the app runs ' + short + '. Reloading…'};
      }
      failAt(at, o.reason || '');
      return {steps: st, done: true, reload: false, failed: true,
              words: 'The update ' + (words[o.outcome] || o.outcome) + ': ' + (o.reason || 'no reason recorded')};
    }
    if (s >= timeoutS) {
      failAt(mine && o.step ? o.step : 'started',
           'no word from the updater in ' + Math.round(timeoutS / 60) + ' min, its unit\'s own limit');
      return {steps: st, done: true, reload: false, failed: true,
              words: 'The updater has not reported. On the host: journalctl -u nmas-update.service -n 50'};
    }
    if (mine && o.outcome === 'running') {
      var step = keys.indexOf(o.step) >= 0 ? o.step : 'started';
      upTo(step, 'current', step === 'wait' || step === 'restart' ? s + ' s' : '');
      if (!health && (step === 'restart' || step === 'wait')) {
        st[step].note = 'the app is restarting, ' + s + ' s';
      }
      return {steps: st, done: false, reload: false, failed: false, words: ''};
    }
    if (!health) {
      upTo('wait', 'current', 'the app is restarting, ' + s + ' s');
      return {steps: st, done: false, reload: false, failed: false, words: ''};
    }
    var queued = status && status.pending && status.pending.length;
    upTo('started', 'current', queued && s >= 60
      ? 'not started in a minute: is nmas-update.path active on the host (Job health says)?'
      : (queued ? 'the request is waiting for the updater, ' + s + ' s' : s + ' s'));
    return {steps: st, done: false, reload: false, failed: false, words: ''};
  }

  /* PURE. UPDATE WHEN CI PASSES: what the page does with /update/status while
     it waits. *status*: its body or null; *target*: the release waited for.
     {state: waiting|requested|ended|unknown, id, words}. */
  function waitOutcome(status, target) {
    if (!status) return {state: 'unknown', id: '', words: ''};
    var w = status.waiting || {};
    if (w.target && w.target === target) return {state: 'waiting', id: '', words: ''};
    var e = status.wait_ended || {};
    if (e.target === target && e.outcome === 'requested' && e.request_id) {
      return {state: 'requested', id: e.request_id, words: ''};
    }
    if (e.target === target && e.outcome) {
      return {state: 'ended', id: '', words: 'The wait for CI ended: ' + (e.words || e.outcome) + '.'};
    }
    return {state: 'ended', id: '', words: 'The wait for CI ended, and how is not recorded here: the page shows the release as it is now.'};
  }

  /* Check again's words, PURE (executed in duktape by the tests). */
  function checkLabel(busy) {
    return busy ? 'Checking…' : 'Check again';
  }
  function checkLateWords(bound, basis) {
    return 'No answer after ' + bound + ' s, longer than this check has taken here ('
      + basis + '). It may still be running: this line changes when it answers, '
      + 'and if it does not, the app log names the run ("on request by").';
  }

  function getJson(url) {
    return root.fetch(url, {headers: {'Accept': 'application/json'}, cache: 'no-store'})
      .then(function (r) { return r.ok ? r.json() : null; }, function () { return null; })
      .then(function (b) { return b; }, function () { return null; });
  }

  /* Draw a stepStates() answer into the server-rendered stepper. */
  function drawSteps(list, states) {
    var items = list.querySelectorAll('[data-step]');
    for (var i = 0; i < items.length; i++) {
      var s = states[items[i].getAttribute('data-step')] || {state: 'pending', note: ''};
      items[i].className = 'step step-' + s.state;
      items[i].setAttribute('aria-current', s.state === 'current' ? 'step' : 'false');
      var note = items[i].querySelector('.step-note');
      if (note) note.textContent = s.note ? ' · ' + s.note : '';
    }
  }

  function register() {
    var A = root.Alpine;
    A.data('update', function () {
      return {
        phase: 'idle', words: '', refusal: '', started: 0, stopping: false,
        // A wait recorded before this page loaded: follow it.
        init: function () {
          var el = this.$root;
          if (el.getAttribute('data-waiting') === 'yes') {
            this.phase = 'waiting';
            this.words = el.getAttribute('data-waiting-words') || '';
            this.follow();
          }
        },
        // Read from $root, the x-data element: see the header.
        get blocked() {
          return this.$root.getAttribute('data-selectable') !== 'yes' || this.phase === 'asking';
        },
        get buttonText() {
          return this.phase === 'asking' ? 'Sending the request…' : this.$root.getAttribute('data-label');
        },
        get showButton() { return this.phase === 'idle' || this.phase === 'asking'; },
        get running() { return this.phase === 'running' || this.phase === 'done'; },
        get waiting() { return this.phase === 'waiting'; },
        get stopText() { return this.stopping ? 'Stopping…' : 'Stop waiting'; },
        get refused() { return this.refusal !== ''; },
        // UPDATE WHEN CI PASSES: the wait ends when the app-pushed reader
        // releases it, and that reader ANNOUNCES; the page reads the status on
        // each announcement, never on a timer of its own.
        follow: function () {
          var self = this, el = this.$root;
          el.setAttribute('data-update-hold', 'yes');
          var target = el.getAttribute('data-target');
          function heard() {
            if (self.phase !== 'waiting') return;
            getJson(el.getAttribute('data-status-url')).then(function (st) {
              var r = waitOutcome(st, target);
              if (self.phase !== 'waiting' || r.state === 'waiting' || r.state === 'unknown') return;
              root.document.body.removeEventListener('nmas:app_version', heard);
              if (r.state === 'requested') {
                self.phase = 'running';
                self.words = '';
                self.started = Date.now();
                self.poll(r.id);
              } else {
                self.phase = 'idle';
                self.refusal = r.words;
                el.removeAttribute('data-update-hold');
              }
            });
          }
          root.document.body.addEventListener('nmas:app_version', heard);
        },
        stopWaiting: function () {
          var self = this, el = this.$root;
          self.stopping = true;
          root.fetch(el.getAttribute('data-apply-url'), {
            method: 'POST', headers: {'Content-Type': 'application/json', 'Accept': 'application/json'},
            body: JSON.stringify({when: 'stop'})
          }).then(function (r) {
            return r.json().then(function (b) { return [r.status, b]; }, function () { return [r.status, null]; });
          }).then(function (got) {
            self.stopping = false;
            if (got[0] === 200) { root.location.reload(); return; }
            self.refusal = 'Not stopped: ' + ((got[1] && got[1].error) || ('the server answered HTTP ' + got[0]));
          }, function (e) {
            self.stopping = false;
            self.refusal = 'Not stopped: the request did not reach the app (' + e.message + ')';
          });
        },
        confirm: function () {
          var self = this, el = this.$root;
          // The boxes are drawn in the PREVIEW, above this component: reading
          // them from $root found none, so a ticked box never reached the
          // request (the operator, 2026-09-30, a580660's step). Read them from
          // the preview that holds both.
          var scope = (el.closest && el.closest('#update-preview')) || el;
          var boxes = scope.querySelectorAll('input[data-host-step]');
          var ack = [];
          for (var i = 0; i < boxes.length; i++) {
            if (boxes[i].checked) ack.push(boxes[i].getAttribute('data-host-step'));
          }
          self.phase = 'asking';
          self.refusal = '';
          // HOLD the panel: the request's own answer announces app_version,
          // and a re-fetch would replace this component and wipe what it
          // shows (found by the real-browser test, 2026-09-30).
          el.setAttribute('data-update-hold', 'yes');
          root.fetch(el.getAttribute('data-apply-url'), {
            method: 'POST', headers: {'Content-Type': 'application/json', 'Accept': 'application/json'},
            body: JSON.stringify({hash: el.getAttribute('data-hash'), acknowledged: ack,
                                  when: el.getAttribute('data-when') || ''})
          }).then(function (r) {
            return r.json().then(function (b) { return [r.status, b]; },
                                 function () { return [r.status, null]; });
          }).then(function (got) {
            if (got[0] !== 202) {
              self.phase = 'idle';
              self.refusal = 'Not requested: ' + ((got[1] && got[1].error) || ('the server answered HTTP ' + got[0]));
              return;
            }
            if (got[1] && got[1].waiting) {
              self.phase = 'waiting';
              self.words = got[1].message || '';
              self.follow();
              return;
            }
            self.phase = 'running';
            self.started = Date.now();
            self.poll(got[1].id);
          }, function (e) {
            self.phase = 'idle';
            self.refusal = 'Not requested: the request did not reach the app (' + e.message + ')';
          });
        },
        poll: function (id) {
          var self = this, el = this.$root;
          var timeout = parseInt(el.getAttribute('data-timeout'), 10) || 900;
          var list = el.querySelector('[data-stepper]');
          var keys = [];
          var items = list.querySelectorAll('[data-step]');
          for (var i = 0; i < items.length; i++) keys.push(items[i].getAttribute('data-step'));
          Promise.all([getJson(el.getAttribute('data-health-url')),
                       getJson(el.getAttribute('data-status-url'))]).then(function (got) {
            var r = stepStates(keys, el.getAttribute('data-target'), id, got[0], got[1],
                               (Date.now() - self.started) / 1000, timeout);
            drawSteps(list, r.steps);
            self.words = r.words;
            if (r.done) self.phase = 'done';
            if (r.reload) { root.setTimeout(function () { root.location.reload(); }, 1500); }
            else if (!r.done) { root.setTimeout(function () { self.poll(id); }, 2000); }
          });
        }
      };
    });
    // "It is done": a person says an AFTER host step no check can answer is
    // done. Busy on itself; the panel re-draws from the announcement and the
    // step leaves the list. Words only for a refusal.
    A.data('stepDone', function () {
      return {
        busy: false, said: '',
        get label() { return this.busy ? 'Recording…' : 'It is done'; },
        say: function () {
          var self = this, el = this.$root;
          self.busy = true;
          self.said = '';
          root.fetch(el.getAttribute('data-url'), {
            method: 'POST', headers: {'Content-Type': 'application/json', 'Accept': 'application/json'},
            body: JSON.stringify({sha: el.getAttribute('data-sha'), step: el.getAttribute('data-step')})
          }).then(function (r) {
            return r.json().then(function (b) { return [r.status, b]; }, function () { return [r.status, null]; });
          }).then(function (got) {
            self.busy = false;
            if (got[0] !== 200) self.said = 'Not recorded: ' + ((got[1] && got[1].error) || ('HTTP ' + got[0]));
          }, function (e) { self.busy = false; self.said = 'Not recorded: ' + e.message; });
        }
      };
    });
    // "Check again": ask origin and CI now instead of at the reader's next run.
    // Its attributes are on the element that carries x-data AND x-on.
    //
    // BUSY ON ITSELF, UNTIL THE ANSWER ARRIVES (the operator, 2026-09-30, the
    // rule for every v2 control). The button reads "Checking…" and is
    // disabled; nothing is narrated beside it. The answer arrives as the
    // reader's announcement, which re-draws the panel holding this component,
    // and the row's timestamp then reads "just now": that is the
    // confirmation. The server draws the button busy while the run is owed an
    // answer, so a re-draw mid-run stays busy. Words appear only when the
    // person must act: a refusal, or no answer within the bound (2.5x the
    // slowest recorded run).
    A.data('check', function () {
      return {
        busy: false, said: '',
        init: function () {
          var el = this.$root;
          var running = parseFloat(el.getAttribute('data-running-for'));
          if (running >= 0) this.wait(running, el.getAttribute('data-bound'), el.getAttribute('data-bound-basis'));
        },
        get label() { return checkLabel(this.busy); },
        wait: function (runningFor, bound, basis) {
          var self = this, b = parseFloat(bound);
          self.busy = true;
          self.said = '';
          if (!(b > 0)) return;
          root.setTimeout(function () {
            if (!self.busy) return;
            self.busy = false;
            self.said = checkLateWords(b, basis);
          }, Math.max(0, b - runningFor) * 1000);
        },
        run: function () {
          var self = this;
          self.busy = true;
          self.said = '';
          root.fetch(this.$root.getAttribute('data-url'), {method: 'POST', headers: {'Accept': 'application/json'}})
            .then(function (r) {
              return r.json().then(function (b) { return [r.status, b]; }, function () { return [r.status, null]; });
            })
            .then(function (got) {
              var b = got[1] || {};
              if (got[0] < 300 && b.ok) {
                self.wait(b.running_for || 0, b.bound_seconds, b.bound_basis);
              } else {
                self.busy = false;
                self.said = 'Not asked: ' + (b.error || ('HTTP ' + got[0]));
              }
            }, function (e) { self.busy = false; self.said = 'Not asked: ' + e.message; });
        }
      };
    });
  }

  /* A panel holding an update in flight, its stepper or its refusal is never
     swapped out from under the person reading it. */
  function holdSwap(e) {
    var target = e.detail && e.detail.target;
    if (target && target.querySelector && target.querySelector('[data-update-hold="yes"]')) {
      e.detail.shouldSwap = false;
    }
  }

  if (root.document && root.document.addEventListener) {
    root.document.addEventListener('alpine:init', register);
    root.document.addEventListener('htmx:beforeSwap', holdSwap);
  }
  root.NMAS_UPDATE = {stepStates: stepStates, TERMINAL: TERMINAL, checkLabel: checkLabel,
                      waitOutcome: waitOutcome,
                      checkLateWords: checkLateWords};
})(typeof window !== 'undefined' ? window : this);
