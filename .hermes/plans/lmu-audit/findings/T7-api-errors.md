# T7 — Audit Error Handling e Resilienza API

**File analizzato:** `web/server.py` (1499 linee) + `database/__init__.py` (1762 linee)  
**Data:** 2026-08-01  
**Versione:** LMU Pit Strategist v1.0.0

---

## 📊 Riepilogo Esecutivo

| Metrica | Valore | Severità |
|---|---|---|
| Endpoint totali | 45 | — |
| Endpoint con try/except | 11 (24%) | 🔴 CRITICAL |
| Endpoint senza try/except | 34 (76%) | 🔴 CRITICAL |
| Exception handler FastAPI registrati | 0 | 🔴 CRITICAL |
| Import `logging` in server.py / database | 0 | 🔴 CRITICAL |
| try/except nel layer database | 0 | 🔴 CRITICAL |
| Formato errore consistente (JSON) | ❌ Misto | 🟠 HIGH |
| Rate limiter | In-memory, resetta al riavvio | 🟡 MEDIUM |
| Timeout su query DB | Nessuno | 🟠 HIGH |
| Gestione DB corrotto | Nessuna | 🔴 CRITICAL |

---

## 1. 🔴 ASSENZA DI EXCEPTION HANDLER FASTAPI

**Nessun `@app.exception_handler()` o `app.add_exception_handler()` è registrato nel progetto.**  
Ogni eccezione non catturata si propaga fino a Starlette, che restituisce una risposta **HTML** con traceback (in debug) o un generico "500 Internal Server Error" in testo piano.

```python
# Cercato in tutto il progetto: nessun risultato
# @app.exception_handler(Exception)
# @app.exception_handler(HTTPException)   # nemmeno questo!
```

**Impatto:** Il frontend si aspetta JSON. Qualsiasi eccezione non gestita produce HTML o plain text → il client JavaScript crasha o mostra errori illeggibili.

---

## 2. 🔴 ENDPOINT SENZA TRY/EXCEPT (34/45, 76%)

Ogni endpoint senza try/except è un potenziale 500 silenzioso. Ecco l'elenco completo:

### Endpoint critici (logica complessa, nessun try/except)

| Endpoint | Funzione | Rischio specifico |
|---|---|---|
| `GET /api/strategy` | `get_strategy` | `PitStrategist.optimize()` può lanciare eccezioni NumPy, division by zero, KeyError |
| `GET /api/setup` | `get_setup_advice` | ~170 linee di logica con dizionari, aggregazioni, divisioni per zero |
| `GET /api/qualifying` | `get_qualifying_analysis` | `QualifyingAnalyst.analyze()` non protetto |
| `GET /api/weather/radar` | `get_weather_radar` | `analyze_rain_risk()`, `get_pit_recommendation()` non protetti |
| `GET /api/laps/chart` | `get_laps_chart` | `fit_degradation_model()` può fallire con dati anomali |
| `GET /api/practice` | `get_practice_analysis` | `analyze_practice_data()` non protetto |
| `GET /api/pit-practice` | `get_pit_practice` | `extract_pit_stops()`, `analyze_pit_performance()` non protetti |
| `GET /api/traffic` | `get_traffic_estimate` | Chiama `estimate_traffic_penalty` (funzione non importata nel modulo corrente! — NameError certo a runtime) |

### Endpoint database (fetch + filtro in memoria, nessun try/except)

| Endpoint | Funzione | Rischio specifico |
|---|---|---|
| `GET /api/laps` | `get_laps` | Fetch TUTTI i giri, filtra in memoria. DB corrotto → eccezione SQLite |
| `GET /api/laps/compare` | `get_laps_compare` | Idem |
| `GET /api/laps/optimal` | `get_optimal_lap` | try/except SOLO su `get_lap_samples`, non sul resto |
| `GET /api/profile` | `get_profile` | try/except SOLO su `detect_anomalies_for_session`, non su `fit_degradation_model` o `np.mean` |
| `GET /api/race/timeline` | `get_race_timeline` | `build_race_timeline()` non protetto |
| `GET /api/sessions` | `get_sessions` | Query SQL diretta, nessun try/except |
| `GET /api/filters/*` | 4 endpoint | Fetch completo, nessun try/except |

