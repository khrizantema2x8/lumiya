function escapeHtml(str) {
  return String(str || '')
    .replace(/[\u200B-\u200F\u202A-\u202E\u2066-\u2069\uFEFF]/g, '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function formatQueueFileName(rawName, maxChars = 36) {
  const clean = String(rawName || '').replace(/[\u0000-\u001F\u007F-\u009F\u200B-\u200F\u202A-\u202E\u2066-\u2069\uFEFF]/g, '');
  if (clean.length <= maxChars) return escapeHtml(clean);
  const dotIdx = clean.lastIndexOf('.');
  const ext = (dotIdx > 0 && clean.length - dotIdx <= 8) ? clean.slice(dotIdx) : '';
  const stem = ext ? clean.slice(0, dotIdx) : clean;
  const keep = Math.max(8, maxChars - ext.length - 5);
  const head = Math.ceil(keep * 0.6);
  const tail = Math.max(3, keep - head);
  return escapeHtml(`${stem.slice(0, head)}(...)${stem.slice(-tail)}${ext}`);
}

function formatLastUsed(ts) {
  if (!ts) return 'Never run';
  return String(ts);
}

function switchTab(tab) {
  ['work', 'insp', 'org', 'cfg'].forEach(t => {
    const btn = document.getElementById(`tab-btn-${t}`);
    const page = document.getElementById(`page-${t}`);
    if (btn) btn.classList.toggle('active', t === tab);
    if (page) page.classList.toggle('active', t === tab);
  });
  // Configuration always reopens on Application Fonts, so the next visit never has to lay out the system list.
  if (tab !== 'cfg' && fb.source !== 'app') {
    fb.source = 'app';
    fb.revealing = false;
    fontRevealToken++;
    renderFontBrowser();
  }
  if (tab === 'cfg') {
    loadManifest();
    if (!integrityLoadedOnce) verifyProgramIntegrity();
  }
  if (tab === 'org') renderOrganizeTab();
  if (tab === 'insp') {
    // The view toolbar can only be measured while visible, so re-check the dock limits on arrival.
    Object.keys(DOCKS).forEach(key => { dockState[key].w = clampDock(key, dockState[key].w); applyDock(key); });
    renderInspectModule();
  }
}

function showBanner(msg, isError = false) {
  const b = document.getElementById('wide-banner');
  document.getElementById('wide-banner-text').innerHTML = msg;
  b.classList.toggle('error-mode', isError);
  b.classList.add('visible');
}

function toggleSensorPop(e, popId) {
  e.stopPropagation();
  document.querySelectorAll('.sensor-popover').forEach(el => {
    if (el.id !== popId) el.classList.remove('open');
  });
  document.getElementById(popId).classList.toggle('open');
}

document.addEventListener('click', () => {
  document.querySelectorAll('.sensor-popover').forEach(el => el.classList.remove('open'));
  document.getElementById('sensor-menu').classList.remove('open');
});

async function debugCmd(cmd, extra = {}) {
  await api('/api/debug_action', {
    method: 'POST',
    body: JSON.stringify({ cmd, ...extra })
  });
  lastBatchesSig = '';
}

/* Import Drag & Drop + Global Ctrl+V Clipboard Paste */
const drop = document.getElementById('drop');
const fileInput = document.getElementById('file');
drop.addEventListener('dragover', (e) => { e.preventDefault(); drop.classList.add('active'); });
drop.addEventListener('dragleave', () => drop.classList.remove('active'));
drop.addEventListener('drop', (e) => {
  e.preventDefault();
  drop.classList.remove('active');
  if (e.dataTransfer.files.length) ingestFiles(e.dataTransfer.files);
});
fileInput.addEventListener('change', () => {
  if (fileInput.files.length) ingestFiles(fileInput.files);
});

window.addEventListener('paste', (e) => {
  const cd = e.clipboardData;
  if (!cd || !cd.items) return;
  const imgFiles = [];
  for (let i = 0; i < cd.items.length; i++) {
    const it = cd.items[i];
    if (it.kind === 'file' && it.type && it.type.startsWith('image/')) {
      const f = it.getAsFile();
      if (f) {
        const ext = (it.type.split('/')[1] || 'png').replace('jpeg', 'jpg');
        const namedFile = (f.name && f.name !== 'image.png')
          ? f
          : new File([f], `clipboard_${new Date().toISOString().replace(/[:.]/g, '-')}.${ext}`, { type: f.type });
        imgFiles.push(namedFile);
      }
    }
  }
  if (imgFiles.length === 0) return;
  e.preventDefault();
  const inspActive = document.getElementById('page-insp').classList.contains('active');
  if (inspActive) {
    ingestStandaloneInspectFiles(imgFiles);
  } else {
    switchTab('work');
    ingestFiles(imgFiles);
  }
});

async function ingestFiles(fileList) {
  const spinner = document.getElementById('upload-spinner');
  const statusTxt = document.getElementById('upload-status-text');
  spinner.classList.add('active');

  const res = await api('/api/create_batch', { method: 'POST' });
  const { batchId } = await res.json();
  const issues = [];

  for (let i = 0; i < fileList.length; i++) {
    const f = fileList[i];
    statusTxt.innerText = `Uploading (${i + 1}/${fileList.length}): ${f.name}`;
    const r = await api(`/api/upload?batch=${encodeURIComponent(batchId)}&name=${encodeURIComponent(f.name)}`, {
      method: 'POST',
      body: f
    });
    const out = await r.json();
    if (!out.accepted) issues.push(out.reason);
  }

  spinner.classList.remove('active');
  fileInput.value = '';
  selectedBatchId = batchId;

  if (issues.length > 0) {
    showBanner('<strong>&#9650; Import Notice:</strong> ' + issues.map(escapeHtml).join(' &bull; '), true);
  }
}

function getActiveTargetBatch() {
  if (!selectedBatchId) return null;
  return allBatches.find(b => b.batchId === selectedBatchId) || null;
}

function selectBatchForEditing(batchId) {
  if (selectedBatchId === batchId) return;
  selectedBatchId = batchId;
  document.querySelectorAll('.batch-node').forEach(el => {
    el.classList.toggle('selected', el.id === `batch-node-${batchId}`);
  });
  syncUnifiedBoxUI();
}

function syncStegoSwitchButtons(modeVal) {
  ['off', 'combined', 'only'].forEach(m => {
    const btn = document.getElementById(`stego-btn-${m}`);
    if (btn) btn.classList.toggle('active', m === modeVal);
  });
  const onlyStego = modeVal === 'only';
  const onlyAi = modeVal === 'off';
  const listEl = document.getElementById('layer-list');
  const headEl = document.getElementById('layer-heading');
  const layeringSec = document.getElementById('layering-params-section');
  const stegoSec = document.getElementById('stego-params-section');
  const txtEl = document.getElementById('s-stego-text');
  // Inline display, because .layer-list sets its own display and would beat the hidden attribute.
  [document.getElementById('ai-layers-section'), listEl, headEl, layeringSec].forEach(el => { if (el) el.style.display = onlyStego ? 'none' : ''; });
  if (stegoSec) stegoSec.style.display = onlyAi ? 'none' : '';
  if (txtEl) txtEl.disabled = onlyAi;
}

function setStegoMode(modeVal) {
  const stegoModeEl = document.getElementById('s-stego-mode');
  stegoModeEl.value = modeVal;
  syncStegoSwitchButtons(modeVal);
  onUnifiedBoxChange();
}

function jumpToAlgoReadme(e, algoId) {
  if (e) e.stopPropagation();
  selectedOrgAlgoId = algoId;
  orgViewMode = 'doc';
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
  const swDoc = document.getElementById('sw-doc');
  const swCode = document.getElementById('sw-code');
  if (swDoc) swDoc.classList.add('active');
  if (swCode) swCode.classList.remove('active');
  switchTab('org');
}

let paramEditing = {};
let hasParamError = false;

// Limits come from the input's min/max, which applyServerBounds() sets from core/config.py BOUNDS.
const PARAM_BOUNDS = {
  'eps': { sliderId: 'r-eps', formatVal: v => v.toFixed(1) },
  'steps': { sliderId: 'r-steps', formatVal: v => `${v}` },
  'temp-weight': { sliderId: 'r-temp-weight', formatVal: v => v.toFixed(2) },
  'mask-aug': { sliderId: 'r-mask-aug', formatVal: v => v.toFixed(1) },
  'stego-strength': { sliderId: 'r-stego-strength', formatVal: v => `${v}` },
  'stego-scale': { sliderId: 'r-stego-scale', formatVal: v => `${v}` },
  'insp-gain': { sliderId: 'insp-gain', formatVal: v => `${v}` },
  'insp-ela-q': { sliderId: 'insp-ela-q', formatVal: v => `${v}` },
  'insp-floor': { sliderId: 'insp-noise-floor', formatVal: v => `${v}` }
};

let serverBoundsApplied = false;
function applyServerBounds(bounds, computeLevels) {
  document.querySelectorAll('[data-bound]').forEach(el => {
    const b = bounds[el.dataset.bound];
    if (b) { el.min = b[0]; el.max = b[1]; }
  });
  if (computeLevels) {
    COMPUTE_LEVELS = computeLevels;
    document.getElementById('r-compute').max = computeLevels.length - 1;
  }
  serverBoundsApplied = true;
}

function closeAllParamEdits(revertInvalid = true) {
  Object.keys(paramEditing).forEach(key => {
    const inp = document.getElementById(`inp-${key}`);
    if (inp && inp._commit) {
      inp._commit(revertInvalid);
    }
  });
}

document.addEventListener('click', (ev) => {
  if (Object.keys(paramEditing).length > 0) {
    if (!ev.target.closest('.param-val-wrap')) {
      closeAllParamEdits(false);
    }
  }
});

function startParamEdit(e, paramKey) {
  if (e) e.stopPropagation();
  closeAllParamEdits(false);
  if (Object.keys(paramEditing).length > 0) return;
  const def = PARAM_BOUNDS[paramKey];
  if (!def) return;
  const slider = document.getElementById(def.sliderId);
  const container = document.getElementById(`v-${paramKey}`);
  if (!slider || !container) return;

  paramEditing[paramKey] = true;
  const curVal = def.formatVal(parseFloat(slider.value));

  container.innerHTML = `
    <div style="position:relative;display:inline-block;" onclick="event.stopPropagation()">
      <input type="text" class="param-inline-input" id="inp-${paramKey}" value="${curVal}">
      <div class="param-error-pop" id="err-${paramKey}" style="display:none;">Out of bound, not applicable value</div>
    </div>
  `;

  const inp = document.getElementById(`inp-${paramKey}`);
  if (!inp) return;
  inp.focus();
  inp.select();

  function commitValue(forceRevert = false) {
    const raw = inp.value.trim();
    const val = parseFloat(raw);
    const errPop = document.getElementById(`err-${paramKey}`);
    if (isNaN(val) || val < parseFloat(slider.min) || val > parseFloat(slider.max)) {
      if (forceRevert) {
        delete paramEditing[paramKey];
        hasParamError = false;
        container.innerText = def.formatVal(parseFloat(slider.value));
        return false;
      }
      hasParamError = true;
      inp.classList.add('error');
      if (errPop) errPop.style.display = 'block';
      lastBatchesSig = '';
      if (typeof renderQueueTree === 'function' && allBatches) {
        renderQueueTree(allBatches, false, '', true);
      }
      return false;
    }

    hasParamError = false;
    inp.classList.remove('error');
    if (errPop) errPop.style.display = 'none';
    delete paramEditing[paramKey];
    slider.value = val;
    container.innerText = def.formatVal(val);
    slider.dispatchEvent(new Event('input'));
    lastBatchesSig = '';
    if (typeof renderQueueTree === 'function' && allBatches) {
      renderQueueTree(allBatches, false, '', true);
    }
    return true;
  }

  inp._commit = commitValue;

  inp.addEventListener('keydown', (ev) => {
    if (ev.key === 'Enter') {
      commitValue(false);
    } else if (ev.key === 'Escape') {
      delete paramEditing[paramKey];
      hasParamError = false;
      container.innerText = def.formatVal(parseFloat(slider.value));
      lastBatchesSig = '';
      if (typeof renderQueueTree === 'function' && allBatches) {
        renderQueueTree(allBatches, false, '', true);
      }
    }
  });

  inp.addEventListener('blur', () => {
    setTimeout(() => {
      if (paramEditing[paramKey]) {
        commitValue(false);
      }
    }, 120);
  });
}

// Hold and drag a parameter number sideways to scrub it (Shift = 4x finer); a plain click still opens the text box.
// Dragging the full PARAM_SCRUB_RANGE_PX covers the slider's whole range, snapped to its step.
const PARAM_SCRUB_RANGE_PX = 240;
const PARAM_SCRUB_DEADZONE_PX = 3;
let paramScrub = null;

document.addEventListener('pointerdown', (e) => {
  const el = e.target.closest && e.target.closest('.param-num-editable[data-param]');
  if (!el || e.button !== 0 || paramEditing[el.dataset.param]) return;
  const def = PARAM_BOUNDS[el.dataset.param];
  const slider = def && document.getElementById(def.sliderId);
  if (!slider || slider.disabled) return;
  e.preventDefault();
  closeAllParamEdits(false);
  paramScrub = { el, key: el.dataset.param, slider, dx: 0, v0: parseFloat(slider.value), shift: e.shiftKey, moved: false, pointerId: e.pointerId };
  el.setPointerCapture(e.pointerId);
  // Grab at once: press the number in and hide the pointer.
  document.body.classList.add('param-scrubbing');
  el.classList.add('scrubbing');
});

// pointerrawupdate delivers movement without waiting for the next frame, where the browser supports it.
document.addEventListener('onpointerrawupdate' in window ? 'pointerrawupdate' : 'pointermove', (e) => {
  const sc = paramScrub;
  if (!sc) return;
  if (e.shiftKey !== sc.shift) {  // re-anchor when Shift changes, so the value never jumps
    sc.shift = e.shiftKey;
    sc.dx = 0;
    sc.v0 = parseFloat(sc.slider.value);
  }
  sc.dx += e.movementX || 0;
  const dx = sc.dx;
  if (!sc.moved && Math.abs(dx) < PARAM_SCRUB_DEADZONE_PX) return;
  if (!sc.moved) {
    sc.moved = true;
    // Pointer lock holds the pointer where the drag began (Chrome shows its Esc notice; it can't be suppressed).
    // Locked only once it's a real drag, so a plain click to type doesn't trigger it.
    try { const req = sc.el.requestPointerLock && sc.el.requestPointerLock(); if (req && req.catch) req.catch(() => {}); } catch (err) {}
  }
  const min = parseFloat(sc.slider.min), max = parseFloat(sc.slider.max), step = parseFloat(sc.slider.step) || 1;
  const pxPerStep = Math.max(2, PARAM_SCRUB_RANGE_PX / Math.max(1, Math.round((max - min) / step))) * (sc.shift ? 4 : 1);
  const raw = Math.min(max, Math.max(min, sc.v0 + Math.round(dx / pxPerStep) * step));
  const val = parseFloat((min + Math.round((raw - min) / step) * step).toFixed(6));
  if (val !== parseFloat(sc.slider.value)) {
    sc.slider.value = val;
    sc.slider.dispatchEvent(new Event('input'));
  }
});

function endParamScrub(e, cancelled) {
  const sc = paramScrub;
  if (!sc) return;
  paramScrub = null;
  document.body.classList.remove('param-scrubbing');
  sc.el.classList.remove('scrubbing');
  if (document.pointerLockElement === sc.el) document.exitPointerLock();
  if (sc.el.hasPointerCapture && sc.el.hasPointerCapture(sc.pointerId)) sc.el.releasePointerCapture(sc.pointerId);
  if (!sc.moved) {
    if (!cancelled) startParamEdit(e, sc.key);
    return;
  }
  lastBatchesSig = '';
  if (typeof renderQueueTree === 'function' && allBatches) renderQueueTree(allBatches, false, '', true);
}
document.addEventListener('pointerup', (e) => endParamScrub(e, false));
document.addEventListener('pointercancel', (e) => endParamScrub(e, true));

function updateNoAlgoBanner(layers, stegoMode) {
  const noAlgo = stegoMode !== 'only' && !Object.values(layers || {}).some(Boolean);
  const banner = document.getElementById('wide-banner');
  const isOurs = document.getElementById('wide-banner-text').textContent.includes('Batch Condition');
  if (noAlgo && !(isOurs && banner.classList.contains('visible'))) {
    showBanner('<strong>&#9650; Batch Condition:</strong> At least one AI-Defense Layers algorithm must be enabled when AI-blocking is active.', true);
  } else if (!noAlgo && isOurs) {
    banner.classList.remove('visible');
  }
}

let stegoMark = '';
// The stream only carries an id for each batch's mark; the image itself is fetched when it changes, and sent back only after an import.
let stegoMarkId = null;
let stegoMarkDirty = false;

async function loadBatchMark(target) {
  stegoMarkId = target.markId || '';
  let mark = '';
  if (stegoMarkId) {
    const r = await api(`/api/batch_mark?batch=${encodeURIComponent(target.batchId)}`);
    mark = (await r.json()).mark || '';
  }
  if (stegoMarkDirty || (target.markId || '') !== stegoMarkId) return;
  stegoMark = mark;
  renderStegoControls();
}
// Replaced by the server list (core/config.py CHOICES) on the first stream message.
let COMPUTE_LEVELS = [0.25, 0.5, 1, 2];
let lastParamEditAt = 0;

function randomizeSeed() {
  document.getElementById('s-seed').value = Math.floor(Math.random() * 2147483647);
  onUnifiedBoxChange();
}

async function openResultFolder(batch) {
  const r = await api(`/api/open_result?batch=${encodeURIComponent(batch)}`, { method: 'POST' });
  const d = await r.json();
  if (!d.ok) showBanner(`<strong>&#9650; Export Missing:</strong> The folder for ${escapeHtml(batch)} no longer exists.`, true);
}

function setConvertPngMode(val) {
  const boolVal = !!val;
  document.getElementById('s-convert-png').value = boolVal ? 'true' : 'false';
  syncConvertPngButtons(boolVal, false);
  onUnifiedBoxChange();
}

function syncConvertPngButtons(convertPngVal, allPngLocked) {
  const btnPng = document.getElementById('fmt-btn-png');
  const btnKeep = document.getElementById('fmt-btn-keep');
  if (!btnPng || !btnKeep) return;
  const effConvert = allPngLocked ? true : !!convertPngVal;
  btnPng.classList.toggle('active', effConvert);
  btnKeep.classList.toggle('active', !effConvert);
  btnKeep.disabled = !!allPngLocked;
  btnKeep.title = allPngLocked ? 'All images in this batch are already lossless .PNG files' : 'Preserve original file format on export';
}

function renderStegoControls() {
  if (!paramEditing['stego-strength']) document.getElementById('v-stego-strength').innerText = document.getElementById('r-stego-strength').value;
  if (!paramEditing['stego-scale']) document.getElementById('v-stego-scale').innerText = document.getElementById('r-stego-scale').value;
  const preview = document.getElementById('s-stego-preview');
  preview.style.display = stegoMark ? 'block' : 'none';
  // Re-assigning the same data URL makes the browser decode the mark again on every slider step.
  if (stegoMark && preview.dataset.mark !== stegoMark) { preview.src = `data:image/png;base64,${stegoMark}`; preview.dataset.mark = stegoMark; }
  const payload = document.getElementById('s-stego-payload').value;
  const isBin = payload === 'binary';
  document.getElementById('s-stego-image-row').hidden = payload !== 'image';
  document.getElementById('s-stego-text').hidden = payload === 'image';
  const strField = document.getElementById('s-stego-strength-field');
  const sclField = document.getElementById('s-stego-scale-field');
  const plcField = document.getElementById('s-stego-placement-field');
  const binNote = document.getElementById('s-stego-binary-note');
  if (strField) strField.style.display = isBin ? 'none' : '';
  if (sclField) sclField.style.display = isBin ? 'none' : '';
  if (plcField) plcField.style.display = isBin ? 'none' : '';
  if (binNote) binNote.style.display = isBin ? 'block' : 'none';
  document.getElementById('v-compute').innerText = `${COMPUTE_LEVELS[document.getElementById('r-compute').value].toFixed(COMPUTE_LEVELS[document.getElementById('r-compute').value] === 0.25 ? 2 : 1)}x`;
}

function setStegoMark(mark) {
  stegoMark = mark;
  stegoMarkDirty = true;
  document.getElementById('s-stego-msg').innerText = '';
  onUnifiedBoxChange();
}

async function onStegoImagePicked(input) {
  const file = input.files[0];
  input.value = '';
  if (file) await importStegoImage(file);
}

function onStegoImageDropped(e) {
  e.preventDefault();
  e.stopPropagation();
  e.currentTarget.classList.remove('drag-over');
  if (e.dataTransfer.files[0]) importStegoImage(e.dataTransfer.files[0]);
}

async function importStegoImage(file) {
  const r = await api('/api/stego_prepare', { method: 'POST', body: file });
  const d = await r.json();
  const msg = document.getElementById('s-stego-msg');
  if (d.ok) setStegoMark(d.mark);
  msg.style.color = d.ok ? 'var(--gold)' : 'var(--red)';
  if (!d.ok) msg.innerText = d.error;
  else if (d.compressed) msg.innerText = 'The imported image is too high-res to be embedded, so it was compressed below 2000x2000. This may lose embedding detail.';
}

// Controls no selected algorithm uses stay visible but locked.
function applyParamSupport(layers) {
  const on = discoveredAlgos.filter(a => layers && layers[a.id]);
  const rawParams = new Set(on.flatMap(a => a.params || []));
  const supported = new Set(rawParams);
  if (rawParams.has('geoAnchorLow') || rawParams.has('geoAnchorHigh')) supported.add('scale');
  if (rawParams.has('temporalWeight')) supported.add('temporal');
  if (rawParams.has('maskAugFactor')) supported.add('mask');
  if (rawParams.has('guidancePrompt')) supported.add('text');

  const budgets = on.filter(a => a.paper && a.paper.budget !== undefined).map(a => Number(a.paper.budget));
  const stepsArr = on.filter(a => a.paper && a.paper.steps !== undefined).map(a => Number(a.paper.steps));
  const temps = on.filter(a => a.paper && a.paper.temporalWeight !== undefined).map(a => Number(a.paper.temporalWeight));
  const masks = on.filter(a => a.paper && a.paper.maskAugFactor !== undefined).map(a => Number(a.paper.maskAugFactor));

  const budgetLbl = document.getElementById('l-budget-paper');
  if (budgetLbl) budgetLbl.innerText = budgets.length ? `${Math.min(...budgets).toFixed(1)} (Paper)` : '— (Paper)';
  const compLbl = document.getElementById('l-compute-paper');
  if (compLbl) compLbl.innerText = stepsArr.length ? `1.0x (${stepsArr.reduce((a, b) => a + b, 0)} steps Paper)` : '1.0x (Paper)';
  const tempLbl = document.getElementById('l-temp-paper');
  if (tempLbl) tempLbl.innerText = temps.length ? `${temps[temps.length - 1].toFixed(2)} (Paper)` : '0.50 (Balanced)';
  const maskLbl = document.getElementById('l-mask-paper');
  if (maskLbl) maskLbl.innerText = masks.length ? `${masks[masks.length - 1].toFixed(1)}x (Paper)` : '1.0x (Contour)';

  document.querySelectorAll('.field[data-param]').forEach(el => {
    const locked = !supported.has(el.dataset.param);
    el.classList.toggle('param-locked', locked);
    el.querySelectorAll('input, select, textarea, button').forEach(c => { c.disabled = locked; });
  });
}

function syncUnifiedBoxUI() {
  const target = getActiveTargetBatch();
  const epsSlider = document.getElementById('r-eps');
  const stepsSlider = document.getElementById('r-steps');
  const promptEl = document.getElementById('s-guidance-prompt');
  const geoLowEl = document.getElementById('r-geo-low');
  const geoHighEl = document.getElementById('r-geo-high');
  const tempWeightEl = document.getElementById('r-temp-weight');
  const maskAugEl = document.getElementById('r-mask-aug');
  const stegoModeEl = document.getElementById('s-stego-mode');
  const stegoTextEl = document.getElementById('s-stego-text');

  const curLayers = target ? target.layers : defaultLayers;
  // The stream can carry values older than the user's last edit; never write those over live controls.
  if (target && Date.now() - lastParamEditAt > 1500) {
    epsSlider.value = target.epsilon ?? 8.0;
    document.getElementById('r-compute').value = Math.max(0, COMPUTE_LEVELS.indexOf(target.computeLevel ?? 1));
    document.getElementById('s-stego-payload').value = target.stegoPayload || 'text';
    document.getElementById('s-seed').value = target.seed ?? 0;
    document.getElementById('r-stego-strength').value = target.stegoStrength ?? 4;
    document.getElementById('r-stego-scale').value = target.stegoScale ?? 40;
    document.getElementById('s-stego-placement').value = target.stegoPlacement || 'center';
    if (!stegoMarkDirty && (target.markId || '') !== stegoMarkId) loadBatchMark(target);
    if (promptEl && document.activeElement !== promptEl) {
      promptEl.value = target.guidancePrompt ?? '';
    }
    if (geoLowEl) geoLowEl.value = target.geoAnchorLow ?? 1.7;
    if (geoHighEl) geoHighEl.value = target.geoAnchorHigh ?? 7.1;
    if (tempWeightEl) tempWeightEl.value = target.temporalWeight ?? 0.50;
    if (maskAugEl) maskAugEl.value = target.maskAugFactor ?? 1.0;
    stegoModeEl.value = target.stegoMode || 'off';
    if (document.activeElement !== stegoTextEl) {
      stegoTextEl.value = target.stegoText || '';
    }
    const convBool = target.convertPng !== undefined ? !!target.convertPng : defaultConvertPng;
    document.getElementById('s-convert-png').value = convBool ? 'true' : 'false';
  }
  const curConv = document.getElementById('s-convert-png').value !== 'false';
  syncConvertPngButtons(curConv, !!(target && target.allPng));
  syncStegoSwitchButtons(stegoModeEl.value || 'off');
  renderStegoControls();
  applyParamSupport(curLayers);

  if (!paramEditing['eps']) document.getElementById('v-eps').innerText = parseFloat(epsSlider.value).toFixed(1);
  if (!paramEditing['steps']) document.getElementById('v-steps').innerText = `${stepsSlider.value}`;
  if (geoLowEl && geoHighEl) {
    document.getElementById('v-geo').innerText = `${parseFloat(geoLowEl.value).toFixed(1)} – ${parseFloat(geoHighEl.value).toFixed(1)}`;
  }
  if (tempWeightEl && !paramEditing['temp-weight']) {
    document.getElementById('v-temp-weight').innerText = parseFloat(tempWeightEl.value).toFixed(2);
  }
  if (maskAugEl && !paramEditing['mask-aug']) {
    document.getElementById('v-mask-aug').innerText = parseFloat(maskAugEl.value).toFixed(1);
  }

  updateNoAlgoBanner(curLayers, stegoModeEl.value || 'off');

  const listEl = document.getElementById('layer-list');
  const favBadge = document.getElementById('fav-count-badge');
  if (discoveredAlgos.length > 0 && listEl) {
    const favSet = new Set(favoriteAlgos);
    const runnable = discoveredAlgos.filter(a => !a.cannotRun);
    let favList = runnable.filter(a => favSet.has(a.id) || favSet.has(a.folderName));
    if (favList.length === 0) favList = runnable.slice(0, 10);
    // Enabled algos outside the visible list would run unseen, so they are switched off.
    const visibleIds = new Set(favList.map(a => a.id));
    const hiddenOn = Object.keys(curLayers).filter(k => curLayers[k] && !visibleIds.has(k));
    if (hiddenOn.length > 0) {
      hiddenOn.forEach(k => { curLayers[k] = false; });
      if (target) batchAction('update_params', target.batchId, { layers: curLayers });
      else api('/api/save_config', { method: 'POST', body: JSON.stringify({ layers: curLayers }) });
    }
    const enabledOrder = Object.keys(curLayers).filter(k => curLayers[k]);
    favList = favList.slice(0, 10);
    if (favBadge) favBadge.innerText = `${favList.length} / 10 Favorites`;

    const newHtml = favList.map(a => {
      const isOn = !!(curLayers[a.id] || (a.id === 'anti_inpainting' && curLayers.antiInpainting));
      const lastStr = formatLastUsed(algoLastUsed[a.id]);
      const seqNum = enabledOrder.length > 1 && isOn ? enabledOrder.indexOf(a.id) + 1 : 0;
      const escId = escapeHtml(a.id);
      return `
        <div class="layer-opt ${isOn ? 'enabled' : ''}" data-algo="${escId}" onclick="toggleAlgoLayer(event, this.dataset.algo)">
          <span class="layer-opt-name" lang="en">${seqNum ? `<span class="layer-seq-num">${seqNum}</span>` : ''}${escapeHtml(a.name)}</span>
          <div class="layer-opt-actions" onclick="event.stopPropagation()">
            <span class="info-icon">i
              <span class="info-tooltip">
                <strong style="color:#fff;">${escapeHtml(a.name)}</strong><br>
                <span style="color:var(--gold);font-size:10px;">${escapeHtml(a.attribution)}</span><br>
                <span style="color:var(--dim);font-size:10px;">Last used: ${escapeHtml(lastStr)}</span>
                <hr style="border:none;border-top:1px solid var(--line);margin:5px 0;">
                ${escapeHtml(a.shortInfo)}
              </span>
            </span>
            <span class="help-jump-btn" data-algo="${escId}" onclick="jumpToAlgoReadme(event, this.dataset.algo)" title="Open ${escapeHtml(a.name)} readmyalgo.md in Organize tab">?</span>
          </div>
        </div>
      `;
    }).join('');
    if (listEl._lastHtml !== newHtml) {
      listEl.innerHTML = newHtml;
      listEl._lastHtml = newHtml;
    }
  }
}

const MULTI_ALGO_MUTE_MS = 15 * 60 * 1000;

function readMultiAlgoMute() {
  try {
    const m = JSON.parse(localStorage.getItem('lumiyaMultiAlgoMute') || 'null');
    if (m && m.until > Date.now()) return m.choice;
    localStorage.removeItem('lumiyaMultiAlgoMute');
    return null;
  } catch (e) { return null; }
}

function closeMultiAlgoPop() {
  const pop = document.getElementById('multi-algo-pop');
  if (pop) pop.remove();
  document.removeEventListener('click', onMultiAlgoOutsideClick, true);
}

function onMultiAlgoOutsideClick(ev) {
  if (ev.target.closest('#multi-algo-pop')) return;
  ev.stopPropagation();
  ev.preventDefault();
  closeMultiAlgoPop();
}

function chooseMultiAlgo(algoId, choice) {
  if (document.getElementById('multi-algo-mute').checked) {
    try {
      localStorage.setItem('lumiyaMultiAlgoMute', JSON.stringify({ choice, until: Date.now() + MULTI_ALGO_MUTE_MS }));
    } catch (e) {}
  }
  closeMultiAlgoPop();
  applyAlgoSelection(algoId, choice);
}

function showMultiAlgoPop(ev, algoId) {
  closeMultiAlgoPop();
  const pop = document.createElement('div');
  pop.id = 'multi-algo-pop';
  pop.className = 'multi-algo-pop';
  const escId = escapeHtml(algoId);
  pop.innerHTML = `
    Using multiple algorithms extends processing time, increases computing power consumption, degrades image quality and can make the defense less effective.
    <div class="pop-actions">
      <button class="q-btn danger" data-algo="${escId}" onclick="chooseMultiAlgo(this.dataset.algo, 'multi')">Continue with multiple</button>
      <button class="q-btn" data-algo="${escId}" onclick="chooseMultiAlgo(this.dataset.algo, 'solo')">Switch to this (solo)</button>
    </div>
    <label><input type="checkbox" id="multi-algo-mute" checked> I know what I'm doing, do not remind me for 15 minutes</label>
  `;
  document.body.appendChild(pop);
  pop.style.left = `${Math.max(8, Math.min(ev.clientX + 8, window.innerWidth - pop.offsetWidth - 8))}px`;
  pop.style.top = `${Math.max(8, Math.min(ev.clientY + 8, window.innerHeight - pop.offsetHeight - 8))}px`;
  document.addEventListener('click', onMultiAlgoOutsideClick, true);
}

function toggleAlgoLayer(ev, algoId) {
  const target = getActiveTargetBatch();
  const layersObj = target ? target.layers : defaultLayers;
  const curStego = target ? (target.stegoMode || 'off') : (document.getElementById('s-stego-mode').value || 'off');
  if (curStego === 'only') return;
  if (layersObj[algoId] || !Object.values(layersObj).some(Boolean)) {
    applyAlgoSelection(algoId, 'multi');
    return;
  }
  const muted = readMultiAlgoMute();
  if (muted) applyAlgoSelection(algoId, muted);
  else showMultiAlgoPop(ev, algoId);
}

function applyAlgoSelection(algoId, choice) {
  const target = getActiveTargetBatch();
  const layersObj = target ? { ...target.layers } : { ...defaultLayers };
  const curVal = !!layersObj[algoId];
  if (choice === 'solo') Object.keys(layersObj).forEach(k => { layersObj[k] = false; });
  // Key order carries the run sequence, so a newly enabled algorithm moves to the end.
  delete layersObj[algoId];
  layersObj[algoId] = choice === 'solo' || !curVal;

  const autoPaperEl = document.getElementById('c-auto-paper');
  const autoPaper = autoPaperEl ? !!autoPaperEl.checked : true;
  const enabledAlgos = discoveredAlgos.filter(a => layersObj[a.id] && a.paper);
  const clickedAlgo = discoveredAlgos.find(a => a.id === algoId);
  const paperUpdates = {};

  if (autoPaper && enabledAlgos.length > 0) {
    const refPaper = (layersObj[algoId] && clickedAlgo && clickedAlgo.paper) ? clickedAlgo.paper : enabledAlgos[enabledAlgos.length - 1].paper;
    const budgets = enabledAlgos.map(a => Number(a.paper.budget)).filter(v => !isNaN(v));
    if (budgets.length > 0) {
      const nextEps = choice === 'solo' && refPaper.budget !== undefined ? Number(refPaper.budget) : Math.min(...budgets);
      document.getElementById('r-eps').value = nextEps;
      document.getElementById('v-eps').innerText = nextEps.toFixed(1);
      paperUpdates.epsilon = nextEps;
    }
    if (refPaper.steps !== undefined) {
      const nextSteps = parseInt(refPaper.steps, 10) || 200;
      document.getElementById('r-steps').value = nextSteps;
      document.getElementById('v-steps').innerText = `${nextSteps}`;
      paperUpdates.steps = nextSteps;
    }
    if (refPaper.geoAnchorLow !== undefined) {
      document.getElementById('r-geo-low').value = Number(refPaper.geoAnchorLow);
      paperUpdates.geoAnchorLow = Number(refPaper.geoAnchorLow);
    }
    if (refPaper.geoAnchorHigh !== undefined) {
      document.getElementById('r-geo-high').value = Number(refPaper.geoAnchorHigh);
      paperUpdates.geoAnchorHigh = Number(refPaper.geoAnchorHigh);
    }
    if (paperUpdates.geoAnchorLow !== undefined || paperUpdates.geoAnchorHigh !== undefined) {
      const gl = parseFloat(document.getElementById('r-geo-low').value);
      const gh = parseFloat(document.getElementById('r-geo-high').value);
      document.getElementById('v-geo').innerText = `${gl.toFixed(1)} – ${gh.toFixed(1)}`;
    }
    if (refPaper.temporalWeight !== undefined) {
      const tw = Number(refPaper.temporalWeight);
      document.getElementById('r-temp-weight').value = tw;
      document.getElementById('v-temp-weight').innerText = tw.toFixed(2);
      paperUpdates.temporalWeight = tw;
    }
    if (refPaper.maskAugFactor !== undefined) {
      const mf = Number(refPaper.maskAugFactor);
      document.getElementById('r-mask-aug').value = mf;
      document.getElementById('v-mask-aug').innerText = mf.toFixed(1);
      paperUpdates.maskAugFactor = mf;
    }
    if (refPaper.guidancePrompt !== undefined) {
      const promptEl = document.getElementById('s-guidance-prompt');
      if (promptEl) {
        promptEl.value = String(refPaper.guidancePrompt);
        paperUpdates.guidancePrompt = String(refPaper.guidancePrompt);
      }
    }
    lastParamEditAt = Date.now();
  }

  if (target) {
    target.layers = layersObj;
    Object.assign(target, paperUpdates);
    batchAction('update_params', target.batchId, { layers: layersObj, ...paperUpdates });
  } else {
    defaultLayers = layersObj;
    api('/api/save_config', { method: 'POST', body: JSON.stringify({ layers: defaultLayers, ...paperUpdates }) });
  }
  lastBatchesSig = '';
  syncUnifiedBoxUI();
}

let saveParamsTimer = null;

function onUnifiedBoxChange() {
  lastParamEditAt = Date.now();
  const eps = parseFloat(document.getElementById('r-eps').value);
  const steps = parseInt(document.getElementById('r-steps').value, 10);
  const guidancePrompt = document.getElementById('s-guidance-prompt').value;
  let geoAnchorLow = parseFloat(document.getElementById('r-geo-low').value);
  let geoAnchorHigh = parseFloat(document.getElementById('r-geo-high').value);
  if (geoAnchorLow > geoAnchorHigh) {
    const tmp = geoAnchorLow; geoAnchorLow = geoAnchorHigh; geoAnchorHigh = tmp;
  }
  const temporalWeight = parseFloat(document.getElementById('r-temp-weight').value);
  const maskAugFactor = parseFloat(document.getElementById('r-mask-aug').value);
  const stegoMode = document.getElementById('s-stego-mode').value;
  const stegoText = document.getElementById('s-stego-text').value;

  syncStegoSwitchButtons(stegoMode);
  const bannerTarget = getActiveTargetBatch();
  updateNoAlgoBanner(bannerTarget ? bannerTarget.layers : defaultLayers, stegoMode);
  if (!paramEditing['eps']) document.getElementById('v-eps').innerText = eps.toFixed(1);
  if (!paramEditing['steps']) document.getElementById('v-steps').innerText = `${steps}`;
  document.getElementById('v-geo').innerText = `${geoAnchorLow.toFixed(1)} – ${geoAnchorHigh.toFixed(1)}`;
  if (!paramEditing['temp-weight']) document.getElementById('v-temp-weight').innerText = temporalWeight.toFixed(2);
  if (!paramEditing['mask-aug']) document.getElementById('v-mask-aug').innerText = maskAugFactor.toFixed(1);

  const paramsPayload = {
    epsilon: eps,
    steps: steps,
    guidancePrompt,
    geoAnchorLow,
    geoAnchorHigh,
    temporalWeight,
    maskAugFactor,
    stegoMode,
    stegoText,
    convertPng: document.getElementById('s-convert-png').value !== 'false',
    computeLevel: COMPUTE_LEVELS[document.getElementById('r-compute').value],
    stegoPayload: document.getElementById('s-stego-payload').value,
    seed: Math.max(0, parseInt(document.getElementById('s-seed').value, 10) || 0),
    stegoStrength: parseFloat(document.getElementById('r-stego-strength').value),
    stegoScale: parseFloat(document.getElementById('r-stego-scale').value),
    stegoPlacement: document.getElementById('s-stego-placement').value,
    ...(stegoMarkDirty ? { stegoMark } : {})
  };
  renderStegoControls();

  const target = getActiveTargetBatch();
  if (target) {
    Object.assign(target, paramsPayload);
  }

  if (saveParamsTimer) clearTimeout(saveParamsTimer);
  saveParamsTimer = setTimeout(() => {
    saveParamsTimer = null;
    stegoMarkDirty = false;
    stegoMarkId = null;
    const curTarget = getActiveTargetBatch();
    if (curTarget) {
      batchAction('update_params', curTarget.batchId, { ...paramsPayload, layers: curTarget.layers });
    } else {
      api('/api/save_config', { method: 'POST', body: JSON.stringify(paramsPayload) });
    }
    lastBatchesSig = '';
  }, 220);
}

/* Telemetry 3-Dot Menu */
function toggleSensorMenu(e) {
  e.stopPropagation();
  renderSensorMenu();
  document.getElementById('sensor-menu').classList.toggle('open');
}

function renderSensorMenu() {
  const container = document.getElementById('sensor-menu-rows');
  container.innerHTML = Object.entries(metricsCfg).map(([key, cfg]) => {
    const swatches = PALETTE.map(c => {
      const isSelected = cfg.color === c;
      const cls = !cfg.enabled ? 'swatch disabled' : (isSelected ? 'swatch selected' : 'swatch');
      return `<div class="${cls}" style="background:${c}" onclick="pickMetricColor('${key}', '${c}')"></div>`;
    }).join('');

    const lineToggle = cfg.type === 'line' ? `
      <button class="style-toggle" ${!cfg.enabled ? 'disabled' : ''} onclick="toggleMetricDash('${key}')">
        ${cfg.dashed ? 'Dotted' : 'Solid'}
      </button>
    ` : `<span style="font-size:10px;color:var(--dim);font-family:var(--font-sans);">4px Bars</span>`;

    return `
      <div class="sensor-row">
        <label style="display:flex;align-items:center;gap:6px;cursor:pointer;">
          <input type="checkbox" ${cfg.enabled ? 'checked' : ''} onchange="toggleMetric('${key}', this.checked)">
          <span style="color:${cfg.enabled ? 'var(--fg)' : 'var(--dim)'}">${cfg.label}</span>
        </label>
        <div class="sensor-controls">
          ${lineToggle}
          <div class="swatch-group">${swatches}</div>
        </div>
      </div>
    `;
  }).join('');
}

function toggleMetric(key, val) { metricsCfg[key].enabled = val; renderSensorMenu(); drawMainGraph(); }
function toggleMetricDash(key) { if (!metricsCfg[key].enabled) return; metricsCfg[key].dashed = !metricsCfg[key].dashed; renderSensorMenu(); drawMainGraph(); }
function pickMetricColor(key, color) { if (!metricsCfg[key].enabled) return; metricsCfg[key].color = color; renderSensorMenu(); drawMainGraph(); }

/* Smooth Anti-Aliased Catmull-Rom / Cubic Bezier Curve Renderer */
let canvasResizeEpoch = 1;
window.addEventListener('resize', () => { canvasResizeEpoch++; });

function ensureHiDPICanvas(c) {
  const dpr = window.devicePixelRatio || 1;
  if (c._resizeEpoch !== canvasResizeEpoch || !c._cssW || !c._cssH) {
    const rect = c.getBoundingClientRect();
    c._cssW = rect.width > 10 ? Math.round(rect.width) : (parseInt(c.getAttribute('width'), 10) || 260);
    c._cssH = rect.height > 10 ? Math.round(rect.height) : (parseInt(c.getAttribute('height'), 10) || 68);
    c._resizeEpoch = canvasResizeEpoch;
  }
  const cssW = c._cssW;
  const cssH = c._cssH;
  const targetW = Math.round(cssW * dpr);
  const targetH = Math.round(cssH * dpr);
  if (c.width !== targetW || c.height !== targetH) {
    c.width = targetW;
    c.height = targetH;
  }
  const ctx = c.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.lineJoin = 'round';
  ctx.lineCap = 'round';
  return { ctx, W: cssW, H: cssH };
}

function traceSmoothBezierPath(ctx, pts, moveFirst = true) {
  if (!pts || pts.length === 0) return;
  if (moveFirst) ctx.moveTo(pts[0].x, pts[0].y);
  else ctx.lineTo(pts[0].x, pts[0].y);
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[i];
    const p1 = pts[i + 1];
    const cx = (p0.x + p1.x) * 0.5;
    ctx.bezierCurveTo(cx, p0.y, cx, p1.y, p1.x, p1.y);
  }
}

