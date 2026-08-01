# T13 — Feature Gap Analysis: LMU LarpTimes vs Competitor Simracing Tools

> **Data analisi**: 01 Agosto 2026  
> **Analista**: Subagent T13 (Feature Gap)  
> **Metodo**: Analisi statica completa della codebase + confronto con feature set documentati dei competitor  
> **Target utente**: Simracer hardcore, endurance, multiclasse (Hypercar/LMP2/GT3)

---

## 1. Riepilogo Esecutivo

LarpTimes è già un tool **molto avanzato** per il calcolo strategico (pit strategist, degrado gomme, compound planner, race engineer TTS) e si posiziona bene nella nicchia *strategia e analisi pre/post-gara*. Tuttavia, rispetto all'ecosistema di tool concorrenti (SimHub, RaceLab, Crew Chief, Second Monitor, Z1, iOverlay), mancano **completamente** alcune categorie di funzionalità fondamentali per il simracer hardcore, in particolare:

- **Live timing e consapevolezza in gara** (relatives, track map, radar)
- **Analisi telemetria professionale** (export MoTeC, setup comparator)
- **Supporto endurance avanzato** (driver swap, team radio)
- **Integrazione hardware** (VR overlay, stream deck, bass shakers, dashboard secondario)
- **Gestione powertrain avanzata** (DRS/ERS/hybrid)

---

## 2. Feature Esistenti in LarpTimes (baseline)

### ✅ Già implementato

| Categoria | Feature | File |
|-----------|---------|------|
| **Overlay** | PySide6 trasparente always-on-top, 4 finestre modulari o 1 full | `overlay/app.py`, `overlay/app_new.py` |
| **Strategia Pit** | Programmazione dinamica multi-sosta, giri fissi e a tempo | `analysis/strategist.py` |
| **Race Engineer** | TTS edge-tts con priority queue (CRITICAL > WARNING > INFO > STATUS) | `analysis/race_engineer.py`, `overlay/voice_engine.py` |
| **Gomme** | Stima vita residua, cliff detection, wear rate, compound planner | `analysis/tyre_manager.py`, `analysis/compounds.py` |
| **Carburante** | Consumo medio/giro, modello Huber, predizione stint | `analysis/models.py` |
| **Meteo** | Previsione stint-by-stint, rain windows, pit recommendation meteo | `analysis/weather.py`, `analysis/weather_radar.py` |
| **Multi-classe** | Rilevamento Hypercar/LMP2/GT3, traffic penalty per classe | `analysis/classes.py` |
| **Qualifica** | Classificazione giri (cold/in-window/degraded), sector analysis | `analysis/qualifying.py` |
| **Micro-settori** | 9 sub-sectors, optimal lap assembly | `analysis/microsectors.py` |
| **Practice** | Suggerisce sessioni pratica se dati insufficienti | `analysis/practice.py` |
| **Pit Stop** | Estrazione e analisi performance pit stop | `analysis/pit_practice.py` |
| **Race Director** | Ricostruzione timeline gara completa da dati lap | `analysis/race_director.py` |
| **Anomaly** | MAD z-score robusto, flag senza cancellazione | `analysis/anomaly.py` |
| **Audio Cues** | Pit soon, pit now, low fuel, strategy changed | `overlay/strategy_refresher.py` |
| **Web UI** | FastAPI: Profilo, Archivio, Strategia, Setup, Login | `web/server.py` |
| **Cloud** | Sync opzionale Turso DB | `database/cloud.py` |
| **Security** | CSP, rate limiting, SQL parametrizzato, self-audit | `security/`, `web/server.py` |
| **Export** | Bundle JSON portabile | `database/__init__.py` |

---

## 3. Matrice Comparativa: LarpTimes vs Competitor

