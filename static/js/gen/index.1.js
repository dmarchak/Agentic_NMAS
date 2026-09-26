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
  // Add loading indicator to add device form
  const addDeviceForm = document.getElementById('addDeviceForm');
  const addDeviceBtn = document.getElementById('addDeviceBtn');

  if (addDeviceForm && addDeviceBtn) {
    addDeviceForm.addEventListener('submit', function() {
      const btnText = addDeviceBtn.querySelector('.btn-text');
      const spinner = addDeviceBtn.querySelector('.spinner-border');

      if (btnText && spinner) {
        btnText.textContent = 'Connecting...';
        spinner.classList.remove('d-none');
        addDeviceBtn.disabled = true;
      }
    });
  }

  // Device search/filter functionality
  const searchInput = document.getElementById('deviceSearch');
  const deviceRows = document.querySelectorAll('.device-row');
  const deviceCount = document.getElementById('deviceCount');

  if (searchInput && deviceRows.length > 0) {
    searchInput.addEventListener('input', function() {
      const searchTerm = this.value.toLowerCase().trim();
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

    searchInput.addEventListener('keydown', function(e) {
      if (e.key === 'Escape') {
        this.value = '';
        this.dispatchEvent(new Event('input'));
        this.blur();
      }
    });
  }

  // ========================================================================
  // Bulk Operations
  // ========================================================================

  const deviceCheckboxes = document.querySelectorAll('.device-checkbox');
  const selectAll = document.getElementById('selectAll');
  const bulkOpsPanel = document.getElementById('bulkOpsPanel');
  const selectedCountSpan = document.getElementById('selectedCount');

  function updateSelection() {
    const selected = Array.from(deviceCheckboxes).filter(cb => cb.checked && !cb.disabled);
    const count = selected.length;

    if (selectedCountSpan) {
      selectedCountSpan.textContent = count;
    }

    if (bulkOpsPanel) {
      bulkOpsPanel.style.display = count > 0 ? 'block' : 'none';
    }

    if (selectAll) {
      const enabledCheckboxes = Array.from(deviceCheckboxes).filter(cb => !cb.disabled);
      selectAll.checked = enabledCheckboxes.length > 0 && selected.length === enabledCheckboxes.length;
    }
  }

  if (selectAll) {
    selectAll.addEventListener('change', function() {
      deviceCheckboxes.forEach(cb => {
        if (!cb.disabled) {
          cb.checked = this.checked;
        }
      });
      updateSelection();
    });
  }

  deviceCheckboxes.forEach(cb => {
    cb.addEventListener('change', updateSelection);
  });

  window.clearSelection = function() {
    deviceCheckboxes.forEach(cb => cb.checked = false);
    if (selectAll) selectAll.checked = false;
    updateSelection();
  };

  window.saveAllConfigs = function() {
    const onlineDeviceIps = Array.from(deviceCheckboxes)
      .filter(cb => !cb.disabled)
      .map(cb => cb.value);

    if (onlineDeviceIps.length === 0) {
      showToast('No online devices available', 'warning');
      return;
    }

    if (!confirm(
      `Fetch running-config from ${onlineDeviceIps.length} online device(s), save as golden configs, and stage in Git?\n\n` +
      `If Jenkins is configured, a validation pipeline will also be created — you can then commit ` +
      `from the Git tab once it passes, or commit directly at any time without one.`
    )) return;

    const saveBtn = document.getElementById('saveAllBtn');
    const btnText = saveBtn.querySelector('.btn-text');
    const spinner = saveBtn.querySelector('.spinner-border');
    btnText.textContent = 'Saving...';
    spinner.classList.remove('d-none');
    saveBtn.disabled = true;

    fetch('/golden_configs/save_all', { method: 'POST' })
    .then(resp => resp.json())
    .then(data => {
      btnText.textContent = 'Save All Configs';
      spinner.classList.add('d-none');
      saveBtn.disabled = false;

      if (data.ok) {
        const pipeMsg = data.pipeline
          ? ` Pipeline <strong>${data.pipeline}</strong> triggered — commit from the Git tab once it passes.`
          : '';
        // The same summary the server logs. A toast that says "saved" while
        // the run produced no commit and no baseline is how an operator ends
        // up reading git to find out what happened.
        const s = data.summary || {};
        const skipped = (s.skipped || []);
        const rows = [
          ['captured',  `${s.captured} of ${s.inventory}`],
          ['changed',   (s.changed || []).join(', ') || 'none'],
          ['unchanged', `${(s.unchanged || []).length}`],
          ['skipped',   skipped.length
                          ? skipped.map(k => `${k.hostname} (${k.reason})`).join(', ')
                          : 'none'],
          ['commit',    s.commit || 'none'],
          ['baseline',  s.baseline || 'none'],
        ];
        const detail = rows.map(([k, v]) =>
          `<div><span class="text-muted">${k}</span> <strong>${v}</strong></div>`
        ).join('');
        // No commit AND no baseline means this run left no restore point.
        const level = (s.baseline && s.baseline !== 'none') ? 'success'
                    : (skipped.length ? 'warning' : 'warning');
        showToast(`${data.message}${pipeMsg}<hr class="my-1">${detail}`, level);
        // Refresh git tab if open
        if (document.getElementById('gitPane') &&
            !document.getElementById('gitPane').classList.contains('d-none')) {
          loadGitTab();
        }
        // ...and the golden-repo panel, which is where baselines are listed.
        // Save All is the main way a baseline is created, and the panel was
        // only refreshed on tab activation — so a new baseline did not appear
        // until the operator navigated away and back. The tag existed; the
        // screen that exists to show it did not say so.
        if (typeof loadGoldenRepoPanel === 'function') loadGoldenRepoPanel();
      } else {
        showToast(data.message || 'Save all configs failed', 'danger');
      }
    })
    .catch(err => {
      btnText.textContent = 'Save All Configs';
      spinner.classList.add('d-none');
      saveBtn.disabled = false;
      console.error('Save all configs failed:', err);
      showToast('Failed to save configs', 'danger');
    });
  };


  window.reloadSelectedDevices = function() {
    const selectedIps = Array.from(deviceCheckboxes)
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

      if (data.status === 'success') {
        showToast(data.message, 'success');
        if (data.updated > 0) {
          setTimeout(() => { window.location.reload(); }, 1500);
        }
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

    const selectedIps = Array.from(deviceCheckboxes)
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

    const selectedIps = Array.from(deviceCheckboxes)
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
    const selectedIps = Array.from(deviceCheckboxes)
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

    const selectedIps = Array.from(deviceCheckboxes)
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
    const hosts = Array.from(deviceCheckboxes)
      .filter(cb => cb.checked && !cb.disabled)
      .map(cb => { const tr = cb.closest('tr'); return tr ? tr.dataset.hostname : ''; })
      .filter(Boolean);
    if (hosts.length === 0) {
      showToast('No devices selected', 'warning');
      return;
    }
    previewBaselineRestore('HEAD', null, {devices: hosts});
  };

  // Update hint when command mode changes
  document.querySelectorAll('input[name="commandMode"]').forEach(radio => {
    radio.addEventListener('change', function() {
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
    });
  });

  window.executeBulkCommand = function() {
    const command = document.getElementById('bulkCommand').value.trim();
    if (!command) {
      showToast('Please enter a command', 'warning');
      return;
    }

    const selectedIps = Array.from(deviceCheckboxes)
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
