/* ── Remote (Phase 2b) ───────────────────────────────────────────────────── */
/*
   A SEPARATE script element, deliberately.

   A syntax error anywhere in a block kills the whole block, so when a string
   literal in this card spanned a line break the browser discarded the
   Baselines loader with it — and the panel that warns which baselines would
   re-publish dead credentials simply stopped rendering. The newest, least
   important card took out the oldest, most consequential one.

   try/catch cannot help: a parse error happens before any of it runs. Two
   blocks is the only isolation that works, and the caller guards the symbol
   as well, so an absent function is skipped rather than throwing.
*/

/* Publishing a network's history — credentials included — is gated on a
   verified PERSON. The flow is deliberately four steps with a read in the
   middle: verify, preview, acknowledge, push. The acknowledgement names the
   gated kinds, so it is an act of reading rather than of clicking. */
async function loadRemotePanel() {
  const host = document.getElementById('remotePanel');
  if (!host) {
    // Nothing to render into is a defect, not a state. Saying so beats
    // returning quietly, which is how this failed the first time.
    console.error('remotePanel container missing — the card cannot render');
    return;
  }
  try {
    const s = await (await fetch('/remote/status')).json();
    if (!s.configured) {
      host.innerHTML = `
        <div class="alert alert-secondary py-2 px-3 mb-2">
          <strong>No remote for this list.</strong>
          Its history is on this host only.
        </div>`;
      return;
    }
    const ack = s.acknowledged;
    const covers = s.acknowledgement_covers || {};
    const held = ack && !covers.ok;
    host.innerHTML = `
      <div class="card border-light-subtle mb-2"><div class="card-body py-2 px-3">
        <h6 class="text-primary fw-semibold mb-2">Remote
          <span class="text-muted fw-normal small ms-1">${_gEsc(s.owner_repo)}</span>
        </h6>
        <div class="small">
          <div>alias <code>${_gEsc(s.ssh_alias)}</code> ·
               branch <code>${_gEsc(s.branch)}</code> ·
               ${s.managed_by_nmas ? 'managed by NMAS' : 'adopted (NMAS does not edit ~/.ssh/config)'}</div>
          <div>read-only checks: ${s.read_verified_at
                ? `<span class="text-success">${_gEsc(s.read_verified_at)}</span>`
                : '<span class="text-muted">not yet</span>'}</div>
          <div>write probe: ${s.verified_at
                ? `<span class="text-success">${_gEsc(s.verified_at)}</span>`
                : '<span class="text-warning">not yet — required before Push</span>'}</div>
          <div>last push: ${_gLastPush(s.last_push)}</div>
          ${s.last_push_failure ? `<div class="text-danger">push FAILED
                ${_gEsc(s.last_push_failure.at)}: ${_gEsc(s.last_push_failure.reason)}</div>` : ''}
          <div>auto-push: ${s.auto_push
                ? '<span class="badge bg-success-subtle text-success-emphasis">on</span>'
                : '<span class="badge bg-secondary-subtle text-secondary-emphasis">off</span>'}</div>
          ${ack ? `<div class="mt-1">acknowledged ${_gEsc(ack.at)} by
                     <code>${_gEsc(ack.by)}</code> (${_gEsc(ack.by_kind)}) —
                     ${_gEsc((ack.kinds || []).join(', '))}</div>` : ''}
          ${held ? `<div class="alert alert-warning py-1 px-2 mt-2 mb-0 small">
                      <strong>Auto-push HELD.</strong> ${_gEsc(covers.reason || '')}
                      Re-acknowledge to resume.</div>` : ''}
        </div>
        <div class="mt-2 d-flex gap-2 flex-wrap">
          <button class="btn btn-outline-secondary btn-sm" onclick="remoteVerify()">Verify (read-only)</button>
          <button class="btn btn-outline-warning btn-sm" onclick="remoteVerifyWrite()"
                  title="Pushes an orphan commit with an empty tree, then removes the ref. It publishes no content, but it IS a write to the remote.">Write probe…</button>
          <button class="btn btn-outline-secondary btn-sm" onclick="remotePreview()">Preview what would publish</button>
          <button class="btn btn-outline-warning btn-sm" onclick="remoteAcknowledge()">Acknowledge…</button>
          <button class="btn btn-outline-danger btn-sm" onclick="remotePush()"
                  ${(s.verified_at && ack && covers.ok) ? '' : 'disabled'}>Push now</button>
        </div>
      </div></div>`;
    _remoteRestore();
  } catch (e) {
    console.error('loadRemotePanel', e);
    host.innerHTML = `<div class="alert alert-danger py-2 px-3 small mb-0">
      Remote card failed to load: ${_gEsc(String(e && e.message || e))}</div>`;
  }
}

