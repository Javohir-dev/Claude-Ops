import collections
import configparser
import json
import re
import shutil
import socket
import subprocess
from pathlib import Path
from urllib import error, parse, request

import config as cfg

RE_ATLASSIAN = re.compile(r"https://([a-z0-9-]+)\.atlassian\.net")
RE_KEY_PREFIX = re.compile(r"\b([A-Z][A-Z0-9]{1,9})-\d+\b")
PG_IMAGES = ("postgres", "postgis", "timescale", "pgvector")


def sh(cmd, cwd=None, timeout=15):
    try:
        res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return res.stdout.strip() if res.returncode == 0 else ""


def found(value, origin, confidence=1.0):
    return {"value": value, "from": origin, "confidence": round(confidence, 2)}


def parse_remote(url):
    url = url.strip()
    if "://" in url:
        u = parse.urlsplit(url)
        host, path = u.hostname, u.path
    else:
        m = re.match(r"^(?:[^@]+@)?([^:/]+):(.+)$", url)
        if not m:
            return None
        host, path = m.group(1), m.group(2)
    path = re.sub(r"\.git/?$", "", path.strip("/"))
    return (f"https://{host}", path) if host and path else None


def repos(root):
    out = []
    origin = sh(["git", "-C", str(root), "remote", "get-url", "origin"])
    if origin:
        out.append({"path": root, "remote": origin, "label": "origin"})
    gm = root / ".gitmodules"
    if gm.exists():
        parser = configparser.ConfigParser()
        try:
            parser.read_string(gm.read_text())
        except configparser.Error:
            return out
        for section in parser.sections():
            path, url = parser.get(section, "path", fallback=""), parser.get(section, "url", fallback="")
            if path and url:
                out.append({"path": root / path, "remote": url, "label": f"submodule {path}"})
    return out


def gitlab_json(base, token, path, params=None):
    url = f"{base}/api/v4/{path}" + ("?" + parse.urlencode(params) if params else "")
    with request.urlopen(request.Request(url, headers={"PRIVATE-TOKEN": token}), timeout=15) as resp:
        return json.loads(resp.read().decode())


def detect_gitlab(root, token):
    candidates = []
    for repo in repos(root):
        parsed = parse_remote(repo["remote"])
        if parsed and parsed[0] != "https://github.com":
            candidates.append(dict(repo, base=parsed[0], project=parsed[1]))
    if not candidates:
        return {}, None
    for c in candidates:
        c["worktrees"] = len(worktree_paths(c["path"]))
    best = max(candidates, key=lambda c: c["worktrees"])
    reason = f"git remote ({best['label']})" + (f", {best['worktrees']} worktrees" if best["worktrees"] else "")
    confidence = 0.9 if len(candidates) == 1 else 0.7 if best["worktrees"] else 0.5
    descriptions = []
    if token:
        scored = []
        for c in candidates:
            try:
                user = gitlab_json(c["base"], token, "user")["username"]
                mrs = gitlab_json(c["base"], token, f"projects/{parse.quote(c['project'], safe='')}/merge_requests", {"author_username": user, "state": "all", "per_page": 100})
            except (error.URLError, ValueError, KeyError, OSError):
                continue
            scored.append((len(mrs), c, mrs))
        if scored:
            scored.sort(key=lambda s: -s[0])
            count, best, mrs = scored[0]
            descriptions = [f"{m.get('title', '')}\n{m.get('description') or ''}" for m in mrs]
            reason = f"git remote ({best['label']}) — {count} of your merge requests"
            confidence = 1.0 if count else 0.6
    out = {
        "gitlab.url": found(best["base"], reason, confidence),
        "gitlab.project": found(best["project"], reason, confidence),
    }
    return out, dict(best, descriptions=descriptions)


def detect_github(root):
    for repo in repos(root):
        parsed = parse_remote(repo["remote"])
        if parsed and parsed[0] == "https://github.com":
            return {"github.repo": found(parsed[1], f"git remote ({repo['label']})", 0.9)}
    return {}


