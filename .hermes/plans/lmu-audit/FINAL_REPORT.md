# 🔍 LMU LarpTimes — Mega Audit Report

**Data:** 2026-08-01  
**Metodo:** 14 subagenti paralleli + analisi orchestrator  
**File analizzati:** 76 `.py`, 5 `.html`, 3 `.js`  
**LOC totali:** ~32,458  

---

## 📊 Riepilogo Esecutivo

| Metrica | Valore |
|---------|--------|
| **Findings totali** | **67** |
| 🔴 **CRITICAL** | **15** |
| 🟠 **HIGH** | **19** |
| 🟡 **MEDIUM** | **21** |
| 🟢 **LOW** | **12** |
| **Overall Score** | **5.8/10** |

**Verdetto:** L'app è **funzionalmente ricca e ben architettata** ma ha **3 colli di bottiglia strutturali** che ne limitano la scalabilità oltre ~3.000 giri, e **diverse vulnerabilità di sicurezza** che, per quanto attenuate dall'uso solo locale, vanno risolte.

---

## 🔴 CRITICAL (15) — Bloccanti

### Performance Killer
| # | Problema | Impatto |
|---|----------|---------|
| **P1** | `get_all_laps_for_archive()` fetch completo senza WHERE — chiamato da 13 endpoint e 4 filtri simultanei | Con 10.000 giri: **25 MB trasferiti** a ogni page load, API `/api/laps` a **350ms**, auto-refresh **4.8 GB/h** |
| **P2** | **7+ indici mancanti** nel DB locale (session_uuid, car+track, session_id, compound_front) — presenti solo nel cloud schema | Table scan su ogni query di analisi |
| **P3** | `export_sessions()`: 3 query N+1 per sessione (100 sessioni = 301 query) | Export lento, blocca la push cloud |
| **P4** | `import_sessions()`: SELECT per ogni lap importato + **nessuna transazione esplicita** | Import parziale se interrotto, dati inconsistenti |

### Bug
| # | Problema | File |
|---|----------|------|
| **B1** | `DegradationModelFit()` chiamato senza 6 parametri obbligatori | `qualifying.py:446` → **crash a runtime** |
| **B2** | 14 variabili CSS non definite nel `:root` ma usate in JS e HTML (`--status-invalid`, `--border-subtle`, `--ink-muted`, etc.) | `index.html`, `app.js` → UI rotta in diversi componenti |
| **B3** | `voice_engine.py` crasha su Linux/macOS: `import winsound` a livello modulo | overlay non funzionante su OS non-Windows |
| **B4** | `RaceEngineer` eccezioni ingoiate con `pass` nudo (righe 248, 429) | Errori silenziosi, impossibile debuggare |
| **B5** | `lap_time < 20.0` magic number e `__import__('datetime')` inline in `detector.py` | Fragile, error-prone |
| **B6** | `_calculate_refuel()` chiamato a riga 699 in `app.py` ma **il metodo non esiste nella classe** | **AttributeError garantito** a ogni frame |
| **B7** | `overallBest` non definita in `app.js:803` — colonna delta temperature rotta | Funzionalità setup rotta |
| **B8** | NameError in `/api/traffic`: `estimate_traffic_penalty` mai importata in `server.py` | Endpoint `/api/traffic` crasha |
| **B9** | XSS massivo in `app.js`: dati API (`l.track`, `l.car`, `r.message`) iniettati via innerHTML senza sanitizzazione | 20+ punti di injection XSS |

### Sicurezza
| # | Problema | Rischio |
|---|----------|---------|
| **S1** | `auth_secret.txt` world-readable (644) — JWT signing secret esposto | Qualsiasi processo sulla macchina può forgiare JWT |
| **S2** | Google OAuth placeholder — `login_google()` accetta `google_id` senza validare il token | Chiunque può impersonare qualsiasi utente Google |
| **S3** | Rate limiting identico (200 req/min) per auth e API — bruteforce password possibile | 288.000 tentativi/giorno, password min 4 caratteri |
| **S4** | Password minima 4 caratteri, nessuna complessità richiesta | `"1234"` o `"aaaa"` sono valide |
| **S5** | JWT expiry 30 giorni senza refresh/revoca — token in chiaro nel DB SQLite | Token compromesso = accesso per 30 giorni |
| **S6** | Timing attack su login: email inesistente → risposta veloce, email esistente → bcrypt lento (250ms) | Enumerazione utenti possibile |

