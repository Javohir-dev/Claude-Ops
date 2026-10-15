import json
import unittest

import demo


class DemoTest(unittest.TestCase):
    def test_demo_state_has_every_page(self):
        state = demo.build(1_800_000_000)
        for key in ("sessions", "containers", "pg", "worktrees", "review", "jira", "mac", "history", "runs"):
            self.assertIn(key, state)
        self.assertEqual(state["review"]["host"], "github")
        json.dumps(state)

    def test_demo_uses_only_example_identities(self):
        import re

        text = json.dumps(demo.build(1_800_000_000)) + json.dumps(demo.DEMO_CONFIG)
        self.assertTrue(all(e.endswith(("acme.example", "example.com")) for e in re.findall(r"[\w.+-]+@[\w.-]+", text)))
        self.assertTrue(all(h in ("github.com", "acme.atlassian.net") for h in re.findall(r"https://([\w.-]+)", text)))

if __name__ == "__main__":
    unittest.main()