| Funzionalità | LarpTimes | Crew Chief | SimHub | RaceLab | Z1 | Second Monitor | iOverlay |
|--------------|-----------|------------|--------|---------|----|----------------|----------|
| **Overlay in-game** | ✅ | ❌ (solo audio) | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Pit Strategist** | ✅✅ (DP avanzato) | ⚠️ (basic) | ⚠️ (via plugin) | ⚠️ (fuel calc) | ❌ | ⚠️ (base) | ❌ |
| **Race Engineer TTS** | ✅✅ | ✅✅ (gold standard) | ⚠️ (via plugin) | ❌ | ✅ (speech) | ❌ | ❌ |
| **Tyre Management** | ✅✅ (cliff+wear) | ⚠️ (basic) | ⚠️ (temps) | ❌ | ✅ (temps) | ❌ | ❌ |
| **Weather Forecast** | ✅ (stint forecast) | ⚠️ (basic) | ⚠️ (data display) | ⚠️ (radar) | ❌ | ❌ | ❌ |
| **Multi-class** | ✅ | ❌ | ✅ (via overlay) | ✅ | ❌ | ✅ | ✅ |
| **Live Timing (relatives)** | ❌ | ❌ | ✅✅ | ✅✅ | ✅✅ | ✅✅ | ✅✅ |
| **Track Map** | ❌ | ❌ | ✅✅ | ✅✅ | ✅✅ | ✅✅ | ✅✅ |
| **Weather Radar Visivo** | ❌ | ❌ | ✅✅ | ✅✅ | ❌ | ❌ | ❌ |
| **Fuel Calculator Avanzato** | ⚠️ (base) | ✅✅ | ✅✅ | ✅✅ | ⚠️ (base) | ✅✅ | ✅ |
| **Setup Comparator** | ❌ | ❌ | ⚠️ (via MoTeC) | ❌ | ✅✅ | ❌ | ❌ |
| **Driver Swap (Endurance)** | ❌ | ❌ | ⚠️ (via plugin) | ❌ | ❌ | ⚠️ (timing) | ❌ |
| **Team Radio** | ❌ | ✅ (via app separata) | ⚠️ (SimGrid) | ❌ | ❌ | ❌ | ❌ |
| **Export MoTeC i2** | ❌ | ❌ | ✅✅ | ❌ | ✅✅ | ❌ | ❌ |
| **VR Overlay nativo** | ❌ | ❌ | ⚠️ (via SteamVR) | ✅✅ | ❌ | ❌ | ⚠️ (OpenXR) |
| **DRS/ERS Management** | ❌ | ❌ | ✅ (via overlay) | ✅ | ⚠️ (data) | ❌ | ✅ |
| **Dashboard secondario** | ❌ | ❌ | ✅✅ (phone/tablet) | ❌ | ✅✅ | ❌ | ❌ |
| **Bass Shaker / Haptics** | ❌ | ❌ | ✅✅ (ShakeIt) | ❌ | ❌ | ❌ | ❌ |
| **Stream Deck Integration** | ❌ | ❌ | ✅✅ | ✅ | ❌ | ❌ | ❌ |

**Legenda**: ✅✅ = feature gold standard | ✅ = presente | ⚠️ = parziale/basic | ❌ = assente

---

## 4. Gap Analysis Dettagliata

### 🔴 MUST HAVE — Funzionalità critiche per competere

#### 4.1 Live Timing Avanzato (Relatives + Standings)
**Stato LarpTimes**: ❌ Assente  
**Competitor di riferimento**: RaceLab, iOverlay, Second Monitor, SimHub  
**Descrizione**: In gara, il pilota deve sapere in tempo reale:
- Posizione assoluta e per classe (Hypercar/LMP2/GT3)
- Gap dal leader (assoluto e per classe)
- Gap dal pilota davanti e dietro (±0.0s)
- Battaglie attive: chi sta guadagnando/perdendo tempo
- Status pit stop degli avversari (in/out)
- Best lap time e best sector di ogni pilota
- Tempo di sessione rimanente, giri completati

**Perché è critico**: Senza live timing, il pilota non ha consapevolezza tattica in gara. È la feature #1 più richiesta dai simracer. LarpTimes ha solo dati sul proprio giro — non vede gli altri.

**Implementazione in LarpTimes**:
- LMU shared memory espone dati dei concorrenti? (da verificare)
- In alternativa: parsing dei file di sessione LMU o plugin MQTT/WebSocket
- UI: nuovo pannello overlay "Standings" con tabella scrollabile, colori per classe
- Integrazione con multi-class detection già esistente

---

#### 4.2 Track Map Interattiva
**Stato LarpTimes**: ❌ Assente  
**Competitor di riferimento**: RaceLab, iOverlay, Z1, Second Monitor  
**Descrizione**:
- Mappa del tracciato con posizione in tempo reale (auto propria e avversari)
- Colori per classe (Hypercar = rosso, LMP2 = blu, GT3 = verde)
- Heat map di performance per settore (dove si guadagna/perde)
- Settori colorati in tempo reale (verde = best, viola = personale best, giallo = slow)
- Zoom e pan interattivi

