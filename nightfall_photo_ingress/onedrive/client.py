"""Microsoft Graph client and poll orchestration for Module 3.

Module 3 scope:
- delta pagination and candidate parsing
- per-account cursor persistence
- staging downloads with retry/backoff handling

Chunk 1 change:
- GraphError / DownloadError imported from errors.py (structured, redacted).
- All raise sites use redact_url() so pre-authenticated URLs never appear in
  logs or exception messages.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import re
import time
from time import monotonic
from typing import Callable, Iterable
from urllib.parse import quote

import httpx

from ..config import AccountConfig, AppConfig
from .auth import AuthError, OneDriveAuthClient
from .errors import DownloadError, GraphError, GraphResyncRequired, redact_url  # noqa: F401
from .retry import (  # noqa: F401
    DEFAULT_POLICY,
    RETRYABLE_STATUS_CODES,
    RetryPolicy,
    classify_status,
    compute_delay,
    parse_retry_after,
)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
DEFAULT_MAX_DELTA_PAGES = 1000


@dataclass(frozen=True)
class RemoteCandidate:
    """Normalized OneDrive file candidate emitted from delta responses."""

    account_name: str
    item_id: str
    name: str
    relative_path: str
    size_bytes: int
    modified_time: str
    download_url: str


@dataclass(frozen=True)
class AccountPollResult:
    """Result summary for one account poll cycle."""

    account_name: str
    downloaded_paths: tuple[Path, ...]
    candidate_count: int
    ghost_item_count: int
    ghost_reason_counts: tuple[tuple[str, int], ...]
    delta_anomaly_count: int
    delta_anomaly_reason_counts: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class _ReducerEntry:
    """Internal reducer slot representing the latest event for an item ID."""

    sequence: int
    candidate: RemoteCandidate | None


_SAFE_STAGING_BASENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")
_SAFE_EXTENSION_RE = re.compile(r"\.[A-Za-z0-9]{1,16}$")


def poll_accounts(
    app_config: AppConfig,
    account_name: str | None = None,
    auth_client: OneDriveAuthClient | None = None,
    http_client_factory: Callable[[], httpx.Client] | None = None,
    policy: RetryPolicy = DEFAULT_POLICY,
    sleeper: Callable[[float], None] = time.sleep,
    jitter_fn: Callable[[], float] | None = None,
) -> tuple[AccountPollResult, ...]:
    """Poll enabled accounts in configured deterministic order.

    Downloads all delta candidates into account-scoped staging folders.
    Ingest decisioning is intentionally deferred to Module 4.

    Args:
        policy:     Retry/backoff policy applied to all HTTP calls in this run.
        sleeper:    Callable used to pause between retries.  Replace with a
                    no-op in tests to avoid real sleeps.
        jitter_fn:  Optional jitter source.  Pass ``lambda: 0.0`` for fully
                    deterministic test runs.
    """

    selected = app_config.ordered_enabled_accounts()
    if account_name is not None:
        selected = tuple(acct for acct in selected if acct.name == account_name)
        if not selected:
            raise GraphError(
                f"Enabled account not found: {account_name}",
                code="account_not_found",
                operation="poll_accounts",
            )

    auth = auth_client or OneDriveAuthClient()
    results: list[AccountPollResult] = []

    for account in selected:
        token = auth.acquire_access_token(account)
        current_access_token = token.token

        def refresh_access_token() -> str:
            """Refresh token once when Graph returns 401/403."""

            nonlocal current_access_token
            refreshed = auth.acquire_access_token(account)
            current_access_token = refreshed.token
            return current_access_token

        with _build_client(http_client_factory) as client:
            (
                downloaded,
                candidate_count,
                ghost_reason_counts,
                delta_anomaly_counts,
            ) = poll_account_once(
                account=account,
                staging_root=app_config.core.staging_path,
                access_token=current_access_token,
                refresh_access_token=refresh_access_token,
                http_client=client,
                max_runtime_seconds=app_config.core.max_poll_runtime_seconds,
                policy=policy,
                sleeper=sleeper,
                jitter_fn=jitter_fn,
            )
        results.append(
            AccountPollResult(
                account_name=account.name,
                downloaded_paths=tuple(downloaded),
                candidate_count=candidate_count,
                ghost_item_count=sum(ghost_reason_counts.values()),
                ghost_reason_counts=tuple(sorted(ghost_reason_counts.items())),
                delta_anomaly_count=sum(delta_anomaly_counts.values()),
                delta_anomaly_reason_counts=tuple(
                    sorted(delta_anomaly_counts.items())
                ),
            )
        )

    return tuple(results)


def poll_account_once(
    account: AccountConfig,
    staging_root: Path,
    access_token: str,
    http_client: httpx.Client,
    refresh_access_token: Callable[[], str] | None = None,
    max_delta_pages: int = DEFAULT_MAX_DELTA_PAGES,
    max_runtime_seconds: int = 300,
    policy: RetryPolicy = DEFAULT_POLICY,
    sleeper: Callable[[float], None] = time.sleep,
    jitter_fn: Callable[[], float] | None = None,
) -> tuple[list[Path], int, dict[str, int], dict[str, int]]:
    """Poll one account and download candidates into staging."""

    cursor = _load_cursor(account.delta_cursor)
    delta_url = cursor or _build_initial_delta_url(account)

    reducer: dict[str, _ReducerEntry] = {}
    reducer_sequence = 0
    next_url: str | None = delta_url
    delta_link: str | None = None
    seen_next_links: set[str] = set()
    seen_item_ids: set[str] = set()
    delta_anomaly_counts: dict[str, int] = {}
    page_count = 0
    start_monotonic = monotonic()

    while next_url:
        if monotonic() - start_monotonic > max_runtime_seconds:
            _record_ghost_reason(delta_anomaly_counts, "delta_runtime_limit_exceeded")
            raise GraphError(
                f"Delta polling exceeded runtime limit for account '{account.name}'",
                code="delta_runtime_limit_exceeded",
                account=account.name,
                operation="poll_account_once",
            )

        if page_count >= max_delta_pages:
            _record_ghost_reason(delta_anomaly_counts, "delta_page_limit_exceeded")
            raise GraphError(
                f"Delta polling exceeded max pages for account '{account.name}'",
                code="delta_page_limit_exceeded",
                account=account.name,
                operation="poll_account_once",
            )

        if next_url in seen_next_links:
            _record_ghost_reason(delta_anomaly_counts, "delta_nextlink_cycle_detected")
            raise GraphError(
                f"Delta nextLink cycle detected for account '{account.name}'",
                code="delta_nextlink_cycle_detected",
                account=account.name,
                operation="poll_account_once",
            )
        seen_next_links.add(next_url)

        try:
            payload = _graph_get_json(
                http_client,
                next_url,
                access_token,
                refresh_access_token=refresh_access_token,
                policy=policy,
                sleeper=sleeper,
                jitter_fn=jitter_fn,
            )
        except GraphResyncRequired as exc:
            _record_ghost_reason(delta_anomaly_counts, "delta_resync_required_410")
            _mark_resync_required(
                cursor_path=account.delta_cursor,
                account_name=account.name,
                reason="delta_resync_required_410",
                resync_url=exc.resync_url,
            )
            return [], 0, {}, delta_anomaly_counts

        page_count += 1
        replay_count = _count_replayed_item_ids(payload, seen_item_ids)
        if replay_count > 0:
            _record_ghost_reason(
                delta_anomaly_counts,
                "delta_replayed_item_id",
                count=replay_count,
            )
        reducer_sequence = _apply_delta_page_to_reducer(
            account_name=account.name,
            payload=payload,
            reducer=reducer,
            start_sequence=reducer_sequence,
            anomaly_counts=delta_anomaly_counts,
        )
        next_url = _as_str(payload.get("@odata.nextLink"))
        delta_link = _as_str(payload.get("@odata.deltaLink")) or delta_link

    if delta_link is None:
        raise GraphError(
            f"No delta link returned for account '{account.name}'",
            code="missing_delta_link",
            account=account.name,
            operation="poll_account_once",
        )

    candidates = _materialize_reduced_candidates(reducer)
    downloaded_paths, ghost_reason_counts = download_candidates(
        candidates=candidates,
        staging_root=staging_root,
        account_name=account.name,
        access_token=access_token,
        http_client=http_client,
        max_downloads=account.max_downloads,
                refresh_access_token=refresh_access_token,
        policy=policy,
        sleeper=sleeper,
        jitter_fn=jitter_fn,
    )

    _save_cursor(account.delta_cursor, delta_link)
    _clear_resync_marker(account.delta_cursor)
    return downloaded_paths, len(candidates), ghost_reason_counts, delta_anomaly_counts


def _apply_delta_page_to_reducer(
    account_name: str,
    payload: dict[str, object],
    reducer: dict[str, _ReducerEntry],
    start_sequence: int,
    anomaly_counts: dict[str, int],
) -> int:
    """Apply one delta page to an in-run reducer keyed by item ID.

    Rules:
    - Only file entries with a download URL become candidates.
    - Deletion events set a tombstone (candidate None).
    - Repeated events for the same item ID overwrite previous state.
    - Last observed event wins, with deletion precedence when last event is a
      tombstone.
    """

    raw_items = payload.get("value")
    if not isinstance(raw_items, list):
        return start_sequence

    sequence = start_sequence
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue

        item_id = _as_str(raw.get("id"))
        if not item_id:
            _record_ghost_reason(anomaly_counts, "delta_item_missing_id")
            continue

        sequence += 1
        had_previous = item_id in reducer
        if had_previous:
            _record_ghost_reason(anomaly_counts, "delta_reducer_event_overwrite")

        if "deleted" in raw:
            reducer[item_id] = _ReducerEntry(sequence=sequence, candidate=None)
            _record_ghost_reason(anomaly_counts, "delta_reducer_tombstone_event")
            continue

        if "file" not in raw:
            # Non-file entities are ignored by ingestion candidate logic.
            continue

        validated = _build_candidate_from_payload(account_name, raw)
        if validated is None:
            reason = _classify_invalid_candidate_reason(raw)
            _record_ghost_reason(anomaly_counts, reason)
            continue

        reducer[item_id] = _ReducerEntry(sequence=sequence, candidate=validated)

    return sequence


def _materialize_reduced_candidates(
    reducer: dict[str, _ReducerEntry],
) -> list[RemoteCandidate]:
    """Return deterministic candidates from reducer state.

    Candidates are emitted in ascending last-event sequence order so repeated
    events produce a stable and auditable final list.
    """

    ordered = sorted(reducer.values(), key=lambda entry: entry.sequence)
    return [entry.candidate for entry in ordered if entry.candidate is not None]


def parse_delta_items(
    account_name: str, payload: dict[str, object]
) -> tuple[RemoteCandidate, ...]:
    """Extract normalized candidates from a Graph delta page payload."""

    raw_items = payload.get("value")
    if not isinstance(raw_items, list):
        return tuple()

    parsed: list[RemoteCandidate] = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue

        if "deleted" in raw:
            continue

        if "file" not in raw:
            continue

        validated = _build_candidate_from_payload(account_name, raw)
        if validated is None:
            continue
        parsed.append(validated)

    return tuple(parsed)


def download_candidates(
    candidates: Iterable[RemoteCandidate],
    staging_root: Path,
    account_name: str,
    access_token: str,
    http_client: httpx.Client,
    refresh_access_token: Callable[[], str] | None = None,
    max_downloads: int | None = None,
    policy: RetryPolicy = DEFAULT_POLICY,
    sleeper: Callable[[float], None] = time.sleep,
    jitter_fn: Callable[[], float] | None = None,
) -> tuple[list[Path], dict[str, int]]:
    """Download candidates into account-scoped staging folder."""

    target_root = staging_root / account_name
    target_root.mkdir(parents=True, exist_ok=True)

    downloaded: list[Path] = []
    ghost_reason_counts: dict[str, int] = {}
    limit = max_downloads if max_downloads is not None else 0

    for index, candidate in enumerate(candidates):
        if limit > 0 and index >= limit:
            break

        safe_base = _safe_staging_basename(candidate.item_id)
        suffix = _safe_extension(candidate.name)
        tmp_path = target_root / f"{safe_base}.tmp"
        final_path = target_root / f"{safe_base}{suffix}"
        try:
            download_with_retry(
                http_client=http_client,
                url=candidate.download_url,
                destination=tmp_path,
                expected_size=candidate.size_bytes,
                policy=policy,
                sleeper=sleeper,
                jitter_fn=jitter_fn,
            )
        except DownloadError as first_error:
            if not _is_download_url_unreachable(first_error):
                raise

            refreshed_url, ghost_reason = _resolve_download_url_once(
                item_id=candidate.item_id,
                access_token=access_token,
                refresh_access_token=refresh_access_token,
                http_client=http_client,
                policy=policy,
                sleeper=sleeper,
                jitter_fn=jitter_fn,
            )

            if refreshed_url is None:
                _record_ghost_reason(ghost_reason_counts, ghost_reason)
                continue

            try:
                download_with_retry(
                    http_client=http_client,
                    url=refreshed_url,
                    destination=tmp_path,
                    expected_size=candidate.size_bytes,
                    policy=policy,
                    sleeper=sleeper,
                    jitter_fn=jitter_fn,
                )
            except DownloadError as refreshed_error:
                if _is_download_url_unreachable(refreshed_error):
                    _record_ghost_reason(
                        ghost_reason_counts,
                        "ghost_download_unreachable_after_refresh",
                    )
                    continue
                raise

        tmp_path.replace(final_path)
        downloaded.append(final_path)

    return downloaded, ghost_reason_counts


def _record_ghost_reason(reason_counts: dict[str, int], reason: str, count: int = 1) -> None:
    """Increment a reason counter by count."""

    reason_counts[reason] = reason_counts.get(reason, 0) + count


def _count_replayed_item_ids(payload: dict[str, object], seen_item_ids: set[str]) -> int:
    """Count repeated item IDs across delta pages.

    This is a lightweight stale/replay anomaly detector and does not alter the
    candidate set. Deduplication semantics are handled in later hardening chunks.
    """

    raw_items = payload.get("value")
    if not isinstance(raw_items, list):
        return 0

    replay_count = 0
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        item_id = _as_str(raw.get("id"))
        if not item_id:
            continue
        if item_id in seen_item_ids:
            replay_count += 1
        else:
            seen_item_ids.add(item_id)
    return replay_count


def _resync_marker_path(cursor_path: Path) -> Path:
    """Return the resync marker path derived from a cursor path."""

    if cursor_path.suffix:
        return cursor_path.with_suffix(cursor_path.suffix + ".resync.json")
    return Path(str(cursor_path) + ".resync.json")


def _mark_resync_required(
    cursor_path: Path,
    account_name: str,
    reason: str,
    resync_url: str | None,
) -> None:
    """Persist a marker indicating this account requires a delta resync."""

    marker_path = _resync_marker_path(cursor_path)
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "account": account_name,
        "required_at": datetime.utcnow().isoformat() + "Z",
        "reason": reason,
        "resync_url": resync_url,
    }
    tmp_path = marker_path.with_suffix(marker_path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    tmp_path.replace(marker_path)


def _clear_resync_marker(cursor_path: Path) -> None:
    """Delete any stale resync marker after successful cursor persistence."""

    _resync_marker_path(cursor_path).unlink(missing_ok=True)


def _is_download_url_unreachable(error: DownloadError) -> bool:
    """Return True when a download URL appears stale or inaccessible."""

    return error.status_code in {401, 403, 404}


def _resolve_download_url_once(
    item_id: str,
    access_token: str,
    refresh_access_token: Callable[[], str] | None,
    http_client: httpx.Client,
    policy: RetryPolicy,
    sleeper: Callable[[float], None],
    jitter_fn: Callable[[], float] | None,
) -> tuple[str | None, str]:
    """Refresh a single item's metadata once to retrieve a fresh download URL.

    Returns:
        (new_url, reason_code)
            - new_url is non-None when refresh succeeded.
            - reason_code is always set and can be emitted as an actionable
              ghost-item counter key.
    """

    escaped_id = quote(item_id, safe="")
    metadata_url = f"{GRAPH_BASE}/me/drive/items/{escaped_id}"
    try:
        payload = _graph_get_json(
            http_client,
            metadata_url,
            access_token,
            refresh_access_token=refresh_access_token,
            policy=policy,
            sleeper=sleeper,
            jitter_fn=jitter_fn,
        )
    except GraphError as exc:
        if exc.status_code == 404:
            return None, "ghost_item_not_found_on_refresh"
        raise

    refreshed = _as_str(payload.get("@microsoft.graph.downloadUrl"))
    if not refreshed:
        return None, "ghost_missing_download_url_after_refresh"
    return refreshed, "download_url_refreshed"


def download_with_retry(
    http_client: httpx.Client,
    url: str,
    destination: Path,
    expected_size: int | None = None,
    policy: RetryPolicy = DEFAULT_POLICY,
    sleeper: Callable[[float], None] = time.sleep,
    jitter_fn: Callable[[], float] | None = None,
) -> None:
    """Download a file with bounded retries for transient statuses and transport errors.

    Retry coverage:
    - HTTP 429/500/502/503/504: transient server-side failures.
    - ``httpx.RequestError``: connection resets, DNS failures, transport errors.

    Back-off (priority order):
    1. ``Retry-After`` header value parsed via :func:`parse_retry_after`
       (supports numeric seconds and RFC 7231 HTTP-date).
    2. Capped exponential back-off with optional jitter when no server hint.

    Args:
        policy:     Retry/backoff configuration.
        sleeper:    Delay function; replace with a no-op in tests.
        jitter_fn:  Jitter source; defaults to ``random.uniform(0, 1)``.
                    Pass ``lambda: 0.0`` for deterministic test behaviour.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)

    def _cleanup_partial() -> None:
        """Remove partial download artifacts after failed attempts."""

        try:
            destination.unlink(missing_ok=True)
        except OSError:
            # Best effort cleanup: preserve primary download error context.
            pass

    for attempt in range(1, policy.max_attempts + 1):
        try:
            response = http_client.get(url, timeout=120.0)
        except httpx.RequestError as exc:
            # Transport-level failure: connection reset, DNS error, timeout, etc.
            _cleanup_partial()
            if attempt >= policy.max_attempts:
                raise DownloadError(
                    "Download transport error after retries exhausted",
                    url=url,
                    code="download_transport_error",
                    safe_hint=(
                        f"Transport failure ({type(exc).__name__}) for "
                        f"{redact_url(url)} after {policy.max_attempts} attempts"
                    ),
                ) from exc
            delay = compute_delay(attempt, None, policy, jitter_fn)
            sleeper(delay)
            continue

        if classify_status(response.status_code):
            _cleanup_partial()
            if attempt >= policy.max_attempts:
                raise DownloadError(
                    "Download retry limit reached",
                    url=url,
                    code="download_retry_exhausted",
                    status_code=response.status_code,
                    safe_hint=(
                        f"Retry limit ({policy.max_attempts}) exceeded for "
                        f"{redact_url(url)}"
                    ),
                )
            retry_after = parse_retry_after(response.headers.get("Retry-After"))
            delay = compute_delay(attempt, retry_after, policy, jitter_fn)
            sleeper(delay)
            continue

        if response.status_code >= 400:
            _cleanup_partial()
            raise DownloadError(
                "Download request returned error status",
                url=url,
                status_code=response.status_code,
                safe_hint=f"HTTP {response.status_code} for {redact_url(url)}",
            )

        bytes_written = 0
        try:
            with destination.open("wb") as handle:
                for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    handle.write(chunk)
                    bytes_written += len(chunk)
        except OSError as exc:
            _cleanup_partial()
            raise DownloadError(
                "Failed to write downloaded content to staging",
                url=url,
                code="download_write_error",
                safe_hint=f"Write failure while saving {redact_url(url)}",
            ) from exc

        if expected_size is not None:
            if expected_size > 0 and bytes_written == 0:
                _cleanup_partial()
                if attempt >= policy.max_attempts:
                    raise DownloadError(
                        "Download returned empty body for non-empty remote file",
                        url=url,
                        code="download_empty_body",
                        safe_hint=(
                            f"Expected {expected_size} bytes but received 0 for "
                            f"{redact_url(url)}"
                        ),
                    )
                delay = compute_delay(attempt, None, policy, jitter_fn)
                sleeper(delay)
                continue

            if expected_size >= 0 and bytes_written != expected_size:
                _cleanup_partial()
                if attempt >= policy.max_attempts:
                    raise DownloadError(
                        "Downloaded byte count did not match expected size",
                        url=url,
                        code="download_size_mismatch",
                        safe_hint=(
                            f"Expected {expected_size} bytes, got {bytes_written} for "
                            f"{redact_url(url)}"
                        ),
                    )
                delay = compute_delay(attempt, None, policy, jitter_fn)
                sleeper(delay)
                continue

        return


