# T5 — Audit Overlay PySide6 Modulare (app_new.py)

**File audited:** `overlay/app_new.py` (2042 righe)  
**File confrontato:** `overlay/app.py` (1055 righe)  
**Data:** 2026-08-01  
**Versione:** Modulare — 10+ finestrelle separate + tray manager + warning banner

---

## 1. DUPLICAZIONE CODICE CON app.py

**Gravità: ALTA.** Oltre il 60% del codice tra `app.py` e `app_new.py` è duplicato
identico o quasi-identico. Nessun modulo condiviso; ogni file è una copia
indipendente con piccole varianti.

### 1.1 Design System duplicato (identico)

| Blocco | app.py (righe) | app_new.py (righe) |
|---|---|---|
| Colori (`BG_DEEP`…`ACCENT_CYAN`) | 47–61 | 62–76 |
| Tipografia (`FONT_DISPLAY`, `FONT_MONO`, `FONT_UI`) | 68–70 | 83–85 |
| `qcolor_hex()` | 73–74 | 116–117 |
| `COMPONENT_ORDER` | 154 | 101 |
| `COMPONENT_LABELS` | 155–158 | 102–113 |

**Nota:** `COMPONENT_ORDER`/`COMPONENT_LABELS` differiscono: `app.py` ne ha 4,
`app_new.py` ne ha 10. Le label in `app_new.py` sono in italiano ("Carburante",
"Usura gomme", "Qualifica"), mentre `app.py` usa abbreviazioni inglesi
("CARBURANTE" vs "Carburante").

### 1.2 Config Persistence duplicata

```python
# app.py:89-97
def load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        return {**DEFAULT_CONFIG, **json.load(open(CONFIG_PATH))}
    return dict(DEFAULT_CONFIG)

def save_config(cfg: dict) -> None:
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)
```

```python
# app_new.py:156-172
def load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r") as f:
            return {**DEFAULT_CONFIG, **json.load(f)}
    return dict(DEFAULT_CONFIG)

def save_config(cfg: dict) -> None:
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)
    # Auto-save to profile system (EXTRA)
    try:
        if _active_profile_name:
            _save_profile(_active_profile_name, cfg)
        _save_profile("last_used", cfg)
    except Exception:
        pass
```

**Differenze:**
- `load_config()`: `app.py` apre il file senza specificare `"r"` e senza `with`
  statement esplicito per il `json.load` — funziona ma è meno robusto.
- `save_config()`: `app_new.py` ha l'auto-save del profilo (extra 6 righe).
  Differenza non documentata; se entrambi i processi sono attivi, l'auto-save
  di `app_new.py` scrive anche le chiavi `_vis`/`_enabled` dei componenti,
  potenzialmente sovrascrivendo lo stato di `app.py`.

**DEFAULT_CONFIG divergenti:**
- `app.py` (riga 83–86): 5 chiavi (`x`, `y`, `visible`, `in_game_only`, `audio_*`)
- `app_new.py` (riga 127–153): 40+ chiavi con posizioni per 10 componenti, hotkey
  IDs, profili. I due DEFAULT_CONFIG non sono compatibili: `app.py` non conosce
  le chiavi `delta_x`, `fuel_x`, etc.

### 1.3 TelemetryWorker quasi-identico

| Aspetto | app.py | app_new.py |
|---|---|---|
| Segnali | 4 identici | 4 identici |
| `start_source()` | Righe 117–134 | Righe 261–279 |
| `stop()` | Righe 136–141 | Righe 281–286 |
| Wrapper race/qualifying | `_race_wrapper`, `_qualifying_wrapper` | `_race_started_wrapper`, `_qualifying_started_wrapper` |

**Unica differenza:** nomi dei metodi wrapper (rinominati in `app_new.py`).
Logica identica, polling a 20 Hz in entrambi.

### 1.4 Logica di strategia duplicata (identica o quasi)

