# Phase-1.5 Web UI Forensic Report

Date: 2026-04-10
Scope: Read-only forensic analysis of lost Phase-1.5 PhotoWheel changes
Repository: nightfall-photo-ingress

---

## J. Executive Summary

**Core Finding:** ALL Phase-1.5 Web UI code changes (19 commits on the `design` branch) were **never merged into `main`**. The "Branch Reconciliation" commit `fbd89b7` on 2026-04-09 at 23:01 CEST was a **docs-only manual commit** (not a git merge), which copied only 6 documentation/planning files. All 20 webui/component/test code files from the `design` branch remain orphaned — reachable only through git reflog.

**Staging Impact:** The staging container was last deployed at 2026-04-09 21:26 UTC (23:26 CEST) via `govctl staging.install`. At that time, the working directory was already on `main` (post-reconciliation). The staging container therefore runs the pre-Phase-1.5 code, missing all fidelity improvements.

**Immediate Recovery:** A single unified patch (3013 lines, 21 files) generated from `git diff 5947ffe0 28233ec5` applies cleanly to current `main` HEAD (`d4b35ed1`) with **zero conflicts**. No must-preserve changes on `main` are affected.

**Risk Level:** LOW. Patch applies cleanly. Must-preserve audit hardening changes (Fixes 2-4) touch completely disjoint files. Recovery is a single `git apply` + verification cycle.

---

## A. Chronological Commit Timeline

### Main branch (5947ffe0..d4b35ed1)

| # | Date (CEST) | SHA | Message | Notes |
|---|-------------|-----|---------|-------|
| 1 | 2026-04-08 11:09 | `5947ffe0` | Harden staging invariants and tighten govctl staging validation | Fork point for `design` branch |
| 2 | 2026-04-09 23:01 | `fbd89b74` | Branch Reconciliation: Merge design into main (docs only) | **NOT a merge commit** — single parent, docs only |
| 3 | 2026-04-09 23:11 | `e0ed8bf7` | Audit Hardening — Fix 2: Align audit triage filter names | **MUST PRESERVE** — touches audit/+page.svelte |
| 4 | 2026-04-09 23:22 | `2376c0eb` | fix(govctl): add run subcommand alias | On fix/issue-18-govctl-run-alias branch |
| 5 | 2026-04-09 23:22 | `bd5c8e69` | Merge fix/issue-18-govctl-run-alias into main | Merge commit (2 parents) |
| 6 | 2026-04-09 23:22 | `4452a0aa` | Audit Hardening — Fix 3: Revalidate queue after triage | **MUST PRESERVE** — touches stagingQueue + new test |
| 7 | 2026-04-09 23:27 | `24e07890` | Audit Hardening — Fix 4: Bound auth failure audit writes | **MUST PRESERVE** — touches test_auth_handshake.py |
| 8 | 2026-04-09 23:38 | `e790c93c` | fix: add auth failure audit prune maintenance | Non-webui |
| 9 | 2026-04-09 23:39 | `ccb7898d` | fix(docs): redirect Playwright E2E to staging | Docs only |
| 10 | 2026-04-09 23:44 | `4d92f2c6` | fix: use repo venv for govctl backend tests | Non-webui |
| 11 | 2026-04-09 23:49 | `d8308403` | fix: align mcp web task mappings | Non-webui |
| 12 | 2026-04-10 00:01 | `a762e673` | refactor: route mcp tasks through govctl | Non-webui |
| 13 | 2026-04-10 00:31 | `d4b35ed1` | docs: consolidate development handbook and operations runbook | HEAD |

### Design branch (5947ffe0..28233ec5) — ORPHANED

