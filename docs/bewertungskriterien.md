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
- Ø-Länge ohne Merge-Commits ≥ 35 Zeichen
- Anteil trivialer Messages ("fix", "update", "wip") < 15%
- Anteil sehr kurzer Messages (<8 Zeichen) < 10%

**Schwellen:** Alle drei müssen erfüllt sein für 1 Punkt.

**Warum so:** 35 statt 25 Zeichen, weil alle SS26-Teams im Schnitt bei 39–48 Zeichen lagen — 25 filterte nichts. 35 trennt knappe von ausführlichen Messages. 15%/10% Toleranzen erlauben einzelne "fix typo"-Commits ohne Punktabzug.

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
- Verlinkung zwischen Epics und User Stories aus drei vereinigten Quellen (eine Story zählt nur einmal):
  1. `#123`-Referenzen in den Bodies (in beide Richtungen),
  2. native **„Child items"** (GitLab-Work-Item-Hierarchie),
  3. native **„Linked items"** (`relates_to`/`blocks`).
  Quellen 2+3 werden via GraphQL geholt (`fetch_epic_links`), weil der REST-`/issues`-Endpoint sie nicht mitliefert.

**Schwellen:** ≥3 Epics UND ≥5 verlinkte Stories → 1 Punkt.

**Warum so:** Teams behelfen sich mit dem Label `type::epic`. Die Verlinkung erfolgt in der Praxis meist über das „Linked items"-Widget (`relates_to`) — diese Beziehung steht nicht im Beschreibungstext und wurde früher übersehen, was zu falschen 0/1 führte, obwohl in GitLab sichtbar Stories verknüpft waren.

**Blinde Flecken:** Verlinkungs-Konventionen außerhalb der drei Quellen (z.B. Task-Listen mit reinem Text ohne `#`-Referenz, Sub-Labels) werden übersehen. Bei 0/1 lohnt der manuelle Blick. Hinweis: GraphQL-Ausfall (alte GitLab-Version) fällt still auf reine Text-Referenzen zurück.

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
- ≥3 substantielle Wiki-Seiten: +1, ≥15 Seiten: +2 (gestaffelt, nicht additiv). „Substanziell" heißt: der bereinigte Seitentext erreicht ≥`code_docs.min_wiki_page_chars` (Default 200) Zeichen — kurze Stub-/Backlog-Seiten zählen nicht mehr mit. (Greift, wenn die Pipeline die Wiki-Inhalte durchreicht; ohne Inhalte zählt wie früher jede Nicht-Upload-Seite.)
- OpenAPI/Swagger-Spec im Repo gefunden (Java-Annotationen ODER `openapi.{yaml,yml,json}`/`swagger.{yaml,yml,json}`): +1
- **Datenbankschema dokumentiert: +1** — `_detect_db_schema` erkennt `*.sql`, `*.prisma`, Liquibase-Changelogs, ein `migrations/`-Verzeichnis mit Inhalt, oder ORM-Entities/Models (`@Entity`, `@Table(`, Django `models.Model`, SQLAlchemy `declarative_base`). Das PDF nennt "Datenbankschemata" explizit.
- Inline-Kommentar-Anteil ≥10% **über alle erkannten Sprachen** (Comment-Marker je Sprache aus der Registry, nicht mehr nur Java): +1

**Warum so:** Gute Doku hat mehrere Quellen. Die Punkte sind so verteilt dass weder reines Wiki noch reines Code-Kommentar volle Punktzahl gibt — der Mix wird belohnt. Da 6 Signale auf max 5 gedeckelt sind, genügt es, einige davon abzudecken.

**LLM ergänzt:** Sample von bis zu 3 Quell-Dateien mit Kommentaren (sprachunabhängig über die Registry) → beurteilt ob die Kommentare WARUM (gut) oder nur WAS (redundant) erklären. Score 0–2.

**Blinde Flecken:** Wiki-Qualität wird nicht inhaltlich geprüft. Das LLM zur Meeting-Doc-Bewertung deckt zwar Meeting-Seiten ab, nicht aber andere Wiki-Seiten. DB-Schema-Erkennung ist signal-/dateibasiert (erkennt z.B. ein nur in Prosa beschriebenes Schema im Wiki nicht).

### Code sauber/ohne größere Mängel (0–1)

