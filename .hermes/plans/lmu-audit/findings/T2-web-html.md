# T2 – Audit UI/UX Frontend Web

**Data**: 2026-08-01  
**File analizzati**: `web/templates/index.html` (2153 righe), `web/templates/login.html` (193 righe)  
**Metodo**: Analisi statica del markup HTML, del CSS inline e del file JavaScript collegato (`web/static/app.js`).

---

## Riepilogo

| Severity | Count |
|----------|-------|
| 🔴 CRITICAL | 2 |
| 🟠 HIGH | 7 |
| 🟡 MEDIUM | 10 |
| 🟢 LOW | 6 |

---

## 🔴 CRITICAL

### C1 – 14 variabili CSS non definite usate in `app.js` e inline HTML

**File**: `index.html` (inline), `app.js` (template literal HTML)  
**Descrizione**: Il JavaScript genera dinamicamente HTML che referenzia variabili CSS mai dichiarate nel `:root`. Il browser le risolve a `initial`/`inherit`, producendo colori errati, spaziature assenti e stili rotti.

**Variabili NON definite ma usate**:
| Variabile | Usata in | Effetto del fallback |
|---|---|---|
| `--status-invalid` | app.js (righe 395, 678, 700, 753, 772) | Colore di stato non visibile |
| `--status-warn` | app.js (678, 753) | Warning color assente |
| `--status-valid` | app.js (772) | Valid color assente |
| `--border-subtle` | app.js | Bordi mancanti |
| `--ink-muted` | app.js (678) | Testo muted invisibile |
| `--ink-primary` | app.js | Testo primary stile errato |
| `--ink-secondary` | app.js (753) | Testo secondary stile errato |
| `--surface-elevated` | app.js | Sfondo errato |
| `--radius-sm` | app.js | Border-radius assente |
| `--space-xs`, `--space-sm`, `--space-md`, `--space-xl` | app.js | Spaziature collassate |
| `--bg-1` | index.html:L1570 (inline) | Sfondo select trasparente |

**Impatto**: Diversi componenti UI (badge stato strategia, raccomandazioni setup, colori comparazione lap) appaiono senza colori o con stili errati. L'elemento `<select>` su L1570 ha `background: var(--bg-1)` → `transparent`.

---

### C2 – Zero attributi ARIA e zero ruoli WAI-ARIA in entrambi i file

**File**: `index.html`, `login.html`  
**Descrizione**: L'intera applicazione è completamente priva di attributi `role` e `aria-*`.  
**Conteggio**: `grep -c 'role=|aria-' index.html` → **0**. `login.html` → **0**.

**Elementi critici senza ARIA**:
- **Navigazione**: `<nav>` senza `aria-label`; i bottoni `.nav-btn` non hanno `aria-current="page"` quando attivi
- **Tabs login**: `role="tablist"`, `role="tab"`, `aria-selected` assenti
- **Toast notifications**: nessun `role="alert"` o `aria-live="polite"` → screen reader non annuncia i toast
- **Offline banner**: nessun `role="alert"`
- **Messaggi errore**: `display:none` usato per nasconderli → completamente invisibili agli screen reader (dovrebbero usare `aria-live` region)
- **Tabelle**: nessun `<caption>`, nessun `aria-describedby`
- **Icone SVG**: nessun `aria-hidden="true"` per icone decorative

**Impatto**: L'applicazione è inutilizzabile da utenti con screen reader. Violazione WCAG 2.1 AA (criteri 1.3.1, 4.1.2).

---

## 🟠 HIGH

### H1 – 89 stili inline nell'HTML body di `index.html`

**File**: `index.html`  
**Descrizione**: 89 occorrenze dell'attributo `style="..."` nel body HTML, con una media di ~1 ogni 10 righe di markup. Molti duplicano pattern già definiti nel CSS.

**Pattern ricorrenti**:
- `style="display:none"` → 18 occorrenze (dovrebbe essere classe `.hidden` o `.d-none`)
- `style="width:XXpx"` → 8+ occorrenze (dovrebbero usare classi di sizing)
- `style="color:var(--red)"` → pattern ripetuto
- `style="margin-top:2rem"` → 3 occorrenze

**Impatto**: Manutenzione difficile, incoerenza visiva, CSS specificity impossibile da gestire, performance peggiore (inline styles non sono cacheable).

### H2 – Classe `.card` inesistente usata nell'HTML

**File**: `index.html`  
**Righe**: L1384 e L1390: `class="card"`  
**Descrizione**: Due `<div>` usano `class="card"` ma non esiste alcuna regola CSS `.card` nel file. Gli elementi sopravvivono solo grazie agli stili inline che compensano.  
**Impatto**: Se qualcuno rimuovesse gli inline style pensando che `.card` sia definita nel CSS, il layout collasserebbe.

### H3 – Contrasto colore insufficiente su `--text-muted` (#35404A)