function drawSensorSparkline(canvasId, dataArr, colorHex, maxScale = 100.0) {
  const c = document.getElementById(canvasId);
  if (!c) return;
  const { ctx, W, H } = ensureHiDPICanvas(c);
  ctx.clearRect(0, 0, W, H);

  if (c._gradW !== W || c._gradColor !== colorHex) {
    const fg = ctx.createLinearGradient(0, 0, W, 0);
    fg.addColorStop(0.0, colorHex + '05');
    fg.addColorStop(0.45, colorHex + '14');
    fg.addColorStop(1.0, colorHex + '28');
    const sg = ctx.createLinearGradient(0, 0, W, 0);
    sg.addColorStop(0.0, colorHex + '18');
    sg.addColorStop(0.45, colorHex + '75');
    sg.addColorStop(1.0, colorHex);
    c._fillGrad = fg;
    c._strokeGrad = sg;
    c._gradW = W;
    c._gradColor = colorHex;
  }

  const pts = [];
  for (let i = 0; i < BINS; i++) {
    const x = (i / (BINS - 1)) * W;
    const norm = Math.min(Math.max(dataArr[i] / Math.max(1, maxScale), 0), 1);
    const y = H - norm * (H - 12) - 1;
    pts.push({ x, y });
  }

  ctx.fillStyle = c._fillGrad;
  ctx.beginPath();
  ctx.moveTo(0, H);
  traceSmoothBezierPath(ctx, pts, false);
  ctx.lineTo(W, H);
  ctx.closePath();
  ctx.fill();

  ctx.strokeStyle = c._strokeGrad;
  ctx.lineWidth = 1.65;
  ctx.beginPath();
  traceSmoothBezierPath(ctx, pts, true);
  ctx.stroke();
}

