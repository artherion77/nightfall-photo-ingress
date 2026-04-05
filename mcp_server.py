#!/usr/bin/env python3
"""Nightfall Photo Ingress — MCP stdio server.

Protocol: MCP 2025-03-26 (also accepted: 2024-11-05).
Transport: stdin/stdout JSON-RPC with Content-Length framing.
"""
from __future__ import annotations

import fcntl
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
import json
import logging
import os
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Protocol constants ────────────────────────────────────────────────────────

SUPPORTED_PROTOCOL_VERSIONS = ["2025-03-26", "2024-11-05"]
HISTORY_MAX = 20  # keep only the N most recent task records

# ── Logging (file-only; stdout is reserved for JSON-RPC) ─────────────────────

log = logging.getLogger("nightfall_mcp")


def _setup_logging(logs_dir: Path) -> None:
    logs_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(logs_dir / "mcp_server.log", encoding="utf-8")],
    )


# ── JSON-RPC framing ──────────────────────────────────────────────────────────

def _write(payload: dict[str, Any]) -> None:
    body = json.dumps(payload).encode("utf-8")
    sys.stdout.buffer.write(
        f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body
    )
    sys.stdout.buffer.flush()


def _read() -> dict[str, Any] | None:
    """Read the next well-formed JSON-RPC message from stdin.

    Returns None only on a clean EOF or unrecoverable I/O error.
    Silently skips malformed frames so one bad message never kills the server.
    """
    while True:
        # Collect headers until blank line
        headers: dict[str, str] = {}
        while True:
            try:
                line = sys.stdin.buffer.readline()
            except OSError as exc:
                log.error("stdin read error: %s", exc)
                return None
            if not line:                   # clean EOF
                return None
            stripped = line.rstrip(b"\r\n")
            if not stripped:               # blank separator line
                break
            try:
                k, _, v = line.decode("ascii", errors="replace").partition(":")
                headers[k.strip().lower()] = v.strip()
            except Exception:
                pass

        # Parse Content-Length
        try:
            content_length = int(headers.get("content-length", "0") or "0")
        except ValueError:
            log.warning("Skipping frame: invalid Content-Length header")
            continue
        if content_length <= 0:
            log.warning("Skipping frame: Content-Length=%d", content_length)
            continue

        # Read body
        try:
            body = sys.stdin.buffer.read(content_length)
        except OSError as exc:
            log.error("stdin body read error: %s", exc)
            return None
        if not body:
            return None  # EOF inside body

        # Decode and parse
        try:
            obj = json.loads(body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            log.warning("Skipping malformed JSON frame: %s", exc)
            continue
        if not isinstance(obj, dict):
            log.warning("Skipping non-object JSON frame")
            continue

        return obj


def _ok(msg_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _err(msg_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


# ── Helpers ───────────────────────────────────────────────────────────────────

REPO_LOCK_FILE = os.environ.get("REPO_LOCK_FILE", "/tmp/nightfall-repo.lock")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Server state ──────────────────────────────────────────────────────────────

class ServerState:
    def __init__(self, workspace_root: Path, model_path: Path) -> None:
        self.workspace_root = workspace_root.resolve()
        self._mcp_dir = self.workspace_root / ".mcp"
        self._logs_dir = self._mcp_dir / "logs"
        self._tasks_dir = self._mcp_dir / "tasks"
        self._history_file = self._tasks_dir / "history.json"
        self._extensions_file = self._tasks_dir / "extensions.json"

        self._lock = threading.Lock()
        self._tasks: dict[str, dict[str, Any]] = {}  # taskId → record
        self._extensions: list[dict[str, Any]] = []

        self._logs_dir.mkdir(parents=True, exist_ok=True)
        self._tasks_dir.mkdir(parents=True, exist_ok=True)

        self._model = self._load_model(model_path)
        self._load_history()
        self._load_extensions()

    # ── Persistence ───────────────────────────────────────────────────────

    def _load_model(self, path: Path) -> dict[str, Any]:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("mappings"), dict):
            raise ValueError(f"Invalid model file: {path}")
        return data

    def _load_history(self) -> None:
        if not self._history_file.exists():
            return
        try:
            records = json.loads(self._history_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        if isinstance(records, list):
            for r in records:
                if isinstance(r, dict) and isinstance(r.get("taskId"), str):
                    self._tasks[r["taskId"]] = r

    def _load_extensions(self) -> None:
        if not self._extensions_file.exists():
            return
        try:
            data = json.loads(self._extensions_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        if isinstance(data, list):
            self._extensions = [x for x in data if isinstance(x, dict)]

    def _save_history(self) -> None:
        """Persist history, keeping only the HISTORY_MAX most recent tasks."""
        all_records = sorted(
            self._tasks.values(),
            key=lambda r: r.get("startedAt", ""),
            reverse=True,
        )
        kept = all_records[:HISTORY_MAX]
        # Evict purged records from in-memory dict as well
        self._tasks = {r["taskId"]: r for r in kept}
        try:
            self._history_file.write_text(json.dumps(kept, indent=2), encoding="utf-8")
        except OSError as exc:
            log.warning("Could not persist task history: %s", exc)

    def _save_extensions(self) -> None:
        try:
            self._extensions_file.write_text(
                json.dumps(self._extensions, indent=2), encoding="utf-8"
            )
        except OSError as exc:
            log.warning("Could not persist extensions: %s", exc)

    # ── Task execution ────────────────────────────────────────────────────

    def enqueue(
        self,
        task_name: str,
        *,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        depends_on: list[str] | None = None,
        significant_task: bool = False,
        extension_recommendation: str | None = None,
    ) -> str:
        mapping = self._model["mappings"].get(task_name)
        if not isinstance(mapping, list) or not all(isinstance(c, str) for c in mapping):
            raise ValueError(f"Unknown task mapping: {task_name!r}")

        cwd_path = self.workspace_root
        if cwd is not None:
            cwd_path = (self.workspace_root / cwd).resolve()
            if not str(cwd_path).startswith(str(self.workspace_root)):
                raise ValueError("cwd must be inside workspace root")

        with self._lock:
            for dep_id in depends_on or []:
                if not isinstance(dep_id, str):
                    raise ValueError("dependsOn entries must be strings")
                if dep_id not in self._tasks:
                    raise ValueError(f"dependsOn task not found: {dep_id!r}")

        task_id = str(uuid.uuid4())
        record: dict[str, Any] = {
            "taskId": task_id,
            "task": task_name,
            "status": "queued",
            "exitCode": None,
            "startedAt": _now(),
            "finishedAt": None,
            "cwd": str(cwd_path),
            "args": args or [],
            "dependsOn": list(depends_on or []),
            "significantTask": significant_task,
            "extensionRecommendation": extension_recommendation,
        }
        with self._lock:
            self._tasks[task_id] = record
            self._save_history()

        threading.Thread(
            target=self._run_task,
            args=(task_id, list(mapping), dict(env or {}), str(cwd_path)),
            daemon=True,
        ).start()
        return task_id

    def _run_task(
        self, task_id: str, commands: list[str], extra_env: dict[str, str], cwd: str
    ) -> None:
        log_path = self._logs_dir / f"{task_id}.log"
        merged_env = {**os.environ, **extra_env, "DEVCTL_GLOBAL_LOCK_HELD": "1"}

        with self._lock:
            record = self._tasks[task_id]
            record["status"] = "waiting" if record["dependsOn"] else "running"

        exit_code = 0
        with log_path.open("w", encoding="utf-8") as lf:
            lf.write(f"[{_now()}] task={record['task']} status={record['status']}\n")

            # Wait for dependencies
            if record["dependsOn"]:
                failure: str | None = None
                while failure is None:
                    with self._lock:
                        deps = [(d, self._tasks.get(d)) for d in record["dependsOn"]]
                    for dep_id, dep in deps:
                        if dep is None:
                            failure = f"dependency missing: {dep_id}"
                            break
                        if dep["status"] == "failed":
                            failure = f"dependency failed: {dep_id}"
                            break
                    else:
                        all_done = all(
                            dep is not None and dep["status"] in ("success", "completed")
                            for _, dep in deps
                        )
                        if all_done:
                            break
                    if failure:
                        break
                    time.sleep(0.25)

                if failure:
                    lf.write(f"{failure}\n")
                    with self._lock:
                        record["status"] = "failed"
                        record["exitCode"] = 1
                        record["finishedAt"] = _now()
                        self._save_history()
                    return

                with self._lock:
                    record["status"] = "running"
                lf.write(f"[{_now()}] dependencies satisfied, running\n")

            # Execute commands sequentially
            for cmd in commands:
                lf.write(f"$ {cmd}\n")
                lf.flush()
                try:
                    os.makedirs(os.path.dirname(REPO_LOCK_FILE), exist_ok=True)
                    with open(REPO_LOCK_FILE, "w") as lock_fh:
                        lock_acquired = False
                        try:
                            fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                            lock_acquired = True
                        except BlockingIOError:
                            lf.write(
                                "[warn] repo lock busy; continuing without exclusive lock\n"
                            )
                        proc = subprocess.Popen(
                            cmd,
                            shell=True,
                            cwd=cwd,
                            env=merged_env,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            text=True,
                        )
                        for line in proc.stdout:  # type: ignore[union-attr]
                            lf.write(line)
                        proc.wait()
                        if lock_acquired:
                            fcntl.flock(lock_fh, fcntl.LOCK_UN)
                    exit_code = proc.returncode
                except OSError as exc:
                    lf.write(f"error launching command: {exc}\n")
                    exit_code = 1
                if exit_code != 0:
                    lf.write(f"command exited with code {exit_code}\n")
                    break

        with self._lock:
            record["status"] = "success" if exit_code == 0 else "failed"
            record["exitCode"] = exit_code
            record["finishedAt"] = _now()
            self._save_history()

        if record.get("significantTask") and record.get("extensionRecommendation"):
            self.propose_extension(
                recommendation=record["extensionRecommendation"],
                related_task_id=task_id,
                task_name=record["task"],
                source="post_significant_task",
            )

    # ── Queries ───────────────────────────────────────────────────────────

    def task_status(self, task_id: str) -> dict[str, Any] | None:
        with self._lock:
            r = self._tasks.get(task_id)
        if r is None:
            return None
        return {k: r.get(k) for k in ("taskId", "task", "status", "exitCode", "startedAt", "finishedAt")}

    def task_log(self, task_id: str, tail: int | None = None) -> str | None:
        log_path = self._logs_dir / f"{task_id}.log"
        if not log_path.exists():
            return None
        text = log_path.read_text(encoding="utf-8")
        if tail:
            return "\n".join(text.splitlines()[-tail:])
        return text

    def extensions_snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._extensions)

    def context(self) -> dict[str, Any]:
        devctl_rel = self._model.get("devctl", {}).get("path", "dev/bin/devctl")
        stagectl_rel = self._model.get("stagectl", {}).get("path", "dev/bin/stagingctl")
        devctl = self.workspace_root / devctl_rel
        stagectl = self.workspace_root / stagectl_rel
        return {
            "model": self._model,
            "runtime": {
                "workspaceRoot": str(self.workspace_root),
                "devctl": {"path": str(devctl), "exists": devctl.exists()},
                "stagectl": {"path": str(stagectl), "exists": stagectl.exists()},
                "taskHistoryCount": len(self._tasks),
                "extensionsBacklogCount": len(self._extensions),
            },
        }

    def verify(self, verify_key: str, target: str) -> dict[str, Any]:
        verifs = self._model.get("verifications", {})
        scope = verifs.get(verify_key)
        if not isinstance(scope, dict):
            raise ValueError(f"Unknown verification key: {verify_key!r}")
        commands = scope.get(target)
        if not isinstance(commands, list):
            raise ValueError(f"No verification for target: {target!r}")
        results = []
        passed = True
        for cmd in commands:
            proc = subprocess.run(
                cmd,
                shell=True,
                cwd=str(self.workspace_root),
                capture_output=True,
                text=True,
            )
            results.append({
                "command": cmd,
                "exitCode": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
            })
            if proc.returncode != 0:
                passed = False
                break
        return {"passed": passed, "results": results}

    def propose_extension(
        self,
        *,
        recommendation: str,
        related_task_id: str | None,
        task_name: str | None,
        source: str,
    ) -> dict[str, Any]:
        proposal = {
            "proposalId": str(uuid.uuid4()),
            "createdAt": _now(),
            "source": source,
            "relatedTaskId": related_task_id,
            "task": task_name,
            "recommendation": recommendation,
            "status": "proposed",
        }
        self._extensions.append(proposal)
        self._save_extensions()
        return proposal


# Backward-compatible alias used by legacy tests/imports.
MCPServerState = ServerState


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _parse_json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    raw_len = handler.headers.get("Content-Length", "0")
    try:
        length = int(raw_len)
    except ValueError as exc:
        raise ValueError("Invalid Content-Length") from exc
    raw = handler.rfile.read(length) if length > 0 else b"{}"
    if not raw:
        return {}
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("JSON body must be an object")
    return data


def _optional_str(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _optional_str_list(payload: dict[str, Any], key: str) -> list[str] | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
        raise ValueError(f"{key} must be an array of strings")
    return value


def _optional_str_dict(payload: dict[str, Any], key: str) -> dict[str, str] | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in value.items()
    ):
        raise ValueError(f"{key} must be an object of string pairs")
    return value


def make_handler(state: ServerState):
    class MCPHandler(BaseHTTPRequestHandler):
        server_version = "NightfallMCPCompat/2.0"

        def log_message(self, fmt: str, *args: Any) -> None:  # noqa: D401
            # Silence per-request logging in tests.
            return

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/mcp/context":
                _json_response(self, HTTPStatus.OK, state.context())
                return

            if self.path.startswith("/mcp/status/"):
                task_id = self.path.split("/mcp/status/", 1)[1]
                status_payload = state.task_status(task_id)
                if status_payload is None:
                    _json_response(self, HTTPStatus.NOT_FOUND, {"error": "taskId not found"})
                    return
                _json_response(self, HTTPStatus.OK, status_payload)
                return

            if self.path.startswith("/mcp/log/"):
                task_id = self.path.split("/mcp/log/", 1)[1]
                log_text = state.task_log(task_id, tail=200)
                if log_text is None:
                    _json_response(self, HTTPStatus.NOT_FOUND, {"error": "log not found"})
                    return
                _json_response(self, HTTPStatus.OK, {"taskId": task_id, "log": log_text})
                return

            if self.path == "/mcp/extensions":
                exts = state.extensions_snapshot()
                _json_response(self, HTTPStatus.OK, {"extensions": exts})
                return

            _json_response(self, HTTPStatus.NOT_FOUND, {"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            try:
                payload = _parse_json_body(self)
            except (json.JSONDecodeError, ValueError) as exc:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return

            if self.path == "/mcp/exec":
                task_name = payload.get("task")
                if not isinstance(task_name, str):
                    _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "task must be a string"})
                    return

                significant = payload.get("significantTask", False)
                if not isinstance(significant, bool):
                    _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "significantTask must be a boolean"})
                    return

                try:
                    args = _optional_str_list(payload, "args")
                    env = _optional_str_dict(payload, "env")
                    cwd = _optional_str(payload, "cwd")
                    depends_on = _optional_str_list(payload, "dependsOn")
                    extension_rec = _optional_str(payload, "extensionRecommendation")
                except ValueError as exc:
                    _json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                    return

                try:
                    task_id = state.enqueue(
                        task_name,
                        args=args,
                        env=env,
                        cwd=cwd,
                        depends_on=depends_on,
                        significant_task=significant,
                        extension_recommendation=extension_rec,
                    )
                except ValueError as exc:
                    _json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                    return

                _json_response(self, HTTPStatus.ACCEPTED, {"taskId": task_id, "status": "queued"})
                return

            if self.path == "/mcp/verify":
                verify_key = payload.get("verify")
                target = payload.get("target")
                if not isinstance(verify_key, str) or not isinstance(target, str):
                    _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "verify and target must be strings"})
                    return
                try:
                    result = state.verify(verify_key, target)
                except ValueError as exc:
                    _json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                    return
                _json_response(self, HTTPStatus.OK, result)
                return

            if self.path == "/mcp/extensions/propose":
                recommendation = payload.get("recommendation")
                related_task_id = payload.get("relatedTaskId")
                task_name = payload.get("task")

                if not isinstance(recommendation, str) or not recommendation.strip():
                    _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "recommendation must be a non-empty string"})
                    return
                if related_task_id is not None and not isinstance(related_task_id, str):
                    _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "relatedTaskId must be a string or null"})
                    return
                if task_name is not None and not isinstance(task_name, str):
                    _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "task must be a string or null"})
                    return

                proposal = state.propose_extension(
                    recommendation=recommendation.strip(),
                    related_task_id=related_task_id if isinstance(related_task_id, str) else None,
                    task_name=task_name if isinstance(task_name, str) else None,
                    source="manual",
                )
                _json_response(self, HTTPStatus.CREATED, proposal)
                return

            _json_response(self, HTTPStatus.NOT_FOUND, {"error": "not found"})

    return MCPHandler


