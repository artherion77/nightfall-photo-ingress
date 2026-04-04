# Security Audit — nightfall-photo-ingress
**Date:** 2026-04-04  
**Auditor:** GitHub Copilot (GPT-5.3-Codex)  
**Scope:** All dependency packages (Python + Node.js) across the full project  
**Triggered by:** devctl legacy-command cleanup, GPT-audit, drift hardening session (commit `062a271`)

---

## 1. Policy

| Severity   | Production packages     | Dev-only packages (build, test toolchain) |
|------------|------------------------|------------------------------------------|
| Critical   | Block release           | Block release                            |
| High       | Block release           | Block release                            |
| Moderate   | Block release           | **Acceptable** — isolated container, no internet attack surface |
| Low        | Acceptable              | Acceptable                               |

**Rationale for dev-tool exception:** The webui test/build stack (vitest, vite dev-server, esbuild, playwright) runs exclusively inside an LXC container on a local network with no externally reachable attack surface. Vulnerabilities in this tier describe either (a) dev-server request proxying exploitable only by a co-located attacker or (b) build-output artefacts that do not ship to production. The SvelteKit static adapter produces plain HTML/JS/CSS; none of the dev toolchain packages are bundled into the deployed artefact.

---

## 2. Python Production Dependencies

Audited with `pip-audit` against the project venv (Python 3.12.3).  
All 65 installed packages (65 direct + transitive) were checked against OSV.

| Package       | Version   | CVEs | Verdict |
|---------------|-----------|------|---------|
| fastapi       | 0.135.3   | 0    | ✅ Clean |
| uvicorn       | 0.42.0    | 0    | ✅ Clean |
| starlette     | 1.0.0     | 0    | ✅ Clean |
| httpx         | 0.28.1    | 0    | ✅ Clean |
| msal          | 1.35.1    | 0    | ✅ Clean |
| pydantic      | 2.12.5    | 0    | ✅ Clean |
| anyio         | 4.13.0    | 0    | ✅ Clean |
| h11           | 0.16.0    | 0    | ✅ Clean |

**Python result: PASS — no known vulnerabilities in production packages.**

---

## 3. Node.js npm Dependencies (webui/)

Audited with `npm audit` against the regenerated `package-lock.json`  
(lockfileVersion 3, Node 22.10.0, npm 10.9.0).

### 3.1 Pre-audit state — exact pins identified and remediated

Two packages were found with exact-pinned versions, preventing automatic patch updates:

| Package   | Before         | After      | Reason for pin (legacy) |
|-----------|----------------|------------|------------------------|
| `vitest`  | `1.6.1` (exact) | `^3.1.0`  | Node 18 compatibility workaround; Node 22 now pinned |
| `jsdom`   | `22.1.0` (exact) | `^25.0.0` | No security updates reaching pinned version |

Additional bump applied:

| Package          | Before     | After      | Reason |
|------------------|------------|------------|--------|
| `@playwright/test` | `^1.55.0` | `^1.55.1` | Minimum raised to patched floor (see HIGH below) |

### 3.2 Resolved versions after lockfile regeneration

| Package               | Resolved version |
|-----------------------|-----------------|
| vitest                | 3.2.4           |
| @vitest/mocker        | 3.2.4           |
| vite-node             | 3.2.4           |
| jsdom                 | 25.0.1          |
| vite                  | 5.4.21          |
| esbuild               | 0.21.5          |
| svelte                | 5.55.1          |
| @sveltejs/kit         | 2.56.1          |
| cookie                | 0.6.0           |
| playwright            | 1.59.1          |
| @playwright/test      | 1.59.1          |

### 3.3 Vulnerability findings after remediation

#### HIGH — playwright SSL certificate bypass `GHSA-7mvr-c777-76hp`
- **Package:** `playwright` / `@playwright/test` < 1.55.1  
- **Finding:** Browser binary downloads did not verify SSL certificate authenticity, enabling supply-chain interception.  
- **Action taken:** `@playwright/test` minimum floor raised to `^1.55.1`. Resolved to 1.59.1.  
- **Status: FIXED** ✅

---

#### MODERATE — esbuild dev-server `GHSA-67mh-4wv8-2f99`
- **Package:** `esbuild` ≤ 0.24.2 (resolved: 0.21.5, via `vite`)  
- **Description:** Any website can send cross-origin requests to the esbuild development server and read the response.  
- **Attack surface:** Vite dev-server only; only reachable within the LXC container's private loopback. The production build output does not include esbuild.  
- **Fix path:** Requires upgrading vite `5.x → 6.x` which is a breaking change for `@sveltejs/vite-plugin-svelte`. Outside scope of this session.  
- **Status: ACCEPTED — dev-only, isolated container** ⚠️