function drawMainGraph() {
  const workPage = document.getElementById('page-work');
  if (workPage && !workPage.classList.contains('active')) return;
  const c = document.getElementById('main-graph');
  if (!c) return;
  const { ctx, W, H } = ensureHiDPICanvas(c);
  ctx.clearRect(0, 0, W, H);

  ctx.setLineDash([]);
  ctx.strokeStyle = '#262626';
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (let y = 26; y < H; y += 26) {
    ctx.moveTo(0, y);
    ctx.lineTo(W, y);
  }
  ctx.stroke();

  const binW = W / BINS;

  if (metricsCfg.rate.enabled) {
    const maxRate = Math.max(...histBuffers.rate, 4.0);
    ctx.fillStyle = metricsCfg.rate.color;
    const barW = 4;
    for (let i = 0; i < BINS; i++) {
      const val = histBuffers.rate[i];
      if (val > 0.01) {
        const barH = Math.max(5, (val / maxRate) * (H - 12));
        const xCenter = i * binW + (binW - barW) * 0.5;
        ctx.fillRect(xCenter, H - barH, barW, barH);
      }
    }
  }

  ['gpu', 'cpu', 'ram', 'vram', 'temp', 'pwr'].forEach(key => {
    const cfg = metricsCfg[key];
    if (!cfg || !cfg.enabled) return;
    const arr = histBuffers[key];
    const scaleMax = key === 'pwr' ? 180.0 : 100.0;
    const pts = [];
    for (let i = 0; i < BINS; i++) {
      const x = i * binW + binW * 0.5;
      const norm = Math.min(Math.max(arr[i] / scaleMax, 0), 1);
      const y = H - norm * (H - 10) - 3;
      pts.push({ x, y });
    }
    ctx.strokeStyle = cfg.color;
    ctx.lineWidth = 1.75;
    ctx.setLineDash(cfg.dashed ? [4, 4] : []);
    ctx.beginPath();
    traceSmoothBezierPath(ctx, pts, true);
    ctx.stroke();
  });
  ctx.setLineDash([]);
}

