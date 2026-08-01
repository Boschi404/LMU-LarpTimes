# T10 – Audit Database: Schema, Query, Indici, Race Conditions

**Data:** 2026-08-01  
**File analizzati:** `database/__init__.py` (1762 righe), `database/cloud.py` (578 righe), `database/cloud_schema.sql`  
**Caller rilevanti:** `web/server.py`, `overlay/app.py`, `overlay/app_new.py`, `overlay/strategy_refresher.py`, `telemetry/detector.py`

---

## 1. Schema: Normalizzazione

### Tabelle definite

| Tabella | Colonne | FK | Note |
|---------|---------|-----|------|
| `sessions` | 8 | — | `session_uuid` **senza UNIQUE né indice** nel DB locale |
| `stints` | 9 | `sessions(id)` CASCADE | |
| `laps` | **33** | `sessions(id)` CASCADE, `stints(id)` **senza azione** | Tabella ipertrofica |
| `pit_stops` | 6 | `sessions(id)` CASCADE | |
| `sync_queue` | 8 | — | Referenzia `session_uuid` (TEXT), **nessuna FK** |
| `db_users` | 8 | — | Singleton (CHECK id=1) |
| `lap_samples` | 16 | `laps(id)` CASCADE | Telemetria per-frame |

### Problemi di normalizzazione

#### 🔴 CRITICO: Tabella `laps` con 33 colonne — denormalizzazione delle gomme
Le 8 colonne di usura pneumatici (`wear_pct_start_FL`, `wear_pct_start_FR`, `wear_pct_start_RL`, `wear_pct_start_RR` + 4 × `_end_*`) violano la 1NF "ogni colonna = un attributo atomico". In pratica ogni lap ha 4 angoli con stato start + end.

```sql
-- Schema normalizzato alternativo:
CREATE TABLE tyre_wear (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lap_id INTEGER NOT NULL,
    position TEXT NOT NULL CHECK(position IN ('FL','FR','RL','RR')),
    wear_pct_start REAL NOT NULL,
    wear_pct_end REAL NOT NULL,
    FOREIGN KEY (lap_id) REFERENCES laps(id) ON DELETE CASCADE
);
```

**Impatto:** 8 colonne × N laps di storage sprecato (la maggior parte dei giri ha stesso compound su tutti gli angoli). Query più verbose per analisi per-angolo. Non bloccante ma design migliorabile.

#### 🟡 `compound_front`/`compound_rear` duplicati tra `stints` e `laps`
Ogni lap eredita il compound dallo stint via `stint_id`, ma le colonne sono presenti in entrambe le tabelle. Rischio di inconsistenza: un lap potrebbe avere `compound_front='Soft'` mentre lo stint associato ha `'Medium'`. Nessun vincolo CHECK o trigger di validazione.

#### 🟡 `sync_queue.session_uuid` senza FK
`sync_queue` referenzia `sessions.session_uuid` come TEXT, ma:
- Non esiste vincolo UNIQUE su `sessions.session_uuid` nel DB locale
- Non esiste FOREIGN KEY tra `sync_queue.session_uuid` e `sessions.session_uuid`
- La cancellazione di una sessione lascia orfani nella coda sync

---

## 2. Indici Mancanti (LOCALE vs Cloud)

### Indici presenti nel DB locale (`database/__init__.py`)

```sql
CREATE INDEX IF NOT EXISTS idx_sync_queue_status ON sync_queue(status);
CREATE INDEX IF NOT EXISTS idx_sessions_owner_email ON sessions(owner_email);  -- solo in migration
CREATE INDEX IF NOT EXISTS idx_laps_owner_email ON laps(owner_email);          -- solo in migration
CREATE INDEX IF NOT EXISTS idx_lap_samples_lap ON lap_samples(lap_id);
```

### 🔴 Indici CRITICI assenti nel DB locale

