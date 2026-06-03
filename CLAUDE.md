# OpenWolf

@.wolf/OPENWOLF.md

This project uses OpenWolf for context management. Read and follow .wolf/OPENWOLF.md every session. Check .wolf/cerebrum.md before generating code. Check .wolf/anatomy.md before reading files.


# CLAUDE.md — Briefing für Claude Code

Dieses Repo enthält eine automatische Bewertungspipeline für studentische SEP-Projekte an der UDE (Universität Duisburg-Essen). Es wurde im Mai 2026 für die SEP-Zwischenprüfung Sommersemester 2026 aufgebaut.

## Was das Tool macht in einem Satz

Es zieht für jede Studi-Team-Gruppe das GitLab-Repo + Issues/MRs/Wiki/Releases, wendet gut 20 heuristische Analysen (sprachunabhängig über eine Registry: Java/TS/Python/Go/Kotlin) plus 12 LLM-Inhaltsprüfungen darauf an, und schreibt pro Team einen Excel-Bewertungsbogen mit Auto-Vorschlag, LLM-Zweitmeinung und Platz für die manuelle Bewertung des Prüfers. Dazu kommen Info-Kriterien (u. a. Konventions-Report und Provenienz-Stempel), die keinen Score haben, aber die manuelle Bewertung absichern.

## Repo-Struktur

```
.
├── CLAUDE.md                       # Diese Datei
├── README.md                       # Quickstart für Menschen
├── pyproject.toml                  # uv-Projekt (Deps + Konsolen-Befehl sep-bewertung)
├── uv.lock                         # uv-Lockfile
├── .env                            # NIE COMMITTEN! Token + API-Key (Fallback: .gitlab-config)
├── .env.example                    # Committbares Template mit Platzhaltern
├── .gitignore
├── assets/Templates/               # Leere Original-Bewertungsbögen UDE (Template *.pdf)
├── skripte/                        # Die Pipeline selbst
│   ├── config.yaml                 # Konfigurierbare Schwellen für Heuristiken
│   ├── team_mapping.json           # Lokaler Ordner → GitLab-Projekt (generiert, gitignored)
│   ├── team_mapping.example.json   # Committbare Vorlage dazu
│   ├── teams.example.txt           # Vorlage für die Team-Liste (gen_mapping.py)
│   ├── gen_mapping.py              # team_mapping.json aus teams.txt + GitLab-API erzeugen
│   ├── evaluate_team.py            # Analysefunktionen (Heuristik + LLM) + collect_results()
│   ├── llm.py                      # Anthropic-API-Wrapper mit Disk-Cache
│   ├── build_xlsx.py               # Excel-Generator
│   ├── build_overview.py           # Übersicht über alle Teams
│   ├── fill_pdf.py                 # PDF-Formular ausfüllen (optional)
│   ├── run_all.py                  # Master-Skript mit Flags
│   ├── test_evaluate.py            # Tests für Heuristiken + Excel-Roundtrip
│   └── test_gen_mapping.py         # Tests für gen_mapping
├── docs/                           # Detaillierte Doku
│   ├── nutzung.md                  # Wie das Tool benutzt wird
│   ├── funktionsweise.md           # Wie es intern funktioniert
│   ├── bewertungskriterien.md      # Was jedes Kriterium misst und warum
│   ├── llm-integration.md          # Welche LLM-Calls existieren, Kosten
│   └── troubleshooting.md          # Bekannte Probleme + Workarounds
└── teams/                          # Alle Team-Ordner + Übersicht
    ├── Uebersicht_alle_Teams.xlsx  # Generierte Übersicht (mit --overview)
    └── team-<name>/                # Pro Team
        ├── Artifacts Exam *.pdf    # Original-Vorlage
        ├── Team Exam *.pdf         # Vorlage für mündliche Prüfung
        ├── Bewertung_team-<name>.xlsx      # Generierter Bewertungsbogen
        ├── Bewertung_team-<name>.xlsx.bak  # Backup vom letzten Lauf
        └── Bewertung_team-<name>.pdf       # Optional: ausgefülltes PDF
```

## Schnellstart-Befehle

Das Projekt ist ein **uv-Projekt** (`pyproject.toml` im Root). uv verwaltet venv +
Dependencies automatisch; der Konsolen-Befehl `sep-bewertung` ist auf
`run_all:main` gemappt. Die Skripte liegen weiterhin flach in `skripte/` (kein
Package — der hatchling source-Remap installiert sie als Top-Level-Module, daher
funktionieren die gegenseitigen Imports `import evaluate_team` etc. unverändert).

