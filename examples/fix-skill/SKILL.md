---
name: fix-review
description: >
  Fix the open review threads and merge conflicts of one of my merge / pull requests.
  Use when asked "/fix-review <number> [push] [skip-tests] [conflict-only]" or from the
  Opsboard dashboard (⋯ → Run fix).
---

# fix-review

Arguments: `<number> [push] [skip-tests] [conflict-only]`, in any order. Run to the end without
asking questions, except where a step says to stop.

| Word | Meaning |
|---|---|
| — | fix threads + merge the target; commit, **do not push**; replies go into the report |
| `push` | also push, reply to each thread and resolve it, update the description if needed |
| `skip-tests` | no test suite; run the quick checks (step 5) |
| `conflict-only` | only merge the target and resolve conflicts (steps 1, 2, 5, 6, 7) |

## 1. Look up the request

```bash
opsboard review whoami          # git_author, reply_language, project_root
opsboard review info <number>   # source, target, conflicts
opsboard review threads <number>
```

If `info` fails (not yours, not open, not configured): stop and report.

## 2. Worktree and target branch

From the project root:

```bash
git fetch origin <source> <target>
git worktree list --porcelain | grep -B2 "branch refs/heads/<source>$"   # reuse it if it exists
git worktree add ../<repo>.worktrees/fix-<number> <source> 2>/dev/null \
  || git worktree add -b <source> ../<repo>.worktrees/fix-<number> origin/<source>
```

In the worktree: uncommitted changes → stop and report. Bring the branch up to date
(`git merge --ff-only origin/<source>`), then `git merge --no-edit origin/<target>` and resolve every
conflict keeping the intent of both sides.

<!-- PROJECT RULES: list files that need special handling in a conflict, e.g. lock files,
     generated code, translation files, version numbers, migrations. -->

## 3. Triage (skip with `conflict-only`)

For each thread decide one of:

| Kind | Action |
|---|---|
| code or behaviour bug | fix it (step 4) |
| question | answer from the code; improve the code if the question shows it is unclear |
| disagree | no change; answer with evidence (file:line, a test, a measurement) |
| bot noise | ignore |

## 4. Fix

- Reproduce first, then fix the root cause, not the symptom.
- Search the whole diff (`git diff origin/<target>...HEAD`) for the same mistake and fix it everywhere.
- Fixed logic gets a regression test that fails without the fix.
- Change only what the threads ask for.

<!-- PROJECT RULES: coding conventions the reviewers keep asking for. -->

## 5. Check

Without `skip-tests`: run the tests covering the changed code.

<!-- PROJECT RULES: the exact test command, e.g. `pytest tests/test_cart.py -q`. -->

Always, also with `skip-tests` — the quick checks, on files changed against the target:

```bash
git diff --name-only --diff-filter=AM origin/<target>...HEAD -- '*.py' | xargs -r python3 -m py_compile
```

<!-- PROJECT RULES: replace or extend with your linters: `ruff check`, `tsc --noEmit`, … -->

A failure: fix and re-run. Three failed attempts: commit nothing more, stop and report.

## 6. Commit

Author from `git_author`. Subject = the request title, body = which threads were fixed and how.

## 7. Push and reply (only with `push`)

1. `git push origin <source>` — never `--force`. Rejected: fetch, merge `origin/<source>`, re-check, push once more; rejected again → stop.
2. Only after the push: for each fixed thread write the reply to a file and run
   `opsboard review reply <number> <thread> <file> --resolve`.
3. If the description is out of date: `opsboard review describe <number> <file>`.
4. `opsboard review threads <number>` should list nothing you meant to resolve.

Replies: in `reply_language`, one to three sentences — what changed, the commit, how it was checked.

## 8. Report

A short table of threads and what was done, the checks that ran, and without `push` the push
command and the reply texts. Then exactly one line:

```
OPS_RESULT {"status":"pushed|committed|stopped","commit":"<short sha>","threads":{"resolved":N,"open":M},"checks":"<what ran>","note":"<why it stopped>"}
```

## Never

- `git push --force`, pushing to another branch, touching someone else's request.
- Replying "fixed" or resolving before the fix is pushed.
- Working in the main checkout.
