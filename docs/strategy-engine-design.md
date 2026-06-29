# Engine di Calcolo Strategia — Design Document

## Visione generale

L'engine deve **calcolare in tempo reale** la strategia di pit stop ottimale per una gara di endurance/sprint, basandosi su:
- Dati di degrado gomme raccolti durante le prove
- Consumo carburante storico
- Condizioni meteo (attuali e previste)
- Giri reali appena completati (ricalcolo live)
- Durata gara (giri fissi o a tempo)

Deve funzionare in **due modalità**, intercambiabili dalla UI:
- **Analisi pre-gara**: su dati di prova, per decidere strategia di partenza
- **Live durante la gara**: ricalcolo continuo appena arriva un nuovo giro, con audio cue quando la strategia cambia

---

## Trigger — quando parte il calcolo

L'engine deve essere chiamato automaticamente in questi casi:

| Evento | Trigger | Azione |
|---|---|---|
| **Inizio gara/qualifica** | `LapBoundaryDetector.on_race_started()` con session_type = RACE o QUALIFYING | Ricalcola strategia completa con dati disponibili, emette audio "strategia caricata" |
| **Nuovo giro completato** | `on_lap_completed()` | Ricalcola strategia con l'ultimo giro incluso nel modello |
| **Timer periodico** | Ogni 5 secondi (StrategyRefresher) | Verifica se condizioni (fuel, usura, meteo) sono cambiate significativamente → ricalcola |
| **Cambio meteo** | Variazione rain_intensity o track_temp rilevata | Ricalcola composti e strategia |
| **Manuale** | Click "Ricalcola strategia" nel menu overlay o nella UI web | Ricalcola forzato |

---

## Input dell'engine

```
Input obbligatori:
  - auto (stringa): modello/macchina
  - tracciato (stringa): nome pista
  - session_type: "RACE" o "QUALIFYING"

Modalità gara:
  - laps_remaining (int, default null): giri rimanenti per gare a giri fissi
  - duration_hours (float, default null): ore per gare a tempo (es. 6.0 = 6 ore)
  - SE nessuno dei due → default 40 giri

Stato attuale (live):
  - current_tyre_age (int): giri sulle gomme attuali
  - current_fuel (float): carburante attuale in litri
  - fuel_capacity (float): capacità serbatoio in litri
  - max_stops (int): numero massimo soste da considerare (default 3)

Meteo (opzionale):
  - track_temp (float): temperatura pista attuale °C
  - weather_state: "DRY" | "WET" | "INTERMEDIATE"
  - rain_intensity (float 0.0-1.0)

Dati storici (letti automaticamente dal DB):
  - Giri di prova validi per quella combinazione auto+pista+mescola
  - Perdita tempo ai box osservata (media delle pit_stops registrate)
```

---

## Pipeline di calcolo

### Step 1: Preparazione dati
1. Carica dal DB i giri di prova per `(car, track)`, escludendo:
   - Giri con `is_deleted = 1`
   - Giri con `anomaly_flag = 1` (anomali)
   - Giri non validi (`is_valid_lap = 0`)
2. Se ci sono **meno di 5 giri** → restituisci errore "dati insufficienti"

### Step 2: Modello di degrado
1. Fitta un modello congiunto **carburante + degrado gomme** (Huber regression):
   ```
   lap_time = base_time + alpha * fuel_liters + deg(tyre_age)
   ```
   dove `deg(age)` è una spline lineare a tratti con possibile cliff dopo N giri
2. Output del modello:
   - `base_time`: tempo base senza carburante (s)
   - `alpha`: coefficiente carburante (s/litro)
   - `cliff_lap`: giro dopo cui il degrado accelera
   - `pre_cliff_slope`: degrado prima del cliff (s/giro)
   - `post_cliff_slope`: degrado dopo il cliff (s/giro)

### Step 3: Modello carburante
1. Calcola consumo medio per giro dai giri puliti (escludendo pit-in/out)
2. Output:
   - `mean_fuel_consumption` (litri/giro)
   - `std_fuel_consumption` (deviazione standard)

### Step 4: Stima perdita pit stop
1. Prende la media delle pit_loss osservate in sessioni precedenti
2. Se non ci sono dati → fallback a 30.0 secondi

### Step 5: Conversione gare a tempo (se duration_hours)
1. Se `duration_hours` è fornito e `laps_remaining` no:
   ```
   pace = modello.predict(tyre_age=1, fuel=fuel_capacity/2)
   laps_remaining = duration_hours * 3600 / pace
   ```
2. Il tentativo viene arrotondato per difetto e mostrato nella UI

### Step 6: Programmazione dinamica (core)

**Stato**: `(lap_idx, tyre_age, k_fuel, stops_left)`
- `lap_idx`: quanti giri già percorsi da inizio stint
- `tyre_age`: giri sulle stesse gomme
- `k_fuel`: giri equivalenti di carburante rimasto
- `stops_left`: quante soste ancora disponibili

**Decisioni per ogni giro**:
1. **Stay** (continuare): lap_time = predict(age, fuel_liters), fuel--, age++ 
2. **Pit** (box): lap_time = predict(age, fuel_liters) + pit_loss, fuel = max_fuel_laps, age = 0, stops_left--
3. Se `k_fuel == 0` → pit obbligatorio (se stops_left > 0), altrimenti DNF

**Ottimizzazione**:
- memoization su tutti gli stati visitati
- esplora `max_stops + 1` scenari (0, 1, 2, ..., max_stops soste)
- per ogni scenario, DP classica bottom-up con memo
- sceglie lo scenario con `total_time` minimo come "ottimale"
- restituisce TUTTI gli scenari come "alternative" per confronto