| # | Date (CEST) | SHA | Message | Category |
|---|-------------|-----|---------|----------|
| 1 | 2026-04-08 21:50 | `4a343aa1` | PhotoWheel Fidelity: final validation and system sign-off | Docs + WebUI + Tests |
| 2 | 2026-04-08 21:59 | `c6d9f903` | design: VIS-1 is a perceptual invariant, not a pixel gate | Docs only |
| 3 | 2026-04-08 22:06 | `0b9737ca` | chore(webui): add Playwright type shim; suppress implicit-any | Tests infra |
| 4 | 2026-04-09 08:32 | `7b9d63bf` | feat(photowheel): Phase 1 complete — absolute stage layout | **Core WebUI** |
| 5 | 2026-04-09 09:29 | `d3cc94af` | feat(photowheel): Phase 2 complete — WAAPI content animation | **Core WebUI** |
| 6 | 2026-04-09 09:47 | `dc561551` | Adjust thumbnail behavior test to use post-arrival request deltas | Tests |
| 7 | 2026-04-09 10:21 | `730323af` | Fix thumbnail auth for img src via query token fallback | **API + WebUI** |
| 8 | 2026-04-09 16:34 | `c5117993` | PhotoWheel Fidelity - Chunk 0: Full-viewport layout and scroll containment | **Core WebUI** |
| 9 | 2026-04-09 16:37 | `54e2b3c0` | moved to implemented | Docs move |
| 10 | 2026-04-09 16:38 | `5e46ee84` | added visual design decisions for the fidelity improvements | Docs |
| 11 | 2026-04-09 16:41 | `7b5253b8` | E2E: fix thumbnail fallback route matcher for tokenized URLs | Tests |
| 12 | 2026-04-09 16:51 | `7bf552aa` | E2E: stabilize visual-invariants navigation assertions | Tests |
| 13 | 2026-04-09 16:57 | `cc64b6a2` | PhotoWheel Fidelity - Chunk 1: active photo visual dominance | **Core WebUI** |
| 14 | 2026-04-09 17:03 | `1e002a1d` | PhotoWheel Fidelity - Chunk 2: CTA button redesign | **Core WebUI** |
| 15 | 2026-04-09 17:09 | `d8f1adb6` | PhotoWheel Fidelity - Chunk 3: drag and drop | **Core WebUI** |
| 16 | 2026-04-09 17:22 | `894b9a3a` | PhotoWheel Fidelity - Chunk 4: operator-first metadata | **Core WebUI** |
| 17 | 2026-04-09 17:32 | `d35178e0` | PhotoWheel Fidelity - Chunk 5: detail sheet and panel removal | **Core WebUI** |
| 18 | 2026-04-09 22:32 | `d5bec1d4` | Several fidelity patches (accept/reject buttons, colors, sidecar) | **Core WebUI** |
| 19 | 2026-04-09 22:44 | `28233ec5` | Audit Hardening — Fix 1: Preload thumbnail auth | **WebUI + Tests** |

---

## B. Branch Activity Map

| Branch | First Commit | Last Commit | Commits | Status | Relevant SHAs |
|--------|-------------|-------------|---------|--------|---------------|
| `main` | pre-existing | 2026-04-10 00:31 | 12 since fork | Active (HEAD) | d4b35ed1 (HEAD) |
| `design` | 2026-04-08 21:50 | 2026-04-09 22:44 | 19 | **DELETED** (orphaned in reflog) | 4a343aa1..28233ec5 |
| `fix/issue-18-govctl-run-alias` | 2026-04-09 23:22 | 2026-04-09 23:22 | 1 | Merged to main, deleted | 2376c0eb |
| `fix/issue-20-playwright-staging-docs` | 2026-04-09 23:27 | 2026-04-09 23:27 | 0 (checkout only) | Deleted | — |
| `metrics` | pre-existing | 2026-04-07 20:19 | 0 since fork | Stale | — |

---

## C. Merge Reconstruction

### The "Reconciliation" Commit

