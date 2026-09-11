import os
import time
from pathlib import Path
import pytest
from labrunner.pueue import PueueAdapter, TaskState


def test_experiment_4_logs(pueue_env):
    adapter = pueue_env.adapter
    script = """
import sys
import time

for i in range(3):
    print(f"out {i}")
    sys.stdout.flush()
    print(f"err {i}", file=sys.stderr)
    sys.stderr.flush()
    time.sleep(0.1)
"""
    script_path = pueue_env.tmp_path / "script.py"
    script_path.write_text(script)

    task_id = adapter.submit(
        run_id="R_LOGS_01",
        argv=["python", str(script_path)],
        cwd=pueue_env.tmp_path,
        env={}
    )

    timeout = 10
    start = time.time()
    while time.time() - start < timeout:
        status = adapter.status(task_id)
        if status.state == TaskState.SUCCEEDED:
            break
        time.sleep(0.5)

    assert status.state == TaskState.SUCCEEDED
    logs = adapter.logs(task_id).output
    assert "out 0" in logs
    assert "err 0" in logs
    assert "out 2" in logs
    assert "err 2" in logs


def test_experiment_5_env_vars(pueue_env):
    adapter = pueue_env.adapter
    task_id = adapter.submit(
        run_id="R_ENV_01",
        argv=["sh", "-c", "echo $LABRUNNER_RUN_ID; echo $LABRUNNER_SEED"],
        cwd=pueue_env.tmp_path,
        env={
            "LABRUNNER_RUN_ID": "R_TEST_001",
            "LABRUNNER_SEED": "42 space test ' quote",
            "CUDA_VISIBLE_DEVICES": "2"
        }
    )

    timeout = 5
    start = time.time()
    while time.time() - start < timeout:
        if adapter.status(task_id).state == TaskState.SUCCEEDED:
            break
        time.sleep(0.1)

    logs = adapter.logs(task_id).output
    assert "R_TEST_001" in logs
    assert "42 space test ' quote" in logs


def test_experiment_6_cwd(pueue_env):
    adapter = pueue_env.adapter
    test_cwd = pueue_env.tmp_path / "my_cwd"
    test_cwd.mkdir()

    task_id = adapter.submit(
        run_id="R_CWD_01",
        argv=["sh", "-c", "pwd && touch output.txt"],
        cwd=test_cwd,
        env={}
    )

    timeout = 5
    start = time.time()
    while time.time() - start < timeout:
        if adapter.status(task_id).state == TaskState.SUCCEEDED:
            break
        time.sleep(0.1)

    assert (test_cwd / "output.txt").exists()
    logs = adapter.logs(task_id).output
    assert str(test_cwd) in logs


def test_experiment_7_quoting(pueue_env):
    adapter = pueue_env.adapter
    args = [
        "python", "-c",
        "import sys; print('\\n'.join(sys.argv[1:]))",
        "spaces spaces",
        "'single quotes'",
        "\"double quotes\"",
        "$DOLLAR",
        "*STAR*",
        ";SEMI",
        "(PARENS)",
        "path with spaces"
    ]

    task_id = adapter.submit(
        run_id="R_QUOTE_01",
        argv=args,
        cwd=pueue_env.tmp_path,
        env={}
    )

    timeout = 5
    start = time.time()
    while time.time() - start < timeout:
        if adapter.status(task_id).state == TaskState.SUCCEEDED:
            break
        time.sleep(0.1)

    logs = adapter.logs(task_id).output
    assert "spaces spaces" in logs
    assert "'single quotes'" in logs
    assert "\"double quotes\"" in logs
    assert "$DOLLAR" in logs
    assert "*STAR*" in logs
    assert ";SEMI" in logs
    assert "(PARENS)" in logs
    assert "path with spaces" in logs


def test_experiment_8_cancellation(pueue_env):
    adapter = pueue_env.adapter
    task_id = adapter.submit(
        run_id="R_CANCEL_01",
        argv=["sleep", "60"],
        cwd=pueue_env.tmp_path,
        env={}
    )

    timeout = 5
    start = time.time()
    while time.time() - start < timeout:
        if adapter.status(task_id).state == TaskState.RUNNING:
            break
        time.sleep(0.1)

    assert adapter.status(task_id).state == TaskState.RUNNING
    adapter.cancel(task_id)

    start = time.time()
    while time.time() - start < timeout:
        if adapter.status(task_id).state == TaskState.CANCELLED:
            break
        time.sleep(0.1)

    assert adapter.status(task_id).state == TaskState.CANCELLED


def test_experiment_9_child_termination(pueue_env):
    adapter = pueue_env.adapter
    script = """
import subprocess
import time
import sys

child = subprocess.Popen(["sleep", "60"])
print(f"CHILD_PID={child.pid}")
sys.stdout.flush()

while True:
    time.sleep(1)
"""
    script_path = pueue_env.tmp_path / "parent.py"
    script_path.write_text(script)

    task_id = adapter.submit(
        run_id="R_CHILD_01",
        argv=["python", str(script_path)],
        cwd=pueue_env.tmp_path,
        env={}
    )

    child_pid = None
    timeout = 10
    start = time.time()
    while time.time() - start < timeout:
        if adapter.status(task_id).state == TaskState.RUNNING:
            logs = adapter.logs(task_id).output
            if "CHILD_PID=" in logs:
                for line in logs.splitlines():
                    if line.startswith("CHILD_PID="):
                        child_pid = int(line.split("=")[1])
                        break
            if child_pid is not None:
                break
        time.sleep(0.5)

    assert child_pid is not None
    import psutil
    assert psutil.pid_exists(child_pid)

    adapter.cancel(task_id)
    start = time.time()
    while time.time() - start < timeout:
        if adapter.status(task_id).state == TaskState.CANCELLED:
            break
        time.sleep(0.1)

    time.sleep(0.5)
    assert not psutil.pid_exists(child_pid)
