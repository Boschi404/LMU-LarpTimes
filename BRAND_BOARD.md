# LMU LarpTimes — Brand Board & Design System v1.0

> ⚠️ **DOCUMENTO DI DESIGN** — Non applicato al codice. Da revisionare prima di qualsiasi implementazione.
>
> Progettato per: LMU LarpTimes (Le Mans Ultimate telemetria e strategia)
> Target: Sim-racer, categoria endurance, multiclasse (Hypercar/LMP2/GT3)
> Filosofia: *"Pit wall engineering — ogni pixel lavora per il pilota"*

---

## Indice

1. [Anti-AI-Slop Manifesto](#1-anti-ai-slop-manifesto)
2. [Brand Soul](#2-brand-soul)
3. [Color System](#3-color-system)
4. [Typography](#4-typography)
5. [Spatial System](#5-spatial-system)
6. [Component Library](#6-component-library)
7. [Data Visualization](#7-data-visualization)
8. [Motion & Interaction](#8-motion--interaction)
9. [Voice & Tone](#9-voice--tone)
10. [UI Patterns to Avoid](#10-ui-patterns-to-avoid)

---

## 1. Anti-AI-Slop Manifesto

Cosa rende un tool di telemetria "professionale" vs "AI-generated":

| ❌ AI Slop | ✅ Professionale |
|---|---|
| Glassmorphism su tutte le card | Superfici solide, opache, con purpose |
| Gradiente viola-blu | Palette selettiva, ogni colore ha un significato dati |
| Inter 400 su tutto | Gerarchia tipografica: 3 pesi, 2 famiglie, razione |
| Card tutte uguali (stesso bordo, stesso radius) | Variazione intenzionale basata sul contenuto |
| Ombre morbide e diffonde | Luci dure da motorsport, shadow nette, definite |
| "Dark mode" come afterthought | Buio funzionale — riduce affaticamento in cabina |
| Icone decorative senza etichetta | Icona + label sempre, niente decorazione |
| Dati separati da tanto whitespace whitespace | Alta densità informativa — è telemetria |
| Transizioni fluide 0.3s ease | Reattività immediata 0.1s — è un tool da gara |
| "SaaS generico" layout | Layout asimmetrico, ottimizzato per scan veloce |

**Principio cardine**: In un tool di telemetria, **il dato è la UI**. Ogni elemento decorativo che non veicola informazione è rumore. Il design system esiste per organizzare il dato, non per "abbellire".

---

## 2. Brand Soul

### Archetype
**The Pit Wall Engineer** — preciso, analitico, affidabile sotto pressione. Non è un brand "divertente" o "giovanile". È uno strumento da professionisti.

### Brand Values
| Valore | Significato | Applicazione |
|---|---|---|
| **Precision** | Ogni millisecondo conta | Timing, allineamento, griglie |
| **Signal over noise** | I dati parlano, il layout tace | Massimo data-ink ratio |
| **Speed of interpretation** | Leggi in un colpo d'occhio | Gerarchia visiva aggressive |
| **Reliability** | Deve funzionare in gara | Zero decorative fluff, robusto |
| **Engineering** | Bellezza nell'architettura | Simmetrie funzionali, non decorative |

### Moodboard descrittivo
Immagina:
- Il muro dei monitor in un box di Le Mans — 6 schermi, ognuno con un dato specifico
- Una dashboard di F1 — pulsanti fisici, feedback immediato, nessuna animazione superflua
- Un orologio analogico Heuer — leggibile in 0.1 secondi, meccanica esposta
- Il cruscotto di una LMP1 — OLED su fibra di carbonio, solo ciò che serve

### Non siamo
- Un "SaaS bello" — non siamo un tool per PMI
- Un gioco — non deve essere "divertente", deve essere efficace
- Un social — niente avatar, niente like, niente gamification

---

## 3. Color System

### Filosofia
The palette is **data-functional**: every color carries information. There is no "primary brand color" used decoratively. Colors exist to encode data states.

### Core Backgrounds

```
--bg-deep:       #030507    (Pit wall dark — fondale assoluto)
--bg-app:        #05080C    (App background — leggibile ma profondo)
--bg-surface:    #0B1017    (Card surface — solido, non glass)
--bg-elevated:   #111A24    (Elevated surface — hover, modali)
--bg-inset:      #182230    (Input, campi dati — interno card)
```

**Regola**: Nessun background trasparente o glass. Le superfici sono solide e definite. Il vetro in telemetria è inutile — aumenta il carico cognitivo senza beneficio.

### Data Colors (functional, not decorative)

```
--data-fast:     #00E5A0    (Fast — tempo positivo, delta negativo)
--data-slow:     #FF4466    (Slow — tempo perso, delta positivo)
--data-neutral:  #6B7D8F    (Neutrale — baseline, riferimento)

--data-blue:     #0088FF    (Selezionato, focus, attivo)
--data-amber:    #FF9000    (Warning — attenzione, pit soon)
--data-purple:   #8860FF    (Lap A nel confronto)
--data-cyan:     #00C8FF    (Lap B nel confronto)

--data-surface:  #1A2A3A    (Chart grid, axis lines)
--data-line:     #2A3A4A    (Chart axes, tick marks)
```

**Regola cromatica**: 
- Il verde NON è "ok" generico. È "più veloce" o "miglior tempo". Non usare verde per "successo" o "completato".
- Il rosso NON è "errore". È "più lento" o "tempo perso". Non usare rosso per "errori UI".
- Il blu NON è "primary". È "selezione attuale" o "focus".

### Text Hierarchy

```
--text-primary:   #E8EDF2    (Dati critici, valori principali)
--text-secondary: #8A9BAB    (Label, metadata, descrizioni)
--text-tertiary:  #4A5A6A    (Placeholder, legenda, non importante)
--text-inverse:   #05080C    (Testo su sfondo chiaro, solo badge)
```

### Semantic Colors (per stati funzionali)

```
--status-pit:     #FF4466    (PIT NOW — critico, urgente)
--status-soon:    #FF9000    (Pit soon — warning)
--status-ok:      #00E5A0    (Tutto nella finestra)
--status-cold:    #0088FF    (Dato insufficiente, gomme fredde)
```

---

## 4. Typography

### ⚠️ Rule #1: NON usare Inter
Inter è il font di default di ogni tool AI. È il "Helvetica del 2025" — ok per documenti, terribile per un brand motorsport.

### Font Stack

#### Display: **Aktiv Grotesk** (o in subordine: **Satoshi**)
Weights: 500 (Medium), 700 (Bold)

Usato per:
- Valori numerici nelle card telemetry (es. "223.456")
- Header delle pagine
- Label di navigazione

Perché: Aktiv Grotesk ha un taglio geometrico preciso, con curve chiuse che ricordano la strumentazione di bordo. La "a" a un piano e la "t" squadrata trasmettono precisione ingegneristica.

#### Mono: **JetBrains Mono** (confermato)
Weights: 400 (Regular), 600 (SemiBold)

Usato per:
- Tutti i dati telemetrici grezzi (lap time, fuel, delta)
- Tabelle e griglie dati
- Tooltip e hover data

Perché: JetBrains Mono ha legature opzionali e un'altezza x generosa che lo rende leggibile anche a corpi piccoli in alta densità.

#### UI: **Inter** (SOLO per UI system — non per dati)
Weights: 400 (Regular), 500 (Medium), 600 (SemiBold)

Usato per:
- Bottoni, filtri, form control
- Messaggi di sistema
- Label non-dati (es. "Carica profilo")

### Size Scale

```
--text-xs:   0.625rem  (10px) — Legenda chart, metadata
--text-sm:   0.75rem   (12px) — Label form, tabella header
--text-base: 0.875rem  (14px) — Body text, descrizioni
--text-lg:   1rem      (16px) — Card title, dati secondari
--text-xl:   1.25rem   (20px) — Valori card, metriche
--text-2xl:  1.5rem    (24px) — Metriche primarie
--text-3xl:  2rem      (32px) — Numeri hero (lap time)
--text-4xl:  2.5rem    (40px) — Delta display in overlay
```

### Type Treatments specifici

| Elemento | Font | Weight | Size | Case |
|---|---|---|---|---|
| Lap time (hero) | Aktiv Grotesk | Bold | 2.5rem | — |
| Delta value | Aktiv Grotesk | Bold | 1.5rem | — |
| Stat label | Inter | Medium | 0.625rem | UPPERCASE |
| Table data | JetBrains Mono | Regular | 0.75rem | — |
| Table header | Inter | SemiBold | 0.625rem | UPPERCASE |
| Section title | Aktiv Grotesk | Bold | 1.25rem | UPPERCASE |
| Badge | Inter | SemiBold | 0.625rem | UPPERCASE |
| Tooltip data | JetBrains Mono | Regular | 0.75rem | — |
| Button label | Inter | SemiBold | 0.75rem | Sentence |
| Filter label | Inter | Medium | 0.625rem | UPPERCASE |

---

## 5. Spatial System

### Grid
Basata su 8px con sotto-griglia 4px per micro-aggiustamenti.

```
--space-1:  0.25rem   (4px)
--space-2:  0.5rem    (8px)
--space-3:  0.75rem   (12px)
--space-4:  1rem      (16px)
--space-5:  1.5rem    (24px)
--space-6:  2rem      (32px)
--space-8:  3rem      (48px)
--space-10: 4rem      (64px)
```

### Layout Principles
1. **Information density**: Il tool di telemetria deve mostrare MOLTI dati. Whitespace non è "aria" — è organizzazione. Non spaziare per bellezza, spazia per leggibilità.
2. **Asimmetria funzionale**: Layout non speculari. La griglia 3×3 del full overlay è simmetrica per necessità (ogni cella è ugualmente importante), ma la web UI deve avere gerarchia visiva.
3. **Sidebar come tool wall**: Ispirata ai pannelli di controllo nei box. Stretta (200px), scura, strumenti di navigazione — non decorazione.

### Border Radii

```
--radius-none: 0px       (Tabelle, input, header)
--radius-sm:   2px       (Card, container)
--radius-md:   4px       (Bottoni, badge)
--radius-full: 9999px    (Solo per chip e toggle)
```

**Regola**: Niente border-radius > 4px su superfici dati. I dati non sono "carini". Il radius esiste solo per distinguere gerarchie, non per estetica.

---

## 6. Component Library

### 6.1 Stat Card

```
┌──────────────────────────┐
│ LABEL                    │  ← Inter Medium, 10px, #8A9BAB, UPPERCASE
│                          │
│ 223.456                  │  ← Aktiv Grotesk Bold, 28px, #E8EDF2
│                          │
│ ±0.042s                  │  ← JetBrains Mono, 12px, #4A5A6A
└──────────────────────────┘
   ↑ Accent bar (3px, data-fast)
   ↑ Surface: #0B1017
   ↑ Border: none (solo accent bar)
```

**Variant**:
- `card--metric`: accent bar = data-*
- `card--stat`: senza accent bar, sfondo #0B1017
- `card--inset`: sfondo #182230, per dati secondari

**Non fare**: card con bordo completo, ombra, glassmorphism, gradienti.

### 6.2 Data Table

```
┌─────────┬──────────┬──────────┬──────────┐
│ SECTOR  │ S1       │ S2       │ S3       │  ← Inter 10px UPPERCASE
├─────────┼──────────┼──────────┼──────────┤     border-bottom: 1px #1A2A3A
│ 223.456 │ 74.123   │ 75.234   │ 74.099   │  ← JetBrains Mono 12px
│ 224.001 │ 74.201   │ 75.300   │ 74.500   │
└─────────┴──────────┴──────────┴──────────┘
```

**Regole**:
- Header: Inter SemiBold 10px UPPERCASE, colore #4A5A6A
- Body: JetBrains Mono Regular 12px
- Bordo header: 1px solid #1A2A3A
- Bordo righe: 1px solid #0B1017 (quasi invisibile)
- Hover row: sfondo #111A24
- Larghezza colonne: determinata dal contenuto, non fissa

**Non fare**: Zebratura, bordi spessi, header con bg gradiente, icone nelle header.

### 6.3 Filter Bar

```
┌──────────────────────────────────────────────┐
│ MACCHINA    PISTA    MESCOLA    [CARICA]     │  ← Inter 10px UPPERCASE
│ [Ferrari ▾] [Spa ▾]  [Soft ▾]   [⟳]        │
└──────────────────────────────────────────────┘
```

- Sfondo: #0B1017 (stesso delle card)
- Bordo: 1px solid #1A2A3A
- Label: Inter Medium 10px UPPERCASE #4A5A6A
- Select: JetBrains Mono 12px, sfondo #182230, bordo #2A3A4A
- Padding interno: 12px

**Non fare**: Sfondo glass, bordo glow, icone grandi, separatori verticali.

### 6.4 Button System

```
[Primary]   [Secondary]   [Danger]
```

| Variant | Sfondo | Bordo | Testo | Hover |
|---|---|---|---|---|
| `btn--primary` | #0088FF | nessuno | #05080C | #00A0FF |
| `btn--primary:disabled` | #1A2A3A | nessuno | #4A5A6A | — |
| `btn--secondary` | #111A24 | 1px #2A3A4A | #E8EDF2 | bg #182230 |
| `btn--danger` | #FF4466 | nessuno | #05080C | #FF6688 |
| `btn--ghost` | trasparente | nessuno | #8A9BAB | bg #111A24 |

- Altezza: 32px (2rem)
- Padding orizzontale: 12px-16px
- Font: Inter SemiBold 12px
- Border-radius: 4px
- Transizione: background-color 0.1s

**Non fare**: Bottoni con gradienti, ombre, icone enormi, border-radius giganti.

### 6.5 Navigation (Sidebar)

```
┌──────────────────┐
│ ⚡ LMU LarpTimes │  ← Aktiv Grotesk Bold, bg #030507
├──────────────────┤
│ ◎ Profilo        │
│ ▣ Archivio       │  ← Inter Medium 13px
│ ◉ Strategia      │
│ ◆ Setup          │  ← active state: bordo sinistro 2px #0088FF
│ ▤ Lap Compare    │
│ ★ Optimal Lap    │
├──────────────────┤
│ ▷ Race Director  │
│ ⚙ Pit Practice   │
└──────────────────┘
```

- Larghezza: 200px
- Sfondo: #05080C (più scuro del main)
- Bordo destro: 1px solid #111A24
- Item padding: 8px 12px
- Active: bordo sinistro 2px #0088FF, bg #0B1017
- Hover: bg #0B1017
- Icone: 14px, stroke 1.5

**Non fare**: Sidebar glass, gradienti, icone colorate, badge non richiesti, avatar utente.

### 6.6 Chart Wrapper

```
┌────────────────────────────────────┐
│ LAP TIME EVOLUTION         [Legend]│  ← Panel header
│                                    │
│            ╱╲                       │
│     ╱╲   ╱  ╲                      │
│  ╱╲  ╲ ╱    ╲╱                     │
│ ╱  ╲ ╲╱                           │
│╱    ╲                             │
│                                    │
└────────────────────────────────────┘
```

- Sfondo: #0B1017
- Bordo: 1px solid #1A2A3A
- Header: padding 8px 12px, Inter SemiBold 10px UPPERCASE
- Chart padding: 12px
- Altezza fissa: 300px-400px

**Non fare**: Chart wrapper con ombra, angoli arrotondati grandi, header con bg separato, gradienti.

### 6.7 Alert / Toast

```
╔══════════════════════════════════╗
║  ⚠ Fuel low — pit in 3 laps    ║  ← 4px left border data-amber
╚══════════════════════════════════╝
╔══════════════════════════════════╗
║  ✕ PIT NOW — tyres critical     ║  ← 4px left border data-slow
╚══════════════════════════════════╝
```

- Sfondo: #111A24
- Bordo sinistro: 4px solid (data color)
- Font: Inter SemiBold 12px
- Padding: 8px 12px
- Durata: auto-dismiss 4s (error 6s)
- Massimo 3 toast visibili

**Non fare**: Toast glass, icone animate, gradienti, ombre grandi.

### 6.8 Badge

```
[HYPERCAR]  [FAST]  [PIT]  [WET]
```

Tutti: Inter SemiBold 9px UPPERCASE, padding 2px 6px, border-radius 2px.

| Variant | Sfondo | Testo |
|---|---|---|
| Hypercar (badge--hypercar) | rgba(0,136,255,0.15) | #0088FF |
| LMP2 (badge--lmp2) | rgba(0,229,160,0.15) | #00E5A0 |
| GT3 (badge--gt3) | rgba(255,68,102,0.15) | #FF4466 |
| Fast (badge--fast) | rgba(0,229,160,0.15) | #00E5A0 |
| Slow (badge--slow) | rgba(255,68,102,0.15) | #FF4466 |
| Pit (badge--pit) | rgba(255,144,0,0.15) | #FF9000 |
| Wet (badge--wet) | rgba(0,136,255,0.15) | #0088FF |

---

## 7. Data Visualization

### 7.1 Speed Trace Chart

```
Speed (km/h)
300 ┤        ╱╲
250 ┤   ╱╱╲╲╱  ╲╱╲
200 ┤  ╱          ╲╱╲
150 ┤ ╱              ╲
100 ┤╱                 ╲╱
   └────────────────────────▶ Distance (%)
   0%        50%       100%
     Lap A ─── Lap B ───
```

- X: distance % (0-100)
- Y: speed km/h (scala auto)
- Lap A: #8860FF (purple)
- Lap B: #00C8FF (cyan)
- Area highlight: fill 10% opacity between curves, verde dove Lap A è più veloce, rosso dove Lap B è più veloce
- Grid: #1A2A3A dotted lines
- Tooltip: JetBrains Mono 11px, sfondo #0B1017 95%, bordo #1A2A3A

### 7.2 Micro-Sector Delta Chart

Barre affiancate per ogni micro-settore:
- Optimal: #00E5A0 (verde/metrica)
- Best lap actual: #0088FF (blu/selezione)
- Delta indicator: text label "+0.042" in #FF4466 se lento

**Mai**: stacked bar (nasconde la comparazione), 3D, gradienti.

### 7.3 Stint Timeline / Race Director

- Stint bars: orizzontali, colorate per compound (vedi badge compound colors)
- Pit events: marker verticali #FF9000
- Weather: banda superiore con sfumatura (blue→gray per pioggia)
- Lap time scatter: punti per stint, linea di regressione opzionale

---

## 8. Motion & Interaction

### Philosophy
La motion in un tool di telemetry serve a:
1. **Orientare** — dove sono, cosa è cambiato
2. **Segnalare** — nuovo dato, aggiornamento
3. **Mai** — decorare, intrattenere, "impressionare"

### Timing

| Azione | Durata | Easing | Quando |
|---|---|---|---|
| Page transition | 150ms | ease-out | Navigazione tab |
| Data update | 100ms | ease-out | Valore che cambia |
| Tooltip appear | 80ms | step-start | Istantaneo per dati |
| Toast appear | 200ms | ease-out | Notifica evento |
| Toast dismiss | 300ms | ease-in | Auto-hide |
| Hover card | 100ms | ease-out | Card highlight |
| Modal overlay | 150ms | ease-out | Dialoghi |

### Micro-interactions

1. **Data flash**: Quando un valore telemetrico cambia, il testo fa un flash 100ms del colore del dato (es. delta migliora → flash verde) poi torna al colore stabile. Questo permette al pilota di percepire il cambiamento in visione periferica.

2. **Pit countdown**: L'overlay "Pit in X" pulsa lievemente (opacità 0.8↔1.0) quando X ≤ 3, diventa fisso quando X = 0.

3. **Status dot**: Ogni sistema (fuel, tyres, weather) ha un dot 6px nella sidebar che cambia colore senza animazione. Verde = ok, ambra = warning, rosso = critico. Il colore cambia istantaneamente — nessun fade.

**Non fare**: Loading spinner, skeleton screen animati, parallasse, particle effects, progress bar con gradiente.

---

## 9. Voice & Tone

### Il Race Engineer parla così:

| Situazione | Tono | Esempio |
|---|---|---|
| Critico | Imperativo, secco | *"Box this lap. Fuel critical."* |
| Warning | Informativo, breve | *"Pit in 3 laps. Tyres approaching cliff."* |
| Info | Descrittivo, preciso | *"GT3 traffic ahead. Losing 1.5 seconds per lap."* |
| Performance | Incoraggiante, metrico | *"Personal best. 223.456. Sector 2 was your strongest."* |
| Sistema | Neutro, funzionale | *"Qualifying session. Hotlap mode active."* |

**Regole**:
- **MAI** dire "great job", "amazing", "incredible" — non siamo un coach motivazionale
- **MAI** usare emoticon nella UI web (già rimosse)
- Preferire metriche a giudizi: "tyre wear 8%/lap" non "tyres wearing fast"
- Usare lessico motorsport: "box" non "pit", "stint" non "run", "cliff" non "limit"
- Frasi brevi. Punto. Due frasi brevi. Non un paragrafo.

### Brand Copy Examples

| Scritto male (AI slop) | Scritto bene (Race Engineer) |
|---|---|
| "Welcome to LMU LarpTimes! We're excited to help you improve your racing experience!" | "Race engineer online." |
| "Oops! Something went wrong. Please try again later." | "Strategy refresh failed. Check connection." |
| "Congratulations! You've completed 100 laps!" | "100 laps recorded. Data set complete." |
| "Your tyres are about to reach the end of their lifespan, so we recommend pitting soon!" | "Pit in 2 laps. Tyres at cliff." |
| "It looks like it might rain soon, so you should consider switching to wet tyres!" | "Rain in 5 minutes. Prepare for wets." |

---

## 10. UI Patterns to Avoid

### ❌ AI Slop Pattern Checklist

- [ ] **Glassmorphism** — nessun background blur, nessun frost effect
- [ ] **Purple-blue gradient hero** — non siamo un SaaS generico
- [ ] **Inter-only typography** — Aktiv Grotesk è il nostro display font
- [ ] **Symmetrical card grid** — le card non devono essere tutte uguali
- [ ] **Rounded everything** — radius massimo 4px su contenitori dati
- [ ] **Soft drop shadows** — se serve ombra, che sia netta e definita
- [ ] **Animated illustrations** — niente Lottie, niente SVG animati decorativi
- [ ] **Loading skeletons** — placeholder text è meglio di skeleton shimmer
- [ ] **"Empty state" illustrations** — dati assenti = testo, non disegnini
- [ ] **Confetti / celebration effects** — niente festeggiamenti per un PB
- [ ] **Avatar / profile pictures** — non è un social network
- [ ] **Notification bell / badges** — il race engineer PARLA, non notifica
- [ ] **"AI-powered" badge** — non dichiarare mai AI nella UI
- [ ] **Theme toggle (light/dark)** — solo dark mode, è un tool da corsa
- [ ] **Onboarding tour** — tooltip one-shot, non wizard
- [ ] **Drag-and-drop con animazione** — drag secco, senza ghost
- [ ] **Animated chart intros** — i dati appaiono, non volano dentro
- [ ] **Gradient text /霓虹 glow** — testo bianco su sfondo scuro, basta

---

## Appendice: Current CSS Variables — Gap Analysis

Rispetto al design system qui definito, le variabili CSS attuali nell'app hanno i seguenti gap:

| Attuale | Dovrebbe | Perché |
|---|---|---|
| `--bg-app: #050709` | `--bg-app: #05080C` | Leggermente più caldo, meno "puro nero" |
| `--bg-sidebar: rgba(...)` | `--bg-sidebar: #030507` | Solido, non trasparente |
| `--surface-glass: rgba(...)` | ELIMINARE | Glass non serve |
| `--accent-blue: #00a1ff` | `--data-blue: #0088FF` | Meno saturo, più professionale |
| `--accent-green: #2ea043` | `--data-fast: #00E5A0` | Verde teal-ish, non "ok" |
| `--accent-red: #ff4d4d` | `--data-slow: #FF4466` | Rosso più caldo |
| `--font-display: Rajdhani` | `--font-display: Aktiv Grotesk` | Rajdhani è troppo "game-y" |
| `--font-body: Inter` | OK | Inter per UI system è ok |
| `--radius: 4px` | OK | Ma solo per bottoni/badge |
| `--space-md: 1rem` | OK | Griglia 8px è standard |

---

*Documento v1.0 — Da revisionare prima dell'implementazione*
