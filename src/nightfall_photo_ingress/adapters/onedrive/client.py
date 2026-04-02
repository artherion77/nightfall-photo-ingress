"""Microsoft Graph client and poll orchestration for the OneDrive client.

OneDrive client scope:
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
from datetime import datetime, timezone
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
import hashlib
import json
import logging
from pathlib import Path
import re
import time
from time import monotonic
from typing import Callable, Iterable
from urllib.parse import quote
from uuid import uuid4

import httpx

from nightfall_photo_ingress.config import AccountConfig, AppConfig
from nightfall_photo_ingress.runtime.process_lock import global_process_lock
from .auth import AuthError, OneDriveAuthClient
from .cache_lock import SingletonLockBusyError, account_singleton_lock
from .errors import DownloadError, GraphError, GraphResyncRequired, redact_url  # noqa: F401
from .retry import (  # noqa: F401
    DEFAULT_POLICY,
    RETRYABLE_STATUS_CODES,
    RetryPolicy,
    classify_status,
    compute_delay,
    parse_retry_after,
)
from .safe_logging import sanitize_extra

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
DEFAULT_MAX_DELTA_PAGES = 1000
LOGGER = logging.getLogger(__name__)
_EXPORTED_DIAGNOSTIC_KEYS = {
    "retry_attempt_total",
    "retry_transport_error_total",
    "throttle_response_total",
    "resync_required_total",
    "auth_refresh_attempt_total",
    "auth_refresh_success_total",
    "auth_refresh_failure_total",
    "graph_response_request_id_seen_total",
    "graph_response_correlation_id_seen_total",
}
_GERMAN_FOLDER_NAMES = frozenset({"bilder", "eigene aufnahmen"})
_ENGLISH_FOLDER_NAMES = frozenset({"camera roll", "pictures", "photos"})
_DISCOVERY_CANDIDATE_PATHS = (
    "/Camera Roll",
    "/Pictures",
    "/Photos",
    "/Bilder/Eigene Aufnahmen",
    "/Bilder",
)
_SPECIAL_CAMERA_ROLL_ALIAS = "cameraroll"
_MEDIA_EXTENSIONS = frozenset(
    {
        ".jpg",
        ".jpeg",
        ".png",
        ".heic",
        ".heif",
        ".dng",
        ".arw",
        ".cr2",
        ".cr3",
        ".nef",
        ".mov",
        ".mp4",
    }
)


def _trace_event(event: str, **fields: object) -> None:
    """Emit a structured trace event for OneDrive network operations."""

    payload = {"event": event}
    payload.update(fields)
    LOGGER.info("onedrive_trace", extra=sanitize_extra(payload))


@dataclass(frozen=True)
class RemoteCandidate:
    """Normalized OneDrive file candidate emitted from delta responses."""

    account_name: str
    item_id: str
    name: str
    relative_path: str
    size_bytes: int | None
    raw_modified_time: str | None
    normalized_modified_time: str
    download_url: str

    @property
    def modified_time(self) -> str:
        """Backward-compatible alias for normalized modified timestamp."""

        return self.normalized_modified_time


@dataclass(frozen=True)
class AccountPollPayload:
    """Payload section of poll result used by downstream ingestion."""

    downloaded_paths: tuple[Path, ...]
    handoff_manifest_path: Path | None
    candidate_count: int


@dataclass(frozen=True)
class DownloadedHandoffCandidate:
    """Production-owned handoff artifact from poll/download to ingest."""

    account_name: str
    onedrive_id: str
    original_filename: str
    relative_path: str
    modified_time: str
    size_bytes: int | None
    staging_path: Path


@dataclass(frozen=True)
class AccountPollAnomalies:
    """Anomaly section of poll result."""

    ghost_item_count: int
    ghost_reason_counts: tuple[tuple[str, int], ...]
    delta_anomaly_count: int
    delta_anomaly_reason_counts: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class AccountPollDiagnostics:
    """Diagnostics section of poll result."""

    counters: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class AccountPollLifecycleState:
    """Lifecycle state section for poll result."""

    state: str
    drift_ratio: float
    drift_events: int


@dataclass(frozen=True)
class AccountPollResult:
    """Result summary for one account poll cycle."""

    account_name: str
    payload: AccountPollPayload
    anomalies: AccountPollAnomalies
    diagnostics: AccountPollDiagnostics
    lifecycle_state: AccountPollLifecycleState

    @property
    def downloaded_paths(self) -> tuple[Path, ...]:
        """Backward-compatible alias for payload.downloaded_paths."""

        return self.payload.downloaded_paths

    @property
    def candidate_count(self) -> int:
        """Backward-compatible alias for payload.candidate_count."""

        return self.payload.candidate_count

    @property
    def ghost_item_count(self) -> int:
        """Backward-compatible alias for anomalies.ghost_item_count."""

        return self.anomalies.ghost_item_count

    @property
    def ghost_reason_counts(self) -> tuple[tuple[str, int], ...]:
        """Backward-compatible alias for anomalies.ghost_reason_counts."""

        return self.anomalies.ghost_reason_counts

    @property
    def delta_anomaly_count(self) -> int:
        """Backward-compatible alias for anomalies.delta_anomaly_count."""

        return self.anomalies.delta_anomaly_count

    @property
    def delta_anomaly_reason_counts(self) -> tuple[tuple[str, int], ...]:
        """Backward-compatible alias for anomalies.delta_anomaly_reason_counts."""

        return self.anomalies.delta_anomaly_reason_counts


@dataclass(frozen=True)
class _ReducerEntry:
    """Internal reducer slot representing the latest event for an item ID."""

    sequence: int
    candidate: RemoteCandidate | None


@dataclass(frozen=True)
class PathDiscoveryCandidate:
    """One discovered candidate path and its media file count."""

    path: str
    media_count: int


@dataclass(frozen=True)
class CameraRollPathResolution:
    """Resolution result for onboarding path validation/discovery."""

    configured_path: str
    configured_exists: bool
    configured_media_count: int
    suggested_path: str | None
    suggested_media_count: int
    suggested_candidates: tuple[PathDiscoveryCandidate, ...]
    reason: str | None

    @property
    def effective_path(self) -> str:
        """Return runtime effective path for this onboarding session."""

        return self.suggested_path or self.configured_path


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
    process_lock_path: Path | None = None,
) -> tuple[AccountPollResult, ...]:
    """Poll enabled accounts in configured deterministic order.

    Downloads all delta candidates into account-scoped staging folders.
    Ingest decisioning is intentionally deferred to the ingest pipeline.

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

    lock_path = process_lock_path or app_config.core.registry_path.with_suffix(".poll.lock")

    with global_process_lock(lock_path):
        auth = auth_client or OneDriveAuthClient()
        results_by_index: dict[int, AccountPollResult] = {}
        deadline = monotonic() + app_config.core.max_poll_runtime_seconds

        poll_run_id = str(uuid4())
        _trace_event(
            "poll_accounts_start",
            poll_run_id=poll_run_id,
            account_count=len(selected),
        )

        worker_count = max(1, min(app_config.core.account_worker_count, len(selected)))

        if worker_count == 1:
            for index, account in enumerate(selected):
                results_by_index[index] = _poll_single_account(
                    account=account,
                    app_config=app_config,
                    auth=auth,
                    http_client_factory=http_client_factory,
                    poll_run_id=poll_run_id,
                    deadline=deadline,
                    policy=policy,
                    sleeper=sleeper,
                    jitter_fn=jitter_fn,
                )
        else:
            futures: dict[Future[AccountPollResult], int] = {}
            with ThreadPoolExecutor(max_workers=worker_count) as pool:
                for index, account in enumerate(selected):
                    remaining = deadline - monotonic()
                    if remaining <= 0:
                        results_by_index[index] = _runtime_budget_exhausted_result(account.name)
                        continue
                    future = pool.submit(
                        _poll_single_account,
                        account,
                        app_config,
                        auth,
                        http_client_factory,
                        poll_run_id,
                        deadline,
                        policy,
                        sleeper,
                        jitter_fn,
                    )
                    futures[future] = index

                for future in as_completed(futures):
                    index = futures[future]
                    results_by_index[index] = future.result()

        results = tuple(results_by_index[idx] for idx in sorted(results_by_index))

        _trace_event(
            "poll_accounts_end",
            poll_run_id=poll_run_id,
            result_count=len(results),
        )

        return results


