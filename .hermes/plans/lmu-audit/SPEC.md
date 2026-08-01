# LMU LarpTimes — Audit Specification

## Problem
Audit completo dell'applicazione LMU LarpTimes/Pit Strategist per identificare:
bug, problemi UI/UX, gap di funzionalità, problemi di performance, vulnerabilità di sicurezza,
e opportunità di miglioramento.

## Scope
Tutti i moduli:
- `web/` — Server FastAPI, template Jinja2, JavaScript frontend
- `overlay/` — Overlay in-game PySide6 (full + modular)
- `telemetry/` — Shared memory LMU/rFactor 2
- `analysis/` — Strategist, race engineer, tyre manager, qualifying, practice, weather
- `auth/` — Autenticazione JWT/bcrypt
- `database/` — SQLite, cloud sync (Turso)
- `security/` — Self-audit
- `vendor/` — Shared memory readers

## Aree di Audit

1. **UI/UX Web** — index.html (2153 righe), login.html (193 righe), app.js (2288 righe)
2. **UI/UX Overlay** — app.py (1055 righe), app_new.py (2042 righe)
3. **API Backend** — server.py (1499 righe), tutti gli endpoint REST
4. **Qualità Codice** — Type hints, docstrings, error handling, DRY
5. **Performance** — Query DB, API response time, memory usage
6. **Sicurezza** — Auth, input validation, rate limiting, secrets
7. **Test Coverage** — 26 file di test, copertura reale
8. **Features Mancanti** — Gap vs工具 simili per simracing

## Acceptance Criteria
- Report dettagliato con bugs trovati e severity
- Lista feature da aggiungere con priorità
- Problemi UI/UX con screenshot mentali
- Metriche quantitative (LOC, test count, API count)
- Raccomandazioni actionable con priorità

## Non-Goals
- Non modificare codice (solo audit)
- Non eseguire l'app (solo analisi statica)
- Non toccare file di configurazione o .env
