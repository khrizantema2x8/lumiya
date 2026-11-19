function toggleHistoryBatch(batchId) {
  if (!batchId) return;
  const collapse = collapsedHistoryBatches[batchId] === false;
  collapsedHistoryBatches[batchId] = collapse;
  // Flip classes on the rows already in the table, so the CSS transition can push them open or shut.
  document.querySelectorAll('#history-rows tr[data-batch]').forEach(r => {
    if (r.dataset.batch !== batchId) return;
    if (r.classList.contains('hist-file-row')) r.classList.toggle('hist-row-collapsed', collapse);
    else r.querySelector('.batch-arrow').classList.toggle('collapsed', collapse);
  });
}

function renderHistoryTable(historyArr) {
  const histEl = document.getElementById('history-rows');
  if (!histEl) return;
  latestHistoryList = Array.isArray(historyArr) ? historyArr : [];
  if (latestHistoryList.length === 0) {
    histEl.innerHTML = `
      <tr>
        <td colspan="7" style="padding:28px 16px;">
          <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;color:var(--muted);">
            <div class="sad-face-glyph" style="width:64px;height:64px;font-size:32px;margin-bottom:10px;">:(</div>
            <div style="font-size:13px;color:var(--dim);font-style:italic;">
              You wouldn&rsquo;t wanna walk barefoot don&rsquo;t ya?
            </div>
          </div>
        </td>
      </tr>
    `;
    return;
  }

  const batchGroups = [];
  const groupMap = {};
  latestHistoryList.forEach(item => {
    const bId = item.batch || 'unassigned';
    if (!groupMap[bId]) {
      groupMap[bId] = [];
      batchGroups.push({ batchId: bId, items: groupMap[bId] });
    }
    groupMap[bId].push(item);
  });

  const rowsHtml = [];
  batchGroups.forEach(grp => {
    const bId = grp.batchId;
    const items = grp.items;
    const isCol = collapsedHistoryBatches[bId] !== false;
    const psnrVals = items.map(x => parseFloat(x.psnr)).filter(v => !isNaN(v));
    const shiftVals = items.map(x => parseFloat(x.shift)).filter(v => !isNaN(v));
    const avgPsnr = psnrVals.length ? (psnrVals.reduce((a, b) => a + b, 0) / psnrVals.length).toFixed(1) : '—';
    const maxShift = shiftVals.length ? Math.max(...shiftVals).toFixed(1) : '—';
    const latestTime = items[0] && items[0].time ? items[0].time : '—';

    rowsHtml.push(`
      <tr class="hist-batch-row" data-batch="${escapeHtml(bId)}" onclick="toggleHistoryBatch(this.dataset.batch)">
        <td class="mono">
          <span class="batch-arrow ${isCol ? 'collapsed' : ''}" style="margin-right:4px;">&#9662;</span>
          <strong style="color:var(--gold);">${escapeHtml(bId)}</strong>
          <span style="color:var(--dim);font-size:11px;margin-left:6px;">[${items.length} file${items.length === 1 ? '' : 's'}]</span>
        </td>
        <td></td>
        <td class="mono" style="color:var(--gold);">Avg ${avgPsnr} dB</td>
        <td class="mono" style="color:var(--muted);">Max ${maxShift} / 255</td>
        <td class="mono" style="color:var(--dim);font-size:11px;">${escapeHtml(latestTime)}</td>
        <td></td>
        <td><button class="q-btn" data-batch="${escapeHtml(bId)}" onclick="event.stopPropagation();openResultFolder(this.dataset.batch)" title="Open Batch Folder in Explorer" aria-label="Open Batch Folder"><svg viewBox="0 0 16 16" width="14" height="14" fill="currentColor" aria-hidden="true"><path d="M1 3h5l2 2h7v8H1z"/></svg></button></td>
      </tr>
    `);

    // Collapsed rows stay in the table at zero height, so expanding and collapsing can animate.
    const cell = html => `<div class="hist-cell"><div class="hist-cell-in">${html}</div></div>`;
    items.forEach((r, idx) => {
      const branchChar = (idx === items.length - 1) ? '&#9492;&#9472;' : '&#9500;&#9472;';
      rowsHtml.push(`
        <tr class="hist-file-row${isCol ? ' hist-row-collapsed' : ''}" data-batch="${escapeHtml(bId)}">
          <td class="mono" title="${escapeHtml(r.name)}" style="padding-left:28px;">
            ${cell(`<span style="color:var(--dim);margin-right:6px;">${branchChar}</span>${formatQueueFileName(r.name, 40)}`)}
          </td>
          <td class="mono">${cell(escapeHtml(r.size))}</td>
          <td class="mono">${cell(`${escapeHtml(r.psnr)} dB`)}</td>
          <td class="mono">${cell(`${escapeHtml(r.shift)} / 255`)}</td>
          <td class="mono" style="color:var(--dim);font-size:11px;">${cell(escapeHtml(r.time || '—'))}</td>
          <td>${cell('<span class="tag">Done</span>')}</td>
          <td>${cell(`<button class="q-btn" data-batch="${escapeHtml(r.batch)}" onclick="openResultFolder(this.dataset.batch)" title="Open in Explorer" aria-label="Open in Explorer"><svg viewBox="0 0 16 16" width="14" height="14" fill="currentColor" aria-hidden="true"><path d="M1 3h5l2 2h7v8H1z"/></svg></button>`)}</td>
        </tr>
      `);
    });
  });

  histEl.innerHTML = rowsHtml.join('');
}

