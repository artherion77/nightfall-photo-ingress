# Copilot Project Instructions

## Infrastructure Policy

### Cloudflared Tunnel Management
- **DO NOT** start the cloudflared tunnel unless explicitly requested in a prompt
- Default state: OFF (cloudflared strict validation should not block E2E tests)
- If a prompt indirectly triggers tunnel operations, halt and ask for confirmation

### E2E Testing Policy
- **DO NOT** run Playwright E2E tests in the dev container (`dev-photo-ingress`)
- **DO NOT** install Playwright browser binaries in the dev container
- **Always use governed E2E execution**: `./dev/bin/govctl run staging.e2e.module1 --json`
- Unit tests (`web.test.unit`) are fine in dev container; E2E must use staging infrastructure

## Execution Guardrails

### Non-Infrastructure Implementation Blocked by Infrastructure Issues
When a non-infrastructure feature implementation (e.g., C7 audit timeline code) is blocked by an unrelated infrastructure issue:

1. **Stop execution** — do not continue work on the feature
2. **Diagnose the blocker** — identify the infrastructure issue (e.g., cloudflared strict check failure)
3. **Recommend corrective actions** — document the issue and suggest ops steps (e.g., disable/fix cloudflared strict validation)
4. **Wait for user confirmation** — do not proceed until the user explicitly acknowledges and approves the workaround

### Rationale
Infrastructure blockers are ops concerns, not code concerns. Continuing feature work while infrastructure is broken creates a false sense of completion and masks systemic issues.