| Metodo | app.py | app_new.py | Differenza |
|---|---|---|---|
| `_estimate_fuel_laps()` | 914–922 | 1342–1350 | **Identico** |
| `_estimate_cliff_laps()` | 924–931 | 1392–1399 | **Identico** |
| `_calculate_refuel()` | (inline in update_frame) | 1352–1390 | Separato in app_new, logica identica |
| `_refresh_strategy()` | 933–950 | 1401–1430 | Logica identica; app_new ha `try/except` più ampio |
| `_run_qualifying_analysis()` | 838–912 | 1432–1455 | Quasi identico; app.py costruisce il testo inline, app_new usa `QualifyingOverlay.update_value()` |
| `_update_practice_analysis()` | 972–1001 | 1457–1467 | app.py costruisce testo inline; app_new usa `PracticeOverlay.update_value()` |
| `on_lap_completed()` | 809–813 | 1317–1321 | **Identico** |
| `on_race_started()` | 815–821 | 1323–1330 | Differenza: app.py nasconde `_lbl_qualy`, app_new no |
| `on_qualifying_started()` | 823–828 | 1332–1340 | Differenza: app.py mostra `_lbl_qualy`, app_new no |
| `set_session_info()` | 830–833 | 1469–1472 | **Identico** |
| `set_pit_plan()` | 835–836 | 1474–1475 | **Identico** |

### 1.5 PaintEvent duplicato

`paintEvent()` in `OverlayWidget` (app.py:543–580) e `MiniOverlay` (app_new.py:448–485)
è strutturalmente identico:
1. Ombra (shadow offset 2,2)
2. Sfondo BG_DEEP + bordo BORDER
3. Texture carbon-fiber (punti ogni 24px)
4. Barra superiore ambra 6px + glow
5. Barra sinistra ambra 3px

**Unica differenza:** app_new.py esegue tutto su un `MiniOverlay` di 160×90,
app.py su un `OverlayWidget` a dimensione variabile.

### 1.6 SettingsDialog duplicato

| Aspetto | app.py (161–304) | app_new.py (1646–1883) |
|---|---|---|
| Righe | ~144 | ~238 |
| Component toggles | ❌ Assenti | ✅ 10 checkbox |
| Profile manager | ❌ Assente | ✅ Completo |
| Overlay mode toggle | ✅ | ✅ (duplicato) |
| Audio test | ✅ | ✅ (duplicato) |

Entrambi definiscono lo stylesheet QDialog da zero (~30 righe identiche).

### 1.7 run_overlay() struttura duplicata

Entrambi i file definiscono `run_overlay()` con lo stesso pattern:
1. `QApplication.instance() or QApplication(sys.argv)`
2. `app.setStyle("Fusion")`
3. Crea widget/manager
4. Crea `TelemetryWorker` + `QThread`
5. Collega segnali
6. Avvia thread + refresher
7. `cleanup()` su `aboutToQuit`
8. `app.exec()`

---

## 2. INCONSISTENZA DESIGN SYSTEM

### 2.1 Label naming: italiano vs inglese

| Componente | `app.py` label | `app_new.py` label |
|---|---|---|
| delta | `"DELTA"` | `"Delta"` |
| fuel | `"CARBURANTE"` | `"Carburante"` |
| cliff | `"CLIFF"` | `"Cliff gomme"` |
| pit | `"BOX"` | `"Pit stop"` |
| weather | (inline) `"METEO"` | `"Meteo"` |
| wear | (inline) `"USURA FL"` | `"Usura gomme"` |
| compound | (inline) `"MESCOLA"` | `"Mescola"` |
| sectors | (inline) `"SETTORI"` | `"Settori"` |
| qualy | (inline) `"QUALIFICA"` | `"Qualifica"` |
| practice | (inline su qualy label) | `"Pratica"` |

### 2.2 Tipografia inconsistente

| Widget | app.py font size | app_new.py font size |
|---|---|---|
| Titolo componente | 7pt | 7pt |
| Valore delta | 11pt | 14pt |
| Valore fuel | 11pt / 10pt | 13pt / 10pt |
| Valore pit | 11pt | 14pt |
| Valore meteo | 10pt | 12pt → 9px inline |
| Valore usura | 10pt | 11pt |
| Valore mescola | 10pt | 12pt |
| Valore settori | 10pt | 11pt |

**Problema:** `WeatherOverlay` e `SectorsOverlay` in `app_new.py` usano
`font-size: 9px` inline via stylesheet, che sovrascrive il font QFont.
Il resto usa QFont in pt — mescolare `pt` e `px` causa scaling imprevedibile
su display DPI diversi.

### 2.3 Stile celle discordante

