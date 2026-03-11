Trigger Logic (same for both levels)
COMPACT_THRESHOLD = 0.70 * MAX_CONTEXT_TOKENS

if current_tokens >= COMPACT_THRESHOLD:
    compacted_state = run_compaction(full_history)
    new_history = [system_prompt, compacted_state, last_2_raw_messages]
Keep the last 2 raw messages so the agent doesn't cold-start — it needs to feel the immediate continuity of what just happened.

Level 1 — Orchestrator Compaction Prompt
You are a context compaction engine for an orchestrator AI agent called Crunchy Neck.
Extract the complete operational state from the conversation below.
Output ONLY the structured block. No preamble. No explanation.

---

## ORIGINAL TASK
<User's exact request, verbatim>

## CURRENT PLAN
<Active plan with step numbers. Mark completed steps [x], active step [→], pending [ ]>

## TODO / CHECKLIST
<Any checklists being tracked, same marking convention>

## PROGRESS SUMMARY
<3-5 sentences: what's been done, what approach was taken, key decisions made>

## DELEGATIONS LOG
<What was handed off to which subagent, with the exact instruction given and the result returned.
Format:
- [codex | browser | other] → "exact instruction" → result / status>

## CRITICAL VALUES
<Every key, ID, token, URL, file path, env var, config value that appeared.
When in doubt — include it. Format: key: value>

## SUBAGENT STATES
<If any subagent (especially browser) is mid-task, capture its current state here:
- what it was doing
- where it got to
- what it still needs to do>

## ERRORS & DEAD ENDS
<Failures, retries, abandoned approaches — and why>

## NEXT STEP
<Exact next action. Be specific. If delegating, say to whom and with what instruction.>

## OPEN QUESTIONS
<Unresolved uncertainties or things needing user input>

Level 2 — Browser Subagent Compaction Prompt
You are a context compaction engine for a browser automation subagent.
Extract complete session state so browsing can resume without prior messages.
Output ONLY the structured block. No preamble. No explanation.

---

## BROWSING OBJECTIVE
<What the subagent was asked to find or do, verbatim>

## CURRENT PAGE
<Exact URL of the current or last page>

## SESSION STATE
<Login status, cookies/session details if known, any auth tokens encountered>

## CRITICAL VALUES
<All URLs, IDs, form values, API keys, extracted data, prices, names — anything found.
Format: key: value. If it appeared on a page — include it.>

## NAVIGATION HISTORY (compressed)
<Bullet list of pages visited and what was found/done on each.
Keep it tight — just enough to understand the path taken.>

## DATA COLLECTED SO FAR
<Structured dump of all meaningful extracted data — tables as tables, JSON as JSON>

## ERRORS & DEAD ENDS
<Pages that failed, CAPTCHAs hit, redirects that went nowhere, approaches abandoned>

## NEXT ACTION
<Exact next step: what URL to go to or what action to take on the current page>

The Rolling Window Swap
After compaction runs, the new context looks like this:
[System Prompt]
[Compacted State Block]        ← replaces ALL old messages
[Second-to-last message]       ← raw, for continuity
[Last message]                 ← raw, for continuity
That's it. No memory store, no injection framing needed — the compacted block is the history floor. The agent reads it as if it always knew this.