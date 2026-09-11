import os
import time
from pathlib import Path
import pytest
from labrunner.pueue import PueueAdapter, TaskState


def test_experiment_3_exit_codes(pueue_env):
    adapter = pueue_env.adapter

    def run_and_wait(argv):
        task_id = adapter.submit(
            run_id="R_EC",
            argv=argv,
            cwd=pueue_env.tmp_path,
            env={}
        )
        timeout = 5
        start = time.time()
        while time.time() - start < timeout:
            status = adapter.status(task_id)
            if status.state in (TaskState.SUCCEEDED, TaskState.FAILED, TaskState.CANCELLED):
                return status
            time.sleep(0.1)
        return adapter.status(task_id)

    st0 = run_and_wait(["sh", "-c", "exit 0"])
    assert st0.state == TaskState.SUCCEEDED
    assert st0.exit_code == 0

    st1 = run_and_wait(["sh", "-c", "exit 1"])
    assert st1.state == TaskState.FAILED
    assert st1.exit_code == 1

    st2 = run_and_wait(["sh", "-c", "exit 2"])
    assert st2.state == TaskState.FAILED
    assert st2.exit_code == 2

    st42 = run_and_wait(["sh", "-c", "exit 42"])
    assert st42.state == TaskState.FAILED
    assert st42.exit_code == 42

    st_sig = run_and_wait(["sh", "-c", "kill -9 $$"])
    assert st_sig.state == TaskState.FAILED
    assert st_sig.exit_code != 0
