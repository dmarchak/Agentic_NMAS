/* Today's pages' way into the break-glass export (7.3; modules/breakglass_export.py).
 *
 * Board 7 (2026-10-03): the export lives on Credentials. Today's pages still carry openers
 * (data-nmas-open="breakglass_export" with data-nmas-list, and the ?open=breakglass_export
 * link); each is sent there, the export ready, for its list. The modal that ran the preview
 * and the export here, and the /breakglass/preview route it read, left at 7.8 (2026-10-12):
 * nothing opened the modal since Board 7, and Credentials draws the preview itself.
 */
(function (root) {
  'use strict';

  if (typeof document !== 'undefined' && document.addEventListener) {
    document.addEventListener('click', function (e) {
      var b = e.target && e.target.closest && e.target.closest('[data-nmas-open="breakglass_export"]');
      // Board 7 (2026-10-03): every way in opens Credentials, the export ready, for its list.
      if (b) {
        e.preventDefault();
        root.location.assign('/v2/credentials?open=export&list='
                             + encodeURIComponent(b.getAttribute('data-nmas-list') || ''));
      }
    });
    /* ?open=breakglass_export&list=<list>, the link the redesigned pages used (C372: a link
       that only opened a page was a dead end). The list is the link's. */
    document.addEventListener('DOMContentLoaded', function () {
      var q = new URLSearchParams(root.location.search);
      // Board 7 (2026-10-03): the export lives on Credentials; an old link goes there.
      if (q.get('open') === 'breakglass_export') {
        root.location.assign('/v2/credentials?open=export&list='
                             + encodeURIComponent(q.get('list') || ''));
      }
    });
  }
})(typeof window !== 'undefined' ? window : this);
