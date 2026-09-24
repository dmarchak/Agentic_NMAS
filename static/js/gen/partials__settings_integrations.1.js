/* Field spec for the integration cards. Phase 0 ships connection tests only;
   Phase 5 adds the read clients behind the same settings. */
const INTEGRATION_SPEC = {
  prometheus: {icon: '📈', fields: [
    {key: 'prometheus_url', label: 'URL', type: 'url', help: 'Prometheus or Thanos Query base URL.'},
    {key: 'prometheus_auth_mode', label: 'Auth', type: 'select', options: ['none', 'basic', 'bearer']},
    {key: 'prometheus_username', label: 'Username', type: 'text'},
    {key: 'prometheus_password', label: 'Password', type: 'secret'},
    {key: 'prometheus_bearer_token', label: 'Bearer token', type: 'secret'},
    {key: 'prometheus_verify_tls', label: 'Verify TLS', type: 'switch'}]},
  grafana: {icon: '📊', fields: [
    {key: 'grafana_url', label: 'Base URL', type: 'url'},
    {key: 'grafana_token', label: 'API token', type: 'secret'},
    {key: 'grafana_device_dashboard_url', label: 'Device dashboard URL', type: 'text',
     help: 'Supports {hostname} and {ip} placeholders.'},
    {key: 'grafana_embed_mode', label: 'Embed mode', type: 'select', options: ['link', 'iframe'],
     help: 'Links are default: embedding needs allow_embedding, and auth proxies often block iframes.'},
    {key: 'grafana_verify_tls', label: 'Verify TLS', type: 'switch'}]},
  loki: {icon: '📜', fields: [
    {key: 'loki_url', label: 'URL', type: 'url'},
    {key: 'loki_auth_mode', label: 'Auth', type: 'select', options: ['none', 'basic', 'bearer']},
    {key: 'loki_username', label: 'Username', type: 'text'},
    {key: 'loki_password', label: 'Password', type: 'secret'},
    {key: 'loki_bearer_token', label: 'Bearer token', type: 'secret'},
    {key: 'loki_selector_template', label: 'LogQL selector', type: 'text',
     help: 'Supports {ip} and {hostname} placeholders.'},
    {key: 'loki_verify_tls', label: 'Verify TLS', type: 'switch'}]},
  oxidized: {icon: '🗄️', fields: [
    {key: 'oxidized_url', label: 'oxidized-web URL', type: 'url'},
    {key: 'oxidized_username', label: 'Username', type: 'text'},
    {key: 'oxidized_password', label: 'Password', type: 'secret'},
    {key: 'oxidized_node_identity', label: 'Node identity', type: 'select', options: ['hostname', 'ip']},
    {key: 'oxidized_verify_tls', label: 'Verify TLS', type: 'switch'}]},
  kea: {icon: '🌐', fields: [
    {key: 'kea_url', label: 'Control Agent URL', type: 'url'},
    {key: 'kea_username', label: 'Username', type: 'text'},
    {key: 'kea_password', label: 'Password', type: 'secret'},
    {key: 'kea_verify_tls', label: 'Verify TLS', type: 'switch'}]},
  topology_service: {icon: '🕸️', fields: [
    {key: 'topology_service_url', label: 'URL', type: 'url',
     help: 'Optional. The built-in CDP/LLDP topology is unaffected.'},
    {key: 'topology_service_type', label: 'Type', type: 'select', options: ['json', 'svg', 'iframe']},
    {key: 'topology_service_token', label: 'Token', type: 'secret'},
    {key: 'topology_service_verify_tls', label: 'Verify TLS', type: 'switch'}]},
  nsot_git: {icon: '🔀', fields: [
    {key: 'nsot_git_repo_path', label: 'Local repo path', type: 'text',
     help: 'Blank uses each list’s data/lists/{slug}/config_repo.'},
    {key: 'nsot_git_remote_url', label: 'Remote URL', type: 'text', help: 'Optional — a local repo is a complete VCS.'},
    {key: 'nsot_git_branch', label: 'Branch', type: 'text'},
    {key: 'nsot_git_author_name', label: 'Author name', type: 'text'},
    {key: 'nsot_git_author_email', label: 'Author email', type: 'text'},
    {key: 'nsot_git_auth_mode', label: 'Auth', type: 'select', options: ['ssh_key', 'token']},
    {key: 'nsot_git_token', label: 'Token', type: 'secret'},
    {key: 'nsot_git_auto_push', label: 'Auto-push after commit', type: 'switch'}]},
  s3: {icon: '🪣', fields: [
    {key: 's3_endpoint', label: 'Endpoint', type: 'url', help: 'Any S3-compatible endpoint (MinIO, AWS S3, …).'},
    {key: 's3_bucket', label: 'Bucket', type: 'text'},
    {key: 's3_access_key', label: 'Access key', type: 'secret'},
    {key: 's3_secret_key', label: 'Secret key', type: 'secret'},
    {key: 's3_region', label: 'Region', type: 'text'},
    {key: 's3_prefix', label: 'Prefix', type: 'text'},
    {key: 's3_verify_tls', label: 'Verify TLS', type: 'switch'}]},
};