def worktree_paths(repo_path):
    if not Path(repo_path).exists():
        return []
    listing = sh(["git", "-C", str(repo_path), "worktree", "list", "--porcelain"])
    paths = [Path(line[9:]) for line in listing.splitlines() if line.startswith("worktree ")]
    return [p for p in paths[1:] if p.exists()]


def detect_worktrees(repo_path):
    extra = worktree_paths(repo_path)
    if not extra:
        return {}
    parent, count = collections.Counter(p.parent for p in extra).most_common(1)[0]
    return {"project.worktrees": found(str(parent), f"git worktree list ({count} worktrees)", 1.0 if count > 1 else 0.7)}


def detect_db(root):
    rows = sh(["docker", "ps", "--format", "{{json .}}"])
    best = None
    for line in rows.splitlines():
        try:
            c = json.loads(line)
        except ValueError:
            continue
        if not any(i in c.get("Image", "") for i in PG_IMAGES):
            continue
        labels = dict(kv.split("=", 1) for kv in c.get("Labels", "").split(",") if "=" in kv)
        wd = labels.get("com.docker.compose.project.working_dir", "")
        score = 2 if wd and Path(wd).resolve() == root.resolve() else 1 if wd and str(root.resolve()).startswith(wd) else 0
        if not best or score > best[0]:
            best = (score, c["Names"], wd)
    out = {}
    if best:
        score, name, wd = best
        origin = f"docker compose project at {wd}" if score else "the only running Postgres container"
        out["db.container"] = found(name, origin, 1.0 if score == 2 else 0.6 if score else 0.4)
        env = sh(["docker", "inspect", name, "--format", "{{range .Config.Env}}{{println .}}{{end}}"])
        user = next((line.split("=", 1)[1] for line in env.splitlines() if line.startswith("POSTGRES_USER=")), "")
        if user:
            out["db.user"] = found(user, f"{name} environment (POSTGRES_USER)")
    if "db.user" not in out:
        for f in (".env", ".env.local", ".env.example"):
            p = root / f
            if not p.exists():
                continue
            m = re.search(r"^\s*(?:POSTGRES_USER|DB_USER|PGUSER)\s*=\s*['\"]?([^'\"\s#]+)", p.read_text(errors="replace"), re.M)
            if m:
                out["db.user"] = found(m.group(1), f"{f}", 0.8)
                break
    return out


def detect_jira_site(root, texts):
    hosts = collections.Counter()
    for t in texts:
        hosts.update(RE_ATLASSIAN.findall(t))
    origin = "links in your merge requests"
    if not hosts:
        for f in [root / "CLAUDE.md", root / "README.md"] + list((root / ".claude").glob("**/*.md"))[:200]:
            try:
                hosts.update(RE_ATLASSIAN.findall(f.read_text(errors="replace")))
            except OSError:
                continue
        origin = "links in the project's docs"
    if not hosts:
        return {}
    name, count = hosts.most_common(1)[0]
    return {"jira.site": found(f"https://{name}.atlassian.net", f"{origin} ({count}×)", 0.9 if count > 2 else 0.6)}


def detect_jira_projects(texts):
    keys = collections.Counter()
    for t in texts:
        keys.update(RE_KEY_PREFIX.findall(t.split("\n", 1)[0]))
    keys = [k for k, n in keys.most_common() if n >= 2 and k not in ("UTF", "ISO", "HTTP", "SHA")]
    return {"jira.projects": found(keys[:5], "task keys in your merge request titles", 0.8)} if keys else {}


def detect_claude(root):
    out = {}
    binary = shutil.which("claude") or next((str(p) for p in [Path.home() / ".local/bin/claude", Path("/opt/homebrew/bin/claude")] if p.exists()), "")
    if binary:
        out["claude.bin"] = found(binary, "PATH")
        version = sh([binary, "--version"], timeout=10)
        if version:
            out["claude.version"] = found(version.split()[0], "claude --version")
    dirs = [root / ".claude" / "skills", Path.home() / ".claude" / "skills"]
    skills = sorted({p.parent.name for d in dirs for p in d.glob("*/SKILL.md")})
    out["claude.skills"] = found(skills, f"{root}/.claude/skills, ~/.claude/skills")
    fixers = [s for s in skills if s in ("mr-fix", "pr-fix", "fix-review")]
    if fixers:
        out["claude.fix_skill"] = found(fixers[0], "installed review-fix skill", 0.8)
    return out


