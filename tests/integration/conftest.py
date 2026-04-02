"""Shared fixtures and helpers for Module 3 to Module 4 integration tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import pytest

from nightfall_photo_ingress.config import AccountConfig, AppConfig, CoreConfig, LoggingConfig
from nightfall_photo_ingress.adapters.onedrive.client import (
    load_boundary_handoff_candidates,
    poll_accounts,
)
from nightfall_photo_ingress.domain.ingest import (
    INGEST_INPUT_SCHEMA_VERSION,
    IngestBatchResult,
    IngestDecisionEngine,
    StagedCandidate,
)
from nightfall_photo_ingress.domain.registry import Registry
from nightfall_photo_ingress.live_photo import LivePhotoHeuristics


@dataclass
class FakeResponse:
    """Minimal httpx-like response used by integration tests."""

    status_code: int
    text: str = "{}"
    headers: dict[str, str] | None = None
    content: bytes = b""
    chunks: list[bytes] | None = None
    iter_error: Exception | None = None

    def __post_init__(self) -> None:
        if self.headers is None:
            self.headers = {}

    def iter_bytes(self, chunk_size: int = 1024 * 1024):
        """Yield deterministic chunks and optionally fail mid-stream."""

        _ = chunk_size
        if self.chunks is not None:
            for chunk in self.chunks:
                yield chunk
        elif self.content:
            yield self.content
        if self.iter_error is not None:
            raise self.iter_error


class FakeGraphClient:
    """Very small deterministic client used at the OneDrive boundary."""

    def __init__(self, mapping: dict[str, list[FakeResponse | Exception]]) -> None:
        self._mapping = mapping

    def get(self, url: str, *args: Any, **kwargs: Any) -> FakeResponse:
        """Return queued responses or raise queued exceptions."""

        _ = args
        _ = kwargs
        queue = self._mapping.get(url)
        if not queue:
            raise AssertionError(f"Unexpected URL requested: {url}")
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def __enter__(self) -> "FakeGraphClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        _ = exc_type
        _ = exc
        _ = tb


class FakeAuthClient:
    """Deterministic auth provider for integration tests."""

    def acquire_access_token(self, account: AccountConfig):
        return type("AccessToken", (), {"token": f"token-for-{account.name}"})


@dataclass(frozen=True)
class RegistryHarness:
    """Registry wrapper exposing convenience query helpers for assertions."""

    registry: Registry

    @property
    def db_path(self) -> Path:
        return self.registry.db_path

    def query_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def file_origins(self) -> list[dict[str, Any]]:
        return self.query_all(
            "SELECT account, onedrive_id, sha256, path_hint FROM file_origins ORDER BY account, onedrive_id"
        )

    def metadata_rows(self) -> list[dict[str, Any]]:
        return self.query_all(
            "SELECT account_name AS account, onedrive_id, size_bytes, modified_time, sha256 FROM metadata_index ORDER BY account_name, onedrive_id"
        )

    def accepted_rows(self) -> list[dict[str, Any]]:
        return self.query_all(
            "SELECT sha256, account, source_path FROM accepted_records ORDER BY id"
        )

    def terminal_events(self) -> list[dict[str, Any]]:
        return self.query_all(
            "SELECT batch_run_id, sequence_no, account, onedrive_id, sha256, action, reason, actor FROM ingest_terminal_audit ORDER BY id"
        )


@dataclass(frozen=True)
class IntegrationCycleResult:
    """End-to-end result bundle for one integration cycle."""

    app_config: AppConfig
    account: AccountConfig
    poll_result: Any
    ingest_result: IngestBatchResult | None
    staged_candidates: tuple[StagedCandidate, ...]
    replay_summary: dict[str, Any] | None
    registry_harness: RegistryHarness
    pending_root: Path
    quarantine_root: Path
    journal_path: Path


class FakeGraphFixture:
    """Queue delta pages and download responses for the real poll path."""

    def __init__(self) -> None:
        self._mapping: dict[str, list[FakeResponse | Exception]] = {}
        self._pages_by_account: dict[str, list[dict[str, Any]]] = {}

    @staticmethod
    def delta_item(
        *,
        item_id: str,
        name: str,
        size_bytes: int | None,
        download_url: str | None,
        modified_time: str = "2026-04-01T10:11:12Z",
        parent_path: str = "/drive/root:/Camera Roll/2026",
    ) -> dict[str, Any]:
        """Create a deterministic file delta item."""

        item: dict[str, Any] = {
            "id": item_id,
            "name": name,
            "file": {"mimeType": "image/heic"},
            "lastModifiedDateTime": modified_time,
            "parentReference": {"path": parent_path},
        }
        if size_bytes is not None:
            item["size"] = size_bytes
        if download_url is not None:
            item["@microsoft.graph.downloadUrl"] = download_url
        return item

    @staticmethod
    def deleted_item(*, item_id: str, name: str = "deleted.heic") -> dict[str, Any]:
        """Create a deterministic deleted/tombstone delta item."""

        return {"id": item_id, "name": name, "deleted": {}}

    def queue_account_pages(self, account: AccountConfig, pages: list[dict[str, Any]]) -> None:
        """Queue a complete delta sequence for one account."""

        self._pages_by_account[account.name] = pages
        if account.delta_cursor.exists() and account.delta_cursor.read_text(encoding="utf-8").strip():
            initial = account.delta_cursor.read_text(encoding="utf-8").strip()
        else:
            initial = self.initial_delta_url(account)
        current_url = initial
        for index, raw_payload in enumerate(pages):
            payload = json.loads(json.dumps(raw_payload))
            is_last = index == len(pages) - 1
            if is_last:
                payload.setdefault("@odata.deltaLink", f"https://delta/{account.name}/final")
            else:
                payload.setdefault("@odata.nextLink", f"https://delta/{account.name}/page/{index + 2}")
            self._mapping.setdefault(current_url, []).append(
                FakeResponse(status_code=200, text=json.dumps(payload))
            )
            current_url = payload.get("@odata.nextLink", current_url)

    def queue_download(
        self,
        url: str,
        *,
        status_code: int = 200,
        content: bytes = b"",
        chunks: list[bytes] | None = None,
        headers: dict[str, str] | None = None,
        iter_error: Exception | None = None,
        repeat: int = 1,
    ) -> None:
        """Queue one download response."""

        queue = self._mapping.setdefault(url, [])
        for _ in range(repeat):
            queue.append(
                FakeResponse(
                    status_code=status_code,
                    content=content,
                    chunks=list(chunks) if chunks is not None else None,
                    headers=dict(headers) if headers is not None else None,
                    iter_error=iter_error,
                )
            )

    def queue_get_exception(self, url: str, exc: Exception) -> None:
        """Queue one transport-level exception."""

        self._mapping.setdefault(url, []).append(exc)

    def build_client(self) -> FakeGraphClient:
        """Build a fake client for poll calls."""

        return FakeGraphClient(self._mapping)

    @staticmethod
    def initial_delta_url(account: AccountConfig) -> str:
        """Mirror the OneDrive client initial delta URL builder."""

        from urllib.parse import quote

        root = account.onedrive_root.strip()
        if not root.startswith("/"):
            root = "/" + root
        segments = [quote(segment, safe="") for segment in root.split("/") if segment]
        encoded_root = "/" + "/".join(segments)
        return f"https://graph.microsoft.com/v1.0/me/drive/root:{encoded_root}:/delta"


class CrashInjectionHelper:
    """Named crash hooks used by integration tests."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._monkeypatch = monkeypatch

    def after_storage_commit_before_registry_finalize(self, registry: Registry) -> None:
        """Crash after storage commit by failing registry finalize call."""

        original = registry.finalize_unknown_ingest
        triggered = False

        def _raise(*args: Any, **kwargs: Any) -> None:
            nonlocal triggered
            if not triggered:
                triggered = True
                raise RuntimeError("injected crash after storage commit")
            return original(*args, **kwargs)

        self._monkeypatch.setattr(registry, "finalize_unknown_ingest", _raise)

    def during_cross_pool_copy(self) -> None:
        """Crash after a partial cross-pool copy write."""

        from nightfall_photo_ingress.domain import storage as storage_module

        original_copy2 = storage_module.shutil.copy2

        def _crash_copy(src: Path, dst: Path) -> Path:
            original_copy2(src, dst)
            Path(dst).write_bytes(b"partial")
            raise RuntimeError("injected crash during cross-pool copy")

        self._monkeypatch.setattr(storage_module.shutil, "copy2", _crash_copy)

    def after_staging_write(self) -> None:
        """Crash after staged file write is finalized by Module 3."""

        from nightfall_photo_ingress.adapters.onedrive import client as client_module

        original_append = client_module._append_lifecycle_event
        triggered = False

        def _raise_after_staging_write(*args: Any, **kwargs: Any) -> None:
            nonlocal triggered
            original_append(*args, **kwargs)
            if triggered:
                return
            if kwargs.get("event_type") == "ready_for_hash":
                triggered = True
                raise RuntimeError("injected crash after staging write")

        self._monkeypatch.setattr(client_module, "_append_lifecycle_event", _raise_after_staging_write)

    def after_hash_complete(self, engine: IngestDecisionEngine) -> None:
        """Crash after hash completion is journaled in Module 4."""

        original_append = engine._journal_append
        triggered = False

        def _raise_after_hash(*args: Any, **kwargs: Any) -> None:
            nonlocal triggered
            original_append(*args, **kwargs)
            if triggered:
                return
            if kwargs.get("phase") == "hash_completed":
                triggered = True
                raise RuntimeError("injected crash after hash complete")

        self._monkeypatch.setattr(engine, "_journal_append", _raise_after_hash)

    def during_journal_append(self, engine: IngestDecisionEngine) -> None:
        """Crash when journal append is attempted during ingest."""

        if engine._journal is None:
            raise AssertionError("journal is required for this crash hook")
        original_append = engine._journal.append
        triggered = False

        def _raise_append(*args: Any, **kwargs: Any) -> None:
            nonlocal triggered
            if not triggered:
                triggered = True
                raise RuntimeError("injected crash during journal append")
            return original_append(*args, **kwargs)

        self._monkeypatch.setattr(engine._journal, "append", _raise_append)

    def during_journal_replay(self, engine: IngestDecisionEngine) -> None:
        """Crash while replay reads journal records."""

        if engine._journal is None:
            raise AssertionError("journal is required for this crash hook")

        def _raise_read_all() -> list[Any]:
            raise RuntimeError("injected crash during journal replay")

        self._monkeypatch.setattr(engine._journal, "read_all", _raise_read_all)


