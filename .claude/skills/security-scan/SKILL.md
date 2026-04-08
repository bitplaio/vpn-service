---
name: security-scan
description: Grep-based security scan across all project files. Use for security audits.
allowed-tools: Bash, Read, Glob, Grep
---

# Security Scan Skill

## Steps

1. **Scan for exposed secrets:**
   ```bash
   grep -r -i -n -E "(password|secret|token|private.?key|api.?key)\s*[:=]" --include="*.yml" --include="*.yaml" --include="*.conf" --include="*.sh" --include="*.env" . 2>/dev/null | grep -v ".example" | grep -v ".git/"
   ```

2. **Check for hardcoded WireGuard keys:**
   ```bash
   grep -r -n -E "[A-Za-z0-9+/]{43}=" --include="*.conf" --include="*.yml" --include="*.yaml" . 2>/dev/null | grep -v ".git/" | grep -v ".example"
   ```

3. **Check .gitignore coverage:**
   - Verify `.env` is gitignored
   - Verify `*.key` / `privatekey` is gitignored
   - Verify `wg0.conf` with real keys is gitignored
   - Verify `backups/` is gitignored

4. **Check Docker security:**
   ```bash
   # Privileged mode (should only be WireGuard)
   grep -r -n "privileged:\s*true" --include="*.yml" . 2>/dev/null
   
   # Exposed ports beyond required
   grep -r -n "ports:" -A 5 --include="*.yml" . 2>/dev/null
   
   # Host network mode (avoid unless necessary)
   grep -r -n "network_mode:\s*host" --include="*.yml" . 2>/dev/null
   ```

5. **Check WireGuard config security:**
   ```bash
   # AllowedIPs too broad (0.0.0.0/0 is OK for clients, not for server peers)
   grep -r -n "AllowedIPs" --include="*.conf" . 2>/dev/null
   
   # DNS settings
   grep -r -n "DNS" --include="*.conf" . 2>/dev/null
   ```

6. **Check Vaultwarden security:**
   ```bash
   # Admin panel enabled (should be disabled or protected in prod)
   grep -r -n "ADMIN_TOKEN" --include="*.yml" --include="*.env" . 2>/dev/null | grep -v ".example"
   
   # Signups enabled (should be disabled after initial setup)
   grep -r -n "SIGNUPS_ALLOWED" --include="*.yml" --include="*.env" . 2>/dev/null
   
   # HTTPS enforcement
   grep -r -n "ROCKET_TLS" --include="*.yml" --include="*.env" . 2>/dev/null
   ```

7. **Check file permissions:**
   ```bash
   # Find world-readable secret files
   find . -name "*.key" -o -name "*.pem" -o -name ".env" | xargs ls -la 2>/dev/null
   ```

8. **Report by severity:**
   ```
   ## Security Scan Results

   ### CRITICAL
   [exposed secrets, hardcoded keys]

   ### HIGH
   [misconfigured permissions, open admin panels]

   ### MEDIUM
   [broad AllowedIPs, signups enabled]

   ### LOW
   [missing .gitignore entries, documentation gaps]

   ### Summary: X critical, X high, X medium, X low
   ```