def port_free(port):
    with socket.socket() as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def detect_profile(root):
    compose = " ".join(p.read_text(errors="ignore") for p in root.glob("*compose*.y*ml") if p.is_file())
    if (root / "src" / "local").is_dir() and "odoo" in compose.lower():
        return {"project.profile": found("odoo-docker-env", "src/local + odoo in docker compose", 0.9)}
    return {"project.profile": found("generic", "no known project layout", 0.5)}


def detect_all():
    results, notes = {}, []
    root_value = cfg.get("project.root")
    root = Path(root_value).expanduser() if root_value else None
    if not root or not root.is_dir():
        return results, ["project.root is not set — nothing to detect from"]
    gl, repo = detect_gitlab(root, cfg.secret("gitlab.token"))
    results.update(gl)
    hub = detect_github(root)
    results.update(hub)
    if gl:
        results["review.host"] = found("gitlab", "a GitLab remote", 0.9)
    elif hub and not cfg.secret("gitlab.token"):
        results["review.host"] = found("github", "a GitHub remote", 0.9)
        repo = repo or {"path": root, "descriptions": []}
    if cfg.get("jira.site") or "jira.site" in results:
        results["tasks.tracker"] = found("jira", "a Jira site is known", 0.8)
    texts = repo["descriptions"] if repo else []
    if repo:
        results.update(detect_worktrees(repo["path"]))
    results.update(detect_db(root))
    results.update(detect_jira_site(root, texts))
    results.update(detect_jira_projects(texts))
    results.update(detect_claude(root))
    results.update(detect_profile(root))
    if not repo:
        notes.append("no git remote found in the project folder")
    if "db.container" not in results:
        notes.append("no running Postgres container found")
    return results, notes


def apply(results):
    changed = []
    for key, item in results.items():
        before = cfg.entry(key)
        if key == "jira.projects":
            item = dict(item, value=list(dict.fromkeys((cfg.get(key) or []) + item["value"])))
        cfg.set(key, item["value"], "auto", item["from"], item["confidence"])
        if before.get("source") in ("auto", "default") and before.get("value") != item["value"]:
            changed.append(key)
    return changed


def _check(cid, ok, detail, fix=""):
    return {"id": cid, "ok": ok, "detail": detail, "fix": fix}


def _github_check():
    from providers import github

    if not cfg.secret("github.token"):
        return _check("github", False, "no token", "github.token")
    if not cfg.get("github.repo"):
        return _check("github", False, "repository unknown — set the project folder or run detect", "github.repo")
    try:
        user = github.login()
        github.get(f"repos/{cfg.get('github.repo')}")
        return _check("github", True, f"{user} @ {github.web_url()}/{cfg.get('github.repo')}")
    except error.HTTPError as exc:
        return _check("github", False, f"HTTP {exc.code} from {github.api_base()}", "github.token" if exc.code == 401 else "github.repo")
    except (error.URLError, OSError, ValueError, KeyError) as exc:
        return _check("github", False, f"cannot reach {github.api_base()}: {exc}", "github.url")