**Perché è critico**: La track map è il secondo overlay più usato dopo il relative. Fornisce consapevolezza spaziale immediata.

**Implementazione in LarpTimes**:
- Necessario database delle mappe dei tracciati (coordinate SVG/GeoJSON dei circuiti LMU)
- Coordinate X/Y dei piloti dalla shared memory (da verificare disponibilità)
- Rendering: canvas HTML5 nel web UI o widget PySide6 nell'overlay
- Integrazione con micro-sector analysis già esistente per heat map

---

#### 4.3 Weather Radar Visivo
**Stato LarpTimes**: ⚠️ Parziale — solo analisi testuale (RainWindow con probabilità, intensità, raccomandazioni)  
**Competitor di riferimento**: SimHub (plugin rain), RaceLab weather overlay, iOverlay radar  
**Descrizione**:
- Mappa radar della pioggia sovrapposta alla track map
- Animazione del movimento delle celle di pioggia (timelapse)
- Zone bagnato/asciutto sul tracciato in tempo reale
- Previsione visuale: "pioggia tra 5 minuti sul settore 2"
- Crossfade tra condizione attuale e prevista
- Icone meteo per ogni stint nel grafico strategia

**Perché è critico**: Per gare endurance con meteo dinamico (Le Mans!), il radar visivo è essenziale per decidere il momento esatto del pit per gomme da bagnato. LarpTimes ha già l'analisi meteo (`weather_radar.py`, `weather.py`) — manca solo la visualizzazione.

**Implementazione in LarpTimes**:
- Estendere `analysis/weather_radar.py` per generare dati di griglia (grid di intensità pioggia)
- Integrare con track map (se implementata)
- Canvas rendering con gradienti di blu (pioggia) sovrapposti alla mappa
- Timeline animata con slider per "previsione a +5min, +10min, +15min"

---

#### 4.4 Export Telemetria MoTeC i2
**Stato LarpTimes**: ❌ Assente  
**Competitor di riferimento**: SimHub (plugin MoTeC export), Z1 Analyzer  
**Descrizione**:
- Export dei dati di telemetria in formato MoTeC i2 (.ld / .ldx)
- Compatibilità con il software MoTeC i2 Pro Analysis (standard de facto nel motorsport reale e simracing)
- Canali esportati: RPM, velocità, acceleratore, freno, sterzo, marcia, temperature gomme, pressioni, forze G, tempo sul giro, settori
- Metadati: nome pilota, auto, tracciato, data, condizioni meteo

**Perché è critico**: MoTeC i2 è il gold standard per l'analisi telemetrica. Senza export MoTeC, LarpTimes è escluso dall'ecosistema di analisi avanzata usato dai team professionisti e dagli alieni.

**Implementazione in LarpTimes**:
- Studio del formato .ld/.ldx (binary structured, documentazione disponibile)
- Scrittura di un writer `telemetry/motec_writer.py`
- Nuovo endpoint API: `POST /api/telemetry/export/motec` 
- Integrazione con `telemetry/source.py` per accesso ai canali raw
- Canali minimi richiesti: RPM, Speed, Throttle, Brake, Gear, SteerAngle, LapTime, LapDistance, TyreTempFL/FR/RL/RR

---

#### 4.5 Fuel Calculator Avanzato
**Stato LarpTimes**: ⚠️ Parziale — calcolo base consumo medio/giro e stima giri rimanenti  
**Competitor di riferimento**: Crew Chief, SimHub, RaceLab  
**Descrizione**:
- **Fuel saving target**: quanti litri/giri risparmiare per evitare uno splash extra
- **Lift & coast advisor**: suggerisce quando fare lift & coast e quanto carburante si risparmia
- **Marginal fuel calculation**: carburante esatto per finire la gara (né una goccia di più)
- **Safety car / FCY adjustment**: ricalcolo automatico consumo in regime di safety car
- **Energy deployment strategy**: per Hypercar ibride, strategia di deploy energia per stint
- **Fuel mix recommendations**: suggerimenti di mappatura motore (lean/rich) per risparmio
- **Tank capacity verification**: verifica che il pieno basti per lo stint più lungo

**Implementazione in LarpTimes**:
- Estendere `analysis/models.py` con `AdvancedFuelModel`
- Nuovo parametro: `fuel_save_target_pct` (es. risparmia il 5% per evitare splash)
- Integrare nel Race Engineer: evento "FUEL_SAVE" con target litri/giro
- UI: nuovo pannello "Fuel Strategy" nella pagina Strategia
- Overlay: indicatore "SAVE FUEL" o "LIFT & COAST" con conteggio litri risparmiati

