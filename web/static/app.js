/* ─── Navigation ─────────────────────────────────────────────────── */
function showPage(name) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('page-' + name).classList.add('active');
  document.getElementById('btn-' + name).classList.add('active');
  restoreFilters(name);
  if (name === 'archivio') {
    loadLaps(true);
    startLapAutoRefresh();
  } else if (name === 'setup') {
    loadSetupAdvice();
  } else if (name === 'compare') {
    loadLapComparison();
  } else {
    stopLapAutoRefresh();
  }
  saveFilters(name);
}

async function populateFilters() {
  try {
    const [cars, tracks, compounds] = await Promise.all([
      fetch('/api/filters/cars').then(r => r.json()),
      fetch('/api/filters/tracks').then(r => r.json()),
      fetch('/api/filters/compounds').then(r => r.json()),
    ]);

    function fillSelect(id, items) {
      const sel = document.getElementById(id);
      if (!sel) return;
      const current = sel.value;
      sel.innerHTML = '<option value="">Tutte</option>';
      items.forEach(v => {
        const opt = document.createElement('option');
        opt.value = v;
        opt.textContent = v;
        sel.appendChild(opt);
      });
      if (current && items.includes(current)) sel.value = current;
    }

    fillSelect('arch-car', cars);
    fillSelect('arch-track', tracks);
    fillSelect('arch-compound', compounds);
    fillSelect('prof-car', cars);
    fillSelect('prof-track', tracks);
    fillSelect('prof-compound', compounds);
    fillSelect('strat-car', cars);
    fillSelect('strat-track', tracks);
    fillSelect('comp-car', cars);
    fillSelect('comp-track', tracks);

    // Restore saved filter values
    restoreFilters('all');

    // Wire up filter change listeners for auto-save
    var filterSelectors = ['prof-car','prof-track','prof-compound','arch-car','arch-track','arch-compound','arch-deleted','strat-car','strat-track','setup-car','setup-track','comp-car','comp-track'];
    filterSelectors.forEach(function(id) {
      var el = document.getElementById(id);
      if (el) {
        el.addEventListener('change', function() {
          // Determine which page this filter belongs to
          var prefix = id.split('-')[0];
          var pageMap = {prof:'profilo', arch:'archivio', strat:'strategia', setup:'setup', comp:'compare'};
          saveFilters(pageMap[prefix] || 'all');
        });
      }
    });
  } catch (e) {
    console.error('Failed to populate filters:', e);
  }
}

populateFilters();
startOfflineDetection();

let _overlayInGameOnly = false;

async function loadOverlaySettings() {
  try {
    const res = await fetch('/api/overlay/settings');
    const d = await res.json();
    _overlayInGameOnly = d.in_game_only || false;
    updateOverlayToggleUI();
  } catch (e) {
    console.error('Failed to load overlay settings:', e);
  }
}

async function toggleOverlayMode() {
  _overlayInGameOnly = !_overlayInGameOnly;
  try {
    const res = await fetch('/api/overlay/settings', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({in_game_only: _overlayInGameOnly})
    });
    const d = await res.json();
    _overlayInGameOnly = d.in_game_only;
    updateOverlayToggleUI();
  } catch (e) {
    showToast('Errore salvataggio impostazioni overlay: ' + e.message, 'error');
    _overlayInGameOnly = !_overlayInGameOnly;
    updateOverlayToggleUI();
  }
}

function updateOverlayToggleUI() {
  const btn = document.getElementById('overlay-in-game-toggle');
  if (btn) {
    btn.textContent = _overlayInGameOnly ? 'ON' : 'OFF';
    btn.style.background = _overlayInGameOnly ? 'var(--status-valid)' : 'var(--surface-elevated)';
    btn.style.color = _overlayInGameOnly ? '#0b0d10' : 'var(--ink-primary)';
    btn.style.border = _overlayInGameOnly ? '1px solid var(--status-valid)' : '1px solid var(--border-subtle)';
  }
}

loadOverlaySettings();

/* ─── Utilities ──────────────────────────────────────────────────── */
function fmtTime(secs) {
  if (secs == null) return '—';
  const m = Math.floor(secs / 60);
  const s = (secs % 60).toFixed(3).padStart(6, '0');
  return m > 0 ? m + ':' + s : s + ' s';
}

/* ─── Toast Notifications ───────────────────────────────────────── */
function showToast(message, type) {
  type = type || 'info';
  var container = document.getElementById('toast-container');
  if (!container) return;
  var toast = document.createElement('div');
  toast.className = 'toast toast-' + type;
  toast.textContent = message;
  toast.addEventListener('click', function() {
    toast.classList.add('toast-out');
    setTimeout(function() { if (toast.parentNode) toast.parentNode.removeChild(toast); }, 300);
  });
  container.appendChild(toast);
  var delay = type === 'error' ? 6000 : 4000;
  setTimeout(function() {
    if (toast.parentNode) {
      toast.classList.add('toast-out');
      setTimeout(function() { if (toast.parentNode) toast.parentNode.removeChild(toast); }, 300);
    }
  }, delay);
}

/* ─── Loading Spinner ───────────────────────────────────────────── */
function showLoading(containerId, message) {
  var el = document.getElementById(containerId);
  if (!el) return;
  // Remove any existing overlay first
  hideLoading(containerId);
  // Save original display state
  if (!el.getAttribute('data-orig-display')) {
    el.setAttribute('data-orig-display', el.style.display || '');
  }
  var overlay = document.createElement('div');
  overlay.className = 'loading-overlay';
  overlay.id = containerId + '-loading';
  overlay.innerHTML = '<div class="spinner"></div><div class="spinner-text">' + (message || 'Caricamento...') + '</div>';
  el.appendChild(overlay);
  el.style.display = 'block';
}

function hideLoading(containerId) {
  var el = document.getElementById(containerId);
  if (!el) return;
  var overlay = document.getElementById(containerId + '-loading');
  if (overlay && overlay.parentNode) {
    overlay.parentNode.removeChild(overlay);
  }
  // Restore original display state
  var origDisplay = el.getAttribute('data-orig-display');
  if (origDisplay !== null) {
    el.style.display = origDisplay;
    el.removeAttribute('data-orig-display');
  }
}

/* ─── Pagination State ──────────────────────────────────────────── */
var _pageSize = 50;
var _currentPage = 1;

/* ─── Persistent Filters via localStorage ───────────────────────── */
function saveFilters(page) {
  var selectors = [];
  if (page === 'profilo' || page === 'all') selectors.push('prof-car', 'prof-track', 'prof-compound');
  if (page === 'archivio' || page === 'all') selectors.push('arch-car', 'arch-track', 'arch-compound', 'arch-deleted');
  if (page === 'strategia' || page === 'all') selectors.push('strat-car', 'strat-track');
  if (page === 'setup' || page === 'all') selectors.push('setup-car', 'setup-track');
  if (page === 'compare' || page === 'all') selectors.push('comp-car', 'comp-track');
  selectors.forEach(function(id) {
    var el = document.getElementById(id);
    if (el) {
      try { localStorage.setItem('filter_' + id, el.value); } catch(e) {}
    }
  });
}

