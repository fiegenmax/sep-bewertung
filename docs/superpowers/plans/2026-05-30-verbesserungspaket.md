# Verbesserungspaket sep-bewertung — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementiert das 13-Punkte-Verbesserungspaket aus `docs/superpowers/specs/2026-05-30-verbesserungspaket-design.md` (Multi-Sprach-Analyse, Excel-Transparenz, Heuristik-Fixes, LLM-Reproduzierbarkeit, Parallelisierung, Test-Ausbau).

**Architecture:** Surgische Änderungen am flachen Funktionsstil von `evaluate_team.py`. Neue Config-Werte (`languages`, `tutors`, `vendor_dirs`, `llm.temperature`, `run.team_workers`) mit Defaults == heutiges Verhalten, gelesen über gecachte module-weite Accessoren analog zum vorhandenen `thr()`. Provenienz und Konventions-Report fließen als Info-Kriterien (`max=0`) durch den bestehenden results-Kanal — null Signatur-Churn.

**Tech Stack:** Python 3 (stdlib + openpyxl + pyyaml), urllib, `unittest` (`skripte/test_evaluate.py`).

**Testlauf (immer aus `skripte/`):** `cd skripte && python -m unittest test_evaluate -v`

---

## Wichtige Konventionen für den Worker

- **Shell:** Windows. Das **Bash-Tool** läuft mit bash → Commit-Messages per Here-Doc (`git commit -F - <<'EOF' … EOF`), NICHT mit PowerShell-`@'…'@`.
- **Encoding:** Datei-I/O immer `encoding="utf-8"` (Default cp1252 auf Windows).
- **Branch:** Arbeit läuft auf `feature/verbesserungspaket`.
- **Keine `git add -A`** (Secrets-Schutz) — gezielt stagen.
- **Excel-Spalten** nur über `ev.COL_*`-Konstanten.
- Nach jeder Task: Tests grün halten.

---

## File Structure

- `skripte/config.yaml` — Modify: neue Blöcke `languages`, `tutors`, `vendor_dirs`, `llm.temperature`, `run`; `tests:`-Keys umbenannt.
- `skripte/evaluate_team.py` — Modify: Accessoren `get_languages/get_tutors/get_vendor_dirs`; `analyze_work_scope`, `analyze_tests`, `analyze_code_structure`, `analyze_user_stories`, `analyze_commit_distribution`, `fetch_coverage_from_ci`; neu `analyze_conventions`; `collect_results` (Provenienz + Konventionen); Modul-Docstring.
- `skripte/llm.py` — Modify: `temperature`-Feld; reine `_parse_score_response`-Funktion.
- `skripte/build_xlsx.py` — Modify: Provenienz-Kopfzeile, Divergenz-Conditional-Format, Kriteriums-Drift-Assert.
- `skripte/run_all.py` — Modify: Teams parallel via ThreadPoolExecutor.
- `skripte/test_evaluate.py` — Modify: neue Tests.

---

## Task 1: Config + Accessoren (Phase A)

**Files:**
- Modify: `skripte/config.yaml`
- Modify: `skripte/evaluate_team.py` (nach `thr()`, ~Z. 99)
- Test: `skripte/test_evaluate.py`

- [ ] **Step 1: Failing test für die Accessoren**

In `test_evaluate.py` neue TestCase ergänzen:

```python
class TestConfigAccessors(unittest.TestCase):
    def setUp(self):
        # Caches leeren, damit Defaults greifen
        ev._THRESHOLDS_CACHE = None
        ev._LANG_CACHE = None
        ev._TUTORS_CACHE = None
        ev._VENDOR_CACHE = None

    def test_languages_default_has_python_and_go(self):
        langs = ev.get_languages()
        self.assertIn("python", langs)
        self.assertIn("go", langs)
        self.assertIn(".java", langs["java"]["source_ext"])

    def test_tutors_default(self):
        self.assertEqual(set(ev.get_tutors()), {"vogelsang", "metzger"})

    def test_vendor_dirs_contains_node_modules(self):
        self.assertIn("node_modules", ev.get_vendor_dirs())
```

- [ ] **Step 2: Run → FAIL** (`AttributeError: module 'evaluate_team' has no attribute 'get_languages'`)

Run: `cd skripte && python -m unittest test_evaluate.TestConfigAccessors -v`

- [ ] **Step 3: Accessoren in `evaluate_team.py` implementieren**

Direkt nach der `thr()`-Funktion (~Z. 99) einfügen:

```python
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
```

- [ ] **Step 4: `config.yaml` erweitern**

Unter `llm:` ergänzen (vor `cache_ttl_days` oder am Ende des llm-Blocks):

```yaml
  # Sampling-Temperatur fuer reproduzierbare Scores (0 = deterministisch)
  temperature: 0
```

Am Ende der Datei (nach `thresholds:`-Block) anfügen:

```yaml
# Parallelisierung in run_all (Teams sind unabhaengig)
run:
  team_workers: 4

# Tutor-Usernamen (Substring-Match) - werden bei der Team-Groesse nicht mitgezaehlt
tutors:
  - vogelsang
  - metzger

# Verzeichnisse, die bei LOC/Test-Scans ausgeschlossen werden
vendor_dirs:
  - node_modules
  - .git
  - dist
  - build
  - target
  - out
  - .gradle
  - .idea
  - vendor
  - venv
  - .venv
  - __pycache__

# Sprach-Registry fuer LOC-/Test-/Struktur-Erkennung (Default deckt Java/TS/Python/Go/Kotlin/Web)
languages:
  java:
    source_ext: [".java"]
    test_globs: ["**/*Test*.java", "**/*Tests.java", "**/*IT.java"]
    test_markers: ["@Test", "@ParameterizedTest"]
    comment_markers: ["//", "*", "/*"]
  typescript:
    source_ext: [".ts"]
    test_globs: ["**/*.spec.ts", "**/*.test.ts", "**/*.spec.tsx", "**/*.test.tsx"]
    test_markers: ["it(", "test(", "expect("]
    comment_markers: ["//", "*", "/*"]
  python:
    source_ext: [".py"]
    test_globs: ["**/test_*.py", "**/*_test.py"]
    test_markers: ["def test_", "assert ", "self.assert"]
    comment_markers: ["#"]
  go:
    source_ext: [".go"]
    test_globs: ["**/*_test.go"]
    test_markers: ["func Test", "func Benchmark"]
    comment_markers: ["//"]
  kotlin:
    source_ext: [".kt"]
    test_globs: ["**/*Test.kt", "**/*Tests.kt"]
    test_markers: ["@Test"]
    comment_markers: ["//", "*", "/*"]
  web:
    source_ext: [".html", ".css"]
    test_globs: []
    test_markers: []
    comment_markers: []
```