```bash
# Alle Teams als Excel generieren
uv run sep-bewertung

# Nur ein Team (voller Ordnername = die teams.txt-Zeile mit team-Praefix)
uv run sep-bewertung team-shannon-alpha

# Cache leeren + frische API-Daten
uv run sep-bewertung --fresh

# Mit PDF und Übersicht
uv run sep-bewertung --pdf --overview

# Tests
uv run python -m pytest skripte
```

Klassischer Weg ohne uv funktioniert weiter: `cd skripte && python run_all.py ...`.

## Wichtige Konzepte (für Claude Code)

### 1. Heuristik vs. LLM

Jede Analyse-Funktion in `evaluate_team.py` liefert ein Dict:

```python
{
    "criterion": "User Stories / Issues ordentlich erstellt",
    "max": 3,
    "score": 1,             # Heuristik-Score (Python-berechnet)
    "label": "Grobe Mängel",
    "reason": "39 User Stories. 7/39 im 'As a...' Format ...",  # Heuristik-Text
    "details": {
        "with_acceptance": 39,
        # ...
        "llm_review": {     # LLM-Zweitmeinung (optional)
            "score": 1,
            "reason": "Die Stories zeigen gemischte Qualität..."
        }
    }
}
```

**Wichtig:** Heuristik und LLM sind getrennt. Der Heuristik-Score steht in `score`. Der LLM-Score steht in `details.llm_review.score`. Sie beeinflussen sich gegenseitig **nicht** auf der Datenebene. Im Excel landen sie in getrennten Spalten (C=Heur, D=LLM).

### 2. Excel-Layout (9 Spalten)

| Spalte | Inhalt               | Datenherkunft                               |
| ------ | -------------------- | ------------------------------------------- |
| A      | Kategorie            | Hartcodiert in `CATEGORIES`                 |
| B      | Kriterium            | `result["criterion"]`                       |
| C      | Heur-Score           | `result["score"]`                           |
| D      | LLM-Score            | `result["details"]["llm_review"]["score"]`  |
| E      | Max                  | `result["max"]`                             |
| F      | Deine Bewertung      | **User-Eingabe**, vorausgefüllt mit C       |
| G      | Anmerkungen          | **User-Eingabe**, leer                      |
| H      | Begründung Heuristik | `result["reason"]`                          |
| I      | Begründung LLM       | `result["details"]["llm_review"]["reason"]` |

Am Ende stehen Summen-Zeilen:

- "GESAMT" — `SUM(F)` der "Deine Bewertung"-Spalte
- "GESAMT (LLM-Hybrid)" — `SUM(IF(D="",C,D))` — nimmt LLM wo vorhanden, sonst Heuristik

### 3. Beim Re-Generieren: alte Werte bleiben erhalten

`build_xlsx.py` liest vor dem Schreiben die bestehende Excel ein (`extract_manual_values`), schreibt ein `.bak`, generiert neu, und merged dann die manuell geänderten Werte aus F und G zurück (`merge_manual_values_into_workbook`). Dein Bewertungs-Fortschritt geht beim Neu-Lauf nicht verloren.

### 4. Caching

Zwei Caches, plattformneutral im OS-Temp-Verzeichnis (Linux meist `/tmp`, Windows
`%TEMP%`). Per Umgebungsvariable `SEP_CACHE_DIR` überschreibbar. Unterordner:

- `<temp>/sep_gitlab_api_cache/` — alle GitLab-API-Antworten als JSON
- `<temp>/sep_llm_cache/` — LLM-Antworten mit TTL aus `config.yaml` (default 7 Tage)

(Dazu noch `<temp>/sep_repos/` für die Klone und `<temp>/sep_gitlab_data/`.)
`evaluate_team.py` und `llm.py` leiten die Basis identisch ab, daher löscht
`--fresh` **beide** Caches. Am einfachsten zum Leeren: `python run_all.py --fresh`.

### 5. LLM-Modelle

Default: **Claude Haiku 4.5** (`claude-haiku-4-5-20251001`) für alle Inhaltsprüfungen — billig und schnell.

