# Design: Auto-Generierung von `team_mapping.json` aus einer Teamnamen-Liste

Datum: 2026-06-01
Status: Approved (Design)

## Ziel

Ein eigenständiges Skript erzeugt `skripte/team_mapping.json` aus einer
gitignorierten Liste von Teamnamen (`skripte/teams.txt`). Pro Team wird der
GitLab-Projekteintrag (ID, URLs, Pfad) über die GitLab-API aufgelöst, statt ihn
von Hand zu pflegen. Mehrfaches Ausführen ist idempotent.

## Eingaben

### `skripte/teams.txt` (gitignored)
- Eine Zeile pro Team.
- Inhalt: Kurzname, mit oder ohne führendes `team-` (`bit` **oder** `team-bit`).
- `#` leitet einen Kommentar ein, Leerzeilen werden ignoriert.
- Committbare Vorlage: `skripte/teams.example.txt`.

### `.env` (bereits gitignored)
Neue Schlüssel (Vorlage in `.env.example`):
- `GITLAB_GROUP=ude-sse/sep-summer-2026/student_projects` — Parent-Namespace, unter
  dem die Team-Projekte liegen.
- `GITLAB_COHORT=shannon` — Kohorten-Token, der im GitLab-Projektnamen steckt,
  aber nicht im lokalen Ordnernamen.
- `GITLAB_TOKEN=…` — bereits vorhanden, für die API-Auth.

## Ableitung pro Zeile (Beispiel `bit`)

| Feld           | Wert                                         | Quelle                                          |
| -------------- | -------------------------------------------- | ----------------------------------------------- |
| `short`        | `bit`                                         | Zeile, führendes `team-` entfernt               |
| `local_folder` | `team-bit`                                     | `team-{short}`                                  |
| GitLab-Pfad    | `…/student_projects/team-shannon-bit`          | `{GITLAB_GROUP}/team-{cohort}-{short}`          |
| `gitlab_id`    | aus API                                        | `id`                                            |
| `gitlab_path`  | `…/student_projects/team-shannon-bit`          | `path_with_namespace` (API, maßgeblich)         |
| `http_url`     | aus API                                        | `http_url_to_repo`                              |
| `ssh_url`      | aus API                                        | `ssh_url_to_repo`                               |
| `web_url`      | aus API                                        | `web_url`                                       |
| `name`         | `team-shannon-bit`                             | voller GitLab-Name = letztes Segment von `path_with_namespace` |

Wichtig: `name` trägt den **vollen GitLab-Projektnamen** (mit Kohorten-Token),
`local_folder` den **lokalen** Ordnernamen (ohne Token).

## Ablauf

1. Wiederverwendung aus `evaluate_team.py` (kein Code-Duplikat):
   `load_config()` (liest `.env`, inkl. neuer Keys), `GITLAB_HOST`, `_http_get()`,
   `OUTPUTS` (= `skripte/`).
2. `teams.txt` lesen, Zeilen normalisieren (`short`), Duplikate dedupen.
3. Pro Team: GitLab-Pfad bauen → `GET {GITLAB_HOST}/api/v4/projects/<urlencoded path>`
   **ohne Cache** (frische IDs/URLs). `urllib.parse.quote(path, safe="")` für das
   `%2F`-Encoding der Slashes.
4. Idempotenter Merge in `team_mapping.json`:
   - bestehende Datei laden (falls vorhanden),
   - `.bak` schreiben (wie `build_xlsx.py`),
   - Einträge per `local_folder` mergen: vorhandene aktualisieren, neue anhängen,
     nicht in der Liste stehende Einträge **behalten**,
   - stabil nach `local_folder` sortiert schreiben (2-Space-Indent, UTF-8).
5. Fehlerbehandlung: 404 / Netzwerkfehler pro Team sammeln, restliche Teams
   weiterverarbeiten. Abschluss-Report `✓ N aufgelöst / ✗ M Fehler` auf stdout,
   Exit-Code ≠ 0, wenn mindestens ein Team fehlschlug.

## Aufruf

```bash
cd skripte
python gen_mapping.py            # nutzt skripte/teams.txt
python gen_mapping.py <pfad>     # alternative Listendatei
```

## Geänderte / neue Dateien

- `skripte/gen_mapping.py` — neu (das Skript)
- `skripte/teams.example.txt` — neu (committbare Vorlage)
- `.gitignore` — `+ skripte/teams.txt`
- `.env.example` — `+ GITLAB_GROUP`, `+ GITLAB_COHORT`
- `docs/nutzung.md` — kurzer Abschnitt zur Mapping-Generierung

## Fehlerfälle & Verhalten

- Fehlende `.env` / `GITLAB_TOKEN`: klare Meldung (über `load_config`).
- Fehlende `GITLAB_GROUP` / `GITLAB_COHORT`: klare Meldung mit Hinweis auf
  `.env.example`.
- Fehlende `teams.txt`: Hinweis, `teams.example.txt` zu kopieren.
- Projekt nicht gefunden (404): pro Team melden, nicht abbrechen.

## Bewusst nicht im Scope (YAGNI)

- Automatisches Enumerieren aller Projekte der Parent-Gruppe.
- Anlegen lokaler Team-Ordner.
- Integration als `run_all.py`-Flag (kann später leicht ergänzt werden).