/* The last result, kept so it survives anything that re-renders. Held in
   state as well as in the DOM: the DOM copy is what the operator reads, and
   the state copy is what restores it if some future card rebuilds the page
   around it. */
window._remoteLastResult = null;

function _remoteOut(html, opts) {
  const el = document.getElementById('remoteOut');
  if (!el) { console.error('remoteOut container missing'); return; }
  const transient = !!(opts && opts.transient);
  if (!transient) {
    const when = new Date().toLocaleTimeString();
    window._remoteLastResult =
      `<div class="card border-light-subtle"><div class="card-body py-2 px-3">
         <div class="d-flex align-items-start gap-2">
           <div class="flex-grow-1">${html}</div>
           <button type="button" class="btn-close btn-sm"
                   aria-label="Dismiss" onclick="remoteDismiss()"></button>
         </div>
         <div class="text-muted mt-1" style="font-size:.75rem">${when}</div>
       </div></div>`;
    el.innerHTML = window._remoteLastResult;
  } else {
    el.innerHTML = `<div class="text-muted">${html}</div>`;
  }
}

window.remoteDismiss = function () {
  window._remoteLastResult = null;
  const el = document.getElementById('remoteOut');
  if (el) el.innerHTML = '';
};

function _remoteRestore() {
  const el = document.getElementById('remoteOut');
  if (el && window._remoteLastResult && !el.innerHTML.trim()) {
    el.innerHTML = window._remoteLastResult;
  }
}

window.remoteVerify = async function () {
  _remoteOut('verifying…', {transient: true});
  const d = await (await fetch('/remote/verify', {method: 'POST'})).json();
  _remoteOut((d.checks || []).map(c =>
    `<div>${c.ok ? '<span class="text-success">[ok]</span>'
                 : '<span class="text-danger">[XX]</span>'}
       <code>${_gEsc(c.name)}</code> ${_gEsc(c.detail || '')}
       ${c.ok ? '' : `<div class="text-danger ms-4">${_gEsc(c.fix || '')}</div>`}</div>`
  ).join('') + `<div class="mt-1"><strong>${d.ok ? 'read-only checks pass' : 'REFUSED'}</strong>
     <span class="text-muted">— ${_gEsc(d.note || '')}</span></div>`);
  loadRemotePanel();
};

window.remoteVerifyWrite = async function () {
  if (!confirm('The write probe pushes to the remote.\n\n' +
               'It publishes no content — an orphan commit with an empty ' +
               'tree, whose ref is removed afterwards — but it is a real ' +
               'write to GitHub. Proceed?')) return;
  _remoteOut('probing write access…', {transient: true});
  const d = await (await fetch('/remote/verify-write', {method: 'POST'})).json();
  _remoteOut((d.checks || []).map(c =>
    `<div>${c.ok ? '<span class="text-success">[ok]</span>'
                 : '<span class="text-danger">[XX]</span>'}
       <code>${_gEsc(c.name)}</code> ${_gEsc(c.detail || '')}
       ${c.ok ? '' : `<div class="text-danger ms-4">${_gEsc(c.fix || '')}</div>`}</div>`
  ).join('') + `<div class="mt-1"><strong>${
    d.ready_to_push ? 'all five pass — ready to push' : 'REFUSED'}</strong></div>`);
  loadRemotePanel();
};

