# Bewertungskriterien — was wird gemessen und warum

Pro Kriterium aus dem offiziellen UDE-Prüfungsprotokoll: was die Heuristik prüft, wie die Schwellen begründet sind, was das LLM ergänzt, und wo blinde Flecken sind.

> **Stand 2026-06-01:** Schema gegen `assets/Templates/Template Artifacts Exam Checklist Fillable.pdf` abgeglichen — alle 17 bewerteten Kriterien, Maximalpunkte und Kategorien sind 1:1 deckungsgleich (Gesamt 50 = 46 automatisiert + 4 manuell). Die Doku-Stellen zu Struktur/Tests/Code-Doku wurden auf die inzwischen **sprachunabhängige** Implementierung (Sprach-Registry) nachgezogen; DB-Schema-Erkennung und ein inhaltlicher User-Story-Fallback wurden ergänzt.

## Übersicht der Kategorien

Aus dem PDF-Protokoll "Prüfungsprotokoll (Artefakte)":

| Kategorie | Punkte |
|---|---|
| Sprintdokumentation | 7 |
| Code-Qualität | 14 |
| Implementierte Funktionalität | 21 |
| Prozessqualität | 8 (4 automatisierbar + 4 manuell) |
| **Gesamt** | **50** |

Davon sind 4 Punkte (Team-Organisation 2 + Selbstständigkeit 2) ausschließlich manuell aus der mündlichen Prüfung. Der Rest (46 Punkte) ist automatisiert bewertbar.

---

## Sprintdokumentation (max 7 Punkte)

### User Stories ordentlich erstellt (0–3)

**Was misst die Heuristik:** Anteil der `type::userstory`-Issues die:
- das Format "As a … I want … so that …" (bzw. "Als … möchte ich … so dass …") einhalten
- eine Sektion "Acceptance criteria" oder "Akzeptanzkriterien" haben
- substantielle Beschreibung (>80 Zeichen)
- ein Story-Weight gesetzt haben (Info, nicht Score-relevant)

**Welche Issues zählen ("User Stories / Issues"):** Primär die mit Label `type::userstory`. Verwendet ein Team gar kein solches Label, greift ein **inhaltlicher Fallback** (`_looks_like_user_story`): Issues, die das Story-Format treffen ODER eine Akzeptanzkriterien-Sektion haben ODER "user story"/"userstory" nennen, werden als Kandidaten gewertet. So bekommt ein Team mit sauberen, aber unlabelten Stories nicht fälschlich 0 — die PDF-Frage heißt explizit "User Stories / **Issues**".

**Schwellen:** ≥85% beider Hauptkriterien → 3 P. | ≥50% → 2 P. | ≥5 Stories vorhanden → 1 P. | sonst 0.

**Warum so:** Das PDF verlangt explizit "vollständig mit Akzeptanzkriterien, Format eingehalten". 85% als Schwelle für volle Punktzahl gibt Toleranz für 1-2 Ausnahmen, ohne dass Pauschalismus durchgeht.

**LLM ergänzt:** Bewertung der **Qualität** der Akzeptanzkriterien — sind sie testbar/messbar oder vage? Beschreibt "so that" einen echten Nutzenwert? Liefert eine Zahl 0–3 als Zweitmeinung.

**Blinde Flecken:** Heuristik prüft Format und Existenz, nicht Inhalt. Eine User Story die nur ein "✓" als Akzeptanzkriterium hat, würde formal akzeptiert. Das LLM korrigiert das.

### Verständliche Commit-Messages (0–1)

**Was misst die Heuristik:**
- Ø-Länge ohne Merge-Commits ≥ 25 Zeichen
- Anteil trivialer Messages ("fix", "update", "wip") < 15%
- Anteil sehr kurzer Messages (<8 Zeichen) < 10%

**Schwellen:** Alle drei müssen erfüllt sein für 1 Punkt.

**Warum so:** 25 Zeichen reicht für "Add user authentication" oder ähnliche aussagekräftige Messages. 15%/10% Toleranzen erlauben einzelne "fix typo"-Commits ohne Punktabzug.

