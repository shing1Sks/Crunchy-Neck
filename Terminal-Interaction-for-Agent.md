The Real Insight from This Doc
The architecture is smart but over-built for most use cases. The core loop an agent actually needs is:
1. Run it — `exec` with `yieldMs=10000` as default
2. If still running — agent gets `sessionId` + current `tail`
3. Poll it — `process(poll)` until done or agent decides to kill
4. Talk to it — `submit`/`send-keys` if it's waiting for input
5. Kill it — when done or stuck
ok so this is the core summary rwquiremnets for the teminal tool architecutre right>