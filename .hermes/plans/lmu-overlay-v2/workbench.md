# Workbench — Overlay v2 (MESM round 1)

## Goal
Restyle 6+ pannelli overlay + fix logici (bandiera blu, posizione di classe, practice tempo).

## Bar
1. pytest 0 failure ✅ (345 passed) · 2. smoke test offscreen rendering ✅ · 3. py_compile pulito ✅ · 4. commit+push

## Stato
- [x] T1 source.py best sectors
- [x] T2 RaceStatus posizione classe + tempo
- [x] T3 Fuel barra 0-100% (verde/ambar/rosso)
- [x] T4 Gap 2 sezioni barre direzionali (fix colori battaglia: BACK rosso, FRONT ambar)
- [x] T5 Wear 4 gomme disegnate (temp: azzurro/verde/rosso; usura colorata)
- [x] T6 Flag blu (6=BLUE) + LED box (fix FCY ambra mancante)
- [x] T7 Meteo icone + colori
- [x] T8 Settori 3 sezioni fucsia/verde/giallo
- [x] T9 test (345 passati) + push

## Verifiche pixel (round 1 critic)
- GAP: BACK barra sinistra→destra ✅, FRONT destra→sinistra ✅, battaglia BACK=rosso/FRONT=ambar ✅
- FLAG: 6→BLUE ✅, FCY→ambra ✅ (era verde, fixato)
- FUEL: barra verde 36% ✅ (era bianca, fixato)
- WEAR: FL azzurro (fredda), FR verde, RL rosso (surriscaldata) ✅
- SECTORS: best→fucsia, +0.3s→verde ✅

## Costo accumulato
- Esecuzione diretta (0 subagenti) · ~$0.2 stimato
