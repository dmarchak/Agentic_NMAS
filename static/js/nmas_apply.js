/* The batch Apply's page (P.9 step d2; routes/v2.py).
 *
 * THE CONFIRM IS NOT HERE (C850, Stage 7 acceptance criterion 6): the batch
 * Apply, Coverage's Deploy missing and History's Re-apply post their confirm
 * with htmx (the one pattern), the body the server drew from the hashes on
 * the screen, and the server answers with the batch's card in #apply-result
 * and the confirm drawn again as started. What stays here is `lockPreview`
 * (C602), run when that answer says the batch started (`lockOnStart`), and its
 * notes drawn only while that batch runs, then once it has ended (`syncLock`,
 * C883). And the rollout order, kept in the page (C888: Earlier, Later and the
 * grip's drag, C905, plan nothing), which the confirm sends as the list shows
 * it (`confirmOrder`). `lockNote`, `moved`, `slotFor`, `confirmOrder` and
 * `movedWords` are PURE, executed in duktape by tests/test_profile_apply_v2.py.
 *
 * ES5, Alpine's CSP build: getters and argument-free methods only, every
 * data-* attribute read from `$root` (the x-data element; C243's rule).
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
 * bar naming the devices ticked and its Actions menu counting them ("Save (3)…"); its head box
 * ticks every row shown, and with all of them ticked the form carries ALL MATCHING (the search
 * and filters, never the names). `deviceWords` is PURE, executed in duktape by
 * tests/test_save_v2.py and tests/test_devices_select_all.py.
 */