function restoreFilters(page) {
  var selectors = [];
  if (page === 'profilo' || page === 'all') selectors.push('prof-car', 'prof-track', 'prof-compound');
  if (page === 'archivio' || page === 'all') selectors.push('arch-car', 'arch-track', 'arch-compound', 'arch-deleted');
  if (page === 'strategia' || page === 'all') selectors.push('strat-car', 'strat-track');
  if (page === 'setup' || page === 'all') selectors.push('setup-car', 'setup-track');
  if (page === 'compare' || page === 'all') selectors.push('comp-car', 'comp-track');
  selectors.forEach(function(id) {
    var el = document.getElementById(id);
    if (el) {
      try {
        var saved = localStorage.getItem('filter_' + id);
        if (saved !== null) el.value = saved;
      } catch(e) {}
    }
  });
}

/* ─── Offline Detection ─────────────────────────────────────────── */
var _offlineCheckTimer = null;

function isOnline() {
  return new Promise(function(resolve) {
    var controller = new AbortController();
    var timeoutId = setTimeout(function() { controller.abort(); }, 3000);
    fetch('/api/laps?limit=1', { signal: controller.signal })
      .then(function(r) {
        clearTimeout(timeoutId);
        resolve(true);
      })
      .catch(function() {
        clearTimeout(timeoutId);
        resolve(false);
      });
  });
}

function showOfflineBanner() {
  var banner = document.getElementById('offline-banner');
  if (banner) banner.style.display = 'block';
}

function hideOfflineBanner() {
  var banner = document.getElementById('offline-banner');
  if (banner) banner.style.display = 'none';
}

function checkOnlineStatus() {
  isOnline().then(function(online) {
    if (online) {
      hideOfflineBanner();
    } else {
      showOfflineBanner();
    }
  });
}

function startOfflineDetection() {
  if (_offlineCheckTimer) clearInterval(_offlineCheckTimer);
  checkOnlineStatus();
  _offlineCheckTimer = setInterval(checkOnlineStatus, 15000);
}

/* ─── Degradation Chart ──────────────────────────────────────────── */
let degradChart = null;

function buildDegradChart(curve, rawPoints) {
  const ctx = document.getElementById('chart-degradation').getContext('2d');
  if (degradChart) degradChart.destroy();

  const labels = curve.map(function(p) { return p.age; });
  const predicted = curve.map(function(p) { return p.predicted_time; });
  const scatterData = rawPoints.map(function(p) { return { x: p.tyre_age, y: p.lap_time }; });

  const rootStyle = getComputedStyle(document.documentElement);
  const colorPrimary = rootStyle.getPropertyValue('--border-focus').trim() || '#4a9eff';
  const colorScatter = rootStyle.getPropertyValue('--ink-secondary').trim() || '#99a3af';
  const gridColor = rootStyle.getPropertyValue('--border-subtle').trim() || '#262c35';

  degradChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: labels,
      datasets: [
        {
          label: 'Model (Huber)',
          data: predicted,
          borderColor: colorPrimary,
          borderWidth: 2,
          pointRadius: 0,
          pointHoverRadius: 4,
          tension: 0.1,
          fill: false,
        },
        {
          label: 'Telemetry',
          data: scatterData,
          type: 'scatter',
          backgroundColor: colorScatter,
          borderColor: 'transparent',
          pointRadius: 3,
          pointHoverRadius: 5,
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
           backgroundColor: 'rgba(15, 15, 15, 0.95)',
           titleFont: { family: "'Geist', sans-serif" },
           bodyFont: { family: "'JetBrains Mono', monospace" },
           cornerRadius: 4,
           borderColor: '#262c35',
           borderWidth: 1
        }
      },
      scales: {
        x: {
          grid: { color: gridColor, drawBorder: false },
          ticks: { color: '#99a3af', font: { family: "'JetBrains Mono', monospace" } }
        },
        y: {
          grid: { color: gridColor, drawBorder: false },
          ticks: { color: '#99a3af', font: { family: "'JetBrains Mono', monospace" } }
        }
      }
    }
  });
}

/* ─── PROFILO DEGRADO ────────────────────────────────────────────── */
async function loadProfile() {
  const car   = document.getElementById('prof-car').value.trim();
  const track = document.getElementById('prof-track').value.trim();
  const comp  = document.getElementById('prof-compound').value.trim();
  if (!car || !track) { showToast('Inserisci auto e pista.', 'warning'); return; }

  showLoading('prof-stats-area', 'Analisi in corso...');

  let url = '/api/profile?car=' + encodeURIComponent(car) + '&track=' + encodeURIComponent(track);
  if (comp) url += '&compound=' + encodeURIComponent(comp);

  try {
    const res = await fetch(url);
    const d   = await res.json();

    hideLoading('prof-stats-area');

    const warnDiv = document.getElementById('prof-warning');
    if (d.warning) {
      document.getElementById('prof-warning-text').textContent = d.warning;
      warnDiv.style.display = 'flex';
    } else {
      warnDiv.style.display = 'none';
    }

    document.getElementById('prof-n-laps').textContent = d.n_valid_laps ?? '—';
    document.getElementById('prof-avg-lap').textContent = d.avg_lap_time != null ? fmtTime(d.avg_lap_time) : '—';
    document.getElementById('prof-std-lap').textContent = d.std_lap_time != null ? '± ' + d.std_lap_time.toFixed(3) + ' s' : '';
    document.getElementById('prof-avg-fuel').textContent = d.avg_fuel_consumption != null ? d.avg_fuel_consumption.toFixed(2) + ' L/lap' : '—';
    document.getElementById('prof-std-fuel').textContent = d.std_fuel_consumption != null ? '± ' + d.std_fuel_consumption.toFixed(2) + ' L' : '';

    const m = d.degradation_model;
    document.getElementById('prof-cliff').textContent = (m && m.cliff_lap < 990) ? m.cliff_lap : 'N/D';
    document.getElementById('prof-beta2').textContent = (m && m.beta_2 > 0.01) ? '+' + m.beta_2.toFixed(3) + ' s/lap' : '';

    const tbody = document.getElementById('model-detail-tbody');
    if (m) {
      tbody.innerHTML =
        '<tr><td>Base Time</td><td class="num-col">' + fmtTime(m.base_time) + '</td></tr>' +
        '<tr><td>Fuel Effect (\u03b1)</td><td class="num-col">' + m.alpha.toFixed(4) + ' s/L</td></tr>' +
        '<tr><td>Linear Deg (\u03b2\u2081)</td><td class="num-col">' + m.beta_1.toFixed(4) + ' s/lap</td></tr>' +
        '<tr><td>Post-Cliff (\u03b2\u2082)</td><td class="num-col">' + m.beta_2.toFixed(4) + ' s/lap</td></tr>' +
        '<tr><td>Cliff Lap</td><td class="num-col" style="color:var(--status-invalid)">' + (m.cliff_lap < 990 ? m.cliff_lap : 'N/D') + '</td></tr>';
    } else {
      tbody.innerHTML = '<tr><td colspan="2" class="text-mono" style="color:var(--ink-muted); text-align:center;">Dati insufficienti.</td></tr>';
    }

    if (d.degradation_curve && d.raw_points) {
      buildDegradChart(d.degradation_curve, d.raw_points);
    }
  } catch (e) {
    hideLoading('prof-stats-area');
    showToast('Errore fetch profilo: ' + e.message, 'error');
  }
}

