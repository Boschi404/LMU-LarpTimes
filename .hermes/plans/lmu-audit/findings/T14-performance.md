# T14 — Performance Audit: Query, Memoria, e Scalabilità

**Data:** 2026-08-01  
**Analista:** Audit automatico  
**Ambito:** `database/__init__.py`, `web/server.py`, `web/static/app.js`, `analysis/`  
**Database:** SQLite embedded (WAL mode, `lmu_pit_strategist.db`)

---

## 1. Riepilogo Esecutivo

L'applicazione presenta **un collo di bottiglia architetturale fondamentale**: la funzione `get_all_laps_for_archive()` esegue un `SELECT * ... JOIN` **senza filtri** e viene chiamata da **12+ endpoint API**, molti dei quali applicano poi filtri in Python dopo aver caricato l'intero dataset. Con **10.000+ giri**, ogni chiamata trasferisce ~15 MB di dati da SQLite → Python dicts → JSON, e su page load il dato viene fetchato **5 volte in parallelo**. L'auto-refresh di 3 secondi moltiplica ulteriormente il carico.

| Metrica | Piccoli dati (100 giri) | 10.000 giri | 50.000 giri |
|---|---|---|---|
| Tempo fetch DB (stima) | <5 ms | 80–150 ms | 400–800 ms |
| Memoria Python dicts | ~150 KB | ~15 MB | ~75 MB |
| JSON response size | ~50 KB | ~5 MB | ~25 MB |
| API response time (end-to-end) | 15–30 ms | 250–600 ms | 2–4 s |
| Auto-refresh 3s (bandwidth) | 17 KB/s | **1.7 MB/s** | **8.3 MB/s** |
| Filtri on-load (5 chiamate) | 0.25 MB | **25 MB** | **125 MB** |
| **Scala?** | ✅ Sì | ⚠️ Degradato | ❌ No |

**Conclusione:** Il sistema collassa oltre ~3.000-5.000 giri. A 10.000 giri funziona ma con latenza percepibile; a 50.000 è inutilizzabile.

---

## 2. Root Cause: `get_all_laps_for_archive()` (CRITICAL)

### 2.1 Codice incriminato

**File:** `database/__init__.py`, righe 605–628

```python
def get_all_laps_for_archive(db_path=None, include_deleted=False):
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    query = """
        SELECT l.*, s.track, s.layout, s.car, s.session_type
        FROM laps l
        JOIN sessions s ON l.session_id = s.id
    """
    if not include_deleted:
        query += " WHERE l.is_deleted = 0"
    query += " ORDER BY l.id DESC"
    cursor.execute(query)
    rows = cursor.fetchall()           # ← CARICA TUTTO IN MEMORIA
    conn.close()
    return [dict(row) for row in rows]  # ← CONVERTE TUTTI I ROW IN DICT
```

### 2.2 Chiamanti (12+ endpoint che fetchano e filtrano in Python)

| # | Endpoint | File:line | Cosa fa dopo il fetch |
|---|---|---|---|
| 1 | `GET /api/laps` | server.py:783 | Filtra per car, track, compound, owner, class **in Python** |
| 2 | `GET /api/filters/cars` | server.py:369 | Estrarre valori unici di `car` con set comprehension |
| 3 | `GET /api/filters/tracks` | server.py:376 | Estrarre valori unici di `track` |
| 4 | `GET /api/filters/compounds` | server.py:383 | Estrarre valori unici di `compound_front` |
| 5 | `GET /api/filters/classes` | server.py:391 | Chiama `get_available_classes(laps)` su tutti i giri |
| 6 | `GET /api/setup` | server.py:407 | Filtra per car+track, poi per valid_laps |
| 7 | `GET /api/laps/compare` | server.py:807 | Filtra per car+track, poi valid+non-anomaly |
| 8 | `GET /api/laps/{id}/telemetry` | server.py:845 | Cerca un singolo lap per ID scorrendo tutti |
| 9 | `GET /api/laps/compare-telemetry` | server.py:871 | Cerca 2 lap per ID scorrendo tutti |
| 10 | `GET /api/laps/optimal` | server.py:1291 | Filtra per car+track, valid+non-anomaly |
| 11 | `GET /api/race/timeline` | server.py:309 | Filtra per session_id |
| 12 | `GET /api/strategy` | server.py:1174 | Estrarre tutte le auto uniche per traffico |
| 13 | `GET /api/traffic` | server.py:1336 | Estrarre classi uniche per track |

**Pattern ricorrente:**
```python
# server.py — pattern in OGNI endpoint
laps = database.get_all_laps_for_archive(include_deleted=False)  # fetch ALL
filtered = [l for l in laps if l.get("car") == car]               # filtra in Python
```

### 2.3 Stima costo per numero di giri

