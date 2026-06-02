#!/usr/bin/env python3
"""
Analyse-Kern der SEP-Bewertung: klont das GitLab-Repo eines Teams, zieht
Issues/MRs/Wiki/Releases und fuehrt die heuristischen + LLM-Analysen aus
(collect_results()).

Die eigentliche Ausgabe (Excel-Bewertungsbogen) erzeugt build_xlsx.py aus
collect_results(); run_all.py orchestriert alle Teams (parallel).

main() hier ist nur ein Smoke-Test-Stub (laedt die Config) - es wird KEIN
Markdown-Report geschrieben. Fuer einen vollstaendigen Lauf: `python run_all.py`.

Erwartet:
- .env im Repo-Root mit GITLAB_TOKEN=... und (optional) ANTHROPIC_API_KEY=...
- skripte/team_mapping.json mit Mapping lokaler Ordner -> GitLab-Projekt

Usage (Smoke-Test):
    python3 evaluate_team.py <local_team_folder>
"""

import os
import sys
import json
import time
import base64
import hashlib
import tempfile
import subprocess
import ssl
import urllib.request
import urllib.error
import urllib.parse
import re
from pathlib import Path
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE = Path(__file__).parent.parent.resolve()
TEAMS = BASE / "teams"
OUTPUTS = Path(__file__).parent.resolve()

# Plattformneutrale Cache-/Arbeitsbasis. Auf Linux i.d.R. /tmp, auf Windows der
# User-Temp-Ordner. Per SEP_CACHE_DIR ueberschreibbar. WICHTIG: llm.py leitet
# seinen CACHE_DIR aus derselben Logik ab, damit `--fresh` beide Caches trifft.
_TMP = Path(os.environ.get("SEP_CACHE_DIR", tempfile.gettempdir()))
REPOS = _TMP / "sep_repos"
DATA = _TMP / "sep_gitlab_data"
GITLAB_HOST = "https://gitlab.git.nrw"

# SSL-Kontext fuer GitLab-Calls. Manche Python-Installationen (z.B. Windows ohne
# gepflegten System-CA-Store) kennen den Aussteller von gitlab.git.nrw nicht und
# scheitern mit CERTIFICATE_VERIFY_FAILED. Wenn certifi installiert ist, dessen
# CA-Bundle nutzen; sonst None -> unveraendertes Default-Verhalten von urlopen.
try:
    import certifi
    _SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except Exception:  # noqa: BLE001 - certifi optional
    _SSL_CONTEXT = None

# ============================================================
# Excel-Spalten-Layout (zentrale Quelle der Wahrheit)
# build_xlsx.py schreibt es, build_overview.py und fill_pdf.py lesen es.
# Diese Konstanten verhindern die fruehere Spalten-Index-Drift.
# A=Kategorie B=Kriterium C=Heur D=LLM E=Max F=Deine_Bew G=Anmerk H=Begr_Heur I=Begr_LLM
# ============================================================
COL_CATEGORY = 1
COL_CRITERION = 2
COL_HEUR = 3       # heuristischer Auto-Score
COL_LLM = 4        # LLM-Zweitmeinung
COL_MAX = 5        # Maximalpunktzahl
COL_SCORE = 6      # "Deine Bewertung" (manuell, vorausgefuellt mit Heuristik)
COL_NOTE = 7       # Anmerkungen (manuell)
COL_REASON_HEUR = 8
COL_REASON_LLM = 9


def load_yaml_config():
    """Laedt skripte/config.yaml. Returns {} wenn nicht da."""
    try:
        import yaml
    except ImportError:
        return {}
    p = OUTPUTS / "config.yaml"
    if not p.exists():
        return {}
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


_THRESHOLDS_CACHE = None


def get_thresholds():
    """Laedt (gecacht) den thresholds:-Block aus config.yaml. {} wenn nicht da."""
    global _THRESHOLDS_CACHE
    if _THRESHOLDS_CACHE is None:
        _THRESHOLDS_CACHE = (load_yaml_config() or {}).get("thresholds", {}) or {}
    return _THRESHOLDS_CACHE


def thr(path, default):
    """Liest einen Schwellenwert per Punkt-Pfad (z.B. 'user_stories.full_score_ratio')
    aus config.yaml thresholds:. Faellt auf den default zurueck, wenn nicht gesetzt.

    WICHTIG: Der default MUSS dem bisherigen hartcodierten Literal entsprechen,
    damit sich ohne config-Aenderung nichts am Scoring aendert. So wird der
    thresholds:-Block (frueher toter Code) tatsaechlich wirksam.
    """
    node = get_thresholds()
    for part in path.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return default
    return node


# ============================================================
# Sprach-Registry / Tutoren / Vendor-Dirs (config-getrieben, Default == bisher)
# ============================================================
_DEFAULT_LANGUAGES = {
    "java": {"source_ext": [".java"],
             "test_globs": ["**/*Test*.java", "**/*Tests.java", "**/*IT.java"],
             "test_markers": ["@Test", "@ParameterizedTest"],
             "comment_markers": ["//", "*", "/*"]},
    "typescript": {"source_ext": [".ts"],
                   "test_globs": ["**/*.spec.ts", "**/*.test.ts", "**/*.spec.tsx", "**/*.test.tsx"],
                   "test_markers": ["it(", "test(", "expect("],
                   "comment_markers": ["//", "*", "/*"]},
    "python": {"source_ext": [".py"],
               "test_globs": ["**/test_*.py", "**/*_test.py"],
               "test_markers": ["def test_", "assert ", "self.assert"],
               "comment_markers": ["#"]},
    "go": {"source_ext": [".go"],
           "test_globs": ["**/*_test.go"],
           "test_markers": ["func Test", "func Benchmark"],
           "comment_markers": ["//"]},
    "kotlin": {"source_ext": [".kt"],
               "test_globs": ["**/*Test.kt", "**/*Tests.kt"],
               "test_markers": ["@Test"],
               "comment_markers": ["//", "*", "/*"]},
    "web": {"source_ext": [".html", ".css"],
            "test_globs": [], "test_markers": [], "comment_markers": []},
}
_DEFAULT_VENDOR_DIRS = ["node_modules", ".git", "dist", "build", "target", "out",
                        ".gradle", ".idea", "vendor", "venv", ".venv", "__pycache__"]
_DEFAULT_TUTORS = ["vogelsang", "metzger"]

_LANG_CACHE = None
_TUTORS_CACHE = None
_VENDOR_CACHE = None


def get_languages():
    """Sprach-Registry aus config.yaml languages:. Default == _DEFAULT_LANGUAGES."""
    global _LANG_CACHE
    if _LANG_CACHE is None:
        cfg = (load_yaml_config() or {}).get("languages")
        _LANG_CACHE = cfg if isinstance(cfg, dict) and cfg else _DEFAULT_LANGUAGES
    return _LANG_CACHE


def get_tutors():
    """Tutor-Username-Fragmente (lowercase) aus config.yaml tutors:."""
    global _TUTORS_CACHE
    if _TUTORS_CACHE is None:
        cfg = (load_yaml_config() or {}).get("tutors")
        items = cfg if isinstance(cfg, list) and cfg else _DEFAULT_TUTORS
        _TUTORS_CACHE = [str(t).lower() for t in items]
    return _TUTORS_CACHE


def get_vendor_dirs():
    """Auszuschliessende Verzeichnis-Namen aus config.yaml vendor_dirs:."""
    global _VENDOR_CACHE
    if _VENDOR_CACHE is None:
        cfg = (load_yaml_config() or {}).get("vendor_dirs")
        items = cfg if isinstance(cfg, list) and cfg else _DEFAULT_VENDOR_DIRS
        _VENDOR_CACHE = set(items)
    return _VENDOR_CACHE


def wrap_student_content(text):
    """Kapselt von Studierenden stammenden Inhalt fuer LLM-Prompts in Delimiter,
    damit das Modell ihn klar als Daten (nicht als Anweisung) erkennt. Ein im
    Inhalt versteckter schliessender Marker wird neutralisiert (Prompt-Injection).
    """
    safe = (text or "").replace("</student_content>", "<\\/student_content>")
    return f"<student_content>\n{safe}\n</student_content>"


def load_config():
    """Laedt Secrets aus .env (Fallback: .gitlab-config fuer Altbestand).

    Format: KEY=VALUE pro Zeile, # leitet Kommentar ein, optionale
    Quotes um den Wert werden entfernt.
    """
    cfg = {}
    path = BASE / ".env"
    if not path.exists():
        legacy = BASE / ".gitlab-config"
        if legacy.exists():
            path = legacy
        else:
            raise FileNotFoundError(
                f"Keine .env gefunden unter {path}. "
                f"Kopiere .env.example zu .env und trage Token + API-Key ein."
            )
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        # Inline-Kommentar abschneiden (nur wenn vor '#' ein Whitespace steht)
        if " #" in v:
            v = v.split(" #", 1)[0]
        v = v.strip().strip('"').strip("'")
        cfg[k.strip()] = v
    return cfg


CACHE_DIR = _TMP / "sep_gitlab_api_cache"
CACHE_ENABLED = True


def _cache_key(path, page=None):
    h = hashlib.sha1(path.encode("utf-8")).hexdigest()[:16]
    suffix = f"_p{page}" if page else ""
    return f"{h}{suffix}.json"


def _cache_read(key):
    if not CACHE_ENABLED:
        return None
    f = CACHE_DIR / key
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def _cache_write(key, data):
    if not CACHE_ENABLED:
        return
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / key).write_text(json.dumps(data), encoding="utf-8")


_RETRY_STATUS = {429, 500, 502, 503, 504}
_MAX_RETRIES = 3


def _retry_after_seconds(err, attempt):
    """Wartezeit fuer den naechsten Versuch: Retry-After-Header wenn vorhanden,
    sonst exponentielles Backoff (1s, 2s, 4s ...). Gedeckelt auf 60s."""
    try:
        ra = err.headers.get("Retry-After") if getattr(err, "headers", None) else None
    except Exception:
        ra = None
    if ra:
        try:
            return min(60, int(ra))
        except (ValueError, TypeError):
            pass
    return min(60, 2 ** attempt)


def _http_get(url, token):
    """GET mit bis zu _MAX_RETRIES Versuchen, exponentiellem Backoff und Beachtung
    von Retry-After bei 429/5xx. Transiente Fehler sollen nicht still ein
    Kriterium auf None/0 kippen lassen."""
    req = urllib.request.Request(url, headers={"PRIVATE-TOKEN": token})
    for attempt in range(_MAX_RETRIES):
        try:
            with urllib.request.urlopen(req, timeout=60, context=_SSL_CONTEXT) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code in _RETRY_STATUS and attempt < _MAX_RETRIES - 1:
                time.sleep(_retry_after_seconds(e, attempt))
                continue
            raise
        except urllib.error.URLError:
            if attempt < _MAX_RETRIES - 1:
                time.sleep(min(60, 2 ** attempt))
                continue
            raise


def api_get(path, token, use_cache=True):
    key = _cache_key(path)
    if use_cache:
        cached = _cache_read(key)
        if cached is not None:
            return cached
    url = f"{GITLAB_HOST}/api/v4{path}"
    data = _http_get(url, token)
    if use_cache:
        _cache_write(key, data)
    return data


def api_get_paginated(path, token, max_pages=50, use_cache=True):
    """GET with simple pagination, with per-page disk cache.

    max_pages deckelt die Anzahl Seiten (a 100 Eintraege). Wird das Limit erreicht,
    OHNE dass eine kurze/leere Seite kam, ist das Ergebnis evtl. unvollstaendig ->
    Warnung auf stderr (nur fuer die grossen Standard-Caps, nicht fuer bewusst
    kleine Stichproben wie MR-Notes mit max_pages=2).
    """
    sep = "&" if "?" in path else "?"
    out = []
    hit_cap = True
    for page in range(1, max_pages + 1):
        key = _cache_key(path, page)
        cached = _cache_read(key) if use_cache else None
        if cached is not None:
            chunk = cached
        else:
            url = f"{GITLAB_HOST}/api/v4{path}{sep}per_page=100&page={page}"
            chunk = _http_get(url, token)
            if use_cache:
                _cache_write(key, chunk)
        if not chunk:
            hit_cap = False
            break
        out.extend(chunk)
        if len(chunk) < 100:
            hit_cap = False
            break
    if hit_cap and max_pages >= 10:
        print(f"WARN: Pagination-Limit ({max_pages} Seiten / {max_pages * 100} Eintraege) "
              f"erreicht fuer {path} - Ergebnis evtl. unvollstaendig (max_pages erhoehen).",
              file=sys.stderr)
    return out


def api_get_parallel(paths, token, max_workers=8):
    """Fetch multiple paths in parallel. Returns dict path -> result (or None)."""
    out = {}
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        fut_to_path = {ex.submit(api_get, p, token): p for p in paths}
        for fut in as_completed(fut_to_path):
            p = fut_to_path[fut]
            try:
                out[p] = fut.result()
            except Exception:
                out[p] = None
    return out


