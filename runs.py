import json
import os
import re
import signal
import subprocess
import time
import uuid
from pathlib import Path

import config as cfg
from core import RUNS_DIR, RUNS_FILE, alive, claude_bin, lock, popen, project_root, runs_lock, state

RE_RESULT = re.compile(r"^OPS_RESULT\s+(\{.*\})\s*$", re.M)


def fix_skill():
    name = cfg.get("claude.fix_skill") or ""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", name):
        raise ValueError("no fix skill chosen — Settings → Claude → Fix skill")
    return name


def fix_prompt(iid, opts):
    words = [f"/{fix_skill()} {int(iid)}"]
    if opts.get("push"):
        words.append("push")
    if opts.get("skiptests"):
        words.append("skip-tests")
    if not opts.get("threads"):
        words.append("conflict-only")
    return " ".join(words)


def launch_fix(body):
    iid = int(body.get("iid"))
    opts = {k: bool(body.get(k)) for k in ("threads", "conflict", "skiptests", "push")}
    if not (opts["threads"] or opts["conflict"]):
        raise ValueError("turn on review threads or merge conflict")
    with lock:
        mrs = {m["iid"]: m for m in (state.get("review") or {}).get("mrs", [])}
    if iid not in mrs or mrs[iid]["state"] != "opened":
        raise ValueError(f"!{iid} is not one of your open merge requests")
    if not cfg.get("claude.background_runs"):
        raise ValueError("background runs are turned off in Settings")
    root = project_root()
    if not root or not root.is_dir():
        raise ValueError("project folder is not set in Settings")
    prompt = fix_prompt(iid, opts)
    name = f"{fix_skill()} !{iid} " + " ".join(prompt.split(" ")[2:])
    mr = mrs[iid]
    env = dict(
        os.environ,
        OPS_REVIEW_HOST=cfg.get("review.host") or "gitlab",
        OPS_PROJECT=(cfg.get("github.repo") if cfg.get("review.host") == "github" else cfg.get("gitlab.project")) or "",
        OPS_NUMBER=str(iid),
        OPS_URL=mr.get("url", ""),
        OPS_SOURCE=mr.get("source", ""),
        OPS_TARGET=mr.get("target", ""),
        OPS_REPLY_LANGUAGE=cfg.get("claude.reply_language") or "thread",
        OPS_PROJECT_ROOT=str(root),
        OPS_PUSH="1" if opts["push"] else "0",
    )
    with runs_lock:
        if any(r["iid"] == iid and r["status"] == "running" for r in load_runs()):
            raise ValueError(f"a fix is already running for !{iid}")
        RUNS_DIR.mkdir(exist_ok=True)
        rid = uuid.uuid4().hex[:12]
        log = RUNS_DIR / f"{rid}.jsonl"
        mode = cfg.get("claude.permission_mode", "auto")
        cmd = [claude_bin(), "-p", prompt, "--permission-mode", mode, "-n", name, "--output-format", "stream-json", "--verbose"]
        with open(log, "wb") as out, open(RUNS_DIR / f"{rid}.err", "wb") as err:
            proc = subprocess.Popen(cmd, cwd=str(root), env=env, stdin=subprocess.DEVNULL, stdout=out, stderr=err, start_new_session=True)
        popen[proc.pid] = proc
        runs = load_runs()
        runs.insert(0, {"id": rid, "iid": iid, "name": name, "prompt": prompt, "pid": proc.pid, "started": time.time(), "status": "running", "log": str(log)})
        save_runs(runs[:50])
    return prompt


def parse_outcome(text):
    found = RE_RESULT.findall(text or "")
    if not found:
        return None
    try:
        out = json.loads(found[-1])
    except ValueError:
        return None
    return out if isinstance(out, dict) else None


def load_runs():
    try:
        return json.loads(RUNS_FILE.read_text())
    except (OSError, ValueError):
        return []


def save_runs(runs):
    RUNS_FILE.write_text(json.dumps(runs))


def _same_process(r):
    """True while the run's own claude process is alive (guards against a reused pid)."""
    proc = popen.get(r["pid"])
    if proc:
        return proc.poll() is None
    if not alive(r["pid"]):
        return False
    try:
        cmd = subprocess.run(["ps", "-o", "command=", "-p", str(r["pid"])], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return True
    return r.get("prompt", "") in cmd


def refresh_runs():
    with runs_lock:
        runs = load_runs()
        changed = False
        for r in runs:
            recent = time.time() - r.get("started", 0) < 86400
            if r["status"] in ("done", "error") and recent and not r.get("exited") and _same_process(r):
                r.update(status="running", ended=0)
                changed = True
            if r["status"] != "running":
                continue
            try:
                lines = Path(r["log"]).read_text(errors="replace").splitlines()
            except OSError:
                lines = []
            last = None
            for line in lines:
                try:
                    ev = json.loads(line)
                except ValueError:
                    continue
                if ev.get("session_id") and not r.get("session_id"):
                    r["session_id"], changed = ev["session_id"], True
                if ev.get("type") == "result":
                    last = ev
            if last is not None:
                text = str(last.get("result") or "")
                update = {"result": text[:4000], "cost": last.get("total_cost_usd"), "outcome": parse_outcome(text), "is_error": bool(last.get("is_error"))}
                if any(r.get(k) != v for k, v in update.items()):
                    r.update(update)
                    changed = True
            if not _same_process(r):
                if last is not None:
                    status = "error" if last.get("is_error") else "done"
                else:
                    err = Path(r["log"]).with_suffix(".err")
                    tail = err.read_text(errors="replace")[-600:].strip() if err.exists() else ""
                    r["result"] = tail or "process exited without a result"
                    status = "error"
                r.update(status="stopped" if r.get("stop_requested") else status, ended=time.time(), exited=True)
                popen.pop(r["pid"], None)
                changed = True
        if changed:
            save_runs(runs)
    return runs


def stop_run(rid):
    with runs_lock:
        runs = load_runs()
        r = next((x for x in runs if x["id"] == rid), None)
        if not r or r["status"] != "running":
            raise ValueError("run is not running")
        r["stop_requested"] = True
        save_runs(runs)
    try:
        os.killpg(r["pid"], signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        pass