- **app.py:** Griglia 3×3 con `border-left: 3px solid amber` su ogni cella (riga 457)
- **app_new.py:** `MiniOverlay` con barra superiore 6px + barra sinistra 3px ambra (riga 472–485)

Due interpretazioni diverse dello stesso "design system". In `app.py` manca
la barra superiore; in `app_new.py` manca il `border-left` sulle label interne.

### 2.4 ManagerTray paintEvent diverso

`ManagerTray.paintEvent()` (app_new.py:1953–1971) ha ombra + sfondo BG_DEEP +
bordo BORDER_STRONG + barra ambra 6px. Ma manca:
- La texture carbon-fiber (puntini)
- La barra sinistra ambra
- Il glow superiore

Quindi il tray è visivamente diverso dai MiniOverlay.

### 2.5 WarningOverlay senza stile

`WarningOverlay` (app_new.py:854–887) **non ha `paintEvent`** definito.
Il widget è `WA_TranslucentBackground` ma non disegna nessuno sfondo.
Risultato: testo flottante senza background, potenzialmente illeggibile
su sfondo scuro del gioco.

---

## 3. WIDGET NON GESTITI / PROBLEMI DI STATO

### 3.1 PracticeOverlay sovrascrive QualifyingOverlay (app.py)

In `app.py`, practice e qualifying condividono la stessa label `_lbl_qualy`
(riga 532). Quando il session type non è RACE né QUALIFYING, la practice
analysis sovrascrive i dati qualifying (riga 996–999). L'utente perde
le informazioni qualifying appena entra in sessione practice.

**In app_new.py:** questo è risolto con due overlay separati. ✅

### 3.2 CompoundOverlay: accesso array senza bounds check

```python
# app_new.py:709
compound = frame.tyre_compounds[0] or "—"
```

Se `tyre_compounds` è una lista vuota, `IndexError`. Stesso bug in `app.py:761`.

### 3.3 SectorsOverlay: divisione per zero mascherata

```python
# app_new.py:729-730
s2 = frame.last_sector2 - frame.last_sector1 if (frame.last_sector2 and frame.last_sector1) else 0
s3 = frame.last_lap_time - frame.last_sector2 if (frame.last_lap_time and frame.last_sector2) else 0
```

Se `last_sector1 > last_sector2`, `s2` sarà negativo — nessun controllo.

### 3.4 WeatherOverlay: pioggia 0%

```python
# app_new.py:596
rain = f"pioggia {frame.rain_intensity:.0%}" if frame.rain_intensity > 0 else ""
```

Se `rain_intensity = 0`, mostra stringa vuota. OK. Ma se `rain_intensity` è
`None`, crash con `TypeError`. app.py non gestisce affatto `rain_intensity`.

### 3.5 WearOverlay: `self.layout()` potrebbe essere None

```python
# app_new.py:615-617
layout = self.layout()
if layout is not None:
    layout.addWidget(self._status)
```

Il check `is not None` è corretto, ma il costruttore di `MiniOverlay` chiama
`super().__init__()` senza passare un parent. Se `QVBoxLayout(self)` fallisce
silenziosamente, `self._status` non viene mai aggiunto e l'utente non vede
lo stato gomme — nessun warning.

### 3.6 WarningOverlay non è un MiniOverlay

`WarningOverlay` estende `QWidget` direttamente, non `MiniOverlay`. Non eredita:
- `toggle_visible()` / `show_overlay()` / `hide_overlay()`
- `reset_position()`
- `contextMenuEvent` (menu tasto destro)
- Drag-to-move (non implementato)
- Persistenza posizione in config
- `paintEvent` (vedi §2.5)

### 3.7 show_overlay() vs hide() inconsistenza

`MiniOverlay.show_overlay()` (riga 365) salva `_vis = True` e chiama `save_config()`.
Ma `contextMenuEvent` (riga 421) chiama `self.hide()` direttamente senza salvare
il config. Inoltre `SettingsDialog._on_comp_toggle()` (riga 1862) chiama
`ov.hide()` senza passare per `hide_overlay()`. Il flag `_vis` rimane `True`
mentre la finestra è nascosta → inconsistenza di stato.

---

## 4. PROBLEMI DI LAYOUT CON 10+ FINESTRELLE

