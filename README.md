# SEP-Bewertungspipeline

Automatisierte Bewertung studentischer Software-Engineering-Praktikum-Projekte (SEP) an der UDE. Zieht GitLab-Repos plus Issues/MRs/Wiki, wendet 20 heuristische Analysen und 11 LLM-Inhaltsprüfungen darauf an, und schreibt pro Team einen Excel-Bewertungsbogen mit Auto-Vorschlag, LLM-Zweitmeinung und Platz für deine manuelle Bewertung.

## Quickstart

Einzige Voraussetzung ist [uv](https://docs.astral.sh/uv/getting-started/installation/)
— es verwaltet venv und Dependencies automatisch, kein manuelles `pip install`
nötig.

### Einmalig einrichten

**1. Zugangsdaten** — `.env.example` nach `.env` kopieren und ausfüllen:

```bash
cp .env.example .env
```

```
GITLAB_TOKEN=glpat-xxxxx          # Pflicht (Scopes: read_api + read_repository)
ANTHROPIC_API_KEY=sk-ant-xxxxx    # optional — ohne läuft es rein heuristisch
GITLAB_GROUP=<deine-gruppe>/...   # Parent-Namespace der Studi-Repos
```

**2. Team-Mapping erzeugen** — legt fest, welche Teams bewertet werden. Es zeigt
auf echte Studi-Repos und ist daher gitignored, du erzeugst es lokal:

```bash
cp skripte/teams.example.txt skripte/teams.txt   # je Team "cohort-kurzname" eintragen
uv run python skripte/gen_mapping.py             # löst GitLab-IDs/URLs per API auf
```

> Pro Zeile der kombinierte GitLab-Name (z. B. `shannon-bit`). Details und die
> manuelle Alternative: siehe [`docs/nutzung.md`](docs/nutzung.md).

### Bewerten

```bash
uv run sep-bewertung                       # alle Teams
uv run sep-bewertung team-shannon-alpha    # nur ein Team (voller Ordnername)
uv run sep-bewertung --pdf --overview      # + PDF-Formular + Übersichts-Excel
uv run sep-bewertung --fresh               # Cache leeren (frische API-Daten)
uv run sep-bewertung --pdf-only            # nur PDFs aus vorhandenen Excels (kein API/LLM)
```

> `--pdf-only` ist der Schnellpfad: keine GitLab-API, kein LLM, keine Analyse —
> es füllt nur die PDF-Formulare aus den schon vorhandenen `Bewertung_<team>.xlsx`.
> Voraussetzung: die Excel und die Vorlagen-PDF müssen im Team-Ordner liegen.
> Funktioniert ebenso für ein einzelnes Team (`uv run sep-bewertung --pdf-only team-shannon-alpha`).

Beim allerersten Lauf legt uv automatisch das venv an und installiert die
Dependencies — danach starten die Läufe sofort. Pro Team entsteht eine
`Bewertung_<team>.xlsx` im jeweiligen Team-Ordner.

<details>
<summary>Ohne uv (klassischer Weg)</summary>

```bash
pip install openpyxl pypdf PyYAML tqdm
cd skripte
python gen_mapping.py            # einmalig, siehe oben
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

Wenn du `uv run sep-bewertung` ein zweites Mal laufen lässt nachdem du in F und G manuell editiert hast, werden diese Werte beim Re-Bauen übernommen — und es gibt ein `.xlsx.bak` als Sicherheit. Manuelle Bewertungen gehen nicht verloren.

## Kosten

Mit Cache-Hit: ~0 USD. Frischer Lauf für alle 6 Teams: ~1 USD. Siehe `docs/llm-integration.md`.

## Lizenz

MIT für die Skripte. Die Original-PDF-Vorlagen sind Eigentum der UDE.
