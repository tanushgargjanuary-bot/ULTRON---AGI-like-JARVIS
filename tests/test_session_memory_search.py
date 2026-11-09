"""Recall saved session summaries through the existing memory search path."""

import unittest
from unittest.mock import patch

from memory import memory_manager


class SessionMemorySearchTests(unittest.TestCase):
    def setUp(self):
        self.memory = {
            "identity": {},
            "preferences": {},
            "projects": {},
            "relationships": {},
            "wishes": {},
            "notes": {
                "preferred_editor": {
                    "value": "Visual Studio Code",
                    "updated": "2026-11-08",
                },
            },
            "sessions": [
                {"date": "2026-11-05", "summary": "Planned the old project schedule."},
            {"date": "2026-11-06", "summary": "Discussed local model routing."},
                {"date": "2026-11-07", "summary": "Reviewed the MCP server design."},
                {"date": "2026-11-08", "summary": "Worked on ULTRON branch consolidation."},
            ],
        }

    def search(self, query, limit=8):
        with patch.object(memory_manager, "load_memory", return_value=self.memory):
            return memory_manager.search_memory(query, limit=limit)

    def test_search_finds_terms_in_session_summaries(self):
        result = self.search("MCP server")
        self.assertIn("session/2026-11-07", result)
        self.assertIn("Reviewed the MCP server design.", result)

    def test_temporal_query_returns_recent_session_summaries(self):
        result = self.search("yesterday")
        self.assertIn("session/2026-11-08", result)
        self.assertNotIn("session/2026-11-05", result)

    def test_date_can_be_used_as_a_search_term(self):
        result = self.search("2026-11-06")
        self.assertIn("session/2026-11-06", result)

    def test_empty_query_includes_saved_sessions(self):
        result = self.search("")
        self.assertIn("session/2026-11-08", result)
        self.assertIn("Visual Studio Code", result)

    def test_limit_applies_to_combined_facts_and_sessions(self):
        result = self.search("", limit=1)
        self.assertEqual(result.count("\n"), 2)

    def test_malformed_session_rows_are_ignored(self):
        self.memory["sessions"].insert(0, None)
        self.memory["sessions"].insert(1, {"date": "2026-11-09"})
        result = self.search("history")
        self.assertNotIn("None", result)
        self.assertNotIn("session/2026-11-09", result)


if __name__ == "__main__":
    unittest.main()
