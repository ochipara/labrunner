import os
import time
from pathlib import Path
import pytest
from labrunner.pueue import PueueAdapter, TaskState, TaskNotFound

def test_experiment_2_task_state(pueue_env):
    adapter = pueue_env.adapter

    subprocess = __import__('subprocess')
    subprocess.run(["pueue", "--config", str(pueue_env.config_path), "pause"])

    task_id1 = adapter.submit(
        run_id="R_STATE_01",
        argv=["sleep", "2"],
        cwd=pueue_env.tmp_path,
        env={}
    )

    status1 = adapter.status(task_id1)
    assert status1.state == TaskState.QUEUED

    subprocess.run(["pueue", "--config", str(pueue_env.config_path), "start"])

    timeout = 5
    start = time.time()
    while time.time() - start < timeout:
        status1 = adapter.status(task_id1)
        if status1.state == TaskState.RUNNING:
            break
        time.sleep(0.1)
    assert status1.state == TaskState.RUNNING

    start = time.time()
    while time.time() - start < timeout:
        status1 = adapter.status(task_id1)
        if status1.state == TaskState.SUCCEEDED:
            break
        time.sleep(0.1)
    assert status1.state == TaskState.SUCCEEDED

    task_id2 = adapter.submit(
        run_id="R_STATE_02",
        argv=["sh", "-c", "exit 42"],
        cwd=pueue_env.tmp_path,
        env={}
    )
    start = time.time()
    while time.time() - start < timeout:
        status2 = adapter.status(task_id2)
        if status2.state == TaskState.FAILED:
            break
        time.sleep(0.1)
    assert status2.state == TaskState.FAILED
    assert status2.exit_code == 42

    task_id3 = adapter.submit(
        run_id="R_STATE_03",
        argv=["sleep", "10"],
        cwd=pueue_env.tmp_path,
        env={}
    )
    adapter.cancel(task_id3)
    start = time.time()
    while time.time() - start < timeout:
        status3 = adapter.status(task_id3)
        if status3.state == TaskState.CANCELLED:
            break
        time.sleep(0.1)
    assert status3.state == TaskState.CANCELLED
