# SEP-Bewertungspipeline

Automatisierte Bewertung studentischer Software-Engineering-Praktikum-Projekte (SEP) an der UDE. Zieht GitLab-Repos plus Issues/MRs/Wiki, wendet 20 heuristische Analysen und 11 LLM-Inhaltsprüfungen darauf an, und schreibt pro Team einen Excel-Bewertungsbogen mit Auto-Vorschlag, LLM-Zweitmeinung und Platz für deine manuelle Bewertung.

## Quickstart

Voraussetzung ist [uv](https://docs.astral.sh/uv/) — es verwaltet venv und
Dependencies automatisch, kein manuelles `pip install` mehr nötig.

```bash
# Config anlegen: .env.example kopieren und Werte eintragen
cp .env.example .env
# Danach in .env eintragen:
#   GITLAB_TOKEN=glpat-xxxxx
#   ANTHROPIC_API_KEY=sk-ant-xxxxx   (optional)

# Alle Teams bewerten (uv legt beim ersten Lauf venv + Deps automatisch an)
uv run sep-bewertung

# Nur ein Team
uv run sep-bewertung team-entropy

# Mit PDF-Ausfüllung und Übersicht
uv run sep-bewertung --pdf --overview

# Cache leeren + frische API-Daten
uv run sep-bewertung --fresh
```

<details>
<summary>Ohne uv (klassischer Weg)</summary>

```bash
pip install openpyxl pypdf PyYAML tqdm
cd skripte
python run_all.py --pdf --overview
```
</details>

## Doku

| Datei | Was drin |
|---|---|
| `CLAUDE.md` | Briefing für Claude Code (KI-Assistent) — wichtige Konzepte und Pattern |
| `docs/nutzung.md` | Wie du die Pipeline benutzt |
| `docs/funktionsweise.md` | Wie es intern funktioniert |
| `docs/bewertungskriterien.md` | Was jedes Kriterium misst und warum |
| `docs/llm-integration.md` | LLM-Calls im Detail, Kosten |
| `docs/troubleshooting.md` | Häufige Probleme |
| `Bewertungs-Methodik.md` | Methodik-Überblick (Legacy, im docs/ besser strukturiert) |

## Was rauskommt

Pro Team eine Excel-Datei mit 9 Spalten:

| Spalte | Inhalt |
|---|---|
| A | Kategorie (Sprintdoku / Code-Qualität / …) |
| B | Kriterium |
| C | Heuristik-Score (Auto-Vorschlag) |
| D | LLM-Score (Zweitmeinung) |
| E | Maximal-Punkte |
| F | **Deine Bewertung** (gelb, editierbar, vorausgefüllt mit C) |
| G | Anmerkungen (gelb, editierbar) |
| H | Begründung Heuristik |
| I | Begründung LLM |

Mit zwei Summen am Ende: "GESAMT" (deine Punkte) und "GESAMT (LLM-Hybrid)" (was rauskäme wenn du immer dem LLM folgst wo eines existiert).

## Bei Re-Lauf bleiben deine Eintragungen erhalten

Wenn du `python run_all.py` ein zweites Mal laufen lässt nachdem du in F und G manuell editiert hast, werden diese Werte beim Re-Bauen übernommen — und es gibt ein `.xlsx.bak` als Sicherheit. Manuelle Bewertungen gehen nicht verloren.

## Kosten

Mit Cache-Hit: ~0 USD. Frischer Lauf für alle 6 Teams: ~1 USD. Siehe `docs/llm-integration.md`.

## Lizenz

MIT für die Skripte. Die Original-PDF-Vorlagen sind Eigentum der UDE.
