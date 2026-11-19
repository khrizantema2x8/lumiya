function toggleLrPanel(panelId) {
  const el = document.getElementById(panelId);
  if (el) el.classList.toggle('collapsed');
}

function canCompareBeforeAfter(item, entry) {
  if (!item || item.isStandalone || !item.hasExport) return false;
  if (entry && entry.loaded && !entry.hasExport) return false;
  return true;
}

function syncInspectViewButtons(item, entry) {
  const canBA = canCompareBeforeAfter(item, entry);
  const sideBtn = document.getElementById('vm-side');
  const wipeBtn = document.getElementById('vm-wipe');
  const swapBtn = document.getElementById('vm-swap');
  if (sideBtn) sideBtn.disabled = !canBA;
  if (wipeBtn) wipeBtn.disabled = !canBA;
  if (swapBtn) swapBtn.disabled = !canBA;
  if (!canBA) {
    if (inspectViewMode !== 'single') {
      inspectViewMode = 'single';
      ['single', 'side', 'wipe'].forEach(m => {
        const b = document.getElementById(`vm-${m}`);
        if (b) b.classList.toggle('active', m === 'single');
      });
      const wipeCtrl = document.getElementById('insp-wipe-ctrl');
      if (wipeCtrl) wipeCtrl.style.display = 'none';
    }
    if (inspectQuickBefore) {
      inspectQuickBefore = false;
      if (swapBtn) swapBtn.classList.remove('active');
    }
  }
}

function updateInspectBadges() {
  const n = inspectItems.length;
  const tabCnt = document.getElementById('insp-tab-count');
  const qStat = document.getElementById('q-insp-status');
  const qPurge = document.getElementById('q-purge-insp-btn');
  const stripPurge = document.getElementById('insp-purge-btn');
  const stripSum = document.getElementById('insp-strip-summary');
  if (tabCnt) tabCnt.innerText = `(${n})`;
  if (qStat) qStat.innerText = `Inspect: ${n} item(s)`;
  if (qPurge) qPurge.disabled = n === 0;
  if (stripPurge) stripPurge.disabled = n === 0;
  if (stripSum) stripSum.innerText = `${n} photo(s) loaded`;
}

function syncInspectCollectionWithBatches() {
  if (inspectItems.length === 0) {
    updateInspectBadges();
    return;
  }
  const next = [];
  for (const item of inspectItems) {
    if (item.isStandalone) {
      next.push(item);
      continue;
    }
    const b = allBatches.find(x => x.batchId === item.batchId);
    if (!b) continue;
    const f = b.files.find(x => x.fileId === item.fileId);
    if (!f) continue;
    const prevDone = item.hasExport;
    const prevRev = item.exportRev || 0;
    item.name = inspectName(f);
    item.dims = f.dims;
    item.status = f.status;
    item.hasStego = f.hasStego;
    item.hasExport = !!f.hasExport || f.status === 'DONE';
    item.exportRev = f.exportRev || 0;
    item.psnr = f.psnr || 0;
    item.shift = f.shift || 0;
    item.thumb = f.thumb;
    if (((!prevDone && item.hasExport) || (prevRev !== item.exportRev)) && inspectCache[item.key]) {
      delete inspectCache[item.key];
    }
    next.push(item);
  }
  inspectItems = next;
  if (activeInspectIdx >= inspectItems.length) {
    activeInspectIdx = Math.max(0, inspectItems.length - 1);
  }
  updateInspectBadges();
}

// Inspect shows the protected export under its own name and format once it exists, not the original upload's.
function inspectName(f) {
  return f.hasExport && f.outName ? f.outName : f.name;
}

function addFileObjToInspect(batchId, f) {
  if (!f || !f.valid) return;
  const key = `${batchId}::${f.fileId}`;
  const existingIdx = inspectItems.findIndex(x => x.key === key);
  const entry = {
    key,
    isStandalone: false,
    batchId,
    fileId: f.fileId,
    name: inspectName(f),
    dims: f.dims,
    status: f.status,
    hasStego: f.hasStego,
    hasExport: !!f.hasExport || f.status === 'DONE',
    exportRev: f.exportRev || 0,
    psnr: f.psnr || 0,
    shift: f.shift || 0,
    thumb: f.thumb
  };
  if (existingIdx >= 0) {
    inspectItems[existingIdx] = entry;
    activeInspectIdx = existingIdx;
  } else {
    inspectItems.push(entry);
    activeInspectIdx = inspectItems.length - 1;
  }
}

async function ingestStandaloneInspectFiles(fileList) {
  const files = [...fileList].filter(Boolean);
  if (!files.length) return;
  // Show the spinner the moment photos are dropped; decoding large files takes a while.
  switchTab('insp');
  const loaderEl = document.getElementById('insp-stage-loader');
  const loaderText = loaderEl.querySelector('span');
  loaderText.innerText = `Reading ${files.length} photo${files.length === 1 ? '' : 's'}...`;
  loaderEl.classList.add('active');
  await new Promise(requestAnimationFrame);
  let added = 0;
  for (const f of files) {
    try {
      const objUrl = URL.createObjectURL(f);
      const img = await loadImgPromise(objUrl);
      const nw = img.naturalWidth || img.width;
      const nh = img.naturalHeight || img.height;
      const thumbUrl = imgToCanvas(img, 140).toDataURL('image/jpeg', 0.8);
      const key = `STANDALONE::${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
      const entry = {
        key,
        isStandalone: true,
        standaloneUrl: objUrl,
        batchId: 'EXTERNAL IMPORT',
        fileId: key,
        name: f.name || 'Imported Image',
        dims: `${nw}x${nh}`,
        status: 'EXTERNAL',
        hasStego: false,
        hasExport: true,
        psnr: 0,
        shift: 0,
        thumb: thumbUrl
      };
      // The stego read uploads the whole file, so it runs after the photo is already on screen.
      entry.standaloneStego = api(`/api/check_stego_raw?name=${encodeURIComponent(f.name)}`, { method: 'POST', body: f })
        .then(r => r.json())
        .catch(() => ({ found: false, method: 'None', message: '' }))
        .then(res => {
          entry.hasStego = !!res.found;
          entry.status = res.found ? 'EXTERNAL (STEGO)' : 'EXTERNAL';
          updateInspectBadges();
          return res;
        });
      inspectItems.push(entry);
      activeInspectIdx = inspectItems.length - 1;
      added++;
    } catch (err) {
      showBanner(`<strong>&#9650; Inspect Import Error:</strong> Could not decode ${escapeHtml(f.name)}.`, true);
    }
  }
  loaderText.innerText = 'Decoding image planes...';
  if (!added) loaderEl.classList.remove('active');
  lastBatchesSig = '';
  updateInspectBadges();
  renderInspectModule();
}

function revokeStandaloneUrls(items) {
  (items || []).forEach(it => {
    if (it && it.isStandalone && it.standaloneUrl) {
      try { URL.revokeObjectURL(it.standaloneUrl); } catch (e) {}
    }
  });
}

function sendFileToInspect(e, batchId, fileId, purgeFirst = false) {
  if (e) e.stopPropagation();
  const b = allBatches.find(x => x.batchId === batchId);
  if (!b) return;
  const f = b.files.find(x => x.fileId === fileId);
  if (!f) return;
  if (purgeFirst) {
    revokeStandaloneUrls(inspectItems);
    inspectItems = [];
  }
  addFileObjToInspect(batchId, f);
  lastBatchesSig = '';
  updateInspectBadges();
  switchTab('insp');
}

function sendBatchToInspect(e, batchId, purgeFirst = false) {
  if (e) e.stopPropagation();
  const b = allBatches.find(x => x.batchId === batchId);
  if (!b) return;
  if (purgeFirst) {
    revokeStandaloneUrls(inspectItems);
    inspectItems = [];
  }
  b.files.forEach(f => addFileObjToInspect(batchId, f));
  if (inspectItems.length > 0) activeInspectIdx = 0;
  lastBatchesSig = '';
  updateInspectBadges();
  switchTab('insp');
}

function purgeInspectCollection() {
  revokeStandaloneUrls(inspectItems);
  inspectItems = [];
  activeInspectIdx = 0;
  inspectStegoOverlay = null;
  inspectMarkImg = null;
  lastBatchesSig = '';
  updateInspectBadges();
  renderInspectModule();
}

// The Purge buttons need a second click within 3s; "Purge & Inspect" calls purgeInspectCollection() directly.
function confirmPurgeInspect(btn) {
  if (btn.dataset.armed) {
    clearTimeout(btn._disarmTimer);
    btn._disarm();
    purgeInspectCollection();
    return;
  }
  btn.dataset.armed = '1';
  btn.dataset.label = btn.textContent;
  btn.textContent = `Click again to purge ${inspectItems.length} photo(s)`;
  btn._disarm = () => { delete btn.dataset.armed; btn.textContent = btn.dataset.label; };
  btn._disarmTimer = setTimeout(btn._disarm, 3000);
}

// Inspect multi-select (item keys) and the three-press remove: × shows 2, then 1, then the photo(s) leave
// Inspect (files on disk are untouched). Pausing for INSP_DEL_RESET_MS starts the count over.
const inspSel = new Set();
let inspSelAnchor = -1;
let inspDel = null; // { keys: [...], n: 2|1, timer }
const INSP_DEL_RESET_MS = 2500;

function inspectTargets(idx) {
  const it = inspectItems[idx];
  if (!it) return [];
  return inspSel.has(it.key) ? inspectItems.filter(x => inspSel.has(x.key)).map(x => x.key) : [it.key];
}

function pressInspectDelete(keys) {
  if (!keys.length) return;
  const same = inspDel && inspDel.keys.length === keys.length && inspDel.keys.every(k => keys.includes(k));
  if (inspDel) clearTimeout(inspDel.timer);
  if (same && inspDel.n === 1) {
    inspDel = null;
    removeInspectItems(keys);
    return;
  }
  inspDel = { keys, n: same ? inspDel.n - 1 : 2 };
  inspDel.timer = setTimeout(() => { inspDel = null; paintInspectDelCounts(); }, INSP_DEL_RESET_MS);
  paintInspectDelCounts();
}

// Only the × badges change while counting, so skip the full Inspect re-render.
function paintInspectDelCounts() {
  document.querySelectorAll('#insp-filmstrip .insp-thumb-del').forEach(el => {
    const n = inspDel && inspDel.keys.includes(el.dataset.key) ? inspDel.n : 0;
    el.textContent = n ? String(n) : '×';
    el.classList.toggle('counting', !!n);
  });
}

