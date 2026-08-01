# T12 — Audit Copertura Test

**Progetto:** LMU Pit Strategist  
**Data analisi:** 2026-08-01  
**Metodologia:** Analisi statica dei 24 file nella cartella `tests/` (22 test + fixtures.py + `__init__.py`), senza esecuzione  
**Totale moduli sorgente analizzati:** 30 file `.py` in `analysis/`, `auth/`, `overlay/`, `database/`, `telemetry/`, `security/`, `web/`

---

## 📊 Riepilogo Copertura per Modulo

| Modulo | Moduli testati | Moduli totali | % Copertura stimata | Giudizio |
|--------|---------------|---------------|---------------------|----------|
| **auth** | 3/3 | 3 | ~95% | ✅ Eccellente |
| **database** | 2/2 | 2 | ~90% | ✅ Buona |
| **security** | 2/2 | 2 | ~90% | ✅ Buona |
| **telemetry** | 2/2 | 2 | ~85% | ✅ Buona |
| **overlay** | 3/4 | 4 | ~60% | ⚠️ Parziale |
| **analysis** | 6/14 | 14 | ~43% | 🔴 Insufficiente |

---

## 🔬 Analisi Dettagliata per Modulo

### 1. ANALYSIS (`analysis/`)

#### Moduli TESTATI (6/14):

| File | Funzioni testate | File di test | Tipo | Mock/Real |
|------|-----------------|-------------|------|-----------|
| `models.py` | `fit_degradation_model()`, `fit_fuel_model()`, `DegradationModelFit` | `test_models.py`, `test_e2e.py`, `test_engine_core.py` | Unit + Integration | Real (dati sintetici) |
| `strategist.py` | `PitStrategist.__init__()`, `optimize()` | `test_strategist.py`, `test_compounds.py`, `test_e2e.py`, `test_engine_core.py` | Unit + Integration | Real (dati sintetici) |
| `compounds.py` | `_normalise_compound()`, `_is_wet()`, `_expected_stint_length()`, `_avg_pace_for_compound()`, `recommend_compound()`, `plan_compounds()` | `test_compounds.py` | Unit + Integration | Real |
| `qualifying.py` | `classify_qualifying_laps()`, `estimate_tyre_temp_window()`, `TYRE_COLD`, `TYRE_IN_WINDOW`, `TYRE_DEGRADED` | `test_qualifying.py` | Unit | Real |
| `anomaly.py` | `detect_anomalies_for_session()` | `test_anomaly.py`, `test_e2e.py`, `test_engine_core.py` | Unit + Integration | Real (DB temporaneo) |
| `weather.py` | `linear_rain_forecast()`, `build_stint_weather_forecast()` | `test_realtime.py` | Unit + Integration | Real |

#### Moduli NON TESTATI (8/14) — GAP CRITICI:

| File | Funzioni non testate | Righe | Criticità | Impatto |
|------|---------------------|-------|-----------|---------|
| **`race_engineer.py`** | `RaceEngineer.update_from_frame()`, `update_strategy()`, `_evaluate_critical_fuel()`, `_evaluate_critical_tyres()`, `_evaluate_critical_weather()`, `_evaluate_critical_strategy()`, `_evaluate_warning_*()`, `_evaluate_traffic()`, `_evaluate_performance()`, `_evaluate_session()`, `get_state_summary()`, `mark_spoken()`, `_can_speak()` | 496 | 🔴 CRITICA | Coordinatore centrale voce — nessun test |
| **`weather_radar.py`** | `analyze_rain_risk()`, `get_pit_recommendation()`, `RainWindow` | 106 | 🔴 CRITICA | Radar meteo avanzato — zero test |
| **`tyre_manager.py`** | `estimate_remaining_life()`, `normalize_compound()`, `TyreStatus` | 173 | 🟠 ALTA | Gestione gomme real-time — nessun test |
| **`classes.py`** | `detect_class()`, `get_class_params()`, `add_class_to_laps()`, `get_available_classes()`, `estimate_traffic_penalty()`, `compute_traffic_adjusted_pace()` | 238 | 🟠 ALTA | Multi-classe Hypercar/LMP2/GT3 — zero test |
| **`race_director.py`** | `build_race_timeline()`, `race_summary_to_dict()`, `RaceSummary`, `RaceEvent`, `StintInfo` | 234 | 🟡 MEDIA | Timeline gara — nessun test |
| **`microsectors.py`** | `compute_microsector_times()`, `compute_optimal_lap()`, `format_time()` | 220 | 🟡 MEDIA | Micro-settori e giro ideale — zero test |
| **`practice.py`** | `analyze_practice_data()` | 190 | 🟡 MEDIA | Analisi qualità dati practice — nessun test |
| **`pit_practice.py`** | `extract_pit_stops()`, `analyze_pit_performance()` | 100 | 🟢 BASSA | Analisi pit stop — nessun test |

