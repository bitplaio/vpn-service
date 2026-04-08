---
name: session-start
description: Load recent sessions + quality patterns, check branch state, create today's session file. Run at START of every session.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

# Session Start Skill

## Steps

1. **Read last 5 sessions:**
   ```bash
   ls -t .claude/sessions/*.md 2>/dev/null | head -5
   ```
   Read each file to understand recent context.

2. **Read quality patterns:**
   Read `memory/quality_patterns.md` from Claude memory directory.

3. **Check branch state:**
   ```bash
   git branch --show-current
   git status --short
   git log --oneline -5
   ```

4. **Check deploy state:**
   ```bash
   cat .claude/docs/deploy-state.json 2>/dev/null
   ```

5. **Create today's session file:**
   Write to `.claude/sessions/YYYY-MM-DD.md`:
   ```markdown
   ---
   date: YYYY-MM-DD
   branch: <current branch>
   status: in-progress
   ---

   # Session: YYYY-MM-DD

   ## Context
   [Branch state, recent sessions summary, what was last worked on]

   ## Goals
   [To be filled — ask user]

   ## Changes
   [Updated during session]

   ## Decisions
   [Updated during session]

   ## Commits
   [Updated during session]

   ## Open Items
   [Updated during session]
   ```

6. **Report to user:**
   ```
   ## Session Started

   **Branch:** <branch>
   **Last session:** <date> — <summary>
   **Pending items:** <from last session>

   What would you like to work on?
   ```
