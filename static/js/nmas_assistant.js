/* The toolbar assistant's chat (board assistant-chat; the operator's order of 2026-11-28;
 * templates/v2/_assistant_panel.html, routes/assistant_v2.py). Everything it shows is drawn by
 * the server; this file only:
 *  - sends on Enter and keeps Shift+Enter a new line (while a question is being answered,
 *    Enter sends nothing);
 *  - shows Stop in Send's place while the conversation the server drew holds a turn being
 *    answered (`data-turn-state="working"`), and Send again once none does (`syncAct`);
 *  - grows the box with its text up to MAX_LINES lines, then scrolls inside it;
 *  - keeps the conversation at its newest answer as each one is drawn, unless the person has
 *    scrolled up to read (`nearBottom`);
 *  - empties the box once its question was taken (the press's answer drawn), so the next
 *    question starts blank;
 *  - when the page's address changes without a new page (a tab, Back), sets the panel's page
 *    to the new address and asks the server what it is looking at (routes/assistant_v2.place);
 *  - resizes the panel by its left edge (`[data-asst-resize]`), by pointer or by the arrow
 *    keys, between MIN_W px and MAX_SHARE of the window (`clampWidth`), the width kept in this
 *    browser's localStorage only (read and written in a try: a blocked store keeps the
 *    default), never sent to Mercury.
 *
 * ES5; no inline script or style attribute (the strict policy: the width is a custom property
 * set through the CSSOM). The pure functions are exported on `window.NMAS_ASST`.
 */