### 4.1 Posizioni predefinite sovrapposte

```python
DEFAULT_POSITIONS = {
    "delta": (50, 50),     "fuel":  (220, 50),
    "cliff": (390, 50),    "pit":   (560, 50),
    "weather": (50, 120),  "wear": (220, 120),
    "compound": (390, 120),"sectors": (560, 120),
    "qualy": (50, 190),    "practice": (50, 260),
}
```

Ogni `MiniOverlay` ha dimensione minima 160×90 (alcuni 160×110). Su una riga
(4 componenti × 160px = 640px + 3 gap), i componenti sulla stessa riga si
toccano. Su schermi 1920×1080 funziona, ma su 1366×768 (laptop) i componenti
della terza e quarta colonna escono dallo schermo (pit_x=560 + 160 = 720, ok,
ma sectors_x=560 + 160 = 720, ok). **Su schermi <1600px di larghezza,**
le posizioni predefinite causano overflow orizzontale.

### 4.2 Nessun meccanismo anti-overlap

I 10 overlay vengono posizionati con `move(x, y)` assoluto. Non esiste:
- Snap-to-grid
- Tiling automatico
- Dock/group
- Rilevamento collisioni

Se l'utente trascina un overlay sopra un altro, rimangono sovrapposti.
Il tray manager (default: 50, 160) si sovrappone a `wear` (220, 120) se
spostato.

### 4.3 Dimensioni finestre inconsistenti

| Overlay | Dimensione |
|---|---|
| Delta, Fuel, Cliff, Pit, Weather, Compound, Sectors, Qualy, Practice | 160×90 |
| Wear | 160×110 (esteso per status label) |
| WarningOverlay | Altezza fissa 38px, larghezza automatica |
| ManagerTray | 44×44 |

Il `WearOverlay` è 20px più alto ma le posizioni predefinite non tengono conto
di questa differenza — la griglia predefinita assume tutte le finestre uguali.

### 4.4 Z-ordering incontrollato

Ogni `MiniOverlay` ha flag `WindowStaysOnTopHint`. Con 10+ finestre
always-on-top, l'ordine di stacking è indeterminato. Qt non garantisce
quale finestra stia sopra quando due si sovrappongono. Non c'è codice
per gestire `raise()` o `lower()`.

### 4.5 ManagerTray posizione fissa vs layout

Il `ManagerTray` viene posizionato a (50, 160) di default, ma non esiste
una relazione spaziale con gli altri overlay. Se l'utente resetta le
posizioni, il tray rimane dov'era — non viene resettato da
`reset_position()` perché non è nel dizionario `components`.

---

## 5. BUG NEL MENU CONFIGURAZIONE

### 5.1 show_settings_menu: closure potenzialmente fragile

```python
# app_new.py:1081-1093
def make_toggle(k):
    def _on_toggle(state):
        self._cfg[f"{k}_enabled"] = bool(state)
        save_config(self._cfg)
        ov = self.components[k]
        if not state:
            ov.hide()         # <-- non chiama hide_overlay(), non salva _vis
        else:
            ov.show_overlay()
    return _on_toggle
checkbox.toggled.connect(make_toggle(key))
```

La `make_toggle(k)` cattura correttamente `k` per valore. Tuttavia:
- `ov.hide()` non aggiorna il flag `_vis` → inconsistenza
- Il segnale `toggled` scatta quando `setChecked()` viene chiamato, anche
  durante la costruzione del menu → `save_config()` chiamato 10 volte
  all'apertura del menu (una per ogni checkbox)

### 5.2 SettingsDialog ri-carica config indipendentemente

```python
# app_new.py:1652
self._cfg = load_config()
```

`SettingsDialog` carica una **copia fresca** del config da disco. Se
l'`OverlayManager` ha modificato lo stato in memoria (es. `_user_wants_visible`),
le modifiche non sono visibili nel dialog finché non viene riaperto.

### 5.3 _on_comp_toggle non sincronizza MiniOverlay._cfg

```python
# app_new.py:1854-1862
def _on_comp_toggle(self, key, state):
    self._cfg[f"{key}_enabled"] = state
    save_config(self._cfg)
    ov = self._manager.components.get(key)
    if ov:
        if state:
            ov.show_overlay()
        else:
            ov.hide()
```

