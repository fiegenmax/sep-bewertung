# Automatische Bewertung – Methodik

> ⚠️ **VERALTET (Stand 2026-05-29).** Dieses Dokument beschreibt einen früheren
> Stand: **15** Heuristiken, ein **7-Spalten**-Excel-Layout und hartcodierte
> `/tmp`-Pfade. Aktuell sind es **20 Heuristiken + 11 LLM-Prüfungen**, ein
> **9-Spalten**-Layout (C=Heur, D=LLM, E=Max, F=Deine Bewertung, G=Anmerkungen,
> H/I=Begründungen) und plattformneutrale Cache-Pfade im OS-Temp-Verzeichnis.
> Maßgeblich sind: [`docs/funktionsweise.md`](funktionsweise.md),
> [`docs/bewertungskriterien.md`](bewertungskriterien.md),
> [`docs/llm-integration.md`](llm-integration.md) und die `CLAUDE.md` im Repo-Root.
> Die folgenden Abschnitte bleiben nur als historischer Kontext erhalten.

Diese Datei erklärt, wie die `Bewertung_<team>.xlsx`-Dateien in den Team-Ordnern entstehen, was sie messen und warum diese Heuristiken gewählt wurden. Lies sie einmal durch — danach kannst du den automatischen Vorschlägen besser vertrauen und siehst, wo du genauer hinschauen solltest.

## TL;DR

Die Skripte im `skripte/`-Ordner ziehen sich pro Team das geklonte Repo plus Daten aus der GitLab-API (Issues, Merge Requests, Wiki, Releases, Pipelines), wenden 15 automatisierte Heuristiken auf die Bewertungs-Kriterien aus dem PDF-Prüfungsprotokoll an und erzeugen eine Excel-Datei mit Bewertungsvorschlägen, Begründungen und einer Spalte für deine eigene Bewertung. Summen aktualisieren sich automatisch, ein "x" markiert Zeilen die du noch anfassen musst.

## Aufbau

```
Zwischenprüfung/
├── .env                        # GitLab-Token + Anthropic-Key (nicht ins Git!)
├── .env.example                # Template mit Platzhaltern (darf ins Git)
├── Bewertungs-Methodik.md      # diese Datei
├── Template *.pdf              # Original-Bewertungsbögen
├── skripte/
│   ├── evaluate_team.py        # Alle Analyse-Funktionen + Markdown-Generator
│   ├── build_xlsx.py           # Excel-Generator (nutzt evaluate_team.py)
│   └── team_mapping.json       # Lokaler Ordner-Name → GitLab-Projekt
└── team-<name>/
    ├── Artifacts Exam *.pdf    # Leere Original-Vorlage
    ├── Team Exam *.pdf         # Vorlage für mündliche Prüfung
    └── Bewertung_team-<name>.xlsx   # Generierter Bewertungsbogen
```

Aufruf für ein Team:

```bash
uv run python skripte/build_xlsx.py team-entropy
```

## Datenquellen

Die Bewertung kombiniert drei Quellen:

1. **Geklontes Git-Repo** (lokal nach `/tmp/repos/<repo-name>`) — Code, Commit-History, Branches, Tags, README-Dateien, Test-Verzeichnisse.
2. **GitLab-API** — Issues, Merge Requests, Wiki-Seiten, Releases, Pipelines, Boards, Mitglieder.
3. **Cached API-Antworten** (`/tmp/gitlab_api_cache/`) — beim zweiten Lauf werden API-Calls aus dem Cache bedient. Cache leeren falls neue Stände gezogen werden sollen: `rm -rf /tmp/gitlab_api_cache /tmp/repos`.

## Bewertungs-Kriterien

Die Kriterien folgen exakt dem PDF "Prüfungsprotokoll (Artefakte)". Pro Kriterium gilt: Das Skript macht einen **Vorschlag** auf Basis messbarer Signale, die Begründung steht in der Spalte "Begründung (automatisch)". Du musst nichts übernehmen — die gelbe Spalte "Deine Bewertung" ist überschreibbar.

### Sprintdokumentation (max 7 P.)

**User Stories / Issues ordentlich erstellt (0–3)**
Analysiert alle Issues mit Label `type::userstory`. Geprüft wird, ob sie das *"As a … I want … so that …"*-Format einhalten und eine Akzeptanzkriterien-Sektion enthalten. Schwelle: ≥85% beider Merkmale → 3 P.; ≥50% beider → 2 P.; ≥5 Stories vorhanden → 1 P.; sonst 0. Zusätzlich wird ausgegeben, wie viele Stories ein Story-Weight (Schätzung) haben — nur als Info, fließt nicht in den Score ein.

**Verständliche Commit-Messages (0–1)**
Durchschnittliche Länge der Commits (ohne Merges) muss ≥35 Zeichen sein. Triviale Messages (`"fix"`, `"update"`, `"wip"` etc.) dürfen <15% ausmachen. Sehr kurze (<8 Zeichen) <10%.

