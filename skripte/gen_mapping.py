#!/usr/bin/env python3
"""
Generiert skripte/team_mapping.json aus einer Liste von Teamnamen.

Eingaben:
- skripte/teams.txt (gitignored): ein Teamname pro Zeile (Kurzname, mit oder
  ohne fuehrendes "team-"). '#' leitet einen Kommentar ein, Leerzeilen werden
  ignoriert. Vorlage: skripte/teams.example.txt.
- .env (gitignored): GITLAB_TOKEN, GITLAB_GROUP (Parent-Namespace) und
  GITLAB_COHORT (Default-Kohorten-Token, der im GitLab-Projektnamen steckt, aber
  nicht im lokalen Ordnernamen). Der Cohort ist pro Team in teams.txt
  ueberschreibbar (Teams koennen zu verschiedenen Tutorien gehoeren).

Pro Team wird der GitLab-Projektpfad gebaut
    {GITLAB_GROUP}/team-{cohort}-{short}
(cohort = Default aus .env oder pro Zeile in teams.txt) und ueber die GitLab-API
(GET /projects/<urlencoded path>) zu ID/URLs aufgeloest.
Das Ergebnis wird idempotent in team_mapping.json gemerged (bestehende Eintraege
werden aktualisiert, nicht gelistete bleiben erhalten). Vor dem Schreiben wird
ein .bak angelegt.

Ausfuehren (aus skripte/):
    python gen_mapping.py            # nutzt skripte/teams.txt
    python gen_mapping.py <pfad>     # alternative Listendatei
"""

import json
import sys
import urllib.parse
from pathlib import Path

import evaluate_team as ev

OUTPUTS = ev.OUTPUTS
MAPPING_PATH = OUTPUTS / "team_mapping.json"
DEFAULT_LIST = OUTPUTS / "teams.txt"

# Felder eines Mapping-Eintrags (Reihenfolge = Schreib-Reihenfolge im JSON).
ENTRY_KEYS = (
    "local_folder",
    "gitlab_path",
    "gitlab_id",
    "name",
    "http_url",
    "ssh_url",
    "web_url",
)


# ============================================================
# Reine Funktionen (netzfrei, unit-getestet)
# ============================================================

def _strip_team(token):
    """Fuehrendes 'team-' entfernen (case-insensitive)."""
    if token.lower().startswith("team-"):
        return token[len("team-"):]
    return token


def parse_line(line, default_cohort):
    """Eine Zeile der Teamliste zu (short, cohort) parsen.

    Unterstuetzte Formen (Inline-'#'-Kommentare und Leerzeilen erlaubt):
      - '<short>'                -> (short, default_cohort), z.B. 'bit'/'team-bit'
      - '<short> <cohort>'       -> (short, cohort), z.B. 'poetical lovelace'
      - 'team-<cohort>-<short>'  -> (short, cohort), voller GitLab-Name

    Gibt None fuer Leer-/Kommentarzeilen zurueck. Hinweis: bei einem einzelnen
    Token mit Bindestrich wird die erste Komponente als Cohort gedeutet; Teams
    mit Bindestrich im Kurznamen daher die Zwei-Token-Form nutzen.
    """
    line = line.split("#", 1)[0].strip()
    if not line:
        return None
    parts = line.split()
    if len(parts) >= 2:
        short = _strip_team(parts[0])
        return (short, parts[1]) if short else None
    token = _strip_team(parts[0])
    if "-" in token:
        cohort, short = token.split("-", 1)
        return (short, cohort)
    return (token, default_cohort) if token else None


def read_teams(path, default_cohort):
    """Teamliste lesen -> deduplizierte (short, cohort)-Paare in Datei-Reihenfolge.

    Dedupliziert nach short (der lokale Ordnername muss eindeutig sein); das
    erste Vorkommen gewinnt.
    """
    teams = []
    seen = set()
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        parsed = parse_line(raw, default_cohort)
        if parsed and parsed[0] not in seen:
            seen.add(parsed[0])
            teams.append(parsed)
    return teams


def project_path(group, cohort, short):
    """Vollen GitLab-Projektpfad bauen: {group}/team-{cohort}-{short}."""
    return f"{group}/team-{cohort}-{short}"


