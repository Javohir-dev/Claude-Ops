import json
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid

from core import DATA, log

FILE = DATA / "notifications.json"
KEEP = 100
PAGE_GONE = 75
_lock = threading.Lock()
_last_alerting_page = 0.0


def load():
    try:
        items = json.loads(FILE.read_text())
        return items if isinstance(items, list) else []
    except (OSError, ValueError):
        return []


def _save(items):
    tmp = FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(items[:KEEP], ensure_ascii=False))
    os.replace(tmp, FILE)


def page_seen(alerts):
    global _last_alerting_page
    if alerts:
        _last_alerting_page = time.time()


def run_finished(r, mr_title=""):
    item = {
        "id": uuid.uuid4().hex[:12],
        "kind": "run",
        "run_id": r["id"],
        "iid": r.get("iid"),
        "name": r.get("name", ""),
        "status": r["status"],
        "outcome": r.get("outcome"),
        "error": ((r.get("result") or "").strip().splitlines() or [""])[-1][:300] if r["status"] == "error" else "",
        "mr_title": mr_title,
        "at": time.time(),
        "read": False,
    }
    with _lock:
        items = [x for x in load() if x.get("run_id") != r["id"]]
        _save([item] + items)
    if time.time() - _last_alerting_page > PAGE_GONE:
        os_notify(*text(item))
    return item


def text(item):
    o = item.get("outcome") or {}
    ref = f"!{item['iid']}" if item.get("iid") else item.get("name", "")
    if item["status"] == "error":
        head, body = f"Fix failed · {ref}", item.get("error") or "the run ended with an error"
    elif o.get("status") == "stopped":
        head, body = f"Fix stopped · {ref}", o.get("note") or "it could not finish"
    else:
        head = f"Fix {o.get('status') or 'finished'} · {ref}"
        th = o.get("threads") or {}
        parts = [str(o["commit"])[:10] if o.get("commit") else "", f"threads {th.get('resolved', 0)} resolved · {th.get('open', 0)} open" if th else "", o.get("checks") or "", o.get("note") or ""]
        body = " · ".join(p for p in parts if p) or item.get("mr_title") or "done"
    return head, body


def mark_read(ids=None):
    with _lock:
        items = load()
        for x in items:
            if ids is None or x["id"] in ids:
                x["read"] = True
        _save(items)


def clear():
    with _lock:
        _save([])


def os_notify(title, body):
    if os.environ.get("OPS_NO_OS_NOTIFY"):
        return
    try:
        if sys.platform == "darwin":
            script = ["-e", "on run argv", "-e", 'display notification (item 2 of argv) with title "Opsboard" subtitle (item 1 of argv)', "-e", "end run"]
            subprocess.Popen(["osascript", *script, title, body], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif shutil.which("notify-send"):
            subprocess.Popen(["notify-send", "-a", "Opsboard", title, body], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as exc:
        log.warning("desktop notification failed: %s", exc)
