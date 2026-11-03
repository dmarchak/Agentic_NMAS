/* An early click is kept, never dropped (C399; the operator, 2026-10-03: "the first click on
   Restore from… did nothing"), and an htmx form is never posted by the browser itself (C2217).

   A v2 page's controls get their behaviour from deferred scripts: htmx (hx-*) and Alpine
   (x-on:*), Alpine the last of eleven. The page is on screen before they run, so a click in
   that window landed on a control with no behaviour yet and did nothing. This file is loaded
   synchronously in the head, before the body: it keeps such a click, marks the control busy
   on itself, and replays it once Alpine has started and the document has loaded (htmx
   processes the page then). A link with an href is left alone: without script it opens its
   page, which is its no-script behaviour. Once the scripts are ready this does nothing for a
   click.

   A form's submit is the second case (C2217, measured 2026-11-03: Build again pressed on a
   pack card htmx had swapped in but not yet processed, in htmx's settle delay; the browser
   posted the form itself and the page became the route's bare fragment). A form carrying
   hx-post or hx-get that htmx has not processed (htmx 2.0.11 keeps an element's state at
   elt['htmx-internal-data'], and a processed one has its initHash) is not submitted by the
   browser: its submit is stopped and its submitter (or the form) marked busy on itself; once
   the document has loaded, Alpine has started and htmx is there, htmx processes the form and
   the submitter is clicked again, so htmx sends it in place with the submitter's name and
   value (htmx 2.0.11 learns which button sent a form from a click on it, never from the
   submit event). Before then it is kept, as a click is. A form htmx has processed, and a
   form with no hx-post or hx-get, is never touched. A press inside an htmx form is left to
   the browser by the click keeper, so its submit reaches this one (the form is no control a
   click replays). */
(function (root) {
  'use strict';
  var doc = root.document;
  var alpine = false, loaded = doc.readyState !== 'loading', pending = null, kept = [];
  // A control whose click needs a deferred script: Alpine's click handler, or an htmx request
  // on an element with nowhere to go without script.
  var NEEDS = '[x-on\\:click], [hx-get]:not([href]), [hx-post]:not([href])';
  // A form whose submit is htmx's to send (C2217).
  var HX_FORM = '[hx-post], [hx-get]';
  // What this did, in order, for a test that finds an early click lost (C2234) or a submit
  // posted by the browser (C2217): each click or submit kept, Alpine's start, the load, each
  // replay and what its control then said. Read only by tests; nothing acts on it.
  var steps = root.__nmasEarly = [];
  function step(words) { if (steps.length < 50) { steps.push(words); } }

  function ready() { return alpine && loaded && !!root.htmx; }

  function replay() {
    if (!pending || !alpine || !loaded) { return; }
    // After every other DOMContentLoaded handler (htmx's processes the page in one).
    root.setTimeout(function () {
      var el = pending;
      pending = null;
      if (!el) { step('replay: nothing kept'); return; }
      if (!doc.contains(el)) { step('replay: the control left the page'); return; }
      el.removeAttribute('aria-busy');
      el.click();
      step('replayed');
      root.setTimeout(function () {
        step('after the replay: aria-expanded ' + el.getAttribute('aria-expanded'));
      }, 50);
    }, 0);
  }

  // Whether htmx has processed *form* (htmx 2.0.11: `re(e)` keeps the state at
  // e["htmx-internal-data"], and `Ft(e)` sets its initHash when it initialises the element).
  function bound(form) {
    var d = form['htmx-internal-data'];
    return !!(d && d.initHash);
  }

  function sendOne(form, by) {
    (by || form).removeAttribute('aria-busy');
    if (!doc.contains(form)) { step('submit: the form left the page'); return; }
    if (!root.htmx) { step('submit: htmx is absent once loaded; nothing was sent'); return; }
    root.htmx.process(form);
    if (!bound(form)) { step('submit: htmx did not process the form; nothing was sent'); return; }
    if (by && by.form === form && doc.contains(by)) {
      by.click();
    } else {
      form.requestSubmit();
    }
    step('submit: sent through htmx');
  }

  // Send the kept submits through htmx. Always from a task of its own: a form whose submit
  // event is still being fired is not submitted again (HTML's "firing submission events"),
  // and htmx's own DOMContentLoaded handler processes the page first.
  function send() {
    if (!kept.length || !alpine || !loaded) { return; }
    root.setTimeout(function () {
      var each = kept;
      kept = [];
      for (var i = 0; i < each.length; i++) { sendOne(each[i].form, each[i].by); }
    }, 0);
  }

  doc.addEventListener('click', function (e) {
    if (ready() || !e.target || !e.target.closest) { return; }
    var el = e.target.closest(NEEDS);
    // A press inside an htmx form is the browser's: a submit it makes is kept below (C2217).
    if (!el || el.tagName === 'FORM') { return; }
    e.preventDefault();
    e.stopPropagation();
    pending = el;
    el.setAttribute('aria-busy', 'true');
    step('kept');
  }, true);
  doc.addEventListener('submit', function (e) {
    var form = e.target;
    if (!form || !form.matches || !form.matches(HX_FORM) || bound(form)) { return; }
    // Stopped here, in the capture phase, so this event never reaches a handler htmx adds to
    // the form before it arrives there: one press, one request.
    e.preventDefault();
    e.stopImmediatePropagation();
    // A form already kept is sent once, however often it is pressed meanwhile.
    for (var i = 0; i < kept.length; i++) {
      if (kept[i].form === form) { step('submit: this form already kept'); return; }
    }
    var by = e.submitter || null;
    kept.push({form: form, by: by});
    (by || form).setAttribute('aria-busy', 'true');
    step('submit kept: the form not processed by htmx');
    send();
  }, true);
  doc.addEventListener('alpine:initialized', function () {
    alpine = true; step('alpine started'); replay(); send();
  });
  doc.addEventListener('DOMContentLoaded', function () {
    loaded = true; step('loaded'); replay(); send();
  });
}(window));