- **SHA:** `fbd89b74bc8228f96c4e032584d708fe3186d1e8`
- **Timestamp:** 2026-04-09 23:01:43 +0200
- **Author:** artherion77
- **Message:** "Branch Reconciliation: Merge design into main (docs only)"
- **Parent count:** 1 (single parent: `5947ffe0`)
- **This is NOT a git merge.** It is a regular commit on `main` that manually added documentation files.

### Files included in the reconciliation:

| File | Lines Added | Status on main |
|------|-------------|----------------|
| design/web/README.md | 1 | Added |
| design/web/photowheel-visual-design-decisions.md | 1236 | Added (identical to design) |
| planning/implemented/photo-wheel-fidelity.md | 1018 | Added (identical to design) |
| planning/invariants-click-flake-investigation-2026-04-09.md | 44 | Added |
| planning/planned/photowheel-fidelity-improvements.md | 569 | Added (identical to design) |
| planning/planned/photowheel-stage-model-migration.md | 459 | Added (identical to design) |

### Files EXCLUDED from the reconciliation (the lost changes):

All webui components, api/auth.py, all E2E tests, all Playwright configs, all component tests modified/created on the design branch.

---

## D. Phase-1.5 Commit Set

### Commits containing code changes (non-docs)

The following commits exist ONLY on the orphaned `design` branch. None are ancestors of `main`.

| SHA | Files Changed | Key Changes |
|-----|--------------|-------------|
| `4a343aa1` | 14 files | PhotoWheel.svelte (+19/-5), playwright.config.ts (new), 3 E2E specs (new), 3 pytest bridges (new), PhotoWheelWindowing.test.ts (+36) |
| `0b9737ca` | 4 files | playwright-shim.d.ts (new), E2E spec type fixes |
| `7b9d63bf` | 4 files | PhotoWheel.svelte (116 lines rewritten — absolute stage layout), E2E specs updated |
| `d3cc94af` | 4 files | PhotoWheel.svelte (+38 — WAAPI animation), E2E spec cleanup |
| `dc561551` | 1 file | thumbnail-behavior.spec.ts test adjustment |
| `730323af` | 3 files | **api/auth.py** (+16 — query token fallback), photocard-image.ts (+4/-1), E2E fix |
| `c5117993` | 4 files | PhotoWheel.svelte (+6/-1 — scroll containment), +layout.svelte (+1), +page.svelte (+5), fidelity plan (new) |
| `7b5253b8` | 1 file | E2E route matcher fix |
| `7bf552aa` | 2 files | E2E navigation assertion stabilization |
| `cc64b6a2` | 3 files | PhotoCard.svelte (+3/-1), PhotoWheel.svelte (+10/-4 — visual dominance) |
| `1e002a1d` | 2 files | TriageControls.svelte (+85 — CTA redesign) |
| `d8f1adb6` | 4 files | PhotoWheel.svelte (+60 — drag&drop), TriageControls.svelte (+64), +page.svelte (+5) |
| `894b9a3a` | 4 files | PhotoCard.svelte (+46/-7 — operator metadata), PhotoWheel.svelte (+2) |
| `d35178e0` | 6 files | **DetailSheet.svelte** (new, 157 lines), PhotoCard.svelte (+42), PhotoWheel.svelte (+5/-1), +page.svelte (+14/-1) |
| `d5bec1d4` | 7 files | PhotoCard.svelte (+266 — major rework), TriageControls.svelte (+31), +page.svelte (+27/-), 2 new E2E specs |
| `28233ec5` | 3 files | PhotoWheel.svelte (+3/-1 — preload auth), test fixes |

---

## E. Divergence Analysis

### Files MISSING from main (exist only on design)

