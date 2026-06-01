# Verbesserungspaket sep-bewertung — Design / Spec

> Erstellt 2026-05-30. Basis: Verbesserungsvorschläge nach Code-Review der Pipeline.
> Der Bug-/Robustheits-Plan (`docs/befundbericht-und-plan.md`, 2026-05-29) ist
> bereits vollständig umgesetzt. Dieses Dokument beschreibt das **nach vorne
> gerichtete** Verbesserungspaket.

## Leitprinzip

Surgische Änderungen am bestehenden flachen Funktionsstil von `evaluate_team.py`.
**Verhaltensneutral wo möglich**: neue Schwellen/Listen kommen als `config.yaml`-
Defaults, die exakt den heutigen hartcodierten Literalen entsprechen. Echte
Verhaltensänderung nur dort, wo sie ein Korrektheits-Fix ist (Multi-Sprach-
Tests/LOC, User-Story-Regex). Jede Änderung bekommt einen Test in
`skripte/test_evaluate.py`.

## Aus dem Scope genommen (Nutzer-Entscheidung 2026-05-30)

- **1a Stichtag/Deadline-Schnitt: ENTFÄLLT.** Es wird immer der aktuellste Stand
  bewertet (`git log --all`, Issues/MRs `state=all` bleiben wie bisher, kein
  Datumsfilter).
- **4b Markdown-Report: KEIN neuer Report.** Stattdessen nur der irreführende
  Docstring wird an die Realität angepasst.

## Umfang (13 Punkte)

| # | Punkt | Art |
|---|-------|-----|
| 1b | Provenienz-Stempel in Excel | Feature |
| 1c | Divergenz-Flag Heuristik ↔ LLM | Feature |
| 1d | LLM `temperature: 0` | Korrektheit/Reproduzierbarkeit |
| 2a | Konventions-Pre-Flight-Report | Feature |
| 2b | Volle Multi-Sprach-Analyse (LOC/Struktur/Tests) | Korrektheits-Fix |
| 2c | User-Story-Regex entschärfen | Bugfix |
| 2d | Tutoren-Namen in Config | Refactor |
| 3a | Kriteriums-Drift-Assert | Robustheit |
| 3b | Autoren-Identität via E-Mail/.mailmap | Korrektheit |
| 3c | Coverage pro CI-Job | Korrektheit |
| 4a | Teams parallel verarbeiten | Performance |
| 4b | Docstring-Fix (kein MD-Report) | Doku |
| 5 | Pipeline-Tests ausbauen | Qualität |

---

## A. Konfiguration & gemeinsame Helfer

### `config.yaml` Erweiterungen

```yaml
llm:
  temperature: 0          # NEU — reproduzierbare Scores

run:                      # NEU
  team_workers: 4         # Parallelität in run_all über Teams

tutors:                   # NEU — ersetzt hartcodierte Namen
  - vogelsang
  - metzger

languages:                # NEU — Sprach-Registry (Default == heutiges Verhalten + Erweiterung)
  java:
    source_ext: [".java"]
    test_globs: ["**/*Test*.java", "**/*Tests.java", "**/*IT.java"]
    test_markers: ["@Test", "@ParameterizedTest"]
    comment_markers: ["//", "*", "/*"]
  typescript:
    source_ext: [".ts"]
    test_globs: ["**/*.spec.ts", "**/*.test.ts", "**/*.spec.tsx", "**/*.test.tsx"]
    test_markers: ["it(", "test(", "expect("]
    comment_markers: ["//", "*", "/*"]
  python:
    source_ext: [".py"]
    test_globs: ["**/test_*.py", "**/*_test.py"]
    test_markers: ["def test_", "assert ", "self.assert"]
    comment_markers: ["#"]
  go:
    source_ext: [".go"]
    test_globs: ["**/*_test.go"]
    test_markers: ["func Test", "func Benchmark"]
    comment_markers: ["//"]
  kotlin:
    source_ext: [".kt"]
    test_globs: ["**/*Test.kt", "**/*Tests.kt"]
    test_markers: ["@Test"]
    comment_markers: ["//", "*", "/*"]
  web:
    source_ext: [".html", ".css"]
    test_globs: []
    test_markers: []
    comment_markers: []

vendor_dirs: ["node_modules", ".git", "dist", "build", "target", "out",
              ".gradle", ".idea", "vendor", "venv", ".venv", "__pycache__"]
```

