/* Organize Tab: Markdown + LaTeX Math Renderer + Favorites & Grid/List View */
function safeHttpUrl(url) {
  const s = String(url || '').trim();
  return /^https?:\/\//i.test(s) ? s : '';
}

function renderLatex(tex, displayMode) {
  if (window.katex) {
    try {
      return window.katex.renderToString(tex.trim(), { displayMode, throwOnError: false });
    } catch (e) {}
  }
  return `<code>${escapeHtml(tex)}</code>`;
}

function parseMarkdown(md) {
  const mathPlaceholders = [];
  const codePlaceholders = [];

  let text = (md || '').replace(/\r\n/g, '\n');
  text = text.replace(/```math[ \t]*\n([\s\S]*?)(?:```|$)/g, (_, tex) => {
    const idx = mathPlaceholders.length;
    mathPlaceholders.push(`<div class="math-block">${renderLatex(tex, true)}</div>`);
    return `@@MATH_BLOCK_${idx}@@`;
  });

  text = text.replace(/\$\$([\s\S]*?)\$\$/g, (_, tex) => {
    const idx = mathPlaceholders.length;
    mathPlaceholders.push(`<div class="math-block">${renderLatex(tex, true)}</div>`);
    return `@@MATH_BLOCK_${idx}@@`;
  });

  text = text.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
    const escaped = code.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    const idx = codePlaceholders.length;
    codePlaceholders.push(`<pre><code>${escaped}</code></pre>`);
    return `@@CODE_BLOCK_${idx}@@`;
  });

  text = text.replace(/\$([^\$\n]+?)\$/g, (_, tex) => {
    const idx = mathPlaceholders.length;
    mathPlaceholders.push(renderLatex(tex, false));
    return `@@MATH_BLOCK_${idx}@@`;
  });

  let html = text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/^---$/gm, '<hr>')
    .replace(/^# (.*$)/gm, '<h1>$1</h1>')
    .replace(/^## (.*$)/gm, '<h2>$1</h2>')
    .replace(/^### (.*$)/gm, '<h3>$1</h3>')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer" class="md-link">$1</a>')
    .replace(/^- (.*$)/gm, '<li>$1</li>');

  html = html.replace(/(<li>.*<\/li>)/gs, '<ul>$1</ul>');

  html = html.split('\n\n').map(block => {
    const t = block.trim();
    if (!t) return '';
    if (t.startsWith('<h') || t.startsWith('<pre') || t.startsWith('<ul') || t.startsWith('<hr') || t.startsWith('@@MATH_BLOCK_') || t.startsWith('@@CODE_BLOCK_')) {
      return t;
    }
    return `<p>${t.replace(/\n/g, ' ')}</p>`;
  }).join('');

  codePlaceholders.forEach((val, idx) => { html = html.replace(`@@CODE_BLOCK_${idx}@@`, val); });
  mathPlaceholders.forEach((val, idx) => { html = html.replace(`@@MATH_BLOCK_${idx}@@`, val); });
  return html;
}

function renderCodeWithLines(codeStr) {
  const lines = (codeStr || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').split('\n');
  const rows = lines.map((line, i) => `
    <tr>
      <td class="code-line-num">${i + 1}</td>
      <td>${line || ' '}</td>
    </tr>
  `).join('');
  return `<table class="code-table"><tbody>${rows}</tbody></table>`;
}

function setOrgViewMode(mode) {
  orgViewMode = mode;
  document.getElementById('sw-doc').classList.toggle('active', mode === 'doc');
  document.getElementById('sw-code').classList.toggle('active', mode === 'code');
  renderOrganizeTab();
}

function toggleOrgLayoutMode() {
  const orgLayout = document.getElementById('org-layout');
  const listEl = document.getElementById('org-algo-list');
  const btn = document.getElementById('org-layout-btn');
  const numBtn = document.getElementById('org-num-toggle-btn');
  if (!listEl) return;
  orgGridMode = !orgGridMode;
  orgGridFadePending = orgGridMode;
  if (orgLayout) orgLayout.classList.toggle('grid-fullscreen', orgGridMode);
  listEl.classList.toggle('grid-mode', orgGridMode);
  listEl.classList.toggle('num-toggled', orgGridMode && orgNumMode !== 'none');
  listEl.classList.remove('num-mode-none', 'num-mode-all', 'num-mode-favs');
  listEl.classList.add('num-mode-' + orgNumMode);
  if (btn) btn.innerText = orgGridMode ? 'List View' : 'Grid View';
  if (numBtn) numBtn.style.display = orgGridMode ? 'inline-flex' : 'none';
  document.getElementById('org-hw-override-btn').style.display = orgGridMode ? 'inline-flex' : 'none';
  renderOrganizeTab();
}

let overrideHardware = false;

const HW_CHECK_MS = 3000;
// A little longer than --panel-dur, so the list rebuild that follows the save never cuts a fade short.
const HW_FADE_MS = 400;
let hwCheckTimer = null;
let hwSyncHoldUntil = 0;

function toggleHardwareOverride() {
  overrideHardware = !overrideHardware;
  const save = () => api('/api/save_config', { method: 'POST', body: JSON.stringify({ overrideHardware }) });
  const listEl = document.getElementById('org-algo-list');
  clearTimeout(hwCheckTimer);
  // Stream frames still carry the old value until the save lands.
  hwSyncHoldUntil = Date.now() + HW_FADE_MS + 1500;
  renderHardwareOverride();
  // Saved only after the fade in either direction: the save rebuilds the list, which would cut a fade short.
  if (overrideHardware) {
    listEl.classList.remove('hw-loading');
    hwCheckTimer = setTimeout(save, HW_FADE_MS);
  } else {
    listEl.classList.add('hw-loading');
    hwCheckTimer = setTimeout(() => {
      save();
      hwCheckTimer = setTimeout(() => listEl.classList.remove('hw-loading'), HW_CHECK_MS - HW_FADE_MS);
    }, HW_FADE_MS);
  }
}

function renderHardwareOverride() {
  document.getElementById('org-hw-override-btn').innerText = `Hardware Limits: ${overrideHardware ? 'Off' : 'On'}`;
  document.getElementById('org-algo-list').classList.toggle('hw-off', overrideHardware);
}

function toggleOrgNumMode() {
  if (orgNumMode === 'none') orgNumMode = 'all';
  else if (orgNumMode === 'all') orgNumMode = 'favs';
  else orgNumMode = 'none';
  const numBtn = document.getElementById('org-num-toggle-btn');
  if (numBtn) {
    if (orgNumMode === 'all') numBtn.innerText = 'Number: All';
    else if (orgNumMode === 'favs') numBtn.innerText = 'Number: Favs';
    else numBtn.innerText = 'Number: None';
  }
  const listEl = document.getElementById('org-algo-list');
  if (listEl) {
    listEl.classList.toggle('num-toggled', orgNumMode !== 'none');
    listEl.classList.remove('num-mode-none', 'num-mode-all', 'num-mode-favs');
    listEl.classList.add('num-mode-' + orgNumMode);
    // Text is updated in place: rebuilding the list here would cut off the mode transition.
    listEl.querySelectorAll('.algo-lastused-line').forEach(el => {
      el.textContent = `Last used: ${lastUsedLabel(algoLastUsed[el.dataset.algo])}`;
    });
  }
}

function lastUsedLabel(ts) {
  const full = formatLastUsed(ts);
  return orgGridMode && orgNumMode !== 'none' ? full : full.slice(0, 10);
}

function toggleFavoriteAlgo(e, algoId) {
  if (e) e.stopPropagation();
  const idx = favoriteAlgos.indexOf(algoId);
  if (idx >= 0) {
    if (favoriteAlgos.length <= 1) {
      showBanner('<strong>&#9650; Favorites Notice:</strong> At least 1 favorite algorithm must remain selected for the Workspace AI-Defense Layers list.', false);
      return;
    }
    favoriteAlgos.splice(idx, 1);
  } else {
    if (favoriteAlgos.length >= 10) {
      showBanner('<strong>&#9650; Favorites Limit Reached:</strong> Up to 10 favorite algorithms can be pinned to the Workspace AI-Defense Layers list. Unstar another algorithm first.', false);
      return;
    }
    favoriteAlgos.push(algoId);
  }
  api('/api/save_config', { method: 'POST', body: JSON.stringify({ favoriteAlgos }) });
  lastBatchesSig = '';
  syncUnifiedBoxUI();
  renderOrganizeTab();
}

function renderOrganizeTab() {
  const listEl = document.getElementById('org-algo-list');
  const favBanner = document.getElementById('org-fav-banner');
  if (!discoveredAlgos || discoveredAlgos.length === 0) {
    listEl.innerHTML = `<div style="color:var(--dim);">No algorithms found.</div>`;
    return;
  }
  if (!selectedOrgAlgoId || !discoveredAlgos.some(a => a.id === selectedOrgAlgoId)) {
    selectedOrgAlgoId = discoveredAlgos[0].id;
  }

  listEl.classList.toggle('num-toggled', orgGridMode && orgNumMode !== 'none');
  listEl.classList.remove('num-mode-none', 'num-mode-all', 'num-mode-favs');
  listEl.classList.add('num-mode-' + orgNumMode);

  const favSet = new Set(favoriteAlgos);
  const validFavCount = discoveredAlgos.filter(a => favSet.has(a.id) || favSet.has(a.folderName)).length;
  if (favBanner) {
    if (validFavCount < 10) {
      favBanner.style.display = 'block';
      favBanner.innerHTML = `&#9650; <strong>${validFavCount} / 10 Favorite Algorithms Selected:</strong> You can star (${10 - validFavCount} more) algorithm(s) below to pin up to 10 favorites in the Workspace <em>AI-Defense Layers</em> book switch.`;
    } else {
      favBanner.style.display = 'none';
    }
  }

  let favCounter = 0;
  listEl.innerHTML = discoveredAlgos.map((a, idx) => {
    const isFav = favSet.has(a.id) || favSet.has(a.folderName);
    if (isFav) favCounter++;
    // Top-left to bottom-right diagonal delay; 5 is the usual grid column count.
    const fadeDelay = orgGridFadePending ? (idx % 5 + Math.floor(idx / 5)) * 40 : 0;
    const lastUsedStr = lastUsedLabel(algoLastUsed[a.id]);
    const escId = escapeHtml(a.id);
    const paperHref = safeHttpUrl(a.paperUrl);
    const actionBtn = a.isDefault
      ? ''
      : `<button class="q-btn danger" style="height:22px;padding:0 8px;font-size:10px;" data-algo="${escId}" onclick="deleteCustomAlgo(event, this.dataset.algo)">Delete</button>`;

    const cannotRun = !!(a.cannotRun || a.unrunnable);
    const hw = a.hardware || {};
    // Shared clock: the list can rebuild mid-spin, and a fresh element would otherwise restart its rotation.
    const spinPhase = -Math.round(performance.now() % 800);
    const badgeHtml = a.limitReason
      ? `<span class="algo-warn-badge">!<span class="info-tooltip">
          <strong style="color:#fff;">${escapeHtml(a.name)}</strong><br>
          Tier ${escapeHtml(hw.tier || '—')} &bull; Needs ${escapeHtml(hw.minVramGb ?? '—')} GB VRAM${hw.requiresCuda ? ' &bull; NVIDIA CUDA' : ''}<br>
          Paper hardware: ${escapeHtml(hw.paperHardware || 'Not reported')}
          <hr style="border:none;border-top:1px solid var(--line);margin:5px 0;">
          ${escapeHtml(a.limitReason)}
        </span></span>`
      : '';
    const warnBadge = `<span class="algo-warn-slot ${a.limitReason ? 'has-warn' : ''}"><span class="algo-warn-spin" style="animation-delay:${spinPhase}ms"></span>${badgeHtml}</span>`;

    return `
      <div class="algo-tree-item ${selectedOrgAlgoId === a.id ? 'active' : ''} ${isFav ? 'fav-item' : ''} ${orgGridFadePending ? 'grid-fade' : ''}" style="animation-delay:${fadeDelay}ms" data-algo="${escId}" onclick="selectOrgAlgo(this.dataset.algo)">
        <div class="algo-watermark-num num-all">${idx + 1}</div>
        ${isFav ? `<div class="algo-watermark-num num-fav">${favCounter}</div>` : ''}
        <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;">
          <strong class="mono" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:12px;">${escapeHtml(a.name)}</strong>
          <div style="display:flex;gap:5px;align-items:center;flex-shrink:0;">
            ${warnBadge}
            <button type="button" class="fav-star-btn ${isFav ? 'active' : ''}" ${cannotRun && !isFav ? 'disabled' : ''} data-algo="${escId}" onclick="toggleFavoriteAlgo(event, this.dataset.algo)" title="${cannotRun ? escapeHtml(a.cannotRunReason || 'Cannot run on this system') : 'Pin/unpin in Workspace AI-Defense Layers (max 10)'}">
              ${isFav ? '&#9733; Fav' : '&#9734; Pin'}
            </button>
            ${actionBtn}
          </div>
        </div>
        <div class="algo-lastused-line mono" data-algo="${escId}">Last used: ${escapeHtml(lastUsedStr)}</div>
        <div class="algo-subline">${escapeHtml(a.attribution)}</div>
        <div class="algo-card-desc">${escapeHtml(a.shortInfo)}</div>
        <div class="algo-card-meta">
          ${paperHref ? `<a class="paper-link" href="${escapeHtml(paperHref)}" target="_blank" rel="noopener noreferrer" onclick="event.stopPropagation()">Original Paper &#8599;</a>` : ''}
        </div>
      </div>
    `;
  }).join('');

  orgGridFadePending = false;

  const cur = discoveredAlgos.find(a => a.id === selectedOrgAlgoId) || discoveredAlgos[0];
  const viewer = document.getElementById('org-md-viewer');
  const paperBtn = document.getElementById('org-paper-link');
  if (paperBtn) {
    const curPaperHref = safeHttpUrl(cur.paperUrl);
    if (curPaperHref) {
      paperBtn.href = curPaperHref;
      paperBtn.style.display = 'inline-flex';
    } else {
      paperBtn.style.display = 'none';
    }
  }

  if (orgViewMode === 'code') {
    document.getElementById('org-doc-title').innerText = `${cur.name} (${cur.pyPath})`;
    viewer.innerHTML = renderCodeWithLines(cur.pyCode);
  } else {
    document.getElementById('org-doc-title').innerText = `${cur.name} (${cur.mdPath})`;
    if (!cur.hasReadme) {
      viewer.innerHTML = `
        <div class="missing-md-placeholder">
          <div class="sad-face-glyph">:(</div>
          <div style="font-size:15px;font-weight:600;color:var(--fg);margin-bottom:6px;">
            readmyalgo.md Not Found
          </div>
          <p style="max-width:460px;font-size:13px;color:var(--dim);">
            No static <code style="color:var(--muted);">readmyalgo.md</code> file exists inside <code style="color:var(--muted);">algos/${escapeHtml(cur.folderName)}/</code>.
            Place a <code style="color:var(--muted);">readmyalgo.md</code> file into the algorithm directory and click <strong>Rescan</strong>.
          </p>
        </div>
      `;
    } else {
      viewer.innerHTML = parseMarkdown(cur.readmeMd);
    }
  }
}

function selectOrgAlgo(id) {
  selectedOrgAlgoId = id;
  if (orgGridMode) {
    orgGridMode = false;
    const orgLayout = document.getElementById('org-layout');
    const listEl = document.getElementById('org-algo-list');
    const btn = document.getElementById('org-layout-btn');
    const numBtn = document.getElementById('org-num-toggle-btn');
    if (orgLayout) orgLayout.classList.remove('grid-fullscreen');
    if (listEl) listEl.classList.remove('grid-mode');
    if (btn) btn.innerText = 'Grid View';
    if (numBtn) numBtn.style.display = 'none';
    document.getElementById('org-hw-override-btn').style.display = 'none';
  }
  renderOrganizeTab();
}

async function deleteCustomAlgo(e, algoId) {
  e.stopPropagation();
  if (!confirm(`Delete custom algorithm folder 'algos/${algoId}' from disk?`)) return;
  const r = await api('/api/algo_action', {
    method: 'POST',
    body: JSON.stringify({ action: 'delete', algoId })
  });
  const d = await r.json();
  if (d.algos) {
    discoveredAlgos = d.algos;
    renderOrganizeTab();
    syncUnifiedBoxUI();
  }
}

async function rescanAlgos() {
  const r = await api('/api/rescan_algos', { method: 'POST' });
  const d = await r.json();
  if (d.algos) {
    discoveredAlgos = d.algos;
    renderOrganizeTab();
    syncUnifiedBoxUI();
  }
}

function onBackendSelectChange() {
  const v = document.getElementById('c-backend').value;
  document.getElementById('cpu-slow-warn').style.display = (v === 'cpu') ? 'block' : 'none';
}

async function loadManifest() {
  const r = await api('/api/manifest');
  const d = await r.json();
  document.getElementById('manifest-box').innerText = d.manifest;
}

async function sysMaint(cmd) {
  if (cmd === 'restart_service') {
    document.getElementById('hdr-restart-btn').classList.add('spinning');
    showBanner('<strong>&#9650; Restarting Service:</strong> Purging caches and restarting PORTtralica Lumiya backend...', false);
    try {
      await api('/api/system_maint?cmd=restart_service', { method: 'POST' });
    } catch (e) {}
    setTimeout(() => window.location.reload(), 1400);
    return;
  }
  const r = await api('/api/system_maint?cmd=' + cmd, { method: 'POST' });
  const d = await r.json();
  if (d.report) {
    showBanner(`<strong>Cleaner Completed:</strong> Freed ${d.report.vramFreedMb} MB cached VRAM, cleared ${d.report.ramBuffersCleared} RAM buffers, removed ${d.report.tempFilesRemoved} temporary files.`, false);
  }
}

function openUninstallModal() {
  document.getElementById('uninstall-modal').classList.add('open');
}

async function executeUninstall(type) {
  document.getElementById('uninstall-modal').classList.remove('open');
  const isPurge = type === 'purge';
  const confMsg = isPurge
    ? "Are you SURE you want to purge all Lumiya runtime pillars? This will remove the Conda 'lumiya' environment, .env, and caches. The program folder and your exported photos (results/) will ALWAYS be kept intact."
    : "Proceed with removing the isolated Lumiya environment (.env & Conda 'lumiya')? The program folder and your exported photos (results/) will be kept intact.";
  if (!confirm(confMsg)) return;
  showBanner(`<strong>&#9650; ${isPurge ? 'Purging Runtime Pillars' : 'Uninstalling Environment'}:</strong> Initiating uninstaller in detached window and shutting down service...`, true);
  try {
    await api(`/api/system_maint?cmd=${type}`, { method: 'POST' });
  } catch (e) {}
}

window.addEventListener('pagehide', () => {
  try {
    navigator.sendBeacon(apiUrl('/api/system_maint?cmd=tab_closed'));
  } catch (e) {}
});

function saveGlobalConfig() {
  const payload = {
    theme: currentTheme,
    computeBackend: document.getElementById('c-backend').value,
    pollMs: parseInt(document.getElementById('c-poll').value, 10),
    workingDim: parseInt(document.getElementById('c-dim').value, 10),
    precision: document.getElementById('c-prec').value,
    tempWarnC: parseFloat(document.getElementById('c-twarn').value),
    tempCritC: parseFloat(document.getElementById('c-tcrit').value),
    jpegQuality: parseInt(document.getElementById('c-jpeg').value, 10),
    autoPaperDefaults: !!document.getElementById('c-auto-paper').checked,
    allowRamSpillover: !!document.getElementById('c-ram-spill').checked
  };
  api('/api/save_config', { method: 'POST', body: JSON.stringify(payload) });
  showBanner('<strong>Configuration Saved:</strong> Engine and telemetry settings updated.', false);
}

/* B-05: resizable, collapsible islands. Bounds are relative to the window: an island never shrinks below today's
   width, grows at most growVw of the window, and always leaves the middle area at least centerFloor(host). */
const DOCKS = {
  workLeft: { host: 'work-layout', panel: '.left', cssVar: '--dock-work-left', side: 'left', def: 400, growVw: 0.10 },
  inspLeft: { host: 'insp-upper', panel: '.insp-left', cssVar: '--dock-insp-left', side: 'left', def: 270, growVw: 0.15 },
  inspRight: { host: 'insp-upper', panel: '.insp-right', cssVar: '--dock-insp-right', side: 'right', def: 340, growVw: 0.17 }
};
const DOCK_STORE_KEY = 'lumiyaDocks';
const DOCK_STRIP_PX = 12;
const dockState = {};

function centerFloor(host) {
  const base = Math.max(320, window.innerWidth * 0.25);
  if (host !== 'insp-upper') return base;
  // Inspect's view toolbar must stay on one line: its groups' natural widths plus gaps and padding (0 while hidden).
  const groups = [...document.querySelectorAll('.insp-toolbar > .insp-mode-group')].filter(g => g.offsetWidth > 0);
  const need = groups.reduce((sum, g) => sum + g.scrollWidth, 0) + 10 * Math.max(0, groups.length - 1) + 28;
  return Math.max(base, need);
}

function clampDock(key, w) {
  const d = DOCKS[key];
  const others = Object.keys(DOCKS)
    .filter(k => k !== key && DOCKS[k].host === d.host && !dockState[k].collapsed)
    .reduce((sum, k) => sum + dockState[k].w, 0);
  const strips = d.host === 'insp-upper' ? 2 * DOCK_STRIP_PX : DOCK_STRIP_PX;
  const max = Math.max(d.def, Math.min(d.def + window.innerWidth * d.growVw, window.innerWidth - strips - others - centerFloor(d.host)));
  return Math.round(Math.min(max, Math.max(d.def, w)));
}

function applyDock(key) {
  const d = DOCKS[key];
  const st = dockState[key];
  const host = document.getElementById(d.host);
  host.style.setProperty(d.cssVar, st.collapsed ? '0px' : `${st.w}px`);
  // Scale mode: the panel keeps its default layout width and is zoomed to fill. Widen mode: it simply gets wider.
  const scale = dockMode === 'scale';
  host.style.setProperty(`${d.cssVar}-w`, `${scale ? d.def : st.w}px`);
  const panel = host.querySelector(d.panel);
  panel.style.zoom = scale ? st.w / d.def : '';
  panel.classList.toggle('dock-collapsed', st.collapsed);
  st.gutter.classList.toggle('collapsed', st.collapsed);
  st.gutter.style[d.side] = `${DOCK_STRIP_PX + st.w - 4}px`;
  st.edge.classList.toggle('collapsed', st.collapsed);
  const pointsLeft = (d.side === 'left') !== st.collapsed;
  st.edge.innerHTML = pointsLeft ? '&#9664;' : '&#9654;';
  st.edge.setAttribute('aria-label', st.collapsed ? 'Show panel' : 'Hide panel');
}

const DOCK_MODE_KEY = 'lumiyaDockMode';
let dockMode = 'scale';
try { if (localStorage.getItem(DOCK_MODE_KEY) === 'widen') dockMode = 'widen'; } catch (e) {}

function setDockMode(mode) {
  dockMode = mode === 'widen' ? 'widen' : 'scale';
  try { localStorage.setItem(DOCK_MODE_KEY, dockMode); } catch (e) {}
  document.getElementById('dock-mode-scale').classList.toggle('active', dockMode === 'scale');
  document.getElementById('dock-mode-widen').classList.toggle('active', dockMode === 'widen');
  Object.keys(dockState).forEach(applyDock);
}

function saveDocks() {
  const out = {};
  Object.keys(dockState).forEach(k => { out[k] = { w: dockState[k].w, collapsed: dockState[k].collapsed }; });
  try { localStorage.setItem(DOCK_STORE_KEY, JSON.stringify(out)); } catch (e) {}
}

function initDocks() {
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem(DOCK_STORE_KEY) || '{}') || {}; } catch (e) {}
  Object.keys(DOCKS).forEach(key => {
    const s = saved[key] || {};
    dockState[key] = { w: Number(s.w) || DOCKS[key].def, collapsed: !!s.collapsed };
  });
  Object.keys(DOCKS).forEach(key => {
    const d = DOCKS[key];
    const host = document.getElementById(d.host);
    const edge = document.createElement('button');
    edge.type = 'button';
    edge.className = 'dock-edge';
    edge.style[d.side] = '0px';
    const gutter = document.createElement('div');
    gutter.className = 'dock-gutter';
    host.append(edge, gutter);
    dockState[key].edge = edge;
    dockState[key].gutter = gutter;
    dockState[key].w = clampDock(key, dockState[key].w);

    edge.addEventListener('click', () => {
      dockState[key].collapsed = !dockState[key].collapsed;
      dockState[key].w = clampDock(key, dockState[key].w);
      applyDock(key);
      saveDocks();
    });
    gutter.addEventListener('pointerdown', (e) => {
      gutter.setPointerCapture(e.pointerId);
      document.body.classList.add('docks-dragging');
      const onMove = (ev) => {
        const rect = host.getBoundingClientRect();
        const w = (d.side === 'left' ? ev.clientX - rect.left : rect.right - ev.clientX) - DOCK_STRIP_PX;
        dockState[key].w = clampDock(key, w);
        applyDock(key);
      };
      const onUp = () => {
        gutter.removeEventListener('pointermove', onMove);
        gutter.removeEventListener('pointerup', onUp);
        document.body.classList.remove('docks-dragging');
        saveDocks();
      };
      gutter.addEventListener('pointermove', onMove);
      gutter.addEventListener('pointerup', onUp);
    });
    applyDock(key);
  });
  setDockMode(dockMode);
  window.addEventListener('resize', () => {
    Object.keys(DOCKS).forEach(key => { dockState[key].w = clampDock(key, dockState[key].w); applyDock(key); });
  });
  // Canvases measure themselves once per epoch, so a resized area must bump it and redraw (at most once a frame).
  let redrawQueued = false;
  const onAreaResize = () => {
    canvasResizeEpoch++;
    if (redrawQueued) return;
    redrawQueued = true;
    requestAnimationFrame(() => {
      redrawQueued = false;
      if (document.getElementById('page-insp').classList.contains('active')) {
        renderInspectStage();
        renderInspectHistogram();
      } else {
        drawMainGraph();
      }
    });
  };
  const observer = new ResizeObserver(onAreaResize);
  observer.observe(document.getElementById('insp-stage'));
  observer.observe(document.querySelector('#work-layout > .right'));
}
initDocks();

/* Global Floating Tooltip Portal (Eliminates Scroll Container Clipping & Layout Reflow) */
(function initGlobalTooltips() {
  const portal = document.getElementById('global-floating-tooltip');
  if (!portal) return;
  let activeIcon = null;

  function positionPortal(icon) {
    const rect = icon.getBoundingClientRect();
    const pw = portal.offsetWidth || 274;
    const ph = portal.offsetHeight || 80;
    let left = rect.right + 10;
    if (left + pw > window.innerWidth - 10) {
      left = rect.left - pw - 10;
    }
    if (left < 10) {
      left = Math.max(10, Math.min(window.innerWidth - pw - 10, rect.left));
    }
    let top = rect.top - 6;
    if (top + ph > window.innerHeight - 10) {
      top = window.innerHeight - ph - 10;
    }
    if (top < 10) top = 10;
    portal.style.left = `${Math.round(left)}px`;
    portal.style.top = `${Math.round(top)}px`;
  }

  document.addEventListener('mouseover', (e) => {
    const t = e.target;
    if (!t || !t.classList) return;
    const icon = t.classList.contains('info-icon') || t.classList.contains('algo-warn-badge') ? t : t.closest('.hdr-icon-btn, .fb-tool, .q-btn.is-locked');
    if (!icon || icon === activeIcon) return;
    showFloatingTip(icon);
  }, { passive: true });

  // Also called on click (e.g. a locked ×), so the notice appears beside the button instead of as a banner.
  window.showFloatingTip = (icon) => {
    const tip = icon.querySelector('.info-tooltip');
    if (!tip) return;
    activeIcon = icon;
    portal.innerHTML = tip.innerHTML;
    portal.style.display = 'block';
    positionPortal(icon);
  };

  document.addEventListener('mouseout', (e) => {
    if (!activeIcon) return;
    const rel = e.relatedTarget;
    if (rel && activeIcon.contains(rel)) return;
    activeIcon = null;
    portal.style.display = 'none';
  }, { passive: true });

  window.addEventListener('scroll', () => {
    if (activeIcon) {
      activeIcon = null;
      portal.style.display = 'none';
    }
  }, { capture: true, passive: true });
})();

let lastHistorySig = '';
let lastDepsSig = '';
let collapsedHistoryBatches = {};
let latestHistoryList = [];
let integrityLoadedOnce = false;