GRAPHQL_URL = f"{GITLAB_HOST}/api/graphql"


def _graphql(query, variables, token, use_cache=True):
    """POST einer GraphQL-Query an GitLab. Gibt das geparste 'data'-Dict zurueck,
    oder None bei jeglichem Fehler (GraphQL-Errors im Body, HTTP-/Netzfehler,
    auf der Instanz nicht vorhandenes Feld).

    Bewusst defensiv: Ein GraphQL-Fehler darf die Pipeline NICHT kippen. Die
    aufrufende Analyse faellt bei None auf ihr bisheriges Verhalten zurueck.
    Cache teilt sich das GitLab-API-Cache-Verzeichnis (Key aus query+variables).
    """
    payload = json.dumps({"query": query, "variables": variables}, sort_keys=True)
    key = _cache_key("GRAPHQL:" + payload)
    if use_cache:
        cached = _cache_read(key)
        if cached is not None:
            return cached
    req = urllib.request.Request(
        GRAPHQL_URL, data=payload.encode("utf-8"), method="POST",
        headers={"PRIVATE-TOKEN": token, "Content-Type": "application/json"})
    body = None
    for attempt in range(_MAX_RETRIES):
        try:
            with urllib.request.urlopen(req, timeout=60, context=_SSL_CONTEXT) as r:
                body = json.loads(r.read())
            break
        except urllib.error.HTTPError as e:
            if e.code in _RETRY_STATUS and attempt < _MAX_RETRIES - 1:
                time.sleep(_retry_after_seconds(e, attempt))
                continue
            return None
        except urllib.error.URLError:
            if attempt < _MAX_RETRIES - 1:
                time.sleep(min(60, 2 ** attempt))
                continue
            return None
    if not isinstance(body, dict) or body.get("errors"):
        return None
    data = body.get("data")
    if use_cache and data is not None:
        _cache_write(key, data)
    return data


# Ein batched Call fuer alle Epic-IIDs. GitLab 18.x: Project.workItems (Plural,
# Connection); das fruehere Project.workItem (Singular) existiert NICHT.
# Zwei Verlinkungs-Widgets sind relevant und werden vereinigt:
#   HIERARCHY.children   -> echte "Child items" (Work-Item-Hierarchie)
#   LINKED_ITEMS         -> "Linked items" (relates_to/blocks) - DAS nutzen die
#                           SS26-Teams real, um Stories an ihre Epics zu haengen.
_EPIC_LINKS_QUERY = """
query($fp: ID!, $iids: [String!]) {
  project(fullPath: $fp) {
    workItems(iids: $iids) {
      nodes {
        iid
        widgets {
          ... on WorkItemWidgetHierarchy { children { nodes { iid } } }
          ... on WorkItemWidgetLinkedItems { linkedItems { nodes { workItem { iid } } } }
        }
      }
    }
  }
}
"""


def fetch_epic_links(full_path, epic_iids, token):
    """Holt je Epic-Issue die mit ihm verknuepften Stories aus GitLabs Work-Item-
    Widgets via GraphQL (ein batched Call ueber alle Epic-IIDs).

    Vereinigt zwei Verknuepfungsarten, die BEIDE nicht als #123-Text im Body
    stehen und daher von der reinen Text-Heuristik uebersehen werden:
      - HIERARCHY.children  (echte "Child items"),
      - LINKED_ITEMS        ("Linked items" / relates_to - die real genutzte
                             Methode der SS26-Teams).
    Befund, der dazu fuehrte: in GitLab haengen an fast allen Epics verknuepfte
    Stories, im PDF wurde aber 'nicht sinnvoll verlinkt' angekreuzt.

    Rueckgabe: {epic_iid(int): [story_iid(int), ...]}. Bei GraphQL-/Schema-/
    Netzfehlern ein leeres Dict - analyze_epics faellt dann auf die Text-
    Referenzen zurueck (kein Pipeline-Crash).
    """
    if not epic_iids:
        return {}
    data = _graphql(_EPIC_LINKS_QUERY,
                    {"fp": full_path, "iids": [str(i) for i in epic_iids]}, token)
    if not data:
        return {}
    try:
        nodes = ((data.get("project") or {}).get("workItems") or {}).get("nodes") or []
    except (AttributeError, TypeError):
        return {}
    out = {}
    for node in nodes:
        try:
            epic_iid = int(node["iid"])
        except (KeyError, ValueError, TypeError):
            continue
        linked = set()
        for w in (node.get("widgets") or []):
            w = w or {}
            for n in ((w.get("children") or {}).get("nodes") or []):
                try:
                    linked.add(int(n["iid"]))
                except (KeyError, ValueError, TypeError):
                    pass
            for n in ((w.get("linkedItems") or {}).get("nodes") or []):
                wi = (n or {}).get("workItem") or {}
                try:
                    linked.add(int(wi["iid"]))
                except (KeyError, ValueError, TypeError):
                    pass
        if linked:
            out[epic_iid] = sorted(linked)
    return out


def _scrub_secrets(text, *secrets):
    """Entfernt Token/Secrets aus (Fehler-)Texten, bevor sie geloggt/geraised werden."""
    out = text or ""
    for s in secrets:
        if s:
            out = out.replace(s, "<REDACTED>")
    return out


def clone_or_update(http_url, token, local):
    """Klont/aktualisiert das Repo nach REPOS/<name>.

    Der Token wird NICHT in die Remote-URL geschrieben (und landet damit nicht im
    Klartext in <repo>/.git/config), sondern nur fluechtig pro git-Aufruf als
    HTTP-Basic-Authorization-Header uebergeben (oauth2:<token>).
    Fail-Fast: prueft hinterher, ob das Repo tatsaechlich Commits enthaelt.
    """
    local.parent.mkdir(parents=True, exist_ok=True)
    basic = base64.b64encode(f"oauth2:{token}".encode("utf-8")).decode("ascii")
    auth = ["-c", f"http.extraHeader=Authorization: Basic {basic}"]
    if local.exists():
        subprocess.run(["git", *auth, "-C", str(local), "fetch", "--all", "--tags", "--prune"],
                       check=False, capture_output=True)
    else:
        result = subprocess.run(["git", *auth, "clone", http_url, str(local)],
                                capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"git clone fehlgeschlagen fuer {http_url}: "
                               f"{_scrub_secrets(result.stderr, token, basic)[:200]}")
    # Sanity-Check: Hat das Repo ueberhaupt Commits?
    log_result = subprocess.run(["git", "-C", str(local), "log", "--oneline", "-1"],
                                capture_output=True, text=True)
    if log_result.returncode != 0 or not log_result.stdout.strip():
        raise RuntimeError(f"Repo {local} ist leer oder hat keine HEAD - kann nicht analysiert werden.")


def run(cmd, cwd):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)


_SHORTLOG_RE = re.compile(r"^\s*(\d+)\s+(.*?)\s+<([^>]*)>\s*$")


def count_active_authors(repo):
    """Anzahl distinkter Commit-Autoren (per E-Mail aggregiert, respektiert .mailmap).
    Zuverlaessiger als die GitLab-Mitgliederzahl als Mass fuer 'wer hat wirklich
    gearbeitet', weil Nie-Committer (passive Mitglieder, Tutoren) nicht mitzaehlen.
    0 wenn kein Git-Repo / keine Commits."""
    out = run(["git", "shortlog", "-sne", "--all", "--no-merges"], repo).stdout.splitlines()
    keys = set()
    for line in out:
        m = _SHORTLOG_RE.match(line)
        if not m:
            continue
        name, email = m.group(2).strip(), m.group(3).strip().lower()
        keys.add(email or name.lower())
    return len(keys)


# ============================================================
# Analysen pro Bewertungs-Kategorie
# ============================================================

_US_FMT_EN = re.compile(r"\bas an? .+?(i want|i'd like|i would like)", re.S | re.I)
_US_FMT_DE = re.compile(r"\bals\s+\S.+?(möchte|will ich|ich will|wünsche)", re.S | re.I)


def _has_acceptance(desc_lower):
    return "acceptance criteria" in desc_lower or "akzeptanzkriterien" in desc_lower


def _has_story_format(desc_lower):
    return bool(_US_FMT_EN.search(desc_lower) or _US_FMT_DE.search(desc_lower))


def _looks_like_user_story(issue):
    """Inhaltliche Story-Erkennung fuer Teams ohne type::userstory-Label
    (PDF-Frage lautet 'User Stories / Issues')."""
    dl = (issue.get("description") or "").lower()
    if _has_acceptance(dl) or _has_story_format(dl):
        return True
    return "user story" in dl or "userstory" in dl


def analyze_user_stories(issues, llm=None, sample_size=5):
    """Issue-Qualität: User Stories mit Akzeptanzkriterien etc. (0-3 Punkte).
    Optional: LLM beurteilt qualitativ die Akzeptanzkriterien einer Sample-Auswahl."""
    us = [i for i in issues if "type::userstory" in i.get("labels", [])]
    n = len(us)
    if n == 0:
        # Fallback: Die Frage heisst "User Stories / Issues". Ein Team ohne
        # type::userstory-Label wird anhand inhaltlicher Story-Signale (Format,
        # Akzeptanzkriterien, explizite Nennung) erkannt, statt faelschlich 0.
        us = [i for i in issues if _looks_like_user_story(i)]
        n = len(us)

    with_acceptance = 0
    with_userstory_format = 0
    with_substantial_desc = 0
    with_weight = 0
    for i in us:
        d = (i.get("description") or "")
        dl = d.lower()
        if _has_acceptance(dl):
            with_acceptance += 1
        if _has_story_format(dl):
            with_userstory_format += 1
        if len(d.strip()) > 80:
            with_substantial_desc += 1
        if i.get("weight") is not None:
            with_weight += 1

    if n == 0:
        score, label = 0, "Nicht durchgeführt"
        reason = "Keine als User Story erkennbaren Issues gefunden."
    else:
        acc_ratio = with_acceptance / n
        fmt_ratio = with_userstory_format / n
        full = thr("user_stories.full_score_ratio", 0.85)
        partial = thr("user_stories.partial_score_ratio", 0.5)
        if acc_ratio >= full and fmt_ratio >= full:
            score, label = 3, "Vollständig durchgeführt"
        elif acc_ratio >= partial and fmt_ratio >= partial:
            score, label = 2, "Mängel"
        elif n >= thr("user_stories.min_stories_for_one", 5):
            score, label = 1, "Grobe Mängel"
        else:
            score, label = 0, "Nicht durchgeführt"
        reason = (f"{n} User Stories. {with_userstory_format}/{n} im 'As a ... I want ... so that ...'-Format, "
                  f"{with_acceptance}/{n} mit Akzeptanzkriterien-Sektion, "
                  f"{with_substantial_desc}/{n} mit substantieller Beschreibung (>80 Zeichen), "
                  f"{with_weight}/{n} mit Story-Weight (Schaetzung) gesetzt.")
    # Optional: LLM-Bewertung der inhaltlichen Qualitaet
    llm_eval = None
    if llm and llm.enabled and us:
        import random
        random.seed(42)
        sample = random.sample(us, min(sample_size, len(us)))
        sample_text = "\n\n---\n\n".join(
            f"#{i['iid']}: {i['title']}\n{(i.get('description') or '')[:600]}"
            for i in sample
        )
        system = ("Du bewertest die inhaltliche Qualitaet von User Stories in einem Studi-SEP-Projekt. "
                  "Achte besonders auf: (1) Sind die Akzeptanzkriterien testbar/messbar? "
                  "(2) Beschreibt 'so that ...' einen echten Nutzerwert? "
                  "(3) Sind die Stories vernuenftig geschnitten? "
                  "Score 0=ueberwiegend schwach, 1=mittel, 2=gut, 3=hervorragend.")
        prompt = (f"Hier sind {len(sample)} zufaellige User Stories:\n\n"
                  + wrap_student_content(sample_text))
        llm_eval = llm.score(prompt, scale_max=3, system=system)
    return {
        "criterion": "User Stories / Issues ordentlich erstellt",
        "max": 3,
        "score": score,
        "label": label,
        "reason": reason,
        "details": {"total_userstories": n, "with_acceptance": with_acceptance,
                    "with_format": with_userstory_format, "with_substantial_desc": with_substantial_desc,
                    "with_weight": with_weight, "llm_review": llm_eval},
    }


_TRIVIAL = re.compile(r"^(wip|fix|update|temp|stuff|changes?|test|asdf+|.|\.\.+|merge|init(ial commit)?)\.?$",
                      re.IGNORECASE)

