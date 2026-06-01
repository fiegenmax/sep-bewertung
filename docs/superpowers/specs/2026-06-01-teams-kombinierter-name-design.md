# Design: teams.txt vereinfachen — Cohort raus, kombinierter Name rein

Datum: 2026-06-01
Status: Approved (Design)

Überarbeitet [`2026-06-01-gen-mapping-design.md`](2026-06-01-gen-mapping-design.md):
der dortige Cohort-Mechanismus (Default + Pro-Zeile-Override, Addendum / bug-044)
wird durch das hier beschriebene, einfachere Format ersetzt.

## Ziel

Das Eingabeformat von `skripte/teams.txt` vereinfachen. Der Cohort ist kein
eigenes Konzept mehr: pro Zeile steht **genau eine Form**, der kombinierte
GitLab-Name `cohort-kurzname` (z. B. `shannon-bit`). Der eindeutige Kurzname
(`bit`) bleibt der lokale Ordnername.

## Motivation

Das alte Format kannte drei Schreibweisen (`bit`, `bit cohort`,
`team-cohort-bit`) plus einen `GITLAB_COHORT`-Default in `.env`. Das war mehr
Mechanik als nötig. Ein bloßer Kurzname `bit` kann den echten GitLab-Pfad
`team-shannon-bit` ohnehin nicht ohne Zusatzwissen (Default-Cohort) auflösen.
Da der Kurzname eindeutig ist und der volle GitLab-Name den Cohort bereits
enthält, genügt der kombinierte Name als einzige Eingabe.

## Neues `teams.txt`-Format

- Eine Zeile pro Team = der kombinierte Name, mit oder ohne führendes `team-`:
  `shannon-bit` **oder** `team-shannon-bit`.
- `#` leitet einen (Inline-)Kommentar ein, Leerzeilen werden ignoriert.
- Committbare Vorlage: `skripte/teams.example.txt`.
- Es gibt **keine** Zwei-Token-Form (`bit cohort`) und **keinen**
  `GITLAB_COHORT`-Default mehr.

## Ableitung pro Zeile (`combined` = z. B. `shannon-bit`)

| Feld           | Wert                                  | Herleitung                                              |
| -------------- | ------------------------------------- | ------------------------------------------------------- |
| GitLab-Pfad    | `…/student_projects/team-shannon-bit` | `{GITLAB_GROUP}/team-{combined}`                        |
| Kurzname       | `bit`                                 | `combined` ohne führendes Cohort-Segment = Teil **nach dem ersten `-`** |
| `local_folder` | `team-bit`                            | `team-{kurzname}`                                        |
| `name`         | `team-shannon-bit`                    | letztes Segment von `path_with_namespace` (API)         |
| `gitlab_id`    | aus API                               | `id`                                                    |
| `gitlab_path`  | aus API                               | `path_with_namespace` (maßgeblich)                      |
| `http_url` / `ssh_url` / `web_url` | aus API           | jeweiliges API-Feld                                     |

Kurzname-Ableitung = **alles nach dem ersten `-`**: `shannon-my-team` → Kurzname
`my-team`, Ordner `team-my-team`. (Der Cohort ist immer das führende Segment.)

## Validierung

- Eine Zeile **ohne `-`** (bloßes `bit`) ist ein Fehler: das Tool kann daraus
  keinen vollständigen GitLab-Pfad bauen. Klare Meldung mit Hinweis, den
  kombinierten Namen `cohort-kurz` anzugeben. Der Lauf bricht deshalb nicht ab —
  die Zeile wird wie ein nicht auflösbares Team behandelt (gesammelter Fehler,
  Exit-Code ≠ 0).
- Dedup nach Kurzname (eindeutig); erstes Vorkommen gewinnt — wie bisher.

## Konkrete Änderungen

### `skripte/gen_mapping.py`
- `parse_line(line)` (ohne `default_cohort`) → gibt `combined` (str) oder `None`
  zurück. Entfernt die Zwei-Token-Logik und die `split("-", 1)`-Cohort-Trennung.
- Neuer Helfer `short_of(combined)` → Teil nach dem ersten `-` (oder Fehler-Sentinel
  bei fehlendem `-`).
- `read_teams(path)` → deduplizierte `combined`-Strings; `default_cohort`-Parameter
  fällt weg.
- `project_path(group, combined)` → `{group}/team-{combined}`.
- `fetch_project(group, combined, token)` entsprechend.
- `entry_from_project(proj, short)` bleibt (bekommt den abgeleiteten Kurznamen).
- `main`: `GITLAB_COHORT` nicht mehr `_require`-pflichtig; Zeilen ohne `-` als
  Fehler sammeln statt aufzulösen.

### Doku / Config (Cohort entfernen)
- `skripte/teams.example.txt` — neu beschrieben, Beispiele `shannon-alpha` etc.
- `.env.example` — `GITLAB_COHORT` raus.
- `README.md` — `GITLAB_COHORT`-Zeile + „gemischte Kohorten"-Verweis anpassen.
- `docs/nutzung.md` — Abschnitt 5 / Variante A auf neues Format umschreiben,
  `GITLAB_COHORT`-Erwähnungen entfernen.
- `CLAUDE.md` — Repo-Struktur-/Geheimnis-Hinweise erwähnen `GITLAB_COHORT` nicht
  prominent; nur falls vorhanden anpassen.

### Tests
- `skripte/test_gen_mapping.py` — TDD: erst auf neues Verhalten umstellen (rot),
  dann Code anpassen. Neue/angepasste Fälle: kombinierte Form, `team-`-Prefix,
  Kurzname-Ableitung (auch mit Bindestrich im Kurznamen), Fehler bei fehlendem `-`,
  Dedup nach Kurzname, `project_path`, `entry_from_project`, `merge_entries`
  (unverändert).

## Was gleich bleibt
- `team_mapping.json`-Schema (alle Felder, Reihenfolge).
- Idempotenter Merge nach `local_folder`, `.bak`-Schreibung.
- API-Auflösung (`GET /projects/<urlencoded path>`, ohne Cache).
- `local_folder = team-{kurzname}`.

## Bewusst nicht im Scope (YAGNI)
- Rückwärtskompatibilität zum alten Drei-Formen-Eingabeformat.
- Anlegen lokaler Team-Ordner, Enumerieren der Parent-Gruppe.
