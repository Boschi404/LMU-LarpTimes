# Changelog

## [0.1.0-beta] — 2026-08-01

### Added
- Overlay in-game con PySide6 (modalità full 3×3 grid + modulare 10 finestrelle)
- Web dashboard con 43 endpoint REST API (FastAPI + Jinja2 + Chart.js)
- Race Engineer TTS con voice cues (edge-tts + winsound)
- Pit Strategy optimizer basato su Dynamic Programming
- Multi-class detection (Hypercar / LMP2 / GT3) con mappatura 50+ auto
- Tyre degradation modelling (Huber loss, cliff detection)
- Weather forecasting (linear extrapolation + stint forecast)
- Qualifying analysis (outlap/hotlap/inlap classification)
- Practice advisor (fuel range, tyre age, compound coverage)
- Lap anomaly detection (Z-score su pace + fuel)
- Micro-sector analysis (9 sub-sectors per giro)
- Race Director timeline builder
- Cloud sync via Turso/libSQL
- Auth system (email+password bcrypt, Google OAuth placeholder, JWT)
- Security self-audit all'avvio
- Bundle export/import (.lmubundle con gzip)
- 325 test automatici

### Fixed (da audit v0.1.0-beta)
- 9 bug critici (crash, XSS, NameError, variabili undefined)
- 7+ indici database mancanti aggiunti
- Rate limiting differenziato auth/API
- Password policy rafforzata (8+ caratteri)
- JWT expiry ridotto (30gg → 24h)
- Timing-attack mitigation su login
- 14 variabili CSS mancanti aggiunte
- Contrasto accessibilità corretto (WCAG AA)
- ARIA base aggiunta (navigation, alert, tablist)
- 60+ eccezioni ingoiate sostituite con logging
- Type hints e docstring aggiunti in moduli core
- Debug print rimossi
- Performance: filtri SQL invece di Python, PRAGMA cache, busy_timeout
