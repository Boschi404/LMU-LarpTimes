# T6 — Audit Sicurezza API Backend

**Data:** 2026-08-01  
**File analizzato:** `web/server.py` (1499 righe) + dipendenze  
**Versione:** LMU Pit Strategist v1.0.0  
**Stack:** FastAPI + SQLite (WAL) + Jinja2 + PyJWT (HS256) + bcrypt

---

## Riepilogo

| Severità | Conteggio | Descrizione |
|----------|-----------|-------------|
| 🔴 CRITICAL | 1 | F-string in query SQL — potenziale SQL injection |
| 🟠 HIGH | 3 | Password minima 4 caratteri, nessun rate-limit su login, token 30gg senza revoca |
| 🟡 MEDIUM | 4 | CORS assente, error leakage, DuckDB f-string injection, in-memory rate limiter senza cleanup |
| 🟢 LOW | 3 | XSS via parametri URL in template, import validazione parziale, no HSTS |
| ℹ️ INFO | 2 | Rate limit 200 req/min, CSP configurato |

---

## 1. CORS Configuration

### Severità: 🟡 MEDIUM

**Stato:** Nessun middleware CORS configurato. Il server usa solo `SecurityHeadersMiddleware` personalizzato.

```python
# web/server.py:166
app.add_middleware(SecurityHeadersMiddleware)
# Nessun CORSMiddleware importato o configurato
```

**Impatto:** FastAPI senza CORS applica la policy same-origin di default (il browser blocca richieste cross-origin). Per un'app locale questo è più sicuro, ma:
- L'overlay Qt (PySide6) fa richieste HTTP al server: se l'overlay carica contenuti da un'origine diversa, le richieste verranno bloccate.
- Se in futuro si espone la porta su rete (es. tunnel), è necessario un CORS restrittivo.

**Raccomandazione:** Se l'overlay usa richieste cross-origin da PySide6 WebView, aggiungere:

```python
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
```

**CVE Reference:** CWE-942 (Permissive Cross-domain Policy)

---

## 2. Rate Limiting

### Severità: 🟢 LOW (configurazione) + 🟡 MEDIUM (implementazione)

**Stato:** Rate limiter in-memory, 200 richieste/minuto per IP.

```python
# web/server.py:62
_RATE_LIMIT = 200  # max requests per minute per IP
```

**Analisi:**

| Aspetto | Valutazione |
|---------|-------------|
| Soglia 200 req/min | Generosa ma ragionevole per uso locale single-user. Se esposta a rete, un attaccante può fare ~3.3 req/sec senza blocchi — sufficiente per brute-force su endpoint login. |
| In-memory store | Dati persi al restart. Nessuna persistenza. Sotto DDoS, il dizionario `_rate_limit_store` cresce indefinitamente (nessuna pulizia IP inattivi). |
| IP spoofing | Facile da bypassare con header `X-Forwarded-For` non validato (anche se il server è su 127.0.0.1). |
| Endpoint auth esclusi | Il rate limiter NON esclude gli endpoint `/api/auth/*` — bene per il brute-force, ma la soglia è troppo alta. |
| Static files | Correttamente esclusi (`/static`). |

**Raccomandazioni:**
1. Aggiungere rate limit specifico per `/api/auth/login`: **5 req/min per IP** (protezione brute-force).
2. Implementare pulizia periodica degli IP inattivi nel `_rate_limit_store`.
3. Valutare `slowapi` o `fastapi-limiter` per produzione.
4. Impostare `_RATE_LIMIT = 60` per endpoint generali se esposto a rete.

**CVE Reference:** CWE-307 (Improper Restriction of Excessive Authentication Attempts), CWE-770 (Allocation of Resources Without Limits or Throttling)

---

## 3. Input Validation

### Severità: 🟢 LOW / 🟡 MEDIUM (import)

**Analisi per endpoint:**

| Endpoint | Validazione | Issue |
|----------|-------------|-------|
| `POST /api/auth/register` | ✅ Email format check (`"@" not in email`), password ≥ 4. | ❌ Password minima 4 caratteri (vedi sezione JWT/Auth) |
| `POST /api/auth/login` | ✅ Email non vuota. | ❌ Nessuna protezione brute-force |
| `GET /api/laps` | ✅ Parametri query string opzionali, nessun sanitizer. | 🟢 I valori sono usati solo per filtrare in-memory, non in query SQL |
| `GET /api/strategy` | ✅ Type hints: `int`, `float`, `Optional[str]` con default. | 🟢 FastAPI valida automaticamente i tipi |
| `GET /api/profile` | ✅ `car: str`, `track: str` (required), `compound: Optional[str]` | 🟢 OK |
| `GET /api/race/timeline` | ⚠️ `session_id: str` — nessuna validazione formato UUID. | 🟡 Se passato a `int()` potrebbe causare eccezione |
| `POST /api/laps/import` | ✅ Struttura validata ricorsivamente da `_validate_import_payload()`. Limiti: 50MB payload, max 5 sessioni, 5000 laps/sessione, 30 stint/sessione. | 🟢 Buona validazione strutturale. ❌ I valori dei campi lap (es. `compound_front`) non sono validati contro valori ammessi — possono contenere stringhe arbitrarie. |
| `POST /api/overlay/settings` | ✅ Solo il campo `in_game_only` viene letto e castato a `bool`. | 🟢 OK |
| `GET /api/setup` | ✅ `car: str`, `track: str` required. | 🟢 OK |