@pytest.fixture
def registry_fixture(tmp_path: Path) -> RegistryHarness:
    """Create an initialized registry plus SQL assertion helpers."""

    registry = Registry(tmp_path / "registry.db")
    registry.initialize()
    return RegistryHarness(registry=registry)


@pytest.fixture
def app_config_fixture(tmp_path: Path, registry_fixture: RegistryHarness):
    """Build deterministic AppConfig instances for integration tests."""

    def _make(
        *,
        account_specs: list[dict[str, Any]] | None = None,
        core_overrides: dict[str, Any] | None = None,
    ) -> AppConfig:
        specs = account_specs or [
            {"name": "lisa", "root": "/Camera Roll", "enabled": True, "max_downloads": 10}
        ]
        accounts: list[AccountConfig] = []
        for spec in specs:
            name = spec["name"]
            accounts.append(
                AccountConfig(
                    name=name,
                    enabled=spec.get("enabled", True),
                    display_name=spec.get("display_name", name),
                    provider="onedrive",
                    authority="https://login.microsoftonline.com/consumers",
                    client_id=f"cid-{name}",
                    onedrive_root=spec.get("root", "/Camera Roll"),
                    token_cache=tmp_path / name / "token.json",
                    delta_cursor=tmp_path / name / "cursor.txt",
                    max_downloads=spec.get("max_downloads", 10),
                )
            )

        core_values = {
            "config_version": 1,
            "poll_interval_minutes": 15,
            "process_accounts_in_config_order": True,
            "staging_path": tmp_path / "staging",
            "pending_path": tmp_path / "pending",
            "accepted_path": tmp_path / "accepted",
            "accepted_storage_template": "{yyyy}/{mm}/{original}",
            "rejected_path": tmp_path / "rejected",
            "trash_path": tmp_path / "trash",
            "registry_path": registry_fixture.db_path,
            "staging_on_same_pool": True,
            "storage_template": "{yyyy}/{mm}/{original}",
            "verify_sha256_on_first_download": True,
            "max_downloads_per_poll": 100,
            "max_poll_runtime_seconds": 300,
            "tmp_ttl_minutes": 120,
            "failed_ttl_hours": 24,
            "orphan_ttl_days": 7,
            "live_photo_capture_tolerance_seconds": 3,
            "live_photo_stem_mode": "exact_stem",
            "live_photo_component_order": "photo_first",
            "live_photo_conflict_policy": "nearest_capture_time",
            "sync_hash_import_enabled": True,
            "sync_hash_import_path": tmp_path / "pictures",
            "sync_hash_import_glob": ".hashes.sha1",
            "integrity_mode": "strict",
            "drift_warning_threshold_ratio": 0.05,
            "drift_critical_threshold_ratio": 0.20,
            "drift_min_events_for_evaluation": 20,
            "drift_fail_fast_enabled": True,
            "delta_loop_resync_threshold": 3,
            "delta_breaker_ghost_threshold": 10,
            "delta_breaker_stale_page_threshold": 10,
            "delta_breaker_cooldown_seconds": 300,
            "account_worker_count": 1,
            "adaptive_backpressure_enabled": True,
            "backpressure_retry_threshold": 20,
            "backpressure_transport_error_threshold": 5,
            "backpressure_cooldown_seconds": 300,
        }
        if core_overrides:
            core_values.update(core_overrides)

        return AppConfig(
            source_path=tmp_path / "photo-ingress.conf",
            core=CoreConfig(**core_values),
            logging=LoggingConfig(log_level="INFO", console_format="json"),
            accounts=tuple(accounts),
        )

    return _make