# ── Tool schema ───────────────────────────────────────────────────────────────

def _tool_list() -> list[dict[str, Any]]:
    S = {"type": "string"}
    return [
        {
            "name": "mcp.exec",
            "description": "Queue a devctl task from .mcp/model.json mappings and return its taskId.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "Mapping key from model.json"},
                    "args": {"type": "array", "items": S, "description": "Extra CLI args"},
                    "env": {"type": "object", "additionalProperties": S},
                    "cwd": {"type": "string", "description": "Working dir relative to workspace root"},
                    "dependsOn": {"type": "array", "items": S, "description": "taskIds to wait for"},
                    "significantTask": {"type": "boolean"},
                    "extensionRecommendation": {"type": "string"},
                },
                "required": ["task"],
            },
        },
        {
            "name": "mcp.status",
            "description": "Get task status by taskId.",
            "inputSchema": {
                "type": "object",
                "properties": {"taskId": S},
                "required": ["taskId"],
            },
        },
        {
            "name": "mcp.log",
            "description": "Get task log. Optional 'tail' limits to last N lines.",
            "inputSchema": {
                "type": "object",
                "properties": {"taskId": S, "tail": {"type": "integer"}},
                "required": ["taskId"],
            },
        },
        {
            "name": "mcp.context",
            "description": "Return MCP model and runtime context.",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "mcp.verify",
            "description": "Run verification commands from .mcp/model.json verifications.",
            "inputSchema": {
                "type": "object",
                "properties": {"verify": S, "target": S},
                "required": ["verify", "target"],
            },
        },
        {
            "name": "mcp.extensions.list",
            "description": "List extension proposals backlog.",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "mcp.extensions.propose",
            "description": "Add an extension proposal.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "recommendation": S,
                    "relatedTaskId": S,
                    "task": S,
                },
                "required": ["recommendation"],
            },
        },
    ]


