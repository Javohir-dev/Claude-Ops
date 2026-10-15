import json
import os
from pathlib import Path

import config as cfg

HERE = Path(__file__).parent
BUILTIN = HERE / "profiles"
LOCAL = Path(os.environ.get("OPS_DATA_DIR", HERE)) / "profile.local.json"

_cache = {"key": None, "value": None}


def names():
    return sorted(p.stem for p in BUILTIN.glob("*.json"))


def _read(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def _merge(base, extra):
    out = dict(base)
    for k, v in extra.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def project_file():
    root = cfg.get("project.root")
    for rel in (".claude/opsboard.profile.json", "opsboard.profile.json"):
        path = Path(root).expanduser() / rel if root else None
        if path and path.is_file():
            return path
    return None


def _mtime(path):
    return path.stat().st_mtime if path and path.exists() else 0


def active():
    name = cfg.get("project.profile") or "generic"
    path = BUILTIN / f"{name}.json"
    if not path.exists():
        name, path = "generic", BUILTIN / "generic.json"
    team = project_file()
    stamp = (name, path.stat().st_mtime, str(team), _mtime(team), _mtime(LOCAL))
    if _cache["key"] != stamp:
        value = _merge(_read(BUILTIN / "generic.json"), _read(path)) if name != "generic" else _read(path)
        value = _merge(value, _read(team)) if team else value
        value = _merge(value, _read(LOCAL))
        value["id"] = name
        _cache.update(key=stamp, value=value)
    return _cache["value"]


def get(key, default=None):
    value = active()
    for part in key.split("."):
        if not isinstance(value, dict) or part not in value:
            return default
        value = value[part]
    return value


def worktree_slug(name):
    import re

    return re.sub(r"[^a-z0-9_]", "_", name.lower())[:40]
