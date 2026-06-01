# `teams/` — Team-Ordner (Inhalte sind NICHT im Repo)

Pro bewertetem Team liegt hier ein Ordner `teams/team-<name>/`. Diese Ordner
enthalten **Studentendaten** (Prüfungs-Vorlagen, ausgefüllte PDFs, generierte
Bewertungen) und sind deshalb per `.gitignore` vom Versionieren ausgeschlossen —
dieses Repo ist öffentlich.

Lege die Ordner lokal selbst an. Erwartetes Layout pro Team:

```
teams/team-<name>/
├── Artifacts Exam <name>.pdf      # offizielle Vorlage (lokal hinterlegen)
├── Team Exam <name>.pdf           # Vorlage mündliche Prüfung
├── Bewertung_team-<name>.xlsx     # generiert von build_xlsx.py
└── Bewertung_team-<name>.pdf      # optional, mit --pdf

teams/Uebersicht_alle_Teams.xlsx   # optional, mit --overview
```

Die leeren Original-Vorlagen findest du unter `assets/Templates/`. Welche Teams
verarbeitet werden, steuert `skripte/team_mapping.json` (Vorlage:
`skripte/team_mapping.example.json`).