def _tool_result(payload: dict[str, Any], *, is_error: bool = False) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": json.dumps(payload, indent=2)}],
        "isError": is_error,
    }


# ── Request dispatch ──────────────────────────────────────────────────────────

def _dispatch(state: ServerState, msg: dict[str, Any]) -> None:
    method: str = msg.get("method", "")
    msg_id = msg.get("id")          # None for notifications
    params: dict[str, Any] = msg.get("params") if isinstance(msg.get("params"), dict) else {}  # type: ignore[assignment]

    log.debug("recv method=%s id=%s", method, msg_id)

    # Notifications have no id and require no response
    if method == "notifications/initialized":
        return
    if method == "exit":
        raise SystemExit(0)
    if msg_id is None:
        return  # other notifications; ignore

    try:
        if method == "initialize":
            client_ver = params.get("protocolVersion", SUPPORTED_PROTOCOL_VERSIONS[0])
            negotiated = (
                client_ver if client_ver in SUPPORTED_PROTOCOL_VERSIONS
                else SUPPORTED_PROTOCOL_VERSIONS[0]
            )
            _write(_ok(msg_id, {
                "protocolVersion": negotiated,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "nightfall-photo-ingress", "version": "2.0.0"},
            }))

        elif method == "ping":
            _write(_ok(msg_id, {}))

        elif method == "tools/list":
            _write(_ok(msg_id, {"tools": _tool_list()}))

        elif method == "tools/call":
            _write(_ok(msg_id, _call_tool(state, params)))

        elif method == "shutdown":
            _write(_ok(msg_id, None))

        else:
            _write(_err(msg_id, -32601, f"Method not found: {method}"))

    except ValueError as exc:
        _write(_err(msg_id, -32602, str(exc)))
    except Exception as exc:
        log.exception("Error handling %s", method)
        _write(_err(msg_id, -32603, str(exc)))


