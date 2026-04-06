# Config Path Rework Open Point

## Problem Statement

The current configuration model requires operators to spell out every individual path
explicitly. This creates several issues:

1. **Cognitive overhead** — an operator must manually construct 8–10 paths that all
   share a common root, with no relationship between them enforced by the config schema.
2. **Error-prone setup** — it is easy to scatter app-data paths across unrelated
   locations by accident, breaking assumptions (e.g. `staging_on_same_pool`).
3. **Per-account boilerplate** — `token_cache` and `delta_cursor` are required per
   account but are entirely predictable from the account name and the app-data root.
   Operators must write them out in full even though there is no realistic reason to
   deviate from the derived default.

---

## Proposed Design

Replace the current flat list of explicit paths with two base path keys and
automatically derived defaults for all subordinate paths.

### Two base paths

| Key (proposed) | Purpose |
|---|---|
| `app_data_path` | Root for all mutable app-internal state: staging scratch space, registry / SQLite DB, token caches, delta cursor files, log files. Should live on fast storage (e.g. SSD). |
| `media_root` | Root for all image-file output queues: `pending`, `accepted`, `rejected`, `trash`. Should live on the media pool. |

> The name `app_data_path` is a candidate; alternatives worth evaluating:
> `data_dir`, `state_dir`, `var_path`, `service_root`. The name should be
> unambiguous to a first-time operator and consistent with similar systemd-style
> conventions (see `StateDirectory=`).

### Derived subordinate paths (default values)

All of the following should be **derived automatically** by `config.py` when not
overridden. The config file should show them as commented-out examples only.

#### From `app_data_path`

| Current key | Derived default |
|---|---|
| `staging_path` | `{app_data_path}/staging` |
| `registry_path` | `{app_data_path}/registry.db` |
| *(implicit)* logs | `{app_data_path}/logs/` |
| *(implicit)* token cache dir | `{app_data_path}/tokens/` |
| *(implicit)* delta cursor dir | `{app_data_path}/cursors/` |

#### From `media_root`

| Current key | Derived default |
|---|---|
| `pending_path` | `{media_root}/pending` |
| `accepted_path` | `{media_root}/accepted` |
| `rejected_path` | `{media_root}/rejected` |
| `trash_path` | `{media_root}/trash` |

#### Per-account keys (currently required, should become optional/derived)

| Current key | Derived default |
|---|---|
| `token_cache` | `{app_data_path}/tokens/{account_name}.json` |
| `delta_cursor` | `{app_data_path}/cursors/{account_name}.cursor` |

These are entirely predictable from the account section name and should only appear in
the config when an operator genuinely wants to deviate from the convention.

---

## Impact Assessment

### config.py

- `_parse_core()` must resolve derived paths after reading the two base keys.
- `_parse_accounts()` must derive `token_cache` and `delta_cursor` when absent rather
  than treating them as required.
- Validation must check that base paths are set; subordinate path validation remains.

### conf/photo-ingress.conf.example

- Replace the current flat list with the two base path keys (uncommented, required).
- All subordinate paths moved to commented-out override examples.

### design/cli-config-specification.md

- §2 Required Keys table shrinks: most current path keys become optional with derived
  defaults.
- §3 account keys: `token_cache` and `delta_cursor` become optional.
- New §X documenting the two base paths and the derivation rules.

### install / docs

- `install.sh` and operational documentation should reference the two base paths when
  creating directories.

---

## Open Questions

1. **Naming** — settle on `app_data_path` vs an alternative before implementation.
2. **Override granularity** — should overriding any subordinate path still be
   supported? (Yes, for non-standard deployments — but it should be explicit and
   clearly marked "advanced".)
3. **`staging_on_same_pool`** — with explicit base paths this flag becomes derivable if
   `app_data_path` and `media_root` are on the same ZFS pool; consider auto-detection
   or removal.
4. **Migration** — existing deployments have explicit path keys. A backward-compatible
   migration path (continue to accept explicit overrides) is required; do not break
   existing configs silently.
5. **Config version** — this change likely warrants bumping `config_version` to `3`.

---

## Status

Open — not assigned, not scheduled.

Raised: 2026-04-03

Tracking issue: #4 (`Follow-up: implement config path base-key derivation rework`)
- https://github.com/artherion77/nightfall-photo-ingress/issues/4