#### MODERATE — vite dev-server (transitive, via esbuild)
- **Packages:** `vite`, `@sveltejs/kit`, `@sveltejs/vite-plugin-svelte`, `@sveltejs/vite-plugin-svelte-inspector`, `vitefu`, `@testing-library/svelte`  
- **Description:** All inherit the esbuild dev-server moderate advisory through the vite 5.x dependency chain.  
- **Status: ACCEPTED — same root cause as esbuild above** ⚠️

#### MODERATE — vitest/vite-node (transitive, via vite)
- **Packages:** `vitest` 3.2.4, `@vitest/mocker` 3.2.4, `vite-node` 3.2.4  
- **Description:** Transitive vite dev-server moderate propagated through vitest's internal vite dependency.  
- **Note:** Upgrading vitest to 3.x (from the pre-audit `1.6.1`) was the correct remediation step; the residual is the vite 5→6 gap, not a vitest-specific flaw.  
- **Status: ACCEPTED — dev-only, isolated container** ⚠️

#### LOW — cookie `GHSA-pxg6-pf52-xh8x`
- **Package:** `cookie` < 0.7.0 (resolved: 0.6.0, via `@sveltejs/kit`)  
- **Description:** Cookie names/paths/domains accept out-of-bounds characters. Affects server-side cookie parsing at runtime.  
- **Classification note:** `@sveltejs/kit` is used for the `vite build` step and SSR/dev-server only. The static adapter (`@sveltejs/adapter-static`) strips all server-side runtime from the deployed artefact; cookie parsing is not present in production output.  
- **Fix path:** `npm audit fix --force` would downgrade `@sveltejs/kit` to `0.0.30` — a mis-targeted advisory resolution. Upstream fix in a compatible `@sveltejs/kit` minor is pending.  
- **Status: ACCEPTED — build-time only** ⚠️

#### LOW — @sveltejs/adapter-static (transitive, via @sveltejs/kit)
- **Description:** Inherits kit's cookie advisory transitively.  
- **Status: ACCEPTED — same root cause** ⚠️

### 3.4 Summary table

| Package group               | Severity   | Production surface | Status    |
|-----------------------------|------------|-------------------|-----------|
| playwright / @playwright/test | HIGH      | test toolchain     | **FIXED** |
| esbuild + vite (dev server) | MODERATE   | none (dev-only)    | Accepted  |
| vitest + vite-node          | MODERATE   | none (dev-only)    | Accepted  |
| @sveltejs/kit chain         | MODERATE   | none (build-time)  | Accepted  |
| cookie                      | LOW        | none (build-time)  | Accepted  |
| @sveltejs/adapter-static    | LOW        | none (build-time)  | Accepted  |

---

## 4. Conclusions

### Policy compliance

| Category | Finding | Policy result |
|----------|---------|---------------|
| Python production packages | 0 known vulnerabilities across all 65 packages | **PASS** |
| Node production packages | No production packages shipped (static adapter) | **PASS** |
| Node HIGH vulnerabilities | 1 found (playwright), 1 fixed | **PASS** |
| Node MODERATE vulnerabilities | 10 found, all dev-server/build-tool only | **PASS** (isolated container exception) |
| Node LOW vulnerabilities | 2 found, all build-time only | **PASS** |

### Overall verdict: **PASS**

All vulnerabilities with a real production attack surface have been resolved. Residual moderate and low findings are confined to the Vite 5.x dev-server, build toolchain, and test runner — none of which run in production or are reachable from outside the local LXC network.

### Remaining technical debt

The one actionable medium-term item is the vite `5.x → 6.x` upgrade, which resolves the esbuild dev-server SSRF advisory chain. This is a breaking change that requires `@sveltejs/vite-plugin-svelte` ≥ 5.x and SvelteKit compat testing; it is tracked as future work and does not affect production security posture today.

---

## 5. Artefacts and references

| Artefact | Location |
|----------|----------|
| npm audit tool | `npm audit` (Node 22.10.0 / npm 10.9.0) |
| Python audit tool | `pip-audit` (OSV database) |
| webui lockfile after remediation | `webui/package-lock.json` (lockfileVersion 3) |
| webui package manifest after remediation | `webui/package.json` |
| Session commit baseline | `062a271` |
| Advisory: playwright SSL | https://github.com/advisories/GHSA-7mvr-c777-76hp |
| Advisory: esbuild dev-server | https://github.com/advisories/GHSA-67mh-4wv8-2f99 |
| Advisory: cookie out-of-bounds | https://github.com/advisories/GHSA-pxg6-pf52-xh8x |
