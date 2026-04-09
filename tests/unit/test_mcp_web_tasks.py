from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from urllib import request

from http.server import ThreadingHTTPServer

from mcp_server import MCPServerState, make_handler


def _start_test_server(workspace_root: Path) -> ThreadingHTTPServer:
    state = MCPServerState(workspace_root=workspace_root, model_path=workspace_root / ".mcp" / "model.json")
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(state))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def _await_status(port: int, task_id: str, *, timeout_seconds: float = 10.0) -> dict[str, object]:
    deadline = time.time() + timeout_seconds
    payload: dict[str, object] = {}
    while time.time() < deadline:
        with request.urlopen(f"http://127.0.0.1:{port}/mcp/status/{task_id}", timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if payload.get("status") in {"success", "failed"}:
            return payload
        time.sleep(0.05)
    return payload


def test_model_exposes_real_web_task_mappings() -> None:
    workspace_root = Path(__file__).resolve().parents[2]
    model = json.loads((workspace_root / ".mcp" / "model.json").read_text(encoding="utf-8"))

    mappings = model["mappings"]
    assert "web.test.e2e" in mappings
    assert "web.test.integration" in mappings
    assert mappings["web.test.e2e"] == ["./dev/bin/govctl run web.test.e2e --json"]
    assert mappings["web.test.integration"] == ["./dev/bin/govctl run web.test.integration --json"]


def test_web_mcp_tasks_execute_successfully_in_isolated_workspace(tmp_path: Path) -> None:
    workspace_root = tmp_path
    (workspace_root / ".mcp").mkdir(parents=True, exist_ok=True)
    (workspace_root / "dev" / "bin").mkdir(parents=True, exist_ok=True)

    govctl = workspace_root / "dev" / "bin" / "govctl"
    govctl.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "if [[ \"${1:-}\" != \"run\" ]]; then echo \"unexpected\"; exit 1; fi\n"
        "case \"${2:-}\" in\n"
        "  web.test.e2e|web.test.integration) echo \"shim:web-e2e\" ;;\n"
        "  *) echo \"shim:noop\" ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    govctl.chmod(0o755)

    model = {
        "mappings": {
            "web.test.e2e": ["./dev/bin/govctl run web.test.e2e --json"],
            "web.test.integration": ["./dev/bin/govctl run web.test.integration --json"],
        }
    }
    (workspace_root / ".mcp" / "model.json").write_text(json.dumps(model), encoding="utf-8")

    prior_path = os.environ.get("PATH", "")
    prior_lock_file = os.environ.get("REPO_LOCK_FILE")
    os.environ["PATH"] = f"{workspace_root / 'dev' / 'bin'}:{prior_path}"
    os.environ["REPO_LOCK_FILE"] = str(workspace_root / ".mcp" / "repo.lock")

    server = _start_test_server(workspace_root)
    try:
        port = server.server_address[1]

        for task_name in ("web.test.e2e", "web.test.integration"):
            body = json.dumps({"task": task_name}).encode("utf-8")
            req = request.Request(
                f"http://127.0.0.1:{port}/mcp/exec",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with request.urlopen(req, timeout=5) as response:
                assert response.status == 202
                payload = json.loads(response.read().decode("utf-8"))

            status_payload = _await_status(port, payload["taskId"])
            assert status_payload.get("status") == "success"
    finally:
        os.environ["PATH"] = prior_path
        if prior_lock_file is None:
            os.environ.pop("REPO_LOCK_FILE", None)
        else:
            os.environ["REPO_LOCK_FILE"] = prior_lock_file
        server.shutdown()
        server.server_close()
