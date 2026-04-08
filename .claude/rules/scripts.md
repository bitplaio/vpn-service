---
paths:
  - "scripts/**"
  - "*.sh"
---

# Scripts Rules

- ALWAYS use `set -euo pipefail` at the top of every script
- ALWAYS quote variables: "$VAR" not $VAR
- NEVER use `rm -rf` without explicit path validation
- ALWAYS check if required tools exist before using them
- ALWAYS provide usage/help when called with wrong arguments
- NEVER hardcode server IPs, paths, or credentials — use env vars or .env
- Make scripts idempotent where possible (safe to run multiple times)
- Use `#!/usr/bin/env bash` shebang for portability
- Add comments for non-obvious logic
- Exit with meaningful error codes and messages
