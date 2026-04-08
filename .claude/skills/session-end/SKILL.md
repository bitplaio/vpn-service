---
name: session-end
description: Write session log, quality analysis, update patterns. Run at END of every session where code changed.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

# Session End Skill

## Steps

1. **Gather commits from this session:**
   ```bash
   git log --oneline --since="today" 2>/dev/null || git log --oneline -10
   ```

2. **Read today's session file:**
   ```bash
   cat .claude/sessions/$(date +%Y-%m-%d).md 2>/dev/null
   ```

3. **Run self-learning analysis:**

   Evaluate the session:
   - **What worked well?** (approaches, tools, patterns that saved time)
   - **What failed or was slow?** (wrong approaches, missing context, errors)
   - **New patterns discovered?** (things to remember for future sessions)
   - **Security concerns?** (any close calls with secrets, permissions)

4. **Update session file with final state:**
   ```markdown
   ## Quality Analysis

   ### What Worked
   - [list]

   ### What Failed / Was Slow
   - [list]

   ### New Patterns
   - [list]

   ### Security Notes
   - [list]

   ---
   status: completed
   ```

5. **Update quality_patterns.md (if new lessons):**
   - Read current `memory/quality_patterns.md`
   - Append new patterns if genuinely new (not duplicates)
   - Categories: Docker, WireGuard, Vaultwarden, Security, Deploys, Context Efficiency

6. **Cleanup old sessions (keep 15 max):**
   ```bash
   ls -t .claude/sessions/*.md 2>/dev/null | tail -n +16 | xargs rm -f 2>/dev/null
   ```

7. **Report summary:**
   ```
   ## Session Complete

   **Commits:** X
   **Changes:** [summary]
   **New patterns:** X added to quality_patterns.md
   **Open items:** [list for next session]
   ```