function removeInspectItem(e, idx) {
  if (e) e.stopPropagation();
  pressInspectDelete(inspectTargets(idx));
}

function removeInspectItems(keys) {
  const activeKey = inspectItems[activeInspectIdx] && inspectItems[activeInspectIdx].key;
  revokeStandaloneUrls(inspectItems.filter(x => keys.includes(x.key)));
  inspectItems = inspectItems.filter(x => !keys.includes(x.key));
  keys.forEach(k => inspSel.delete(k));
  const keep = inspectItems.findIndex(x => x.key === activeKey);
  activeInspectIdx = keep >= 0 ? keep : Math.min(activeInspectIdx, Math.max(0, inspectItems.length - 1));
  inspSelAnchor = -1;
  inspectStegoOverlay = null;
  inspectMarkImg = null;
  lastBatchesSig = '';
  updateInspectBadges();
  renderInspectModule();
}

// Plain click views a photo and clears the selection; Ctrl/Cmd toggles one, Shift selects a range.
function onInspectThumbClick(e, idx) {
  const it = inspectItems[idx];
  if (!it) return;
  if (e.shiftKey) {
    const from = inspSelAnchor >= 0 ? inspSelAnchor : activeInspectIdx;
    const [a, z] = [from, idx].sort((p, q) => p - q);
    if (!(e.ctrlKey || e.metaKey)) inspSel.clear();
    inspectItems.slice(a, z + 1).forEach(x => inspSel.add(x.key));
  } else if (e.ctrlKey || e.metaKey) {
    if (!inspSel.size && inspectItems[activeInspectIdx]) inspSel.add(inspectItems[activeInspectIdx].key);
    if (inspSel.has(it.key)) inspSel.delete(it.key); else inspSel.add(it.key);
    inspSelAnchor = idx;
  } else {
    inspSel.clear();
    inspSelAnchor = idx;
  }
  selectInspectItem(idx);
}

function selectInspectItem(idx) {
  if (idx < 0 || idx >= inspectItems.length) return;
  activeInspectIdx = idx;
  if (inspectLens === 'fa') setInspectLens('normal');
  inspectStegoOverlay = null;
  inspectMarkImg = null;
  renderInspectModule();
}

function loadImgPromise(url) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = reject;
    img.src = url;
  });
}

function imgToCanvas(img, maxDim = 2560) {
  const nw = img.naturalWidth || img.width;
  const nh = img.naturalHeight || img.height;
  const scale = Math.min(1.0, maxDim / Math.max(nw, nh, 1));
  const c = document.createElement('canvas');
  c.width = Math.max(1, Math.round(nw * scale));
  c.height = Math.max(1, Math.round(nh * scale));
  const ctx = c.getContext('2d');
  ctx.imageSmoothingEnabled = true;
  ctx.drawImage(img, 0, 0, c.width, c.height);
  return c;
}

const inspectCacheOrder = [];

async function ensureInspectPairLoaded(item) {
  if (!item) return null;
  const cached = inspectCache[item.key];
  if (cached && cached.loaded && cached.hasExport === item.hasExport && cached.exportRev === (item.exportRev || 0)) {
    return cached;
  }
  if (cached && cached.loadingPromise) {
    return cached.loadingPromise;
  }
  while (inspectCacheOrder.length >= 6) {
    const oldestKey = inspectCacheOrder.shift();
    if (oldestKey && oldestKey !== item.key) delete inspectCache[oldestKey];
  }
  if (!inspectCacheOrder.includes(item.key)) inspectCacheOrder.push(item.key);
  const entry = { loaded: false, hasExport: item.hasExport, exportRev: item.exportRev || 0, lensCanvases: {}, lensOrder: [] };
  inspectCache[item.key] = entry;
  const loaderEl = document.getElementById('insp-stage-loader');
  if (loaderEl) loaderEl.classList.add('active');
  entry.loadingPromise = (async () => {
    try {
      let beforeImg, afterImg;
      if (item.isStandalone && item.standaloneUrl) {
        beforeImg = await loadImgPromise(item.standaloneUrl);
        afterImg = beforeImg;
      } else {
        const baseUrl = apiUrl(`/api/preview_image?batch=${encodeURIComponent(item.batchId)}&file=${encodeURIComponent(item.fileId)}`);
        beforeImg = await loadImgPromise(baseUrl + '&export=0');
        afterImg = item.hasExport
          ? await loadImgPromise(`${baseUrl}&export=1&rev=${item.exportRev || 0}`).catch(() => beforeImg)
          : beforeImg;
      }

      entry.origW = beforeImg.naturalWidth || beforeImg.width;
      entry.origH = beforeImg.naturalHeight || beforeImg.height;
      entry.beforeImg = beforeImg;
      entry.afterImg = afterImg;
      entry.beforeCanvas = imgToCanvas(beforeImg, 2560);
      entry.afterCanvas = imgToCanvas(afterImg, 2560);
      entry.w = entry.beforeCanvas.width;
      entry.h = entry.beforeCanvas.height;
      entry.beforeData = entry.beforeCanvas.getContext('2d').getImageData(0, 0, entry.w, entry.h);
      entry.afterData = entry.afterCanvas.getContext('2d').getImageData(0, 0, entry.w, entry.h);
      entry.loaded = true;
      entry.loadingPromise = null;
      if (loaderEl) loaderEl.classList.remove('active');
      syncInspectViewButtons(item, entry);
      runInspectStegoScan();
      updateLiveLsbHexStream(entry);
      renderInspectStage();
      renderInspectHistogram();
      return entry;
    } catch (err) {
      if (loaderEl) loaderEl.classList.remove('active');
      delete inspectCache[item.key];
      return null;
    }
  })();
  return entry.loadingPromise;
}

let inspectMarkImg = null;

function markLensCanvas(entry, isBefore) {
  const key = `mark::${isBefore ? 'B' : 'A'}::${stegoInvert ? 1 : 0}`;
  if (entry[key] && entry[key]._src === inspectMarkImg) return entry[key];
  const c = document.createElement('canvas');
  c.width = entry.w;
  c.height = entry.h;
  const ctx = c.getContext('2d');
  ctx.fillStyle = stegoInvert ? '#fff' : '#000';
  ctx.fillRect(0, 0, c.width, c.height);
  if (!isBefore && inspectMarkImg) {
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = 'high';
    ctx.drawImage(inspectMarkImg, 0, 0, c.width, c.height);
    if (stegoInvert) {
      const id = ctx.getImageData(0, 0, c.width, c.height);
      const d = id.data;
      for (let i = 0; i < d.length; i += 4) {
        d[i] ^= 255; d[i + 1] ^= 255; d[i + 2] ^= 255;
      }
      ctx.putImageData(id, 0, 0);
    }
  }
  c._src = inspectMarkImg;
  entry[key] = c;
  return c;
}

// Bit-level views need the file's real pixels: the display copy of photos over 2560px is resampled, which scrambles
// the low bits (and hides the bit-0 mark). Reads the original at full size, cropped to cw x ch when given.
function nativePixels(entry, isBefore, cw, ch) {
  const img = isBefore ? entry.beforeImg : entry.afterImg;
  const c = document.createElement('canvas');
  c.width = cw || entry.origW;
  c.height = ch || entry.origH;
  const ctx = c.getContext('2d', { willReadFrequently: true });
  ctx.drawImage(img, 0, 0);
  return ctx.getImageData(0, 0, c.width, c.height);
}

// Real pixels picked (nearest, never blended) onto the display grid, so every bit shown is a bit from the file.
function bitSource(entry, isBefore) {
  const k = isBefore ? 'bitSrcB' : 'bitSrcA';
  if (entry[k]) return entry[k];
  const nat = nativePixels(entry, isBefore);
  const NW = nat.width, NH = nat.height, w = entry.w, h = entry.h, nd = nat.data;
  const out = new Uint8ClampedArray(w * h * 4);
  for (let y = 0; y < h; y++) {
    const row = Math.min(NH - 1, Math.floor(y * NH / h)) * NW;
    for (let x = 0; x < w; x++) {
      const si = (row + Math.min(NW - 1, Math.floor(x * NW / w))) * 4, di = (y * w + x) * 4;
      out[di] = nd[si]; out[di + 1] = nd[si + 1]; out[di + 2] = nd[si + 2]; out[di + 3] = nd[si + 3];
    }
  }
  return (entry[k] = out);
}

function lensCacheKey(isBefore) {
  return `${isBefore ? 'B' : 'A'}::${inspectLens}::${inspectGain}::${inspectElaQ}::${inspectNoiseFloor}::${stegoChannel}::${stegoBitPlane}::${stegoInvert ? 1 : 0}::${stegoLut ? 1 : 0}`;
}

// True when drawing this photo means computing a lens from scratch (hundreds of ms on big photos).
function lensNeedsCompute(entry) {
  if (inspectLens === 'mark' || inspectLens === 'fa') return false;
  if (inspectLens === 'normal' && stegoChannel === 'rgb' && stegoBitPlane === -1 && !stegoInvert && !stegoLut) return false;
  // Bit planes take a few ms once the file's pixels are read, so they draw at once (no spinner flash while sliding).
  const quickBits = (inspectLens === 'stego_plane' || inspectLens === 'normal') && stegoBitPlane >= 0 && stegoChannel !== 'luma';
  if (quickBits && (entry.origW <= entry.w || (entry.bitSrcA && entry.bitSrcB))) return false;
  return !entry.lensCanvases[lensCacheKey(true)] || !entry.lensCanvases[lensCacheKey(false)];
}

// Show the spinner over the current picture, compute the lens two frames later (after the spinner is painted), then draw.
let lensComputeToken = 0;
let lensComputePending = false;
function hideLensComputeLoader() {
  if (!lensComputePending) return;
  lensComputePending = false;
  const loaderEl = document.getElementById('insp-stage-loader');
  loaderEl.classList.remove('active');
  loaderEl.querySelector('span').innerText = 'Decoding image planes...';
}

function deferLensCompute(entry) {
  const tok = ++lensComputeToken;
  lensComputePending = true;
  const loaderEl = document.getElementById('insp-stage-loader');
  loaderEl.querySelector('span').innerText = 'Computing view...';
  loaderEl.classList.add('active');
  requestAnimationFrame(() => requestAnimationFrame(() => {
    if (tok !== lensComputeToken) return;
    try {
      getLensCanvas(entry, true);
      getLensCanvas(entry, false);
    } finally {
      hideLensComputeLoader();
    }
    renderInspectStage();
  }));
}

