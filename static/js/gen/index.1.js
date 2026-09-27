// ========================================================================
// Device List Management
// ========================================================================

window.showCreateListModal = function() {
  const modal = new bootstrap.Modal(document.getElementById('createListModal'));
  document.getElementById('newListName').value = '';
  modal.show();
  document.getElementById('createListModal').addEventListener('shown.bs.modal', function() {
    document.getElementById('newListName').focus();
  }, { once: true });
};

window.createDeviceList = function() {
  const nameInput = document.getElementById('newListName');
  const name = nameInput.value.trim();

  if (!name) {
    showToast('Please enter a list name', 'warning');
    nameInput.focus();
    return;
  }

  fetch('/device_lists', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: name })
  })
  .then(resp => resp.json())
  .then(data => {
    if (data.status === 'success') {
      showToast(data.message, 'success');
      fetch('/select_device_list', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name })
      })
      .then(() => { window.location.reload(); });
    } else {
      showToast(data.message || 'Failed to create list', 'danger');
    }
  })
  .catch(err => {
    console.error('Create list failed:', err);
    showToast('Failed to create device list', 'danger');
  });
};

window.deleteCurrentList = function() {
  const select = document.getElementById('deviceListSelect');
  const currentList = select.value;

  if (!confirm(`Are you sure you want to delete the device list "${currentList}"?\n\nThis will permanently delete all devices, backups, playbooks, and notes for this list.`)) {
    return;
  }

  fetch(`/device_lists/${encodeURIComponent(currentList)}`, { method: 'DELETE' })
  .then(resp => resp.json())
  .then(data => {
    if (data.status === 'success') {
      showToast(data.message, 'success');
      window.location.reload();
    } else {
      showToast(data.message || 'Failed to delete list', 'danger');
    }
  })
  .catch(err => {
    console.error('Delete list failed:', err);
    showToast('Failed to delete device list', 'danger');
  });
};

document.addEventListener('DOMContentLoaded', () => {
  const deviceListSelect = document.getElementById('deviceListSelect');
  if (deviceListSelect) {
    deviceListSelect.addEventListener('change', function() {
      const selectedList = this.value;
      fetch('/select_device_list', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: selectedList })
      })
      .then(resp => resp.json())
      .then(data => {
        if (data.status === 'success') {
          window.location.reload();
        } else {
          showToast(data.message || 'Failed to switch list', 'danger');
        }
      })
      .catch(err => {
        console.error('Switch list failed:', err);
        showToast('Failed to switch device list', 'danger');
      });
    });
  }

  const newListNameInput = document.getElementById('newListName');
  if (newListNameInput) {
    newListNameInput.addEventListener('keydown', function(e) {
      if (e.key === 'Enter') {
        e.preventDefault();
        createDeviceList();
      }
    });
  }
});

