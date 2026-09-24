// ── State per view ────────────────────────────────────────────────────────
const _topoNetworks   = { cdp: null, ospf: null, bgp: null, tunnel: null };
const _topoData       = { cdp: null, ospf: null, bgp: null, tunnel: null };
const _topoPositions  = { cdp: {},   ospf: {},   bgp: {},   tunnel: {} };
const _topoHidden     = { cdp: new Set(), ospf: new Set(), bgp: new Set(), tunnel: new Set() };
let   _selectedNodeId = { cdp: null, ospf: null, bgp: null, tunnel: null };
let   _topoSaveTimer  = null;
let   _protoLoaded    = false;       // have we fetched protocol state this session?

// ── Link status polling state ─────────────────────────────────────────────
let _cdpEdgesDataSet  = null;   // vis.DataSet for CDP edges (kept for live updates)
let _cdpRawEdges      = [];     // raw edge objects from last render
let _linkStatusTimer  = null;   // setInterval handle

// Per-view protocol polling state
const _protoEdgesDataSet = { ospf: null, bgp: null, tunnel: null };
const _protoRawEdges     = { ospf: [],   bgp: [],   tunnel: [] };
const _protoLinkTimers   = { ospf: null, bgp: null, tunnel: null };

// ── Helpers ───────────────────────────────────────────────────────────────
const _isDark = () => document.documentElement.getAttribute('data-bs-theme') === 'dark';

function _fontColor()      { return _isDark() ? '#dee2e6' : '#333333'; }
function _edgeColor()      { return _isDark() ? '#6c757d' : '#888888'; }
function _edgeLabelColor() { return _isDark() ? '#adb5bd' : '#555555'; }
function _strokeColor()    { return _isDark() ? '#212529' : '#ffffff'; }

function _containerFor(view) { return document.getElementById(`topo${_cap(view)}Container`); }
function _placeholderFor(v)  { return document.getElementById(`topo${_cap(v)}Placeholder`); }
function _cap(s)             { return s.charAt(0).toUpperCase() + s.slice(1); }

// ── CDP position persistence ──────────────────────────────────────────────
function saveTopoPositions() {
  clearTimeout(_topoSaveTimer);
  _topoSaveTimer = setTimeout(() => {
    const net = _topoNetworks.cdp;
    if (!net) return;
    const pos = net.getPositions();
    fetch('/topology/positions', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ positions: pos })
    }).catch(() => {});
    _topoPositions.cdp = pos;
  }, 800);
}

function saveProtoPositions(view) {
  const net = _topoNetworks[view];
  if (!net) return;
  const pos = net.getPositions();
  fetch('/topology/proto_positions', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ view, positions: pos })
  }).catch(() => {});
  _topoPositions[view] = pos;
}

function saveHiddenNodes() {
  fetch('/topology/hidden', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ hidden: Array.from(_topoHidden.cdp) })
  }).catch(() => {});
}

function saveProtoHidden(view) {
  fetch('/topology/proto_hidden', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ view, hidden: Array.from(_topoHidden[view]) })
  }).catch(() => {});
}

