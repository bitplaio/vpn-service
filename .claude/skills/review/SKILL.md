---
name: review
description: Run code-reviewer + security-auditor agents in parallel. Use before merging or deploying.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, Agent
---

# Review Skill

## Steps

1. **Get list of changed files:**
   ```bash
   git diff --name-only HEAD~1
   git diff --cached --name-only
   ```

2. **Spawn agents in parallel:**

   **Agent 1: code-reviewer**
   - Use `.claude/agents/code-reviewer.md` agent definition
   - Pass list of changed files
   - Ask to review against project rules

   **Agent 2: security-auditor**
   - Use `.claude/agents/security-auditor.md` agent definition
   - Pass list of changed files
   - Ask to audit for security issues

3. **Synthesize results:**
   - Combine findings from both agents
   - Group by severity (CRITICAL, HIGH, MEDIUM, LOW)
   - List specific files and line numbers

4. **Give verdict:**
   - **READY** — no critical or high issues
   - **NEEDS FIXES** — list what must be fixed before deploy

5. **Output format:**
   ```
   ## Review Results

   ### Code Review
   [findings]

   ### Security Audit
   [findings]

   ### Verdict: READY / NEEDS FIXES
   [summary]
   ```