function renderIntegrityReport(rep) {
  if (!rep) return;
  integrityLoadedOnce = true;
  const msgEl = document.getElementById('upd-state-msg');
  const tagEl = document.getElementById('upd-manifest-tag');
  const lumpBody = document.getElementById('integrity-lump-rows');
  const fileBody = document.getElementById('integrity-file-rows');

  if (msgEl) {
    const mismatchCount = (rep.mismatches || []).length;
    if (rep.ok) {
      msgEl.innerHTML = `<span style="color:var(--green);">&#10004; You're good!</span>`;
    } else {
      msgEl.innerHTML = `<span style="color:var(--yellow);">&#9650; ${mismatchCount} modified file(s) detected.</span>`;
    }
  }
  if (tagEl) {
    tagEl.innerText = rep.ok ? 'Verified' : 'Modified';
    tagEl.style.cssText = rep.ok ? '' : 'border-color:var(--yellow);color:var(--yellow);background:#302605;';
  }

  const formatStatus = st => {
    if (!st) return '';
    if (st === 'VERIFIED') return 'Verified';
    if (st === 'MODIFIED') return 'Modified';
    return st.charAt(0).toUpperCase() + st.slice(1).toLowerCase();
  };

  if (lumpBody && rep.lumpSums) {
    const order = ['master', 'core', 'scripts'];
    lumpBody.innerHTML = order.map(k => {
      const item = rep.lumpSums[k];
      if (!item) return '';
      const ok = item.status === 'VERIFIED';
      const stStyle = ok ? '' : 'border-color:var(--yellow);color:var(--yellow);background:#302605;';
      return `
        <tr>
          <td class="mono"><strong>${escapeHtml(item.key)}</strong></td>
          <td class="mono">${item.count}</td>
          <td class="mono" style="font-size:11px;word-break:break-all;">${escapeHtml(item.sha256)}</td>
          <td class="mono" style="font-size:11px;">${escapeHtml(item.md5)}</td>
          <td><span class="tag" style="${stStyle}">${escapeHtml(formatStatus(item.status))}</span></td>
        </tr>
      `;
    }).join('');
  }

  if (fileBody && Array.isArray(rep.files)) {
    fileBody.innerHTML = rep.files.map(f => {
      const ok = f.status === 'VERIFIED';
      const stStyle = ok ? '' : 'border-color:var(--yellow);color:var(--yellow);background:#302605;';
      return `
        <tr>
          <td class="mono" style="font-size:11px;color:var(--gold);">${escapeHtml(f.pillar)}</td>
          <td class="mono" style="font-size:11px;">${escapeHtml(f.path)}</td>
          <td class="mono" style="font-size:10px;word-break:break-all;">${escapeHtml(f.sha256)}</td>
          <td class="mono" style="font-size:10px;">${escapeHtml(f.md5)}</td>
          <td><span class="tag" style="${stStyle}">${escapeHtml(formatStatus(f.status))}</span></td>
        </tr>
      `;
    }).join('');
  }
}

async function verifyProgramIntegrity() {
  const msgEl = document.getElementById('upd-state-msg');
  if (msgEl) msgEl.innerText = 'Checking files...';
  const r = await api('/api/system_maint?cmd=verify_integrity', { method: 'POST' });
  const d = await r.json();
  if (d.integrity) renderIntegrityReport(d.integrity);
  else if (d.error) showBanner(`<strong>&#9650; Integrity Check:</strong> ${escapeHtml(d.error)}`, true);
}

