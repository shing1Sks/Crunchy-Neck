Skills Load-in / Load-out Architecture
The Core Enforcement Mechanism
The answer to "why doesn't the model just do it itself" is a mandatory instruction in the system prompt + teasers but not full content:


## Skills (mandatory)
Before replying: scan <available_skills> <description> entries.
- If exactly one skill clearly applies: read its SKILL.md at <location> with `read`, then follow it.
- If multiple could apply: choose the most specific one, then read/follow it.
- If none clearly apply: do not read any SKILL.md.
Constraints: never read more than one skill up front; only read after selecting.
The word "mandatory" in the heading and "Before replying" are doing the enforcement work. The model is instructed to check before acting, not after.

Phase 1: Discovery at Session Start (not per-message)
loadSkillEntries() in workspace.ts scans these directories in priority order (later wins on name collision):


extra dirs (config)         lowest priority
bundled (openclaw built-in)
~/.config/openclaw/skills   (managed/installed)
~/.agents/skills            (personal agent skills)
<workspace>/.agents/skills  (project agent skills)
<workspace>/skills          highest priority
Each skill directory must have a SKILL.md file. The discovery is limited by:

maxCandidatesPerRoot = 300 — directory scan cap
maxSkillsLoadedPerSource = 200 — per source cap
maxSkillFileBytes = 256KB — oversized SKILL.md files are skipped
Phase 2: Eligibility Filtering (binary gate)
shouldIncludeSkill() in config.ts checks each skill's YAML frontmatter:


metadata:
  openclaw:
    requires: { anyBins: ["claude", "codex", "opencode", "pi"] }
    os: ["darwin"]
    primaryEnv: "GITHUB_TOKEN"
Rules:

enabled: false in config → excluded
allowBundled allowlist → bundled skills not in list → excluded
requires.anyBins → if none of the listed binaries exist on the host, excluded
requires.env / primaryEnv → if env var missing and no config apiKey, excluded
os → if OS doesn't match, excluded
always: true → bypasses most eligibility checks
This means e.g. the coding-agent skill only appears if claude, codex, opencode, or pi binary exists.

Phase 3: Prompt Injection — Teasers Only
Only name + description go into the system prompt, NOT the full SKILL.md content. Limits applied:

maxSkillsInPrompt = 150
maxSkillsPromptChars = 30,000
Binary search trims to fit char budget
The injected block (from formatSkillsForPrompt) looks like:


<available_skills>
<skill name="coding-agent" location="~/.config/openclaw/skills/coding-agent/SKILL.md">
  <description>Delegate coding tasks to Codex, Claude Code, or Pi agents via background process. Use when: (1) building/creating new features...</description>
</skill>
<skill name="github" location="~/.../github/SKILL.md">
  <description>...</description>
</skill>
...
</available_skills>
Home dir paths are compressed to ~/ to save ~400–600 tokens (compactSkillPaths()).

Skills with disable-model-invocation: true in frontmatter are excluded from this block (they're user-invocable only via slash commands, not model-triggered).

Phase 4: Lazy Load — Model Reads On Demand
The model sees the description and decides if the skill applies. If yes, it calls the read tool on <location>:


read tool: ~/.config/openclaw/skills/coding-agent/SKILL.md
The full SKILL.md is then returned as a tool result in the conversation. The model follows the instructions inside it.

Key constraints baked into the system prompt:

Never read more than one skill up front
Only read after selecting
Rate limit awareness for skills that write to external APIs
Snapshot vs Live Load
skills-runtime.ts shows the optimization:


const shouldLoadSkillEntries = !params.skillsSnapshot || !params.skillsSnapshot.resolvedSkills;
If a SkillSnapshot was pre-built (e.g., during session startup or via a CLI pre-scan), it's reused directly — no filesystem scanning. The snapshot caches:

prompt (the pre-built <available_skills> block)
skills[] (names + env requirements)
resolvedSkills[] (the actual Skill objects)
If no snapshot exists, it scans live from disk.

Summary Flow

Session starts
      │
      ▼
loadSkillEntries()       ← scan 6 source dirs
      │
      ▼
shouldIncludeSkill()     ← binary/env/os gate (per skill)
      │
      ▼
formatSkillsForPrompt()  ← inject teasers into system prompt
      │
      ▼
Model receives message
      │
      ▼
"Before replying: scan <available_skills>"  ← mandatory rule
      │
   ┌──┴──────────────────────┐
   │ Skill matches?          │ No match → proceed without skill
   ▼                         ▼
read tool → full SKILL.md   Do it directly
      │
      ▼
Follow instructions in SKILL.md
The enforcement is purely prompt-level — it works because the model is told "mandatory" and "before replying". There is no server-side gating that prevents the model from ignoring it, but the instruction is strong enough that a well-aligned model complies.