document.addEventListener('DOMContentLoaded', () => {
  // Device search/filter functionality.
  //
  // DELEGATED, and every lookup LIVE (Stage 7.0). The device list's rows,
  // checkboxes and search box are redrawn in place when a response
  // invalidates `inventory` (refreshDeviceRegions below). They were captured
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

  // ========================================================================
  // Bulk Operations
  // ========================================================================

  const selectedCountSpan = document.getElementById('selectedCount');

  // A function, not a captured NodeList: the rows are redrawn in place.
  function deviceCheckboxes() {
    return document.querySelectorAll('.device-checkbox');
  }

  function updateSelection() {
    const selected = Array.from(deviceCheckboxes()).filter(cb => cb.checked && !cb.disabled);
    const count = selected.length;
    const countSpan = document.getElementById('selectedCount') || selectedCountSpan;
    const bulkOpsPanel = document.getElementById('bulkOpsPanel');
    const selectAll = document.getElementById('selectAll');

    if (countSpan) {
      countSpan.textContent = count;
    }

    if (bulkOpsPanel) {
      bulkOpsPanel.style.display = count > 0 ? 'block' : 'none';
    }

    if (selectAll) {
      const enabledCheckboxes = Array.from(deviceCheckboxes()).filter(cb => !cb.disabled);
      selectAll.checked = enabledCheckboxes.length > 0 && selected.length === enabledCheckboxes.length;
    }
  }

  document.addEventListener('change', function(e) {
    const t = e.target;
    if (!t) return;
    if (t.id === 'selectAll') {
      deviceCheckboxes().forEach(cb => {
        if (!cb.disabled) {
          cb.checked = t.checked;
        }
      });
      updateSelection();
    } else if (t.classList && t.classList.contains('device-checkbox')) {
      updateSelection();
    }
  });

  window.clearSelection = function() {
    deviceCheckboxes().forEach(cb => cb.checked = false);
    const selectAll = document.getElementById('selectAll');
    if (selectAll) selectAll.checked = false;
    updateSelection();
  };

  // Save All is the WHOLE-FLEET form of the capture operation (7.1 step 4,
  // register C89): every device read now, previewed against its golden and
  // its committed intent, confirmed, then recorded in one commit. It used to
  // commit on one click, and a hand change became a golden, a baseline and a
  // pushed commit in four minutes with nothing asking whether it was intended.
  window.saveAllConfigs = function() {
    previewCapture(null);
  };


  window.reloadSelectedDevices = function() {
    const selectedIps = Array.from(deviceCheckboxes())
      .filter(cb => cb.checked && !cb.disabled)
      .map(cb => cb.value);

    if (selectedIps.length === 0) {
      showToast('Select at least one device first', 'warning');
      return;
    }

    if (!confirm(
      `WARNING: This will reload (reboot) ${selectedIps.length} device(s).\n\n` +
      `The devices will be unreachable for several minutes.\n\nContinue?`
    )) return;

    const btn     = document.getElementById('reloadDevicesBtn');
    const btnText = btn.querySelector('.btn-text');
    const spinner = btn.querySelector('.spinner-border');
    btnText.textContent = 'Reloading…';
    spinner.classList.remove('d-none');
    btn.disabled = true;

    const formData = new FormData();
    selectedIps.forEach(ip => formData.append('device_ips[]', ip));

    fetch('/bulk_reload', { method: 'POST', body: formData })
    .then(r => r.json())
    .then(data => {
      btnText.textContent = 'Reload Devices';
      spinner.classList.add('d-none');
      btn.disabled = false;
      if (data.status === 'success') {
        showToast(data.message, 'warning');
      } else {
        showToast(data.message || 'Reload failed', 'danger');
      }
    })
    .catch(err => {
      btnText.textContent = 'Reload Devices';
      spinner.classList.add('d-none');
      btn.disabled = false;
      showToast('Reload request failed: ' + err, 'danger');
    });
  };

  window.refreshHostnames = function() {
    if (!confirm('Query all online devices for their current hostnames?\n\nThis will update the device list if any hostnames have changed.')) {
      return;
    }

    const refreshBtn = document.getElementById('refreshHostnamesBtn');
    const btnText = refreshBtn.querySelector('.btn-text');
    const spinner = refreshBtn.querySelector('.spinner-border');
    btnText.textContent = 'Refreshing...';
    spinner.classList.remove('d-none');
    refreshBtn.disabled = true;

    fetch('/refresh_hostnames', { method: 'POST' })
    .then(resp => resp.json())
    .then(data => {
      btnText.textContent = 'Refresh Hostnames';
      spinner.classList.add('d-none');
      refreshBtn.disabled = false;

      // No reload: the response invalidates `inventory` and `goldens`, so the
      // device list and the golden panel redraw in place, and the message
      // (which says what is left to do) is not erased by a new page.
      if (data.status === 'success' || data.status === 'warning') {
        showToast(data.message, data.status);
      } else {
        showToast(data.message || 'Refresh hostnames failed', 'danger');
      }
    })
    .catch(err => {
      btnText.textContent = 'Refresh Hostnames';
      spinner.classList.add('d-none');
      refreshBtn.disabled = false;
      console.error('Refresh hostnames failed:', err);
      showToast('Failed to refresh hostnames', 'danger');
    });
  };

  window.saveTftpServer = function() {
    const tftpServer = document.getElementById('bulkTftpServer').value.trim();

    if (!tftpServer) {
      showToast('Please enter a TFTP server address', 'warning');
      return;
    }

    fetch('/save_tftp_server', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tftp_server: tftpServer })
    })
    .then(resp => resp.json())
    .then(data => {
      if (data.status === 'success') {
        showToast(data.message, 'success');
      } else {
        showToast(data.message || 'Failed to save TFTP server', 'danger');
      }
    })
    .catch(err => {
      console.error('Save TFTP server failed:', err);
      showToast('Failed to save TFTP server address', 'danger');
    });
  };

  window.bulkUploadFile = function() {
    const fileInput = document.getElementById('bulkUploadFile');
    const file = fileInput.files[0];

    if (!file) {
      showToast('Please select a file to upload', 'warning');
      return;
    }

    const selectedIps = Array.from(deviceCheckboxes())
      .filter(cb => cb.checked && !cb.disabled)
      .map(cb => cb.value);

    if (selectedIps.length === 0) {
      showToast('No devices selected', 'warning');
      return;
    }

    if (!confirm(`Upload "${file.name}" to flash: on ${selectedIps.length} device(s)?`)) {
      return;
    }

    const formData = new FormData();
    selectedIps.forEach(ip => formData.append('device_ips[]', ip));
    formData.append('file', file);
    formData.append('tftp_server', document.getElementById('bulkTftpServer').value.trim());

    showToast('Starting bulk upload...', 'info');

    fetch('/bulk_tftp_upload', { method: 'POST', body: formData })
    .then(resp => resp.json())
    .then(data => {
      if (data.status === 'success') {
        showToast(data.message, 'success');
        showBulkResults(data.operation_id);
        fileInput.value = '';
      } else {
        showToast(data.message || 'Bulk upload failed', 'danger');
      }
    })
    .catch(err => {
      console.error('Bulk upload failed:', err);
      showToast('Failed to start bulk upload', 'danger');
    });
  };

  window.bulkDownloadFile = function() {
    const filename = document.getElementById('bulkDownloadFilename').value.trim();

    if (!filename) {
      showToast('Please enter a filename to download', 'warning');
      return;
    }

    const selectedIps = Array.from(deviceCheckboxes())
      .filter(cb => cb.checked && !cb.disabled)
      .map(cb => cb.value);

    if (selectedIps.length === 0) {
      showToast('No devices selected', 'warning');
      return;
    }

    if (!confirm(`Download "${filename}" from flash: on ${selectedIps.length} device(s) to TFTP server?`)) {
      return;
    }

    const formData = new FormData();
    selectedIps.forEach(ip => formData.append('device_ips[]', ip));
    formData.append('filename', filename);
    formData.append('tftp_server', document.getElementById('bulkTftpServer').value.trim());

    showToast('Starting bulk download...', 'info');

    fetch('/bulk_tftp_download', { method: 'POST', body: formData })
    .then(resp => resp.json())
    .then(data => {
      if (data.status === 'success') {
        showToast(data.message, 'success');
        showBulkResults(data.operation_id);
        document.getElementById('bulkDownloadFilename').value = '';
      } else {
        showToast(data.message || 'Bulk download failed', 'danger');
      }
    })
    .catch(err => {
      console.error('Bulk download failed:', err);
      showToast('Failed to start bulk download', 'danger');
    });
  };

  window.bulkDownloadConfig = function(configType) {
    const selectedIps = Array.from(deviceCheckboxes())
      .filter(cb => cb.checked && !cb.disabled)
      .map(cb => cb.value);

    if (selectedIps.length === 0) {
      showToast('No devices selected', 'warning');
      return;
    }

    const configName = configType === 'startup' ? 'startup-config' : 'running-config';

    if (!confirm(`Download ${configName} from ${selectedIps.length} device(s) to TFTP server?`)) {
      return;
    }

    const formData = new FormData();
    selectedIps.forEach(ip => formData.append('device_ips[]', ip));
    formData.append('config_type', configType);
    formData.append('tftp_server', document.getElementById('bulkTftpServer').value.trim());

    showToast(`Starting ${configName} download...`, 'info');

    fetch('/bulk_download_config', { method: 'POST', body: formData })
    .then(resp => resp.json())
    .then(data => {
      if (data.status === 'success') {
        showToast(data.message, 'success');
        showBulkResults(data.operation_id);
      } else {
        showToast(data.message || 'Config download failed', 'danger');
      }
    })
    .catch(err => {
      console.error('Config download failed:', err);
      showToast('Failed to start config download', 'danger');
    });
  };

  window.bulkDeleteFile = function() {
    const filename = document.getElementById('bulkDeleteFilename').value.trim();

    if (!filename) {
      showToast('Please enter a filename to delete', 'warning');
      return;
    }

    const selectedIps = Array.from(deviceCheckboxes())
      .filter(cb => cb.checked && !cb.disabled)
      .map(cb => cb.value);

    if (selectedIps.length === 0) {
      showToast('No devices selected', 'warning');
      return;
    }

    if (!confirm(`DELETE "${filename}" from flash: on ${selectedIps.length} device(s)?\n\nThis action cannot be undone!`)) {
      return;
    }

    const formData = new FormData();
    selectedIps.forEach(ip => formData.append('device_ips[]', ip));
    formData.append('filename', filename);

    showToast('Starting bulk delete...', 'info');

    fetch('/bulk_delete_file', { method: 'POST', body: formData })
    .then(resp => resp.json())
    .then(data => {
      if (data.status === 'success') {
        showToast(data.message, 'success');
        showBulkResults(data.operation_id);
        document.getElementById('bulkDeleteFilename').value = '';
      } else {
        showToast(data.message || 'Bulk delete failed', 'danger');
      }
    })
    .catch(err => {
      console.error('Bulk delete failed:', err);
      showToast('Failed to start bulk delete', 'danger');
    });
  };

  // P.3 step 3 (D5): the guarded restore preview at HEAD, scoped to the
  // selected devices. It used to POST to an unguarded replay that pushed the
  // whole golden line by line: no plan, no hash, no rollback.
  window.bulkRestoreGoldenConfig = function() {
    const hosts = Array.from(deviceCheckboxes())
      .filter(cb => cb.checked && !cb.disabled)
      .map(cb => { const tr = cb.closest('tr'); return tr ? tr.dataset.hostname : ''; })
      .filter(Boolean);
    if (hosts.length === 0) {
      showToast('No devices selected', 'warning');
      return;
    }
    previewBaselineRestore('HEAD', null, {devices: hosts});
  };

  // Update hint when command mode changes. Delegated: the radios are inside
  // the bulk panel, which is redrawn in place (Stage 7.0).
  document.addEventListener('change', function(e) {
    if (!e.target || e.target.name !== 'commandMode') return;
    (function() {
      const modeHint = document.getElementById('modeHint');
      const configHint = document.getElementById('configHint');
      const commandInput = document.getElementById('bulkCommand');

      if (this.value === 'config') {
        modeHint.textContent = 'Enter configuration commands (auto enters config mode)';
        configHint.style.display = 'block';
        commandInput.placeholder = 'Enter config command(s) - use semicolons for multiple';
      } else {
        modeHint.textContent = 'Run show/exec commands (e.g., show ip int brief) — separate multiple with semicolons';
        configHint.style.display = 'none';
        commandInput.placeholder = 'Enter command(s) - use semicolons for multiple';
      }
    }).call(e.target);
  });

  window.executeBulkCommand = function() {
    const command = document.getElementById('bulkCommand').value.trim();
    if (!command) {
      showToast('Please enter a command', 'warning');
      return;
    }

    const selectedIps = Array.from(deviceCheckboxes())
      .filter(cb => cb.checked && !cb.disabled)
      .map(cb => cb.value);

    if (selectedIps.length === 0) {
      showToast('No devices selected', 'warning');
      return;
    }

    const commandMode = document.querySelector('input[name="commandMode"]:checked').value;
    const modeText = commandMode === 'config' ? 'configuration' : 'enable';

    if (!confirm(`Execute "${command}" in ${modeText} mode on ${selectedIps.length} device(s)?`)) {
      return;
    }

    const formData = new FormData();
    selectedIps.forEach(ip => formData.append('device_ips[]', ip));
    formData.append('command', command);
    formData.append('command_mode', commandMode);

    showToast('Starting bulk operation...', 'info');

    fetch('/bulk_execute', { method: 'POST', body: formData })
    .then(resp => resp.json())
    .then(data => {
      if (data.status === 'success') {
        showToast(data.message, 'success');
        showBulkResults(data.operation_id);
      } else {
        showToast(data.message || 'Bulk operation failed', 'danger');
      }
    })
    .catch(err => {
      console.error('Bulk execute failed:', err);
      showToast('Failed to start bulk operation', 'danger');
    });
  };

  function showBulkResults(operationId) {
    const modal = new bootstrap.Modal(document.getElementById('bulkResultsModal'));
    modal.show();

    document.getElementById('bulkProgressBar').style.width = '0%';
    document.getElementById('bulkProgressText').textContent = '0/0';
    document.getElementById('bulkSuccessCount').textContent = '0 succeeded';
    document.getElementById('bulkFailCount').textContent = '0 failed';
    document.getElementById('bulkResults').innerHTML = '<p class="text-muted">Executing...</p>';

    const pollInterval = setInterval(() => {
      fetch(`/bulk_status/${operationId}`)
        .then(resp => resp.json())
        .then(data => {
          if (data.status === 'success') {
            updateBulkProgress(data.operation);

            if (data.operation.status === 'completed') {
              clearInterval(pollInterval);
              document.getElementById('bulkProgressBar').classList.remove('progress-bar-animated');
              showToast('Bulk operation completed', 'success');
            }
          }
        })
        .catch(err => console.error('Poll failed:', err));
    }, 1000);

    document.getElementById('bulkResultsModal').addEventListener('hidden.bs.modal', () => {
      clearInterval(pollInterval);
    }, { once: true });
  }

  function updateBulkProgress(operation) {
    const { total, completed, failed, results } = operation;
    const progress = total > 0 ? ((completed + failed) / total * 100) : 0;

    document.getElementById('bulkProgressBar').style.width = progress + '%';
    document.getElementById('bulkProgressText').textContent = `${completed + failed}/${total}`;
    document.getElementById('bulkSuccessCount').textContent = `${completed} succeeded`;
    document.getElementById('bulkFailCount').textContent = `${failed} failed`;

    if (results.length > 0) {
      const resultsHtml = results.map(result => `
        <div class="card mb-2">
          <div class="card-header d-flex justify-content-between align-items-center">
            <span><strong>${result.hostname}</strong> (${result.ip})</span>
            <span class="badge bg-${result.status === 'success' ? 'success' : 'danger'}">${result.status}</span>
          </div>
          <div class="card-body">
            ${result.error
              ? `<p class="text-danger mb-0">${escapeHtml(result.error)}</p>`
              : `<pre class="bg-body-secondary border p-2 mb-0" style="max-height: 200px; overflow-y: auto;"><code>${escapeHtml(result.output)}</code></pre>`
            }
          </div>
        </div>
      `).join('');

      document.getElementById('bulkResults').innerHTML = resultsHtml;
    }
  }

  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }
});