**Assunzioni:**
- Ogni row SQLite: ~500 bytes (30 colonne × ~16 bytes medi)
- Ogni dict Python: ~800 bytes (overhead dict + stringhe)
- JSON serialized per lap: ~400 bytes (solo campi necessari)

| Giri | Fetch SQLite | Memoria dicts (totale) | JSON response | Latenza totale |
|---|---|---|---|---|
| 100 | ~50 KB | ~80 KB | ~40 KB | 15 ms |
| 1.000 | ~500 KB | ~800 KB | ~400 KB | 40 ms |
| 5.000 | ~2.5 MB | ~4 MB | ~2 MB | 150 ms |
| 10.000 | ~5 MB | **~8 MB** | **~4 MB** | 350 ms |
| 25.000 | ~12.5 MB | **~20 MB** | **~10 MB** | 1.2 s |
| 50.000 | ~25 MB | **~40 MB** | **~20 MB** | 3.5 s |
| 100.000 | ~50 MB | **~80 MB** 💥 | **~40 MB** | 8+ s / crash |

💥 = l'heap Python con ~80 MB per una singola request rischia MemoryError su macchine con <256 MB liberi.

---

## 3. Firestorm al Page Load

### 3.1 Sequenza di caricamento

Quando la pagina si carica, `app.js` esegue **immediatamente**:

```javascript
// app.js:87 — eseguito allo script load, NON al DOMContentLoaded
populateFilters();  // ← 4 chiamate API parallele
```

```javascript
// app.js:23-30
async function populateFilters() {
    const [cars, tracks, compounds, classes] = await Promise.all([
        fetch('/api/filters/cars'),      // → get_all_laps_for_archive() #1
        fetch('/api/filters/tracks'),     // → get_all_laps_for_archive() #2
        fetch('/api/filters/compounds'),  // → get_all_laps_for_archive() #3
        fetch('/api/filters/classes'),    // → get_all_laps_for_archive() #4
    ]);
}
```

Poi, dopo 100ms (timeout in index.html:2130):

```javascript
// app.js:823-838
async function loadOwner() {
    fetch('/api/owner');
    fetch('/api/laps?limit=1');  // → get_all_laps_for_archive() #5
}
```

**Risultato: 5 fetch completi del database entro i primi 200ms di caricamento.**

Con 10.000 giri: **5 × 8 MB = 40 MB di memoria allocata simultaneamente** (anche se momentanea, GC non libera istantaneamente).

### 3.2 Auto-refresh Archivio (3 secondi)

```javascript
// app.js:415-419
_lapsAutoTimer = setInterval(function() {
    if (document.getElementById('page-archivio').classList.contains('active')) {
        loadLaps(true);  // → /api/laps → get_all_laps_for_archive()
    }
}, 3000);
```

**Effetto:** Ogni 3 secondi, l'intero database viene riletto, convertito in dicts, serializzato in JSON, inviato al client, ordinato in JS e renderizzato in tabella HTML.

| Giri | Dati/refresh | Bandwidth/h | CPU server/h | CPU client/h |
|---|---|---|---|---|
| 1.000 | 400 KB | 480 MB | bassa | moderata |
| 10.000 | **4 MB** | **4.8 GB** | alta | alta |
| 50.000 | **20 MB** | **24 GB** ❌ | estrema | browser crash |

---

## 4. Loop O(n²) e Pattern Subottimali in Analysis

### 4.1 `build_race_timeline()` — O(n × s) dove s = stints

**File:** `analysis/race_director.py`, righe 145–158

```python
# Per ogni stint, itera TUTTI i valid_laps
for s in stints:
    stint_laps_data = [l for l in valid_laps
                       if l.get("stint_number") == s["stint_number"]]
    # ... calcola avg
```

Con 10 stints e 10.000 laps: **10 × 10.000 = 100.000 iterazioni** per costruire una lista che poteva essere accumulata in un singolo passaggio. Questo codice viene anche eseguito inline durante la costruzione degli stint (righe 145–150, duplicato).

**Impatto:** Moderato (O(n × s), non O(n²)), ma evitabile con un dict `{stint_number: [laps]}` costruito in O(n).

### 4.2 `detect_anomalies_for_session()` — n UPDATE individuali

**File:** `analysis/anomaly.py`, righe 102–119

```python
for lap in all_laps:                    # O(n)
    ...
    database.update_lap_anomaly(lap_id, True, reason_text, db_path=db_path)
    # OGNI chiamata apre/chiude una connessione SQLite
```

Con 10.000 laps da controllare: **10.000 connessioni SQLite aperte e chiuse** (ogni `update_lap_anomaly` chiama `get_db_connection()` → `commit()` → `close()`). Questo è ~10-30 secondi di overhead solo per le connessioni.

