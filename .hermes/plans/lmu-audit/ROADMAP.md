# LMU LarpTimes — Audit Roadmap

## Phase 1: Scansione e Metriche
- Conteggio LOC per modulo
- Mappatura dipendenze
- Conteggio API endpoint

## Phase 2: Audit Parallelo (8 stream)
- UI Web + JS audit
- UI Overlay audit
- API Backend audit
- Code Quality audit
- Performance audit
- Security audit
- Test Coverage audit
- Feature Gap analysis

## Phase 3: Global Re-Check
- Verifica consistenza tra moduli
- Controllo firme e naming
- Dead code detection

## Phase 4: Report Finale
- Compilazione risultati
- Prioritizzazione fixes
- Raccomandazioni

## Risks
- Analisi statica limitata (no runtime)
- Dipendenze esterne non verificate
- Shared memory logic non testabile senza LMU

## Validation
- Ogni subagent produce file .md in `.hermes/plans/lmu-audit/findings/`
- Assembly task compila il report finale