function getLensCanvas(entry, isBefore) {
  if (inspectLens === 'mark') return markLensCanvas(entry, isBefore);
  if (inspectLens === 'fa') return faLensCanvas(entry);
  if (inspectLens === 'normal' && stegoChannel === 'rgb' && stegoBitPlane === -1 && !stegoInvert && !stegoLut) {
    return (isBefore ? entry.beforeImg : entry.afterImg) || (isBefore ? entry.beforeCanvas : entry.afterCanvas);
  }

  const cacheKey = lensCacheKey(isBefore);
  if (entry.lensCanvases[cacheKey]) return entry.lensCanvases[cacheKey];
  if (entry.lensOrder) {
    while (entry.lensOrder.length >= 6) {
      const oldK = entry.lensOrder.shift();
      delete entry.lensCanvases[oldK];
    }
    entry.lensOrder.push(cacheKey);
  }

  const w = entry.w, h = entry.h;
  const bitLevel = inspectLens === 'lsb' || ((inspectLens === 'stego_plane' || inspectLens === 'normal') && stegoBitPlane >= 0);
  const src = bitLevel && entry.origW > w ? bitSource(entry, isBefore) : (isBefore ? entry.beforeData : entry.afterData).data;
  const ref = entry.beforeData.data;
  const outC = document.createElement('canvas');
  outC.width = w;
  outC.height = h;
  const ctx = outC.getContext('2d');
  const outImg = ctx.createImageData(w, h);
  const dst = outImg.data;
  const n = w * h * 4;
  const floor = inspectNoiseFloor;

  if (inspectLens === 'lsb') {
    for (let i = 0; i < n; i += 4) {
      dst[i]     = (src[i] & 3) * 85;
      dst[i + 1] = (src[i + 1] & 3) * 85;
      dst[i + 2] = (src[i + 2] & 3) * 85;
      dst[i + 3] = 255;
    }
  } else if (inspectLens === 'stego_plane' || (inspectLens === 'normal' && (stegoChannel !== 'rgb' || stegoBitPlane !== -1 || stegoInvert || stegoLut))) {
    const bp = stegoBitPlane;
    if (bp >= 0 && stegoChannel !== 'luma') {
      // One 32-bit word per pixel (RGBA, little-endian): pull the bit out of every channel at once, ~10x faster.
      const s32 = new Uint32Array(src.buffer, src.byteOffset, n >> 2);
      const d32 = new Uint32Array(dst.buffer, dst.byteOffset, n >> 2);
      if (stegoChannel === 'rgb') {
        for (let i = 0; i < s32.length; i++) d32[i] = (((s32[i] >>> bp) & 0x010101) * 255) | 0xFF000000;
      } else {
        const sh = { r: 0, g: 8, b: 16, a: 24 }[stegoChannel] + bp;
        for (let i = 0; i < s32.length; i++) d32[i] = (((s32[i] >>> sh) & 1) * 0xFFFFFF) | 0xFF000000;
      }
    } else for (let i = 0; i < n; i += 4) {
      let r = src[i], g = src[i + 1], b = src[i + 2], a = src[i + 3];
      if (stegoChannel === 'r') { g = r; b = r; }
      else if (stegoChannel === 'g') { r = g; b = g; }
      else if (stegoChannel === 'b') { r = b; g = b; }
      else if (stegoChannel === 'a') { r = a; g = a; b = a; }
      else if (stegoChannel === 'luma') {
        const lum = Math.min(255, Math.round(0.299 * r + 0.587 * g + 0.114 * b));
        r = lum; g = lum; b = lum;
      }
      if (bp >= 0 && bp <= 7) {
        if (stegoChannel === 'rgb') {
          r = ((src[i] >> bp) & 1) * 255;
          g = ((src[i + 1] >> bp) & 1) * 255;
          b = ((src[i + 2] >> bp) & 1) * 255;
        } else {
          const bit = ((r >> bp) & 1) * 255;
          r = bit; g = bit; b = bit;
        }
      }
      dst[i] = r; dst[i + 1] = g; dst[i + 2] = b; dst[i + 3] = 255;
    }
  } else if (inspectLens === 'diff') {
    for (let i = 0; i < n; i += 4) {
      const dr = Math.max(0, Math.abs(entry.afterData.data[i] - ref[i]) - floor);
      const dg = Math.max(0, Math.abs(entry.afterData.data[i + 1] - ref[i + 1]) - floor);
      const db = Math.max(0, Math.abs(entry.afterData.data[i + 2] - ref[i + 2]) - floor);
      dst[i]     = Math.min(255, dr * inspectGain);
      dst[i + 1] = Math.min(255, dg * inspectGain);
      dst[i + 2] = Math.min(255, db * inspectGain);
      dst[i + 3] = 255;
    }
  } else if (inspectLens === 'fft') {
    const mult = Math.max(1, Math.floor(inspectGain / 3));
    for (let y = 1; y < h - 1; y++) {
      for (let x = 1; x < w - 1; x++) {
        const idx = (y * w + x) * 4;
        for (let c = 0; c < 3; c++) {
          const center = src[idx + c] * 4;
          const lap = Math.max(0, Math.abs(center - src[idx - 4 + c] - src[idx + 4 + c] - src[idx - w * 4 + c] - src[idx + w * 4 + c]) - floor);
          dst[idx + c] = Math.min(255, lap * mult);
        }
        dst[idx + 3] = 255;
      }
    }
  } else if (inspectLens === 'ela') {
    const qStep = Math.max(1, Math.round((100 - inspectElaQ) * 0.6));
    const mult = Math.max(1, Math.floor(inspectGain / 2));
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        const idx = (y * w + x) * 4;
        const bx = (x & ~7) + 4 < w ? (x & ~7) + 4 : x;
        const by = (y & ~7) + 4 < h ? (y & ~7) + 4 : y;
        const bIdx = (by * w + bx) * 4;
        for (let c = 0; c < 3; c++) {
          const quant = Math.round(src[idx + c] / qStep) * qStep;
          const blk = Math.abs(src[idx + c] - src[bIdx + c]) * 0.35 + Math.abs(src[idx + c] - quant);
          dst[idx + c] = Math.min(255, Math.max(0, blk - floor) * mult);
        }
        dst[idx + 3] = 255;
      }
    }
  } else if (inspectLens === 'sobel') {
    const gainScale = Math.max(0.5, inspectGain / 10.0);
    for (let y = 1; y < h - 1; y++) {
      for (let x = 1; x < w - 1; x++) {
        const idx = (y * w + x) * 4;
        const lL = src[idx - 4] * 0.3 + src[idx - 3] * 0.59 + src[idx - 2] * 0.11;
        const lR = src[idx + 4] * 0.3 + src[idx + 5] * 0.59 + src[idx + 6] * 0.11;
        const lU = src[idx - w * 4] * 0.3 + src[idx - w * 4 + 1] * 0.59 + src[idx - w * 4 + 2] * 0.11;
        const lD = src[idx + w * 4] * 0.3 + src[idx + w * 4 + 1] * 0.59 + src[idx + w * 4 + 2] * 0.11;
        const mag = Math.min(255, Math.max(0, Math.hypot(lR - lL, lD - lU) - floor) * gainScale);
        dst[idx] = mag * 0.35;
        dst[idx + 1] = mag * 0.75;
        dst[idx + 2] = mag;
        dst[idx + 3] = 255;
      }
    }
  } else if (inspectLens === 'srm') {
    const mult = Math.max(1, Math.floor(inspectGain / 2));
    for (let y = 1; y < h - 1; y++) {
      for (let x = 1; x < w - 1; x++) {
        const idx = (y * w + x) * 4;
        for (let c = 0; c < 3; c++) {
          const hRes = Math.abs(2 * src[idx + c] - src[idx - 4 + c] - src[idx + 4 + c]);
          const vRes = Math.abs(2 * src[idx + c] - src[idx - w * 4 + c] - src[idx + w * 4 + c]);
          const rVal = Math.max(0, (hRes + vRes) * 0.5 - floor);
          dst[idx + c] = Math.min(255, rVal * mult);
        }
        dst[idx + 3] = 255;
      }
    }
  } else if (inspectLens === 'luma_map') {
    for (let i = 0; i < n; i += 4) {
      const lum = Math.min(255, Math.round(0.299 * src[i] + 0.587 * src[i + 1] + 0.114 * src[i + 2]));
      if (lum <= 2) {
        dst[i] = 15; dst[i + 1] = 98; dst[i + 2] = 254;
      } else if (lum >= 253) {
        dst[i] = 250; dst[i + 1] = 77; dst[i + 2] = 86;
      } else {
        dst[i] = lum; dst[i + 1] = lum; dst[i + 2] = lum;
      }
      dst[i + 3] = 255;
    }
  } else if (inspectLens === 'chroma') {
    const gainScale = Math.max(1.0, inspectGain / 8.0);
    for (let i = 0; i < n; i += 4) {
      const r = src[i], g = src[i + 1], b = src[i + 2];
      const y = 0.299 * r + 0.587 * g + 0.114 * b;
      const cb = Math.min(255, Math.max(0, 128 + (b - y) * gainScale));
      const cr = Math.min(255, Math.max(0, 128 + (r - y) * gainScale));
      dst[i] = cr;
      dst[i + 1] = Math.min(255, Math.abs(cr - 128) + Math.abs(cb - 128));
      dst[i + 2] = cb;
      dst[i + 3] = 255;
    }
  }

  if (stegoLut) {
    for (let i = 0; i < n; i += 4) {
      const idxLut = ((dst[i] & 1) << 2) | ((dst[i + 1] & 1) << 1) | (dst[i + 2] & 1);
      const c = STEGO_RANDOM_LUT[idxLut];
      dst[i] = c[0]; dst[i + 1] = c[1]; dst[i + 2] = c[2];
    }
  }
  if (stegoInvert) {
    for (let i = 0; i < n; i += 4) {
      dst[i] ^= 255; dst[i + 1] ^= 255; dst[i + 2] ^= 255;
    }
  }

  ctx.putImageData(outImg, 0, 0);
  entry.lensCanvases[cacheKey] = outC;
  return outC;
}

function getFitScale(entry, viewW, viewH) {
  return Math.min((viewW - 24) / Math.max(1, entry.w), (viewH - 24) / Math.max(1, entry.h));
}

function getEffectiveScale(entry, viewW, viewH) {
  const fitScale = getFitScale(entry, viewW, viewH);
  return inspectZoom === 'FIT' ? fitScale : inspectZoom;
}