def analyze_commit_messages(repo, llm=None):
    """Verständliche Commit-Messages (0-1)."""
    r = run(["git", "log", "--all", "--pretty=format:%s"], repo)
    msgs = [m for m in r.stdout.splitlines() if m.strip()]
    if not msgs:
        return {"criterion": "Verständliche Commit-Messages", "max": 1, "score": 0,
                "label": "Nicht durchgeführt", "reason": "Keine Commits gefunden.", "details": {}}
    merge = sum(1 for m in msgs if m.startswith("Merge "))
    non_merge = [m for m in msgs if not m.startswith("Merge ")]
    # Alle Qualitaets-Kennzahlen gegen dieselbe Grundmenge (non_merge) zaehlen -
    # bad_ratio und der very_short-Vergleich beziehen sich auf len(non_merge).
    trivial = sum(1 for m in non_merge if _TRIVIAL.match(m.strip()))
    short = sum(1 for m in non_merge if len(m) < 15)
    very_short = sum(1 for m in non_merge if len(m) < 8)
    avg_len = sum(len(m) for m in non_merge) / max(len(non_merge), 1)

    bad_ratio = trivial / max(len(non_merge), 1)
    if (avg_len >= thr("commit_messages.min_avg_length", 25)
            and bad_ratio < thr("commit_messages.max_trivial_ratio", 0.15)
            and very_short < thr("commit_messages.max_very_short_ratio", 0.10) * len(non_merge)):
        score, label = 1, "Durchgeführt"
    else:
        score, label = 0, "Nicht durchgeführt"
    reason = (f"{len(msgs)} Commits total ({merge} Merges, {len(non_merge)} eigene). "
              f"Ø-Länge (ohne Merges): {avg_len:.0f} Zeichen. "
              f"{trivial} triviale ('fix', 'update' o.ä.), {very_short} sehr kurz (<8 Zeichen).")
    llm_eval = analyze_commit_substance(repo, llm)
    return {"criterion": "Verständliche Commit-Messages", "max": 1, "score": score,
            "label": label, "reason": reason,
            "details": {"total": len(msgs), "merges": merge, "trivial": trivial,
                        "very_short": very_short, "avg_length": round(avg_len, 1),
                        "llm_review": llm_eval}}


def analyze_meeting_docs(wikis, wiki_contents=None, llm=None):
    """Team-Meetings dokumentiert (0-1).
    Mit wiki_contents (dict slug->content) wird die Substanz der Seiten geprueft.
    """
    wiki_contents = wiki_contents or {}
    meeting_pages = []
    substantive_pages = []
    # Datum auch mit 2-stelligem Jahr zulassen (JJ.MM.TT / TT.MM.JJ), nicht nur 4-stellig
    date_re = re.compile(r"\d{2}[.\-/]\d{2}[.\-/]\d{2,4}|\d{2,4}[.\-/]\d{2}[.\-/]\d{2}")
    keywords = ["meeting", "protokoll", "protocol", "minutes", "sprint", "besprechung",
                "retro", "retrospektive", "retrospective", "review", "planning", "plenum",
                "standup", "stand-up", "daily", "jour fixe", "jourfixe", "sitzung",
                "weekly", "kickoff", "kick-off", "sync", "abstimmung"]
    for w in wikis:
        title = w.get("title", "")
        slug = w.get("slug", "")
        if slug.startswith("uploads/"):
            continue
        if date_re.search(title) or any(k in title.lower() for k in keywords):
            meeting_pages.append(title)
            content = wiki_contents.get(slug, "")
            # Substanziell = mehr als 150 Zeichen Text (Bilder/Uploads ignoriert)
            text_only = re.sub(r"!\[.*?\]\(.*?\)|<[^>]+>", "", content)
            if len(text_only.strip()) >= thr("meetings.min_text_length_for_substantial", 150):
                substantive_pages.append(title)
    # Score: substantiell zaehlt, sonst nur Titel-Match (weniger Vertrauen)
    min_pages = thr("meetings.min_substantial_pages", 2)
    if len(substantive_pages) >= min_pages or (len(meeting_pages) >= min_pages and not wiki_contents):
        score, label = 1, "Durchgeführt"
    elif len(meeting_pages) >= 2:
        score, label = 0, "Nicht durchgeführt (Seiten existieren aber sehr knapp)"
    else:
        score, label = 0, "Nicht durchgeführt"
    reason = (f"{len(meeting_pages)} Wiki-Seite(n) wirken wie Meeting-Protokolle, "
              f"davon {len(substantive_pages)} mit substantiellem Inhalt (>=150 Zeichen Text). "
              f"Titel: {meeting_pages[:10]}")
    # Optional: LLM checkt qualitativ ob das echte Meeting-Protokolle sind
    llm_eval = None
    if llm and llm.enabled and meeting_pages:
        sample_contents = []
        for w in wikis[:5]:
            slug = w.get("slug", "")
            if slug.startswith("uploads/"):
                continue
            if w.get("title") in meeting_pages:
                content = (wiki_contents or {}).get(slug, "")
                if content.strip():
                    sample_contents.append(f"### {w['title']}\n{content[:1500]}")
                if len(sample_contents) >= 3:
                    break
        if sample_contents:
            system = ("Du bewertest Wiki-Seiten als Meeting-Protokolle eines Studi-Teams. "
                      "Gute Protokolle haben: Datum, anwesende Personen, klare Diskussions-Outputs, "
                      "Beschluesse oder konkrete Action Items. Score 0=keine echten Protokolle, "
                      "1=mindestens ein substantielles Protokoll vorhanden.")
            prompt = (f"Hier sind {len(sample_contents)} Wiki-Seiten:\n\n"
                      + wrap_student_content("\n\n---\n\n".join(sample_contents)))
            llm_eval = llm.score(prompt, scale_max=1, system=system)
    return {"criterion": "Team-Meetings dokumentiert", "max": 1, "score": score,
            "label": label, "reason": reason,
            "details": {"meeting_pages": meeting_pages, "substantive_pages": substantive_pages,
                        "total_wiki_pages": len(wikis), "llm_review": llm_eval}}


def analyze_release_changelog(releases, repo, llm=None):
    """Release mit Changelog/Release Notes (0-1)."""
    if not releases:
        # Fallback: git tags?
        tags = run(["git", "tag", "-l"], repo).stdout.split()
        return {"criterion": "Release mit Changelog/Release-Notes", "max": 1, "score": 0,
                "label": "Nicht durchgeführt",
                "reason": f"Kein Release über die GitLab-API. Git-Tags: {tags}",
                "details": {"git_tags": tags}}
    rel = releases[0]
    desc = rel.get("description") or ""
    if len(desc.strip()) >= thr("release_changelog.min_description_chars", 200):
        score, label = 1, "Durchgeführt"
        reason = f"Release '{rel.get('tag_name')}' mit Release-Notes ({len(desc)} Zeichen)."
    elif desc.strip():
        score, label = 0, "Nicht durchgeführt"
        reason = f"Release vorhanden ('{rel.get('tag_name')}'), aber Notes sehr knapp ({len(desc)} Zeichen)."
    else:
        score, label = 0, "Nicht durchgeführt"
        reason = f"Release '{rel.get('tag_name')}' ohne Release-Notes."
    # Optional: LLM checkt ob Release-Notes substantielle Info enthalten
    llm_eval = None
    if llm and llm.enabled and releases and desc.strip():
        system = ("Du bewertest Release-Notes eines Studi-Teams. Gute Release-Notes haben: "
                  "(1) Liste implementierter Features, (2) bekannte Probleme/Einschraenkungen, "
                  "(3) idealerweise geplante Features oder Roadmap. Score 0=schwach/Marketing-Text, "
                  "1=akzeptabel, 2=gut, 3=ausfuehrlich strukturiert.")
        prompt = "Bewerte diese Release-Notes:\n\n" + wrap_student_content(desc[:3000])
        llm_eval = llm.score(prompt, scale_max=3, system=system)
    # Zusatz: LLM-Check Release vs. tatsaechliche Features (ergaenzt llm_eval)
    rvf_eval = analyze_release_vs_features(releases, repo, llm) if llm and llm.enabled else None
    if rvf_eval and llm_eval:
        # Kombiniere die beiden LLM-Reviews
        combined_score = round((llm_eval["score"] + rvf_eval["score"]) / 2)
        combined_reason = (f"Release-Substanz: {llm_eval['reason']} | "
                            f"Release vs. Commits: {rvf_eval['reason']}")
        # Beide Teil-Scores sind 0-3; scale_max mitfuehren, damit build_xlsx den
        # kombinierten Score korrekt auf die Kriteriums-Skala normalisiert (bug-074).
        llm_eval = {"score": combined_score, "reason": combined_reason,
                    "scale_max": llm_eval.get("scale_max", 3)}
    elif rvf_eval:
        llm_eval = rvf_eval
    return {"criterion": "Release mit Changelog/Release-Notes", "max": 1, "score": score,
            "label": label, "reason": reason,
            "details": {"releases": [{"tag": r["tag_name"], "name": r["name"],
                                       "desc_chars": len(r.get("description") or "")} for r in releases],
                        "llm_review": llm_eval}}


def analyze_epics(issues, epic_links=None):
    """Sinnvolle Epics + Verlinkung (0-1).
    Teams markieren Epics per Label 'type::epic'. Verlinkung wird aus DREI
    Quellen vereinigt:
      1. Story-Referenzen (#123) im Epic-Beschreibungstext,
      2. Epic-Referenzen (#123) im Story-Beschreibungstext,
      3. native Work-Item-Verknuepfungen (epic_links, via fetch_epic_links):
         "Child items" (Hierarchie) UND "Linked items" (relates_to) - beides
         steht NICHT als #-Text im Body und wird sonst uebersehen.

    epic_links: optionales {epic_iid: [story_iid, ...]} aus fetch_epic_links.
    """
    epics = [i for i in issues if "type::epic" in i.get("labels", [])]
    non_epics = [i for i in issues if "type::epic" not in i.get("labels", [])]
    if not epics:
        return {"criterion": "Sinnvolle Epics + Verlinkung", "max": 1, "score": 0,
                "label": "Nicht durchgeführt",
                "reason": "Keine als Epic markierten Issues (Label 'type::epic') gefunden.",
                "details": {"epics": 0}}
    # Verlinkung prüfen: Stories sollten in Epic-Body referenziert sein (oder umgekehrt)
    ref_re = re.compile(r"#(\d+)")
    referenced_from_epics = set()
    for e in epics:
        for m in ref_re.findall(e.get("description") or ""):
            referenced_from_epics.add(int(m))
    issues_referencing_epic_ids = set()
    epic_iids = {e["iid"] for e in epics}
    for i in non_epics:
        for m in ref_re.findall(i.get("description") or ""):
            if int(m) in epic_iids:
                issues_referencing_epic_ids.add(i["iid"])
                break
    issues_referencing_epic = len(issues_referencing_epic_ids)
    # Native Work-Item-Verknuepfungen ("Child items" + "Linked items"/relates_to):
    # strukturell, NICHT im Beschreibungstext -> per GraphQL (fetch_epic_links).
    native_linked_iids = set()
    for kids in (epic_links or {}).values():
        for k in kids:
            try:
                native_linked_iids.add(int(k))
            except (ValueError, TypeError):
                pass
    # Set-Vereinigung statt Summe: eine Story, die in einem Epic-Body referenziert
    # wird, selbst ein Epic referenziert UND nativ verknuepft ist, zaehlt 1x.
    linked = len(referenced_from_epics | issues_referencing_epic_ids | native_linked_iids)
    if len(epics) >= thr("epics.min_epics", 3) and linked >= thr("epics.min_linked_stories", 5):
        score, label = 1, "Durchgeführt"
    else:
        score, label = 0, "Nicht durchgeführt"
    src = (f"{len(referenced_from_epics)} Stories in Epic-Bodies referenziert, "
           f"{issues_referencing_epic} Stories referenzieren ein Epic, "
           f"{len(native_linked_iids)} nativ verknuepft (Child/Linked items); "
           f"vereinigt {linked} verlinkte Stories")
    if score == 0:
        reason = (f"{len(epics)} Epic-Issues vorhanden, aber zu wenig/keine Verlinkung zu User Stories "
                  f"erkennbar ({src}). "
                  f"Das PDF-Kriterium verlangt EXPLIZIT beides: 'Epics erstellt UND verlinkt' - daher 0/1. "
                  f"Hinweis: Verlinkung erfolgt ueber Issue-Referenzen (#123), Task-Listen ODER die nativen "
                  f"'Child items'-/'Linked items'-Widgets. "
                  f"PRUEFE MANUELL ob die Stories evtl. noch anders mit Epics verbunden sind.")
    else:
        reason = (f"{len(epics)} Epic-Issues vorhanden, sinnvoll mit User Stories verlinkt ({src}). "
                  f"Verlinkung via Label 'type::epic' + Issue-Referenzen und/oder native "
                  f"'Child items'-/'Linked items'-Verknuepfungen.")
    return {"criterion": "Sinnvolle Epics + Verlinkung", "max": 1, "score": score,
            "label": label, "reason": reason,
            "details": {"epic_count": len(epics), "linked_from_epics": len(referenced_from_epics),
                        "referencing_epic": issues_referencing_epic,
                        "native_linked": len(native_linked_iids),
                        "linked_total": linked}}


_BUILD_MARKERS = ["pom.xml", "build.gradle", "build.gradle.kts", "package.json",
                  "go.mod", "pyproject.toml", "setup.py", "Cargo.toml"]