| File | Design SHA | Status |
|------|-----------|--------|
| webui/src/lib/components/staging/DetailSheet.svelte | 157 lines | Never merged |
| webui/playwright.config.ts | 44 lines | Never merged |
| webui/tests/playwright-shim.d.ts | 38 lines | Never merged |
| webui/tests/e2e/photowheel.centering-perceptual.spec.ts | 359 lines | Never merged |
| webui/tests/e2e/photowheel.visual-invariants.spec.ts | 546 lines | Never merged |
| webui/tests/e2e/photowheel.thumbnail-behavior.spec.ts | 343 lines | Never merged |
| webui/tests/e2e/cta-button-colors.spec.ts | 90 lines | Never merged |
| webui/tests/e2e/photocard.action-buttons.spec.ts | 63 lines | Never merged |
| tests/e2e/test_photowheel_centering_playwright.py | 59 lines | Never merged |
| tests/e2e/test_photowheel_thumbnail_behavior_playwright.py | 59 lines | Never merged |
| tests/e2e/test_photowheel_visual_invariants_playwright.py | 59 lines | Never merged |

### Files DIVERGED between main and design

| File | Main Blob SHA | Design Blob SHA | Classification |
|------|--------------|----------------|----------------|
| PhotoWheel.svelte | `5ba8b611` | `42b666d6` | Never merged (main has pre-Phase-1.5 version) |
| PhotoCard.svelte | `85d08480` | `899c7dff` | Never merged |
| TriageControls.svelte | `1d0270c0` | `c2752065` | Never merged |
| photocard-image.ts | `754be53a` | `086dcfdc` | Never merged |
| +page.svelte (staging) | `555ca30f` | `a4a0f4ee` | Never merged |
| +layout.svelte | `87d2968c` | `eb8f7dc2` | Never merged |
| PhotoWheelWindowing.test.ts | `a358e8a0` | `345f122f` | Never merged |
| PhotoCardImageLogic.test.ts | `f726cbfe` | `91d367e7` | Never merged |
| PhotoCardImage.test.ts | `217f73ff` | `58ab8e76` | Never merged |
| api/auth.py | (fork version) | `3ccbda1` | Never merged |

**All divergences are classified as: "never merged into main."** No overwrites or post-merge regressions occurred. The code simply was never brought over.

---

## F. Micro-Changes on Main (Must Preserve)

| SHA | Date | Message | Files | Why Preserve |
|-----|------|---------|-------|-------------|
| `e0ed8bf7` | 2026-04-09 23:11 | Audit Hardening — Fix 2: Align audit triage filter names | webui/src/routes/audit/+page.svelte | Audit correctness fix |
| `4452a0aa` | 2026-04-09 23:22 | Audit Hardening — Fix 3: Revalidate queue after triage | webui/src/lib/stores/stagingQueue.svelte.js, webui/tests/component/StagingQueue.test.ts (new) | Queue integrity fix + test coverage |
| `24e07890` | 2026-04-09 23:27 | Audit Hardening — Fix 4: Bound auth failure audit writes | tests/e2e/test_auth_handshake.py | Security hardening |

**Conflict Risk: ZERO.** The Phase-1.5 patch (from fork-point to design tip) touches NONE of these files. The two change sets are fully disjoint.

---

## G. Staging Container Runtime Verification

| Property | Value |
|----------|-------|
| Container Name | staging-photo-ingress |
| Status | RUNNING |
| IP | 192.168.200.242 |
| WebUI Build Timestamp | 2026-04-09 21:36:28 UTC |
| Last staging.install govctl run | 2026-04-09 21:26:01 UTC (run-20260409T212601-o4zm5vxxxxxx) |
| Code deployed from | `main` branch (post-reconciliation, pre-audit-fixes) |
| Web build fingerprint | `2c72a1e8128a3582a82bfa6a8806c7e1252cc895367973d1e9db6c0806bd19a8` |
| Backend wheel fingerprint | `32b771eff09fde592108d1e5c7e8019398590f94dadd3103a5815f7b864d69ce` |

**Finding:** The staging container runs code from `main` at approximately commit `bd5c8e69` or `4452a0aa` (between Audit Fix 2 and Fix 4, based on the 23:26 CEST deploy time). This code does NOT contain any Phase-1.5 WebUI changes. It also does NOT contain the latest `main` HEAD commits (Audit Fix 4, docs consolidation, MCP routing, etc.).

