# T4 — Audit Overlay PySide6 FULL (overlay/app.py)

**File**: `overlay/app.py` (1055 righe)  
**Versione**: Full overlay — finestra unica 3×3 cockpit  
**Data audit**: 2026-08-01  
**Metodo**: analisi statica completa + cross-reference con `strategy_refresher.py`, `voice_engine.py`, `icons.py`, `database/__init__.py`, `telemetry/source.py`, `telemetry/detector.py`

---

## RIEPILOGO FINDINGS

| # | Categoria | Severità | Riga | Descrizione |
|---|-----------|----------|------|-------------|
| F1 | 🛑 AttributeError | CRITICAL | 699 | `_calculate_refuel()` non definito |
| F2 | 🛑 Thread safety | CRITICAL | 114,136 | `_running` flag senza sincronizzazione |
| F3 | 🛑 Thread safety | CRITICAL | 139 | `source.stop()` chiamato da thread sbagliato |
| F4 | 🟡 Memory leak | HIGH | 345,203s | QTimer del refresher non parentato |
| F5 | 🟡 Segfault potenziale | HIGH | 265s | Accesso a widget distrutto dal timer refresher |
| F6 | 🟡 Segfault potenziale | HIGH | 613 | PeekMessageW su finestra potenzialmente invalida |
| F7 | 🟡 Race condition | HIGH | 114,136 | TelemetryWorker stop non deterministico |
| F8 | 🟠 Performance | MEDIUM | 917,926 | Connessioni DB per ogni frame (20 Hz) |
| F9 | 🟠 Resource leak | MEDIUM | 604 | Hotkey Win32 non sempre deregistrata |
| F10 | 🟠 Inconsistenza | MEDIUM | 91 | File opened senza context manager |
| F11 | 🔵 UI/Disegno | LOW | 417s | Font non verificati (Rajdhani, JetBrains Mono, Inter) |
| F12 | 🔵 Dead code potenziale | LOW | 700-702 | Ramo condizionale irraggiungibile (F1 correlato) |

---

## DETTAGLIO FINDINGS

### F1 — `_calculate_refuel()` non definito [CRITICAL]

**Riga**: 699  
**File**: `overlay/app.py`

```python
# Linea 699
refuel = self._calculate_refuel(frame)
```

Il metodo `_calculate_refuel` **non esiste** nella classe `OverlayWidget` (né come metodo proprio né ereditato da `QWidget`). È invece definito in `app_new.py:1352` nella versione modulare, ma assente nella versione full.

**Impatto**: `AttributeError` a runtime su **ogni frame** di telemetria (20 Hz). L'overlay crasha immediatamente all'avvio se il gioco è in esecuzione. L'unico scenario in cui non crasha è se `frame` è `None` (nessun dato), ma con una source attiva il crash è garantito.

**Fix suggerito**: Copiare `_calculate_refuel` da `app_new.py:1352` in `app.py`, oppure rimuovere il blocco refuel (linee 698-707) se non necessario nella modalità full.

---

### F2 — `_running` flag senza sincronizzazione [CRITICAL]

**Righe**: 114 (init), 125 (worker thread read), 136-137 (main thread write)

```python
class TelemetryWorker(QObject):
    def __init__(self, ...):
        self._running = False          # R114: init su main thread

    def start_source(self):
        self._running = True           # R125: write su worker thread
        while self._running:           # R127: read su worker thread (loop)
            ...

    def stop(self):
        self._running = False          # R136: write su MAIN thread
```

`_running` è un attributo Python standard (`bool`), letto in un busy-loop sul worker thread e scritto dal main thread. Senza `threading.Lock` o `threading.Event`, non c'è garanzia formale di visibilità cross-thread, anche se il GIL di CPython rende il crash improbabile.

**Impatto**: In teoria, il worker thread potrebbe non vedere mai `_running = False` se la CPU cache non viene flushata, causando un loop infinito e impossibilità di shutdown pulito.

