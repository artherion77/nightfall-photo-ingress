# Design: Staging Queue Footer Poll Status

**Date:** 2026-04-10
**Status:** Implemented

---

## 1. Summary

This document specifies the redesign of the Staging Queue app footer to accurately
display last-poll status, next-poll time, systemd timer operational state, and a
manual poll trigger button. It replaces the previous static "Last poll: never" display
with a full state machine driven by expanded health API fields.

---

## 2. Root Cause Analysis

### Causal chain for "Last poll: never / Invalid Date" defect

1. Status file `/run/nightfall-status.d/photo-ingress.json` lives on tmpfs; it is
   absent after container restart or first boot.
2. `HealthService.get_health()` checks file existence; if absent sets
   `updated_at = "never"` (string sentinel, not null).
3. `HealthResponse.last_updated_at` carries this string sentinel to the frontend.
4. The health store initialises `last_updated_at: undefined`.
5. `AppFooter.formatTime()` guards with `if (!iso) return 'never'`. The string
   `"never"` is truthy, so it passes into `new Date("never")`, producing Invalid Date.
6. `Invalid Date.getTime()` returns NaN; all time arithmetic returns NaN, resulting
   in malformed time display (e.g., "NaNm ago") or silent breakage.

### Additional deficiencies

- No `last_poll_at` field exposed as nullable ISO; only string sentinels.
- No `next_poll_at` field (systemd timer next fire time not exposed).
- No `poller_status` field (timer and service active state not exposed).
- No `poll_interval_minutes` in health response.
- No manual poll trigger API endpoint or UI button.

---

## 3. Data Model

### HealthResponse extended fields

| Field                 | Type          | Semantics |
|-----------------------|---------------|-----------|
| `last_poll_at`        | `str \| None` | ISO 8601 UTC of last status write; `None` when file absent |
| `next_poll_at`        | `str \| None` | ISO 8601 UTC of next scheduled timer fire; `None` if not computable |
| `poller_status`       | `str`         | `timer_running` \| `timer_stopped` \| `in_progress` \| `unknown` |
| `poll_interval_minutes` | `int`       | From effective config |
| `last_updated_at`     | `str`         | Retained backward-compat; value is `last_poll_at or "never"` |

### PollTriggerResponse

| Field    | Type  | Semantics                    |
|----------|-------|------------------------------|
| `status` | `str` | Always `"accepted"` on 202   |

### Frontend store additions

| Field                   | Type                         | Semantics |
|-------------------------|------------------------------|-----------|
| `last_poll_at`          | `string \| null \| undefined` | `undefined` while initialising, `null` if never polled |
| `next_poll_at`          | `string \| null`             | ISO string or null |
| `poller_status`         | `string`                     | Mirror of backend enum |
| `poll_interval_minutes` | `number`                     | From health response |

---

## 4. Backend Implementation

### Systemd status resolution

Two subprocess calls with a 2-second timeout apiece:

```
systemctl is-active nightfall-photo-ingress.service
  → "active"   = in_progress

systemctl is-active nightfall-photo-ingress.timer
  → "active"   = timer_running
  → "inactive" = timer_stopped

systemctl show nightfall-photo-ingress.timer \
  --property=NextElapseUSecRealtime --value
  → microseconds since Unix epoch (0 = not scheduled)
```

All calls are wrapped in `try/except`; failure falls back to `"unknown"` / `None`
so the service remains operational in test environments without systemd.

### Poll trigger endpoint

`POST /api/v1/poll/trigger` (auth required):

- Returns 409 if `poller_status === "in_progress"`.
- Spawns `sys.executable -m nightfall_photo_ingress.cli poll --path <config_path>`
  as a detached background process (`start_new_session=True`, `close_fds=True`).
- Returns 202 with `{"status": "accepted"}`.

### Config path routing

`config_path` is stored in `app.state.config_path` during lifespan startup.
`get_config_path(request)` dependency reads it, defaulting to
`/etc/nightfall/photo-ingress.conf` if not set.

---

## 5. Footer State Machine

Priority of evaluation: HEALTH_UNAVAILABLE → POLL_IN_PROGRESS → INITIALIZING →
null/non-null branch.

| State                      | Condition                                                    | Display |
|----------------------------|--------------------------------------------------------------|---------|
| `INITIALIZING`             | `last_poll_at === undefined`                                 | Last poll: loading… |
| `HEALTH_UNAVAILABLE`       | `health.error !== null`                                      | Health check unavailable |
| `POLL_IN_PROGRESS`         | `pollInProgress \|\| poller_status === 'in_progress'`        | spinner + Poll in progress… |
| `NEVER_POLLED`             | `last_poll_at === null && poller_status === 'timer_running'`  | Last poll: never + Next: [time] |
| `TIMER_STOPPED_NEVER_POLLED` | `last_poll_at === null && poller_status !== 'timer_running'` | Last poll: never + ⚠ Timer stopped |
| `POLLED_TIMER_RUNNING`     | `last_poll_at !== null && poller_status === 'timer_running'`  | Last poll: [time] + Next: [time] |
| `POLLED_TIMER_STOPPED`     | `last_poll_at !== null && poller_status === 'timer_stopped'`  | Last poll: [time] + ⚠ Timer stopped |
| `POLLED_UNKNOWN`           | `last_poll_at !== null && poller_status === 'unknown'`        | Last poll: [time] |