function openLightbox(batchId, fileId, fileName) {
  const modal = document.getElementById('lightbox-modal');
  document.getElementById('lightbox-title').innerText = `Preview: ${fileName}`;
  document.getElementById('lightbox-img').src = apiUrl(`/api/preview_image?batch=${encodeURIComponent(batchId)}&file=${encodeURIComponent(fileId)}`);
  modal.classList.add('open');
}

function closeLightbox() {
  document.getElementById('lightbox-modal').classList.remove('open');
  document.getElementById('lightbox-img').src = '';
}

async function checkStegoMessage(e, batchId, fileId, fileName) {
  if (e) e.stopPropagation();
  const r = await api(`/api/check_stego?batch=${encodeURIComponent(batchId)}&file=${encodeURIComponent(fileId)}`);
  const d = await r.json();
  const bodyEl = document.getElementById('stego-modal-body');
  const inspBtn = document.getElementById('stego-modal-insp-btn');
  if (inspBtn) {
    inspBtn.onclick = () => inspectStegoRegionFromPopup(batchId, fileId);
  }
  if (d.found) {
    bodyEl.innerHTML = `
      <div style="color:var(--green);margin-bottom:8px;">&#10004; STEGANOGRAPHIC PAYLOAD VERIFIED</div>
      <div style="color:var(--dim);margin-bottom:4px;">File: <span style="color:var(--fg);">${escapeHtml(fileName)}</span></div>
      <div style="color:var(--dim);margin-bottom:4px;">Method: <span style="color:var(--fg);">${escapeHtml(d.method || '2-Bit RGB LSB')}</span></div>
      <div style="color:var(--dim);margin-bottom:10px;">Primary Frame Origin: <span style="color:var(--fg);">Pixel (0, 0) &rarr; Top-Left Scanline Header (LMY1)</span></div>
      ${d.message ? `<div class="enclosed-stego-readout">${escapeHtml(d.message)}</div>` : ''}
      ${d.markPng ? `<div style="color:var(--muted);margin:6px 0 4px;">Recovered mark (${d.markCoverage}% of photo, confidence ${d.markScore}%)</div><img alt="Recovered hidden mark" src="data:image/png;base64,${d.markPng}" style="width:100%;background:#000;">` : ''}
    `;
  } else {
    bodyEl.innerHTML = `
      <div style="color:var(--red);margin-bottom:8px;">&#10008; NO STEGANOGRAPHIC PAYLOAD FOUND</div>
      <div style="color:var(--muted);">${escapeHtml(d.error || 'No Lumiya LSB frame was detected in this file.')}</div>
    `;
  }
  document.getElementById('stego-modal').classList.add('open');
}

