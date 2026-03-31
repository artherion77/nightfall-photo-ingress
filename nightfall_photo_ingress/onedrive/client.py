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
import time
from typing import Callable, Iterable

import httpx

from ..config import AccountConfig, AppConfig
from .auth import OneDriveAuthClient
from .errors import DownloadError, GraphError, redact_url  # noqa: F401
from .retry import (  # noqa: F401
    DEFAULT_POLICY,
    RETRYABLE_STATUS_CODES,
    RetryPolicy,
    classify_status,
    compute_delay,
    parse_retry_after,
)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


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
        with _build_client(http_client_factory) as client:
            downloaded, candidate_count = poll_account_once(
                account=account,
                staging_root=app_config.core.staging_path,
                access_token=token.token,
                http_client=client,
                policy=policy,
                sleeper=sleeper,
                jitter_fn=jitter_fn,
            )
        results.append(
            AccountPollResult(
                account_name=account.name,
                downloaded_paths=tuple(downloaded),
                candidate_count=candidate_count,
            )
        )

    return tuple(results)


def poll_account_once(
    account: AccountConfig,
    staging_root: Path,
    access_token: str,
    http_client: httpx.Client,
    policy: RetryPolicy = DEFAULT_POLICY,
    sleeper: Callable[[float], None] = time.sleep,
    jitter_fn: Callable[[], float] | None = None,
) -> tuple[list[Path], int]:
    """Poll one account and download candidates into staging."""

    cursor = _load_cursor(account.delta_cursor)
    delta_url = cursor or _build_initial_delta_url(account)

    candidates: list[RemoteCandidate] = []
    next_url: str | None = delta_url
    delta_link: str | None = None

    while next_url:
        payload = _graph_get_json(
            http_client, next_url, access_token,
            policy=policy, sleeper=sleeper, jitter_fn=jitter_fn,
        )
        candidates.extend(parse_delta_items(account.name, payload))
        next_url = _as_str(payload.get("@odata.nextLink"))
        delta_link = _as_str(payload.get("@odata.deltaLink")) or delta_link

    if delta_link is None:
        raise GraphError(
            f"No delta link returned for account '{account.name}'",
            code="missing_delta_link",
            account=account.name,
            operation="poll_account_once",
        )

    downloaded_paths = download_candidates(
        candidates=candidates,
        staging_root=staging_root,
        account_name=account.name,
        http_client=http_client,
        max_downloads=account.max_downloads,
        policy=policy,
        sleeper=sleeper,
        jitter_fn=jitter_fn,
    )

    _save_cursor(account.delta_cursor, delta_link)
    return downloaded_paths, len(candidates)


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

        download_url = _as_str(raw.get("@microsoft.graph.downloadUrl"))
        if not download_url:
            continue

        parsed.append(
            RemoteCandidate(
                account_name=account_name,
                item_id=_as_str(raw.get("id")) or "",
                name=_as_str(raw.get("name")) or "",
                relative_path=_extract_relative_path(raw),
                size_bytes=int(raw.get("size", 0)),
                modified_time=_as_str(raw.get("lastModifiedDateTime"))
                or datetime.utcnow().isoformat(),
                download_url=download_url,
            )
        )

    return tuple(parsed)


def download_candidates(
    candidates: Iterable[RemoteCandidate],
    staging_root: Path,
    account_name: str,
    http_client: httpx.Client,
    max_downloads: int | None,
    policy: RetryPolicy = DEFAULT_POLICY,
    sleeper: Callable[[float], None] = time.sleep,
    jitter_fn: Callable[[], float] | None = None,
) -> list[Path]:
    """Download candidates into account-scoped staging folder."""

    target_root = staging_root / account_name
    target_root.mkdir(parents=True, exist_ok=True)

    downloaded: list[Path] = []
    limit = max_downloads if max_downloads is not None else 0

    for index, candidate in enumerate(candidates):
        if limit > 0 and index >= limit:
            break

        suffix = Path(candidate.name).suffix or ".bin"
        tmp_path = target_root / f"{candidate.item_id}.tmp"
        final_path = target_root / f"{candidate.item_id}{suffix}"
        download_with_retry(
            http_client=http_client,
            url=candidate.download_url,
            destination=tmp_path,
            expected_size=candidate.size_bytes,
            policy=policy,
            sleeper=sleeper,
            jitter_fn=jitter_fn,
        )
        tmp_path.replace(final_path)
        downloaded.append(final_path)

    return downloaded


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
) -> dict[str, object]:
    """Execute a Graph GET request and return parsed JSON payload.

    Applies the same retry/backoff policy as :func:`download_with_retry`:
    - HTTP 429/500/502/503/504 are retried with Retry-After / exponential back-off.
    - Transport errors (``httpx.RequestError``) are retried up to
      ``policy.max_attempts``.
    """
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

    return f"{GRAPH_BASE}/me/drive/root:{root}:/delta"


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