**Was misst die Heuristik:** Eine Liste von Negativ-Checks. Sobald **einer** auslöst → 0. Die meisten lösen schon bei der ersten Fundstelle aus, zwei haben aber eine kleine Toleranz (konfigurierbar unter `thresholds.repo_hygiene`):

- `node_modules/` im Git-Index — löst ab **1** Datei aus
- Build-Artefakte (`dist/`, `target/`, `build/`, `out/`, `.gradle/`, `.idea/`) — erst ab **>5** Dateien (`max_build_artifacts`)
- IDE-Configs (`.idea/`, `.vscode/`, `*.iml`) — erst ab **>3** Dateien (`max_ide_configs`)
- OS-Cruft (`.DS_Store`, `Thumbs.db`) — ab **1**
- Debug-/Log-Dateien (`merge-debug.txt`, `debug.log`, `*.log`) — ab **1**
- Binaries >5 MB (`large_binary_mb`) — ab **1** (Scan auf die ersten 500 getrackten Dateien begrenzt)
- **>20** TODO/FIXME/XXX/HACK-Marker (`max_todos`) — **nur in `*.java`/`*.ts` gezählt** (je erste 300 Dateien), nicht sprachunabhängig
- Keine Lint-Config (`.eslintrc*`/`eslint.config.*`/`.prettierrc*`/`checkstyle.xml`) UND keine `.editorconfig`

**Warum so:** Das sind alles klassische "wurde nicht aufgeräumt"-Indikatoren. Bei studentischen Repos kommen sie regelmäßig vor und sind ein guter Negativ-Hint. Die Toleranz bei Build-Artefakten/IDE-Configs federt vereinzelte Fehl-Commits ab, ohne ein systematisch unsauberes Repo durchzulassen.

**Blinde Flecken:** Die Heuristik gibt 0/1 — kein Halbwert. Ein Repo mit nur einer .DS_Store-Datei bekommt die gleiche Bewertung wie eins mit 100 MB node_modules + 200 TODOs. Und: Der TODO-Zähler ist Java/TS-spezifisch — ein reines Python-/Go-Team wird bei TODOs nicht erfasst (die übrigen Checks sind dagegen `git ls-files`-basiert und damit sprachunabhängig).

### Tests vorhanden und sinnvoll (0–7)

**Was misst die Heuristik (additiv, max 7, sprachunabhängig über die Registry):**
Aggregiert über alle Sprachen (`test_globs`/`test_markers` je Sprache): Gesamtzahl Test-Dateien, davon **substantielle** (>1 primärer Test-Marker), und Gesamtzahl Test-Methoden/-Fälle.
- ≥5 Test-Dateien insgesamt: +1
- ≥25 Test-Dateien: +1
- ≥5 substantielle Test-Dateien: +1
- ≥80 Test-Methoden/-Fälle insgesamt: +1
- ≥8 substantielle Test-Dateien: +1
- ≥18 substantielle Test-Dateien: +1
- ≥130 Methoden/-Fälle UND ≥22 substantielle Test-Dateien: +1

**Coverage-Boost:** Wenn CI Coverage reportet (Schwellen konfigurierbar via `tests.coverage_bonus_min` / `coverage_penalty_max`):
- ≥80%: +1 (capped bei max 7)
- <30%: -1 (mindestens 2)

**Warum so (Kalibrierung SS26):** Die oberen Stufen wurden ~2–4× angehoben, weil mit den alten Schwellen **alle** Teams 7/7 erreichten (23–32 Dateien, 107–157 Methoden), das LLM aber nur 0–2/7 vergab — die Skala war oben „durchgebrannt". Die Heuristik **zählt** nur (Datei/Methode), sie misst keine Qualität; der Substanz-Filter (substantiell = **mehr als ein** primärer Test-Marker: `@Test` / `def test_` / `func Test` / `it(`) hält 1-Test-Stubs (z.B. Angulars "should create") raus, aber die eigentliche Qualitätsaussage tragen Coverage und die LLM-Spalte.

**LLM ergänzt:** Sample von bis zu 6 Test-Dateien (sprachunabhängig, `llm_sampling.tests_files`) → beurteilt: nur Happy Path oder auch Edge Cases / Error-Pfade? Score 0–3.

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
- ≥65% aller Issues geschlossen
- UND ≥60% der `priority::must`-Issues geschlossen

> Hinweis: Die Heuristik misst hier nur **Issue-Abschluss**, nicht echte Ziel­erreichung (Issues schließen ≠ Sprintziel erreicht). Die Lücke ist semantisch, nicht nur eine Schwelle — im Zweifel der LLM-Spalte (D) mehr Gewicht geben.

