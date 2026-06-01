# Troubleshooting

Häufige Probleme und Workarounds.

## "Workspace still starting"

Beim ersten Bash-Aufruf in einer Cowork-Session. Einfach ein paar Sekunden warten und nochmal versuchen.

## `git clone` schlägt fehl

```
fatal: Authentication failed for 'https://gitlab.git.nrw/...'
```

Token ist nicht gesetzt oder abgelaufen. Prüfe `.env`:

```bash
grep ^GITLAB_TOKEN .env
# Sollte zeigen: GITLAB_TOKEN=glpat-...
```

Token-Scopes: mindestens `read_api` und `read_repository`.

## LLM-Calls geben keine Antworten zurück

Schaue im Log nach `LLM HTTPError`:

- **401** → API-Key falsch oder abgelaufen. In `.env` `ANTHROPIC_API_KEY=` anpassen.
- **429** → Rate-Limit. Anthropic erlaubt einige Anfragen pro Minute. Lass dem Lauf Zeit oder reduziere Sample-Größen.
- **500/503** → Anthropic-Backend kurzzeitig nicht erreichbar. Nochmal versuchen.

Wenn permanent kein Key da ist und du das LLM nicht nutzen willst:

```yaml
# skripte/config.yaml
llm:
  enabled: false
```

## Excel-Datei lässt sich nicht überschreiben

```
PermissionError: [Errno 13] Permission denied: 'Bewertung_team-X.xlsx'
```

Wahrscheinlich hast du die Datei in Excel/LibreOffice offen. Schließen, nochmal versuchen.

## Manuelle Werte sind weg

Du hast `--fresh` benutzt oder die `.xlsx.bak` ist überschrieben. Beim nächsten Lauf werden alte Werte aus der **aktuellen** `Bewertung_team-X.xlsx` übernommen, nicht aus der `.bak`. Wenn die aktuelle Datei nicht mehr existierte (z.B. weil du sie gelöscht hast), wird sie frisch gebaut.

Generell vor jedem Re-Lauf: prüfe ob die `.bak` noch sichern was du brauchst.

## Conditional Formatting in F-Spalte zeigt nichts an

Wenn alle "Deine Bewertung"-Zellen rot/fett sind obwohl du sie nicht geändert hast: das passiert wenn `C` (Heur-Score) leer ist (kommt vor bei den manuellen Kriterien Team-Org/Selbstständigkeit). Die Bedingung ist `AND(C<>"",F<>C)` — leere C-Zellen werden eigentlich ignoriert.

Wenn das Verhalten trotzdem komisch ist: Excel-Conditional-Formatting hat Eigenheiten bei verschiedenen Versionen. Die Logik hat keinen Bug, aber das Rendering kann abweichen.

## Pipeline ist sehr langsam

Erster Lauf für ein neues Team kann 1-2 Minuten dauern (clone + alle API-Calls + LLM-Calls). Folge-Läufe sollten <10 Sekunden sein dank Cache.

Wenn auch der zweite Lauf langsam ist:
- LLM-Cache leeren? `--fresh` löscht beide Caches (GitLab + LLM). Wenn du nur GitLab neu willst aber den LLM-Cache behalten: lösche gezielt den Ordner `sep_gitlab_api_cache` im OS-Temp-Verzeichnis — Linux/macOS: `rm -rf "$TMPDIR/sep_gitlab_api_cache"` (bzw. `/tmp/sep_gitlab_api_cache`); Windows (PowerShell): `Remove-Item -Recurse -Force "$env:TEMP\sep_gitlab_api_cache"`.
- Sehr großes Repo? Bei einem Mega-Repo dauert `git fetch` länger.

## Sync-Problem im Cowork-Mount

Symptom: Python-Skript wirft `SyntaxError` am Dateiende obwohl die letzte sichtbare Funktion vollständig aussieht.

Erklärung: Der Cowork-Mount synct manchmal nur einen Teil einer geschriebenen Datei. Das Resultat ist eine abgeschnittene Datei.

Lösung: Datei nochmal speichern. Wenn du im Cowork-Modus arbeitest, kannst du im Bash:

```bash
tail -5 skripte/evaluate_team.py
```

Wenn das letzte was du siehst nicht in einer logischen Stelle endet, ist die Datei abgeschnitten.

