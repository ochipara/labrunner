# LabRunner Local Supervision Design

**Status:** Phase 1 Completed

## 1. Overview

Based on the Phase 1 evaluation, LabRunner officially adopts **Pueue** as the local process supervisor for executing scientific workloads.

The system is designed with a strict boundary:
- **LabRunner** is responsible for global experiment state, orchestration, tracking runs, deciding which worker receives a job, and providing the scientific environment.
- **Pueue** is strictly responsible for local process execution, grouping/concurrency locks, process tree termination, and capturing basic task outcomes locally.

## 2. Integration Boundary: `PueueAdapter`

The Python `PueueAdapter` isolates LabRunner from the specifics of Pueue's CLI and JSON structures.

LabRunner workers interact exclusively with the adapter interface:
- **`health()`**: Returns boolean status on daemon availability.
- **`submit()`**: Queues a run into Pueue. Safely maps `LABRUNNER_RUN_ID` as a Pueue task `--label` to guarantee deduplication and trackability.
- **`status()`**: Retrieves strongly-typed Enums indicating whether the task is `RUNNING`, `SUCCEEDED`, `FAILED`, etc.
- **`cancel()`**: Instructs Pueue to kill the process group, cleanly severing all child processes.
- **`logs()`**: Extracts the merged stdout/stderr for the given run.
- **`remove()`**: Purges completed task history from Pueue once LabRunner has finalized the global state.

## 3. Slot Management & Concurrency

Pueue's internal `group` feature maps perfectly to LabRunner resource slots.

For example, on a machine with 4 GPUs, the LabRunner worker configures Pueue with 4 groups (`gpu0`, `gpu1`, `gpu2`, `gpu3`), each strictly constrained to `parallelism = 1`.

LabRunner submits an experiment targeting a specific GPU slot by assigning it to the respective Pueue group. Pueue guarantees only 1 process runs on that GPU slot at any time.

## 4. Crash Recovery Model

- **Worker Crash**: If the Python worker crashes, running Pueue tasks are **unaffected**. On restart, the worker queries Pueue, finds tasks matching known `RUN_ID` labels, and syncs their status back to the controller.
- **Daemon/Host Crash**: If the server reboots or `pueued` abruptly dies, running tasks are abruptly terminated by the OS. Upon reboot, `pueued` records those interrupted tasks as `Failed` or `Killed`. LabRunner detects this failure status and flags the run for automatic restart or manual review based on controller policy.

## 5. Duplicate Execution Prevention

The most critical window of failure is submitting a task to Pueue, but the Python worker crashing before saving the generated Pueue Task ID to local state.

**Solution:** The adapter injects the `LABRUNNER_RUN_ID` via Pueue's `--label` parameter. When the worker restarts, before submitting a task, it queries `pueue status --json` to check if a task with that label already exists. If it does, it adopts the existing Task ID, effectively preventing duplicate submissions.
