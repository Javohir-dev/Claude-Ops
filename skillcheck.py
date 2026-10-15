import re
import sys
from pathlib import Path

import config as cfg
from core import project_root

REQUIRED = 5
CHECKS = (
    ("front matter with name and description", lambda t: bool(re.search(r"^---\s*\n(?=[\s\S]*?^name:\s*\S)(?=[\s\S]*?^description:)[\s\S]*?^---", t, re.M))),
    ("understands `push`", lambda t: bool(re.search(r"`push`", t))),
    ("understands `skip-tests`", lambda t: "skip-tests" in t),
    ("understands `conflict-only`", lambda t: "conflict-only" in t),
    ("ends with an OPS_RESULT line", lambda t: "OPS_RESULT" in t),
    ("talks to the host through `opsboard review`", lambda t: "opsboard review" in t),
    ("says never to force-push", lambda t: bool(re.search(r"(never|no|not)[^\n]{0,40}force", t, re.I))),
    ("works in a worktree", lambda t: "worktree" in t.lower()),
    ("replies only after pushing", lambda t: bool(re.search(r"(after|before)[^\n]{0,30}push", t, re.I))),
)


def find(name):
    for base in filter(None, [project_root(), Path.home()]):
        path = base / ".claude" / "skills" / name / "SKILL.md"
        if path.exists():
            return path
    return None


def main(argv):
    if argv[:1] == ["check"]:
        argv = argv[1:]
    name = argv[0] if argv else cfg.get("claude.fix_skill")
    if not name:
        print("usage: opsboard skill check <name>   (or choose a fix skill in Settings)", file=sys.stderr)
        return 2
    path = find(name)
    if not path:
        print(f"✗ {name}: no SKILL.md in <project>/.claude/skills/{name} or ~/.claude/skills/{name}")
        return 1
    text = path.read_text(errors="replace")
    failed = advised = 0
    print(f"{name}  ({path})")
    for i, (label, test) in enumerate(CHECKS):
        ok = test(text)
        required = i < REQUIRED
        failed += required and not ok
        advised += not required and not ok
        print(f"  {'✓' if ok else '✗' if required else '!'} {label}{'' if ok or required else '  (recommended)'}")
    if failed:
        print(f"{failed} required point(s) missing — see docs/fix-skill.md")
    else:
        print("follows the fix-skill contract" + (f"; {advised} recommendation(s) not found (the check reads English text only)" if advised else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    argv = sys.argv[1:]
    if argv[:1] == ["skill"]:
        argv = argv[1:]
    sys.exit(main(argv))
