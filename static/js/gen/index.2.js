/* Which devices to poll, read from the ROWS each time (Stage 7.0). It was
   parsed once from the page's JSON block, so a device promoted after the
   page loaded was drawn by the in-place redraw and never polled. */
function deviceIps() {
  return Array.from(document.querySelectorAll('.device-row'))
    .map(row => row.dataset.ip).filter(Boolean);
}

/* Seed the AI device cache from server-rendered data on page load. */
(function seedDeviceCache() {
  try {
    const full = JSON.parse(document.getElementById("device-full-data").textContent);
    const cache = {
      timestamp: Date.now(),
      devices: full.map(d => ({
        hostname:    d.hostname || '',
        ip:          d.ip      || '',
        device_type: d.device_type || 'cisco_ios',
        online:      d.online !== undefined ? d.online : false,
      }))
    };
    localStorage.setItem('ndm_device_cache', JSON.stringify(cache));
  } catch (e) { /* non-critical */ }
})();

function updateStatus(ip) {
  fetch(`/status/${ip}`)
    .then(resp => resp.json())
    .then(data => {
      /* Keep the AI cache in sync with every status poll result */
      try {
        const raw = localStorage.getItem('ndm_device_cache');
        if (raw) {
          const cache = JSON.parse(raw);
          const dev = cache.devices.find(d => d.ip === data.ip);
          if (dev) {
            dev.online = data.online;
            cache.timestamp = Date.now();
            localStorage.setItem('ndm_device_cache', JSON.stringify(cache));
          }
        }
      } catch (e) { /* non-critical */ }

      const statusEl = document.getElementById(`status-${data.ip}`);
      if (statusEl) {
        if (data.online) {
          statusEl.className = "btn btn-sm btn-success";
          statusEl.textContent = "Online";
        } else {
          statusEl.className = "btn btn-sm btn-danger";
          statusEl.textContent = "Offline";
        }
      }
      const btn = document.getElementById(`btn-${data.ip}`);
      if (btn) {
        if (data.online) {
          btn.outerHTML = `<a id="btn-${data.ip}" href="/device/${data.ip}" class="btn btn-sm btn-primary" target="_blank" rel="noopener">Manage</a>`;
        } else {
          btn.outerHTML = `<button id="btn-${data.ip}" class="btn btn-sm btn-secondary" disabled>Offline</button>`;
        }
      }
    })
    .catch(err => console.error("Status update failed:", err));
}
setInterval(() => {
  deviceIps().forEach(ip => updateStatus(ip));
}, 5000);
