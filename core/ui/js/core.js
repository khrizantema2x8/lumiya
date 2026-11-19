// --listen mode prints the page link with ?token=; every API call carries it back, including <img>, beacon and stream URLs.
const API_TOKEN = new URLSearchParams(location.search).get('token') || '';
function apiUrl(url) {
  return API_TOKEN ? `${url}${url.includes('?') ? '&' : '?'}token=${encodeURIComponent(API_TOKEN)}` : url;
}

// All server calls go through here so a refused or unreachable request is shown instead of silently doing nothing.
async function api(url, opts) {
  let r;
  try {
    r = await fetch(apiUrl(url), opts);
  } catch (e) {
    showBanner('<strong>&#9650; Server unreachable:</strong> the Lumiya service did not answer. Check the terminal window.', true);
    throw e;
  }
  if (!r.ok) showBanner(`<strong>&#9650; Request refused:</strong> ${url.split('?')[0]} answered ${r.status}${r.status === 403 ? ' (open the page with the link printed in the terminal)' : ''}.`, true);
  return r;
}

let currentTheme = localStorage.getItem('lumiyaTheme') || 'carbon';
let loadedThemes = [];
let themesMap = {};
document.documentElement.setAttribute('data-theme', currentTheme);

function applyThemeVariables(colors) {
  if (!colors || typeof colors !== 'object') return;
  const root = document.documentElement;
  for (const [k, v] of Object.entries(colors)) {
    if (k.startsWith('--')) {
      root.style.setProperty(k, v);
    }
  }
}

function selectTheme(themeId, shouldSave = true) {
  currentTheme = themeId;
  document.documentElement.setAttribute('data-theme', themeId);
  localStorage.setItem('lumiyaTheme', themeId);

  if (themesMap[themeId] && themesMap[themeId].colors) {
    applyThemeVariables(themesMap[themeId].colors);
  }

  loadedThemes.forEach(t => {
    const el = document.getElementById('theme-card-' + t.id);
    if (el) el.classList.toggle('active', t.id === themeId);
  });

  if (shouldSave) {
    api('/api/save_config', {
      method: 'POST',
      body: JSON.stringify({ theme: themeId })
    }).catch(() => {});
  }

  if (typeof renderInspectStage === 'function') {
    const inspPage = document.getElementById('page-insp');
    if (inspPage && inspPage.classList.contains('active')) {
      renderInspectStage();
    }
  }
}

function renderThemeCards() {
  const grid = document.getElementById('theme-selector-grid');
  if (!grid) return;
  grid.innerHTML = loadedThemes.map(t => {
    const isActive = t.id === currentTheme;
    const thumbUrl = t.thumbnail || `/identity/theme/${t.id}.jpg`;
    return `
      <div class="theme-card ${isActive ? 'active' : ''}" id="theme-card-${escapeHtml(t.id)}" onclick="selectTheme('${escapeHtml(t.id)}')">
        <div class="theme-preview-box">
          <img src="${escapeHtml(thumbUrl)}" alt="${escapeHtml(t.name)} Theme Preview" onerror="this.onerror=null; this.src='/identity/media/workspace.png'">
        </div>
        <div class="theme-name">${escapeHtml(t.name)}</div>
      </div>
    `;
  }).join('');
}

async function fetchThemes(forceRefresh = false) {
  try {
    const url = forceRefresh ? `/api/themes?_t=${Date.now()}` : '/api/themes';
    const res = await api(url);
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const data = await res.json();
    if (data && data.ok && Array.isArray(data.themes) && data.themes.length > 0) {
      loadedThemes = data.themes;
      themesMap = {};
      loadedThemes.forEach(t => { themesMap[t.id] = t; });
      renderThemeCards();

      if (themesMap[currentTheme]) {
        selectTheme(currentTheme, false);
      } else if (loadedThemes[0]) {
        selectTheme(loadedThemes[0].id, false);
      }
    }
  } catch (err) {
    console.warn('Could not load dynamic themes:', err);
  }
}

function toggleThemePanel(e) {
  if (e.target.closest('#btn-reload-themes')) return;
  const panel = document.getElementById('themes-panel');
  if (panel) panel.classList.toggle('collapsed');
}

function reloadThemes(e) {
  if (e) e.stopPropagation();
  const icon = document.getElementById('reload-themes-icon');
  if (icon) {
    icon.classList.add('spinning');
    setTimeout(() => icon.classList.remove('spinning'), 500);
  }
  fetchThemes(true);
}

