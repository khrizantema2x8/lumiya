// ---- Display font (Tailoring) ----
// Application fonts come only from identity/fonts; Geist is built in (identity/media/fallback-font) and is what the
// app shows when nothing is chosen, the folder is emptied, or the chosen font disappears.
const FONT_NAME_RE = /^[\p{L}\p{N}\p{M}_ .,&'()+-]{1,64}$/u;
const DEFAULT_FONT = 'Geist';
const FONT_CLASSES = [
  ['', 'All Classes'], ['serif', 'Serif'], ['slab', 'Slab Serif'], ['sans', 'Sans Serif'], ['script', 'Script'],
  ['monospace', 'Monospace'], ['handwritten', 'Handwritten'], ['blackletter', 'Blackletter'], ['decorative', 'Decorative'],
];
const FONT_FORMATS = ['', 'otf', 'ttf'];
const FONT_FORMAT_TIPS = {
  '': 'Showing all formats. Click to show OpenType only.',
  otf: 'Showing OpenType only. Click to show TrueType only.',
  ttf: 'Showing TrueType only. Click to show all formats.',
};
const BUILTIN_FAMILY = {
  name: DEFAULT_FONT, cls: 'sans', fmt: 'ttf', builtin: true,
  faces: [{ style: 'Regular', weight: 400, italic: false, wght: [100, 900] }],
};

let currentFont = '';
try { currentFont = localStorage.getItem('lumiyaFont') || ''; } catch (e) {}
if (!FONT_NAME_RE.test(currentFont)) currentFont = '';
let favoriteFonts = [];
let favoriteFontsHydrated = false;
let appFamilies = [BUILTIN_FAMILY];
let systemFamilies = null;        // null until the System Fonts tab is first opened
let systemFontsLoading = false;
let appFontsLoaded = false;
const appFontFaces = new Map();   // file -> FontFace registered on document.fonts
const fb = { revealing: false, source: 'app', cls: '', fmt: '', favOnly: false, query: '', classesHidden: false, selected: '', face: null };
try {
  const saved = JSON.parse(localStorage.getItem('lumiyaFontBrowser') || '{}');
  if (FONT_CLASSES.some(c => c[0] === saved.cls)) fb.cls = saved.cls;
  fb.classesHidden = !!saved.classesHidden;
} catch (e) {}

function saveFontBrowserState() {
  try { localStorage.setItem('lumiyaFontBrowser', JSON.stringify({ cls: fb.cls, classesHidden: fb.classesHidden })); } catch (e) {}
}

function fontStackFor(name) {
  return name ? `"${name}", var(--font-sans-default)` : 'var(--font-sans-default)';
}

// Canvas text cannot read CSS variables, so resolve the stack at draw time.
function uiFontStack() {
  const v = getComputedStyle(document.documentElement).getPropertyValue('--font-sans-default').trim();
  return currentFont ? `"${currentFont}", ${v}` : v;
}

// Faces the page registered count as available; an installed font is detected because a missing family renders in the
// fallback and so measures the same as the fallback in two different generic families.
function fontAvailable(name) {
  if (!name) return true;
  if (document.fonts && [...document.fonts].some(f => f.family.replace(/["']/g, '') === name)) return true;
  const ctx = (fontAvailable._c ||= document.createElement('canvas').getContext('2d'));
  const sample = 'mmmmmmmmmmlliWW@#0123';
  return ['monospace', 'serif'].some(g => {
    ctx.font = `72px ${g}`;
    const base = ctx.measureText(sample).width;
    ctx.font = `72px "${name}", ${g}`;
    return ctx.measureText(sample).width !== base;
  });
}

function groupFontFaces(faces) {
  const byName = new Map();
  for (const f of faces) {
    if (!f || !FONT_NAME_RE.test(f.family || '')) continue;
    let fam = byName.get(f.family);
    if (!fam) {
      fam = { name: f.family, cls: f.cls || '', fmt: f.fmt === 'otf' ? 'otf' : 'ttf', faces: [] };
      byName.set(f.family, fam);
    }
    if (!fam.cls && f.cls) fam.cls = f.cls;
    fam.faces.push({ style: f.style || 'Regular', weight: f.weight || 400, italic: !!f.italic, wght: f.wght || null, file: f.file, mtime: f.mtime });
  }
  const out = [...byName.values()];
  out.forEach(fam => fam.faces.sort((a, b) => (a.italic - b.italic) || (a.weight - b.weight) || a.style.localeCompare(b.style)));
  return out.sort((a, b) => a.name.localeCompare(b.name));
}

function registerAppFontFaces(faces) {
  if (!document.fonts || typeof FontFace === 'undefined') return;
  const keep = new Set();
  for (const f of faces) {
    if (!f.file || !FONT_NAME_RE.test(f.family || '') || f.family === DEFAULT_FONT) continue;
    const key = `${f.file}?${f.mtime || 0}`;
    keep.add(key);
    if (appFontFaces.has(key)) continue;
    const weight = f.wght ? `${f.wght[0]} ${f.wght[1]}` : String(f.weight || 400);
    const url = `/identity/fonts/${encodeURIComponent(f.file)}?v=${f.mtime || 0}`;
    const face = new FontFace(f.family, `url("${url}")`, { weight, style: f.italic ? 'italic' : 'normal', display: 'swap' });
    document.fonts.add(face);
    appFontFaces.set(key, face);
  }
  // Files removed from the folder stop being offered and stop rendering.
  for (const [key, face] of appFontFaces) {
    if (!keep.has(key)) { document.fonts.delete(face); appFontFaces.delete(key); }
  }
}

let appFontsSig = '';
async function loadAppFonts() {
  try {
    const res = await api('/api/fonts');
    const data = await res.json();
    const faces = Array.isArray(data.app) ? data.app : [];
    const sig = JSON.stringify(faces);
    // Re-read on every visit to the tab, but the list is only rebuilt when the folder actually changed.
    if (sig !== appFontsSig || !appFontsLoaded) {
      appFontsSig = sig;
      registerAppFontFaces(faces);
      appFamilies = [BUILTIN_FAMILY].concat(groupFontFaces(faces).filter(f => f.name !== DEFAULT_FONT));
    }
  } catch (err) {
    if (!appFontsLoaded) appFamilies = [BUILTIN_FAMILY];
  }
  appFontsLoaded = true;
  await buildFontSource('app');
  renderFontBrowser();
  previewFont(fb.selected);
}

// Start-up work: both lists are built once, in idle-time batches, and laid out as they are built, so every font's
// first-use cost is paid while the app loads. After that, filters, tabs and selection only flip classes on the rows,
// and later layouts of the list reuse the warm font and style caches.
const fontWarmState = { app: false, system: false };
const fbBuilt = { app: null, system: null };    // the family array each list was built from
const fbIndex = { app: new Map(), system: new Map() };
let cfgPrelayoutCount = 0;
const fontIdle = window.requestIdleCallback
  ? (fn) => window.requestIdleCallback(fn, { timeout: 400 })
  : (fn) => setTimeout(() => fn({ timeRemaining: () => 8 }), 16);

function filterAvailableFamilies(families) {
  return new Promise(resolve => {
    const kept = [];
    let i = 0;
    const step = (deadline) => {
      while (i < families.length && deadline.timeRemaining() > 3) {
        const fam = families[i++];
        if (fontAvailable(fam.name)) kept.push(fam);
      }
      if (i < families.length) fontIdle(step);
      else resolve(kept);
    };
    fontIdle(step);
  });
}

async function loadSystemFonts(refresh = false) {
  if (systemFontsLoading) return;
  systemFontsLoading = true;
  if (fb.source === 'system') renderFontBrowser();
  try {
    const res = await api('/api/fonts/system' + (refresh ? '?refresh=1' : ''));
    const data = await res.json();
    // Only names this browser can actually draw.
    systemFamilies = await filterAvailableFamilies(groupFontFaces(Array.isArray(data.system) ? data.system : []));
  } catch (err) {
    systemFamilies = [];
  }
  await buildFontSource('system');
  systemFontsLoading = false;
  renderFontBrowser();
}

function sourceFamilies(src) {
  return src === 'app' ? appFamilies : (systemFamilies || []);
}

function familyList() {
  return sourceFamilies(fb.source);
}

function familyMatches(f) {
  const q = fb.query.trim().toLowerCase();
  return (!fb.cls || f.cls === fb.cls)
    && (!fb.fmt || f.fmt === fb.fmt)
    && (!fb.favOnly || favoriteFonts.includes(f.name))
    && (!q || f.name.toLowerCase().includes(q));
}

function visibleFamilies() {
  return familyList().filter(familyMatches);
}

const FB_STAR_SVG = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 1.8l1.9 3.9 4.3.6-3.1 3 .7 4.3L8 11.6l-3.8 2 .7-4.3-3.1-3 4.3-.6z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>';
const FB_CHEV_SVG = '<svg viewBox="0 0 10 10" aria-hidden="true"><path d="M3.5 1.5 7 5 3.5 8.5" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>';

function fontFormatGlyph(fmt) {
  return fmt === 'otf'
    ? '<span class="fb-fmt-glyph otf" title="OpenType">O</span>'
    : '<span class="fb-fmt-glyph" title="TrueType">TT</span>';
}

function faceLabel(face) {
  return face.wght ? `${face.style} · variable ${face.wght[0]}–${face.wght[1]}` : face.style;
}

function familyHtml(fam, i) {
  const stack = escapeHtml(fontStackFor(fam.name));
  const multi = fam.faces.length > 1;
  const variable = fam.faces.some(f => f.wght);
  const styles = multi ? `<div class="fb-styles"><div class="fb-styles-in">${fam.faces.map((face, j) =>
    `<div class="fb-row fb-style" data-face="${j}" role="option" aria-selected="false"><span></span><span></span>`
    + `<span class="fb-name">${escapeHtml(faceLabel(face))}</span><span></span><span></span>`
    + `<span class="fb-sample" style="font-family: ${stack}; font-weight: ${face.weight}; font-style: ${face.italic ? 'italic' : 'normal'}">Sample</span></div>`).join('')}</div></div>` : '';
  return `<div class="fb-fam" data-fam="${i}"><div class="fb-row fb-main" role="option" aria-selected="false">`
    + `<button type="button" class="fb-star" aria-pressed="false" aria-label="Add to favourites">${FB_STAR_SVG}</button>`
    + `<span class="fb-chev">${multi ? FB_CHEV_SVG : ''}</span>`
    + `<span class="fb-name" title="${escapeHtml(fam.name)}${variable ? ' (variable)' : ''}">${escapeHtml(fam.name)}</span>`
    + `<span class="fb-tag"></span><span class="fb-fmt">${fontFormatGlyph(fam.fmt)}</span>`
    + `<span class="fb-sample" style="font-family: ${stack}">Sample</span></div>${styles}</div>`;
}

// Lets the hidden Configuration page lay out while a list is being built (it otherwise skips its contents).
function cfgPrelayout(on) {
  cfgPrelayoutCount = Math.max(0, cfgPrelayoutCount + (on ? 1 : -1));
  document.getElementById('page-cfg').classList.toggle('cfg-prelayout', cfgPrelayoutCount > 0);
}

function buildFontSource(src) {
  const fams = src === 'app' ? appFamilies : systemFamilies;
  const box = document.getElementById('fb-src-' + src);
  if (!box || !fams || fbBuilt[src] === fams) return Promise.resolve();
  fbBuilt[src] = fams;
  fontWarmState[src] = false;
  fbIndex[src] = new Map(fams.map((f, i) => [f.name, i]));
  box.innerHTML = '';
  box.classList.add('fb-src-building');
  cfgPrelayout(true);
  return new Promise(resolve => {
    let i = 0;
    const step = (deadline) => {
      if (fbBuilt[src] !== fams) { cfgPrelayout(false); resolve(); return; }  // a newer list replaced this one
      while (i < fams.length && deadline.timeRemaining() > 3) {
        box.insertAdjacentHTML('beforeend', familyHtml(fams[i], i));
        i++;
        void box.offsetHeight;  // lay this family out (and load its fonts) inside the idle slot
      }
      if (i < fams.length) { fontIdle(step); return; }
      box.classList.remove('fb-src-building');
      cfgPrelayout(false);
      fontWarmState[src] = true;
      resolve();
    };
    fontIdle(step);
  });
}

function famElFor(src, name) {
  const i = fbIndex[src].get(name);
  return i === undefined ? null : document.querySelector(`#fb-src-${src} > .fb-fam[data-fam="${i}"]`);
}

function famFromEl(famEl) {
  const box = famEl && famEl.closest('.fb-src');
  return box ? sourceFamilies(box.dataset.src)[Number(famEl.dataset.fam)] : null;
}

// In-use tags, stars and selection, updated in place on the rows that already exist.
function syncFontRows(src) {
  const box = document.getElementById('fb-src-' + src);
  const fams = sourceFamilies(src);
  const inUse = currentFont || DEFAULT_FONT;
  box.querySelectorAll(':scope > .fb-fam').forEach(el => {
    const fam = fams[Number(el.dataset.fam)];
    if (!fam) return;
    const row = el.firstElementChild;
    row.classList.toggle('in-use', fam.name === inUse);
    const tag = row.querySelector('.fb-tag');
    const tagText = fam.name === inUse ? 'In use' : fam.builtin ? 'Default' : '';
    if (tag.textContent !== tagText) tag.textContent = tagText;
    tag.classList.toggle('muted', tagText === 'Default');
    const star = row.querySelector('.fb-star');
    const fav = favoriteFonts.includes(fam.name);
    if (star.classList.contains('on') !== fav) {
      star.classList.toggle('on', fav);
      star.setAttribute('aria-pressed', String(fav));
      star.setAttribute('aria-label', `${fav ? 'Remove from' : 'Add to'} favourites`);
    }
  });
  markFontSelection();
}

function markFontSelection(scroll = false) {
  document.querySelectorAll('#fb-list .fb-row.selected').forEach(el => { el.classList.remove('selected'); el.setAttribute('aria-selected', 'false'); });
  const famEl = famElFor(fb.source, fb.selected);
  const rowEl = famEl ? (fb.face === null ? famEl.firstElementChild : famEl.querySelector(`.fb-style[data-face="${fb.face}"]`)) : null;
  if (!rowEl) return;
  rowEl.classList.add('selected');
  rowEl.setAttribute('aria-selected', 'true');
  if (scroll) scrollFontListTo(rowEl);
}

function applyFontFilter(src) {
  const fams = sourceFamilies(src);
  let shown = 0;
  document.querySelectorAll(`#fb-src-${src} > .fb-fam`).forEach(el => {
    const ok = familyMatches(fams[Number(el.dataset.fam)]);
    if (el.classList.contains('fb-off') === ok) el.classList.toggle('fb-off', !ok);
    if (ok) shown++;
  });
  return shown;
}

function renderFontBrowser() {
  const root = document.getElementById('font-browser');
  if (!root) return;
  root.classList.toggle('classes-hidden', fb.classesHidden);
  document.getElementById('fb-tip-classes').textContent = fb.classesHidden ? 'Show the font classes' : 'Hide the font classes';
  document.getElementById('fb-tool-classes').setAttribute('aria-label', fb.classesHidden ? 'Show font classes' : 'Hide font classes');
  for (const src of ['app', 'system']) {
    const tab = document.getElementById('fb-tab-' + src);
    tab.classList.toggle('active', fb.source === src);
    tab.setAttribute('aria-selected', String(fb.source === src));
  }
  const fmtGlyph = document.getElementById('fb-fmt-glyph');
  document.getElementById('fb-tool-format').classList.toggle('on', !!fb.fmt);
  fmtGlyph.textContent = fb.fmt === 'otf' ? 'O' : 'TT';
  fmtGlyph.classList.toggle('otf', fb.fmt === 'otf');
  document.getElementById('fb-tip-format').textContent = FONT_FORMAT_TIPS[fb.fmt];
  const favTool = document.getElementById('fb-tool-fav');
  favTool.classList.toggle('on', fb.favOnly);
  favTool.setAttribute('aria-pressed', String(fb.favOnly));
  const search = document.getElementById('fb-search');
  if (search.value !== fb.query) search.value = fb.query;
  document.querySelectorAll('#fb-classes .fb-class').forEach(btn => {
    const on = (btn.dataset.cls || '') === fb.cls;
    btn.classList.toggle('active', on);
    btn.setAttribute('aria-checked', String(on));
  });

  const ready = { app: fontWarmState.app, system: fontWarmState.system && !systemFontsLoading && !fb.revealing };
  for (const src of ['app', 'system']) {
    document.getElementById('fb-src-' + src).classList.toggle('fb-src-off', fb.source !== src || !ready[src]);
  }
  const loading = document.getElementById('fb-loading');
  const none = document.getElementById('fb-none');
  loading.hidden = ready[fb.source];
  loading.textContent = fb.source === 'app' ? 'Reading identity/fonts…'
    : fb.revealing ? 'Loading fonts…' : 'Reading the fonts installed on this computer…';
  let shown = 0;
  if (ready[fb.source]) {
    shown = applyFontFilter(fb.source);
    syncFontRows(fb.source);
  }
  none.hidden = !ready[fb.source] || shown > 0;
  if (!none.hidden) {
    const why = fb.favOnly && !favoriteFonts.length ? 'No favourites yet. Click the star on a font to add it.' : 'No fonts match these filters.';
    none.innerHTML = `${why}<br><button type="button" class="q-btn" onclick="clearFontFilters()">Clear All</button>`;
  }
  const total = familyList().length;
  document.getElementById('fb-foot').innerHTML = !ready[fb.source] ? ''
    : fb.source === 'app'
      ? `${total} application ${total === 1 ? 'font' : 'fonts'}, read from <code>identity/fonts</code> (.ttf, .otf, .woff, .woff2). Geist is built in and is used when that folder is empty.`
      : `${total} fonts installed on this computer.`;
}

function setFontStatus(text, bad = false) {
  const el = document.getElementById('font-status');
  if (!el) return;
  el.textContent = text;
  el.classList.toggle('bad', bad);
}

function inUseLabel() {
  return currentFont ? currentFont : `${DEFAULT_FONT} (default)`;
}

// Null case: the saved font was removed from identity/fonts (or uninstalled), so the page is drawing Geist.
function reportMissingFont() {
  if (appFontsLoaded && currentFont && !fontAvailable(currentFont)) {
    setFontStatus(`"${currentFont}" is no longer in identity/fonts or installed on this computer, so Lumiya is showing ${DEFAULT_FONT}.`, true);
    return true;
  }
  return false;
}

function previewFont(name, face = null) {
  const preview = document.getElementById('font-preview');
  const applyBtn = document.getElementById('btn-apply-font');
  if (!preview || !applyBtn) return;
  const target = name || DEFAULT_FONT;
  preview.style.fontFamily = fontStackFor(target === DEFAULT_FONT ? '' : target);
  preview.style.fontWeight = face ? face.weight : '';
  preview.style.fontStyle = face ? (face.italic ? 'italic' : 'normal') : '';
  const sameAsInUse = (target === DEFAULT_FONT ? '' : target) === currentFont;
  applyBtn.disabled = sameAsInUse;
  if (sameAsInUse) {
    if (!reportMissingFont()) setFontStatus(`In use: ${inUseLabel()}. Click a font to preview it; double-click or press Enter to use it.`);
  } else {
    setFontStatus(`Previewing "${target}"${face ? ` ${face.style}` : ''}. In use: ${inUseLabel()}. Press "Use this font" to keep it.`);
  }
}

function setAppFont(name, shouldSave = true) {
  currentFont = name;
  if (name) document.documentElement.style.setProperty('--font-sans', fontStackFor(name));
  else document.documentElement.style.removeProperty('--font-sans');
  try { localStorage.setItem('lumiyaFont', name); } catch (e) {}
  if (shouldSave) {
    api('/api/save_config', { method: 'POST', body: JSON.stringify({ fontFamily: name }) }).catch(() => {});
  }
  // Text widths changed: let layouts that measure text (docks, inspect toolbar) redo their sums.
  window.dispatchEvent(new Event('resize'));
  if (typeof renderInspectStage === 'function') {
    const inspPage = document.getElementById('page-insp');
    if (inspPage && inspPage.classList.contains('active')) renderInspectStage();
  }
}

function applyFont() {
  const name = fb.selected || DEFAULT_FONT;
  if (!FONT_NAME_RE.test(name)) return;
  setAppFont(name === DEFAULT_FONT ? '' : name);
  syncFontRows(fb.source);
  previewFont(name);
  setFontStatus(`In use: ${inUseLabel()}. Lumiya will keep this font.`);
}

function resetFont() {
  fb.selected = DEFAULT_FONT;
  fb.face = null;
  setAppFont('');
  syncFontRows(fb.source);
  previewFont(DEFAULT_FONT);
}

function selectFontRow(name, faceIdx = null, scroll = false) {
  fb.selected = name;
  fb.face = faceIdx;
  markFontSelection(scroll);
  const fam = sourceFamilies(fb.source)[fbIndex[fb.source].get(name)];
  previewFont(name, fam && faceIdx !== null ? fam.faces[faceIdx] : null);
}

// Scrolls only the list: scrollIntoView would also scroll the Configuration page behind it.
function scrollFontListTo(el) {
  const list = document.getElementById('fb-list');
  const lr = list.getBoundingClientRect(), er = el.getBoundingClientRect();
  if (er.top < lr.top) list.scrollTop -= lr.top - er.top;
  else if (er.bottom > lr.bottom) list.scrollTop += er.bottom - lr.bottom;
}

function toggleFontFamilyOpen(famEl, open) {
  const fam = famFromEl(famEl);
  if (!fam || fam.faces.length < 2) return;
  famEl.classList.toggle('open', open === undefined ? !famEl.classList.contains('open') : open);
}

function toggleFavoriteFont(name) {
  const on = !favoriteFonts.includes(name);
  favoriteFonts = on ? favoriteFonts.concat(name) : favoriteFonts.filter(n => n !== name);
  api('/api/save_config', { method: 'POST', body: JSON.stringify({ favoriteFonts }) }).catch(() => {});
  if (fb.favOnly) renderFontBrowser();
  else syncFontRows(fb.source);
}

let fontRevealToken = 0;

function setFontSource(src) {
  fb.source = src === 'system' ? 'system' : 'app';
  const token = ++fontRevealToken;
  // The system list is hundreds of rows in as many fonts: show the spinner first, and lay the list out only once the
  // spinner has been painted (two frames later), so the click answers at once and the list arrives ready to scroll.
  fb.revealing = fb.source === 'system' && fontWarmState.system && !systemFontsLoading;
  document.getElementById('fb-list').scrollTop = 0;
  renderFontBrowser();
  if (fb.revealing) {
    requestAnimationFrame(() => requestAnimationFrame(() => {
      if (token !== fontRevealToken) return;
      fb.revealing = false;
      renderFontBrowser();
    }));
  }
  // The folder is re-read each time, so fonts dropped into identity/fonts appear without restarting.
  if (fb.source === 'app') loadAppFonts();
  else if (systemFamilies === null) loadSystemFonts();
}

function toggleFontClasses() {
  fb.classesHidden = !fb.classesHidden;
  saveFontBrowserState();
  renderFontBrowser();
}

function cycleFontFormat() {
  fb.fmt = FONT_FORMATS[(FONT_FORMATS.indexOf(fb.fmt) + 1) % FONT_FORMATS.length];
  renderFontBrowser();
}

function toggleFontFavOnly() {
  fb.favOnly = !fb.favOnly;
  renderFontBrowser();
}

function onFontSearch(value) {
  fb.query = String(value || '').slice(0, 64);
  renderFontBrowser();
}

function clearFontFilters() {
  fb.cls = '';
  fb.fmt = '';
  fb.favOnly = false;
  fb.query = '';
  saveFontBrowserState();
  renderFontBrowser();
}

function onFontListKey(e) {
  const fams = visibleFamilies();
  if (!fams.length) return;
  let idx = fams.findIndex(f => f.name === fb.selected);
  if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
    e.preventDefault();
    idx = idx < 0 ? 0 : Math.max(0, Math.min(fams.length - 1, idx + (e.key === 'ArrowDown' ? 1 : -1)));
    selectFontRow(fams[idx].name, null, true);
  } else if ((e.key === 'ArrowRight' || e.key === 'ArrowLeft') && idx >= 0) {
    e.preventDefault();
    const famEl = famElFor(fb.source, fams[idx].name);
    if (famEl) toggleFontFamilyOpen(famEl, e.key === 'ArrowRight');
  } else if (e.key === 'Enter' && idx >= 0) {
    e.preventDefault();
    applyFont();
  }
}

function initFontChooser() {
  const list = document.getElementById('fb-list');
  const classes = document.getElementById('fb-classes');
  if (!list || !classes) return;
  classes.innerHTML = FONT_CLASSES.map(([id, label]) =>
    `<button type="button" class="fb-class" role="radio" aria-checked="false" data-cls="${id}">${label}</button>`).join('');
  classes.addEventListener('click', (e) => {
    const btn = e.target.closest('.fb-class');
    if (!btn) return;
    fb.cls = btn.dataset.cls || '';
    saveFontBrowserState();
    renderFontBrowser();
  });
  list.addEventListener('click', (e) => {
    const famEl = e.target.closest('.fb-fam');
    const fam = famFromEl(famEl);
    if (!fam) return;
    if (e.target.closest('.fb-star')) { toggleFavoriteFont(fam.name); return; }
    if (e.target.closest('.fb-chev') && fam.faces.length > 1) { toggleFontFamilyOpen(famEl); return; }
    const styleRow = e.target.closest('.fb-style');
    selectFontRow(fam.name, styleRow ? Number(styleRow.dataset.face) : null);
    list.focus({ preventScroll: true });
  });
  list.addEventListener('dblclick', (e) => {
    if (e.target.closest('.fb-star, .fb-chev')) return;
    if (e.target.closest('.fb-row')) applyFont();
  });
  fb.selected = currentFont || DEFAULT_FONT;
  renderFontBrowser();
  previewFont(fb.selected);
  // Both lists load and are built during start-up, whichever tab is showing.
  loadAppFonts().then(() => loadSystemFonts());
}

window.addEventListener('storage', (e) => {
  if (e.key === 'lumiyaFont' && e.newValue !== null && e.newValue !== currentFont) {
    setAppFont(FONT_NAME_RE.test(e.newValue) ? e.newValue : '', false);
    fb.selected = currentFont || DEFAULT_FONT;
    renderFontBrowser();
    previewFont(fb.selected);
  }
  if (e.key === 'lumiyaTheme' && e.newValue && e.newValue !== currentTheme) {
    selectTheme(e.newValue, false);
  }
});

const PALETTE = ['#0f62fe', '#42be65', '#be95ff', '#3ddbd9', '#ff7eb6', '#f1c21b', '#ff832b'];
const DEP_INFO = {
  torch: "PyTorch: Core tensor & autograd engine used to backpropagate PGD perturbations through the VAE.",
  cuda: "NVIDIA CUDA Runtime: Hardware acceleration enabling FP16 Tensor Core execution on NVIDIA GPUs.",
  diffusers: "Hugging Face Diffusers: Provides the AutoencoderKL latent variational autoencoder architecture.",
  transformers: "Hugging Face Transformers: Model configuration and safetensors weight utilities.",
  pil: "Pillow: Image decoding, EXIF orientation transposition, steganography, and 4:4:4 JPEG encoding.",
  psutil: "psutil: System CPU, RAM, power, and thermal telemetry collector.",
  git: "Git: Version control & in-app self-update engine.",
  conda: "Miniconda3 / Anaconda3: Isolated Python environment manager."
};

const metricsCfg = {
  rate: { label: 'Step Throughput (Bars)', enabled: true,  color: '#0f62fe', type: 'bar',  dashed: false },
  gpu:  { label: 'GPU Load %',             enabled: true,  color: '#42be65', type: 'line', dashed: false },
  cpu:  { label: 'CPU Load %',             enabled: false, color: '#be95ff', type: 'line', dashed: false },
  ram:  { label: 'RAM Usage %',            enabled: false, color: '#3ddbd9', type: 'line', dashed: true  },
  vram: { label: 'VRAM Usage %',           enabled: false, color: '#ff7eb6', type: 'line', dashed: false },
  temp: { label: 'Temperature °C',         enabled: false, color: '#ff832b', type: 'line', dashed: true  },
  pwr:  { label: 'System Power (W)',       enabled: false, color: '#f1c21b', type: 'line', dashed: false }
};

const BINS = 60;
const histBuffers = {
  rate: new Array(BINS).fill(0),
  cpu:  new Array(BINS).fill(0),
  ram:  new Array(BINS).fill(0),
  gpu:  new Array(BINS).fill(0),
  vram: new Array(BINS).fill(0),
  temp: new Array(BINS).fill(0),
  pwr:  new Array(BINS).fill(0)
};

let discoveredAlgos = [];
let favoriteAlgos = [
  'photoguard', 'blurguard', 'diffusionguard', 'anti_inpainting', 'veto',
  'srim', 'metacloak', 'mist', 'antipure', 'decontext'
];
let algoLastUsed = {};
let allBatches = [];
let selectedBatchId = null;
let selectedOrgAlgoId = null;
let orgViewMode = 'doc';
let orgGridMode = false;
let orgNumMode = 'none';
let orgGridFadePending = false;
let defaultLayers = { photoguard: true, blurguard: false, diffusionguard: false, anti_inpainting: false, veto: false };
let defaultConvertPng = true;
let collapsedBatches = {};
let lastBatchesSig = '';
let lastAlgosSig = '';
let hwAdvisoryShown = false;
let missingDepsBannerShown = false;
let dragPayload = null;

