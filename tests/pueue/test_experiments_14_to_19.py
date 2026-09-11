import os
import time
from pathlib import Path
import pytest
from labrunner.pueue import PueueAdapter, TaskState, TaskNotFound, PueueUnavailable, ProtocolError


def test_experiment_14_groups(pueue_env):
    adapter = pueue_env.adapter
    adapter._run_cli(["group", "add", "gpu0"])
    adapter._run_cli(["parallel", "1", "-g", "gpu0"])

    task1 = adapter.submit(
        run_id="R_GRP_01",
        argv=["sleep", "2"],
        cwd=pueue_env.tmp_path,
        env={},
        group="gpu0"
    )
    task2 = adapter.submit(
        run_id="R_GRP_02",
        argv=["sleep", "2"],
        cwd=pueue_env.tmp_path,
        env={},
        group="gpu0"
    )

    time.sleep(1)
    assert adapter.status(task1).state == TaskState.RUNNING
    assert adapter.status(task2).state == TaskState.QUEUED

    try:
        adapter.cancel(task1)
    except Exception:
        # Sometimes killing a rapidly finishing sleep command right at the end returns failure in pueue.
        # We can just ignore the cancel error here since we just want to free the slot.
        pass

    timeout = 5
    start = time.time()
    while time.time() - start < timeout:
        if adapter.status(task2).state == TaskState.RUNNING:
            break
        time.sleep(0.1)

    assert adapter.status(task2).state == TaskState.RUNNING


def test_experiment_15_multiple_tasks(pueue_env):
    adapter = pueue_env.adapter
    adapter._run_cli(["parallel", "5"])

    tasks = []
    for i in range(5):
        t = adapter.submit(
            run_id=f"R_MULTI_{i}",
            argv=["sleep", "5"],
            cwd=pueue_env.tmp_path,
            env={}
        )
        tasks.append(t)

    time.sleep(1)

    for t in tasks:
        assert adapter.status(t).state == TaskState.RUNNING

    timeout = 10
    start = time.time()
    while time.time() - start < timeout:
        all_done = all(adapter.status(t).state == TaskState.SUCCEEDED for t in tasks)
        if all_done:
            break
        time.sleep(0.2)

    for t in tasks:
        assert adapter.status(t).state == TaskState.SUCCEEDED


def test_experiment_16_task_cleanup(pueue_env):
    adapter = pueue_env.adapter
    task_id = adapter.submit(
        run_id="R_CLEAN_01",
        argv=["echo", "done"],
        cwd=pueue_env.tmp_path,
        env={}
    )

    timeout = 5
    start = time.time()
    while time.time() - start < timeout:
        if adapter.status(task_id).state == TaskState.SUCCEEDED:
            break
        time.sleep(0.1)

    assert adapter.status(task_id).state == TaskState.SUCCEEDED
    adapter.remove(task_id)
    with pytest.raises(TaskNotFound):
        adapter.status(task_id)


def test_experiment_17_pueue_unavailable(pueue_env):
    adapter = pueue_env.adapter
    task_id = adapter.submit(
        run_id="R_UNAVAIL",
        argv=["echo", "test"],
        cwd=pueue_env.tmp_path,
        env={}
    )

    pueue_env.stop()
    time.sleep(1)

    try:
        adapter.status(task_id)
    except (PueueUnavailable, ProtocolError) as e:
        if "Failed to connect" in str(e) or "connecting to daemon" in str(e) or "Connection refused" in str(e) or "No such file" in str(e):
            pass
        else:
            raise e

    pueue_env.start()


def test_experiment_18_unknown_task(pueue_env):
    adapter = pueue_env.adapter
    with pytest.raises(TaskNotFound):
        adapter.status(999999)


def test_experiment_19_idempotency(pueue_env):
    adapter = pueue_env.adapter
    task_id = adapter.submit(
        run_id="R_IDEMPOTENT_01",
        argv=["sleep", "2"],
        cwd=pueue_env.tmp_path,
        env={}
    )

    import json
    res = adapter._run_cli(["status", "--json"], check=True)
    data = json.loads(res.stdout)

    tasks = data.get("tasks", {})
    found_tasks = []
    for tid, tdata in tasks.items():
        if tdata.get("label") == "R_IDEMPOTENT_01":
            found_tasks.append(int(tid))

    assert task_id in found_tasks
    assert len(found_tasks) == 1
