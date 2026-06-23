# Checklist operativa di implementazione — LMU Pit Strategist

## Scopo
Checklist per completare le feature richieste dal prompt originale. Questa lista è compatibile con lo stato attuale del repository e indica chiaramente cosa è già presente e cosa va verificato/implementato.

---

## Stato attuale rilevato

### Già implementato / presente
- `telemetry/source.py`
  - `TelemetrySource` base
  - `LiveSharedMemorySource` con fallback `pyLMUSharedMemory` / `pyRfactor2SharedMemory`
  - `SyntheticReplaySource` per sviluppo senza gioco
- `telemetry/detector.py`
  - `LapBoundaryDetector` che rileva fine giro, stint, pit-in / pit-out e salva in SQLite
- `database.py`
  - schema `sessions`, `laps`, `pit_stops`
  - WAL enabled, soft-delete `is_deleted`
  - funzioni CRUD per sessioni, giri, anomalie, pit stop
- `analysis/anomaly.py`
  - anomaly detector robusto basato su MAD e regressione semplice
- `analysis/models.py`
  - fit modello degrado + cliff con Huber loss
  - fit consumo carburante
- `analysis/strategist.py`
  - `PitStrategist` con programmazione dinamica e alternative per 0..N soste
- `web/server.py`
  - FastAPI server con API per profilo, archivio giri, strategia, cancellazione soft-delete
- `web/templates/index.html`
  - UI esterna con pagine `Profilo`, `Archivio Giri`, `Strategia`
  - supporto per filtri, grafico degrado, tabelle, azioni di soft-delete
- `overlay/app.py`
  - overlay PySide6 window senza bordi, sempre in primo piano
  - drag per spostare, hotkey `Ctrl+Shift+O` per nascondere/mostrare
  - worker che legge un `TelemetrySource` e registra i frame in DB
- `tests/test_e2e.py`
  - test di integrazione con `SyntheticReplaySource`, rilevamento giri, modello e strategist

### Mancano o vanno verificati
- file `README.md` con istruzioni di setup e abilitazione shared memory LMU
- entrypoint / launcher chiaro per avviare:
  - processo overlay
  - processo UI web
- verifiche live / runtime per `LiveSharedMemorySource` con LMU
- test specifici per:
  - `LiveSharedMemorySource` stubbed
  - `overlay` con `SyntheticReplaySource`
  - API `GET /api/profile`, `/api/laps`, `/api/strategy`
- potenziale revisione del modello strategist e del calcolo carburante per fedeltà reale
- controllo del browser/overlap con LMU in modalità finestra borderless nel README

---

## Milestone operative

### Milestone A — Dati e storage
- [ ] confermare schema DB e `init_db()` in `database.py`
- [ ] verificare che `sessions` includa `started_at`
- [ ] verificare la scrittura di `laps` con i campi richiesti
- [ ] verificare la creazione di `pit_stops`
- [ ] testare `SyntheticReplaySource` per almeno 40 giri sintetici
- [ ] testare `LapBoundaryDetector.process_frame()` con `SyntheticReplaySource`

### Milestone B — Anomaly detector
- [ ] verificare raggruppamento per mescola + fascia temperatura
- [ ] verificare correzione tempo in funzione di carburante + età gomme
- [ ] verificare MAD/Z-score robusto e flag `anomaly_flag`
- [ ] test su dati sintetici con outlier noti

### Milestone C — Modelli degrado / carburante
- [ ] testare `fit_degradation_model()` su dati con degradazione lineare + cliff
- [ ] testare `fit_fuel_model()` su dati puliti
- [ ] verificare che il modello ritorni parametri non negativi e un `cliff_lap` sensato
- [ ] testare la curva predittiva e la monotonicità rispetto all’età gomma

### Milestone D — Pit strategist
- [ ] verificare `PitStrategist.optimize()` con più alternative (0..N soste)
- [ ] validare output `optimal`, `alternatives`, `pit_laps`
- [ ] coprire scenari: gara corta 0-soste, gara media, gara lunga con multiple soste
- [ ] confrontare con strategie alternative manuali su scenario sintetico

### Milestone E — Live shared memory integration
- [ ] confermare `LiveSharedMemorySource.start()`/`stop()` e parsing `pyLMUSharedMemory`
- [ ] gestire graceful fallback a `pyRfactor2SharedMemory`
- [ ] assicurarsi che `LiveSharedMemorySource` rispetti l’interfaccia `TelemetrySource`
- [ ] aggiungere test stubbed per evitare dipendenza su gioco acceso

### Milestone F — Overlay PySide6
- [ ] integrare `OverlayWidget` con sorgente `TelemetrySource`
- [ ] verificare che il worker registri i giri in DB in tempo reale
- [ ] controllare drag, posizione salvata, visibilità hotkey
- [ ] mostrare regole minime: delta vs miglior giro, giri carburante rimasti, cliff gomma, box suggerito
- [ ] documentare la limitazione della modalità finestra del gioco nel README

### Milestone G — UI esterna web locale
- [ ] assicurare due pagine separate nell’HTML: `Profilo`, `Archivio Giri`, `Strategia`
- [ ] `Profilo`: statistiche aggregate, warning su dati insufficienti, curva degrado
- [ ] `Archivio Giri`: tabella filtrabile/ordinabile, flag anomalie, soft-delete
- [ ] `Strategia`: richiesta a `/api/strategy`, visualizzazione alternative e piano ottimale
- [ ] assicurare che i giri eliminati non compaiano nell’archivio attivo e siano esclusi dai calcoli

---

## Task aggiuntivi di completamento

- [ ] creare `README.md` con:
  - installazione environment Python 3.11+
  - avvio `uvicorn web.server:app --reload`
  - avvio overlay PySide6
  - come abilitare shared memory in LMU
  - assunzioni fatte e limiti noti
- [ ] aggiungere commenti / docstring mancanti laddove utili
- [ ] aggiungere un `main.py` o script `run_overlay.py` e `run_server.py` se non esistono
- [ ] verificare che il database sia accessibile in WAL da entrambi i processi simultaneamente
- [ ] controllare eventuali problemi di multithreading nel worker PySide6

---

## Assunzioni da esplicitare

- il repository deve rimanere un tool monoutente locale
- LMU shared memory è accessibile solo su Windows
- in assenza di gioco acceso, la fonte principale di sviluppo/test è `SyntheticReplaySource`
- `overlay` e `UI web` non condividono stato diretto: comunicano solo via SQLite
- `Soft-delete` è implementato con `laps.is_deleted`
- `pit_stops` è derivabile dai giri ma viene anche salvato in tabella separata

---

## Priorità di verifica

1. milestone A+B+C+D con `pytest` su dati sintetici
2. milestone F con overlay su `SyntheticReplaySource`
3. milestone G con UI web + API
4. milestone E con integrazione `LiveSharedMemorySource` e documentazione
