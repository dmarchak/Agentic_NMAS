let _topoSvcTimer = null;

function _topoSvcShowError(message, notConfigured) {
  const placeholder = document.getElementById('topoSvcPlaceholder');
  const frame = document.getElementById('topoSvcFrame');
  if (!placeholder) { console.error('topoSvc: no placeholder element'); return; }
  if (frame) frame.hidden = true;
  placeholder.hidden = false;
  // An UNCONFIGURED integration is a state, not an error (the plan's
  // constraint 4): muted, and saying where and what to set. It was drawn red
  // and read as the topology having failed (2026-09-28, C126).
  if (notConfigured) {
    placeholder.classList.remove('text-danger');
    placeholder.classList.add('text-muted');
  } else {
    placeholder.classList.remove('text-muted');
    placeholder.classList.add('text-danger');
  }
  placeholder.textContent = message;
}

/* Pure: what the panel says for one /topology/service/status payload.
   `{kind: 'not_configured' | 'load', message}`. */
function topoSvcStateFor(d) {
  if (!d || !d.configured) {
    return {kind: 'not_configured',
            message: 'Not configured. This panel shows the rcn-topology service\'s '
                     + 'rendered graph, and nothing has told the NMAS where that service '
                     + 'is: set Settings \u2192 Integrations \u2192 Topology service \u2192 URL '
                     + 'to its base URL (it fetches <base>/topology.svg). Nothing failed. '
                     + 'The built-in discovery below does not need it.'};
  }
  return {kind: 'load', message: ''};
}

function topoSvcRefresh() {
  const image = document.getElementById('topoSvcImage');
  const placeholder = document.getElementById('topoSvcPlaceholder');
  const frame = document.getElementById('topoSvcFrame');
  const stamp = document.getElementById('topoSvcStamp');
  if (!image || !placeholder || !frame) {
    console.error('topoSvc: panel elements missing; the partial did not render');
    return;
  }

  // Ask first, so a misconfigured or unreachable service yields a REASON.
  // An <img> that fails gives only a broken-image icon and an onerror with
  // no detail, which is the blank-area failure in a different costume.
  fetch('/topology/service/status')
    .then(function (r) { return r.json(); })
    .then(function (d) {
      const state = topoSvcStateFor(d);
      if (state.kind === 'not_configured') {
        _topoSvcShowError(state.message, true);
        return;
      }
      if (stamp) stamp.textContent = 'loading…';
      // Cache-busting timestamp: without it the browser serves the previous
      // render and Refresh silently does nothing.
      image.src = '/topology/service/svg?t=' + Date.now();
    })
    .catch(function (e) {
      _topoSvcShowError('Could not ask the NMAS about the topology service: ' + e);
    });
}

function topoSvcSetInterval() {
  const select = document.getElementById('topoSvcInterval');
  if (_topoSvcTimer) { clearInterval(_topoSvcTimer); _topoSvcTimer = null; }
  const seconds = select ? parseInt(select.value, 10) : 0;
  if (seconds > 0) _topoSvcTimer = setInterval(topoSvcRefresh, seconds * 1000);
}

function topoSvcInit() {
  const image = document.getElementById('topoSvcImage');
  if (!image) { console.error('topoSvc: no image element to initialise'); return; }

  image.addEventListener('load', function () {
    const placeholder = document.getElementById('topoSvcPlaceholder');
    const frame = document.getElementById('topoSvcFrame');
    const stamp = document.getElementById('topoSvcStamp');
    if (placeholder) placeholder.hidden = true;
    if (frame) frame.hidden = false;
    if (stamp) stamp.textContent = 'refreshed ' + new Date().toLocaleTimeString();
  });

  image.addEventListener('error', function () {
    // The route answers JSON with a reason on failure, so fetch it and say
    // what went wrong rather than leaving a broken-image icon.
    fetch('/topology/service/svg?t=' + Date.now())
      .then(function (r) { return r.json(); })
      .then(function (d) {
        _topoSvcShowError(d && d.error ? d.error
                                       : 'The topology service did not return an image.');
      })
      .catch(function () {
        _topoSvcShowError('The topology service did not return an image.');
      });
  });

  topoSvcRefresh();
}

document.addEventListener('DOMContentLoaded', topoSvcInit);
