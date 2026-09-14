# Specification & Implementation Plan: Experiment Runner (`runner.sh`) and Task I/O

## 1. Executive Summary

This plan outlines the complete specification for simplifying the execution, monitoring, and inspection of LabRunner experiments via a unified CLI (`runner.sh` backed by `labrunner.cli`), and defines the formal data input and output contract for tasks.

---

## 2. The Task Data I/O & Environment Contract

A core challenge in reproducible experiment execution is decoupling the task code from machine-specific absolute filesystem paths while ensuring deterministic tracking.

```
+-----------------------------------------------------------------------------------------+
|                                    RUN DIRECTORY                                        |
|                          (~/.labrunner/runs/<run_id>/)                                  |
|                                                                                         |
|  +---------------------------+        +----------------------------------------------+  |
|  | run.json (Provenance)     |        | logs/                                        |  |
|  |   - Snapshot ID           |        |   - stdouterr.log (captured via Pueue)       |  |
|  |   - Dataset Identities    |        +----------------------------------------------+  |
|  |   - Command, Seed, Config |                                                          |
|  +---------------------------+        +----------------------------------------------+  |
|                                       | outputs/  ($LABRUNNER_OUTPUT_DIR)            |  |
|  +---------------------------+        |   - checkpoints/, metrics.json, figures/    |  |
|  | worktree/ (Source Code)   |        +----------------------------------------------+  |
|  |   - Detached Git state    |                                                          |
|  |   - Materialized snapshot |        +----------------------------------------------+  |
|  |   - CWD for execution     |        | status.json                                  |  |
|  +---------------------------+        |   - State, exit code, start/end timestamps   |  |
|                                       +----------------------------------------------+  |
+-----------------------------------------------------------------------------------------+
```

### A. How a Task Knows Where to Load Data From (Input Contract)
When an experiment spec declares datasets:
```yaml
datasets:
  - name: imagenet
    identity: imagenet-2012-v1
```

1. **Dataset Registry Mapping**:
   - LabRunner maintains a local dataset registry (e.g. `~/.labrunner/datasets.yaml` or configured via `LABRUNNER_DATA_ROOT`).
   - Maps dataset name/identity to local disk paths: e.g. `imagenet-2012-v1 -> /data/datasets/imagenet`.
2. **Fast Pre-Flight Verification**:
   - Before task startup, LabRunner validates the dataset against its manifest (`fast_check_dataset`).
3. **Injection via Standard Environment Variables**:
   - `LABRUNNER_DATASET_<NAME_UPPER>`: Direct path to dataset (e.g., `LABRUNNER_DATASET_IMAGENET=/data/datasets/imagenet`).
   - `LABRUNNER_DATA_DIR`: Base directory containing datasets if grouped under a common path.
   - `LABRUNNER_DATASETS_JSON`: JSON map of `{ "<name>": "/path/to/dataset" }`.
4. **Optional Path Placeholders in Command**:
   - Arguments in `experiment.yaml` can optionally reference `${{ datasets.<name>.path }}`, which LabRunner expands prior to process submission.

### B. How a Task Knows Where to Output Results (Output Contract)
1. **Isolated Output Directory**:
   - Each run receives a dedicated output directory: `<run_dir>/outputs/`.
2. **Environment Variable**:
   - `LABRUNNER_OUTPUT_DIR`: Path to the dedicated outputs directory.
   - `LABRUNNER_RUN_DIR`: Path to root run directory.
3. **Execution Context**:
   - `LABRUNNER_RUN_ID`: Unique run identifier.
   - `LABRUNNER_SEED`: Deterministic 32-bit unsigned integer seed.
4. **Preservation**:
   - All files written to `$LABRUNNER_OUTPUT_DIR` (and `./outputs` if relative) are preserved and cataloged in the run's metadata.

---

## 3. CLI Specification (`runner.sh` / `labrunner.cli`)

`runner.sh` acts as the primary user entry point (wrapping `python -m labrunner.cli "$@"` for portability and clean environment setup).

### Core Commands

#### 1. `runner.sh run <experiment.yaml> [options]`
Submits an experiment for execution:
- Options:
  - `--seed <int>`: Override or set random seed.
  - `--group <group>`: Target a specific Pueue slot/group (e.g., `gpu0`, `cpu`).
  - `--detach` / `-d`: Return immediately after submission instead of following logs.
  - `--no-verify`: Skip MD5/mtime dataset integrity check (for rapid iteration).
- **Workflow**:
  1. Parses and validates `experiment.yaml`.
  2. Captures source snapshot of current repo into `~/.labrunner/snapshots/<snapshot_id>`.
  3. Resolves dataset paths from local registry and runs fast verification.
  4. Allocates unique `run_id` (e.g. `run_20260913_112000_a1b2`).
  5. Creates run directory `<runs_dir>/<run_id>/` and writes canonical `run.json` provenance.
  6. Materializes detached Git worktree inside `<run_dir>/worktree`.
  7. Submits task to Pueue with injected env vars (`LABRUNNER_*`) and working directory set to `worktree`.
  8. If not detached, streams task output live until completion.

#### 2. `runner.sh status [run_id]`
- If `run_id` is omitted: lists recent runs in a clean tabular format showing:
  - `RUN ID`, `EXPERIMENT`, `STATUS` (QUEUED, RUNNING, SUCCEEDED, FAILED), `SLOT/GROUP`, `DURATION`, `CREATED`.
- If `run_id` is provided: displays detailed run telemetry, exit code, resource parameters, dataset identities, and source snapshot hash.

#### 3. `runner.sh logs <run_id> [--follow / -f]`
- Displays stdout/stderr captured by Pueue for the specified run.
- Supports continuous live tailing with `-f`.

#### 4. `runner.sh inspect <run_id>` / `runner.sh data <run_id>`
- Displays all outputs and artifacts generated in `$LABRUNNER_OUTPUT_DIR`.
- Lists generated files, file sizes, checkpoints, and summary metrics.
- Provides flags to print paths or open directory:
  - `runner.sh inspect <run_id> --path`: Prints output directory path.
  - `runner.sh inspect <run_id> --cat <filename>`: View content of a specific output file.

#### 5. `runner.sh cancel <run_id>`
- Aborts a running task and terminates its child process group cleanly via Pueue.

#### 6. `runner.sh dataset <subcommand>`
- `runner.sh dataset register <path> --name <name>`: Scans a folder, computes MD5 manifest, and registers it.
- `runner.sh dataset list`: Shows registered datasets and local path bindings.
- `runner.sh dataset verify <name>`: Performs fast/full integrity verification.
