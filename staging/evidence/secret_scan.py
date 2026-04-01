#!/usr/bin/env python3
"""Secret and high-entropy leak scanner for staging evidence directories.

Can be run standalone (pushed to the container) or imported as a module.

Exit codes:
  0  — no findings
  1  — one or more findings (potential leaks)
  2  — usage error

Usage::
    python3 secret_scan.py /var/lib/ingress/evidence/<run-id>
    python3 secret_scan.py /var/lib/ingress/evidence/<run-id> --json
"""

from __future__ import annotations

import argparse
import base64
import json
import math
import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

# ── regex patterns ────────────────────────────────────────────────────────────

# Patterns that indicate a real secret rather than placeholder text
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "bearer_token",
        re.compile(r"(?i)\bbearer\s+[A-Za-z0-9\-._~+/]{20,}", re.ASCII),
    ),
    (
        "authorization_header",
        re.compile(r"(?i)\"Authorization\"\s*:\s*\"[A-Za-z0-9\-._~+/]{20,}\""),
    ),
    (
        "access_token_json_key",
        re.compile(r"(?i)\"access_token\"\s*:\s*\"[A-Za-z0-9\-._~+/=]{20,}\""),
    ),
    (
        "refresh_token_json_key",
        re.compile(r"(?i)\"refresh_token\"\s*:\s*\"[A-Za-z0-9\-._~+/=]{20,}\""),
    ),
    (
        "client_secret",
        re.compile(r"(?i)\"client_secret\"\s*:\s*\"[A-Za-z0-9\-._~+/=!@#$%^&*]{8,}\""),
    ),
    (
        "password_field",
        re.compile(r"(?i)\"password\"\s*:\s*\"[^\"]{4,}\""),
    ),
    (
        "private_key_pem",
        re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    ),
]

# Strings matching this pattern are excluded from entropy scan (low-risk)
_ENTROPY_EXCLUDE = re.compile(
    r"(?i)(placeholder|example|localhost|test|staging|dummy|null|none|false|true|"
    r"STAGING_CLIENT_ID_PLACEHOLDER)"
)

# Binary / non-text MIME extensions to skip
_SKIP_EXTENSIONS = {".db", ".pyc", ".pyo", ".png", ".jpg", ".jpeg", ".gif", ".zip", ".whl"}

# ── entropy scan ──────────────────────────────────────────────────────────────

_BASE64_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=")
_HEX_CHARS = set("0123456789abcdefABCDEF")

_MIN_ENTROPY_BITS = 4.5   # bits per character
_MIN_TOKEN_LENGTH = 20    # characters


def _shannon_entropy(s: str) -> float:
    if not s:
        return 0.0
    freq: dict[str, int] = {}
    for ch in s:
        freq[ch] = freq.get(ch, 0) + 1
    length = len(s)
    return -sum((c / length) * math.log2(c / length) for c in freq.values())


def _high_entropy_tokens(line: str) -> list[str]:
    """Return tokens in *line* that look like high-entropy secrets."""
    # Tokenise on whitespace and common delimiters
    tokens = re.split(r'[\s"\',:=\[\]{}()]+', line)
    results = []
    for tok in tokens:
        if len(tok) < _MIN_TOKEN_LENGTH:
            continue
        if _ENTROPY_EXCLUDE.search(tok):
            continue
        # Only flag tokens that use base64 or hex character sets
        char_set = set(tok)
        if not (char_set <= _BASE64_CHARS or char_set <= _HEX_CHARS):
            continue
        if _shannon_entropy(tok) >= _MIN_ENTROPY_BITS:
            results.append(tok)
    return results


# ── finding model ─────────────────────────────────────────────────────────────

@dataclass
class Finding:
    file: str
    line_number: int
    kind: str          # "pattern" | "entropy"
    rule: str
    snippet: str       # redacted excerpt, never the full token


def _redact(value: str) -> str:
    """Keep first 6 chars, replace the rest with ***."""
    if len(value) <= 6:
        return "***"
    return value[:6] + "***"


# ── scanner ───────────────────────────────────────────────────────────────────

def scan_file(path: Path) -> list[Finding]:
    if path.suffix in _SKIP_EXTENSIONS:
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    findings: list[Finding] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        # Regex pattern scan
        for rule_name, pattern in _PATTERNS:
            m = pattern.search(line)
            if m:
                findings.append(Finding(
                    file=str(path),
                    line_number=lineno,
                    kind="pattern",
                    rule=rule_name,
                    snippet=_redact(m.group(0)),
                ))

        # Entropy scan
        for token in _high_entropy_tokens(line):
            findings.append(Finding(
                file=str(path),
                line_number=lineno,
                kind="entropy",
                rule="high_entropy_token",
                snippet=_redact(token),
            ))

    return findings


def scan_directory(directory: Path) -> list[Finding]:
    all_findings: list[Finding] = []
    for root, _dirs, files in os.walk(directory):
        for fname in sorted(files):
            fpath = Path(root) / fname
            all_findings.extend(scan_file(fpath))
    return all_findings


# ── CLI ───────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="secret_scan",
        description="Scan an evidence directory for leaked secrets or high-entropy tokens.",
    )
    p.add_argument("directory", help="Evidence directory to scan.")
    p.add_argument("--json", action="store_true", help="Emit findings as JSON to stdout.")
    p.add_argument(
        "--allow-entropy",
        action="store_true",
        help="Suppress entropy findings (keep only pattern findings).",
    )
    return p


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    target = Path(args.directory)
    if not target.is_dir():
        print(f"[secret_scan] ERROR: not a directory: {target}", file=sys.stderr)
        return 2

    findings = scan_directory(target)

    if args.allow_entropy:
        findings = [f for f in findings if f.kind != "entropy"]

    report = {
        "scanned_directory": str(target),
        "finding_count": len(findings),
        "findings": [asdict(f) for f in findings],
    }

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        if not findings:
            print(f"[secret_scan] OK: no findings in {target}")
        else:
            print(f"[secret_scan] WARNING: {len(findings)} finding(s) in {target}")
            for f in findings:
                print(
                    f"  {f.kind.upper():10s}  {f.rule:35s}  "
                    f"{os.path.relpath(f.file, target)}:{f.line_number}  {f.snippet}"
                )

    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