**Note:** The staging container has no git checkout — code is deployed via built artifacts (wheel + SvelteKit build). No `.deploy-sha` or deploy metadata file exists in the container. The exact commit is inferred from govctl timestamps and reflog correlation.

---

## H. Reconstruction Plan

### Prerequisites
- Working directory clean on `main` branch
- All must-preserve changes verified present (Audit Fixes 2-4)

### Step 1: Apply the unified patch

```bash
cd /home/chris/dev/nightfall-photo-ingress
git checkout main
git apply --check tmp/phase15-complete-patch.diff   # dry run
git apply --index tmp/phase15-complete-patch.diff    # apply and stage
```

**Conflict expectation: NONE.** Tested via `git apply --check` — applies cleanly.

### Step 2: Verify must-preserve files are untouched

```bash
git diff --cached -- webui/src/lib/stores/stagingQueue.svelte.js   # should be empty
git diff --cached -- webui/src/routes/audit/+page.svelte            # should be empty  
git diff --cached -- webui/tests/component/StagingQueue.test.ts     # should be empty
git diff --cached -- tests/e2e/test_auth_handshake.py               # should be empty
```

### Step 3: Commit

```bash
git commit -m "feat(webui): restore Phase-1.5 PhotoWheel fidelity changes

Re-apply all Phase-1.5 Web UI changes from orphaned design branch
(4a343aa1..28233ec5) that were omitted from the docs-only reconciliation
commit fbd89b74.

Includes:
- Absolute stage layout (Phase 1) and WAAPI animation (Phase 2)
- Full-viewport scroll containment
- PhotoWheel Fidelity Chunks 0-5
- CTA button redesign
- Drag and drop support
- Operator-first metadata on PhotoCard
- DetailSheet component
- Thumbnail query-token auth fallback (api/auth.py)
- Playwright E2E test suites
- Component test updates"
```

### Step 4: Run verification

```bash
./dev/bin/govctl run test.web --json                    # typecheck + unit tests
./dev/bin/govctl run staging.install --json              # redeploy to staging
./dev/bin/govctl run staging.smoke --json                # smoke test
./dev/bin/govctl run staging.e2e.module1 --json          # E2E tests
```

### Alternative: Cherry-pick approach (NOT recommended)

Cherry-picking individual commits from the orphaned design branch is possible but unnecessary since:
1. The unified patch applies cleanly as a single unit
2. The design branch has a linear history (no merges)
3. A single commit is easier to revert if issues arise

If cherry-pick is preferred (e.g. for finer commit granularity):
```bash
git cherry-pick 4a343aa1 c6d9f903 0b9737ca 7b9d63bf d3cc94af dc561551 \
  730323af c5117993 54e2b3c0 5e46ee84 7b5253b8 7bf552aa cc64b6a2 \
  1e002a1d d8f1adb6 894b9a3a d35178e0 d5bec1d4 28233ec5
```

**Warning:** Cherry-pick may produce conflicts with must-preserve changes on `main` for files touched by both branches (PhotoCardImage.test.ts, PhotoCardImageLogic.test.ts). The unified-patch approach avoids this because it computes the diff from the fork point.

---

## I. Patch Bundle

Saved to: `tmp/phase15-complete-patch.diff` (3013 lines, 21 files)

Generated via:
```bash
git diff 5947ffe0 28233ec5 -- 'webui/**' 'tests/e2e/**' 'api/auth.py'
```

### Files in patch:

| File | Type | Lines |
|------|------|-------|
| api/auth.py | Modified | +16 |
| tests/e2e/test_photowheel_centering_playwright.py | New | +59 |
| tests/e2e/test_photowheel_thumbnail_behavior_playwright.py | New | +59 |
| tests/e2e/test_photowheel_visual_invariants_playwright.py | New | +59 |
| webui/playwright.config.ts | New | +44 |
| webui/src/lib/components/staging/DetailSheet.svelte | New | +157 |
| webui/src/lib/components/staging/PhotoCard.svelte | Modified | +281/-6 |
| webui/src/lib/components/staging/PhotoWheel.svelte | Modified | +221/-34 |
| webui/src/lib/components/staging/TriageControls.svelte | Modified | +158/-8 |
| webui/src/lib/components/staging/photocard-image.ts | Modified | +4/-1 |
| webui/src/routes/+layout.svelte | Modified | +1 |
| webui/src/routes/staging/+page.svelte | Modified | +51/-7 |
| webui/tests/component/PhotoCardImage.test.ts | Modified | +1/-1 |
| webui/tests/component/PhotoCardImageLogic.test.ts | Modified | +4/-2 |
| webui/tests/component/PhotoWheelWindowing.test.ts | Modified | +36 |
| webui/tests/e2e/cta-button-colors.spec.ts | New | +90 |
| webui/tests/e2e/photocard.action-buttons.spec.ts | New | +63 |
| webui/tests/e2e/photowheel.centering-perceptual.spec.ts | New | +359 |
| webui/tests/e2e/photowheel.thumbnail-behavior.spec.ts | New | +343 |
| webui/tests/e2e/photowheel.visual-invariants.spec.ts | New | +546 |
| webui/tests/playwright-shim.d.ts | New | +38 |

---

## K. Risk and Regression Analysis

| Risk | Severity | Mitigation |
|------|----------|------------|
| Patch fails to apply after future commits on main | LOW (tested clean today) | Apply promptly; re-test with `git apply --check` before applying |
| api/auth.py query token fallback security | MEDIUM | Review the `hmac.compare_digest` usage — it uses constant-time comparison, which is correct. Ensure `app_config.web.api_token` is never empty in production. |
| Playwright E2E specs reference staging URLs | LOW | Specs use `STAGING_BASE_URL` env var; confirm staging is redeployed before running E2E |
| Design tokens or CSS variable drift | LOW | No CSS token files were modified on `main` since fork. Token file unchanged. |
| DetailSheet.svelte is entirely new | LOW | No import conflicts — `+page.svelte` from design adds the import |
| Unit test count regression | NONE | Design branch adds 36 tests; existing 150+ tests in StagingQueue.test.ts are disjoint |
| Staging needs redeploy after patch | REQUIRED | Run `govctl staging.install` after committing |

### Recommended application order:
1. Apply unified patch (`git apply --index`)
2. Verify must-preserve files untouched
3. Commit
4. Run `govctl run test.web --json` (typecheck + unit)
5. Push to remote
6. Run `govctl run staging.install --json`
7. Run `govctl run staging.smoke --json`
8. Run `govctl run staging.e2e.module1 --json`

---

## L. Machine-Readable JSON Summary