@pytest.fixture
def fake_graph_fixture() -> FakeGraphFixture:
    """Provide deterministic delta pages and download streams."""

    return FakeGraphFixture()


@pytest.fixture
def ingest_engine_fixture(tmp_path: Path, registry_fixture: RegistryHarness):
    """Construct ingest engine instances with journaling enabled."""

    def _make(*, journal_name: str = "ingest.journal") -> IngestDecisionEngine:
        return IngestDecisionEngine(
            registry_fixture.registry,
            journal_path=tmp_path / journal_name,
        )

    return _make


@pytest.fixture
def crash_injection_fixture(monkeypatch: pytest.MonkeyPatch) -> CrashInjectionHelper:
    """Provide named interruption points for crash-boundary tests."""

    return CrashInjectionHelper(monkeypatch)


@pytest.fixture
def fs_snapshot_fixture():
    """Capture directory trees as sorted relative paths."""

    def _snapshot(root: Path) -> tuple[str, ...]:
        if not root.exists():
            return tuple()
        entries: list[str] = []
        for path in sorted(root.rglob("*")):
            rel = path.relative_to(root)
            suffix = "/" if path.is_dir() else ""
            entries.append(f"{rel}{suffix}")
        return tuple(entries)

    return _snapshot


@pytest.fixture
def deterministic_time_fixture(monkeypatch: pytest.MonkeyPatch):
    """Freeze ingest/journal wall-clock calls for deterministic assertions."""

    class _FrozenDateTime:
        _frozen: datetime = datetime(2026, 4, 1, 12, 0, 0, tzinfo=UTC)

        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return cls._frozen
            return cls._frozen.astimezone(tz)

        @classmethod
        def fromisoformat(cls, value: str):
            return datetime.fromisoformat(value)

    from nightfall_photo_ingress.domain import ingest as ingest_module
    from nightfall_photo_ingress.domain import journal as journal_module

    monkeypatch.setattr(ingest_module, "datetime", _FrozenDateTime)
    monkeypatch.setattr(journal_module, "datetime", _FrozenDateTime)

    def _set(iso_value: str) -> None:
        _FrozenDateTime._frozen = datetime.fromisoformat(iso_value.replace("Z", "+00:00"))

    return _set