def _runtime_budget_exhausted_result(account_name: str) -> AccountPollResult:
    """Return a deterministic result when poll runtime budget is exhausted."""

    anomaly_counts = {"scheduler_runtime_budget_exhausted": 1}
    return AccountPollResult(
        account_name=account_name,
        payload=AccountPollPayload(
            downloaded_paths=tuple(),
            handoff_manifest_path=None,
            candidate_count=0,
        ),
        anomalies=AccountPollAnomalies(
            ghost_item_count=0,
            ghost_reason_counts=tuple(),
            delta_anomaly_count=1,
            delta_anomaly_reason_counts=tuple(sorted(anomaly_counts.items())),
        ),
        diagnostics=AccountPollDiagnostics(counters=tuple()),
        lifecycle_state=AccountPollLifecycleState(
            state="skipped_runtime_budget",
            drift_ratio=0.0,
            drift_events=0,
        ),
    )


def _poll_single_account(
    account: AccountConfig,
    app_config: AppConfig,
    auth: OneDriveAuthClient,
    http_client_factory: Callable[[], httpx.Client] | None,
    poll_run_id: str,
    deadline: float,
    policy: RetryPolicy,
    sleeper: Callable[[float], None],
    jitter_fn: Callable[[], float] | None,
) -> AccountPollResult:
    """Poll a single account and return normalized result."""

    _trace_event(
        "account_poll_start",
        poll_run_id=poll_run_id,
        account_name=account.name,
    )

    remaining_budget = int(deadline - monotonic())
    if remaining_budget <= 0:
        result = _runtime_budget_exhausted_result(account.name)
        _trace_event(
            "account_poll_end",
            poll_run_id=poll_run_id,
            account_name=account.name,
            downloaded_count=0,
            candidate_count=0,
            ghost_item_count=0,
            delta_anomaly_count=result.delta_anomaly_count,
        )
        return result

    try:
        with account_singleton_lock(account.token_cache):
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
                    max_runtime_seconds=min(
                        app_config.core.max_poll_runtime_seconds,
                        max(1, remaining_budget),
                    ),
                    tmp_ttl_minutes=app_config.core.tmp_ttl_minutes,
                    integrity_mode=app_config.core.integrity_mode,
                    delta_loop_resync_threshold=app_config.core.delta_loop_resync_threshold,
                    delta_breaker_ghost_threshold=app_config.core.delta_breaker_ghost_threshold,
                    delta_breaker_stale_page_threshold=(
                        app_config.core.delta_breaker_stale_page_threshold
                    ),
                    delta_breaker_cooldown_seconds=(
                        app_config.core.delta_breaker_cooldown_seconds
                    ),
                    poll_run_id=poll_run_id,
                    policy=policy,
                    sleeper=sleeper,
                    jitter_fn=jitter_fn,
                )
    except SingletonLockBusyError as exc:
        raise GraphError(
            (
                f"Account '{account.name}' is already being polled by another process."
            ),
            code="account_singleton_lock_busy",
            account=account.name,
            operation="poll_accounts",
            safe_hint=str(exc),
        ) from exc

    drift_state, drift_ratio, drift_events = _evaluate_drift_state(
        delta_anomaly_counts,
        warning_threshold=app_config.core.drift_warning_threshold_ratio,
        critical_threshold=app_config.core.drift_critical_threshold_ratio,
        min_events=app_config.core.drift_min_events_for_evaluation,
    )
    _trace_event(
        "drift_state_evaluated",
        poll_run_id=poll_run_id,
        account_name=account.name,
        operation="drift_evaluation",
        drift_state=drift_state,
        drift_ratio=drift_ratio,
        drift_events=drift_events,
    )
    if app_config.core.drift_fail_fast_enabled and drift_state == "critical":
        raise GraphError(
            f"Schema drift threshold exceeded for account '{account.name}'",
            code="drift_threshold_critical",
            account=account.name,
            operation="poll_accounts",
            safe_hint=(
                f"drift_state=critical drift_ratio={drift_ratio:.3f} "
                f"drift_events={drift_events}"
            ),
        )

    anomaly_counts, diagnostics = _split_anomaly_and_diagnostics(delta_anomaly_counts)
    handoff_manifest_path = _boundary_manifest_path_for_account(
        app_config.core.staging_path,
        account.name,
    )
    result = AccountPollResult(
        account_name=account.name,
        payload=AccountPollPayload(
            downloaded_paths=tuple(downloaded),
            handoff_manifest_path=handoff_manifest_path,
            candidate_count=candidate_count,
        ),
        anomalies=AccountPollAnomalies(
            ghost_item_count=sum(ghost_reason_counts.values()),
            ghost_reason_counts=tuple(sorted(ghost_reason_counts.items())),
            delta_anomaly_count=sum(anomaly_counts.values()),
            delta_anomaly_reason_counts=tuple(sorted(anomaly_counts.items())),
        ),
        diagnostics=AccountPollDiagnostics(counters=tuple(sorted(diagnostics.items()))),
        lifecycle_state=AccountPollLifecycleState(
            state=drift_state,
            drift_ratio=drift_ratio,
            drift_events=drift_events,
        ),
    )

    _apply_adaptive_backpressure(account, app_config, result)

    _trace_event(
        "account_poll_end",
        poll_run_id=poll_run_id,
        account_name=account.name,
        downloaded_count=len(downloaded),
        candidate_count=candidate_count,
        ghost_item_count=sum(ghost_reason_counts.values()),
        delta_anomaly_count=sum(delta_anomaly_counts.values()),
    )
    return result