(function (root) {
  'use strict';

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

  /* PURE. Which note the preview draws (C883): none until a batch confirmed from it started
     (*locked*), then 'running' while its job card says so, else 'ended'. Before C883 the
     running note was drawn on every preview: `.notice`'s display beat `hidden`. */
  function lockNote(locked, running) {
    if (!locked) return '';
    return running ? 'running' : 'ended';
  }

  var LOCK_WHY = {
    running: 'The batch is running in the order you confirmed: a change here cannot reach it',
    ended: 'The batch confirmed here has ended: open this page again to plan another'
  };

  /* The notes and the controls' hover words, from the state as the page holds it now: the
     preview locked by a started batch (`data-locked`, set once, by lockPreview) and the job
     card in #apply-result (`data-job`, running while it carries `data-running`). Run on every
     swap, so the note follows the card as it redraws. Returns the note shown. */
  function syncLock(doc) {
    var form = doc && doc.getElementById ? doc.getElementById('apply-form') : null;
    var card = doc && doc.querySelector ? doc.querySelector('#apply-result [data-job]') : null;
    var which = lockNote(!!(form && form.hasAttribute('data-locked') && card),
                         !!(card && card.hasAttribute('data-running')));
    var running = doc && doc.getElementById ? doc.getElementById('apply-locked') : null;
    var ended = doc && doc.getElementById ? doc.getElementById('apply-ended') : null;
    if (running) running.hidden = which !== 'running';
    if (ended) ended.hidden = which !== 'ended';
    if (which) {
      var all = form.querySelectorAll('button, input, select, textarea');
      for (var i = 0; i < all.length; i++) {
        if (all[i].type === 'hidden' || all[i].id === 'apply-confirm') continue;
        all[i].setAttribute('title', LOCK_WHY[which]);
      }
    }
    return which;
  }

  /* Once the confirm has started the batch (C602, the operator's Coverage walk, 2026-10-09):
     it runs in the order confirmed, so nothing on the preview may plan again or move. Every
     control in the preview's form is disabled with the reason on its hover, and the note says
     so. A move clicked then had re-planned the preview for 3 to 6 s with nothing showing, and
     could not reach the running batch. Returns how many controls it locked. */
  function lockPreview(doc) {
    var form = doc && doc.getElementById ? doc.getElementById('apply-form') : null;
    if (!form) return 0;
    var all = form.querySelectorAll('button, input, select, textarea'), n = 0;
    for (var i = 0; i < all.length; i++) {
      if (all[i].type === 'hidden' || all[i].id === 'apply-confirm') continue;
      all[i].disabled = true;
      n++;
    }
    form.setAttribute('data-locked', '');
    form.classList.add('apply-locked-form');
    syncLock(doc);
    return n;
  }

  /* The confirm's answer swapped into #apply-result (C850): 202 is the batch started, so the
     preview is locked (C602). A refusal (400) locks nothing: the person may plan again. PURE
     over the event's detail: whether this swap started a batch. */
  function startedBatch(d) {
    return !!(d && d.target && d.target.id === 'apply-result' && d.xhr && d.xhr.status === 202);
  }
  function lockOnStart(e) {
    if (startedBatch(e.detail)) lockPreview(root.document);
    else syncLock(root.document);
  }

  /* ------------------------------------------------ the rollout order (C888, C905)
   *
   * The order is kept in the page: no device's program or hash depends on its place in it
   * (routes.deploy.plan_devices plans each device alone; its command hash is its program,
   * reasons and removals), so a move plans nothing. Earlier and Later move a row; the grip
   * drags one (the shared guard, nmas_drag.js, holds the preview from every swap while the
   * pointer is down). A move reorders what the person reads with the list: each device's
   * section and its number, and the form's devices, so a Leave out or a ticked line plans in
   * the order shown. The confirm sends the list as drawn when pressed (`confirmOrder`), and
   * the route refuses an order that is not exactly the devices confirmed. */

  /* PURE. *names* with the one at *from* moved to *to* (both indexes in *names*). */
  function moved(names, from, to) {
    var out = names.slice(), it = out.splice(from, 1)[0];
    out.splice(Math.max(0, Math.min(to, out.length)), 0, it);
    return out;
  }

  /* PURE. Where a dragged row lands: how many of the OTHER rows' middles (*mids*, top to
     bottom, in px) are above the pointer's *y*. */
  function slotFor(mids, y) {
    var n = 0;
    for (var i = 0; i < mids.length; i++) if (mids[i] < y) n++;
    return n;
  }

  /* PURE. The confirm's order: the devices *confirmed* (the server's, from the hashes it
     drew), in the order *shown* (the list as drawn). A confirmed device the list does not
     show is left out here, so the route's check (exactly the devices confirmed) refuses it
     rather than this guessing a place for it. */
  function confirmOrder(shown, confirmed) {
    var out = [];
    for (var i = 0; i < shown.length; i++) {
      if (confirmed.indexOf(shown[i]) >= 0 && out.indexOf(shown[i]) < 0) out.push(shown[i]);
    }
    return out;
  }

  /* PURE. A move in words, for a screen reader (and a refused drop for everyone). */
  function movedWords(name, at, of, was) {
    if (at === was) return name + ' stays at ' + (at + 1) + ' of ' + of + '.';
    return name + ' moved to ' + (at + 1) + ' of ' + of + '.';
  }

  function rows(doc) {
    var list = doc.getElementById('rollout');
    return list ? Array.prototype.slice.call(list.querySelectorAll('li[data-device]')) : [];
  }
  function namesOf(items) {
    return items.map(function (li) { return li.getAttribute('data-device'); });
  }
  function locked(doc) {
    var form = doc.getElementById('apply-form');
    return !form || form.hasAttribute('data-locked');
  }

  function say(doc, words, refused) {
    var slot = doc.getElementById('rollout-said');
    if (!slot) return;
    slot.className = refused ? 'rollout-said notice notice-danger' : 'rollout-said sr-only';
    slot.setAttribute('role', refused ? 'alert' : 'status');
    slot.textContent = words;
  }

  /* The page in *order*: the list's rows, each device's section and its number, the form's
     device fields (the rest, with nothing to send, after), and Earlier on the first and Later
     on the last disabled. Nothing is asked of the server. */
  function applyOrder(doc, order) {
    var list = doc.getElementById('rollout'), form = doc.getElementById('apply-form');
    if (!list || !form) return;
    var byName = {}, items = rows(doc);
    items.forEach(function (li) { byName[li.getAttribute('data-device')] = li; });
    order.forEach(function (name) { if (byName[name]) list.appendChild(byName[name]); });
    var secs = Array.prototype.slice.call(form.querySelectorAll('section.apply-device[data-device]'));
    if (secs.length) {
      var after = secs[secs.length - 1].nextSibling, parent = secs[0].parentNode, bySec = {};
      secs.forEach(function (s) { bySec[s.getAttribute('data-device')] = s; });
      order.forEach(function (name) { if (bySec[name]) parent.insertBefore(bySec[name], after); });
    }
    Array.prototype.slice.call(form.querySelectorAll('section.apply-device .apply-pos'))
      .forEach(function (pos, i) { pos.textContent = (i + 1) + '.'; });
    var fields = Array.prototype.slice.call(form.querySelectorAll('input[type=hidden][name=device]'));
    if (fields.length) {
      var anchor = fields[fields.length - 1].nextSibling, home = fields[0].parentNode;
      var rest = fields.filter(function (f) { return order.indexOf(f.value) < 0; });
      order.forEach(function (name) {
        for (var i = 0; i < fields.length; i++) {
          if (fields[i].value === name) { home.insertBefore(fields[i], anchor); return; }
        }
      });
      rest.forEach(function (f) { home.insertBefore(f, anchor); });
    }
    var now = rows(doc);
    now.forEach(function (li, i) {
      var up = li.querySelector('button[data-move=up]'), down = li.querySelector('button[data-move=down]');
      if (up) up.disabled = i === 0;
      if (down) down.disabled = i === now.length - 1;
    });
  }

  /* Earlier or Later: one row, one place; the focus stays on the button pressed (or its
     neighbour, when the row reached the end and the button is now disabled). */
  function onMoveClick(e) {
    var btn = e.target && e.target.closest ? e.target.closest('#rollout button[data-move]') : null;
    if (!btn || btn.disabled) return;
    var doc = root.document;
    if (locked(doc)) return;
    var li = btn.closest('li[data-device]'), names = namesOf(rows(doc));
    var name = li.getAttribute('data-device'), from = names.indexOf(name);
    var to = btn.getAttribute('data-move') === 'up' ? from - 1 : from + 1;
    if (to < 0 || to >= names.length) return;
    applyOrder(doc, moved(names, from, to));
    var keep = btn.disabled ? li.querySelector('button[data-move]:not([disabled])') : btn;
    if (keep) keep.focus();
    say(doc, movedWords(name, to, names.length, from), false);
  }

  /* The drag, by the grip; one pointer at a time. */
  var drag = null;

  function midsOf(items, skip) {
    var out = [];
    items.forEach(function (li) {
      if (li === skip) return;
      var r = li.getBoundingClientRect();
      out.push(r.top + r.height / 2);
    });
    return out;
  }

  /* Outside the list: further than half a row from its box, either way. */
  function outside(list, x, y) {
    var r = list.getBoundingClientRect(), pad = 20;
    return x < r.left - pad || x > r.right + pad || y < r.top - pad || y > r.bottom + pad;
  }

  function mark(d, slot, out) {
    var others = rows(root.document).filter(function (li) { return li !== d.li; });
    others.forEach(function (li) { li.classList.remove('rollout-before', 'rollout-after'); });
    d.list.classList.toggle('rollout-out', out);
    if (out || slot === d.from) return;
    if (slot < others.length) others[slot].classList.add('rollout-before');
    else if (others.length) others[others.length - 1].classList.add('rollout-after');
  }

  function endDrag(d) {
    d.li.classList.remove('rollout-dragging');
    d.li.style.transform = '';
    mark(d, d.from, false);
    if (d.grip.releasePointerCapture) {
      try { d.grip.releasePointerCapture(d.pointerId); } catch (err) { /* already released */ }
    }
  }

  /* The hold let go, AFTER the drop's order is in the page: a re-plan's answer set aside while
     held (a reason typed, then the grip pressed) was planned in the old order, so it is asked
     again from the form, which now carries the order shown. */
  function letGo(d) {
    var got = root.NMAS_DRAG ? root.NMAS_DRAG.release(d.hold, false) : '';
    if (got === 'unasked') {
      var form = root.document.getElementById('apply-form');
      if (form && root.htmx && !locked(root.document)) root.htmx.trigger(form, 'change');
    }
  }

  function onGripDown(e) {
    var grip = e.target && e.target.closest ? e.target.closest('#rollout [data-grip]') : null;
    if (!grip || drag || (e.button !== undefined && e.button !== 0)) return;
    var doc = root.document;
    if (locked(doc)) return;
    e.preventDefault();
    var li = grip.closest('li[data-device]'), items = rows(doc);
    var region = doc.getElementById('apply-preview');
    drag = {li: li, grip: grip, list: doc.getElementById('rollout'), pointerId: e.pointerId,
            name: li.getAttribute('data-device'), from: items.indexOf(li), of: items.length,
            y0: e.clientY, shown: items.indexOf(li), out: false,
            hold: root.NMAS_DRAG && region ? root.NMAS_DRAG.hold(region, e.pointerId) : null};
    if (grip.setPointerCapture) grip.setPointerCapture(e.pointerId);
    li.classList.add('rollout-dragging');
    say(doc, 'Moving ' + drag.name + ', at ' + (drag.from + 1) + ' of ' + drag.of +
        ': let go where it should run, or outside the list to leave the order as it is.', false);
  }

  function onGripMove(e) {
    var d = drag;
    if (!d || e.pointerId !== d.pointerId) return;
    d.li.style.transform = 'translateY(' + (e.clientY - d.y0) + 'px)';
    d.out = outside(d.list, e.clientX, e.clientY);
    d.shown = d.out ? d.from : slotFor(midsOf(rows(root.document), d.li), e.clientY);
    mark(d, d.shown, d.out);
  }

  function onGripUp(e) {
    var d = drag;
    if (!d || e.pointerId !== d.pointerId) return;
    drag = null;
    var doc = root.document;
    // Where it lands, read again now from the list on the page, against where the line said.
    var there = d.li.isConnected && d.list.isConnected;
    var out = !there || outside(d.list, e.clientX, e.clientY);
    var landed = out ? d.from : slotFor(midsOf(rows(doc), d.li), e.clientY);
    var off = out ? null : (root.NMAS_DRAG ? root.NMAS_DRAG.far([landed], [d.shown], 0) : null);
    endDrag(d);
    if (!there) {
      letGo(d);
      return;
    }
    if (out) {
      say(doc, d.name + ' was let go outside the list: the order is as it was.', false);
    } else if (off) {
      say(doc, 'Not moved: ' + d.name + ' would have landed at ' + (landed + 1) + ', but the ' +
          'line showed ' + (d.shown + 1) + '; the order is as it was. Drag it again.', true);
    } else {
      var names = namesOf(rows(doc));
      if (landed !== d.from) applyOrder(doc, moved(names, d.from, landed));
      say(doc, movedWords(d.name, landed, names.length, d.from), false);
    }
    letGo(d);
  }

  function onGripCancel(e) {
    var d = drag;
    if (!d || e.pointerId !== d.pointerId) return;
    drag = null;
    endDrag(d);
    say(root.document, d.name + ': the drag was cancelled; the order is as it was.', false);
    letGo(d);
  }

  /* The confirm carries the order the list shows (C888): the one field the page sets. */
  function onConfigRequest(e) {
    var d = e.detail, doc = root.document;
    if (!d || !d.elt || d.elt.id !== 'apply-confirm' || !doc.getElementById('rollout')) return;
    var sent;
    try { sent = JSON.parse(d.parameters.order || '[]'); } catch (err) { sent = []; }
    d.parameters.order = JSON.stringify(confirmOrder(namesOf(rows(doc)), sent));
  }

  /* PURE. The Devices page's selection words: *names* the ticked devices; the menu's count.
     *whole* is 'matching' when every row shown under a search or filter is ticked, 'every'
     when every row of the unfiltered list is, else '' (the selection is the names). */
  function deviceWords(names, whole) {
    var n = names.length, shown = names.slice(0, 8).join(', ');
    var lead = whole === 'matching' ? 'All ' + n + ' matching selected'
             : whole === 'every' ? 'All ' + n + ' selected' : n + ' selected';
    return {summary: lead,
            detail: '· ' + shown + (n > 8 ? ' and ' + (n - 8) + ' more' : ''),
            count: '(' + n + ')'};
  }

  function register() {
    /* The head box ticks every row shown (a pending row has none) and is indeterminate when
       some are. Every row ticked, the selection is ALL MATCHING: the form's `match` and the
       search and filters are enabled and `carry` drops each `device` from the submit, so the
       action resolves the devices itself from them, never from 900 names. */
    root.Alpine.data('deviceSelect', function () {
      return {
        names: [], whole: '',
        init: function () { this.recount(); },
        boxes: function () {
          return Array.prototype.slice.call(this.$root.querySelectorAll('input[name=device]'));
        },
        recount: function () {
          var all = this.boxes(), names = [];
          for (var i = 0; i < all.length; i++) if (all[i].checked) names.push(all[i].value);
          this.names = names;
          var every = !!all.length && names.length === all.length;
          this.whole = !every ? '' : this.$root.hasAttribute('data-filtered') ? 'matching' : 'every';
          var head = this.$refs.all;
          if (head) {
            head.checked = every;
            head.indeterminate = !!names.length && !every;
          }
        },
        pickAll: function () {
          var on = !!(this.$refs.all && this.$refs.all.checked), all = this.boxes();
          for (var i = 0; i < all.length; i++) all[i].checked = on;
          this.recount();
        },
        carry: function (e) {
          if (this.whole && e && e.formData) e.formData.delete('device');
        },
        clear: function () {
          var all = this.boxes();
          for (var i = 0; i < all.length; i++) all[i].checked = false;
          this.recount();
        },
        get partial() { return !this.whole; },
        get nonePicked() { return !this.names.length; },
        get summary() { return deviceWords(this.names, this.whole).summary; },
        get detail() { return deviceWords(this.names, this.whole).detail; },
        get count() { return deviceWords(this.names, this.whole).count; }
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
  }

  if (root.document && root.document.addEventListener) {
    root.document.addEventListener('alpine:init', register);
    root.document.addEventListener('htmx:afterSwap', lockOnStart);
    root.document.addEventListener('htmx:configRequest', onConfigRequest);
    root.document.addEventListener('click', onMoveClick);
    root.document.addEventListener('pointerdown', onGripDown);
    root.document.addEventListener('pointermove', onGripMove);
    root.document.addEventListener('pointerup', onGripUp);
    root.document.addEventListener('pointercancel', onGripCancel);
  }
  root.NMAS_APPLY = {startedBatch: startedBatch, ipslaBody: ipslaBody,
                     ipslaOutcome: ipslaOutcome, coverageWords: coverageWords,
                     deviceWords: deviceWords, lockNote: lockNote, moved: moved,
                     slotFor: slotFor, confirmOrder: confirmOrder, movedWords: movedWords};
})(typeof window !== 'undefined' ? window : this);
