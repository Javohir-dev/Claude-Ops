import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import runs
from core import popen


class RefreshRunsTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.log = Path(self.dir.name) / "r.jsonl"
        self.proc = subprocess.Popen(["sleep", "30"])
        popen[self.proc.pid] = self.proc
        self.store = []
        patches = [mock.patch.object(runs, "load_runs", lambda: self.store), mock.patch.object(runs, "save_runs", lambda r: None)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        self.proc.kill()
        self.proc.wait()
        popen.pop(self.proc.pid, None)
        self.dir.cleanup()

    def write(self, *events):
        self.log.write_text("\n".join(json.dumps(e) for e in events))

    def run_entry(self, status="running"):
        self.store.append({"id": "x", "iid": 1, "prompt": "/fix 1", "pid": self.proc.pid, "started": runs.time.time(), "status": status, "log": str(self.log)})
        return self.store[0]

    def test_result_while_alive_keeps_running(self):
        self.write({"type": "result", "result": "first"}, {"type": "result", "result": "second"})
        r = self.run_entry()
        runs.refresh_runs()
        self.assertEqual(r["status"], "running")
        self.assertEqual(r["result"], "second")
        self.proc.kill()
        self.proc.wait()
        runs.refresh_runs()
        self.assertEqual(r["status"], "done")

    def test_done_but_alive_is_reopened(self):
        self.write({"type": "result", "result": "turn"})
        r = self.run_entry(status="done")
        runs.refresh_runs()
        self.assertEqual(r["status"], "running")

    def test_exit_without_result_is_error(self):
        self.write({"type": "system", "session_id": "s"})
        r = self.run_entry()
        self.proc.kill()
        self.proc.wait()
        runs.refresh_runs()
        self.assertEqual(r["status"], "error")
        self.assertEqual(r["session_id"], "s")


if __name__ == "__main__":
    unittest.main()