// ── Hidden-node UI (all views) ────────────────────────────────────────────
function updateHiddenUI(view) {
  const cap      = _cap(view);
  const dropId   = view === 'cdp' ? 'topoHiddenDropdown'  : `topo${cap}HiddenDropdown`;
  const countId  = view === 'cdp' ? 'topoHiddenCount'     : `topo${cap}HiddenCount`;
  const listId   = view === 'cdp' ? 'topoHiddenList'      : `topo${cap}HiddenList`;
  const dropdown = document.getElementById(dropId);
  const countEl  = document.getElementById(countId);
  const listEl   = document.getElementById(listId);
  if (!dropdown) return;
  const hidden = _topoHidden[view];
  countEl.textContent = hidden.size;
  dropdown.style.display = hidden.size > 0 ? '' : 'none';
  listEl.innerHTML = '<li><h6 class="dropdown-header">Hidden devices — click to restore</h6></li>';
  hidden.forEach(id => {
    const topo  = _topoData[view];
    const label = topo ? (topo.nodes.find(n => n.id === id)?.label || id) : id;
    const li = document.createElement('li');
    const escapedId = id.replace(/'/g, "\\'");
    li.innerHTML = `<button class="dropdown-item" onclick="restoreNode('${view}','${escapedId}')">&#8635; ${label}</button>`;
    listEl.appendChild(li);
  });
}

window.hideSelectedNode = function() {
  if (!_selectedNodeId.cdp || !_topoData.cdp) return;
  _topoHidden.cdp.add(_selectedNodeId.cdp);
  saveHiddenNodes();
  document.getElementById('topoDetailsPanel').style.display = 'none';
  renderCdpTopology(_topoData.cdp, _topoPositions.cdp);
};

window.hideProtoNode = function(view) {
  const nodeId = _selectedNodeId[view];
  if (!nodeId || !_topoData[view]) return;
  _topoHidden[view].add(nodeId);
  saveProtoHidden(view);
  document.getElementById(`topo${_cap(view)}Details`).style.display = 'none';
  renderProtoTopology(view, _topoData[view], _topoPositions[view]);
};

window.restoreNode = function(view, id) {
  _topoHidden[view].delete(id);
  if (view === 'cdp') {
    saveHiddenNodes();
    if (_topoData.cdp) renderCdpTopology(_topoData.cdp, _topoPositions.cdp);
  } else {
    saveProtoHidden(view);
    if (_topoData[view]) renderProtoTopology(view, _topoData[view], _topoPositions[view]);
  }
  updateHiddenUI(view);
};

// ── Load saved state on tab open ──────────────────────────────────────────
function loadSavedTopology() {
  if (_topoNetworks.cdp) return;
  fetch('/topology/state')
    .then(r => r.json())
    .then(data => {
      if (data.topology && data.topology.nodes && data.topology.nodes.length > 0) {
        _topoData.cdp = data.topology;
        _topoPositions.cdp = data.positions || {};
        _topoHidden.cdp = new Set(data.hidden || []);
        renderCdpTopology(data.topology, _topoPositions.cdp);
      } else {
        // No saved topology — auto-discover immediately
        discoverTopology();
      }
    }).catch(() => {
      // On error also try to discover
      discoverTopology();
    });
}

function loadSavedProtoTopology() {
  if (_protoLoaded) return;
  _protoLoaded = true;
  fetch('/topology/protocol_state')
    .then(r => r.json())
    .then(data => {
      const positions = data.positions || {};
      const hidden    = data.hidden    || {};
      ['ospf', 'bgp', 'tunnel'].forEach(v => {
        const topo = data[v];
        if (topo && topo.nodes && topo.nodes.length > 0) {
          _topoData[v]      = topo;
          _topoPositions[v] = positions[v] || {};
          _topoHidden[v]    = new Set(hidden[v] || []);
        }
      });
    }).catch(() => {});
}

// ── CDP Discovery ─────────────────────────────────────────────────────────
// Keep the Discover button disabled whenever neither protocol is checked —
// there'd be nothing for the backend to query.
window.updateTopoDiscoverBtn = function() {
  const btn  = document.getElementById('topoDiscoverBtn');
  const cdp  = document.getElementById('topoProtoCdp');
  const lldp = document.getElementById('topoProtoLldp');
  if (!btn || !cdp || !lldp) return;
  btn.disabled = !cdp.checked && !lldp.checked;
};

window.discoverTopology = function() {
  const btn = document.getElementById('topoDiscoverBtn');
  const btnText = btn.querySelector('.btn-text');
  const spinner = btn.querySelector('.spinner-border');
  const cdp  = document.getElementById('topoProtoCdp')?.checked ?? true;
  const lldp = document.getElementById('topoProtoLldp')?.checked ?? true;
  btnText.textContent = 'Discovering...';
  spinner.classList.remove('d-none');
  btn.disabled = true;

  fetch(`/topology_data?cdp=${cdp ? 1 : 0}&lldp=${lldp ? 1 : 0}`)
    .then(r => r.json())
    .then(data => {
      btnText.textContent = 'Discover Topology';
      spinner.classList.add('d-none');
      updateTopoDiscoverBtn();
      if (data.status === 'success') {
        // Capture live positions of currently-rendered nodes before replacing data
        const mergedPositions = Object.assign({}, _topoPositions.cdp);
        if (_topoNetworks.cdp && _topoData.cdp) {
          (_topoData.cdp.nodes || []).forEach(n => {
            try {
              const pos = _topoNetworks.cdp.getPosition(n.id);
              if (pos && (pos.x !== 0 || pos.y !== 0)) mergedPositions[n.id] = pos;
            } catch(_) {}
          });
        }
        _topoData.cdp      = data.topology;
        _topoPositions.cdp = mergedPositions;
        renderCdpTopology(data.topology, mergedPositions);

        const newIds  = new Set(data.topology.nodes.map(n => n.id));
        const n = data.topology.nodes.length, e = data.topology.edges.length;
        if (n === 0)
          showToast('No topology data found. Ensure devices are online and CDP or LLDP is enabled.', 'warning');
        else
          showToast(`Topology updated: ${n} node(s), ${e} link(s)`, 'success');
      } else {
        showToast(data.message || 'Topology discovery failed', 'danger');
      }
    })
    .catch(() => {
      btnText.textContent = 'Discover Topology';
      spinner.classList.add('d-none');
      updateTopoDiscoverBtn();
      showToast('Failed to discover topology', 'danger');
    });
};

// ── Protocol Discovery (OSPF / BGP / Tunnel) ──────────────────────────────
window.discoverProtoTopology = function(view, btn) {
  const btnText = btn.querySelector('.btn-text');
  const spinner = btn.querySelector('.spinner-border');
  btnText.textContent = 'Discovering...';
  spinner.classList.remove('d-none');
  btn.disabled = true;

  fetch('/topology/protocol_data')
    .then(r => r.json())
    .then(data => {
      btnText.textContent = `Discover ${_cap(view)}`;
      spinner.classList.add('d-none');
      btn.disabled = false;
      if (data.status !== 'success') {
        showToast(data.message || 'Discovery failed', 'danger');
        return;
      }
      ['ospf', 'bgp', 'tunnel'].forEach(v => {
        if (data[v]) {
          // Capture live positions before replacing data so user layout is preserved
          const liveNet = _topoNetworks[v];
          const livePos = liveNet ? liveNet.getPositions() : {};
          _topoData[v] = data[v];
          // Merge: keep saved positions for nodes still present, let new nodes auto-position
          const merged = Object.assign({}, _topoPositions[v], livePos);
          const newIds  = new Set(data[v].nodes.map(n => n.id));
          _topoPositions[v] = Object.fromEntries(
            Object.entries(merged).filter(([id]) => newIds.has(id))
          );
        }
      });
      renderProtoTopology(view, _topoData[view], _topoPositions[view]);
      const n = data[view]?.nodes?.length ?? 0;
      const e = data[view]?.edges?.length ?? 0;
      showToast(`${_cap(view)} topology: ${n} node(s), ${e} link(s)`, n > 0 ? 'success' : 'warning');
    })
    .catch(() => {
      btnText.textContent = `Discover ${_cap(view)}`;
      spinner.classList.add('d-none');
      btn.disabled = false;
      showToast('Discovery failed', 'danger');
    });
};

// ── Reset view ────────────────────────────────────────────────────────────
window.resetTopoView = function(view) {
  const net = _topoNetworks[view];
  if (net) net.fit({ animation: { duration: 500, easingFunction: 'easeInOutQuad' } });
};

// ── Shared vis.js helpers ─────────────────────────────────────────────────
function _nodeIcon(role) {
  if (role === 'switch')   return 'https://img.icons8.com/color/48/switch.png';
  if (role === 'firewall') return 'https://img.icons8.com/color/48/firewall.png';
  return 'https://img.icons8.com/color/48/router.png';
}

function _makeVisNode(node, savedPos, opts = {}) {
  const pos = savedPos[node.id];
  const obj = {
    id:    node.id,
    label: node.label,
    title: node.title,
    shape: 'image',
    image: opts.image || 'https://img.icons8.com/color/48/router.png',
    size:  opts.size  || 30,
    font:  { size: 13, color: _fontColor(), bold: { color: _fontColor() } },
    borderWidth: opts.borderWidth || 2,
    color: opts.color || {
      border:    '#0d6efd',
      background:'#cfe2ff',
      highlight: { border: '#0a58ca', background: '#9ec5fe' }
    },
    shadow: true,
  };
  if (pos) { obj.x = pos.x; obj.y = pos.y; obj.fixed = false; }
  return obj;
}

function _makeVisNetwork(container, nodes, edges) {
  return new vis.Network(container, { nodes, edges }, {
    nodes:  { shapeProperties: { useImageSize: false, useBorderWithImage: true, interpolation: false } },
    edges:  { smooth: { type: 'continuous' } },
    physics: { enabled: false },
    interaction: { hover: true, tooltipDelay: 200, navigationButtons: true, keyboard: true, zoomView: true },
    layout:  { improvedLayout: true }
  });
}

// Stable string key for a CDP edge — matches the backend's link_status key format.
function _edgeKey(edge) {
  return `${edge.from}|${edge.from_intf||''}|${edge.to}|${edge.to_intf||''}`;
}

// After layout, reorder each edge label so the left-side interface name
// always appears on the left of the ↔ symbol.  Called once after the first
// draw (positions are stable then) and again after every node drag.
function _fixEdgeLabels(net, edgesDataSet, rawEdges) {
  const updates = [];
  rawEdges.forEach(edge => {
    if (!edge.from_label || !edge.to_label) return;
    const fp = net.getPosition(edge.from);
    const tp = net.getPosition(edge.to);
    if (!fp || !tp) return;
    const label = fp.x <= tp.x
      ? `${edge.from_label}  \u2194  ${edge.to_label}`
      : `${edge.to_label}  \u2194  ${edge.from_label}`;
    updates.push({ id: _edgeKey(edge), label });
  });
  if (updates.length) edgesDataSet.update(updates);
}

// ── Link status polling ────────────────────────────────────────────────────
window.setLinkStatusInterval = function(seconds) {
  if (_linkStatusTimer) { clearInterval(_linkStatusTimer); _linkStatusTimer = null; }
  const ms = parseInt(seconds, 10) * 1000;
  const badge = document.getElementById('linkStatusBadge');
  if (ms <= 0) {
    if (badge) badge.style.display = 'none';
    return;
  }
  if (badge) { badge.style.display = ''; badge.className = 'badge bg-secondary'; badge.textContent = 'checking…'; }
  updateLinkStatus();
  _linkStatusTimer = setInterval(updateLinkStatus, ms);
};

function updateLinkStatus() {
  if (!_cdpEdgesDataSet || !_cdpRawEdges.length) return;
  fetch('/topology/link_status')
    .then(r => r.json())
    .then(data => {
      if (data.status !== 'ok') return;
      const updates = _cdpRawEdges.map(edge => {
        const key = _edgeKey(edge);
        const status = data.links[key];
        let color;
        if (status === 'up')        color = '#198754';   // green
        else if (status === 'down') color = '#dc3545';   // red
        else                        color = _edgeColor(); // theme default (unknown)
        return { id: key, color: { color, highlight: '#0d6efd' } };
      });
      _cdpEdgesDataSet.update(updates);

      const vals   = Object.values(data.links);
      const upCnt  = vals.filter(s => s === 'up').length;
      const dwnCnt = vals.filter(s => s === 'down').length;
      const total  = vals.length;
      const badge  = document.getElementById('linkStatusBadge');
      if (badge && total > 0) {
        badge.style.display = '';
        if (dwnCnt > 0) {
          badge.className   = 'badge bg-danger';
          badge.textContent = `${dwnCnt} link${dwnCnt > 1 ? 's' : ''} down`;
        } else {
          badge.className   = 'badge bg-success';
          badge.textContent = `${upCnt}/${total} up`;
        }
      }
    })
    .catch(() => {});
}

// ── Protocol link status polling ──────────────────────────────────────────
function _protoEdgeKey(view, edge) {
  if (view === 'tunnel') return `${edge.from}|${edge.tunnel||''}|${edge.to}`;
  return `${edge.from}|${edge.to}`;
}

window.setProtoLinkStatusInterval = function(view, seconds) {
  if (_protoLinkTimers[view]) { clearInterval(_protoLinkTimers[view]); _protoLinkTimers[view] = null; }
  const ms = parseInt(seconds, 10) * 1000;
  const badge = document.getElementById(`${view}LinkBadge`);
  if (ms <= 0) {
    if (badge) badge.style.display = 'none';
    return;
  }
  if (badge) { badge.style.display = ''; badge.className = 'badge bg-secondary'; badge.textContent = 'checking…'; }
  _updateProtoLinkStatus(view);
  _protoLinkTimers[view] = setInterval(() => _updateProtoLinkStatus(view), ms);
};

function _updateProtoLinkStatus(view) {
  if (!_protoEdgesDataSet[view] || !_protoRawEdges[view].length) return;
  fetch(`/topology/proto_link_status?view=${view}`)
    .then(r => r.json())
    .then(data => {
      if (data.status !== 'ok') return;
      const updates = _protoRawEdges[view].map(edge => {
        const key    = _protoEdgeKey(view, edge);
        const status = data.links[key];
        let color;
        if (status === 'up')        color = '#198754';   // green
        else if (status === 'down') color = '#dc3545';   // red
        else if (view === 'tunnel') color = '#fd7e14';   // orange (unknown tunnel)
        else                        color = _edgeColor(); // theme default
        return { id: key, color: { color, highlight: '#0d6efd' } };
      });
      _protoEdgesDataSet[view].update(updates);

      const vals   = Object.values(data.links);
      const upCnt  = vals.filter(s => s === 'up').length;
      const dwnCnt = vals.filter(s => s === 'down').length;
      const total  = vals.length;
      const badge  = document.getElementById(`${view}LinkBadge`);
      if (badge && total > 0) {
        badge.style.display = '';
        if (dwnCnt > 0) {
          badge.className   = 'badge bg-danger';
          badge.textContent = `${dwnCnt} down`;
        } else {
          badge.className   = 'badge bg-success';
          badge.textContent = `${upCnt}/${total} up`;
        }
      }
    })
    .catch(() => {});
}

// ── CDP Render ────────────────────────────────────────────────────────────
function renderCdpTopology(topology, savedPositions) {
  savedPositions = savedPositions || {};
  const container   = document.getElementById('topoCdpContainer');
  const placeholder = document.getElementById('topoCdpPlaceholder');
  if (placeholder) placeholder.style.display = 'none';

  const visibleNodes   = topology.nodes.filter(n => !_topoHidden.cdp.has(n.id));
  const visibleNodeIds = new Set(visibleNodes.map(n => n.id));
  const visibleEdges   = topology.edges.filter(e => visibleNodeIds.has(e.from) && visibleNodeIds.has(e.to));
  updateHiddenUI('cdp');

  const nodes = new vis.DataSet(visibleNodes.map(node => {
    const isManaged = node.type === 'managed';
    const role = node.role || (isManaged ? 'router' : 'switch');
    return _makeVisNode(node, savedPositions, {
      image:       _nodeIcon(role),
      size:        isManaged ? 35 : 28,
      borderWidth: isManaged ? 3 : 2,
      color: {
        border:    isManaged ? '#0d6efd' : '#6c757d',
        background:isManaged ? '#cfe2ff' : '#e2e3e5',
        highlight: { border: isManaged ? '#0a58ca' : '#495057', background: isManaged ? '#9ec5fe' : '#c4c5c7' }
      }
    });
  }));

  const edges = new vis.DataSet(visibleEdges.map(edge => ({
    id:    _edgeKey(edge),
    from:  edge.from,
    to:    edge.to,
    label: (edge.from_label && edge.to_label) ? `${edge.from_label}  \u2194  ${edge.to_label}` : '',
    title: edge.title || '',
    font:  { size: 10, color: _edgeLabelColor(), strokeWidth: 3, strokeColor: _strokeColor(), align: 'middle', multi: true },
    color: { color: _edgeColor(), highlight: '#0d6efd' },
    width: 2,
    smooth: { type: 'continuous' },
  })));

  // Store for live link-status updates
  _cdpEdgesDataSet = edges;
  _cdpRawEdges     = visibleEdges;

  if (_topoNetworks.cdp) _topoNetworks.cdp.destroy();
  const net = _makeVisNetwork(container, nodes, edges);
  _topoNetworks.cdp = net;
  net.once('afterDrawing', () => _fixEdgeLabels(net, edges, visibleEdges));
  net.on('dragEnd', () => _fixEdgeLabels(net, edges, visibleEdges));

  net.on('click', params => {
    const panel = document.getElementById('topoDetailsPanel');
    const titleEl = document.getElementById('topoDetailTitle');
    const bodyEl  = document.getElementById('topoDetailBody');
    if (params.nodes.length > 0) {
      const nodeId = params.nodes[0];
      _selectedNodeId.cdp = nodeId;
      const node = topology.nodes.find(n => n.id === nodeId);
      if (node) {
        titleEl.textContent = node.label;
        bodyEl.innerHTML    = node.title;
        const connEdges = topology.edges.filter(e => e.from === nodeId || e.to === nodeId);
        if (connEdges.length) {
          let html = '<hr><strong>Connected Links:</strong><ul class="mb-0 mt-1">';
          connEdges.forEach(e => {
            const peer      = e.from === nodeId ? topology.nodes.find(n => n.id === e.to)?.label || e.to : topology.nodes.find(n => n.id === e.from)?.label || e.from;
            const localIntf = e.from === nodeId ? e.from_label : e.to_label;
            const remIntf   = e.from === nodeId ? e.to_label   : e.from_label;
            html += `<li>${localIntf} &harr; ${peer} (${remIntf})`;
            const ips = [e.local_ip, e.remote_ip].filter(Boolean).join(', ');
            if (ips) html += ` <span class="text-muted">[${ips}]</span>`;
            html += '</li>';
          });
          html += '</ul>';
          bodyEl.innerHTML += html;
        }
        panel.style.display = 'block';
      }
    } else {
      _selectedNodeId.cdp = null;
      panel.style.display = 'none';
    }
  });
  net.on('dragEnd', p => { if (p.nodes?.length) saveTopoPositions(); });
  setTimeout(() => net.fit({ animation: { duration: 400, easingFunction: 'easeInOutQuad' } }), 150);

  // (Re)start link-status polling at whatever interval the user has selected
  const sel = document.getElementById('linkStatusIntervalSelect');
  if (sel) setLinkStatusInterval(sel.value);
}

// ── Protocol Render (OSPF / BGP / Tunnel) ─────────────────────────────────
function renderProtoTopology(view, topology, savedPositions) {
  if (!topology || !topology.nodes) return;
  savedPositions = savedPositions || {};
  const container   = _containerFor(view);
  const placeholder = _placeholderFor(view);
  if (placeholder) placeholder.style.display = 'none';

  const hiddenSet    = _topoHidden[view];
  const visibleNodes = topology.nodes.filter(n => !hiddenSet.has(n.id));
  const visibleIds   = new Set(visibleNodes.map(n => n.id));
  const visibleEdges = topology.edges.filter(e => visibleIds.has(e.from) && visibleIds.has(e.to));
  updateHiddenUI(view);

  // Build nodes
  const nodes = new vis.DataSet(visibleNodes.map(node => {
    const isManaged  = node.type === 'managed';
    const isExternal = node.type === 'external';
    let color;
    if (view === 'bgp' && isExternal)
      color = { border: '#6f42c1', background: '#e2d9f3', highlight: { border: '#59359a', background: '#cdb8f5' } };
    else if (isManaged)
      color = { border: '#0d6efd', background: '#cfe2ff', highlight: { border: '#0a58ca', background: '#9ec5fe' } };
    else
      color = { border: '#6c757d', background: '#e2e3e5', highlight: { border: '#495057', background: '#c4c5c7' } };
    return _makeVisNode(node, savedPositions, {
      image: _nodeIcon(node.role || (isManaged ? 'router' : 'switch')),
      size:  isManaged ? 35 : 28,
      borderWidth: isManaged ? 3 : 2,
      color,
    });
  }));

  // Build edges with color by state
  const edges = new vis.DataSet(visibleEdges.map(edge => {
    let edgeColor = _edgeColor();
    let label = '';
    if (view === 'ospf') {
      edgeColor = edge.established ? '#198754' : '#dc3545';
      const area = edge.area !== '' && edge.area !== undefined ? `Area ${edge.area}` : '';
      const state = edge.state || '';
      label = [area, state].filter(Boolean).join('\n');
    } else if (view === 'bgp') {
      edgeColor = edge.established ? '#198754' : '#dc3545';
      const asLabel = `AS${edge.local_as} ↔ AS${edge.remote_as}`;
      label = edge.established ? asLabel : `${asLabel}\n${edge.state}`;
    } else if (view === 'tunnel') {
      edgeColor = '#fd7e14';
      label     = edge.tunnel || '';
    } else if (edge.from_label && edge.to_label) {
      label = `${edge.from_label}  \u2194  ${edge.to_label}`;
    }
    return {
      id:    _protoEdgeKey(view, edge),
      from:  edge.from,
      to:    edge.to,
      label,
      title: edge.title || '',
      font:  { size: 10, color: _edgeLabelColor(), strokeWidth: 3, strokeColor: _strokeColor(), align: 'middle', multi: true },
      color: { color: edgeColor, highlight: '#0d6efd' },
      width: 2,
      smooth: { type: 'continuous' },
    };
  }));

  // Store for live link-status updates
  _protoEdgesDataSet[view] = edges;
  _protoRawEdges[view]     = visibleEdges;

  if (_topoNetworks[view]) _topoNetworks[view].destroy();
  const net = _makeVisNetwork(container, nodes, edges);
  _topoNetworks[view] = net;

  // Details panels per view
  const detailPanelId = `topo${_cap(view)}Details`;
  const detailTitleId = `topo${_cap(view)}DetailTitle`;
  const detailBodyId  = `topo${_cap(view)}DetailBody`;

  net.on('click', params => {
    const panel  = document.getElementById(detailPanelId);
    const titleEl= document.getElementById(detailTitleId);
    const bodyEl = document.getElementById(detailBodyId);
    if (!panel) return;
    if (params.nodes.length > 0) {
      const nodeId = params.nodes[0];
      _selectedNodeId[view] = nodeId;
      const node   = topology.nodes.find(n => n.id === nodeId);
      if (!node) return;
      titleEl.textContent = node.label;
      bodyEl.innerHTML    = node.title || `<b>${node.label}</b>`;
      // Connected edges
      const connEdges = topology.edges.filter(e => e.from === nodeId || e.to === nodeId);
      if (connEdges.length) {
        let html = '<hr><strong>Connections:</strong><ul class="mb-0 mt-1">';
        connEdges.forEach(e => {
          const peer = e.from === nodeId
            ? topology.nodes.find(n => n.id === e.to)?.label  || e.to
            : topology.nodes.find(n => n.id === e.from)?.label || e.from;
          html += `<li>${e.title || peer}</li>`;
        });
        html += '</ul>';
        bodyEl.innerHTML += html;
      }
      panel.style.display = 'block';
    } else {
      _selectedNodeId[view] = null;
      panel.style.display = 'none';
    }
  });

  net.on('dragEnd', p => { if (p.nodes?.length) saveProtoPositions(view); });
  setTimeout(() => net.fit({ animation: { duration: 400, easingFunction: 'easeInOutQuad' } }), 150);

  // (Re)start link-status polling at whatever interval the user has selected
  const selId = { ospf: 'ospfLinkIntervalSelect', bgp: 'bgpLinkIntervalSelect', tunnel: 'tunnelLinkIntervalSelect' }[view];
  const sel = selId ? document.getElementById(selId) : null;
  if (sel) setProtoLinkStatusInterval(view, sel.value);
}

// ── Init ──────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  // Load CDP topology when the main Topology tab first opens
  const topoTab = document.getElementById('topology-tab');
  if (topoTab) {
    topoTab.addEventListener('shown.bs.tab', () => {
      loadSavedTopology();
      loadSavedProtoTopology();
    });
  }

  // When switching to a protocol sub-tab, render cached data if available
  ['ospf', 'bgp', 'tunnel'].forEach(view => {
    const tab = document.getElementById(`topo-${view}-tab`);
    if (tab) {
      tab.addEventListener('shown.bs.tab', () => {
        if (_topoData[view] && !_topoNetworks[view]) {
          renderProtoTopology(view, _topoData[view], _topoPositions[view]);
        }
      });
    }
  });
});
