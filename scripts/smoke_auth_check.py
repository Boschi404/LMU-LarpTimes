import json
import re
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8765"

def call(method, path, body=None, token=None, full=False):
    req = urllib.request.Request(BASE + path, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(req, data) as r:
            raw = r.read().decode()
            return r.status, (raw if full else raw[:300])
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        return e.code, (raw if full else raw[:300])

results = []
results.append(("1. GET /api/laps no token (atteso 200)", call("GET", "/api/laps")))
results.append(("2. POST /api/seed no token (atteso 401)", call("POST", "/api/seed")))
results.append(("3. POST /api/laps/1/delete no token (atteso 401)", call("POST", "/api/laps/1/delete")))
results.append(("4. register password corta (atteso 400)", call("POST", "/api/auth/register", {"email": "smoke.test@example.com", "password": "short", "display_name": "Smoke"})))
s, b = call("POST", "/api/auth/register", {"email": "smoke.test@example.com", "password": "Secret12", "display_name": "Smoke"})
results.append(("5. register valido (atteso 200/201)", (s, b)))
s, b = call("POST", "/api/auth/login", {"email": "smoke.test@example.com", "password": "Secret12"}, full=True)
token = ""
try:
    token = json.loads(b).get("token", "")
except Exception:
    pass
results.append(("6. login (atteso 200 + token)", (s, b[:120] if s == 200 else b)))
results.append(("7. GET /api/auth/me con token (atteso 200)", call("GET", "/api/auth/me", token=token)))
results.append(("8. POST /api/seed CON token (atteso 200)", call("POST", "/api/seed", token=token)))
results.append(("9. POST logout (atteso 200)", call("POST", "/api/auth/logout", token=token)))
results.append(("10. POST /api/seed token revocato (atteso 401)", call("POST", "/api/seed", token=token)))
results.append(("11. GET /api/auth/me senza token (atteso 401)", call("GET", "/api/auth/me")))

ok = True
for name, (s, b) in results:
    m = re.search(r"atteso (\d+)", name)
    expected = int(m.group(1)) if m else None
    mark = "✅" if (expected is None or s == expected) else "❌"
    if mark == "❌":
        ok = False
    print(f"{mark} {name} -> {s} | {b[:150]}")
print("\nRISULTATO:", "TUTTI OK" if ok else "FAILURE PRESENTI")
