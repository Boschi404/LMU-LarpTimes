# Audit Qualità Codice — Modulo `analysis/`

**Data:** 2026-08-01  
**File analizzati:** 14 (.py)  
**Linee totali:** ~2,470  
**Criteri:** type hints mancanti, docstrings assenti, funzioni troppo lunghe (>50 righe), import non usati, variabili non usate, copia-incolla duplicato, nomi inconsistenti, classi che violano SRP.

---

## 📊 Riepilogo

| Categoria | Conteggio |
|---|---|
| 🔴 Bug (crash a runtime) | 1 |
| 🟠 Problemi seri (type hints / SRP) | 5 |
| 🟡 Warning (funzioni lunghe, duplicazione, naming) | 12 |
| 🔵 Minori (docstring, import, debug print) | 6 |

---

## 🔴 Bug Critici

### B1 – `qualifying.py:446` — `DegradationModelFit()` chiamato senza parametri obbligatori

```python
# qualifying.py, riga 446
if model_fit is None:
    model_fit = DegradationModelFit()  # ❌ ERRORE: mancano 6 parametri obbligatori!
```

`DegradationModelFit.__init__` (models.py:19) richiede **6 parametri posizionali obbligatori**:
`base_time, alpha, beta_1, beta_2, cliff_lap, huber_loss_val`.

Nessuno ha un valore di default → questa chiamata causa `TypeError` a runtime.

**Fix suggerito:** aggiungere valori di default al costruttore, oppure usare un factory method / valori sentinella.

---

## 🟠 Problemi Seri

### S1 – `race_engineer.py` — `RaceEngineer` è un God Class (violazione SRP)

La classe `RaceEngineer` (496 righe, ~410 di logica) gestisce:
- Monitoraggio carburante (fuel)
- Monitoraggio gomme (tyres)
- Monitoraggio meteo (weather)
- Monitoraggio traffico
- Monitoraggio strategia pit-stop
- Valutazione performance (personal best, consistenza)
- Gestione sessione (annunci inizio gara/qualifica)
- Sistema di cooldown / deduplica messaggi vocali
- Prioritizzazione eventi

**Rischio:** impossibile testare isolatamente; modificare un sottosistema rischia di romperne altri.

**Suggerimento:** Estrarre ogni sottosistema di valutazione (`_evaluate_critical_fuel`, `_evaluate_warning_tyres`, etc.) in classi separate (es. `FuelMonitor`, `TyreMonitor`, `WeatherMonitor`) con interfaccia comune `→ Optional[RaceEngineerEvent]`.

### S2 – `strategist.py:84-131` — Funzione `solve()` interna senza type hints

La closure `solve()` definita dentro `PitStrategist.optimize()` (righe 84-131) non ha **nessun** type hint su parametri e ritorno, pur essendo il cuore dell'algoritmo DP:

```python
def solve(lap_idx: int, age: int, k_fuel: int, stops_left: int) -> Tuple[float, List[str]]:
```

La mancanza di type hints rende il codice fragile e difficile da debuggare.

### S3 – `race_engineer.py:97` — `frame` non tipizzato

```python
def update_from_frame(self, frame) -> Optional[RaceEngineerEvent]:
```

`frame` è un oggetto "aperto" (usato via `getattr`), senza interfaccia definita. Questo è il punto d'ingresso principale del Race Engineer e dovrebbe avere un tipo esplicito (es. un Protocol o una dataclass `TelemetryFrame`).

### S4 – `anomaly.py` — Funzione monolitica con side-effect su database

`detect_anomalies_for_session()` (120 righe) fa TUTTO: fetch dal DB, bucketing, regressione lineare, Z-score su pace, Z-score su fuel, update del DB, in un'unica funzione. Viola SRP e rende impossibile testare le parti di calcolo separatamente dal DB.

### S5 – `weather_radar.py` — Parametri inutilizzati

In `analyze_rain_risk()` (riga 16-23):
- `lap_time_avg: float = 0` — **mai usato**
- `laps_remaining: int = 0` — **mai usato**

In `get_pit_recommendation()` (riga 73-80):
- `lap_time_avg: float` — **mai usato**
- `laps_remaining: int` — **mai usato**
- `current_lap: int` — **mai usato**
- `pit_loss_seconds: float = 30.0` — **mai usato**

