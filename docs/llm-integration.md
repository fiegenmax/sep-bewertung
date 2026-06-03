# LLM-Integration

Wo das LLM eingebunden ist, welche Prompts es bekommt, was es kostet.

## Verwendete Modelle

Stand: Mai 2026.

- **Claude Haiku 4.5** (`claude-haiku-4-5-20251001`) — Default für alle Inhaltsprüfungen. Billig ($1 / $5 pro Mio Tokens) und schnell.
- **Claude Sonnet 4.6** (`claude-sonnet-4-6`) — für **Issue-vs-Code-Konsistenz** und die **Code-Qualitäts-Zweitmeinung**. Code verstehen ist anspruchsvoll, Haiku ist da nicht zuverlässig genug. Sonnet kostet $3 / $15 pro Mio Tokens.

Konfigurierbar in `skripte/config.yaml` → `llm.model` (Default-Modell) bzw. `llm.code_quality_model` (Modell für den Code-Qualitäts-Review; auf das Haiku-Modell setzen, um zu sparen).

## Wo das LLM überall hingt

12 LLM-Calls pro Team-Lauf (wenn alle Daten vorhanden sind):

| # | Call | Wo eingebunden | Modell | Score-Skala | Input ca. | Output ca. |
|---|---|---|---|---|---|---|
| 1 | User-Story-Inhalt | `analyze_user_stories` | Haiku | 0–3 | 4k | 0.6k |
| 2 | Meeting-Substanz | `analyze_meeting_docs` | Haiku | 0–1 | 6k | 0.6k |
| 3 | Release-Notes-Substanz | `analyze_release_changelog` | Haiku | 0–3 | 3k | 0.6k |
| 4 | Release vs. Commits | `analyze_release_changelog` (zweite Phase, gemittelt) | Haiku | 0–3 | 5k | 0.6k |
| 5 | Code-Kommentar-Qualität | `analyze_code_docs` | Haiku | 0–2 | 4k | 0.6k |
| 6 | Test-Substanz | `analyze_tests` | Haiku | 0–3 | 7.5k | 0.6k |
| 7 | Commit-Message-Substanz | `analyze_commit_messages` | Haiku | 0–3 | 2k | 0.4k |
| 8 | **Issue ↔ Code** | `analyze_sprint_goals` | **Sonnet** | 0–3 | 30–50k | 3k |
| 9 | Branching-Pattern | `analyze_branching` | Haiku | 0–2 | 2k | 0.4k |
| 10 | Code-Review-Substanz | `analyze_code_reviews` | Haiku | 0–1 | 2k | 0.6k |
| 11 | Sanity-Check | `analyze_sanity_check` (am Ende) | Haiku | 0–2 | 3k | 0.8k |
| 12 | **Code-Qualität** | `analyze_code_clean` → `analyze_code_quality_llm` | **Sonnet** | 0–3 | ~12k | 0.6k |

Call 12 sampelt die **größten** Produktions-Source-Files (Test-/Vendor-Dateien ausgeschlossen) und prüft sie auf größere Mängel (God-Classes, Duplikation, toter Code, verschluckte Exceptions). Er ist die Code-*Qualitäts*-Sicht, komplementär zur Heuristik in `analyze_code_clean`, die nur Repo-*Hygiene* (committeter Müll, Lint-Config, TODOs) zählt und den Code nie liest. Stichproben-Limits in `config.yaml` → `llm_sampling.code_quality_*`.

**Total pro Team:** ~80-100k Input-Tokens + ~10k Output-Tokens (Haiku) + ~42-62k + 3.6k (Sonnet).

**Kostenrechnung:**
- Haiku-Anteil: ~0.08 USD
- Sonnet-Anteil: ~0.14 USD (Issue↔Code + Code-Qualität)
- **Total: ~0.22 USD pro Team-Lauf**

Bei 6 Teams: **~1.30 USD**. Bei 13 Teams: ~2.85 USD.

Mit Cache-Hit (Re-Run mit gleichem Input): nahezu 0 USD.

## Wie die LLM-Calls technisch aussehen

Alle gehen über `LLMClient.score(prompt, scale_max, system=...)` (oder `score_with_model` für Sonnet). Das hängt automatisch ans System-Prompt an:

> WICHTIG: Antworte AUSSCHLIESSLICH als EIN JSON-Objekt (nicht Liste!) mit genau diesen Feldern: `{"score": <integer 0-X>, "reason": "<kurze Begruendung 1-3 Saetze>"}`.

Wenn die Antwort eine Liste mit mehreren Objekten ist (kommt vor), wird der Mittelwert genommen.

Wenn das Parsing fehlschlägt, wird `None` zurückgegeben — die zugehörige Spalte im Excel bleibt leer, alles andere funktioniert weiter.

## Beispiel-Prompts

### User-Story-Inhalt

System:
> Du bewertest die inhaltliche Qualitaet von User Stories in einem Studi-SEP-Projekt. Achte besonders auf: (1) Sind die Akzeptanzkriterien testbar/messbar? (2) Beschreibt 'so that …' einen echten Nutzerwert? (3) Sind die Stories vernuenftig geschnitten? Score 0=ueberwiegend schwach, 1=mittel, 2=gut, 3=hervorragend.

User-Prompt: 5 zufällige User Stories mit Titel + Beschreibung.

### Issue vs. Code (Sonnet)

System:
> Du pruefst ob User Stories sauber implementiert wurden. Achte auf: (1) Alle Akzeptanzkriterien adressiert? (2) Scope-Creep? (3) Passt der Code zur Story-Beschreibung? Score 0=passt nicht, 1=teilweise, 2=ueberwiegend, 3=sauber.

User-Prompt: 4 Story+MR-Diff-Paare. Diffs werden auf 1500 Zeichen pro File und 6000 Zeichen pro Paar gekappt.

### Code-Review-Substanz

System:
> Du bewertest Code-Review-Kommentare in Merge Requests. Substantiell = konkrete Fragen, Verbesserungsvorschlaege, Bug-Hinweise. Schwach = nur 'LGTM', Smileys, allgemeine Bestaetigungen. Score 0=ueberwiegend schwach, 1=mindestens einige substantielle Reviews.

User-Prompt: 5 Sample-Review-Kommentare (nicht vom MR-Autor).

### Sanity-Check

System:
> Pruefe Konsistenz: (1) widerspruechliche Einschaetzungen? (2) Diskrepanzen zwischen Kategorien? (3) plausibler Gesamtscore? Score 0=Inkonsistenzen, 1=plausibel mit Auffaelligkeiten, 2=konsistent.

User-Prompt: Liste aller 17 Heuristik-Bewertungen mit Score und Begründung (~3k Zeichen).

### Code-Qualität (Sonnet)

System:
> Du beurteilst die Code-QUALITAET, nicht die Repo-Hygiene. Achte NUR auf GROESSERE Maengel: God-Classes/ueberlange Funktionen, Copy-Paste-Duplikation, auskommentierter/toter Code, verschluckte Exceptions oder fehlende Fehlerbehandlung, irrefuehrende Namen, fehlende Trennung von Verantwortlichkeiten. Stil-Nitpicks (Einrueckung, Quotes, Zeilenlaenge) IGNORIEREN. Score 0=gravierende Maengel, 1=mehrere Maengel, 2=ueberwiegend sauber, 3=durchgehend sauber.

User-Prompt: Die größten Produktions-Source-Files (Default 6, je 2500 Zeichen, gesamt 12k), Test- und Vendor-Dateien ausgeschlossen.

## Cache-Verhalten

Cache liegt in `<temp>/sep_llm_cache/` (`<temp>` = OS-Temp-Verzeichnis, per `SEP_CACHE_DIR` überschreibbar). Key ist SHA1 von `model + "|" + system_prompt + "||" + user_prompt + "||" + max_tokens`. Leere/abgebrochene Antworten werden **nicht** gecacht.

TTL aus `config.yaml` → `llm.cache_ttl_days` (default 7 Tage).

Wenn der Cache-Eintrag älter als TTL ist, wird er als nicht-vorhanden behandelt und neu angefragt.

Bei `uv run sep-bewertung --fresh` wird der gesamte Cache gelöscht.

## Wann LLM-Calls überspringen

