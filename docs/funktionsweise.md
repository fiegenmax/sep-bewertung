# Funktionsweise

Wie die Pipeline intern aufgebaut ist. Für Entwickler-Sicht.

## Hoher Überblick

```
                    .env (Token + Key)
                            │
                            ▼
┌──────────────────────────────────────────────────────┐
│              run_all.py (Master)                      │
│   parsed args, loaded config, Teams PARALLEL          │
│   (ThreadPoolExecutor, config run.team_workers)       │
└────────────┬─────────────────────────────────────────┘
             │
             ▼
   ┌─────────────────────────────────────────┐
   │  Pro Team:                              │
   │  1. evaluate_team.clone_or_update()     │  → <temp>/sep_repos/<team>/
   │  2. evaluate_team.api_get(...)          │  → GitLab API (mit Cache)
   │  3. ~22× evaluate_team.analyze_*()      │  → List[Result-Dict]
   │     (sprachunabhaengig: Java/TS/Py/Go/Kt)│  + Info: Konventionen, Provenienz
   │  4. evaluate_team.analyze_sanity_check()│  → LLM Konsistenz-Check
   │  5. build_xlsx.build_xlsx()             │  → team-X/Bewertung_X.xlsx
   │  (optional) fill_pdf.main_for()         │  → team-X/Bewertung_X.pdf
   └─────────────────────────────────────────┘
             │
             ▼
   (optional) build_overview.main()           → Uebersicht_alle_Teams.xlsx
```

## Datenfluss

### 1. Konfiguration laden

`evaluate_team.load_config()` parsed `.env` (Fallback: `.gitlab-config`) als simples `KEY=VALUE`-Format.

`evaluate_team.load_yaml_config()` parsed `skripte/config.yaml` und gibt einen Dict mit Schwellen zurück. Daraus werden über gecachte Accessoren gelesen: `get_thresholds()`/`thr()` (Schwellen), `get_languages()` (Sprach-Registry für LOC/Tests/Struktur), `get_tutors()` (nicht mitgezählte Usernamen) und `get_vendor_dirs()` (ausgeschlossene Ordner). Alle mit Defaults == bisherigem Verhalten.

`llm.load_llm_from_configs(...)` kombiniert beides und erzeugt einen `LLMClient`. Wenn `ANTHROPIC_API_KEY` leer oder dummy, wird `client.enabled = False` — alle LLM-Aufrufe geben dann sofort `None` zurück.

### 2. Repo klonen oder fetchen

`clone_or_update(http_url, token, local_path)`:
- Wenn `local_path` existiert: `git fetch --all --tags --prune`.
- Sonst: `git clone <auth_url>` wobei der Token als `oauth2:<token>@` in die URL injiziert wird.
- Sanity-Check am Schluss: `git log --oneline -1` — wenn leer, RuntimeError. Verhindert dass leere Repos die nachgelagerten Analysen crashen.

### 3. API-Daten holen

Drei Funktionen wrappen die GitLab-API:

- `api_get(path, token)` — single GET, returns dict.
- `api_get_paginated(path, token)` — automatische Pagination bis chunk < 100.
- `api_get_parallel(paths, token, max_workers=8)` — ThreadPoolExecutor für viele paths (z.B. Wiki-Inhalte aller Seiten).

Alle drei nutzen einen **persistenten Disk-Cache** unter `<temp>/sep_gitlab_api_cache/` (`<temp>` = OS-Temp-Verzeichnis, per `SEP_CACHE_DIR` überschreibbar). Cache-Key ist SHA1 von `path` (+ Seitennummer). Cache wird **nicht** invalidiert über die Zeit — beim nächsten Lauf kommt also der gleiche Wert zurück. Deshalb `--fresh`: löscht den Cache-Ordner komplett (GitLab- **und** LLM-Cache).

### 4. Analysen ausführen

`evaluate_team.py` definiert 20 `analyze_*`-Funktionen, jede mit einheitlicher Signatur:

```python
def analyze_xxx(...) -> Dict[str, Any]:
    return {
        "criterion": str,
        "max": int,
        "score": int,
        "label": str,
        "reason": str,
        "details": dict,
    }
```

Eine Auswahl davon kann optional ein `llm: LLMClient`-Argument bekommen. Wenn `llm` übergeben ist und enabled, wird die zugehörige LLM-Inhaltsprüfung mit gemacht und das Ergebnis in `details.llm_review` gespeichert (eigene Sub-Dict mit `score` und `reason`).

### 5. Excel-Generierung

`build_xlsx.build_xlsx(team_name, gitlab_path, web_url, results, output_path, keep_manual=True, do_backup=True)`:

