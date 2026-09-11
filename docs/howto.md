# LabRunner How-To Guide (Phase 1)

This guide covers how to perform common tasks using the `PueueAdapter` from a LabRunner worker.

## 1. Initializing the Adapter

The adapter expects a running Pueue daemon (`pueued`). By default, it connects to the user's default socket.

```python
from labrunner.pueue import PueueAdapter
from pathlib import Path

# Connects to default daemon
adapter = PueueAdapter()

# (For tests or custom instances, you can pass a config_path)
# adapter = PueueAdapter(config_path=Path("/tmp/pueue.yml"))
```

## 2. Checking Daemon Health

Always check if the local daemon is running before attempting operations.

```python
health = adapter.health()
if not health.daemon_running:
    print("Pueue is down!")
```

## 3. Submitting an Experiment

Use `submit` to queue a command. Pass the unique LabRunner Run ID, arguments, working directory, and environment variables.

```python
task_id = adapter.submit(
    run_id="RUN_2023_ABCD",
    argv=["python", "train.py", "--epochs", "100"],
    cwd=Path("/experiments/RUN_2023_ABCD"),
    env={
        "CUDA_VISIBLE_DEVICES": "1",
        "LABRUNNER_SEED": "42"
    },
    group="gpu1" # Optional: assign to a specific concurrency group
)
print(f"Submitted task successfully! Pueue ID: {task_id}")
```

## 4. Polling Task Status

Check the state of an experiment to update the global LabRunner controller.

```python
from labrunner.pueue import TaskState

status = adapter.status(task_id)

if status.state == TaskState.RUNNING:
    print("Experiment is training...")
elif status.state == TaskState.SUCCEEDED:
    print("Finished successfully!")
elif status.state == TaskState.FAILED:
    print(f"Failed with exit code: {status.exit_code}")
```

## 5. Fetching Logs

Fetch the full stdout/stderr of an experiment (during execution or after completion).

```python
logs = adapter.logs(task_id)
print(logs.output)
```

## 6. Cancelling a Run

If a user aborts an experiment globally, LabRunner signals Pueue to terminate the local process tree.

```python
adapter.cancel(task_id)
print("Task and child processes killed.")
```

## 7. Cleaning up History

Once an experiment has successfully completed and LabRunner has secured all results and provenance data, purge the task from local Pueue history.

```python
adapter.remove(task_id)
```