### Endpoint autenticazione

| Endpoint | Funzione | Rischio specifico |
|---|---|---|
| `POST /api/auth/login` | `login` | `AuthManager.login_email()` può lanciare eccezioni DB |
| `POST /api/auth/logout` | `logout` | `AuthManager.logout()` non protetto |
| `GET /api/auth/me` | `me` | `current_user.to_dict()` non protetto |

### Endpoint cloud

| Endpoint | Funzione | Rischio specifico |
|---|---|---|
| `GET /api/cloud/user` | `get_cloud_user` | `database.get_local_user()` |
| `POST /api/cloud/push` | `cloud_push` | `database.push_pending_sessions()` — chiamata di rete! |
| `POST /api/cloud/pull` | `cloud_pull` | `database.pull_remote_sessions()` — chiamata di rete! |
| `POST /api/cloud/display-name` | `set_cloud_display_name` | Nessuna validazione |
| `GET /api/cloud/status` | `cloud_status` | Nessun try/except |

---

## 3. 🔴 DATABASE LAYER: ZERO GESTIONE ERRORI

**Nessuna funzione in `database/__init__.py` (1762 linee) contiene try/except.**  
Ogni operazione SQLite può fallire con:

- `sqlite3.OperationalError` — database locked, disk I/O error, file non trovato
- `sqlite3.DatabaseError` — database corrotto, schema mismatch
- `sqlite3.IntegrityError` — constraint violation
- `sqlite3.ProgrammingError` — SQL malformato

### Cosa succede se il DB è corrotto?

1. `get_db_connection()` apre il file corrotto → **nessun errore all'apertura** (SQLite non verifica all'open)
2. Prima query → `sqlite3.DatabaseError: database disk image is malformed`
3. L'eccezione si propaga attraverso tutte le funzioni database (nessun try/except)
4. Arriva all'endpoint FastAPI (nessun try/except)
5. FastAPI restituisce **500 in HTML** (nessun exception handler)
6. **Tutti gli endpoint diventano inutilizzabili** — non c'è degradazione parziale

### Connection management problematico

```python
# Pattern usato OVUNQUE nel database layer:
conn = get_db_connection(db_path)
# ... operazioni ...
conn.close()  # MAI in finally! Se query lancia eccezione, connection LEAK!
```

Ogni eccezione SQLite causa un **connection leak**. Con il tempo, si esauriscono i file descriptor.

---

## 4. 🟠 RISPOSTE DI ERRORE INCONSISTENTI (JSON vs Dict vs HTML)

Il formato delle risposte di errore **non è uniforme**:

### Tipo A: JSONResponse con status code corretto ✅
```python
# /api/auth/register, /api/strategy, /api/qualifying, /api/owner, /api/laps/import
return JSONResponse(status_code=400, content={"error": "..."})
return JSONResponse(status_code=422, content={"error": "..."})
return JSONResponse(status_code=429, content={"error": "..."})
```
**7 endpoint** usano questo pattern.

### Tipo B: Dict restituito come 200 OK ❌
```python
# /api/laps/optimal (linea 1298-1301)
return {
    "error": f"Need at least 2 valid laps...",
    "car": car, "track": track,
}
# ↑ Questo restituisce HTTP 200 con un campo "error"! Il client pensa sia OK.
```

### Tipo C: Eccezione non gestita → HTML 500 ❌
```python
# Qualsiasi eccezione in uno dei 34 endpoint senza try/except
# → FastAPI default: HTML traceback o "500 Internal Server Error" in plain text
```

### Tipo D: HTTPException (solo nella dipendenza auth) ⚠️
```python
# /api/auth/* via require_user dependency
raise HTTPException(status_code=401, detail="Auth required")
# ↑ Queste producono JSON: {"detail": "Auth required"} — formato diverso da {"error": "..."}
```

**Il client deve gestire 4 formati diversi di errore.**

---

## 5. 🔴 LOGGING TOTALMENTE ASSENTE

