# Nutzung

Praktische Anleitung wie du die Pipeline für eine SEP-Bewertung verwendest. Wenn du wissen willst **wie sie intern funktioniert**, siehe `funktionsweise.md`. Wenn du wissen willst **was jedes Kriterium misst und warum**, siehe `bewertungskriterien.md`.

## Voraussetzungen einmalig einrichten

### 1. uv installieren

Das Projekt ist ein [uv](https://docs.astral.sh/uv/)-Projekt. uv verwaltet venv und
Dependencies automatisch — du musst nichts mehr von Hand mit `pip` installieren.
Installation von uv siehe https://docs.astral.sh/uv/getting-started/installation/.

Beim ersten `uv run sep-bewertung ...` (siehe unten) legt uv automatisch ein
`.venv` an und installiert `openpyxl`, `pypdf`, `PyYAML` und `tqdm` aus
`pyproject.toml`. Python ≥ 3.9 genügt; uv besorgt bei Bedarf selbst eine passende
Version.

> Ohne uv geht es auch klassisch: `pip install openpyxl pypdf PyYAML tqdm`, dann
> `cd skripte && python run_all.py ...`.

### 2. Git und ein GitLab Personal Access Token

Settings → Access Tokens auf der GitLab-Instanz. Scopes mindestens `read_api` + `read_repository`.

### 3. (Optional) Anthropic API Key

Für die LLM-gestützten Inhaltsprüfungen brauchst du einen Anthropic-API-Key (`https://console.anthropic.com/settings/keys`). Ohne Key fällt das Tool auf rein heuristische Bewertung zurück, der Rest funktioniert weiter.

### 4. `.env` anlegen

Im Wurzelverzeichnis (nicht in `skripte/`!) liegt `.env.example` als Vorlage. Kopiere sie und trage deine echten Werte ein:

```bash
cp .env.example .env
# dann .env bearbeiten:
#   GITLAB_TOKEN=glpat-xxxxxxxxxxxx
#   ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxx   (optional)
```

Die Datei `.env` steht in `.gitignore` und darf nicht ins Git. `.env.example` darf committet werden (enthält nur Platzhalter).

Für Altinstallationen mit `.gitlab-config` greift ein Fallback — neue Setups sollten aber `.env` nutzen.

### 5. `skripte/team_mapping.json` befüllen

Liste der Teams mit Mapping lokaler Ordner → GitLab-Projekt. Es gibt zwei Wege:

#### Variante A (empfohlen): automatisch aus einer Teamliste erzeugen

`gen_mapping.py` löst pro Team die GitLab-ID/URLs über die API auf, du musst sie
nicht von Hand abtippen.

1. In `.env` zusätzlich zu `GITLAB_TOKEN` eintragen (Vorlage in `.env.example`):

   ```
   GITLAB_GROUP=ude-sse/sep-summer-2026/student_projects   # Parent-Namespace
   ```

2. `skripte/teams.example.txt` nach `skripte/teams.txt` kopieren und pro Team
   eine Zeile eintragen: den **kombinierten GitLab-Namen** `cohort-kurzname`
   (z. B. `shannon-bit`), mit oder ohne führendes `team-` (`#` für Kommentare).
   `teams.txt` ist gitignored.

   Daraus wird das GitLab-Projekt `{GITLAB_GROUP}/team-<cohort>-<kurzname>`; der
   lokale Ordner heißt `team-<kurzname>` (der Kurzname = Teil nach dem ersten
   `-` ist eindeutig). Teams aus **verschiedenen Tutorien/Kohorten** stehen
   einfach mit ihrem jeweiligen Cohort-Präfix in derselben Liste, z. B.
   `lovelace-poetical`.

3. Generieren:

   ```bash
   uv run python skripte/gen_mapping.py            # nutzt skripte/teams.txt
   uv run python skripte/gen_mapping.py <pfad>     # alternative Listendatei
   ```

   Der Lauf ist idempotent: bestehende Einträge werden aktualisiert, nicht
   gelistete bleiben erhalten, vorher wird ein `team_mapping.json.bak` angelegt.
   Teams, die GitLab nicht findet (z.B. Tippfehler), werden gemeldet, brechen den
   Lauf aber nicht ab.

#### Variante B: manuell

Kopiere `skripte/team_mapping.example.json` nach `skripte/team_mapping.json` und
trage deine echten Werte ein (die `team_mapping.json` ist per `.gitignore`
ausgeschlossen, damit keine Studi-Repo-Pfade ins öffentliche Repo gelangen):

```json
[
  {
    "local_folder": "team-beispiel",
    "gitlab_path": "<deine-gruppe>/student_projects/team-beispiel",
    "gitlab_id": 0000,
    "name": "team-beispiel",
    "http_url": "https://gitlab.example.com/<deine-gruppe>/student_projects/team-beispiel.git",
    "ssh_url": "git@gitlab.example.com:<deine-gruppe>/student_projects/team-beispiel.git",
    "web_url": "https://gitlab.example.com/<deine-gruppe>/student_projects/team-beispiel"
  }
]
```

Tipp: bei einer neuen Prüfungsrunde reicht es, `teams.txt` und den `.env`-Wert
`GITLAB_GROUP` anzupassen und Variante A erneut laufen zu lassen.

### 6. Pro Team einen lokalen Ordner anlegen

```
teams/team-beispiel/
├── Artifacts Exam team-beispiel.pdf
└── Team Exam team-beispiel.pdf
```

Das sind die offiziellen Vorlagen — wenn du sie nicht hast, einfach die Templates aus dem Wurzelverzeichnis kopieren.

## Tägliche Bedienung

### Alle Teams auf einmal generieren

```bash
uv run sep-bewertung
```

Was passiert: für jedes Team in `team_mapping.json` wird das Repo aktualisiert, alle API-Daten gezogen, 20 Analysen durchgeführt, das LLM zur Inhaltsprüfung befragt, und eine Excel `Bewertung_team-X.xlsx` im jeweiligen Team-Ordner geschrieben.

### Nur ein Team

```bash
uv run sep-bewertung team-entropy
```

Identischer Ablauf, aber nur für eines.

### Cache leeren (echte Re-Analyse)

```bash
uv run sep-bewertung --fresh
```

Bei Folgeläufen werden GitLab-API-Antworten aus `<temp>/sep_gitlab_api_cache/` und LLM-Antworten aus `<temp>/sep_llm_cache/` benutzt (`<temp>` = OS-Temp-Verzeichnis, per `SEP_CACHE_DIR` überschreibbar) — was sehr schnell ist, aber bei aktiv weiterentwickelten Repos die alten Daten zeigt. `--fresh` löscht beide Caches.

### Mit PDF-Formular und Übersichts-Excel

```bash
uv run sep-bewertung --pdf --overview
```

- `--pdf` befüllt zusätzlich das offizielle PDF-Formular (`Bewertung_<team>.pdf`): Teamname, angekreuzte Punkte (Checkboxes nach der "Deine Bewertung"-Spalte F), Gesamtpunktzahl und Abschnitts-Zwischensummen. Kommentare/Anmerkungen werden bewusst **nicht** ins PDF geschrieben.
- `--overview` baut am Ende `Uebersicht_alle_Teams.xlsx` im `teams/`-Ordner: alle Teams nebeneinander, mit Farbskala. Gut zum Sortieren oder als Sanity-Check.

### Nur die PDFs aus den vorhandenen Excels erzeugen (ohne Analyse)

Wenn die `Bewertung_<team>.xlsx` schon existieren (z. B. nach manueller Bewertung) und du nur die PDF-Formulare (neu) ausfüllen willst — **ohne** git-Fetch, GitLab-API oder LLM:

```bash
uv run sep-bewertung --pdf-only            # alle Teams
uv run sep-bewertung --pdf-only team-bit   # nur ein Team
```

Das liest ausschließlich die jeweilige Excel (Spalte F + die Kriterien-Namen) und braucht weder `GITLAB_TOKEN` noch `ANTHROPIC_API_KEY`. Für ein einzelnes Team geht alternativ direkt `uv run python skripte/fill_pdf.py team-bit`.

## Die Excel verstehen und ausfüllen

Wenn du eine `Bewertung_team-X.xlsx` öffnest, siehst du Sheet "Bewertung" mit 9 Spalten:

| Spalte | Was bedeutet's |
|---|---|
| A: Kategorie | Sprintdoku, Code-Qualität, Implementierte Funktionalität, Prozessqualität |
| B: Kriterium | Originaltext aus dem Prüfungsprotokoll |
| C: Heur-Score | Was die Heuristik vorschlägt (Zähl-Algorithmus) |
| D: LLM-Score | Was das LLM vorschlägt (qualitative Bewertung) — kann leer sein wenn keine LLM-Analyse für das Kriterium existiert |
| E: Max | Maximalpunktzahl laut PDF |
| F: Deine Bewertung | **Hier trägst du die finale Punktzahl ein**, vorausgefüllt mit C |
| G: Anmerkungen | **Hier schreibst du Anmerkungen** für den mündlichen Teil oder das offizielle Protokoll |
| H: Begründung Heuristik | Genau **wie** die Heuristik zu C kommt (Zahlen, Verhältnisse) |
| I: Begründung LLM | **Warum** das LLM zu D kommt (qualitative Einschätzung) |

### Spalte F: "Deine Bewertung"

- Bei jedem Kriterium ist F mit dem Heuristik-Score (C) vorausgefüllt.
- Wenn du einen anderen Wert eintippst, **wird die Zelle rot/fett markiert** (Conditional Formatting). So siehst du beim Drüberscrollen welche Werte du selbst angepasst hast.
- Bei den zwei manuellen Kriterien (Team-Organisation, Selbstständigkeit) steht ein `x` als Vorgabe — das musst du durch eine Zahl ersetzen. Solange das `x` steht, weißt du dass die Zeile noch nicht erledigt ist. `x` wird in den Summen ignoriert (Excel `SUM` zählt Text-Zellen als 0).

### Summenzeilen unten

- "GESAMT" — `SUM(F)`, deine finale Summe.
- "GESAMT (LLM-Hybrid)" — was rauskäme wenn du immer dem LLM folgst wo es eine Meinung hat, sonst der Heuristik. Reine Info zur Orientierung — beeinflusst keinen anderen Wert.

### Sheet "Zusatzinfos"

Hier stehen Daten ohne direkten Score, aber wichtig für die manuellen Bewertungs-Kriterien:

- Commit-Verteilung pro Autor (mit Gini-Koeffizient — wenn 1 Person 80% macht, ist das ein Red Flag für Team-Organisation)
- CI-Pipeline-Status (wenn rot, ist "Release ausführbar" wahrscheinlich überschätzt)
- MR-Größen + Time-to-Merge
- Velocity-Trend pro Woche
- Aktivitäts-Verteilung (erkennt Last-Minute-Hacking)
- Sanity-Check (LLM-Kommentar zur Gesamtkonsistenz)

## Bewertungen aktualisieren (neuer Stand des Repos)

Wenn das Team seit dem letzten Lauf Commits gemacht hat und du neu bewerten willst:

```bash
uv run sep-bewertung --fresh
```

`--fresh` wischt den Cache, damit garantiert frische Daten kommen. **Deine bereits manuell eingetragenen Werte und Anmerkungen werden automatisch übernommen** — das Skript liest die alte Excel ein, schreibt ein `.bak`-Backup, generiert neu und merged deine manuellen Änderungen zurück.

Wenn du deine alten Werte komplett wegwerfen willst, lösche vorher die `Bewertung_*.xlsx` selbst.

## Was tun wenn das LLM verrückt spielt

- LLM gibt einen anscheinend falschen Score → in der "Begründung LLM" steht warum. Du entscheidest selbst was du in Spalte F einträgst. Die LLM-Spalten sind nur Vorschläge.
- LLM-Calls fehlen ganz (Spalte D leer) → entweder kein API-Key gesetzt, der Key ist abgelaufen, oder es gab einen API-Fehler. Im Log siehst du `LLM HTTPError` Meldungen. Den Rest der Pipeline beeinflusst das nicht.
- LLM-Antworten kosten zu viel → in `skripte/config.yaml` kannst du `llm.enabled: false` setzen, dann läuft das Tool rein heuristisch.

## Was tun nach der Bewertung

1. Excel pro Team füllen (Spalte F + Anmerkungen + die zwei manuellen Kriterien).
2. (Optional) `uv run sep-bewertung --pdf` laufen lassen, dann hast du die offiziellen PDF-Formulare ausgefüllt — Teamname, Checkboxes nach Spalte F, Gesamtpunktzahl und Zwischensummen. Anmerkungen (Spalte G) bleiben in der Excel, sie werden nicht ins PDF übernommen.
3. Die PDFs ausdrucken/digital weitergeben wie es die Prüfungsordnung verlangt.

## Wichtige Backup-Hinweise

- Bei jedem Lauf wird `Bewertung_team-X.xlsx.bak` als Backup geschrieben (überschreibt die vorherige .bak).
- Wenn du eine wirklich wichtige Zwischenversion sichern willst, kopiere die Excel manuell weg bevor du nochmal generierst.
- Das `.bak` ist im `.gitignore` ausgeschlossen.
