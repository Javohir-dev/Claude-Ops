import os
import sys
from pathlib import Path


def stale_links(skills_dir, repo_skills):
    prefixes = {str(Path(repo_skills).absolute()) + os.sep, str(Path(repo_skills).resolve()) + os.sep}
    out = []
    for link in sorted(Path(skills_dir).glob("*")):
        if link.is_symlink() and os.readlink(link).startswith(tuple(prefixes)) and not link.exists():
            out.append(link)
    return out


def main():
    here = Path(__file__).resolve().parent
    for link in stale_links(Path.home() / ".claude" / "skills", here / "skills"):
        link.unlink()
        print(f"removed {link} — Opsboard no longer ships this skill; choose your own in Settings → Claude → Fix skill (docs/fix-skill.md)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