- **`web/server.py`**: nessun `import logging`, nessun `logger.info/error/warning`
- **`database/__init__.py`**: nessun `import logging`
- **`auth/`**: nessun `import logging`
- **Unico logging nel progetto**: vendor libraries (`pyLMUSharedMemory`, `pyRfactor2SharedMemory`) — irrilevante per l'API

**Conseguenze:**
- Errori 500 sono completamente silenziosi lato server
- Impossibile fare debugging in produzione
- Nessuna traccia di chi chiama cosa, tassi di errore, pattern di utilizzo
- Nessun alerting possibile

---

## 6. 🟡 RATE LIMITER: IN-MEMORY, NO PERSISTENZA

```python
_rate_limit_store: Dict[str, List[float]] = {}  # In-memory dict!
_RATE_LIMIT = 200  # max requests per minute per IP
```

### Problemi:

1. **Riavvio = reset**: tutto il rate limit si azzera al riavvio del server
2. **Single-process only**: se si usano worker multipli (gunicorn), ogni worker ha il suo dizionario → rate limit **non funziona** (ogni worker permette 200 req/min)
3. **Memory leak potenziale**: IP mai puliti se non fanno più richieste (la pulizia avviene solo alla prossima richiesta dello stesso IP)
4. **Nessun header standard**: mancano `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `Retry-After`

### Bypass potenziali:
- Usare IP multipli (triviale)
- Multi-process: ogni worker ha contatore separato
- `X-Forwarded-For` non considerato → se dietro reverse proxy, tutti sembrano 127.0.0.1

---

## 7. 🟠 NESSUN TIMEOUT SU OPERAZIONI LUNGHE

Nessun meccanismo di timeout è implementato:

| Operazione | Tempo stimato (DB grande) | Rischio |
|---|---|---|
| `get_all_laps_for_archive()` | O(n) su tutti i giri | Fetch di migliaia di righe |
| `fit_degradation_model()` | Computazione NumPy | Regressione su molti punti |
| `PitStrategist.optimize()` | Backtracking combinatorio | CPU-bound, nessun timeout |
| `cloud_pull()` / `cloud_push()` | HTTP request esterna | Network timeout assente |
| `analyze_rain_risk()` | Computazione | Nessun timeout |

Se un'operazione si blocca, l'intero worker FastAPI è bloccato. Non c'è `asyncio.wait_for()` né `concurrent.futures.TimeoutError`.

---

## 8. 🟡 PROBLEMI AGGIUNTIVI

### 8.1 Fetch completo prima di filtrare (performance e memoria)

```python
@server.py lines 783-800
laps = database.get_all_laps_for_archive(include_deleted=include_deleted)  # TUTTI!
if car:
    laps = [l for l in laps if l.get("car") == car]  # Filtro in Python
