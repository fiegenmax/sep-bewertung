#!/usr/bin/env python3
"""
Generiert skripte/team_mapping.json aus einer Liste von Teamnamen.

Eingaben:
- skripte/teams.txt (gitignored): ein Teamname pro Zeile (Kurzname, mit oder
  ohne fuehrendes "team-"). '#' leitet einen Kommentar ein, Leerzeilen werden
  ignoriert. Vorlage: skripte/teams.example.txt.
- .env (gitignored): GITLAB_TOKEN, GITLAB_GROUP (Parent-Namespace) und
  GITLAB_COHORT (Kohorten-Token, der im GitLab-Projektnamen steckt, aber nicht
  im lokalen Ordnernamen).

Pro Team wird der GitLab-Projektpfad gebaut
    {GITLAB_GROUP}/team-{GITLAB_COHORT}-{short}
und ueber die GitLab-API (GET /projects/<urlencoded path>) zu ID/URLs aufgeloest.
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

def normalize_short(line):
    """Eine Zeile der Teamliste zu einem Kurznamen normalisieren.

    Entfernt Inline-/ganze Kommentare, umgebenden Whitespace und ein fuehrendes
    'team-'. Gibt None fuer Leer- und Kommentarzeilen zurueck.
    """
    # Inline-Kommentar abschneiden
    line = line.split("#", 1)[0].strip()
    if not line:
        return None
    if line.lower().startswith("team-"):
        line = line[len("team-"):]
    return line or None


def read_team_names(path):
    """Teamliste lesen -> deduplizierte Kurznamen in Datei-Reihenfolge."""
    shorts = []
    seen = set()
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        short = normalize_short(raw)
        if short and short not in seen:
            seen.add(short)
            shorts.append(short)
    return shorts


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
    cohort = _require(
        cfg, "GITLAB_COHORT",
        "Kohorten-Token im GitLab-Projektnamen, z.B. shannon.",
    )

    shorts = read_team_names(list_path)
    if not shorts:
        raise SystemExit(f"FEHLER: Keine Teamnamen in {list_path}.")

    resolved = []
    failures = []
    for short in shorts:
        try:
            proj = fetch_project(group, cohort, short, token)
            entry = entry_from_project(proj, short)
            resolved.append(entry)
            print(f"  OK  team-{short:<14} -> {entry['gitlab_path']} (id {entry['gitlab_id']})")
        except Exception as e:  # noqa: BLE001 - pro Team weitermachen
            failures.append((short, e))
            print(f"  XX  team-{short:<14} -> {e}", file=sys.stderr)

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
