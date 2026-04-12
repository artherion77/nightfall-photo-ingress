from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from nightfall_photo_ingress import cli
from nightfall_photo_ingress.domain.registry import HASH_IMPORT_ACCOUNT
from nightfall_photo_ingress.hash_import import _compute_directory_hash
from nightfall_photo_ingress.hash_import_cli import resolve_hash_import_chunk_size


def _write_config(tmp_path: Path, *, import_chunk_size: int | None = None) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    cfg = tmp_path / "photo-ingress.conf"
    import_block = ""
    if import_chunk_size is not None:
        import_block = f"\n[import]\nchunk_size = {import_chunk_size}\n"

    cfg.write_text(
        f"""
[core]
config_version = 2
poll_interval_minutes = 720
process_accounts_in_config_order = true
staging_path = {tmp_path / 'staging'}
pending_path = {tmp_path / 'pending'}
accepted_path = {tmp_path / 'accepted'}
accepted_storage_template = {{yyyy}}/{{mm}}/{{original}}
rejected_path = {tmp_path / 'rejected'}
trash_path = {tmp_path / 'trash'}
registry_path = {tmp_path / 'registry.db'}
staging_on_same_pool = false
storage_template = {{yyyy}}/{{mm}}/{{original}}
verify_sha256_on_first_download = true
max_downloads_per_poll = 200
max_poll_runtime_seconds = 300
sync_hash_import_enabled = true
sync_hash_import_path = {tmp_path / 'pictures'}
sync_hash_import_glob = .hashes.sha1
{import_block}
[account.primary]
enabled = true
provider = onedrive
authority = https://login.microsoftonline.com/consumers
client_id = cid
onedrive_root = /Camera Roll
token_cache = {tmp_path / 'primary.token'}
delta_cursor = {tmp_path / 'primary.cursor'}
""".strip(),
        encoding="utf-8",
    )
    return cfg


def _write_valid_v2(directory: Path, payload: bytes) -> None:
    file_path = next(path for path in directory.iterdir() if path.is_file())
    directory_hash = _compute_directory_hash(directory)
    sha1 = hashlib.sha1(payload).hexdigest()
    sha256 = hashlib.sha256(payload).hexdigest()
    (directory / ".hashes.v2").write_text(
        "\n".join(
            [
                "CACHE_SCHEMA v2",
                f"DIRECTORY_HASH {directory_hash}",
                f"{sha1}\t{sha256}\t{file_path}",
            ]
        ),
        encoding="utf-8",
    )


def test_hash_import_parser_registration_and_options() -> None:
    parser = cli._build_parser()
    args = parser.parse_args(
        [
            "hash-import",
            "/tmp/library",
            "--path",
            "/tmp/photo-ingress.conf",
            "--chunk-size",
            "500",
            "--dry-run",
            "--quiet",
            "--stats",
            "--stop-on-error",
        ]
    )

    assert args.command == "hash-import"
    assert args.root_path == "/tmp/library"
    assert args.path == "/tmp/photo-ingress.conf"
    assert args.chunk_size == 500
    assert args.dry_run is True
    assert args.quiet is True
    assert args.stats is True
    assert args.stop_on_error is True


def test_hash_import_chunk_size_precedence_cli_over_config_over_default(tmp_path: Path) -> None:
    cfg_with_import = _write_config(tmp_path / "cfg1", import_chunk_size=250)
    cfg_default = _write_config(tmp_path / "cfg2")

    assert resolve_hash_import_chunk_size(config_path=cfg_with_import, cli_chunk_size=500) == 500
    assert resolve_hash_import_chunk_size(config_path=cfg_with_import, cli_chunk_size=None) == 250
    assert resolve_hash_import_chunk_size(config_path=cfg_default, cli_chunk_size=None) == 1000


def test_cli_hash_import_dry_run_on_fixture_tree(tmp_path: Path, monkeypatch) -> None:
    cfg = _write_config(tmp_path)
    root = tmp_path / "pictures"
    directory = root / "2026" / "04"
    directory.mkdir(parents=True)
    payload = b"alpha"
    (directory / "A.HEIC").write_bytes(payload)
    _write_valid_v2(directory, payload)

    snapshots: list[dict[str, object]] = []
    monkeypatch.setattr(cli, "_emit_status_snapshot", lambda **kwargs: snapshots.append(kwargs))

    exit_code = cli.main(["hash-import", str(root), "--path", str(cfg), "--dry-run"])

    assert exit_code == 0
    assert snapshots[-1]["command"] == "hash-import"
    assert snapshots[-1]["success"] is True

    with sqlite3.connect(tmp_path / "registry.db") as conn:
        row_count = conn.execute("SELECT COUNT(*) FROM external_hash_cache").fetchone()[0]
    assert row_count == 0


def test_cli_hash_import_writes_registry_rows_and_status_snapshot(tmp_path: Path, monkeypatch) -> None:
    cfg = _write_config(tmp_path, import_chunk_size=1)
    root = tmp_path / "pictures"
    first_dir = root / "2026" / "04"
    second_dir = root / "2026" / "05"
    first_dir.mkdir(parents=True)
    second_dir.mkdir(parents=True)
    first_payload = b"alpha"
    second_payload = b"beta"
    (first_dir / "A.HEIC").write_bytes(first_payload)
    (second_dir / "B.HEIC").write_bytes(second_payload)
    _write_valid_v2(first_dir, first_payload)
    _write_valid_v2(second_dir, second_payload)

    snapshots: list[dict[str, object]] = []
    monkeypatch.setattr(cli, "_emit_status_snapshot", lambda **kwargs: snapshots.append(kwargs))

    exit_code = cli.main(["hash-import", str(root), "--path", str(cfg), "--stats"])

    assert exit_code == 0
    details = snapshots[-1]["details"]
    assert snapshots[-1]["command"] == "hash-import"
    assert details["chunk_size"] == 1
    assert details["total_imported"] == 2
    assert details["total_skipped"] == 0

    with sqlite3.connect(tmp_path / "registry.db") as conn:
        rows = conn.execute(
            "SELECT account_name, source_relpath, hash_algo, verified_sha256 FROM external_hash_cache ORDER BY hash_value"
        ).fetchall()

    assert len(rows) == 2
    assert all(row[0] == HASH_IMPORT_ACCOUNT for row in rows)
    assert all(row[1] is None for row in rows)
    assert all(row[2] == "sha256" for row in rows)
    assert all(row[3] for row in rows)


def test_cli_hash_import_invalid_root_returns_exit_code_two(tmp_path: Path, monkeypatch) -> None:
    cfg = _write_config(tmp_path)
    snapshots: list[dict[str, object]] = []
    monkeypatch.setattr(cli, "_emit_status_snapshot", lambda **kwargs: snapshots.append(kwargs))

    exit_code = cli.main(["hash-import", str(tmp_path / "missing"), "--path", str(cfg), "--stop-on-error"])

    assert exit_code == 2
    assert snapshots[-1]["command"] == "hash-import"
    assert snapshots[-1]["success"] is False


def test_cli_hash_import_help_text_lists_h6_options(capsys) -> None:
    exit_code = cli.main(["hash-import", "--help"])

    assert exit_code == 0
    help_text = capsys.readouterr().out
    assert "--chunk-size" in help_text
    assert "--dry-run" in help_text
    assert "--quiet" in help_text
    assert "--stats" in help_text
    assert "--stop-on-error" in help_text
