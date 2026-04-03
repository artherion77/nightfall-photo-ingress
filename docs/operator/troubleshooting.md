# Troubleshooting Guide

**Status:** active  
**Source:** extracted from `docs/operations-runbook.md` §Failure handling, §Staged File Recovery, §Troubleshooting P2 Failures, §Troubleshooting P3 Failures  
**See also:** [operational-playbook.md](operational-playbook.md), [cli-guide.md](cli-guide.md), [maintenance.md](maintenance.md)

---

## Failure Handling: Service Units

### Timer or Path Unit Not Active

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now nightfall-photo-ingress.timer
sudo systemctl enable --now nightfall-photo-ingress-trash.path
```

### Status File Missing After a Run

- Confirm `/run/nightfall-status.d` exists and is writable by the service.
- Run `nightfall-photo-ingress config-check --path /etc/nightfall/photo-ingress.conf` manually.
- Inspect journald output for serialization or permission failures.

### Trash Processing Does Not Trigger

- Confirm queue files land in the configured `trash_path` (inside the container: `/var/lib/ingress/trash`).
- Check `systemctl status nightfall-photo-ingress-trash.path`.
- Start the processor directly to separate path-watch failures from processor failures:
  ```bash
  systemctl start nightfall-photo-ingress-trash.service
  ```

---

## Staged File Recovery

If the poll service crashes or is killed mid-run, follow this procedure to return to a consistent state.

### When Recovery Is Needed

Signs that a partial poll run occurred:
- Status file shows `ingest_error` or is absent.
- Stale `.tmp` files present in the `staging_path` directory.
- Registry and journal are out of sync (pending rows without corresponding journal entries).

### Recovery Procedure

**Step 1: Stop the poll timer**

```bash
systemctl stop nightfall-photo-ingress.timer
```

**Step 2: Inspect the staging directory**

```bash
find /var/lib/ingress/staging -name "*.tmp" -ls
find /var/lib/ingress/staging -type f -ls
```

`.tmp` files are incomplete downloads and are safe to delete. Any non-`.tmp` file with a corresponding `pending` registry record was downloaded successfully but not finalized.

**Step 3: Run config-check to verify the service can start**

```bash
nightfall-photo-ingress config-check --path /etc/nightfall/photo-ingress.conf
```

**Step 4: Remove stale `.tmp` files**

```bash
find /var/lib/ingress/staging -name "*.tmp" -delete
```

**Step 5: Restart the timer**

```bash
systemctl start nightfall-photo-ingress.timer
```

The next triggered poll re-enumerates from the last committed cursor. Registry idempotency ensures already-pending files are not re-ingested.

> **Working state path note:** Inside the deployed LXC container, the working state directory is `/var/lib/ingress/`. The `conf/photo-ingress.conf.example` uses `/mnt/ssd/photo-ingress/` as a host-relative path example — that applies only to non-containerized deployments.

---

## Troubleshooting P2: Interactive Authentication (Device-Code Flow)

### Error: "Application with identifier '...' was not found in the directory"

Root cause: App registration misconfigured.

- [ ] Verify Application (client) ID matches config.
- [ ] Verify "Supported account types" is set to "Personal Microsoft accounts only".
- [ ] Verify API token version is set to 2 (Authentication → Advanced settings).

Fix: Update app registration, then rerun P2.

### Error: "Device-code flow did not return verification details"

Root cause: MSAL cannot communicate with the auth endpoint.

- [ ] Confirm container has network access: `curl https://login.microsoftonline.com >/dev/null`
- [ ] Confirm `client_id` is not a placeholder: `cat /etc/nightfall/photo-ingress.conf | grep client_id`

### Error: User cancels sign-in or consent

User action required: Run P2 again and complete the full sign-in and consent flow.

---

## Troubleshooting P3: Live Authenticated Poll

### Error: "No cached account found for 'staging'. Run auth-setup first."

Token cache is missing or not signed in. Run P2 again.

### Error: "Graph request returned error status"

OneDrive path is incorrect or user lacks permission.

- [ ] Confirm configured `onedrive_root` exists in user's OneDrive (e.g. `/Camera Roll` or `/Bilder/Eigene Aufnahmen`).
- [ ] Confirm user has read access to the folder.
- [ ] Confirm `Files.Read` permission is granted (App registration → API permissions in Azure portal).

### Error: Secret scan failed (credentials detected in logs)

Review log files in `/mnt/ssd/staging/photo-ingress/logs/<run-id>` for leaked tokens or client IDs. Do not commit sensitive data.

---

## Registry Corruption Recovery

If `state = registry_corrupt` in the status file:

1. Stop the service immediately:
   ```bash
   systemctl stop nightfall-photo-ingress.timer
   systemctl stop nightfall-photo-ingress.service
   ```
2. Run SQLite integrity check:
   ```bash
   sqlite3 /var/lib/ingress/registry.db "PRAGMA integrity_check;"
   ```
3. If integrity check fails, restore from last ZFS snapshot:
   ```bash
   zfs rollback ssdpool/photo-ingress@<snapshot-name>
   ```
4. Re-enable the timer after confirming registry integrity:
   ```bash
   systemctl start nightfall-photo-ingress.timer
   ```

---

*For routine operator workflows, see [operational-playbook.md](operational-playbook.md).*  
*For staging environment validation flows, see [maintenance.md](maintenance.md).*