/* ─── ARCHIVIO GIRI ──────────────────────────────────────────────── */
let _lapsAutoTimer = null;

function startLapAutoRefresh() {
  stopLapAutoRefresh();
  if (!document.getElementById('page-archivio').classList.contains('active')) return;
  _lapsAutoTimer = setInterval(function() {
    if (document.getElementById('page-archivio').classList.contains('active')) {
      loadLaps(true);
    }
  }, 3000);
}

function stopLapAutoRefresh() {
  if (_lapsAutoTimer) clearInterval(_lapsAutoTimer);
  _lapsAutoTimer = null;
}

let _lapsData = [];
let _sortKey = 'lap_number';
let _sortAsc = true;

async function loadLaps(silent) {
  if (silent === undefined) silent = false;
  const car   = document.getElementById('arch-car').value.trim();
  const track = document.getElementById('arch-track').value.trim();
  const comp  = document.getElementById('arch-compound').value.trim();
  const incDel = document.getElementById('arch-deleted').value === '1';

  let url = '/api/laps?include_deleted=' + incDel;
  if (car)  url += '&car=' + encodeURIComponent(car);
  if (track) url += '&track=' + encodeURIComponent(track);
  if (comp) url += '&compound=' + encodeURIComponent(comp);

  const tbody = document.getElementById('laps-tbody');
  if (!silent) {
    tbody.innerHTML = '<tr><td colspan="19"><div class="spinner-container"><div class="spinner"></div><div class="spinner-text">Fetching laps...</div></div></td></tr>';
  }

  try {
    const res = await fetch(url);
    _lapsData = await res.json();
    _currentPage = 1;
    renderLapsTable();
  } catch (e) {
    if (!silent) {
      tbody.innerHTML = '<tr><td colspan="19" class="text-mono" style="color:var(--accent-red); text-align:center;">Error: ' + e.message + '</td></tr>';
    }
  }
}

function sortTable(key) {
  if (_sortKey === key) _sortAsc = !_sortAsc;
  else { _sortKey = key; _sortAsc = true; }
  renderLapsTable();
}

function renderLapsTable() {
  var data = _lapsData.slice().sort(function(a, b) {
    var av = a[_sortKey], bv = b[_sortKey];
    if (av == null) return 1;
    if (bv == null) return -1;
    return _sortAsc ? (av < bv ? -1 : 1) : (av > bv ? -1 : 1);
  });

  var totalPages = Math.max(1, Math.ceil(data.length / _pageSize));
  if (_currentPage > totalPages) _currentPage = totalPages;
  var startIdx = (_currentPage - 1) * _pageSize;
  var pageData = data.slice(startIdx, startIdx + _pageSize);

  var tbody = document.getElementById('laps-tbody');
  if (!pageData.length) {
    tbody.innerHTML = '<tr><td colspan="19" class="text-mono" style="color:var(--text-muted); text-align:center;">Nessun giro trovato.</td></tr>';
    renderPagination(0, 0);
    return;
  }

  var html = '';
  for (var i = 0; i < pageData.length; i++) {
    var l = pageData[i];
    var deleted = l.is_deleted === 1;
    var cls = deleted ? ' class="deleted"' : '';
    var validBadge = l.is_valid_lap ? '<span class="badge badge-valid">VALID</span>' : '<span class="badge badge-invalid">INVALID</span>';
    var pitBadge = l.is_pit_in_lap ? '<span class="badge badge-pit">IN</span> ' : (l.is_pit_out_lap ? '<span class="badge badge-pit">OUT</span> ' : '');
    var anomStr = l.anomaly_flag ? '<span style="color:var(--accent-orange); cursor:help;" title="' + (l.anomaly_reason || 'Anomalia rilevata') + '">\u26a0\ufe0f</span>' : '';

    var action = deleted
      ? '<button class="btn btn-restore" onclick="restoreLap(' + l.id + ')">Restore</button>'
      : '<button class="btn btn-danger" onclick="deleteLap(' + l.id + ')">Drop</button>';

    var wearStart = l.wear_pct_start_FL != null ? l.wear_pct_start_FL.toFixed(0) + '%' : '—';
    var wearEnd = l.wear_pct_end_FL != null ? l.wear_pct_end_FL.toFixed(0) + '%' : '—';
    var wearBadge = '—';
    if (l.wear_pct_start_FL != null && l.wear_pct_end_FL != null) {
      var wColor = l.wear_pct_end_FL > 50 ? 'var(--accent-red)' : 'var(--text-secondary)';
      wearBadge = '<span style="font-size:0.75rem; color:' + wColor + '">' + wearStart + ' \u2192 ' + wearEnd + '</span>';
    }

    var compoundStr = l.compound_front || '—';
    if (l.compound_rear) compoundStr += ' / ' + l.compound_rear;

    var weatherStr = l.weather_state || '—';
    if (l.rain_intensity > 0) weatherStr += ' \ud83c\udf27';

    html += '<tr' + cls + '>' +
      '<td class="num-col">' + l.lap_number + '</td>' +
      '<td>' + (l.track || '—') + '</td>' +
      '<td>' + (l.car || '—') + '</td>' +
      '<td>' + (l.session_type || '—') + '</td>' +
      '<td class="num-col">' + (l.stint_id != null ? l.stint_id : '—') + '</td>' +
      '<td class="num-col">' + fmtTime(l.lap_time) + '</td>' +
      '<td class="num-col">' + (l.sector_1 ? l.sector_1.toFixed(3) : '—') + '</td>' +
      '<td class="num-col">' + (l.sector_2 ? l.sector_2.toFixed(3) : '—') + '</td>' +
      '<td class="num-col">' + (l.sector_3 ? l.sector_3.toFixed(3) : '—') + '</td>' +
      '<td class="num-col">' + (l.fuel_start_l != null ? l.fuel_start_l.toFixed(1) : '—') + '</td>' +
      '<td class="num-col">' + (l.fuel_end_l != null ? l.fuel_end_l.toFixed(1) : '—') + '</td>' +
      '<td class="num-col">' + (l.tyre_age_laps != null ? l.tyre_age_laps : '—') + '</td>' +
      '<td>' + compoundStr + '</td>' +
      '<td class="num-col">' + wearBadge + '</td>' +
      '<td class="num-col">' + (l.track_temp != null ? l.track_temp.toFixed(1) : '—') + '\u00b0</td>' +
      '<td class="num-col">' + (l.ambient_temp != null ? l.ambient_temp.toFixed(1) : '—') + '\u00b0</td>' +
      '<td>' + weatherStr + '</td>' +
      '<td>' + pitBadge + validBadge + ' ' + anomStr + '</td>' +
      '<td style="text-align: right; padding: var(--space-xs) var(--space-md);">' + action + '</td>' +
    '</tr>';
  }

  tbody.innerHTML = html;
  renderPagination(data.length, totalPages);
}