**Percentuale copertura stimata per analysis: ~43%**

---

### 2. AUTH (`auth/`)

#### Moduli TESTATI (3/3):

| File | Funzioni testate | File di test | Tipo | Mock/Real |
|------|-----------------|-------------|------|-----------|
| `crypto.py` | `hash_password()`, `verify_password()`, `create_jwt()`, `decode_jwt()` | `test_auth.py` | Unit | Real (bcrypt, JWT) |
| `db.py` | `create_user()`, `get_user_by_id()`, `get_user_by_email()`, `get_user_by_google_id()`, `delete_user()`, `list_users()`, `authenticate_user()`, `set_current_user()`, `get_current_user()`, `clear_current_user()`, `get_current_token()` | `test_auth.py` | Unit + Integration | Real (DB temporaneo) |
| `manager.py` | `AuthManager.register_email()`, `login_email()`, `login_google()`, `logout()`, `verify_token()`, `is_logged_in()`, `get_current()`, `get_token()` | `test_auth.py` | Unit + Integration | Real (DB temporaneo) |

**Percentuale copertura stimata: ~95%**  
**Nessun gap rilevato.**

Test coprono: password hashing, verifica, JWT roundtrip, JWT scaduto, token invalido, CRUD utenti, duplicati, campi obbligatori, autenticazione, Google login, logout, sessione attiva, utente inattivo.

---

### 3. OVERLAY (`overlay/`)

#### Moduli TESTATI (3/4):

| File | Funzioni testate | File di test | Tipo | Mock/Real |
|------|-----------------|-------------|------|-----------|
| `app_new.py` | `load_config()`, `save_config()`, `MiniOverlay`, `DeltaOverlay`, `FuelOverlay`, `CliffOverlay`, `PitOverlay`, `OverlayManager`, `DEFAULT_CONFIG`, `DEFAULT_POSITIONS`, `COMPONENT_ORDER`, `COMPONENT_LABELS` | `test_overlay_modular.py` | Unit (offscreen Qt) | Real (QApplication offscreen) |
| `icons.py` | `settings_icon()`, `refresh_cw_icon()`, `eye_icon()`, `eye_off_icon()`, `globe_icon()`, `x_icon()`, `rotate_ccw_icon()`, `zap_icon()`, `circle_dot_icon()`, `play_icon()`, `crosshair_icon()`, `flame_icon()`, `droplet_icon()`, `thermometer_icon()`, `cloud_rain_icon()`, `cloud_icon()`, `flag_icon()`, `volume_2_icon()`, `volume_x_icon()`, `check_icon()`, `alert_triangle_icon()`, `moon_icon()`, `book_open_icon()`, `ban_icon()`, `icon_pixmap()`, `icon_widget()`, `clean_action_text()` | `test_icons.py` | Unit (offscreen Qt) | Real (QApplication offscreen) |
| `strategy_refresher.py` | `StrategyRefresher._has_state_changed()`, `_plan_signature()`, `_tick()`, `request_refresh()`, `AudioEngine.play()`, `clear_cooldowns()`, `PracticeAdvisor.advise()` | `test_realtime.py`, `test_engine_core.py` | Unit | Real + Mock (MockManager) |

#### Moduli NON TESTATI (1/4):

| File | Funzioni non testate | Righe | Criticità |
|------|---------------------|-------|-----------|
| **`voice_engine.py`** | `VoiceEngine.__init__()`, `speak()`, `_generate_wav()`, `_cleanup_cache()`, `play_test()`, `set_volume()` | 117 | 🟡 MEDIA |

**Percentuale copertura stimata: ~60%**

---

### 4. DATABASE (`database/`)

#### Moduli TESTATI (2/2):