Ausnahme: **Sonnet 4.6** (`score_with_model()`) für die zwei Calls mit Code-Verständnis:
- **Issue ↔ Code Konsistenz** in `analyze_sprint_goals` (Story vs. MR-Diff).
- **Code-Qualität** in `analyze_code_quality_llm` (von `analyze_code_clean` aufgerufen): liest die größten Produktions-Source-Files und prüft sie auf größere Mängel. Modell konfigurierbar über `llm.code_quality_model` (auf Haiku setzbar).

Kosten pro Team-Lauf (mit allen LLM-Features): **~0,22 USD** (genaue Aufschlüsselung in `docs/llm-integration.md` — die maßgebliche Quelle). Mit Cache-Hit ~0.

### 6. Geheimnisse

`/.env` enthält:

```
GITLAB_TOKEN=glpat-xxxxx
ANTHROPIC_API_KEY=sk-ant-xxxxx
```

**NIE committen!** Steht in `.gitignore`. Vorlage zum Kopieren: `.env.example` (darf ins Git). Für Altinstallationen mit `.gitlab-config` greift weiterhin ein Loader-Fallback. Wenn weder `.env` noch `.gitlab-config` da sind, crasht das Skript mit einem klaren Hinweis.

Wenn `ANTHROPIC_API_KEY` leer oder Dummy ist, fällt das Tool auf reine Heuristik zurück (siehe `llm.py` → `DUMMY_KEYS`).

## Wenn du was änderst

### Nach jeder Aufgabe committen

Nach Abschluss einer Aufgabe wird **immer** sauber committed — inklusive aller geänderten Dateien: Skripte, Docs, `.wolf/`-Dateien (memory, cerebrum, anatomy, buglog), CLAUDE.md, Settings etc.

Kein "fast fertig"-Commit. Alle zusammengehörenden Änderungen in einem Commit, aussagekräftige Message. `.env`, `.env.local`, `teams/**/*.xlsx`, `teams/**/*.pdf` und `.bak`-Dateien nie committen (stehen im `.gitignore`).

```powershell
# Alle Änderungen prüfen
git status

# Gezielt stagen (nie git add -A, um Secrets-Slip zu vermeiden)
git add CLAUDE.md skripte/evaluate_team.py docs/nutzung.md .wolf/memory.md  # etc.

# Commit
git commit -m "kurze beschreibung was getan wurde"
```

### Schwellen anpassen

→ `skripte/config.yaml`. Beispiel: `thresholds.user_stories.full_score_ratio: 0.85`

Weitere config-Blöcke (alle mit Defaults == bisherigem Verhalten):
- `languages:` — Sprach-Registry (Dateiendungen für LOC, Test-Globs/-Marker, Comment-Marker) für die sprachunabhängige LOC-/Test-/Struktur-Erkennung.
- `vendor_dirs:` — Verzeichnisse, die bei LOC-/Test-Scans ausgeschlossen werden.
- `tutors:` — Usernamen-Fragmente, die bei der Team-Größe nicht mitzählen (statt hartcodiert).
- `run.team_workers:` — Parallelität in `run_all.py` über die Teams (Default 4).
- `llm.temperature:` — Sampling-Temperatur (Default 0 = reproduzierbare Scores).

### Neue Analyse hinzufügen

→ Funktion `analyze_xxx(...)` in `evaluate_team.py` schreiben, im `CATEGORIES`-Mapping einbinden und in `collect_results()` (in `evaluate_team.py`) aufrufen. `collect_results()` ist die zentrale Stelle, die alle `analyze_*`-Aufrufe bündelt — `run_all.py` und `build_xlsx.py` rufen beide nur noch `collect_results()` auf, du musst sie nicht mehr einzeln anfassen. Pattern beachten: `return {"criterion": "...", "max": N, "score": ..., "reason": ..., "details": {"llm_review": ...}}`.

### Neue LLM-Funktion

→ Eine Helper-Funktion `analyze_xxx_llm(...)` in `evaluate_team.py` schreiben (siehe `analyze_commit_substance` als Vorbild), die `llm.score(prompt, scale_max, system=...)` aufruft. Dann in der Haupt-Analyse über `details.llm_review` einbinden.

### Excel-Layout ändern

→ `skripte/build_xlsx.py`. Spalten-Verschiebungen erfordern Anpassung an mehreren Stellen: Header, Zeilen-Schreibung, Conditional Formatting, Summen-Formeln, `extract_manual_values` und `merge_manual_values_into_workbook`.

## Mount-Sync-Hinweis

