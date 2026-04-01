"""Live Photo pairing support for Module 5.

This module provides V1 pairing heuristics, deferred correlation for late-arriving
counterparts, and operator-facing diagnostics for unresolved candidates.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


PHOTO_EXTENSIONS = {".heic", ".jpg", ".jpeg", ".png"}
VIDEO_EXTENSIONS = {".mov", ".mp4", ".m4v"}

DEFAULT_CAPTURE_TOLERANCE_SECONDS = 3
DEFAULT_STEM_MODE = "exact_stem"
DEFAULT_COMPONENT_ORDER = "photo_first"
DEFAULT_CONFLICT_POLICY = "nearest_capture_time"


class LivePhotoError(RuntimeError):
    """Raised when live photo operations fail."""


@dataclass(frozen=True)
class LivePhotoHeuristics:
    """V1 pairing heuristics surfaced in config."""

    capture_tolerance_seconds: int = DEFAULT_CAPTURE_TOLERANCE_SECONDS
    stem_mode: str = DEFAULT_STEM_MODE
    component_order: str = DEFAULT_COMPONENT_ORDER
    conflict_policy: str = DEFAULT_CONFLICT_POLICY


@dataclass(frozen=True)
class LivePhotoCandidate:
    """Input candidate used for pairing."""

    account: str
    onedrive_id: str
    filename: str
    captured_at: str


@dataclass(frozen=True)
class LivePhotoPair:
    """Resolved photo+video pair."""

    account: str
    stem: str
    photo_onedrive_id: str
    video_onedrive_id: str


@dataclass(frozen=True)
class UnresolvedLivePhotoCandidate:
    """Operator-facing diagnostics row for unresolved candidates."""

    account: str
    onedrive_id: str
    filename: str
    component: str
    stem: str
    captured_at: str
    queued_at: str
    age_seconds: int


@dataclass(frozen=True)
class _Queued:
    candidate: LivePhotoCandidate
    component: str
    stem: str
    captured_at: datetime
    queued_at: datetime


def enforce_v1_defaults(heuristics: LivePhotoHeuristics) -> None:
    """Accept only V1 default heuristic values at runtime."""

    if heuristics.capture_tolerance_seconds != DEFAULT_CAPTURE_TOLERANCE_SECONDS:
        raise LivePhotoError(
            "V1 runtime accepts only live_photo_capture_tolerance_seconds="
            f"{DEFAULT_CAPTURE_TOLERANCE_SECONDS}"
        )
    if heuristics.stem_mode != DEFAULT_STEM_MODE:
        raise LivePhotoError(
            "V1 runtime accepts only "
            f"live_photo_stem_mode={DEFAULT_STEM_MODE}"
        )
    if heuristics.component_order != DEFAULT_COMPONENT_ORDER:
        raise LivePhotoError(
            "V1 runtime accepts only "
            f"live_photo_component_order={DEFAULT_COMPONENT_ORDER}"
        )
    if heuristics.conflict_policy != DEFAULT_CONFLICT_POLICY:
        raise LivePhotoError(
            "V1 runtime accepts only "
            f"live_photo_conflict_policy={DEFAULT_CONFLICT_POLICY}"
        )


class DeferredPairQueue:
    """In-memory deferred queue that resolves late-arriving pair members."""

    def __init__(self, heuristics: LivePhotoHeuristics) -> None:
        enforce_v1_defaults(heuristics)
        self._heuristics = heuristics
        self._queued: list[_Queued] = []

    def ingest(self, candidate: LivePhotoCandidate) -> LivePhotoPair | None:
        """Ingest one candidate and return a pair when counterpart is available."""

        component = _classify_component(candidate.filename)
        if component is None:
            return None

        captured_at = _parse_iso(candidate.captured_at)
        stem = _stem(candidate.filename)
        counterpart_component = "video" if component == "photo" else "photo"

        eligible = [
            queued
            for queued in self._queued
            if queued.candidate.account == candidate.account
            and queued.stem == stem
            and queued.component == counterpart_component
            and _within_tolerance(
                queued.captured_at,
                captured_at,
                tolerance_seconds=self._heuristics.capture_tolerance_seconds,
            )
        ]

        if not eligible:
            self._queued.append(
                _Queued(
                    candidate=candidate,
                    component=component,
                    stem=stem,
                    captured_at=captured_at,
                    queued_at=datetime.now(UTC),
                )
            )
            return None

        counterpart = min(
            eligible,
            key=lambda queued: abs((queued.captured_at - captured_at).total_seconds()),
        )
        self._queued.remove(counterpart)

        if component == "photo":
            photo_id = candidate.onedrive_id
            video_id = counterpart.candidate.onedrive_id
        else:
            photo_id = counterpart.candidate.onedrive_id
            video_id = candidate.onedrive_id

        return LivePhotoPair(
            account=candidate.account,
            stem=stem,
            photo_onedrive_id=photo_id,
            video_onedrive_id=video_id,
        )

    def unresolved_diagnostics(self) -> tuple[UnresolvedLivePhotoCandidate, ...]:
        """Return unresolved queue diagnostics for operators."""

        now = datetime.now(UTC)
        rows = [
            UnresolvedLivePhotoCandidate(
                account=queued.candidate.account,
                onedrive_id=queued.candidate.onedrive_id,
                filename=queued.candidate.filename,
                component=queued.component,
                stem=queued.stem,
                captured_at=queued.candidate.captured_at,
                queued_at=queued.queued_at.isoformat(),
                age_seconds=max(0, int((now - queued.queued_at).total_seconds())),
            )
            for queued in self._queued
        ]
        rows.sort(key=lambda row: (row.account, row.stem, row.queued_at))
        return tuple(rows)

    def pop_aged_unresolved(self, *, max_age_seconds: int) -> tuple[UnresolvedLivePhotoCandidate, ...]:
        """Remove and return unresolved rows older than max_age_seconds."""

        now = datetime.now(UTC)
        keep: list[_Queued] = []
        removed: list[UnresolvedLivePhotoCandidate] = []

        for queued in self._queued:
            age = max(0, int((now - queued.queued_at).total_seconds()))
            if age >= max_age_seconds:
                removed.append(
                    UnresolvedLivePhotoCandidate(
                        account=queued.candidate.account,
                        onedrive_id=queued.candidate.onedrive_id,
                        filename=queued.candidate.filename,
                        component=queued.component,
                        stem=queued.stem,
                        captured_at=queued.candidate.captured_at,
                        queued_at=queued.queued_at.isoformat(),
                        age_seconds=age,
                    )
                )
            else:
                keep.append(queued)

        self._queued = keep
        removed.sort(key=lambda row: (row.account, row.stem, row.queued_at))
        return tuple(removed)


def _classify_component(filename: str) -> str | None:
    ext = Path(filename).suffix.lower()
    if ext in PHOTO_EXTENSIONS:
        return "photo"
    if ext in VIDEO_EXTENSIONS:
        return "video"
    return None


def _stem(filename: str) -> str:
    return Path(filename).stem


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _within_tolerance(a: datetime, b: datetime, *, tolerance_seconds: int) -> bool:
    return abs((a - b).total_seconds()) <= tolerance_seconds