| File | Funzioni testate | File di test | Tipo | Mock/Real |
|------|-----------------|-------------|------|-----------|
| `__init__.py` | `init_db()`, `create_session()`, `create_stint()`, `insert_lap()`, `get_laps_for_analysis()`, `get_all_laps_for_archive()`, `soft_delete_lap()`, `export_sessions()`, `import_sessions()`, `push_pending_sessions()`, `pull_remote_sessions()`, `get_sync_status()`, `get_local_user()`, `opt_in_to_community()`, `opt_out_of_community()`, `set_display_name()`, `_attach_user_to_payload()`, `_generate_display_name()`, `get_owner_email()`, `set_owner_email()` | `test_db.py`, `test_cloud_sync.py`, `test_db_share.py`, `test_community_db.py`, `test_owner_email.py`, `test_e2e.py` | Unit + Integration + API | Real (DB temporaneo) + Mock (backend cloud) |
| `cloud.py` | `NullSync`, `TursoSync`, `DuckDBR2Sync`, `HTTPSync`, `backend_from_config()`, `set_backend()`, `get_backend()` | `test_cloud_sync.py`, `test_security.py` | Unit | Real + Mock (backend mock) |

**Percentuale copertura stimata: ~90%**  
**Nessun gap rilevato.**

Test coprono: WAL mode, CRUD sessioni/lap, soft delete/restore, export/import, dedup, overwrite, roundtrip, CLI bundle_laps, sync cloud (push/pull/status), NullSync, MockSync, backend factory, community opt-in/out, attach user, push con filtro laps minimi, owner email (set/get/backfill/auto-tag/API filter), validazione email, migrazione sync_queue.

---

### 5. TELEMETRY (`telemetry/`)

#### Moduli TESTATI (2/2):

| File | Funzioni testate | File di test | Tipo | Mock/Real |
|------|-----------------|-------------|------|-----------|
| `source.py` | `SyntheticReplaySource` (start/stop/get_next_frame, pit stop simulation), `LiveSharedMemorySource` (LMU detection, RF2 fallback, frame parsing, weather, pits, qualifying), `TelemetryFrame` | `test_sources.py`, `test_live_source.py`, `test_e2e.py` | Unit | Mock (shared memory patched) + Real (synthetic) |
| `detector.py` | `LapBoundaryDetector.process_frame()`, tyre change detection, `on_session_complete` hook | `test_detector.py`, `test_community_db.py`, `test_e2e.py` | Unit + Integration | Real (DB temporaneo) |

**Percentuale copertura stimata: ~85%**

Test coprono: frame processing, lap boundary detection, settori, fuel tracking, tyre age tracking, compound change → stint reset, session completion hook, LMU source detection, RF2 fallback, weather parsing, pit flags, qualifying session type, exception handling, synthetic replay.

---

### 6. SECURITY (`security/` + `web/server.py`)

#### Moduli TESTATI (2/2):

| File | Funzioni testate | File di test | Tipo | Mock/Real |
|------|-----------------|-------------|------|-----------|
| `self_audit.py` | `check_gitignore()`, `check_env_permissions()`, `check_env_token()`, `check_host_binding()`, `check_webbrowser_exposed()`, `run_audit()` | `test_self_audit.py` | Unit | Real |
| `web/server.py` | Security headers (CSP, X-Content-Type-Options, X-Frame-Options), rate limiting (429), import validation (payload size, structure, laps count, sessions count, stints count, JSON validity), strategy endpoint input validation, SQL injection (TursoSync parameterized queries), data leak (export no token, .env gitignored), CORS, path traversal, CSRF (DELETE requires POST), owner email validation | `test_security.py`, `test_e2e.py`, `test_db_share.py`, `test_community_db.py`, `test_owner_email.py`, `test_realtime.py` | Unit + Integration (TestClient) | Real (FastAPI TestClient) + Mock (monkeypatch rate limit) |

**Percentuale copertura stimata: ~90%**

---

## 🎯 Analisi Feature Critiche

### PitStrategist (`analysis/strategist.py`)
**Copertura: ✅ ECCELLENTE (~90%)**

Test presenti:
- `test_strategist.py`: test base con parametri semplici, verifica pit laps, alternative, 0-stop invalido
- `test_engine_core.py`: **T-2 brute-force DP verification** (6 scenari parametrizzati), **T-3 outlier detection**, **T-4 k_fuel=0 edge case** (forced pit e DNF), **T-5 performance** (100 laps < 2s), **T-6 refresher** (state change detection, plan signature)
- `test_compounds.py`: integrazione con `compound_plan`, weather forecast, rain
- `test_e2e.py`: integrazione end-to-end con modelli reali

### Race Engineer (`analysis/race_engineer.py`)
**Copertura: 🔴 ZERO (0%) — NESSUN TEST**