**Raccomandazioni:**
- Validare `session_id` nei parametri query come intero o UUID.
- Nell'import, validare i campi `compound_front`/`compound_rear` contro una whitelist di mescole valide (Soft, Medium, Hard, Inter, Wet).
- Validare `weather_state` contro enum (DRY, WET, DRIZZLE, ecc.).

**CVE Reference:** CWE-20 (Improper Input Validation)

---

## 4. SQL Injection

### Severità: 🔴 CRITICAL (1 instance) + 🟡 MEDIUM (2 instances)

### 4.1 — F-string in `insert_lap()` (CRITICAL)

**File:** `database/__init__.py`, riga 448

```python
columns = ", ".join(fields)       # fields derivati da field_map, validati contro schema tabella
placeholders = ", ".join(["?"] * len(fields))
cursor.execute(f"INSERT INTO laps ({columns}) VALUES ({placeholders})", values)
```

**Analisi:** I `fields` sono costruiti da `field_map` che mappa solo colonne esistenti nella tabella (verifica via `PRAGMA table_info`). Il rischio è **basso** perché:
- I nomi colonna provengono da un dizionario hardcoded (`field_map`).
- Vengono filtrati contro `existing_cols` (da PRAGMA).
- I valori vanno con parametri posizionali (`?`).

Tuttavia, l'uso di f-string per costruire SQL è una **cattiva pratica** e potrebbe diventare vulnerabile se `field_map` venisse esteso con input dinamico.

### 4.2 — F-string in `export_sessions()` (MEDIUM)

**File:** `database/__init__.py`, righe 820, 834, 850

```python
cursor.execute(
    f"SELECT {', '.join(SHAREABLE_SESSION_COLUMNS)} FROM sessions{where_sql} ORDER BY id",
    tuple(where_args),
)
```

**Analisi:**
- `SHAREABLE_SESSION_COLUMNS` è una lista hardcoded (righe 754-757) → **sicuro**.
- `where_sql` è costruito da `where_clauses` che aggiungono solo `car = ?` e `track = ?` con parametri posizionali → **sicuro**.
- Stesso pattern alle righe 834 e 850 per stint e lap columns → **sicuro**.

### 4.3 — F-string in DuckDBR2Sync (MEDIUM)

**File:** `database/cloud.py`, righe 365-370

```python
con.execute(f"""
    SET s3_endpoint = '{self.endpoint}';
    SET s3_access_key_id = '{self.access_key}';
    SET s3_secret_access_key = '{self.secret_key}';
    SET s3_region = 'auto';
""")
```

**Analisi:** I valori provengono dalla configurazione (`.env` o costruttore), quindi non da input utente diretto. Tuttavia, se un attaccante riuscisse a controllare il file `.env`, potrebbe iniettare SQL via `access_key` o `endpoint`.

**Raccomandazioni:**
1. **Sostituire la f-string in `insert_lap()`** con una query costruita dinamicamente usando placeholder per i nomi colonna (es. validazione whitelist).
2. Nel caso DuckDB, usare parametri prepared statement se supportati, o almeno sanitizzare l'input.
3. Adottare una policy "zero f-string in SQL" per tutto il codebase.

**CVE Reference:** CWE-89 (SQL Injection), CVE-2024-... (pattern f-string SQL)

---

## 5. XSS nei Template Jinja2

### Severità: 🟢 LOW

**Stato:** I template usano Jinja2 con auto-escaping abilitato (default FastAPI).

**Analisi:**
- `index.html` (2153 righe): Template statico, nessun `{{ variabile }}` dinamica non escaped.
- `login.html` (193 righe): Idem.
- **Nessun uso di `|safe` filter** (confermato da grep).
- **Nessun `autoescape false`** nei template.
- **Nessun `innerHTML`** nel JavaScript del template — tutti gli aggiornamenti DOM usano `textContent` (implicito via template literals che popolano `textContent` di elementi `<span>`, `<div>`).