function inspectStegoRegionFromPopup(batchId, fileId) {
  document.getElementById('stego-modal').classList.remove('open');
  const b = allBatches.find(x => x.batchId === batchId);
  if (!b) return;
  const f = b.files.find(x => x.fileId === fileId);
  if (!f) return;
  addFileObjToInspect(batchId, f);
  inspectQuickBefore = false;
  document.getElementById('vm-swap').classList.remove('active');
  inspectViewMode = 'side';
  ['single', 'side', 'wipe'].forEach(m => {
    const btn = document.getElementById(`vm-${m}`);
    if (btn) btn.classList.toggle('active', m === 'side');
  });
  document.getElementById('insp-wipe-ctrl').style.display = 'none';
  inspectLens = 'normal';
  setInspectLens('lsb');
  inspectZoom = 8;
  inspectTargetZoom = 8;
  inspectCenter = { u: 0.04, v: 0.04 };
  inspectTargetCenter = { u: 0.04, v: 0.04 };
  toggleInspectEyePopup(true);
  lastBatchesSig = '';
  updateInspectBadges();
  switchTab('insp');
}

async function batchAction(action, batchId, extra = {}) {
  const r = await api('/api/batch_action', {
    method: 'POST',
    body: JSON.stringify({ action, batchId, ...extra })
  });
  try {
    const d = await r.json();
    // Parameter edits save half-finished setups too (no mark yet); Run/Restart validate again and report then.
    if (d && d.ok === false && d.error) {
      if (action === 'update_params') return;
      showBanner(`<strong>&#9650; Batch Condition:</strong> ${escapeHtml(d.error)}`, true);
    } else if (document.getElementById('wide-banner-text').textContent.includes('Batch Condition')) {
      document.getElementById('wide-banner').classList.remove('visible');
    }
    return d;
  } catch (e) {}
}

