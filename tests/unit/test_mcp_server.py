from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from urllib import request

from mcp_server import MCPServerState, make_handler
from http.server import ThreadingHTTPServer


def _start_test_server(workspace_root: Path):
    state = MCPServerState(workspace_root=workspace_root, model_path=workspace_root / ".mcp" / "model.json")
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(state))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def test_context_returns_model_and_runtime():
    workspace_root = Path(__file__).resolve().parents[2]
    server = _start_test_server(workspace_root)
    try:
        port = server.server_address[1]
        with request.urlopen(f"http://127.0.0.1:{port}/mcp/context", timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        assert "model" in payload
        assert "runtime" in payload
        assert "mappings" in payload["model"]
    finally:
        server.shutdown()
        server.server_close()


def test_exec_accepts_mapped_task_and_status_is_available():
    workspace_root = Path(__file__).resolve().parents[2]
    server = _start_test_server(workspace_root)
    try:
        port = server.server_address[1]
        body = json.dumps({"task": "web.test.unit"}).encode("utf-8")
        req = request.Request(
            f"http://127.0.0.1:{port}/mcp/exec",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=5) as response:
            assert response.status == 202
            payload = json.loads(response.read().decode("utf-8"))

        task_id = payload["taskId"]
        deadline = time.time() + 5
        status_payload = None
        while time.time() < deadline:
            with request.urlopen(f"http://127.0.0.1:{port}/mcp/status/{task_id}", timeout=5) as response:
                status_payload = json.loads(response.read().decode("utf-8"))
            if status_payload["status"] in {"success", "failed"}:
                break
            time.sleep(0.1)

        assert status_payload is not None
        assert status_payload["taskId"] == task_id
        assert status_payload["status"] in {"queued", "running", "success", "failed"}
    finally:
        server.shutdown()
        server.server_close()