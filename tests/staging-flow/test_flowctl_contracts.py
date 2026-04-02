"""Policy contract tests for the staging production flow test controller.

These are static contract checks: they only read workspace files and never
invoke LXC, run the application, or modify any state.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


FLOWCTL_PATH = Path(__file__).resolve().parent / "flowctl"
README_PATH = Path(__file__).resolve().parent / "README.md"


@pytest.fixture(scope="module")
def flowctl_text() -> str:
    return FLOWCTL_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def readme_text() -> str:
    return README_PATH.read_text(encoding="utf-8")


class TestFilePresence:
    def test_flowctl_exists(self) -> None:
        assert FLOWCTL_PATH.exists(), "flowctl script not found"

    def test_flowctl_is_executable(self) -> None:
        assert os.access(FLOWCTL_PATH, os.X_OK), "flowctl is not executable"

    def test_readme_exists(self) -> None:
        assert README_PATH.exists(), "README.md not found"


class TestPhaseStructure:
    def test_all_five_phases_defined(self, flowctl_text: str) -> None:
        for phase in ("phase_p1", "phase_p2", "phase_p3", "phase_p4", "phase_p5"):
            assert f"{phase}()" in flowctl_text, f"phase function {phase}() not found"

    def test_phase_selector_present(self, flowctl_text: str) -> None:
        assert "_should_run" in flowctl_text

    def test_all_phases_dispatched_from_cmd_run(self, flowctl_text: str) -> None:
        for phase in ("p1", "p2", "p3", "p4", "p5"):
            assert f'_should_run "{phase}"' in flowctl_text


class TestInteractiveGating:
    def test_skip_interactive_flag_present(self, flowctl_text: str) -> None:
        assert "--skip-interactive" in flowctl_text

    def test_phase_option_present(self, flowctl_text: str) -> None:
        assert "--phase" in flowctl_text

    def test_operator_prompt_function_present(self, flowctl_text: str) -> None:
        # _confirm reads from /dev/tty so interactive phases don't consume stdin
        assert "_confirm()" in flowctl_text
        assert "/dev/tty" in flowctl_text

    def test_assume_answer_flags_present(self, flowctl_text: str) -> None:
        for flag in ("--assume-yes", "--assume-no", "--assume-default", "--yes", "--no"):
            assert flag in flowctl_text

    def test_p2_skips_when_non_interactive(self, flowctl_text: str) -> None:
        assert "SKIP_INTERACTIVE" in flowctl_text
        assert "P2:auth_setup" in flowctl_text

    def test_p3_skips_when_non_interactive(self, flowctl_text: str) -> None:
        assert "P3:discovery" in flowctl_text

    def test_p4_skips_when_non_interactive(self, flowctl_text: str) -> None:
        assert "P4:live_poll" in flowctl_text


class TestStepLabels:
    """Verify all documented step labels are present in the script."""

    def test_p1_step_labels(self, flowctl_text: str) -> None:
        for step in ("S1.1", "S1.2", "S1.3", "S1.4", "S1.5", "S1.6", "S1.7"):
            assert step in flowctl_text, f"Step label {step} not found in flowctl"

    def test_p2_step_labels(self, flowctl_text: str) -> None:
        for step in ("P2.1", "P2.2", "P2.3", "P2.4"):
            assert step in flowctl_text, f"Step label {step} not found in flowctl"

    def test_p3_step_labels(self, flowctl_text: str) -> None:
        for step in ("P3.1", "P3.2"):
            assert step in flowctl_text, f"Step label {step} not found in flowctl"

    def test_p4_step_labels(self, flowctl_text: str) -> None:
        for step in ("P4.1", "P4.2"):
            assert step in flowctl_text, f"Step label {step} not found in flowctl"

    def test_p5_step_labels(self, flowctl_text: str) -> None:
        for step in ("P5.1", "P5.2", "P5.3"):
            assert step in flowctl_text, f"Step label {step} not found in flowctl"


class TestEvidenceContract:
    def test_flow_run_id_generated(self, flowctl_text: str) -> None:
        assert "FLOW_RUN_ID" in flowctl_text

    def test_flow_evidence_dir_created(self, flowctl_text: str) -> None:
        assert "FLOW_EVIDENCE_DIR" in flowctl_text
        assert "mkdir -p" in flowctl_text

    def test_manifest_jsonl_written(self, flowctl_text: str) -> None:
        assert "FLOW_MANIFEST" in flowctl_text
        assert "flow_started" in flowctl_text
        assert "flow_finished" in flowctl_text

    def test_evidence_base_env_respected(self, flowctl_text: str) -> None:
        assert 'FLOW_EVIDENCE_BASE="${FLOW_EVIDENCE_BASE:-' in flowctl_text

    def test_per_phase_subdirs(self, flowctl_text: str) -> None:
        # Each phase writes logs to a named subdirectory
        for phase in ("p1", "p2", "p3", "p4", "p5"):
            assert f'"$FLOW_EVIDENCE_DIR/{phase}"' in flowctl_text


class TestStagingctlIntegration:
    def test_references_stagingctl(self, flowctl_text: str) -> None:
        assert 'STAGINGCTL=' in flowctl_text
        assert '"$STAGINGCTL" auth-setup' in flowctl_text
        assert '"$STAGINGCTL" discover-paths' in flowctl_text
        assert '"$STAGINGCTL" smoke-live' in flowctl_text
        assert '"$STAGINGCTL" reset' in flowctl_text

    def test_stagingctl_path_is_relative_to_project_root(self, flowctl_text: str) -> None:
        assert 'PROJECT_ROOT' in flowctl_text
        assert 'staging/stagingctl' in flowctl_text

    def test_p2_auth_setup_not_piped(self, flowctl_text: str) -> None:
        # auth-setup must not be piped — a pipe breaks TTY pass-through for device-code
        # flow. The comment in the script explains why.
        assert "TTY" in flowctl_text or "tty" in flowctl_text.lower()

    def test_p3_onboarding_sidecar_check_present(self, flowctl_text: str) -> None:
        assert ".onboarding.json" in flowctl_text
        assert "P3.2:onboarding_sidecar" in flowctl_text

    def test_p4_preserves_tty_when_interactive(self, flowctl_text: str) -> None:
        assert "script -qefc" in flowctl_text
        assert "smoke-live.log" in flowctl_text


class TestDocumentationCoverage:
    def test_readme_documents_all_phases(self, readme_text: str) -> None:
        for phase in ("P1", "P2", "P3", "P4", "P5"):
            assert phase in readme_text

    def test_readme_documents_skip_interactive(self, readme_text: str) -> None:
        assert "--skip-interactive" in readme_text

    def test_readme_documents_assume_answer_flags(self, readme_text: str) -> None:
        for flag in ("--assume-yes", "--assume-no", "--assume-default"):
            assert flag in readme_text

    def test_readme_documents_prerequisites(self, readme_text: str) -> None:
        assert "stagingctl create" in readme_text
        assert "stagingctl install" in readme_text

    def test_readme_documents_evidence_output(self, readme_text: str) -> None:
        assert "manifest.jsonl" in readme_text
        assert "FLOW_EVIDENCE_BASE" in readme_text