function renderPagination(totalItems, totalPages) {
  var container = document.getElementById('laps-pagination');
  if (!container) return;
  if (totalItems === 0) {
    container.innerHTML = '';
    return;
  }

  var html = '';
  // Prev button
  html += '<button class="page-btn" onclick="goToPage(' + (_currentPage - 1) + ')"' + (_currentPage <= 1 ? ' disabled' : '') + '>‹ Prev</button>';

  // Page numbers
  var startPage = Math.max(1, _currentPage - 2);
  var endPage = Math.min(totalPages, _currentPage + 2);
  if (endPage - startPage < 4) {
    if (startPage === 1) endPage = Math.min(totalPages, startPage + 4);
    else startPage = Math.max(1, endPage - 4);
  }

  if (startPage > 1) {
    html += '<button class="page-btn" onclick="goToPage(1)">1</button>';
    if (startPage > 2) html += '<span class="page-info">…</span>';
  }

  for (var p = startPage; p <= endPage; p++) {
    html += '<button class="page-btn' + (p === _currentPage ? ' active' : '') + '" onclick="goToPage(' + p + ')">' + p + '</button>';
  }

  if (endPage < totalPages) {
    if (endPage < totalPages - 1) html += '<span class="page-info">…</span>';
    html += '<button class="page-btn" onclick="goToPage(' + totalPages + ')">' + totalPages + '</button>';
  }

  // Next button
  html += '<button class="page-btn" onclick="goToPage(' + (_currentPage + 1) + ')"' + (_currentPage >= totalPages ? ' disabled' : '') + '>Next ›</button>';

  // Info
  html += '<span class="page-info">' + ((_currentPage - 1) * _pageSize + 1) + '–' + Math.min(_currentPage * _pageSize, totalItems) + ' of ' + totalItems + '</span>';

  container.innerHTML = html;
}

function goToPage(page) {
  _currentPage = page;
  renderLapsTable();
}

async function deleteLap(id) {
  if (!confirm('Drop this lap from model analysis?')) return;
  await fetch('/api/laps/' + id + '/delete', { method: 'POST' });
  loadLaps();
}

async function restoreLap(id) {
  await fetch('/api/laps/' + id + '/restore', { method: 'POST' });
  loadLaps();
}

/* ─── CALCOLO STRATEGIA ──────────────────────────────────────────── */
async function calculateStrategy() {
  var car   = document.getElementById('strat-car').value.trim();
  var track = document.getElementById('strat-track').value.trim();
  var laps  = document.getElementById('strat-laps').value;
  var fuel  = document.getElementById('strat-fuel').value;
  var capacity = document.getElementById('strat-capacity').value;
  var maxstops = document.getElementById('strat-maxstops').value;
  var formation = document.getElementById('strat-formation').checked;
  var mode = document.getElementById('strat-mode').value;

  if (!car || !track) { showToast('Inserisci auto e pista.', 'warning'); return; }

  document.getElementById('strat-error').style.display = 'none';
  document.getElementById('strat-results').style.display = 'none';
  showLoading('strat-results', 'Calcolo strategia...');

  var url = '/api/strategy?car=' + encodeURIComponent(car) + '&track=' + encodeURIComponent(track) +
    '&current_fuel=' + fuel + '&fuel_capacity=' + capacity + '&max_stops=' + maxstops;
  if (formation) url += '&formation_lap=true';
  if (mode === 'time') {
    url += '&duration_hours=' + document.getElementById('strat-hours').value;
  } else {
    url += '&laps_remaining=' + laps;
  }

  try {
    var res = await fetch(url);
    var d   = await res.json();

    hideLoading('strat-results');

    if (!res.ok) {
      document.getElementById('strat-error-text').textContent = d.error || 'Errore sconosciuto.';
      document.getElementById('strat-error').style.display = 'flex';
      return;
    }

    var r = d.result;
    var optStops = r.optimal ? r.optimal.stops : null;
    var cards = Object.values(r.alternatives || {}).sort(function(a, b) { return a.stops - b.stops; });

    var cardsHtml = cards.map(function(s) {
      var isOpt = s.stops === optStops;
      var timeMin = Math.floor(s.total_time / 60);
      var timeSec = (s.total_time % 60).toFixed(1);
      var pitLapsStr = s.pit_laps.length ? s.pit_laps.join(', ') : 'No Stop';
      var badge = isOpt ? '<span class="badge badge-valid" style="margin-bottom:var(--space-xs); width:max-content;">OPTIMAL</span>' : '';

      return '<div class="strat-variant' + (isOpt ? ' optimal' : '') + '">' +
        '<div>' + badge + '</div>' +
        '<div style="font-size:1.5rem; font-family:var(--font-mono); line-height:1">' + s.stops + ' <span style="font-size:0.875rem; color:var(--ink-secondary)">Stops</span></div>' +
        '<div style="font-size:0.875rem; margin-top:var(--space-xs);">Pit Windows: <span class="text-mono" style="font-weight:600;">' + pitLapsStr + '</span></div>' +
        '<div style="font-size:0.875rem; color:var(--ink-secondary)">Est. Race Time: <span class="text-mono" style="color:var(--ink-primary); font-weight:600;">' + timeMin + 'm ' + timeSec + 's</span></div>' +
      '</div>';
    }).join('');

    document.getElementById('strat-cards').innerHTML = cardsHtml || '<p class="text-mono" style="color:var(--ink-muted)">No viable strategy found.</p>';

    if (r.optimal) {
      var opt = r.optimal;
      var timelineCells = (opt.decisions || []).map(function(dec, i) {
        var isPit = dec === 'pit';
        return '<div class="lap-cell' + (isPit ? ' pit' : '') + '">' + (i + 1) + '</div>';
      }).join('');

      document.getElementById('strat-detail').innerHTML =
        '<div style="display: flex; gap: var(--space-xl); margin-bottom: var(--space-xl);">' +
          '<div>' +
            '<div class="stat-label">Mean Fuel/Lap</div>' +
            '<div class="stat-value text-mono" style="color: var(--status-valid);">' + opt.mean_fuel_consumption + ' L</div>' +
          '</div>' +
          '<div style="padding-left: var(--space-xl); border-left: 1px solid var(--border-subtle);">' +
            '<div class="stat-label">Pit Loss Penalty</div>' +
            '<div class="stat-value text-mono" style="color: var(--status-invalid);">' + opt.pit_loss_seconds + ' s</div>' +
          '</div>' +
        '</div>' +
        '<div>' +
          '<div class="stat-label">Lap-by-Lap Execution Plan</div>' +
          '<div class="timeline-grid">' + timelineCells + '</div>' +
        '</div>';
    }

    document.getElementById('strat-results').style.display = 'block';
  } catch (e) {
    hideLoading('strat-results');
    document.getElementById('strat-error-text').textContent = 'Network error: ' + e.message;
    document.getElementById('strat-error').style.display = 'flex';
  }
}