def analyze_code_structure(repo):
    """Code sinnvoll strukturiert (0-1) - sprachunabhaengig."""
    files = run(["git", "ls-files"], repo).stdout.splitlines()
    top_dirs = set()
    for f in files:
        if "/" in f:
            top_dirs.add(f.split("/")[0])
    found_markers = sorted({m for m in _BUILD_MARKERS
                            if any(f == m or f.endswith("/" + m) for f in files)})
    has_backend = any(d.lower() in ("backend", "server", "api") for d in top_dirs)
    has_frontend = any(d.lower() in ("frontend", "client", "web", "ui") for d in top_dirs)
    has_src = any(d.lower() in ("src", "cmd", "internal", "pkg", "lib", "app") for d in top_dirs)
    # generische Modul-/Pakettiefe: tiefster Quellpfad (>= 3 Ebenen = strukturiert)
    src_exts = {e for lang in get_languages().values() for e in lang.get("source_ext", [])}
    max_depth = max((f.count("/") for f in files
                     if any(f.endswith(e) for e in src_exts)), default=0)
    structured = bool(found_markers) or (has_backend and has_frontend) or has_src or max_depth >= 3
    score = 1 if structured else 0
    label = "Durchgeführt" if score else "Nicht durchgeführt"
    reason = (f"Top-Level-Ordner: {sorted(top_dirs)[:15]}. "
              f"Build-Marker: {found_markers or 'keine'}. "
              f"Backend/Frontend-Split: {has_backend and has_frontend}. "
              f"Max. Quell-Pfadtiefe: {max_depth}.")
    return {"criterion": "Code sinnvoll strukturiert", "max": 1, "score": score,
            "label": label, "reason": reason,
            "details": {"top_dirs": sorted(top_dirs), "build_markers": found_markers,
                        "max_source_depth": max_depth}}


def _detect_db_schema(repo, vendor=None):
    """Erkennt dokumentierte Datenbankschemata (PDF nennt 'Datenbankschemata'
    explizit). Liefert (gefunden: bool, kurze_beschreibung: str)."""
    vendor = vendor if vendor is not None else get_vendor_dirs()
    def ok(p):
        return not any(part in vendor for part in p.parts)
    for f in repo.rglob("*.sql"):
        if ok(f):
            return True, f"SQL-Datei {f.name}"
    for f in repo.rglob("*.prisma"):
        if ok(f):
            return True, "Prisma-Schema"
    for f in repo.rglob("db.changelog*"):
        if ok(f):
            return True, "Liquibase-Changelog"
    for name in ("migrations", "migration"):
        for d in repo.rglob(name):
            if d.is_dir() and ok(d):
                try:
                    if any(d.iterdir()):
                        return True, f"{d.name}/-Verzeichnis"
                except OSError:
                    pass
    # ORM-Entities/Models (JPA/TypeORM @Entity, Django models.Model, SQLAlchemy)
    src_exts = {e for spec in get_languages().values() for e in spec.get("source_ext", [])}
    markers = ("@Entity", "@Table(", "models.Model", "declarative_base")
    for ext in src_exts:
        for f in repo.rglob(f"*{ext}"):
            if not ok(f):
                continue
            try:
                txt = f.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            if any(m in txt for m in markers):
                return True, "ORM-Entities/Models"
    return False, ""


def analyze_code_docs(repo, wikis, llm=None):
    """Code ausreichend dokumentiert (0-5) - sprachunabhaengig.
    Quellen: README(s), Wiki, API-Spezifikation, Datenbankschema, Inline-Kommentare."""
    vendor = get_vendor_dirs()
    readmes = []
    for r_path in repo.rglob("README.md"):
        if "node_modules" in r_path.parts or ".git" in r_path.parts:
            continue
        size = r_path.stat().st_size
        readmes.append((str(r_path.relative_to(repo)), size))
    top_readme_chars = next((s for p, s in readmes if p == "README.md"), 0)
    other_readme_chars = sum(s for p, s in readmes if p != "README.md")

    # Template-README erkennen
    is_template = False
    top_r = repo / "README.md"
    if top_r.exists():
        content = top_r.read_text(encoding="utf-8", errors="ignore")
        if "team-repo-template" in content or "Already a pro? Just edit this README.md" in content:
            is_template = True

    # OpenAPI/Swagger
    has_openapi = False
    for f in repo.rglob("*.java"):
        if "node_modules" in f.parts or ".git" in f.parts:
            continue
        try:
            txt = f.read_text(encoding="utf-8", errors="ignore")
            if "@OpenAPIDefinition" in txt or "@Operation" in txt or "springdoc" in txt:
                has_openapi = True
                break
        except Exception:
            pass
    # auch Konfigfiles (sprachunabhaengig)
    for pat in ("openapi.y*ml", "openapi.json", "swagger.y*ml", "swagger.json"):
        if any(not any(part in vendor for part in f.parts) for f in repo.rglob(pat)):
            has_openapi = True
            break

    # Wiki / sonstige Doku (nur substantielle Seiten zaehlen wenn moeglich)
    real_wiki_pages = [w for w in wikis if not w.get("slug", "").startswith("uploads/")]
    # Wenn wiki_contents im Skript gesetzt sind, koennte man hier filtern - aktuell signature-stabil halten

    # Inline-Kommentar-Anteil sprachunabhaengig: Extension -> Comment-Marker aus der Registry
    ext_markers = {}
    for spec in get_languages().values():
        for e in spec.get("source_ext", []):
            bucket = ext_markers.setdefault(e, [])
            for m in spec.get("comment_markers", []):
                if m and m not in bucket:
                    bucket.append(m)
    total_lines = 0
    comment_lines = 0
    for ext, markers in ext_markers.items():
        if not markers:
            continue
        for f in repo.rglob(f"*{ext}"):
            if any(part in vendor for part in f.parts):
                continue
            try:
                for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
                    total_lines += 1
                    s = line.strip()
                    if any(s.startswith(m) for m in markers):
                        comment_lines += 1
            except Exception:
                pass
    comment_ratio = comment_lines / total_lines if total_lines else 0
    has_db_schema, db_schema_desc = _detect_db_schema(repo, vendor)

    # Score-Heuristik (0-5) -- Wiki/READMEs zaehlen staerker als Inline-Kommentare,
    # da gute Doku oft ausserhalb des Codes liegt (Wiki, API-Docs).
    score = 0
    reasons = []
    if is_template:
        reasons.append("Top-Level-README ist die GitLab-Template-Vorlage - kein eigener Projekt-Ueberblick.")
    else:
        if top_readme_chars >= thr("code_docs.min_top_readme_chars", 500):
            score += 1
            reasons.append(f"Eigene Top-Level-README ({top_readme_chars} Zeichen).")
    if other_readme_chars >= thr("code_docs.min_subreadme_chars", 1000):
        score += 1
        reasons.append(f"Weitere README(s) in Subprojekten ({other_readme_chars} Zeichen).")
    # Wiki: gestaffelt (1 Punkt fuer wenig, 2 fuer viel substantielles)
    if len(real_wiki_pages) >= thr("code_docs.wiki_pages_for_two_points", 8):
        score += 2
        reasons.append(f"{len(real_wiki_pages)} substanzielle Wiki-Seiten - umfangreiche Dokumentation.")
    elif len(real_wiki_pages) >= thr("code_docs.wiki_pages_for_one_point", 3):
        score += 1
        reasons.append(f"{len(real_wiki_pages)} substanzielle Wiki-Seiten.")
    if has_openapi:
        score += 1
        reasons.append("API-Dokumentation (OpenAPI/Swagger) gefunden.")
    if has_db_schema:
        score += 1
        reasons.append(f"Datenbankschema dokumentiert ({db_schema_desc}).")
    if comment_ratio >= thr("code_docs.min_inline_comment_ratio", 0.05):
        score += 1
        reasons.append(f"Inline-Kommentare {comment_ratio*100:.1f}% - akzeptabel.")
    elif comment_ratio < 0.01:
        reasons.append(f"Inline-Kommentare sehr selten ({comment_ratio*100:.1f}%) - kein Bonus, aber kein Abzug, "
                       f"wenn andere Doku ausreichend ist.")
    score = min(score, 5)
    # Optional: LLM checkt Code-Kommentar-Qualitaet
    llm_eval = None
    if llm and llm.enabled:
        samples = []
        for ext, markers in ext_markers.items():
            if not markers or len(samples) >= 3:
                continue
            for f in repo.rglob(f"*{ext}"):
                if any(part in vendor for part in f.parts):
                    continue
                try:
                    txt = f.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue
                if any(m in txt for m in markers):
                    samples.append(f"### {f.relative_to(repo)}\n```\n{txt[:1200]}\n```")
                if len(samples) >= 3:
                    break
        if samples:
            system = ("Du bewertest Code-Kommentare. Gut: erklaeren WARUM (Intention, "
                      "Annahmen, Trade-offs). Schwach: redundant (sagen nur WAS der Code schon sagt) "
                      "oder gar keine Kommentare. Score 0=kaum/redundant, 1=mittel, 2=hilfreich.")
            prompt = (f"Hier sind {len(samples)} Code-Ausschnitte:\n\n"
                      + wrap_student_content("\n\n".join(samples)))
            llm_eval = llm.score(prompt, scale_max=2, system=system)
    return {"criterion": "Code ausreichend dokumentiert", "max": 5, "score": score,
            "label": str(score), "reason": " ".join(reasons),
            "details": {"top_readme_chars": top_readme_chars, "is_template_readme": is_template,
                        "other_readme_chars": other_readme_chars, "wiki_pages": len(real_wiki_pages),
                        "has_openapi": has_openapi, "has_db_schema": has_db_schema,
                        "db_schema": db_schema_desc, "comment_ratio": round(comment_ratio, 3),
                        "source_lines_total": total_lines, "source_comment_lines": comment_lines,
                        "llm_review": llm_eval}}


def analyze_code_clean(repo):
    """Code sauber/ohne groessere Maengel (0-1).
    Checks: Debug-Dateien, Linter-Config, TODOs, node_modules/build-Artefakte,
    IDE-Configs, grosse Binaries, OS-Cruft (.DS_Store).
    """
    todos = 0
    has_lint = False
    for _ in list(repo.glob(".eslintrc*")) + list(repo.glob("eslint.config.*")) + list(repo.glob(".prettierrc*")):
        has_lint = True
    for f in repo.rglob(".eslintrc*"):
        if "node_modules" not in f.parts:
            has_lint = True
            break
    for _ in repo.rglob("checkstyle.xml"):
        has_lint = True
        break
    has_editor_config = any(repo.rglob(".editorconfig"))

    debug_files = []
    committed_node_modules = []
    build_artifacts = []
    ide_configs = []
    ds_stores = []
    large_binaries = []

    # Liste aller git-tracked files
    tracked = run(["git", "ls-files"], repo).stdout.splitlines()
    for f in tracked:
        parts = f.split("/")
        # node_modules im Repo (vergangenheit oder gegenwart)
        if "node_modules" in parts:
            committed_node_modules.append(f)
        # Build-Artefakte
        if any(p in parts for p in ("dist", "build", "target", "out", ".gradle", ".idea")):
            build_artifacts.append(f)
        # IDE-Configs
        if any(p in parts for p in (".idea", ".vscode")) or f.endswith(".iml"):
            ide_configs.append(f)
        # OS-Cruft
        if f.endswith(".DS_Store") or f.endswith("Thumbs.db"):
            ds_stores.append(f)
        # Debug-Files
        bn = parts[-1]
        if bn in ("merge-debug.txt", "debug.log") or bn.endswith(".log"):
            if bn != "package-lock.json":
                debug_files.append(f)

    # Grosse Binaries (>5MB)
    large_bin_bytes = thr("repo_hygiene.large_binary_mb", 5) * 1024 * 1024
    for f in tracked[:500]:  # nur sample für perf
        fp = repo / f
        try:
            if fp.is_file() and fp.stat().st_size > large_bin_bytes:
                large_binaries.append(f"{f} ({fp.stat().st_size // 1024 // 1024}MB)")
        except Exception:
            pass

    # TODO/FIXME-Count
    for f in list(repo.rglob("*.java"))[:300] + list(repo.rglob("*.ts"))[:300]:
        if any(p in f.parts for p in ("node_modules", ".git", "dist", "build", "target")):
            continue
        try:
            for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
                if re.search(r"\b(TODO|FIXME|XXX|HACK)\b", line):
                    todos += 1
        except Exception:
            pass

    issues_found = []
    if debug_files:
        issues_found.append(f"Debug-/Log-Dateien im Repo ({len(debug_files)}): {debug_files[:3]}")
    if committed_node_modules:
        issues_found.append(f"node_modules im Repo committed ({len(committed_node_modules)} Files).")
    if build_artifacts and len(build_artifacts) > thr("repo_hygiene.max_build_artifacts", 5):
        issues_found.append(f"Build-Artefakte im Repo ({len(build_artifacts)} Files): {build_artifacts[:3]}")
    if ide_configs and len(ide_configs) > thr("repo_hygiene.max_ide_configs", 3):
        issues_found.append(f"IDE-Configs im Repo ({len(ide_configs)}): {ide_configs[:3]}")
    if ds_stores:
        issues_found.append(f"OS-Cruft (.DS_Store/Thumbs.db) im Repo: {ds_stores[:3]}")
    if large_binaries:
        issues_found.append(f"Grosse Binaerdateien (>5MB): {large_binaries[:3]}")
    if not has_lint and not has_editor_config:
        issues_found.append("Keine Linter-/Editor-Config gefunden.")
    if todos > thr("repo_hygiene.max_todos", 20):
        issues_found.append(f"{todos} TODO/FIXME-Marker.")

    score = 0 if issues_found else 1
    label = "Durchgefuehrt" if score else "Nicht durchgefuehrt"
    reason = (" ".join(issues_found) if issues_found
              else f"Keine Repo-Hygiene-Probleme gefunden, Lint-/Editor-Config vorhanden, {todos} TODOs.")
    return {"criterion": "Code sauber/ohne größere Mängel", "max": 1, "score": score,
            "label": label, "reason": reason,
            "details": {"has_lint_config": has_lint, "has_editor_config": has_editor_config,
                        "debug_files": debug_files[:10], "todo_count": todos,
                        "committed_node_modules_count": len(committed_node_modules),
                        "build_artifacts_count": len(build_artifacts),
                        "ide_configs_count": len(ide_configs),
                        "ds_store_files": ds_stores[:5],
                        "large_binaries": large_binaries[:5]}}