def _apply_adaptive_backpressure(
    account: AccountConfig,
    app_config: AppConfig,
    result: AccountPollResult,
) -> None:
    """Apply account cooldown when retry/transport anomalies exceed thresholds."""

    if not app_config.core.adaptive_backpressure_enabled:
        return

    counts = dict(result.diagnostics.counters)
    retry_total = counts.get("retry_attempt_total", 0)
    transport_total = counts.get("retry_transport_error_total", 0)
    if (
        retry_total >= app_config.core.backpressure_retry_threshold
        or transport_total >= app_config.core.backpressure_transport_error_threshold
    ):
        _arm_breaker_cooldown(
            account.delta_cursor,
            app_config.core.backpressure_cooldown_seconds,
        )
        _trace_event(
            "adaptive_backpressure_armed",
            account_name=account.name,
            operation="adaptive_backpressure",
            retry_total=retry_total,
            transport_total=transport_total,
            cooldown_seconds=app_config.core.backpressure_cooldown_seconds,
        )


def poll_account_once(
    account: AccountConfig,
    staging_root: Path,
    access_token: str,
    http_client: httpx.Client,
    refresh_access_token: Callable[[], str] | None = None,
    poll_run_id: str | None = None,
    max_delta_pages: int = DEFAULT_MAX_DELTA_PAGES,
    max_runtime_seconds: int = 300,
    tmp_ttl_minutes: int = 120,
    integrity_mode: str = "strict",
    delta_loop_resync_threshold: int = 3,
    delta_breaker_ghost_threshold: int = 10,
    delta_breaker_stale_page_threshold: int = 10,
    delta_breaker_cooldown_seconds: int = 300,
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
    diagnostics_counts: dict[str, int] = {}
    page_count = 0
    start_monotonic = monotonic()

    account_staging_root = staging_root / account.name
    incident_state = _load_incident_state(account.delta_cursor)
    if _is_breaker_cooldown_active(incident_state):
        _record_ghost_reason(delta_anomaly_counts, "delta_breaker_cooldown_active")
        return [], 0, {}, delta_anomaly_counts

    _recover_staging_tmp_files(
        staging_dir=account_staging_root,
        ttl_minutes=tmp_ttl_minutes,
        diagnostics_counts=diagnostics_counts,
    )

    while next_url:
        _trace_event(
            "delta_page_start",
            poll_run_id=poll_run_id,
            account_name=account.name,
            page_index=page_count + 1,
            operation="delta_page",
            delta_url=redact_url(next_url),
        )
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
            loop_incidents = _increment_loop_incident(account.delta_cursor)
            if loop_incidents >= delta_loop_resync_threshold:
                _record_ghost_reason(
                    delta_anomaly_counts,
                    "delta_forced_resync_after_loop_threshold",
                )
                _mark_resync_required(
                    cursor_path=account.delta_cursor,
                    account_name=account.name,
                    reason="delta_forced_resync_after_loop_threshold",
                    resync_url=None,
                )
                _reset_loop_incidents(account.delta_cursor)
                return [], 0, {}, delta_anomaly_counts
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
                account_name=account.name,
                poll_run_id=poll_run_id,
                refresh_access_token=refresh_access_token,
                diagnostics_counts=diagnostics_counts,
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
        _trace_event(
            "delta_page_end",
            poll_run_id=poll_run_id,
            account_name=account.name,
            page_index=page_count,
            operation="delta_page",
            has_next=bool(next_url),
            has_delta_link=bool(delta_link),
        )

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
        integrity_mode=integrity_mode,
        refresh_access_token=refresh_access_token,
        poll_run_id=poll_run_id,
        diagnostics_counts=diagnostics_counts,
        policy=policy,
        sleeper=sleeper,
        jitter_fn=jitter_fn,
    )

    # Fold diagnostics into anomaly map under explicit "diag_" keys so
    # callers can consume one counter dictionary without interface churn.
    for key, value in diagnostics_counts.items():
        if key in _EXPORTED_DIAGNOSTIC_KEYS:
            _record_ghost_reason(delta_anomaly_counts, f"diag_{key}", count=value)

    stale_count = delta_anomaly_counts.get("delta_replayed_item_id", 0)
    ghost_total = sum(ghost_reason_counts.values())
    if stale_count >= delta_breaker_stale_page_threshold:
        _record_ghost_reason(delta_anomaly_counts, "delta_breaker_armed_stale_page")
        _arm_breaker_cooldown(account.delta_cursor, delta_breaker_cooldown_seconds)
    elif ghost_total >= delta_breaker_ghost_threshold:
        _record_ghost_reason(delta_anomaly_counts, "delta_breaker_armed_ghost")
        _arm_breaker_cooldown(account.delta_cursor, delta_breaker_cooldown_seconds)

    _save_cursor(account.delta_cursor, delta_link)
    _clear_resync_marker(account.delta_cursor)

    LOGGER.info(
        "account poll diagnostics",
        extra=sanitize_extra(
            {
            "account": account.name,
            "diagnostic_counts": dict(sorted(diagnostics_counts.items())),
            "ghost_reason_counts": dict(sorted(ghost_reason_counts.items())),
            "delta_anomaly_counts": dict(sorted(delta_anomaly_counts.items())),
            }
        ),
    )
    return downloaded_paths, len(candidates), ghost_reason_counts, delta_anomaly_counts


def _incident_state_path(cursor_path: Path) -> Path:
    """Return persistent incident state path derived from cursor path."""

    if cursor_path.suffix:
        return cursor_path.with_suffix(cursor_path.suffix + ".incidents.json")
    return Path(str(cursor_path) + ".incidents.json")


def _load_incident_state(cursor_path: Path) -> dict[str, object]:
    """Load persistent incident state for breaker/escalation logic."""

    path = _incident_state_path(cursor_path)
    if not path.exists():
        return {}

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    if not isinstance(raw, dict):
        return {}
    return raw


