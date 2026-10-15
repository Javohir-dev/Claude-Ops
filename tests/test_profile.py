import json
import tempfile
import unittest
from pathlib import Path

import config as cfg
import detect
import stackprofile


class ProfileTest(unittest.TestCase):
    def setUp(self):
        cfg.save(cfg._empty())
        stackprofile.LOCAL.unlink(missing_ok=True)

    def test_generic_by_default(self):
        self.assertEqual(stackprofile.active()["id"], "generic")
        self.assertEqual(stackprofile.get("tasks.status_map"), {})

    def test_named_profile_merges_over_generic(self):
        cfg.set("project.profile", "odoo-docker-env", "user")
        p = stackprofile.active()
        self.assertEqual(p["id"], "odoo-docker-env")
        self.assertEqual(p["worktrees"]["repo"], "src/local")
        self.assertEqual(p["tasks"]["status_map"]["Готово"], "done")
        self.assertIn("clean_title", p["tasks"])

    def test_local_overlay_wins(self):
        cfg.set("project.profile", "odoo-docker-env", "user")
        stackprofile.LOCAL.write_text(json.dumps({"tasks": {"areas": {"labels": {"crm": "CRM"}}}}))
        self.assertEqual(stackprofile.get("tasks.areas.labels"), {"crm": "CRM"})
        self.assertEqual(stackprofile.get("worktrees.repo"), "src/local")

    def test_project_file_sits_between_profile_and_local(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / ".claude").mkdir()
            (Path(d) / ".claude" / "opsboard.profile.json").write_text(json.dumps({"tasks": {"areas": {"labels": {"crm": "CRM (team)", "voip": "VoIP"}}}}))
            cfg.set("project.root", d, "user")
            cfg.set("project.profile", "odoo-docker-env", "user")
            self.assertEqual(stackprofile.get("tasks.areas.labels"), {"crm": "CRM (team)", "voip": "VoIP"})
            stackprofile.LOCAL.write_text(json.dumps({"tasks": {"areas": {"labels": {"crm": "Mine"}}}}))
            self.assertEqual(stackprofile.get("tasks.areas.labels"), {"crm": "Mine", "voip": "VoIP"})

    def test_unknown_profile_falls_back(self):
        cfg.set("project.profile", "nope", "user")
        self.assertEqual(stackprofile.active()["id"], "generic")

    def test_detect_profile(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.assertEqual(detect.detect_profile(root)["project.profile"]["value"], "generic")
            (root / "src" / "local").mkdir(parents=True)
            (root / "docker-compose.yml").write_text("services:\n  odoo:\n    image: odoo:16\n")
            self.assertEqual(detect.detect_profile(root)["project.profile"]["value"], "odoo-docker-env")


if __name__ == "__main__":
    unittest.main()
