---
name: coding-agent
description: Delegate coding tasks to Codex. Use for building features, refactoring, PR review, and batch fixes.
metadata:
  requires:
    anyBins: ["codex"]
  always: false
---

# Coding Agent (Codex)

Use **Codex** for all coding delegation. Run via the `exec` tool.

## When to Use

- Building or creating new features / apps
- Refactoring large codebases
- Reviewing PRs (spawn in temp dir or worktree)
- Parallel batch issue fixing
- Any iterative coding that needs file exploration

**Do NOT use for:** simple one-liner fixes (just edit directly), reading/explaining code (use `read`).

---

## Exec Tool Parameters

| Parameter    | Description                                              |
| ------------ | -------------------------------------------------------- |
| `command`    | Shell command string                                     |
| `intent`     | Required — what this command does (be specific)          |
| `cwd`        | Working directory — always set this to the target project |
| `background` | `true` to run async, returns session_id for monitoring   |
| `timeout`    | Seconds before kill (default: no limit)                  |
| `shell`      | `true` to run via shell (required for chained commands)  |

## Process Tool Actions (for background sessions)

| Action      | Description                                    |
| ----------- | ---------------------------------------------- |
| `list`      | List all running/recent sessions               |
| `poll`      | Check if session is still running              |
| `get-log`   | Get session output (with optional offset/limit)|
| `send-keys` | Send key tokens or raw data to stdin           |
| `submit`    | Send data + newline (like pressing Enter)      |
| `kill`      | Terminate the session                          |

---

## Codex Flags

| Flag            | Effect                                              |
| --------------- | --------------------------------------------------- |
| `exec "prompt"` | One-shot execution, exits when done                 |
| `--full-auto`   | Sandboxed but auto-approves changes in workspace    |
| `--yolo`        | No sandbox, no approvals (fastest, most dangerous)  |

**Model:** `gpt-5.2-codex` is the default (configured in `~/.codex/config.toml`).

---

## Quick Start: One-Shot Tasks

```
# One-shot in an existing project
exec(
  command='codex exec --full-auto "Add error handling to the API calls"',
  cwd="C:/Projects/myproject",
  intent="Run Codex to add error handling",
)

# Scratch work — Codex requires a git repo!
exec(
  command='mkdir -p /tmp/scratch && cd /tmp/scratch && git init && codex exec "Your prompt here"',
  intent="Create temp git repo and run Codex one-shot",
  shell=True,
)
```

---

## Background Tasks (Longer Work)

```
# Start in background
result = exec(
  command='codex --yolo "Refactor the auth module"',
  cwd="C:/Projects/myproject",
  intent="Run Codex to refactor auth module",
  background=True,
)
session_id = result["session_id"]

# Monitor progress
process(action="get-log", session_id=session_id)

# Check if done
process(action="poll", session_id=session_id)

# Send input if Codex asks a question
process(action="submit", session_id=session_id, keys="yes")

# Kill if needed
process(action="kill", session_id=session_id)
```

When the background task finishes, send a completion update to the user:
```
ping_user(type="update", msg="Codex finished: <brief summary of what changed>", title="coding-agent")
```

---

## Reviewing PRs

**Always clone to a temp dir or use a git worktree — never review in the live project folder.**

```
# Clone to temp for safe review
exec(
  command='REVIEW_DIR=$(mktemp -d) && git clone https://github.com/user/repo.git $REVIEW_DIR && cd $REVIEW_DIR && gh pr checkout 130 && codex exec "Review this PR, summarize changes and flag issues"',
  intent="Clone repo and run Codex PR review in temp dir",
  shell=True,
)

# Or use git worktree (keeps main intact)
exec(
  command='git worktree add /tmp/pr-130 pr-130-branch && codex exec "Review this PR, summarize changes" ',
  cwd="C:/Projects/myproject",
  intent="Create worktree and run Codex PR review",
  shell=True,
)
```

---

## Parallel Issue Fixing (git worktrees)

```
# 1. Create worktrees
exec(command='git worktree add -b fix/issue-78 /tmp/issue-78 main', cwd="...", intent="Create worktree for issue 78", shell=True)
exec(command='git worktree add -b fix/issue-99 /tmp/issue-99 main', cwd="...", intent="Create worktree for issue 99", shell=True)

# 2. Launch Codex in each (background)
exec(command='codex --yolo "Fix issue #78: <description>. Commit after."', cwd="/tmp/issue-78", intent="Run Codex on issue 78", background=True)
exec(command='codex --yolo "Fix issue #99: <description>. Commit after."', cwd="/tmp/issue-99", intent="Run Codex on issue 99", background=True)

# 3. Monitor
process(action="list")

# 4. Create PRs after fixes
exec(command='git push -u origin fix/issue-78 && gh pr create --head fix/issue-78 --title "fix: ..."', cwd="/tmp/issue-78", intent="Push and create PR for issue 78", shell=True)

# 5. Cleanup
exec(command='git worktree remove /tmp/issue-78 && git worktree remove /tmp/issue-99', cwd="...", intent="Remove worktrees", shell=True)
```

---

## Rules

1. **Always set `cwd`** to the target project directory — Codex should wake up focused.
2. **Codex requires a git repo.** Use `git init` in a temp dir for scratch work.
3. **Use `codex exec` for one-shots** — it runs and exits cleanly.
4. **Use `background=True` for long work** — poll with `process(get-log)` to check progress.
5. **Use `--full-auto` for building**, no flags for reviewing.
6. **Never run Codex in the agent's own workspace directory** — it'll read unrelated files.
7. **Notify the user** with `ping_user(type="update")` when a background task finishes or needs input.
8. **Be patient** — don't kill sessions just because they're slow. Check logs first.
9. **If an agent fails, respawn or ask the user** — don't silently take over and hand-code the fix.

---

## Progress Updates

When you spawn Codex in the background, keep Shreyash in the loop:

- Send 1 short `ping_user(type="update")` when you start (what's running + where).
- Update again only when something changes: milestone reached, agent asks a question, error, or task done.
- Include what changed and where when the task finishes.
