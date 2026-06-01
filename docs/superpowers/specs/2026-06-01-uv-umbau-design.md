# Design: Umbau auf ein uv-Projekt (Variante „Konsolen-Befehl")

**Datum:** 2026-06-01
**Ziel:** Nutzung vereinfachen — statt manuellem `pip install ...` + `cd skripte` +
`python run_all.py` soll ein einziger Befehl genügen, der venv und Dependencies
automatisch verwaltet:

```
uv run sep-bewertung                          # alle Teams (Excel)
uv run sep-bewertung team-entropy             # nur ein Team
uv run sep-bewertung --pdf --overview         # mit PDF + Übersicht
uv run sep-bewertung --fresh                  # Cache leeren
```

## Entscheidungen

- **Umfang:** Minimal + sauberer Konsolen-Befehl. Die flache Modul-Struktur in
  `skripte/` bleibt unangetastet (kein Repackaging in ein `src/`-Package).
- **Python-Floor:** `>=3.9` (kein 3.10+-Syntax im Code verwendet — geprüft).
- **Dependencies fest statt optional:** `openpyxl`, `pypdf`, `pyyaml`, `tqdm`
  werden alle vier deklariert, damit `--pdf` und der Fortschrittsbalken
  out-of-the-box funktionieren (heute sind pypdf/tqdm lazy importiert).
- **`uv.lock` wird committet** (reproduzierbare Tool-Umgebung).

## Änderungen

### 1. Neue Datei `pyproject.toml` (Repo-Root)

- `[project]`: `name = "sep-bewertung"`, `requires-python = ">=3.9"`,
  `dependencies = ["openpyxl", "pypdf", "pyyaml", "tqdm"]`.
- `[project.scripts]`: `sep-bewertung = "run_all:main"`.
- Build-Backend **hatchling** mit Source-Remap, damit die flachen Imports
  (`import evaluate_team`, `from build_xlsx import build_xlsx`, …) **unverändert**
  weiterfunktionieren — `skripte/*.py` werden als Top-Level-Module installiert:

  ```toml
  [tool.hatch.build.targets.wheel]
  sources = ["skripte"]
  include = ["skripte/*.py"]
  exclude = ["skripte/test_*.py"]
  ```

- `[dependency-groups] dev = ["pytest"]` (optional; Tests laufen auch mit
  stdlib-`unittest`).

### 2. Kein Code-Umbau

`run_all.py` besitzt bereits `main()` + `if __name__ == "__main__": main()` und
liest `sys.argv[1:]` direkt — funktioniert als Konsolen-Befehl unverändert.

### 3. `.gitignore`

`.venv/` ergänzen.

### 4. Docs

`README.md`, `CLAUDE.md` (Schnellstart) und `docs/nutzung.md` auf
`uv run sep-bewertung` umstellen; den alten `pip`/`cd skripte`-Weg als Fallback
kurz erwähnen.

## Verifikation

Heikelster Punkt ist der `sources`-Remap (editable install unter Windows).
Vor der Fertigmeldung:

- `uv sync` läuft fehlerfrei.
- `uv run sep-bewertung --pdf-only team-nonexistent` lädt Module + Mapping ohne
  Netz/Token (erwartet sauberen „kein Mapping"-Fehler, keinen ImportError).
- `uv run python -m unittest` (aus `skripte/`) — bestehende Tests grün.
