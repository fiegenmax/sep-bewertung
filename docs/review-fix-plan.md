# Review-Fix-Plan

Stand: 2026-06-02

Dieser Plan adressiert die Findings aus dem Projekt-Review. Ziel ist, zuerst Bewertungsverfaelschungen zu vermeiden und danach kleinere Bedien-/Wartbarkeitsprobleme zu bereinigen.

## 1. Repo-Update korrekt machen

**Prioritaet:** hoch

**Problem:** Bei bestehenden Clones fuehrt `clone_or_update()` nur `git fetch` aus. Der Arbeitsbaum bleibt dadurch ggf. auf einem alten Commit, waehrend Issues/MRs/Wiki frisch aus der API kommen.

**Betroffene Datei:** `skripte/evaluate_team.py`

**Vorgehen:**

1. Nach dem Fetch den Default-Branch ermitteln, bevorzugt ueber `origin/HEAD`, fallback `origin/main`, dann `origin/master`.
2. Arbeitsbaum deterministisch auf diesen Remote-Stand setzen, z. B. `git checkout -B <branch> origin/<branch>` oder `git reset --hard origin/<branch>` nur im Cache-Clone unter `SEP_CACHE_DIR`.
3. Fetch-/Checkout-Fehler nicht ignorieren, sondern mit bereinigter Fehlermeldung abbrechen.
4. Provenienz danach unveraendert aus `HEAD` lesen, damit Excel den tatsaechlich bewerteten Commit zeigt.

**Tests/Verifikation:**

1. Unit-Test mit temporarem Bare-Remote: Clone erzeugen, Remote weiter committen, `clone_or_update()` erneut ausfuehren, `HEAD` muss auf neuem Remote-Commit stehen.
2. Test fuer Fetch-Fehler: Fehler muss RuntimeError ausloesen.
3. `uv run pytest -q`

## 2. Branching-Heuristik squash-merge-fest machen

**Prioritaet:** mittel

**Problem:** `analyze_branching()` zaehlt First-Parent-Commits als Direktpushes, wenn die Commit-Message nicht mit `Merge ` beginnt. GitLab-Squash-Merges koennen dadurch falsch als Direktpushes gelten.

**Betroffene Datei:** `skripte/evaluate_team.py`

**Vorgehen:**

1. Aus gemergten MRs bekannte Merge-/Squash-SHAs sammeln (`merge_commit_sha`, `squash_commit_sha`).
2. First-Parent-Commits auf `main`/`master` gegen diese SHAs abgleichen.
3. Nur Commits zaehlen, die weder Merge-Commit noch bekannter MR-Merge-/Squash-Commit sind.
4. Reason/Details erweitern, damit sichtbar ist, wie viele Commits als MR-Squash erkannt wurden.

**Tests/Verifikation:**

1. Unit-Test mit MRs, deren `squash_commit_sha` auf der First-Parent-Linie liegt: darf nicht als Direktpush zaehlen.
2. Unit-Test fuer echten Direktcommit ohne MR-SHA: muss weiterhin gezaehlt werden.
3. `uv run pytest -q`

## 3. Wiki-Doku nach Substanz bewerten

**Prioritaet:** mittel

**Problem:** `analyze_code_docs()` vergibt Wiki-Punkte nach Anzahl der Wiki-Seiten. Kurze Stub-/Backlog-Seiten koennen dadurch als substanzielle Dokumentation zaehlen.

**Betroffene Dateien:** `skripte/evaluate_team.py`, ggf. Tests in `skripte/test_evaluate.py`

**Vorgehen:**

1. Signatur von `analyze_code_docs(repo, wikis, llm=None)` auf optionales `wiki_contents=None` erweitern.
2. In `collect_results()` das bereits geladene `wiki_contents` an `analyze_code_docs()` uebergeben.
3. Wiki-Seiten fuer Code-Doku nur zaehlen, wenn ihr bereinigter Text eine Mindestlaenge erreicht.
4. Mindestlaenge in `config.yaml` unter `thresholds.code_docs` konfigurierbar machen, mit Default fuer Rueckwaertskompatibilitaet.
5. Reason/Details von `wiki_pages` auf `substantial_wiki_pages` erweitern.

**Tests/Verifikation:**

1. Test: viele kurze Wiki-Seiten ergeben keinen Wiki-Doku-Bonus.
2. Test: mehrere laengere Wiki-Seiten ergeben wie erwartet 1 bzw. 2 Punkte.
3. Bestehende Tests fuer `analyze_code_docs()` an neue optionale Signatur anpassen.
4. `uv run pytest -q`

## 4. Uebersicht ohne Token erlauben

**Prioritaet:** niedrig

**Problem:** `build_overview.main()` laedt `.env`, obwohl fuer die Uebersicht nur vorhandene Excel-Dateien und `team_mapping.json` gebraucht werden.

**Betroffene Datei:** `skripte/build_overview.py`

**Vorgehen:**

1. Unbenutztes `cfg = ev.load_config()` entfernen.
2. Sicherstellen, dass `uv run python skripte/build_overview.py` ohne `.env` funktioniert, solange `team_mapping.json` und Excel-Dateien existieren.

**Tests/Verifikation:**

1. Kleinen Unit-Test oder Smoke-Test fuer `build_overview.build_overview()` ohne Config.
2. `uv run pytest -q`

## Abschluss

Nach allen Fixes:

1. `uv run pytest -q`
2. Optional ein echter Lauf fuer ein Team mit `uv run sep-bewertung <team>` und Kontrolle der Provenienz-Zeile im Excel.
3. Bei geaenderten Bewertungsheuristiken kurz in `docs/bewertungskriterien.md` oder `docs/funktionsweise.md` dokumentieren.
