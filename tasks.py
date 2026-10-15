import json
import threading
from urllib import error

import config as cfg
from core import DATA, http_json, jira_site, lock, put, state
from providers import jira, review_host, tracker

refresh_tasks = threading.Event()


ALIASES_FILE = DATA / "key-aliases.json"


def resolve_key_aliases():
    with lock:
        issues = (state.get("jira") or {}).get("issues") or []
        mrs = (state.get("review") or {}).get("mrs") or []
    if not issues or not jira.jira_configured():
        return
    try:
        aliases = json.loads(ALIASES_FILE.read_text())
    except (OSError, ValueError):
        aliases = {}
    known = {i["key"] for i in issues}
    missing = {k for m in mrs for k in m["keys"]} - known - set(aliases)
    if missing:
        headers = jira.jira_headers()
        for key in sorted(missing):
            try:
                aliases[key] = http_json(f"{jira_site()}/rest/api/3/issue/{key}?fields=summary", headers)["key"]
            except error.HTTPError as exc:
                if exc.code in (403, 404):
                    aliases[key] = key
            except (error.URLError, ValueError, KeyError, OSError):
                continue
        ALIASES_FILE.write_text(json.dumps(aliases))
    put("key_aliases", {old: new for old, new in aliases.items() if old != new})


def collect_tasks_loop():
    while True:
        steps = (jira.collect, resolve_key_aliases) if tracker() == "jira" else ()
        if tracker() != "jira":
            put("jira", {"configured": False, "disabled": True})
        for fn in (review_host().collect, *steps):
            try:
                fn()
                with lock:
                    state.pop(f"error_{fn.__module__}.{fn.__name__}", None)
            except Exception as exc:  # noqa: BLE001
                with lock:
                    state[f"error_{fn.__module__}.{fn.__name__}"] = repr(exc)
        refresh_tasks.wait(int(cfg.get("refresh.tasks_seconds", 300)))
        refresh_tasks.clear()