function toggleBatchCollapse(e, batchId) {
  if (e) e.stopPropagation();
  selectBatchForEditing(batchId);
  collapsedBatches[batchId] = !collapsedBatches[batchId];
  const isCol = !!collapsedBatches[batchId];
  const node = document.getElementById(`batch-node-${batchId}`);
  const arrow = document.getElementById(`batch-arrow-${batchId}`);
  const wrap = document.getElementById(`batch-children-${batchId}`);
  if (node) node.classList.toggle('collapsed', isCol);
  if (arrow) arrow.classList.toggle('collapsed', isCol);
  if (wrap) wrap.classList.toggle('collapsed', isCol);
}

/* Drag & Drop File Sequence Reordering & Splitting to New Batch */
// Queue file selection: plain click selects one, Ctrl/Cmd toggles, Shift selects a range. One batch at a time.
const queueSel = { batchId: null, ids: new Set(), anchor: null };

function isLockedQueueFile(f) { return f.status === 'DONE' || f.status === 'RUNNING'; }

function onQueueRowClick(e, batchId, fileId) {
  if (e.target.closest('button, .preview-btn')) return;
  const b = allBatches.find(x => x.batchId === batchId);
  if (!b) return;
  const order = b.files.map(f => f.fileId);
  if (queueSel.batchId !== batchId) { queueSel.batchId = batchId; queueSel.ids = new Set(); queueSel.anchor = null; }
  if (e.shiftKey && queueSel.anchor && order.includes(queueSel.anchor)) {
    const [a, z] = [order.indexOf(queueSel.anchor), order.indexOf(fileId)].sort((p, q) => p - q);
    if (!(e.ctrlKey || e.metaKey)) queueSel.ids = new Set();
    order.slice(a, z + 1).forEach(id => queueSel.ids.add(id));
  } else if (e.ctrlKey || e.metaKey) {
    if (queueSel.ids.has(fileId)) queueSel.ids.delete(fileId); else queueSel.ids.add(fileId);
    queueSel.anchor = fileId;
  } else {
    const onlyThis = queueSel.ids.size === 1 && queueSel.ids.has(fileId);
    queueSel.ids = onlyThis ? new Set() : new Set([fileId]);
    queueSel.anchor = fileId;
  }
  applyQueueSelection();
}

function applyQueueSelection() {
  const b = allBatches.find(x => x.batchId === queueSel.batchId);
  if (!b) { queueSel.batchId = null; queueSel.ids.clear(); }
  else queueSel.ids.forEach(id => { if (!b.files.some(f => f.fileId === id)) queueSel.ids.delete(id); });
  document.querySelectorAll('#queue-tree .file-row').forEach(row => {
    row.classList.toggle('selected', row.dataset.batch === queueSel.batchId && queueSel.ids.has(row.dataset.file));
  });
}

// The files an action on this row applies to: the whole selection if the row is part of it, else just the row.
function queueTargets(batchId, fileId) {
  const b = allBatches.find(x => x.batchId === batchId);
  if (!b) return [];
  if (queueSel.batchId === batchId && queueSel.ids.has(fileId)) return b.files.filter(f => queueSel.ids.has(f.fileId));
  return b.files.filter(f => f.fileId === fileId);
}

function onFileDragStart(e, batchId, fileId) {
  dragPayload = { batchId, fileIds: queueTargets(batchId, fileId).map(f => f.fileId) };
  e.dataTransfer.effectAllowed = 'copyMove';
}

function onFileDragOver(e, rowEl) {
  e.preventDefault();
  rowEl.classList.add('drag-over');
}

function onFileDragLeave(rowEl) {
  rowEl.classList.remove('drag-over');
}

async function onFileDropOnRow(e, targetBatchId, targetIndex, rowEl) {
  e.preventDefault();
  e.stopPropagation();
  rowEl.classList.remove('drag-over');
  if (!dragPayload) return;
  await batchAction('reorder_file', dragPayload.batchId, {
    fileIds: dragPayload.fileIds,
    targetBatchId: targetBatchId,
    targetIndex: targetIndex
  });
  dragPayload = null;
}

async function onFileDropNewBatch(e, zoneEl) {
  e.preventDefault();
  e.stopPropagation();
  zoneEl.classList.remove('drag-over');
  if (!dragPayload) return;
  await batchAction('reorder_file', dragPayload.batchId, {
    fileIds: dragPayload.fileIds,
    targetBatchId: 'NEW_BATCH',
    targetIndex: 0
  });
  dragPayload = null;
}

let delDriveTimer = null;
let delIrreversibleTimer = null;