---

### 🟡 NICE TO HAVE — Differenziatori competitivi

#### 4.6 Setup Comparator
**Stato LarpTimes**: ❌ Assente (la pagina "Setup" mostra solo consigli meteo, non confronto setup)  
**Competitor di riferimento**: Z1 Analyzer, VRS Telemetry, Garage 61, Motec i2  
**Descrizione**:
- Confronto telemetrico tra due setup (A vs B) sulla stessa pista
- Differenza di tempo per settore/micro-settore
- Analisi differenziale: carico aerodinamico, altezza da terra, rigidità sospensioni, pressioni gomme
- Overlay grafico dei canali (throttle trace, brake trace, steering trace) sovrapposti per setup A e B
- Database setup condiviso (community hub)
- Suggerimenti automatici: "con setup B guadagni 0.3s in S1 ma perdi 0.1s in S3"

**Implementazione in LarpTimes**:
- Nuovo modulo `analysis/setup_comparator.py`
- Caricamento file setup LMU (formato JSON/proprietario — da investigare)
- Integrazione con micro-sector analysis per delta per settore
- UI: nuova tab "Setup Compare" con grafici sovrapposti e tabella differenze

---

#### 4.7 Driver Swap per Endurance
**Stato LarpTimes**: ❌ Assente  
**Competitor di riferimento**: Second Monitor (timing per pilota), SimHub (via plugin community)  
**Descrizione**:
- Pianificazione turni piloti prima della gara (driver schedule)
- Timer stint per pilota corrente
- Statistiche per pilota: pace medio, consumo carburante, errori, best lap
- Regolamenti endurance: tempo minimo/massimo per pilota, numero massimo di stint consecutivi
- Alert: "driver swap tra 3 giri", "tempo minimo pilota raggiunto"
- UI dedicata per il team manager: vista globale di tutti i piloti
- Integrazione con login/owner_email per identificare il pilota corrente

**Implementazione in LarpTimes**:
- Nuovo modulo `analysis/driver_swap.py`
- Nuova tabella DB: `drivers` (nome, email, statistiche aggregate)
- Estensione `RaceEngineer` con eventi "DRIVER_SWAP_DUE", "DRIVER_MIN_TIME_MET"
- UI web: pagina "Endurance" con pianificazione stint e statistiche pilota

---

#### 4.8 Team Radio Simulata
**Stato LarpTimes**: ❌ Assente (Race Engineer parla solo al pilota locale)  
**Competitor di riferimento**: Crew Chief (networked mode), SimGrid TeamLINQ  
**Descrizione**:
- Comunicazione vocale TTS tra membri dello stesso team (es. pilota 1 → pilota 2)
- Messaggi strategici automatici: "Sto entrando ai box tra 2 giri"
- Notifiche broadcast: "Pioggia in arrivo, tutti ai box per gomme wet"
- Chat testuale integrata nella UI web per il team manager
- Integrazione Discord: webhook per notifiche strategiche nel canale team
- Supporto per spotter condiviso (stessa istanza Crew Chief-like per tutto il team)

**Implementazione in LarpTimes**:
- Estendere `RaceEngineer` con modalità networked
- Protocollo WebSocket tra istanze LarpTimes (team member A ↔ team member B)
- Nuovo endpoint WebSocket: `/ws/team`
- Chat UI nella pagina web "Team Radio"

---

#### 4.9 VR Overlay
**Stato LarpTimes**: ❌ Assente (PySide6 non funziona in VR)  
**Competitor di riferimento**: RaceLab (OpenXR/OpenVR nativo), iOverlay (OpenXR)  
**Descrizione**:
- Overlay renderizzati nativamente nello spazio VR (non come finestra desktop)
- Posizionamento 3D personalizzabile: sopra il volante, a lato, nel cielo
- Supporto OpenXR (standard moderno) e OpenVR (SteamVR, legacy)
- Performance: rendering efficiente senza impattare il framerate
- UI di configurazione in VR (point & click con controller VR)
- Stessi componenti dell'overlay desktop: delta, fuel, cliff, pit, standings, track map, radar

**Implementazione in LarpTimes**:
- Nuovo modulo `overlay/vr_overlay.py` usando OpenXR (via ctypes/pyopenxr)
- Rendering: texture 2D proiettate in quad 3D
- Configurazione posizione/rotazione/scala per ogni pannello
- Integrazione con il sistema overlay esistente (stesse fonti dati)

