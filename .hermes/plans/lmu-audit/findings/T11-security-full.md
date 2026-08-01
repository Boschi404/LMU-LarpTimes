# 🔒 Audit di Sicurezza Completo — LMU Pit Strategist

**Data:** 2026-08-01  
**Ambito:** Progetto locale (`localhost:8000`) con sync cloud opzionale (Turso)  
**Metodologia:** Analisi statica del codice (NO modifica, NO lettura .env/auth_secret.txt)  
**File analizzati:** 76 `.py` + `.gitignore` + `requirements.txt` + `auth_secret.txt` (metadati)

---

## 📊 Riepilogo Rischi

| Priorità | Conteggio | Descrizione |
|----------|-----------|-------------|
| 🔴 **CRITICO** | 3 | Richiede intervento immediato |
| 🟠 **ALTO** | 3 | Azione entro il prossimo sprint |
| 🟡 **MEDIO** | 4 | Mitigare quando possibile |
| 🟢 **BASSO** | 3 | Monitorare, accettabile per localhost |

**Overall Score:** 6.2/10 — Sicurezza base accettabile per localhost, con criticità note.

---

## 🔴 CRITICO (3)

### C1 — `auth_secret.txt` world-readable (0644)

**File:** `auth_secret.txt`  
**Permessi:** `-rw-r--r--` (644)  
**Contenuto:** 86 byte — JWT signing secret generato con `secrets.token_urlsafe(64)`  
**Rischio:** Qualsiasi processo/utente sulla macchina può leggere il segreto e forgiare JWT validi per impersonare qualsiasi utente. Su Windows multi-utente questo è particolarmente pericoloso.

**Codice rilevante:**
```
auth/crypto.py:39-43  → genera secret e lo salva senza restringere i permessi
auth/crypto.py:95-96  → usa il secret per firmare/verificare JWT (HS256)
```

**Fix raccomandato:**  
- Su Windows: spostare in `%APPDATA%` con ACL ristrette, o crittografare con DPAPI  
- Su POSIX: `os.chmod(secret_path, 0o600)` dopo scrittura

---

### C2 — Google OAuth placeholder: nessuna validazione token

**File:** `auth/manager.py:69-90`  
**Rischio:** La funzione `login_google()` accetta `google_id`, `email`, `display_name` come parametri diretti **senza mai verificare il Google ID token** contro le API di Google. Un attaccante può inviare un `google_id` arbitrario e impersonare qualsiasi utente.

```python
# auth/manager.py:69-90 — NESSUNA chiamata a Google per validare!
def login_google(google_id: str, email: Optional[str], display_name: str) -> User:
    existing = get_user_by_google_id(google_id)
    if existing:
        set_current_user(existing.id)
        ...
    # Nuovo utente Google: creato senza verificare il token!
    user = _create_user_google(
        email=email, display_name=display_name,
        auth_provider="google", google_id=google_id,
    )
```

**Fix raccomandato:**  
Validare il token con `google-auth` library: `idinfo = google.oauth2.id_token.verify_oauth2_token(token, requests.Request(), CLIENT_ID)` prima di accettare il `google_id`.

---

### C3 — Rate limiting locale condiviso per auth e API generiche

**File:** `web/server.py:60-90`  
**Rischio:** Stessa soglia (200 req/min) per endpoint di login/register e per API generiche. Su localhost l'IP è sempre `127.0.0.1`, quindi il rate limit è facilmente saturabile. **Bruteforce password possibile**: con password min 4 caratteri, 200 tentativi/min consentono ~288.000 tentativi/giorno.

```python
# web/server.py:85
if len(_rate_limit_store[client_ip]) >= _RATE_LIMIT:
    return JSONResponse(status_code=429, ...)
```

**Fix raccomandato:**  
- Rate limit separato per `/api/auth/login`: 5 tentativi/min  
- Dopo N fallimenti: bloccare l'account per 15 min (lockout)  
- Aumentare `_RATE_LIMIT` auth a 10 req/min, API a 500 req/min  

