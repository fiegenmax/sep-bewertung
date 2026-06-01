#!/usr/bin/env python3
"""
Generiert die Excel-Bewertung fuer alle Teams aus team_mapping.json.

Usage:
    python run_all.py                       # alle Teams (Excel)
    python run_all.py team-entropy          # nur ein Team
    python run_all.py --fresh               # Cache vorher loeschen (frische API-Daten)
    python run_all.py --pdf                 # zusaetzlich PDF-Formular ausfuellen
    python run_all.py --overview            # zusaetzlich Uebersichts-Excel
    python run_all.py --pdf --overview      # alles auf einmal
    python run_all.py --pdf-only            # NUR PDFs aus vorhandenen Excels (keine Analyse)
    python run_all.py --pdf-only team-bit   # dito, nur ein Team

Backup: Vor dem Ueberschreiben wird automatisch eine .bak.xlsx angelegt.
Manuell eingetragene Werte und Notizen aus dem letzten Lauf werden uebernommen.

Fortschritt: Mit installiertem `tqdm` wird ein Fortschrittsbalken angezeigt;
ohne tqdm laeuft alles weiter (eine Statuszeile pro fertigem Team).
"""

import sys
import json
import shutil
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import evaluate_team as ev
from build_xlsx import build_xlsx

# tqdm ist optional (wie pypdf in fill_pdf): ohne Installation faellt der
# Fortschrittsbalken weg und es wird wie bisher pro fertigem Team geprintet.
try:
    from tqdm import tqdm
except ImportError:
    tqdm = None


def process(entry, token, llm_client=None, yaml_cfg=None):
    lf = entry["local_folder"]
    lines = [f"-> {lf}: git fetch + API + Analyse ..."]
    results = ev.collect_results(entry, token, llm_client=llm_client, yaml_cfg=yaml_cfg)
    out = ev.TEAMS / lf / f"Bewertung_{lf}.xlsx"
    build_xlsx(lf, entry["gitlab_path"], entry["web_url"], results, out)
    lines.append(f"   OK: {out.name}")
    return "\n".join(lines)


def _select_entries(args, mapping):
    """Alle Teams oder (bei Argument) ein bestimmtes."""
    if args:
        target = args[0]
        entries = [m for m in mapping if m["local_folder"] == target]
        if not entries:
            print(f"FEHLER: Kein Mapping fuer {target}")
            sys.exit(1)
        return entries
    return mapping


def run_pdf_only(entries):
    """Befuellt die PDF-Formulare NUR aus den bereits vorhandenen
    Bewertung_<team>.xlsx — kein git/API/LLM, keine Excel-Neugenerierung.
    Braucht weder GITLAB_TOKEN noch ANTHROPIC_API_KEY."""
    import fill_pdf
    print(f"Erzeuge PDFs aus vorhandenen Excel-Dateien fuer {len(entries)} Team(s) "
          f"(keine Analyse):")
    ok = 0
    for entry in entries:
        try:
            fill_pdf.main_for(entry["local_folder"])
            ok += 1
        except Exception as e:
            print(f"   PDF fehlgeschlagen ({entry['local_folder']}): {e}")
    print(f"Fertig: {ok}/{len(entries)} PDF(s)")


def main():
    args = sys.argv[1:]
    fresh = "--fresh" in args
    do_pdf = "--pdf" in args
    do_overview = "--overview" in args
    pdf_only = "--pdf-only" in args
    for flag in ("--fresh", "--pdf", "--overview", "--pdf-only"):
        while flag in args:
            args.remove(flag)

    mapping = json.loads((ev.OUTPUTS / "team_mapping.json").read_text(encoding="utf-8"))
    entries = _select_entries(args, mapping)

    # Schnellpfad: nur PDFs aus den vorhandenen Excels (kein Token/LLM/Analyse).
    if pdf_only:
        run_pdf_only(entries)
        return

    if fresh:
        import llm as llm_mod
        # Beide Caches loeschen: GitLab-API (evaluate_team) UND LLM (llm).
        for cache in (ev.CACHE_DIR, llm_mod.CACHE_DIR):
            if cache.exists():
                shutil.rmtree(cache)
                print(f"Cache geloescht: {cache}")

    cfg = ev.load_config()
    token = cfg["GITLAB_TOKEN"]
    yaml_cfg = ev.load_yaml_config()
    import llm as llm_mod
    llm_client = llm_mod.load_llm_from_configs(cfg, yaml_cfg)

    print(f"Generiere Excel fuer {len(entries)} Team(s):")
    print(f"  LLM-Inhaltspruefung: {'AKTIV' if llm_client.enabled else 'INAKTIV'}")
    print(f"  PDF: {'JA' if do_pdf else 'nein'}")
    print(f"  Uebersicht: {'JA' if do_overview else 'nein'}")
    print()

    from concurrent.futures import ThreadPoolExecutor, as_completed
    team_workers = int(((yaml_cfg or {}).get("run", {}) or {}).get("team_workers", 4))
    failed = []
    # Fortschrittsbalken via tqdm wenn verfuegbar, sonst stinknormales print.
    # tqdm.write() statt print() haelt die Balkenzeile beim Loggen intakt.
    bar = tqdm(total=len(entries), desc="Teams", unit="Team") if tqdm else None
    emit = tqdm.write if bar is not None else print
    # Teams sind unabhaengig (eigener Clone/API/Excel) -> parallel verarbeiten.
    # LLMClient ist threadsafe (kein self.model-Mutieren), GitLab-API ebenso.
    with ThreadPoolExecutor(max_workers=max(1, team_workers)) as pool:
        fut_to_entry = {pool.submit(process, entry, token, llm_client, yaml_cfg): entry
                        for entry in entries}
        for fut in as_completed(fut_to_entry):
            entry = fut_to_entry[fut]
            try:
                emit(fut.result())
            except Exception as e:
                emit(f"   FEHLER bei {entry['local_folder']}: {e}")
                failed.append(entry["local_folder"])
            if bar is not None:
                bar.update(1)
    if bar is not None:
        bar.close()

    # PDF sequentiell nach den Excels (greift auf die geschriebenen Dateien zu)
    if do_pdf:
        for entry in entries:
            if entry["local_folder"] in failed:
                continue
            try:
                import fill_pdf
                fill_pdf.main_for(entry["local_folder"])
            except Exception as e:
                print(f"   PDF fehlgeschlagen ({entry['local_folder']}): {e}")

    print(f"Fertig: {len(entries) - len(failed)}/{len(entries)}")
    if do_overview:
        import build_overview
        build_overview.main()


if __name__ == "__main__":
    main()