**File**: `index.html`  
**Descrizione**: Il colore `--text-muted: #35404A` è usato per label, testo secondario e metadati su sfondo `--bg-app: #0A0C0E` e `--bg-surface: #0F1317`.

**Calcolo contrasto**:
- `#35404A` su `#0F1317` → rapporto ~2.5:1 (WCAG AA richiede ≥4.5:1 per testo normale, ≥3:1 per large text)
- `#35404A` su `#0A0C0E` → rapporto ~2.1:1

**Elementi affetti**: `.stat-label`, `.filter-group label`, `.slider-group label`, `.stat-sub` (tutti a font-size 0.7rem–0.75rem, quindi "normal text").

**Impatto**: Il testo è illeggibile per utenti ipovedenti. Violazione WCAG 2.1 AA criterio 1.4.3.

### H4 – Login: input non wrappati in `<form>`, label senza attributo `for`

**File**: `login.html`  
**Descrizione**: Gli input email/password non sono contenuti in un elemento `<form>`. Le label non hanno attributo `for` che le associ esplicitamente agli input.

**Conseguenze**:
- Il browser non offre validazione nativa (es. `type="email"` non controlla il formato)
- L'autocomplete del browser potrebbe non funzionare correttamente
- Screen reader non associano label → input
- L'invio con tasto Enter richiede JavaScript manuale (L189-190)

### H5 – Nessun focus indicator personalizzato per bottoni e link

**File**: `index.html`, `login.html`  
**Descrizione**: Mentre gli input e select hanno `:focus` con bordo arancione (L257-261), i bottoni `.nav-btn`, `.btn`, e le tab di login NON hanno uno stile `:focus-visible` definito.  
**Impatto**: Navigazione da tastiera impossibile da seguire visivamente. Violazione WCAG 2.1 AA criterio 2.4.7.

### H6 – Assenza totale di skip-link "Vai al contenuto principale"

**File**: `index.html`  
**Descrizione**: Nessun link nascosto per saltare la sidebar e andare direttamente al `<main>`.  
**Impatto**: Utenti keyboard-only devono tabbare attraverso 8 pulsanti nav + sidebar footer prima di raggiungere il contenuto.

### H7 – `login.html` non condivide il design system (colori hardcodati)

**File**: `login.html`  
**Descrizione**: Tutti i colori sono hex codificati a mano (`#0A0C0E`, `#FF6B00`, `#5A6A7A`, etc.) invece di usare le variabili CSS `:root` di `index.html`.  
**Impatto**: Se il tema viene modificato in `index.html`, il login rimane con i vecchi colori. Duplicazione di 20+ valori colore.

---

## 🟡 MEDIUM

### M1 – Media query responsive insufficienti

**File**: `index.html`  
**Descrizione**: Solo 3 breakpoint definiti:

| Breakpoint | Cosa gestisce |
|---|---|
| `768px` | Collasso sidebar → colonna |
| `800px` | Weather grid 1 colonna |
| `1200px` | Chart layout 1 colonna |

**Problemi**:
- Nessuna gestione per schermi <480px (mobile piccolo)
- Nessun font-size responsive (no `clamp()`, solo unità fisse `rem`/`px`)
- Tabelle con `white-space: nowrap` su `td` → overflow orizzontale su mobile
- Nessun hamburger menu; la sidebar a 768px diventa una barra orizzontale ma occupa spazio prezioso

### M2 – Tabelle senza `scope` su `<th>` e senza `<caption>`

**File**: `index.html`  
**Descrizione**: Tutte le 7+ tabelle non hanno `<caption>` e gli header `<th>` non hanno attributo `scope="col"`.  
**Impatto**: Screen reader non possono descrivere il contesto della tabella. Violazione WCAG 2.1 AA criterio 1.3.1.

### M3 – Toast container fuori dal flusso normale del DOM

**File**: `index.html` L2152  
**Descrizione**: `<div id="toast-container"></div>` è posizionato DOPO la chiusura di `<main>` e DOPO il tag `<script>`, ma PRIMA di `</body>`. È fuori dal flusso logico del documento e non ha `aria-live`.  
**Nota**: `position: fixed` lo rende visivamente corretto, ma semanticamente è fuori posto.

### M4 – `login.html`: messaggi di errore con `display:none` invece di `visibility` o `aria-live`

**File**: `login.html`  
**Righe**: L58-59 (`.error-msg`, `.info-msg` con `display: none`)  
**Descrizione**: Gli errori di login/registrazione sono nascosti con `display:none`, che li rimuove completamente dall'accessibility tree. Quando JavaScript imposta `display:block`, uno screen reader potrebbe non notare il cambiamento.  
**Fix suggerito**: Usare `visibility:hidden` con `height:0` oppure un `aria-live` region.

### M5 – Icone SVG inline duplicate in ogni `<button>` nav