**LLM ergänzt:** Sample von 20 zufälligen Commits → bewertet ob sie WAS UND WARUM beschreiben oder nur WAS. Score 0–3.

**Blinde Flecken:** Eine Heuristik kann nicht zwischen "Add user authentication" (gut) und "Update file" (länger aber unscharf) unterscheiden. Das LLM schließt diese Lücke.

### Team-Meetings dokumentiert (0–1)

**Was misst die Heuristik:**
- Wiki-Seiten mit Datums-Titel (Format DD.MM.YYYY oder Variationen) ODER Schlüsselwörtern wie "Sprint", "Meeting", "Besprechung", "Protokoll", "Retro", "Review", "Planning", "Standup".
- Davon nur jene als "substantiell" gezählt, deren Textinhalt nach Markdown-Stripping ≥150 Zeichen hat.

**Schwellen:** ≥2 substantielle Meeting-Seiten → 1 Punkt.

**Warum so:** Ein Team muss mehrere Meetings dokumentiert haben, nicht nur Sprint-0. Reine Bilder ohne Text werden nicht gezählt.

**LLM ergänzt:** Liest 3 Sample-Seiten und beurteilt: sind das echte Protokolle (Datum, Anwesende, Beschlüsse, Action Items) oder nur Stichpunkt-Notizen? Score 0–1.

**Blinde Flecken:** Heuristik erkennt "10.05.2026" als Meeting-Datum, übersieht aber Seiten mit Titel "Erstes Treffen" o.ä. Das LLM kann das nicht heilen weil die Suche nach Wiki-Seiten vorgelagert ist.

### Release mit Changelog/Release-Notes (0–1)

**Was misst die Heuristik:**
- Release-Tag in GitLab existiert
- Release-Beschreibung ≥ 200 Zeichen

**Warum so:** 200 Zeichen ist etwa eine Liste mit 3-5 stichpunktartigen Features. Darunter ist es kein ernstgemeintes Changelog.

**LLM ergänzt:** Zwei Checks:
1. Substanz der Notes (Übersicht, Features, Einschränkungen) → 0–3
2. **Vergleich mit den tatsächlichen Commit-Messages** der letzten 50 Commits → 0–3 (versprechen die Notes Features die nicht im Code sind?)

Die zwei Scores werden gemittelt.

**Blinde Flecken:** Heuristik kann nicht erkennen ob die Release-Notes inhaltlich richtig sind. LLM-Vergleich mit Commits fängt das ab.

### Sinnvolle Epics + Verlinkung (0–1)

**Was misst die Heuristik:**
- Issues mit Label `type::epic` müssen existieren
- Verlinkung zwischen Epics und User Stories: gezählt werden `#123`-Referenzen in den Bodies (in beide Richtungen)

**Schwellen:** ≥3 Epics UND ≥5 Verlinkungen → 1 Punkt.

**Warum so:** GitLab Free hat keine echten Epics — Teams müssen sich mit Labels behelfen, und die Verlinkung erfolgt durch manuelle Issue-Referenzen.

**Blinde Flecken (groß):** Wenn das Team eine andere Konvention nutzt (z.B. Task-Listen in Epic-Beschreibungen, Sub-Labels), wird das übersehen. Das PDF-Kriterium ist explizit "Epics erstellt UND User Stories mit diesen verlinkt" — bei 0/1 sollte manuell geprüft werden.

---

## Code-Qualität (max 14 Punkte)

### Code sinnvoll strukturiert (0–1)

**Was misst die Heuristik (sprachunabhängig, `analyze_code_structure`):**
- Build-Marker im Repo (`pom.xml`, `build.gradle(.kts)`, `package.json`, `go.mod`, `pyproject.toml`, `setup.py`, `Cargo.toml`)
- ODER Backend/Frontend-Split (Top-Level-Folder `backend`/`server`/`api` + `frontend`/`client`/`web`/`ui`)
- ODER eine Quell-Konvention (`src`/`cmd`/`internal`/`pkg`/`lib`/`app`)
- ODER maximale Quell-Pfadtiefe ≥ 3 Ebenen (generische Modul-/Pakettiefe über die Datei-Endungen der Sprach-Registry)

