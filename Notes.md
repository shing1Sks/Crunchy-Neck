Compaction :

"Merge these partial summaries into a single cohesive summary.

MUST PRESERVE:
- Active tasks and their current status (in-progress, blocked, pending)
- Batch operation progress (e.g., '5/17 items completed')
- The last thing the user requested and what was being done about it
- Decisions made and their rationale
- TODOs, open questions, and constraints
- Any commitments or follow-ups promised

PRIORITIZE recent context over older history. The agent needs to know
what it was doing, not just what was discussed."

Long Term Memory :

"## Memory Recall
Before answering anything about prior work, decisions, dates, people,
preferences, or todos: run memory_search on MEMORY.md + memory/*.md;
then use memory_get to pull only the needed lines.
If low confidence after search, say you checked.

Citations: include Source: <path#line> when it helps the user verify memory snippets."


$env:PYTHONPATH = "C:\Users\SHREYASH KUMAR SINGH\Desktop\Crunchy-Neck-Agent"


ok so for this crunchy-neck agent

the tools are ready (most of it)

and the compaction logic is ready

so we are at a decent place from building the main agent i think few things remain

so first is skills, how do i design the folder plus a small prompt defenition in /agent-design which will define how to use skills
: it is mandatory to scan the skill names and descriptions first of all and read the skills suitable (most suitable for the task) then use it

we dont want a complex skill sections like user deifined, downloaded etc etc

common skills folder

the second thing is identity prompt:
contains several things , you are crunchy neck agent, personal agent to handle your users works

then a support for USER.md to support context management of user and his details should aslo have a prompt in agent design telling how to interact with USER.md and how to update it when finding a fact and prefrence

then a support for MEMORY.md to manage multiple sessions memory, context (size capped based extraction into the agent) updation will be automatic after session ends