**File**: `index.html`  
**Righe**: L1323–1360  
**Descrizione**: Ogni pulsante della sidebar contiene un SVG inline completo (16-20 righe di markup SVG ciascuno). 8 bottoni × ~18 righe = ~144 righe di markup SVG ripetitivo.  
**Impatto**: Aumenta dimensione HTML, nessun riuso. Si potrebbe usare un sistema di icone (`<use href="#icon-...">`) o sprite SVG.

### M6 – `login.html`: tab non hanno `aria-selected` e `aria-controls`

**File**: `login.html` L72-73  
**Descrizione**: Il componente tab Accedi/Registrati non segue il pattern ARIA "Tabs". Manca `role="tablist"` sul contenitore, `role="tab"` sui bottoni, `aria-selected`, `tabindex`, `aria-controls`.  
**Impatto**: Screen reader non capiscono che sono tab.

### M7 – `login.html`: nessun `minlength` sull'input password

**File**: `login.html` L100  
**Descrizione**: L'input password di registrazione dice "min 4 caratteri" nel placeholder ma non ha l'attributo HTML `minlength="4"`.  
**Impatto**: Nessuna validazione lato client prima dell'invio.

### M8 – `app.js` usa `innerHTML` per costruire tabelle (XSS potenziale)

**File**: `app.js` (template literal ovunque)  
**Descrizione**: Il JS costruisce HTML dinamicamente con concatenazione di stringhe e template literal. Sebbene i dati provengano dall'API backend (quindi probabilmente trusted), il pattern è fragile.  
**Esempio**: `'<td class="num-col">' + l.lap_number + '</td>'` — se `l.lap_number` contenesse HTML, sarebbe iniettato.

### M9 – `login.html`: overflow non gestito su card a 90vw

**File**: `login.html` L24  
**Descrizione**: `.card` ha `max-width: 90vw` ma nessun `overflow` o scroll. Su schermi molto piccoli (<300px), la card potrebbe eccedere. Problema minore data la rarità.

### M10 – Tabelle senza header `sticky` (usabilità)

**File**: `index.html`  
**Descrizione**: Le tabelle lunghe (es. archivio lap con scroll orizzontale) non hanno `position: sticky` su `<thead>`. Su dati abbondanti, l'utente perde il contesto delle colonne durante lo scroll.

---

## 🟢 LOW

### L1 – `::-webkit-scrollbar` senza fallback Firefox

**File**: `index.html` L65-68  
**Descrizione**: Scrollbar customizzati solo per WebKit. Firefox usa `scrollbar-width` e `scrollbar-color`.

### L2 – `@keyframes fadeIn` potrebbe causare content flash

**File**: `index.html` L183-186  
**Descrizione**: L'animazione `fadeIn` parte da `opacity:0`. Se JavaScript è lento, l'utente vede una pagina vuota per un attimo (FOUT). Basso impatto su questa app.

### L3 – `login.html` usa `font-family` hardcodate invece di variabili

**File**: `login.html`  
**Descrizione**: `'Inter'`, `'Rajdhani'`, `'JetBrains Mono'` sono ripetuti come stringhe letterali invece di usare le variabili `--font-body`, `--font-display`, `--font-mono`.

### L4 – `index.html` carica font da Google Fonts senza `font-display: swap`

**File**: `index.html` L12  
**Descrizione**: Il link Google Fonts non include `&display=swap`, il che significa che il browser usa `font-display: block` (default Google Fonts), bloccando il rendering del testo finché i font non sono caricati.

### L5 – Favicon inline via data URI (non funziona su tutti i browser)

**File**: `index.html` L9  
**Descrizione**: Il favicon è un data URI SVG. Non supportato da Safari vecchi e alcuni browser mobili. Funziona sui moderni, ma un `.ico` o `.svg` separato sarebbe più robusto.

### L6 – Select `#strat-mode` ha stili che duplicano il CSS globale

**File**: `index.html` L1570  
**Descrizione**: `<select id="strat-mode" style="width:100px;...;background:var(--bg-1);...">` duplica inutilmente gli stili già definiti in `.filter-bar select` (L244-255), e come notato in C1, `--bg-1` non esiste.

---

## Riepilogo per priorità di intervento

| Ordine | ID | Cosa fare |
|--------|-----|-----------|
| 1 | C1 | Aggiungere le 14 variabili CSS mancanti al `:root` |
| 2 | C2 | Aggiungere ARIA landmarks, ruoli e attributi essenziali |
| 3 | H3 | Correggere `--text-muted` per contrasto ≥4.5:1 |
| 4 | H1 | Estrarre classi CSS per gli 89 stili inline (almeno `.hidden`, sizing utils) |
| 5 | H7 | Allineare `login.html` al design system con variabili CSS |
| 6 | H4 | Wrapper `<form>` + attributi `for` in `login.html` |
| 7 | H5 | Aggiungere `:focus-visible` su tutti gli elementi interattivi |
| 8 | H2 | Rimuovere `class="card"` o definire la classe |
| 9 | M1–M10 | Miglioramenti responsive e semantici |
| 10 | L1–L6 | Pulizie minori |