def fetch_coverage_from_ci(token, project_id):
    """Versucht Coverage aus letzter erfolgreichen Pipeline zu holen.
    Returns (coverage_percent, source) oder (None, None).
    Coverage wird oft direkt am Pipeline-Object reported (Feld 'coverage').
    """
    try:
        pipelines = api_get(f"/projects/{project_id}/pipelines?status=success&per_page=5", token)
    except Exception:
        return None, None
    for p in pipelines:
        cov = p.get("coverage")
        if cov is not None:
            try:
                return float(cov), f"Pipeline #{p['id']}"
            except (ValueError, TypeError):
                pass
    # Fallback: hoechste Job-Coverage der erfolgreichen Pipelines
    best = None
    best_src = None
    for p in pipelines:
        try:
            jobs = api_get(f"/projects/{project_id}/pipelines/{p['id']}/jobs", token)
        except Exception:
            continue
        for j in jobs or []:
            c = j.get("coverage")
            if c is None:
                continue
            try:
                c = float(c)
            except (ValueError, TypeError):
                continue
            if best is None or c > best:
                best, best_src = c, f"Pipeline #{p['id']} Job {j.get('name', '?')}"
    return (best, best_src) if best is not None else (None, None)


def _tests_thr(new_key, old_key, default):
    """Liest tests.<new_key>, faellt auf tests.<old_key> (alte config) bzw. default."""
    node = get_thresholds().get("tests", {})
    if isinstance(node, dict):
        if new_key in node:
            return node[new_key]
        if old_key in node:
            return node[old_key]
    return default


def _scan_tests_for_language(repo, lang_spec, vendor):
    """Zaehlt fuer eine Sprache: (files, substantive_files, primary_methods).
    Substantiell = mehr als ein primaerer Test-Marker (mehr als ein Testfall) -
    filtert generierte 1-Test-Stubs (z.B. Angulars 'should create') heraus.
    primary = erster test_marker (@Test / def test_ / func Test / it()."""
    files = set()
    for glob in lang_spec.get("test_globs", []):
        for f in repo.rglob(glob.replace("**/", "")):
            if any(part in vendor for part in f.parts):
                continue
            files.add(f)
    markers = lang_spec.get("test_markers", [])
    primary = markers[0] if markers else None
    n_files = n_subst = n_methods = 0
    for f in files:
        try:
            txt = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        n_files += 1
        primary_count = txt.count(primary) if primary else 0
        n_methods += primary_count
        if primary_count > 1:
            n_subst += 1
    return n_files, n_subst, n_methods


def analyze_tests(repo, llm=None, coverage_pct=None):
    """Tests (0-7), sprachunabhaengig ueber die Registry. Optional coverage_pct aus CI."""
    vendor = get_vendor_dirs()
    per_lang = {}
    total_test_files = substantive_test_files = total_test_methods = 0
    for name, spec in get_languages().items():
        if not spec.get("test_globs"):
            continue
        nf, ns, nm = _scan_tests_for_language(repo, spec, vendor)
        per_lang[name] = {"files": nf, "substantive": ns, "methods": nm}
        total_test_files += nf
        substantive_test_files += ns
        total_test_methods += nm

    score = 0
    if total_test_files >= _tests_thr("files_for_first_point", "files_for_first_point", 5): score += 1
    if total_test_files >= _tests_thr("files_for_second_point", "files_for_second_point", 15): score += 1
    if substantive_test_files >= _tests_thr("substantive_for_third", "java_substantive_for_third", 5): score += 1
    if total_test_methods >= _tests_thr("methods_for_fourth", "java_methods_for_fourth", 30): score += 1
    if substantive_test_files >= _tests_thr("substantive_for_fifth", "ts_substantive_for_fifth", 3): score += 1
    if substantive_test_files >= _tests_thr("big_substantive_for_sixth", "big_java_for_sixth", 10): score += 1
    if (total_test_methods >= _tests_thr("big_methods_for_seventh", "big_java_methods_for_seventh", 50)
            and substantive_test_files >= _tests_thr("big_substantive_for_seventh", "big_ts_for_seventh", 8)): score += 1
    score = min(score, 7)

    lang_summary = ", ".join(f"{k}: {v['files']}F/{v['substantive']}subst/{v['methods']}M"
                             for k, v in per_lang.items() if v["files"])
    reason = (f"{total_test_files} Test-Dateien ueber alle Sprachen "
              f"({substantive_test_files} substanziell = >1 Testfall, "
              f"{total_test_methods} Test-Methoden/Faelle). "
              f"Pro Sprache: {lang_summary or 'keine'}.")
    if coverage_pct is not None:
        reason += f" Coverage aus CI: {coverage_pct:.1f}%."
        if coverage_pct >= 80 and score < 7:
            score = min(7, score + 1); reason += " (+1 wegen >=80% Coverage)"
        elif coverage_pct < 30 and score > 2:
            score = max(2, score - 1); reason += " (-1 wegen <30% Coverage)"

    llm_eval = None
    if llm and llm.enabled:
        samples = []
        for name, spec in get_languages().items():
            if not spec.get("test_globs") or len(samples) >= 5:
                continue
            for glob in spec["test_globs"]:
                for f in repo.rglob(glob.replace("**/", "")):
                    if any(part in vendor for part in f.parts):
                        continue
                    try:
                        samples.append(f"### {f.name}\n```\n{f.read_text(encoding='utf-8', errors='ignore')[:1500]}\n```")
                    except Exception:
                        pass
                    if len(samples) >= 5:
                        break
                if len(samples) >= 5:
                    break
        if samples:
            system = ("Du bewertest Test-Qualitaet eines Studi-Teams. Gut: Edge Cases, Error-Pfade, "
                      "klare Assertions. Schwach: nur Happy Path, leere Tests, 'should be created'-Stubs. "
                      "Score 0=ueberwiegend Stubs, 1=mittel, 2=gut, 3=hervorragend (Edge Cases und Error-Pfade).")
            prompt = (f"Hier sind {len(samples)} Test-Dateien:\n\n"
                      + wrap_student_content("\n\n".join(samples)))
            llm_eval = llm.score(prompt, scale_max=3, system=system)

    return {"criterion": "Tests vorhanden und sinnvoll", "max": 7, "score": score,
            "label": str(score), "reason": reason,
            "details": {"total_test_files": total_test_files,
                        "substantive_test_files": substantive_test_files,
                        "total_test_methods": total_test_methods,
                        "per_language": per_lang, "llm_review": llm_eval,
                        "coverage_pct": coverage_pct}}


def analyze_release_executable(repo, releases):
    """Release ausführbar (0-5).
    Indirekt bewertbar: Dockerfile/compose, Build-Skripte, CI grün, Release-Notes-Inhalt.
    """
    has_compose = (repo / "compose.yaml").exists() or (repo / "docker-compose.yml").exists()
    has_backend_docker = (repo / "backend" / "Dockerfile").exists()
    has_frontend_docker = (repo / "frontend" / "Dockerfile").exists()
    has_ci = (repo / ".gitlab-ci.yml").exists()

    rel_desc_len = len(releases[0].get("description") or "") if releases else 0
    score = 0
    reasons = []
    if releases:
        score += 1; reasons.append("Release existiert.")
    if rel_desc_len >= thr("release_executable.min_release_notes_chars", 500):
        score += 1; reasons.append(f"Release-Notes substanziell ({rel_desc_len} Zeichen).")
    if has_compose:
        score += 1; reasons.append("docker-compose vorhanden.")
    if has_backend_docker and has_frontend_docker:
        score += 1; reasons.append("Backend & Frontend Dockerfiles.")
    if has_ci:
        score += 1; reasons.append(".gitlab-ci.yml vorhanden.")
    score = min(score, 5)
    reasons.insert(0, "WICHTIG - MANUELLE PRUEFUNG ZWINGEND: Dieses Kriterium misst nur die strukturelle "
                      "Bereitschaft (Compose/Docker/CI/Release-Notes), NICHT ob das Release tatsaechlich "
                      "startet und die Features ohne Maengel funktionieren. Release lokal starten und durchklicken!")
    return {"criterion": "Release ausfuehrbar", "max": 5, "score": score,
            "label": str(score), "reason": " ".join(reasons),
            "details": {"has_compose": has_compose, "has_backend_docker": has_backend_docker,
                        "has_frontend_docker": has_frontend_docker, "has_ci": has_ci,
                        "release_notes_chars": rel_desc_len}}


def analyze_sprint_goals(issues, milestones, releases, mrs=None, token=None,
                          project_id=None, llm=None):
    """Sprint-Ziele erreicht (0-1)."""
    closed = sum(1 for i in issues if i.get("state") == "closed")
    opened = sum(1 for i in issues if i.get("state") == "opened")
    total = closed + opened
    must_closed = sum(1 for i in issues if "priority::must" in i.get("labels", []) and i.get("state") == "closed")
    must_open = sum(1 for i in issues if "priority::must" in i.get("labels", []) and i.get("state") == "opened")
    must_total = must_closed + must_open
    close_ratio = closed / total if total else 0
    must_ratio = must_closed / must_total if must_total else 0

    if (close_ratio >= thr("sprint_goals.min_closed_ratio", 0.5)
            and must_ratio >= thr("sprint_goals.min_must_closed_ratio", 0.6)):
        score, label = 1, "Durchgeführt"
    else:
        score, label = 0, "Deutlich hinter den eigenen Zielen"
    reason = (f"{closed} von {total} Issues geschlossen ({close_ratio*100:.0f}%). "
              f"'priority::must': {must_closed} von {must_total} geschlossen ({must_ratio*100:.0f}%).")
    # LLM-Check: Wurden die Stories sauber implementiert? (Issue vs Code mit Sonnet)
    llm_eval = None
    if llm and llm.enabled and mrs and token and project_id:
        llm_eval = analyze_issue_vs_code(issues, mrs, token, project_id, llm,
                                          use_sonnet=True, sample_size=4)
    return {"criterion": "Sprint-Ziele erreicht", "max": 1, "score": score,
            "label": label, "reason": reason,
            "details": {"closed": closed, "opened": opened, "must_closed": must_closed,
                        "must_total": must_total, "llm_review": llm_eval}}


