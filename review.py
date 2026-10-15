import argparse
import json
import subprocess
import sys
from pathlib import Path
from urllib import error

import config as cfg
from core import project_root
from providers import review_host


def git_author():
    def get(key):
        return subprocess.run(["git", "config", key], capture_output=True, text=True, cwd=project_root() or None).stdout.strip()

    return f"{get('user.name')} <{get('user.email')}>"


def main(argv):
    ap = argparse.ArgumentParser(prog="opsboard review", description="Work with your own merge / pull requests on the configured code host.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("whoami", help="host user, git author, reply language, project folder")
    p = sub.add_parser("mine", help="your open merge requests")
    p.add_argument("--conflicts", action="store_true", help="only those with merge conflicts")
    p = sub.add_parser("info", help="branches, sha, conflicts, state")
    p.add_argument("number", type=int)
    p = sub.add_parser("threads", help="open review threads (JSON)")
    p.add_argument("number", type=int)
    p.add_argument("--all", action="store_true", help="include resolved threads")
    p = sub.add_parser("reply", help="reply to a thread with the text of a file")
    p.add_argument("number", type=int)
    p.add_argument("thread")
    p.add_argument("file")
    p.add_argument("--resolve", action="store_true")
    p = sub.add_parser("resolve", help="resolve a thread")
    p.add_argument("number", type=int)
    p.add_argument("thread")
    p = sub.add_parser("describe", help="replace the description with the text of a file (old text saved to <file>.bak)")
    p.add_argument("number", type=int)
    p.add_argument("file")
    p = sub.add_parser("upload", help="upload a file, print a markdown link")
    p.add_argument("file")
    args = ap.parse_args(argv)
    host = review_host()
    if args.cmd == "whoami":
        out = dict(host.whoami(), git_author=git_author(), reply_language=cfg.get("claude.reply_language") or "thread", project_root=str(project_root() or ""))
    elif args.cmd == "mine":
        out = host.mine(args.conflicts)
    elif args.cmd == "info":
        out = host.info(args.number)
    elif args.cmd == "threads":
        out = host.threads(args.number, args.all)
    elif args.cmd == "reply":
        out = host.reply(args.number, args.thread, Path(args.file).read_text(), args.resolve)
    elif args.cmd == "resolve":
        out = host.resolve_thread(args.number, args.thread)
    elif args.cmd == "describe":
        old = host.describe(args.number, Path(args.file).read_text())
        Path(args.file + ".bak").write_text(old)
        out = {"described": args.number, "backup": args.file + ".bak"}
    else:
        out = host.upload(args.file)
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    argv = sys.argv[1:]
    if argv[:1] == ["review"]:
        argv = argv[1:]
    try:
        sys.exit(main(argv))
    except (ValueError, PermissionError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
    except error.HTTPError as exc:
        print(f"error: HTTP {exc.code} from the code host", file=sys.stderr)
        sys.exit(3)
    except (error.URLError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(3)