// Target center that keeps image point (u, v) at offset (x, y) px from the pane centre once zoom reaches `scale`.
// The stage size the renderer draws with; zoom maths must use the same numbers or anchored points drift.
function inspectStageSize(stage) {
  return { w: stage._cssW || stage.clientWidth, h: stage._cssH || stage.clientHeight };
}

// Zoom for a click: the remembered zoom, but always clearly deeper than Fit.
function inspectClickZoomFor(entry) {
  const size = inspectStageSize(document.getElementById('insp-stage'));
  const paneW = inspectViewMode === 'side' ? size.w * 0.5 : size.w;
  return Math.min(16, Math.max(inspectClickZoom, getFitScale(entry, paneW, size.h) * 1.5));
}

function anchoredTarget(entry, u, v, x, y, scale) {
  const clamp01 = n => Math.max(0, Math.min(1, n));
  return {
    u: clamp01(u - x / Math.max(1, entry.w * scale)),
    v: clamp01(v - y / Math.max(1, entry.h * scale)),
    anchor: { u, v, x, y }
  };
}

function requestInspectSmoothAnim() {
  if (inspectAnimRaf) return;
  const step = () => {
    const item = inspectItems[activeInspectIdx];
    const entry = item ? inspectCache[item.key] : null;
    const stage = document.getElementById('insp-stage');
    if (!entry || !entry.loaded || !stage) {
      inspectAnimRaf = null;
      return;
    }
    const size = inspectStageSize(stage);
    const paneW = inspectViewMode === 'side' ? size.w * 0.5 : size.w;
    const fitS = getFitScale(entry, paneW, size.h);
    const curZ = inspectZoom === 'FIT' ? fitS : inspectZoom;
    const tgtZ = inspectTargetZoom === 'FIT' ? fitS : inspectTargetZoom;

    const logDz = Math.log(tgtZ / curZ);
    const du = inspectTargetCenter.u - inspectCenter.u;
    const dv = inspectTargetCenter.v - inspectCenter.v;

    if (Math.abs(logDz) < 0.002 && Math.abs(du) < 0.0008 && Math.abs(dv) < 0.0008) {
      inspectZoom = inspectTargetZoom;
      inspectCenter.u = inspectTargetCenter.u;
      inspectCenter.v = inspectTargetCenter.v;
      // Drop the anchor: a later zoom that keeps this center (a preset) must find its own fixed point.
      inspectTargetCenter = { u: inspectTargetCenter.u, v: inspectTargetCenter.v };
      inspectAnimRaf = null;
      // Remember a real zoom-in (not one that is barely above Fit) for the next click.
      if (inspectZoom !== 'FIT' && inspectZoom > fitS * 1.25) {
        inspectClickZoom = inspectZoom;
        try { localStorage.setItem(INSPECT_ZOOM_STORE_KEY, String(inspectClickZoom)); } catch (e) {}
      }
      renderInspectStage();
      return;
    }

    // A zoom with a center change has one screen point that stays still: scale about it so the picture never
    // slides while it grows or shrinks. Pure pans (no zoom change) keep the plain glide.
    if (!inspectTargetCenter.anchor && Math.abs(logDz) > 0.01) {
      const fixedU = (inspectCenter.u * curZ - inspectTargetCenter.u * tgtZ) / (curZ - tgtZ);
      const fixedV = (inspectCenter.v * curZ - inspectTargetCenter.v * tgtZ) / (curZ - tgtZ);
      inspectTargetCenter.anchor = {
        u: fixedU,
        v: fixedV,
        x: (fixedU - inspectTargetCenter.u) * entry.w * tgtZ,
        y: (fixedV - inspectTargetCenter.v) * entry.h * tgtZ
      };
    }

    // Zoom moves evenly in log scale, so 0.3 -> 2 does not jump at the start and crawl at the end.
    const alpha = 0.28;
    inspectZoom = curZ * Math.exp(logDz * alpha);
    const anchor = inspectTargetCenter.anchor;
    if (anchor) {
      const pinned = anchoredTarget(entry, anchor.u, anchor.v, anchor.x, anchor.y, inspectZoom);
      inspectCenter.u = pinned.u;
      inspectCenter.v = pinned.v;
    } else {
      inspectCenter.u = inspectCenter.u + du * alpha;
      inspectCenter.v = inspectCenter.v + dv * alpha;
    }
    renderInspectStage();
    inspectAnimRaf = requestAnimationFrame(step);
  };
  inspectAnimRaf = requestAnimationFrame(step);
}

function drawViewportSlice(ctx, sourceDrawable, entry, vx, vy, vw, vh, badgeText, clipX = vx, clipY = vy, clipW = vw, clipH = vh) {
  ctx.save();
  ctx.beginPath();
  ctx.rect(clipX, clipY, clipW, clipH);
  ctx.clip();

  const scale = getEffectiveScale(entry, vw, vh);
  ctx.imageSmoothingEnabled = scale < 2.0;
  const drawW = entry.w * scale;
  const drawH = entry.h * scale;
  const dx = vx + vw * 0.5 - inspectCenter.u * drawW;
  const dy = vy + vh * 0.5 - inspectCenter.v * drawH;

  ctx.drawImage(sourceDrawable, dx, dy, drawW, drawH);

  if (badgeText) {
    ctx.font = '600 11px ' + uiFontStack();
    const tw = ctx.measureText(badgeText).width + 14;
    ctx.fillStyle = 'rgba(15, 15, 15, 0.84)';
    ctx.fillRect(clipX + 10, clipY + 10, tw, 22);
    ctx.strokeStyle = '#525252';
    ctx.strokeRect(clipX + 10, clipY + 10, tw, 22);
    ctx.fillStyle = '#f3d689';
    ctx.fillText(badgeText, clipX + 17, clipY + 25);
  }
  if (!badgeText.toLowerCase().startsWith('before') && inspectStegoOverlay) {
    const sx = entry.w / Math.max(1, entry.origW || entry.w);
    const sy = entry.h / Math.max(1, entry.origH || entry.h);
    const drawNonOverlappingBox = (bbox, strokeColor, labelText) => {
      if (!bbox) return;
      const bx = dx + (bbox.x || 0) * sx * scale;
      const by = dy + (bbox.y || 0) * sy * scale;
      const bw = Math.max(16, (bbox.w || 32) * sx * scale);
      const bh = Math.max(10, (bbox.h || 8) * sy * scale);
      ctx.strokeStyle = strokeColor;
      ctx.lineWidth = 1.5;
      ctx.setLineDash([4, 3]);
      ctx.strokeRect(bx, by, bw, bh);
      ctx.setLineDash([]);
      if (labelText) {
        ctx.font = '600 10px ' + uiFontStack();
        const ltw = ctx.measureText(labelText).width + 10;
        const lby = by >= clipY + 38 ? by - 20 : by + bh + 4;
        ctx.fillStyle = 'rgba(14, 14, 14, 0.9)';
        ctx.fillRect(bx, lby, ltw, 17);
        ctx.strokeStyle = strokeColor;
        ctx.strokeRect(bx, lby, ltw, 17);
        ctx.fillStyle = strokeColor;
        ctx.fillText(labelText, bx + 5, lby + 12);
      }
    };
    if (inspectLens === 'lsb' && inspectStegoOverlay.binaryBBox) {
      drawNonOverlappingBox(inspectStegoOverlay.binaryBBox, '#38bdf8', `LSB STREAM (${inspectStegoOverlay.bitPlane || 'Bit-0/1'})`);
    }
    if (inspectLens === 'mark' && inspectStegoOverlay.markBBox) {
      drawNonOverlappingBox(inspectStegoOverlay.markBBox, '#f3d689', inspectStegoOverlay.markScore != null ? `HIDDEN MARK (${inspectStegoOverlay.markScore}%)` : 'HIDDEN MARK');
    }
  }
  ctx.restore();
}

// Half the visible width/height of the main view, in 0..1 image units.
function inspectViewHalf(entry, mainW, mainH) {
  const paneW = inspectViewMode === 'side' ? mainW * 0.5 : mainW;
  const scale = getEffectiveScale(entry, paneW, mainH);
  return { u: paneW / (entry.w * scale) * 0.5, v: mainH / (entry.h * scale) * 0.5 };
}

// Where the letterboxed picture sits inside the navigator canvas, in page pixels.
function navigatorImageRect(entry) {
  const c = document.getElementById('insp-nav-canvas');
  const r = c.getBoundingClientRect();
  const fit = Math.min(c.width / entry.w, c.height / entry.h);
  const sx = r.width / c.width;
  const sy = r.height / c.height;
  return {
    left: r.left + (c.width - entry.w * fit) * 0.5 * sx,
    top: r.top + (c.height - entry.h * fit) * 0.5 * sy,
    w: entry.w * fit * sx,
    h: entry.h * fit * sy
  };
}

function renderInspectNavigator(entry, mainW, mainH) {
  const navC = document.getElementById('insp-nav-canvas');
  if (!navC) return;
  const nctx = navC.getContext('2d');
  nctx.clearRect(0, 0, navC.width, navC.height);
  const item = inspectItems[activeInspectIdx];
  syncInspectViewButtons(item, entry);
  if (!entry || !entry.loaded) return;

  const fit = Math.min(navC.width / entry.w, navC.height / entry.h);
  const dw = entry.w * fit;
  const dh = entry.h * fit;
  const ox = (navC.width - dw) * 0.5;
  const oy = (navC.height - dh) * 0.5;

  nctx.imageSmoothingEnabled = true;
  const srcC = getLensCanvas(entry, inspectQuickBefore);
  nctx.drawImage(srcC, ox, oy, dw, dh);

  const { u: halfU, v: halfV } = inspectViewHalf(entry, mainW, mainH);
  // Intersect with the image so a pan past its edge shows the area really on screen.
  const u0 = Math.max(0, inspectCenter.u - halfU);
  const v0 = Math.max(0, inspectCenter.v - halfV);
  const u1 = Math.min(1, inspectCenter.u + halfU);
  const v1 = Math.min(1, inspectCenter.v + halfV);

  nctx.strokeStyle = '#f3d689';
  nctx.lineWidth = 1.5;
  nctx.strokeRect(ox + u0 * dw, oy + v0 * dh, Math.max(0, u1 - u0) * dw, Math.max(0, v1 - v0) * dh);
}

