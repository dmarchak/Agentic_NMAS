// Today's list management (the list bar's select, + New List, Delete List and the New List
// dialog, which posted to /device_lists and /select_device_list) left at 7.8 on 2026-10-17
// (P7-26): Settings' New network… and Delete this network…, and the top bar's Network ▾.

document.addEventListener('DOMContentLoaded', () => {
  // Device search/filter functionality.
  //
  // DELEGATED, and every lookup LIVE (Stage 7.0). The device list's rows,
  // checkboxes and search box are redrawn in place when a response
  // invalidates `inventory` (the in-place redraw, removed at 7.8). They were captured
  // once at load, so a redrawn list kept these handlers pointed at rows that
  // no longer existed: the newly promoted device could not be searched or
  // selected, and "Select all" missed it.
  const deviceRowsNow = () => document.querySelectorAll('.device-row');

  document.addEventListener('input', function(e) {
    if (!e.target || e.target.id !== 'deviceSearch') return;
    const searchTerm = e.target.value.toLowerCase().trim();
    const deviceRows = deviceRowsNow();
    const deviceCount = document.getElementById('deviceCount');
    let visibleCount = 0;

    deviceRows.forEach(row => {
      const hostname = row.querySelector('.device-hostname').textContent.toLowerCase();
      const ip = row.querySelector('.device-ip').textContent.toLowerCase();
      const matches = hostname.includes(searchTerm) || ip.includes(searchTerm);

      if (matches) {
        row.style.display = '';
        visibleCount++;
      } else {
        row.style.display = 'none';
      }
    });

    if (deviceCount) {
      if (searchTerm) {
        deviceCount.textContent = `${visibleCount} of ${deviceRows.length} device(s)`;
      } else {
        deviceCount.textContent = `${deviceRows.length} device(s)`;
      }
    }
  });

  document.addEventListener('keydown', function(e) {
    if (!e.target || e.target.id !== 'deviceSearch') return;
    if (e.key === 'Escape') {
      e.target.value = '';
      e.target.dispatchEvent(new Event('input', {bubbles: true}));
      e.target.blur();
    }
  });

  // Save All is the WHOLE-FLEET form of the capture operation (7.1 step 4,
  // register C89): every device read now, previewed against its golden and
  // its committed intent, confirmed, then recorded in one commit. It used to
  // commit on one click, and a hand change became a golden, a baseline and a
  // pushed commit in four minutes with nothing asking whether it was intended.
  window.saveAllConfigs = function() {
    previewCapture(null);
  };

  // Today's bulk panel (the device selection, its command box and results
  // modal, and its Restore Golden Config at HEAD) left at 7.8 on 2026-10-15:
  // Show commands runs allowlisted reads across devices, and a device's
  // Restore from… and History's baselines restore.
});
