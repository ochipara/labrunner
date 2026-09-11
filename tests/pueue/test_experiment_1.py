import os
import time
from pathlib import Path
import pytest
from labrunner.pueue import PueueAdapter, TaskState, TaskNotFound


def test_experiment_1_basic_submission(pueue_env):
    adapter = pueue_env.adapter

    task_id = adapter.submit(
        run_id="R_TEST_001",
        argv=["sh", "-c", "echo 'start' && sleep 1 && echo 'end'"],
        cwd=pueue_env.tmp_path,
        env={}
    )

    assert isinstance(task_id, int)

    status = adapter.status(task_id)
    assert status.id == task_id
    assert status.state in (TaskState.QUEUED, TaskState.RUNNING)

    timeout = 10
    start = time.time()
    while time.time() - start < timeout:
        status = adapter.status(task_id)
        if status.state in (TaskState.SUCCEEDED, TaskState.FAILED, TaskState.CANCELLED):
            break
        time.sleep(0.5)

    assert status.state == TaskState.SUCCEEDED
    assert status.exit_code == 0
