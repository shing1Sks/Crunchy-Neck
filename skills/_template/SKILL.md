---
name: skill-name
description: One-line teaser describing exactly when to trigger this skill (~10 words)
metadata:
  requires:
    anyBins: []   # skill excluded if none of these binaries exist on PATH; e.g. ["gh", "git"]
    env: []       # skill excluded if any listed env var is absent; e.g. ["GITHUB_TOKEN"]
  os: []          # limit to specific OSes: ["win32", "darwin", "linux"] — empty means all
  always: false   # if true, bypasses all eligibility checks (useful for always-on skills)
  disable-model-invocation: false  # if true, model never sees it (user-only slash command skill)
---

# Skill Name

## When to use

Describe the exact task types or conditions that should trigger this skill.
Be specific — the model chooses based on description match, not fuzzy scoring.

Good examples:
- "Use when the user asks to create, update, or merge a GitHub PR"
- "Use when managing tmux sessions: new window, split pane, attach/detach"

## Steps

Numbered instructions the model should follow when this skill is active.

1. First action
2. Second action — include exact tool calls, commands, or flags where applicable
3. ...

## Examples

Show concrete input → output pairs with the exact tool calls expected.

**Example 1: [short label]**

User: "..."

Model does:
```
exec("some-command --flag value")
```

Reply: "..."

## Notes

- Rate limits, API quotas, or other constraints
- Error handling guidance
- Edge cases to watch for
- Any caveats about when NOT to use this skill