def entry_from_project(proj, short):
    """API-Projektantwort + Kurzname -> Mapping-Eintrag.

    local_folder traegt den lokalen Ordnernamen ('team-bit'), name den vollen
    GitLab-Projektnamen ('team-shannon-bit'). gitlab_path/URLs kommen direkt aus
    der API (maszgeblich).
    """
    pwn = proj["path_with_namespace"]
    return {
        "local_folder": f"team-{short}",
        "gitlab_path": pwn,
        "gitlab_id": proj["id"],
        "name": pwn.rsplit("/", 1)[-1],
        "http_url": proj["http_url_to_repo"],
        "ssh_url": proj["ssh_url_to_repo"],
        "web_url": proj["web_url"],
    }


def merge_entries(existing, new_entries):
    """Idempotenter Merge nach local_folder.

    Bestehende Eintraege werden durch gleichnamige neue ersetzt, neue angehaengt,
    nicht gelistete behalten. Ergebnis ist stabil nach local_folder sortiert.
    """
    by_folder = {e["local_folder"]: e for e in existing}
    for e in new_entries:
        by_folder[e["local_folder"]] = e
    return [by_folder[k] for k in sorted(by_folder)]


# ============================================================
# Netz + I/O
# ============================================================

def fetch_project(group, cohort, short, token):
    """GitLab-Projekt fuer einen Kurznamen aufloesen (ohne Cache, frische IDs)."""
    path = project_path(group, cohort, short)
    encoded = urllib.parse.quote(path, safe="")
    url = f"{ev.GITLAB_HOST}/api/v4/projects/{encoded}"
    return ev._http_get(url, token)


def _require(cfg, key, hint):
    val = cfg.get(key)
    if not val:
        raise SystemExit(
            f"FEHLER: {key} fehlt in .env. {hint}\n"
            f"(Vorlage: .env.example)"
        )
    return val


def write_mapping(entries):
    """Mapping schreiben, vorher .bak des alten Standes anlegen."""
    if MAPPING_PATH.exists():
        bak = MAPPING_PATH.with_suffix(MAPPING_PATH.suffix + ".bak")
        bak.write_text(MAPPING_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    MAPPING_PATH.write_text(
        json.dumps(entries, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def main(argv):
    list_path = Path(argv[1]) if len(argv) > 1 else DEFAULT_LIST
    if not list_path.exists():
        raise SystemExit(
            f"FEHLER: Teamliste {list_path} nicht gefunden.\n"
            f"Kopiere skripte/teams.example.txt zu skripte/teams.txt und trage "
            f"die Teamnamen ein."
        )

    cfg = ev.load_config()
    token = _require(cfg, "GITLAB_TOKEN", "Trage dein GitLab-Token ein.")
    group = _require(
        cfg, "GITLAB_GROUP",
        "Parent-Namespace der Team-Projekte, z.B. "
        "ude-sse/sep-summer-2026/student_projects.",
    )
    default_cohort = _require(
        cfg, "GITLAB_COHORT",
        "Default-Kohorten-Token im GitLab-Projektnamen, z.B. shannon. "
        "Pro Team in teams.txt ueberschreibbar.",
    )

    teams = read_teams(list_path, default_cohort)
    if not teams:
        raise SystemExit(f"FEHLER: Keine Teamnamen in {list_path}.")

    resolved = []
    failures = []
    for short, cohort in teams:
        try:
            proj = fetch_project(group, cohort, short, token)
            entry = entry_from_project(proj, short)
            resolved.append(entry)
            print(f"  OK  team-{short:<14} -> {entry['gitlab_path']} (id {entry['gitlab_id']})")
        except Exception as e:  # noqa: BLE001 - pro Team weitermachen
            failures.append((short, e))
            print(f"  XX  team-{short:<14} ({cohort}) -> {e}", file=sys.stderr)

    if resolved:
        existing = []
        if MAPPING_PATH.exists():
            existing = json.loads(MAPPING_PATH.read_text(encoding="utf-8"))
        merged = merge_entries(existing, resolved)
        write_mapping(merged)
        print(f"\n{MAPPING_PATH.name}: {len(merged)} Eintraege geschrieben.")

    print(f"\nFertig: {len(resolved)} aufgeloest, {len(failures)} Fehler.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
