// PURE: the /deploy/receipts payload in, HTML out, so the shipped code runs
// in duktape against a real payload. Absent and unreadable are different
// sentences: "nothing recorded yet" is not "the record cannot be read".
function deviceChangesHtml(d) {
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g,
    c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  if (!d || d.ok !== true) {
    return '<div class="alert alert-danger" data-changes-state="unreadable">The receipt '
      + 'record could not be read: ' + esc((d || {}).error || 'no answer')
      + '. This is not the same as no change having been made.</div>';
  }
  if (d.state === 'absent' || !(d.changes || []).length) {
    return '<div class="text-muted small" data-changes-state="none">No deploy or restore '
      + 'has been recorded for ' + esc(d.device || 'this device') + ' in '
      + esc(d.list) + ' yet.</div>';
  }
  return (d.changes || []).map(c =>
    '<details class="mb-2" data-change="' + esc(c.batch_id) + '"><summary class="small">'
    + '<span class="font-monospace">' + esc(c.at) + '</span> '
    + '<strong>' + esc(c.action) + '</strong>'
    + (c.source_ref ? ' from <code>' + esc(c.source_ref) + '</code>' : '')
    + ' by ' + esc(c.actor || 'an unrecorded actor') + '</summary>'
    + previewConfirmResultHtml(c.result, {}) + '</details>').join('');
}

async function loadDeviceChanges() {
  const box = document.getElementById('deviceChangesBody');
  if (!box) return;
  box.innerHTML = '<div class="small text-muted">Reading the receipts…</div>';
  try {
    const r = await fetch('/deploy/receipts?device='
                          + encodeURIComponent(box.dataset.hostname) + '&limit=20');
    box.innerHTML = deviceChangesHtml(await r.json());
  } catch (e) {
    box.innerHTML = deviceChangesHtml({ok: false, error: e.message});
  }
}

document.addEventListener('DOMContentLoaded', function () {
  const tab = document.getElementById('changes-tab');
  if (!tab) return;
  tab.addEventListener('shown.bs.tab', loadDeviceChanges);
  if (tab.classList.contains('active')) loadDeviceChanges();
});