window.remotePreview = async function () {
  _remoteOut('scanning history…', {transient: true});
  const d = await (await fetch('/remote/preview')).json();
  if (!d.ok) { _remoteOut(`<span class="text-danger">${_gEsc(d.error)}</span>`); return; }
  const rows = (d.secrets.rows || []).reduce((acc, r) => {
    const k = acc[r.kind] || (acc[r.kind] = {live: 0, dead: 0, rec: r.recoverable});
    k.live += r.live; k.dead += r.dead; return acc;
  }, {});
  const snmp = d.snmp || {};
  _remoteOut(`
    <div>publishes to <code>${_gEsc(d.owner_repo)}</code> —
      ${d.commits} commits, ${d.tags} tags, ${d.notes} notes</div>
    <div class="mt-1">SNMP: ${snmp.all_read_only
      ? '<span class="text-success">all communities read-only</span>'
      : '<span class="text-danger">a WRITE community is present — stop</span>'}</div>
    <table class="table table-sm mt-1 mb-1"><tbody>
      ${Object.entries(rows).map(([kind, v]) => `<tr>
        <td><code>${_gEsc(kind)}</code></td>
        <td>live ${v.live}</td><td>dead ${v.dead}</td>
        <td>${v.rec && v.live ? '<span class="badge bg-danger-subtle text-danger-emphasis">acknowledgement required</span>'
                              : '<span class="text-muted">not gated</span>'}</td>
      </tr>`).join('')}
    </tbody></table>
    <div class="text-muted">Rotating these after pushing does not unpublish them.</div>`);
};

window.remoteAcknowledge = async function () {
  const d = await (await fetch('/remote/preview')).json();
  if (!d.ok) { _remoteOut(`<span class="text-danger">${_gEsc(d.error)}</span>`); return; }
  const kinds = (d.gated && d.gated.kinds) || [];
  if (!kinds.length) { _remoteOut('nothing requires acknowledgement'); return; }
  const counts = (d.gated && d.gated.counts) || {};
  // Built as an array and joined, so no string literal here spans a line
  // break. The previous version was written through a Python string, where a
  // single-backslash \n becomes a REAL newline — which a backtick template
  // literal tolerates and a single-quoted string does not. One of them was
  // single-quoted, and the parse error took the whole script block with it.
  const lines = ['Publishing to ' + d.owner_repo + ' exposes, in history:', ''];
  kinds.forEach(k => lines.push('  ' + k + ' x' + counts[k]));
  lines.push('', 'Rotating them afterwards does not unpublish them.', '',
             'Type the gated kinds to acknowledge:', '  ' + kinds.join(' '));
  const typed = prompt(lines.join('\n'));
  if (typed === null) return;
  const r = await fetch('/remote/acknowledge', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({typed: typed})});
  const out = await r.json();
  _remoteOut(out.ok
    ? `<span class="text-success">acknowledged</span> — ${_gEsc(JSON.stringify(out.acknowledged.counts))}`
    : `<span class="text-danger">${_gEsc(out.error)}</span>` +
      (out.expected ? ` (expected: <code>${_gEsc(out.expected)}</code>)` : ''));
  loadRemotePanel();
};

window.remotePush = async function () {
  if (!confirm('Publish this list\'s full history and tags to the remote?\n\n' +
               'This cannot be undone: rotating a credential afterwards does ' +
               'not unpublish it.')) return;
  _remoteOut('pushing…', {transient: true});
  const r = await fetch('/remote/push', {method: 'POST'});
  const d = await r.json();
  if (!d.ok) { _remoteOut(`<span class="text-danger">${_gEsc(d.error)}</span>`); return; }
  _remoteOut(`<span class="text-success">pushed</span> to <code>${_gEsc(d.remote)}</code> —
    ${d.heads_pushed} head(s), ${d.tags_pushed} tag(s), ${d.notes_pushed} note ref(s)
    of ${d.note_refs_present} present, ${d.refs_now} refs on the remote, ${d.seconds}s.
    <button class="btn btn-outline-secondary btn-sm ms-2" onclick="remoteEnableAuto()">
      Enable auto-push</button>`);
  loadRemotePanel();
};

/* Initialised HERE, by this block, on its own event.
   Being called from another block made the card depend on that block's
   internal ordering — and it lost: the call ran before the container the
   other block was about to create. A component that needs another
   component's call order is not isolated, whatever else is done to it. */
document.addEventListener('DOMContentLoaded', loadRemotePanel);

window.remoteEnableAuto = async function () {
  const r = await fetch('/remote/auto-push', {method: 'POST'});
  const d = await r.json();
  _remoteOut(d.ok ? '<span class="text-success">auto-push enabled</span>'
                  : `<span class="text-danger">${_gEsc(d.error)}</span>`);
  loadRemotePanel();
};