def _save_incident_state(cursor_path: Path, payload: dict[str, object]) -> None:
    """Persist incident state atomically."""

    path = _incident_state_path(cursor_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def _is_breaker_cooldown_active(state: dict[str, object]) -> bool:
    """Return True when cooldown window has not yet elapsed."""

    cooldown_until = state.get("cooldown_until_epoch")
    if isinstance(cooldown_until, (int, float)):
        return time.time() < float(cooldown_until)
    return False


def _arm_breaker_cooldown(cursor_path: Path, cooldown_seconds: int) -> None:
    """Set cooldown in incident state for current account."""

    state = _load_incident_state(cursor_path)
    state["cooldown_until_epoch"] = time.time() + float(cooldown_seconds)
    _save_incident_state(cursor_path, state)


def _increment_loop_incident(cursor_path: Path) -> int:
    """Increment repeated loop incident counter and return new value."""

    state = _load_incident_state(cursor_path)
    current = state.get("loop_incidents")
    if not isinstance(current, int):
        current = 0
    current += 1
    state["loop_incidents"] = current
    _save_incident_state(cursor_path, state)
    return current


def _reset_loop_incidents(cursor_path: Path) -> None:
    """Reset loop incident counter after escalation to forced resync."""

    state = _load_incident_state(cursor_path)
    state["loop_incidents"] = 0
    _save_incident_state(cursor_path, state)


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
    poll_run_id: str | None = None,
    max_downloads: int | None = None,
    integrity_mode: str = "strict",
    diagnostics_counts: dict[str, int] | None = None,
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
    lifecycle_journal = target_root / "_lifecycle.journal.jsonl"
    handoff_manifest = _boundary_manifest_path_for_account(staging_root, account_name)
    quarantine_root = target_root / "_quarantine"
    quarantine_root.mkdir(parents=True, exist_ok=True)
    used_basenames: set[str] = set()
    handoff_manifest.unlink(missing_ok=True)

    for index, candidate in enumerate(candidates):
        if limit > 0 and index >= limit:
            break

        safe_base = _unique_staging_basename(candidate.item_id, used_basenames)
        suffix = _safe_extension(candidate.name)
        tmp_path = target_root / f"{safe_base}.tmp"
        final_path = target_root / f"{safe_base}{suffix}"

        if candidate.size_bytes is None:
            _increment_counter(diagnostics_counts, "integrity_uncertain_total")
            if integrity_mode == "strict":
                _increment_counter(diagnostics_counts, "integrity_strict_blocked_total")
                _record_ghost_reason(
                    ghost_reason_counts,
                    "integrity_missing_expected_size_blocked",
                )
                continue

        _append_lifecycle_event(
            lifecycle_journal,
            event_type="download_started",
            account_name=account_name,
            item_id=candidate.item_id,
            path=tmp_path,
            diagnostics_counts=diagnostics_counts,
        )
        try:
            download_with_retry(
                http_client=http_client,
                url=candidate.download_url,
                destination=tmp_path,
                expected_size=candidate.size_bytes,
                account_name=account_name,
                poll_run_id=poll_run_id,
                diagnostics_counts=diagnostics_counts,
                policy=policy,
                sleeper=sleeper,
                jitter_fn=jitter_fn,
            )
        except DownloadError as first_error:
            tmp_path.unlink(missing_ok=True)
            if not _is_download_url_unreachable(first_error):
                raise

            refreshed_url, ghost_reason = _resolve_download_url_once(
                item_id=candidate.item_id,
                access_token=access_token,
                refresh_access_token=refresh_access_token,
                http_client=http_client,
                account_name=account_name,
                poll_run_id=poll_run_id,
                diagnostics_counts=diagnostics_counts,
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
                    account_name=account_name,
                    poll_run_id=poll_run_id,
                    diagnostics_counts=diagnostics_counts,
                    policy=policy,
                    sleeper=sleeper,
                    jitter_fn=jitter_fn,
                )
            except DownloadError as refreshed_error:
                tmp_path.unlink(missing_ok=True)
                if _is_download_url_unreachable(refreshed_error):
                    _record_ghost_reason(
                        ghost_reason_counts,
                        "ghost_download_unreachable_after_refresh",
                    )
                    continue
                raise

        _append_lifecycle_event(
            lifecycle_journal,
            event_type="download_completed",
            account_name=account_name,
            item_id=candidate.item_id,
            path=tmp_path,
            diagnostics_counts=diagnostics_counts,
        )

        if candidate.size_bytes is None and integrity_mode == "tolerant":
            quarantine_path = quarantine_root / f"{safe_base}{suffix}"
            tmp_path.replace(quarantine_path)
            _increment_counter(diagnostics_counts, "integrity_quarantined_total")
            _record_ghost_reason(
                ghost_reason_counts,
                "integrity_missing_expected_size_quarantined",
            )
            _append_lifecycle_event(
                lifecycle_journal,
                event_type="download_quarantined",
                account_name=account_name,
                item_id=candidate.item_id,
                path=quarantine_path,
                diagnostics_counts=diagnostics_counts,
            )
            continue

        tmp_path.replace(final_path)
        _append_lifecycle_event(
            lifecycle_journal,
            event_type="ready_for_hash",
            account_name=account_name,
            item_id=candidate.item_id,
            path=final_path,
            diagnostics_counts=diagnostics_counts,
        )
        _append_boundary_handoff_entry(
            manifest_path=handoff_manifest,
            candidate=candidate,
            staging_path=final_path,
        )
        downloaded.append(final_path)

    return downloaded, ghost_reason_counts


def _boundary_manifest_path_for_account(staging_root: Path, account_name: str) -> Path:
    """Return account-scoped boundary manifest path for Module 3 -> Module 4."""

    return staging_root / account_name / "_boundary_handoff.jsonl"


def _append_boundary_handoff_entry(
    *,
    manifest_path: Path,
    candidate: RemoteCandidate,
    staging_path: Path,
) -> None:
    """Append one line of handoff metadata for ingest boundary consumers."""

    payload = {
        "account_name": candidate.account_name,
        "onedrive_id": candidate.item_id,
        "original_filename": candidate.name,
        "relative_path": candidate.relative_path,
        "modified_time": candidate.normalized_modified_time,
        "size_bytes": candidate.size_bytes,
        "staging_path": str(staging_path),
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True))
        handle.write("\n")


