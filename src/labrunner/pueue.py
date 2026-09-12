import json
import subprocess
import shlex
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from enum import Enum


class PueueError(Exception):
    """Base class for all Pueue-related errors."""


class PueueUnavailable(PueueError):
    """Raised when the Pueue daemon is not responding or cannot be reached."""


class TaskNotFound(PueueError):
    """Raised when querying a task ID that does not exist."""


class SubmissionFailed(PueueError):
    """Raised when task submission fails."""


class CancellationFailed(PueueError):
    """Raised when canceling a task fails."""


class ProtocolError(PueueError):
    """Raised when the response from Pueue is malformed or invalid JSON."""


class TaskState(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    PAUSED = "PAUSED"
    STASHED = "STASHED"


@dataclass
class Health:
    daemon_running: bool
    version: Optional[str] = None


@dataclass
class TaskStatus:
    id: int
    state: TaskState
    exit_code: Optional[int]
    start_time: Optional[str]
    end_time: Optional[str]
    command: str
    path: str
    env: Dict[str, str]
    group: str


@dataclass
class TaskLogs:
    id: int
    output: str


class PueueAdapter:
    """
    Adapter for interacting with a local Pueue daemon via the `pueue` CLI.
    """

    def __init__(self, config_path: Optional[Path] = None):
        """
        :param config_path: Path to the pueue config file (for test isolation).
        """
        self.config_path = config_path

    def _run_cli(self, args: List[str], check: bool = True, env: Optional[Dict[str, str]] = None) -> subprocess.CompletedProcess:
        cmd = ["pueue"]
        if self.config_path:
            cmd.extend(["--config", str(self.config_path)])
        cmd.extend(args)

        try:
            return subprocess.run(cmd, capture_output=True, text=True, check=check, env=env)
        except FileNotFoundError:
            raise PueueUnavailable("pueue CLI executable not found.")
        except subprocess.CalledProcessError as e:
            if check:
                raise
            return e

    def _run_cli_json(self, args: List[str]) -> Any:
        res = self._run_cli([*args, "--json"], check=False)

        if res.returncode != 0:
            if "connecting to daemon" in res.stderr or "Connection refused" in res.stderr or "No such file or directory" in res.stderr:
                raise PueueUnavailable(f"Daemon unavailable: {res.stderr}")

        try:
            return json.loads(res.stdout), res
        except json.JSONDecodeError:
            raise ProtocolError(f"Malformed JSON from pueue: {res.stdout}\nStderr: {res.stderr}")

    def health(self) -> Health:
        try:
            data, res = self._run_cli_json(["status"])
            if res.returncode != 0:
                if "Daemon is not running" in res.stderr or "Connection reset" in res.stderr or "Connection refused" in res.stderr:
                    return Health(daemon_running=False)
                raise PueueUnavailable(f"Error checking health: {res.stderr}")
            return Health(daemon_running=True)
        except PueueUnavailable:
            return Health(daemon_running=False)
        except ProtocolError:
            return Health(daemon_running=False)

    def submit(
        self,
        *,
        run_id: str,
        argv: List[str],
        cwd: Path,
        env: Dict[str, str],
        group: Optional[str] = None,
    ) -> int:
        import os

        command_str = shlex.join(argv)

        run_env = os.environ.copy()
        run_env.update(env)

        args = ["add", "--print-task-id", "--working-directory", str(cwd), "--label", run_id]
        if group:
            args.extend(["--group", group])

        args.append(command_str)

        try:
            res = self._run_cli(args, check=True, env=run_env)
            task_id_str = res.stdout.strip()
            if not task_id_str.isdigit():
                raise SubmissionFailed(f"Pueue did not return a valid task ID. Got: {task_id_str}")
            return int(task_id_str)
        except subprocess.CalledProcessError as e:
            raise SubmissionFailed(f"Failed to submit task: {e.stderr}")

    def status(self, task_id: int) -> TaskStatus:
        data, res = self._run_cli_json(["status"])
        if res.returncode != 0:
            raise PueueUnavailable(f"Pueue status failed: {res.stderr}")

        tasks = data.get("tasks", {})
        task_str = str(task_id)

        if task_str not in tasks:
            raise TaskNotFound(f"Task ID {task_id} not found.")

        task_data = tasks[task_str]

        raw_state = task_data.get("status", {})

        exit_code = None
        start_time = None
        end_time = None

        # Common fields in newer pueue versions are at the top level
        if "start" in task_data:
            start_time = task_data.get("start")
        if "end" in task_data:
            end_time = task_data.get("end")

        if isinstance(raw_state, dict):
            if "Done" in raw_state:
                done_info = raw_state["Done"]

                # In newer pueue versions, "Done" might just map to a string directly (e.g. "Success")
                if isinstance(done_info, str):
                    result = done_info
                else:
                    if start_time is None and "start" in done_info:
                        start_time = done_info.get("start")
                    if end_time is None and "end" in done_info:
                        end_time = done_info.get("end")
                    result = done_info.get("result", done_info)

                if result == "Success" or done_info == "Success":
                    state = TaskState.SUCCEEDED
                    exit_code = 0
                elif isinstance(result, dict) and "FailedToExecute" in result:
                    state = TaskState.FAILED
                elif isinstance(result, dict) and "Failed" in result:
                    state = TaskState.FAILED
                    exit_code = result["Failed"]
                elif result == "Killed" or (isinstance(result, dict) and "Killed" in result):
                    state = TaskState.CANCELLED
                elif isinstance(result, dict) and "Signaled" in result:
                    state = TaskState.CANCELLED
                else:
                    state = TaskState.FAILED
            elif "Running" in raw_state:
                state = TaskState.RUNNING
                if start_time is None and isinstance(raw_state["Running"], dict) and "start" in raw_state["Running"]:
                    start_time = raw_state["Running"].get("start")
            elif "Queued" in raw_state:
                state = TaskState.QUEUED
            elif "Paused" in raw_state:
                state = TaskState.PAUSED
            elif "Stashed" in raw_state:
                state = TaskState.STASHED
            else:
                state = TaskState.FAILED
        elif raw_state == "Running":
            state = TaskState.RUNNING
        elif raw_state == "Queued":
            state = TaskState.QUEUED
        elif raw_state == "Paused":
            state = TaskState.PAUSED
        elif raw_state == "Stashed":
            state = TaskState.STASHED
        elif raw_state == "Locked":
            state = TaskState.QUEUED
        else:
            state = TaskState.FAILED


        return TaskStatus(
            id=task_id,
            state=state,
            exit_code=exit_code,
            start_time=start_time,
            end_time=end_time,
            command=task_data.get("command", ""),
            path=task_data.get("path", ""),
            env=task_data.get("envs", {}),
            group=task_data.get("group", "default")
        )

    def logs(self, task_id: int) -> TaskLogs:
        self.status(task_id)

        res = self._run_cli(["log", str(task_id)], check=False)
        if res.returncode != 0:
            raise PueueError(f"Failed to get logs for task {task_id}: {res.stderr}")

        return TaskLogs(id=task_id, output=res.stdout)

    def cancel(self, task_id: int, max_retries: int = 5, delay_sec: float = 0.2) -> None:
        import time
        res = None
        for attempt in range(max_retries):
            # Check current status; if already terminal, no need to kill
            task_status = self.status(task_id)
            if task_status.state in (TaskState.SUCCEEDED, TaskState.FAILED, TaskState.CANCELLED):
                return

            res = self._run_cli(["kill", str(task_id)], check=False)

            if res.returncode == 0:
                break

            error_msg = res.stdout.strip()
            race_msg = f"The command failed for tasks: {task_id}"

            if res.returncode == 1 and race_msg in error_msg:
                # Re-verify status; the task may have crashed or completed rapidly
                current_status = self.status(task_id)
                if current_status.state not in (TaskState.QUEUED, TaskState.RUNNING):
                    break

                if attempt < max_retries - 1:
                    time.sleep(delay_sec)
                    continue

            break

        # Verify postcondition instead of purely relying on return code
        for _ in range(25):
            status = self.status(task_id)
            if status.state in (TaskState.SUCCEEDED, TaskState.FAILED, TaskState.CANCELLED):
                return
            time.sleep(0.2)

        raise CancellationFailed(
            f"Failed to cancel task {task_id}: "
            f"pueue kill returned {res.returncode if res else 'N/A'}; "
            f"task status is {self.status(task_id).state}; "
            f"stdout: {res.stdout if res else 'N/A'}; stderr: {res.stderr if res else 'N/A'}"
        )

    def remove(self, task_id: int) -> None:
        self.status(task_id)
        res = self._run_cli(["remove", str(task_id)], check=False)
        if res.returncode != 0:
            raise PueueError(f"Failed to remove task {task_id}: {res.stderr}")