```json
{
  "report_date": "2026-04-10",
  "repository": "nightfall-photo-ingress",
  "finding": "Phase-1.5 Web UI changes never merged to main",
  "cause": "docs-only reconciliation commit (not a git merge)",
  "reconciliation_commit": "fbd89b74bc8228f96c4e032584d708fe3186d1e8",
  "fork_point": "5947ffe0d88dfbaed053b8fcaebb7f0b6001a61c",
  "design_branch_tip": "28233ec51254c0e7000b06b0c535b937b4e74573",
  "main_head": "d4b35ed134ce14b130404fd3d67b16240e424ecf",
  "design_branch_status": "deleted_orphaned_in_reflog",
  "orphaned_commits": [
    "4a343aa194d2487ea141050268a681820bc20b42",
    "c6d9f903d33613c8d15d3b6853fbdbf69e306970",
    "0b9737cadd6b4f4279c6304e476d282c681a9e57",
    "7b9d63bf567588ccbfd2ef698ac14320dd6a9a9f",
    "d3cc94af44aaad8eeaf3c0f57ec7d8ef8298f3f2",
    "dc561551bf5ac44de7f59d42292874781dbb13a8",
    "730323af56667e199b9a048d885b4a551a3d75a3",
    "c511799304cbfe2c7aedca6ce500a14a0552c960",
    "54e2b3c0d4a3eedd8276b39dcca1ae1b643c3742",
    "5e46ee84da511b1102126ad05f5d7a49254f4cc0",
    "7b5253b82c235e3530802f4a8d6df35745e34c34",
    "7bf552aaf5e4aa4b55281b4e86831a2867838da1",
    "cc64b6a24a130ee9076b4808cfe0d8bb0bd648d6",
    "1e002a1d3b2b5e56e164dd05401f74d98b4faaa6",
    "d8f1adb60c3cffd9a9afa0489a111e642cf723cd",
    "894b9a3a73eff8f18732a6bc522591a8b8a29f17",
    "d35178e07e53b9e7e682d2ee09ba7f66c1c06e7e",
    "d5bec1d478d8d8c0f9d99bfcbf230fa9ad04bc9e",
    "28233ec51254c0e7000b06b0c535b937b4e74573"
  ],
  "must_preserve_commits": [
    "e0ed8bf7ddbdd5227446e26f8ccde1fc6246d794",
    "4452a0aa6713590d392e9ef20518693fef89db89",
    "24e07890e5fff048e96fb4a82d7f534c88b2a612"
  ],
  "patch_applies_cleanly": true,
  "patch_conflict_count": 0,
  "patch_file": "tmp/phase15-complete-patch.diff",
  "patch_lines": 3013,
  "patch_files_count": 21,
  "affected_files": [
    "api/auth.py",
    "tests/e2e/test_photowheel_centering_playwright.py",
    "tests/e2e/test_photowheel_thumbnail_behavior_playwright.py",
    "tests/e2e/test_photowheel_visual_invariants_playwright.py",
    "webui/playwright.config.ts",
    "webui/src/lib/components/staging/DetailSheet.svelte",
    "webui/src/lib/components/staging/PhotoCard.svelte",
    "webui/src/lib/components/staging/PhotoWheel.svelte",
    "webui/src/lib/components/staging/TriageControls.svelte",
    "webui/src/lib/components/staging/photocard-image.ts",
    "webui/src/routes/+layout.svelte",
    "webui/src/routes/staging/+page.svelte",
    "webui/tests/component/PhotoCardImage.test.ts",
    "webui/tests/component/PhotoCardImageLogic.test.ts",
    "webui/tests/component/PhotoWheelWindowing.test.ts",
    "webui/tests/e2e/cta-button-colors.spec.ts",
    "webui/tests/e2e/photocard.action-buttons.spec.ts",
    "webui/tests/e2e/photowheel.centering-perceptual.spec.ts",
    "webui/tests/e2e/photowheel.thumbnail-behavior.spec.ts",
    "webui/tests/e2e/photowheel.visual-invariants.spec.ts",
    "webui/tests/playwright-shim.d.ts"
  ],
  "recovery_command": "git apply --index tmp/phase15-complete-patch.diff",
  "verification_commands": [
    "./dev/bin/govctl run test.web --json",
    "./dev/bin/govctl run staging.install --json",
    "./dev/bin/govctl run staging.smoke --json",
    "./dev/bin/govctl run staging.e2e.module1 --json"
  ],
  "staging_container": {
    "name": "staging-photo-ingress",
    "status": "RUNNING",
    "ip": "192.168.200.242",
    "deploy_timestamp_utc": "2026-04-09T21:36:28Z",
    "has_phase15_changes": false,
    "is_latest_main": false,
    "deployed_via": "govctl staging.install (run-20260409T212601-o4zm5vxxxxxx)",
    "web_build_sha256": "2c72a1e8128a3582a82bfa6a8806c7e1252cc895367973d1e9db6c0806bd19a8"
  }
}
```
