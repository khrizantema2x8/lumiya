// Forensic Analytics: heavier tools that run on the server against the real file bytes or a real model.
// Results are kept per Inspect item; "Show on stage" draws a result map through the 'fa' lens.
const FA_TOOLS = {
  ela: { label: 'True ELA', map: true },
  robust: { label: 'Robustness Test', map: false },
  latent: { label: 'Latent Shift', map: true },
};
let faShownTool = '';
let faRunning = '';

function faItem() { return inspectItems[activeInspectIdx] || null; }

async function runForensicAnalytics(tool) {
  const item = faItem();
  if (!item || faRunning) return;
  faRunning = tool;
  renderForensicAnalytics();
  const key = item.key;
  let res;
  try {
    const q = `tool=${tool}&quality=${encodeURIComponent(document.getElementById('fa-ela-q')?.value || 90)}`;
    if (item.isStandalone) {
      const blob = await fetch(item.standaloneUrl).then(r => r.blob());
      res = await api(`/api/analyze?${q}`, { method: 'POST', body: blob }).then(r => r.json());
    } else {
      res = await api(`/api/analyze?${q}&batch=${encodeURIComponent(item.batchId)}&file=${encodeURIComponent(item.fileId)}`, { method: 'POST' }).then(r => r.json());
    }
  } catch (e) {
    res = { ok: false, error: String(e) };
  }
  faRunning = '';
  item.faResults = item.faResults || {};
  item.faResults[tool] = res;
  if (res.ok && res.png) {
    res.img = await loadImgPromise(`data:image/png;base64,${res.png}`).catch(() => null);
  }
  const cur = faItem();
  if (cur && cur.key === key) {
    if (res.ok && FA_TOOLS[tool].map) showForensicResult(tool);
    renderForensicAnalytics();
  }
}

function showForensicResult(tool) {
  faShownTool = tool;
  if (inspectLens === 'fa') renderInspectStage();
  else setInspectLens('fa');
  renderForensicAnalytics();
}

function faLensCanvas(entry) {
  const res = faItem()?.faResults?.[faShownTool];
  const c = document.createElement('canvas');
  c.width = entry.w;
  c.height = entry.h;
  const ctx = c.getContext('2d');
  ctx.fillStyle = '#000';
  ctx.fillRect(0, 0, c.width, c.height);
  if (res && res.img) {
    // The map is a measured field: smoothing would blur cell edges into values that were never computed.
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(res.img, 0, 0, c.width, c.height);
  }
  return c;
}

function renderForensicAnalytics() {
  const box = document.getElementById('insp-fa-box');
  if (!box) return;
  const item = faItem();
  if (!item) { box.innerHTML = `<div style="color:var(--dim);">Select an image in the filmstrip to analyse.</div>`; return; }
  const results = item.faResults || {};
  const rows = Object.entries(FA_TOOLS).map(([tool, t]) => {
    const r = results[tool];
    const busy = faRunning === tool;
    const shown = inspectLens === 'fa' && faShownTool === tool;
    let body = '';
    if (busy) body = `<div style="color:var(--dim);">Running...</div>`;
    else if (r && !r.ok) body = `<div style="color:var(--red);">${escapeHtml(r.error || 'Failed.')}</div>`;
    else if (r && tool === 'robust') {
      body = `<table class="fa-table"><tr><th>Edit</th><th>Mark</th><th>LSB</th></tr>${r.rows.map(x => `<tr><td>${escapeHtml(x.attack)}</td><td style="color:${x.markFound ? 'var(--green)' : 'var(--dim)'};">${x.markFound ? `found ${x.markScore}%` : 'not found'}</td><td style="color:${x.lsbFound ? 'var(--green)' : 'var(--dim)'};">${x.lsbFound ? 'found' : 'no'}</td></tr>`).join('')}</table>`;
    } else if (r) {
      body = `${Object.entries(r.stats || {}).map(([k, v]) => `<div class="insp-meta-row"><span>${escapeHtml(k)}</span><span class="mono">${escapeHtml(v)}</span></div>`).join('')}
        <div class="insp-meta-row"><span>Colour scale</span><span class="mono">${escapeHtml(r.scale || '')}</span></div>`;
    }
    const prov = r && r.ok ? `<div class="fa-prov">${escapeHtml(r.method || '')} &middot; ${r.seconds}s</div>` : '';
    const showBtn = r && r.ok && t.map ? `<button class="q-btn fa-btn${shown ? ' active' : ''}" onclick="${shown ? `setInspectLens('normal')` : `showForensicResult('${tool}')`};renderForensicAnalytics()">${shown ? 'Hide' : 'Show'}</button>` : '';
    return `<div class="fa-tool">
      <div class="fa-head"><strong>${t.label}</strong><span>${showBtn}<button class="q-btn fa-btn" ${faRunning ? 'disabled' : ''} onclick="runForensicAnalytics('${tool}')">${r ? 'Rerun' : 'Run'}</button></span></div>
      ${body}${prov}</div>`;
  });
  box.innerHTML = rows.join('');
}
