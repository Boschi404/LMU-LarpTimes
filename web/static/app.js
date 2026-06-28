/* ─── Navigation ─────────────────────────────────────────────────── */
function showPage(name) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('page-' + name).classList.add('active');
  document.getElementById('btn-' + name).classList.add('active');
  if (name === 'archivio') {
    loadLaps(true);
    startLapAutoRefresh();
  } else if (name === 'setup') {
    loadSetupAdvice();
  } else {
    stopLapAutoRefresh();
  }
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
  } catch (e) {
    console.error('Failed to populate filters:', e);
  }
}

populateFilters();

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
    alert('Errore salvataggio impostazioni overlay: ' + e.message);
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
  if (!car || !track) { alert('Inserisci auto e pista.'); return; }

  let url = '/api/profile?car=' + encodeURIComponent(car) + '&track=' + encodeURIComponent(track);
  if (comp) url += '&compound=' + encodeURIComponent(comp);

  try {
    const res = await fetch(url);
    const d   = await res.json();

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
    alert('Errore fetch profilo: ' + e.message);
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
    tbody.innerHTML = '<tr><td colspan="19" class="text-mono" style="color:var(--ink-muted); text-align:center;">Fetching...</td></tr>';
  }

  try {
    const res = await fetch(url);
    _lapsData = await res.json();
    renderLapsTable();
  } catch (e) {
    if (!silent) {
      tbody.innerHTML = '<tr><td colspan="17" class="text-mono" style="color:var(--status-invalid); text-align:center;">Error: ' + e.message + '</td></tr>';
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

  var tbody = document.getElementById('laps-tbody');
  if (!data.length) {
    tbody.innerHTML = '<tr><td colspan="19" class="text-mono" style="color:var(--ink-muted); text-align:center;">Nessun giro trovato.</td></tr>';
    return;
  }

  var html = '';
  for (var i = 0; i < data.length; i++) {
    var l = data[i];
    var deleted = l.is_deleted === 1;
    var cls = deleted ? ' class="deleted"' : '';
    var validBadge = l.is_valid_lap ? '<span class="badge badge-valid">VALID</span>' : '<span class="badge badge-invalid">INVALID</span>';
    var pitBadge = l.is_pit_in_lap ? '<span class="badge badge-pit">IN</span> ' : (l.is_pit_out_lap ? '<span class="badge badge-pit">OUT</span> ' : '');
    var anomStr = l.anomaly_flag ? '<span style="color:var(--status-warn); cursor:help;" title="' + (l.anomaly_reason || 'Anomalia rilevata') + '">\u26a0\ufe0f</span>' : '';

    var action = deleted
      ? '<button class="btn btn-restore" onclick="restoreLap(' + l.id + ')">Restore</button>'
      : '<button class="btn btn-danger" onclick="deleteLap(' + l.id + ')">Drop</button>';

    var wearStart = l.wear_pct_start_FL != null ? l.wear_pct_start_FL.toFixed(0) + '%' : '—';
    var wearEnd = l.wear_pct_end_FL != null ? l.wear_pct_end_FL.toFixed(0) + '%' : '—';
    var wearBadge = '—';
    if (l.wear_pct_start_FL != null && l.wear_pct_end_FL != null) {
      var wColor = l.wear_pct_end_FL > 50 ? 'var(--status-invalid)' : 'var(--ink-secondary)';
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

  if (!car || !track) { alert('Inserisci auto e pista.'); return; }

  document.getElementById('strat-error').style.display = 'none';
  document.getElementById('strat-results').style.display = 'none';

  var url = '/api/strategy?car=' + encodeURIComponent(car) + '&track=' + encodeURIComponent(track) +
    '&laps_remaining=' + laps + '&current_fuel=' + fuel + '&fuel_capacity=' + capacity + '&max_stops=' + maxstops;

  try {
    var res = await fetch(url);
    var d   = await res.json();

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
    document.getElementById('strat-error-text').textContent = 'Network error: ' + e.message;
    document.getElementById('strat-error').style.display = 'flex';
  }
}

/* ─── SETUP ADVISOR ──────────────────────────────────────────────────── */
async function loadSetupAdvice() {
  var car = document.getElementById('setup-car').value.trim();
  var track = document.getElementById('setup-track').value.trim();

  if (!car || !track) {
    alert('Inserisci auto e pista.');
    return;
  }

  document.getElementById('setup-error').style.display = 'none';
  document.getElementById('setup-content').style.display = 'none';
  document.getElementById('setup-loading').style.display = 'flex';

  try {
    var res = await fetch('/api/setup?car=' + encodeURIComponent(car) + '&track=' + encodeURIComponent(track));
    var d = await res.json();

    if (!res.ok || d.insufficient_data) {
      document.getElementById('setup-error-text').textContent = d.message || 'Insufficient data for setup analysis.';
      document.getElementById('setup-error').style.display = 'flex';
      document.getElementById('setup-loading').style.display = 'none';
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
    document.getElementById('setup-loading').style.display = 'none';
  } catch (e) {
    document.getElementById('setup-error-text').textContent = 'Network error: ' + e.message;
    document.getElementById('setup-error').style.display = 'flex';
    document.getElementById('setup-loading').style.display = 'none';
  }
}


// ── Owner email (S-4) ──────────────────────────────────────────────────

async function loadOwner() {
  try {
    var r = await fetch('/api/owner');
    var d = await r.json();
    var input = document.getElementById('owner-email-input');
    if (input) input.value = d.email || '';
  } catch (e) {
    console.error('loadOwner:', e);
  }
}

async function saveOwner() {
  var input = document.getElementById('owner-email-input');
  var status = document.getElementById('owner-status');
  var email = (input.value || '').trim();
  if (email === '') {
    status.textContent = 'Inserisci un\'email o lascia vuoto per togliere il filtro';
    status.style.color = 'var(--text-muted)';
    return;
  }
  try {
    var r = await fetch('/api/owner', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({email: email})
    });
    var d = await r.json();
    if (r.ok) {
      status.textContent = '✓ Salvato (' + (d.email || 'nessuno') + ')';
      status.style.color = 'var(--accent-green)';
      // Re-load profile with the new filter
      if (typeof loadProfile === 'function') loadProfile();
      if (typeof loadLaps === 'function') loadLaps();
    } else {
      status.textContent = '✗ ' + (d.error || 'Errore');
      status.style.color = 'var(--accent-red)';
    }
  } catch (e) {
    status.textContent = '✗ Network error';
    status.style.color = 'var(--accent-red)';
  }
}

// Load owner when the profilo page is shown
var _origShowPage = showPage;
showPage = function(name) {
  _origShowPage(name);
  if (name === 'profilo') loadOwner();
};