function _intField(f, cfg) {
  const id = 'int_' + f.key;
  const val = cfg[f.key];
  const help = f.help ? `<div class="form-text">${f.help}</div>` : '';
  if (f.type === 'switch') {
    return `<div class="col-md-6"><div class="form-check form-switch mt-4">
      <input class="form-check-input" type="checkbox" role="switch" id="${id}" ${val ? 'checked' : ''}>
      <label class="form-check-label" for="${id}">${f.label}</label></div>${help}</div>`;
  }
  if (f.type === 'select') {
    const opts = f.options.map(o => `<option value="${o}" ${val === o ? 'selected' : ''}>${o}</option>`).join('');
    return `<div class="col-md-6"><label class="form-label fw-semibold">${f.label}</label>
      <select class="form-select form-select-sm" id="${id}">${opts}</select>${help}</div>`;
  }
  if (f.type === 'secret') {
    const isSet = (cfg._secrets || {})[f.key];
    const badge = isSet
      ? '<span class="badge bg-success-subtle text-success-emphasis ms-1">set</span>'
      : '<span class="badge bg-secondary-subtle text-secondary-emphasis ms-1">not set</span>';
    return `<div class="col-md-6"><label class="form-label fw-semibold">${f.label}${badge}</label>
      <input type="password" class="form-control form-control-sm" id="${id}" autocomplete="off"
             placeholder="${isSet ? 'Leave blank to keep' : ''}">
      <div class="form-text">Encrypted at rest; never shown or logged.</div></div>`;
  }
  return `<div class="col-md-6"><label class="form-label fw-semibold">${f.label}</label>
    <input type="${f.type}" class="form-control form-control-sm" id="${id}" value="${val == null ? '' : String(val).replace(/"/g, '&quot;')}">${help}</div>`;
}

async function loadIntegrationSettings() {
  try {
    const r = await fetch('/settings/integrations');
    const d = await r.json();
    if (!d.ok) return;

    const host = document.getElementById('integrationCards');
    host.innerHTML = Object.entries(INTEGRATION_SPEC).map(([name, spec]) => {
      const cfg = d.integrations[name] || {};
      const fields = spec.fields.map(f => _intField(f, cfg)).join('');
      return `<div class="col-12"><div class="card border-light-subtle">
        <div class="card-body py-2 px-3">
          <div class="d-flex justify-content-between align-items-center mb-2">
            <span class="fw-semibold">${spec.icon} ${cfg.label || name}</span>
            <span>
              <span id="intStatus_${name}" class="small text-muted me-2"></span>
              <button type="button" class="btn btn-outline-secondary btn-sm"
                      onclick="testIntegration('${name}')">Test</button>
              <button type="button" class="btn btn-outline-primary btn-sm"
                      onclick="saveIntegration('${name}')">Save</button>
            </span>
          </div>
          <div class="row g-2">${fields}</div>
        </div></div></div>`;
    }).join('');

    loadIntegrationStatus();
  } catch (e) { console.error('loadIntegrationSettings', e); }
}

async function loadIntegrationStatus() {
  try {
    const r = await fetch('/settings/integrations/status');
    const d = await r.json();
    if (!d.ok) return;
    const cls = {up: 'bg-success', down: 'bg-danger', not_configured: 'bg-secondary'};
    document.getElementById('integrationStatusStrip').innerHTML = d.statuses.map(s =>
      `<span class="badge ${cls[s.state] || 'bg-secondary'}" title="${(s.message || '').replace(/"/g, '&quot;')}">
         ${s.label}</span>`).join('');
  } catch (e) { console.error('loadIntegrationStatus', e); }
}