async function checkForUpdates() {
  const msgEl = document.getElementById('upd-state-msg');
  const updBtn = document.getElementById('btn-self-update');
  if (updBtn) {
    updBtn.disabled = true;
    updBtn.title = "Checking for updates...";
  }
  if (msgEl) msgEl.innerText = 'Checking GitHub...';
  const r = await api('/api/system_maint?cmd=check_update', { method: 'POST' });
  const d = await r.json();
  if (d.integrity) renderIntegrityReport(d.integrity);
  if (!d.ok) {
    if (msgEl) msgEl.innerHTML = `<span style="color:var(--red);">&#10008; ${escapeHtml(d.error || 'Update check failed.')}</span>`;
    if (updBtn) updBtn.title = "Update check failed";
    showBanner(`<strong>&#9650; Update Check:</strong> ${escapeHtml(d.error || 'Could not reach GitHub.')}`, true);
    return;
  }
  let statusStr = '';
  if (d.updateAvailable) {
    statusStr = `<span style="color:var(--gold);">&#9650; Update available:</span> <code>${escapeHtml(d.localVersion || d.localSha)}</code> &rarr; <code>${escapeHtml(d.remoteVersion || d.remoteSha)}</code>`;
    if (updBtn) {
      updBtn.disabled = false;
      updBtn.title = `Update to ${d.remoteVersion || d.remoteSha}`;
    }
  } else if (d.versionAhead && d.localVersion && d.remoteVersion && d.localVersion !== d.remoteVersion) {
    statusStr = `<span style="color:var(--green);">&#10004; Local build (<code>${escapeHtml(d.localVersion)}</code>) is ahead of GitHub (<code>${escapeHtml(d.remoteVersion)}</code> / <code>${escapeHtml(d.remoteSha)}</code>).</span>`;
    if (updBtn) updBtn.title = "Local build is ahead of GitHub";
  } else if (d.aheadOfRemote || (d.aheadCount && d.aheadCount > 0)) {
    statusStr = `<span style="color:var(--green);">&#10004; Local build (<code>${escapeHtml(d.localSha)}</code>) is ${d.aheadCount} commit(s) ahead of GitHub (<code>${escapeHtml(d.remoteSha)}</code>).</span>`;
    if (updBtn) updBtn.title = "Local build is ahead of GitHub";
  } else {
    statusStr = `<span style="color:var(--green);">&#10004; Up to date (<code>${escapeHtml(d.localVersion || d.localSha)}</code>).</span>`;
    if (updBtn) updBtn.title = "Already up to date";
  }
  if (msgEl) msgEl.innerHTML = statusStr;
}

async function triggerSelfUpdate() {
  const updBtn = document.getElementById('btn-self-update');
  if (updBtn && updBtn.disabled) return;
  if (updBtn) updBtn.disabled = true;
  const msgEl = document.getElementById('upd-state-msg');
  if (msgEl) msgEl.innerText = 'Updating from GitHub...';
  const r = await api('/api/system_maint?cmd=self_update', { method: 'POST' });
  const d = await r.json();
  if (d.integrity) renderIntegrityReport(d.integrity);
  if (!d.ok) {
    if (msgEl) msgEl.innerHTML = `<span style="color:var(--red);">&#10008; ${escapeHtml(d.error || 'Update failed.')}</span>`;
    showBanner(`<strong>&#9650; Update Failed:</strong> ${escapeHtml(d.error || 'Update failed')}`, true);
    return;
  }
  const msg = d.message || d.msg || 'Up to date.';
  if (msgEl) msgEl.innerHTML = `<span style="color:var(--green);">&#10004; ${escapeHtml(msg)}</span>`;
  showBanner(`<strong>&#10004; Update:</strong> ${escapeHtml(msg)}`, false);
  if (d.updated) {
    setTimeout(() => window.location.reload(), 1500);
  }
}

