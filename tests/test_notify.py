import time
import unittest
from unittest import mock

import notify


def run(status="done", outcome=None, result=""):
    return {"id": "r1", "iid": 7, "name": "fix !7", "status": status, "outcome": outcome, "result": result}


class NotifyTest(unittest.TestCase):
    def setUp(self):
        notify.clear()
        notify._last_alerting_page = 0.0
        p = mock.patch.object(notify, "os_notify")
        self.os_notify = p.start()
        self.addCleanup(p.stop)

    def test_one_unread_item_per_run(self):
        notify.run_finished(run(), "Fix totals")
        notify.mark_read()
        notify.run_finished(run(status="error", result="boom\nlast line"))
        items = notify.load()
        self.assertEqual(len(items), 1)
        self.assertEqual((items[0]["status"], items[0]["error"], items[0]["read"]), ("error", "last line", False))

    def test_desktop_alert_only_without_an_alerting_page(self):
        notify.run_finished(run())
        self.assertEqual(self.os_notify.call_count, 1)
        notify.page_seen(False)
        notify.run_finished(run())
        self.assertEqual(self.os_notify.call_count, 2)
        notify.page_seen(True)
        notify.run_finished(run())
        self.assertEqual(self.os_notify.call_count, 2)
        notify._last_alerting_page = time.time() - notify.PAGE_GONE - 1
        notify.run_finished(run())
        self.assertEqual(self.os_notify.call_count, 3)

    def test_text(self):
        o = {"status": "pushed", "commit": "a1b2c3d", "threads": {"resolved": 3, "open": 0}, "checks": "tests 4/4"}
        self.assertEqual(notify.text(notify.run_finished(run(outcome=o))), ("Fix pushed · !7", "a1b2c3d · threads 3 resolved · 0 open · tests 4/4"))
        self.assertEqual(notify.text(notify.run_finished(run(outcome={"status": "stopped", "note": "conflict"})))[0], "Fix stopped · !7")
        self.assertEqual(notify.text(notify.run_finished(run(status="error", result="  ")))[1], "the run ended with an error")

    def test_mark_read_and_clear(self):
        a = notify.run_finished(run())
        notify.run_finished({**run(), "id": "r2"})
        notify.mark_read({a["id"]})
        self.assertEqual([x["read"] for x in notify.load()], [False, True])
        notify.clear()
        self.assertEqual(notify.load(), [])


if __name__ == "__main__":
    unittest.main()