Questi parametri sono "placeholder" che ingannano il chiamante facendogli credere che influenzino il risultato.

---

## 🟡 Warning

### W1 – Funzioni troppo lunghe (>80 righe)

| File | Funzione | Righe | Violazione |
|---|---|---|---|
| `strategist.py` | `PitStrategist.optimize()` | 152 | Contiene closure `solve()` di 48 righe — andrebbe estratta a metodo |
| `qualifying.py` | `estimate_tyre_temp_window()` | 140 | Divide in sezioni logiche con commenti `# ──` — estrarre in helper |
| `qualifying.py` | `_build_suggestions()` | 73 | Ogni blocco `if` è una regola indipendente — pattern Strategy |
| `tyre_manager.py` | `estimate_remaining_life()` | 120 | 7 step numerati — estrarre ogni step in metodo privato |
| `compounds.py` | `recommend_compound()` | 110 | Scoring di ogni compound potrebbe essere un metodo separato |
| `practice.py` | `analyze_practice_data()` | 175 | Analisi fuel + tyre + compound + assessment in unica funzione |
| `microsectors.py` | `compute_optimal_lap()` | 94 | Costruzione `per_lap_deltas` (righe 182-195) estraibile |
| `race_director.py` | `build_race_timeline()` | 153 | Costruzione stint + eventi + meteo in unica funzione |
| `models.py` | `fit_degradation_model()` | 64 | OK per funzione scientifica, ma la grid search e il fitting potrebbero essere separati |

### W2 – Duplicazione copia-incolla

| Pattern | File | Righe |
|---|---|---|
| `"Wet" not in X and "Intermediate" not in X and "Inter" not in X` | `weather_radar.py` | 90, 93, 97, 103 |
| `normalize_compound()` / `_normalise_compound()` | `tyre_manager.py` + `compounds.py` | Logica duplicata con spelling diverso (🇺🇸 vs 🇬🇧) |
| `RaceEngineerEvent(priority=..., category=..., message=..., tts_text=..., event_id=...)` | `race_engineer.py` | Pattern ripetuto in 9+ metodi evaluator — factory method auspicabile |
| `l for l, t in zip(laps, types) if t == LAP_HOTLAP` | `qualifying.py` | Righe 261 e 315 — calcolato due volte in metodi diversi della stessa classe |

### W3 – Import inutilizzati

| File | Import | Note |
|---|---|---|
| `models.py:3` | `Optional`, `Tuple` | Importati da `typing` ma mai usati nel file |
| `qualifying.py:9` | `Tuple` | Importato ma mai usato |
| `practice.py:12` | `Optional`, `Tuple` | Importati ma mai usati |

### W4 – Nomi inconsistenti

| Problema | Dettaglio |
|---|---|
| `normalize_compound` (🇺🇸) vs `_normalise_compound` (🇬🇧) | `tyre_manager.py` vs `compounds.py` — stesso scopo, spelling diverso, uno è pubblico l'altro privato |
| `pit_loss` (strategist.py) vs `pit_loss_seconds` (pit_practice.py, classes.py) vs `pit_loss` (race_director.py) | Stesso concetto con nomi diversi in 4 file |
| `L_fuel` (strategist.py:24) | Nome con underscore dopo lettera maiuscola — convenzione atipica; suggerito `max_fuel_laps` |

### W5 – Debug print residui

| File | Riga | Contenuto |
|---|---|---|
| `strategist.py` | 178 | `print("Pit strategist module written.")` |
| `anomaly.py` | 120 | `print("Anomaly detector module written.")` |

Questi sono artefatti di sviluppo che non dovrebbero essere in produzione.

### W6 – `race_summary_to_dict()` — tipo di ritorno bare

```python
# race_director.py:198
def race_summary_to_dict(summary: Optional[RaceSummary]) -> Dict:
```

`Dict` senza parametri generici. Dovrebbe essere `Dict[str, Any]`.

### W7 – `extract_pit_stops()` — tipo di ritorno mancante

```python
# pit_practice.py:20
def extract_pit_stops(laps: List[Dict]) -> List[PitStopRecord]:
```

Il tipo del parametro `laps` è `List[Dict]` (bare Dict). Dovrebbe essere `List[Dict[str, Any]]`. Il tipo di ritorno manca del tutto — aggiungere `-> List[PitStopRecord]`.

---

## 🔵 Minori