**Fix suggerito**: Usare `threading.Event` (`self._stop_event = threading.Event()`) e sostituire il while con `while not self._stop_event.is_set()`. In `stop()`, chiamare `self._stop_event.set()`.

---

### F3 — `source.stop()` chiamato da thread sbagliato [CRITICAL]

**Righe**: 117 (worker thread), 139 (main thread)

```python
# R117: start_source() chiama source.start() sul worker thread
def start_source(self):
    self.source.start()    # WORKER thread

# R136-141: stop() chiama source.stop() dal MAIN thread
def stop(self):
    self._running = False
    self.source.stop()     # MAIN thread ← thread diverso!
```

La `TelemetrySource` (es. `LiveSharedMemorySource`) apre handle di shared memory in `start()`. Se l'implementazione usa API Windows (CreateFileMapping, MapViewOfFile), queste richiedono che `start()` e `stop()` siano chiamate dallo stesso thread. Chiamare `stop()` dal main thread mentre la risorsa è stata aperta dal worker thread può causare:
- Handle leak (la shared memory non viene chiusa correttamente)
- Access violation se la memory view è mappata nel contesto del worker thread

**Fix suggerito**: Invece di chiamare `source.stop()` direttamente, emettere un segnale o usare `QMetaObject.invokeMethod` per delegare lo stop al worker thread, oppure usare un flag coordinato da `threading.Event`.

---

### F4 — QTimer del refresher senza parent [HIGH]

**Riga**: `strategy_refresher.py:203`

```python
class StrategyRefresher(QObject):
    def start(self):
        self._timer = QTimer()              # ← senza parent!
        self._timer.timeout.connect(self._tick)
        self._timer.start(self._interval_ms)

    def stop(self):
        if self._timer:
            self._timer.stop()
            self._timer = None
```

Il `QTimer` è creato **senza parent QObject**. Se `stop()` non viene chiamato (es. crash, eccezione in cleanup, `sys.exit()` forzato), il timer continua a vivere nel event loop Qt e il suo callback `_tick` tenterà di accedere a `self._manager` (OverlayWidget) potenzialmente già distrutto → segfault.

**Impatto**: Memory leak del timer + potenziale segfault differito se l'overlay viene chiuso senza cleanup pulito.

**Fix suggerito**: Passare `parent=self` al costruttore `QTimer(self)` così che Qt lo distrugga automaticamente quando il `StrategyRefresher` viene garbage-collectato.

---

### F5 — Accesso a widget distrutto dal timer refresher [HIGH]

**Righe**: `strategy_refresher.py:265` e `app.py:1027-1030`

```python
# strategy_refresher.py R265
def _tick(self):
    self._manager._refresh_strategy()   # self._manager = OverlayWidget
```

`StrategyRefresher._manager` è il riferimento all'`OverlayWidget` passato a riga 345 di `app.py` (`StrategyRefresher(self, ...)`). La sequenza di cleanup in `run_overlay()` è:

1. `overlay.refresher.stop()` (R1027)
2. `worker.stop()` (R1028)
3. `thread.quit()` + `thread.wait()` (R1029-1030)

Tuttavia, se l'applicazione viene terminata con `QApplication.quit()` dal menu contestuale (R386) o da Ctrl+C, `closeEvent` dell'overlay (R633) viene chiamato **prima** di `cleanup()`. L'ordine degli eventi Qt in shutdown non è deterministico: il timer del refresher potrebbe scattare dopo che l'overlay è stato distrutto ma prima che `cleanup()` esegua `refresher.stop()`.

**Impatto**: Segfault per accesso a widget C++ distrutto.

**Fix suggerito**: In `_tick()`, verificare che `self._manager` sia ancora valido (es. `if not sip.isdeleted(self._manager):`) o spostare il `refresher.stop()` in `closeEvent`.

---

### F6 — PeekMessageW su finestra potenzialmente invalida [HIGH]

**Righe**: 601-637

