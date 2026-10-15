import json
import os
import socket
import subprocess
import sys
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from tests import DATA, ROOT


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class HttpTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.port = free_port()
        env = dict(os.environ, OPS_DATA_DIR=DATA, OPS_SECRET_STORE="file")
        cls.proc = subprocess.Popen([sys.executable, str(ROOT / "server.py"), "--port", str(cls.port)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.time() + 20
        while time.time() < deadline:
            try:
                urllib.request.urlopen(cls.url("/api/notes"), timeout=1)
                break
            except OSError:
                time.sleep(0.2)
        cls.token = (Path(DATA) / ".page-token").read_text().strip()

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        cls.proc.wait(10)

    @classmethod
    def url(cls, path):
        return f"http://127.0.0.1:{cls.port}{path}"

    def call(self, path, body=None, headers=None):
        req = urllib.request.Request(self.url(path), data=json.dumps(body).encode() if body is not None else None, headers=headers or {}, method="POST" if body is not None else "GET")
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, r.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, ""

    def test_page_carries_token(self):
        status, page = self.call("/")
        self.assertEqual(status, 200)
        self.assertIn(self.token, page)

    def test_foreign_host_is_refused(self):
        self.assertEqual(self.call("/api/state", headers={"Host": "evil.example"})[0], 421)
        self.assertEqual(self.call("/api/notes", {"items": []}, {"Host": "evil.example", "X-Ops-Token": self.token})[0], 421)

    def test_post_needs_token(self):
        self.assertEqual(self.call("/api/notes", {"version": 0, "items": []})[0], 403)
        self.assertEqual(self.call("/api/notes", {"version": 0, "items": []}, {"X-Ops-Token": "wrong"})[0], 403)

    def test_foreign_origin_is_refused(self):
        h = {"X-Ops-Token": self.token, "Origin": "http://evil.example"}
        self.assertEqual(self.call("/api/notes", {"version": 0, "items": []}, h)[0], 403)

    def test_post_with_token(self):
        status, body = self.call("/api/notes", {"version": 99, "items": []}, {"X-Ops-Token": self.token, "Content-Type": "application/json"})
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["ok"])


if __name__ == "__main__":
    unittest.main()