function renderInspectStage() {
  const stage = document.getElementById('insp-stage');
  const mainC = document.getElementById('insp-main-canvas');
  const emptyEl = document.getElementById('insp-empty-overlay');
  if (!stage || !mainC) return;

  const dpr = window.devicePixelRatio || 1;
  if (stage._resizeEpoch !== canvasResizeEpoch || !stage._cssW || !stage._cssH) {
    const rect = stage.getBoundingClientRect();
    stage._cachedRect = rect;
    stage._cssW = rect.width > 10 ? Math.floor(rect.width) : 960;
    stage._cssH = rect.height > 10 ? Math.floor(rect.height) : 620;
    stage._resizeEpoch = canvasResizeEpoch;
  }
  const cssW = stage._cssW;
  const cssH = stage._cssH;
  const targetW = Math.round(cssW * dpr);
  const targetH = Math.round(cssH * dpr);
  if (mainC.width !== targetW || mainC.height !== targetH) {
    mainC.width = targetW;
    mainC.height = targetH;
  }
  const pendItem = inspectItems[activeInspectIdx];
  const pendEntry = pendItem && inspectCache[pendItem.key];
  if (pendEntry && pendEntry.loaded && lensNeedsCompute(pendEntry)) {
    deferLensCompute(pendEntry);
    return;
  }
  // A cheaper view replaced a pending lens computation: cancel it and take its spinner down with it.
  lensComputeToken++;
  hideLensComputeLoader();
  const W = cssW, H = cssH;
  const ctx = mainC.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, W, H);

  // Batched darkroom grid background (single draw call, coordinated with theme lookup table)
  const computedStyle = getComputedStyle(document.documentElement);
  ctx.strokeStyle = computedStyle.getPropertyValue('--inspect-grid').trim() || '#1a1a1a';
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (let x = 0; x < W; x += 32) { ctx.moveTo(x, 0); ctx.lineTo(x, H); }
  for (let y = 0; y < H; y += 32) { ctx.moveTo(0, y); ctx.lineTo(W, y); }
  ctx.stroke();

  const item = inspectItems[activeInspectIdx];
  if (!item) {
    emptyEl.style.display = 'flex';
    renderInspectNavigator(null, W, H);
    return;
  }
  emptyEl.style.display = 'none';

  const entry = inspectCache[item.key];
  if (!entry || !entry.loaded) {
    ensureInspectPairLoaded(item);
    return;
  }

  const paneW = inspectViewMode === 'side' ? W * 0.5 : W;
  const effScale = getEffectiveScale(entry, paneW, H);
  const pctText = Math.round(effScale * 100) + '%';
  const activePreset = inspectTargetZoom;
  document.getElementById('insp-zoom-readout').innerText = activePreset === 'FIT' ? `FIT (${pctText})` : `${Number(effScale).toFixed(effScale >= 2 ? 1 : 2)}:1 (${pctText})`;
  stage.classList.toggle('zoomed', activePreset !== 'FIT');

  ['fit', '1', '2', '4', '8'].forEach(k => {
    const b = document.getElementById(`zp-${k}`);
    if (b) b.classList.toggle('active', (k === 'fit' && activePreset === 'FIT') || parseFloat(k) === activePreset);
  });

  const beforeC = getLensCanvas(entry, true);
  const afterC = getLensCanvas(entry, false);
  const afterTag = item.isStandalone
    ? ''
    : (item.hasExport ? 'After (Protected)' : 'After (Unprocessed)');

  if (inspectViewMode === 'single') {
    const showBef = inspectQuickBefore;
    drawViewportSlice(ctx, showBef ? beforeC : afterC, entry, 0, 0, W, H, showBef ? 'Before (Original)' : afterTag);
  } else if (inspectViewMode === 'side') {
    const half = Math.floor(W * 0.5);
    drawViewportSlice(ctx, beforeC, entry, 0, 0, half - 1, H, 'Before (Original)', 0, 0, half - 1, H);
    drawViewportSlice(ctx, afterC, entry, half + 1, 0, W - half - 1, H, afterTag, half + 1, 0, W - half - 1, H);
    ctx.fillStyle = '#0f62fe';
    ctx.fillRect(half - 1, 0, 2, H);
  } else if (inspectViewMode === 'wipe') {
    const splitX = Math.floor(W * inspectWipePct);
    // Sliding Door: both Before and After share the full stage (0, 0, W, H) and are clipped at splitX
    drawViewportSlice(ctx, beforeC, entry, 0, 0, W, H, 'Before (Original)', 0, 0, splitX, H);
    drawViewportSlice(ctx, afterC, entry, 0, 0, W, H, '', splitX, 0, W - splitX, H);

    if (afterTag) {
      ctx.font = '600 11px ' + uiFontStack();
      const tw = ctx.measureText(afterTag).width + 14;
      ctx.fillStyle = 'rgba(15, 15, 15, 0.84)';
      ctx.fillRect(W - tw - 10, 10, tw, 22);
      ctx.strokeStyle = '#525252';
      ctx.strokeRect(W - tw - 10, 10, tw, 22);
      ctx.fillStyle = '#42be65';
      ctx.fillText(afterTag, W - tw - 3, 25);
    }

    ctx.fillStyle = '#f3d689';
    ctx.fillRect(splitX - 1, 0, 2, H);
    ctx.fillStyle = '#141414';
    ctx.strokeStyle = '#f3d689';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.arc(splitX, H * 0.5, 12, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
    ctx.fillStyle = '#f3d689';
    ctx.font = '600 10px ' + uiFontStack();
    ctx.fillText('<>', splitX - 6, H * 0.5 + 3.5);
  }

  renderInspectNavigator(entry, W, H);
}

function renderInspectHistogram() {
  const hc = document.getElementById('insp-hist-canvas');
  if (!hc) return;
  const { ctx, W, H } = ensureHiDPICanvas(hc);
  ctx.clearRect(0, 0, W, H);

  const item = inspectItems[activeInspectIdx];
  const entry = item ? inspectCache[item.key] : null;
  if (!entry || !entry.loaded) {
    document.getElementById('ih-mean').innerText = 'Mean: —';
    document.getElementById('ih-std').innerText = 'Std: —';
    document.getElementById('ih-ent').innerText = 'LSB Chi²: —';
    return;
  }

  const useBef = inspectQuickBefore;
  document.getElementById('insp-hist-mode').innerText = useBef ? 'Before' : 'After';
  const data = (useBef ? entry.beforeData : entry.afterData).data;
  const rBins = new Uint32Array(256);
  const gBins = new Uint32Array(256);
  const bBins = new Uint32Array(256);
  const lBins = new Uint32Array(256);
  const lsbCounts = [0, 0, 0, 0];

  let sum = 0, sumSq = 0, count = 0;
  const step = Math.max(4, Math.floor((data.length / 4) / 25000) * 4);
  for (let i = 0; i < data.length; i += step) {
    const r = data[i], g = data[i + 1], b = data[i + 2];
    const lum = Math.min(255, Math.round(0.299 * r + 0.587 * g + 0.114 * b));
    rBins[r]++; gBins[g]++; bBins[b]++; lBins[lum]++;
    lsbCounts[r & 3]++; lsbCounts[g & 3]++; lsbCounts[b & 3]++;
    sum += lum;
    sumSq += lum * lum;
    count++;
  }

  const mean = sum / Math.max(1, count);
  const std = Math.sqrt(Math.max(0, sumSq / Math.max(1, count) - mean * mean));
  const expected = (count * 3) / 4;
  const chiSq = lsbCounts.reduce((acc, c) => acc + Math.pow(c - expected, 2) / Math.max(1, expected), 0);

  document.getElementById('ih-mean').innerText = `Mean: ${mean.toFixed(1)}`;
  document.getElementById('ih-std').innerText = `Std: ${std.toFixed(1)}`;
  document.getElementById('ih-ent').innerText = `LSB Chi²: ${chiSq.toFixed(1)}`;

  let maxVal = 1;
  for (let i = 1; i < 255; i++) {
    maxVal = Math.max(maxVal, rBins[i], gBins[i], bBins[i], lBins[i]);
  }

  const drawChannel = (bins, color, fillAlpha) => {
    const pts = [];
    for (let i = 0; i < 256; i += 2) {
      const avg = (bins[i] + (bins[i + 1] || bins[i])) * 0.5;
      const x = (i / 255) * W;
      const y = H - Math.min(1, avg / maxVal) * (H - 8);
      pts.push({ x, y });
    }
    ctx.beginPath();
    ctx.moveTo(0, H);
    traceSmoothBezierPath(ctx, pts, false);
    ctx.lineTo(W, H);
    ctx.closePath();
    ctx.fillStyle = color + fillAlpha;
    ctx.fill();
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.25;
    ctx.beginPath();
    traceSmoothBezierPath(ctx, pts, true);
    ctx.stroke();
  };

  drawChannel(rBins, '#fa4d56', '30');
  drawChannel(gBins, '#42be65', '30');
  drawChannel(bBins, '#0f62fe', '35');
  drawChannel(lBins, '#e0e0e0', '22');
}

function updateLiveLsbHexStream(entry) {
  const hexBox = document.getElementById('stego-hex-box');
  if (!hexBox) return;
  if (!entry || !entry.loaded) {
    hexBox.innerText = 'Select an image to inspect live LSB bytes.';
    return;
  }
  // 64 bytes need at most 86 pixels from the top-left corner; read them from the file, not the resampled copy.
  const corner = entry.origW > entry.w ? nativePixels(entry, inspectQuickBefore, Math.min(entry.origW, 96), Math.min(entry.origH, 96)) : null;
  const src = corner ? corner.data : (inspectQuickBefore ? entry.beforeData : entry.afterData).data;
  const w = corner ? corner.width : entry.w, h = corner ? corner.height : entry.h;
  const bytes = [];
  let curByte = 0, bitCount = 0;
  const pushBits = (val2) => {
    for (let b = 1; b >= 0; b--) {
      const bit = (val2 >> b) & 1;
      if (lsbBitMsbFirst) {
        curByte = ((curByte << 1) | bit) & 0xFF;
      } else {
        curByte = (curByte | (bit << bitCount)) & 0xFF;
      }
      bitCount++;
      if (bitCount === 8) {
        bytes.push(curByte);
        curByte = 0;
        bitCount = 0;
      }
    }
  };
  if (lsbScanRowFirst) {
    for (let y = 0; y < h && bytes.length < 64; y++) {
      for (let x = 0; x < w && bytes.length < 64; x++) {
        const i = (y * w + x) * 4;
        pushBits(src[i] & 3);
        if (bytes.length < 64) pushBits(src[i + 1] & 3);
        if (bytes.length < 64) pushBits(src[i + 2] & 3);
      }
    }
  } else {
    for (let x = 0; x < w && bytes.length < 64; x++) {
      for (let y = 0; y < h && bytes.length < 64; y++) {
        const i = (y * w + x) * 4;
        pushBits(src[i] & 3);
        if (bytes.length < 64) pushBits(src[i + 1] & 3);
        if (bytes.length < 64) pushBits(src[i + 2] & 3);
      }
    }
  }
  const hexStr = bytes.slice(0, 48).map(b => b.toString(16).padStart(2, '0').toUpperCase()).join(' ');
  const asciiStr = bytes.slice(0, 48).map(b => (b >= 32 && b <= 126) ? String.fromCharCode(b) : '.').join('');
  hexBox.innerHTML = `<div style="color:var(--gold);margin-bottom:3px;">HEX: ${escapeHtml(hexStr)}</div><div style="color:var(--fg);">ASC: ${escapeHtml(asciiStr)}</div>`;
}

