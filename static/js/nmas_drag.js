/* One guard for anything a person drags on a v2 page (C882; the operator's walk W1, 2026-10-16).

   Measured in a real browser: Topology's map region redraws itself whole when `topology` is
   announced (any person's move, the reader's minute) and when a move's save answers. A redraw
   that landed while a device was being dragged replaced the map under the pointer: the device
   jumped back to its saved place, the drag went on moving the replaced map (detached, its screen
   offset lost, so the pointer read some 360 map units off), and the drop saved that far place for
   everyone, recorded. Two rules, one home, for the map and for any draggable list (C905, the
   rollout order):

   - while a pointer is down on a held region, no swap is applied to it, to anything inside it, or
     to anything holding it: no incoming position reaches the dragged item or the rest. When the
     pointer comes up, a drop whose own request redraws the region (a save) needs nothing more;
     otherwise the region asks once again for what it set aside (its hx-get).
   - a drop is refused when where it would land is more than *limit* from where the pointer says
     it should land (`far`, pure): the caller says so in place and saves nothing.

   Interface (window.NMAS_DRAG):
     hold(region, pointerId) -> a hold        the pointer went down on *region*
     release(hold, answered) -> 'asked'|''    the pointer came up; *answered*: the drop's own
                                              request redraws the region (no second ask)
     holding(el) -> bool                      is *el* inside, or holding, a held region
     stillThere(hold) -> bool                 is the held region still on the page
     far(landed, wanted, limit) -> null | {by, limit}   PURE: the largest difference on any
                                              axis (a map's x and y, a list's index), when it is
                                              more than *limit*
   Strict CSP: no inline handler; listeners on the document. */
(function (root) {
  'use strict';

  var holds = [];

  /* PURE: null when *landed* is within *limit* of *wanted* on every axis, else how far it is.
     Per axis, not the straight-line distance: a pointer between two grid points lands on either
     one, a full step away on each axis at worst. */
  function far(landed, wanted, limit) {
    var by = 0;
    for (var i = 0; i < wanted.length; i++) by = Math.max(by, Math.abs(landed[i] - wanted[i]));
    return by > limit ? {by: Math.round(by), limit: limit} : null;
  }

  function hold(region, pointerId) {
    var h = {region: region, pointerId: pointerId, deferred: null};
    holds.push(h);
    return h;
  }

  function covers(h, el) {
    return !!(el && el.contains && (el === h.region || el.contains(h.region) ||
                                    h.region.contains(el)));
  }

  function holding(el) {
    for (var i = 0; i < holds.length; i++) if (covers(holds[i], el)) return true;
    return false;
  }

  function stillThere(h) {
    return !!(h && h.region && h.region.isConnected);
  }

  /* The region asks again for what it set aside: the element the set-aside answer was for,
     by its own hx-get, as the live path would have. An element with none cannot be asked. */
  function askAgain(el) {
    var url = el && el.isConnected && el.getAttribute && el.getAttribute('hx-get');
    if (!url || !root.htmx) return false;
    root.htmx.ajax('GET', url, {target: el, swap: el.getAttribute('hx-swap') || 'outerHTML'});
    return true;
  }

  function release(h, answered) {
    var i = holds.indexOf(h);
    if (i < 0) return '';
    holds.splice(i, 1);
    if (!h.deferred || answered) return '';
    // Another hold on the same region (a second pointer) keeps it set aside.
    for (var j = 0; j < holds.length; j++) {
      if (holds[j].region === h.region) { holds[j].deferred = h.deferred; return ''; }
    }
    return askAgain(h.deferred) ? 'asked' : '';
  }

  /* Before any swap (an answer, an announcement's redraw, an out-of-band part): one that would
     replace a held region, or anything in it, is set aside. Registered after nmas_v2.js's own
     (this script loads after it), so it has the last word. */
  function setAside(e) {
    var d = e.detail;
    if (!d || !d.shouldSwap || !holds.length) return;
    var target = d.target;
    for (var i = 0; i < holds.length; i++) {
      if (covers(holds[i], target)) {
        d.shouldSwap = false;
        holds[i].deferred = target;
      }
    }
  }

  /* A pointer that came up with its hold still taken (its owner lost track of it) releases it
     here, after every document listener has run, so a region is never held for good. */
  function sweep(e) {
    holds.slice().forEach(function (h) {
      if (h.pointerId === e.pointerId) release(h, false);
    });
  }

  if (root.document && root.document.addEventListener) {
    root.document.addEventListener('htmx:beforeSwap', setAside);
    root.document.addEventListener('htmx:oobBeforeSwap', setAside);
  }
  if (root.addEventListener) {
    root.addEventListener('pointerup', sweep);
    root.addEventListener('pointercancel', sweep);
  }
  root.NMAS_DRAG = {hold: hold, release: release, holding: holding, stillThere: stillThere,
                    far: far};
}(typeof window !== 'undefined' ? window : this));
