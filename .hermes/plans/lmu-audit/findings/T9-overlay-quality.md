# T9 — Audit Qualità Codice: overlay/ + telemetry/ + auth/

**Data**: 2026-08-01
**File analizzati**: 8
**Metodo**: analisi statica (nessuna modifica al codice)

---

## Riepilogo per file

### 1. overlay/strategy_refresher.py

**Type Hints** ⚠️ Buono ma con lacune
- `AudioEngine.__init__`, `play()`, `_play_native()`: buoni.
- `PracticeAdvisor.advise()`: parametro senza tipo, solo return type.
- `StrategyRefresher.__init__`: parametro `manager` senza type hint (solo commento `# OverlayManager`).
- `_plan_signature`, `_tick`, `_recompute_full_plan`, `_safe_get_laps`, `_safe_get_pit_losses`: OK.
- `voice_engine` dichiarato `Optional[Any]` — code smell (si perde type safety).

**Docstrings** ⚠️ Parziale
- Docstring di modulo presente e completa.
- `AudioEngine`, `PracticeAdvisor`, `StrategyRefresher`: docstring di classe ok.
- `_current_state_snapshot`, `_has_state_changed`, `_recompute_full_plan`: con docstring.
- `_plan_signature`, `_tick`, `_safe_get_laps`, `_safe_get_pit_losses`: **no docstring**.
- `play()`: docstring ok.

**Error Handling** ⚠️ Silenzioso
- `_play_native()`: try/except su winsound ok.
- `_tick()`: try/except silenzia `_refresh_strategy()` → l'errore viene perso.
- `_recompute_full_plan()`: try/except ampio che ritorna None — maschera tutti i bug.
- `_safe_get_laps()`, `_safe_get_pit_losses()`: try/except con fallback a `[]` — ok per robustness ma nessun log.
- **Pattern comune**: eccezioni ingoiate senza alcun logging.

**Hardcoded Paths** 🟢 OK
- Percorsi audio relativi (`"audio/pit_now.wav"`) risolti con `paths.data_path()`.

**Platform-Specific** 🟡 Windows-first, fallback cross-platform
- `_play_native()`: branch `platform.system() == "Windows"` → winsound; else subprocess `afplay`/`aplay`.
- `import winsound` è lazy (dentro `_play_native`) → non crasha su non-Windows. ✅

**Import Circolari** 🟢 Nessuno
- Import lazy di `paths` in `_resolve_paths()` e `database` nei metodi `_safe_*`. Pattern difensivo.

**Classi Fantasma** 🟢 Nessuna
- `AudioEngine`, `PracticeAdvisor`, `StrategyRefresher` tutte referenziate in `overlay/app.py`.

---

### 2. overlay/voice_engine.py

**Type Hints** ✅ Buono
- `__init__`, `speak()`, `_generate_wav()`, `play_test()`: tipizzati.
- `set_volume()`: parametro tipizzato ma **no return type**.

**Docstrings** ⚠️ Minime
- Docstring di modulo ok.
- Docstring di classe: una riga.
- `speak()`, `_generate_wav()`, `_cleanup_cache()`, `play_test()`: con docstring o inline comment.
- `set_volume()`: **no docstring**.

**Error Handling** ⚠️ Fragile
- `speak()`: il playback avviene in un thread separato; l'eccezione è catch-ata e stampata.
- `_generate_wav()`: catch di `ImportError` → `_tts_available = False` **permanentemente**. Una volta fallito, non ritenta mai più.
- `_cleanup_cache()`: except con `pass` nudo — nessun log.
- Il metodo `speak()` ritorna `True` appena spawna il thread, **prima** che il playback avvenga effettivamente → race condition: il chiamante crede che l'audio sia partito ma potrebbe fallire dopo.

**Hardcoded Paths** 🟢 OK
- Cache dir via `paths.data_path("overlay", "tts_cache")`.

**Platform-Specific** 🔴 **CRITICO: Windows-only a livello di import**
- **`import winsound` a livello modulo (riga 11)** — crasha immediatamente su Linux/macOS all'import del file.
- `winsound.PlaySound()` usato direttamente (righe 60-63).
- `edge_tts` (import lazy) è cross-platform, ma la riproduzione è solo Windows.
- **Impatto**: `voice_engine.py` non è importabile su nessun OS tranne Windows.