Il DB **cloud** (`cloud_schema.sql`) ha 7 indici; il DB **locale** (quello usato dall'app!) ne ha solo 3-4. Ecco quelli mancanti:

| Indice mancante | Query interessate | Impatto |
|-----------------|-------------------|---------|
| `sessions(session_uuid)` | `_find_session_by_uuid`, export, import, enqueue, sync | **Table scan** su ogni lookup |
| `sessions(car, track)` | `get_laps_for_analysis`, `get_laps_chart_data`, `get_pit_stops_loss_by_session`, etc. (~50+ chiamate) | **Table scan** su ogni query analisi |
| `laps(session_id)` | JOIN in tutte le query analisi, export loop, import dedup | **Table scan** sulla tabella più grande |
| `laps(session_id, lap_number)` | `_find_lap_by_session_and_number` (chiamato per OGNI lap in import) | **O(N²)** lookup senza indice |
| `stints(session_id)` | `get_active_stint`, `_find_stint_by_number`, export loop | **Table scan** |
| `stints(session_id, stint_number)` | `_find_stint_by_number` | Dedup stints lento |
| `pit_stops(session_id)` | JOIN in `get_laps_chart_data`, `get_pit_stops_loss_by_session` | **Table scan** |

### 🟡 Indici aggiuntivi raccomandati

| Indice | Motivazione |
|--------|-------------|
| `laps(anomaly_flag, is_valid_lap, is_deleted)` | Filtri composti in `get_laps_for_analysis` (WHERE con 5 condizioni) |
| `laps(compound_front)` | Filtro compound in query analisi (presente nel cloud, assente nel locale) |
| `sessions(started_at)` | Ordinamento in `get_all_sessions`, dashboard |
| `laps(lap_time)` | Query ordinamento / best lap (se presenti in futuro) |

---

## 3. Pattern N+1

### 🔴 `export_sessions()` — 3 query per sessione (N+1)
```python
# Righe 828-880: per ogni sessione, 3 query separate
for s_row in session_rows:      # N sessioni
    cursor.execute("SELECT ... FROM stints WHERE session_uuid = ?")   # Query 1
    cursor.execute("SELECT ... FROM laps ... WHERE session_uuid = ?") # Query 2
    cursor.execute("SELECT ... FROM pit_stops ... WHERE session_uuid = ?") # Query 3
```
Con 100 sessioni = **301 query**. Si potrebbe fare con 3 query totali usando `WHERE session_uuid IN (...)` + raggruppamento in Python.

### 🔴 `import_sessions()` — lookup per ogni lap
```python
# Righe 1015-1098: per ogni lap, query di dedup
for lap in entry.get("laps", []):
    existing_lap = _find_lap_by_session_and_number(cursor, session_id, ln)  # SELECT individuale
```
Con 50 sessioni da 100 giri ciascuna = **5,000 query** solo per il dedup. Si potrebbe caricare tutti i `(session_id, lap_number)` esistenti in un `set()` con una sola query `SELECT session_id, lap_number FROM laps WHERE session_id IN (...)`.

### 🟡 `_find_stint_by_number()` — lookup per stint
Stesso pattern: ogni stint importato fa una SELECT individuale (linea 993).

### 🟡 `delete_user_data()` in `TursoSync` (cloud.py:300-312)
```python
rows = self._http_query("SELECT id FROM sessions WHERE user_id = ?")
for row in rows:
    self._http_execute("DELETE FROM sessions WHERE id = ?", [sid])
```
N+1 HTTP round-trip verso Turso. Una singola `DELETE FROM sessions WHERE user_id = ?` (con FK CASCADE) farebbe tutto in una query.

---

## 4. Fetch Completo + Filtro in Python (Performance Killer)

### 🔴🔴 CRITICO: `get_all_laps_for_archive()` — fetch di TUTTI i giri senza WHERE

```python
# Righe 605-628: nessun filtro WHERE (tranne is_deleted)
def get_all_laps_for_archive(db_path=None, include_deleted=False):
    query = "SELECT l.*, s.track, s.layout, s.car, s.session_type FROM laps l JOIN sessions s ..."
    if not include_deleted:
        query += " WHERE l.is_deleted = 0"
    query += " ORDER BY l.id DESC"
    # NESSUN LIMIT, NESSUN FILTRO car/track/sessione!
```

**Ogni chiamante** (13 endpoint in `web/server.py` + overlay) carica TUTTI i giri e filtra in Python:

```python
# server.py:309-310 — per ottenere i giri di UNA sessione
laps = database.get_all_laps_for_archive(include_deleted=False)    # TUTTI i giri
session_laps = [l for l in laps if str(l.get("session_id")) == session_id]  # filtro Python

# server.py:369-370 — per ottenere la lista unica di auto
laps = database.get_all_laps_for_archive(include_deleted=False)    # TUTTI i giri
cars = sorted({l.get("car", "") for l in laps if l.get("car")})    # set in Python

# server.py:376-377 — per ottenere la lista unica di tracciati
laps = database.get_all_laps_for_archive(include_deleted=False)    # TUTTI i giri (di nuovo!)
tracks = sorted({l.get("track", "") for l in laps if l.get("track")})

# server.py:383-384 — per ottenere la lista unica di compound
laps = database.get_all_laps_for_archive(include_deleted=False)    # TUTTI i giri (di nuovo!!)
compounds = sorted({l.get("compound_front", "") for l in laps if l.get("compound_front")})

# server.py:407-410 — setup advice con filtro car+track in Python
laps = database.get_all_laps_for_archive(include_deleted=False)    # TUTTI
car_laps = [l for l in laps if l.get("car") == car and l.get("track") == track]
```

**Stima impatto:** Con 10,000 giri nel DB, ogni chiamata API trasferisce 10,000 righe × 33 colonne dal DB al processo Python, solo per estrarre poche decine di valori. Le chiamate `/api/filters/*` vengono eseguite a ogni refresh del frontend (tipicamente 3-4 chiamate simultanee).

**Fix suggerito:**
```python
# Invece di get_all_laps_for_archive() per i filtri:
def get_distinct_cars(db_path=None):
    return conn.execute("SELECT DISTINCT car FROM sessions ORDER BY car").fetchall()

def get_distinct_tracks(db_path=None):
    return conn.execute("SELECT DISTINCT track FROM sessions ORDER BY track").fetchall()

def get_distinct_compounds(db_path=None):
    return conn.execute("SELECT DISTINCT compound_front FROM laps WHERE is_deleted=0 ORDER BY compound_front").fetchall()
```

### 🟡 Chiamate duplicate in overlay (`app_new.py`)
Nello stesso frame loop, `get_laps_for_analysis()` viene chiamata **fino a 4-6 volte** con gli stessi parametri `(car, track)`:
- `on_frame()` → usura gomme (riga 1271)
- `_estimate_fuel_laps()` → consumo carburante (riga 1345)
- `_calculate_refuel()` (riga 1357)
- `_refresh_strategy()` (riga 1394/1404)
- `_run_qualifying_analysis()` (riga 1438)
- `_run_practice_analysis()` (riga 1462)

**Nessun caching.** Ogni chiamata riapre il DB, riesegue la stessa JOIN+LIMIT filtrata per car+track. Con un DB di 5,000 giri, sono 6 × 5,000 = 30,000 righe processate per frame. Suggerito: cache in-process con TTL breve o passare i dati già fetchati come parametro.

---

## 5. Race Conditions in Scritture Concorrenti

### 🔴 `insert_lap()` — TOCTOU sullo schema
```python
cursor.execute("PRAGMA table_info(laps)")          # Legge schema
existing_cols = {r[1] for r in cursor.fetchall()}
# ... costruisce field_map basato sulle colonne esistenti ...
cursor.execute(f"INSERT INTO laps ...")             # Scrive
```
Se una migration (`_migrate_db`) modifica lo schema tra la PRAGMA e l'INSERT, l'INSERT può fallire o scrivere dati errati. La migration però avviene solo in `init_db()`, quindi il rischio è basso se l'app chiama `init_db()` una volta all'avvio. Comunque: la PRAGMA su ogni INSERT è uno spreco.

### 🔴 `opt_in_to_community()` — read-then-write su user_id
```python
cursor.execute("SELECT user_id, display_name, opt_in_at FROM db_users WHERE id = 1")
existing = cursor.fetchone()
if existing_user_id:
    user_id = existing_user_id  # mantiene esistente
else:
    user_id = str(uuid.uuid4())  # genera nuovo
cursor.execute("UPDATE db_users SET user_id = ?, ...")
```
Due thread/processi concorrenti possono entrambi leggere `existing_user_id IS NULL` e generare due UUID diversi. Solo l'ultimo UPDATE vince. Dovrebbe usare `UPDATE ... WHERE user_id IS NULL` atomico, o `INSERT ... ON CONFLICT`.

### 🟡 `set_owner_email()` — due connessioni separate
```python
conn = get_db_connection(db_path)     # Connessione 1
cursor.execute("UPDATE db_users SET email = ? WHERE id = 1", (email,))
conn.commit()
conn.close()

if email:
    conn = get_db_connection(db_path) # Connessione 2 (nuova!)
    cursor.execute("UPDATE sessions SET owner_email = ? WHERE owner_email IS NULL OR owner_email = ''", (email,))
    cursor.execute("UPDATE laps SET owner_email = ? WHERE owner_email IS NULL OR owner_email = ''", (email,))
    conn.commit()
    conn.close()
```
Se la connessione 1 committa ma la connessione 2 fallisce, lo stato è inconsistente (email impostata su db_users ma non backfillata su sessions/laps). Inoltre il backfill modifica TUTTE le righe senza owner_email, comprese quelle di altri ipotetici utenti (anche se in pratica ce n'è uno solo).

### 🟡 `import_sessions()` — auto-commit implicito
Nonostante il `conn.commit()` a fine funzione (riga 1115), Python sqlite3 in default autocommit mode committa ogni INSERT individualmente. Se l'import fallisce a metà, le sessioni/laps già inseriti restano nel DB. Manca un `BEGIN` esplicito o `isolation_level='DEFERRED'`.

### ✅ Pattern corretti
- `_enqueue_session_for_sync()` usa `ON CONFLICT ... DO UPDATE` (atomico)
- Le operazioni CRUD semplici (`create_session`, `insert_lap`, etc.) sono mono-istruzione, quindi atomiche

---

## 6. WAL Mode

### ✅ Corretto
```python
conn.execute("PRAGMA journal_mode=WAL;")
conn.execute("PRAGMA foreign_keys=ON;")
```
WAL mode abilitato su ogni connessione. Consente letture concorrenti senza bloccare le scritture.

### 🟡 Problemi

1. **Nessun `busy_timeout`:** Se due scritture concorrenti collidono, SQLite restituisce immediatamente `SQLITE_BUSY` invece di attendere. L'app non gestisce questo errore, quindi le scritture concorrenti falliscono silenziosamente.
   ```python
   # Manca:
   conn.execute("PRAGMA busy_timeout = 5000")  # 5 secondi
   ```

2. **Connessione per operazione:** `get_db_connection()` crea una NUOVA connessione ogni volta. 50+ chiamate al DB in un frame = 50 aperture/chiusure connessione. WAL non risolve questo overhead.

3. **`check_same_thread=False`:** Necessario per WAL multi-thread, ma sposta la responsabilità della thread-safety sull'applicazione. Le operazioni su una singola connessione non sono thread-safe senza lock espliciti.

4. **Nessun `WAL checkpoint`:** Il file WAL cresce indefinitamente. Manca un checkpoint periodico (automatico con `PRAGMA wal_autocheckpoint=1000` è il default, ma andrebbe verificato/monitorato).

---

## 7. ON DELETE CASCADE

### ✅ Corretto
| FK | Azione | OK? |
|----|--------|-----|
| `stints.session_id → sessions.id` | CASCADE | ✅ |
| `laps.session_id → sessions.id` | CASCADE | ✅ |
| `pit_stops.session_id → sessions.id` | CASCADE | ✅ |
| `lap_samples.lap_id → laps.id` | CASCADE | ✅ |

### 🔴 Mancante
| FK | Problema |
|----|----------|
| `laps.stint_id → stints.id` | **Nessuna azione** (né CASCADE né SET NULL). Con FK enforcement ON, cancellare uno stint fallisce se ha laps associati. |
| `sync_queue.session_uuid → sessions.session_uuid` | **FK assente.** Orfani garantiti se una sessione viene cancellata. Inoltre `session_uuid` non ha UNIQUE in sessions (locale). |

### 🟡 Cloud schema: azione diversa
```sql
-- cloud_schema.sql:40
FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
```
OK: se un utente viene cancellato, le sessioni rimangono anonime (user_id=NULL).

---

## 8. Transazioni Mancanti

### 🔴 `import_sessions()` — nessuna transazione esplicita
```python
# Righe 926-1124: centinaia di INSERT/UPDATE individuali
# Con autocommit (default Python sqlite3), ogni INSERT è una transazione separata
# Il conn.commit() finale è un no-op
```
**Conseguenza:** Se l'import viene interrotto (errore, crash, Ctrl+C), il DB rimane in uno stato parzialmente importato. Nessun rollback possibile.

**Fix:**
```python
conn.execute("BEGIN IMMEDIATE")
try:
    # ... tutti gli INSERT ...
    conn.commit()
except Exception:
    conn.rollback()
    raise
```

### 🟡 `push_pending_sessions()` — operazioni multi-step senza transazione
```python
_mark_sync_result(uuid, ok=False, ...)  # Scrive su sync_queue (committa)
_enqueue_session_for_sync(...)           # Scrive su sync_queue (committa)
result = backend.push(...)               # Chiamata di rete
_mark_sync_result(uuid, ok=..., ...)     # Scrive su sync_queue (committa)
```
Se il processo crasha tra `_enqueue` e `backend.push`, il record sync_queue rimane in stato intermedio. È gestito decentemente (riprovabile), ma non atomico.

### 🟡 `export_sessions()` in `push_pending_sessions()` — export di TUTTO per spingere una sessione
```python
all_payload = export_sessions(db_path=db_path)  # Esporta TUTTE le sessioni
for uuid in pending:
    single_session = {**all_payload, "sessions": [
        s for s in all_payload.get("sessions", [])
        if s.get("session", {}).get("session_uuid") == uuid
    ]}
```
Esporta l'intero DB (con tutte le query N+1 di `export_sessions`) per poi filtrare una singola sessione. Con 100 sessioni pendenti, esporta 100 volte lo stesso intero DB. 

**Fix:** `export_sessions()` dovrebbe accettare un parametro `session_uuids: list[str]` per filtrare a monte.

---

## 9. Problemi Aggiuntivi

### 🟡 `insert_lap()` — PRAGMA table_info su ogni INSERT
```python
cursor.execute("PRAGMA table_info(laps)")  # Righe 378-379
existing_cols = {r[1] for r in cursor.fetchall()}
```
Eseguito a **ogni singolo giro** inserito. Con 100 giri/ora e sessioni di 2 ore = 200 PRAGMA ridondanti. Lo schema non cambia durante l'esecuzione normale (la migration avviene solo in `init_db()`).

### 🟡 `get_laps_chart_data()` — 4 query separate invece di JOIN unica
```python
# 4 round-trip al DB per gli stessi parametri car+track
cursor.execute("SELECT ... FROM laps l JOIN sessions s ... WHERE s.car=? AND s.track=?")  # Query 1
cursor.execute("SELECT ... FROM pit_stops p JOIN sessions s ... WHERE s.car=? AND s.track=?")  # Query 2
cursor.execute("SELECT ... FROM stints st JOIN sessions s ... WHERE s.car=? AND s.track=?")  # Query 3
cursor.execute("SELECT ... FROM sessions s WHERE s.car=? AND s.track=?")  # Query 4
```

### 🟡 `session_uuid` senza UNIQUE nel DB locale
```sql
-- DB locale:
session_uuid TEXT NOT NULL,   -- nessun vincolo UNIQUE!

-- DB cloud:
session_uuid TEXT NOT NULL UNIQUE,  -- corretto
```
Due sessioni potrebbero avere lo stesso `session_uuid` nel DB locale. Le funzioni `_find_session_by_uuid` e `export_sessions` assumono implicitamente che sia univoco, ma senza vincolo possono verificarsi duplicati.

### 🔵 `create_session()` ha colonna `owner_email` ma `init_db()` non la crea
La colonna `owner_email` su `sessions` viene creata solo dalla migration (`_migrate_db`). Se `init_db()` crea la tabella per la prima volta, la colonna `owner_email` **non esiste**, ma `create_session()` tenta di inserirla (riga 301). Questo funziona perché `_migrate_db` viene chiamato subito dopo in `init_db()`, ma se la migration fallisce silenziosamente (try/except a riga 173), la colonna manca e i successivi INSERT falliscono.

---

## Riepilogo Priorità

| # | Severità | Categoria | Problema | Righe |
|---|----------|-----------|----------|-------|
| 1 | 🔴🔴 | Performance | `get_all_laps_for_archive()` fetch completo + filtro Python in 13 endpoint | 605-628, server.py:309-410 |
| 2 | 🔴🔴 | Performance | Indici mancanti su `session_uuid`, `car+track`, `session_id` nel DB locale | 34-134 |
| 3 | 🔴 | N+1 | `export_sessions()`: 3 query per sessione | 828-880 |
| 4 | 🔴 | N+1 | `import_sessions()`: SELECT per ogni lap importato | 1015-1020 |
| 5 | 🔴 | Transazioni | `import_sessions()` senza transazione esplicita → import parziale | 926-1124 |
| 6 | 🔴 | Race condition | `opt_in_to_community()` read-then-write non atomico | 1476-1505 |
| 7 | 🔴 | Integrità | `laps.stint_id` FK senza ON DELETE, `sync_queue` senza FK | 100, 117-134 |
| 8 | 🟡 | Performance | `get_laps_for_analysis()` chiamata 4-6× nello stesso frame senza cache | overlay/app_new.py |
| 9 | 🟡 | Performance | `push_pending_sessions()` esporta intero DB per ogni sessione pendente | 1260-1271 |
| 10 | 🟡 | Integrità | `session_uuid` senza UNIQUE nel DB locale | 38 |
| 11 | 🟡 | Race condition | Nessun `busy_timeout` → SQLITE_BUSY non gestito | 12-22 |
| 12 | 🟡 | Manutenibilità | `insert_lap()` PRAGMA table_info su ogni INSERT | 378-379 |
| 13 | 🟡 | Design | Tabella `laps` con 33 colonne (denormalizzazione gomme) | 64-102 |

---

## Suggerimenti non-code

1. **Connection pool:** Riutilizzare una connessione (o un piccolo pool) invece di aprirne una nuova per ogni operazione. In WAL mode una singola connessione può gestire letture multi-thread.
2. **Query logging:** Attivare `sqlite3_trace` in debug mode per profilare le query effettivamente eseguite.
3. **Test di carico:** Simulare 10,000 giri nel DB e misurare i tempi di risposta delle API `/api/filters/*` e `/api/race/timeline`.
4. **`session_uuid` UNIQUE:** Aggiungere il vincolo nel DB locale con una migration pulita. Prima di farlo, verificare che non esistano duplicati.