let cfgFormHydrated = false;
const sse = new EventSource(apiUrl('/api/stream'));
sse.onmessage = (e) => {
  const d = JSON.parse(e.data);
  if (d.bounds && !serverBoundsApplied) applyServerBounds(d.bounds, d.computeLevels);
  if (d.appVersion) {
    document.getElementById('hdr-version').innerText = d.appVersion;
    const aboutVer = document.getElementById('about-version-line');
    if (aboutVer) aboutVer.innerText = `Version ${d.appVersion} (64-bit)`;
  }
  if (d.resultsRoot) document.getElementById('folder').innerText = d.resultsRoot;
  document.getElementById('s-cpu').innerText = d.hw.cpu.toFixed(1) + '%';
  document.getElementById('s-ram').innerText = d.hw.ram.toFixed(1) + '%';
  const ramSub = document.getElementById('s-ram-sub');
  if (ramSub) {
    ramSub.innerText = (d.hw.ramTotal > 0) ? `${d.hw.ramUsed.toFixed(1)} / ${d.hw.ramTotal.toFixed(1)} GB` : '';
  }
  document.getElementById('s-gpu-name').innerText = 'GPU (' + d.hw.gpuName + ')';
  document.getElementById('s-gpu').innerText = d.hw.gpu.toFixed(0) + '%';
  document.getElementById('s-vram').innerText = d.hw.vramUsed.toFixed(1) + ' / ' + d.hw.vramTotal.toFixed(1) + ' GB';
  document.getElementById('s-temp-label').innerText = d.hw.tempSensorLabel || 'TEMP';

  if (d.hw.tempC > 0) {
    document.getElementById('s-temp-c').innerHTML = `${d.hw.tempC.toFixed(0)}&deg;C`;
    document.getElementById('s-temp-f').innerHTML = `${d.hw.tempF.toFixed(0)}&deg;F`;
  } else {
    document.getElementById('s-temp-c').innerHTML = `--&deg;C`;
    document.getElementById('s-temp-f').innerHTML = `--&deg;F`;
  }

  const pwrW = d.hw.powerW || 0;
  const sPwr = document.getElementById('s-pwr');
  if (sPwr) sPwr.innerText = `${pwrW.toFixed(1)} W`;
  const sPwrLbl = document.getElementById('s-pwr-label');
  if (sPwrLbl) sPwrLbl.innerText = d.hw.powerLabel || 'SYS POWER (EST)';

  let favOrLastChanged = false;
  if (d.cfg) {
    if (!cfgFormHydrated) {
      cfgFormHydrated = true;
      const cfgFields = [
        ['c-backend', d.cfg.computeBackend],
        ['c-poll', d.cfg.pollMs],
        ['c-dim', d.cfg.workingDim],
        ['c-prec', d.cfg.precision],
        ['c-twarn', d.cfg.tempWarnC],
        ['c-tcrit', d.cfg.tempCritC],
        ['c-jpeg', d.cfg.jpegQuality],
      ];
      cfgFields.forEach(([id, val]) => {
        const el = document.getElementById(id);
        if (el && val !== undefined && document.activeElement !== el) {
          el.value = String(val);
        }
      });
      if (typeof onBackendSelectChange === 'function') onBackendSelectChange();
    }
    if (!localStorage.getItem('lumiyaTheme') && d.cfg.theme && d.cfg.theme !== currentTheme) {
      selectTheme(d.cfg.theme, false);
    }
    if (localStorage.getItem('lumiyaFont') === null && typeof d.cfg.fontFamily === 'string' && FONT_NAME_RE.test(d.cfg.fontFamily) && d.cfg.fontFamily !== currentFont) {
      setAppFont(d.cfg.fontFamily, false);
      fb.selected = currentFont;
      renderFontBrowser();
      previewFont(fb.selected);
    }
    if (!favoriteFontsHydrated && Array.isArray(d.cfg.favoriteFonts)) {
      favoriteFontsHydrated = true;
      favoriteFonts = d.cfg.favoriteFonts.filter(n => typeof n === 'string' && FONT_NAME_RE.test(n));
      renderFontBrowser();
    }
    if (d.cfg.convertPng !== undefined) {
      defaultConvertPng = !!d.cfg.convertPng;
    }
    if (d.cfg.allowRamSpillover !== undefined) {
      const ramSpillEl = document.getElementById('c-ram-spill');
      if (ramSpillEl && document.activeElement !== ramSpillEl) ramSpillEl.checked = !!d.cfg.allowRamSpillover;
    }
    if (d.cfg.autoPaperDefaults !== undefined) {
      const autoPaperEl = document.getElementById('c-auto-paper');
      if (autoPaperEl && document.activeElement !== autoPaperEl) autoPaperEl.checked = !!d.cfg.autoPaperDefaults;
    }
    if (Array.isArray(d.cfg.favoriteAlgos) && d.cfg.favoriteAlgos.length > 0) {
      const nextFavSig = d.cfg.favoriteAlgos.join(',');
      if (nextFavSig !== favoriteAlgos.join(',')) {
        favoriteAlgos = d.cfg.favoriteAlgos;
        favOrLastChanged = true;
      }
    }
    if (Date.now() > hwSyncHoldUntil && overrideHardware !== !!d.cfg.overrideHardware) {
      overrideHardware = !!d.cfg.overrideHardware;
      renderHardwareOverride();
    }
    if (d.cfg.algoLastUsed) {
      algoLastUsed = d.cfg.algoLastUsed;
    }
  }

  // Debug Bar visibility
  document.getElementById('debug-bar').classList.toggle('visible', !!d.ui.debugMode);
  document.getElementById('dbg-state-lbl').innerText = `Emulator: ${d.ui.emulateExecution ? 'ACTIVE (No GPU Required)' : 'OFF'}`;

  // Red Notification when Major Dependencies are Missing
  if (!d.majorReady && !missingDepsBannerShown) {
    missingDepsBannerShown = true;
    showBanner(
      '<strong>&#9650; Major Dependencies Missing:</strong> Core compute packages (PyTorch, Diffusers, or Pillow) are missing. Open the <strong>Configuration</strong> tab to inspect missing packages and run <code>install.bat</code>.',
      true
    );
  }

  if (!hwAdvisoryShown && d.deps && d.deps.hardwareAdvisory && d.majorReady) {
    hwAdvisoryShown = true;
    document.getElementById('hw-advisory-text').innerText =
      d.deps.advisoryReason ||
      "No CUDA-accelerable hardware detected. Running this program on non-CUDA accelerated platform will be considerably slower. Consider changing the platform or continue and accept less optimal performance.";
    document.getElementById('hw-advisory-modal').classList.add('open');
  }

  if (d.algos) {
    discoveredAlgos = d.algos;
    syncUnifiedBoxUI();
    renderOrganizeTab();
  } else if (favOrLastChanged) {
    syncUnifiedBoxUI();
    renderOrganizeTab();
  }

  const vramPct = d.hw.vramTotal > 0 ? (d.hw.vramUsed / d.hw.vramTotal) * 100 : 0;
  document.getElementById('w-cpu').classList.toggle('active', d.hw.cpu >= d.cfg.loadWarnPct);
  document.getElementById('w-ram').classList.toggle('active', d.hw.ram >= d.cfg.loadWarnPct);
  document.getElementById('w-gpu').classList.toggle('active', d.hw.gpu >= d.cfg.loadWarnPct);
  document.getElementById('w-vram').classList.toggle('active', vramPct >= d.cfg.loadWarnPct);
  const wPwr = document.getElementById('w-pwr');
  if (wPwr) wPwr.classList.toggle('active', pwrW >= 115.0);

  const wTemp = document.getElementById('w-temp');
  const popTemp = document.getElementById('pop-temp');
  const warnC = Math.round(d.cfg.tempWarnC ?? 62);
  const critC = Math.round(d.cfg.tempCritC ?? 85);
  if (d.hw.tempState === 'erratic') {
    wTemp.classList.add('active');
    popTemp.className = 'sensor-popover' + (popTemp.classList.contains('open') ? ' open' : '');
    popTemp.innerHTML = '<strong>&#9650; Erratic Thermal Sensor</strong><br>Temperature readings are fluctuating rapidly.';
    showBanner(
      '<strong>&#9650; Erratic Thermal Sensor:</strong> Temperature readings are fluctuating rapidly. Make sure your computer cooling system is in working order.',
      false
    );
  } else if (d.hw.tempState === 'crit') {
    wTemp.className = 'warn-tri active crit';
    popTemp.className = 'sensor-popover crit' + (popTemp.classList.contains('open') ? ' open' : '');
    popTemp.innerHTML = `<strong>&#9650; Critical Thermal Throttling (&gt;${critC}&deg;C)</strong><br>Sustained critical temperature detected. Hardware is actively throttling clock speeds; improve ventilation and make sure your computer cooling system is in working order.`;
  } else if (d.hw.tempState === 'warn') {
    wTemp.className = 'warn-tri active';
    popTemp.className = 'sensor-popover' + (popTemp.classList.contains('open') ? ' open' : '');
    popTemp.innerHTML = `<strong>&#9650; Elevated Thermal Load (&gt;${warnC}&deg;C)</strong><br>Sustained compute load is raising hardware temperatures. Ensure adequate workspace ventilation.`;
  } else {
    wTemp.className = 'warn-tri';
  }

  histBuffers.rate.push(d.ui.stepRate || 0); histBuffers.rate.shift();
  histBuffers.cpu.push(d.hw.cpu);            histBuffers.cpu.shift();
  histBuffers.ram.push(d.hw.ram);            histBuffers.ram.shift();
  histBuffers.gpu.push(d.hw.gpu);            histBuffers.gpu.shift();
  histBuffers.vram.push(vramPct);            histBuffers.vram.shift();
  histBuffers.temp.push(d.hw.tempC);         histBuffers.temp.shift();
  histBuffers.pwr.push(pwrW);                histBuffers.pwr.shift();

  drawSensorSparkline('bg-cpu', histBuffers.cpu, metricsCfg.cpu.color, 100.0);
  drawSensorSparkline('bg-ram', histBuffers.ram, metricsCfg.ram.color, 100.0);
  drawSensorSparkline('bg-gpu', histBuffers.gpu, metricsCfg.gpu.color, 100.0);
  drawSensorSparkline('bg-vram', histBuffers.vram, metricsCfg.vram.color, 100.0);
  drawSensorSparkline('bg-temp', histBuffers.temp, metricsCfg.temp.color, 100.0);
  drawSensorSparkline('bg-pwr', histBuffers.pwr, metricsCfg.pwr.color, 180.0);
  drawMainGraph();

  document.getElementById('p-speed').innerText = (d.ui.stepRate || 0).toFixed(1) + ' steps/s';
  const pct = d.ui.steps > 0 ? (d.ui.step / d.ui.steps) * 100 : 0;
  document.getElementById('p-bar').style.width = pct.toFixed(1) + '%';

  if (d.ui.busy) {
    document.getElementById('p-text').innerText =
      `Batch [${d.ui.activeBatch}] — [${d.ui.idx}/${d.ui.total}] ${d.ui.file} (${d.ui.step}/${d.ui.steps})`;
    const m = Math.floor(d.ui.eta / 60).toString().padStart(2, '0');
    const s = Math.floor(d.ui.eta % 60).toString().padStart(2, '0');
    document.getElementById('p-eta').innerText = `ETA: ${m}:${s}`;
  } else {
    document.getElementById('p-text').innerText = 'Idle — select or run a batch in queue';
    document.getElementById('p-eta').innerText = 'ETA: 00:00';
  }

  renderQueueTree(d.batches || allBatches, d.ui.busy, d.ui.activeBatch, d.majorReady);

  // History Table (Batch-Tree Grouped, Collapsible & Expandable in One Table)
  const histSig = JSON.stringify(d.ui.history || []);
  if (histSig !== lastHistorySig) {
    lastHistorySig = histSig;
    renderHistoryTable(d.ui.history || []);
  }

  // Configuration Dependency List + Recommended Version Matrix
  const depsEl = document.getElementById('deps-list');
  const depsSig = JSON.stringify(d.deps || {});
  if (depsEl && d.deps && depsSig !== lastDepsSig) {
    lastDepsSig = depsSig;
    const depLabels = { torch: 'PyTorch', cuda: 'CUDA', diffusers: 'Diffusers', transformers: 'Transformers', pil: 'Pillow', psutil: 'psutil', git: 'Git', conda: 'Conda' };
    const keys = ['torch', 'cuda', 'diffusers', 'transformers', 'pil', 'psutil', 'git', 'conda'];
    depsEl.innerHTML = keys.map(k => {
      const rec = (d.deps.recommended && d.deps.recommended[k]) || 'Latest';
      const curVer = (d.deps.versions && d.deps.versions[k]) || (d.deps[k] ? 'Detected' : 'Missing');
      const label = depLabels[k] || (k.charAt(0).toUpperCase() + k.slice(1));
      return `
        <div class="cfg-row">
          <div class="label-group">
            <span class="mono">${label}</span>
            <span class="info-icon">i
              <span class="info-tooltip">${DEP_INFO[k]}</span>
            </span>
            <span style="font-size:11px;color:var(--dim);font-family:var(--font-sans);">
              (Rec: ${rec} | Found: ${curVer})
            </span>
          </div>
          <span class="tag" style="${d.deps[k] ? '' : 'border-color:var(--red);color:var(--red);background:#351013;'}">
            ${d.deps[k] ? 'Verified' : 'Missing'}
          </span>
        </div>
      `;
    }).join('');
  }
};

// Initial Theme Card UI Sync & Dynamic Themes Loader
selectTheme(currentTheme, false);
fetchThemes();
initFontChooser();
