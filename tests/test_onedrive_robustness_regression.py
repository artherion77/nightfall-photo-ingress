"""Robustness regression suite for OneDrive client behavior.

These tests intentionally combine multiple failure modes in one flow to prevent
future regressions across chunk boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from nightfall_photo_ingress.config import AccountConfig
from nightfall_photo_ingress.onedrive.client import GraphError, poll_account_once


@dataclass
class _FakeResponse:
    status_code: int
    text: str = "{}"
    headers: dict[str, str] | None = None
    content: bytes = b""

    def __post_init__(self) -> None:
        if self.headers is None:
            self.headers = {}

    def iter_bytes(self, chunk_size: int = 1024 * 1024):
        # Return payload in chunks to exercise streaming paths.
        for index in range(0, len(self.content), chunk_size):
            yield self.content[index : index + chunk_size]


class _FakeClient:
    def __init__(self, mapping: dict[str, list[_FakeResponse]]) -> None:
        self._mapping = mapping

    def get(self, url: str, *args: Any, **kwargs: Any) -> _FakeResponse:
        _ = args
        _ = kwargs
        queue = self._mapping.get(url)
        if not queue:
            raise AssertionError(f"Unexpected URL requested: {url}")
        return queue.pop(0)


def _make_account(tmp_path: Path, name: str, root: str) -> AccountConfig:
    return AccountConfig(
        name=name,
        enabled=True,
        display_name=name,
        provider="onedrive",
        authority="https://login.microsoftonline.com/consumers",
        client_id=f"cid-{name}",
        onedrive_root=root,
        token_cache=tmp_path / name / "token.json",
        delta_cursor=tmp_path / name / "cursor.txt",
        max_downloads=10,
    )


@pytest.mark.robustness
def test_robustness_combines_auth_refresh_and_throttled_download_retry(
    tmp_path: Path,
) -> None:
    """401 refresh and throttled download should recover in one poll cycle."""

    account = _make_account(tmp_path, "alice", "/Camera Roll")
    root_delta = "https://graph.microsoft.com/v1.0/me/drive/root:/Camera%20Roll:/delta"

    refresh_calls: list[str] = []

    def refresh() -> str:
        refresh_calls.append("refresh")
        return "token-refreshed"

    client = _FakeClient(
        {
            root_delta: [
                _FakeResponse(status_code=401),
                _FakeResponse(
                    status_code=200,
                    text=(
                        '{"value":[{"id":"a1","name":"IMG_1.HEIC","file":{},'
                        '"size":7,"@microsoft.graph.downloadUrl":"https://download/a1"}],'
                        '"@odata.deltaLink":"https://delta/final"}'
                    ),
                ),
            ],
            "https://download/a1": [
                _FakeResponse(status_code=503, headers={"Retry-After": "0"}),
                _FakeResponse(status_code=200, content=b"payload"),
            ],
        }
    )

    downloaded, candidate_count, ghost_counts, anomaly_counts = poll_account_once(
        account=account,
        staging_root=tmp_path / "staging",
        access_token="token-initial",
        refresh_access_token=refresh,
        http_client=client,
    )

    assert len(refresh_calls) == 1
    assert candidate_count == 1
    assert len(downloaded) == 1
    assert ghost_counts == {}
    assert anomaly_counts.get("diag_auth_refresh_attempt_total") == 1
    assert anomaly_counts.get("diag_auth_refresh_success_total") == 1
    assert anomaly_counts.get("diag_throttle_response_total", 0) >= 1
    assert anomaly_counts.get("diag_retry_attempt_total", 0) >= 1


@pytest.mark.robustness
def test_robustness_detects_nextlink_cycles_early(tmp_path: Path) -> None:
    """nextLink loops must fail with a deterministic explicit error code."""

    account = _make_account(tmp_path, "alice", "/Camera Roll")
    root_delta = "https://graph.microsoft.com/v1.0/me/drive/root:/Camera%20Roll:/delta"

    client = _FakeClient(
        {
            root_delta: [
                _FakeResponse(
                    status_code=200,
                    text='{"value":[],"@odata.nextLink":"https://next/same"}',
                )
            ],
            "https://next/same": [
                _FakeResponse(
                    status_code=200,
                    text='{"value":[],"@odata.nextLink":"https://next/same"}',
                )
            ],
        }
    )

    with pytest.raises(GraphError) as exc_info:
        poll_account_once(
            account=account,
            staging_root=tmp_path / "staging",
            access_token="token",
            http_client=client,
        )

    assert exc_info.value.code == "delta_nextlink_cycle_detected"


@pytest.mark.robustness
def test_robustness_classifies_ghost_after_empty_and_unreachable_download(
    tmp_path: Path,
) -> None:
    """Empty-body anomaly followed by unreachable URL should classify ghost item."""

    account = _make_account(tmp_path, "alice", "/Camera Roll")
    root_delta = "https://graph.microsoft.com/v1.0/me/drive/root:/Camera%20Roll:/delta"

    client = _FakeClient(
        {
            root_delta: [
                _FakeResponse(
                    status_code=200,
                    text=(
                        '{"value":[{"id":"g1","name":"VID_1.MOV","file":{},'
                        '"size":5,"@microsoft.graph.downloadUrl":"https://download/g1"}],'
                        '"@odata.deltaLink":"https://delta/final"}'
                    ),
                )
            ],
            "https://download/g1": [
                _FakeResponse(status_code=200, content=b""),
                _FakeResponse(status_code=404),
            ],
            "https://graph.microsoft.com/v1.0/me/drive/items/g1": [
                _FakeResponse(status_code=200, text='{"id":"g1","name":"VID_1.MOV"}'),
            ],
        }
    )

    downloaded, candidate_count, ghost_counts, anomaly_counts = poll_account_once(
        account=account,
        staging_root=tmp_path / "staging",
        access_token="token",
        http_client=client,
    )

    assert candidate_count == 1
    assert downloaded == []
    assert ghost_counts == {"ghost_missing_download_url_after_refresh": 1}
    assert anomaly_counts.get("diag_retry_attempt_total", 0) >= 1


@pytest.mark.robustness
def test_robustness_graph_errors_keep_query_strings_redacted(tmp_path: Path) -> None:
    """Operator-facing hints should never expose signed URL query parameters."""

    account = _make_account(tmp_path, "alice", "/Camera Roll")
    root_delta = "https://graph.microsoft.com/v1.0/me/drive/root:/Camera%20Roll:/delta"

    client = _FakeClient(
        {
            root_delta: [
                _FakeResponse(
                    status_code=500,
                    headers={"Retry-After": "0"},
                ),
                _FakeResponse(
                    status_code=500,
                    headers={"Retry-After": "0"},
                ),
                _FakeResponse(
                    status_code=500,
                    headers={"Retry-After": "0"},
                ),
                _FakeResponse(
                    status_code=500,
                    headers={"Retry-After": "0"},
                ),
            ]
        }
    )

    with pytest.raises(GraphError) as exc_info:
        poll_account_once(
            account=account,
            staging_root=tmp_path / "staging",
            access_token="token",
            http_client=client,
        )

    hint = exc_info.value.safe_hint
    assert "?" not in hint
    assert "token=" not in hint.lower()
