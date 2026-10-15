import unittest

import config as cfg
import core
import detect
import notes
import server


class ParsingTest(unittest.TestCase):
    def test_parse_remote(self):
        self.assertEqual(detect.parse_remote("git@gitlab.example.com:team/app.git"), ("https://gitlab.example.com", "team/app"))
        self.assertEqual(detect.parse_remote("https://github.com/acme/tool.git"), ("https://github.com", "acme/tool"))
        self.assertEqual(detect.parse_remote("ssh://git@host:2222/a/b"), ("https://host", "a/b"))
        self.assertIsNone(detect.parse_remote("not a remote"))

    def test_status_bucket_falls_back_to_category(self):
        self.assertEqual(detect.status_bucket("Something odd", "done"), "done")
        self.assertEqual(detect.status_bucket("Something odd", "indeterminate"), "doing")
        self.assertEqual(detect.status_bucket("Something odd", "new"), "todo")

    def test_epoch_handles_nanoseconds_and_compact_offsets(self):
        self.assertAlmostEqual(core.epoch("2026-10-15T10:00:00.123456789Z"), core.epoch("2026-10-15T10:00:00.123456Z"))
        self.assertEqual(core.epoch("2026-10-15T15:00:00.000+0500"), core.epoch("2026-10-15T10:00:00.000Z"))

    def test_redact(self):
        cfg.save(cfg._empty())
        cfg._secrets.clear()
        cfg.set_secret("jira.token", "my-very-own-jira-secret")
        text = "jira my-very-own-jira-secret gl glpat-AAAAAAAAAAAAAAAAAAAA gh ghp_" + "b" * 36
        out = server.redact(text)
        self.assertNotIn("my-very-own-jira-secret", out)
        self.assertNotIn("glpat-", out)
        self.assertNotIn("ghp_", out)

    def test_marks_validation(self):
        with self.assertRaises(ValueError):
            notes.set_mark("../etc", "red")
        with self.assertRaises(ValueError):
            notes.set_mark("AD-1", "pink")
        notes.set_mark("!42", "red")
        self.assertEqual(notes.load_marks()["!42"], "red")


if __name__ == "__main__":
    unittest.main()