### M1 – `tyre_manager.py` — `COMPOUND_TEMP_WINDOW` incompleto

```python
COMPOUND_TEMP_WINDOW = {
    "Soft": (2, 3),
    "Medium": (2, 4),
    "Hard": (2, 5),
}
```

Mancano `"Wet"` e `"Intermediate"`. `estimate_remaining_life()` accede a questo dict con `compound` (riga 136) ma il fallback `(2, 3)` è implicito via `.get(normalize_compound(compound), (2, 3))`. Sarebbe più chiaro avere entry esplicite per tutte le mescole.

### M2 – `_COMPOUND_WINDOW_END` in `qualifying.py` contiene duplicato `"Wet"`

```python
_WET_COMPOUNDS = {"Wet", "Intermediate", "FullWet", "Wet"}  # "Wet" duplicato
```

`"Wet"` appare due volte nel set — innocuo ma indica copia-incolla distratto.

### M3 – `classes.py:166` — nome con underscore leading per variabile "privata" a livello modulo

```python
_TRAFFIC_BASE_PENALTIES: Dict[tuple, float] = { ... }
```

Corretto (convenzione Python per module-private), ma il tipo `tuple` è bare — dovrebbe essere `Dict[Tuple[str, str], float]`.

### M4 – `microsectors.py:216` — `format_time` accetta `None` ma type hint dice `float`

```python
def format_time(seconds: float) -> str:
    if seconds is None or seconds <= 0:
```

Il type hint dice `float` ma il codice gestisce `None` — inconsistenza type hint/logica.

### M5 – `models.py` — `DegradationModelFit.__init__` senza type hints

```python
def __init__(
    self,
    base_time: float,      # ❌ nessun type hint
    alpha: float,
    ...
```

Nessun parametro del costruttore ha type hint. Aggiungere.

### M6 – `strategist.py:82` — type hint dichiarato ma non applicato

```python
memo: Dict[Tuple[int, int, int, int], Tuple[float, List[str]]] = {}
```

La variabile `memo` ha un type hint corretto ma la funzione interna `solve` che la popola non è tipizzata → il type checker non può validare la coerenza.

---

## ✅ Cose Fatte Bene

- **Docstring**: 13/14 file hanno docstring a livello modulo. Tutte le funzioni pubbliche sono documentate. Eccellente.
- **Dataclass**: Uso appropriato di `@dataclass` per `RaceState`, `RaceEngineerEvent`, `RainWindow`, `TyreStatus`, `StintInfo`, `RaceSummary`, `RaceEvent`, `PitStopRecord`. Pattern consistente.
- **Type hints su API pubbliche**: La maggior parte delle funzioni esportate ha type hints completi (es. `linear_rain_forecast`, `estimate_remaining_life`, `recommend_compound`).
- **Separazione in moduli**: L'organizzazione in 14 file con responsabilità distinte (tyre, weather, compounds, qualifying, practice, etc.) è buona. Il problema è dentro alcuni file, non tra di essi.
- **Numpy/scipy**: Uso appropriato di `numpy` per calcoli numerici e `scipy.optimize.minimize` per il fitting.
- **Gestione errori**: `race_engineer.py` wrappa le chiamate ai sottosistemi in `try/except` (righe 202-211, 215-222, 247-248) — buona pratica difensiva.

---

## 📋 Priorità d'Intervento

| Priorità | Item | Impatto |
|---|---|---|
| 🔴 **P0** | B1: `DegradationModelFit()` senza parametri | Crash a runtime in `analyze_qualifying()` |
| 🟠 **P1** | S3: `frame` non tipizzato in `RaceEngineer` | Rende fragile l'intero sistema di eventi vocali |
| 🟠 **P1** | S2: `solve()` interna senza type hints | Rende il DP non verificabile staticamente |
| 🟡 **P2** | S1: `RaceEngineer` God Class | Manutenibilità a lungo termine |
| 🟡 **P2** | W1: Funzioni >100 righe | Leggibilità e testabilità |
| 🟡 **P2** | W2: Duplicazione `normalize_compound` | Rischio desincronizzazione |
| 🔵 **P3** | W3: Import inutilizzati | Pulizia codice |
| 🔵 **P3** | W5: Debug print residui | Pulizia output |
| 🔵 **P3** | S5: Parametri inutilizzati in `weather_radar` | API fuorviante |