function toggleLsbScanOrder() {
  lsbScanRowFirst = !lsbScanRowFirst;
  const b = document.getElementById('lsb-order-btn');
  if (b) b.innerText = lsbScanRowFirst ? 'Row-First' : 'Col-First';
  const item = inspectItems[activeInspectIdx];
  const entry = item ? inspectCache[item.key] : null;
  updateLiveLsbHexStream(entry);
}

function toggleLsbBitOrder() {
  lsbBitMsbFirst = !lsbBitMsbFirst;
  const b = document.getElementById('lsb-bitend-btn');
  if (b) b.innerText = lsbBitMsbFirst ? 'MSB' : 'LSB';
  const item = inspectItems[activeInspectIdx];
  const entry = item ? inspectCache[item.key] : null;
  updateLiveLsbHexStream(entry);
}

async function runInspectStegoScan() {
  const box = document.getElementById('insp-stego-box');
  if (!box) return;
  const item = inspectItems[activeInspectIdx];
  inspectMarkImg = null;
  inspectStegoOverlay = null;
  if (!item) {
    box.innerHTML = `<div style="color:var(--dim);">Select an image in the filmstrip to inspect.</div>`;
    renderInspectStage();
    return;
  }
  const targetKey = item.key;
  let d;
  if (item.isStandalone && item.standaloneStego) {
    d = await item.standaloneStego;
  } else {
    const r = await api(`/api/check_stego?batch=${encodeURIComponent(item.batchId)}&file=${encodeURIComponent(item.fileId)}`);
    d = await r.json();
  }
  const curItem = inspectItems[activeInspectIdx];
  if (!curItem || curItem.key !== targetKey) return;
  if (d && d.markPng) {
    const img = new Image();
    img.onload = () => {
      const activeNow = inspectItems[activeInspectIdx];
      if (!activeNow || activeNow.key !== targetKey) return;
      inspectMarkImg = img;
      if (inspectLens === 'mark') renderInspectStage();
    };
    img.src = `data:image/png;base64,${d.markPng}`;
  }
  if (d && d.found) {
    const isBinaryOnly = !!(d.binaryFound && !d.markFound);
    inspectStegoOverlay = {
      binaryOnly: isBinaryOnly,
      binaryBBox: d.binaryBBox || null,
      markBBox: d.markBBox || null,
      bitPlane: d.bitPlane || 'LSB Bit-Planes 0 & 1 (RGB)',
      markScore: d.markScore
    };
    box.innerHTML = `
      <div style="color:var(--green);margin-bottom:6px;">&#10004; SIGNATURE VERIFIED (${escapeHtml(d.method || '2-Bit RGB LSB')})</div>
      ${d.message ? `<div class="enclosed-stego-readout">${escapeHtml(d.message)}</div>` : ''}
      ${d.binaryFound ? `<div style="color:var(--muted);font-size:10px;margin-top:5px;">Embedded in <span style="color:var(--gold);">${escapeHtml(d.bitPlane || 'LSB Bit-Planes 0 & 1 (RGB)')}</span> across top ${d.scanlines || 1} scanline(s).</div>` : ''}
      ${d.markPng ? `<div style="color:var(--muted);margin:6px 0 4px;">Recovered mark (${d.markCoverage}% of photo, confidence ${d.markScore}%)</div><img alt="Recovered hidden mark" src="data:image/png;base64,${d.markPng}" style="width:100%;background:#000;image-rendering:auto;border:1px solid var(--line);">` : ''}
      ${foreignStegoHtml(d)}
    `;
    renderInspectStage();
  } else {
    const other = foreignStegoHtml(d);
    box.innerHTML = other || `<div style="color:var(--muted);">&#8212; No hidden mark, text or watermark found in this image.</div>`;
    renderInspectStage();
  }
}

// Hidden data and watermarks written by other tools (stego/scan.py). Kept apart from the Lumiya result above.
function foreignStegoHtml(d) {
  const list = (d && d.foreign) || [];
  if (!list.length) return '';
  return `<div style="color:var(--gold);margin:8px 0 4px;">Other hidden data / watermarks (${list.length})</div>
    ${list.map(f => `<div class="insp-meta-row" style="display:block;margin-bottom:5px;"><div><strong>${escapeHtml(f.name)}</strong> <span style="color:var(--dim);">&middot; ${escapeHtml(f.confidence)}</span></div><div style="color:var(--muted);font-size:10px;">${escapeHtml(f.detail)}</div></div>`).join('')}`;
}

function renderInspectModule() {
  updateInspectBadges();
  const strip = document.getElementById('insp-filmstrip');
  const item = inspectItems[activeInspectIdx];
  const entry = item ? inspectCache[item.key] : null;
  syncInspectViewButtons(item, entry);

  document.getElementById('im-name').innerText = item ? formatQueueFileName(item.name, 26) : '—';
  document.getElementById('im-name').title = item ? item.name : '';
  document.getElementById('im-batch').innerText = item ? item.batchId : '—';
  document.getElementById('im-dims').innerText = item ? item.dims : '—';
  document.getElementById('im-status').innerText = item ? item.status : '—';
  document.getElementById('im-psnr').innerText = item && item.psnr ? `${item.psnr} dB` : '—';
  document.getElementById('im-shift').innerText = item && item.shift ? `${item.shift} / 255` : '—';

  if (strip) {
    if (!strip.dataset.wheelBound) {
      strip.dataset.wheelBound = '1';
      strip.addEventListener('wheel', (ev) => {
        if (Math.abs(ev.deltaY) > Math.abs(ev.deltaX)) {
          ev.preventDefault();
          strip.scrollLeft += ev.deltaY;
        }
      }, { passive: false });
    }
    if (inspectItems.length === 0) {
      strip.innerHTML = `<div style="color:var(--dim);font-family:var(--font-sans);font-size:11px;">[ Collection empty — send photos from Workspace or import photos manually ]</div>`;
    } else {
      [...inspSel].forEach(k => { if (!inspectItems.some(x => x.key === k)) inspSel.delete(k); });
      strip.innerHTML = inspectItems.map((it, idx) => {
        const count = inspDel && inspDel.keys.includes(it.key) ? inspDel.n : 0;
        return `
        <div class="insp-thumb-card ${idx === activeInspectIdx ? 'active' : ''} ${inspSel.has(it.key) ? 'selected' : ''}" onclick="onInspectThumbClick(event, ${idx})" title="${escapeHtml(it.name)} (${escapeHtml(it.batchId)})">
          <span class="insp-thumb-del ${count ? 'counting' : ''}" data-key="${escapeHtml(it.key)}" onclick="removeInspectItem(event, ${idx})" title="Remove from Inspect: press 3 times (files on disk stay)">${count || '&times;'}</span>
          ${it.thumb ? `<img src="${it.thumb}" alt="${escapeHtml(it.name)}">` : `<div style="height:58px;display:flex;align-items:center;color:var(--dim);font-size:10px;">IMG</div>`}
          <div class="insp-thumb-lbl">${idx + 1}. ${escapeHtml(it.name)}</div>
        </div>
      `;}).join('');
      const activeCard = strip.querySelector('.insp-thumb-card.active');
      if (activeCard && typeof activeCard.scrollIntoView === 'function') {
        activeCard.scrollIntoView({ block: 'nearest', inline: 'nearest' });
      }
    }
  }

  renderInspectStage();
  renderInspectHistogram();
  updateLiveLsbHexStream(entry);
  runInspectStegoScan();
  renderForensicAnalytics();
}

function toggleInspectEyePopup(forceState) {
  const el = document.getElementById('insp-floating-info');
  if (!el) return;
  if (typeof forceState === 'boolean') el.classList.toggle('open', forceState);
  else el.classList.toggle('open');
}

function setInspectViewMode(mode) {
  const item = inspectItems[activeInspectIdx];
  const entry = item ? inspectCache[item.key] : null;
  if (mode !== 'single' && !canCompareBeforeAfter(item, entry)) return;
  inspectViewMode = mode;
  ['single', 'side', 'wipe'].forEach(m => {
    const b = document.getElementById(`vm-${m}`);
    if (b) b.classList.toggle('active', m === mode);
  });
  document.getElementById('insp-wipe-ctrl').style.display = mode === 'wipe' ? 'flex' : 'none';
  renderInspectStage();
}

function toggleInspectQuickBefore() {
  const item = inspectItems[activeInspectIdx];
  const entry = item ? inspectCache[item.key] : null;
  if (!canCompareBeforeAfter(item, entry)) return;
  inspectQuickBefore = !inspectQuickBefore;
  document.getElementById('vm-swap').classList.toggle('active', inspectQuickBefore);
  renderInspectStage();
  renderInspectHistogram();
  updateLiveLsbHexStream(entry);
}

let inspectSliderRaf = null;

function onInspectWipeSlider(val) {
  inspectWipePct = parseFloat(val) / 100.0;
  if (!inspectSliderRaf) {
    inspectSliderRaf = requestAnimationFrame(() => {
      inspectSliderRaf = null;
      renderInspectStage();
    });
  }
}

const ALL_LENS_IDS = ['normal', 'diff', 'fft', 'ela', 'sobel', 'srm', 'luma_map', 'chroma', 'lsb', 'mark'];

function syncStegoChannelButtons() {
  const isChanLens = inspectLens === 'normal' || inspectLens === 'stego_plane';
  ['rgb', 'r', 'g', 'b', 'a', 'luma'].forEach(c => {
    const b = document.getElementById(`sc-${c}`);
    if (b) b.classList.toggle('active', isChanLens && c === stegoChannel);
  });
  const lbl = document.getElementById('stego-chan-lbl');
  if (lbl) {
    if (inspectLens === 'mark') lbl.innerText = 'QIM / BIT-0';
    else if (inspectLens === 'lsb') lbl.innerText = '2-BIT LSB (x85)';
    else lbl.innerText = stegoChannel.toUpperCase();
  }
}

