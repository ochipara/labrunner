import os
import time
from pathlib import Path
import pytest
from labrunner.pueue import PueueAdapter, TaskState


def test_experiment_10_daemon_restart(pueue_env):
    adapter = pueue_env.adapter

    task_id = adapter.submit(
        run_id="R_RESTART_01",
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

    try:
        import psutil
        sleep_procs = [p for p in psutil.process_iter(['name']) if 'sleep' in p.info['name']]
    except ImportError:
        sleep_procs = []

    daemon_pid = pueue_env.daemon_process.pid
    os.kill(daemon_pid, 9)
    pueue_env.daemon_process.wait()
    pueue_env.daemon_process = None

    time.sleep(1)
    assert not adapter.health().daemon_running

    pueue_env.start()
    assert adapter.health().daemon_running
    assert adapter.status(task_id).state == TaskState.CANCELLED

    try:
        import psutil
        for p in sleep_procs:
            if psutil.pid_exists(p.pid):
                p.kill()
    except (ImportError, Exception):
        pass


def test_experiment_11_submitter_failure(pueue_env):
    adapter1 = PueueAdapter(pueue_env.config_path)
    task_id = adapter1.submit(
        run_id="R_FAIL_01",
        argv=["sleep", "2"],
        cwd=pueue_env.tmp_path,
        env={}
    )

    del adapter1
    adapter2 = PueueAdapter(pueue_env.config_path)
    assert adapter2.status(task_id).state in (TaskState.QUEUED, TaskState.RUNNING, TaskState.SUCCEEDED)


def test_experiment_13_persistence(pueue_env):
    adapter = pueue_env.adapter
    task_id = adapter.submit(
        run_id="R_PERSIST_01",
        argv=["sh", "-c", "echo 'persisted log' && exit 42"],
        cwd=pueue_env.tmp_path,
        env={}
    )

    timeout = 5
    start = time.time()
    while time.time() - start < timeout:
        if adapter.status(task_id).state == TaskState.FAILED:
            break
        time.sleep(0.1)

    pueue_env.stop()
    time.sleep(1)
    pueue_env.start()

    status = adapter.status(task_id)
    assert status.state == TaskState.FAILED
    assert status.exit_code == 42
    assert "persisted log" in adapter.logs(task_id).output
    assert status.start_time is not None
    assert status.end_time is not None