**Import Circolari** 🟢 Nessuno

**Classi Fantasma** 🟢 Nessuna. `VoiceEngine` usata in `overlay/app.py` e `app_new.py`.

---

### 3. overlay/icons.py

**Type Hints** ⚠️ Inconsistenti
- 22 funzioni icona SVG: **nessun type hint** (solo `size=16` senza tipo).
- `icon_pixmap(svg_str: str, size: int = 16, color: str = ...)`: parametri tipizzati ma **no return type** (implicitamente `QPixmap`).
- `icon_widget()`: stessa situazione.
- `make_icon_button()`: `parent=None` senza tipo, `hover_color` tipizzato.
- `clean_action_text(text: str) -> str`: ✅ completo.

**Docstrings** ⚠️ Solo helper
- Docstring di modulo presente.
- Le 22 funzioni icona **non hanno docstring** (solo `zap_icon` e `book_open_icon` ce l'hanno).
- Funzioni helper (`icon_pixmap`, `icon_widget`, `make_icon_button`, `clean_action_text`): docstring ok.

**Error Handling** 🔴 Assente
- Nessun try/except in tutto il file.

**Hardcoded Paths** 🟢 Nessuno

**Platform-Specific** 🟢 Nessuno
- PySide6 import lazy (dentro funzioni), cross-platform.

**Import Circolari** 🟢 Nessuno
- `import re` a livello modulo, ma usato solo in `clean_action_text()`.

**Classi Fantasma** 🟢 Nessuna. Tutte funzioni helper.

---

### 4. telemetry/source.py

**Type Hints** ✅ Buono
- `TelemetryFrame` dataclass: tutti i campi tipizzati.
- `TelemetrySource` ABC: metodi astratti tipizzati.
- `LiveSharedMemorySource`: metodi con type hints.
- `SyntheticReplaySource.__init__`: parametri estensivi e tipizzati.
- `SyntheticReplaySource`: **attributi di istanza senza type annotation** a livello classe (assegnati solo in `__init__`).

**Docstrings** ⚠️ Lacune significative
- **Nessuna docstring di modulo** (il file inizia direttamente con `import sys`).
- `TelemetryFrame`: docstring ok.
- `TelemetrySource`: docstring di classe e metodi ok.
- `LiveSharedMemorySource.get_next_frame()`: **nessuna docstring** — metodo di 180+ linee, complesso, non documentato.
- `SyntheticReplaySource.get_next_frame()`: **nessuna docstring** — metodo di 120+ linee con logica di simulazione.
- `LiveSharedMemorySource.start()`: ok.

**Error Handling** 🟡 Robusto ma migliorabile
- `get_next_frame()` LMU: try/except ampio che ritorna None (ok per resilienza).
- Campi individuali: pattern `try/except AttributeError` per ogni campo telemetria (difensivo).
- `SyntheticReplaySource`: nessun error handling (deterministico, va bene).
- `start()` RF2 fallback: try/except ok.

**Hardcoded Paths** 🟡 Side-effect a import-time
- `VENDOR_PATH = paths.data_path("vendor")` a livello modulo.
- `sys.path.insert(0, ...)` **a import-time** (righe 12-14): anti-pattern. Modifica il `sys.path` globale come side-effect dell'import.
- **Track length**: `5793.0` metri hardcodato in `SyntheticReplaySource` (Monza).
- **Sector thresholds**: `0.35`, `0.70` hardcodati.

**Platform-Specific** 🟡 Windows-only implicito
- `pyLMUSharedMemory` e `pyRfactor2SharedMemory` sono probabilmente binding C/DLL Windows-only.
- L'import è lazy (dentro `start()`), quindi non crasha a import-time, ma è inutilizzabile su altri OS.
- Nessun fallback cross-platform per la fonte live.

**Import Circolari** 🟢 Nessuno

**Classi Fantasma** 🟢 Nessuna

---

### 5. telemetry/detector.py

**Type Hints** ⚠️ Inconsistenti
- `__init__`: parametri callback senza tipo (`on_session_complete=None`), `fallback_pit_loss` tipizzato.
- Attributi di istanza: **nessuna type annotation** a livello classe.
- `_create_session()`, `_reset_stint_state()`, `process_frame()`: parametri tipizzati, ma **nessun return type** su `_create_session` e `_reset_stint_state`.
- `_handle_stint_change()`: tipi ok.

**Docstrings** 🔴 Praticamente assenti
- **Nessuna docstring di modulo**.
- **Nessuna docstring di classe** (`LapBoundaryDetector`).
- **Nessuna docstring sui metodi** — solo qualche commento inline.
- L'unica "documentazione" sono i `print()` di debug.

**Error Handling** ⚠️ Selettivo
- Callback (`on_session_complete`, `on_race_started`, `on_qualifying_started`): try/except con `pass` nudo.
- `save_lap_samples`: try/except con stampa errore.
- Validazione `lap_time < 20.0`: numero magico, nessuna costante.
- `lap_gap > 1`: warning stampato ma nessun handling speciale.

**Hardcoded Paths** 🟡 Database path
- Default `db_path = database.DEFAULT_DB_PATH`.

**Platform-Specific** 🟢 Nessuno

**Import Circolari** 🟢 Nessuno
- `from telemetry.source import TelemetryFrame` è intra-package.

**Code Smells**:
- `__import__('datetime')` inline (righe 57, 205) invece di `import datetime` a inizio file.
- `_sample_counter` vs `_current_lap_samples` — logica di campionamento fragile (basata su `int(lap_elapsed)`).

**Classi Fantasma** 🟢 Nessuna

---

### 6. auth/manager.py

**Type Hints** ✅ Completo
- Tutti i metodi `@staticmethod` hanno parametri e return type.
- `Optional[User]` usato correttamente per risultati potenzialmente nulli.

**Docstrings** ✅ Buono
- Docstring di modulo (flusso auth).
- Docstring di classe.
- Metodi documentati: `get_current`, `register_email`, `login_email`, `login_google`, `logout`, `get_token`, `verify_token`.
- `is_logged_in()`: **no docstring** (ma è ovvio).

**Error Handling** 🟢 Delega
- Manager è un facade puro: non contiene error handling proprio, delega a `db.py` e `crypto.py`.
- `verify_token()` gestisce il caso `None` in modo pulito.

**Hardcoded Paths** 🟢 Nessuno

**Platform-Specific** 🟢 Nessuno

**Import Circolari** 🟢 Nessuno
- `from .db import ...` e `from .crypto import ...` sono intra-package.
- Nota: `get_token()` e `verify_token()` fanno **lazy import** di funzioni da `.db` (code smell minore: perché non importare a inizio file?).

**Code Smells**:
- `_create_user_google` (riga 15) è un alias di `create_user` — ma `create_user` è già importato alla riga 12. Confusione di naming.

**Classi Fantasma** 🟢 Nessuna

---

### 7. auth/crypto.py

**Type Hints** ✅ Completo
- Tutte le funzioni hanno parametri e return type annotati.

**Docstrings** ✅ Eccellente
- Docstring di modulo: spiega hashing, JWT, scadenze.
- Ogni funzione (`_get_jwt_secret`, `hash_password`, `verify_password`, `create_jwt`, `decode_jwt`, `fingerprint_password`) ha docstring.
- `fingerprint_password`: docstring spiega che è inutilizzata, tenuta per future migrazioni.

**Error Handling** ✅ Robusto
- `verify_password()`: catch `ValueError, TypeError`.
- `decode_jwt()`: catch `ExpiredSignatureError, InvalidTokenError, ValueError`.
- `hash_password()`: raise `ValueError` su password vuota.
- `_get_jwt_secret()`: gestisce file mancante, genera secret al primo avvio.

**Hardcoded Paths** 🟢 OK
- `paths.data_path("auth_secret.txt")` — risolto dinamicamente.

**Platform-Specific** 🟢 Nessuno

**Import Circolari** 🟢 Nessuno

**Classi Fantasma** 🟢 Nessuna

---

### 8. auth/db.py

**Type Hints** ✅ Buono
- `User` dataclass con tutti i campi tipizzati.
- Funzioni CRUD con firme complete.
- `_get_conn()` → `sqlite3.Connection` annotato.
- `_row_to_user(row: sqlite3.Row) -> User` completo.

**Docstrings** ⚠️ Parziale
- Docstring di modulo **eccellente** (include schema SQL completo).
- `User`: docstring assente (ma è auto-documentante).
- `init_auth_db()`, `create_user()`, `authenticate_user()`: con docstring.
- `get_user_by_id()`, `get_user_by_email()`, `get_user_by_google_id()`: **no docstring**.
- `update_last_login()`, `delete_user()`, `list_users()`: **no docstring**.
- `set_current_user()`, `get_current_user()`, `get_current_token()`, `clear_current_user()`: con docstring.
- `_row_to_user()`: **no docstring**.

**Error Handling** ⚠️ Connection leak risk
- `create_user()`: catch `sqlite3.IntegrityError` → reraise `ValueError`. ✅
- `set_current_user()`: raise `ValueError` se utente non trovato. ✅
- **Pattern pericoloso**: ogni funzione fa `conn = _get_conn()` ... `conn.close()` manualmente. Se un'eccezione occorre tra open e close, **la connessione perde** (no context manager, no `try/finally`).
- `check_same_thread=False` su SQLite — ok per app single-thread ma potenzialmente rischioso.

**Hardcoded Paths** 🟢 OK
- `paths.data_path("lmu_pit_strategist.db")` — dinamico.

**Platform-Specific** 🟢 Nessuno

**Import Circolari** 🟢 Nessuno
- `from .crypto import hash_password, verify_password, create_jwt` — intra-package.

**Classi Fantasma** 🟢 Nessuna

---

## Tabella riepilogativa

| File | Type Hints | Docstrings | Error Handling | Hardcoded Paths | Platform-Specific | Import Circolari | Classi Fantasma |
|------|-----------|------------|----------------|-----------------|-------------------|------------------|-----------------|
| `overlay/strategy_refresher.py` | ⚠️ | ⚠️ | ⚠️ | 🟢 | 🟡 | 🟢 | 🟢 |
| `overlay/voice_engine.py` | ✅ | ⚠️ | ⚠️ | 🟢 | 🔴 | 🟢 | 🟢 |
| `overlay/icons.py` | ⚠️ | ⚠️ | 🔴 | 🟢 | 🟢 | 🟢 | 🟢 |
| `telemetry/source.py` | ✅ | ⚠️ | 🟡 | 🟡 | 🟡 | 🟢 | 🟢 |
| `telemetry/detector.py` | ⚠️ | 🔴 | ⚠️ | 🟡 | 🟢 | 🟢 | 🟢 |
| `auth/manager.py` | ✅ | ✅ | 🟢 | 🟢 | 🟢 | 🟢 | 🟢 |
| `auth/crypto.py` | ✅ | ✅ | ✅ | 🟢 | 🟢 | 🟢 | 🟢 |
| `auth/db.py` | ✅ | ⚠️ | ⚠️ | 🟢 | 🟢 | 🟢 | 🟢 |

---

## Findings critici

### 🔴 CRIT-1: `voice_engine.py` non importabile su Linux/macOS
**File**: `overlay/voice_engine.py`, riga 11
```python
import winsound
```
`winsound` è un modulo solo Windows. L'import a livello modulo causa `ImportError` su qualsiasi OS non-Windows. L'intero file è inutilizzabile.
**Fix suggerito**: spostare `import winsound` dentro `_play()` o usare un blocco `try/except ImportError` con fallback cross-platform (es. `playsound`, `pygame`, o subprocess).

### 🔴 CRIT-2: Eccezioni ingoiate senza logging
**File**: `overlay/strategy_refresher.py`, `telemetry/detector.py`, `overlay/voice_engine.py`
Pattern diffuso: `try: ... except Exception: pass` o `return None`. Le eccezioni vengono silenziate completamente, rendendo impossibile il debug. In produzione, un errore nello strategist o nel detector è invisibile.
**Fix suggerito**: usare `logging.exception()` o almeno `print(traceback.format_exc())`.

### 🟡 HIGH-1: `sys.path.insert` a import-time
**File**: `telemetry/source.py`, righe 12-14
```python
VENDOR_PATH = paths.data_path("vendor")
sys.path.insert(0, os.path.join(VENDOR_PATH, "pyLMUSharedMemory"))
sys.path.insert(0, os.path.join(VENDOR_PATH, "pyRfactor2SharedMemory"))
```
Modifica lo stato globale di Python come side-effect dell'import. Può causare conflitti con altri moduli.
**Fix suggerito**: usare `importlib` per caricare i moduli vendored senza toccare `sys.path`.

### 🟡 HIGH-2: `detector.py` senza docstring
**File**: `telemetry/detector.py`
Classe `LapBoundaryDetector` (327 righe, logica complessa): zero docstring. Il metodo `process_frame()` (185 righe) non è documentato. Solo commenti sparsi e `print()`.
**Fix suggerito**: aggiungere docstring di classe e metodo che spieghino la state machine di rilevamento giri.

### 🟡 HIGH-3: Connection leak potenziale in `auth/db.py`
**File**: `auth/db.py`
Pattern ripetuto 15+ volte:
```python
conn = _get_conn()
cur = conn.cursor()
# ... operazioni ...
conn.close()
```
Se una qualsiasi operazione tra `_get_conn()` e `conn.close()` lancia eccezione, la connessione rimane aperta (leak).
**Fix suggerito**: usare `contextlib.closing` o un context manager.

### 🟡 HIGH-4: `voice_engine.py` disabilita TTS permanentemente al primo errore
**File**: `overlay/voice_engine.py`, `_generate_wav()`
```python
except ImportError:
    self._tts_available = False
except Exception:
    self._tts_available = False
```
Un singolo errore di rete o timeout disabilita edge-tts **per sempre** fino al restart dell'app.
**Fix suggerito**: retry con backoff, o reimpostare `_tts_available = True` dopo un certo tempo.

---

## Findings minori

| ID | File | Descrizione |
|----|------|-------------|
| M1 | `overlay/strategy_refresher.py` | `voice_engine` dichiarato `Optional[Any]` — perde type safety |
| M2 | `overlay/strategy_refresher.py` | `_plan_signature()` e `_tick()` senza docstring |
| M3 | `overlay/icons.py` | 22 funzioni icona senza type hints e senza docstring |
| M4 | `overlay/icons.py` | `clean_action_text`: regex emoji con range duplicati (`\\u2600-\\u27BF` ripetuto 3 volte) |
| M5 | `telemetry/source.py` | `SyntheticReplaySource`: attributi senza type annotation a livello classe |
| M6 | `telemetry/source.py` | `SyntheticReplaySource`: track length `5793.0` hardcodato (Monza) |
| M7 | `telemetry/source.py` | `LiveSharedMemorySource.get_next_frame()`: 180+ righe senza docstring |
| M8 | `telemetry/detector.py` | `__import__('datetime')` inline invece di import a inizio file |
| M9 | `telemetry/detector.py` | `fallback_pit_loss=30.0`, `lap_time < 20.0`: magic numbers senza costanti |
| M10 | `telemetry/detector.py` | `sector=3` per `else` — comportamento poco chiaro (S3 o unknown?) |
| M11 | `auth/manager.py` | `_create_user_google` alias confusione con `create_user` già importato |
| M12 | `auth/manager.py` | `get_token()` e `verify_token()` fanno lazy import non necessario |
| M13 | `auth/db.py` | `check_same_thread=False` senza commento sul perché |
| M14 | `overlay/voice_engine.py` | `speak()` ritorna `True` prima che il thread di playback completi |

---

## Giudizio complessivo per modulo

| Modulo | Voto | Note |
|--------|------|------|
| **auth/** | ⭐⭐⭐⭐ | Il più maturo. Buona separazione, type hints, docstrings. Unico neo: connection management in db.py. |
| **telemetry/** | ⭐⭐⭐ | Solido ma poco documentato. `detector.py` ha bisogno urgente di docstring. `source.py` ha side-effect a import-time. |
| **overlay/** | ⭐⭐ | Il più problematico. `voice_engine.py` è Windows-only, error handling silenzioso ovunque, `icons.py` senza type hints. |

**Nessuna classe fantasma né import circolari rilevati in nessun file.**