function _collectIntegration(name) {
  const out = {};
  for (const f of INTEGRATION_SPEC[name].fields) {
    const el = document.getElementById('int_' + f.key);
    if (!el) continue;
    if (f.type === 'switch') out[f.key] = el.checked;
    else if (f.type === 'secret') { if (el.value) out[f.key] = el.value; }
    else out[f.key] = el.value;
  }
  return out;
}

async function saveIntegration(name) {
  const el = document.getElementById('intStatus_' + name);
  try {
    const r = await fetch(`/settings/integrations/${name}`, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(_collectIntegration(name)),
    });
    const d = await r.json();
    el.className = 'small me-2 ' + (d.ok ? 'text-success' : 'text-danger');
    el.textContent = d.ok ? 'Saved' : (d.error || 'Save failed');
    if (d.ok) {
      /* CHECK WHAT CAME BACK. The save is followed by a re-render from the
         server, so a field that did not persist is redrawn with the stored
         value and simply appears to clear — the same silent-drop shape as a
         control missing from the save payload, one layer further on. A
         non-secret field that empties itself must say so.

         Secrets are skipped: they are never echoed, by design. */
      const sent = _collectIntegration(name);
      const back = d.integration || {};
      const secret = new Set(INTEGRATION_SPEC[name].fields
        .filter(f => f.type === 'secret').map(f => f.key));
      const lost = Object.keys(sent).filter(k =>
        !secret.has(k) && JSON.stringify(back[k]) !== JSON.stringify(sent[k]));
      if (lost.length) {
        el.className = 'small me-2 text-warning';
        el.textContent = `Saved, but ${lost.join(', ')} did not persist`;
        showToast(`${name}: ${lost.join(', ')} did not persist as sent — `
                  + 'the field will redraw with the stored value.', 'warning');
      }
      loadIntegrationSettings();
    }
  } catch (e) { el.className = 'small me-2 text-danger'; el.textContent = e.message; }
}

async function testIntegration(name) {
  const el = document.getElementById('intStatus_' + name);
  el.className = 'small me-2 text-muted';
  el.textContent = 'Testing…';
  try {
    const r = await fetch(`/settings/integrations/${name}/test`, {method: 'POST'});
    const d = await r.json();
    el.className = 'small me-2 ' + (d.ok ? 'text-success' : 'text-danger');
    el.textContent = d.ok ? (d.message || 'OK') : (d.error || 'Failed');
  } catch (e) { el.className = 'small me-2 text-danger'; el.textContent = e.message; }
  loadIntegrationStatus();
}

const _GENERAL_MAP = {
  flask_host: 'settingsFlaskHost', flask_port: 'settingsFlaskPort',
  auto_open_browser: 'settingsAutoOpenBrowser', tftp_root: 'settingsTftpRoot',
  jenkins_step_shell: 'settingsJenkinsStepShell',
  collector_trap_enabled: 'settingsCollectorTrap',
  collector_netflow_enabled: 'settingsCollectorNetflow',
  collector_syslog_enabled: 'settingsCollectorSyslog',
  monitoring_identity_mode: 'settingsMonIdentityMode',
  monitoring_identity_field: 'settingsMonIdentityField',
  monitoring_prom_label: 'settingsMonPromLabel',
  monitoring_strip_port: 'settingsMonStripPort',
  promql_device_up: 'settingsPromqlDeviceUp', promql_cpu: 'settingsPromqlCpu',
  promql_interface_oper: 'settingsPromqlInterfaceOper',
};

async function loadGeneralIntegrationSettings() {
  try {
    const r = await fetch('/settings/integrations/general');
    const d = await r.json();
    if (!d.ok) return;
    for (const [key, id] of Object.entries(_GENERAL_MAP)) {
      const el = document.getElementById(id);
      if (!el) continue;
      if (el.type === 'checkbox') el.checked = !!d.settings[key];
      else el.value = d.settings[key] == null ? '' : d.settings[key];
    }
  } catch (e) { console.error('loadGeneralIntegrationSettings', e); }
}

/* Called from saveSettings() in index.html so the existing Save button
   persists these alongside the settings it already owns. */
async function saveGeneralIntegrationSettings() {
  const payload = {};
  for (const [key, id] of Object.entries(_GENERAL_MAP)) {
    const el = document.getElementById(id);
    if (!el) continue;
    if (el.type === 'checkbox') payload[key] = el.checked;
    else if (el.type === 'number') payload[key] = parseInt(el.value, 10) || undefined;
    else payload[key] = el.value;
  }
  try {
    const r = await fetch('/settings/integrations/general', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload),
    });
    return await r.json();
  } catch (e) { return {ok: false, error: e.message}; }
}
