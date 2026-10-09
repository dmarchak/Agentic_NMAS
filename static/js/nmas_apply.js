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
 *
 * Also `ipslaPost`, Monitoring > IP SLA's two buttons (P.9 d4): commit the
 * policy, or commit the ticked suggested probes to intent and go to the
 * batch Apply scoped to IP SLA lines. Busy on itself; a refusal is said
 * beside it in the server's words. `ipslaBody` and `ipslaOutcome` are PURE,
 * executed in duktape by tests/test_ip_sla_policy.py.
 *
 * Also `coverageSelect`, Monitoring > Coverage's selection (artboard A): the row boxes
 * feed this Apply. The bar above the grid names the devices ticked and how many missing
 * templates the profile supplies for them, recounted on each change; the header box ticks
 * every device that has one, and Clear unticks them. `coverageWords` is PURE, executed in
 * duktape by tests/test_coverage_grid.py.
 *
 * Also `deviceSelect`, the Devices page's selection (C593, board A): the same selection, its
 * bar naming the devices ticked and its Actions menu counting them ("Save (3)…").
 * `deviceWords` is PURE, executed in duktape by tests/test_save_v2.py.
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

  /* PURE. The IP SLA page's POST body (P.9 d4): the server-drawn *base* (a
     JSON string), the policy fields the form holds (each "" when absent),
     and the keys of the ticked suggestions. */
  function ipslaBody(base, policy, frequency, picked) {
    var b = base ? JSON.parse(base) : {};
    if (policy) b.policy = policy;
    if (frequency) b.frequency = frequency;
    if (picked) b.picked = picked;
    return JSON.stringify(b);
  }

  /* PURE. What the IP SLA page does with an answer: go to the scoped batch
     Apply the server names, redraw (a policy committed), or say why not. */
  function ipslaOutcome(status, body) {
    if (status === 200 && body && body.ok) return {go: body.url || '', reload: !body.url, error: ''};
    var why = body && body.error ? body.error : 'refused (HTTP ' + status + ')';
    return {go: '', reload: false, error: why};
  }

  /* PURE. The selection bar's words: *names* the ticked devices, *missing* the templates the
     profile supplies for them, summed. */
  function coverageWords(names, missing) {
    var n = names.length;
    return {summary: n + ' device' + (n === 1 ? '' : 's') + ' selected',
            detail: '· ' + names.join(', ') + ' · ' + missing + ' missing template' +
                    (missing === 1 ? '' : 's')};
  }

  /* Once the confirm has started the batch (C602, the operator's Coverage walk, 2026-10-09):
     it runs in the order confirmed, so nothing on the preview may plan again. Every control in
     the preview's form is disabled with the reason on its hover, and the note says so. A move
     clicked then had re-planned the preview for 3 to 6 s with nothing showing, and could not
     reach the running batch. Returns how many controls it locked. */
  function lockPreview(doc) {
    var form = doc && doc.getElementById ? doc.getElementById('apply-form') : null;
    if (!form) return 0;
    var why = 'The batch is running in the order you confirmed: a change here cannot reach it';
    var all = form.querySelectorAll('button, input, select, textarea'), n = 0;
    for (var i = 0; i < all.length; i++) {
      if (all[i].type === 'hidden' || all[i].id === 'apply-confirm') continue;
      all[i].disabled = true;
      all[i].setAttribute('title', why);
      n++;
    }
    var note = doc.getElementById('apply-locked');
    if (note) note.hidden = false;
    return n;
  }

  /* PURE. The Devices page's selection words: *names* the ticked devices; the menu's count. */
  function deviceWords(names) {
    var n = names.length, shown = names.slice(0, 8).join(', ');
    return {summary: n + ' selected',
            detail: '· ' + shown + (n > 8 ? ' and ' + (n - 8) + ' more' : ''),
            count: '(' + n + ')'};
  }

  function register() {
    root.Alpine.data('deviceSelect', function () {
      return {
        names: [],
        init: function () { this.recount(); },
        boxes: function () {
          return Array.prototype.slice.call(this.$root.querySelectorAll('input[name=device]'));
        },
        recount: function () {
          var all = this.boxes(), names = [];
          for (var i = 0; i < all.length; i++) if (all[i].checked) names.push(all[i].value);
          this.names = names;
        },
        clear: function () {
          var all = this.boxes();
          for (var i = 0; i < all.length; i++) all[i].checked = false;
          this.recount();
        },
        get nonePicked() { return !this.names.length; },
        get summary() { return deviceWords(this.names).summary; },
        get detail() { return deviceWords(this.names).detail; },
        get count() { return deviceWords(this.names).count; }
      };
    });
    root.Alpine.data('coverageSelect', function () {
      return {
        names: [], missing: 0,
        init: function () { this.recount(); },
        boxes: function () {
          return Array.prototype.slice.call(this.$root.querySelectorAll('input[name=device]'));
        },
        recount: function () {
          var all = this.boxes(), names = [], missing = 0;
          for (var i = 0; i < all.length; i++) {
            if (!all[i].checked) continue;
            names.push(all[i].value);
            missing += parseInt(all[i].getAttribute('data-missing'), 10) || 0;
          }
          this.names = names;
          this.missing = missing;
          var head = this.$refs.all;
          if (head) {
            head.checked = !!all.length && names.length === all.length;
            head.indeterminate = !!names.length && names.length < all.length;
          }
        },
        pickAll: function () {
          var on = !!(this.$refs.all && this.$refs.all.checked), all = this.boxes();
          for (var i = 0; i < all.length; i++) all[i].checked = on;
          this.recount();
        },
        clear: function () {
          var all = this.boxes();
          for (var i = 0; i < all.length; i++) all[i].checked = false;
          this.recount();
        },
        get nonePicked() { return !this.names.length; },
        get summary() { return coverageWords(this.names, this.missing).summary; },
        get detail() { return coverageWords(this.names, this.missing).detail; }
      };
    });
    root.Alpine.data('ipslaPost', function () {
      return {
        busy: false, error: '',
        get hasError() { return !!this.error; },
        get label() {
          return this.busy ? this.$root.getAttribute('data-busy')
                           : this.$root.getAttribute('data-label');
        },
        post: function () {
          var self = this, el = self.$root;
          if (self.busy) return;
          var sel = el.querySelector('select[name=policy]');
          var freq = el.querySelector('input[name=frequency]');
          var boxes = el.querySelectorAll('input[name=pick]');
          var picked = null;
          if (boxes.length) {
            picked = [];
            for (var i = 0; i < boxes.length; i++) if (boxes[i].checked) picked.push(boxes[i].value);
          }
          self.busy = true;
          self.error = '';
          root.fetch(el.getAttribute('data-url'), {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'Accept': 'application/json'},
            body: ipslaBody(el.getAttribute('data-body'), sel ? sel.value : '',
                            freq ? freq.value : '', picked)
          }).then(function (r) {
            return r.json().then(function (b) { return ipslaOutcome(r.status, b); },
                                 function () { return ipslaOutcome(r.status, null); });
          }).then(function (o) {
            if (o.go) { root.location.assign(o.go); return; }
            if (o.reload) { root.location.reload(); return; }
            self.busy = false;
            self.error = o.error;
          }, function (e) {
            self.busy = false;
            self.error = 'Nothing was committed: the request did not reach the server (' + e + ')';
          });
        }
      };
    });
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
            if (o.started) lockPreview(root.document);
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
  root.NMAS_APPLY = {confirmOutcome: confirmOutcome, ipslaBody: ipslaBody,
                     ipslaOutcome: ipslaOutcome, coverageWords: coverageWords,
                     deviceWords: deviceWords};
})(typeof window !== 'undefined' ? window : this);
