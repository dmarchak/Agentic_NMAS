const deviceIps = JSON.parse(document.getElementById("device-data").textContent);

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
  deviceIps.forEach(ip => updateStatus(ip));
}, 5000);