def _graph_get_json(
    http_client: httpx.Client,
    url: str,
    access_token: str,
    policy: RetryPolicy = DEFAULT_POLICY,
    sleeper: Callable[[float], None] = time.sleep,
    jitter_fn: Callable[[], float] | None = None,
    refresh_access_token: Callable[[], str] | None = None,
) -> dict[str, object]:
    """Execute a Graph GET request and return parsed JSON payload.

    Applies the same retry/backoff policy as :func:`download_with_retry`:
    - HTTP 429/500/502/503/504 are retried with Retry-After / exponential back-off.
    - Transport errors (``httpx.RequestError``) are retried up to
      ``policy.max_attempts``.
    """
    refreshed_once = False
    for attempt in range(1, policy.max_attempts + 1):
        try:
            response = http_client.get(
                url,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=30.0,
            )
        except httpx.RequestError as exc:
            if attempt >= policy.max_attempts:
                raise GraphError(
                    "Graph transport error after retries exhausted",
                    url=url,
                    code="graph_transport_error",
                    safe_hint=(
                        f"Transport failure ({type(exc).__name__}) for "
                        f"{redact_url(url)} after {policy.max_attempts} attempts"
                    ),
                ) from exc
            delay = compute_delay(attempt, None, policy, jitter_fn)
            sleeper(delay)
            continue

        if response.status_code in {401, 403}:
            if refreshed_once or refresh_access_token is None:
                raise GraphError(
                    "Graph authentication failed",
                    url=url,
                    code="graph_auth_failed",
                    status_code=response.status_code,
                    safe_hint=(
                        f"HTTP {response.status_code} for {redact_url(url)} "
                        "after refresh attempt"
                    ),
                )
            try:
                access_token = refresh_access_token()
            except AuthError as exc:
                raise GraphError(
                    "Graph token refresh failed",
                    url=url,
                    code="graph_auth_refresh_failed",
                    status_code=response.status_code,
                    safe_hint=f"Token refresh failed for {redact_url(url)}",
                ) from exc
            refreshed_once = True
            continue

        if classify_status(response.status_code):
            if attempt >= policy.max_attempts:
                raise GraphError(
                    "Graph request retry limit reached",
                    url=url,
                    code="graph_retry_exhausted",
                    status_code=response.status_code,
                    safe_hint=(
                        f"HTTP {response.status_code} after {policy.max_attempts} "
                        f"retries for {redact_url(url)}"
                    ),
                )
            retry_after = parse_retry_after(response.headers.get("Retry-After"))
            delay = compute_delay(attempt, retry_after, policy, jitter_fn)
            sleeper(delay)
            continue

        if response.status_code == 410:
            raise GraphResyncRequired(
                "Graph delta cursor is no longer valid and requires resync",
                url=url,
                status_code=response.status_code,
                resync_url=response.headers.get("Location"),
                safe_hint=f"HTTP 410 for {redact_url(url)}",
            )

        if response.status_code >= 400:
            raise GraphError(
                "Graph request returned error status",
                url=url,
                status_code=response.status_code,
                safe_hint=f"HTTP {response.status_code} for {redact_url(url)}",
            )

        try:
            return json.loads(response.text)
        except json.JSONDecodeError as exc:
            raise GraphError(
                "Invalid JSON in Graph response",
                url=url,
                code="graph_invalid_json",
                safe_hint=f"JSON parse error for {redact_url(url)}",
            ) from exc

    # Unreachable: loop always returns or raises on the final attempt.
    raise GraphError(  # pragma: no cover
        "Unexpected retry loop exit",
        url=url,
        code="graph_retry_loop_exit",
    )