`self._cfg` è la copia del dialog, MA `save_config()` scrive su disco.
`MiniOverlay._cfg` è un riferimento all'oggetto originale in memoria
(passato nel costruttore). Quando il dialog chiama `save_config(self._cfg)`,
scrive la sua copia locale, potenzialmente sovrascrivendo chiavi modificate
dal manager nel frattempo.

### 5.4 Profilo "last_used" caricato ma non mostrato

```python
# app_new.py:972-981
stored_profile = self._cfg.get("_current_profile", "last_used")
profile_data = load_profile(stored_profile)
if profile_data:
    _active_profile_name = stored_profile
    self._current_profile = stored_profile
    self._apply_profile_data(profile_data)
else:
    _active_profile_name = "last_used"
    self._current_profile = "last_used"
    self._cfg["_current_profile"] = "last_used"
```

Se il profilo `_current_profile` non esiste su disco, si fallbacka a
`"last_used"`. Ma `load_profile("last_used")` potrebbe anche fallire,
e in quel caso non viene applicato nessun layout — le finestre appaiono
nelle posizioni di default. Il nome profilo mostrato nel tray rimane
`"last_used"` anche se nessun layout è stato effettivamente caricato.

### 5.5 Eliminazione profilo attivo non gestita nel menu

`_prompt_delete_profile()` (riga 1617) permette di eliminare qualsiasi
profilo, incluso quello attivo. `delete_profile_by_name()` gestisce il
fallback a `"last_used"`, ma se anche `"last_used"` è corrotto, il
sistema rimane senza profilo valido.

### 5.6 Menu header hardcoded per modalità modulare

```python
# app_new.py:1057
title = menu.addAction("  COMPONENTI MODULARI")
```

Il menu `show_settings_menu()` è condiviso tra tutte le modalità, ma
il titolo hardcoded "COMPONENTI MODULARI" appare anche quando l'overlay
è in modalità full.

---

## 6. HOTKEY GLOBALI MALFUNZIONANTI

### 6.1 Docstring ingannevole

```python
# app_new.py:16
#   - Hotkey globali: Ctrl+Shift+O toggle full, Ctrl+Shift+M toggle modulare.
```

**app_new.py NON registra Ctrl+Shift+O.** Quella hotkey è registrata
solo da `app.py` (riga 604, ID=1). `app_new.py` registra:
- `Ctrl+Shift+M` (ID=2) → toggle visibilità modulare
- `Ctrl+Shift+H` (ID=3) → hide all

La docstring è fuorviante: l'utente si aspetta che Ctrl+Shift+O funzioni
anche nell'overlay modulare.

### 6.2 Conflitto ID hotkey tra processi

Entrambi i processi (app.py e app_new.py) vengono lanciati come processi
separati. Gli ID hotkey Windows (`RegisterHotKey`) sono globali per
il desktop. Se entrambi i processi sono attivi:

- **app.py** registra ID=1 (Ctrl+Shift+O)
- **app_new.py** registra ID=2 (Ctrl+Shift+M) e ID=3 (Ctrl+Shift+H)

Se il launcher (`run_app.py`) lancia l'overlay, decide quale processo
avviare in base a `overlay_mode` nel config (riga 184). In teoria solo
uno è attivo. **MA** se l'utente cambia `overlay_mode` nel config senza
riavviare, o se un processo zombie rimane in esecuzione, entrambi possono
coesistere e ID=1 (usato da app.py) non colliderà con ID=2,3 (usati da
app_new.py) — ma il comportamento è imprevedibile.

### 6.3 app.py hardcoded ID=1, non legge config

```python
# app.py:602
self._hk_toggle = 1
```

`app.py` ignora completamente `hk_full_id` dal config. Se il config ha
`"hk_full_id": 1`, funziona per coincidenza. Se l'utente cambiasse
`hk_full_id` a 10, `app.py` continuerebbe a usare ID=1.

### 6.4 RegisterHotKey fallisce silenziosamente

```python
# app_new.py:990-998
try:
    ctypes.windll.user32.RegisterHotKey(
        None, self._hk_modular_id, MOD_CONTROL | MOD_SHIFT, VK_M
    )
    ...
except Exception:
    pass
```

