#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fcntl
import json
import os
import shutil
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


REPO_LOCK_FILE = "/tmp/nightfall-repo.lock"


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
    dependsOn: list[str]
    significantTask: bool
    extensionRecommendation: str | None

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
            "dependsOn": self.dependsOn,
            "significantTask": self.significantTask,
            "extensionRecommendation": self.extensionRecommendation,
        }


TERMINAL_STATUSES = {"success", "failed", "completed"}
SUCCESS_STATUSES = {"success", "completed"}


def normalize_status(status: str) -> str:
    if status in SUCCESS_STATUSES:
        return "success"
    if status == "failed":
        return "failed"
    if status in {"queued", "running", "waiting"}:
        return status
    return status


def is_terminal_status(status: str) -> bool:
    return status in TERMINAL_STATUSES


class MCPServerState:
    def __init__(self, workspace_root: Path, model_path: Path):
        self.workspace_root = workspace_root
        self.model_path = model_path
        self.logs_dir = workspace_root / ".mcp" / "logs"
        self.tasks_dir = workspace_root / ".mcp" / "tasks"
        self.history_file = self.tasks_dir / "history.json"
        self.extensions_file = self.tasks_dir / "extensions.json"
        self.lock = threading.Lock()
        self.tasks: dict[str, TaskRecord] = {}
        self.extensions: list[dict[str, Any]] = []
        self.model = self._load_model()
        self._ensure_dirs()
        self._load_history()
        self._load_extensions()

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
                dependsOn=list(item.get("dependsOn", [])),
                significantTask=bool(item.get("significantTask", False)),
                extensionRecommendation=(
                    str(item.get("extensionRecommendation"))
                    if item.get("extensionRecommendation") is not None
                    else None
                ),
            )

    def _persist_history(self) -> None:
        with self.lock:
            payload = [record.to_dict() for record in self.tasks.values()]
            self.history_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _load_extensions(self) -> None:
        if not self.extensions_file.exists():
            return
        try:
            raw = json.loads(self.extensions_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return
        if isinstance(raw, list):
            self.extensions = [item for item in raw if isinstance(item, dict)]

    def _persist_extensions(self) -> None:
        with self.lock:
            self.extensions_file.write_text(
                json.dumps(self.extensions, indent=2),
                encoding="utf-8",
            )

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
        depends_on: list[str] | None,
        significant_task: bool = False,
        extension_recommendation: str | None = None,
    ) -> str:
        commands = self.get_mapping(task_name)
        if commands is None:
            raise ValueError(f"Unknown task mapping: {task_name}")

        task_id = str(uuid.uuid4())
        cwd_path = self.workspace_root if cwd is None else (self.workspace_root / cwd).resolve()
        if not str(cwd_path).startswith(str(self.workspace_root.resolve())):
            raise ValueError("cwd must stay inside workspace root")

        validated_dependencies: list[str] = []
        for dep_task_id in depends_on or []:
            if not isinstance(dep_task_id, str) or not dep_task_id.strip():
                raise ValueError("dependsOn entries must be non-empty strings")
            dep = self.tasks.get(dep_task_id)
            if dep is None:
                raise ValueError(f"dependsOn taskId not found: {dep_task_id}")
            if dep_task_id == task_id:
                raise ValueError("dependsOn cannot include the current task")
            validated_dependencies.append(dep_task_id)

        record = TaskRecord(
            taskId=task_id,
            task=task_name,
            status="queued",
            exitCode=None,
            startedAt=utc_now_iso(),
            finishedAt=None,
            cwd=str(cwd_path),
            args=args or [],
            dependsOn=validated_dependencies,
            significantTask=significant_task,
            extensionRecommendation=extension_recommendation.strip() if extension_recommendation else None,
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
            record.status = "waiting" if record.dependsOn else "running"
            if not record.dependsOn:
                record.startedAt = utc_now_iso()
        self._persist_history()

        merged_env = os.environ.copy()
        for key, value in env.items():
            if isinstance(key, str) and isinstance(value, str):
                merged_env[key] = value
        merged_env["DEVCTL_GLOBAL_LOCK_HELD"] = "1"

        exit_code = 0
        with log_path.open("a", encoding="utf-8") as log_file:
            if record.dependsOn:
                deps = ",".join(record.dependsOn)
                log_file.write(f"[{utc_now_iso()}] task={record.task} status=waiting dependsOn={deps}\n")
            else:
                log_file.write(f"[{utc_now_iso()}] task={record.task} status=running\n")

            if record.dependsOn:
                wait_failure: str | None = None
                while True:
                    with self.lock:
                        dep_records = [(dep_id, self.tasks.get(dep_id)) for dep_id in record.dependsOn]
                    missing = [dep_id for dep_id, dep_record in dep_records if dep_record is None]
                    if missing:
                        wait_failure = f"Dependency missing: {missing[0]}"
                        break

                    failed_dep = next(
                        (
                            dep_id
                            for dep_id, dep_record in dep_records
                            if dep_record is not None and normalize_status(dep_record.status) == "failed"
                        ),
                        None,
                    )
                    if failed_dep is not None:
                        wait_failure = f"Dependency failed: {failed_dep}"
                        break

                    all_done = all(
                        dep_record is not None and normalize_status(dep_record.status) == "success"
                        for _, dep_record in dep_records
                    )
                    if all_done:
                        break

                    time.sleep(0.25)

                if wait_failure is not None:
                    exit_code = 1
                    log_file.write(f"{wait_failure}\n")
                    with self.lock:
                        record = self.tasks[task_id]
                        record.exitCode = exit_code
                        record.status = "failed"
                        record.finishedAt = utc_now_iso()
                    self._persist_history()
                    return

                with self.lock:
                    record = self.tasks[task_id]
                    record.status = "running"
                    record.startedAt = utc_now_iso()
                self._persist_history()
                log_file.write(f"[{utc_now_iso()}] dependencies satisfied; task={record.task} status=running\n")

            for command in commands:
                log_file.write(f"$ {command}\n")
                log_file.flush()
                os.makedirs(os.path.dirname(REPO_LOCK_FILE), exist_ok=True)
                with open(REPO_LOCK_FILE, "w", encoding="utf-8") as lock_handle:
                    fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
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

        if record.significantTask and record.extensionRecommendation:
            self.propose_extension(
                recommendation=record.extensionRecommendation,
                related_task_id=record.taskId,
                task_name=record.task,
                source="post_significant_task_review",
            )

    def status(self, task_id: str) -> dict[str, Any] | None:
        with self.lock:
            record = self.tasks.get(task_id)
            if record is None:
                return None
            return {
                "taskId": record.taskId,
                "status": record.status,
                "normalizedStatus": normalize_status(record.status),
                "terminal": is_terminal_status(record.status),
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
            "extensionPolicy": {
                "enabled": True,
                "extensionsBacklogCount": len(self.extensions),
                "extensionsBacklogPath": str(self.extensions_file),
            },
            "statusModel": {
                "terminalStatuses": ["success", "failed", "completed"],
                "preferredPollingTerminalStatuses": ["success", "failed"],
            },
        }
        return {"model": self.model, "runtime": runtime}

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
            "createdAt": utc_now_iso(),
            "source": source,
            "relatedTaskId": related_task_id,
            "task": task_name,
            "recommendation": recommendation,
            "status": "proposed",
        }
        self.extensions.append(proposal)
        self._persist_extensions()
        return proposal


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

            if self.path == "/mcp/extensions":
                json_response(self, HTTPStatus.OK, {"extensions": state.extensions})
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
                depends_on = payload.get("dependsOn")
                significant_task = payload.get("significantTask", False)
                extension_recommendation = payload.get("extensionRecommendation")

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
                if depends_on is not None:
                    if not isinstance(depends_on, list) or not all(isinstance(item, str) for item in depends_on):
                        json_response(self, HTTPStatus.BAD_REQUEST, {"error": "dependsOn must be an array of taskId strings"})
                        return
                if not isinstance(significant_task, bool):
                    json_response(self, HTTPStatus.BAD_REQUEST, {"error": "significantTask must be a boolean"})
                    return
                if extension_recommendation is not None and not isinstance(extension_recommendation, str):
                    json_response(self, HTTPStatus.BAD_REQUEST, {"error": "extensionRecommendation must be a string or null"})
                    return

                try:
                    task_id = state.enqueue_task(
                        task_name,
                        args,
                        env,
                        cwd,
                        depends_on,
                        significant_task=significant_task,
                        extension_recommendation=extension_recommendation,
                    )
                except ValueError as exc:
                    json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                    return
                json_response(self, HTTPStatus.ACCEPTED, {"taskId": task_id, "status": "queued"})
                return

            if self.path == "/mcp/extensions/propose":
                recommendation = payload.get("recommendation")
                related_task_id = payload.get("relatedTaskId")
                task_name = payload.get("task")

                if not isinstance(recommendation, str) or not recommendation.strip():
                    json_response(self, HTTPStatus.BAD_REQUEST, {"error": "recommendation must be a non-empty string"})
                    return
                if related_task_id is not None and not isinstance(related_task_id, str):
                    json_response(self, HTTPStatus.BAD_REQUEST, {"error": "relatedTaskId must be a string or null"})
                    return
                if task_name is not None and not isinstance(task_name, str):
                    json_response(self, HTTPStatus.BAD_REQUEST, {"error": "task must be a string or null"})
                    return

                proposal = state.propose_extension(
                    recommendation=recommendation.strip(),
                    related_task_id=related_task_id,
                    task_name=task_name,
                    source="manual",
                )
                json_response(self, HTTPStatus.CREATED, proposal)
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