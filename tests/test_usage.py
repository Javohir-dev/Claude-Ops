import json
import os
import unittest
from pathlib import Path

import core
import system


class ClaudeUsageTest(unittest.TestCase):
    def setUp(self):
        self.path = Path(os.environ["OPS_DATA_DIR"]) / "claude.json"
        system.CLAUDE_STATE = self.path

    def test_reads_the_cached_limits(self):
        limits = [
            {"kind": "session", "percent": 38, "severity": "normal", "resets_at": "2026-10-15T15:30:00+00:00", "scope": None, "is_active": True},
            {"kind": "weekly_all", "percent": 34, "severity": "normal", "resets_at": "2026-10-20T11:00:00+00:00", "scope": None},
            {"kind": "weekly_scoped", "percent": 0, "resets_at": "2026-10-20T11:00:00+00:00", "scope": {"model": {"display_name": "Fable"}}},
        ]
        self.path.write_text(
            json.dumps(
                {
                    "oauthAccount": {"emailAddress": "dev@acme.example", "organizationName": "Acme", "organizationType": "claude_team"},
                    "cachedUsageUtilization": {"fetchedAtMs": 1792076054261, "accountUuid": "acct-51c97336-secret", "utilization": {"limits": limits}},
                }
            )
        )
        system.collect_claude_usage()
        usage = core.state["claude_usage"]
        self.assertEqual([x["label"] for x in usage["limits"]], ["Session (5hr)", "Weekly (7 day)", "Weekly Fable"])
        self.assertEqual(usage["limits"][0]["percent"], 38)
        self.assertAlmostEqual(usage["fetched"], 1792076054.261)
        self.assertEqual(usage["account"], {"email": "dev@acme.example", "org": "Acme", "plan": "Claude Team"})
        self.assertNotIn("acct-51c97336", json.dumps(usage))

    def test_missing_file_is_empty(self):
        self.path.unlink(missing_ok=True)
        system.collect_claude_usage()
        self.assertEqual(core.state["claude_usage"], {})


if __name__ == "__main__":
    unittest.main()