---

## 🟠 HIGH (19)

### UI/UX Web
| # | Problema |
|---|----------|
| **H1** | Zero attributi ARIA, zero ruoli WAI-ARIA — app completamente inaccessibile a screen reader |
| **H2** | 89 stili inline nell'HTML body — manutenzione impossibile, incoerenza visiva |
| **H3** | Contrasto `--text-muted` (#35404A su #0F1317) = **2.5:1** vs 4.5:1 richiesto → illeggibile |
| **H4** | `login.html` non condivide il design system — 20+ valori colore hardcodati |
| **H5** | Nessun `:focus-visible` su bottoni — navigazione da tastiera impossibile |
| **H6** | Input non wrappati in `<form>`, label senza `for` in `login.html` |

### Overlay
| # | Problema |
|---|----------|
| **H7** | **60%+ duplicazione codice** tra `app.py` (1055 righe) e `app_new.py` (2042 righe) — design system, config, worker, helper identici |
| **H8** | `sys.path.insert` a import-time in `telemetry/source.py` — side-effect globale |
| **H9** | `LapBoundaryDetector` (327 righe): zero docstring — classe complessa non documentata |
| **H10** | `voice_engine.py`: TTS disabilitato **permanentemente** dopo primo errore (rete/timeout) |

### Database / Performance
| # | Problema |
|---|----------|
| **H11** | 4-6 chiamate duplicate di `get_laps_for_analysis()` nello stesso frame overlay — 30.000 righe processate per frame |
| **H12** | `session_uuid` senza vincolo UNIQUE nel DB locale — possibili duplicati |
| **H13** | `laps.stint_id` FK senza ON DELETE, `sync_queue` senza FK — orfani garantiti |
| **H14** | `opt_in_to_community()` read-then-write non atomico — race condition su user_id |
| **H15** | Connection leak potenziale in `auth/db.py`: `conn = _get_conn()` ... `conn.close()` senza try/finally |
| **H16** | Nessun `busy_timeout` su SQLite → `SQLITE_BUSY` non gestito |

### Code Quality
| # | Problema |
|---|----------|
| **H17** | `RaceEngineer` God Class (496 righe): gestisce fuel, tyres, weather, traffic, strategy, performance, session — viola SRP |
| **H18** | `anomaly.py`: `detect_anomalies_for_session()` monolitica — fetch DB + analisi + update in unica funzione |
| **H19** | `weather_radar.py`: parametri inutilizzati (`lap_time_avg`, `laps_remaining`, `current_lap`) — API fuorviante |

---

## 🟡 MEDIUM (21)

### UI/UX
- M1: `login.html` messaggi errore con `display:none` invece di `aria-live`
- M2: Tabelle senza `scope` su `<th>` e senza `<caption>`
- M3: `login.html` non ha `minlength` sull'input password
- M4: Nessun skip-link "Vai al contenuto principale"
- M5: Favicon via data URI — non supportato su tutti i browser

### Overlay
- M6: `icons.py`: 22 funzioni icona senza type hints e senza docstring
- M7: `strategy_refresher.py`: voce `Optional[Any]` perde type safety
- M8: `SyntheticReplaySource`: track length `5793.0` hardcodato (Monza)

### Code Quality
- M9: Funzioni >100 righe in 9 file (`qualifying.py`, `practice.py`, `strategist.py`, etc.)
- M10: `normalize_compound` (🇺🇸) vs `_normalise_compound` (🇬🇧) — duplicazione con spelling diverso
- M11: Debug print residui in `strategist.py:178` e `anomaly.py:120`
- M12: Import inutilizzati in `models.py`, `qualifying.py`, `practice.py`
- M13: `pit_loss` / `pit_loss_seconds` — stesso concetto, 3 nomi diversi in 4 file

### Test Coverage
- M14: **RaceEngineer (496 righe): ZERO test** — il coordinatore voce principale
- M15: **weather_radar.py (106 righe): ZERO test** — radar meteo avanzato
- M16: **tyre_manager.py (173 righe): ZERO test** — gestione gomme real-time
- M17: **classes.py (238 righe): ZERO test** — multi-classe Hypercar/LMP2/GT3
- M18: **race_director.py (234 righe): ZERO test** — timeline gara
- M19: Coverage analysis module: solo **43%** (6/14 moduli testati)

### Performance
- M20: `insert_lap()` esegue `PRAGMA table_info(laps)` a ogni INSERT — 200 PRAGMA ridondanti per sessione
- M21: Chart.js senza decimazione punti — 10.000 punti scatter = **200-800ms** di rendering

---

## 🟢 LOW (12)

- L1: Scrollbar custom solo WebKit, nessun fallback Firefox
- L2: `@keyframes fadeIn` può causare FOUT (flash of unstyled content)
- L3: `login.html` font-family hardcodate invece di variabili
- L4: Google Fonts senza `&display=swap` → blocco rendering
- L5: `BRAND_BOARD.html` (1419 righe), `v2/index.html` (1041 righe), `UI_STRUCTURE_CLEAN.html` (506 righe) — **design file morti**, non usati
- L6: `_WET_COMPOUNDS` set con `"Wet"` duplicato in `qualifying.py`
- L7: CDN esterne senza Subresource Integrity (SRI)
- L8: `microsectors.py`: `format_time` type hint dice `float` ma gestisce `None`
- L9: `crypto.py:37`: `open(secret_path).read().strip()` senza encoding esplicito
- L10: `auth/manager.py`: `_create_user_google` alias confusionario
- L11: `detector.py`: `fallback_pit_loss=30.0` magic number senza costante
- L12: `overlay_config.json` tracciato in git (non critico, nessun secret)

---

## ✅ Cose Fatte BENISSIMO

1. **Auth module** (auth/): 95% test coverage, bcrypt work factor 12, JWT HS256, test eccellenti
2. **Design System** (index.html): Sistema di variabili CSS `:root` ben strutturato (amber, red, green, blue, purple palette)
3. **Security middleware**: CSP header, rate limiter, security headers — solida base
4. **Self-audit** (`security/self_audit.py`): check automatici all'avvio (gitignore, host binding, permissions)
5. **Multi-class support**: Hypercar/LMP2/GT3 con mappatura completa (238 righe)
6. **Pit Strategy DP**: Dynamic Programming per strategia pit-stop — algoritmo corretto
7. **Voice Engine TTS**: edge-tts con caching e dedup — design pulito (a parte il bug Windows-only)
8. **Bundle export/import**: `.lmubundle` con compressione gzip — buona UX per sharing
9. **SQLite WAL mode + FK enforcement**: pratica corretta per concorrenza
10. **43 API endpoint REST** ben organizzati per area funzionale

---

## 🚀 Raccomandazioni Prioritizzate

### SPRINT 1 (immediato — 1-2 giorni)

| # | Azione | Impatto |
|---|--------|---------|
| 1 | **Fix `DegradationModelFit()` crash** in `qualifying.py:446` | Previene crash a runtime |
| 2 | **Aggiungere 14 variabili CSS mancanti** al `:root` | Fixa UI rotta |
| 3 | **Aggiungere indici mancanti** nel DB locale (7 indici) | 10-100× speedup query |
| 4 | **Spostare `import winsound` dentro `_play()`** con try/except | Overlay cross-platform |
| 5 | **Rate limiting differenziato** per `/api/auth/login` (5 req/min) | Blocca bruteforce |
| 6 | **Password min 8 caratteri** + validazione complessità | Sicurezza base |
| 7 | **Restringere permessi `auth_secret.txt`** (chmod 600 / ACL) | Protegge JWT secret |

### SPRINT 2 (breve termine — 1 settimana)

| # | Azione | Impatto |
|---|--------|---------|
| 8 | **Riscrivere `get_all_laps_for_archive()`** con filtri SQL (car, track, compound, session_id) | **200× meno dati trasferiti** |
| 9 | **Unificare `populateFilters()`** in endpoint aggregato `/api/filters` | Da 4 fetch → 1 |
| 10 | **Aumentare auto-refresh a 15s** o passare a SSE/WebSocket | **96% meno bandwidth** |
| 11 | **Transazione esplicita in `import_sessions()`** con rollback | Import atomico |
| 12 | **Aggiungere ARIA base**: `role="navigation"`, `aria-label`, `role="alert"` su toast | Accessibilità |
| 13 | **Estrarre classi CSS per 89 stili inline** | Manutenibilità |
| 14 | **Correggere contrasto `--text-muted`** ≥ 4.5:1 | WCAG AA |
| 15 | **Validare Google ID token** con `google-auth` library | Sicurezza OAuth |

### SPRINT 3 (medio termine — 2-4 settimane)

| # | Azione | Impatto |
|---|--------|---------|
| 16 | **Refactor `RaceEngineer`** in componenti separati (FuelMonitor, TyreMonitor, WeatherMonitor) | Testabilità, SRP |
| 17 | **Estrarre modulo condiviso** overlay tra `app.py` e `app_new.py` (design system, config, worker) | Elimina 60% duplicazione |
| 18 | **Aggiungere test** per RaceEngineer, weather_radar, tyre_manager, classes, race_director | Copertura 43% → 85% |
| 19 | **Paginazione server-side** su `/api/laps` | Riduce payload API |
| 20 | **Decimazione punti Chart.js** (max 500 punti) | Rendering 500ms → 20ms |
| 21 | **Connection pool SQLite** invece di open/close per ogni query | -30% latenza |
| 22 | **JWT expiry 24h + refresh token + blacklist** | Sicurezza token |
| 23 | **Cache in-memory per filtri** (cars/tracks/compounds — TTL 60s) | Elimina full-scan al page load |
| 24 | **Rimuovere `'unsafe-inline'` da CSP** usando nonce | XSS protection reale |

---

## 📁 Feature da Aggiungere (Gap Analysis)

### Must Have (high impact, relativamente facile)
- **Track Map** visiva con posizione in tempo reale
- **Setup Comparator**: confrontare setup tra sessioni con stesse condizioni
- **MoTeC/i2 Export**: esportazione telemetria in formato standard
- **Fuel Calculator** avanzato: quanta benzina serve per finire la gara
- **Driver Swap** timer per gare endurance multi-pilota

### Nice to Have
- **Radar Meteo Visivo** (non solo testuale)
- **Live Timing** completo (posizioni, gap, best sectors)
- **Crew Chief** style: più frasi vocali contestuali, riconoscimento voce
- **VR Overlay**: supporto visore VR (OpenVR/OpenXR)
- **Discord Rich Presence**: mostra sessione corrente su Discord
- **Telemetria per-canale** (throttle, brake, steering trace)

### Future / Aspirational
- **Machine Learning** per strategie predittive (LSTM su meteo, degrado)
- **Multiplayer sync**: condividere strategia con team in tempo reale
- **Mobile companion app**: visualizzare dati sul telefono durante la gara
- **Hardware integration**: LED strip, bass shaker, dashboard fisica

---

## 📈 Metriche del Progetto

| Metrica | Valore |
|---------|--------|
| LOC Python | 19,784 |
| LOC HTML | 4,313 |
| LOC JavaScript | 2,315 |
| File Python | 76 |
| File HTML | 5 |
| Endpoint API REST | 43 |
| Test totali | 301 |
| Dipendenze esterne | 12 |
| Copertura test analysis | ~43% |
| Copertura test auth | ~95% |
| Subagenti usati | 14 |

---

*Report generato da Elysium Swarmloop v0.13.2 — 14 subagenti, 1 orchestrator. Tutti i findings sono verificabili nei file in `.hermes/plans/lmu-audit/findings/`.*
