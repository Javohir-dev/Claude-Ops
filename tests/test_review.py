import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import config as cfg
import runs
from providers import gitlab

CALLS = []


class FakeGitLab(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, body, code=200):
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/v4/user":
            return self.reply({"username": "me", "name": "Me"})
        if path.endswith("/merge_requests/1"):
            return self.reply({"iid": 1, "title": "t", "web_url": "u", "state": "opened", "source_branch": "f", "target_branch": "main", "author": {"username": "me"}})
        if path.endswith("/merge_requests/2"):
            return self.reply({"iid": 2, "author": {"username": "someone"}})
        if path.endswith("/merge_requests/1/discussions"):
            return self.reply(
                [
                    {"id": "d1", "notes": [{"id": 10, "system": False, "author": {"username": "rev"}, "body": "fix", "resolvable": True, "resolved": False}]},
                    {"id": "d2", "notes": [{"id": 11, "system": False, "author": {"username": "rev"}, "body": "ok", "resolvable": True, "resolved": True}]},
                    {"id": "d3", "notes": [{"id": 12, "system": True, "author": {"username": "rev"}, "body": "sys"}]},
                    {"id": "d4", "notes": [{"id": 13, "system": False, "author": {"username": "me"}, "body": "mine", "resolvable": True}]},
                ]
            )
        self.reply({}, 404)

    def do_POST(self):
        CALLS.append(("POST", self.path, self.rfile.read(int(self.headers.get("Content-Length") or 0))))
        self.reply({"id": 1})

    def do_PUT(self):
        CALLS.append(("PUT", self.path, self.rfile.read(int(self.headers.get("Content-Length") or 0))))
        self.reply({})


class ReviewTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeGitLab)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        cfg.save(cfg._empty())
        cfg._secrets.clear()
        cfg.set("gitlab.url", f"http://127.0.0.1:{self.server.server_port}", "user")
        cfg.set("gitlab.project", "team/app", "user")
        cfg.set_secret("gitlab.token", "test-token")
        CALLS.clear()

    def test_threads_are_open_and_from_others(self):
        self.assertEqual([t["id"] for t in gitlab.threads(1)], ["d1"])
        self.assertEqual([t["id"] for t in gitlab.threads(1, include_resolved=True)], ["d1", "d2"])

    def test_someone_elses_merge_request_is_refused(self):
        with self.assertRaises(PermissionError):
            gitlab.threads(2)
        with self.assertRaises(PermissionError):
            gitlab.reply(2, "d1", "x", resolve=True)
        self.assertEqual(CALLS, [])

    def test_reply_and_resolve(self):
        gitlab.reply(1, "d1", "done", resolve=True)
        self.assertEqual([c[0] for c in CALLS], ["POST", "PUT"])
        self.assertIn(b'"done"', CALLS[0][2])
        self.assertIn("resolved=true", CALLS[1][1])

    def test_not_configured(self):
        cfg.set("gitlab.project", "", "user")
        with self.assertRaises(ValueError):
            gitlab.info(1)


class FixContractTest(unittest.TestCase):
    def setUp(self):
        cfg.save(cfg._empty())

    def test_prompt_words(self):
        cfg.set("claude.fix_skill", "my-fix", "user")
        self.assertEqual(runs.fix_prompt(7, {"threads": True, "push": True}), "/my-fix 7 push")
        self.assertEqual(runs.fix_prompt(7, {"threads": True, "push": True, "skiptests": True}), "/my-fix 7 push skip-tests")
        self.assertEqual(runs.fix_prompt(7, {"conflict": True}), "/my-fix 7 conflict-only")

    def test_no_skill_chosen(self):
        with self.assertRaises(ValueError):
            runs.fix_prompt(7, {"threads": True})

    def test_outcome_line(self):
        text = 'done\nOPS_RESULT {"status":"pushed","commit":"abc"}\n'
        self.assertEqual(runs.parse_outcome(text), {"status": "pushed", "commit": "abc"})
        self.assertIsNone(runs.parse_outcome("no result here"))
        self.assertIsNone(runs.parse_outcome("OPS_RESULT {broken"))


if __name__ == "__main__":
    unittest.main()