**Warum so:** Bei studentischen SEP-Projekten ist Full-Stack mit Backend/Frontend-Split der übliche Fall. Ein Build-Marker oder eine ordentliche Paket-/Pfadstruktur deutet generell auf Strukturbewusstsein hin — unabhängig von der Sprache (Java/TS/Python/Go/Kotlin).

### Code ausreichend dokumentiert (0–5)

**Was misst die Heuristik (additiv, Summe gedeckelt bei 5):**
- Top-Level-README ≥500 Zeichen und nicht die GitLab-Default-Vorlage: +1
- Sub-READMEs (z.B. in backend/frontend) ≥1000 Zeichen gesamt: +1
- ≥3 substantielle Wiki-Seiten: +1, ≥8 Seiten: +2 (gestaffelt, nicht additiv)
- OpenAPI/Swagger-Spec im Repo gefunden (Java-Annotationen ODER `openapi.{yaml,yml,json}`/`swagger.{yaml,yml,json}`): +1
- **Datenbankschema dokumentiert: +1** — `_detect_db_schema` erkennt `*.sql`, `*.prisma`, Liquibase-Changelogs, ein `migrations/`-Verzeichnis mit Inhalt, oder ORM-Entities/Models (`@Entity`, `@Table(`, Django `models.Model`, SQLAlchemy `declarative_base`). Das PDF nennt "Datenbankschemata" explizit.
- Inline-Kommentar-Anteil ≥5% **über alle erkannten Sprachen** (Comment-Marker je Sprache aus der Registry, nicht mehr nur Java): +1

**Warum so:** Gute Doku hat mehrere Quellen. Die Punkte sind so verteilt dass weder reines Wiki noch reines Code-Kommentar volle Punktzahl gibt — der Mix wird belohnt. Da 6 Signale auf max 5 gedeckelt sind, genügt es, einige davon abzudecken.

**LLM ergänzt:** Sample von bis zu 3 Quell-Dateien mit Kommentaren (sprachunabhängig über die Registry) → beurteilt ob die Kommentare WARUM (gut) oder nur WAS (redundant) erklären. Score 0–2.

**Blinde Flecken:** Wiki-Qualität wird nicht inhaltlich geprüft. Das LLM zur Meeting-Doc-Bewertung deckt zwar Meeting-Seiten ab, nicht aber andere Wiki-Seiten. DB-Schema-Erkennung ist signal-/dateibasiert (erkennt z.B. ein nur in Prosa beschriebenes Schema im Wiki nicht).

### Code sauber/ohne größere Mängel (0–1)

**Was misst die Heuristik:** Eine Liste von Negativ-Checks. Wenn auch nur einer zutrifft → 0.
- `node_modules/` im Git-Index
- Build-Artefakte (`dist/`, `target/`, `build/`, `out/`, `.gradle/`, `.idea/`)
- IDE-Configs (`.idea/`, `.vscode/`, `*.iml`)
- OS-Cruft (`.DS_Store`, `Thumbs.db`)
- Debug-/Log-Dateien (`merge-debug.txt`, `debug.log`, `*.log`)
- Binaries >5 MB
- >20 TODOs/FIXMEs im Code
- Keine Lint-Config UND keine `.editorconfig`

**Warum so:** Das sind alles klassische "wurde nicht aufgeräumt"-Indikatoren. Bei studentischen Repos kommen sie regelmäßig vor und sind ein guter Negativ-Hint.

**Blinde Flecken:** Die Heuristik gibt 0/1 — kein Halbwert. Ein Repo mit nur einer .DS_Store-Datei bekommt die gleiche Bewertung wie eins mit 100MB node_modules + 200 TODOs.

### Tests vorhanden und sinnvoll (0–7)