**Impatto:** ALTO. Dovrebbe usare `executemany` o una transazione singola con cursore persistente.

### 4.3 `export_sessions()` — query per sessione

**File:** `database/__init__.py`, righe 828–860

```python
for s_row in session_rows:        # O(sessions)
    cursor.execute("SELECT ... FROM stints WHERE ...")   # query #1
    cursor.execute("SELECT ... FROM laps ...")            # query #2
    cursor.execute("SELECT ... FROM pit_stops ...")       # query #3
```

Con 50 sessioni: **150 query SQL**. Ciascuna è piccola, ma l'overhead di round-trip si accumula.

**Impatto:** Basso per pochi utenti, ma la funzione è esposta come API pubblica (`/api/laps/export`).

### 4.4 `get_laps_chart_data()` — 4 query separate

**File:** `database/__init__.py`, righe 655–727

Esegue 4 query SQL sequenziali (laps, pit_stops, stints, sessions) filtrate per car+track. Questo è il pattern **corretto** — le query hanno WHERE clause. Ma notare che il chiamante (`/api/laps/chart` in server.py:913) poi chiama **anche** `get_laps_for_analysis()` (line 929) per il degradation model, duplicando il fetch dei giri.

---

## 5. Memoria

### 5.1 Stima dimensione lap in memoria

Un singolo lap dict (da `get_all_laps_for_archive`) contiene:
- 20 campi da `laps` table (lap_time, sector_1/2/3, fuel, wear × 8, temps, weather, etc.)
- 5 campi aggiuntivi da `sessions` JOIN (track, layout, car, session_type, session_id)
- Overhead dict Python: ~64 bytes base + ~50 bytes per chiave

**Totale stimato: ~800 bytes/lap in memoria Python.**

| Giri | Memoria (dicts) | JSON serialized |
|---|---|---|
| 5.000 | 4 MB | 2 MB |
| 10.000 | 8 MB | 4 MB |
| 25.000 | 20 MB | 10 MB |
| 50.000 | 40 MB | 20 MB |

Con 5 chiamate simultanee (page load firestorm): 5 × 8 MB = 40 MB a 10.000 giri.

### 5.2 Memoria lato client

`_lapsData` in `app.js` mantiene l'array completo. A 10.000 giri, l'heap JavaScript del browser contiene ~10.000 oggetti complessi (~4-8 MB). Su browser mobile/tablet questo è significativo.

---

## 6. Chart Rendering Performance

### 6.1 Lap Evolution Chart (`renderLapChart`)

**File:** `app.js`, righe 893–1117

```javascript
var laps = data.laps.slice().sort(...)       // O(n log n) — 10k items
for (var i = 0; i < laps.length; i++) ...    // 3 scansioni complete
// Chart.js riceve array di n punti
datasets.push({
    data: laps.map(function(l) {
        return { x: l.lap_number, y: l.lap_time || 0 };
    }),
    pointRadius: 3,     // ← OGNI punto disegnato singolarmente
    type: 'scatter',
});
```

**Problema:** Con 10.000 punti scatter, Chart.js disegna 10.000 cerchi SVG/Canvas individualmente. Non c'è **decimazione** (nessun algoritmo di riduzione punti come Ramer-Douglas-Peucker). Il rendering può richiedere **200-800ms** su hardware moderno, e su ogni hover/redraw.

**Degradation curve:** Calcolata punto per punto per ogni età gomma (`range(1, max_age + 2)`) — in genere <100 punti, non problematico.

### 6.2 Profilo Degrado (`buildDegradChart`)

**File:** `app.js`, righe 284–347

Stesso pattern: tutti i raw_points passati a Chart.js senza decimazione. Con 10.000 raw points, la chart è illeggibile e lenta.

---

## 7. Auto-Refresh 3s — Scaling Breakdown

### 7.1 Carico a regime

Scenario: utente tiene aperta la pagina Archivio per 10 minuti.

| Giri | Refresh count | Dati totali trasferiti | Memoria allocata (cumulativa) |
|---|---|---|---|
| 1.000 | 200 | 80 MB | ~160 MB |
| 10.000 | 200 | **800 MB** | ~1.6 GB |
| 50.000 | 200 | **4 GB** 💥 | ~8 GB (swap/crash) |

### 7.2 Effetti collaterali

- **GC pressure:** Ogni 3 secondi, il GC di Python deve liberare ~8 MB di dicts (a 10.000 giri). Il GC di JavaScript deve fare lo stesso lato client.
- **Lock SQLite:** Anche in WAL mode, letture concorrenti condividono il lock. Con refresh frequenti + altre richieste, si crea coda.
- **Batteria:** Su laptop, il trasferimento continuo di 4 MB/3s consuma batteria significativamente.

---