Das LLM überspringt automatisch:
- Wenn `client.enabled = False` (kein API-Key gesetzt)
- Wenn die nötigen Daten fehlen (z.B. keine User Stories vorhanden → kein Story-LLM-Call)
- Wenn die HTTP-Anfrage fehlschlägt

Du kannst das LLM in `config.yaml` komplett deaktivieren:

```yaml
llm:
  enabled: false
```

## Wie LLM-Score und Heuristik-Score koexistieren

Die zwei Scores sind **bewusst getrennt**:

- **Heuristik-Score** (`result["score"]`) ist deterministisch — gleicher Input ergibt gleichen Output. Wird im Excel in Spalte C angezeigt und ist die Default-Vorbelegung von Spalte F ("Deine Bewertung").
- **LLM-Score** (`result["details"]["llm_review"]["score"]`) ist die qualitative Zweitmeinung. Steht im Excel in Spalte D.
- Du als Prüfer entscheidest in Spalte F welcher Wert (oder ein dritter) der finale ist.

Es gibt **keine automatische Verrechnung** zwischen Heuristik und LLM. Eine Ausnahme: in `analyze_release_changelog` werden zwei LLM-Sub-Scores (Substanz + vs.-Features) gemittelt — beide sind aber LLM, nicht Mix mit Heuristik.

### LLM-Hybrid-Summe im Excel

Am Ende des Sheets gibt es eine Info-Zeile "GESAMT (LLM-Hybrid)" mit der Formel:

```
=IF(D6="",C6,D6) + IF(D7="",C7,D7) + ... 
```

Sie zeigt was rauskäme wenn du **immer dem LLM folgst wo eines existiert**, sonst der Heuristik. Reine Orientierung, beeinflusst keinen anderen Wert.

## Eigene LLM-Checks bauen

Pattern: Eine Hilfsfunktion am unteren Ende von `evaluate_team.py` definieren, in einer der Haupt-Analyse-Funktionen einbinden:

```python
def analyze_xxx_llm(some_data, llm=None):
    if not (llm and llm.enabled):
        return None
    prompt = f"... {some_data} ..."
    system = "Du bewertest ... Score 0=X, 1=Y, 2=Z."
    return llm.score(prompt, scale_max=2, system=system)


def analyze_xxx(data, llm=None):
    # ... Heuristik-Logik ...
    llm_eval = analyze_xxx_llm(data, llm)
    return {
        "criterion": "Mein neues Kriterium",
        "max": 2,
        "score": heuristic_score,
        "reason": heuristic_reason,
        "details": {
            "...": "...",
            "llm_review": llm_eval,  # ← wichtig dass es so heißt
        }
    }
```

Die Excel-Generierung erkennt `details.llm_review` automatisch und schreibt Score+Begründung in die D/I-Spalten.

## Kosten in den Griff bekommen

Wenn die Kosten steigen sollten:

1. **Cache-TTL erhöhen** → seltener neu anfragen.
2. **Sonnet rauswerfen** — in `analyze_sprint_goals` → `use_sonnet=False`, und/oder `config.yaml` → `llm.code_quality_model` auf das Haiku-Modell setzen. Spart den Großteil des Sonnet-Anteils, verliert etwas Genauigkeit bei Code-Verständnis.
3. **Sample-Größen reduzieren** → in `analyze_user_stories` z.B. `sample_size=3` statt 5. In `analyze_issue_vs_code` z.B. `sample_size=2` statt 4.
4. **LLM komplett aus** → `config.yaml`. Heuristik bleibt voll funktionsfähig.

## Ehrlichkeitscheck: was das LLM nicht kann

- Nicht in echter Coverage-Daten substituieren — wenn die CI keine Coverage misst, weiß das LLM auch nicht ob die Tests gut sind.
- Nicht beurteilen ob ein Release wirklich startet (nur Strukturindikatoren prüfen).
- Nicht hinter die Fassade gucken — ein Team mit perfekten Issue-Beschreibungen aber katastrophalem Code bekommt vom LLM einen ehrlichen Mix-Score; du musst die Komposition selbst werten.
- Nicht plagiierten/AI-generierten Code als solchen erkennen (Versuche dazu sind heutzutage unzuverlässig und politisch heikel).