### Accessor in `evaluate_team.py`

Analog zum bestehenden `thr()`/`get_thresholds()` (module-weit, gecacht, kein
Signatur-Churn an den 20 `analyze_*`):

- `get_languages()` → dict aus `config.yaml languages:`, Default = obige Registry.
- `get_tutors()` → Liste aus `config.yaml tutors:`, Default `["vogelsang", "metzger"]`.
- `get_vendor_dirs()` → set aus `config.yaml vendor_dirs:`, Default wie oben.

---

## B. Multi-Sprach-Analyse (2b)

**Ansatz: config-getriebene Sprach-Registry als Daten** (keine Klassen pro
Sprache — passt zum flachen Funktionsstil, leichter testbar).

### LOC — `analyze_work_scope`

Statt fest `*.java/*.ts/*.html/*.css`: über alle `source_ext` aller Registry-
Sprachen iterieren, Vendor-Dirs aus `get_vendor_dirs()` ausschließen. Zählweise
(pro Datei Zeilen mit `errors="ignore"`) bleibt. Default-Registry enthält
java/ts/html/css → für reine Java/Angular-Teams **identische LOC** wie bisher;
Python/Go/Kotlin werden zusätzlich gezählt.

### Tests — `analyze_tests`

Pro Sprache:
- Test-Dateien = Dateien, die auf eines der `test_globs` passen (Vendor-Dirs raus).
- Substanz pro Datei: Anzahl Vorkommen der `test_markers`. Eine Datei gilt als
  *substantiell*, wenn sie > 1 Testfunktion/Assertion-Marker enthält (bisherige
  Angular-Logik: `it<=1 and expect<=1` → Stub; verallgemeinert).
- `test_methods` = Summe der primären Methoden-Marker (z. B. `@Test`, `def test_`,
  `func Test`, `it(`).

Aggregation in sprach-agnostische Kennzahlen:
- `total_test_files`, `substantive_test_files`, `total_test_methods`.

7-Punkte-Heuristik wird auf diese Aggregate umgemappt. **config-Defaults behalten
die heutigen Zahlen**, damit Java/Angular-Teams gleich bleiben:

```yaml
tests:
  files_for_first_point: 5
  files_for_second_point: 15
  substantive_for_third: 5          # war java_substantive_for_third
  methods_for_fourth: 30            # war java_methods_for_fourth
  substantive_for_fifth: 3          # war ts_substantive_for_fifth
  big_substantive_for_sixth: 10     # war big_java_for_sixth (+ ts>=5)
  big_methods_for_seventh: 50       # war big_java_methods_for_seventh
  big_substantive_for_seventh: 8    # war big_ts_for_seventh
```

Hinweis: Die alten keys (`java_substantive_for_third` etc.) werden auf die neuen
gemappt; alte `config.yaml`-Einträge bleiben über einen Fallback lesbar, damit
bestehende Configs nicht brechen. Die Sprach-Aufschlüsselung bleibt vollständig
in `details`.

Coverage-Bonus/Malus-Logik (`coverage_pct`) bleibt unverändert.

### Code-Struktur — `analyze_code_structure`

Generalisieren. Strukturiert = mindestens eines:
- Build-Marker vorhanden: `pom.xml`, `build.gradle(.kts)`, `package.json`,
  `go.mod`, `pyproject.toml`/`setup.py`, `Cargo.toml`.
- `src/`-Layout ODER Backend/Frontend-Split (bestehende Dir-Namen-Heuristik bleibt).
- Generische Modul-/Pakettiefe ≥ 3 (statt nur Java-Pakete; verschachtelte
  Quellordner unter `src/`/Sprachordnern).

`details` listet gefundene Build-Marker + Top-Dirs.

---

## C. Fairness / Transparenz in der Excel

### 1b Provenienz