def load_boundary_handoff_candidates(
    manifest_path: Path | None,
) -> tuple[DownloadedHandoffCandidate, ...]:
    """Load deterministic ingest handoff records produced by poll/download."""

    if manifest_path is None or not manifest_path.exists():
        return tuple()

    rows: list[DownloadedHandoffCandidate] = []
    for raw in manifest_path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        payload = json.loads(raw)
        rows.append(
            DownloadedHandoffCandidate(
                account_name=str(payload.get("account_name", "")),
                onedrive_id=str(payload.get("onedrive_id", "")),
                original_filename=str(payload.get("original_filename", "")),
                relative_path=str(payload.get("relative_path", "")),
                modified_time=str(payload.get("modified_time", "")),
                size_bytes=payload.get("size_bytes"),
                staging_path=Path(str(payload.get("staging_path", ""))),
            )
        )
    return tuple(rows)


def _record_ghost_reason(reason_counts: dict[str, int], reason: str, count: int = 1) -> None:
    """Increment a reason counter by count."""

    reason_counts[reason] = reason_counts.get(reason, 0) + count


def _increment_counter(
    counters: dict[str, int] | None,
    key: str,
    count: int = 1,
) -> None:
    """Increment an optional diagnostics counter dictionary safely."""

    if counters is None:
        return
    counters[key] = counters.get(key, 0) + count


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
        "required_at": datetime.now(timezone.utc).isoformat(),
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
    account_name: str,
    poll_run_id: str | None,
    diagnostics_counts: dict[str, int] | None,
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
            account_name=account_name,
            poll_run_id=poll_run_id,
            refresh_access_token=refresh_access_token,
            diagnostics_counts=diagnostics_counts,
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
    account_name: str | None = None,
    poll_run_id: str | None = None,
    policy: RetryPolicy = DEFAULT_POLICY,
    sleeper: Callable[[float], None] = time.sleep,
    jitter_fn: Callable[[], float] | None = None,
    *,
    diagnostics_counts: dict[str, int] | None = None,
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
        _trace_event(
            "download_attempt_start",
            poll_run_id=poll_run_id,
            account_name=account_name,
            operation="download",
            attempt=attempt,
            max_attempts=policy.max_attempts,
            url=redact_url(url),
            expected_size=expected_size,
            destination=destination,
        )
        _increment_counter(diagnostics_counts, "download_request_total")
        try:
            response = http_client.get(url, timeout=120.0)
        except httpx.RequestError as exc:
            # Transport-level failure: connection reset, DNS error, timeout, etc.
            _cleanup_partial()
            _increment_counter(diagnostics_counts, "retry_attempt_total")
            _increment_counter(diagnostics_counts, "retry_transport_error_total")
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
            _trace_event(
                "download_retry_scheduled",
                poll_run_id=poll_run_id,
                account_name=account_name,
                operation="download",
                attempt=attempt,
                reason="transport_error",
                delay_seconds=delay,
                error_type=type(exc).__name__,
                url=redact_url(url),
            )
            sleeper(delay)
            continue

        if classify_status(response.status_code):
            _cleanup_partial()
            _increment_counter(diagnostics_counts, "retry_attempt_total")
            if response.status_code in {429, 503}:
                _increment_counter(diagnostics_counts, "throttle_response_total")
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
            _trace_event(
                "download_retry_scheduled",
                poll_run_id=poll_run_id,
                account_name=account_name,
                operation="download",
                attempt=attempt,
                reason="http_retryable_status",
                status_code=response.status_code,
                retry_after=retry_after,
                delay_seconds=delay,
                url=redact_url(url),
            )
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
                _increment_counter(diagnostics_counts, "retry_attempt_total")
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
                _trace_event(
                    "download_retry_scheduled",
                    poll_run_id=poll_run_id,
                    account_name=account_name,
                    operation="download",
                    attempt=attempt,
                    reason="empty_body",
                    delay_seconds=delay,
                    expected_size=expected_size,
                    url=redact_url(url),
                )
                sleeper(delay)
                continue

            if expected_size >= 0 and bytes_written != expected_size:
                _cleanup_partial()
                _increment_counter(diagnostics_counts, "retry_attempt_total")
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
                _trace_event(
                    "download_retry_scheduled",
                    poll_run_id=poll_run_id,
                    account_name=account_name,
                    operation="download",
                    attempt=attempt,
                    reason="size_mismatch",
                    delay_seconds=delay,
                    expected_size=expected_size,
                    bytes_written=bytes_written,
                    url=redact_url(url),
                )
                sleeper(delay)
                continue

        _trace_event(
            "download_attempt_success",
            poll_run_id=poll_run_id,
            account_name=account_name,
            operation="download",
            attempt=attempt,
            status_code=response.status_code,
            bytes_written=bytes_written,
            destination=destination,
            url=redact_url(url),
        )

        return


