# LMU LarpTimes — Pit Strategist

Tool locale per **Le Mans Ultimate (LMU)** che legge telemetria in tempo reale, archivia giri, analizza degrado gomme e consumi, calcola strategia di gara ottimale e mostra overlay live + UI web.

> **Stato**: 270 test, 0 failure. Funzionante con LMU live e in modalità standalone con dati sintetici.

---

## Funzionalità

| Cosa | Dettaglio |
|---|---|
| **Telemetria live** | Legge shared memory LMU via `pyLMUSharedMemory` (vendorizzata) |
| **Dati sintetici** | `SyntheticReplaySource` per sviluppo e test senza gioco |
| **Archiviazione giri** | SQLite WAL mode — sessioni, giri, pit stop, stint |
| **Anomaly detection** | MAD z-score robusto su passo e consumi — non cancella mai, solo flagga |
| **Degrado gomme** | Regressione Huber congiunta carburante + età gomma + cliff |
| **Pit strategist** | Programmazione dinamica: soste ottimali per giri fissi **o a tempo** |
| **Compound planner** | Mescola consigliata per ogni stint in base a meteo + degrado storico |
| **Meteo** | Previsione stint-by-stint (pioggia, temperatura) |
| **Overlay live** | PySide6 trasparente always-on-top: modulare (4 finestre) o full (1 griglia) |
| **Audio cues** | Suono quando cambia strategia, carburante basso, pit imminente |
| **Race detection** | Rileva automaticamente inizio gara/qualifica → calcola strategia |
| **UI web** | FastAPI locale: Profilo (curve degrado), Archivio (tabella filtrabile), Strategia (calcolo + chart lap times), Setup (consigli meteo) |
| **Login** | Pagina di accesso con email (locale, niente cloud obbligatorio) |
| **Owner identity** | Filtro dashboard per utente (`owner_email` su ogni giro) |
| **Export/import** | Bundle JSON portabile (`/api/laps/export`, `/api/laps/import`) |
| **Cloud sync** | Opzionale — push/pull su Turso DB (community) con opt-in |
| **Security** | CSP headers, rate limiting (200 req/min), input validation, SQL parameterized, self-audit all'avvio |
| **Practice advisor** | Suggerisce stint di pratica se dati insufficienti |

---

## Requisiti

- **Windows** (target per shared memory LMU)
- **Python 3.11+**
- LMU opzionale — tutto funziona anche senza (dati sintetici)

### Per LMU live
- Abilita **"Enable Plugins"** in LMU → Impostazioni → Gameplay
- LMU in modalità **Finestra** o **Finestra senza bordi** (fullscreen esclusivo non supporta overlay)

---

## Installazione

```powershell
cd "C:\Users\leob3\Desktop\Everything\Other\Coding\LMU app"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

---

## Avvio rapido

### Solo UI web (nessun gioco)

```powershell
run_server.bat
# Apri http://127.0.0.1:8000
```

Inserisci la tua email nella pagina di login. Se non hai dati, clicca **"Crea 20 giri di esempio"** sul welcome banner.

### Overlay + UI web

```powershell
run_app.bat
```

### Solo overlay

```powershell
# Modulare (4 finestre + ⚙)
run_overlay.bat

# Full (1 finestra, griglia)
python run_overlay.py

# Con LMU live
python run_overlay_live.py
```

---

## Architettura

```
Processo A (mentre guidi):
  LMU → SharedMemory → TelemetrySource (live/synthetic)
                      → LapBoundaryDetector → SQLite
                      → Overlay trasparente PySide6
                      → Audio cues + race detection

Processo B (UI esterna, anche offline):
  SQLite → Anomaly detector → Modelli degrado/fuel → Pit strategist
         → FastAPI server (127.0.0.1:8000)
         → Pagine: Profilo, Archivio, Strategia, Setup

