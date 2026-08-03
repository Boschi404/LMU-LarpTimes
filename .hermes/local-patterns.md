# Local patterns — LMU LarpTimes (project-local, auto-loaded)

## Audit MESM 2026-08-03 — lezioni strutturali

### L1: Test auth che inquinano il DB reale
`auth/db.py::_users_db_path()` punta a `paths.data_path("lmu_pit_strategist.db")`
— i test che chiamano `init_auth_db()` + `register_email()` scrivono nel DB VERO.
Primo run pytest: verde. Secondo run: `UNIQUE constraint failed: users.email`
(4+ test rotti, sembrano regressioni ma sono stati).
**Fix (applicato):** `LMU_AUTH_DB_PATH` env override in `_users_db_path()` +
`tests/conftest.py` fixture autouse function-scoped (DB auth temp per test).
**Regola:** ogni test che tocca auth DEVE girare con DB auth isolato.

### L2: Auth enforcement e revoca sessione
Endpoints di mutazione (delete/restore/seed/owner/overlay-settings POST) ora
richiedono `require_user`. `verify_token` verifica che il token sia l'active
session in DB → logout revoca immediatamente. L'app.js usa wrapper fetch con
Bearer + redirect 401 → /login. `scripts/smoke_auth_check.py` verifica il
flusso completo (register→login→azioni→logout→revoca).

### L3: Commenti non chiusi in JS = regressioni silenziose
Il bug più grave del run: `/* ─── Toast Notifications` senza `*/` in app.js
aveva inghiottito la definizione di `showToast` → 12 chiamate ReferenceError
sui percorsi di errore. `node --check` NON lo rileva (sintatticamente valido
come commento). **Verifica:** `grep -c "function showToast"` dopo ogni merge.