```

Pattern usato in: `/api/laps`, `/api/laps/compare`, `/api/filters/*`, `/api/setup`, `/api/strategy`, `/api/profile`, `/api/weather/radar`, `/api/traffic`, `/api/pit-practice`.

Con 10,000 giri nel DB, ogni richiesta carica ~10MB in memoria e itera su tutti.

### 8.2 Silent error swallowing

```python
# server.py lines 338-339
except Exception:
    pass  # ❌ Errore di lettura JSON completamente ignorato!

# server.py lines 1040-1042
except Exception:
    pass  # ❌ Anomaly detection fallita? Non lo sapremo mai.

# server.py lines 1312-1313
except Exception:
    pass  # ❌ Telemetria corrotta? Ignorato.

# server.py lines 725-726, 750-751
except Exception:
    hist_list = []  # ❌ JSON weather history invalido? Silenziosamente sostituito con [].
```

### 8.3 Connection leak nel database layer

```python
# Pattern in TUTTE le funzioni database:
conn = get_db_connection(db_path)
cursor = conn.cursor()
cursor.execute(...)     # Se qui lancia eccezione...
conn.commit()
conn.close()            # ...non si arriva mai qui → CONNECTION LEAK
```

Non c'è **nessun** `try/finally` o context manager (`with conn:`) in tutto `database/__init__.py`.

### 8.4 Bug certo: `estimate_traffic_penalty` non importata

```python
# server.py line 1350
penalty = estimate_traffic_penalty(  # ← FUNZIONE NON IMPORTATA!
    own_class, c,
    ...
)
```

Né `from analysis.classes import estimate_traffic_penalty` né definita localmente.  
→ **L'endpoint `/api/traffic` crasha sempre con `NameError` a runtime.**

---

## 9. 📋 MATRICE DI RISCHIO

| Rischio | Probabilità | Impatto | Classe |
|---|---|---|---|
| DB corrotto → 500 a catena | Bassa | Catastrofico | 🔴 CRITICAL |
| Eccezione in endpoint senza try/except | Alta | Alto (500 HTML) | 🔴 CRITICAL |
| Nessun logging → errori invisibili | Certa | Alto | 🔴 CRITICAL |
| Connection leak su errore SQLite | Media | Alto (esaurimento FD) | 🟠 HIGH |
| Risposte errore inconsistenti | Certa | Medio (client rotti) | 🟠 HIGH |
| Rate limit bypassabile | Media | Medio | 🟡 MEDIUM |
| Timeout assenti su operazioni lunghe | Media | Medio (worker bloccato) | 🟠 HIGH |
| `estimate_traffic_penalty` non importata | Certa | Basso (1 endpoint) | 🟠 HIGH |
| Silent error swallowing | Alta | Medio | 🟡 MEDIUM |
| Fetch completo prima di filtrare | Alta | Medio (perf) | 🟡 MEDIUM |

---

## 10. 🛠️ RACCOMANDAZIONI

### Priorità 1 (CRITICAL) — Bloccanti per produzione

1. **Aggiungere exception handler globale FastAPI** che logga e restituisce JSON:
   ```python
   @app.exception_handler(Exception)
   async def global_exception_handler(request, exc):
       logger.error(f"Unhandled: {exc}", exc_info=True)
       return JSONResponse(status_code=500, content={"error": "Internal server error"})
   ```

2. **Wrappare TUTTE le operazioni database in try/except**, con logging e risposta JSON:
   ```python
   try:
       laps = database.get_all_laps_for_archive(...)
   except sqlite3.Error as e:
       logger.error(f"DB error: {e}")
       return JSONResponse(status_code=500, content={"error": "Database error"})
   ```

3. **Aggiungere `try/finally` nel layer database** per garantire `conn.close()`:
   ```python
   conn = get_db_connection()
   try:
       ...
   finally:
       conn.close()
   ```

4. **Aggiungere logging strutturato** (`import logging; logger = logging.getLogger(__name__)`) in server.py e database.

5. **Gestire DB corrotto**: `PRAGMA integrity_check` allo startup, degraded mode se fallisce.

### Priorità 2 (HIGH)

6. **Uniformare le risposte di errore**: sempre `JSONResponse(status_code=XXX, content={"error": "..."})`.
7. **Aggiungere timeout** con `asyncio.wait_for()` per operazioni lunghe.
8. **Importare `estimate_traffic_penalty`** o rimuovere l'endpoint `/api/traffic`.
9. **Filtrare a livello SQL**, non in Python: passare `car`, `track`, `compound` come parametri SQL.

### Priorità 3 (MEDIUM)

10. **Rate limiter**: usare Redis o almeno un file-backed store, header standard.
11. **Health check endpoint**: `GET /health` che verifichi la connettività DB.
12. **Sostituire `except Exception: pass`** con logging almeno `logger.warning()`.

---

## 📎 Appendice: Lista completa endpoint con stato try/except

| # | Method | Route | Funzione | try/except | Cosa protegge |
|---|---|---|---|---|---|
| 1 | GET | `/` | `index` | ❌ | — |
| 2 | GET | `/login` | `login_page` | ❌ | — |
| 3 | POST | `/api/auth/register` | `register` | ✅ | ValueError da AuthManager |
| 4 | POST | `/api/auth/login` | `login` | ❌ | — |
| 5 | POST | `/api/auth/logout` | `logout` | ❌ | — |
| 6 | GET | `/api/auth/me` | `me` | ❌ | — |
| 7 | GET | `/api/sessions` | `get_sessions` | ❌ | — |
| 8 | GET | `/api/race/sessions` | `get_race_sessions` | ❌ | — |
| 9 | GET | `/api/race/timeline` | `get_race_timeline` | ❌ | — |
| 10 | GET | `/api/overlay/settings` | `get_overlay_settings` | ✅ | JSON file read (silent pass) |
| 11 | POST | `/api/overlay/settings` | `set_overlay_settings` | ✅ | JSON file read (silent pass) |
| 12 | GET | `/api/filters/cars` | `get_filter_cars` | ❌ | — |
| 13 | GET | `/api/filters/tracks` | `get_filter_tracks` | ❌ | — |
| 14 | GET | `/api/filters/compounds` | `get_filter_compounds` | ❌ | — |
| 15 | GET | `/api/filters/classes` | `get_filter_classes` | ❌ | — |
| 16 | GET | `/api/setup` | `get_setup_advice` | ❌ | — |
| 17 | GET | `/api/cloud/user` | `get_cloud_user` | ❌ | — |
| 18 | POST | `/api/cloud/opt-in` | `opt_in` | ✅ | `await request.json()` |
| 19 | POST | `/api/cloud/opt-out` | `opt_out` | ✅ | `await request.json()` |
| 20 | POST | `/api/cloud/display-name` | `set_cloud_display_name` | ❌ | — |
| 21 | GET | `/api/cloud/status` | `cloud_status` | ❌ | — |
| 22 | POST | `/api/cloud/push` | `cloud_push` | ❌ | — |
| 23 | POST | `/api/cloud/pull` | `cloud_pull` | ❌ | — |
| 24 | GET | `/api/laps/export` | `export_laps` | ❌ | — |
| 25 | POST | `/api/laps/import` | `import_laps` | ✅ | JSONDecodeError, size validation |
| 26 | GET | `/api/weather/forecast` | `get_weather_forecast` | ✅ | `json.loads(history)` |
| 27 | GET | `/api/weather/stint-forecast` | `get_stint_weather_forecast` | ✅ | `json.loads(history)` |
| 28 | GET | `/api/laps` | `get_laps` | ❌ | — |
| 29 | GET | `/api/laps/compare` | `get_laps_compare` | ❌ | — |
| 30 | GET | `/api/laps/{id}/telemetry` | `get_lap_telemetry` | ❌ | — |
| 31 | GET | `/api/laps/compare-telemetry` | `compare_lap_telemetry` | ❌ | — |
| 32 | GET | `/api/laps/chart` | `get_laps_chart` | ❌ | — |
| 33 | POST | `/api/laps/{id}/delete` | `soft_delete_lap` | ❌ | — |
| 34 | POST | `/api/laps/{id}/restore` | `restore_lap` | ❌ | — |
| 35 | GET | `/api/profile` | `get_profile` | ✅ | `detect_anomalies_for_session` only |
| 36 | GET | `/api/strategy` | `get_strategy` | ❌ | — |
| 37 | GET | `/api/qualifying` | `get_qualifying_analysis` | ❌ | — |
| 38 | GET | `/api/laps/optimal` | `get_optimal_lap` | ✅ | `get_lap_samples` only |
| 39 | GET | `/api/traffic` | `get_traffic_estimate` | ❌ | — |
| 40 | GET | `/api/practice` | `get_practice_analysis` | ❌ | — |
| 41 | GET | `/api/pit-practice` | `get_pit_practice` | ❌ | — |
| 42 | GET | `/api/weather/radar` | `get_weather_radar` | ❌ | — |
| 43 | GET | `/api/owner` | `get_owner` | ❌ | — |
| 44 | POST | `/api/owner` | `set_owner` | ✅ | ValueError da set_owner_email |
| 45 | POST | `/api/seed` | `seed_sample_data` | ❌ | — |

**Legenda:** ✅ = ha try/except (sempre parziale), ❌ = nessun try/except