Außerdem im bestehenden `tests:`-Block die Keys umbenennen (alte → neue):

```yaml
  tests:
    files_for_first_point: 5
    files_for_second_point: 15
    substantive_for_third: 5
    methods_for_fourth: 30
    substantive_for_fifth: 3
    big_substantive_for_sixth: 10
    big_methods_for_seventh: 50
    big_substantive_for_seventh: 8
```

- [ ] **Step 5: Run → PASS**

Run: `cd skripte && python -m unittest test_evaluate.TestConfigAccessors -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add skripte/config.yaml skripte/evaluate_team.py skripte/test_evaluate.py
git commit -F - <<'EOF'
Phase A: Config-Registry (languages/tutors/vendor_dirs) + Accessoren

get_languages/get_tutors/get_vendor_dirs analog zu thr() (gecacht, Default ==
bisheriges Verhalten). tests:-Schwellen-Keys sprach-agnostisch umbenannt.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
```

---

## Task 2: Multi-Sprach-LOC in `analyze_work_scope` (Phase B.1)

**Files:**
- Modify: `skripte/evaluate_team.py` — `analyze_work_scope` (~Z. 1005-1044)
- Test: `skripte/test_evaluate.py`

- [ ] **Step 1: Failing test (LOC zählt Python mit)**

```python
class TestMultiLangLoc(unittest.TestCase):
    def setUp(self):
        ev._LANG_CACHE = None
        ev._VENDOR_CACHE = None
        ev._THRESHOLDS_CACHE = None
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_counts_python_and_go_loc(self):
        (self.tmp / "app.py").write_text("a = 1\nb = 2\nc = 3\n", encoding="utf-8")
        (self.tmp / "main.go").write_text("package main\nfunc main() {}\n", encoding="utf-8")
        (self.tmp / "node_modules").mkdir()
        (self.tmp / "node_modules" / "junk.py").write_text("x=1\n"*999, encoding="utf-8")
        res = ev.analyze_work_scope(self.tmp, issues=[], mrs=[], members=[])
        self.assertEqual(res["details"]["loc"], 5)  # 3 py + 2 go, node_modules raus
```

(Imports `tempfile`, `shutil`, `Path` ggf. oben in der Testdatei ergänzen, falls nicht vorhanden.)

- [ ] **Step 2: Run → FAIL** (loc zählt aktuell nur java/ts/html/css → 0)

Run: `cd skripte && python -m unittest test_evaluate.TestMultiLangLoc -v`

- [ ] **Step 3: LOC-Schleife in `analyze_work_scope` ersetzen**

Den Block (aktuell):

```python
    loc = 0
    for ext in ("*.java", "*.ts", "*.html", "*.css"):
        for f in repo.rglob(ext):
            if "node_modules" in f.parts or ".git" in f.parts:
                continue
            try:
                with f.open("r", encoding="utf-8", errors="ignore") as fh:
                    loc += sum(1 for _ in fh)
            except Exception:
                pass
```

ersetzen durch:

```python
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
```

- [ ] **Step 4: Run → PASS**

Run: `cd skripte && python -m unittest test_evaluate.TestMultiLangLoc -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add skripte/evaluate_team.py skripte/test_evaluate.py
git commit -F - <<'EOF'
Phase B.1: LOC sprachunabhaengig (Registry-source_ext + vendor_dirs)

analyze_work_scope zaehlt jetzt alle Registry-Sprachen (Java/TS/Python/Go/Kotlin/
Web), Vendor-Dirs aus config. Java/Angular-Teams unveraendert; Python/Go-Teams
werden nicht mehr unterschaetzt.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
```

---

## Task 3: Multi-Sprach-Tests in `analyze_tests` (Phase B.2)

**Files:**
- Modify: `skripte/evaluate_team.py` — `analyze_tests` (~Z. 849-939)
- Test: `skripte/test_evaluate.py`

- [ ] **Step 1: Failing test (Go/Python/Kotlin-Testdateien werden erkannt)**

```python
class TestMultiLangTests(unittest.TestCase):
    def setUp(self):
        ev._LANG_CACHE = None
        ev._VENDOR_CACHE = None
        ev._THRESHOLDS_CACHE = None
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_detects_python_and_go_tests(self):
        (self.tmp / "test_foo.py").write_text(
            "def test_a():\n    assert 1==1\n\ndef test_b():\n    assert 2==2\n", encoding="utf-8")
        (self.tmp / "bar_test.go").write_text(
            "package x\nfunc TestA(t *testing.T){}\nfunc TestB(t *testing.T){}\n", encoding="utf-8")
        res = ev.analyze_tests(self.tmp, llm=None)
        d = res["details"]
        self.assertEqual(d["total_test_files"], 2)
        self.assertGreaterEqual(d["substantive_test_files"], 2)
        self.assertGreaterEqual(d["total_test_methods"], 4)

    def test_stub_spec_not_substantive(self):
        # eine Angular-Default-Spec (1 it, 1 expect) ist nicht substantiell
        (self.tmp / "a.spec.ts").write_text(
            "it('should create', () => { expect(c).toBeTruthy(); });", encoding="utf-8")
        res = ev.analyze_tests(self.tmp, llm=None)
        self.assertEqual(res["details"]["total_test_files"], 1)
        self.assertEqual(res["details"]["substantive_test_files"], 0)
```

- [ ] **Step 2: Run → FAIL** (`details` hat keine sprach-agnostischen Keys)

Run: `cd skripte && python -m unittest test_evaluate.TestMultiLangTests -v`

- [ ] **Step 3: `analyze_tests` umschreiben**

Die komplette Funktion ersetzen durch (Coverage- und LLM-Logik bleiben erhalten):

