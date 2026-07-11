## Claude Best Practices
  ┌───────────┬────────────────────────────────────────────────────────────────────────────────────────────────┐
  │   Mode    │                                          How it works                                          │
  ├───────────┼────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Team      │ Staged pipeline: plan → PRD → exec → verify → fix. Multiple Claude agents on shared task list. │
  ├───────────┼────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Autopilot │ Single lead agent drives from requirement to completion autonomously.                          │
  ├───────────┼────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Ralph     │ Persistence loop — won't stop until verification confirms full completion.                     │
  ├───────────┼────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ UltraWork │ Maximum parallelism, burst execution across many agents.                                       │
  ├───────────┼────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ UltraQA   │ Cycles diagnose → fix until tests/builds/lint all pass.                                        │
  └───────────┴────────────────────────────────────────────────────────────────────────────────────────────────┘
### Chat
**Prompt this first:** "Rewrite this email to sound more direct but not rude."

---

### Cowork
Cowork reads your files & creates real documents - Excel, Word, PDF

**Prompt this first:** "Read my files first. Then ask me questions before you start."

**Pro tip:** Write one .md file about yourself: what you do, how you write. Claude stops sounding generic.

**Common mistake:** Dumping 200 files and hoping for Claude to give you the best; 5 great files beat 50 messy ones.

---

### Projects

**Pro tip:** One Project per recurring task. Don't build one mega Project for everything.

**Common mistake:** Uploading 30 reference docs; Claude won't know which ones matter; You pick the best - not the AI

---

### Artifacts

Claude builds interactive files you can use, edit, and download

**Prompt this first:** Build me a monthly budget calculator with fields for rent, groceries, transport & subscriptions - totals update in real time.

**Pro tip:** Ask for changes after it builds: "Make it dark mode." "Add a column."

**Common mistake:** Thinking Artifacts are just demos. Ask for what you'd normally build in a spreadsheet or Canva (planners, trackers).

---

### Connectors

Link Slack, Google Drive, Notion, Gamma (slides), & 50+ tools. Claude searches them during chat.

**Prompt this first:** "Find the Q3 sales deck in my Drive" - no uploading, no screenshots.

**Pro tip:** Use the Gamma connector in Cowork to go from a prompt > outline > finished presentation slides.

**Common mistake:** Thinking it syncs live. Claude searches your go-to tools on demand.

---

### Plugins

One-click skill packs that add commands for Sales, Marketing, Legal, Data, and more.

**Pro tip:** Type / in any chat to see every command a plugin added.

- Install the Marketing plugin
- type /draft-post
- get a LinkedIn post with a specific CTA

**Common mistake:** Installing all 11 plugins. Each adds context that Claude has to judge. Pick 2 plugins that actually match your actual job.

---

### Skills

Reusable instruction packs that make Claude better at specific tasks.

- Go to Settings > enable Code Execution
- Browse the pre-built Skills library
- Install one

**Pro tip:** You can create your own. Brand guidelines, review checklists, writing formats.

---

## Others
1. https://github.com/weikma/claude-code-rebuilt
2. https://github.com/shareAI-lab/learn-claude-code
3. agent infra: https://github.com/iii-hq/iii?tab=readme-ov-file
4. Android device automation: https://llamalab.com/automate/
5. https://github.com/ruizrica/agent-pi