**Team-Meetings dokumentiert (0–1)**
Wiki-Seiten mit Datums-Titel (z.B. `18.05.2026`) oder Schlüsselwörtern (`meeting`, `sprint`, `besprechung`, `protokoll`). Zusätzlich wird der Inhalt geprüft: nur Seiten mit >150 Zeichen reinem Text (Bilder/Uploads rausgerechnet) zählen als "substantiell". ≥2 substantielle Seiten → 1 P.

**Release mit Changelog/Release-Notes (0–1)**
Es existiert ein Release auf GitLab UND die Beschreibung hat ≥200 Zeichen. Reine Tag-Erstellung ohne Notes reicht nicht.

**Sinnvolle Epics + Verlinkung (0–1)**
Issues mit Label `type::epic` müssen existieren UND mit User Stories verlinkt sein (Referenzen wie `#123` im Body, beidseitig erkannt). Schwelle: ≥3 Epics + ≥5 Verlinkungen. **Hinweis:** GitLab Free hat keine echten Epics — Teams müssen sich mit Labels + manuellen Issue-Referenzen behelfen. Wenn 0/1 erscheint trotz vieler Epics, lohnt sich ein Blick ins Issue-Board.

### Code-Qualität (max 14 P.)

**Code sinnvoll strukturiert (0–1)**
Backend/Frontend-Split vorhanden ODER ≥3 Java-Pakete ODER `src/`-Konvention. Verhindert reine Monorepos ohne Trennung.

**Code ausreichend dokumentiert (0–5)**
Punktevergabe additiv:
- Top-Level-README ist **nicht** die GitLab-Default-Vorlage und ≥500 Zeichen → +1
- README(s) in Subprojekten mit ≥1000 Zeichen → +1
- ≥3 substantielle Wiki-Seiten → +1, ≥8 → +2 (gestaffelt)
- OpenAPI/Swagger-Spec gefunden → +1
- Inline-Kommentar-Anteil im Java-Code ≥5% → +1

Inline-Kommentare werden bewusst nur "belohnt", nicht "bestraft" — gute Doku liegt oft im Wiki, nicht im Code.

**Code sauber/ohne größere Mängel (0–1)**
Negativ-Checks auf Git-Tracked-Files: `node_modules/`, Build-Artefakte (`dist/`, `target/`, `build/`), IDE-Configs (`.idea/`, `.vscode/`), `.DS_Store`, Debug-Logs, Binaries >5MB, mehr als 20 TODOs/FIXMEs, fehlende Linter/Editor-Config. Wenn auch nur eines davon zutrifft → 0.

**Tests vorhanden und sinnvoll (0–7)**
Heuristik auf 7 Stufen, additiv:
- ≥5 / ≥25 Test-Dateien → +1 / +1
- ≥5 substantielle Java-Test-Klassen → +1
- ≥80 / ≥130 `@Test`-Methoden → +1 / +1
- ≥3 substantielle Angular-Specs (nicht nur Default-Stubs!) → +1
- Wenn beide Welten viele substantielle Tests haben → +1

Default-Specs (Angular generiert `should be created` als einzigen Test) werden erkannt und nicht mitgezählt.

### Implementierte Funktionalität (max 21 P.)

**Release ausführbar (0–5)** ⚠️ **MANUELL PRÜFEN!**
Das Skript misst nur die strukturelle Bereitschaft:
- Release existiert (+1)
- Release-Notes ≥500 Zeichen (+1)
- `docker-compose` (+1)
- Backend- UND Frontend-Dockerfile (+1)
- `.gitlab-ci.yml` (+1)

**Es testet NICHT, ob das Release tatsächlich startet oder ob die Features funktionieren.** Du musst es lokal hochfahren und durchklicken.

**Sprint-Ziele erreicht (0–1)**
≥50% aller Issues geschlossen UND ≥60% der `priority::must`-Issues geschlossen. Sonst 0.

**Arbeitsumfang angemessen (0/5/10/15)**
Grobe Heuristik aus Commits, gemergten MRs, geschlossenen Issues und LoC (Java/TS/HTML/CSS, ohne `node_modules`):
- <20 Commits & <1k LoC → 0
- <60 Commits ODER <3k LoC → 5
- <120 Commits ODER <6k LoC → 10
- darüber → 15

Manuell prüfen, ob das zur Sprint-Anzahl und Team-Größe passt.

### Prozessqualität (max 4 P. automatisch + 4 P. manuell)

**GitLab-Nutzung (0–2)**
Issues haben Labels (≥85%) UND Assignees (≥70%) UND ≥50% sind geschlossen → 2. Wenn nur ≥50% gelabelt → 1.

**Branching-Workflow (0–1)**
≥10 gemergte MRs UND ≥3 Branches neben main. **Plus**: Direktpushes auf main (Commits ohne MR-Hintergrund auf der first-parent-Linie) dürfen ≤15 sein. Sonst 0 wegen "Workflow umgangen".

**Code-Reviews durchgeführt (0–1)** — verbessert seit erster Version
Schaut auf **drei** Review-Signale pro MR:
1. Reviewer wurde gesetzt
2. Formales Approval durch jemand anderen als den Autor
3. Schriftlicher Kommentar von Reviewer