```python
def _setup_hotkeys(self):
    self._hk_timer = QTimer(self)
    self._hk_timer.timeout.connect(self._check_hk)
    self._hk_timer.start(100)                     # 10 Hz polling

def _check_hk(self):
    msg = ctypes.wintypes.MSG()
    if ctypes.windll.user32.PeekMessageW(ctypes.byref(msg), None, 0x0312, 0x0312, 1):
        ...
```

Il timer continua a chiamare `PeekMessageW` anche quando la finestra è nascosta o in fase di distruzione. Se l'handle nativo della finestra (`HWND`) diventa invalido durante lo shutdown, `PeekMessageW` con `HWND = None` (che significa "tutte le finestre del thread") è generalmente sicuro. Tuttavia:

1. La combinazione `PeekMessageW(..., None, ...)` con `PM_REMOVE` (flag `1` = `PM_REMOVE`) **rimuove** il messaggio `WM_HOTKEY` dalla coda. Se c'è un altro handler di hotkey nello stesso thread, il messaggio viene perso.
2. Se `RegisterHotKey` fallisce (R603-608), `self._hk_toggle` non viene inizializzato e `UnregisterHotKey` in `closeEvent` (R635) usa un valore indeterminato.

**Fix suggerito**: Inizializzare `self._hk_toggle` fuori dal try (es. `self._hk_toggle = None`), e verificare che non sia `None` prima di chiamare `UnregisterHotKey`. Usare `PM_NOREMOVE` (0) per non consumare i messaggi.

---

### F7 — TelemetryWorker stop non deterministico [HIGH]

**Righe**: 1026-1030

```python
def cleanup():
    overlay.refresher.stop()
    worker.stop()           # (1) setta _running=False + chiama source.stop()
    thread.quit()           # (2) chiede all'event loop del thread di uscire
    thread.wait()           # (3) aspetta che il thread termini
```

Problema: il worker thread è bloccato dentro `start_source()` in un `while self._running` loop (R127) con `time.sleep(0.05)` (R134). Quando `worker.stop()` setta `_running = False`, il loop uscirà al prossimo `sleep`. Ma `source.stop()` dentro `worker.stop()` viene chiamato **prima** che il loop sia effettivamente uscito — il thread è ancora vivo e potrebbe star chiamando `source.get_next_frame()`. Se `source.stop()` rilascia risorse che `get_next_frame()` sta usando, si ha una data race.

**Fix suggerito**: Riordinare: prima setta `_running = False`, poi `thread.wait()`, e solo DOPO chiama `source.stop()`.

---

### F8 — Connessioni database per ogni frame (20 Hz) [MEDIUM]

**Righe**: 917, 926, 936, 942, 977 (database usato dentro `update_frame`)

```python
def _estimate_fuel_laps(self, frame: TelemetryFrame) -> float:
    laps = database.get_laps_for_analysis(self._car, self._track, db_path=self.db_path)
    # ↑ chiamato OGNI frame (20 Hz) — crea nuova connessione SQLite
```

`update_frame()` chiama `_estimate_fuel_laps()` e `_estimate_cliff_laps()` a ogni frame (20 Hz). Ciascuna chiamata crea una nuova connessione SQLite (`database.get_db_connection()` → `sqlite3.connect()`). Su Windows, aprire e chiudere file 40+ volte al secondo è inefficiente e può causare contention con il detector thread che scrive simultaneamente.

**Impatto**: Degrado performance, potenziale I/O starvation, rischio teorico di `SQLITE_BUSY` se WAL non configurato correttamente (anche se WAL è abilitato a riga 20 di `database/__init__.py`).

**Fix suggerito**: Cache dei risultati per almeno 1-2 secondi, o usare un connection pool / connessione persistente in sola lettura.

---

### F9 — Hotkey Win32 non sempre deregistrata [MEDIUM]

**Righe**: 604, 633-637

