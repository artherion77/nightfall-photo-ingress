"""Parser tests for the hash-import `.hashes.v2` format."""

from __future__ import annotations

from pathlib import Path

import pytest

from nightfall_photo_ingress.hash_import import HashImportParseError, parse_hashes_v2_file, parse_hashes_v2_text


def test_parse_hashes_v2_text_returns_sha256_values_in_order() -> None:
    parsed = parse_hashes_v2_text(
        "\n".join(
            [
                "CACHE_SCHEMA v2",
                "DIRECTORY_HASH 0123456789abcdef0123456789abcdef01234567",
                "0123456789abcdef0123456789abcdef01234567\taaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\t/library/A.HEIC",
                "fedcba9876543210fedcba9876543210fedcba98\tBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB\t/library/B.HEIC",
            ]
        ),
        source="fixture.hashes.v2",
    )

    assert parsed == (
        "a" * 64,
        "b" * 64,
    )


def test_parse_hashes_v2_file_reads_from_disk(tmp_path: Path) -> None:
    cache_path = tmp_path / ".hashes.v2"
    cache_path.write_text(
        "\n".join(
            [
                "CACHE_SCHEMA v2",
                "DIRECTORY_HASH 0123456789abcdef0123456789abcdef01234567",
                "0123456789abcdef0123456789abcdef01234567\taaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\t/library/A.HEIC",
            ]
        ),
        encoding="utf-8",
    )

    assert parse_hashes_v2_file(cache_path) == ("a" * 64,)


def test_parse_hashes_v2_text_rejects_missing_header() -> None:
    with pytest.raises(HashImportParseError, match=r"fixture\.hashes\.v2: line 1: expected exact header 'CACHE_SCHEMA v2'"):
        parse_hashes_v2_text(
            "DIRECTORY_HASH 0123456789abcdef0123456789abcdef01234567\n",
            source="fixture.hashes.v2",
        )


def test_parse_hashes_v2_text_rejects_invalid_directory_hash_header() -> None:
    with pytest.raises(HashImportParseError, match=r"fixture\.hashes\.v2: line 2: invalid DIRECTORY_HASH header"):
        parse_hashes_v2_text(
            "\n".join(
                [
                    "CACHE_SCHEMA v2",
                    "DIRECTORY_HASH not-a-hash",
                ]
            ),
            source="fixture.hashes.v2",
        )


def test_parse_hashes_v2_text_rejects_invalid_sha256_with_line_number() -> None:
    with pytest.raises(HashImportParseError, match=r"fixture\.hashes\.v2: line 3: invalid SHA-256 value in column 2"):
        parse_hashes_v2_text(
            "\n".join(
                [
                    "CACHE_SCHEMA v2",
                    "DIRECTORY_HASH 0123456789abcdef0123456789abcdef01234567",
                    "0123456789abcdef0123456789abcdef01234567\tnot-a-sha256\t/library/A.HEIC",
                ]
            ),
            source="fixture.hashes.v2",
        )


def test_parse_hashes_v2_text_rejects_rows_with_fewer_than_three_fields() -> None:
    with pytest.raises(HashImportParseError, match=r"fixture\.hashes\.v2: line 3: expected exactly 3 tab-separated fields"):
        parse_hashes_v2_text(
            "\n".join(
                [
                    "CACHE_SCHEMA v2",
                    "DIRECTORY_HASH 0123456789abcdef0123456789abcdef01234567",
                    "0123456789abcdef0123456789abcdef01234567\taaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                ]
            ),
            source="fixture.hashes.v2",
        )


def test_parse_hashes_v2_text_allows_header_only_file() -> None:
    assert parse_hashes_v2_text(
        "\n".join(
            [
                "CACHE_SCHEMA v2",
                "DIRECTORY_HASH 0123456789abcdef0123456789abcdef01234567",
            ]
        ),
        source="fixture.hashes.v2",
    ) == ()


def test_parse_hashes_v2_text_rejects_empty_path() -> None:
    with pytest.raises(HashImportParseError, match=r"fixture\.hashes\.v2: line 3: empty path in column 3"):
        parse_hashes_v2_text(
            "\n".join(
                [
                    "CACHE_SCHEMA v2",
                    "DIRECTORY_HASH 0123456789abcdef0123456789abcdef01234567",
                    "0123456789abcdef0123456789abcdef01234567\taaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\t",
                ]
            ),
            source="fixture.hashes.v2",
        )