Funzioni completamente non testate:
- ❌ `RaceEngineer.update_from_frame()` — processa frame telemetria
- ❌ `RaceEngineer.update_strategy()` — aggiorna pit plan
- ❌ `_evaluate_critical_fuel()` — "PIT NOW — fuel critical!"
- ❌ `_evaluate_critical_tyres()` — "PIT NOW — tyres at cliff!"
- ❌ `_evaluate_critical_weather()` — "RAIN — pit for wets!"
- ❌ `_evaluate_critical_strategy()` — "Pit window OPEN"
- ❌ `_evaluate_warning_fuel()` — warning benzina bassa
- ❌ `_evaluate_warning_tyres()` — warning gomme
- ❌ `_evaluate_warning_weather()` — warning pioggia in arrivo
- ❌ `_evaluate_warning_strategy()` — "Pit in N laps"
- ❌ `_evaluate_traffic()` — traffico GT3
- ❌ `_evaluate_performance()` — personal best, consistenza
- ❌ `_evaluate_session()` — annunci inizio sessione
- ❌ `get_state_summary()` — riepilogo overlay
- ❌ `_can_speak()` — cooldown logica
- ❌ `mark_spoken()` — dedup eventi

**Rischio:** Il Race Engineer è il coordinatore centrale che integra fuel, gomme, meteo, traffico e strategia in una macchina a stati per eventi vocali. È la feature più complessa del progetto (496 righe) e non ha alcun test. Ogni modifica potrebbe rompere silenziosamente la logica di prioritizzazione eventi.

### Weather Radar (`analysis/weather_radar.py`)
**Copertura: 🔴 ZERO (0%) — NESSUN TEST**

Funzioni non testate:
- ❌ `analyze_rain_risk()` — analisi rischio pioggia con forecast
- ❌ `get_pit_recommendation()` — raccomandazione pit per meteo
- ❌ `RainWindow` dataclass

**Nota:** `analysis/weather.py` (`linear_rain_forecast`, `build_stint_weather_forecast`) è testato in `test_realtime.py`. Ma `weather_radar.py` è un modulo separato più avanzato con logica diversa.

### Tyre Manager (`analysis/tyre_manager.py`)
**Copertura: 🔴 ZERO (0%) — NESSUN TEST**

- ❌ `estimate_remaining_life()` — stima vita residua gomme (con wear rate, temperatura, compound)
- ❌ `normalize_compound()` — normalizzazione nome mescola
- ❌ `TyreStatus` dataclass

---

## 📈 Classificazione Test: Unit vs Integration vs Mock

### Unit Test (no dipendenze esterne, solo mock/DB temporaneo)
- `test_models.py` — ✅ Puro unit test su `fit_degradation_model` e `fit_fuel_model`
- `test_strategist.py` — ✅ Unit test su `PitStrategist.optimize()` con model fit mockato
- `test_qualifying.py` — ✅ Unit test su funzioni qualifying
- `test_compounds.py` — ✅ Unit test su funzioni compounds + integrazione strategist
- `test_icons.py` — ✅ Unit test su SVG rendering
- `test_engine_core.py` — ✅ Unit test su DP brute-force verification, edge case, performance
- `test_live_source.py` — ✅ Unit test con mock shared memory
- `test_sources.py` — ✅ Unit test su `SyntheticReplaySource`
- `test_self_audit.py` — ✅ Unit test su security checks

### Integration Test (DB reale, API endpoint)
- `test_db.py` — ✅ Integration: DB reale temporaneo
- `test_anomaly.py` — ✅ Integration: DB + anomaly detection
- `test_detector.py` — ✅ Integration: DB + detector
- `test_auth.py` — ✅ Integration: DB auth + crypto reale
- `test_cloud_sync.py` — ✅ Integration: DB + mock backend cloud
- `test_db_share.py` — ✅ Integration: DB + API + CLI
- `test_community_db.py` — ✅ Integration: DB + mock backend + API
- `test_owner_email.py` — ✅ Integration: DB + API
- `test_e2e.py` — ✅ Integration: pipeline completa (DB → telemetry → analysis → strategist → API)
- `test_realtime.py` — ✅ Integration: API + weather forecaster
- `test_security.py` — ✅ Integration: FastAPI TestClient
- `test_setup_turso.py` — ✅ Integration: subprocess + mock libsql
- `test_overlay_modular.py` — ✅ Unit con QApplication offscreen

