const STACK_TOOLS = ['netbox', 'prometheus', 'loki', 'oxidized', 'kea', 'grafana'];

function _stackEscape(text) {
  const d = document.createElement('div');
  d.textContent = text === null || text === undefined ? '' : String(text);
  return d.innerHTML;
}

function _stackBadge(state) {
  if (state === 'up') return ['bg-success', 'up'];
  if (state === 'down') return ['bg-danger', 'down'];
  if (state === 'not_configured') return ['bg-secondary', 'off'];
  return ['bg-secondary', '?'];
}

function _stackRender(tool, data) {
  const badge = document.getElementById('stackBadge-' + tool);
  const body = document.getElementById('stackBody-' + tool);
  if (!body) { console.error('monitoring stack: no container for ' + tool); return; }

  const [cls, text] = _stackBadge(data.state);
  if (badge) { badge.className = 'badge me-2 ' + cls; badge.textContent = text; }

  // Every branch writes something. A card that goes quiet on an unexpected
  // shape looks identical to a card that never ran.
  if (data.state === 'not_configured') {
    body.innerHTML = '<span class="text-muted">' + _stackEscape(data.message) + '</span>';
    return;
  }
  if (!data.ok) {
    body.innerHTML = '<span class="text-danger">' + _stackEscape(data.error || 'unreachable') + '</span>';
    return;
  }

  let html = '';
  (data.metrics || []).forEach(function (m) {
    const colour = m.state === 'down' ? 'text-danger' : 'text-info';
    html += '<div class="d-flex justify-content-between">'
          + '<span class="text-muted">' + _stackEscape(m.label) + '</span>'
          + '<span class="' + colour + '">' + _stackEscape(m.value)
          + (m.suffix ? ' <span class="text-muted">' + _stackEscape(m.suffix) + '</span>' : '')
          + '</span></div>';
  });

  const rows = data.detail || [];
  if (rows.length) {
    html += '<div class="mt-2 pt-2" style="border-top:1px solid #334155;max-height:11rem;overflow:auto">';
    rows.forEach(function (row) {
      const colour = row.state === 'down' ? 'text-danger' : 'text-muted';
      html += '<div class="' + colour + '" style="font-size:.75rem;white-space:nowrap;'
            + 'overflow:hidden;text-overflow:ellipsis">' + _stackEscape(row.text)
            + (row.value ? ' <span class="text-secondary">' + _stackEscape(row.value) + '</span>' : '')
            + (row.note ? ' <span class="text-warning">' + _stackEscape(row.note) + '</span>' : '')
            + '</div>';
    });
    html += '</div>';
  }

  if (data.link && data.link.href) {
    html += '<a class="btn btn-outline-info btn-sm mt-2" target="_blank" rel="noopener" href="'
          + _stackEscape(data.link.href) + '">' + _stackEscape(data.link.text || 'Open') + '</a>';
    if (data.link.note) {
      html += '<div class="text-muted mt-1" style="font-size:.7rem">'
            + _stackEscape(data.link.note) + '</div>';
    }
  }

  body.innerHTML = html || '<span class="text-muted">no data</span>';
}

function loadMonitoringStack() {
  const stamp = document.getElementById('stackStamp');
  if (stamp) stamp.textContent = 'checking…';

  // Six independent requests. One tool being slow or dead must not hold up
  // or blank the other five, which is why this is not one aggregate call.
  const each = STACK_TOOLS.map(function (tool) {
    const body = document.getElementById('stackBody-' + tool);
    if (body) body.innerHTML = '<span class="text-muted">checking…</span>';
    return fetch('/monitoring/stack/' + tool)
      .then(function (r) { return r.json(); })
      .then(function (data) { _stackRender(tool, data); })
      .catch(function (e) {
        _stackRender(tool, {ok: false, state: 'down', error: 'request failed: ' + e});
      });
  });

  Promise.all(each).then(function () {
    if (stamp) stamp.textContent = 'checked ' + new Date().toLocaleTimeString();
  });
}

document.addEventListener('DOMContentLoaded', loadMonitoringStack);
