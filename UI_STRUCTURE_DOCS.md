# LMU Pit Strategist — Struttura UI per shadcn

**Data**: 23 Giugno 2026  
**Scopo**: Documento di struttura HTML per Claude + preset shadcn

---

## 📋 Componenti principali

### 1. **Header/Navigation**
```
<header>
  - Logo con gradient
  - 3 Nav buttons: Profilo | Archivio Giri | Strategia
  - Status dot (pulsante)
```

### 2. **Page: PROFILO (Session Profile)**

#### Sezione Filtri
```
- Input: Auto (text)
- Input: Pista (text)
- Input: Mescola (text, optional)
- Button: Aggiorna
```

#### Warning Banner
```
- Conditional display (warning alert)
- Testo dinamico
```

#### Stats Grid (4 cards, responsive)
```
1. Giri validi (numero)
2. Passo medio (tempo formato MM:SS.sss, con std dev)
3. Consumo medio (L/giro, con std dev)
4. Cliff degrado (numero giro, con beta_2)
```

#### Two-Column Layout
```
LEFT: Chart (Canvas.js)
  - Linea: Modello Huber
  - Scatter: Giri reali
  - Assi X/Y con labels

RIGHT: Model Detail Table
  - Tempo base
  - Effetto carburante (α)
  - Degrado lineare (β₁)
  - Degrado post-cliff (β₂)
  - Giro cliff
```

---

### 3. **Page: ARCHIVIO (Lap Archive)**

#### Sezione Filtri
```
- Input: Auto (text)
- Input: Pista (text)
- Input: Mescola (text)
- Select: Mostra eliminati (Solo attivi | Tutti)
- Button: Aggiorna
```

#### Tabella Giri (sortable headers)
```
Colonne:
  Giro | Tempo | S1 | S2 | S3 | Carb. | Età G. | Mescola | T.Pista | Stato | Anomalia | Azioni

Dati per riga:
  - lap_number
  - lap_time (formatted)
  - sector_1, sector_2, sector_3
  - fuel_start_l
  - tyre_age_laps
  - compound_front
  - track_temp
  - is_valid_lap (✓/✗ badge)
  - anomaly_flag (⚠️ o —)
  - Azioni: Elimina (se attivo) | Ripristina (se eliminato)
```

---

### 4. **Page: STRATEGIA (Strategy Calculator)**

#### Sezione Parametri
```
- Input: Auto (text)
- Input: Pista (text)
- Input: Giri rimanenti (number, default 40)
- Input: Carburante attuale L (number, default 100)
- Input: Capacità serbatoio L (number, default 100)
- Input: Max soste (number, default 3)
- Button: Calcola
```

#### Error Banner
```
- Conditional display (error alert)
- Testo dinamico
```

#### Risultati (Grid di Strategy Cards)
```
Per ogni strategia:
  - Numero soste (grande, bold)
  - Label "Sost{a|e}"
  - Box ai giri: [comma-separated lap numbers o "(no-stop)"]
  - Tempo totale: ⏱ XXmYYs
  
  SE OTTIMALE:
    - Bordo verde/evidenziato
    - Badge: ★ OTTIMALE
```

#### Dettaglio Strategia Ottimale
```
- Consumo medio: X.XX L/giro
- Pit loss: YY.Y s
- Decisioni giro per giro: Sequenza di 🔴 (pit) e ● (no-pit)
```

---

## 🎨 Componenti UI da restyling con shadcn

| Componente | shadcn Equivalent | Note |
|-----------|------------------|------|
| **Header** | Custom nav bar | Sticky, backdrop blur |
| **Nav Buttons** | Tabs component | Active state con gradient |
| **Cards** | Card component | Border, shadow, hover effect |
| **Stat Cards** | Card + Badge | Gradient bg, pseudo-element |
| **Buttons** | Button component | Primary, danger, restore variants |
| **Inputs** | Input component | Text, number, select |
| **Filter Bar** | Form layout | Flex wrap |
| **Warning Banner** | Alert component | Warning style |
| **Badge** | Badge component | Multiple colors (valid, invalid, anomaly, pit, optimal) |
| **Table** | Table component | Sortable headers, hover state |
| **Chart** | (Chart.js wrapper) | No shadcn component |
| **Grid Layouts** | CSS Grid | Responsive auto-fill/auto-fit |

---

## 📊 Data Flow

### Profilo
```
1. User enters car + track
2. GET /api/profile?car=X&track=Y
3. Response: stats, degradation_model, degradation_curve, raw_points
4. Render: stats grid + chart + model table
```

### Archivio
```
1. Filters (optional)
2. GET /api/laps?include_deleted=X&car=Y&track=Z&compound=W
3. Response: array of lap records
4. Render: table with sorting
5. Actions: DELETE /api/laps/{id}/delete or POST /api/laps/{id}/restore
```

### Strategia
```
1. User enters params (car, track, laps, fuel, capacity, max_stops)
2. GET /api/strategy?car=X&track=Y&laps_remaining=Z&...
3. Response: result { alternatives{}, optimal{stops, pit_laps, decisions, mean_fuel_consumption, pit_loss_seconds} }
4. Render: strategy cards grid + optimal detail
```

---

## 💡 CSS Classes to Define

```
.page
.page.active
.card
.card-title
.filter-bar
.filter-group
.btn
.btn-primary
.btn-danger
.btn-restore
.stats-grid
.stat-card
.stat-label
.stat-value
.stat-sub
.warning-banner
.strat-grid
.strat-card
.strat-card.optimal
.strat-stops
.strat-label
.strat-laps
.strat-time
.badge-optimal
.chart-wrapper
.table-scroll
.badge
.badge-anomaly
.badge-valid
.badge-invalid
.badge-pit
.tooltip-wrap
.tooltip-text
.loader
.loading-row
.two-col
.status-dot
.nav-btn
.nav-btn.active
.logo
.spacer
```

---

## 📌 Note Importanti

- **Responsive**: Media query per `@media (max-width: 900px)` per two-col layout
- **Animazioni**: fadeIn page transition, pulse status dot, hover elevation
- **Fonts**: Geist (corpo), JetBrains Mono (numeri)
- **Dark Mode**: Palette basata su bg-0, bg-1, bg-2, bg-3
- **Chart.js**: Mantenere per grafici interattivi
- **JavaScript**: Vanilla JS (no framework), API calls via fetch()