Wenn ≥50% der MRs ein Approval haben ODER ≥70% irgendein Review-Signal haben → 1. Vorherige Versionen haben nur Kommentare gezählt und Teams mit reinem Approval-Workflow unfair benotet.

**Team-Organisation (0–2) und Selbstständigkeit (0–2)**
Nicht automatisierbar. Bleiben leer, du füllst sie nach der mündlichen Prüfung aus. Diese Zeilen tragen automatisch ein "x" in der Marker-Spalte, bis du Werte einträgst.

## Excel-Aufbau

Sheet **"Bewertung"** hat 7 Spalten:

| Spalte | Inhalt | Editierbar |
|---|---|---|
| A | Kategorie | nein |
| B | Kriterium | nein |
| C | Auto-Vorschlag (grau/kursiv) | nein |
| D | Max-Punkte | nein |
| E | **Deine Bewertung** (gelb, vorausgefüllt) | **ja** |
| F | Anmerkungen (gelb, leer) | **ja** |
| G | Begründung des Auto-Vorschlags | nein |

### Markierungen in der "Deine Bewertung"-Spalte (E)

**`x` als Wert** = du musst hier noch eintragen. Standardmäßig in den manuellen Kriterien (Team-Organisation und Selbstständigkeit), wo nach der mündlichen Prüfung ein Wert hin soll. Sobald du das "x" durch eine Zahl ersetzt, ist die Zeile erledigt.

**Rote, fette Zelle** (Conditional Formatting) = Wert wurde vom Auto-Vorschlag (Spalte C) **geändert**. Sobald du wieder auf den Auto-Wert zurückstellst, wird die Hervorhebung automatisch entfernt. So siehst du beim Scrollen sofort, welche Zeilen du angefasst hast.

### Summen

Zwischensummen pro Kategorie und die Gesamtsumme sind als Excel-`SUM`-Formeln auf die "Deine Bewertung"-Spalte gebaut. Sobald du einen Wert änderst, aktualisiert Excel automatisch. Text-Werte wie "x" werden von `SUM` ignoriert — die Summe zeigt also immer den Stand der bereits eingetragenen Zahlen.

Die Zwischensumme der manuellen Kriterien zeigt also 0, solange Team-Org und Selbstständigkeit noch auf "x" stehen.

Sheet **"Zusatzinfos"** enthält Daten, die keinen direkten Score haben aber für die manuellen Kriterien helfen:
- **Commit-Verteilung pro Autor** — wenn 1 Person >50% der Commits macht, ist das ein Hinweis für die "Team-Organisation"-Bewertung
- **CI-Pipeline-Status** — wenn die letzten Pipelines auf main rot sind, sollte "Release ausführbar" niedriger ausfallen als der Auto-Vorschlag suggeriert

## Wo dem Skript nicht zu trauen ist

Eingebaute Schwächen, die manuelle Prüfung erfordern:

1. **Release ausführbar** misst nur Struktur, nicht Funktion → lokal starten!
2. **Code-Doku** zählt Wiki-Seiten und READMEs, kann aber Qualität nicht beurteilen → Stichprobe ins Wiki
3. **Epics + Verlinkung** ist sehr formal (sucht `#123`-Referenzen); andere Verknüpfungs-Methoden (z.B. Task-Listen, Labels) übersieht es
4. **Arbeitsumfang** ist pure Quantität — viele kleine Refactoring-Commits schlagen genauso zu Buche wie echte Features
5. **Test-Substanz** wird über Anzahl `@Test` und `it()` geschätzt, nicht über Coverage oder Assertion-Tiefe

Generell gilt: Der Auto-Vorschlag ist eine **Vorlage**, kein Endurteil. Die Begründung in Spalte H erklärt jedes Mal, *warum* das Skript zu seinem Wert kommt — überprüfe diese Begründung, statt blind die Zahl zu übernehmen.

## Caching

Beim ersten Lauf werden alle GitLab-API-Antworten in `/tmp/gitlab_api_cache/` abgelegt. Folge-Läufe sind dadurch viel schneller (~1 Sek statt mehrerer Sekunden). Wiki-Inhalte werden parallel mit 8 Threads geladen.

Cache leeren wenn du frische Daten willst:
```bash
rm -rf /tmp/gitlab_api_cache /tmp/gitlab_data
```

Die geklonten Repos in `/tmp/repos/` werden bei Folge-Läufen via `git fetch` aktualisiert, nicht neu geklont.

## Skripte anpassen

Alle Änderungen an den Heuristiken passieren in `skripte/evaluate_team.py`. Jede `analyze_*`-Funktion gibt ein Dict mit `criterion`, `max`, `score`, `label`, `reason`, `details` zurück — wenn du Schwellen änderst, denk daran auch die `reason` anzupassen, damit die Begründung im Excel passt.

Die Excel-Generierung passiert in `skripte/build_xlsx.py`. Layout-Änderungen (Spaltenbreiten, Farben, Header-Texte) gehen dort.