---

## 6. Time Formatting Rules

All times are displayed in the **browser local timezone** via
`Date.toLocaleTimeString()` and `Date.toLocaleDateString()`.
`Invalid Date` must never appear in any visible text.

### Past times (`last_poll_at`)

| Condition            | Output                          |
|----------------------|---------------------------------|
| `null \| undefined`  | `"never"`                       |
| Invalid date         | `"unknown"`                     |
| < 60 seconds ago     | `"just now"`                    |
| < 3 600 seconds ago  | `"Xm ago"`                      |
| < 86 400 seconds ago | `"Xh ago"`                      |
| Same calendar day    | `"today at HH:MM"` (local)      |
| Previous day         | `"yesterday at HH:MM"` (local)  |
| Within 7 days        | `"Ddd at HH:MM"` (local)        |
| Older                | `"D Mon YYYY"` (locale date)    |

### Future times (`next_poll_at`)

| Condition            | Output                           |
|----------------------|----------------------------------|
| `null \| undefined`  | `""` (field not rendered)        |
| Invalid date         | `""` (field not rendered)        |
| ≤ 0 seconds away     | `"soon"`                         |
| < 3 600 seconds away | `"in Xm"`                        |
| < 86 400 seconds away| `"in Xh"`                        |
| Same calendar day    | `"today at HH:MM"` (local)       |
| Next calendar day    | `"tomorrow at HH:MM"` (local)    |
| Other                | `"D Mon YYYY"` (locale date)     |

---

## 7. Manual Poll Button

### Placement

Footer right region, adjacent to the registry status badge.

### Button states

| Condition                                                     | State    | Label    |
|---------------------------------------------------------------|----------|----------|
| `!pollInProgress && poller_status !== 'in_progress'`          | enabled  | Poll now |
| `pollInProgress === true`                                     | disabled | Polling… + spinner |
| `poller_status === 'in_progress'`                             | disabled | Poll now |
| `health.error !== null`                                       | disabled | Poll now |

### Click flow

1. Set local `pollInProgress = true` (immediate button disable, `$state`).
2. Call `health.triggerPoll()` which POSTs `/api/v1/poll/trigger` then calls
   `fetchHealth()`.
3. On success: call `stagingQueue.loadPage()` to refresh queue display.
4. On any error: show transient error message in footer center for 4 seconds.
5. On 409 (already in progress): error propagates; health's `poller_status`
   keeps button disabled; transient message shows.
6. `pollInProgress = false` in `finally` block.

Non-optimistic: staging queue content is not modified before the API response.

---

## 8. Acceptance Criteria

### Last poll (LP)
- LP-1: Footer center always shows a last-poll indicator.
- LP-2: `last_poll_at === null` → displays "never".
- LP-3: Valid ISO → formatted time per rules above.
- LP-4: All displayed times in browser local timezone.
- LP-5: "Invalid Date" never appears in any browser-visible text.

### Next poll (NP)
- NP-1: Non-null `next_poll_at` → renders "Next: [formatted time]".
- NP-2: Null `next_poll_at` → no "Next:" line rendered.
- NP-3: `timer_stopped` → shows "⚠ Timer stopped" in place of "Next:" line.

### Timer status (TS)
- TS-1: `timer_running` → normal display, no warning badge.
- TS-2: `in_progress` → spinner + "Poll in progress…" message.
- TS-3: `timer_stopped` → amber "⚠ Timer stopped" badge.

### Manual poll button (MP)
- MP-1: "Poll now" button always rendered (may be disabled).
- MP-2: Button disabled when `pollInProgress || poller_status === 'in_progress' || health.error`.
- MP-3: Click triggers POST `/api/v1/poll/trigger`.
- MP-4: 202 response triggers health refresh + staging queue reload.
- MP-5: Spinner and "Polling…" label shown while request is in flight.
- MP-6: Error shows transient message, auto-clears after 4 seconds.
- MP-7: Staging queue not modified before response.

### Error handling (EH)
- EH-1: Health failures below threshold silently swallowed.
- EH-2: Three or more consecutive failures → `HEALTH_UNAVAILABLE` state.
- EH-3: Null/undefined date never passed to `new Date()` without guard.
- EH-4: String sentinels ("never", "error") never passed to `new Date()`.