/* ─── SETUP ADVISOR ──────────────────────────────────────────────────── */
async function loadSetupAdvice() {
  var car = document.getElementById('setup-car').value.trim();
  var track = document.getElementById('setup-track').value.trim();

  if (!car || !track) {
    showToast('Inserisci auto e pista.', 'warning');
    return;
  }

  document.getElementById('setup-error').style.display = 'none';
  document.getElementById('setup-content').style.display = 'none';
  showLoading('setup-loading', 'Analyzing telemetry data...');

  try {
    var res = await fetch('/api/setup?car=' + encodeURIComponent(car) + '&track=' + encodeURIComponent(track));
    var d = await res.json();

    hideLoading('setup-loading');

    if (!res.ok || d.insufficient_data) {
      document.getElementById('setup-error-text').textContent = d.message || 'Insufficient data for setup analysis.';
      document.getElementById('setup-error').style.display = 'flex';
      return;
    }

    document.getElementById('setup-valid-laps').textContent = d.total_valid_laps;
    document.getElementById('setup-optimal-temp').textContent = d.optimal_temp_range || 'N/A';
    document.getElementById('setup-current-temp').textContent = d.current_avg_track_temp ? d.current_avg_track_temp.toFixed(1) + '\u00b0C' : 'N/A';
    document.getElementById('setup-best-lap').textContent = fmtTime(d.all_time_best);

    var recDiv = document.getElementById('setup-recommendations');
    if (d.recommendations && d.recommendations.length > 0) {
      var recHtml = '';
      for (var i = 0; i < d.recommendations.length; i++) {
        var r = d.recommendations[i];
        var priorityColor = r.priority === 'high' ? 'var(--status-invalid)' : (r.priority === 'medium' ? 'var(--status-warn)' : 'var(--ink-secondary)');
        recHtml += '<div style="padding: var(--space-md); background: var(--surface-elevated); border-radius: var(--radius-sm); border-left: 4px solid ' + priorityColor + ';">' +
          '<div style="font-weight: 600; margin-bottom: var(--space-xs);">' + r.title + '</div>' +
          '<div style="font-size: 0.9rem; color: var(--ink-secondary); margin-bottom: var(--space-xs);">' + r.message + '</div>' +
          '<div style="font-size: 0.8rem; color: var(--ink-muted);">Impact: ' + r.impact + '</div>' +
        '</div>';
      }
      recDiv.innerHTML = recHtml;
    } else {
      recDiv.innerHTML = '<p style="color: var(--ink-muted);">No specific recommendations. Conditions are within optimal range based on historical data.</p>';
    }

    var weatherTbody = document.getElementById('setup-weather-tbody');
    var weatherEntries = Object.entries(d.weather_performance || {}).sort(function(a, b) { return a[1] - b[1]; });
    var bestWeatherTime = weatherEntries.length > 0 ? weatherEntries[0][1] : null;
    var wHtml = '';
    for (var j = 0; j < weatherEntries.length; j++) {
      var entry = weatherEntries[j];
      var delta = bestWeatherTime ? (entry[1] - bestWeatherTime).toFixed(2) : '—';
      var deltaColor = delta === '—' || parseFloat(delta) <= 0 ? 'var(--status-valid)' : 'var(--status-invalid)';
      var deltaStr = delta === '—' ? '—' : ((delta > 0 ? '+' : '') + delta + 's');
      wHtml += '<tr><td>' + entry[0] + '</td><td class="num-col">' + fmtTime(entry[1]) + '</td><td class="num-col" style="color: ' + deltaColor + ';">' + deltaStr + '</td></tr>';
    }
    weatherTbody.innerHTML = wHtml;

    var compoundTbody = document.getElementById('setup-compound-tbody');
    var compoundEntries = Object.entries(d.compound_stats || {}).sort(function(a, b) { return a[1]["avg_lap"] - b[1]["avg_lap"]; });
    var cHtml = '';
    for (var k = 0; k < compoundEntries.length; k++) {
      var centry = compoundEntries[k];
      var stats = centry[1];
      var temps = stats.temps;
      var tempRange = '—';
      if (temps && temps.length > 0) {
        tempRange = Math.min.apply(null, temps).toFixed(0) + '\u00b0C - ' + Math.max.apply(null, temps).toFixed(0) + '\u00b0C';
      }
      cHtml += '<tr><td><strong>' + centry[0] + '</strong></td><td class="num-col">' + fmtTime(stats.avg_lap) + '</td><td class="num-col">' + stats.count +
        '</td><td class="num-col">' + stats.avg_wear_increase.toFixed(1) + '%</td><td>' + tempRange + '</td></tr>';
    }
    compoundTbody.innerHTML = cHtml;

    var tempTbody = document.getElementById('setup-temp-tbody');
    var tempEntries = Object.entries(d.temp_buckets || {}).sort(function(a, b) { return parseInt(a[0]) - parseInt(b[0]); });
    var tHtml = '';
    for (var ti = 0; ti < tempEntries.length; ti++) {
      var tentry = tempEntries[ti];
      var laps2 = tentry[1];
      var times2 = laps2.map(function(ll) { return ll["lap_time"]; });
      var best2 = Math.min.apply(null, times2);
      var avg2 = times2.reduce(function(a2, b2) { return a2 + b2; }, 0) / times2.length;
      var delta2 = overallBest ? (avg2 - overallBest).toFixed(2) : '—';
      tHtml += '<tr><td>' + tentry[0] + '\u00b0C - ' + (parseInt(tentry[0]) + 5) + '\u00b0C</td>' +
        '<td class="num-col">' + laps2.length + '</td>' +
        '<td class="num-col">' + fmtTime(best2) + '</td>' +
        '<td class="num-col">' + fmtTime(avg2) + '</td></tr>';
    }
    tempTbody.innerHTML = tHtml;

    document.getElementById('setup-content').style.display = 'block';
    hideLoading('setup-loading');
  } catch (e) {
    hideLoading('setup-loading');
    document.getElementById('setup-error-text').textContent = 'Network error: ' + e.message;
    document.getElementById('setup-error').style.display = 'flex';
  }
}


// ── Owner email (S-4) ──────────────────────────────────────────────────

async function loadOwner() {
  try {
    var r = await fetch('/api/owner');
    var d = await r.json();
    var display = document.getElementById('owner-display');
    if (display) {
      display.textContent = d.email || 'Non loggato';
    }
    // Show welcome banner if no laps
    var r2 = await fetch('/api/laps?limit=1');
    var laps = await r2.json();
    var banner = document.getElementById('welcome-banner');
    if (banner) {
      banner.style.display = (!laps || laps.length === 0) ? 'block' : 'none';
    }
  } catch (e) {
    console.error('loadOwner:', e);
  }
}