def doctor():
    import base64

    out = []
    root_value = cfg.get("project.root")
    root = Path(root_value).expanduser() if root_value else None
    out.append(_check("project", bool(root and root.is_dir()), str(root) if root else "not set", "project.root"))
    if (cfg.get("review.host") or "gitlab") == "github":
        out.append(_github_check())
    else:
        token, base, project = cfg.secret("gitlab.token"), cfg.get("gitlab.url"), cfg.get("gitlab.project")
        if not token:
            out.append(_check("gitlab", False, "no token", "gitlab.token"))
        elif not (base and project):
            out.append(_check("gitlab", False, "server or project unknown — set the project folder or run detect", "gitlab.project"))
        else:
            try:
                user = gitlab_json(base, token, "user")["username"]
                gitlab_json(base, token, f"projects/{parse.quote(project, safe='')}")
                out.append(_check("gitlab", True, f"{user} @ {base}/{project}"))
            except error.HTTPError as exc:
                out.append(_check("gitlab", False, f"HTTP {exc.code} from {base}", "gitlab.token" if exc.code == 401 else "gitlab.project"))
            except (error.URLError, OSError, ValueError, KeyError) as exc:
                out.append(_check("gitlab", False, f"cannot reach {base}: {exc}", "gitlab.url"))
    email, jtoken, site = cfg.get("jira.email"), cfg.secret("jira.token"), cfg.get("jira.site")
    tracker = cfg.get("tasks.tracker") or ("jira" if jtoken else "none")
    if tracker != "jira":
        out.append(_check("jira", None, "not used (Settings → Tasks → Tracker)", "tasks.tracker"))
    elif not (email and jtoken):
        out.append(_check("jira", False, "not connected — email and API token are required", "jira.token"))
    elif not site:
        out.append(_check("jira", False, "Jira site unknown", "jira.site"))
    else:
        auth = base64.b64encode(f"{email}:{jtoken}".encode()).decode()
        try:
            req = request.Request(f"{site}/rest/api/3/myself", headers={"Authorization": f"Basic {auth}", "Accept": "application/json"})
            with request.urlopen(req, timeout=15) as resp:
                me = json.loads(resp.read().decode())
            out.append(_check("jira", True, f"{me.get('displayName')} @ {site}"))
        except error.HTTPError as exc:
            out.append(_check("jira", False, f"HTTP {exc.code} from {site}", "jira.token" if exc.code in (401, 403) else "jira.site"))
        except (error.URLError, OSError, ValueError) as exc:
            out.append(_check("jira", False, f"cannot reach {site}: {exc}", "jira.site"))
    docker_ok = bool(sh(["docker", "info", "--format", "{{.ServerVersion}}"]))
    out.append(_check("docker", docker_ok if docker_ok else None, "running" if docker_ok else "not running (optional)", ""))
    container, user = cfg.get("db.container"), cfg.get("db.user")
    if not docker_ok or not container:
        out.append(_check("postgres", None, "skipped" if not docker_ok else "no container set (optional)", "db.container"))
    else:
        ok = sh(["docker", "exec", container, "psql", "-U", user or "postgres", "-d", "postgres", "-Atc", "select 1"]) == "1"
        out.append(_check("postgres", ok, f"{container} as {user}" if ok else f"psql failed in {container} as {user}", "db.container" if not ok else ""))
    binary = cfg.get("claude.bin")
    version = sh([binary, "--version"], timeout=10) if binary else ""
    out.append(_check("claude", bool(version) if binary else None, version.split()[0] if version else "claude CLI not found (optional)", "claude.bin"))
    name = cfg.get("claude.fix_skill")
    skill = bool(name) and any((d / ".claude" / "skills" / name / "SKILL.md").exists() for d in filter(None, [root, Path.home()]))
    msg = f"{name} installed" if skill else (f"{name} not found in .claude/skills" if name else "none chosen — Run fix is hidden (optional)")
    out.append(_check("fix-skill", True if skill else (False if name else None), msg, "claude.fix_skill"))
    return out


STATUS_RULES = (
    ("cancelled", re.compile(r"cancel|reject|отмен|отклон|bekor|won.?t", re.I)),
    ("staging", re.compile(r"stag|стейдж|pre-?prod|release", re.I)),
    ("review", re.compile(r"review|провер|qa\b|test|тест|code", re.I)),
    ("discuss", re.compile(r"discuss|дискус|hold|block|ожида|wait|pause|пауз", re.I)),
)


def status_bucket(name, category):
    for bucket, rx in STATUS_RULES:
        if rx.search(name):
            return bucket
    return {"done": "done", "indeterminate": "doing"}.get(category, "todo")


def detect_status_map(issues):
    seen = {}
    for i in issues:
        if i.get("status"):
            seen.setdefault(i["status"], i.get("category", ""))
    return {name: status_bucket(name, cat) for name, cat in seen.items()}
