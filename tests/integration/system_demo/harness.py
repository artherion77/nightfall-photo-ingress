from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class LayerRationale:
    defect_class: str
    candidate_layers_considered: tuple[str, ...]
    selected_layer: str
    why_lower_layers_are_insufficient: str
    flake_risk_controls: tuple[str, ...]


@dataclass(frozen=True)
class BrowserScenarioContract:
    scenario_id: str
    title: str
    rationale: LayerRationale


@dataclass
class ScenarioResult:
    scenario_id: str
    passed: bool
    assertions: tuple[str, ...]
    artifact_path: str


class BrowserHarness(Protocol):
    def run_staging_keyboard_triage(self) -> ScenarioResult:
        ...

    def run_blocklist_confirm_cancel(self) -> ScenarioResult:
        ...

    def run_blocklist_error_feedback(self) -> ScenarioResult:
        ...


@dataclass
class DemoBrowserHarness:
    artifact_root: Path
    events: list[str] = field(default_factory=list)

    def _artifact_for(self, scenario_id: str) -> str:
        path = self.artifact_root / scenario_id
        path.mkdir(parents=True, exist_ok=True)
        return str(path)

    def run_staging_keyboard_triage(self) -> ScenarioResult:
        # Simulate browser-only keyboard choreography and action dispatch semantics.
        self.events.extend([
            "keydown:ArrowRight",
            "active_index:1",
            "keydown:ArrowLeft",
            "active_index:0",
            "keydown:A",
            "post:/api/triage/accept",
            "keydown:R",
            "post:/api/triage/reject",
            "keydown:D",
            "post:/api/triage/defer",
        ])
        return ScenarioResult(
            scenario_id="staging.keyboard-triage.spec.ts",
            passed=True,
            assertions=(
                "arrow-navigation-index-bounds",
                "single-request-per-action",
                "count-decrements-after-success",
            ),
            artifact_path=self._artifact_for("staging.keyboard-triage"),
        )

    def run_blocklist_confirm_cancel(self) -> ScenarioResult:
        # Simulate dialog open/cancel/confirm and overlay propagation semantics.
        self.events.extend([
            "click:delete",
            "dialog:open",
            "click:cancel",
            "dialog:closed-no-delete",
            "click:delete",
            "dialog:open",
            "click:overlay",
            "dialog:closed",
            "click:delete",
            "dialog:open",
            "click:confirm",
            "delete:single-request",
            "row:removed",
        ])
        return ScenarioResult(
            scenario_id="blocklist.delete-confirm.spec.ts",
            passed=True,
            assertions=(
                "cancel-no-delete-request",
                "overlay-close-content-no-close",
                "confirm-single-delete-row-removed",
            ),
            artifact_path=self._artifact_for("blocklist.delete-confirm"),
        )

    def run_blocklist_error_feedback(self) -> ScenarioResult:
        # Simulate forced API failure with visible error feedback and rollback.
        self.events.extend([
            "click:confirm-delete",
            "delete:500",
            "row:rollback-visible",
            "error-feedback:visible",
        ])
        return ScenarioResult(
            scenario_id="blocklist.delete-error-feedback.spec.ts",
            passed=True,
            assertions=(
                "forced-failure-observed",
                "optimistic-rollback-visible",
                "error-feedback-visible-within-2s",
            ),
            artifact_path=self._artifact_for("blocklist.delete-error-feedback"),
        )


def variant_b_browser_contracts() -> tuple[BrowserScenarioContract, ...]:
    common_candidates = ("pytest", "vitest", "playwright")
    common_controls = (
        "stable-selectors",
        "deterministic-waits",
        "isolated-fixtures",
        "artifact-path-output",
    )
    return (
        BrowserScenarioContract(
            scenario_id="staging.keyboard-triage.spec.ts",
            title="Staging keyboard triage",
            rationale=LayerRationale(
                defect_class="keyboard_choreography_and_focus_order",
                candidate_layers_considered=common_candidates,
                selected_layer="playwright",
                why_lower_layers_are_insufficient="Needs real keyboard events and active-card focus transitions in a browser loop.",
                flake_risk_controls=common_controls,
            ),
        ),
        BrowserScenarioContract(
            scenario_id="blocklist.delete-confirm.spec.ts",
            title="Blocklist confirm/cancel dialog semantics",
            rationale=LayerRationale(
                defect_class="overlay_propagation_and_dialog_interaction_semantics",
                candidate_layers_considered=common_candidates,
                selected_layer="playwright",
                why_lower_layers_are_insufficient="Needs overlay click propagation and modal interaction behavior in a real DOM runtime.",
                flake_risk_controls=common_controls,
            ),
        ),
        BrowserScenarioContract(
            scenario_id="blocklist.delete-error-feedback.spec.ts",
            title="Blocklist delete failure visible feedback",
            rationale=LayerRationale(
                defect_class="visible_feedback_and_optimistic_rollback",
                candidate_layers_considered=common_candidates,
                selected_layer="playwright",
                why_lower_layers_are_insufficient="Needs timing-visible feedback checks coupled with rollback visibility on failed browser action.",
                flake_risk_controls=common_controls,
            ),
        ),
    )


def run_variant_b_demo(harness: BrowserHarness) -> tuple[ScenarioResult, ...]:
    return (
        harness.run_staging_keyboard_triage(),
        harness.run_blocklist_confirm_cancel(),
        harness.run_blocklist_error_feedback(),
    )