function closeDelDriveConfirmModal() {
  if (delIrreversibleTimer) {
    clearInterval(delIrreversibleTimer);
    delIrreversibleTimer = null;
  }
  const modal = document.getElementById('del-drive-confirm-modal');
  if (modal) modal.classList.remove('open');
}

function openDelDriveConfirm(onConfirm) {
  const modal = document.getElementById('del-drive-confirm-modal');
  const finalBtn = document.getElementById('del-drive-final-btn');
  if (!modal || !finalBtn) return;
  if (delIrreversibleTimer) {
    clearInterval(delIrreversibleTimer);
    delIrreversibleTimer = null;
  }
  let sLeft = 3;
  finalBtn.disabled = true;
  finalBtn.innerText = `(I know what I'm doing) (${sLeft}s)`;
  modal.classList.add('open');

  delIrreversibleTimer = setInterval(() => {
    sLeft--;
    if (sLeft > 0) {
      finalBtn.innerText = `(I know what I'm doing) (${sLeft}s)`;
    } else {
      clearInterval(delIrreversibleTimer);
      delIrreversibleTimer = null;
      finalBtn.innerText = "I know what I'm doing";
      finalBtn.disabled = false;
    }
  }, 1000);

  finalBtn.onclick = () => {
    closeDelDriveConfirmModal();
    onConfirm();
  };
}

function requestDeleteBatch(e, batchId, isLastFileRemoval = false, fileId = null) {
  if (e) e.stopPropagation();
  const run = keepExports => {
    if (isLastFileRemoval && fileId && keepExports) batchAction('remove_file', batchId, { fileId });
    else batchAction('delete_batch', batchId, { keepExports });
  };
  const muteUntil = parseInt(localStorage.getItem('lumiyaMuteDeleteUntil') || '0', 10);
  if (Date.now() < muteUntil && localStorage.getItem('lumiyaMuteDeleteChoice') === 'catalog') {
    run(true);
    return;
  }
  const modal = document.getElementById('del-modal');
  document.getElementById('del-modal-title').innerText = 'Delete Batch Queue';
  document.getElementById('del-modal-text').innerText = isLastFileRemoval
    ? `Removing the last image in batch [${batchId}] will delete the entire batch queue. Continue?`
    : `Remove batch queue [${batchId}]? Remove from Catalog keeps its exported files. Delete from Drive also erases its results folder.`;
  document.getElementById('del-mute-chk').checked = false;
  modal.classList.add('open');

  const confirmBtn = document.getElementById('del-confirm-btn');
  const catalogBtn = document.getElementById('del-catalog-btn');

  if (delDriveTimer) {
    clearInterval(delDriveTimer);
    delDriveTimer = null;
  }
  confirmBtn.classList.add('danger-solid');
  let secondsLeft = 10;
  confirmBtn.disabled = true;
  confirmBtn.innerText = `Delete from Drive (${secondsLeft}s)`;

  delDriveTimer = setInterval(() => {
    secondsLeft--;
    if (secondsLeft > 0) {
      confirmBtn.innerText = `Delete from Drive (${secondsLeft}s)`;
    } else {
      clearInterval(delDriveTimer);
      delDriveTimer = null;
      confirmBtn.innerText = 'Delete from Drive';
      confirmBtn.disabled = false;
    }
  }, 1000);

  catalogBtn.style.display = '';
  catalogBtn.onclick = () => {
    if (delDriveTimer) { clearInterval(delDriveTimer); delDriveTimer = null; }
    if (document.getElementById('del-mute-chk').checked) {
      localStorage.setItem('lumiyaMuteDeleteUntil', (Date.now() + 30 * 60 * 1000).toString());
      localStorage.setItem('lumiyaMuteDeleteChoice', 'catalog');
    }
    closeDelModal();
    run(true);
  };

  confirmBtn.onclick = () => {
    if (confirmBtn.disabled) return;
    if (delDriveTimer) { clearInterval(delDriveTimer); delDriveTimer = null; }
    const muteChecked = document.getElementById('del-mute-chk').checked;
    closeDelModal();
    openDelDriveConfirm(() => {
      if (muteChecked) {
        localStorage.setItem('lumiyaMuteDeleteUntil', (Date.now() + 30 * 60 * 1000).toString());
        localStorage.setItem('lumiyaMuteDeleteChoice', 'drive');
      }
      run(false);
    });
  };
}

function requestClearHistory() {
  const muteUntil = parseInt(localStorage.getItem('lumiyaMuteHistoryUntil') || '0', 10);
  if (Date.now() < muteUntil) {
    api('/api/clear_history', { method: 'POST' });
    return;
  }
  if (delDriveTimer) {
    clearInterval(delDriveTimer);
    delDriveTimer = null;
  }
  const modal = document.getElementById('del-modal');
  const confirmBtn = document.getElementById('del-confirm-btn');
  confirmBtn.disabled = false;
  confirmBtn.classList.remove('danger-solid');
  document.getElementById('del-modal-title').innerText = 'Clear Artifact History';
  confirmBtn.innerText = 'Confirm Delete';
  document.getElementById('del-catalog-btn').style.display = 'none';
  document.getElementById('del-modal-text').innerText = 'Clear all entries from the persistent History log (user/history.json)? Exported files in results/ will remain untouched.';
  document.getElementById('del-mute-chk').checked = false;
  modal.classList.add('open');

  confirmBtn.onclick = () => {
    if (document.getElementById('del-mute-chk').checked) {
      localStorage.setItem('lumiyaMuteHistoryUntil', (Date.now() + 30 * 60 * 1000).toString());
    }
    closeDelModal();
    api('/api/clear_history', { method: 'POST' });
  };
}

function closeDelModal() {
  if (delDriveTimer) {
    clearInterval(delDriveTimer);
    delDriveTimer = null;
  }
  const confirmBtn = document.getElementById('del-confirm-btn');
  if (confirmBtn) {
    confirmBtn.disabled = false;
    confirmBtn.classList.remove('danger-solid');
  }
  document.getElementById('del-modal').classList.remove('open');
}

// Unprocessed images go freely (an emptied batch just disappears, nothing was produced); processed ones are locked.
function removeSingleFile(e, batchId, fileId) {
  e.stopPropagation();
  const targets = queueTargets(batchId, fileId);
  const free = targets.filter(f => !isLockedQueueFile(f));
  if (!free.length) {
    if (window.showFloatingTip) showFloatingTip(e.currentTarget);
    return;
  }
  queueSel.ids.clear();
  batchAction('remove_file', batchId, { fileIds: free.map(f => f.fileId) }).then(d => {
    if (!d || !d.ok) return;
    // Drop the rows now instead of waiting up to a poll interval for the next status update to redraw the queue.
    const b = allBatches.find(x => x.batchId === batchId);
    if (!b) return;
    const gone = new Set(free.map(f => f.fileId));
    b.files = b.files.filter(f => !gone.has(f.fileId));
    if (d.batchDeleted) allBatches = allBatches.filter(x => x !== b);
    lastBatchesSig = '';
    renderQueueTree(allBatches, lastQueueBusy, lastQueueActive, lastQueueMajor);
  });
}