// ========================================================================
// The device list, redrawn in place (Stage 7.0; NSOT_STAGE7_GUI.md 6b)
// ========================================================================
//
// The first of the three measured cases: onboarding's Verify promoted a
// device and the list still read "0 devices" until a manual reload. The
// list is server-rendered, and an empty list renders no table at all, so it
// is redrawn from the SAME templates the index uses (GET /devices/regions).

/* The payload in, the two regions and the list selector's count updated.
   Returns false when there is nothing to apply, so the registry marks the
   panel stale instead of leaving a stale list looking current. */
function applyDeviceRegions(data, doc) {
  doc = doc || document;
  if (!data || data.ok !== true) return false;
  const toolbar = doc.getElementById('deviceToolbarRegion');
  const table = doc.getElementById('deviceTableRegion');
  if (!toolbar || !table) return false;
  toolbar.innerHTML = data.toolbar_html;
  table.innerHTML = data.table_html;
  const select = doc.getElementById('deviceListSelect');
  if (select && select.options) {
    for (let i = 0; i < select.options.length; i++) {
      const opt = select.options[i];
      if (opt.value === data.list) opt.textContent = `${data.list} (${data.count} devices)`;
    }
  }
  return true;
}

async function refreshDeviceRegions() {
  // The operator's place survives the redraw: the search text and the
  // devices they had ticked. A redraw that clears a half-made selection is
  // a panel that punishes the action it is reporting on.
  const search = document.getElementById('deviceSearch');
  const term = search ? search.value : '';
  const ticked = Array.from(document.querySelectorAll('.device-checkbox:checked'))
    .map(cb => cb.value);
  const r = await fetch('/devices/regions');
  if (!r.ok) return false;
  if (!applyDeviceRegions(await r.json())) return false;
  let first = null;
  document.querySelectorAll('.device-checkbox').forEach(cb => {
    if (ticked.indexOf(cb.value) !== -1 && !cb.disabled) {
      cb.checked = true;
      first = first || cb;
    }
  });
  if (first) first.dispatchEvent(new Event('change', {bubbles: true}));
  const newSearch = document.getElementById('deviceSearch');
  if (newSearch && term) {
    newSearch.value = term;
    newSearch.dispatchEvent(new Event('input', {bubbles: true}));
  }
  if (typeof window.bindDeviceTableSortable === 'function') window.bindDeviceTableSortable();
  return true;
}

NMAS.subscribe('inventory', 'deviceList', refreshDeviceRegions, {panel: 'deviceTableRegion'});