def _graph_get_json(
    http_client: httpx.Client,
    url: str,
    access_token: str,
    policy: RetryPolicy = DEFAULT_POLICY,
    sleeper: Callable[[float], None] = time.sleep,
    jitter_fn: Callable[[], float] | None = None,
    refresh_access_token: Callable[[], str] | None = None,
    *,
    diagnostics_counts: dict[str, int] | None = None,
    account_name: str | None = None,
    poll_run_id: str | None = None,
) -> dict[str, object]:
    """Execute a Graph GET request and return parsed JSON payload.

    Applies the same retry/backoff policy as :func:`download_with_retry`:
    - HTTP 429/500/502/503/504 are retried with Retry-After / exponential back-off.
    - Transport errors (``httpx.RequestError``) are retried up to
      ``policy.max_attempts``.
    """
    refreshed_once = False
    for attempt in range(1, policy.max_attempts + 1):
        client_request_id = str(uuid4())
        request_headers = {
            "Authorization": f"Bearer {access_token}",
            "client-request-id": client_request_id,
            "return-client-request-id": "true",
        }
        _increment_counter(diagnostics_counts, "graph_request_total")
        _increment_counter(diagnostics_counts, "graph_client_request_id_sent_total")
        _trace_event(
            "graph_request_attempt_start",
            poll_run_id=poll_run_id,
            account_name=account_name,
            operation="graph_get",
            attempt=attempt,
            max_attempts=policy.max_attempts,
            client_request_id=client_request_id,
            url=redact_url(url),
        )
        try:
            response = http_client.get(
                url,
                headers=request_headers,
                timeout=30.0,
            )
        except httpx.RequestError as exc:
            _increment_counter(diagnostics_counts, "retry_attempt_total")
            _increment_counter(diagnostics_counts, "retry_transport_error_total")
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
            _trace_event(
                "graph_retry_scheduled",
                poll_run_id=poll_run_id,
                account_name=account_name,
                operation="graph_get",
                attempt=attempt,
                reason="transport_error",
                delay_seconds=delay,
                error_type=type(exc).__name__,
                client_request_id=client_request_id,
                url=redact_url(url),
            )
            sleeper(delay)
            continue

        request_id = response.headers.get("request-id")
        correlation_id = response.headers.get("x-ms-correlation-request-id")
        if request_id:
            _increment_counter(diagnostics_counts, "graph_response_request_id_seen_total")
        if correlation_id:
            _increment_counter(
                diagnostics_counts,
                "graph_response_correlation_id_seen_total",
            )

        if response.status_code in {401, 403}:
            support_suffix = _response_support_suffix(response)
            _increment_counter(diagnostics_counts, "auth_refresh_attempt_total")
            _trace_event(
                "graph_auth_refresh_attempt",
                poll_run_id=poll_run_id,
                account_name=account_name,
                operation="graph_get",
                attempt=attempt,
                status_code=response.status_code,
                client_request_id=client_request_id,
                url=redact_url(url),
            )
            if refreshed_once or refresh_access_token is None:
                raise GraphError(
                    "Graph authentication failed",
                    url=url,
                    code="graph_auth_failed",
                    status_code=response.status_code,
                    safe_hint=(
                        f"HTTP {response.status_code} for {redact_url(url)} "
                        f"after refresh attempt{support_suffix}"
                    ),
                )
            try:
                access_token = refresh_access_token()
                _increment_counter(diagnostics_counts, "auth_refresh_success_total")
                _trace_event(
                    "graph_auth_refresh_success",
                    poll_run_id=poll_run_id,
                    account_name=account_name,
                    operation="graph_get",
                    attempt=attempt,
                    client_request_id=client_request_id,
                    url=redact_url(url),
                )
            except AuthError as exc:
                _increment_counter(diagnostics_counts, "auth_refresh_failure_total")
                _trace_event(
                    "graph_auth_refresh_failure",
                    poll_run_id=poll_run_id,
                    account_name=account_name,
                    operation="graph_get",
                    attempt=attempt,
                    client_request_id=client_request_id,
                    error_code=getattr(exc, "code", None),
                    url=redact_url(url),
                )
                raise GraphError(
                    "Graph token refresh failed",
                    url=url,
                    code="graph_auth_refresh_failed",
                    status_code=response.status_code,
                    safe_hint=(
                        f"Token refresh failed for {redact_url(url)}"
                        f"{support_suffix}"
                    ),
                ) from exc
            refreshed_once = True
            continue

        if classify_status(response.status_code):
            support_suffix = _response_support_suffix(response)
            _increment_counter(diagnostics_counts, "retry_attempt_total")
            if response.status_code in {429, 503}:
                _increment_counter(diagnostics_counts, "throttle_response_total")
            if attempt >= policy.max_attempts:
                raise GraphError(
                    "Graph request retry limit reached",
                    url=url,
                    code="graph_retry_exhausted",
                    status_code=response.status_code,
                    safe_hint=(
                        f"HTTP {response.status_code} after {policy.max_attempts} "
                        f"retries for {redact_url(url)}{support_suffix}"
                    ),
                )
            retry_after = parse_retry_after(response.headers.get("Retry-After"))
            delay = compute_delay(attempt, retry_after, policy, jitter_fn)
            _trace_event(
                "graph_retry_scheduled",
                poll_run_id=poll_run_id,
                account_name=account_name,
                operation="graph_get",
                attempt=attempt,
                reason="http_retryable_status",
                status_code=response.status_code,
                retry_after=retry_after,
                delay_seconds=delay,
                client_request_id=client_request_id,
                url=redact_url(url),
            )
            sleeper(delay)
            continue

        if response.status_code == 410:
            _increment_counter(diagnostics_counts, "resync_required_total")
            support_suffix = _response_support_suffix(response)
            raise GraphResyncRequired(
                "Graph delta cursor is no longer valid and requires resync",
                url=url,
                status_code=response.status_code,
                resync_url=response.headers.get("Location"),
                safe_hint=f"HTTP 410 for {redact_url(url)}{support_suffix}",
            )

        if response.status_code >= 400:
            support_suffix = _response_support_suffix(response)
            raise GraphError(
                "Graph request returned error status",
                url=url,
                status_code=response.status_code,
                safe_hint=(
                    f"HTTP {response.status_code} for {redact_url(url)}"
                    f"{support_suffix}"
                ),
            )

        try:
            payload = json.loads(response.text)
        except json.JSONDecodeError as exc:
            raise GraphError(
                "Invalid JSON in Graph response",
                url=url,
                code="graph_invalid_json",
                safe_hint=f"JSON parse error for {redact_url(url)}",
            ) from exc

        _trace_event(
            "graph_request_attempt_success",
            poll_run_id=poll_run_id,
            account_name=account_name,
            operation="graph_get",
            attempt=attempt,
            status_code=response.status_code,
            client_request_id=client_request_id,
            request_id=request_id,
            correlation_id=correlation_id,
            url=redact_url(url),
        )
        return payload

    # Unreachable: loop always returns or raises on the final attempt.
    raise GraphError(  # pragma: no cover
        "Unexpected retry loop exit",
        url=url,
        code="graph_retry_loop_exit",
    )


def _build_initial_delta_url(account: AccountConfig) -> str:
    """Construct the initial folder delta URL for an account."""

    root = _normalize_root_path(account.effective_onedrive_root)

    # Encode each path segment explicitly to avoid Graph path addressing bugs
    # with spaces or reserved characters in user-provided roots.
    segments = [quote(segment, safe="") for segment in root.split("/") if segment]
    encoded_root = "/" + "/".join(segments)

    return f"{GRAPH_BASE}/me/drive/root:{encoded_root}:/delta"


def detect_account_locale(
    account: AccountConfig,
    access_token: str,
    http_client: httpx.Client,
) -> str | None:
    """Best-effort locale detection based on top-level OneDrive folder names.

    Returns:
        "de" when German naming is detected, "en" for English naming, or
        None when there is no confident signal.
    """

    payload = _graph_get_json(
        http_client=http_client,
        url=f"{GRAPH_BASE}/me/drive/root/children?$select=name,folder",
        access_token=access_token,
        account_name=account.name,
    )

    folder_names: set[str] = set()
    for raw in payload.get("value", []):
        if not isinstance(raw, dict):
            continue
        if not isinstance(raw.get("folder"), dict):
            continue
        name = _as_str(raw.get("name"))
        if not name:
            continue
        folder_names.add(name.casefold())

    if folder_names & _GERMAN_FOLDER_NAMES:
        return "de"
    if folder_names & _ENGLISH_FOLDER_NAMES:
        return "en"
    return None


