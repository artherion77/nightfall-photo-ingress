#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TaskRecord:
    taskId: str
    task: str
    status: str
    exitCode: int | None
    startedAt: str
    finishedAt: str | None
    cwd: str
    args: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "taskId": self.taskId,
            "task": self.task,
            "status": self.status,
            "exitCode": self.exitCode,
            "startedAt": self.startedAt,
            "finishedAt": self.finishedAt,
            "cwd": self.cwd,
            "args": self.args,
        }


class MCPServerState:
    def __init__(self, workspace_root: Path, model_path: Path):
        self.workspace_root = workspace_root
        self.model_path = model_path
        self.logs_dir = workspace_root / ".mcp" / "logs"
        self.tasks_dir = workspace_root / ".mcp" / "tasks"
        self.history_file = self.tasks_dir / "history.json"
        self.lock = threading.Lock()
        self.tasks: dict[str, TaskRecord] = {}
        self.model = self._load_model()
        self._ensure_dirs()
        self._load_history()

    def _ensure_dirs(self) -> None:
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.tasks_dir.mkdir(parents=True, exist_ok=True)

    def _load_model(self) -> dict[str, Any]:
        data = json.loads(self.model_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Model file must contain a JSON object")
        if "mappings" not in data or not isinstance(data["mappings"], dict):
            raise ValueError("Model file must contain object key 'mappings'")
        return data

    def _load_history(self) -> None:
        if not self.history_file.exists():
            return
        try:
            raw = json.loads(self.history_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return
        if not isinstance(raw, list):
            return
        for item in raw:
            if not isinstance(item, dict):
                continue
            task_id = item.get("taskId")
            if not isinstance(task_id, str):
                continue
            self.tasks[task_id] = TaskRecord(
                taskId=task_id,
                task=str(item.get("task", "")),
                status=str(item.get("status", "failed")),
                exitCode=item.get("exitCode"),
                startedAt=str(item.get("startedAt", "")),
                finishedAt=item.get("finishedAt"),
                cwd=str(item.get("cwd", str(self.workspace_root))),
                args=list(item.get("args", [])),
            )

    def _persist_history(self) -> None:
        with self.lock:
            payload = [record.to_dict() for record in self.tasks.values()]
            self.history_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def get_mapping(self, task_name: str) -> list[str] | None:
        mapping = self.model.get("mappings", {})
        commands = mapping.get(task_name)
        if not isinstance(commands, list):
            return None
        if not all(isinstance(item, str) for item in commands):
            return None
        return commands

    def enqueue_task(
        self,
        task_name: str,
        args: list[str] | None,
        env: dict[str, str] | None,
        cwd: str | None,
    ) -> str:
        commands = self.get_mapping(task_name)
        if commands is None:
            raise ValueError(f"Unknown task mapping: {task_name}")

        task_id = str(uuid.uuid4())
        cwd_path = self.workspace_root if cwd is None else (self.workspace_root / cwd).resolve()
        if not str(cwd_path).startswith(str(self.workspace_root.resolve())):
            raise ValueError("cwd must stay inside workspace root")

        record = TaskRecord(
            taskId=task_id,
            task=task_name,
            status="queued",
            exitCode=None,
            startedAt=utc_now_iso(),
            finishedAt=None,
            cwd=str(cwd_path),
            args=args or [],
        )
        with self.lock:
            self.tasks[task_id] = record
        self._persist_history()

        thread = threading.Thread(
            target=self._run_task,
            args=(task_id, commands, env or {}, str(cwd_path)),
            daemon=True,
        )
        thread.start()
        return task_id

    def _run_task(self, task_id: str, commands: list[str], env: dict[str, str], cwd: str) -> None:
        log_path = self.logs_dir / f"{task_id}.log"
        with self.lock:
            record = self.tasks[task_id]
            record.status = "running"
            record.startedAt = utc_now_iso()
        self._persist_history()

        merged_env = os.environ.copy()
        for key, value in env.items():
            if isinstance(key, str) and isinstance(value, str):
                merged_env[key] = value

        exit_code = 0
        with log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(f"[{utc_now_iso()}] task={record.task} status=running\n")
            for command in commands:
                log_file.write(f"$ {command}\n")
                log_file.flush()
                proc = subprocess.Popen(
                    command,
                    shell=True,
                    cwd=cwd,
                    env=merged_env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                assert proc.stdout is not None
                for line in proc.stdout:
                    log_file.write(line)
                proc.wait()
                if proc.returncode != 0:
                    exit_code = proc.returncode
                    log_file.write(f"Command failed with exit code {exit_code}\n")
                    break

        with self.lock:
            record = self.tasks[task_id]
            record.exitCode = exit_code
            record.status = "success" if exit_code == 0 else "failed"
            record.finishedAt = utc_now_iso()
        self._persist_history()

    def status(self, task_id: str) -> dict[str, Any] | None:
        with self.lock:
            record = self.tasks.get(task_id)
            if record is None:
                return None
            return {
                "taskId": record.taskId,
                "status": record.status,
                "exitCode": record.exitCode,
                "startedAt": record.startedAt,
                "finishedAt": record.finishedAt,
            }

    def read_log(self, task_id: str, tail: int | None = None) -> str | None:
        log_path = self.logs_dir / f"{task_id}.log"
        if not log_path.exists():
            return None
        text = log_path.read_text(encoding="utf-8")
        if tail is None:
            return text
        lines = text.splitlines()
        return "\n".join(lines[-tail:])

    def verify(self, verify_key: str, target: str) -> dict[str, Any]:
        verifications = self.model.get("verifications", {})
        scoped = verifications.get(verify_key)
        if not isinstance(scoped, dict):
            raise ValueError(f"Unknown verification key: {verify_key}")
        commands = scoped.get(target)
        if not isinstance(commands, list) or not all(isinstance(item, str) for item in commands):
            raise ValueError(f"No verification mapping for target: {target}")

        details: list[dict[str, Any]] = []
        merged_env = os.environ.copy()
        passed = True
        for command in commands:
            proc = subprocess.run(
                command,
                shell=True,
                cwd=str(self.workspace_root),
                env=merged_env,
                capture_output=True,
                text=True,
            )
            detail = {
                "command": command,
                "exitCode": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
            }
            details.append(detail)
            if proc.returncode != 0:
                passed = False
                break
        return {"passed": passed, "details": details}

    def context(self) -> dict[str, Any]:
        devctl = self.model.get("devctl", {})
        stagectl = self.model.get("stagectl", {})
        devctl_path = self.workspace_root / str(devctl.get("path", ""))
        stagectl_path = self.workspace_root / str(stagectl.get("path", ""))

        devcontainer_cli = shutil.which("devcontainer")
        runtime = {
            "workspaceRoot": str(self.workspace_root),
            "devctl": {
                "path": str(devctl_path),
                "exists": devctl_path.exists(),
                "executable": os.access(devctl_path, os.X_OK),
            },
            "stagectl": {
                "path": str(stagectl_path),
                "exists": stagectl_path.exists(),
                "executable": os.access(stagectl_path, os.X_OK),
            },
            "devcontainer": {
                "cliAvailable": devcontainer_cli is not None,
                "devcontainerJsonExists": (self.workspace_root / ".devcontainer" / "devcontainer.json").exists(),
            },
        }
        return {"model": self.model, "runtime": runtime}


def json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def parse_json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0"))
    raw = handler.rfile.read(length) if length else b"{}"
    if not raw:
        return {}
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("JSON body must be an object")
    return data


def make_handler(state: MCPServerState):
    class MCPHandler(BaseHTTPRequestHandler):
        server_version = "NightfallMCP/1.0"

        def log_message(self, fmt: str, *args: Any) -> None:
            return

        def do_GET(self) -> None:
            if self.path == "/mcp/context":
                json_response(self, HTTPStatus.OK, state.context())
                return

            if self.path.startswith("/mcp/status/"):
                task_id = self.path.split("/mcp/status/", 1)[1]
                status_payload = state.status(task_id)
                if status_payload is None:
                    json_response(self, HTTPStatus.NOT_FOUND, {"error": "taskId not found"})
                    return
                json_response(self, HTTPStatus.OK, status_payload)
                return

            if self.path.startswith("/mcp/log/"):
                task_id = self.path.split("/mcp/log/", 1)[1]
                log_text = state.read_log(task_id, tail=200)
                if log_text is None:
                    json_response(self, HTTPStatus.NOT_FOUND, {"error": "log not found"})
                    return
                json_response(self, HTTPStatus.OK, {"taskId": task_id, "log": log_text})
                return

            json_response(self, HTTPStatus.NOT_FOUND, {"error": "not found"})

        def do_POST(self) -> None:
            try:
                payload = parse_json_body(self)
            except (json.JSONDecodeError, ValueError) as exc:
                json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return

            if self.path == "/mcp/exec":
                task_name = payload.get("task")
                args = payload.get("args")
                env = payload.get("env")
                cwd = payload.get("cwd")

                if not isinstance(task_name, str):
                    json_response(self, HTTPStatus.BAD_REQUEST, {"error": "task must be a string"})
                    return
                if args is not None and not isinstance(args, list):
                    json_response(self, HTTPStatus.BAD_REQUEST, {"error": "args must be a list"})
                    return
                if env is not None and not isinstance(env, dict):
                    json_response(self, HTTPStatus.BAD_REQUEST, {"error": "env must be an object"})
                    return
                if cwd is not None and not isinstance(cwd, str):
                    json_response(self, HTTPStatus.BAD_REQUEST, {"error": "cwd must be a string or null"})
                    return

                try:
                    task_id = state.enqueue_task(task_name, args, env, cwd)
                except ValueError as exc:
                    json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                    return
                json_response(self, HTTPStatus.ACCEPTED, {"taskId": task_id, "status": "queued"})
                return

            if self.path == "/mcp/verify":
                verify_key = payload.get("verify")
                target = payload.get("target")
                if not isinstance(verify_key, str) or not isinstance(target, str):
                    json_response(self, HTTPStatus.BAD_REQUEST, {"error": "verify and target must be strings"})
                    return
                try:
                    result = state.verify(verify_key, target)
                except ValueError as exc:
                    json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                    return
                json_response(self, HTTPStatus.OK, result)
                return

            json_response(self, HTTPStatus.NOT_FOUND, {"error": "not found"})

    return MCPHandler


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Nightfall MCP orchestrator server")
    parser.add_argument("--host", default=os.environ.get("MCP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("MCP_PORT", "8765")))
    parser.add_argument("--workspace", default=os.environ.get("MCP_WORKSPACE", "."))
    parser.add_argument("--model", default=os.environ.get("MCP_MODEL_PATH", ".mcp/model.json"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    workspace_root = Path(args.workspace).resolve()
    model_path = (workspace_root / args.model).resolve()
    state = MCPServerState(workspace_root=workspace_root, model_path=model_path)
    handler = make_handler(state)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"MCP server listening on http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()