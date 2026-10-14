// ============================================================
// CONFIG
// ============================================================

const API_BASE = 'http://localhost:8000';

// ============================================================
// THEME
// ============================================================

function applyTheme(isDark) {
  const html = document.documentElement;
  if (isDark) {
    html.classList.add('dark');
    html.classList.remove('light');
  } else {
    html.classList.add('light');
    html.classList.remove('dark');
  }
  const btn = document.getElementById('themeBtn');
  if (btn) btn.textContent = isDark ? '☀️' : '🌙';
  localStorage.setItem('soilgpt_theme', isDark ? 'dark' : 'light');
}

function toggleTheme() {
  const isDark = document.documentElement.classList.contains('dark');
  applyTheme(!isDark);
}

// ============================================================
// NAVIGATION
// ============================================================

function navigateTo(pageId) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));

  const page = document.getElementById('page-' + pageId);
  if (page) page.classList.add('active');

  const navItem = document.querySelector(`.nav-item[data-page="${pageId}"]`);
  if (navItem) navItem.classList.add('active');

  localStorage.setItem('soilgpt_page', pageId);

  const sidebar = document.getElementById('sidebar');
  if (sidebar && window.innerWidth <= 900) {
    sidebar.classList.remove('open');
  }
}

function toggleSidebar() {
  const sidebar = document.getElementById('sidebar');
  if (sidebar) sidebar.classList.toggle('open');
}

// ============================================================
// STATE
// ============================================================

let state = {
  analyses: [],
  currentResult: null
};

const STORAGE_KEY = 'soilgpt_state_v1';

function saveState() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch (e) {
    console.error('Save failed:', e);
  }
}

function loadState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      state = { ...state, ...parsed };
    }
  } catch (e) {
    console.error('Load failed:', e);
  }
}

// ============================================================
// FETCH SOIL DATA
// ============================================================

async function fetchSoilData(location) {
  const url = `${API_BASE}/analyze?location=${encodeURIComponent(location)}`;
  const response = await fetch(url);

  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(err.detail || `HTTP ${response.status}`);
  }

  return await response.json();
}

// ============================================================
// HELPERS
// ============================================================

function escapeHtml(s) {
  const div = document.createElement('div');
  div.textContent = s || '';
  return div.innerHTML;
}

function pickTop(prop) {
  if (!prop || typeof prop !== 'object') return null;
  if (prop["0-5cm"] !== undefined) return prop["0-5cm"];
  const keys = Object.keys(prop);
  return keys.length ? prop[keys[0]] : null;
}

function getPhStatus(ph) {
  if (ph === null || ph === undefined || isNaN(ph)) {
    return { label: 'Unknown', className: 'unknown' };
  }
  if (ph < 5.5) return { label: 'Strongly Acidic', className: 'strongly-acidic' };
  if (ph < 6.5) return { label: 'Acidic', className: 'acidic' };
  if (ph < 7.5) return { label: 'Neutral', className: 'neutral' };
  if (ph < 8.5) return { label: 'Alkaline', className: 'alkaline' };
  return { label: 'Strongly Alkaline', className: 'strongly-alkaline' };
}

function formatSoilValue(name, value) {
  if (value === null || value === undefined) return '--';
  const maps = {
    phh2o:    { unit: '',         decimals: 2 },
    nitrogen: { unit: ' g/kg',    decimals: 2 },
    soc:      { unit: ' g/kg',    decimals: 2 },
    cec:      { unit: ' cmol/kg', decimals: 2 },
    clay:     { unit: '%',        decimals: 1 },
    sand:     { unit: '%',        decimals: 1 },
    silt:     { unit: '%',        decimals: 1 },
  };
  const cfg = maps[name] || { unit: '', decimals: 2 };
  return `${Number(value).toFixed(cfg.decimals)}${cfg.unit}`;
}

function barPercent(name, value) {
  if (value === null || value === undefined) return 0;
  const maxes = {
    phh2o: 14, nitrogen: 5, soc: 50, cec: 60,
    clay: 100, sand: 100, silt: 100,
  };
  const max = maxes[name] || 100;
  return Math.min(100, (value / max) * 100);
}