let lastQueueBusy = false, lastQueueActive = '', lastQueueMajor = true;
function renderQueueTree(batches, systemBusy, activeBatchId, majorReady) {
  [lastQueueBusy, lastQueueActive, lastQueueMajor] = [systemBusy, activeBatchId, majorReady];
  allBatches = batches || [];
  if (!selectedBatchId && allBatches.length > 0) {
    selectedBatchId = allBatches[0].batchId;
  } else if (selectedBatchId && !allBatches.some(b => b.batchId === selectedBatchId)) {
    selectedBatchId = allBatches.length > 0 ? allBatches[0].batchId : null;
  }

  syncInspectCollectionWithBatches();
  const inspCount = inspectItems.length;
  const sig = JSON.stringify({ batches, systemBusy, activeBatchId, selectedBatchId, collapsedBatches, majorReady, inspCount, favoriteAlgos });
  if (sig === lastBatchesSig) return;
  lastBatchesSig = sig;
  syncUnifiedBoxUI();

  const container = document.getElementById('queue-tree');
  if (allBatches.length === 0) {
    container.innerHTML = `<div class="empty-queue">
      <div class="empty-queue-face" aria-hidden="true">:(</div>
      <div>&ldquo;Please, your honorable, give me a j*b, I know this economy is bad.&rdquo;</div>
    </div>`;
    return;
  }

  const batchesHtml = allBatches.map(b => {
    const isCollapsed = !!collapsedBatches[b.batchId];
    const isSelected = selectedBatchId === b.batchId;
    const isThisRunning = systemBusy && activeBatchId === b.batchId;
    const isLockedByOther = systemBusy && activeBatchId !== b.batchId;
    const hasActiveAlgo = b.layers && Object.values(b.layers).some(Boolean);
    const hasStegoText = b.stegoPayload === 'image' ? !!(b.markId || b.stegoMark) : !!(b.stegoText && b.stegoText.trim().length > 0);
    const paramInvalid = hasParamError || (b.stegoMode !== 'only' && !hasActiveAlgo) || ((b.stegoMode === 'combined' || b.stegoMode === 'only') && !hasStegoText);
    const canRunThis = isSelected && (majorReady || b.stegoMode === 'only') && !systemBusy && !paramInvalid;
    const isFinished = b.state === 'COMPLETED' || b.state === 'STOPPED';
    const depBlocked = !majorReady && b.stegoMode !== 'only';
    const canExport = !!b.hasExported;

    const lockReason = hasParamError
      ? '▲ Parameter value is out of bounds: not an applicable value. Correct parameter value before running.'
      : (depBlocked
          ? '▲ Missing required dependencies. Open the Configuration tab to inspect missing packages and run install.bat.'
          : (paramInvalid
              ? '▲ Batch parameters incomplete: enable at least one AI-Defense Layer or enter a non-empty steganography payload.'
              : '▲ Another batch is currently executing on the compute engine.'));

    const escBid = escapeHtml(b.batchId);
    const childrenHtml = `
      <div class="batch-children-wrap ${isCollapsed ? 'collapsed' : ''}" id="batch-children-${escBid}">
        <div class="batch-children-inner">
          <div class="batch-children">
            ${b.files.map((f, idx) => {
              const escFid = escapeHtml(f.fileId);
              const escName = escapeHtml(f.name);
              const dispName = formatQueueFileName(f.name, 36);
              const fStatusDisp = f.status ? (f.status.charAt(0).toUpperCase() + f.status.slice(1).toLowerCase()) : '';
              return `
              <div class="file-row"
                   data-batch="${escBid}" data-file="${escFid}"
                   onclick="onQueueRowClick(event, this.dataset.batch, this.dataset.file)"
                   draggable="true"
                   ondragstart="onFileDragStart(event, this.dataset.batch, this.dataset.file)"
                   ondragover="onFileDragOver(event, this)"
                   ondragleave="onFileDragLeave(this)"
                   ondrop="onFileDropOnRow(event, this.dataset.batch, ${idx}, this)">
                <div class="file-left">
                  <span class="drag-grip" title="Drag up/down to reorder or drag to bottom zone for new batch">&#8942;&#8942;</span>
                  <span style="color:var(--dim);flex-shrink:0;">&#9500;&#9472;</span>
                  ${!f.valid ? `<span class="bad-tri" title="${escapeHtml(f.errorMsg)}">&#9650;</span>` : ''}
                  <span class="file-name-cell" title="${escName}">${dispName}</span>
                  <span class="file-meta-cell">(${escapeHtml(f.dims)} &bull; ${f.sizeKb} KB)</span>
                </div>
                <div class="file-right">
                  <span class="mono" style="font-size:11px;color:var(--muted);">${escapeHtml(fStatusDisp)}</span>
                  ${(f.status === 'DONE' && f.hasStego) ? `
                    <button class="preview-btn" style="border-color:var(--gold);color:var(--gold);" data-batch="${escBid}" data-file="${escFid}" data-name="${escName}" onclick="checkStegoMessage(event, this.dataset.batch, this.dataset.file, this.dataset.name)" title="Decode embedded steganographic signature">
                      See Hidden Message
                    </button>
                  ` : ''}
                  ${f.thumb ? `
                    <div class="preview-btn" data-batch="${escBid}" data-file="${escFid}" data-name="${escName}" onclick="openLightbox(this.dataset.batch, this.dataset.file, this.dataset.name)" title="Click to enlarge">
                      Preview
                      <div class="preview-pop"><img src="${f.thumb}" alt="Preview"></div>
                    </div>
                  ` : ''}
                  <button class="preview-btn" data-batch="${escBid}" data-file="${escFid}" onclick="sendFileToInspect(event, this.dataset.batch, this.dataset.file, false)" title="Add this image to the Inspect collection">Inspect</button>
                  ${inspCount > 0 ? `<button class="preview-btn" style="border-color:var(--gold);color:var(--gold);" data-batch="${escBid}" data-file="${escFid}" onclick="sendFileToInspect(event, this.dataset.batch, this.dataset.file, true)" title="Purge current Inspect collection and inspect only this image">Purge &amp; Inspect</button>` : ''}
                  <button class="q-btn danger ${isLockedQueueFile(f) ? 'is-locked' : ''}" data-batch="${escBid}" data-file="${escFid}" onclick="removeSingleFile(event, this.dataset.batch, this.dataset.file)" ${isLockedQueueFile(f) ? '' : 'title="Remove image (or every selected image)"'}>&times;${isLockedQueueFile(f) ? '<span class="info-tooltip"><strong>Already processed.</strong> This image cannot be removed from its batch. Drag it to another batch to queue a fresh copy of the original.</span>' : ''}</button>
                </div>
              </div>
            `;}).join('')}
          </div>
        </div>
      </div>
    `;

    const bStateDisplay = b.state ? (b.state.charAt(0).toUpperCase() + b.state.slice(1).toLowerCase()) : '';
    return `
      <div class="batch-node ${isSelected ? 'selected' : ''} ${isCollapsed ? 'collapsed' : ''}" id="batch-node-${escBid}">
        <div class="batch-header" data-batch="${escBid}" onclick="toggleBatchCollapse(event, this.dataset.batch)">
          <div class="batch-title">
            <span class="batch-arrow ${isCollapsed ? 'collapsed' : ''}" id="batch-arrow-${escBid}">&#9660;</span>
            <strong>${escBid}</strong>
            <span style="color:var(--muted);font-size:11px;">[${b.files.length} file(s) &bull; ${escapeHtml(bStateDisplay)} &bull; Budget ${b.epsilon} &bull; Compute ${b.computeLevel}x${b.stegoMode !== 'off' ? ' &bull; Stego:' + escapeHtml(b.stegoMode) : ''}]</span>
          </div>
          <div class="batch-actions" onclick="event.stopPropagation()">
            <div class="run-lock-wrap ${(depBlocked || isLockedByOther || paramInvalid) ? 'locked' : ''}">
              ${depBlocked ? `<span class="dep-missing-tri" onclick="switchTab('cfg')">&#9650;</span>` : ''}
              <div class="run-lock-tip">${lockReason}</div>
              <button class="q-btn primary" ${!canRunThis ? 'disabled' : ''} data-batch="${escBid}" onclick="batchAction('${isFinished ? 'restart' : 'run'}', this.dataset.batch)">${isFinished ? '&#8635; Redo' : '&#9654; Run'}</button>
            </div>
            <button class="q-btn" ${!isThisRunning ? 'disabled' : ''} data-batch="${escBid}" onclick="batchAction('stop', this.dataset.batch)">&#9209; Stop</button>
            <button class="q-btn" data-batch="${escBid}" onclick="sendBatchToInspect(event, this.dataset.batch, false)" title="Add all valid images in this batch to Inspect">Inspect</button>
            ${inspCount > 0 ? `<button class="q-btn" style="border-color:var(--gold);color:var(--gold);" data-batch="${escBid}" onclick="sendBatchToInspect(event, this.dataset.batch, true)" title="Purge current Inspect collection and load this batch">Purge &amp; Inspect</button>` : ''}
            <button class="q-btn" ${!canExport ? 'disabled' : ''} data-batch="${escBid}" onclick="batchAction('open_batch_export', this.dataset.batch)" title="Open in Explorer" aria-label="Open in Explorer"><svg viewBox="0 0 16 16" width="14" height="14" fill="currentColor" aria-hidden="true"><path d="M1 3h5l2 2h7v8H1z"/></svg></button>
            <button class="q-btn danger" data-batch="${escBid}" onclick="requestDeleteBatch(event, this.dataset.batch, false)">&#10005; Delete</button>
          </div>
        </div>
        ${childrenHtml}
      </div>
    `;
  }).join('');

  container.innerHTML = batchesHtml + `
    <div class="split-batch-dropzone"
         ondragover="event.preventDefault();this.classList.add('drag-over')"
         ondragleave="this.classList.remove('drag-over')"
         ondrop="onFileDropNewBatch(event, this)">
      [ + Drag any queued file here to detach and create a new Batch ]
    </div>
  `;
  applyQueueSelection();
}

/* ========================================================================= */
/* INSPECT TAB: LIGHTROOM CLASSIC LOUPE / SPLIT / WIPE & FORENSIC SUITE      */
/* ========================================================================= */
let inspectItems = [];
let activeInspectIdx = 0;
let inspectViewMode = 'single'; // 'single' | 'side' | 'wipe'
let inspectQuickBefore = false;
let inspectWipePct = 0.50;
let inspectLens = 'normal'; // 'normal' | 'diff' | 'fft' | 'ela' | 'sobel' | 'srm' | 'luma_map' | 'chroma' | 'lsb' | 'mark' | 'stego_plane'
let inspectGain = 20;
let inspectElaQ = 90;
let inspectNoiseFloor = 0;
let stegoChannel = 'rgb'; // 'rgb' | 'r' | 'g' | 'b' | 'a' | 'luma'
let stegoBitPlane = -1;   // -1 (All Bits) | 0..7
let stegoInvert = false;
let stegoLut = false;
let lsbScanRowFirst = true;
let lsbBitMsbFirst = true;
let inspectStegoOverlay = null;
let inspectZoom = 'FIT'; // 'FIT' | number (0.25 .. 16)
let inspectTargetZoom = 'FIT';
let inspectCenter = { u: 0.5, v: 0.5 };
let inspectTargetCenter = { u: 0.5, v: 0.5 };
let inspectAnimRaf = null;
let inspectDrag = null;
// Click / Z / navigator zoom: the last zoom the user settled on, remembered across sessions (2:1 until then).
const INSPECT_ZOOM_STORE_KEY = 'lumiyaInspectZoom';
let inspectClickZoom = 2;
try { inspectClickZoom = Number(localStorage.getItem(INSPECT_ZOOM_STORE_KEY)) || 2; } catch (e) {}
const inspectCache = {};

const STEGO_RANDOM_LUT = [
  [0, 0, 0],
  [250, 77, 86],
  [66, 190, 101],
  [15, 98, 254],
  [243, 214, 137],
  [190, 149, 255],
  [61, 219, 217],
  [255, 126, 182]
];