@pytest.fixture
def audit_reader_fixture(registry_fixture: RegistryHarness):
    """Expose typed audit and terminal event readers for assertions."""

    class _AuditReader:
        def audit_actions(self, sha256: str) -> tuple[str, ...]:
            return tuple(event.action for event in registry_fixture.registry.list_audit_events(sha256=sha256))

        def audit_reasons(self, sha256: str) -> tuple[str, ...]:
            return tuple(event.reason for event in registry_fixture.registry.list_audit_events(sha256=sha256))

        def audit_actors(self, sha256: str) -> tuple[str, ...]:
            return tuple(event.actor for event in registry_fixture.registry.list_audit_events(sha256=sha256))

        def terminal_actions(self) -> tuple[str, ...]:
            return tuple(row["action"] for row in registry_fixture.terminal_events())

        def terminal_reasons(self) -> tuple[str, ...]:
            return tuple(row["reason"] for row in registry_fixture.terminal_events())

        def terminal_actors(self) -> tuple[str, ...]:
            return tuple(row["actor"] for row in registry_fixture.terminal_events())

        def batch_run_ids(self) -> tuple[str, ...]:
            return tuple(row["batch_run_id"] for row in registry_fixture.terminal_events())

        def sequence_numbers(self) -> tuple[int, ...]:
            return tuple(int(row["sequence_no"]) for row in registry_fixture.terminal_events())

        def terminal_events(self) -> list[dict[str, Any]]:
            return registry_fixture.terminal_events()

    return _AuditReader()