// ============================================================
// RENDER SOIL RESULT
// ============================================================

function renderSoilResult(data) {
  const page = document.getElementById('page-analyze');
  if (!page) return;

  const oldResult = document.getElementById('soilResult');
  if (oldResult) oldResult.remove();

  const live = data.live || {};
  const ref = data.reference || {};

  const moisture = live.soil_moisture_0_1cm;
  const temp0 = live.soil_temperature_0cm;
  const temp6 = live.soil_temperature_6cm;

  const moisturePct = moisture !== null && moisture !== undefined
    ? Math.min(100, (moisture / 0.5) * 100)
    : 0;

  const tempPct = temp0 !== null && temp0 !== undefined
    ? Math.min(100, Math.max(0, ((temp0 + 5) / 55) * 100))
    : 0;

  const result = document.createElement('div');
  result.id = 'soilResult';
  result.className = 'card';
  result.style.marginTop = '20px';

  result.innerHTML = `
    <div class="card-header">
      <h2>Soil Health Report — ${escapeHtml(data.location || 'Unknown')}</h2>
      <span style="font-size:11px;color:var(--text-faint);">
        ${data.lat && data.lon ? `${Number(data.lat).toFixed(3)}, ${Number(data.lon).toFixed(3)}` : ''}
        ${live.reading_time ? ' · ' + live.reading_time : ''}
      </span>
    </div>

    <!-- LIVE DATA -->
    <div style="margin-bottom:22px;">
      <div style="font-size:11px;text-transform:uppercase;letter-spacing:0.1em;color:var(--text-faint);font-weight:700;margin-bottom:14px;">
        📡 Live Soil Data
      </div>

      <div class="soil-grid">
        <div class="soil-item">
          <div class="soil-item-label">Soil Moisture (0–1 cm)</div>
          <div class="soil-item-value">${moisture !== null && moisture !== undefined ? (moisture * 100).toFixed(1) + '%' : '--'}</div>
          <div class="soil-item-bar"><div class="soil-item-fill" style="width:${moisturePct}%"></div></div>
        </div>

        <div class="soil-item">
          <div class="soil-item-label">Soil Temperature (0 cm)</div>
          <div class="soil-item-value">${temp0 !== null && temp0 !== undefined ? temp0.toFixed(1) + ' °C' : '--'}</div>
          <div class="soil-item-bar"><div class="soil-item-fill" style="width:${tempPct}%"></div></div>
        </div>

        <div class="soil-item">
          <div class="soil-item-label">Soil Temperature (6 cm)</div>
          <div class="soil-item-value">${temp6 !== null && temp6 !== undefined ? temp6.toFixed(1) + ' °C' : '--'}</div>
          <div class="soil-item-bar"><div class="soil-item-fill" style="width:${temp0 !== null ? tempPct : 0}%"></div></div>
        </div>
      </div>
    </div>

    <!-- REFERENCE DATA -->
    <div style="margin-bottom:22px;">
      <div style="font-size:11px;text-transform:uppercase;letter-spacing:0.1em;color:var(--text-faint);font-weight:700;margin-bottom:14px;">
        📚 Regional Soil Reference (ICAR)
      </div>

      <div style="background:var(--bg-subtle);padding:16px;border-radius:10px;border:1px solid var(--border);">
        <div class="info-row" style="padding:8px 0;">
          <div class="info-label" style="width:130px;">Soil Type</div>
          <div class="info-value">${escapeHtml(ref.soil_type || '--')}</div>
        </div>
        <div class="info-row" style="padding:8px 0;">
          <div class="info-label" style="width:130px;">pH Range</div>
          <div class="info-value">${escapeHtml(ref.ph_range || '--')}</div>
        </div>
        <div class="info-row" style="padding:8px 0;">
          <div class="info-label" style="width:130px;">Organic Carbon</div>
          <div class="info-value">${escapeHtml(ref.organic_carbon || '--')}</div>
        </div>
        <div class="info-row" style="padding:8px 0;">
          <div class="info-label" style="width:130px;">Nitrogen</div>
          <div class="info-value">${escapeHtml(ref.nitrogen || '--')}</div>
        </div>
        <div class="info-row" style="padding:8px 0;">
          <div class="info-label" style="width:130px;">Phosphorus</div>
          <div class="info-value">${escapeHtml(ref.phosphorus || '--')}</div>
        </div>
        <div class="info-row" style="padding:8px 0;">
          <div class="info-label" style="width:130px;">Potassium</div>
          <div class="info-value">${escapeHtml(ref.potassium || '--')}</div>
        </div>
        <div class="info-row" style="padding:8px 0;">
          <div class="info-label" style="width:130px;">Deficiencies</div>
          <div class="info-value">${escapeHtml(ref.deficiencies || '--')}</div>
        </div>
      </div>
    </div>

    <!-- RECOMMENDATION -->
    ${ref.recommendation ? `
    <div style="margin-bottom:22px;">
      <div style="font-size:11px;text-transform:uppercase;letter-spacing:0.1em;color:var(--text-faint);font-weight:700;margin-bottom:10px;">
        💡 Recommendation
      </div>
      <div style="background:var(--accent-bg);padding:16px;border-radius:10px;border-left:3px solid var(--accent);color:var(--text);font-size:13px;line-height:1.6;">
        ${escapeHtml(ref.recommendation)}
      </div>
    </div>
    ` : ''}

    <div class="soil-footer">
      <div class="soil-source">
        Live: Open-Meteo · Reference: ICAR-NBSS&amp;LUP / Soil Health Card
      </div>
      <button class="btn-primary" onclick="saveToHistory()">
        💾 Save to History
      </button>
    </div>
  `;

  page.appendChild(result);
  result.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ============================================================
// HISTORY
// ============================================================

function saveToHistory() {
  if (!state.currentResult) return;

  state.analyses.unshift({
    ...state.currentResult,
    timestamp: new Date().toISOString()
  });

  if (state.analyses.length > 20) {
    state.analyses = state.analyses.slice(0, 20);
  }

  saveState();
  updateStats();
  renderHistory();
  showToast('✅ Saved to history');
}

function renderHistory() {
  const page = document.getElementById('page-history');
  if (!page) return;

  const card = page.querySelector('.card');
  if (!card) return;

  if (state.analyses.length === 0) {
    card.innerHTML = `
      <div class="empty-state">
        <div class="empty-illustration">📭</div>
        <div class="empty-text">No history yet</div>
      </div>
    `;
    return;
  }

  card.innerHTML = `
    <div class="card-header">
      <h2>Past Analyses</h2>
    </div>
    <div class="history-list">
      ${state.analyses.map((a, i) => `
        <div class="history-item" onclick="loadFromHistory(${i})">
          <div class="history-icon">📍</div>
          <div class="history-content">
            <div class="history-location">${escapeHtml(a.location || 'Unknown')}</div>
            <div class="history-meta">${new Date(a.timestamp).toLocaleString()}</div>
          </div>
          <div class="history-arrow">→</div>
        </div>
      `).join('')}
    </div>
  `;
}

function loadFromHistory(index) {
  const entry = state.analyses[index];
  if (!entry) return;

  state.currentResult = entry;
  navigateTo('analyze');
  renderSoilResult(entry);
}

// ============================================================
// STATS
// ============================================================

function updateStats() {
  const statValues = document.querySelectorAll('.stat-value');
  if (statValues.length >= 4) {
    statValues[0].textContent = state.analyses.length || '--';
    statValues[1].textContent = new Set(state.analyses.map(a => a.location)).size || '--';
    statValues[2].textContent = '--';
    statValues[3].textContent = state.analyses.length || '--';
  }
}

// ============================================================
// TOAST
// ============================================================

function showToast(message) {
  const existing = document.querySelector('.toast');
  if (existing) existing.remove();

  const toast = document.createElement('div');
  toast.className = 'toast';
  toast.textContent = message;
  document.body.appendChild(toast);

  setTimeout(() => toast.classList.add('show'), 10);
  setTimeout(() => {
    toast.classList.remove('show');
    setTimeout(() => toast.remove(), 300);
  }, 2500);
}

// ============================================================
// MAIN ACTION
// ============================================================

async function runAnalysis() {
  const input = document.getElementById('locationInput');
  if (!input) return;

  const location = input.value.trim();

  if (!location) {
    showToast('⚠️ Enter a location or PIN code');
    input.focus();
    return;
  }

  if (/^\d+$/.test(location) && location.length !== 6) {
    showToast('⚠️ PIN code must be 6 digits');
    return;
  }

  const btn = document.querySelector('#page-analyze .btn-primary');
  const originalText = btn ? btn.innerHTML : '';

  if (btn) {
    btn.innerHTML = '⏳ Fetching data...';
    btn.disabled = true;
  }

  try {
    const data = await fetchSoilData(location);
    state.currentResult = data;
    saveState();
    renderSoilResult(data);
    updateStats();
    showToast('✅ Soil data fetched');

  } catch (err) {
    console.error('Analysis error:', err);
    showToast('❌ ' + (err.message || 'Failed to fetch soil data'));

    const page = document.getElementById('page-analyze');
    const old = document.getElementById('soilResult');
    if (old) old.remove();

    const errCard = document.createElement('div');
    errCard.id = 'soilResult';
    errCard.className = 'card';
    errCard.style.marginTop = '20px';
    errCard.innerHTML = `
      <div class="empty-state">
        <div class="empty-illustration">⚠️</div>
        <div class="empty-text">
          Could not fetch soil data for <strong>${escapeHtml(location)}</strong><br>
          <small style="color:var(--text-faint);">${escapeHtml(err.message || '')}</small>
        </div>
        <button class="btn-primary" onclick="runAnalysis()">🔄 Try Again</button>
      </div>
    `;
    page.appendChild(errCard);

  } finally {
    if (btn) {
      btn.innerHTML = originalText;
      btn.disabled = false;
    }
  }
}

// ============================================================
// GLOBAL SEARCH BAR
// ============================================================

function handleGlobalSearch() {
  const globalSearch = document.getElementById('globalSearch');
  if (!globalSearch) return;

  const query = globalSearch.value.trim();
  if (!query) return;

  // Navigate to Analyze page
  navigateTo('analyze');

  // Fill the location input
  const locInput = document.getElementById('locationInput');
  if (locInput) {
    locInput.value = query;
    // Run analysis after a short delay (allow DOM to update)
    setTimeout(() => {
      runAnalysis();
    }, 200);
  }
}

// ============================================================
// INIT
// ============================================================

function init() {
  const savedTheme = localStorage.getItem('soilgpt_theme');
  const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  applyTheme(savedTheme ? savedTheme === 'dark' : prefersDark);

  loadState();

  const lastPage = localStorage.getItem('soilgpt_page') || 'dashboard';
  navigateTo(lastPage);

  renderHistory();
  updateStats();

  // Nav clicks
  document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', (e) => {
      e.preventDefault();
      const pageId = item.dataset.page;
      if (pageId) navigateTo(pageId);
    });
  });

  // Global search bar → Enter key
  const globalSearch = document.getElementById('globalSearch');
  if (globalSearch) {
    globalSearch.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        handleGlobalSearch();
      }
    });
  }

  // Sidebar close on mobile
  document.addEventListener('click', (e) => {
    if (window.innerWidth > 900) return;
    const sidebar = document.getElementById('sidebar');
    const menuBtn = document.querySelector('.menu-btn');
    if (!sidebar || !menuBtn) return;

    if (sidebar.classList.contains('open') &&
        !sidebar.contains(e.target) &&
        !menuBtn.contains(e.target)) {
      sidebar.classList.remove('open');
    }
  });

  console.log('✅ SoilGPT initialized');
}

// Expose functions to global scope (for inline onclick handlers)
window.toggleTheme = toggleTheme;
window.toggleSidebar = toggleSidebar;
window.navigateTo = navigateTo;
window.runAnalysis = runAnalysis;
window.saveToHistory = saveToHistory;
window.loadFromHistory = loadFromHistory;
window.handleGlobalSearch = handleGlobalSearch;

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}