**Was misst die Heuristik (additiv, max 7, sprachunabhängig über die Registry):**
Aggregiert über alle Sprachen (`test_globs`/`test_markers` je Sprache): Gesamtzahl Test-Dateien, davon **substantielle** (>1 primärer Test-Marker), und Gesamtzahl Test-Methoden/-Fälle.
- ≥5 Test-Dateien insgesamt: +1
- ≥15 Test-Dateien: +1
- ≥5 substantielle Test-Dateien: +1
- ≥30 Test-Methoden/-Fälle insgesamt: +1
- ≥3 substantielle Test-Dateien: +1
- ≥10 substantielle Test-Dateien: +1
- ≥50 Methoden/-Fälle UND ≥8 substantielle Test-Dateien: +1

**Coverage-Boost:** Wenn CI Coverage reportet:
- ≥80%: +1 (capped bei max 7)
- <30%: -1 (mindestens 2)

**Warum so:** Reine Anzahl kann Stubs zählen, deshalb der Substanz-Filter: substantiell = **mehr als ein** primärer Test-Marker (erster Eintrag der Sprache: `@Test` / `def test_` / `func Test` / `it(`). Das filtert generierte 1-Test-Stubs (z.B. Angulars "should create") heraus. Coverage liefert das fehlende Substanz-Signal.

**LLM ergänzt:** Sample von bis zu 5 Test-Dateien (sprachunabhängig) → beurteilt: nur Happy Path oder auch Edge Cases / Error-Pfade? Score 0–3.

**Blinde Flecken:** Die Heuristik kennt keine Cypress/E2E-Tests die in einem separaten Repo liegen würden.

---

## Implementierte Funktionalität (max 21 Punkte)

### Release ausführbar (0–5) — ⚠ MANUELL prüfen!

**Was misst die Heuristik (additiv):**
- Release-Tag existiert: +1
- Release-Notes ≥500 Zeichen: +1
- `compose.yaml` oder `docker-compose.yml`: +1
- Backend- UND Frontend-Dockerfile: +1
- `.gitlab-ci.yml` vorhanden: +1

**Warum so/Grenzen:** Das prüft nur Bereitschaft, nicht Funktion. Ein Team mit perfekter Compose-Datei und kaputter Datenbank-Migration kriegt 5/5. **Du musst es selbst starten und durchklicken.**

Im Excel steht prominent in der Begründung: "WICHTIG - MANUELLE PRÜFUNG ZWINGEND".

### Sprint-Ziele erreicht (0–1)

**Was misst die Heuristik:**
- ≥50% aller Issues geschlossen
- UND ≥60% der `priority::must`-Issues geschlossen

**Warum so:** Die Must-Quote ist wichtiger als die Gesamt-Quote — wenn nur Could/Should-Issues offen sind, ist das okay.

**LLM ergänzt (Sonnet):** Pro Stichprobe von 4 User-Story+MR-Diff-Paaren → bewertet ob die Story sauber implementiert ist (alle Akzeptanzkriterien adressiert, kein Scope-Creep). Score 0–3.

**Blinde Flecken:** Die Heuristik prüft nur State-Transition, nicht Qualität der Implementierung. Das LLM mit Code-Verständnis (deswegen Sonnet) schließt diese Lücke — aber nur für MRs mit `Closes #N` in der Description.

### Arbeitsumfang angemessen (0/5/10/15)

**Was misst die Heuristik:**
- Anzahl Commits, LOC (Java/TS/HTML/CSS, ohne node_modules)
- Schwellen (cumulative):
  - <20 Commits & <1k LoC → 0
  - <60 Commits ODER <3k LoC → 5
  - <120 Commits ODER <6k LoC → 10
  - sonst → 15

**Warum so:** Über mehrere Sprints im SEP-Kurs sind diese Zahlen kalibriert. Bei einem 6er-Team mit 4 Sprints ist 120+ Commits und 6k+ LoC üblicherweise erreichbar.

**Blinde Flecken:** Quantität ≠ Qualität. Viele kleine Refactoring-Commits zählen genauso wie echte Features. Das LLM könnte hier sekundär helfen (gibt aber aktuell keine LLM-Bewertung für dieses Kriterium).