def resolve_camera_roll_path_for_onboarding(
    account: AccountConfig,
    access_token: str,
    http_client: httpx.Client,
) -> CameraRollPathResolution:
    """Validate configured path and auto-discover alternatives when needed."""

    configured_path = _normalize_root_path(account.onedrive_root)
    configured_exists, configured_media_count = _evaluate_media_path(
        path=configured_path,
        account=account,
        access_token=access_token,
        http_client=http_client,
    )

    special_camera_roll = _resolve_special_folder_path(
        alias=_SPECIAL_CAMERA_ROLL_ALIAS,
        account=account,
        access_token=access_token,
        http_client=http_client,
    )
    if special_camera_roll is not None:
        exists, media_count = _evaluate_media_path(
            path=special_camera_roll,
            account=account,
            access_token=access_token,
            http_client=http_client,
        )
        if exists:
            if special_camera_roll == configured_path:
                return CameraRollPathResolution(
                    configured_path=configured_path,
                    configured_exists=configured_exists,
                    configured_media_count=configured_media_count,
                    suggested_path=None,
                    suggested_media_count=0,
                    suggested_candidates=tuple(),
                    reason=None,
                )

            if configured_exists and configured_media_count > 0:
                reason = "configured_path_not_camera_roll"
            elif configured_exists and configured_media_count == 0:
                reason = "configured_path_has_no_media"
            elif not configured_exists:
                reason = "configured_path_not_found"
            else:
                reason = None

            return CameraRollPathResolution(
                configured_path=configured_path,
                configured_exists=configured_exists,
                configured_media_count=configured_media_count,
                suggested_path=special_camera_roll,
                suggested_media_count=media_count,
                suggested_candidates=(
                    PathDiscoveryCandidate(path=special_camera_roll, media_count=media_count),
                ),
                reason=reason,
            )

    if configured_exists and configured_media_count > 0:
        return CameraRollPathResolution(
            configured_path=configured_path,
            configured_exists=True,
            configured_media_count=configured_media_count,
            suggested_path=None,
            suggested_media_count=0,
            suggested_candidates=tuple(),
            reason=None,
        )

    candidates: list[PathDiscoveryCandidate] = []
    metadata_preferred: list[PathDiscoveryCandidate] = []
    seen_paths: set[str] = {configured_path}
    for raw_path in _DISCOVERY_CANDIDATE_PATHS:
        normalized = _normalize_root_path(raw_path)
        if normalized in seen_paths:
            continue
        seen_paths.add(normalized)
        exists, media_count = _evaluate_media_path(
            path=normalized,
            account=account,
            access_token=access_token,
            http_client=http_client,
        )
        if exists and media_count > 0:
            candidate = PathDiscoveryCandidate(path=normalized, media_count=media_count)
            candidates.append(candidate)
            if _path_has_special_folder_name(
                path=normalized,
                expected_name=_SPECIAL_CAMERA_ROLL_ALIAS,
                account=account,
                access_token=access_token,
                http_client=http_client,
            ):
                metadata_preferred.append(candidate)

    metadata_preferred.sort(key=lambda item: item.media_count, reverse=True)
    candidates.sort(key=lambda item: item.media_count, reverse=True)
    suggestion = metadata_preferred[0] if metadata_preferred else (candidates[0] if candidates else None)

    if configured_exists and configured_media_count == 0:
        reason = "configured_path_has_no_media"
    elif not configured_exists:
        reason = "configured_path_not_found"
    else:
        reason = None

    return CameraRollPathResolution(
        configured_path=configured_path,
        configured_exists=configured_exists,
        configured_media_count=configured_media_count,
        suggested_path=suggestion.path if suggestion else None,
        suggested_media_count=suggestion.media_count if suggestion else 0,
        suggested_candidates=tuple(candidates),
        reason=reason,
    )


def _evaluate_media_path(
    *,
    path: str,
    account: AccountConfig,
    access_token: str,
    http_client: httpx.Client,
) -> tuple[bool, int]:
    """Return (exists, media_count) for a given OneDrive folder path."""

    normalized = _normalize_root_path(path)
    url = _build_children_url(normalized)
    try:
        payload = _graph_get_json(
            http_client=http_client,
            url=url,
            access_token=access_token,
            account_name=account.name,
        )
    except GraphError as exc:
        if exc.status_code == 404:
            return False, 0
        raise

    media_count = _count_media_in_children(payload)
    return True, media_count


def _resolve_special_folder_path(
    *,
    alias: str,
    account: AccountConfig,
    access_token: str,
    http_client: httpx.Client,
) -> str | None:
    """Return normalized path for a special-folder alias, if Graph exposes one."""

    url = f"{GRAPH_BASE}/me/drive/special/{quote(alias, safe='')}?$select=name,parentReference,specialFolder"
    try:
        payload = _graph_get_json(
            http_client=http_client,
            url=url,
            access_token=access_token,
            account_name=account.name,
        )
    except GraphError as exc:
        if exc.status_code in {403, 404}:
            return None
        raise

    special_name = _extract_special_folder_name(payload)
    if special_name != alias.casefold():
        return None
    return _drive_item_path(payload)


def _path_has_special_folder_name(
    *,
    path: str,
    expected_name: str,
    account: AccountConfig,
    access_token: str,
    http_client: httpx.Client,
) -> bool:
    """Return True when a folder path resolves to the expected specialFolder facet."""

    normalized = _normalize_root_path(path)
    url = _build_item_url(normalized)
    try:
        payload = _graph_get_json(
            http_client=http_client,
            url=url,
            access_token=access_token,
            account_name=account.name,
        )
    except GraphError as exc:
        if exc.status_code == 404:
            return False
        raise

    return _extract_special_folder_name(payload) == expected_name.casefold()


def _extract_special_folder_name(payload: dict[str, object]) -> str | None:
    """Return casefolded specialFolder facet name when present."""

    special_folder = payload.get("specialFolder")
    if not isinstance(special_folder, dict):
        return None
    name = _as_str(special_folder.get("name"))
    return name.casefold() if name else None


def _drive_item_path(payload: dict[str, object]) -> str | None:
    """Reconstruct a normalized root-relative path from a driveItem payload."""

    name = _as_str(payload.get("name"))
    parent = payload.get("parentReference")
    if not name or not isinstance(parent, dict):
        return None

    base = _as_str(parent.get("path")) or "/drive/root:"
    if base == "/drive/root:":
        return _normalize_root_path(f"/{name}")
    prefix = "/drive/root:"
    if base.startswith(prefix):
        return _normalize_root_path(base[len(prefix):] + f"/{name}")
    return None


