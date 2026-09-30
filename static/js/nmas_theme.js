/* NMAS theme (the operator, 2026-09-30: a dark mode option). Loaded in the
 * HEAD without defer, so the saved choice is on <html> before the first paint
 * (no flash of the other theme); the strict policy refuses inline script, so
 * it is its own file.
 *
 * Three choices: System (follows the browser's `prefers-color-scheme`, the
 * default), Light and Dark. The choice is a per-browser convenience kept in
 * localStorage; every access is guarded, so a private window or blocked
 * storage simply follows the system. `nmas:theme` is dispatched on the
 * document whenever the EFFECTIVE theme may have changed (a choice, or the
 * system's own switch while on System), so the charts redraw in its colours.
 * ES5: executed in duktape by tests/test_v2_theme.py.
 */
(function (root) {
  'use strict';

  var KEY = 'nmas.theme';
  var CHOICES = ['system', 'light', 'dark'];

  function valid(choice) { return CHOICES.indexOf(choice) >= 0 ? choice : 'system'; }

  function stored() {
    try { return valid(root.localStorage.getItem(KEY)); } catch (e) { return 'system'; }
  }

  function systemDark() {
    try { return !!(root.matchMedia && root.matchMedia('(prefers-color-scheme: dark)').matches); }
    catch (e) { return false; }
  }

  /* PURE: which theme is drawn for a choice, given the system's. */
  function effective(choice, sysDark) {
    choice = valid(choice);
    if (choice === 'system') return sysDark ? 'dark' : 'light';
    return choice;
  }

  function apply(choice) {
    var d = root.document && root.document.documentElement;
    if (!d) return;
    if (valid(choice) === 'system') d.removeAttribute('data-theme');
    else d.setAttribute('data-theme', valid(choice));
  }

  function announce() {
    try {
      var ev = root.document.createEvent('CustomEvent');
      ev.initCustomEvent('nmas:theme', false, false, {theme: effective(stored(), systemDark())});
      root.document.dispatchEvent(ev);
    } catch (e) { /* no event, no redraw: the next load draws right */ }
  }

  function set(choice) {
    choice = valid(choice);
    try { root.localStorage.setItem(KEY, choice); } catch (e) { /* this page only */ }
    apply(choice);
    announce();
    return choice;
  }

  apply(stored());
  try {
    var mq = root.matchMedia && root.matchMedia('(prefers-color-scheme: dark)');
    if (mq && mq.addEventListener) {
      mq.addEventListener('change', function () { if (stored() === 'system') announce(); });
    }
  } catch (e) { /* the system switch is then seen on the next load */ }

  root.NMAS_THEME = {CHOICES: CHOICES, get: stored, set: set, effective: effective,
                     current: function () { return effective(stored(), systemDark()); }};
})(typeof window !== 'undefined' ? window : this);