function setInspectLens(lens) {
  // Allow clicking Hidden Mark or 2-Bit LSB a second time to unchoose it back onto the active channel
  if ((lens === 'mark' || lens === 'lsb') && inspectLens === lens) {
    lens = (stegoChannel === 'rgb' && stegoBitPlane === -1) ? 'normal' : 'stego_plane';
  }
  inspectLens = lens;
  if (lens === 'normal') {
    stegoChannel = 'rgb';
    stegoBitPlane = -1;
    const sld = document.getElementById('stego-bit-slider');
    if (sld) sld.value = -1;
    const lbl = document.getElementById('stego-bit-lbl');
    if (lbl) lbl.innerText = 'All Bits (Full)';
  } else if (lens !== 'stego_plane') {
    stegoBitPlane = -1;
    const sld = document.getElementById('stego-bit-slider');
    if (sld) sld.value = -1;
    const lbl = document.getElementById('stego-bit-lbl');
    if (lbl) lbl.innerText = 'All Bits (Full)';
  }
  ALL_LENS_IDS.forEach(l => {
    const b = document.getElementById(`lens-${l}`);
    if (b) b.classList.toggle('active', l === inspectLens);
  });
  if (lens !== 'fa' && typeof faShownTool !== 'undefined' && faShownTool) {
    faShownTool = '';
    if (typeof renderForensicAnalytics === 'function') renderForensicAnalytics();
  }
  syncStegoChannelButtons();
  renderInspectStage();
}

function setStegoChannel(ch) {
  stegoChannel = ch;
  inspectLens = (ch === 'rgb' && stegoBitPlane === -1) ? 'normal' : 'stego_plane';
  ALL_LENS_IDS.forEach(l => {
    const b = document.getElementById(`lens-${l}`);
    if (b) b.classList.toggle('active', l === inspectLens);
  });
  if (typeof faShownTool !== 'undefined' && faShownTool) {
    faShownTool = '';
    if (typeof renderForensicAnalytics === 'function') renderForensicAnalytics();
  }
  syncStegoChannelButtons();
  renderInspectStage();
}

function setStegoBitPlane(bp) {
  const clamped = Math.max(-1, Math.min(7, bp));
  stegoBitPlane = clamped;
  const sld = document.getElementById('stego-bit-slider');
  if (sld) sld.value = clamped;
  const lbl = document.getElementById('stego-bit-lbl');
  if (lbl) {
    lbl.innerText = clamped === -1 ? 'All Bits (Full)' : `Bit ${clamped} (${clamped === 0 ? 'LSB' : (clamped === 7 ? 'MSB' : 'Plane')})`;
  }
  inspectLens = (clamped === -1 && stegoChannel === 'rgb') ? 'normal' : 'stego_plane';
  ALL_LENS_IDS.forEach(l => {
    const b = document.getElementById(`lens-${l}`);
    if (b) b.classList.toggle('active', l === inspectLens);
  });
  if (typeof faShownTool !== 'undefined' && faShownTool) {
    faShownTool = '';
    if (typeof renderForensicAnalytics === 'function') renderForensicAnalytics();
  }
  syncStegoChannelButtons();
  renderInspectStage();
}

function stepStegoBitPlane(delta) {
  let next = stegoBitPlane + delta;
  if (next > 7) next = -1;
  if (next < -1) next = 7;
  setStegoBitPlane(next);
}

function toggleStegoInvert() {
  stegoInvert = !stegoInvert;
  const btn = document.getElementById('stego-btn-invert');
  const lbl = document.getElementById('stego-inv-lbl');
  if (btn) btn.classList.toggle('toggle-on', stegoInvert);
  if (lbl) lbl.innerText = stegoInvert ? 'ON' : 'OFF';
  renderInspectStage();
}

function toggleStegoLut() {
  stegoLut = !stegoLut;
  const btn = document.getElementById('stego-btn-lut');
  const lbl = document.getElementById('stego-lut-lbl');
  if (btn) btn.classList.toggle('toggle-on', stegoLut);
  if (lbl) lbl.innerText = stegoLut ? 'ON' : 'OFF';
  renderInspectStage();
}

function onInspectGainChange(val) {
  inspectGain = parseInt(val, 10);
  document.getElementById('v-insp-gain').innerText = `${inspectGain}`;
  if (!inspectSliderRaf) {
    inspectSliderRaf = requestAnimationFrame(() => {
      inspectSliderRaf = null;
      renderInspectStage();
    });
  }
}

function onInspectElaQChange(val) {
  inspectElaQ = parseInt(val, 10);
  document.getElementById('v-insp-ela-q').innerText = `${inspectElaQ}`;
  if (inspectLens !== 'ela') setInspectLens('ela');
  else if (!inspectSliderRaf) {
    inspectSliderRaf = requestAnimationFrame(() => {
      inspectSliderRaf = null;
      renderInspectStage();
    });
  }
}

function onInspectFloorChange(val) {
  inspectNoiseFloor = parseInt(val, 10);
  document.getElementById('v-insp-floor').innerText = `${inspectNoiseFloor}`;
  if (!inspectSliderRaf) {
    inspectSliderRaf = requestAnimationFrame(() => {
      inspectSliderRaf = null;
      renderInspectStage();
    });
  }
}

function setInspectZoomPreset(z) {
  inspectTargetZoom = z;
  if (z === 'FIT') {
    inspectTargetCenter = { u: 0.5, v: 0.5 };
  }
  requestInspectSmoothAnim();
}

function stepInspectZoom(factor) {
  const item = inspectItems[activeInspectIdx];
  const entry = item ? inspectCache[item.key] : null;
  if (!entry || !entry.loaded) return;
  const stage = document.getElementById('insp-stage');
  const paneW = inspectViewMode === 'side' ? stage.clientWidth * 0.5 : stage.clientWidth;
  const cur = inspectTargetZoom === 'FIT' ? getFitScale(entry, paneW, stage.clientHeight) : inspectTargetZoom;
  const next = Math.max(0.25, Math.min(16, Math.round(cur * factor * 100) / 100));
  inspectTargetZoom = next;
  requestInspectSmoothAnim();
}

