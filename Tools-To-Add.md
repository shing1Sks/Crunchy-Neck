Just rough plan needs modifying

Tier 1 — Non-negotiable core
>exec(command, intent) File ops, CLI calls, installs — everything flows through this
>read(path) Can't act on anything without reading it first
>write(path, content) Create and save output
>edit(path, old, new)Surgical edits without full overwrites
>ping_user(msg, type, medium = whatsapp/telegram) Ask/update — the human in the loop
>remember(query) Long-term memory retrieval
<!-- web_search(query) for searching for a query / link | leave it to default model capabilities -->

Tier 2 — Makes it actually useful
>process(action, session_id) Manage long-running background processes from exec
>send_user_media(path) Return files, images, output to user
snapshot() Desktop screenshot for visual context
spawn_subagent(prompt, agent) Delegate to browser agent or Codex — this is the delegation primitive
image_gen() to gemini
tts() via inworld
schedule_agent(time, task) fires and  agent for task designated to run at some other time