**Rischi residui:**
- I valori passati al template via `{{ request }}` nel contesto Jinja2 sono auto-escaped per default.
- Le API restituiscono JSON, il frontend JavaScript costruisce HTML dinamicamente. Se un dato (es. `car`, `track`, `display_name`) contenesse `<script>`, verrebbe renderizzato come textContent → **sicuro**.

**Raccomandazione:** Continuare a evitare `|safe` e `innerHTML`. Valutare Content Security Policy più restrittiva (rimuovere `'unsafe-inline'` da `script-src` usando nonce/hash).

**CVE Reference:** CWE-79 (Cross-Site Scripting)

---

## 6. File Upload / Path Traversal

### Severità: 🟢 LOW

**Stato:** Nessun endpoint di file upload nell'API. L'import/export opera interamente su payload JSON in-memory.

**Analisi:**
- `POST /api/laps/import`: riceve JSON body, validato strutturalmente. Nessun file scritto a disco.
- `GET /api/laps/export`: restituisce JSON generato dal database.
- `POST /api/overlay/settings`: scrive su `paths.data_path("overlay", "overlay_config.json")` — percorso fisso, non controllabile dall'utente.
- Il server serve file statici da `STATIC_DIR` con `StaticFiles` — FastAPI impedisce directory traversal di default.

**Raccomandazione:** Nessuna azione necessaria. Se in futuro si aggiungono upload di file (es. telemetria), validare estensione, MIME type, e usare `werkzeug.utils.secure_filename`.

**CVE Reference:** CWE-22 (Path Traversal), CWE-434 (Unrestricted File Upload)

---

## 7. JWT Handling

### Severità: 🟠 HIGH

**Configurazione:**

```python
# auth/crypto.py
DEFAULT_JWT_EXPIRATION = 30 * 24 * 60 * 60  # 30 giorni
jwt.encode(payload, _get_jwt_secret(), algorithm="HS256")
```

**Analisi:**

| Aspetto | Stato | Rischio |
|---------|-------|---------|
| Algoritmo | HS256 (simmetrico) | 🟢 OK per app locale |
| Secret generation | `secrets.token_urlsafe(64)` | 🟢 Eccellente |
| Secret storage | File `auth_secret.txt` in data dir | 🟡 File system locale, permessi non verificati |
| Expiration | 30 giorni | 🔴 Troppo lungo per un token senza revoca |
| Refresh token | ❌ Non implementato | 🔴 Il token è l'unica credenziale per 30gg |
| Token revocation | ❌ Non implementata | 🔴 Se un token viene compromesso, non c'è modo di invalidarlo |
| `active_session` table | Singleton row (`id=1`) | 🟡 Single-user by design, ma se multi-user in futuro servirà tabella sessioni multipla |

**Raccomandazioni:**
1. Ridurre expiration a **1 ora**, implementare refresh token (7-30 giorni).
2. Aggiungere endpoint `POST /api/auth/refresh` per rinnovare il token.
3. Implementare blacklist token su logout (anche in-memory).
4. Verificare permessi file `auth_secret.txt` (chmod 600 su Linux, ACL su Windows).

**CVE Reference:** CWE-613 (Insufficient Session Expiration), CWE-384 (Session Fixation)

---

## 8. Error Information Leakage

### Severità: 🟡 MEDIUM

**Analisi:** Diversi endpoint restituiscono messaggi di errore dettagliati che potrebbero rivelare informazioni interne.

