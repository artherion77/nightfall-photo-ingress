# Copilot Project Instructions

## E2E Testing Instructions

Use the following guidelines when working with E2E tests in the Copilot project:
1. Use the project's governed E2E execution commands for all E2E test runs:
   ```bash
   ./dev/bin/govctl run staging.e2e --json
   ./dev/bin/govctl run staging.e2e.module1 --json
   ./dev/bin/govctl run staging.e2e.* --json
   ```

2. It is permissible to extend the command surface with additional module-specific commands (e.g., `staging.e2e.patterns`) as needed, but all E2E test execution must go through `govctl` to ensure proper environment setup and infrastructure integration.
3. Do not run Playwright E2E tests directly in the dev container (`dev-photo-ingress`).
4. Do not install Playwright browser binaries in the dev container or the host environment.
5. If you encounter infrastructure issues (e.g., cloudflared tunnel problems) that block E2E test execution, halt and diagnose the issue before proceeding with any feature work.
6. Document any infrastructure blockers and recommended corrective actions, and wait for explicit user confirmation before resuming work on the feature or tests.
