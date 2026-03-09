Message Lifecycle — From User Input to Agent Action
The 10,000-foot view

User types message
  → Platform adapter receives it (Telegram, Slack, CLI, WebChat...)
  → Normalized and buffered
  → Routed to the right agent session via a "lane"
  → Agent runner starts → calls LLM → streams back
  → LLM decides to call tools → tools execute
  → Text blocks accumulate → reply formatted for platform
  → Platform API sends reply back to user
  → Session transcript saved
Stage 1 — Message Arrives at the Platform Adapter
Each platform has its own adapter. The entry mechanics differ but all normalize into the same internal shape.


Telegram     → grammyjs bot webhook/polling
               src/telegram/

Slack        → HTTP webhook
               src/slack/http/

Discord      → WebSocket
               src/discord/

CLI          → stdin
               src/cli/

WebChat      → WebSocket to gateway
               src/gateway/server-http.ts
What the platform adapters do before dispatch
They don't immediately dispatch. They run several filters first:


Raw platform event
  │
  ├─ shouldSkipUpdate()     ← ignore bot's own messages, edits, etc.
  ├─ isSenderAllowed()      ← check against allowlist (user IDs, group IDs)
  ├─ deduplication check    ← createTelegramUpdateDedupe() prevents replay
  │
  ├─ Buffer phase:
  │    textFragmentBuffer   ← coalesce rapid consecutive texts into one message
  │    mediaGroupBuffer     ← group photos/videos sent together (same media_group_id)
  │    debounce (ms)        ← wait for user to stop typing before triggering
  │
  └─ Proceed to context building
Why buffering? Telegram sometimes splits a message + photo into two separate events milliseconds apart. Without buffering, the agent would get two separate triggers. Buffering waits and coalesces them.

Stage 2 — Context Assembly
The platform adapter builds a rich context object. This is the "normalized message" that everything downstream uses.


// This is the payload the agent's system prompt template receives
ctxPayload = {
  Text:        "can you refactor the login module",   // user message
  From:        "user_12345",                          // sender ID
  Channel:     "telegram",                            // which platform
  SessionKey:  "agent:main:telegram:direct:12345",    // routing key
  MessageId:   "msg_abc",                             // unique message ID
  Timestamp:   1709123456789,                         // unix ms
  History:     "... previous messages ...",           // loaded from session store
  MediaPath:   "/tmp/img_abc.jpg",                    // if photo attached
  IsGroup:     false,
  IsThread:    false,
  // ... more fields depending on platform
}
The SessionKey is the most important field. It determines:

Which session history to load
Which lane the task runs in (serialization)
Where to write the transcript afterwards
Session key anatomy