| Endpoint | Errore esposto | Rischio |
|----------|----------------|---------|
| `POST /api/auth/register` | `str(e)` da `ValueError` (es. "user with that email already exists") | 🟡 User enumeration — un attaccante può capire se un'email è registrata |
| `POST /api/auth/login` | "Email o password errati" | 🟢 OK — messaggio generico (non dice se l'email esiste o la password è sbagliata) |
| `POST /api/laps/import` | `f"invalid JSON: {e}"` — espone dettagli `JSONDecodeError` | 🟡 Rivela dettagli del parser JSON |
| `GET /api/strategy` | `f"Dati insufficienti: servono almeno 5 giri validi, trovati {len}"` | 🟢 OK — messaggio funzionale |
| `GET /api/race/timeline` | `f"No laps found for session {session_id}"` | 🟢 OK |
| `POST /api/seed` | Messaggi descrittivi | 🟢 OK (endpoint di sviluppo) |

**Raccomandazioni:**
1. In produzione, non esporre `str(e)` raw. Usare messaggi generici e loggare l'errore completo lato server.
2. Per `/api/auth/register`, restituire sempre "Registrazione completata" anche se l'email esiste (o inviare email di verifica).
3. Per `/api/laps/import`, restituire "Invalid JSON format" senza dettagli del parser.

**CVE Reference:** CWE-209 (Information Exposure Through an Error Message), CWE-204 (User Enumeration)

---

## 9. Authentication & Password Policy

### Severità: 🟠 HIGH

```python
# web/server.py:223
if len(password) < 4:
    return JSONResponse(status_code=400,
        content={"error": "Password troppo corta (min 4 caratteri)"})
```

**Analisi:**
- Password minima: 4 caratteri — **estremamente debole**. OWASP raccomanda minimo 8, NIST raccomanda 8+.
- Nessun requisito di complessità (no uppercase, no numeri, no caratteri speciali).
- Nessun account lockout dopo tentativi falliti.
- Nessun rate limit specifico per endpoint login (solo il rate limit globale 200/min).
- Nessun MFA/2FA.
- Hash bcrypt con work factor 12 — 🟢 buona scelta.

**Raccomandazioni:**
1. Alzare il minimo password a **8 caratteri**.
2. Implementare rate limiting specifico per `/api/auth/login`: **5 tentativi/min per IP**.
3. Implementare account lockout temporaneo dopo 10 tentativi falliti.
4. Validare complessità password: almeno 1 maiuscola, 1 numero, 1 carattere speciale.
5. Considerare `zxcvbn` per stimare la forza della password lato client.

**CVE Reference:** CWE-521 (Weak Password Requirements), CWE-307 (Improper Restriction of Excessive Authentication Attempts)

---

## 10. Security Headers

### Severità: ℹ️ INFO

**Stato:** Headers configurati correttamente nel `SecurityHeadersMiddleware`:

```python
response.headers["X-Content-Type-Options"] = "nosniff"           # ✅
response.headers["X-Frame-Options"] = "DENY"                     # ✅
response.headers["X-XSS-Protection"] = "1; mode=block"           # ✅ (deprecato ma utile per browser legacy)
response.headers["Content-Security-Policy"] = "..."              # ✅ (buona policy, ma 'unsafe-inline')
response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"  # ✅
response.headers["Permissions-Policy"] = "interest-cohort=()"    # ✅
```

**Carenze:**
- ❌ **Manca `Strict-Transport-Security` (HSTS)** — anche se locale, se mai esposto via HTTPS serve. Per ora è un'app solo HTTP.
- ⚠️ CSP include `'unsafe-inline'` per script e style. Necessario per Chart.js inline, ma riduce la protezione XSS.
- ❌ **Manca `X-Content-Security-Policy`** (header legacy, opzionale).
- ⚠️ Manca `Cross-Origin-Embedder-Policy` e `Cross-Origin-Opener-Policy` (utili per isolamento).

**Raccomandazioni:**
1. Valutare l'uso di nonce/hash CSP per eliminare `'unsafe-inline'`.
2. Aggiungere HSTS se si prevede HTTPS.
3. Aggiungere `Cross-Origin-Resource-Policy: same-origin`.

**CVE Reference:** CWE-693 (Protection Mechanism Failure)

---

## 11. Dipendenze e Supply Chain

### Severità: ℹ️ INFO

```python
# requirements.txt (dedotto da run_app.py)
numpy, fastapi, uvicorn, jinja2, psutil, PySide6, scipy, bcrypt, PyJWT, httpx
```

**Analisi rapida:**
- `PyJWT` — nessuna CVE critica nota recente.
- `bcrypt` — libreria matura, work factor 12 adeguato.
- `fastapi` — costantemente aggiornato.
- `jinja2` — auto-escaping di default.
- `PySide6` — solo per overlay GUI.

**Raccomandazione:** Eseguire `pip-audit` o `safety check` periodicamente.

---

## Raccomandazioni Prioritarie

### 🔴 Immediato (entro 1 sprint)
1. **Sostituire f-string SQL in `insert_lap()`** con costruzione sicura.
2. **Alzare password minima a 8 caratteri** in `/api/auth/register`.
3. **Aggiungere rate limit 5/min su `/api/auth/login`**.

### 🟠 Breve termine (2-3 sprint)
4. **Ridurre JWT expiration a 1 ora**, implementare refresh token.
5. **Implementare blacklist token su logout**.
6. **Rivedere error leakage** — niente `str(e)` raw.
7. **Aggiungere account lockout** dopo 10 tentativi falliti.

### 🟡 Medio termine
8. Configurare **CORS restrittivo** per dominio overlay.
9. Pulire **rate limit store** da IP inattivi.
10. Aggiungere **HSTS** se si prevede HTTPS.
11. **Content validation** nei campi import (compound, weather_state).

### 🟢 Basso priorità
12. CSP senza `'unsafe-inline'` (con nonce).
13. `pip-audit` nel CI/CD.
14. Validazione `session_id` come intero.

---

*Report generato da audit automatico del codice — nessuna modifica è stata apportata ai file analizzati.*