```python
def _setup_hotkeys(self):
    try:
        ctypes.windll.user32.RegisterHotKey(None, self._hk_toggle, ...)
        # ... timer ...
    except Exception:
        pass   # ← se fallisce, _hk_toggle potrebbe essere non inizializzato
```

```python
def closeEvent(self, _event):
    try:
        ctypes.windll.user32.UnregisterHotKey(None, self._hk_toggle)
    except Exception:
        pass   # ← ignora errori, ma la hotkey rimane registrata a livello OS!
```

Se `closeEvent` non viene chiamato (es. kill del processo, `os._exit()`), la hotkey globale rimane registrata nel sistema operativo fino al logout/reboot. Inoltre, se `RegisterHotKey` fallisce, `self._hk_toggle` non è definito e `closeEvent` produce un `AttributeError` (catturato da `except Exception`).

**Fix suggerito**: Inizializzare `self._hk_toggle = None` nel costruttore, e in `closeEvent` controllare `if self._hk_toggle is not None` prima di deregistrare.

---

### F10 — File opened senza context manager [MEDIUM]

**Righe**: 91 e 96

```python
def load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        return {**DEFAULT_CONFIG, **json.load(open(CONFIG_PATH))}   # ← file mai chiuso
    return dict(DEFAULT_CONFIG)

def save_config(cfg: dict) -> None:
    with open(CONFIG_PATH, "w") as f:                                # ← questo è OK
        json.dump(cfg, f, indent=2)
```

`load_config()` apre `CONFIG_PATH` con `open()` senza `with`, senza chiamare `.close()`. Su CPython, il garbage collector chiude il file quando l'oggetto file viene deallocato, ma non è garantito e può causare un `ResourceWarning` in ambienti di test.

**Fix suggerito**: `with open(CONFIG_PATH) as f: return {**DEFAULT_CONFIG, **json.load(f)}`

---

### F11 — Font non verificati [LOW]

**Righe**: 68-70, 197, 413, 464, etc.

```python
FONT_DISPLAY = "Rajdhani"
FONT_MONO = "JetBrains Mono"
FONT_UI = "Inter"
```

Questi font sono usati in tutto l'overlay ma non vengono verificati. Se non installati sul sistema, Qt usa il fallback di sistema, che potrebbe rompere il layout (Rajdhani è un font condensato). Non c'è un meccanismo di fallback esplicito.

**Fix suggerito**: Aggiungere un controllo `QFontDatabase` all'avvio e loggare un warning se i font non sono disponibili. Includere i font come risorse o fornire istruzioni di installazione.

---

### F12 — Ramo condizionale irraggiungibile (F1 correlato) [LOW]

**Righe**: 698-707

```python
refuel = self._calculate_refuel(frame)    # ← AttributeError
if refuel is not None and refuel > 0:     # mai raggiunto
    ...
else:                                      # sempre raggiunto via except implicito? NO
    ...
```

Poiché `_calculate_refuel` non esiste, l'`AttributeError` si propaga e **nessuno** dei due rami viene eseguito. L'intero blocco refuel è dead code finché F1 non viene risolto. Inoltre, le righe 700-707 sovrascrivono `self._lbl_fuel.setText()` già impostato a riga 686, quindi in caso di fix di F1, il comportamento sarebbe comunque ambiguo (doppio setText sullo stesso label).

---

## ANALISI AGGIUNTIVE

### Thread Safety — Panoramica generale

| Componente | Thread | Accessi sicuri? |
|------------|--------|-----------------|
| `TelemetryWorker.start_source()` | Worker (QThread) | ✅ Loop interno ok |
| `TelemetryWorker.stop()` | Main | ❌ Vedi F2, F3 |
| `OverlayWidget.update_frame()` | Main (via signal/slot) | ✅ Sempre main thread |
| `StrategyRefresher._tick()` | Main (QTimer) | ✅ Main thread |
| `VoiceEngine.speak()` | Chiamante (main) → spawna daemon thread | ⚠️ Winsound async ok, ma `_last_played` update in lock |
| `Database.get_laps_for_analysis()` | Main + Worker | ✅ Connessioni separate, WAL mode |
| `LapBoundaryDetector.process_frame()` | Worker | ✅ Single-thread nel worker |