**Warum so:** Die Must-Quote ist wichtiger als die Gesamt-Quote — wenn nur Could/Should-Issues offen sind, ist das okay.

**LLM ergänzt (Sonnet):** Pro Stichprobe von 4 User-Story+MR-Diff-Paaren → bewertet ob die Story sauber implementiert ist (alle Akzeptanzkriterien adressiert, kein Scope-Creep). Score 0–3.

**Blinde Flecken:** Die Heuristik prüft nur State-Transition, nicht Qualität der Implementierung. Das LLM mit Code-Verständnis (deswegen Sonnet) schließt diese Lücke — aber nur für MRs mit `Closes #N` in der Description.

### Arbeitsumfang angemessen (0/5/10/15)

**Was misst die Heuristik:** Anzahl Commits und LOC (sprachunabhängig über die
Registry, ohne Vendor-Dirs) — **pro Kopf normalisiert**.

**Normalisierungsbasis (`config.yaml → work_scope.normalize_by`):** Der Teiler
für die Pro-Kopf-Werte ist konfigurierbar, Default ist **`measured`**:
- **`measured` (Default):** geteilt wird durch die **real gemessene** Zahl aktiver
  Commit-Autoren (per E-Mail dedupliziert, Tutoren/Staff via `staff_email_domains`
  ausgefiltert) — aber **geklammert** auf `[work_scope.team_size_min,
  work_scope.team_size_max]` (Default **5–8**). Die Klammer ist der
  Trittbrettfahrer-Schutz: ein 1-Personen-Team wird auf min 5 angehoben (kein
  riesiger Pro-Kopf-Exploit), ein 12-Personen-Eintrag auf max 8 gedeckelt (kein
  Verwässern durch Nie-Committer/Tutoren). Ungleiche Verteilung fängt ohnehin das
  Info-Kriterium **Commit-Verteilung** (Gini) ab.
- **`fixed` (altes Verhalten):** geteilt wird durch eine **feste angenommene
  Teamgröße** (`work_scope.assumed_active_authors`, Default **6**), unabhängig von
  der gemessenen Autorenzahl.

Hintergrund: Die GitLab-Mitgliederzahl überschätzt (zählt Nie-Committer/Tutoren
mit; im SS26 meldete GitLab 11–12 „Mitglieder" bei real nur 7–8 Commit-Autoren) —
deshalb die Klammer statt der rohen Mitglieder- oder Autorenzahl. Die gemessene
Autorenzahl und der angewandte Teiler stehen im Reason-Text; eine ausgelöste
Klammerung (`auf Minimum 5 angehoben` / `auf Maximum 8 gedeckelt`) wird dort
explizit vermerkt.

**Schwellen (kumulativ, pro Kopf — Schwellen kalibriert auf ~6 Autoren):**
- <20 Commits & <1k LoC (absolut) → 0
- <15 Commits/Kopf ODER <800 LoC/Kopf → 5
- <40 Commits/Kopf ODER <2000 LoC/Kopf → 10
- sonst → 15

**Warum so:** Rohe Gesamtzahlen sind ein schwaches Signal — ein normales
Semester-SEP knackt jede absolute Schwelle, weshalb die alte Logik faktisch
**immer 15** gab (alle SS26-Teams: 193–634 Commits, 8k–23k LoC → ausnahmslos
15/15). Pro Kopf entsteht wieder ein Spread (SS26 schwächstes Team ~35 Commits/Kopf
& ~1.4k LoC/Kopf → 10, stärkstes ~106 & ~3.9k → 15).

**Blinde Flecken:** Quantität ≠ Qualität. Viele kleine Refactoring-Commits zählen
genauso wie echte Features. Deshalb bleibt der ⚠-Hinweis zur manuellen Prüfung.

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

Direktpushes werden über die First-Parent-Linie von `origin/main` gezählt. Davon abgezogen werden echte Merge-Commits **und** bekannte MR-Merge-/Squash-Commits (`merge_commit_sha`/`squash_commit_sha` der gemergten MRs) — sonst würde ein GitLab-Squash-Merge, dessen Commit-Message nicht mit „Merge " beginnt, fälschlich als Direktpush gewertet. Die Zahl der so erkannten MR-Squash-Commits steht in Reason/Details (`mr_squash_commits_recognized`).

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