def _count_media_in_children(payload: dict[str, object]) -> int:
    """Count media files in a Graph /children payload."""

    count = 0
    for raw in payload.get("value", []):
        if not isinstance(raw, dict):
            continue
        if not isinstance(raw.get("file"), dict):
            continue
        name = _as_str(raw.get("name"))
        if not name:
            continue
        suffix = Path(name).suffix.casefold()
        if suffix in _MEDIA_EXTENSIONS:
            count += 1
    return count


def _build_children_url(root: str) -> str:
    """Build Graph children URL for a root path using encoded segments."""

    segments = [quote(segment, safe="") for segment in root.split("/") if segment]
    encoded_root = "/" + "/".join(segments)
    return f"{GRAPH_BASE}/me/drive/root:{encoded_root}:/children?$select=name,file,folder"


def _build_item_url(root: str) -> str:
    """Build Graph driveItem URL for a root path using encoded segments."""

    segments = [quote(segment, safe="") for segment in root.split("/") if segment]
    encoded_root = "/" + "/".join(segments)
    return (
        f"{GRAPH_BASE}/me/drive/root:{encoded_root}"
        "?$select=name,parentReference,specialFolder"
    )


def _normalize_root_path(root: str) -> str:
    """Normalize user-configured root path for Graph path addressing."""

    normalized = root.strip()
    if not normalized.startswith("/"):
        normalized = "/" + normalized
    return normalized


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


def _response_support_suffix(response: httpx.Response) -> str:
    """Return a compact support diagnostics suffix from Graph response headers."""

    request_id = response.headers.get("request-id")
    correlation_id = response.headers.get("x-ms-correlation-request-id")
    parts: list[str] = []
    if request_id:
        parts.append(f"request-id={request_id}")
    if correlation_id:
        parts.append(f"correlation-id={correlation_id}")
    if not parts:
        return ""
    return " (" + ", ".join(parts) + ")"


def _safe_staging_basename(item_id: str) -> str:
    """Return a filesystem-safe staging basename derived from item ID."""

    sanitized = _SAFE_STAGING_BASENAME_RE.sub("_", item_id).strip("._-")
    if not sanitized:
        return "item"
    return sanitized[:120]


def _unique_staging_basename(item_id: str, used_basenames: set[str]) -> str:
    """Return deterministic unique basename when sanitization collisions occur."""

    base = _safe_staging_basename(item_id)
    if base not in used_basenames:
        used_basenames.add(base)
        return base

    suffix = hashlib.sha256(item_id.encode("utf-8")).hexdigest()[:8]
    candidate = f"{base}-{suffix}"
    used_basenames.add(candidate)
    return candidate


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

    size_raw = raw.get("size")
    size_bytes: int | None
    if size_raw is None:
        size_bytes = None
    else:
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
        raw_modified_time=_as_str(raw.get("lastModifiedDateTime")),
        normalized_modified_time=_as_str(raw.get("lastModifiedDateTime"))
        or datetime.now(timezone.utc).isoformat(),
        download_url=download_url,
    )


def _split_anomaly_and_diagnostics(
    counts: dict[str, int],
) -> tuple[dict[str, int], dict[str, int]]:
    """Split mixed anomaly+diagnostic counters into explicit sections."""

    anomalies: dict[str, int] = {}
    diagnostics: dict[str, int] = {}
    for key, value in counts.items():
        if key.startswith("diag_"):
            diagnostics[key[5:]] = value
        else:
            anomalies[key] = value
    return anomalies, diagnostics


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

    size_raw = raw.get("size")
    if size_raw is None:
        return "delta_file_missing_size"
    try:
        size_value = int(size_raw)
    except (TypeError, ValueError):
        return "delta_file_invalid_size"
    if size_value < 0:
        return "delta_file_invalid_size"

    return "delta_file_invalid_payload"


def _recover_staging_tmp_files(
    staging_dir: Path,
    ttl_minutes: int,
    diagnostics_counts: dict[str, int] | None,
) -> None:
    """Reconcile stale .tmp artifacts in account staging directory.

    Recovery policy:
    - files ending with ``.tmp`` older than TTL are moved to quarantine,
      preserving evidence for operator inspection.
    - finalized files are never touched.
    """

    if not staging_dir.exists():
        return

    tmp_quarantine = staging_dir / "_recovery_quarantine"
    now_epoch = time.time()
    ttl_seconds = max(ttl_minutes, 0) * 60

    for path in staging_dir.iterdir():
        if not path.is_file() or path.suffix != ".tmp":
            continue

        age_seconds = now_epoch - path.stat().st_mtime
        if age_seconds < ttl_seconds:
            continue

        tmp_quarantine.mkdir(parents=True, exist_ok=True)
        quarantine_target = tmp_quarantine / f"{path.name}.{int(now_epoch)}"
        path.replace(quarantine_target)
        _increment_counter(diagnostics_counts, "staging_tmp_files_quarantined_total")


def _append_lifecycle_event(
    journal_path: Path,
    event_type: str,
    account_name: str,
    item_id: str,
    path: Path,
    diagnostics_counts: dict[str, int] | None,
) -> None:
    """Append a lifecycle event to account journal as JSONL."""

    journal_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event_type,
        "account": account_name,
        "item_id": item_id,
        "path": str(path),
    }
    with journal_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True))
        handle.write("\n")
    _increment_counter(diagnostics_counts, "lifecycle_events_written_total")


def _evaluate_drift_state(
    anomaly_counts: dict[str, int],
    warning_threshold: float,
    critical_threshold: float,
    min_events: int,
) -> tuple[str, float, int]:
    """Evaluate drift state from anomaly counters.

    Drift-sensitive anomalies are those related to malformed/missing item fields.
    """

    drift_prefixes = (
        "delta_item_missing_",
        "delta_file_missing_",
        "delta_file_invalid_",
    )
    drift_events = sum(
        value
        for key, value in anomaly_counts.items()
        if key.startswith(drift_prefixes)
    )
    total_events = max(sum(anomaly_counts.values()), 1)
    drift_ratio = drift_events / float(total_events)

    if drift_events < min_events:
        return "normal", drift_ratio, drift_events
    if drift_ratio >= critical_threshold:
        return "critical", drift_ratio, drift_events
    if drift_ratio >= warning_threshold:
        return "warning", drift_ratio, drift_events
    return "normal", drift_ratio, drift_events
