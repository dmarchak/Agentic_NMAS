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