Se la registrazione fallisce (es. hotkey già presa da altro programma),
l'eccezione è silenziata. L'utente non sa che la hotkey non funziona.
Nessun fallback, nessun log, nessun messaggio.

Stesso problema in `app.py:604-609`.

### 6.5 PeekMessageW può perdere eventi

```python
# app_new.py:1009-1013
msg = ctypes.wintypes.MSG()
WM_HOTKEY = 0x0312
if ctypes.windll.user32.PeekMessageW(
    ctypes.byref(msg), None, WM_HOTKEY, WM_HOTKEY, 1
):
```

`PeekMessageW` con `wMsgFilterMin=WM_HOTKEY, wMsgFilterMax=WM_HOTKEY`
filtra solo WM_HOTKEY. Il parametro `wRemoveMsg=1` (PM_REMOVE) rimuove
il messaggio dalla coda. Se il timer QTimer è a 100ms, pressioni molto
ravvicinate (<100ms) potrebbero essere accodate ma solo una viene
processata per ciclo. In pratica non è grave, ma due pressioni rapide
di Ctrl+Shift+M potrebbero non alternare due volte.

### 6.6 unregister_hotkeys parziale

```python
# app_new.py:1000-1005
def unregister_hotkeys(self):
    for hk_id in (self._hk_modular_id, self._hk_hideall_id):
        try:
            ctypes.windll.user32.UnregisterHotKey(None, hk_id)
        except Exception:
            pass
```

App_new deregistra solo ID 2 e 3. Se in futuro venisse aggiunta la
registrazione di ID 1 (Ctrl+Shift+O), questa non verrebbe pulita.

### 6.7 Nessuna hotkey per singolo componente

Il menu contestuale di ogni `MiniOverlay` (riga 409) mostra:
```
Hotkey globale: Ctrl+Shift+M (modulare)
```

Ma non esiste una hotkey per toggle del singolo componente (es.
Ctrl+Shift+D per delta). L'utente deve usare il menu tasto destro
per ogni finestra.

---

## 7. RIEPILOGO RISCHI

| Rischio | Severità | Priorità |
|---|---|---|
| Duplicazione massiva — manutenzione impossibile | 🔴 CRITICA | P0 |
| Hotkey silenziosamente non funzionanti | 🔴 CRITICA | P0 |
| WarningOverlay senza sfondo (illeggibile) | 🟠 ALTA | P1 |
| Inconsistenza stato `_vis` vs `hide()` | 🟠 ALTA | P1 |
| Config sovrascritto da processi concorrenti | 🟠 ALTA | P1 |
| Layout rotto su schermi <1600px | 🟡 MEDIA | P2 |
| Practice sovrascrive Qualy (app.py) | 🟡 MEDIA | P2 |
| CompoundOverlay IndexError potenziale | 🟡 MEDIA | P2 |
| Design system divergente tra full/modulare | 🟢 BASSA | P3 |
| Font px vs pt inconsistente | 🟢 BASSA | P3 |

---

## 8. RACCOMANDAZIONI

1. **Estrarre modulo condiviso** `overlay/_shared.py` con:
   - Design system (colori, font, `qcolor_hex`)
   - Config persistence (`load_config`, `save_config`, `DEFAULT_CONFIG` unificato)
   - `TelemetryWorker`
   - Metodi strategia (`_estimate_fuel_laps`, `_estimate_cliff_laps`,
     `_calculate_refuel`, `_refresh_strategy`, `_run_qualifying_analysis`,
     `_update_practice_analysis`)
   - `paintEvent` base
   - `COMPONENT_ORDER`, `COMPONENT_LABELS` unificati

2. **Unificare SettingsDialog** in un unico file, con sezioni condizionali
   (component toggles visibili solo in modalità modulare).

3. **Centralizzare gestione hotkey** in un modulo `_hotkeys.py` con:
   - Registrazione con fallback e log
   - Condivisione ID tra processi
   - Cleanup consistente

4. **Aggiungere sistema di layout** per 10+ finestre:
   - Griglia adattiva (n colonne configurabili)
   - Snap-to-grid
   - Evitare overlap

5. **Rendere WarningOverlay una sottoclasse di MiniOverlay** per ereditare
   stile, drag, persistenza.

6. **Aggiungere bounds check** su `tyre_compounds[0]` in entrambi i file.