---

### 🟢 FUTURE — Roadmap a medio-lungo termine

#### 4.10 DRS/ERS Management
**Stato LarpTimes**: ❌ Assente  
**Competitor di riferimento**: RaceLab, iOverlay (per F1); SimHub (via overlay custom)  
**Descrizione**:
- Stato DRS: disponibile (verde), attivo (arancione), non disponibile (grigio)
- Rilevamento automatico zona DRS (da track map)
- ERS/hybrid: stato batteria, modalità deploy (Qualify/Balanced/Build), energia per giro
- Suggerimenti strategici: "Attiva DRS tra curva 3 e 4", "Cambia modalità ERS in Build per ricaricare"
- Predizione: "con ERS in Qualify mode guadagni 0.5s al giro ma la batteria dura 3 giri"
- Nota: LMU (Hypercar) ha sistema ibrido ma non DRS; la feature è più rilevante per F1

**Implementazione futura**: Solo se/shared memory LMU espone canali ibridi (MGU-K, batteria, deploy mode).

---

#### 4.11 Dashboard Secondario (Phone/Tablet)
**Stato LarpTimes**: ❌ Assente  
**Competitor di riferimento**: SimHub (phone/tablet via browser), Z1 (server mode), RaceLab (browser)  
**Descrizione**:
- UI web responsive ottimizzata per tablet/phone come dashboard secondaria
- Layout specifici per device (7", 10", phone)
- Connessione via WiFi locale (stessa rete)
- Sincronizzazione in tempo reale (WebSocket)
- Design "cruscotto": RPM, marcia, velocità, temperature, fuel, giri rimasti

**Implementazione futura**: LarpTimes ha già un server web FastAPI — estendere con WebSocket + layout responsive.

---

#### 4.12 Integrazione Hardware (Stream Deck, Bass Shakers, LED)
**Stato LarpTimes**: ❌ Assente  
**Competitor di riferimento**: SimHub (ShakeIt bass shakers, Stream Deck plugin, LED matrix, wind sim)  
**Descrizione**:
- **Stream Deck**: tasti configurabili per cambiare pagina overlay, ricalcolare strategia, toggle muto TTS
- **Bass Shakers**: feedback tattile per ABS, TC, kerbs, cambio marcia, bloccaggio ruote
- **LED**: shift lights su Arduino/STM32
- **Wind Simulator**: ventole sincronizzate con la velocità

**Implementazione futura**: Richiede SDK hardware specifici, priorità più bassa.

---

## 5. Riepilogo Prioritizzazione

### 🔴 MUST HAVE (da implementare entro 3 mesi per restare competitivi)

| # | Feature | Impatto | Sforzo stimato | Competitor chiave |
|---|---------|---------|----------------|-------------------|
| 1 | **Live Timing Avanzato** | 🔴 Critico | 3-4 settimane | RaceLab, iOverlay |
| 2 | **Track Map Interattiva** | 🔴 Critico | 2-3 settimane | RaceLab, Z1, iOverlay |
| 3 | **Weather Radar Visivo** | 🔴 Alto | 1-2 settimane | SimHub, RaceLab |
| 4 | **Export MoTeC i2** | 🔴 Alto | 2 settimane | SimHub, Z1 |
| 5 | **Fuel Calculator Avanzato** | 🔴 Alto | 1-2 settimane | Crew Chief, RaceLab |

### 🟡 NICE TO HAVE (differenziatori, entro 6 mesi)

| # | Feature | Impatto | Sforzo stimato | Competitor chiave |
|---|---------|---------|----------------|-------------------|
| 6 | **Setup Comparator** | 🟡 Medio-Alto | 3-4 settimane | Z1, VRS, Garage 61 |
| 7 | **Driver Swap Endurance** | 🟡 Medio | 2-3 settimane | Second Monitor |
| 8 | **Team Radio Simulata** | 🟡 Medio | 2-3 settimane | Crew Chief (networked) |
| 9 | **VR Overlay** | 🟡 Medio | 4-6 settimane | RaceLab |

### 🟢 FUTURE (roadmap 6-12 mesi, nice-to-explore)

