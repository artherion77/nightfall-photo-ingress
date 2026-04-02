"""Secret scan unit tests — no container required.

Tests the secret_scan module's pattern detection and entropy scanner
in isolation. These run as fast pure-Python tests.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_STAGING_DIR = Path(__file__).parent.parent.parent / "staging"
if str(_STAGING_DIR) not in sys.path:
    sys.path.insert(0, str(_STAGING_DIR))

from evidence.secret_scan import Finding, _shannon_entropy, scan_file, scan_directory

pytestmark = pytest.mark.staging


# ── entropy helper ────────────────────────────────────────────────────────────

class TestShannonEntropy:
    def test_uniform_string_has_maximum_entropy(self):
        # Each character unique → max entropy
        s = "abcdefghijklmnopqrstuvwxyz0123"
        e = _shannon_entropy(s)
        assert e > 4.0

    def test_repeated_string_has_zero_entropy(self):
        e = _shannon_entropy("aaaaaaaaaaaaaaaaaaa")
        assert e == pytest.approx(0.0)

    def test_empty_string_returns_zero(self):
        assert _shannon_entropy("") == 0.0

    def test_high_entropy_base64_token(self):
        # Simulate a high-entropy token (32 random-ish chars)
        token = "aB3dEf9HiJkLmN0pQrStUvWxYz123456"
        assert _shannon_entropy(token) > 4.0


# ── pattern detection ─────────────────────────────────────────────────────────

class TestPatternDetection:
    def test_bearer_token_in_log(self, tmp_path):
        log = tmp_path / "poll.log"
        log.write_text(
            '{"level":"DEBUG","msg":"auth","header":"Bearer eyJhbGciOiJSUzI1NiJ9.AAABBBCCC"}\n'
        )
        findings = scan_file(log)
        kinds = [f.rule for f in findings]
        assert "bearer_token" in kinds

    def test_access_token_in_json(self, tmp_path):
        log = tmp_path / "auth.json"
        log.write_text('{"access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.payload123"}\n')
        findings = scan_file(log)
        rules = [f.rule for f in findings]
        assert "access_token_json_key" in rules

    def test_refresh_token_in_json(self, tmp_path):
        log = tmp_path / "cache.json"
        log.write_text('{"refresh_token": "0.AAAA-BBBB-CCCC-valid-token-here123456789"}\n')
        findings = scan_file(log)
        rules = [f.rule for f in findings]
        assert "refresh_token_json_key" in rules

    def test_pem_private_key_header(self, tmp_path):
        log = tmp_path / "key.pem"
        log.write_text("-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAK...\n")
        findings = scan_file(log)
        rules = [f.rule for f in findings]
        assert "private_key_pem" in rules

    def test_placeholder_config_is_clean(self, tmp_path):
        cfg = tmp_path / "photo-ingress.conf"
        cfg.write_text(
            "[core]\nconfig_version = 2\n"
            "[account.staging]\nclient_id = STAGING_CLIENT_ID_PLACEHOLDER\n"
        )
        findings = scan_file(cfg)
        # Placeholders should not trigger findings
        assert not findings, f"Unexpected findings: {findings}"

    def test_normal_log_line_is_clean(self, tmp_path):
        log = tmp_path / "clean.log"
        log.write_text(
            '{"level":"INFO","msg":"poll completed","account":"staging","candidates":3}\n'
        )
        findings = scan_file(log)
        assert not findings, f"Unexpected findings: {findings}"


# ── redaction ─────────────────────────────────────────────────────────────────

class TestSnippetRedaction:
    def test_bearer_snippet_is_redacted(self, tmp_path):
        log = tmp_path / "poll.log"
        real_token = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.payload"
        log.write_text(f"Bearer {real_token}\n")
        findings = scan_file(log)
        assert findings
        for f in findings:
            assert real_token not in f.snippet, "Full token must not appear in snippet"
            assert f.snippet.endswith("***"), f"Snippet not redacted: {f.snippet!r}"


# ── directory scan ────────────────────────────────────────────────────────────

class TestDirectoryScan:
    def test_clean_directory_returns_no_findings(self, tmp_path):
        (tmp_path / "manifest.jsonl").write_text(
            '{"event":"run_started","run_id":"x","ts":"2026-04-01T00:00:00Z"}\n'
        )
        (tmp_path / "counters.json").write_text('{"requests":3,"throttles":0}\n')
        findings = scan_directory(tmp_path)
        assert not findings

    def test_leaked_token_in_subdirectory_is_found(self, tmp_path):
        sub = tmp_path / "logs"
        sub.mkdir()
        (sub / "debug.log").write_text(
            '{"Authorization": "Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.full_token_here"}\n'
        )
        findings = scan_directory(tmp_path)
        assert findings

    def test_binary_db_file_is_skipped(self, tmp_path):
        # Write a file with a .db extension that contains a fake secret pattern —
        # the scanner should skip it because it's a binary extension.
        (tmp_path / "registry.db").write_bytes(b"Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.xxx")
        findings = scan_directory(tmp_path)
        assert not findings

    def test_finding_line_numbers_are_1_based(self, tmp_path):
        log = tmp_path / "out.log"
        log.write_text("line 1 - clean\nline 2 - Bearer eyJhbGciOiJSUzI1NiJ9.BBBBBBBBBBBBBBBB\n")
        findings = scan_file(log)
        assert findings
        assert findings[0].line_number == 2


# ── CLI (main) ────────────────────────────────────────────────────────────────

class TestCLI:
    def test_clean_directory_exits_0(self, tmp_path):
        from evidence.secret_scan import main
        rc = main([str(tmp_path)])
        assert rc == 0

    def test_directory_with_leak_exits_1(self, tmp_path):
        from evidence.secret_scan import main
        (tmp_path / "leak.log").write_text(
            "Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.payload_data_here\n"
        )
        rc = main([str(tmp_path)])
        assert rc == 1

    def test_nonexistent_directory_exits_2(self, tmp_path):
        from evidence.secret_scan import main
        rc = main([str(tmp_path / "nonexistent")])
        assert rc == 2

    def test_json_output_is_parseable(self, tmp_path, capsys):
        import json
        from evidence.secret_scan import main
        rc = main(["--json", str(tmp_path)])
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "findings" in data
        assert "finding_count" in data
        assert rc == 0
