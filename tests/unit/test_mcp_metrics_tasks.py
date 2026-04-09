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


def _await_status(port: int, task_id: str, *, timeout_seconds: float = 5.0) -> dict[str, object]:
    deadline = time.time() + timeout_seconds
    payload: dict[str, object] = {}
    while time.time() < deadline:
        with request.urlopen(f"http://127.0.0.1:{port}/mcp/status/{task_id}", timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if payload.get("status") in {"success", "failed"}:
            return payload
        time.sleep(0.05)
    return payload


def test_model_exposes_metrics_mcp_task_mappings() -> None:
    workspace_root = Path(__file__).resolve().parents[2]
    model = json.loads((workspace_root / ".mcp" / "model.json").read_text(encoding="utf-8"))

    mappings = model["mappings"]
    assert mappings["metrics.status"] == ["./dev/bin/govctl run metrics.status --json"]
    assert mappings["metrics.run-now"] == ["./dev/bin/govctl run metrics.run-now --json"]
    assert mappings["metrics.publish"] == ["./dev/bin/govctl run metrics.publish --json"]
    assert mappings["metrics.install"] == ["./dev/bin/govctl run metrics.install --json"]
    assert mappings["metrics.stop"] == ["./dev/bin/govctl run metrics.stop --json"]


def test_metrics_mcp_tasks_delegate_to_metricsctl_in_isolated_workspace(tmp_path: Path) -> None:
    workspace_root = tmp_path
    (workspace_root / ".mcp").mkdir(parents=True, exist_ok=True)

    govctl = workspace_root / "dev" / "bin" / "govctl"
    govctl.parent.mkdir(parents=True, exist_ok=True)
    govctl.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "if [[ \"${1:-}\" != \"run\" ]]; then echo 'unknown'; exit 1; fi\n"
        "cmd=\"${2:-}\"\n"
        "case \"$cmd\" in\n"
        "  metrics.status) echo '{\"runtime\":\"ok\"}' ;;\n"
        "  metrics.run-now) echo '{\"status\":\"success\"}' ;;\n"
        "  metrics.publish) echo '{\"status\":\"published\"}' ;;\n"
        "  metrics.install) echo '{\"installed\":true}' ;;\n"
        "  metrics.stop) echo '{\"enabled\":false}' ;;\n"
        "  *) echo 'unknown' ; exit 1 ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    govctl.chmod(0o755)

    model = {
        "mappings": {
            "metrics.status": ["./dev/bin/govctl run metrics.status --json"],
            "metrics.run-now": ["./dev/bin/govctl run metrics.run-now --json"],
            "metrics.publish": ["./dev/bin/govctl run metrics.publish --json"],
            "metrics.install": ["./dev/bin/govctl run metrics.install --json"],
            "metrics.stop": ["./dev/bin/govctl run metrics.stop --json"],
        }
    }
    (workspace_root / ".mcp" / "model.json").write_text(json.dumps(model), encoding="utf-8")

    prior_path = os.environ.get("PATH", "")
    os.environ["PATH"] = f"{workspace_root}:{prior_path}"

    server = _start_test_server(workspace_root)
    try:
        port = server.server_address[1]
        for task_name in ("metrics.status", "metrics.run-now", "metrics.publish", "metrics.install", "metrics.stop"):
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
        server.shutdown()
        server.server_close()
