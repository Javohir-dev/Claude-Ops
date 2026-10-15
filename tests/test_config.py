import os
import unittest

import config as cfg


class ConfigTest(unittest.TestCase):
    def setUp(self):
        cfg.save(cfg._empty())
        cfg._secrets.clear()

    def test_writes_into_the_test_data_dir(self):
        self.assertTrue(str(cfg.CONFIG_FILE).startswith(os.environ["OPS_DATA_DIR"]))

    def test_precedence(self):
        self.assertEqual(cfg.get("server.port"), 8095)
        cfg.set("server.port", 9001, "auto")
        cfg.set("server.port", 9002, "agent")
        self.assertEqual(cfg.get("server.port"), 9002)
        cfg.set("server.port", 9003, "user")
        self.assertEqual(cfg.entry("server.port")["source"], "user")
        os.environ["OPS_PORT"] = "9004"
        try:
            self.assertEqual(cfg.entry("server.port"), {"value": "9004", "source": "env", "from": "OPS_PORT"})
        finally:
            del os.environ["OPS_PORT"]

    def test_secret_is_masked_in_public(self):
        cfg.set_secret("gitlab.token", "glpat-abcdefghijklmnop1234")
        self.assertEqual(cfg.secret("gitlab.token"), "glpat-abcdefghijklmnop1234")
        pub = cfg.public()
        self.assertEqual(pub["_secrets"]["gitlab.token"], "••••1234")
        self.assertNotIn("glpat-", str(pub))

    def test_unknown_secret_rejected(self):
        with self.assertRaises(ValueError):
            cfg.set_secret("aws.key", "x")

    def test_clearing_a_secret(self):
        cfg.set_secret("jira.token", "abc")
        cfg.set_secret("jira.token", "")
        self.assertEqual(cfg.secret("jira.token"), "")


if __name__ == "__main__":
    unittest.main()