(function bindInspectEvents() {
  const stage = document.getElementById('insp-stage');
  const navBox = document.getElementById('insp-nav-box');
  const dropOverlay = document.getElementById('insp-drop-overlay');
  if (!stage) return;

  function isPointOnInspectImage(entry, rect, mx, my) {
    if (!entry || !entry.loaded || !rect) return false;
    if (mx < 0 || mx >= rect.width || my < 0 || my >= rect.height) return false;
    const paneW = inspectViewMode === 'side' ? rect.width * 0.5 : rect.width;
    const localX = inspectViewMode === 'side' && mx >= paneW ? mx - paneW : mx;
    const scale = getEffectiveScale(entry, paneW, rect.height);
    const drawW = entry.w * scale;
    const drawH = entry.h * scale;
    const ox = paneW * 0.5 - inspectCenter.u * drawW;
    const oy = rect.height * 0.5 - inspectCenter.v * drawH;
    return localX >= ox && localX <= ox + drawW && my >= oy && my <= oy + drawH;
  }

  stage.addEventListener('mouseleave', () => {
    stage.classList.remove('over-img');
  });

  // Standalone Drag-and-Drop directly onto Inspect Stage (including dynamic "Drop to upload" overlay)
  let stageDragDepth = 0;
  stage.addEventListener('dragenter', (e) => {
    e.preventDefault();
    stageDragDepth++;
    if (dropOverlay) dropOverlay.classList.add('active');
  });
  stage.addEventListener('dragover', (e) => {
    e.preventDefault();
    if (dropOverlay && !dropOverlay.classList.contains('active')) {
      dropOverlay.classList.add('active');
    }
  });
  stage.addEventListener('dragleave', (e) => {
    e.preventDefault();
    stageDragDepth = Math.max(0, stageDragDepth - 1);
    if (stageDragDepth === 0 && dropOverlay) {
      dropOverlay.classList.remove('active');
    }
  });
  stage.addEventListener('drop', (e) => {
    e.preventDefault();
    stageDragDepth = 0;
    if (dropOverlay) dropOverlay.classList.remove('active');
    if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      ingestStandaloneInspectFiles(e.dataTransfer.files);
    }
  });

  stage.addEventListener('wheel', (e) => {
    e.preventDefault();
    const item = inspectItems[activeInspectIdx];
    const entry = item ? inspectCache[item.key] : null;
    if (!entry || !entry.loaded) return;

    const rect = stage.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    if (!isPointOnInspectImage(entry, rect, mx, my)) return;
    const paneW = inspectViewMode === 'side' ? rect.width * 0.5 : rect.width;
    const localX = inspectViewMode === 'side' && mx >= paneW ? mx - paneW : mx;
    const localY = my;

    const curScale = getEffectiveScale(entry, paneW, rect.height);
    const baseTarget = inspectTargetZoom === 'FIT' ? curScale : inspectTargetZoom;
    const wheelMag = Math.min(2.5, Math.max(0.4, Math.abs(e.deltaY) / 100));
    const factor = e.deltaY < 0 ? (1 + 0.22 * wheelMag) : (1 / (1 + 0.22 * wheelMag));
    const nextScale = Math.max(0.25, Math.min(16, baseTarget * factor));

    // Anchor zoom smoothly toward the cursor coordinates
    const drawW = entry.w * curScale;
    const drawH = entry.h * curScale;
    const ox = paneW * 0.5 - inspectCenter.u * drawW;
    const oy = rect.height * 0.5 - inspectCenter.v * drawH;
    const cursorU = Math.max(0, Math.min(1, (localX - ox) / Math.max(1, drawW)));
    const cursorV = Math.max(0, Math.min(1, (localY - oy) / Math.max(1, drawH)));

    inspectTargetZoom = Math.round(nextScale * 100) / 100;
    inspectTargetCenter = anchoredTarget(entry, cursorU, cursorV, localX - paneW * 0.5, localY - rect.height * 0.5, inspectTargetZoom);
    requestInspectSmoothAnim();
  }, { passive: false });

  stage.addEventListener('mousedown', (e) => {
    if (e.button !== 0) return;
    const item = inspectItems[activeInspectIdx];
    const entry = item ? inspectCache[item.key] : null;
    if (!entry || !entry.loaded) return;
    const rect = stage.getBoundingClientRect();
    stage._cachedRect = rect;
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;

    if (inspectViewMode === 'wipe' && Math.abs(mx - rect.width * inspectWipePct) <= 18) {
      inspectDrag = { type: 'wipe', moved: true };
      return;
    }
    if (!isPointOnInspectImage(entry, rect, mx, my)) return;
    inspectDrag = {
      type: 'pan',
      startX: mx,
      startY: my,
      startU: inspectCenter.u,
      startV: inspectCenter.v,
      moved: false
    };
    stage.classList.add('panning');
  });

  let loupeHoverRaf = null;
  stage.addEventListener('mousemove', (e) => {
    if (inspectDrag || loupeHoverRaf) return;
    const clientX = e.clientX;
    const clientY = e.clientY;
    loupeHoverRaf = requestAnimationFrame(() => {
      loupeHoverRaf = null;
      const item = inspectItems[activeInspectIdx];
      const entry = item ? inspectCache[item.key] : null;
      if (!entry || !entry.loaded) {
        stage.classList.remove('over-img');
        return;
      }
      const rect = stage._cachedRect || stage.getBoundingClientRect();
      stage._cachedRect = rect;
      const mx = clientX - rect.left;
      const my = clientY - rect.top;
      const onImg = isPointOnInspectImage(entry, rect, mx, my);
      stage.classList.toggle('over-img', onImg);
      if (onImg) {
        const paneW = inspectViewMode === 'side' ? rect.width * 0.5 : rect.width;
        const localX = inspectViewMode === 'side' && mx >= paneW ? mx - paneW : mx;
        const scale = getEffectiveScale(entry, paneW, rect.height);
        const drawW = entry.w * scale;
        const drawH = entry.h * scale;
        const ox = paneW * 0.5 - inspectCenter.u * drawW;
        const oy = rect.height * 0.5 - inspectCenter.v * drawH;
        const px = Math.floor((localX - ox) / scale);
        const py = Math.floor((my - oy) / scale);
        if (px >= 0 && px < entry.w && py >= 0 && py < entry.h) {
          const idx = (py * entry.w + px) * 4;
          const bd = entry.beforeData.data;
          const ad = entry.afterData.data;
          const dr = Math.abs(ad[idx] - bd[idx]);
          const dg = Math.abs(ad[idx + 1] - bd[idx + 1]);
          const db = Math.abs(ad[idx + 2] - bd[idx + 2]);
          document.getElementById('im-xy').innerText = `${px}, ${py}`;
          document.getElementById('im-rgb-bef').innerText = `${bd[idx]}, ${bd[idx + 1]}, ${bd[idx + 2]}`;
          document.getElementById('im-rgb-aft').innerText = `${ad[idx]}, ${ad[idx + 1]}, ${ad[idx + 2]} (\u0394${Math.max(dr, dg, db)})`;
        }
      }
    });
  });

  window.addEventListener('mousemove', (e) => {
    if (!inspectDrag) return;
    const item = inspectItems[activeInspectIdx];
    const entry = item ? inspectCache[item.key] : null;
    if (!entry || !entry.loaded) return;
    const rect = stage._cachedRect || stage.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;

    if (inspectDrag.type === 'wipe') {
      inspectWipePct = Math.max(0.05, Math.min(0.95, mx / Math.max(1, rect.width)));
      document.getElementById('insp-wipe-slider').value = Math.round(inspectWipePct * 100);
      renderInspectStage();
      return;
    }
    const dx = mx - inspectDrag.startX;
    const dy = my - inspectDrag.startY;
    if (Math.abs(dx) > 4 || Math.abs(dy) > 4) inspectDrag.moved = true;
    if (inspectDrag.moved) {
      const paneW = inspectViewMode === 'side' ? rect.width * 0.5 : rect.width;
      const scale = getEffectiveScale(entry, paneW, rect.height);
      inspectCenter.u = Math.max(0, Math.min(1, inspectDrag.startU - dx / (entry.w * scale)));
      inspectCenter.v = Math.max(0, Math.min(1, inspectDrag.startV - dy / (entry.h * scale)));
      inspectTargetCenter = { u: inspectCenter.u, v: inspectCenter.v };
      renderInspectStage();
    }
  });

  window.addEventListener('mouseup', (e) => {
    if (!inspectDrag) return;
    stage.classList.remove('panning');
    const wasMoved = inspectDrag.moved;
    inspectDrag = null;

    // Single-click Loupe toggle: Fit <-> last zoom, keeping the clicked point under the pointer
    if (!wasMoved) {
      const item = inspectItems[activeInspectIdx];
      const entry = item ? inspectCache[item.key] : null;
      if (!entry || !entry.loaded) return;
      if (inspectTargetZoom === 'FIT') {
        const rect = stage.getBoundingClientRect();
        const size = inspectStageSize(stage);
        const paneW = inspectViewMode === 'side' ? size.w * 0.5 : size.w;
        const localX = (e.clientX - rect.left) % paneW;
        const localY = e.clientY - rect.top;
        const scale = getEffectiveScale(entry, paneW, size.h);
        const ox = paneW * 0.5 - inspectCenter.u * entry.w * scale;
        const oy = size.h * 0.5 - inspectCenter.v * entry.h * scale;
        const clickU = Math.max(0, Math.min(1, (localX - ox) / (entry.w * scale)));
        const clickV = Math.max(0, Math.min(1, (localY - oy) / (entry.h * scale)));
        // Zoom into the clicked spot without moving it: it stays under the pointer.
        inspectTargetZoom = inspectClickZoomFor(entry);
        inspectTargetCenter = anchoredTarget(entry, clickU, clickV, localX - paneW * 0.5, localY - size.h * 0.5, inspectTargetZoom);
      } else {
        inspectTargetZoom = 'FIT';
        inspectTargetCenter = { u: 0.5, v: 0.5 };
      }
      requestInspectSmoothAnim();
    }
  });

  // Navigator, Lightroom-style: the viewing rectangle is a draggable box. Clicking outside it jumps there and keeps
  // dragging; at Fit a click zooms in on that spot; a click on the box without dragging goes back to Fit.
  if (navBox) {
    let navDrag = null;
    const navPoint = (entry, e) => {
      const r = navigatorImageRect(entry);
      return { u: (e.clientX - r.left) / Math.max(1, r.w), v: (e.clientY - r.top) / Math.max(1, r.h) };
    };
    const clamp01 = x => Math.max(0, Math.min(1, x));
    const activeEntry = () => {
      const item = inspectItems[activeInspectIdx];
      const entry = item ? inspectCache[item.key] : null;
      return entry && entry.loaded ? entry : null;
    };
    const viewHalf = entry => inspectViewHalf(entry, stage.clientWidth, stage.clientHeight);

    navBox.addEventListener('mousedown', (e) => {
      if (e.button !== 0) return;
      const entry = activeEntry();
      if (!entry) return;
      e.preventDefault();
      const pt = navPoint(entry, e);
      if (inspectTargetZoom === 'FIT') {
        inspectTargetCenter = { u: clamp01(pt.u), v: clamp01(pt.v) };
        inspectTargetZoom = inspectClickZoomFor(entry);
        requestInspectSmoothAnim();
        return;
      }
      const half = viewHalf(entry);
      const insideBox = Math.abs(pt.u - inspectCenter.u) <= half.u && Math.abs(pt.v - inspectCenter.v) <= half.v;
      // Grabbing the box keeps the grab point under the pointer; elsewhere the box centers on the pointer.
      navDrag = {
        offU: insideBox ? pt.u - inspectCenter.u : 0,
        offV: insideBox ? pt.v - inspectCenter.v : 0,
        insideBox,
        moved: false,
        startX: e.clientX,
        startY: e.clientY
      };
      if (!insideBox) {
        inspectTargetCenter = { u: clamp01(pt.u), v: clamp01(pt.v) };
        requestInspectSmoothAnim();
      }
      navBox.classList.add('dragging');
    });

    window.addEventListener('mousemove', (e) => {
      const entry = activeEntry();
      if (!entry) return;
      if (!navDrag) {
        if (!navBox.contains(e.target) || inspectTargetZoom === 'FIT') {
          navBox.classList.remove('over-view');
          return;
        }
        const pt = navPoint(entry, e);
        const half = viewHalf(entry);
        navBox.classList.toggle('over-view', Math.abs(pt.u - inspectCenter.u) <= half.u && Math.abs(pt.v - inspectCenter.v) <= half.v);
        return;
      }
      if (Math.abs(e.clientX - navDrag.startX) > 2 || Math.abs(e.clientY - navDrag.startY) > 2) navDrag.moved = true;
      if (!navDrag.moved) return;
      const pt = navPoint(entry, e);
      inspectCenter = { u: clamp01(pt.u - navDrag.offU), v: clamp01(pt.v - navDrag.offV) };
      inspectTargetCenter = { u: inspectCenter.u, v: inspectCenter.v };
      renderInspectStage();
    });

    window.addEventListener('mouseup', () => {
      if (!navDrag) return;
      if (navDrag.insideBox && !navDrag.moved) {
        inspectTargetZoom = 'FIT';
        inspectTargetCenter = { u: 0.5, v: 0.5 };
        requestInspectSmoothAnim();
      }
      navDrag = null;
      navBox.classList.remove('dragging');
    });
  }

  window.addEventListener('resize', () => {
    if (document.getElementById('page-insp').classList.contains('active')) {
      renderInspectStage();
    }
  });

  window.addEventListener('keydown', (e) => {
    if (!document.getElementById('page-insp').classList.contains('active')) return;
    if (e.target && (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT' || e.target.tagName === 'TEXTAREA')) return;
    if (e.key === 'z' || e.key === 'Z') {
      const zItem = inspectItems[activeInspectIdx];
      const zEntry = zItem ? inspectCache[zItem.key] : null;
      if (zEntry && zEntry.loaded) setInspectZoomPreset(inspectTargetZoom === 'FIT' ? inspectClickZoomFor(zEntry) : 'FIT');
    } else if (e.key === '\\') {
      toggleInspectQuickBefore();
    } else if (e.key === 'y' || e.key === 'Y') {
      const order = ['single', 'side', 'wipe'];
      setInspectViewMode(order[(order.indexOf(inspectViewMode) + 1) % order.length]);
    } else if (e.key === 'ArrowRight') {
      if (activeInspectIdx + 1 < inspectItems.length) selectInspectItem(activeInspectIdx + 1);
    } else if (e.key === 'ArrowLeft') {
      if (activeInspectIdx > 0) selectInspectItem(activeInspectIdx - 1);
    } else if (e.key === 'x' || e.key === 'X') {
      removeInspectItem(null, activeInspectIdx);
    }
  });
})();