### Memory — Widget e oggetti non deallocati

1. **QTimer del refresher** (F4): non parentato, può sopravvivere al widget.
2. **QTimer hotkey** (R605): parentato a `self` → deallocato con l'overlay. OK.
3. **SettingsDialog**: creato on-demand a R389 senza parent → sopravvive dopo `exec()`. La dialog viene distrutta da Python GC quando esce dallo scope (dopo `exec()`). OK.
4. **LapBoundaryDetector**: creato in `start_source()` a R119, mai esplicitamente deallocato. Referenziato da `self._detector` del worker, deallocato col worker. OK.
5. **Connessioni SQLite**: create e chiuse a ogni chiamata database. OK (nessun leak, ma inefficiente — F8).
6. **Thread TTS** (`voice_engine.py:71`): thread daemon → terminato automaticamente a shutdown. OK.
7. **File audio aperti da winsound** (`SND_ASYNC`): winsound gestisce la riproduzione asincrona internamente. Nessun leak noto. OK.

### Segnali Qt non connessi — Verifica

| Segnale | Connesso a | Stato |
|---------|------------|-------|
| `worker.frame_ready` | `overlay.update_frame` | ✅ R1018 |
| `worker.lap_completed` | `overlay.on_lap_completed` | ✅ R1019 |
| `worker.race_started` | `overlay.on_race_started` | ✅ R1020 |
| `worker.qualifying_started` | `overlay.on_qualifying_started` | ✅ R1021 |
| `refresher.audio_cue` | `overlay._play_audio_cue` | ✅ R346 |
| `refresher.plan_updated` | `overlay._on_plan_updated` | ✅ R347 |
| `thread.started` | `worker.start_source` | ✅ R1017 |

Tutti i segnali sono connessi. ✅

### Widget creati ma mai mostrati

| Widget | Creato | Mostrato? |
|--------|--------|-----------|
| `_lbl_warning` | R524 | Inizialmente nascosto (R528), mostrato condizionalmente a R783/R786 |
| `_lbl_qualy` | R532 | Inizialmente nascosto (R536), mostrato in qualifying (R827) o practice (R999) |
| `_lbl_tyre_status_title` | R510 | Sempre visibile (aggiunto a layout, nessun hide) ✅ |
| `_lbl_tyre_status` | R515 | Sempre visibile ✅ |
| `_btn_settings` | R422 | Sempre visibile ✅ |

Nessun widget orfano. Tutti i widget creati hanno un percorso di visualizzazione. ✅

---

## RACCOMANDAZIONI

### Urgenti (bloccanti)
1. **F1**: Implementare `_calculate_refuel()` o rimuovere il blocco refuel (righe 698-707).
2. **F2**: Sostituire `_running` bool con `threading.Event`.
3. **F3**: Spostare `source.stop()` dentro il worker thread o usare signal/slot cross-thread.

### Prioritari (rischio crash)
4. **F4**: Passare `parent=self` a `QTimer()` in `StrategyRefresher.start()`.
5. **F5**: Aggiungere guardia `sip.isdeleted()` in `StrategyRefresher._tick()`.
6. **F7**: Riordinare la sequenza di shutdown: flag → wait → stop source.

### Miglioramenti (qualità)
7. **F8**: Aggiungere cache temporale (1-2s) per `_estimate_fuel_laps()` e `_estimate_cliff_laps()`.
8. **F9**: Inizializzare `_hk_toggle = None` e controllare prima di `UnregisterHotKey`.
9. **F10**: Usare `with open(...)` in `load_config()`.
10. **F11**: Verificare disponibilità font all'avvio.

---

*Report generato da audit statico — nessuna modifica al codice effettuata.*