---

## Prozessqualität (max 8 Punkte: 4 automatisierbar + 4 manuell)

### GitLab-Nutzung (0–2)

**Was misst die Heuristik:**
- Anteil Issues mit Labels
- Anteil Issues mit Assignees
- Anteil geschlossener Issues

**Schwellen:**
- Labels ≥85% UND Assignees ≥70% UND ≥50% geschlossen: 2
- Nur Labels ≥50%: 1
- Sonst 0

### Branching-Workflow (0–1)

**Was misst die Heuristik:**
- ≥10 gemergte MRs
- UND ≥3 Branches neben main
- UND ≤15 Direkt-Pushes auf main (Commits ohne Merge-Hintergrund)

**Warum so:** Das PDF verlangt "Feature-Branches, MR". Direkte Pushes auf main sind ein Verstoß. 15 als Schwelle erlaubt initial commit + ein paar kleine Fixes.

**LLM ergänzt:** Bewertet ob ein konsistenter Git-Workflow erkennbar ist (GitFlow / GitHub Flow / Trunk-Based / Chaos). Score 0–2.

### Code-Reviews durchgeführt (0–1) — Approval-aware!

**Was misst die Heuristik:** Drei Review-Signale pro gemergtem MR:
1. Reviewer wurde gesetzt
2. Formales Approval durch jemand anderen als den Autor
3. Schriftlicher Kommentar von Reviewer

**Schwellen:**
- ≥50% Approvals durch andere ODER ≥70% irgendein Review-Signal: 1
- ≥40% irgendein Signal: 1 (mit Label "ueberwiegend ohne textuelle Kommentare")
- Sonst 0

**Warum so:** Frühe Version maß nur Kommentare und gab Teams die Approval-only-Workflows nutzen 0/1. Approvals zählen jetzt als Review-Signal — pragmatischer und fairer.

**LLM ergänzt:** Liest 5 Sample-Review-Kommentare → bewertet ob substantiell (konkrete Fragen, Verbesserungen) oder nur "LGTM". Score 0–1.

### Team-Organisation & Kommunikation (0–2) — manuell

Nicht automatisierbar. Aus der mündlichen Prüfung zu bewerten.

Hilfestellung im Excel-Sheet "Zusatzinfos":
- Commit-Verteilung pro Autor + Gini-Koeffizient. Wenn 1 Person 80% der Commits hat, ist das ein Hinweis auf ungleiche Beteiligung.

### Selbstständigkeit (0–2) — manuell

Nicht automatisierbar. Aus der mündlichen Prüfung zu bewerten.

Hilfestellung in Zusatzinfos:
- Aktivitäts-Verteilung (Last-Minute-Hacking?)
- CI-Pipeline-Status (haben sie ihre CI grün gehalten, oder ignoriert?)

---

## Sanity-Check (LLM Info)

Am Ende läuft das LLM noch einmal über alle Begründungen + Scores und prüft:
1. Widersprüche zwischen Kategorien (z.B. "gute Tests" aber CI rot)
2. Auffällige Diskrepanzen
3. Plausibilität des Gesamtscores

Score 0–2 (kein PDF-Kriterium, nur Info). Steht im Zusatzinfos-Sheet.

---

## Zusatz-Infos ohne Score

Diese laufen mit, vergeben aber keinen Score — sie helfen bei der manuellen Bewertung:

| Info | Was misst es |
|---|---|
| Commit-Verteilung | Top-Committer, Gini-Koeffizient |
| CI-Pipeline-Status | Letzte 5 Pipelines grün/rot |
| MR-Qualität | Time-to-Merge, Ø-Größe |
| Velocity | Story-Points/Woche-Trend |
| Aktivitäts-Verteilung | Commits pro Tag, Last-Minute-Erkennung |
| Sanity-Check | LLM-Konsistenz-Bewertung |

Alle stehen im "Zusatzinfos"-Sheet der Team-Excel.
