# Staging Permission Review Open Point

## Current accepted compromise

For now, host-side staging directories are intentionally permissive so non-root workflows work reliably with isolated LXD idmap:

- /mnt/ssd/staging/photo-ingress/evidence: mode 0777
- /mnt/ssd/staging/photo-ingress/logs: mode 0777
- Staging profile uses isolated idmap (base 100000, size 65536)

This was accepted temporarily to unblock:

- stagingctl lifecycle execution without root for normal operations
- staging test suite execution without host-side sudo for evidence/log access

## Open security point

The 0777 mode is broader than desired and should be tightened.

Target state:

- Restrict evidence/log directories to least privilege (prefer 0700 or 0750 equivalent)
- Preserve non-root operator/test usability
- Preserve container write/read behavior for bind mounts

## Follow-up options

1. Preferred: map container root to host chris via raw.idmap in staging profile, then switch evidence/logs to 0700 chris:chris.
2. Alternative: keep isolated idmap and apply ACLs for mapped host UID/GID used by container root, then set directory mode to 0750.

## Exit criteria

- Non-root `stagingctl create/install/smoke/reset/uninstall` succeeds
- Staging tests run without sudo
- Evidence/log paths are no longer world-writable
- Behavior documented in staging README and profile notes