def analyze_work_scope(repo, issues, mrs, members):
    """Arbeitsumfang (0/5/10/15), PRO KOPF normalisiert.

    Rohe Gesamt-Commits/LOC sind als 'angemessen?'-Signal schwach: ein normales
    Semester-SEP knackt jede absolute Schwelle, daher gab die alte Logik faktisch
    immer 15 (alle SS26-Teams: 193-634 Commits, 8k-23k LOC -> ausnahmslos 15/15).
    Wir staffeln deshalb nach Commits/Kopf und LOC/Kopf.

    ANNAHME (bewusst, dokumentiert): Ein SEP-Team hat erfahrungsgemaess
    *5-6 aktive Autoren*. Die Pro-Kopf-Normalisierung rechnet deshalb mit einer
    festen angenommenen Teamgroesse (config: work_scope.assumed_active_authors,
    Default 6 = konservativ am oberen Rand), NICHT mit der real gemessenen
    Autorenzahl. Gruende:
      - Die GitLab-Mitgliederzahl ueberschaetzt (zaehlt Nie-Committer/Tutoren mit;
        SS26: 11-12 'Mitglieder' bei real 7-8 Commit-Autoren).
      - Durch die *gemessene* Autorenzahl zu teilen wuerde Trittbrettfahrer
        belohnen (1 Person macht alles -> riesige Pro-Kopf-Werte -> 15). Ungleiche
        Verteilung faengt ohnehin das Kriterium 'Commit-Verteilung' (Gini) ab.
    Die gemessene Autorenzahl wird nur zur Transparenz/Plausibilitaet ausgewiesen;
    weicht sie stark von 5-6 ab, weist der Reason-Text auf manuelle Pruefung hin.
    """
    tutors = get_tutors()
    n_members = sum(1 for m in members if m.get("access_level", 0) <= 40
                    and not any(t in (m.get("username", "") or "").lower() for t in tutors))
    n_authors = count_active_authors(repo)
    commits = run(["git", "log", "--all", "--pretty=format:%H"], repo).stdout.splitlines()
    n_commits = len(commits)
    merged_mrs = sum(1 for m in mrs if m.get("state") == "merged")
    closed_issues = sum(1 for i in issues if i.get("state") == "closed")
    # LOC in reinem Python zaehlen (plattformneutral; bash/find/xargs/wc fehlen auf
    # Windows und liessen loc still auf 0 fallen -> Arbeitsumfang-Score zu niedrig).
    loc = 0
    vendor = get_vendor_dirs()
    exts = {e for lang in get_languages().values() for e in lang.get("source_ext", [])}
    for f in repo.rglob("*"):
        if not f.is_file() or f.suffix not in exts:
            continue
        if any(part in vendor for part in f.parts):
            continue
        try:
            with f.open("r", encoding="utf-8", errors="ignore") as fh:
                loc += sum(1 for _ in fh)
        except Exception:
            pass

    # Normalisierungsbasis: angenommene Teamgroesse (5-6 aktive Autoren, s.o.).
    team_size = max(1, thr("work_scope.assumed_active_authors", 6))
    commits_per_dev = n_commits / team_size
    loc_per_dev = loc / team_size

    # Heuristik (Schwellen PRO KOPF, kalibriert auf 6 angenommene Autoren):
    #   0  = quasi leeres Repo (absoluter Boden, teamgroessen-unabhaengig)
    #   5  = stark mangelhaft   (< ~15 Commits/Kopf ODER < ~800 LOC/Kopf)
    #   10 = ausreichend        (< ~40 Commits/Kopf ODER < ~2000 LOC/Kopf)
    #   15 = perfekt/ueberdurchschnittlich (sonst)
    if n_commits < thr("work_scope.zero_commits", 20) and loc < thr("work_scope.zero_loc", 1000):
        score, label = 0, "Arbeitsumfang gegen 0"
    elif (commits_per_dev < thr("work_scope.five_commits_per_dev", 15)
          or loc_per_dev < thr("work_scope.five_loc_per_dev", 800)):
        score, label = 5, "Stark mangelhaft"
    elif (commits_per_dev < thr("work_scope.ten_commits_per_dev", 40)
          or loc_per_dev < thr("work_scope.ten_loc_per_dev", 2000)):
        score, label = 10, "Ausreichend, sollte etwas mehr sein"
    else:
        score, label = 15, "Perfekt / überdurchschnittlich"

    devnote = f"{n_authors} aktive Commit-Autoren gemessen"
    if n_members and n_members != n_authors:
        devnote += f" (GitLab listet {n_members} Mitglieder)"
    if n_authors and not (5 <= n_authors <= 7):
        devnote += " — weicht von der 5-6-Annahme ab, Umfang ggf. relativieren"
    reason = (f"{n_commits} Commits, {merged_mrs} gemergte MRs, {closed_issues} geschlossene Issues, "
              f"ca. {loc} Lines of Code. {devnote}. "
              f"Normalisiert auf {team_size} angenommene aktive Autoren: "
              f"{commits_per_dev:.0f} Commits/Kopf, {loc_per_dev:.0f} LOC/Kopf. "
              f"⚠ Manuell prüfen, ob der Umfang zur tatsächlichen Sprint-Zahl passt.")
    return {"criterion": "Arbeitsumfang angemessen", "max": 15, "score": score,
            "label": label, "reason": reason,
            "details": {"commits": n_commits, "merged_mrs": merged_mrs, "closed_issues": closed_issues,
                        "loc": loc, "estimated_devs": n_members, "git_authors": n_authors,
                        "assumed_team_size": team_size,
                        "commits_per_dev": round(commits_per_dev, 1),
                        "loc_per_dev": round(loc_per_dev, 1)}}


def analyze_gitlab_usage(issues, board_lists, releases):
    """GitLab auf vorgesehene Art genutzt (0-2)."""
    n = len(issues)
    if n == 0:
        return {"criterion": "GitLab-Nutzung (Issues, Board)", "max": 2, "score": 0,
                "label": "Nicht durchgeführt", "reason": "Keine Issues vorhanden.", "details": {}}
    labeled = sum(1 for i in issues if i.get("labels"))
    assigned = sum(1 for i in issues if i.get("assignees"))
    closed = sum(1 for i in issues if i.get("state") == "closed")
    label_ratio = labeled / n
    assign_ratio = assigned / n

    if (label_ratio >= thr("gitlab_usage.min_label_ratio_full", 0.85)
            and assign_ratio >= thr("gitlab_usage.min_assignee_ratio_full", 0.7)
            and closed >= n * thr("gitlab_usage.min_closed_ratio_full", 0.5)):
        score, label = 2, "Vollständig durchgeführt"
    elif label_ratio >= thr("gitlab_usage.min_label_ratio_partial", 0.5):
        score, label = 1, "Mängel"
    else:
        score, label = 0, "Nicht durchgeführt"
    reason = (f"{n} Issues. {labeled}/{n} mit Labels ({label_ratio*100:.0f}%), "
              f"{assigned}/{n} mit Assignee ({assign_ratio*100:.0f}%), "
              f"{closed}/{n} geschlossen.")
    return {"criterion": "GitLab-Nutzung (Issues, Board)", "max": 2, "score": score,
            "label": label, "reason": reason,
            "details": {"issues_total": n, "labeled": labeled, "assigned": assigned, "closed": closed}}


def analyze_branching(repo, mrs, llm=None):
    """Branching-Workflow (Feature-Branches, MRs) (0-1).
    Zusaetzlich: Direktpushes auf main (Commits ohne MR-Verbindung) als Negativsignal.
    """
    branches = run(["git", "branch", "-r"], repo).stdout.splitlines()
    feature_branches = [b for b in branches if any(s in b.lower() for s in ("feature/", "feat/", "fix/", "bugfix/", "hotfix/"))]
    all_branches = [b.strip() for b in branches if "HEAD" not in b]
    non_main = [b for b in all_branches if not b.endswith("main") and not b.endswith("master")]
    merged_mrs = [m for m in mrs if m.get("state") == "merged"]
    target_main = sum(1 for m in merged_mrs if m.get("target_branch") in ("main", "master"))

    # Direktpushes auf main erkennen:
    # Commits auf main, die KEINE Merge-Commits sind und KEINE first-parent-Beziehung zu einem Merge haben
    main_ref = "origin/main"
    # Wenn main nicht existiert, probiere master
    if not any("origin/main" in b for b in branches):
        if any("origin/master" in b for b in branches):
            main_ref = "origin/master"
    # Erste Variante: alle Commits direkt auf main (--first-parent zeigt nur die main-Linie)
    fp = run(["git", "log", main_ref, "--first-parent", "--pretty=format:%H %s"], repo).stdout.splitlines()
    # Davon abziehen: jene die Merge-Commits sind (kommen via MR rein)
    direct_commits_main = [line for line in fp if " " in line and not line.split(" ", 1)[1].startswith("Merge ")]
    # Schwelle: 5 oder weniger direkte Commits sind normal (initial commit, kleine Fixes)
    direct_push_count = len(direct_commits_main)

    enough_branches = (len(merged_mrs) >= thr("branching.min_merged_mrs", 10)
                       and len(non_main) >= thr("branching.min_non_main_branches", 3))
    excessive_direct_pushes = direct_push_count > thr("branching.max_direct_pushes_to_main", 15)

    if enough_branches and not excessive_direct_pushes:
        score, label = 1, "Durchgeführt"
    elif enough_branches and excessive_direct_pushes:
        score, label = 0, "Nicht durchgeführt (zu viele Direktpushes auf main)"
    else:
        score, label = 0, "Nicht durchgeführt"
    reason = (f"{len(all_branches)} Remote-Branches insgesamt ({len(non_main)} neben main), "
              f"davon {len(feature_branches)} mit Feature/Fix-Prefix. "
              f"{len(merged_mrs)} gemergte MRs ({target_main} auf main). "
              f"Direkte Commits auf {main_ref} (nicht via MR): {direct_push_count}.")
    llm_eval = analyze_branching_pattern(repo, mrs, llm)
    return {"criterion": "Branching-Workflow (Feature-Branches, MR)", "max": 1, "score": score,
            "label": label, "reason": reason,
            "details": {"remote_branches": len(all_branches), "non_main_branches": len(non_main),
                        "feature_named_branches": len(feature_branches), "merged_mrs": len(merged_mrs),
                        "direct_commits_on_main": direct_push_count,
                        "sample_direct_commits": direct_commits_main[:5],
                        "llm_review": llm_eval}}


def analyze_code_reviews(mrs, token, project_id, llm=None):
    """Code-Reviews bei MRs (0-1).
    Review-Signale (in absteigender Stärke):
      1) Formales Approval durch jemand anderen als den Autor
      2) Reviewer wurden gesetzt
      3) Textuelle Kommentare durch jemand anderen als den Autor
    Wenn >= 50% der gemergten MRs irgendein Review-Signal haben -> 1/1.
    """
    merged_mrs = [m for m in mrs if m.get("state") == "merged"]
    if not merged_mrs:
        return {"criterion": "Code-Reviews durchgefuehrt", "max": 1, "score": 0,
                "label": "Nicht durchgefuehrt", "reason": "Keine gemergten MRs vorhanden.",
                "details": {"merged_mrs": 0}}

    # Pruefe ALLE gemergten MRs (kein Sampling) - das gibt verlaesslichere Zahlen
    with_approval = 0
    with_reviewer = 0
    with_human_note = 0
    any_signal = 0
    for m in merged_mrs:
        iid = m["iid"]
        author = (m.get("author") or {}).get("username")
        rev_set = bool(m.get("reviewers"))
        if rev_set:
            with_reviewer += 1
        signal = rev_set
        # Approvals
        try:
            appr = api_get(f"/projects/{project_id}/merge_requests/{iid}/approvals", token)
            approved_by = [a["user"]["username"] for a in (appr.get("approved_by") or [])
                           if a.get("user", {}).get("username") != author]
            if approved_by:
                with_approval += 1
                signal = True
        except Exception:
            pass
        # Human Notes von jemand anderem als Autor
        try:
            notes = api_get_paginated(f"/projects/{project_id}/merge_requests/{iid}/notes",
                                       token, max_pages=2)
            human_notes_others = [n for n in notes
                                  if not n.get("system")
                                  and (n.get("author") or {}).get("username") != author]
            if human_notes_others:
                with_human_note += 1
                signal = True
        except Exception:
            pass
        if signal:
            any_signal += 1

    n = len(merged_mrs)
    signal_ratio = any_signal / n
    approval_ratio = with_approval / n
    if (approval_ratio >= thr("code_reviews.min_approval_ratio_strong", 0.5)
            or signal_ratio >= thr("code_reviews.min_any_signal_ratio_strong", 0.7)):
        score, label = 1, "Durchgefuehrt"
    elif signal_ratio >= thr("code_reviews.min_any_signal_ratio_weak", 0.4):
        score, label = 1, "Durchgefuehrt (Reviews ueberwiegend ohne textuelle Kommentare)"
    else:
        score, label = 0, "Nicht durchgefuehrt"
    reason = (f"{n} gemergte MRs. Reviewer gesetzt: {with_reviewer}/{n} ({with_reviewer/n*100:.0f}%). "
              f"Formal approved durch andere(n): {with_approval}/{n} ({approval_ratio*100:.0f}%). "
              f"Kommentar von Reviewer (nicht Autor): {with_human_note}/{n} ({with_human_note/n*100:.0f}%). "
              f"Irgendein Review-Signal: {any_signal}/{n} ({signal_ratio*100:.0f}%).")
    # Optional: LLM checkt qualitativ ob die Review-Kommentare substantiell sind
    llm_eval = None
    if llm and llm.enabled and with_human_note > 0:
        # Sammle einige echte Review-Notes
        review_notes = []
        for m in merged_mrs[:20]:
            if len(review_notes) >= 5:
                break
            iid = m["iid"]
            author = (m.get("author") or {}).get("username")
            try:
                notes = api_get_paginated(f"/projects/{project_id}/merge_requests/{iid}/notes",
                                           token, max_pages=2)
                for n2 in notes:
                    if (not n2.get("system")
                            and (n2.get("author") or {}).get("username") != author):
                        body = (n2.get("body") or "").strip()
                        if len(body) > 10:
                            review_notes.append(f"!{iid}: {body[:400]}")
                            break
            except Exception:
                pass
        if review_notes:
            system = ("Du bewertest Code-Review-Kommentare in Merge Requests. Substantiell = "
                      "konkrete Fragen, Verbesserungsvorschlaege, Bug-Hinweise. Schwach = nur 'LGTM', "
                      "Smileys, allgemeine Bestaetigungen. Score 0=ueberwiegend schwach, "
                      "1=mindestens einige substantielle Reviews.")
            prompt = (f"Hier sind {len(review_notes)} Review-Kommentare:\n\n"
                      + wrap_student_content("\n\n---\n\n".join(review_notes)))
            llm_eval = llm.score(prompt, scale_max=1, system=system)
    return {"criterion": "Code-Reviews durchgefuehrt", "max": 1, "score": score,
            "label": label, "reason": reason,
            "details": {"merged_mrs": n, "with_reviewer_set": with_reviewer,
                        "with_approval_by_other": with_approval,
                        "with_human_note_by_other": with_human_note,
                        "with_any_review_signal": any_signal,
                        "llm_review": llm_eval}}