### Mock vs Real
| Approccio | File di test |
|-----------|-------------|
| **Real (DB temporaneo)** | `test_db.py`, `test_anomaly.py`, `test_detector.py`, `test_auth.py`, `test_e2e.py`, `test_cloud_sync.py`, `test_db_share.py`, `test_community_db.py`, `test_owner_email.py` |
| **Real (FastAPI TestClient)** | `test_security.py`, `test_e2e.py`, `test_realtime.py`, `test_db_share.py`, `test_community_db.py`, `test_owner_email.py` |
| **Real (QApplication offscreen)** | `test_overlay_modular.py`, `test_icons.py` |
| **Real (subprocess CLI)** | `test_db_share.py`, `test_setup_turso.py` |
| **Mock (backend cloud)** | `test_cloud_sync.py`, `test_community_db.py` |
| **Mock (shared memory)** | `test_live_source.py` |
| **Mock (libsql client)** | `test_setup_turso.py` |
| **Synthetic data** | `fixtures.py`, `test_engine_core.py`, `test_e2e.py` |

---

## 🚨 Priorità Azioni

### P0 — CRITICHE (bloccano la fiducia nel sistema)
1. **Race Engineer** (`analysis/race_engineer.py`): 0% copertura, 496 righe, coordinatore centrale eventi vocali
   - Testare: `update_from_frame()` con frame mockati, ogni `_evaluate_*()`, `_can_speak()` cooldown, `mark_spoken()` dedup
2. **Weather Radar** (`analysis/weather_radar.py`): 0% copertura, modulo meteo avanzato
   - Testare: `analyze_rain_risk()` con forecast data, `get_pit_recommendation()` per ogni scenario

### P1 — ALTE (feature core senza safety net)
3. **Tyre Manager** (`analysis/tyre_manager.py`): 0% copertura, gestione gomme real-time
   - Testare: `estimate_remaining_life()` con vari wear rate, compound, temperature
4. **Multi-Class** (`analysis/classes.py`): 0% copertura, detection Hypercar/LMP2/GT3
   - Testare: `detect_class()` per ogni auto conosciuta, `estimate_traffic_penalty()` per ogni combinazione classi

### P2 — MEDIE (quality-of-life)
5. **Race Director** (`analysis/race_director.py`): 0% copertura, timeline gara
6. **Micro-sectors** (`analysis/microsectors.py`): 0% copertura, giro ideale
7. **Practice Analyzer** (`analysis/practice.py`): 0% copertura, analisi dati
8. **Voice Engine** (`overlay/voice_engine.py`): 0% copertura, TTS engine

### P3 — BASSE (nice-to-have)
9. **Pit Practice** (`analysis/pit_practice.py`): 0% copertura, analisi pit stop

---

## 📊 Statistiche Globali

| Metrica | Valore |
|---------|--------|
| Totale file di test | 21 (esclusi `__init__.py` e `fixtures.py`) |
| Totale funzioni di test | ~120+ |
| Moduli sorgente totali | 30 |
| Moduli con 0% copertura | 9 (30%) |
| Moduli con >80% copertura | 12 (40%) |
| Unit test puri | ~50% dei test |
| Integration test | ~40% dei test |
| Test con mock | ~10% dei test |
| Copertura media pesata | ~65% (trainata da auth/database/telemetry) |
| Copertura analysis (core business) | ~43% (critica) |

---

## ✅ Punti di Forza

1. **`test_engine_core.py`** — Eccellente: brute-force DP verification con 6 scenari parametrizzati, edge case k_fuel=0, performance test, state change detection
2. **`test_auth.py`** — Completo: copre tutte le operazioni CRUD, edge case, JWT, sessioni
3. **`test_security.py`** — Robusto: security headers, rate limiting, input validation, SQL injection detection, data leak prevention
4. **`test_compounds.py`** — Completo: tutti i path dry/wet, scoring, integrazione strategist
5. **`test_qualifying.py`** — Completo: classificazione giri, finestra temperatura, edge case
6. **`fixtures.py`** — Ben progettato: dati sintetici condivisi, modello di degradazione parametrico

## ⚠️ Aree di Rischio

1. **Race Engineer** (496 righe, 0 test) — se questo modulo ha un bug, l'intero sistema di notifiche vocali è compromesso
2. **Weather Radar** (106 righe, 0 test) — raccomandazioni pit basate su meteo potrebbero essere errate
3. **Tyre Manager** (173 righe, 0 test) — stime vita gomme errate → strategia pit sbagliata
4. **Classi Multi-Classe** (238 righe, 0 test) — detection classe errata → parametri strategia sbagliati
5. **Dipendenza da `test_e2e.py`** — molti moduli sono testati solo indirettamente via E2E; se l'E2E fallisce è difficile isolare il modulo responsabile