@pytest.fixture
def poll_and_ingest_fixture(
    app_config_fixture,
    registry_fixture: RegistryHarness,
    fake_graph_fixture: FakeGraphFixture,
    ingest_engine_fixture,
):
    """Run a full OneDrive client to ingest pipeline cycle."""

    def _run(
        *,
        pages: list[dict[str, Any]],
        downloads: dict[str, dict[str, Any]],
        app_config: AppConfig | None = None,
        account_name: str = "lisa",
        run_ingest: bool = True,
        input_schema_version: int = INGEST_INPUT_SCHEMA_VERSION,
        pre_hash_size_verify: bool = True,
        zero_byte_policy: str = "allow",
        worker_count: int = 1,
        storage_template: str | None = None,
        replay_after_ingest: bool = False,
    ) -> IntegrationCycleResult:
        config = app_config or app_config_fixture()
        account = next(acct for acct in config.accounts if acct.name == account_name)
        fake_graph_fixture.queue_account_pages(account, pages)
        for url, params in downloads.items():
            fake_graph_fixture.queue_download(url, **params)

        poll_result = poll_accounts(
            config,
            account_name=account_name,
            auth_client=FakeAuthClient(),
            http_client_factory=fake_graph_fixture.build_client,
            sleeper=lambda _seconds: None,
            jitter_fn=lambda: 0.0,
        )[0]

        handoff_candidates = load_boundary_handoff_candidates(
            poll_result.payload.handoff_manifest_path
        )
        staged_candidates = tuple(
            StagedCandidate(
                account_name=candidate.account_name,
                onedrive_id=candidate.onedrive_id,
                original_filename=candidate.original_filename,
                relative_path=(
                    candidate.relative_path
                    if candidate.relative_path.startswith("/")
                    else f"/{candidate.relative_path}"
                ),
                modified_time=candidate.modified_time,
                size_bytes=candidate.size_bytes,
                staging_path=candidate.staging_path,
            )
            for candidate in handoff_candidates
        )

        journal_path = config.core.staging_path / "ingest.journal"
        engine = ingest_engine_fixture(journal_name="ingest.journal")
        ingest_result: IngestBatchResult | None = None
        if run_ingest:
            ingest_result = engine.process_batch(
                candidates=list(staged_candidates),
                pending_root=config.core.pending_path,
                storage_template=storage_template or config.core.storage_template,
                staging_on_same_pool=config.core.staging_on_same_pool,
                input_schema_version=input_schema_version,
                pre_hash_size_verify=pre_hash_size_verify,
                zero_byte_policy=zero_byte_policy,
                quarantine_dir=config.core.staging_path / account.name / "_quarantine",
                worker_count=worker_count,
                live_photo_heuristics=LivePhotoHeuristics(
                    capture_tolerance_seconds=config.core.live_photo_capture_tolerance_seconds,
                    stem_mode=config.core.live_photo_stem_mode,
                    component_order=config.core.live_photo_component_order,
                    conflict_policy=config.core.live_photo_conflict_policy,
                ),
            )

        replay_summary = None
        if replay_after_ingest:
            replay_summary = engine.replay_interrupted_operations()

        return IntegrationCycleResult(
            app_config=config,
            account=account,
            poll_result=poll_result,
            ingest_result=ingest_result,
            staged_candidates=staged_candidates,
            replay_summary=replay_summary,
            registry_harness=registry_fixture,
            pending_root=config.core.pending_path,
            quarantine_root=config.core.staging_path / account.name / "_quarantine",
            journal_path=journal_path,
        )

    return _run