Beim Entwickeln im Cowork-Modus mit dem Mount-FS kam es vor, dass Schreibvorgänge mittendrin unterbrochen wurden. Wenn `evaluate_team.py` oder eines der anderen Skripte syntaktisch kaputt aussieht (`SyntaxError: '(' was never closed` am Dateiende), wurde wahrscheinlich nur ein Teil geschrieben. Lösung: das Stück nochmal anfügen.

In einem normalen Filesystem (lokales Git, kein Mount) tritt das nicht auf.

## Bekannte Limitierungen

1. **Release ausführbar** prüft nur Strukturindikatoren (Compose/Dockerfile/CI), nicht den tatsächlichen Start. Du musst es selbst hochfahren.
2. **Issue ↔ Code** funktioniert nur wenn die MRs `Closes #N` in der Description haben. Andere Konventionen werden übersehen.
3. **Epics** werden über das Label `type::epic` erkannt. Die Verlinkung zu User Stories wird aus drei Quellen vereinigt: Issue-Referenzen (`#N`) im Beschreibungstext **plus** den nativen GitLab-Work-Item-Widgets „Child items" (Hierarchie) und „Linked items" (`relates_to`) — letztere via GraphQL geholt (`fetch_epic_links`), da der REST-`/issues`-Endpoint sie nicht enthält. Verlinkungen außerhalb dieser drei Quellen werden übersehen.
4. **Heuristik-Schwellen** sind auf das SS26 kalibriert. Bei abweichendem Team-Workflow könnten sie nachjustiert werden müssen.

## Wenn was nicht klappt

Siehe `docs/troubleshooting.md` für die häufigsten Probleme.

---

### Öffentliches Repo — was draußen bleiben MUSS

Dieses Repo ist als **öffentliches** Repo gedacht (nur der Tool-Code). Die History
wurde dafür bewusst neu aufgesetzt, damit keine Altdaten in alten Commits liegen.
Folgendes darf **niemals** committet werden (steht in `.gitignore`):

- `.env` / `.gitlab-config` / `*.token` — GitLab-Token + Anthropic-API-Key
- `skripte/team_mapping.json` — zeigt mit echten Pfaden/IDs auf die Studi-Repos
  (Vorlage zum Kopieren: `skripte/team_mapping.example.json`)
- `teams/team-*/` — alle Team-Vorlagen, ausgefüllten Prüfungs-PDFs und generierten
  Bewertungen (Studentendaten); ebenso `teams/Uebersicht_alle_Teams.xlsx`

Vor jedem Push prüfen (Checkliste unten). Gezielt stagen statt `git add -A`.

> Hinweis: Die Heuristik-Schwellen sind damit öffentlich einsehbar. Wer das nicht
> will, kann das Repo stattdessen privat lassen und Kollegen als Collaborator
> einladen (`gh repo add-collaborator <user>/sep-bewertung <kollege>`).

**GitHub via gh CLI (einfachster Weg):**

```powershell
# gh CLI: https://cli.github.com/
gh repo create sep-bewertung --public --source=. --remote=origin --push
```

**GitHub manuell:**

1. Auf https://github.com/new ein **Public** Repo namens `sep-bewertung` anlegen (kein Description, kein README erzeugen)
2. Dann lokal:

```powershell
git remote add origin git@github.com:<USERNAME>/sep-bewertung.git
git push -u origin main
```

### Vor dem ersten Push doppelt prüfen

```powershell
# Sind die geheimen Files wirklich ignoriert?
git status

# In der Ausgabe sollten .env, .gitlab-config und git_token.txt NICHT auftauchen.
# (.env.example DARF auftauchen — das ist die committbare Vorlage.)
# Wenn doch -> .gitignore checken, ggf. mit "git rm --cached <datei>" wieder entfernen.

git ls-files | findstr /i "gitlab-config token"
# Sollte LEER sein
git ls-files | findstr /r /c:"^\.env$"
# Sollte LEER sein (.env.example darf hier nicht matchen, weil $ ans Ende ankert)

# Keine Studentendaten getrackt?
git ls-files | findstr /i ".xlsx .pdf team_mapping.json"
# Sollte LEER sein bis auf assets/Templates/*.pdf (leere Vorlagen)
#   und skripte/team_mapping.example.json

# Keine echten Studi-Repo-Pfade/IDs im Code oder in der History?
git grep -i "student_projects" $(git rev-list --all)
# Sollte LEER sein
```