def analyze_commit_distribution(repo):
    """Commit-Verteilung pro Autor (per E-Mail aggregiert, respektiert .mailmap).
    Kein Score, nur Info fuer die manuelle Bewertung."""
    out = run(["git", "shortlog", "-sne", "--all", "--no-merges"], repo).stdout.splitlines()
    by_email = {}  # key -> {"count", "name", "name_count"}
    for line in out:
        m = _SHORTLOG_RE.match(line)
        if not m:
            continue
        count, name, email = int(m.group(1)), m.group(2).strip(), m.group(3).strip().lower()
        key = email or name.lower()
        entry = by_email.setdefault(key, {"count": 0, "name": name, "name_count": 0})
        entry["count"] += count
        if count > entry["name_count"]:   # haeufigsten Einzel-Namen je Mail behalten
            entry["name_count"], entry["name"] = count, name
    authors = sorted(((e["name"], e["count"]) for e in by_email.values()),
                     key=lambda x: x[1], reverse=True)
    total = sum(c for _, c in authors)
    if not authors:
        return {"criterion": "Commit-Verteilung (Info)", "max": 0, "score": 0,
                "label": "n/a", "reason": "Keine Commits.", "details": {}}
    top_author, top_count = authors[0]
    top_share = top_count / total if total else 0
    # Gini-Koeffizient grob: 0 = gleichverteilt, 1 = einer macht alles
    counts = sorted([c for _, c in authors])
    n = len(counts)
    if n > 1:
        cum = sum((i + 1) * c for i, c in enumerate(counts))
        gini = (2 * cum) / (n * total) - (n + 1) / n
    else:
        gini = 1.0

    hint = ""
    if top_share > 0.5:
        hint = " UNGLEICHE VERTEILUNG: 1 Person macht ueber 50% der Commits."
    elif top_share > 0.4:
        hint = " Etwas ungleich: Top-Person macht ueber 40% der Commits."

    reason = (f"{len(authors)} Autoren (per E-Mail aggregiert, .mailmap beruecksichtigt), "
              f"{total} Commits total (ohne Merges). "
              f"Top: {top_author} mit {top_count} ({top_share*100:.0f}%). "
              f"Gini-Koeffizient: {gini:.2f} (0=gleich, 1=eine Person). "
              f"Hinweis: Eine Person mit mehreren E-Mails wird ggf. doppelt gezaehlt." + hint)
    return {"criterion": "Commit-Verteilung (Info)", "max": 0, "score": 0,
            "label": "Info", "reason": reason,
            "details": {"authors": authors[:15], "gini": round(gini, 3),
                        "top_author_share": round(top_share, 3), "total_commits": total}}