---

## 🟠 ALTO (3)

### A1 — Password minima 4 caratteri, nessun requisito di complessità

**File:** `web/server.py:223`  
**Rischio:** Password `"1234"` o `"aaaa"` sono considerate valide. Nessun controllo su: lunghezza maggiore, maiuscole, numeri, caratteri speciali, password comuni.

```python
# web/server.py:223
if len(password) < 4:
    return JSONResponse(status_code=400, content={"error": "Password troppo corta (min 4 caratteri)"})
```

**Bcrypt work factor 12** è eccellente (~250ms/hash, auth/crypto.py:53), ma viene annullato da password banali.

**Fix raccomandato:** Minimo 8 caratteri. Validazione complessità (almeno 1 maiuscola, 1 numero). Opzionale: dizionario password comuni (zxcvbn).

---

### A2 — JWT expiry di 30 giorni senza refresh/revoca

**File:** `auth/crypto.py:22`  
**Rischio:** Se un token viene compromesso (es. log di richieste, localStorage leak, XSS), l'attaccante ha 30 giorni di accesso senza possibilità di revoca. Non esiste una token blacklist.

```python
# auth/crypto.py:22
DEFAULT_JWT_EXPIRATION = 30 * 24 * 60 * 60  # 30 giorni
```

**Fix raccomandato:**  
- Ridurre a 1-24 ore per uso locale  
- Aggiungere refresh token con rotazione  
- Implementare token blacklist in SQLite per revoca immediata  

---

### A3 — JWT e password hash nel database SQLite world-readable

**File:** `lmu_pit_strategist.db` (stessa directory del progetto)  
**Rischio:** Il database contiene `password_hash` (bcrypt) e `jwt_token` in chiaro nella tabella `active_session`. Se il file `.db` è accessibile, un attaccante legge i token attivi e ruba la sessione. I bcrypt hash sono resistenti a cracking offline, ma il JWT in chiaro è utilizzabile immediatamente.

```sql
-- auth/db.py:96-105
CREATE TABLE IF NOT EXISTS active_session (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    user_id TEXT,
    jwt_token TEXT,         -- token JWT in chiaro!
    expires_at TEXT,
    created_at TEXT NOT NULL,
    ...
)
```

**Fix raccomandato:**  
- Spostare il DB in una directory dati protetta (es. `%APPDATA%/LMU-Pit-Strategist/`)  
- Non persistire il JWT in chiaro nel DB — validare solo con signature verification  
- Crittografare il DB con SQLCipher o estensione SEE  

---

## 🟡 MEDIO (4)

### M1 — CSP: `'unsafe-inline'` in script-src e style-src

**File:** `web/server.py:98-106`  
**Rischio:** `'unsafe-inline'` permette l'esecuzione di script inline, annullando buona parte della protezione XSS offerta dal CSP. Necessario per Chart.js e template Jinja2, ma lascia una superficie d'attacco.

```
Content-Security-Policy: script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net ...
                        style-src 'self' 'unsafe-inline' ...
```

**Fix raccomandato:**  
- Usare `'nonce-{random}'` o `'hash-{sha256}'` per script legittimi  
- Chart.js può essere caricato con `'strict-dynamic'` se servito con nonce  

---

### M2 — Nessun account lockout dopo tentativi falliti

**File:** `auth/db.py:174-190` (authenticate_user)  
**Rischio:** Nessun meccanismo che blocca l'account dopo N tentativi falliti. Combinato con password da 4 caratteri e rate limit 200/min, bruteforce è fattibile.

```python
# auth/db.py:174-190 — authenticate_user non traccia tentativi falliti
def authenticate_user(email: str, password: str) -> Optional[User]:
    ...
    if not verify_password(password, row["password_hash"] or ""):
        return None  # nessun log, nessun contatore, nessun lockout
```

**Fix raccomandato:**  
- Aggiungere colonna `failed_attempts` e `locked_until` alla tabella `users`  
- Dopo 5 tentativi falliti: lock per 15 minuti  