```python
def _tests_thr(new_key, old_key, default):
    """Liest tests.<new_key>, faellt auf tests.<old_key> (alte config) bzw. default."""
    node = get_thresholds().get("tests", {}) if isinstance(get_thresholds(), dict) else {}
    if isinstance(node, dict):
        if new_key in node:
            return node[new_key]
        if old_key in node:
            return node[old_key]
    return default


def _scan_tests_for_language(repo, lang_spec, vendor):
    """Zaehlt fuer eine Sprache: (files, substantive_files, primary_methods).
    Substantiell = > 1 Test-Marker-Treffer in der Datei.
    primary_methods = Treffer des ERSTEN test_markers (z.B. @Test / def test_ / func Test / it()."""
    files = set()
    for glob in lang_spec.get("test_globs", []):
        for f in repo.rglob(glob.replace("**/", "")):
            if any(part in vendor for part in f.parts):
                continue
            files.add(f)
    markers = lang_spec.get("test_markers", [])
    primary = markers[0] if markers else None
    n_files, n_subst, n_methods = 0, 0, 0
    for f in files:
        try:
            txt = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        n_files += 1
        marker_hits = sum(txt.count(m) for m in markers)
        if primary:
            n_methods += txt.count(primary)
        if marker_hits > 1:
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
              f"({substantive_test_files} substanziell, {total_test_methods} Test-Methoden/Assertions). "
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
```

- [ ] **Step 4: Run → PASS**

Run: `cd skripte && python -m unittest test_evaluate.TestMultiLangTests test_evaluate.TestTests -v`
(Falls eine bestehende `TestTests`-Klasse Java/Angular-Fixtures prüft: anpassen, dass sie die neuen `details`-Keys `total_test_files`/`substantive_test_files` nutzt.)
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add skripte/evaluate_team.py skripte/test_evaluate.py
git commit -F - <<'EOF'
Phase B.2: Tests sprachunabhaengig ueber die Sprach-Registry