(function (root) {
  'use strict';

  var MIN_W = 320;
  var MAX_SHARE = 0.6;
  var STEP_W = 16;
  var MAX_LINES = 8;
  var WIDTH_KEY = 'nmas-asst-width';
  var NEAR_PX = 32;

  /* PURE: a width the panel may take in a window *viewport* px wide: at least MIN_W, at most
     MAX_SHARE of the window (never under MIN_W, and never wider than the window itself). */
  function clampWidth(w, viewport) {
    var max = Math.max(MIN_W, Math.floor(viewport * MAX_SHARE));
    max = Math.min(max, Math.max(0, viewport));
    var min = Math.min(MIN_W, max);
    var n = Math.round(Number(w));
    if (!isFinite(n)) return null;
    return Math.max(min, Math.min(max, n));
  }

  /* PURE: whether a scroller is at (or within NEAR_PX of) its foot. */
  function nearBottom(scrollTop, clientHeight, scrollHeight) {
    return scrollHeight - scrollTop - clientHeight <= NEAR_PX;
  }

  /* PURE: the box's height in px for its content's *scrollHeight*, one line *lineHeight* and
     its padding and border *extra*: at most MAX_LINES lines. ``[height, scrolls]``. */
  function boxHeight(scrollHeight, lineHeight, extra) {
    var max = lineHeight * MAX_LINES + extra;
    return [Math.min(scrollHeight, max), scrollHeight > max];
  }

  function doc() { return root.document; }
  function panel() { return doc().getElementById('asst-panel'); }
  function log() { return doc().getElementById('asst-answer'); }
  function box() { return doc().getElementById('asst-q'); }

  // ── the width ────────────────────────────────────────────────────────────────────────────
  function storedWidth() {
    try { return root.localStorage.getItem(WIDTH_KEY); } catch (e) { return null; }
  }
  function keepWidth(w) {
    try { root.localStorage.setItem(WIDTH_KEY, String(w)); } catch (e) { /* not kept */ }
  }
  /* The window's width the panel is fixed against: the layout viewport, without a page
     scrollbar (the panel's right edge is the scrollbar's left edge). */
  function viewWidth() {
    var d = doc().documentElement;
    return (d && d.clientWidth) || root.innerWidth;
  }
  function currentWidth() {
    var p = panel();
    return p && p.offsetWidth ? p.offsetWidth : 440;
  }
  function applyWidth(w) {
    var c = clampWidth(w, viewWidth());
    if (c === null) return null;
    doc().documentElement.style.setProperty('--asst-w', c + 'px');
    var h = doc().querySelector('[data-asst-resize]');
    if (h) {
      h.setAttribute('aria-valuenow', String(c));
      h.setAttribute('aria-valuemax', String(clampWidth(1e9, viewWidth())));
    }
    return c;
  }
  function restoreWidth() {
    var w = storedWidth();
    if (w !== null && w !== '') applyWidth(w);
  }

  var drag = null;
  function onPointerDown(e) {
    var h = e.target && e.target.closest ? e.target.closest('[data-asst-resize]') : null;
    if (!h || (e.button !== undefined && e.button !== 0)) return;
    e.preventDefault();
    drag = { id: e.pointerId };
    try { h.setPointerCapture(e.pointerId); } catch (x) { /* a mouse without capture */ }
    doc().body.classList.add('asst-resizing');
  }
  function onPointerMove(e) {
    if (!drag) return;
    applyWidth(viewWidth() - e.clientX);
  }
  function onPointerUp() {
    if (!drag) return;
    drag = null;
    doc().body.classList.remove('asst-resizing');
    keepWidth(currentWidth());
  }
  function onHandleKey(e) {
    var w = currentWidth(), next = null;
    if (e.key === 'ArrowLeft') next = w + STEP_W;
    else if (e.key === 'ArrowRight') next = w - STEP_W;
    else if (e.key === 'Home') next = MIN_W;
    else if (e.key === 'End') next = 1e9;
    if (next === null) return;
    e.preventDefault();
    var c = applyWidth(next);
    if (c !== null) keepWidth(c);
  }

  // ── the box ──────────────────────────────────────────────────────────────────────────────
  function grow(b) {
    if (!b) return;
    var cs = root.getComputedStyle(b);
    var lh = parseFloat(cs.lineHeight) || 20;
    var extra = (parseFloat(cs.paddingTop) || 0) + (parseFloat(cs.paddingBottom) || 0) +
      (parseFloat(cs.borderTopWidth) || 0) + (parseFloat(cs.borderBottomWidth) || 0);
    b.style.height = 'auto';
    var got = boxHeight(b.scrollHeight + (parseFloat(cs.borderTopWidth) || 0) +
                        (parseFloat(cs.borderBottomWidth) || 0), lh, extra);
    b.style.height = got[0] + 'px';
    b.style.overflowY = got[1] ? 'auto' : 'hidden';
  }
  function sendButton() {
    var act = doc().getElementById('asst-act');
    if (!act || act.classList.contains('asst-working')) return null;
    return act.querySelector('button[type=submit]');
  }
  /* Send, or Stop in its place: Stop while the conversation the server drew holds a turn
     still being answered (`data-turn-state="working"`), Send once none does. */
  function syncAct() {
    var act = doc().getElementById('asst-act');
    if (!act) return;
    var working = !!doc().querySelector('#asst-answer [data-turn-state="working"]');
    if (working !== act.classList.contains('asst-working')) act.classList.toggle('asst-working', working);
  }
  function onKey(e) {
    var b = e.target;
    if (!b || b.id !== 'asst-q' || e.key !== 'Enter' || e.shiftKey || e.isComposing) return;
    e.preventDefault();
    var send = sendButton();
    if (!send || send.disabled || !b.value.replace(/\s+/g, '')) return;
    var form = b.form;
    if (form && form.requestSubmit) form.requestSubmit(send);
    else if (send) send.click();
  }
  function onInput(e) {
    if (e.target && e.target.id === 'asst-q') grow(e.target);
  }

  // ── the conversation ─────────────────────────────────────────────────────────────────────
  var stick = true;
  function toFoot() {
    var l = log();
    if (l) l.scrollTop = l.scrollHeight;
  }
  function onScroll(e) {
    var l = e.target;
    if (!l || l.id !== 'asst-answer') return;
    stick = nearBottom(l.scrollTop, l.clientHeight, l.scrollHeight);
  }
  function inPanel(el) {
    var p = panel();
    return !!(p && el && el.nodeType === 1 && p.contains(el));
  }
  function onSettle(e) {
    var t = e.target;
    syncAct();
    if (t && t.id === 'asst-body') {
      // The panel drawn (opened, a New conversation, a reopen): at its newest, the box sized.
      stick = true;
      grow(box());
      toFoot();
      return;
    }
    // A turn redrawn in place (its outerHTML swap leaves the event on the new element) or
    // added: kept at the newest unless the person scrolled up.
    if (stick && (inPanel(t) || !t || !t.isConnected)) toFoot();
  }
  function onAfterRequest(e) {
    var elt = e.detail && e.detail.elt;
    if (!elt || elt.id !== 'asst-compose' || !e.detail.successful) return;
    var b = box();
    if (b) { b.value = ''; grow(b); }
    var empty = doc().querySelector('#asst-answer [data-asst-empty]');
    if (empty && empty.parentNode) empty.parentNode.removeChild(empty);
    stick = true;
    toFoot();
  }

  // ── what it is looking at, as the address changes ────────────────────────────────────────
  function onAddress() {
    var p = panel(), form = doc().getElementById('asst-compose');
    if (!p || !form) return;
    var path = root.location.pathname + root.location.search;
    var fields = p.querySelectorAll('input[name=path]');
    for (var i = 0; i < fields.length; i++) fields[i].value = path;
    var nav = form.querySelector('input[name=nav]');
    // Drawn by the server with the page's network already in it (`?list=`, page_network).
    var url = form.getAttribute('data-place-url');
    if (!url || !root.htmx || !doc().getElementById('asst-place')) return;
    var sep = url.indexOf('?') < 0 ? '?' : '&';
    root.htmx.ajax('GET', url + sep + 'path=' + encodeURIComponent(path) + '&nav=' +
                   encodeURIComponent(nav ? nav.value : ''),
                   { target: '#asst-place', swap: 'outerHTML', select: '#asst-place' });
  }

  function wire() {
    var d = doc();
    d.addEventListener('pointerdown', onPointerDown);
    d.addEventListener('pointermove', onPointerMove);
    d.addEventListener('pointerup', onPointerUp);
    d.addEventListener('pointercancel', onPointerUp);
    d.addEventListener('keydown', function (e) {
      if (e.target && e.target.hasAttribute && e.target.hasAttribute('data-asst-resize')) onHandleKey(e);
      else onKey(e);
    });
    d.addEventListener('input', onInput);
    d.addEventListener('scroll', onScroll, true);
    d.addEventListener('htmx:afterSettle', onSettle);
    d.addEventListener('htmx:afterRequest', onAfterRequest);
    d.addEventListener('htmx:pushedIntoHistory', onAddress);
    d.addEventListener('htmx:replacedInHistory', onAddress);
    root.addEventListener('popstate', onAddress);
    root.addEventListener('resize', function () {
      var w = storedWidth();
      if (w !== null && w !== '') applyWidth(w);
    });
  }

  root.NMAS_ASST = { clampWidth: clampWidth, nearBottom: nearBottom, boxHeight: boxHeight,
                     MIN_W: MIN_W, MAX_SHARE: MAX_SHARE, MAX_LINES: MAX_LINES,
                     WIDTH_KEY: WIDTH_KEY };
  if (root.document && root.document.addEventListener) {
    restoreWidth();
    wire();
  }
})(typeof window !== 'undefined' ? window : this);