async function seedData() {
  var btn = document.getElementById('seed-btn');
  var status = document.getElementById('seed-status');
  btn.disabled = true;
  status.textContent = 'Creazione in corso...';
  try {
    var r = await fetch('/api/seed', {method: 'POST'});
    var d = await r.json();
    status.textContent = d.message || 'Fatto!';
    if (d.ok) {
      location.reload();
    } else {
      status.textContent = d.message;
      btn.disabled = false;
    }
  } catch (e) {
    status.textContent = 'Errore: ' + e.message;
    btn.disabled = false;
  }
}

async function saveOwner() {
  window.location.href = '/login';
}


// Load owner when the profilo page is shown
var _origShowPage = showPage;
showPage = function(name) {
  _origShowPage(name);
  if (name === 'profilo') loadOwner();
};


// ── Lap Time Evolution Chart (C-2) ─────────────────────────────────────

var _lapChartInstance = null;

async function renderLapChart(car, track) {
  if (!car || !track) return;
  try {
    var r = await fetch('/api/laps/chart?car=' + encodeURIComponent(car) + '&track=' + encodeURIComponent(track));
    var data = await r.json();
    if (!data.laps || data.laps.length < 3) {
      document.getElementById('strat-chart').style.display = 'none';
      return;
    }
    document.getElementById('strat-chart').style.display = 'block';

    if (_lapChartInstance) {
      _lapChartInstance.destroy();
      _lapChartInstance = null;
    }

    var canvas = document.getElementById('strat-chart');
    var ctx = canvas.getContext('2d');

    // ── Compute fuel-corrected pace (removes the effect of fuel so you see pure tyre deg) ──
    // Best estimate of fuel penalty: use alpha from degradation model if available, else 0.03s/lap
    var alphaFuel = 0.03;
    if (data.degradation && data.degradation.params) {
      alphaFuel = data.degradation.params.alpha || 0.03;
    }

    // Each point: lap_number, raw_lap_time, fuel_corrected (time minus fuel penalty)
    var allPoints = data.laps.map(function(lap) {
      return {
        x: lap.lap_number,
        y: lap.lap_time,
        yc: lap.lap_time - alphaFuel * (lap.fuel_start_l || 0),
        fuel: lap.fuel_start_l,
        age: lap.tyre_age_laps,
        stint_id: lap.stint_id,
        compound: lap.compound_front,
      };
    });

    // ── Stint colors and single legend entry per stint (no duplicates) ──
    var stintColors = {
      1: '#1dd1a1', 2: '#4a9eff', 3: '#ff6b6b',
      4: '#ffa94d', 5: '#a29bfe', 6: '#fd79a8'
    };

    // Group points by stint (for color, not for legend)
    var stints = {};  // stint_id -> {color, compound, lap_start, lap_end, fuel_start}
    allPoints.forEach(function(p) {
      var s = p.stint_id || 1;
      if (!stints[s]) {
        stints[s] = {
          id: s, color: stintColors[s] || '#7d8590',
          compound: p.compound || 'Medium', lap_start: p.x, lap_end: p.x,
          fuel_start: p.fuel, fuel_end: p.fuel
        };
      }
      stints[s].lap_end = p.x;
      stints[s].fuel_end = p.fuel;
    });
    var stintList = Object.values(stints);

    // ── Build chart datasets ──
    var datasets = [];

    // 1) RAW pace (real lap times — includes fuel effect)
    datasets.push({
      label: 'Lap time (real)',
      data: allPoints.map(function(p) { return {x: p.x, y: p.y}; }),
      backgroundColor: '#7d8590',
      borderColor: '#7d8590',
      pointRadius: 3,
      pointHoverRadius: 5,
      showLine: false,
      type: 'scatter',
      order: 4
    });

    // 2) FUEL-CORRECTED pace (pure tyre degradation, the real underlying signal)
    datasets.push({
      label: 'Tyre degradation (fuel-corrected)',
      data: allPoints.map(function(p) { return {x: p.x, y: p.yc}; }),
      backgroundColor: function(ctx) {
        return stintColors[ctx.raw.stint_id] || '#ffa94d';
      },
      borderColor: '#ffa94d',
      pointRadius: 4,
      pointHoverRadius: 7,
      showLine: false,
      type: 'scatter',
      order: 3
    });

    // 3) Degradation model line (the fit through fuel-corrected pace)
    if (data.degradation && data.degradation.curve) {
      datasets.push({
        label: 'Degradation model fit',
        data: data.degradation.curve.map(function(p) { return {x: p.age, y: p.predicted}; }),
        borderColor: '#1dd1a1',
        backgroundColor: 'rgba(29,209,161,0.15)',
        pointRadius: 0,
        borderWidth: 2.5,
        borderDash: [6, 4],
        showLine: true,
        fill: false,
        order: 1
      });
    }

    // 4) FUEL MASS line (how much fuel = how much lap time penalty)
    // Show this as a separate small chart on the right axis? Simpler: add to tooltip only.

    // ── Pit stop annotations (one per stint transition) ──
    var pitAnnotations = {};
    if (data.pit_stops && data.pit_stops.length > 0) {
      data.pit_stops.forEach(function(ps) {
        pitAnnotations['pit-' + ps.lap_number] = {
          type: 'line',
          xMin: ps.lap_number, xMax: ps.lap_number,
          yMin: 0, yMax: 999,
          borderColor: '#ff6b6b',
          borderWidth: 2,
          borderDash: [8, 4],
          label: {
            display: true,
            content: 'PIT ' + Math.round(ps.pit_loss) + 's',
            position: 'start',
            backgroundColor: 'rgba(255,107,107,0.85)',
            color: '#fff',
            padding: 3,
            font: {size: 10, weight: 'bold'}
          }
        };
      });
    }

    // ── Stint bands (background colors to show each stint's range) ──
    stintList.forEach(function(st) {
      pitAnnotations['stint-' + st.id] = {
        type: 'box',
        xMin: st.lap_start,
        xMax: st.lap_end + 0.5,
        backgroundColor: st.color + '14',  // very transparent
        borderColor: st.color + '40',
        borderWidth: 1,
        borderDash: [2, 2],
        label: {
          display: true,
          content: 'Stint ' + st.id + ' (' + st.compound + ')',
          position: {x: 'center', y: 'start'},
          color: st.color,
          font: {size: 10, weight: 'bold'},
          backgroundColor: 'rgba(10,14,24,0.7)',
          padding: 3
        }
      };
    });

    // ── Chart options ──
    _lapChartInstance = new Chart(ctx, {
      type: 'scatter',
      data: {datasets: datasets},
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: {duration: 300},
        plugins: {
          legend: {
            position: 'top',
            labels: {
              color: '#7d8590',
              font: {family: 'Inter, sans-serif', size: 11},
              generateLabels: function(chart) {
                // Build labels: 2 dataset labels + 1 per stint
                var labels = Chart.defaults.plugins.legend.labels.generateLabels(chart);
                // Add stint info as legend entries
                stintList.forEach(function(st) {
                  labels.push({
                    text: 'Stint ' + st.id + ': ' + st.compound + ' (' + st.lap_start + '–' + st.lap_end + ')',
                    fillStyle: st.color,
                    strokeStyle: st.color,
                    lineWidth: 0,
                    fontColor: '#7d8590',
                    pointStyle: 'rect',
                    hidden: false
                  });
                });
                return labels;
              }
            }
          },
          tooltip: {
            callbacks: {
              label: function(ctx) {
                var raw = ctx.raw || {};
                var p = allPoints.find(function(x) { return x.x === raw.x; });
                if (!p) return ctx.formattedValue;
                var lines = [
                  'Lap ' + p.x + ' — ' + p.y.toFixed(2) + 's',
                  'Stint ' + p.stint_id + ' (' + p.compound + ')',
                  'Tyre age: ' + p.age + ' laps',
                  'Fuel: ' + p.fuel.toFixed(1) + 'L (' + (p.fuel * 0.62).toFixed(1) + 'kg)',
                  'Fuel penalty: +' + (alphaFuel * p.fuel).toFixed(2) + 's',
                  'Pure tyre pace: ' + p.yc.toFixed(2) + 's'
                ];
                return lines;
              }
            }
          },
          annotation: {
            annotations: pitAnnotations
          }
        },
        scales: {
          x: {
            type: 'linear',
            title: {display: true, text: 'Lap Number', color: '#7d8590'},
            ticks: {color: '#7d8590', stepSize: 1, precision: 0},
            grid: {color: 'rgba(255,255,255,0.05)'}
          },
          y: {
            title: {display: true, text: 'Lap Time (s)', color: '#7d8590'},
            ticks: {color: '#7d8590'},
            grid: {color: 'rgba(255,255,255,0.05)'}
          }
        }
      }
    });
  } catch (e) {
    console.error('renderLapChart:', e);
  }
}

