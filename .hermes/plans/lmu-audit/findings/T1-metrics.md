# T1 — Metriche Quantitative del Progetto LMU LarpTimes

> **Data analisi:** 2026-08-01  
> **Metodo:** Analisi statica (nessuna modifica al codice)  
> **Path:** `C:\Users\leob3\Desktop\LMU-LarpTimes-main\LMU-LarpTimes`

---

## 1. Riepilogo Generale

| Metrica | Valore |
|---------|--------|
| **LOC totali (intero progetto)** | **32.458** |
| **File totali (escluso .git e __pycache__)** | **120** |
| **File Python (.py)** | 76 |
| **File HTML (.html)** | 5 |
| **File JavaScript (.js)** | 3 |
| **File CSS (.css)** | 0 |
| **File JSON (.json)** | 4 |
| **File SQL (.sql)** | 1 |
| **File Markdown (.md)** | 7 |
| **File batch (.bat)** | 5 |
| **File audio (.wav)** | 9 |
| **Altri file (.txt, .db, .gitignore)** | 10 |

---

## 2. LOC per Modulo

| Modulo | LOC Totali | File | .py LOC | .html LOC | .js LOC | .json LOC | .sql LOC | Altro LOC |
|--------|-----------|------|---------|-----------|---------|-----------|----------|-----------|
| **web/** | 6.161 | 7 | 1.499 (2) | 2.347 (2) | 2.315 (3) | — | — | — |
| **overlay/** | 4.071 | 13 | 3.929 (6) | — | — | 142 (3) | — | 0 (4 wav) |
| **vendor/** | 3.389 | 11 | 3.389 (11) | — | — | — | — | — |
| **analysis/** | 3.086 | 15 | 3.086 (15) | — | — | — | — | — |
| **database/** | 2.495 | 3 | 2.340 (2) | — | — | — | 155 (1) | — |
| **telemetry/** | 853 | 3 | 853 (3) | — | — | — | — | — |
| **auth/** | 627 | 4 | 627 (4) | — | — | — | — | — |
| **security/** | 248 | 2 | 248 (2) | — | — | — | — | — |
| **tests/** | 6.017 | 24 | 6.017 (24) | — | — | — | — | — |
| **scripts/** | 487 | 2 | 487 (2) | — | — | — | — | — |
| **v2/** | 1.041 | 1 | — | 1.041 (1) | — | — | — | — |
| **root/** | 3.983 | 35 | 491 (5) | 1.925 (2) | — | — | — | 1.567 (28) |

> **Nota:** I valori tra parentesi indicano il numero di file per estensione.  
> **root/** include: `run_app.py`, `run_server.py`, `run_overlay_live.py`, `paths.py`, `demo_seed.py`, `BRAND_BOARD.html`, `UI_STRUCTURE_CLEAN.html`, `.md`, `.bat`, `.txt`.

---

## 3. Dettaglio LOC per File nei Moduli Principali

### 3.1 web/ (6.161 LOC)

| File | LOC | Tipo |
|------|-----|------|
| `web/server.py` | 1.499 | Python (FastAPI backend) |
| `web/__init__.py` | 0 | Python |
| `web/templates/index.html` | 1.385 | HTML |
| `web/templates/login.html` | 962 | HTML |
| `web/static/app.js` | 2.261 | JavaScript |
| `web/static/chart.umd.min.js` | 27 | JS (minificato) |
| `web/static/chartjs-plugin-annotation.min.js` | 27 | JS (minificato) |

### 3.2 overlay/ (4.071 LOC)

| File | LOC | Tipo |
|------|-----|------|
| `overlay/app.py` | 2.727 | Python (app PySide6) |
| `overlay/app_new.py` | 713 | Python (nuova versione) |
| `overlay/voice_engine.py` | 220 | Python |
| `overlay/icons.py` | 152 | Python |
| `overlay/strategy_refresher.py` | 117 | Python |
| `overlay/__init__.py` | 0 | Python |
| `overlay/overlay_config.json` | 7 | JSON |
| `overlay/profiles/last_used.json` | 14 | JSON |
| `overlay/profiles/test.json` | 121 | JSON |

### 3.3 analysis/ (3.086 LOC)

| File | LOC | Tipo |
|------|-----|------|
| `analysis/strategist.py` | 540 | Python |
| `analysis/race_director.py` | 437 | Python |
| `analysis/practice.py` | 339 | Python |
| `analysis/qualifying.py` | 321 | Python |
| `analysis/race_engineer.py` | 262 | Python |
| `analysis/pit_practice.py` | 238 | Python |
| `analysis/models.py` | 207 | Python |
| `analysis/compounds.py` | 199 | Python |
| `analysis/weather_radar.py` | 134 | Python |
| `analysis/microsectors.py` | 107 | Python |
| `analysis/tyre_manager.py` | 96 | Python |
| `analysis/weather.py` | 96 | Python |
| `analysis/classes.py` | 93 | Python |
| `analysis/anomaly.py` | 17 | Python |
| `analysis/__init__.py` | 0 | Python |

### 3.4 vendor/ (3.389 LOC)

| File | LOC | Tipo |
|------|-----|------|
| `vendor/pyLMUSharedMemory/lmu_data.py` | 1.192 | Python |
| `vendor/pyLMUSharedMemory/lmu_type.py` | 945 | Python |
| `vendor/pyLMUSharedMemory/lmu_mmap.py` | 39 | Python |
| `vendor/pyLMUSharedMemory/lmu_enum.py` | 82 | Python |
| `vendor/pyLMUSharedMemory/__init__.py` | 0 | Python |
| `vendor/pyRfactor2SharedMemory/sharedMemoryAPI.py` | 643 | Python |
| `vendor/pyRfactor2SharedMemory/rF2Type.py` | 362 | Python |
| `vendor/pyRfactor2SharedMemory/rF2data.py` | 67 | Python |
| `vendor/pyRfactor2SharedMemory/rF2MMap.py` | 59 | Python |
| `vendor/pyRfactor2SharedMemory/__init__.py` | 0 | Python |
| `vendor/__init__.py` | 0 | Python |

### 3.5 database/ (2.495 LOC)

| File | LOC | Tipo |
|------|-----|------|
| `database/cloud.py` | 2.340 | Python |
| `database/cloud_schema.sql` | 155 | SQL |
| `database/__init__.py` | 0 | Python |

---

## 4. Endpoint API REST

**Totale: 43 endpoint REST + 2 pagine HTML** (definiti in `web/server.py`)

### 4.1 Ripartizione per Metodo HTTP

| Metodo | Count |
|--------|-------|
| `GET` | 27 |
| `POST` | 16 |
| **Totale API** | **43** |

### 4.2 Ripartizione per Area Funzionale

| Area | Endpoint | Count |
|------|----------|-------|
| **Auth** | `/api/auth/register`, `/api/auth/login`, `/api/auth/logout`, `/api/auth/me` | 4 |
| **Sessioni** | `/api/sessions` | 1 |
| **Race Director** | `/api/race/sessions`, `/api/race/timeline` | 2 |
| **Overlay Settings** | `/api/overlay/settings` (GET+POST) | 2 |
| **Filtri** | `/api/filters/cars`, `/api/filters/tracks`, `/api/filters/compounds`, `/api/filters/classes` | 4 |
| **Setup** | `/api/setup` | 1 |
| **Cloud Sync** | `/api/cloud/user`, `/api/cloud/opt-in`, `/api/cloud/opt-out`, `/api/cloud/display-name`, `/api/cloud/status`, `/api/cloud/push`, `/api/cloud/pull` | 7 |
| **Laps CRUD** | `/api/laps`, `/api/laps/export`, `/api/laps/import`, `/api/laps/{id}/delete`, `/api/laps/{id}/restore`, `/api/laps/compare`, `/api/laps/{id}/telemetry`, `/api/laps/compare-telemetry`, `/api/laps/chart`, `/api/laps/optimal` | 10 |
| **Weather** | `/api/weather/forecast`, `/api/weather/stint-forecast`, `/api/weather/radar` | 3 |
| **Profile** | `/api/profile`, `/api/owner` (GET+POST), `/api/seed` | 4 |
| **Strategy** | `/api/strategy`, `/api/qualifying`, `/api/traffic`, `/api/practice`, `/api/pit-practice` | 5 |
| **Pagine HTML** | `/` (index), `/login` | 2 (non API) |

### 4.3 Elenco Completo Endpoint

```
GET  /api/auth/me
POST /api/auth/register
POST /api/auth/login
POST /api/auth/logout
GET  /api/sessions
GET  /api/race/sessions
GET  /api/race/timeline
GET  /api/overlay/settings
POST /api/overlay/settings
GET  /api/filters/cars
GET  /api/filters/tracks
GET  /api/filters/compounds
GET  /api/filters/classes
GET  /api/setup
GET  /api/cloud/user
POST /api/cloud/opt-in
POST /api/cloud/opt-out
POST /api/cloud/display-name
GET  /api/cloud/status
POST /api/cloud/push
POST /api/cloud/pull
GET  /api/laps/export
POST /api/laps/import
GET  /api/laps
GET  /api/laps/compare
GET  /api/laps/{lap_id}/telemetry
GET  /api/laps/compare-telemetry
GET  /api/laps/chart
POST /api/laps/{lap_id}/delete
POST /api/laps/{lap_id}/restore
GET  /api/weather/forecast
GET  /api/weather/stint-forecast
GET  /api/weather/radar
GET  /api/owner
POST /api/owner
POST /api/seed
GET  /api/profile
GET  /api/strategy
GET  /api/qualifying
GET  /api/laps/optimal
GET  /api/traffic
GET  /api/practice
GET  /api/pit-practice
GET  /            (pagina HTML)
GET  /login       (pagina HTML)
```

---

## 5. Test

| Metrica | Valore |
|---------|--------|
| **File di test** (`test_*.py`) | **22** |
| **File di supporto** (`__init__.py`, `fixtures.py`) | 2 |
| **LOC test totali** | **6.017** |
| **Funzioni di test** (`def test_*`) | **301** |

### 5.1 Dettaglio File di Test

| File | LOC | Test Functions |
|------|-----|---------------|
| `tests/test_icons.py` | 198 | 29 |
| `tests/test_auth.py` | 304 | 26 |
| `tests/test_e2e.py` | 390 | 25 |
| `tests/test_realtime.py` | 367 | 24 |
| `tests/test_security.py` | 401 | 22 |
| `tests/test_community_db.py` | 432 | 20 |
| `tests/test_compounds.py` | 383 | 19 |
| `tests/test_overlay_modular.py` | 271 | 17 |
| `tests/test_cloud_sync.py` | 401 | 16 |
| `tests/test_qualifying.py` | 260 | 16 |
| `tests/test_self_audit.py` | 190 | 16 |
| `tests/test_db_share.py` | 422 | 15 |
| `tests/test_setup_turso.py` | 401 | 14 |
| `tests/test_owner_email.py` | 327 | 13 |
| `tests/test_engine_core.py` | 429 | 10 |
| `tests/test_live_source.py` | 318 | 9 |
| `tests/test_db.py` | 123 | 3 |
| `tests/test_detector.py` | 120 | 2 |
| `tests/test_sources.py` | 84 | 2 |
| `tests/test_anomaly.py` | 84 | 1 |
| `tests/test_models.py` | 57 | 1 |
| `tests/test_strategist.py` | 55 | 1 |
| **Totale** | **6.017** | **301** |

---

## 6. Dipendenze Esterne

**Totale: 12 dipendenze** (da `requirements.txt`)

| # | Pacchetto | Versione minima | Categoria | Utilizzo |
|---|-----------|----------------|-----------|----------|
| 1 | `fastapi` | ≥0.104.1 | Web Framework | Server REST (`web/server.py`) |
| 2 | `uvicorn` | ≥0.24.0 | ASGI Server | Avvio server web |
| 3 | `numpy` | ≥1.26.2 | Calcolo numerico | Analisi dati, modelli |
| 4 | `scipy` | ≥1.11.4 | Calcolo scientifico | Degradazione gomme, fuel model |
| 5 | `scikit-learn` | ≥1.3.2 | ML/Statistica | Rilevamento anomalie, regressione |
| 6 | `PySide6` | ≥6.6.0 | GUI Desktop | Overlay in-game (`overlay/app.py`) |
| 7 | `psutil` | ≥5.9.6 | Sistema | Rilevamento processo gioco (telemetry) |
| 8 | `jinja2` | ≥3.1.2 | Template Engine | Pagine HTML (`web/templates/`) |
| 9 | `httpx` | ≥0.27.0 | HTTP Client | TestClient FastAPI, richieste HTTP |
| 10 | `bcrypt` | ≥4.0.0 | Sicurezza | Hashing password (`auth/`) |
| 11 | `PyJWT` | ≥2.8.0 | Sicurezza | Token JWT (`auth/`) |
| 12 | `pytest` | ≥7.4.3 | Testing | Framework test (`tests/`) |

### 6.1 Classificazione

| Categoria | Dipendenze |
|-----------|-----------|
| **Produzione** | 11 (tutte tranne pytest) |
| **Sviluppo/Test** | 1 (pytest) |
| **Web/Server** | fastapi, uvicorn, jinja2, httpx |
| **Analisi Dati** | numpy, scipy, scikit-learn |
| **GUI Desktop** | PySide6 |
| **Sistema** | psutil |
| **Sicurezza** | bcrypt, PyJWT |

---

## 7. Sintesi Architetturale

```
LMU-LarpTimes/
├── web/            (6.161 LOC) — Server FastAPI + frontend JS/HTML
│   ├── server.py   (1.499 LOC) — 43 endpoint REST
│   ├── static/     (2.315 LOC) — app.js + librerie Chart.js
│   └── templates/  (2.347 LOC) — index.html + login.html
├── overlay/        (4.071 LOC) — GUI PySide6 in-game overlay
│   ├── app.py      (2.727 LOC) — app principale
│   └── app_new.py  (713 LOC)   — nuova versione
├── analysis/       (3.086 LOC) — Logica di analisi racing
│   ├── strategist.py       (540 LOC)
│   ├── race_director.py    (437 LOC)
│   └── ...altri 13 file
├── vendor/         (3.389 LOC) — Librerie shared-memory (LMU + rFactor2)
├── database/       (2.495 LOC) — Cloud sync + schema SQL
│   └── cloud.py    (2.340 LOC) — file più grande del progetto
├── telemetry/      (853 LOC)  — Acquisizione dati in tempo reale
├── auth/           (627 LOC)  — Autenticazione JWT + bcrypt
├── security/       (248 LOC)  — Self-audit sicurezza
├── tests/          (6.017 LOC) — 22 file, 301 test
├── scripts/        (487 LOC)  — Utility (bundle, setup Turso)
├── v2/             (1.041 LOC) — Frontend alternativo
└── root/           (3.983 LOC) — Config, documentazione, script avvio
```

---

*Report generato automaticamente da analisi statica — nessuna modifica al codice.*