I due processi NON comunicano direttamente — condividono solo il DB SQLite.
```

---

## Pagine web

| Pagina | URL | Cosa mostra |
|---|---|---|
| **Profilo** | `/` (dopo login) | Curva degrado + statistiche aggregate filtrabili |
| **Archivio** | Clicca "Archivio" | Tabella giri filtrabile, flag anomalie, soft-delete |
| **Strategia** | Clicca "Strategia" | Calcolo pit stop (giri fissi o a tempo) + chart lap times |
| **Setup** | Clicca "Setup" | Consigli setup basati su meteo/temperatura |

---

## Overlay — due versioni

### Modulare (4 finestre)
- Ogni componente è una finestra separata (Delta, Fuel, Cliff, Pit)
- ⚙ tray button: click sinistro → menu rapido, doppio click → settings dialog
- Audio cues, practice mode, community opt-in

### Full (1 finestra, griglia 3×3)
- Tutti i dati in un colpo d'occhio
- Stesse feature: audio, refresher, race detection, settings dialog
- Hotkey: `Ctrl+Shift+O` toggle visibilità

---

## Gare a tempo vs giri fissi

Il pit strategist supporta entrambe:

- **Giri fissi**: inserisci il numero di giri (es. 50 per una sprint)
- **A tempo**: inserisci la durata in ore (es. 6.0 per 6 ore). Il numero di giri viene stimato dal passo medio.

Seleziona la modalità nella pagina Strategia con il selettore "Tipo gara".

---

## Assunzioni principali

1. **Monoutente locale** — niente autenticazione di rete, niente multi-utente. L'owner_email è solo un identificativo opzionale per filtrare la dashboard.
2. **SQLite WAL** — overlay e web server condividono il DB senza IPC. WAL garantisce letture senza bloccare scritture.
3. **Sviluppo offline** — `SyntheticReplaySource` genera dati plausibili per testare senza LMU.
4. **Soft-delete** — i giri cancellati restano nel DB (`is_deleted = 1`), esclusi da calcoli e archivio attivo.
5. **Modello di degrado** — assume degrado lineare a tratti con possibile cliff dopo N giri. Non modella graining termico improvviso.
6. **Consumo carburante** — lineare per giro. Non modella variazioni per stint di bandiera gialla o safety car.
7. **Perdita pit stop** — costante per tutta la gara. Non modella box chiusi o variazioni per traffico.
8. **Shared memory LMU** — funziona solo su Windows con "Enable Plugins" attivo in LMU.
9. **Overlay** — richiede LMU in finestra o finestra senza bordi. Fullscreen esclusivo non supporta overlay sovrapposti.
10. **Gare a tempo** — il numero di giri è stimato dal passo medio. Durante la gara il ricalcolo può raffinare la stima.

---

## Test

```powershell
python -m pytest
# 270 test, 0 failure attesi
```

Include test per: anomaly detection, modelli degrado/fuel, pit strategist (DP), compound planner, web API, overlay, security (CSP, rate limit, SQL injection scan), auth module, cloud sync, self-audit, owner email.

---

## Struttura repository

```
├── analysis/          # Modelli: degrado, carburante, strategist, anomalie, compound, meteo
├── auth/              # Modulo auth (bcrypt + JWT + Google OAuth — disattivato, usa owner_email)
├── database/          # DB SQLite: schema, CRUD, export/import, cloud sync (Turso)
├── overlay/           # PySide6 overlay: full (app.py), modulare (app_new.py), strategy_refresher
├── security/          # Self-audit all'avvio (env, token, binding, tunneling)
├── telemetry/         # Fonti dati: source (live + synthetic), detector (lap boundary)
├── web/               # FastAPI server, template HTML, static JS/CSS
│   ├── server.py      # API endpoints + security middleware
│   ├── templates/     # index.html, login.html
│   └── static/        # app.js
├── vendor/            # Librerie vendorizzate: pyLMUSharedMemory, pyRfactor2SharedMemory
├── tests/             # 270 test
├── run_app.bat        # Avvia tutto (server + overlay)
├── run_server.bat     # Avvia solo UI web
└── run_overlay.bat    # Avvia solo overlay modulare
```