agent:main:telegram:direct:12345
   │     │      │       │     │
   │     │      │       │     └─ peer ID (user's Telegram ID)
   │     │      │       └─ peer kind (DM vs group)
   │     │      └─ channel (which platform)
   │     └─ agent ID
   └─ namespace
Multiple users get different session keys → different lanes → they never block each other.

Stage 3 — Route Resolution
Before the agent runs, the system figures out which agent to use. This is important because OpenClaw can have multiple configured agents.


resolveAgentRoute(channel, peerId, guildId, memberRoles)
  │
  Match against config bindings in priority order:
  │
  ├─ 1. Specific peer binding (DM to a specific user)
  ├─ 2. Parent peer binding (thread scoped to a user)
  ├─ 3. Guild + member roles (Discord RBAC)
  ├─ 4. Guild-wide (whole Discord server)
  ├─ 5. Team binding (Slack workspace)
  ├─ 6. Account binding
  ├─ 7. Channel binding
  └─ 8. Default agent (fallback)
  │
  └─ ResolvedAgentRoute {
       agentId:       "main",
       accountId:     "account1",
       sessionKey:    "agent:main:telegram:direct:12345",
       mainSessionKey: "agent:main:main",
     }
Stage 4 — Command Lane Queueing
This is the concurrency control mechanism. Every message is wrapped in a task and placed in a lane.


enqueueCommandInLane(
  "session:agent:main:telegram:direct:12345",   // ← lane = session key
  async () => {
    // everything below runs inside here
    return processMessage(context)
  }
)
What lanes guarantee

Lane "session:...userA":  msg1 → msg2 → msg3    ← sequential per user
Lane "session:...userB":  msg1 → msg2            ← parallel with userA
Lane "cron":              job1 → job2            ← its own lane

Each lane = FIFO queue, one task at a time within that lane
Multiple lanes = run fully in parallel
If userA sends 3 messages quickly, they queue up. The agent finishes replying to msg1 before starting msg2. This prevents out-of-order replies and context corruption.

Stage 5 — Agent Run Starts
Inside the lane task, the dispatch pipeline calls down to the agent runner.


dispatchTelegramMessage(context)
  └─ dispatchReplyFromConfig(context)
       └─ runEmbeddedPiAgent({
            runId:      "run_xyz",
            sessionKey: "agent:main:telegram:direct:12345",
            messages:   [systemPrompt, ...history, userMessage],
            tools:      [...allTools],
            model:      "claude-3-5-sonnet",
            provider:   "anthropic",
            onAgentEvent: (event) => streamToUI(event),
            signal:     abortController.signal,
          })
The messages array is literally what gets sent to the LLM:


[
  { role: "system",    content: "You are OpenClaw..." },  // built from SKILL.md + config
  { role: "user",      content: "previous message 1" },  // loaded from session store
  { role: "assistant", content: "previous reply 1"   },
  { role: "user",      content: "previous message 2" },
  { role: "assistant", content: "previous reply 2"   },
  { role: "user",      content: "can you refactor the login module" }  // ← current message
]
The outer retry loop
runEmbeddedPiAgent wraps everything in a retry loop before calling the LLM:


for attempt in range(maxRetries):  ← up to 160 iterations across all profiles
  pick auth profile (API key)
  if profile in cooldown: skip
  try:
    result = runEmbeddedAttempt(...)
    if success: markProfileGood(); return result
  except RateLimitError:
    markProfileCooldown(30s)
    try next profile
  except BillingError:
    cooldown 60s
    try next profile
  except ContextOverflow:
    compact history (summarize old turns)
    retry same profile
  except AuthError:
    mark profile bad permanently
    try next profile
Stage 6 — LLM Streaming
runEmbeddedAttempt calls the LLM and subscribes to the stream. This is where the model "thinks and talks".


streamSimple(messages, tools, model, apiKey)   ← the actual LLM API call
  │
  └─ subscribeEmbeddedPiSession(stream, handlers)
       │
       Processes events as they arrive:
       │
       ├─ message_start          → agent started
       ├─ content_block_start    → new text or tool block starting
       ├─ content_block_delta    → streaming text chunk
       │    └─ accumulate into deltaBuffer
       │    └─ fire onDelta(chunk) → live typing effect in UI
       ├─ content_block_stop     → block finished
       │    └─ if text block: emit onBlockReply(text)
       │    └─ if tool block:  → Stage 7
       └─ message_stop           → agent finished turn
Text splitting and chunking
Raw text from the LLM is not sent immediately. It goes through a splitter:


LLM streams: "I'll refactor the login module by..."
               (character by character)
  │
  └─ Accumulate until:
       ├─ paragraph boundary reached  (prefer natural breaks)
       ├─ min 1500 chars accumulated
       ├─ 1000ms idle (LLM stopped sending for a moment)
       └─ message_stop

  Each chunk → onBlockReply(payload)  → sent to user immediately
This creates a "typing" effect — the user sees the reply building up in real time rather than waiting for the entire response.

Stage 7 — Tool Call Interception
When the LLM decides to call a tool (bash, browser, file read/write, etc.):


LLM emits: tool_use block {
  id:    "tool_use_abc",
  name:  "bash",
  input: { command: "find src/ -name '*.ts' | head -20" }
}
  │
subscribeEmbeddedPiSession detects this
  │
  ├─ fire onToolCall({ name: "bash", input: {...} })   ← UI shows tool running
  │
  ├─ look up tool handler in registered tools
  │
  ├─ execute tool:
  │    bash → bash-tools.exec.ts → supervisor → child process → output
  │    browser → browser control server → Playwright → Chrome
  │    file read → pi-tools.read.ts → fs.readFile
  │    sessions_spawn → spawn sub-agent (recursive!)
  │
  ├─ collect tool result:
  │    { output: "src/auth/login.ts\nsrc/auth/session.ts\n..." }
  │
  ├─ fire onToolResult({ name: "bash", result: "..." })  ← UI shows result
  │
  └─ append to conversation:
       { role: "user", content: [{ type: "tool_result", id: "tool_use_abc", content: "..." }] }
The re-threading loop
After a tool call, the conversation continues. The LLM gets the tool result and keeps going:


Turn 1:  user says "refactor login module"
         → LLM responds: "Let me look at the files first" + calls bash(find ...)

Turn 2:  tool result injected: "src/auth/login.ts..."
         → LLM responds: "I can see the structure, let me read login.ts" + calls read(file)

Turn 3:  file content injected
         → LLM responds: "Here's my refactored version:" + calls write(file, new_content)

Turn 4:  write result injected: "file written"
         → LLM responds: "Done! I've refactored the login module. Here's what changed..."

↑ This loop continues until LLM stops calling tools
Each tool call + result is a new "turn" added to the message array and sent back to the LLM.

Stage 8 — Reply Composition
As text blocks accumulate from the LLM, they go through a reply pipeline before hitting the platform.


onBlockReply(text)
  │
  ├─ extract reply directives:
  │    [[think:on]]          → enable extended thinking next turn
  │    [[block-streaming:off]] → buffer entire reply, don't stream
  │    [[exec:dangerous]]    → pre-approve next bash command
  │
  ├─ build ReplyPayload:
  │    {
  │      text:      "cleaned text (directives stripped)",
  │      textRaw:   "raw text with directives",
  │      media:     [...],    // any images the agent generated
  │      reactions: [...],    // emoji reactions to add
  │      targets:   [...],    // from send_message tool calls
  │    }
  │
  └─ → Stage 9
Stage 9 — Platform Delivery
The reply payload is formatted for the specific platform and sent via its API.


ReplyPayload
  │
  ├─ Telegram:
  │    renderTelegramHtmlText(text)          ← **bold**, `code`, etc.
  │    chunk to 4096 chars max              ← Telegram's limit
  │    bot.api.sendMessage(chatId, html, { parse_mode: "HTML" })
  │    if reply streaming: edit previous message with new text
  │
  ├─ Slack:
  │    renderSlackMarkdown(text)
  │    build Block Kit JSON for rich formatting
  │    slack.chat.postMessage(channel, blocks)
  │
  ├─ Discord:
  │    chunk to 2000 chars max
  │    build embed if needed
  │    channel.send(content)
  │
  └─ CLI:
       ANSI color formatting
       write to stdout
After sending, the full conversation (user message + assistant reply + all tool calls) is written back to the session store so it's available as history for the next message.

The Complete Sequence Diagram

User                Platform          Lane            Agent Runner         LLM API         Tool
 │                     │               │                   │                  │              │
 │── sends message ───▶│               │                   │                  │              │
 │                     │               │                   │                  │              │
 │                  buffer/dedup       │                   │                  │              │
 │                  build context      │                   │                  │              │
 │                  resolve route      │                   │                  │              │
 │                     │               │                   │                  │              │
 │                     │──enqueue ────▶│                   │                  │              │
 │                     │               │──start task ─────▶│                  │              │
 │                     │               │                   │─── stream req ──▶│              │
 │                     │               │                   │                  │              │
 │                     │               │                ◀──│── text delta ───│              │
 │◀── partial reply ── │               │                   │                  │              │
 │                     │               │                   │                  │              │
 │                     │               │                ◀──│── tool_call ────│              │
 │                     │               │                   │──── execute ───────────────────▶│
 │                     │               │                ◀──│──── result ────────────────────│
 │                     │               │                   │─── tool result ─▶│              │
 │                     │               │                   │                  │              │
 │                     │               │                ◀──│── more text ────│              │
 │◀── more reply ──────│               │                   │                  │              │
 │                     │               │                ◀──│── message_stop ─│              │
 │                     │               │                   │                  │              │
 │                     │               │◀──── done ────────│                  │              │
 │                     │               │                                                     │
 │                   save transcript                                                          │
 │                   next msg in lane                                                         │
Key Insight: What Makes This Architecture Work
The whole system is built on three orthogonal ideas:

1. Lanes = per-session serialization
No shared global queue. Every session is its own FIFO. One user's slow AI call never blocks another user.

2. Streaming at every layer
LLM → subscribeEmbeddedPiSession → onBlockReply → platform API. The reply starts arriving at the user before the LLM finishes. This is why the "typing" effect works.

3. Tool calls are just more turns
There's no separate "tool execution mode". A tool call is just another message appended to the conversation array, and the LLM call is made again. The same streaming loop handles both text and tool interleaving uniformly.