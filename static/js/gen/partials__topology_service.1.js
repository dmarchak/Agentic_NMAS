let _topoSvcTimer = null;

function _topoSvcShowError(message) {
  const placeholder = document.getElementById('topoSvcPlaceholder');
  const frame = document.getElementById('topoSvcFrame');
  if (!placeholder) { console.error('topoSvc: no placeholder element'); return; }
  if (frame) frame.hidden = true;
  placeholder.hidden = false;
  placeholder.classList.add('text-danger');
  placeholder.textContent = message;
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
      if (!d.configured) {
        _topoSvcShowError('Topology service is not configured — set its URL '
                          + 'in Settings → Topology service.');
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