def _build_initial_delta_url(account: AccountConfig) -> str:
    """Construct the initial folder delta URL for an account."""

    root = account.onedrive_root.strip()
    if not root.startswith("/"):
        root = "/" + root

    # Encode each path segment explicitly to avoid Graph path addressing bugs
    # with spaces or reserved characters in user-provided roots.
    segments = [quote(segment, safe="") for segment in root.split("/") if segment]
    encoded_root = "/" + "/".join(segments)

    return f"{GRAPH_BASE}/me/drive/root:{encoded_root}:/delta"


def _load_cursor(path: Path) -> str | None:
    """Read a saved delta cursor if present."""

    if not path.exists():
        return None

    cursor = path.read_text(encoding="utf-8").strip()
    return cursor or None


def _save_cursor(path: Path, cursor: str) -> None:
    """Persist latest delta cursor atomically."""

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(cursor, encoding="utf-8")
    tmp_path.replace(path)


def _extract_relative_path(raw: dict[str, object]) -> str:
    """Extract parent path from Graph payload in a safe way."""

    parent_ref = raw.get("parentReference")
    if not isinstance(parent_ref, dict):
        return ""

    raw_path = _as_str(parent_ref.get("path")) or ""
    marker = "/root:"
    if marker not in raw_path:
        return raw_path

    return raw_path.split(marker, maxsplit=1)[1].strip("/")


