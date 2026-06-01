#!/usr/bin/env python3
"""
Tests fuer gen_mapping.py (Generierung von team_mapping.json aus teams.txt).

Ausfuehren (aus skripte/):
    python -m unittest test_gen_mapping -v

Alle Tests sind netzfrei: die GitLab-API wird nicht aufgerufen, stattdessen
werden API-Antworten als Fixtures uebergeben. Getestet werden die reinen
Funktionen (Namens-Ableitung, Eintrags-Bau, idempotenter Merge).

Format: eine teams.txt-Zeile = der kombinierte GitLab-Name 'cohort-kurz'
(z.B. 'shannon-bit'), mit oder ohne fuehrendes 'team-'. Kein Cohort-Default
und keine Zwei-Token-Form mehr.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gen_mapping as gm


# Beispiel-Antwort der GitLab-API fuer GET /projects/<id-oder-pfad>
def _project(path_with_namespace, pid):
    name = path_with_namespace.rsplit("/", 1)[-1]
    return {
        "id": pid,
        "name": name,
        "path": name,
        "path_with_namespace": path_with_namespace,
        "http_url_to_repo": f"https://gitlab.git.nrw/{path_with_namespace}.git",
        "ssh_url_to_repo": f"git@gitlab.git.nrw:{path_with_namespace}.git",
        "web_url": f"https://gitlab.git.nrw/{path_with_namespace}",
    }


class ParseLineTests(unittest.TestCase):
    def test_combined_form_passes_through(self):
        self.assertEqual(gm.parse_line("shannon-bit"), "shannon-bit")

    def test_strips_leading_team_prefix(self):
        self.assertEqual(gm.parse_line("team-shannon-bit"), "shannon-bit")

    def test_strips_surrounding_whitespace(self):
        self.assertEqual(gm.parse_line("  shannon-entropy  "), "shannon-entropy")

    def test_blank_line_returns_none(self):
        self.assertIsNone(gm.parse_line("   "))

    def test_comment_line_returns_none(self):
        self.assertIsNone(gm.parse_line("# ein Kommentar"))

    def test_inline_comment_is_stripped(self):
        self.assertEqual(gm.parse_line("shannon-bit  # das Bit-Team"), "shannon-bit")

    def test_keeps_internal_hyphens_in_short(self):
        self.assertEqual(gm.parse_line("shannon-my-team"), "shannon-my-team")

    def test_bare_short_without_hyphen_passes_through(self):
        # Validierung (fehlendes '-') passiert spaeter in main, nicht hier.
        self.assertEqual(gm.parse_line("bit"), "bit")


class ShortOfTests(unittest.TestCase):
    def test_short_is_part_after_first_hyphen(self):
        self.assertEqual(gm.short_of("shannon-bit"), "bit")

    def test_short_keeps_internal_hyphens(self):
        self.assertEqual(gm.short_of("shannon-my-team"), "my-team")

    def test_no_hyphen_returns_input(self):
        self.assertEqual(gm.short_of("bit"), "bit")


class ReadTeamsTests(unittest.TestCase):
    def test_reads_dedupes_by_short_and_strips_prefix(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "teams.txt"
            p.write_text(
                "# Liste\nshannon-bit\nteam-shannon-entropy\n\nshannon-bit\n"
                "lovelace-poetical\nteam-lovelace-poetical\n",
                encoding="utf-8",
            )
            self.assertEqual(
                gm.read_teams(p),
                ["shannon-bit", "shannon-entropy", "lovelace-poetical"],
            )


class ProjectPathTests(unittest.TestCase):
    def test_builds_full_path_from_combined_name(self):
        self.assertEqual(
            gm.project_path(
                "ude-sse/sep-summer-2026/student_projects", "shannon-bit"
            ),
            "ude-sse/sep-summer-2026/student_projects/team-shannon-bit",
        )


class EntryFromProjectTests(unittest.TestCase):
    def setUp(self):
        self.proj = _project(
            "ude-sse/sep-summer-2026/student_projects/team-shannon-bit", 3492
        )
        self.entry = gm.entry_from_project(self.proj, "bit")

    def test_local_folder_has_no_cohort_token(self):
        self.assertEqual(self.entry["local_folder"], "team-bit")

    def test_name_is_full_gitlab_project_name(self):
        self.assertEqual(self.entry["name"], "team-shannon-bit")

    def test_gitlab_path_from_api(self):
        self.assertEqual(
            self.entry["gitlab_path"],
            "ude-sse/sep-summer-2026/student_projects/team-shannon-bit",
        )

    def test_gitlab_id_from_api(self):
        self.assertEqual(self.entry["gitlab_id"], 3492)

    def test_urls_from_api(self):
        self.assertEqual(
            self.entry["http_url"],
            "https://gitlab.git.nrw/ude-sse/sep-summer-2026/student_projects/team-shannon-bit.git",
        )
        self.assertEqual(
            self.entry["ssh_url"],
            "git@gitlab.git.nrw:ude-sse/sep-summer-2026/student_projects/team-shannon-bit.git",
        )
        self.assertEqual(
            self.entry["web_url"],
            "https://gitlab.git.nrw/ude-sse/sep-summer-2026/student_projects/team-shannon-bit",
        )

    def test_has_exactly_the_expected_keys(self):
        self.assertEqual(
            set(self.entry.keys()),
            {
                "local_folder",
                "gitlab_path",
                "gitlab_id",
                "name",
                "http_url",
                "ssh_url",
                "web_url",
            },
        )


class MergeEntriesTests(unittest.TestCase):
    def _entry(self, short, pid):
        return gm.entry_from_project(
            _project(
                f"ude-sse/sep-summer-2026/student_projects/team-shannon-{short}",
                pid,
            ),
            short,
        )

    def test_adds_new_entries_sorted_by_local_folder(self):
        merged = gm.merge_entries([], [self._entry("entropy", 1), self._entry("bit", 2)])
        self.assertEqual([e["local_folder"] for e in merged], ["team-bit", "team-entropy"])

    def test_updates_existing_entry_in_place(self):
        old = self._entry("bit", 999)
        new = self._entry("bit", 3492)
        merged = gm.merge_entries([old], [new])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["gitlab_id"], 3492)

    def test_keeps_unlisted_existing_entries(self):
        existing = [self._entry("noisy", 7)]
        merged = gm.merge_entries(existing, [self._entry("bit", 2)])
        folders = [e["local_folder"] for e in merged]
        self.assertIn("team-noisy", folders)
        self.assertIn("team-bit", folders)

    def test_idempotent_running_twice_changes_nothing(self):
        new = [self._entry("bit", 2), self._entry("entropy", 1)]
        once = gm.merge_entries([], new)
        twice = gm.merge_entries(once, new)
        self.assertEqual(once, twice)


if __name__ == "__main__":
    unittest.main()
