/* An early click is kept, never dropped (C399; the operator, 2026-10-03: "the first click on
   Restore from… did nothing").

   A v2 page's controls get their behaviour from deferred scripts: htmx (hx-*) and Alpine
   (x-on:*), Alpine the last of eleven. The page is on screen before they run, so a click in
   that window landed on a control with no behaviour yet and did nothing. This file is loaded
   synchronously in the head, before the body: it keeps such a click, marks the control busy
   on itself, and replays it once Alpine has started and the document has loaded (htmx
   processes the page then). A link with an href is left alone: without script it opens its
   page, which is its no-script behaviour. Once the scripts are ready this does nothing. */
(function (root) {
  'use strict';
  var doc = root.document;
  var alpine = false, loaded = doc.readyState !== 'loading', pending = null;
  // A control whose click needs a deferred script: Alpine's click handler, or an htmx request
  // on an element with nowhere to go without script.
  var NEEDS = '[x-on\\:click], [hx-get]:not([href]), [hx-post]:not([href])';

  function ready() { return alpine && loaded && !!root.htmx; }

  function replay() {
    if (!pending || !alpine || !loaded) { return; }
    // After every other DOMContentLoaded handler (htmx's processes the page in one).
    root.setTimeout(function () {
      var el = pending;
      pending = null;
      if (!el || !doc.contains(el)) { return; }
      el.removeAttribute('aria-busy');
      el.click();
    }, 0);
  }

  doc.addEventListener('click', function (e) {
    if (ready() || !e.target || !e.target.closest) { return; }
    var el = e.target.closest(NEEDS);
    if (!el) { return; }
    e.preventDefault();
    e.stopPropagation();
    pending = el;
    el.setAttribute('aria-busy', 'true');
  }, true);
  doc.addEventListener('alpine:initialized', function () { alpine = true; replay(); });
  doc.addEventListener('DOMContentLoaded', function () { loaded = true; replay(); });
}(window));