// Auto-load chart after strategy calculation
var _origCalcStrategy = calculateStrategy;
calculateStrategy = function() {
  _origCalcStrategy();
  // After a brief delay for the strategy results to render, load the chart
  setTimeout(function() {
    var car = document.getElementById('strat-car').value.trim();
    var track = document.getElementById('strat-track').value.trim();
    if (car && track) renderLapChart(car, track);
  }, 500);
};

// ── Toggle race mode (laps vs duration) ────────────────────────────

function toggleStratMode() {
  var mode = document.getElementById('strat-mode').value;
  document.getElementById('strat-laps-group').style.display = mode === 'laps' ? '' : 'none';
  document.getElementById('strat-hours-group').style.display = mode === 'time' ? '' : 'none';
}

/* ─── LAP COMPARISON ──────────────────────────────────────────── */
let _compLapsData = [];
let _compChart = null;

async function loadLapComparison() {
  const car = document.getElementById('comp-car').value.trim();
  const track = document.getElementById('comp-track').value.trim();

  if (!car || !track) {
    showToast('Select car and track.', 'warning');
    return;
  }

  showLoading('comp-results', 'Caricamento giri...');

  try {
    const res = await fetch('/api/laps/compare?car=' + encodeURIComponent(car) + '&track=' + encodeURIComponent(track));
    _compLapsData = await res.json();

    hideLoading('comp-results');

    const selA = document.getElementById('comp-lap-a');
    const selB = document.getElementById('comp-lap-b');
    selA.innerHTML = '<option value="">Select Lap A...</option>';
    selB.innerHTML = '<option value="">Select Lap B...</option>';

    _compLapsData.forEach(function(lap) {
      var optA = document.createElement('option');
      optA.value = lap.id;
      optA.textContent = 'Lap ' + lap.lap_number + ' \u2014 ' + fmtTime(lap.lap_time) + (lap.stint_number ? ' (Stint ' + lap.stint_number + ')' : '');
      selA.appendChild(optA);

      var optB = document.createElement('option');
      optB.value = lap.id;
      optB.textContent = 'Lap ' + lap.lap_number + ' \u2014 ' + fmtTime(lap.lap_time) + (lap.stint_number ? ' (Stint ' + lap.stint_number + ')' : '');
      selB.appendChild(optB);
    });

    document.getElementById('comp-lap-selectors').style.display = 'flex';
    document.getElementById('comp-results').style.display = 'none';
    document.getElementById('comp-empty').style.display = 'none';

    if (selA.value && selB.value) {
      renderLapComparison();
    }
  } catch (e) {
    hideLoading('comp-results');
    console.error('loadLapComparison:', e);
    showToast('Error loading laps: ' + e.message, 'error');
  }
}