| # | Feature | Impatto | Sforzo stimato | Note |
|---|---------|---------|----------------|------|
| 10 | **DRS/ERS Management** | 🟢 Basso-Medio | 2-3 settimane | Rilevante solo se LMU espone canali ibridi |
| 11 | **Dashboard Secondario** | 🟢 Basso-Medio | 1-2 settimane | Già presente server web, estensione moderata |
| 12 | **Haptics/Hardware** | 🟢 Basso | 4-8 settimane | Stream Deck, bass shakers, LED — molto complesso |

---

## 6. Vantaggi Competitivi di LarpTimes (da preservare e comunicare)

LarpTimes ha già **importanti vantaggi** rispetto ai competitor che vanno valorizzati:

| Vantaggio | Dettaglio |
|-----------|-----------|
| **Pit Strategist avanzato** | DP multi-sosta con degrado gomme congiunto — unico nel suo genere tra i tool gratuiti |
| **Race Engineer TTS integrato** | Non un plugin separato — è nativo con priority queue e cooldown intelligente |
| **Multi-class nativo** | Rilevamento Hypercar/LMP2/GT3 con parametri specifici per classe — non presente in Crew Chief |
| **Micro-sector analysis** | 9 sub-sectors per giro — analisi più granulare di qualsiasi competitor (tipicamente solo 3 settori) |
| **Offline-first** | Funziona completamente senza connessione, senza gioco (SyntheticReplaySource) |
| **Architettura pulita** | Processo A (overlay) + Processo B (web server) — separazione chiara, senza IPC complesso |
| **Gratuito e open** | Nessun piano a pagamento, codice ispezionabile |

---

## 7. Raccomandazioni Strategiche

1. **Implementare il trio Live Timing + Track Map + Weather Radar** come primo blocco. Sono le feature che fanno la differenza tra "tool di analisi post-gara" e "compagno di gara in tempo reale". Senza queste, LarpTimes è solo un tool di preparazione, non un race companion.

2. **Prioritizzare l'export MoTeC** perché apre l'interoperabilità con l'ecosistema di analisi professionale (Motec i2, ATLAS, WinTax) e permette a LarpTimes di essere il "data collector" per tool di analisi esterni.

3. **Il fuel calculator avanzato è low-hanging fruit**: l'infrastruttura (modello degrado, strategist, weather) c'è già — manca solo l'interfaccia utente e qualche metrica aggiuntiva.

4. **Non cercare di competere con SimHub sull'hardware**: SimHub domina incontrastato su bass shakers, LED, motion, dashboards fisici. LarpTimes deve differenziarsi su strategia, analisi e race engineering.

5. **Il VR overlay è un investimento costoso**: richiede competenze 3D/OpenXR non presenti nel team. Meglio integrare con RaceLab o iOverlay via API piuttosto che reinventare.

---

## 8. Fonti e Riferimenti

- **SimHub**: https://www.simhubdash.com/ — Dashboards, ShakeIt, MoTeC export, overlays, LED
- **Crew Chief V4**: https://mr_belowski.gitlab.io/CrewChiefV4/ — Spotter, race engineer audio, fuel calc
- **RaceLab**: https://racelab.app/ — VR overlay, live timing, track map, radar, fuel calc
- **iOverlay**: https://ioverlay.app/ — Live timing, track map, radar, standings
- **Second Monitor**: https://github.com/Winzarten/SecondMonitor — Live timing, telemetry viewer, driver timing
- **Z1 Dashboard**: https://www.z1racetech.com/dashboard/ — Dashboard, Analyzer, Server, telemetry
- **Sim Racing Telemetry (SRT)**: https://www.simracingtelemetry.com/ — Cross-platform telemetry analysis
- **Edge Overlays**: https://edgeoverlays.com/ — Free overlays, VR support, fuel calc
- **Track Impulse**: https://track-impulse.com/overlays — Free SimHub alternative, radar spotter
- **Sim Racing Manual (comparison)**: https://simracingmanual.com/resources/telemetry-and-overlays/

---

## 9. Allegati e Note

- **Tutti i file di LarpTimes analizzati**: 60+ file Python, 3 file HTML, 1 file JS, 3 file MD di progetto
- **Nessun file modificato**: questa è un'analisi statica, nessun codice toccato
- **Test totali**: 284 test, 0 failure (da PROJECT_STATE.md)
- **Riga di codice stimata**: ~15,000 LOC Python + ~3,500 LOC HTML/JS/CSS
- **API endpoint documentati**: 15+ (da web/server.py)

---

*Task T13 completato. Prossimo passo: Assembly (T15) compilerà questo report con gli altri findings.*
