import base64
import collections
import time
from urllib import error

import config as cfg
import detect
from core import epoch, http_json, jira_site, lock, put, state


def jira_configured():
    return bool(cfg.get("jira.email") and cfg.secret("jira.token"))


def jira_headers(email=None, token=None):
    email, token = email or cfg.get("jira.email"), token or cfg.secret("jira.token")
    auth = base64.b64encode(f"{email}:{token}".encode()).decode()
    return {"Authorization": f"Basic {auth}", "Accept": "application/json"}


def jira_whoami(email, token, site=None):
    return http_json(f"{(site or jira_site()).rstrip('/')}/rest/api/3/myself", jira_headers(email, token))


def save_jira_account(email, token, site=None):
    me = jira_whoami(email, token, site)
    if site:
        cfg.set("jira.site", site.rstrip("/"), "user")
    cfg.set("jira.email", email, "user")
    cfg.set_secret("jira.token", token)
    cfg.set("jira.name", me.get("displayName", ""), "auto", "Jira /myself")
    return me


def jira_account():
    if not jira_configured():
        return {"connected": False}
    return {"connected": True, "email": cfg.get("jira.email", ""), "name": cfg.get("jira.name", "")}


def collect():
    if not jira_configured():
        put("jira", {"configured": False, "site": jira_site()})
        return
    issues, token = [], None
    fields = ["summary", "status", "priority", "issuetype", "created", "updated", "duedate", "resolutiondate"]
    try:
        headers = jira_headers()
        while True:
            body = {"jql": cfg.get("jira.jql"), "fields": fields, "maxResults": 100}
            if token:
                body["nextPageToken"] = token
            page = http_json(f"{jira_site()}/rest/api/3/search/jql", headers, body)
            for it in page.get("issues", []):
                f = it["fields"]
                issues.append(
                    {
                        "key": it["key"],
                        "summary": f.get("summary", ""),
                        "status": (f.get("status") or {}).get("name", ""),
                        "category": ((f.get("status") or {}).get("statusCategory") or {}).get("key", ""),
                        "priority": (f.get("priority") or {}).get("name", ""),
                        "type": (f.get("issuetype") or {}).get("name", ""),
                        "created": epoch(f.get("created", "")),
                        "updated": epoch(f.get("updated", "")),
                        "resolved": epoch(f.get("resolutiondate") or ""),
                        "due": f.get("duedate"),
                    }
                )
            token = page.get("nextPageToken")
            if page.get("isLast", True) or not token:
                break
    except (error.URLError, ValueError, KeyError, OSError) as exc:
        with lock:
            prev = state.get("jira") or {}
        put("jira", dict(prev, configured=True, error=str(exc)[:300]))
        return
    put("jira", {"configured": True, "issues": issues, "fetched": time.time(), "site": jira_site(), "account": jira_account()})
    prefixes = collections.Counter(i["key"].split("-")[0] for i in issues)
    known = cfg.get("jira.projects") or []
    projects = list(dict.fromkeys(known + [p for p, _ in prefixes.most_common()]))
    if projects != known:
        cfg.set("jira.projects", projects, "auto", "your Jira issues and merge request titles", 1.0)
    status_map = dict(cfg.load()["settings"].get("jira.status_map", {}).get("auto", {}).get("value") or {})
    status_map.update(detect.detect_status_map(issues))
    if status_map:
        cfg.set("jira.status_map", status_map, "auto", "your Jira statuses", 0.8)