---

### M3 — Nessuna protezione contro timing attack su login

**File:** `auth/db.py:174-190`  
**Rischio:** `authenticate_user` restituisce `None` immediatamente se l'email non esiste, mentre se esiste fa bcrypt check (250ms). Un attaccante può enumerare utenti misurando il tempo di risposta.

```python
# auth/db.py:184-189
row = cur.fetchone()
if not row:
    return None           # risposta veloce → email non esiste
if not verify_password(password, row["password_hash"] or ""):
    return None           # risposta lenta (~250ms) → email esiste, password sbagliata
```

**Fix raccomandato:**  
- Eseguire `verify_password` con un hash fittizio anche quando l'utente non esiste (constant-time dummy check)  

---

### M4 — Nessun HTTPS, token JWT in chiaro su rete locale

**File:** `run_app.py:17` → `SERVER_HOST = "127.0.0.1"`  
**Rischio:** Tutto il traffico è HTTP in chiaro. Su localhost il rischio è basso, MA se l'app viene esposta accidentalmente (es. tunneling ngrok, rete locale condivisa) il JWT viaggia in chiaro.

```python
# run_app.py:17
SERVER_HOST = "127.0.0.1"  # corretto: localhost only
```

**Self-audit rileva tunneling** (`security/self_audit.py:159-166`): controlla `NGROK_AUTHTOKEN` e simili — BUONO.

**Fix raccomandato:**  
- Aggiungere opzione `--ssl` per HTTPS self-signed in futuro  
- Documentare chiaramente: "Questa app non è progettata per esposizione su rete"  

---

## 🟢 BASSO (3)

### B1 — CDN esterne caricate senza Subresource Integrity (SRI)

**File:** `web/server.py:100` → `script-src ... https://cdn.jsdelivr.net`  
**Rischio:** Chart.js da CDN non ha hash SRI. Se jsdelivr viene compromesso, l'attaccante inietta JS malevolo. Basso per app locale.

---

### B2 — `check_same_thread=False` su SQLite

**File:** `auth/db.py:72`, `database/__init__.py:18`  
**Rischio:** Necessario per FastAPI (connessioni da thread diversi), ma disabilita il controllo di thread safety di SQLite. Basso rischio per app single-user locale.

---

### B3 — Nessun header `Strict-Transport-Security` (HSTS)

**File:** `web/server.py:95-108` (SecurityHeadersMiddleware)  
**Rischio:** HSTS non applicabile a localhost (nessun HTTPS). Accettabile.

---

## 📋 Dettaglio tecnico per area

### 1. Auth Flow

| Componente | Valutazione | Dettaglio |
|-----------|-------------|-----------|
| Password hashing | ✅ | bcrypt work factor 12, ~250ms/hash |
| Password validation | 🔴 | Min 4 caratteri, nessuna complessità |
| JWT signing | ✅ | HS256, secret 86 byte da `secrets.token_urlsafe(64)` |
| JWT expiry | 🟠 | 30 giorni, troppo lungo, nessuna revoca |
| JWT storage | 🔴 | Token in chiaro in SQLite, world-readable |
| Account lockout | 🔴 | Assente |
| Google OAuth | 🔴 | Placeholder, nessuna validazione token |
| Timing attack | 🟡 | Enumerazione utenti possibile |

### 2. Secrets in Codice

| Pattern cercato | Esito |
|----------------|-------|
| `password = "..."` hardcoded | ✅ Nessuno |
| `api_key = "..."` hardcoded | ✅ Nessuno |
| `secret = "..."` hardcoded | ✅ Nessuno (generato a runtime) |
| `token = "..."` hardcoded | ✅ Nessuno |
| `TURSO_TOKEN` | ✅ Via env var |
| `JWT_SECRET` | ✅ Via env var o file |
| `auth_secret.txt` | 🔴 World-readable (644), nella root progetto |

### 3. CSP Headers

