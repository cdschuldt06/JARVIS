from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import subprocess

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from jarvis.core.config import get_settings
from jarvis.database.models import CodexSandboxMode, CodexTask, CodexTaskStatus
from jarvis.handoffs.service import HandoffService


SANDBOX_TO_CLI = {
    CodexSandboxMode.read_only: "read-only",
    CodexSandboxMode.workspace_write: "workspace-write",
}
CLI_TO_SANDBOX = {
    "read-only": CodexSandboxMode.read_only,
    "read_only": CodexSandboxMode.read_only,
    "workspace-write": CodexSandboxMode.workspace_write,
    "workspace_write": CodexSandboxMode.workspace_write,
}


class CodexTaskService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()
        self.handoffs = HandoffService(db)

    def create_task(
        self,
        project_id: int | None,
        user_request: str,
        title: str | None = None,
        sandbox_mode: CodexSandboxMode | None = None,
    ) -> CodexTask:
        generated_brief = self.generate_brief(project_id, user_request)
        task = CodexTask(
            project_id=project_id,
            title=title or self._title_from_request(user_request),
            user_request=user_request,
            generated_brief=generated_brief,
            status=CodexTaskStatus.ready,
            sandbox_mode=sandbox_mode or self._default_sandbox(),
        )
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)
        return task

    def generate_brief(self, project_id: int | None, user_request: str) -> str:
        return self.handoffs.generate_brief(user_request, project_id)

    def approve_task(self, task_id: int) -> CodexTask:
        task = self.read_task(task_id)
        if task.status not in {
            CodexTaskStatus.draft,
            CodexTaskStatus.ready,
            CodexTaskStatus.failed,
            CodexTaskStatus.timed_out,
            CodexTaskStatus.blocked,
        }:
            raise HTTPException(status_code=409, detail=f"Cannot approve a task with status {task.status.value}.")
        task.status = CodexTaskStatus.approved
        self.db.commit()
        self.db.refresh(task)
        return task

    def update_brief(self, task_id: int, generated_brief: str) -> CodexTask:
        task = self.read_task(task_id)
        if task.status not in {
            CodexTaskStatus.draft,
            CodexTaskStatus.ready,
            CodexTaskStatus.failed,
            CodexTaskStatus.timed_out,
            CodexTaskStatus.blocked,
        }:
            raise HTTPException(status_code=409, detail=f"Cannot edit a brief for a task with status {task.status.value}.")
        task.generated_brief = generated_brief
        self.db.commit()
        self.db.refresh(task)
        return task

    def run_task(self, task_id: int) -> CodexTask:
        task = self.read_task(task_id)
        if task.status != CodexTaskStatus.approved:
            raise HTTPException(status_code=409, detail="Codex task must be approved before it can run.")

        command = self._command_for_task(task)
        timeout_seconds = self._timeout_seconds()
        auth_error = self._chatgpt_auth_error()
        if auth_error:
            task.status = CodexTaskStatus.failed
            task.completed_at = datetime.utcnow()
            task.codex_stderr = auth_error
            task.codex_result_summary = auth_error
            self.db.commit()
            self.db.refresh(task)
            return task

        task.status = CodexTaskStatus.running
        task.started_at = datetime.utcnow()
        task.completed_at = None
        task.codex_command = self._render_command(command)
        task.codex_stdout = ""
        task.codex_stderr = ""
        task.codex_result_summary = ""
        self.db.commit()

        try:
            process = subprocess.Popen(
                command,
                cwd=self.settings.codex_working_directory,
                shell=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=self._codex_subprocess_env(),
            )
            try:
                stdout, stderr = process.communicate(timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
                task.codex_stdout = stdout or ""
                task.codex_stderr = (stderr or "").strip()
                timeout_message = f"Codex execution timed out after {timeout_seconds} seconds."
                if task.codex_stderr:
                    task.codex_stderr = f"{task.codex_stderr}\n{timeout_message}"
                else:
                    task.codex_stderr = timeout_message
                task.codex_result_summary = timeout_message
                task.completed_at = datetime.utcnow()
                task.status = CodexTaskStatus.timed_out
            else:
                task.codex_stdout = stdout or ""
                task.codex_stderr = stderr or ""
                task.codex_result_summary = self._result_summary(task.codex_stdout, task.codex_stderr)
                task.completed_at = datetime.utcnow()
                task.status = CodexTaskStatus.completed if process.returncode == 0 else CodexTaskStatus.failed
        except OSError as exc:
            task.codex_stderr = str(exc)
            task.codex_result_summary = f"Could not start Codex CLI: {exc}"
            task.completed_at = datetime.utcnow()
            task.status = CodexTaskStatus.failed
        except Exception as exc:
            task.codex_stderr = str(exc)
            task.codex_result_summary = f"Codex execution failed unexpectedly: {exc}"
            task.completed_at = datetime.utcnow()
            task.status = CodexTaskStatus.failed

        self.db.commit()
        self.db.refresh(task)
        return task

    def mark_failed(self, task_id: int, reason: str | None = None) -> CodexTask:
        task = self.read_task(task_id)
        if task.status != CodexTaskStatus.running:
            raise HTTPException(status_code=409, detail=f"Only running tasks can be marked failed. Current status: {task.status.value}.")
        message = reason or "Task was manually marked failed from the Codex tab."
        task.status = CodexTaskStatus.failed
        task.completed_at = datetime.utcnow()
        task.codex_result_summary = message
        if task.codex_stderr:
            task.codex_stderr = f"{task.codex_stderr}\n{message}"
        else:
            task.codex_stderr = message
        self.db.commit()
        self.db.refresh(task)
        return task

    def reset_to_ready(self, task_id: int) -> CodexTask:
        task = self.read_task(task_id)
        if task.status not in {
            CodexTaskStatus.running,
            CodexTaskStatus.failed,
            CodexTaskStatus.timed_out,
            CodexTaskStatus.blocked,
            CodexTaskStatus.completed,
        }:
            raise HTTPException(status_code=409, detail=f"Cannot reset a task with status {task.status.value}.")
        task.status = CodexTaskStatus.ready
        task.started_at = None
        task.completed_at = None
        task.codex_result_summary = "Task was reset to ready and must be approved before it can run."
        self.db.commit()
        self.db.refresh(task)
        return task

    def read_task(self, task_id: int) -> CodexTask:
        task = self.db.get(CodexTask, task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Codex task not found.")
        return task

    def list_tasks(self, project_id: int | None = None) -> list[CodexTask]:
        stmt = select(CodexTask)
        if project_id is not None:
            stmt = stmt.where(CodexTask.project_id == project_id)
        return self.db.scalars(stmt.order_by(CodexTask.created_at.desc())).all()

    def _command_for_task(self, task: CodexTask) -> list[str]:
        cli_path = self.settings.codex_cli_path.strip() or "codex"
        working_directory = Path(self.settings.codex_working_directory)
        sandbox = SANDBOX_TO_CLI.get(task.sandbox_mode, "read-only")
        prompt = (
            f"{task.generated_brief.strip()}\n\n"
            "Execution constraints:\n"
            "- Run only through this Codex task.\n"
            "- Respect the configured sandbox.\n"
            "- Report what changed, what was verified, and any blockers."
        )
        return [
            cli_path,
            "exec",
            "--json",
            "--cd",
            str(working_directory),
            "--sandbox",
            sandbox,
            prompt,
        ]

    def _render_command(self, command: list[str]) -> str:
        rendered = []
        for part in command:
            if "\n" in part:
                rendered.append("<generated brief>")
            elif " " in part:
                rendered.append(f'"{part}"')
            else:
                rendered.append(part)
        return " ".join(rendered)

    def _result_summary(self, stdout: str, stderr: str) -> str:
        final_message = ""
        last_error = ""
        for line in stdout.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "item.completed":
                item = event.get("item") or {}
                if item.get("type") == "agent_message":
                    final_message = str(item.get("text") or final_message)
            elif event.get("type") == "error":
                last_error = str(event.get("message") or event)
        if final_message:
            return final_message.strip()
        if last_error:
            return last_error.strip()
        if stderr.strip():
            return stderr.strip()[-2000:]
        return stdout.strip()[-2000:]

    def _timeout_seconds(self) -> int:
        return max(1, int(self.settings.codex_exec_timeout_seconds or 300))

    def _chatgpt_auth_error(self) -> str:
        if not self.settings.codex_require_chatgpt_auth:
            return ""

        auth_path = Path.home() / ".codex" / "auth.json"
        if not auth_path.exists():
            return "Codex ChatGPT auth is required, but ~/.codex/auth.json was not found. Run `codex login` with your ChatGPT account."

        try:
            auth = json.loads(auth_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return f"Codex ChatGPT auth is required, but auth.json could not be read: {exc}"

        auth_mode = str(auth.get("auth_mode") or "").strip().lower()
        if auth_mode != "chatgpt":
            return f"Codex ChatGPT auth is required for Jarvis tasks. Current Codex auth_mode is `{auth_mode or 'unknown'}`."
        return ""

    def _codex_subprocess_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env.pop("OPENAI_API_KEY", None)
        env.pop("CODEX_API_KEY", None)
        return env

    def _default_sandbox(self) -> CodexSandboxMode:
        return CLI_TO_SANDBOX.get(self.settings.codex_default_sandbox.strip().lower(), CodexSandboxMode.read_only)

    def _title_from_request(self, user_request: str) -> str:
        cleaned = " ".join(user_request.strip().split())
        if not cleaned:
            return "Codex task"
        return cleaned[:120]