`collect_results` erfasst nach dem Clone:
- HEAD-SHA: `git rev-parse HEAD`
- Branch: `git rev-parse --abbrev-ref HEAD`
- Fetch-Zeit: `datetime.now(timezone.utc).isoformat()` (UTC)
- Projekt-ID: `entry["gitlab_id"]`

**Ansatz: als Info-Kriterium (`max=0`) durch den bestehenden results-Kanal**
(„Datengrundlage (Info)"). Null Signatur-Änderung an `run_all.process`/
`build_xlsx.main`; landet automatisch im Zusatzinfos-Sheet. Zusätzlich rendert
`build_xlsx` eine kompakte Kopfzeile (neue Zeile A4) mit SHA (kurz) + Fetch-Zeit.

### 1c Divergenz-Flag

`build_xlsx`: conditional-format-Regel auf den D-Bereich der Kriterien-Zeilen:
`AND($D{anchor}<>"", ABS($D{anchor}-$C{anchor})>1)` → auffällige Füllfarbe.
Hinweistext in A3 ergänzen: „Orange in D: Heuristik und LLM weichen > 1 Punkt ab —
manuell prüfen."

### 2a Konventions-Report

Neues Info-Kriterium `analyze_conventions(issues, mrs)` (`max=0`):
- Anzahl `type::userstory`, `type::epic`, `priority::*`-Labels
- Anzahl MRs mit `Closes/Closed/Fixes #N` in Description
- Anzahl Issues mit `weight`, Anzahl mit Milestone
- Klartext-Hinweis, welche Konventionen NICHT gefunden wurden (→ welchen Auto-
  Scores man misstrauen sollte).

Wird in `collect_results` vorne in die results-Liste aufgenommen → Zusatzinfos.

### 3a Kriteriums-Drift-Assert

In `build_xlsx` (nach dem Schreiben der Datenzeilen): prüfen, dass jedes
Kriterium aus `CATEGORIES` in `by_crit` vorkam. Fehlende → `print("WARN: ...",
file=sys.stderr)` mit Liste. Verhindert, dass eine String-/Umlaut-Drift ein
Kriterium still aus der Excel fallen lässt. Test: alle `CATEGORIES`-Kriterien
sind durch die `collect_results`-Result-`criterion`-Strings abgedeckt.

---

## D. Heuristik-Fixes

### 2c User-Story-Regex

In `analyze_user_stories`: bare `als ` entfernen. Format zählt nur, wenn
Rolle + Wunsch zusammen auftreten:
- EN: `re.search(r"\bas an? .+?(i want|i'd like|i would like)", dl, re.S)`
- DE: `re.search(r"\bals\s+\S.+?(möchte|will ich|ich will|wünsche)", dl, re.S)`

Test: „mehr als 5 Tasks" zählt NICHT; „Als Nutzer möchte ich …" zählt.

### 2d Tutoren in Config

`analyze_work_scope`: Filter über `get_tutors()` (Substring-Match, lowercase)
statt hartcodierter `"vogelsang"`/`"metzger"`.

### 3b Autoren-Identität

`analyze_commit_distribution`: `git shortlog -sne --all --no-merges` (respektiert
vorhandene `.mailmap`). Aggregation per lowercased E-Mail; Anzeige-Name = häufigster
Name je Mail. Gini/Top-Share auf der mail-aggregierten Verteilung. Limitierung
(eine Person, zwei Mails) wird in `details`/`reason` als Hinweis vermerkt.

### 3c Coverage pro Job

`fetch_coverage_from_ci`: wenn `pipeline.coverage` für alle gesampelten Pipelines
`None` ist, für die erfolgreichen Pipelines `/projects/:id/pipelines/:pid/jobs`
laden und das höchste `job.coverage` nehmen. Quelle im Rückgabe-Tupel als
`"Pipeline #X Job <name>"`.

---

## E. LLM

### 1d temperature

`llm.py` `call()`: `body["temperature"] = self.temperature`. Feld im
`LLMClient.__init__` (Default 0), aus `config.yaml llm.temperature` über
`load_llm_from_configs`. Cache-Key bleibt unberührt (temperature ist Teil des
deterministischen Setups, nicht des Prompts) — bestehende Caches bleiben gültig.

### 5 (teilweise) Parse-Funktion extrahieren

Die JSON-Parse-Logik aus `LLMClient.score()` (Z. ~188-215) in eine **pure
Funktion `_parse_score_response(out, scale_max)`** in `llm.py` herausziehen.
`score()` ruft sie auf. Ohne Netzwerk testbar.

---

## F. Performance & Doku

### 4a Teams parallel

`run_all.main`: Teams über `ThreadPoolExecutor(max_workers=get run.team_workers)`
parallel verarbeiten (I/O-bound: git/API/LLM; `LLMClient` ist bereits threadsafe,
GitLab-API-Funktionen ebenso). Pro-Team-Output in einen String puffern und beim
Future-Abschluss am Stück ausgeben (kein interleaving). PDF- und Overview-
Generierung laufen **nach** dem parallelen Block (sequentiell, da sie auf die
geschriebenen Excels zugreifen). Fehler einzelner Teams werden wie bisher
gesammelt (`failed`-Liste), kippen den Batch nicht.

### 4b Docstring-Fix

`evaluate_team.py` Modul-Docstring (Z. 12-13): „Markdown-Report … als
`Bewertung_<team>.md`" → korrekt: „Die eigentliche Ausgabe erzeugt `build_xlsx.py`
als Excel-Bewertungsbogen; `evaluate_team.collect_results()` liefert die
Analyse-Daten. `main()` ist nur ein Smoke-Test-Stub."

---

## G. Tests (`skripte/test_evaluate.py`)

Neu:
1. `_parse_score_response`: dict-Antwort, Listen-Antwort (Aggregation),
   ```json-Wrap, Müll → None, Score-Clamping.
2. `analyze_conventions`: Zählung gegen konstruierte issues/mrs-Fixtures.
3. Multi-Sprach-Test-Erkennung: Fixtures mit Go-/Python-/Kotlin-Testdateien →
   korrekte `total_test_files`/`substantive_test_files`.
4. Multi-Sprach-LOC: Python-Datei wird mitgezählt.
5. Kriteriums-Drift-Assert: alle `CATEGORIES`-Kriterien sind durch
   `analyze_*`-`criterion`-Strings abgedeckt.
6. User-Story-Regex 2c: Positiv-/Negativfälle.
7. Tutoren-Config: `get_tutors()`-Override greift in `analyze_work_scope`.
8. Divergenz-Flag: Workbook enthält die conditional-format-Regel auf D
   (Round-Trip-Check der Regel-Existenz/Formel).

Akzeptanz: `cd skripte && python -m unittest test_evaluate` grün (bisher 18 Tests,
danach mehr).

---

## Umsetzungs-Reihenfolge & Commits

Thematische Commits analog zu den früheren Phasen:

1. **A + Helfer** (config.yaml, `get_languages/get_tutors/get_vendor_dirs`).
2. **B** Multi-Sprach (LOC, Tests, Struktur) + Tests.
3. **C** Provenienz, Divergenz-Flag, Konventions-Report, Drift-Assert + Tests.
4. **D** Heuristik-Fixes (Regex, Tutoren-Verdrahtung, mailmap, Job-Coverage) + Tests.
5. **E** LLM temperature + Parse-Funktion + Tests.
6. **F** Parallelisierung + Docstring.
7. Doku-Abgleich (CLAUDE.md/docs falls Schwellen-Keys umbenannt), `.wolf/`-Pflege.

Nach jedem Commit Tests grün halten.

## Risiken / bewusst offen

- Multi-Sprach-Tests können Python-/Go-Teams **höher** bewerten als bisher — das
  ist der beabsichtigte Korrektheits-Fix, kein Regressionsfehler. Java/Angular-
  Teams bleiben durch Default-Schwellen gleich.
- `.mailmap` löst nur „eine Person, mehrere Namen, gleiche Mail". Mehrere Mails
  pro Person bleiben offen (dokumentiert).
- Umbenannte `tests:`-Schwellen-Keys: Rückwärtskompatibler Fallback auf die alten
  Keys, damit vorhandene `config.yaml` nicht still bricht.
