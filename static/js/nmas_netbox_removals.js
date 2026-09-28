/* NetBox removals: the result of a Remove, and the record read back (C121).

   A Remove's toast said "Removed N object(s)" in green whenever the request
   succeeded, including when NetBox refused some deletes, and nothing recorded
   a removal at all. The result is drawn by the result component from the
   recorded row, so the screen at apply and the record read back later are one
   computation; its colour comes from the server's level. */
(function (root) {
  function esc(s) {
    return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  /* Pure: the removals panel for one /netbox/safety/removals payload. A
     failed read is never drawn as "none recorded". */
  function netboxRemovalsHtml(d) {
    if (!d || d.ok !== true) {
      return '<div class="alert alert-warning py-2 px-3 small" data-nb-removals="unknown">'
        + '<strong>The removal record could not be read</strong>'
        + (d && d.error ? ': ' + esc(d.error) : '') + '. This is not the same as no '
        + 'removal having happened.</div>';
    }
    var rows = d.removals || [];
    if (!rows.length) {
      return '<div class="small text-muted" data-nb-removals="none">No NetBox removal has '
        + 'been recorded' + (d.state === 'absent' ? ' (the record has never been written)' : '')
        + '.</div>';
    }
    return rows.map(function (row, i) {
      var r = row.result || {};
      var head = esc(row.at) + ' by ' + esc(row.by || 'an unrecorded actor') + ': '
        + esc(((r.happened || {}).summary) || '');
      return i === 0
        ? '<div class="mb-2" data-nb-removal="latest"><div class="small fw-semibold mb-1">Latest: '
          + head + '</div>' + (typeof previewConfirmResultHtml === 'function'
            ? previewConfirmResultHtml(r, {}) : '') + '</div>'
        : '<div class="small" data-nb-removal="earlier">' + head + '</div>';
    }).join('');
  }

  async function loadNetboxRemovals() {
    var el = document.getElementById('netboxRemovalsPanel');
    if (!el) return;
    var d;
    try {
      d = await (await fetch('/netbox/safety/removals', {cache: 'no-store'})).json();
    } catch (e) {
      d = {ok: false, error: e.message};
    }
    el.innerHTML = netboxRemovalsHtml(d);
  }

  /* The result of a Remove the operator just confirmed, in its own modal. */
  function showNetboxRemovalResult(result) {
    var el = document.createElement('div');
    el.className = 'modal fade';
    el.tabIndex = -1;
    el.innerHTML = '<div class="modal-dialog modal-lg modal-dialog-scrollable"><div class="modal-content">'
      + '<div class="modal-header"><h5 class="modal-title">NetBox removal</h5>'
      + '<button type="button" class="btn-close" data-bs-dismiss="modal"></button></div>'
      + '<div class="modal-body">' + previewConfirmResultHtml(result, {}) + '</div>'
      + '<div class="modal-footer"><button type="button" class="btn btn-secondary" '
      + 'data-bs-dismiss="modal">Close</button></div></div></div>';
    el.addEventListener('hidden.bs.modal', function () { el.remove(); });
    document.body.appendChild(el);
    new bootstrap.Modal(el).show();
    showToast(((result || {}).happened || {}).summary || 'Removal finished',
              previewConfirmResultLevel(result));
  }

  root.netboxRemovalsHtml = netboxRemovalsHtml;
  root.loadNetboxRemovals = loadNetboxRemovals;
  root.showNetboxRemovalResult = showNetboxRemovalResult;
  if (typeof document !== 'undefined' && document.addEventListener) {
    document.addEventListener('DOMContentLoaded', function () {
      if (root.NMAS && root.NMAS.subscribe) {
        root.NMAS.subscribe('netbox', 'netboxRemovals', loadNetboxRemovals,
                            {panel: 'netboxRemovalsPanel'});
      }
    });
  }
})(typeof window !== 'undefined' ? window : this);