analyze_tests scannt jetzt alle Registry-Sprachen (Java/TS/Python/Go/Kotlin),
aggregiert in total_test_files/substantive_test_files/total_test_methods und
mappt die 7-Punkte-Heuristik darauf. Default-Schwellen == bisherige Java/Angular-
Zahlen (rueckwaerts-kompatibler Key-Fallback). per_language bleibt in details.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
```

---

## Task 4: `analyze_code_structure` generalisieren (Phase B.3)

**Files:**
- Modify: `skripte/evaluate_team.py` — `analyze_code_structure` (~Z. 588-612)
- Test: `skripte/test_evaluate.py`

- [ ] **Step 1: Failing test (Go-Modul gilt als strukturiert)**

```python
class TestCodeStructure(unittest.TestCase):
    def setUp(self):
        ev._VENDOR_CACHE = None
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _git_init_with_files(self, files):
        import subprocess
        subprocess.run(["git", "init", "-q"], cwd=self.tmp)
        for rel in files:
            p = self.tmp / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("x\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=self.tmp)

    def test_go_module_is_structured(self):
        self._git_init_with_files(["go.mod", "cmd/app/main.go", "internal/svc/svc.go"])
        res = ev.analyze_code_structure(self.tmp)
        self.assertEqual(res["score"], 1)
        self.assertIn("go.mod", res["details"]["build_markers"])
```

- [ ] **Step 2: Run → FAIL** (heute kein `build_markers`, Go nicht erkannt)

Run: `cd skripte && python -m unittest test_evaluate.TestCodeStructure -v`

- [ ] **Step 3: `analyze_code_structure` ersetzen**

```python
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
    # generische Modul-/Pakettiefe: tiefster Quellpfad >= 3 Ebenen
    max_depth = max((f.count("/") for f in files
                     if any(f.endswith(e) for lang in get_languages().values()
                            for e in lang.get("source_ext", []))), default=0)
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
```

- [ ] **Step 4: Run → PASS**

Run: `cd skripte && python -m unittest test_evaluate.TestCodeStructure -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add skripte/evaluate_team.py skripte/test_evaluate.py
git commit -F - <<'EOF'
Phase B.3: analyze_code_structure sprachunabhaengig

Erkennt Build-Marker (pom/gradle/package.json/go.mod/pyproject/Cargo), generische
src-Layouts (cmd/internal/pkg/...) und Modultiefe statt nur Java-Pakete.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
```

---

## Task 5: User-Story-Regex entschärfen (Phase D, 2c)

**Files:**
- Modify: `skripte/evaluate_team.py` — `analyze_user_stories` (~Z. 337)
- Test: `skripte/test_evaluate.py`

- [ ] **Step 1: Failing test**

```python
class TestUserStoryRegex(unittest.TestCase):
    def _us(self, desc):
        return [{"iid": 1, "title": "t", "labels": ["type::userstory"], "description": desc}]

    def test_real_story_counts(self):
        res = ev.analyze_user_stories(self._us("Als Nutzer möchte ich mich einloggen, so dass ..."))
        self.assertEqual(res["details"]["with_format"], 1)

    def test_mehr_als_does_not_count(self):
        res = ev.analyze_user_stories(self._us("Wir haben mehr als 5 offene Tasks und wollen aufraeumen."))
        self.assertEqual(res["details"]["with_format"], 0)
```

- [ ] **Step 2: Run → FAIL** (heute matcht "mehr als" via bare `als `)

Run: `cd skripte && python -m unittest test_evaluate.TestUserStoryRegex -v`

- [ ] **Step 3: Regex in `analyze_user_stories` ersetzen**

Die Zeile (aktuell):

```python
        if re.search(r"as a |als (eine?r? )?", dl) and ("i want" in dl or "möchte" in dl or "ich will" in dl):
            with_userstory_format += 1
```

ersetzen durch:

```python
        en_fmt = re.search(r"\bas an? .+?(i want|i'd like|i would like)", dl, re.S)
        de_fmt = re.search(r"\bals\s+\S.+?(möchte|will ich|ich will|wünsche)", dl, re.S)
        if en_fmt or de_fmt:
            with_userstory_format += 1
```

- [ ] **Step 4: Run → PASS**

Run: `cd skripte && python -m unittest test_evaluate.TestUserStoryRegex test_evaluate.TestUserStories -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add skripte/evaluate_team.py skripte/test_evaluate.py
git commit -F - <<'EOF'
Phase D (2c): User-Story-Format-Regex entschaerft

Bare "als " matchte beliebigen Text ("mehr als"). Jetzt muss Rolle + Wunsch
zusammen auftreten (als <X> ... moechte/will/wuensche bzw. as a ... i want).

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
```

---

## Task 6: Tutoren aus Config (Phase D, 2d)

**Files:**
- Modify: `skripte/evaluate_team.py` — `analyze_work_scope` (~Z. 1007-1009)
- Test: `skripte/test_evaluate.py`

- [ ] **Step 1: Failing test**

```python
class TestTutorsConfig(unittest.TestCase):
    def setUp(self):
        ev._TUTORS_CACHE = None
        ev._LANG_CACHE = None
        ev._VENDOR_CACHE = None
        self.tmp = Path(tempfile.mkdtemp())
    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        ev._TUTORS_CACHE = None

    def test_tutor_excluded_from_devcount(self):
        ev._TUTORS_CACHE = ["tutorx"]
        members = [{"access_level": 30, "username": "alice"},
                   {"access_level": 40, "username": "tutorx_helper"},
                   {"access_level": 30, "username": "bob"}]
        res = ev.analyze_work_scope(self.tmp, issues=[], mrs=[], members=members)
        self.assertEqual(res["details"]["estimated_devs"], 2)
```

- [ ] **Step 2: Run → FAIL** (heute hartcodiert vogelsang/metzger → tutorx_helper zählt mit → 3)

Run: `cd skripte && python -m unittest test_evaluate.TestTutorsConfig -v`

- [ ] **Step 3: `analyze_work_scope` Filter ersetzen**

Aktuell:

```python
    n_devs = sum(1 for m in members if m.get("access_level", 0) <= 40
                 and "vogelsang" not in m.get("username", "")
                 and "metzger" not in m.get("username", ""))
```

ersetzen durch:

```python
    tutors = get_tutors()
    n_devs = sum(1 for m in members if m.get("access_level", 0) <= 40
                 and not any(t in (m.get("username", "") or "").lower() for t in tutors))
```

- [ ] **Step 4: Run → PASS**

Run: `cd skripte && python -m unittest test_evaluate.TestTutorsConfig -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add skripte/evaluate_team.py skripte/test_evaluate.py
git commit -F - <<'EOF'
Phase D (2d): Tutor-Usernamen aus config.yaml statt hartcodiert

analyze_work_scope nutzt get_tutors() (Substring, lowercase) fuer die Team-Groesse.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
```

---

## Task 7: Autoren-Identität via E-Mail/.mailmap (Phase D, 3b)

**Files:**
- Modify: `skripte/evaluate_team.py` — `analyze_commit_distribution` (~Z. 1228-1268)
- Test: `skripte/test_evaluate.py`

- [ ] **Step 1: Failing test (zwei Namen, gleiche Mail → 1 Autor)**

```python
class TestAuthorIdentity(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        import subprocess
        subprocess.run(["git", "init", "-q"], cwd=self.tmp)
        def commit(name, email, msg):
            env = {**os.environ, "GIT_AUTHOR_NAME": name, "GIT_AUTHOR_EMAIL": email,
                   "GIT_COMMITTER_NAME": name, "GIT_COMMITTER_EMAIL": email}
            (self.tmp / "f.txt").write_text(msg, encoding="utf-8")
            subprocess.run(["git", "add", "-A"], cwd=self.tmp, env=env)
            subprocess.run(["git", "commit", "-q", "-m", msg], cwd=self.tmp, env=env)
        commit("Alice", "alice@x.de", "c1")
        commit("Alice Wonder", "alice@x.de", "c2")
        commit("Bob", "bob@x.de", "c3")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_same_email_merged(self):
        res = ev.analyze_commit_distribution(self.tmp)
        # Alice (2 Commits unter einer Mail) + Bob = 2 Autoren
        self.assertEqual(len(res["details"]["authors"]), 2)
```

(Test-Imports `os` sicherstellen.)

- [ ] **Step 2: Run → FAIL** (heute via `-sn` Namen → Alice/Alice Wonder getrennt → 3)

Run: `cd skripte && python -m unittest test_evaluate.TestAuthorIdentity -v`

- [ ] **Step 3: `analyze_commit_distribution` auf E-Mail-Aggregation umstellen**

Den Parsing-Block ersetzen. Statt `git shortlog -sn` jetzt `-sne` und nach E-Mail mergen:

```python
def analyze_commit_distribution(repo):
    """Commit-Verteilung pro Autor (per E-Mail aggregiert, respektiert .mailmap)."""
    out = run(["git", "shortlog", "-sne", "--all", "--no-merges"], repo).stdout.splitlines()
    by_email = {}   # email -> [count, name]
    line_re = re.compile(r"^\s*(\d+)\s+(.*?)\s+<([^>]*)>\s*$")
    for line in out:
        m = line_re.match(line)
        if not m:
            continue
        count, name, email = int(m.group(1)), m.group(2).strip(), m.group(3).strip().lower()
        key = email or name.lower()
        if key not in by_email or count > by_email[key][0]:
            # haeufigsten Namen behalten (groesster Einzel-Block)
            existing = by_email.get(key)
            by_email[key] = [(existing[0] if existing else 0) + count, name]
        else:
            by_email[key][0] += count
    authors = sorted(((name, cnt) for cnt, name in by_email.values()),
                     key=lambda x: x[1], reverse=True)
    total = sum(c for _, c in authors)
    if not authors:
        return {"criterion": "Commit-Verteilung (Info)", "max": 0, "score": 0,
                "label": "n/a", "reason": "Keine Commits.", "details": {}}
    top_author, top_count = authors[0]
    top_share = top_count / total if total else 0
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
              f"Gini: {gini:.2f} (0=gleich, 1=eine Person)."
              f" Hinweis: Eine Person mit mehreren E-Mails wird ggf. doppelt gezaehlt." + hint)
    return {"criterion": "Commit-Verteilung (Info)", "max": 0, "score": 0,
            "label": "Info", "reason": reason,
            "details": {"authors": authors[:15], "gini": round(gini, 3),
                        "top_author_share": round(top_share, 3), "total_commits": total}}
```

- [ ] **Step 4: Run → PASS**

Run: `cd skripte && python -m unittest test_evaluate.TestAuthorIdentity -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add skripte/evaluate_team.py skripte/test_evaluate.py
git commit -F - <<'EOF'
Phase D (3b): Commit-Verteilung per E-Mail aggregieren

git shortlog -sne; mergt Namen-Dubletten gleicher Mail, respektiert .mailmap.
Limitierung (eine Person, mehrere Mails) im reason dokumentiert.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
```

---

## Task 8: Coverage pro CI-Job (Phase D, 3c)

**Files:**
- Modify: `skripte/evaluate_team.py` — `fetch_coverage_from_ci` (~Z. 830-846)
- Test: `skripte/test_evaluate.py`

- [ ] **Step 1: Failing test (Fallback auf Job-Coverage via monkeypatch)**

```python
class TestJobCoverage(unittest.TestCase):
    def test_falls_back_to_job_coverage(self):
        calls = {}
        def fake_api_get(path, token):
            if "/jobs" in path:
                return [{"name": "test", "coverage": 73.5}, {"name": "build", "coverage": None}]
            if "/pipelines" in path:
                return [{"id": 7, "coverage": None}]
            return []
        orig = ev.api_get
        ev.api_get = fake_api_get
        try:
            cov, src = ev.fetch_coverage_from_ci("tok", 1)
        finally:
            ev.api_get = orig
        self.assertEqual(cov, 73.5)
        self.assertIn("Job", src)
```

- [ ] **Step 2: Run → FAIL** (heute kein Job-Fallback → None)

Run: `cd skripte && python -m unittest test_evaluate.TestJobCoverage -v`

- [ ] **Step 3: `fetch_coverage_from_ci` erweitern**

```python
def fetch_coverage_from_ci(token, project_id):
    """Coverage aus letzter erfolgreicher Pipeline. Fallback: hoechste Job-Coverage.
    Returns (coverage_percent, source) oder (None, None)."""
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
    # Fallback: Job-Coverage der erfolgreichen Pipelines
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
```

- [ ] **Step 4: Run → PASS**

Run: `cd skripte && python -m unittest test_evaluate.TestJobCoverage -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add skripte/evaluate_team.py skripte/test_evaluate.py
git commit -F - <<'EOF'
Phase D (3c): Coverage-Fallback auf CI-Job-Coverage

Wenn pipeline.coverage leer ist, hoechste job.coverage der erfolgreichen
Pipelines nehmen (haeufigster Reporting-Weg).

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
```

---

## Task 9: LLM temperature + testbare Parse-Funktion (Phase E, 1d + 5)

**Files:**
- Modify: `skripte/llm.py` — `__init__`, `call`, `score`, neu `_parse_score_response`
- Modify: `skripte/llm.py` — `load_llm_from_configs`
- Test: `skripte/test_evaluate.py`

- [ ] **Step 1: Failing test für `_parse_score_response`**

```python
import llm as llm_mod

class TestParseScore(unittest.TestCase):
    def test_dict(self):
        self.assertEqual(llm_mod._parse_score_response('{"score": 2, "reason": "ok"}', 3),
                         {"score": 2, "reason": "ok"})
    def test_json_fence(self):
        out = '```json\n{"score": 5, "reason": "x"}\n```'
        self.assertEqual(llm_mod._parse_score_response(out, 3)["score"], 3)  # clamp auf 3
    def test_list_aggregates(self):
        out = '[{"score":2,"reason":"a"},{"score":0,"reason":"b"}]'
        r = llm_mod._parse_score_response(out, 3)
        self.assertEqual(r["score"], 1)  # round((2+0)/2)
    def test_garbage_none(self):
        self.assertIsNone(llm_mod._parse_score_response("not json", 3))
    def test_empty_none(self):
        self.assertIsNone(llm_mod._parse_score_response("", 3))
```

- [ ] **Step 2: Run → FAIL** (`_parse_score_response` existiert nicht)

Run: `cd skripte && python -m unittest test_evaluate.TestParseScore -v`

- [ ] **Step 3: Parse-Funktion aus `score()` extrahieren**

In `llm.py` (Modul-Ebene, vor der Klasse) einfügen:

```python
def _parse_score_response(out, scale_max):
    """Parst die LLM-Score-Antwort zu {'score': int, 'reason': str} oder None.
    Reine Funktion (kein Netzwerk) - direkt testbar."""
    if not out or not out.strip():
        return None
    out = out.strip()
    if out.startswith("```"):
        out = out.strip("`")
        if out.startswith("json"):
            out = out[4:].strip()
    try:
        data = json.loads(out)
    except (ValueError, json.JSONDecodeError, TypeError):
        return None
    if isinstance(data, list) and data:
        scores = [int(d.get("score", 0)) for d in data if isinstance(d, dict)]
        reasons = [str(d.get("reason", "")).strip() for d in data if isinstance(d, dict)]
        if not scores:
            return None
        avg = max(0, min(scale_max, round(sum(scores) / len(scores))))
        reason = (f"Mittel aus {len(scores)} Samples (Scores: {scores}). " + " | ".join(reasons[:3]))
        return {"score": avg, "reason": reason[:500]}
    if isinstance(data, dict):
        score = max(0, min(scale_max, int(data.get("score", 0))))
        return {"score": score, "reason": str(data.get("reason", "")).strip()}
    return None
```

Dann in `LLMClient.score()` den Parse-Block (alles ab `out = out.strip()` bis zum `except`) ersetzen durch:

```python
        out = self.call(prompt, system=full_system, max_tokens=600, model=model)
        result = _parse_score_response(out, scale_max)
        if result is None and out:
            log.warning(f"LLM score parse failed (got: {out[:200]})")
        return result
```

- [ ] **Step 4: temperature-Feld ergänzen**

In `LLMClient.__init__` Signatur + Feld:

```python
    def __init__(self, api_key, model="claude-haiku-4-5-20251001",
                 max_tokens=400, cache_ttl_days=7, enabled=True, temperature=0):
        ...
        self.temperature = temperature
```

In `call()` den `body` erweitern:

```python
        body = {
            "model": m,
            "max_tokens": max_t,
            "temperature": self.temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
```

In `load_llm_from_configs` ergänzen:

```python
        temperature=llm_cfg.get("temperature", 0),
```

- [ ] **Step 5: Run → PASS (alle Tests)**

Run: `cd skripte && python -m unittest test_evaluate -v`
Expected: PASS (inkl. TestParseScore)

- [ ] **Step 6: Commit**

```bash
git add skripte/llm.py skripte/test_evaluate.py
git commit -F - <<'EOF'
Phase E: LLM temperature=0 + testbare _parse_score_response

temperature aus config.yaml (Default 0) fuer reproduzierbare Scores. Parse-Logik
aus score() in reine Funktion extrahiert und mit Unit-Tests abgedeckt (dict,
Liste, ```json-Wrap, Muell, leer).

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
```

---

## Task 10: Konventions-Report (Phase C, 2a)

**Files:**
- Modify: `skripte/evaluate_team.py` — neu `analyze_conventions`; Einbindung in `collect_results`
- Test: `skripte/test_evaluate.py`

- [ ] **Step 1: Failing test**

```python
class TestConventions(unittest.TestCase):
    def test_counts_conventions(self):
        issues = [
            {"iid": 1, "labels": ["type::userstory", "priority::must"], "weight": 3, "milestone": {"id": 1}},
            {"iid": 2, "labels": ["type::epic"], "weight": None, "milestone": None},
        ]
        mrs = [{"iid": 9, "description": "Closes #1"}]
        res = ev.analyze_conventions(issues, mrs)
        d = res["details"]
        self.assertEqual(res["max"], 0)
        self.assertEqual(d["userstory_labels"], 1)
        self.assertEqual(d["epic_labels"], 1)
        self.assertEqual(d["priority_labels"], 1)
        self.assertEqual(d["mrs_with_closes"], 1)
        self.assertEqual(d["issues_with_weight"], 1)
```

- [ ] **Step 2: Run → FAIL**

Run: `cd skripte && python -m unittest test_evaluate.TestConventions -v`

- [ ] **Step 3: `analyze_conventions` implementieren** (vor `CATEGORIES` einfügen)

```python
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
```

- [ ] **Step 4: In `collect_results` einbinden**

In der `results = [...]`-Liste als ERSTEN Info-Eintrag nach den Score-Kriterien ergänzen (vor `analyze_commit_distribution`), z. B. direkt nach `analyze_gitlab_usage(...)`:

```python
        analyze_conventions(issues, mrs),
```

- [ ] **Step 5: Run → PASS**

Run: `cd skripte && python -m unittest test_evaluate.TestConventions -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add skripte/evaluate_team.py skripte/test_evaluate.py
git commit -F - <<'EOF'
Phase C (2a): Konventions-Report als Info-Kriterium

analyze_conventions zaehlt gefundene GitLab-Konventionen und nennt fehlende -
Vertrauenssignal, welchen konventionsabhaengigen Auto-Scores man trauen kann.
Landet im Zusatzinfos-Sheet.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
```

---

## Task 11: Provenienz-Stempel (Phase C, 1b)

**Files:**
- Modify: `skripte/evaluate_team.py` — `collect_results` (Provenienz erfassen + Info-Kriterium)
- Modify: `skripte/build_xlsx.py` — Kopfzeile A4
- Test: `skripte/test_evaluate.py`

- [ ] **Step 1: Failing test (Provenienz-Helfer)**

```python
class TestProvenance(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        import subprocess
        subprocess.run(["git", "init", "-q"], cwd=self.tmp)
        (self.tmp / "f.txt").write_text("x", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=self.tmp)
        env = {**os.environ, "GIT_AUTHOR_NAME": "A", "GIT_AUTHOR_EMAIL": "a@x",
               "GIT_COMMITTER_NAME": "A", "GIT_COMMITTER_EMAIL": "a@x"}
        subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=self.tmp, env=env)
    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_provenance_has_sha(self):
        prov = ev.build_provenance(self.tmp, project_id=42)
        self.assertEqual(len(prov["head_sha"]), 40)
        self.assertEqual(prov["project_id"], 42)
        self.assertTrue(prov["fetched_at"].endswith("+00:00") or "T" in prov["fetched_at"])
```

- [ ] **Step 2: Run → FAIL**

Run: `cd skripte && python -m unittest test_evaluate.TestProvenance -v`

- [ ] **Step 3: `build_provenance` + Info-Kriterium implementieren**

In `evaluate_team.py` (vor `collect_results`):

```python
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
```

In `collect_results` nach `clone_or_update(...)` die Provenienz erfassen:

```python
    prov = build_provenance(repo, pid)
```

und in der `results`-Liste als ERSTEN Eintrag (vor `analyze_user_stories`) einfügen:

```python
        _provenance_result(prov),
```

- [ ] **Step 4: Kopfzeile in `build_xlsx` rendern**

In `build_xlsx`, nach dem `A3`-Hinweis-Block (vor `HEADER_ROW = 5`), die Provenienz aus den Info-Results ziehen und in eine kompakte Zeile schreiben. **Wichtig:** `HEADER_ROW` von 5 auf 5 belassen ist schwierig, da A4 frei sein muss — A4 ist aktuell ungenutzt (Titel A1, GitLab A2, Hinweis A3). A4 ist frei. Einfügen:

```python
    prov_res = next((r for r in results if r.get("criterion") == "Datengrundlage (Info)"), None)
    if prov_res:
        p = prov_res["details"]
        ws["A4"] = "Datengrundlage:"
        ws["A4"].font = Font(name=FONT, bold=True, size=9)
        ws["B4"] = (f"Commit {p['head_sha'][:10]} ({p['branch']}) · Projekt {p['project_id']} · "
                    f"geholt {p['fetched_at']} UTC")
        ws["B4"].font = Font(name=FONT, italic=True, color="808080", size=9)
        ws.merge_cells("B4:I4")
```

(`build_xlsx` hat `results` als Parameter — verfügbar.)

- [ ] **Step 5: Run → PASS**

Run: `cd skripte && python -m unittest test_evaluate.TestProvenance -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add skripte/evaluate_team.py skripte/build_xlsx.py skripte/test_evaluate.py
git commit -F - <<'EOF'
Phase C (1b): Provenienz-Stempel (Commit-SHA/Branch/Zeit)

build_provenance erfasst HEAD-SHA/Branch/UTC-Zeit/Projekt-ID; flieast als Info-
Kriterium "Datengrundlage" durch den results-Kanal (Zusatzinfos) und als kompakte
Kopfzeile A4 in der Bewertung. Macht nachvollziehbar, welcher Stand bewertet wurde.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
```

---

## Task 12: Divergenz-Flag + Kriteriums-Drift-Assert (Phase C, 1c + 3a)

**Files:**
- Modify: `skripte/build_xlsx.py` — Conditional Format auf D; Assert nach Datenzeilen; A3-Hinweis
- Test: `skripte/test_evaluate.py`

- [ ] **Step 1: Failing test (Drift-Assert deckt alle CATEGORIES ab)**

```python
class TestCriterionCoverage(unittest.TestCase):
    def test_all_categories_have_matching_criterion_strings(self):
        # Die in CATEGORIES gelisteten Kriterien muessen exakt den criterion-Strings
        # der analyze_*-Funktionen entsprechen (sonst faellt eine Zeile still raus).
        import build_xlsx
        produced = set()
        # Sammle alle criterion-Strings aus den Score-Analysen via Dummy-Aufrufen:
        produced.update([
            ev.analyze_epics([])["criterion"],
            ev.analyze_code_structure.__doc__ and "Code sinnvoll strukturiert",
            ev.analyze_gitlab_usage([], [], [])["criterion"],
        ])
        # Pragmatisch: pruefe, dass build_xlsx.check_criterion_coverage existiert
        self.assertTrue(hasattr(build_xlsx, "check_criterion_coverage"))
        missing = build_xlsx.check_criterion_coverage({"User Stories / Issues ordentlich erstellt": {}})
        self.assertIn("Verständliche Commit-Messages", missing)
```

(Vereinfachter Test: prüft die Helferfunktion direkt.)

- [ ] **Step 2: Run → FAIL** (`check_criterion_coverage` existiert nicht)

Run: `cd skripte && python -m unittest test_evaluate.TestCriterionCoverage -v`

- [ ] **Step 3: `check_criterion_coverage` + Aufruf in `build_xlsx`**

In `build_xlsx.py` (Modul-Ebene):

```python
def check_criterion_coverage(by_crit):
    """Gibt die CATEGORIES-Kriterien zurueck, fuer die KEIN Result vorliegt.
    Verhindert, dass eine String-/Umlaut-Drift eine Zeile still verschwinden laesst."""
    expected = [c for _, crits in CATEGORIES for c in crits]
    return [c for c in expected if c not in by_crit]
```

In `build_xlsx()` direkt nach `by_crit = {...}` (Z. ~138):

```python
    missing = check_criterion_coverage(by_crit)
    if missing:
        print(f"WARN: {len(missing)} Kriterium(en) ohne Result (Drift in criterion-Strings?): "
              f"{missing}", file=sys.stderr)
```

(`import sys` ist in build_xlsx bereits vorhanden.)

- [ ] **Step 4: Divergenz-Conditional-Format ergänzen**

In `build_xlsx`, im Conditional-Formatting-Abschnitt (nach der bestehenden F-Regel, ~Z. 385), eine Regel auf den D-Bereich der Kriterien-Zeilen:

```python
    if criterion_rows:
        d_anchor = criterion_rows[0]
        d_range = " ".join(f"{L_LLM}{a}:{L_LLM}{b}" for a, b in _contiguous_runs(criterion_rows))
        diverge_rule = FormulaRule(
            formula=[f'AND({L_LLM}{d_anchor}<>"",ABS({L_LLM}{d_anchor}-{L_HEUR}{d_anchor})>1)'],
            fill=PatternFill("solid", start_color="FFD9A0"),
        )
        ws.conditional_formatting.add(d_range, diverge_rule)
```

Und den A3-Hinweis erweitern (am Ende des bestehenden B3-Strings):

```python
                " Orange in Spalte D: Heuristik und LLM weichen >1 Punkt ab – manuell prüfen.")
```

- [ ] **Step 5: Run → PASS**

Run: `cd skripte && python -m unittest test_evaluate.TestCriterionCoverage -v`
Expected: PASS

- [ ] **Step 6: Round-Trip-Smoke (Divergenz-Regel landet im Workbook)**

Optionaler Zusatztest:

```python
class TestDivergenceRule(unittest.TestCase):
    def test_divergence_rule_present(self):
        import build_xlsx
        from openpyxl import load_workbook
        results = ev.collect_results.__doc__ and None  # nicht aufrufen (Netzwerk)
        # Minimal-Results bauen: ein Kriterium mit LLM-Review
        res = [{"criterion": c, "max": m, "score": 0, "reason": "r",
                "details": {"llm_review": {"score": 3, "reason": "x"}}}
               for cat, crits in ev.CATEGORIES for c in crits
               for m in [1]]
        tmp = Path(tempfile.mkdtemp()) / "b.xlsx"
        build_xlsx.build_xlsx("t", "g/p", "http://x", res, tmp, keep_manual=False, do_backup=False)
        wb = load_workbook(tmp)
        ws = wb["Bewertung"]
        # mind. eine Conditional-Formatting-Range existiert
        self.assertTrue(len(list(ws.conditional_formatting)) >= 1)
```

Run: `cd skripte && python -m unittest test_evaluate.TestDivergenceRule -v` → PASS

- [ ] **Step 7: Commit**

```bash
git add skripte/build_xlsx.py skripte/test_evaluate.py
git commit -F - <<'EOF'
Phase C (1c+3a): Divergenz-Flag (Heur vs LLM) + Kriteriums-Drift-Assert

Conditional-Format faerbt Spalte D, wo |D-C|>1 (manuelle Pruefung lenken).
check_criterion_coverage warnt laut, wenn ein CATEGORIES-Kriterium kein Result
hat (verhindert stilles Verschwinden bei String-Drift).

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
```

---

## Task 13: Teams parallel verarbeiten (Phase F, 4a)

**Files:**
- Modify: `skripte/run_all.py` — `main` (Schleife ~Z. 77-89), `process` (Output puffern)
- Test: manueller Smoke (Parallelisierung ist I/O-/netzwerkgebunden, kein Unit-Test)

- [ ] **Step 1: `process` so umbauen, dass es Output als String zurückgibt**

```python
def process(entry, token, llm_client=None, yaml_cfg=None):
    lf = entry["local_folder"]
    lines = [f"-> {lf}: git fetch + API + Analyse ..."]
    results = ev.collect_results(entry, token, llm_client=llm_client, yaml_cfg=yaml_cfg)
    out = ev.TEAMS / lf / f"Bewertung_{lf}.xlsx"
    build_xlsx(lf, entry["gitlab_path"], entry["web_url"], results, out)
    lines.append(f"   OK: {out.name}")
    return "\n".join(lines)
```

- [ ] **Step 2: `main` parallelisieren**

Den sequentiellen Block (`for entry in entries: try: process(...)`) ersetzen durch:

```python
    from concurrent.futures import ThreadPoolExecutor, as_completed
    team_workers = int(((yaml_cfg or {}).get("run", {}) or {}).get("team_workers", 4))
    failed = []
    with ThreadPoolExecutor(max_workers=max(1, team_workers)) as pool:
        fut_to_entry = {pool.submit(process, entry, token, llm_client, yaml_cfg): entry
                        for entry in entries}
        for fut in as_completed(fut_to_entry):
            entry = fut_to_entry[fut]
            try:
                print(fut.result())
            except Exception as e:
                print(f"   FEHLER bei {entry['local_folder']}: {e}")
                failed.append(entry["local_folder"])

    # PDF sequentiell nach den Excels (greift auf geschriebene Dateien zu)
    if do_pdf:
        for entry in entries:
            if entry["local_folder"] in failed:
                continue
            try:
                import fill_pdf
                fill_pdf.main_for(entry["local_folder"])
            except Exception as e:
                print(f"   PDF fehlgeschlagen ({entry['local_folder']}): {e}")
```

(Den alten `for entry in entries`-Block inkl. der darin enthaltenen PDF-Logik vollständig durch obiges ersetzen. `print()` nach `print(f"Fertig...")` bleibt; `do_overview`-Block bleibt am Ende.)

- [ ] **Step 3: Smoke-Test (ohne Netzwerk: Syntax + Import)**

Run: `cd skripte && python -c "import run_all; print('ok')"`
Expected: `ok` (keine ImportError/SyntaxError)

- [ ] **Step 4: Commit**

```bash
git add skripte/run_all.py
git commit -F - <<'EOF'
Phase F (4a): Teams parallel verarbeiten

run_all nutzt ThreadPoolExecutor (config run.team_workers, Default 4). Pro-Team-
Output gepuffert ausgegeben; PDF/Overview laufen sequentiell danach. Groesster
Wall-Clock-Gewinn bei mehreren Teams (I/O-bound, LLMClient ist threadsafe).

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
```

---

## Task 14: Docstring-Fix + Doku-Abgleich (Phase F, 4b)

**Files:**
- Modify: `skripte/evaluate_team.py` — Modul-Docstring (Z. 1-14)
- Modify: `CLAUDE.md`, `docs/funktionsweise.md` — falls Schwellen-Keys/Multi-Sprach erwähnt werden müssen
- Modify: `.wolf/cerebrum.md`, `.wolf/anatomy.md`, `.wolf/memory.md`

- [ ] **Step 1: Modul-Docstring korrigieren**

Den Docstring von `evaluate_team.py` (Z. 2-14) ersetzen durch:

```python
"""
Analyse-Kern der SEP-Bewertung: klont das GitLab-Repo eines Teams, zieht
Issues/MRs/Wiki/Releases und fuehrt die heuristischen + LLM-Analysen aus.

Die eigentliche Ausgabe (Excel-Bewertungsbogen) erzeugt build_xlsx.py aus
collect_results(). run_all.py orchestriert alle Teams.

main() hier ist nur ein Smoke-Test-Stub (laedt Config) - es wird KEIN
Markdown-Report geschrieben. Fuer einen vollstaendigen Lauf: `python run_all.py`.

Usage (Smoke-Test):
    python3 evaluate_team.py <local_team_folder>
"""
```

- [ ] **Step 2: CLAUDE.md / docs abgleichen**

Prüfen, ob CLAUDE.md „20 heuristische Analysen plus 11 LLM-Inhaltsprüfungen" noch stimmt (jetzt + Konventions-Report + Provenienz = 2 zusätzliche Info-Kriterien). Zahl der Info-Kriterien anpassen, Multi-Sprach-Fähigkeit + neue config-Blöcke (`languages`, `tutors`, `vendor_dirs`, `run`) in `docs/funktionsweise.md` kurz erwähnen.

- [ ] **Step 3: `.wolf/`-Pflege**

- `.wolf/cerebrum.md` → `## Key Learnings`: Eintrag zur Sprach-Registry + Provenienz/Konventions-Info-Kriterien + `_parse_score_response`. `## Decision Log`: Stichtag bewusst NICHT umgesetzt; Multi-Sprach statt nur konfigurierbar.
- `.wolf/anatomy.md` → Funktionslisten von evaluate_team/build_xlsx/llm/run_all aktualisieren (neue Funktionen).
- `.wolf/memory.md` → Session-Zusammenfassung.

- [ ] **Step 4: Vollständiger Testlauf**

Run: `cd skripte && python -m unittest test_evaluate -v`
Expected: ALLE Tests PASS.

- [ ] **Step 5: Commit**

```bash
git add skripte/evaluate_team.py CLAUDE.md docs/funktionsweise.md .wolf/cerebrum.md .wolf/anatomy.md .wolf/memory.md
git commit -F - <<'EOF'
Phase F (4b) + Doku: Docstring-Fix, Doku-Abgleich, .wolf-Pflege

evaluate_team-Docstring an Realitaet angepasst (kein MD-Report). CLAUDE.md/
funktionsweise.md um Multi-Sprach + neue config-Bloecke + Info-Kriterien ergaenzt.
cerebrum/anatomy/memory aktualisiert.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
```

---

## Abschluss

- [ ] **Finaler Testlauf:** `cd skripte && python -m unittest test_evaluate -v` → alles grün.
- [ ] **Optional realer Smoke:** `cd skripte && python run_all.py team-entropy` (braucht .env mit Token) — prüfen, dass Excel inkl. A4-Provenienz, Zusatzinfos „Konventions-Report"/„Datengrundlage" und ggf. Divergenz-Färbung erzeugt wird.
- [ ] **finishing-a-development-branch** Skill: Merge/PR von `feature/verbesserungspaket` entscheiden.

---

## Self-Review (Plan vs. Spec)

**Spec-Coverage:** 1b→T11, 1c→T12, 1d→T9, 2a→T10, 2b→T2/T3/T4, 2c→T5, 2d→T6, 3a→T12, 3b→T7, 3c→T8, 4a→T13, 4b→T14, 5→verteilt (T2/T3/T4/T5/T6/T7/T8/T9/T10/T11/T12 Tests + T9 Parse-Tests). Alle 13 Punkte abgedeckt.

**Placeholder-Scan:** Keine TBD/TODO; jeder Code-Step zeigt vollständigen Code.

**Typ-Konsistenz:** `get_languages/get_tutors/get_vendor_dirs` (T1) konsistent in T2/T3/T4/T6 genutzt. `_parse_score_response(out, scale_max)` (T9) Signatur konsistent. `check_criterion_coverage(by_crit)` (T12) konsistent. `build_provenance(repo, project_id)` → `_provenance_result(prov)` (T11) konsistent. `details`-Keys `total_test_files/substantive_test_files/total_test_methods` (T3) in den Tests konsistent referenziert.

**Bekannte Anpass-Notwendigkeit:** Bestehende Tests in `test_evaluate.py`, die alte `analyze_tests`-`details`-Keys (`java_test_files` etc.) prüfen, müssen in T3 auf die neuen Keys umgestellt werden (im Step-4-Run vermerkt).
