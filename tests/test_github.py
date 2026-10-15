import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import config as cfg
from core import state
from providers import github

CALLS = []
PR = {
    "number": 5,
    "title": "(AB-12) - shop: faster cart",
    "html_url": "https://example/pr/5",
    "state": "open",
    "draft": False,
    "mergeable_state": "dirty",
    "head": {"ref": "feat/cart", "sha": "abc"},
    "base": {"ref": "main"},
    "user": {"login": "me"},
    "requested_reviewers": [{"login": "rev"}],
    "body": "old",
}


class FakeGitHub(BaseHTTPRequestHandler):
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
        if path == "/api/v3/user":
            return self.reply({"login": "me"})
        if path == "/api/v3/search/issues":
            return self.reply(
                {
                    "items": [
                        dict(PR, labels=[{"name": "bug", "color": "d73a4a"}], created_at="2026-10-01T10:00:00Z", updated_at="2026-10-02T10:00:00Z", pull_request={"merged_at": None}),
                        {"number": 4, "title": "old one", "html_url": "u4", "state": "closed", "user": {"login": "me"}, "labels": [], "pull_request": {"merged_at": "2026-09-01T10:00:00Z"}},
                    ]
                }
            )
        if path == "/api/v3/repos/acme/shop/pulls/5":
            return self.reply(PR)
        if path == "/api/v3/repos/acme/shop/pulls/6":
            return self.reply(dict(PR, number=6, user={"login": "someone"}))
        if path == "/api/v3/repos/acme/shop/pulls/5/reviews":
            return self.reply([{"user": {"login": "rev"}, "state": "CHANGES_REQUESTED"}, {"user": {"login": "rev"}, "state": "APPROVED"}])
        if path == "/api/v3/repos/acme/shop/commits/abc/check-runs":
            return self.reply({"check_runs": [{"status": "completed", "conclusion": "success"}, {"status": "in_progress", "conclusion": None}]})
        self.reply({}, 404)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        CALLS.append(("POST", self.path, body))
        if self.path == "/api/graphql":
            if "reviewThreads" in body["query"]:
                nodes = [
                    {"id": "T1", "isResolved": False, "path": "cart.py", "line": 3, "comments": {"nodes": [{"author": {"login": "rev"}, "body": "slow", "url": "c1"}]}},
                    {"id": "T2", "isResolved": True, "path": "cart.py", "line": 9, "comments": {"nodes": [{"author": {"login": "rev"}, "body": "ok", "url": "c2"}]}},
                ]
                return self.reply({"data": {"repository": {"pullRequest": {"reviewThreads": {"pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": nodes}}}}})
            return self.reply({"data": {}})
        self.reply({}, 404)

    def do_PATCH(self):
        CALLS.append(("PATCH", self.path, json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))))
        self.reply({})


class GitHubTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeGitHub)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        cfg.save(cfg._empty())
        cfg._secrets.clear()
        cfg.set("review.host", "github", "user")
        cfg.set("github.url", f"http://127.0.0.1:{self.server.server_port}", "user")
        cfg.set("github.repo", "acme/shop", "user")
        cfg.set("jira.projects", ["AB"], "user")
        cfg.set_secret("github.token", "test-token")
        CALLS.clear()

    def test_collect_normalises_pull_requests(self):
        github.collect()
        review = state["review"]
        self.assertEqual(review["host"], "github")
        pr, old = review["mrs"]
        self.assertEqual((pr["iid"], pr["state"], pr["conflicts"], pr["source"], pr["target"]), (5, "opened", True, "feat/cart", "main"))
        self.assertEqual((pr["threads"], pr["threads_total"], pr["pipeline"]), (1, 2, "running"))
        self.assertEqual((pr["approved"], pr["approved_by"]), (True, ["rev"]))
        self.assertEqual(pr["keys"], ["AB-12"])
        self.assertEqual(old["state"], "merged")
        self.assertEqual(review["labels"]["bug"], {"color": "#d73a4a", "text": "#ffffff"})

    def test_threads_reply_resolve(self):
        self.assertEqual([t["id"] for t in github.threads(5)], ["T1"])
        github.reply(5, "T1", "fixed", resolve=True)
        mutations = [c[2]["query"] for c in CALLS if "mutation" in c[2].get("query", "")]
        self.assertEqual(len(mutations), 2)
        self.assertIn("addPullRequestReviewThreadReply", mutations[0])
        self.assertIn("resolveReviewThread", mutations[1])

    def test_someone_elses_pull_request_is_refused(self):
        with self.assertRaises(PermissionError):
            github.reply(6, "T1", "x")
        self.assertFalse([c for c in CALLS if "mutation" in c[2].get("query", "")])

    def test_describe(self):
        self.assertEqual(github.describe(5, "new"), "old")
        self.assertEqual(CALLS[-1][0], "PATCH")

    def test_upload_is_not_supported(self):
        with self.assertRaises(ValueError):
            github.upload("x.txt")


if __name__ == "__main__":
    unittest.main()
