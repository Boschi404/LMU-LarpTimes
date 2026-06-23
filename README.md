# LMU Pit Strategist

Uno strumento locale in Python per Le Mans Ultimate (LMU) che:

- legge telemetria da shared memory (o genera dati sintetici per lo sviluppo)
- salva i giri su SQLite in WAL mode
- rileva anomalie di passo e consumo
- stima degrado gomme e consumo carburante
- propone una strategia di pit stop ottimale
- fornisce un overlay live in-game e una UI web esterna

---

## Requisiti

- Windows (target operativo per shared memory LMU)
- Python 3.11+
- `pip`

---

## Dipendenze

Installa le librerie richieste con:

```powershell
cd "c:\Users\leob3\Desktop\Everything\Other\Coding\LMU app"
python -m pip install -r requirements.txt
```

---

## Inizializzazione database

Prima di avviare il server o l'overlay, crea lo schema SQLite:

```powershell
python -c "import database; database.init_db()"
```

Questo creerà il file database di default nel workspace e abiliterà la modalità WAL, consentendo a più processi di leggere/scrivere contemporaneamente.

---

## Avvio della UI esterna (Processo B)

Puoi eseguire il server FastAPI locale con lo script dedicato:

```powershell
python run_server.py
```

Oppure con Uvicorn direttamente:

```powershell
python -m uvicorn web.server:app --host 127.0.0.1 --port 8000 --reload
```

Poi apri nel browser:

```
http://127.0.0.1:8000
```

### Pagine principali

- `Profilo`: analisi aggregata e curva di degrado
- `Archivio Giri`: tabella filtrabile, flag anomalie, soft-delete
- `Strategia`: calcolo dei pit-stop basato sui dati disponibili

---

## Avvio dell'overlay live (Processo A)

Sono disponibili due modalità:

### 1. Demo sintetica (nessun gioco richiesto)

```powershell
python run_overlay.py
```

Questo avvierà l'overlay usando `SyntheticReplaySource` e registrerà giri fittizi su SQLite.

### 2. Integrazione live con LMU

```powershell
python run_overlay_live.py
```

Questo avvierà l'overlay leggendo i dati reali dalla shared memory di LMU (o fallback a rFactor 2).

> **Prerequisiti per la modalità live:**
> - LMU deve essere in esecuzione su Windows
> - Abilita "Enable Plugins" in LMU Settings → Gameplay
> - LMU deve essere in modalità Finestra o Finestra senza bordi (non fullscreen esclusivo)

L'overlay supporta `LiveSharedMemorySource` che tenta di collegarsi a LMU, con fallback automatico a rFactor 2 se disponibile.


---

## Come funziona il DB

Il progetto usa tre tabelle principali:

- `sessions`: metadati di sessione (`track`, `layout`, `car`, `session_type`, `started_at`)
- `laps`: un giro completato per riga, con tutti i campi richiesti e `is_deleted` per soft-delete
- `pit_stops`: pit-stop registrati con perdita tempo osservata

Il server e l'overlay condividono lo stesso database SQLite; non comunicano direttamente tra loro.

---

## Fonti di telemetria

Sono supportate due sorgenti intercambiabili:

- `LiveSharedMemorySource`: legge i frame reali da LMU / rFactor 2 tramite le librerie vendorizzate `pyLMUSharedMemory` e `pyRfactor2SharedMemory`
- `SyntheticReplaySource`: genera telemetria plausibile per sviluppo e test senza gioco acceso

Tutta la pipeline successiva (rilevamento giri, storage, anomaly detection, modelli, strategist) funziona allo stesso modo con entrambe.

---

## Come testare rapidamente

Esegui i test con `pytest`:

```powershell
python -m pytest
```

I test includono flussi end-to-end sintetici, modelli di degrado, anomaly detection e strategist.

---

## Assunzioni principali

- il tool è monoutente e locale, senza autenticazione o cloud
- lo storage è SQLite in WAL mode per supportare overlay e UI separate
- lo sviluppo offline si basa su `SyntheticReplaySource`
- l'overlay e il server non condividono socket o IPC, solo il file DB
- i giri eliminati sono gestiti con soft-delete (`laps.is_deleted = 1`)
- il pit planner usa dinamica a stati su giri rimanenti, età gomma e carburante

---

## Prossimi passi consigliati

- aggiungere un launcher dedicato `run_overlay.py` e `run_server.py`
- migliorare l'integrazione live con LMU verificando la disponibilità reale della shared memory
- validare i modelli su dati race reali quando LMU è disponibile
- aggiungere un file `CONFIG.md` se serve configurazione aggiuntiva per serbatoi o tipi di mescola

---

## Contatti

Questo repository è stato scaffolded per un progetto personale su Le Mans Ultimate. Per ulteriori modifiche, usa `IMPLEMENTATION_CHECKLIST.md` come guida per completare le milestone richieste.