| Direttiva | Valore | Valutazione |
|-----------|--------|-------------|
| `default-src` | `'self'` | ✅ |
| `script-src` | `'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com` | 🟡 unsafe-inline |
| `style-src` | `'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net` | 🟡 unsafe-inline |
| `frame-ancestors` | `'none'` | ✅ |
| `X-Content-Type-Options` | `nosniff` | ✅ |
| `X-Frame-Options` | `DENY` | ✅ |
| `X-XSS-Protection` | `1; mode=block` | ✅ |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | ✅ |
| `Permissions-Policy` | `interest-cohort=()` | ✅ |

### 4. Rate Limiting

| Aspetto | Valutazione |
|---------|-------------|
| Implementazione | ✅ In-memory, 200 req/min |
| Persistenza | 🔴 Reset al riavvio |
| Endpoint auth | 🔴 Stessa soglia API generiche |
| Bruteforce protection | 🔴 Assente (no lockout) |
| Rate limit per IP | 🟡 Tutti `127.0.0.1` su localhost |
| Skip static | ✅ |

### 5. HTTPS

| Aspetto | Valutazione |
|---------|-------------|
| HTTPS | ⚪ Non presente (localhost) |
| Host binding | ✅ 127.0.0.1 (non 0.0.0.0) |
| HSTS | ⚪ N/A per localhost |
| Self-audit tunneling | ✅ Controlla NGROK_AUTHTOKEN etc. |

### 6. File Permissions

| File | Permessi | Rischio |
|------|----------|---------|
| `auth_secret.txt` | 644 (rw-r--r--) | 🔴 World-readable |
| `.env` | Non presente | ✅ |
| `.gitignore` | Include `.env` e `auth_secret.txt` | ✅ |
| `lmu_pit_strategist.db` | Default (644) | 🟠 Contiene JWT e hash |
| `*.py` | Default | ✅ |
| `web/static/*` | 644 | ✅ |

### 7. .env / Auth Secret Exposure

| File | In .gitignore? | Stato |
|------|---------------|-------|
| `.env` | ✅ (riga 108) | Non presente — cloud sync non configurato |
| `auth_secret.txt` | ✅ (riga 115) | Presente (86 byte), world-readable |
| `.env*` pattern | ✅ in .gitignore | Copre `.env.production` etc. |

---

## 🔧 Raccomandazioni Prioritarie

### Immediate (Sprint corrente)
1. **Restringere permessi `auth_secret.txt`**: `chmod 600` o ACL equivalenti su Windows
2. **Aumentare password min length a 8+** e aggiungere validazione complessità
3. **Implementare rate limiting differenziato** per `/api/auth/login` (5 req/min) con lockout

### Breve termine (Prossimo sprint)
4. **Validare Google ID token** con `google-auth` library
5. **Ridurre JWT expiry a 24h** e aggiungere refresh token
6. **Spostare DB in directory dati protetta** (`%APPDATA%`)
7. **Aggiungere timing-attack mitigation**: dummy bcrypt per utenti inesistenti

### Medio termine
8. **Rimuovere `'unsafe-inline'` da CSP** usando nonce o hash
9. **Aggiungere SRI hash** per CDN esterne
10. **Implementare token blacklist** per revoca JWT
11. **Crittografare il DB SQLite** (SQLCipher) per dati sensibili

---

## 📝 Note

- **Self-audit esistente**: Il modulo `security/self_audit.py` esegue check all'avvio (silenzioso) su gitignore, permessi .env, token Turso, host binding, JWT secret, network exposure. Buona pratica.
- **Test coverage**: `tests/test_security.py` (401 righe) copre input validation, SQL injection, CSP, rate limiting, data leak, path traversal, CORS. Buona copertura.
- **No modifica codice effettuata** durante questo audit (sola analisi statica).
- **.env e auth_secret.txt** non sono stati letti nel contenuto — solo metadati (dimensione, permessi, posizione).

---

*Report generato da audit statico automatico — verificare con penetration test manuale per conferma.*