function renderLapComparison() {
  var idA = parseInt(document.getElementById('comp-lap-a').value);
  var idB = parseInt(document.getElementById('comp-lap-b').value);

  if (!idA || !idB) {
    document.getElementById('comp-results').style.display = 'none';
    return;
  }

  var lapA = null, lapB = null;
  for (var i = 0; i < _compLapsData.length; i++) {
    if (_compLapsData[i].id === idA) lapA = _compLapsData[i];
    if (_compLapsData[i].id === idB) lapB = _compLapsData[i];
  }

  if (!lapA || !lapB) return;

  var aFaster = lapA.lap_time <= lapB.lap_time;

  // Render cards
  function renderCard(lap, isFaster) {
    var cls = isFaster ? 'faster' : 'slower';
    var badge = isFaster ? 'FASTER' : 'SLOWER';
    var hours = Math.floor(lap.lap_time / 3600);
    var mins = Math.floor((lap.lap_time % 3600) / 60);
    var secs = (lap.lap_time % 60).toFixed(3);
    var timeStr = hours > 0 ? hours + ':' + (mins < 10 ? '0' : '') + mins + ':' + (secs < 10 ? '0' : '') + secs : (mins > 0 ? mins + ':' + (secs < 10 ? '0' : '') + secs : secs + 's');
    return '<div class="comp-card-header">' +
      '<div class="comp-card-title">Lap ' + lap.lap_number + (lap.stint_number ? ' <span style="font-size:0.75rem;color:var(--text-muted);font-weight:400;">(Stint ' + lap.stint_number + ')</span>' : '') + '</div>' +
      '<div class="comp-badge ' + cls + '">' + badge + '</div>' +
      '</div>' +
      '<div class="comp-row"><span class="comp-row-label">Lap Time</span><span class="comp-row-value ' + cls + '">' + timeStr + '</span></div>' +
      '<div class="comp-row"><span class="comp-row-label">Sector 1</span><span class="comp-row-value">' + (lap.sector_1 != null ? lap.sector_1.toFixed(3) : '\u2014') + '</span></div>' +
      '<div class="comp-row"><span class="comp-row-label">Sector 2</span><span class="comp-row-value">' + (lap.sector_2 != null ? lap.sector_2.toFixed(3) : '\u2014') + '</span></div>' +
      '<div class="comp-row"><span class="comp-row-label">Sector 3</span><span class="comp-row-value">' + (lap.sector_3 != null ? lap.sector_3.toFixed(3) : '\u2014') + '</span></div>' +
      '<div class="comp-row"><span class="comp-row-label">Fuel Start</span><span class="comp-row-value">' + (lap.fuel_start_l != null ? lap.fuel_start_l.toFixed(1) + ' L' : '\u2014') + '</span></div>' +
      '<div class="comp-row"><span class="comp-row-label">Fuel End</span><span class="comp-row-value">' + (lap.fuel_end_l != null ? lap.fuel_end_l.toFixed(1) + ' L' : '\u2014') + '</span></div>' +
      '<div class="comp-row"><span class="comp-row-label">Fuel Used</span><span class="comp-row-value">' + (lap.fuel_used_l != null ? lap.fuel_used_l.toFixed(1) + ' L' : '\u2014') + '</span></div>' +
      '<div class="comp-row"><span class="comp-row-label">Tyre Age</span><span class="comp-row-value">' + (lap.tyre_age_laps != null ? lap.tyre_age_laps + ' laps' : '\u2014') + '</span></div>' +
      '<div class="comp-row"><span class="comp-row-label">Compound</span><span class="comp-row-value">' + (lap.compound_front || '\u2014') + '</span></div>' +
      '<div class="comp-row"><span class="comp-row-label">Track Temp</span><span class="comp-row-value">' + (lap.track_temp != null ? lap.track_temp.toFixed(1) + '\u00b0C' : '\u2014') + '</span></div>' +
      '<div class="comp-row"><span class="comp-row-label">Weather</span><span class="comp-row-value">' + (lap.weather_state || '\u2014') + '</span></div>';
  }

  document.getElementById('comp-card-a').className = 'comp-card' + (aFaster ? ' faster' : ' slower');
  document.getElementById('comp-card-b').className = 'comp-card' + (!aFaster ? ' faster' : ' slower');
  document.getElementById('comp-card-a').innerHTML = renderCard(lapA, aFaster);
  document.getElementById('comp-card-b').innerHTML = renderCard(lapB, !aFaster);

  // Sector comparison bars
  var sectors = ['sector_1', 'sector_2', 'sector_3'];
  var sectorLabels = ['S1', 'S2', 'S3'];
  var sectorsHtml = '';

  for (var si = 0; si < sectors.length; si++) {
    var key = sectors[si];
    var tA = lapA[key];
    var tB = lapB[key];

    if (tA != null && tB != null) {
      var diff = Math.abs(tA - tB);
      var aIsFaster = tA <= tB;
      var maxTime = Math.max(tA, tB);
      var barWidthA = Math.max(2, Math.round((tA / maxTime) * 200));
      var barWidthB = Math.max(2, Math.round((tB / maxTime) * 200));

      sectorsHtml += '<div class="sector-bar-row">' +
        '<div class="sector-label">' + sectorLabels[si] + '</div>' +
        '<div class="sector-bar-container">' +
          '<div class="sector-bar ' + (aIsFaster ? 'faster' : 'slower') + '" style="width:' + barWidthA + 'px;"></div>' +
          '<span class="sector-time">' + tA.toFixed(3) + '</span>' +
        '</div>' +
        '<div class="sector-bar-container">' +
          '<div class="sector-bar ' + (!aIsFaster ? 'faster' : 'slower') + '" style="width:' + barWidthB + 'px;"></div>' +
          '<span class="sector-time">' + tB.toFixed(3) + '</span>' +
        '</div>' +
        '<div class="sector-delta" style="color:' + (aIsFaster ? 'var(--accent-green)' : 'var(--accent-red)') + '">' + (aIsFaster ? '-' : '+') + diff.toFixed(3) + '</div>' +
      '</div>';
    } else {
      sectorsHtml += '<div class="sector-bar-row">' +
        '<div class="sector-label">' + sectorLabels[si] + '</div>' +
        '<div class="sector-bar-container" style="justify-content:center;color:var(--text-muted);">N/A</div>' +
        '<div class="sector-bar-container" style="justify-content:center;color:var(--text-muted);">N/A</div>' +
        '<div class="sector-delta">\u2014</div>' +
      '</div>';
    }
  }

  document.getElementById('comp-sectors').innerHTML = sectorsHtml;

  // Build chart
  buildCompChart(lapA, lapB, aFaster);

  document.getElementById('comp-results').style.display = 'block';
}

function buildCompChart(lapA, lapB, aFaster) {
  var ctx = document.getElementById('comp-chart').getContext('2d');
  if (_compChart) _compChart.destroy();

  var labels = ['Lap Time', 'Sector 1', 'Sector 2', 'Sector 3', 'Fuel Used', 'Tyre Age', 'Track Temp'];
  var aColor = aFaster ? '#2ea043' : '#ff4d4d';
  var bColor = aFaster ? '#ff4d4d' : '#2ea043';

  function extract(lap, key) {
    var val = lap[key];
    return val != null ? val : 0;
  }

  _compChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [{
        label: 'Lap A (Lap ' + lapA.lap_number + ')',
        data: [
          extract(lapA, 'lap_time'),
          extract(lapA, 'sector_1'),
          extract(lapA, 'sector_2'),
          extract(lapA, 'sector_3'),
          extract(lapA, 'fuel_used_l'),
          extract(lapA, 'tyre_age_laps'),
          extract(lapA, 'track_temp'),
        ],
        backgroundColor: aColor + '99',
        borderColor: aColor,
        borderWidth: 1,
      }, {
        label: 'Lap B (Lap ' + lapB.lap_number + ')',
        data: [
          extract(lapB, 'lap_time'),
          extract(lapB, 'sector_1'),
          extract(lapB, 'sector_2'),
          extract(lapB, 'sector_3'),
          extract(lapB, 'fuel_used_l'),
          extract(lapB, 'tyre_age_laps'),
          extract(lapB, 'track_temp'),
        ],
        backgroundColor: bColor + '99',
        borderColor: bColor,
        borderWidth: 1,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          labels: { color: '#7d8590', font: { family: 'Inter, sans-serif', size: 11 } }
        },
        tooltip: {
          backgroundColor: 'rgba(15, 15, 15, 0.95)',
          titleFont: { family: "'Geist', sans-serif" },
          bodyFont: { family: "'JetBrains Mono', monospace" },
          cornerRadius: 4,
          borderColor: '#262c35',
          borderWidth: 1
        }
      },
      scales: {
        x: {
          grid: { color: 'rgba(255,255,255,0.05)', drawBorder: false },
          ticks: { color: '#7d8590', font: { family: "'JetBrains Mono', monospace" } }
        },
        y: {
          grid: { color: 'rgba(255,255,255,0.05)', drawBorder: false },
          ticks: { color: '#7d8590', font: { family: "'JetBrains Mono', monospace" } }
        }
      }
    }
  });
}