def _call_tool(state: ServerState, params: dict[str, Any]) -> dict[str, Any]:
    name = params.get("name")
    a: dict[str, Any] = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}  # type: ignore[assignment]

    if name == "mcp.exec":
        task_name = a.get("task")
        if not isinstance(task_name, str):
            raise ValueError("mcp.exec: 'task' must be a string")
        task_id = state.enqueue(
            task_name,
            args=a.get("args") if isinstance(a.get("args"), list) else None,
            env=a.get("env") if isinstance(a.get("env"), dict) else None,
            cwd=a.get("cwd") if isinstance(a.get("cwd"), str) else None,
            depends_on=a.get("dependsOn") if isinstance(a.get("dependsOn"), list) else None,
            significant_task=bool(a.get("significantTask", False)),
            extension_recommendation=a.get("extensionRecommendation") if isinstance(a.get("extensionRecommendation"), str) else None,
        )
        return _tool_result({"taskId": task_id, "status": "queued"})

    if name == "mcp.status":
        task_id = a.get("taskId")
        if not isinstance(task_id, str):
            raise ValueError("mcp.status: 'taskId' must be a string")
        s = state.task_status(task_id)
        return _tool_result(s) if s is not None else _tool_result({"error": "taskId not found"}, is_error=True)

    if name == "mcp.log":
        task_id = a.get("taskId")
        if not isinstance(task_id, str):
            raise ValueError("mcp.log: 'taskId' must be a string")
        text = state.task_log(task_id, tail=a.get("tail") if isinstance(a.get("tail"), int) else None)
        if text is None:
            return _tool_result({"error": "log not found"}, is_error=True)
        return _tool_result({"taskId": task_id, "log": text})

    if name == "mcp.context":
        return _tool_result(state.context())

    if name == "mcp.verify":
        verify_key, target = a.get("verify"), a.get("target")
        if not isinstance(verify_key, str) or not isinstance(target, str):
            raise ValueError("mcp.verify: 'verify' and 'target' must be strings")
        return _tool_result(state.verify(verify_key, target))

    if name == "mcp.extensions.list":
        with state._lock:
            exts = list(state._extensions)
        return _tool_result({"extensions": exts})

    if name == "mcp.extensions.propose":
        rec = a.get("recommendation")
        if not isinstance(rec, str) or not rec.strip():
            raise ValueError("mcp.extensions.propose: 'recommendation' must be a non-empty string")
        proposal = state.propose_extension(
            recommendation=rec.strip(),
            related_task_id=a.get("relatedTaskId") if isinstance(a.get("relatedTaskId"), str) else None,
            task_name=a.get("task") if isinstance(a.get("task"), str) else None,
            source="manual",
        )
        return _tool_result(proposal)

    raise ValueError(f"Unknown tool: {name!r}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    import argparse

    script_dir = Path(__file__).resolve().parent
    p = argparse.ArgumentParser(description="Nightfall Photo Ingress MCP server (stdio)")
    p.add_argument("--workspace", default=os.environ.get("MCP_WORKSPACE", str(script_dir)))
    p.add_argument("--model", default=os.environ.get("MCP_MODEL_PATH", ".mcp/model.json"))
    args = p.parse_args()

    workspace = Path(args.workspace).resolve()
    logs_dir = workspace / ".mcp" / "logs"

    # Redirect stderr to a log file before anything else so Python tracebacks
    # never pollute stdout (which is the JSON-RPC pipe).
    _setup_logging(logs_dir)
    sys.stderr = open(logs_dir / "mcp_server_stderr.log", "a", encoding="utf-8")  # noqa: SIM115

    model_path = (workspace / args.model).resolve()
    log.info(
        "Starting nightfall-photo-ingress MCP server workspace=%s model=%s",
        workspace, model_path,
    )

    try:
        state = ServerState(workspace_root=workspace, model_path=model_path)
    except Exception as exc:
        log.critical("Failed to initialise server state: %s", exc, exc_info=True)
        sys.exit(1)

    log.info("Server ready, entering stdio loop")
    while True:
        msg = _read()
        if msg is None:
            log.info("stdin EOF — exiting")
            break
        try:
            _dispatch(state, msg)
        except SystemExit:
            break
        except Exception as exc:
            log.exception("Unhandled error in dispatch: %s", exc)


if __name__ == "__main__":
    main()