def analyze_mr_quality(mrs, token, project_id):
    """Info: MR-Groessen + Time-to-Merge. Kein Score, hilft bei manuellen Bewertungen."""
    from datetime import datetime
    merged = [m for m in mrs if m.get("state") == "merged"]
    if not merged:
        return {"criterion": "MR-Qualitaet (Info)", "max": 0, "score": 0,
                "label": "n/a", "reason": "Keine gemergten MRs.", "details": {}}
    # Time-to-Merge fuer Stichprobe
    times = []
    sizes = []  # additions + deletions
    for m in merged[:20]:
        ca = m.get("created_at")
        ma = m.get("merged_at")
        if ca and ma:
            try:
                dt = (datetime.fromisoformat(ma.replace("Z","+00:00"))
                      - datetime.fromisoformat(ca.replace("Z","+00:00")))
                times.append(dt.total_seconds() / 3600)  # Stunden
            except Exception:
                pass
        # MR-Groesse holen
        try:
            detail = api_get(f"/projects/{project_id}/merge_requests/{m['iid']}", token)
            ch = detail.get("changes_count")
            if ch:
                # changes_count ist z.B. "5+", parse als int
                try:
                    sizes.append(int(str(ch).rstrip("+")))
                except ValueError:
                    pass
        except Exception:
            pass
    avg_time = sum(times) / len(times) if times else 0
    median_time = sorted(times)[len(times)//2] if times else 0
    avg_size = sum(sizes) / len(sizes) if sizes else 0
    big_mrs = sum(1 for s in sizes if s > 30)

    reason = (f"Stichprobe von {len(merged[:20])} MRs. "
              f"Ø Time-to-Merge: {avg_time:.1f}h (Median: {median_time:.1f}h). "
              f"Ø MR-Groesse: {avg_size:.1f} geaenderte Dateien, "
              f"{big_mrs} MR(s) mit >30 Dateien (= schwer reviewbar).")
    return {"criterion": "MR-Qualitaet (Info)", "max": 0, "score": 0,
            "label": "Info", "reason": reason,
            "details": {"avg_time_hours": round(avg_time, 1),
                        "median_time_hours": round(median_time, 1),
                        "avg_size_files": round(avg_size, 1),
                        "big_mrs_over_30_files": big_mrs}}


def analyze_velocity(issues):
    """Info: Velocity-Trend (geschlossene Weights pro Woche)."""
    from datetime import datetime
    from collections import defaultdict
    closed_us = [i for i in issues
                 if i.get("state") == "closed"
                 and "type::userstory" in i.get("labels", [])
                 and i.get("weight") is not None
                 and i.get("closed_at")]
    if len(closed_us) < 3:
        return {"criterion": "Velocity (Info)", "max": 0, "score": 0,
                "label": "n/a",
                "reason": f"Zu wenig geschlossene Stories mit Weight ({len(closed_us)}). "
                          f"Velocity nicht berechenbar.",
                "details": {}}
    by_week = defaultdict(int)
    for i in closed_us:
        try:
            dt = datetime.fromisoformat(i["closed_at"].replace("Z", "+00:00"))
            iso = dt.isocalendar()
            key = f"{iso[0]}-W{iso[1]:02d}"
            by_week[key] += int(i["weight"])
        except Exception:
            pass
    weeks = sorted(by_week.items())
    if not weeks:
        return {"criterion": "Velocity (Info)", "max": 0, "score": 0,
                "label": "n/a", "reason": "Keine parsbaren Daten.", "details": {}}
    avg = sum(v for _, v in weeks) / len(weeks)
    last3 = [v for _, v in weeks[-3:]]
    reason = (f"{len(closed_us)} geschlossene Stories mit Weight ueber {len(weeks)} Woche(n). "
              f"Ø Velocity: {avg:.1f} Story-Points/Woche. "
              f"Letzte 3 Wochen: {last3}.")
    return {"criterion": "Velocity (Info)", "max": 0, "score": 0,
            "label": "Info", "reason": reason,
            "details": {"weeks": dict(weeks), "avg_per_week": round(avg, 1),
                        "total_closed_with_weight": len(closed_us)}}



def analyze_activity_heatmap(repo):
    """Info: Commits pro Tag (letzte 60 Tage). Erkennt Last-Minute-Hacking."""
    from collections import defaultdict
    from datetime import datetime, timedelta
    log_out = run(["git", "log", "--all", "--no-merges", "--pretty=format:%aI"], repo).stdout
    by_day = defaultdict(int)
    for line in log_out.splitlines():
        try:
            d = line.split("T")[0]
            by_day[d] += 1
        except Exception:
            pass
    if not by_day:
        return {"criterion": "Aktivitaets-Verteilung (Info)", "max": 0, "score": 0,
                "label": "n/a", "reason": "Keine Commits.", "details": {}}
    sorted_days = sorted(by_day.items())
    last_60_days = sorted_days[-60:]
    total_recent = sum(c for _, c in last_60_days)
    last_7 = sorted_days[-7:]
    last_7_count = sum(c for _, c in last_7)
    last_minute_ratio = last_7_count / total_recent if total_recent else 0
    active_days = len(last_60_days)
    hint = ""
    if last_minute_ratio > 0.5 and active_days < 30:
        hint = " LAST-MINUTE-HACKING: Mehr als 50% der Commits in den letzten 7 Tagen."
    elif last_minute_ratio > 0.3:
        hint = " Hinweis: Aktivitaet konzentriert sich auf die letzten Tage."
    reason = (f"{sum(by_day.values())} Commits insgesamt, {active_days} aktive Tage "
              f"in den letzten 60. Letzte 7 Tage: {last_7_count} Commits "
              f"({last_minute_ratio*100:.0f}% der letzten 60 Tage).{hint}")
    return {"criterion": "Aktivitaets-Verteilung (Info)", "max": 0, "score": 0,
            "label": "Info", "reason": reason,
            "details": {"active_days_last_60": active_days,
                        "commits_last_7_days": last_7_count,
                        "last_7_days_ratio": round(last_minute_ratio, 2),
                        "by_day_last_30": dict(sorted_days[-30:])}}


def analyze_ci_status(token, project_id):
    """Letzter Pipeline-Status auf main - kein Score, Warnung wenn rot."""
    try:
        pipelines = api_get(f"/projects/{project_id}/pipelines?ref=main&per_page=5", token)
    except Exception:
        try:
            pipelines = api_get(f"/projects/{project_id}/pipelines?ref=master&per_page=5", token)
        except Exception:
            pipelines = []
    if not pipelines:
        return {"criterion": "CI-Pipeline-Status (Info)", "max": 0, "score": 0,
                "label": "n/a", "reason": "Keine Pipelines auf main/master gefunden.",
                "details": {}}
    last = pipelines[0]
    status = last.get("status", "?")
    when = last.get("updated_at", "?")
    if status == "success":
        msg = "OK - letzte Pipeline auf main war erfolgreich."
    elif status in ("failed", "canceled"):
        msg = f"ACHTUNG - letzte Pipeline auf main ist {status}. Release-Bewertung pruefen!"
    elif status == "running":
        msg = "Letzte Pipeline laeuft gerade."
    else:
        msg = f"Letzte Pipeline-Status: {status}."
    statuses = [p.get("status") for p in pipelines]
    success_count = sum(1 for s in statuses if s == "success")
    failed_count = sum(1 for s in statuses if s == "failed")
    reason = (f"{msg} Letzte 5 Pipelines: {success_count} success, {failed_count} failed. "
              f"Letzte Aktualisierung: {when}.")
    return {"criterion": "CI-Pipeline-Status (Info)", "max": 0, "score": 0,
            "label": "Info", "reason": reason,
            "details": {"last_status": status, "last_updated": when,
                        "recent_statuses": statuses}}


# ============================================================
# LLM-only Hilfs-Analysen (werden in andere analyze_* eingebunden)
# ============================================================

def analyze_commit_substance(repo, llm=None):
    """LLM-only: 'was UND warum' in Commit-Messages? Liefert Score-Dict oder None."""
    if not (llm and llm.enabled):
        return None
    out = run(["git", "log", "--all", "--no-merges", "--pretty=format:%s"], repo).stdout.splitlines()
    if len(out) < 5:
        return None
    import random
    random.seed(42)
    sample = random.sample(out, min(20, len(out)))
    prompt = ("Hier sind " + str(len(sample)) + " Commit-Messages:\n\n"
              + wrap_student_content("\n".join("- " + m for m in sample)))
    system = ("Du bewertest Commit-Messages eines Studi-Projekts. "
              "Gut: beschreibt WAS geaendert UND WARUM oder welchen Bug/Feature. "
              "Schwach: nur 'fix', 'update', 'wip'. "
              "Score 0=ueberwiegend schwach, 1=mittel, 2=gut, 3=hervorragend.")
    return llm.score(prompt, scale_max=3, system=system)


def analyze_issue_vs_code(issues, mrs, token, project_id, llm=None,
                           use_sonnet=True, sample_size=4):
    """LLM (Sonnet): vergleicht User Stories mit MR-Diffs die sie schliessen."""
    if not (llm and llm.enabled):
        return None
    import re
    us_by_iid = {i["iid"]: i for i in issues if "type::userstory" in i.get("labels", [])}
    pairs = []
    for m in mrs:
        if m.get("state") != "merged":
            continue
        body = (m.get("description") or "").lower()
        closes = re.findall(r"clos\w+\s+#(\d+)", body)
        for c in closes:
            iid = int(c)
            if iid in us_by_iid:
                pairs.append((us_by_iid[iid], m))
                break
    if not pairs:
        return None
    import random
    random.seed(42)
    sample = random.sample(pairs, min(sample_size, len(pairs)))
    parts = []
    for story, mr in sample:
        try:
            changes = api_get("/projects/" + str(project_id) + "/merge_requests/" + str(mr["iid"]) + "/changes", token)
            diff_text = ""
            for ch in (changes.get("changes") or [])[:8]:
                diff = ch.get("diff", "")[:1500]
                diff_text += "--- " + str(ch.get("new_path", "?")) + "\n" + diff + "\n"
            diff_text = diff_text[:6000]
            story_desc = (story.get("description") or "")[:1500]
            parts.append(
                "=== User Story #" + str(story["iid"]) + ": " + story["title"] + " ===\n" +
                story_desc + "\n\n=== MR !" + str(mr["iid"]) + ": " + mr["title"] + " ===\n" +
                diff_text
            )
        except Exception:
            pass
    if not parts:
        return None
    prompt = ("Bewerte ob die User Stories tatsaechlich durch die MRs umgesetzt werden:\n\n"
              + wrap_student_content("\n\n###\n\n".join(parts)))
    system = ("Du pruefst ob User Stories sauber implementiert wurden. "
              "Achte auf: (1) Alle Akzeptanzkriterien adressiert? "
              "(2) Scope-Creep? "
              "(3) Passt der Code zur Story-Beschreibung? "
              "Score 0=passt nicht, 1=teilweise, 2=ueberwiegend, 3=sauber.")
    model = "claude-sonnet-4-6" if use_sonnet else llm.model
    return llm.score_with_model(prompt, scale_max=3, model=model, system=system)


def analyze_release_vs_features(releases, repo, llm=None):
    """LLM: Release-Notes vs. tatsaechliche Commits."""
    if not (llm and llm.enabled) or not releases:
        return None
    desc = releases[0].get("description") or ""
    if not desc.strip():
        return None
    commits = run(["git", "log", "main", "--no-merges", "-50", "--pretty=format:%s"], repo).stdout
    if not commits.strip():
        commits = run(["git", "log", "--all", "--no-merges", "-50", "--pretty=format:%s"], repo).stdout
    prompt = "Vergleiche Release-Notes mit den tatsaechlichen Commits:\n\n" + wrap_student_content(
        "=== Release-Notes ===\n" + desc[:3000] + "\n\n=== Letzte Commit-Messages ===\n" + commits)
    system = ("Du vergleichst Release-Notes mit tatsaechlichen Commits. "
              "Score 0=Notes versprechen Features die in Commits fehlen (Marketing), "
              "1=teilweise konsistent, 2=Notes passen gut, 3=sehr ehrlich.")
    return llm.score(prompt, scale_max=3, system=system)


def analyze_branching_pattern(repo, mrs, llm=None):
    """LLM: erkennbarer Git-Workflow?"""
    if not (llm and llm.enabled):
        return None
    branches = run(["git", "branch", "-a"], repo).stdout.splitlines()
    branches = [b.strip().replace("remotes/", "") for b in branches[:50] if b.strip()]
    mr_titles = ["!" + str(m["iid"]) + ": " + m["title"] + " (target=" + str(m.get("target_branch")) + ")"
                 for m in mrs[:30]]
    prompt = "Beurteile den Git-Workflow anhand dieser Daten:\n\n" + wrap_student_content(
        "=== Remote-Branches ===\n" + "\n".join(branches[:40])
        + "\n\n=== Letzte MR-Titel ===\n" + "\n".join(mr_titles))
    system = ("Bewerte ob ein konsistenter Git-Workflow erkennbar ist. "
              "Erkenntnistypen: GitFlow, GitHub Flow, Trunk-Based, Chaos. "
              "Score 0=Chaos, 1=Ansaetze, 2=klarer Workflow durchgehalten.")
    return llm.score(prompt, scale_max=2, system=system)


def analyze_sanity_check(results, llm=None):
    """LLM: konsistenzcheck der Gesamtbewertung."""
    if not (llm and llm.enabled):
        return None
    summary = []
    total_score = 0
    total_max = 0
    for r in results:
        if r.get("max", 0) > 0:
            summary.append("- " + r["criterion"] + ": " + str(r["score"]) + "/" + str(r["max"])
                           + " | " + r["reason"][:400])
            total_score += r["score"]
            total_max += r["max"]
    if not summary:
        return None
    prompt = ("Hier ist die automatische Bewertung eines Studi-Teams:\n\n"
              + "\n".join(summary) + "\n\nGesamt: " + str(total_score) + "/" + str(total_max))
    system = ("Pruefe Konsistenz: (1) widerspruechliche Einschaetzungen? "
              "(2) Diskrepanzen zwischen Kategorien? (3) plausibler Gesamtscore? "
              "Score 0=Inkonsistenzen, 1=plausibel mit Auffaelligkeiten, 2=konsistent.")
    return llm.score(prompt, scale_max=2, system=system)


def analyze_conventions(issues, mrs):
    """Info (max=0): welche GitLab-Konventionen wurden gefunden? Vertrauenssignal
    fuer den Pruefer - bricht ein Auto-Score auf 0, weil die Konvention fehlt?"""
    us = sum(1 for i in issues if "type::userstory" in (i.get("labels") or []))
    epic = sum(1 for i in issues if "type::epic" in (i.get("labels") or []))
    prio = sum(1 for i in issues if any(str(l).startswith("priority::") for l in (i.get("labels") or [])))
    weight = sum(1 for i in issues if i.get("weight") is not None)
    milestone = sum(1 for i in issues if i.get("milestone"))
    closes_re = re.compile(r"\b(clos\w+|fix\w*|resolv\w+)\s+#\d+", re.IGNORECASE)
    mrs_closes = sum(1 for m in (mrs or []) if closes_re.search((m.get("description") or "")))
    missing = []
    if us == 0: missing.append("type::userstory")
    if epic == 0: missing.append("type::epic")
    if prio == 0: missing.append("priority::*")
    if mrs_closes == 0: missing.append("Closes #N in MRs")
    if weight == 0: missing.append("Story-Weights")
    reason = (f"Gefundene Konventionen: {us} User-Story-Labels, {epic} Epic-Labels, "
              f"{prio} Priority-Labels, {weight} Issues mit Weight, {milestone} mit Milestone, "
              f"{mrs_closes} MRs mit Closes/Fixes #N. "
              + (f"NICHT gefunden (Auto-Scores hier mit Vorsicht): {', '.join(missing)}."
                 if missing else "Alle erwarteten Konventionen vorhanden."))
    return {"criterion": "Konventions-Report (Info)", "max": 0, "score": 0,
            "label": "Info", "reason": reason,
            "details": {"userstory_labels": us, "epic_labels": epic, "priority_labels": prio,
                        "issues_with_weight": weight, "issues_with_milestone": milestone,
                        "mrs_with_closes": mrs_closes, "missing_conventions": missing}}


CATEGORIES = [
    ("Sprintdokumentation", ["User Stories / Issues ordentlich erstellt",
                              "Verständliche Commit-Messages",
                              "Team-Meetings dokumentiert",
                              "Release mit Changelog/Release-Notes",
                              "Sinnvolle Epics + Verlinkung"]),
    ("Code-Qualität", ["Code sinnvoll strukturiert",
                       "Code ausreichend dokumentiert",
                       "Code sauber/ohne größere Mängel",
                       "Tests vorhanden und sinnvoll"]),
    ("Implementierte Funktionalität", ["Release ausfuehrbar",
                                       "Sprint-Ziele erreicht",
                                       "Arbeitsumfang angemessen"]),
    ("Prozessqualität (teilweise automatisierbar)",
     ["GitLab-Nutzung (Issues, Board)",
      "Branching-Workflow (Feature-Branches, MR)",
      "Code-Reviews durchgefuehrt"]),
]

MANUAL_CRITERIA = [
    ("Prozessqualität (manuell)", [
        ("Team-Organisation & Kommunikation", 2),
        ("Selbstständigkeit (proaktiv mit Tutor)", 2),
    ]),
]


def build_provenance(repo, project_id):
    """Erfasst Commit-SHA/Branch/Zeit fuer den Audit-Stempel der Bewertung."""
    from datetime import datetime, timezone
    sha = run(["git", "-C", str(repo), "rev-parse", "HEAD"], repo).stdout.strip()
    branch = run(["git", "-C", str(repo), "rev-parse", "--abbrev-ref", "HEAD"], repo).stdout.strip()
    return {"head_sha": sha, "branch": branch,
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "project_id": project_id}


def _provenance_result(prov):
    return {"criterion": "Datengrundlage (Info)", "max": 0, "score": 0, "label": "Info",
            "reason": (f"Bewertet auf Commit {prov['head_sha'][:10]} (Branch {prov['branch']}), "
                       f"GitLab-Projekt {prov['project_id']}, Daten geholt am {prov['fetched_at']} (UTC). "
                       f"Spaetere Commits/Issues sind NICHT enthalten."),
            "details": prov}


def collect_results(entry, token, llm_client=None, yaml_cfg=None):
    """Klont/aktualisiert das Repo, zieht alle GitLab-Daten und fuehrt die 20
    Analysen (+ optionalen LLM-Sanity-Check) aus. Gibt die results-Liste zurueck.

    Zentralisiert den frueher in run_all.process UND build_xlsx.main wortgleich
    duplizierten Datenbeschaffungs-/Analyse-Block, damit beide Aufrufer garantiert
    dieselbe Analyse fahren. yaml_cfg liefert (optional) llm.sample_size.
    """
    pid = entry["gitlab_id"]
    repo_name = entry["gitlab_path"].rsplit("/", 1)[-1]
    repo = REPOS / repo_name
    clone_or_update(entry["http_url"], token, repo)
    prov = build_provenance(repo, pid)

    issues = api_get_paginated(f"/projects/{pid}/issues?state=all", token)
    # Native Epic-Verknuepfungen (Child items + Linked items) zusaetzlich via
    # GraphQL, weil der /issues-REST-Endpoint diese Verlinkung nicht enthaelt.
    epic_iids = [i["iid"] for i in issues if "type::epic" in (i.get("labels") or [])]
    epic_links = fetch_epic_links(entry["gitlab_path"], epic_iids, token)
    mrs = api_get_paginated(f"/projects/{pid}/merge_requests?state=all", token)
    releases = api_get_paginated(f"/projects/{pid}/releases", token)
    milestones = api_get_paginated(f"/projects/{pid}/milestones?state=all", token)
    wikis = api_get(f"/projects/{pid}/wikis", token)
    members = api_get_paginated(f"/projects/{pid}/members/all", token)
    try:
        board_lists = api_get(f"/projects/{pid}/boards", token)
    except Exception:
        board_lists = []

    wiki_paths = [f"/projects/{pid}/wikis/" + urllib.parse.quote(w["slug"], safe="")
                  for w in wikis if not w.get("slug", "").startswith("uploads/")]
    wiki_results = api_get_parallel(wiki_paths, token, max_workers=8)
    wiki_contents = {d.get("slug", ""): d.get("content", "")
                     for p, d in wiki_results.items() if d and isinstance(d, dict)}

    sample_size = int(((yaml_cfg or {}).get("llm", {}) or {}).get("sample_size", 5))
    coverage_pct, _ = fetch_coverage_from_ci(token, pid)
    results = [
        _provenance_result(prov),
        analyze_user_stories(issues, llm=llm_client, sample_size=sample_size),
        analyze_commit_messages(repo, llm=llm_client),
        analyze_meeting_docs(wikis, wiki_contents, llm=llm_client),
        analyze_release_changelog(releases, repo, llm=llm_client),
        analyze_epics(issues, epic_links=epic_links),
        analyze_code_structure(repo),
        analyze_code_docs(repo, wikis, llm=llm_client),
        analyze_code_clean(repo),
        analyze_tests(repo, llm=llm_client, coverage_pct=coverage_pct),
        analyze_release_executable(repo, releases),
        analyze_sprint_goals(issues, milestones, releases, mrs, token, pid, llm_client),
        analyze_work_scope(repo, issues, mrs, members),
        analyze_gitlab_usage(issues, board_lists, releases),
        analyze_branching(repo, mrs, llm=llm_client),
        analyze_code_reviews(mrs, token, pid, llm=llm_client),
        analyze_commit_distribution(repo),
        analyze_ci_status(token, pid),
        analyze_mr_quality(mrs, token, pid),
        analyze_velocity(issues),
        analyze_activity_heatmap(repo),
        analyze_conventions(issues, mrs),
    ]
    sanity = analyze_sanity_check(results, llm_client)
    if sanity:
        results.append({"criterion": "Sanity-Check (LLM Info)", "max": 0, "score": 0,
                        "label": "Info",
                        "reason": f"LLM-Konsistenz-Check: {sanity['score']}/2 - {sanity['reason']}",
                        "details": {"llm_review": sanity}})
    return results


def main():
    if len(sys.argv) < 2:
        print("Usage: " + sys.argv[0] + " <local_team_folder>")
        sys.exit(2)
    local_folder = sys.argv[1]
    cfg = load_config()
    print("Loaded config; use build_xlsx.py for full report")


if __name__ == "__main__":
    main()