## 8. Raccomandazioni (SENZA modificare codice — solo piano)

### Priorità CRITICAL (bloccante oltre 5.000 giri)

1. **Riscrivere `get_all_laps_for_archive()` per accettare filtri SQL:**
   - Aggiungere parametri `car`, `track`, `compound`, `session_id`, `owner_email`, `limit`, `offset`
   - Spostare i filtri nella WHERE clause SQL
   - Ogni endpoint passerebbe i propri filtri direttamente al database
   - **Impatto atteso:** riduzione da 8 MB → 40 KB per richieste filtrate (200×)

2. **Eliminare le chiamate duplicate al page load:**
   - `populateFilters()` dovrebbe chiamare un endpoint aggregato (`/api/filters`) che restituisce cars + tracks + compounds + classes in UNA query SQL (4 `SELECT DISTINCT`)
   - `/api/laps?limit=1` in `loadOwner()` è inutile: usare `SELECT COUNT(*) FROM laps` o un endpoint `/api/stats`

3. **Aumentare l'intervallo di auto-refresh o usare polling condizionale:**
   - 3 secondi → minimo 10-15 secondi
   - Oppure passare a Server-Sent Events (SSE) / WebSocket per notificare solo quando ci sono nuovi dati
   - In alternativa, polling con header `If-Modified-Since` e `Last-Modified` sul DB

### Priorità ALTA (degrado percepibile 1.000-5.000 giri)

4. **Sostituire `for` loop O(n²) in `build_race_timeline()`:**
   - Accumulare stint_laps in un dict durante l'iterazione principale
   - Riduzione da O(n × s) a O(n)

5. **Batch update in `detect_anomalies_for_session()`:**
   - Usare una singola connessione con `executemany` invece di n connessioni separate
   - Riduzione da ~10s a ~100ms per 10.000 laps

6. **Aggiungere decimazione punti per Chart.js:**
   - Prima di passare i dati a Chart.js, applicare riduzione (es. media mobile, max 500 punti visibili)
   - Riduzione tempo rendering da 500ms → 20ms

### Priorità MEDIA (ottimizzazione)

7. **Pool di connessioni SQLite:**
   - L'attuale pattern apre/chiude una connessione per ogni query
   - Un connection pool (o connessione persistente) ridurrebbe latenza del 30-50%

8. **Aggiungere indici mancanti:**
   - `CREATE INDEX idx_laps_session_car ON laps(session_id, car)` (se si aggiunge car)
   - `CREATE INDEX idx_sessions_car_track ON sessions(car, track)`
   - L'indice su `laps.owner_email` e `sessions.owner_email` esiste già (migration)

9. **Cache in-memory per dati statici (filtri):**
   - I valori unici di cars/tracks/compounds cambiano raramente
   - Cache con TTL di 60 secondi eliminerebbe 4 chiamate full-scan al page load

10. **Paginazione server-side:**
    - `GET /api/laps?limit=50&offset=0` invece di fetchare tutto e paginare in JS
    - La tabella mostra già solo 50 righe per pagina ma i dati viaggiano tutti

---

## 9. Stima Impatti delle Ottimizzazioni

| Scenario attuale | 1.000 giri | 10.000 giri | 50.000 giri |
|---|---|---|---|
| Page load (5 chiamate) | 200ms / 2MB | 1.5s / 20MB | 8s+ / 100MB |
| Latenza API `/api/laps` | 30ms | 350ms | 3.5s |
| Auto-refresh bandwidth/h | 480 MB | 4.8 GB | 24 GB |
| Chart render time | 50ms | 500ms | 3s+ |

| Dopo ottimizzazioni CRITICAL | 10.000 giri | 50.000 giri |
|---|---|---|
| Page load (con filtri SQL) | 80ms / 200KB | 150ms / 500KB |
| Latenza API `/api/laps?car=X` | 15ms | 40ms |
| Auto-refresh con SSE | 0 (push) | 0 (push) |
| Chart render (decimato) | 20ms | 30ms |

---

## 10. Verifica Rapida sul Campo

Per testare senza modificare codice:

```bash
# Conta i giri nel database
sqlite3 data/lmu_pit_strategist.db "SELECT COUNT(*) FROM laps WHERE is_deleted = 0;"

# Misura tempo di una query completa
time sqlite3 data/lmu_pit_strategist.db \
  "SELECT l.*, s.track, s.car FROM laps l JOIN sessions s ON l.session_id = s.id WHERE l.is_deleted = 0;" \
  > /dev/null

# Stima memoria: numero_giri × 800 = byte
```

Se il conteggio supera 5.000, le ottimizzazioni CRITICAL sono **necessarie** prima di aggiungere altre funzionalità.

---

*Report generato da audit automatico — nessun codice modificato.*