1. **Manuelle Werte aus existierender Datei extrahieren** (`extract_manual_values`). Liest Spalte F und G aller Kriterien-Zeilen aus der alten Datei (Auto-Detect ob altes oder neues Layout).
2. **Backup machen** (`backup_existing`) — `.xlsx.bak` der vorherigen Version.
3. **Workbook neu aufbauen**:
   - Sheet "Bewertung" mit Headerzeile, Datenrows pro Kriterium, Zwischensummen pro Kategorie, GESAMT + GESAMT (LLM-Hybrid).
   - Sheet "Zusatzinfos" mit den Info-Analysen (max=0, kein Score-Beitrag).
4. **Manuelle Werte zurückmergen** (`merge_manual_values_into_workbook`) — wenn ein altes Wert vorhanden ist und ungleich dem neuen Auto-Vorschlag, wird er übernommen.
5. **Speichern**.

Excel-Formeln:
- Zwischensumme: `=SUM(F<row1>,F<row2>,...)` — Liste statt Range, weil Zeilen nicht zwingend zusammenhängend sind.
- Gesamtsumme: `=SUM(F<alle>)`.
- LLM-Hybrid: `=IF(D<r>="",C<r>,D<r>)+IF(D<r2>="",C<r2>,D<r2>)+...` — eine Term-Liste pro Zeile statt SUMPRODUCT (das in alten Excel-Versionen Array-Formel-Probleme hat).

Conditional Formatting:
- Spalte F bekommt rote+fette Schrift wenn `F<>C` (Heur-Score wurde manuell geändert). Macht beim Drüberscrollen sichtbar wo du eingegriffen hast.

### 6. PDF-Ausfüllung (optional)

`fill_pdf.fill_pdf(template_path, scores, total_score, output_path, team_name)`:

1. Lädt das Template-PDF (`assets/Templates/Template Artifacts Exam Checklist Fillable.pdf`) mit `pypdf.PdfReader` und klont es in einen `PdfWriter`.
2. Mapping `CHECKBOX_MAP` (in fill_pdf.py hartcodiert) ordnet Kriterium-Name + Punktzahl zu `Kontrollkästchen<N>`. **Wichtig:** die vertikalen Antwort-Listen im Template sind *invers* nummeriert (oberstes Kästchen = 0 Punkte = höchste ID), die horizontalen Skalen aufsteigend.
3. Für jeden Score in der Excel (Spalte F): wenn numerisch, das passende Kästchen auf seinen Ja-Zustand (`/Yes`) setzen. `x`/leer = noch nicht bewertet → kein Kreuz.
4. Header-Textfelder: `Geprüftes Team` (Textfeld1), `Prüfer` (Textfeld0), `Gesamtpunktzahl` (Textfeld2 = Summe Spalte F) sowie die Abschnitts-Zwischensummen (Textfeld3/13/17). **Es werden keine Anmerkungen/Kommentare ins PDF geschrieben.**
5. `NeedAppearances=True` setzen, damit Viewer die Textwerte rendern.

Das Mapping wurde aus der Geometrie der PDF-Form-Felder verifiziert und ist durch `test_evaluate.TestCheckboxMapMatchesGeometry` gegen das Template abgesichert. Wenn das offizielle Template sich ändert, schlägt dieser Test an und das Mapping muss nachgezogen werden.

### 7. Übersicht (optional)

`build_overview.main()`:

1. Liest alle existierenden `Bewertung_team-X.xlsx`-Dateien ein (via `read_team_xlsx`).
2. Baut eine neue Excel mit Teams als Spalten, Kriterien als Zeilen.
3. Conditional Formatting: Farbskala pro Team-Spalte (rot=niedrig, grün=hoch).
4. Schreibt nach `Uebersicht_alle_Teams.xlsx` ins Wurzelverzeichnis.

## LLM-Wrapper im Detail

`llm.LLMClient` wrappt die Anthropic Messages API ohne SDK (nur `urllib.request`).

### Caching

`LLMClient.call(prompt, system, max_tokens)`:
1. Berechnet Cache-Key aus `system + prompt + max_tokens` (SHA1, 24 chars).
2. Wenn Cache-Datei in `<temp>/sep_llm_cache/` existiert und nicht älter als `cache_ttl_days` (default 7) → liefert gecachte Antwort.
3. Sonst: POST an `https://api.anthropic.com/v1/messages`, Antwort speichern, zurückgeben.

Bei HTTPError oder Exception wird `None` zurückgegeben — die `analyze_*`-Funktionen erkennen das und überspringen die LLM-Bewertung.

### Score-Hilfsfunktion

`LLMClient.score(prompt, scale_max, system=None)`:
- Hängt automatisch eine Format-Anweisung an das System-Prompt an: "Antworte ausschließlich als JSON-Objekt mit score und reason".
- Versucht das Ergebnis als JSON zu parsen, mit Fallbacks für `[...]`-Listen-Antworten (aggregiert dann via Mittelwert) und `\`\`\`json` Wraps.
- Returns `{"score": int, "reason": str}` oder `None`.