### Step 7: Compound planner (se dati storici sufficienti)
1. Per ogni stint, chiama `plan_compounds()` che:
   - Analizza degrado storico per diverse mescole
   - Considera meteo previsto per quello stint
   - Considera temperatura pista
   - Restituisce la mescola consigliata per ogni stint
2. Se meteo è pioggia, forza mescola da bagnato/intermedia

### Step 8: Output dell'engine

```json
{
  "optimal": {
    "stops": 2,
    "pit_laps": [15, 32],
    "total_time": 4523.7,
    "compound_plan": [
      {"stint": 1, "compound": "Medium", "laps": 15},
      {"stint": 2, "compound": "Medium", "laps": 17},
      {"stint": 3, "compound": "Soft", "laps": 13}
    ]
  },
  "alternatives": {
    "0": { "stops": 0, "pit_laps": [], "total_time": 4721.3, ... },
    "1": { "stops": 1, "pit_laps": [22], "total_time": 4612.8, ... },
    "2": { ... },  // optimal
    "3": { "stops": 3, "pit_laps": [12, 26, 38], "total_time": 4567.2, ... }
  },
  "laps_used": 45,
  "duration_hours": null,
  "mean_fuel_consumption": 3.2,
  "pit_loss_seconds": 28.5
}
```

---

## Ricalcolo live durante la gara

Quando arriva un nuovo giro:

1. Il `StrategyRefresher` (timer 5s) raccoglie:
   - `current_lap` = ultimo giro completato
   - `current_tyre_age` = giri sulle stesse gomme
   - `current_fuel` = fuel attuale
   - `total_laps` = laps_remaining calcolato (o duration convertito)
   - `laps_remaining` = total_laps - current_lap

2. Rilancia `optimize()` con i nuovi parametri

3. Se la strategia cambia rispetto alla precedente:
   - Nuovo piano di pit-stop diverso → emette audio "strategia cambiata"
   - Se il pit consigliato è tra 1-2 giri → emette audio "pit soon"
   - Se il pit consigliato è il giro corrente → emette audio "pit now" + mostra warning rosso
   - Se fuel < 2 giri → emette audio "low fuel"

4. L'overlay mostra:
   - Giro di pit consigliato
   - Quanti giri mancano al pit
   - Avviso se fuori strategia

---

## UI — visualizzazione risultati

### Tabella alternativa (Mostra/nascondi)
- Ogni alternativa (0, 1, 2, 3 soste) è una card
- Card evidenziata in verde = ottimale
- Mostra: numero soste, lap pit, tempo totale, delta dal tempo ottimale

### Grafico Lap Time Evolution
- **X**: giro numero
- **Y**: tempo sul giro (secondi)
- **Punti scatter**: giri reali colorati per stint (colori stint: verde, blu, rosso, ambra, viola, rosa)
- **Linea predetta**: curva di degrado dal modello (gialla, tratteggiata)
- **Linee verticali rosse**: pit stop reali (tratteggiate, label "PIT")
- **Linee verticali arancioni**: pit stop pianificati (tratteggiate, label "PIT PLAN")
- **Tooltip**: lap number, tempo giro, carburante, composto
- **Legenda**: stint, degrado, pit stop

### Overlay durante la gara
- **Fuel**: giri di carburante rimanenti (arancione se < 3)
- **Cliff**: giri al cliff degrado (arancione se < 5)
- **Pit**: prossimo pit stop (L22, o "BOX!" se il giro corrente)
- **Audio**: pit_soon (1-2 giri prima), pit_now (giro corrente), low_fuel (< 2 giri), strategy_changed
- **Warning banner**: "BOX QUESTO GIRO" (rosso) o "CARBURANTE CRITICO" (ambra)

---

## Architettura del codice

```
analysis/
├── models.py          # fit_degradation_model(), fit_fuel_model(), DegradationModelFit.predict()
├── strategist.py      # PitStrategist.optimize() — DP core
├── compounds.py       # plan_compounds() — mescola per stint
├── weather.py         # Previsioni stint, linear_rain_forecast
└── anomaly.py         # MAD z-score detection

overlay/
├── app.py             # Overlay full (1 finestra)
├── app_new.py         # Overlay modulare (4 finestre + ⚙)
└── strategy_refresher.py  # AudioEngine, PracticeAdvisor, StrategyRefresher (ricalcolo live)

web/
├── server.py          # API /api/strategy con laps_remaining + duration_hours
├── templates/index.html  # Pagina Strategia con selettore tipo gara + chart
└── static/app.js      # calculateStrategy(), renderLapChart(), toggleStratMode()
```

---

## Gare a tempo — comportamento atteso

La UI deve offrire un selettore "Tipo gara":
- **Giri fissi**: mostra input "Laps" (numero intero, 1-500)
- **A tempo**: mostra input "Ore" (float, 0.5-24, step 0.5)

Quando si clicca "Calcola":
- Se modalità "giri fissi" → chiama `/api/strategy?laps_remaining=X`
- Se modalità "a tempo" → chiama `/api/strategy?duration_hours=Y`

L'API risponde con `laps_used` che mostra quanti giri stima per quella durata.

Il ricalcolo live durante la gara parte dallo stesso `duration_hours` convertito in giri totali → calcola laps_remaining = total - current_lap.

---

## Note di implementazione

- La DP ha complessità O(laps × max_stops × fuel_laps × tyre_age_max). Con gare fino a 200 giri e 3 soste, è nell'ordine di 200×4×20×30 ≈ 480K stati → calcolabile in <1 secondo.
- La memoization è un dizionario {(lap, age, fuel, stops): (time, path)}.
- Il path è una lista di decisioni ["stay", "stay", "pit", "stay", ...] poi convertita in pit_laps (indici dove la decisione è "pit").
- I compound plan per stint alternativi vanno calcolati SOLO se richiesti (weather data presente), non di default.