In einem echten lokalen Git-Repo passiert das nicht.

## PDF-Formular ist nach Ausfüllen leer

Adobe Reader rendert manchmal die programmatisch ausgefüllten Form-Werte nicht ohne weiteres. Workaround:

1. PDF in Adobe Reader öffnen
2. Eine Form-Field anklicken und mit Tab durchgehen — die Werte erscheinen

Alternative: `NeedAppearances` ist im PDF-Schreibcode gesetzt, sollte das fixen — aber je nach Reader-Version klappt das nicht immer.

## Übersichts-Excel ist leer

`build_overview.py` liest die existierenden `Bewertung_team-X.xlsx`-Dateien ein. Wenn die nicht existieren, ist auch die Übersicht leer.

Erst pro Team eine Bewertung generieren, dann `python build_overview.py` (oder `python run_all.py --overview`).

## `coverage_pct` ist immer None

Das Tool liest Coverage aus dem `coverage`-Feld der GitLab-Pipeline-Resource. Wenn die CI das nicht setzt (z.B. weil JaCoCo nicht eingebunden ist), ist es None.

Falls dein Team einen Coverage-Report erzeugt aber nicht über das Pipeline-Feld berichtet: das müsste man als Artifact downloaden und parsen — nicht implementiert.

## Heuristik-Schwellen wirken zu streng/locker

Anpassbar in `skripte/config.yaml` unter `thresholds:`. Diese Schwellen sind jetzt **wirksam**: `evaluate_team.py` liest sie über den `thr("pfad.key", default)`-Accessor; fehlt ein Wert, greift der eingebaute Default (= der bisherige Wert). Du kannst also einzelne Schwellen überschreiben, ohne Code zu ändern. Beispiel: `thresholds.user_stories.full_score_ratio: 0.9` macht die volle Punktzahl strenger.

## `team-ewd` (oder ein anderes Team) wird nicht bewertet

Es gibt einen Ordner `teams/team-ewd/` (mit den Original-Templates), aber **keinen
Eintrag in `skripte/team_mapping.json`** — `run_all.py` iteriert ausschliesslich
ueber das Mapping, ein Ordner ohne Eintrag wird daher uebersprungen.

Beheben: einen Eintrag nach dem Muster der anderen Teams ergaenzen. Die fehlenden
Felder (`gitlab_id`, `gitlab_path`, `http_url`, `ssh_url`, `web_url`) holst du aus
GitLab (Projekt-Seite bzw. `GET /api/v4/projects?search=team-ewd`):

```json
{
  "local_folder": "team-ewd",
  "gitlab_path": "<deine-gruppe>/student_projects/team-<...>-ewd",
  "gitlab_id": <ID aus GitLab>,
  "name": "team-<...>-ewd",
  "http_url": "https://gitlab.example.com/<deine-gruppe>/student_projects/team-<...>-ewd.git",
  "ssh_url": "git@gitlab.example.com:<deine-gruppe>/student_projects/team-<...>-ewd.git",
  "web_url": "https://gitlab.example.com/<deine-gruppe>/student_projects/team-<...>-ewd"
}
```

## "FEHLER bei team-XYZ: ..."

`run_all.py` fängt Fehler pro Team ab. Im Output siehst du dann eine Liste der fehlgeschlagenen Teams.

Häufige Gründe:
- Repo leer oder kein `main`-Branch.
- API-Aufrufe schlagen fehl (Permission auf Projekt fehlt).
- Cache enthält invalides JSON aus früherem Lauf — `--fresh` lösen das.

## Auf macOS/Linux: `python` statt `python3`

Die README/Doku spricht von `python run_all.py`. Auf macOS/Linux ist das oft `python3`. Anpassen oder einen Alias setzen.

## Was nicht gehen wird

- Bewertung **anderer Module** ohne Anpassung. Die Heuristiken sind auf das UDE-SEP-Format kalibriert (Labels, Wiki-Konventionen, Issue-Templates).
- Bewertung **privater Repos ohne Token-Zugriff**. Das Tool nutzt die GitLab-API; ohne Token sieht es nichts.
- **Notebooks / Jupyter** als Code-Inhalt. Wird als binär behandelt.