### Modell-Override

`LLMClient.score_with_model(prompt, scale_max, model, system=None)` setzt temporär `self.model = model` für genau einen Aufruf. Wird genutzt für **Sonnet bei Issue↔Code-Vergleich** (Code-Verständnis braucht das größere Modell).

## Datei-für-Datei

### `skripte/evaluate_team.py` (~1500 Zeilen)

Das Herzstück. Enthält:
- API-Wrapper (`api_get`, etc.)
- Repo-Operations (`clone_or_update`, `run`)
- 20 `analyze_*`-Funktionen mit Heuristik + optional LLM
- 5 LLM-only Hilfsfunktionen (`analyze_commit_substance`, `analyze_issue_vs_code`, etc.) die in andere `analyze_*` eingebunden sind
- `analyze_sanity_check` der am Ende über alle Ergebnisse läuft
- `fetch_coverage_from_ci` für Test-Coverage aus Pipelines
- `CATEGORIES` und `MANUAL_CRITERIA` als Konstanten

### `skripte/llm.py` (~170 Zeilen)

`LLMClient`-Klasse + Cache-Helper + `load_llm_from_configs` Factory.

### `skripte/build_xlsx.py` (~440 Zeilen)

`build_xlsx`-Funktion + Helper für extract/merge + ein eigenes `main()` für Standalone-Aufruf (`python build_xlsx.py team-X`).

### `skripte/build_overview.py` (~170 Zeilen)

Liest existierende Bewertungs-Excels, baut Übersicht.

### `skripte/fill_pdf.py` (~190 Zeilen)

PDF-Form-Filling mit `pypdf`. Hartcodiertes Mapping zwischen Kriterium-Name und PDF-Form-Field.

### `skripte/run_all.py` (~140 Zeilen)

Master-Skript, parsed Flags (`--fresh`, `--pdf`, `--overview`), looped über Teams. Try/Except pro Team damit ein kaputtes Team nicht alle anderen stoppt.

### `skripte/config.yaml`

Konfigurierbare Schwellen pro Kriterium. Wird via PyYAML geladen. Beispiel:

```yaml
thresholds:
  user_stories:
    full_score_ratio: 0.85
    partial_score_ratio: 0.5
    min_stories_for_one: 5
```

Aktuell werden die Schwellen noch teilweise hartcodiert in den `analyze_*`-Funktionen genutzt — wenn du `config.yaml` ernsthaft als Konfiguration nutzen willst, müssen die hartcodierten Werte durch Zugriffe ersetzt werden. Das ist ein TODO.

### `skripte/team_mapping.json`

Pro Team ein Eintrag mit `local_folder`, `gitlab_path`, `gitlab_id`, URLs. Wird einmalig erzeugt aus der GitLab-Group-API.

## Aufruf-Sequenz im Detail (Beispiel: `python run_all.py team-entropy --fresh`)

1. `main()` parsed Args, erkennt `--fresh` und löscht den Cache.
2. Lädt `.env` (oder Fallback `.gitlab-config`) und `config.yaml`.
3. Erzeugt LLM-Client (mit Schalter `enabled`).
4. Lädt `team_mapping.json`, filtert auf `team-entropy`.
5. Ruft `process(entry, token, llm_client)`:
   1. `clone_or_update` — git fetch oder clone.
   2. `api_get_paginated` für issues, mrs, releases, milestones, members.
   3. `api_get` für wikis, boards.
   4. `api_get_parallel` für Wiki-Seiteninhalte.
   5. `fetch_coverage_from_ci`.
   6. 20× `analyze_*` mit dem LLM-Client.
   7. `analyze_sanity_check`.
   8. `build_xlsx(...)` schreibt die Excel.
6. (optional) `fill_pdf.main_for("team-entropy")`.
7. (optional, am Ende) `build_overview.main()`.

Bei `--fresh`-Lauf für 1 Team: ~1-2 min (LLM-Calls dominieren). Bei warmem Cache: ~5 Sekunden.

## Fehlerverhalten

- **Repo leer** → `clone_or_update` wirft RuntimeError, von `run_all.process` gefangen, Team wird in `failed` Liste vermerkt.
- **GitLab-API-Fehler** → `urllib.request.urlopen` wirft Exception, in den `api_get_*` Funktionen gefangen wenn möglich, sonst propagiert sich's und beendet das eine Team.
- **LLM-Fehler** → in `llm.py` immer gefangen, `None` zurückgegeben. Andere Analysen laufen normal.
- **Excel-Schreib-Fehler** → propagiert sich. Backup ist aber schon geschrieben, also Datenverlust unwahrscheinlich.