def _build_client(factory: Callable[[], httpx.Client] | None) -> httpx.Client:
    """Build an HTTP client from optional factory."""

    if factory:
        return factory()
    return httpx.Client()


def _as_str(value: object) -> str | None:
    """Convert optional scalar to string when possible."""

    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _safe_staging_basename(item_id: str) -> str:
    """Return a filesystem-safe staging basename derived from item ID."""

    sanitized = _SAFE_STAGING_BASENAME_RE.sub("_", item_id).strip("._-")
    if not sanitized:
        return "item"
    return sanitized[:120]


def _safe_extension(name: str) -> str:
    """Return a safe file extension for staging artifacts."""

    suffix = Path(name).suffix
    if not suffix:
        return ".bin"
    if not _SAFE_EXTENSION_RE.fullmatch(suffix):
        return ".bin"
    return suffix.lower()


def _build_candidate_from_payload(
    account_name: str,
    raw: dict[str, object],
) -> RemoteCandidate | None:
    """Build a validated candidate from raw Graph payload.

    Returns None when required fields are missing or malformed.
    """

    item_id = _as_str(raw.get("id"))
    if not item_id:
        return None

    name = _as_str(raw.get("name"))
    if not name:
        return None

    download_url = _as_str(raw.get("@microsoft.graph.downloadUrl"))
    if not download_url:
        return None

    size_raw = raw.get("size", 0)
    try:
        size_bytes = int(size_raw)
    except (TypeError, ValueError):
        return None
    if size_bytes < 0:
        return None

    return RemoteCandidate(
        account_name=account_name,
        item_id=item_id,
        name=name,
        relative_path=_extract_relative_path(raw),
        size_bytes=size_bytes,
        modified_time=_as_str(raw.get("lastModifiedDateTime"))
        or datetime.utcnow().isoformat(),
        download_url=download_url,
    )


def _classify_invalid_candidate_reason(raw: dict[str, object]) -> str:
    """Classify invalid candidate payload reason for anomaly counters."""

    item_id = _as_str(raw.get("id"))
    if not item_id:
        return "delta_item_missing_id"

    name = _as_str(raw.get("name"))
    if not name:
        return "delta_file_missing_name"

    download_url = _as_str(raw.get("@microsoft.graph.downloadUrl"))
    if not download_url:
        return "delta_file_missing_download_url"

    size_raw = raw.get("size", 0)
    try:
        size_value = int(size_raw)
    except (TypeError, ValueError):
        return "delta_file_invalid_size"
    if size_value < 0:
        return "delta_file_invalid_size"

    return "delta_file_invalid_payload"
