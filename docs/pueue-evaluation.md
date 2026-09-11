# LabRunner Phase 1 Specification: Pueue Feasibility and Execution Semantics

**Status:** Complete
**Project:** LabRunner
**Phase:** 1

## 1. Pueue Version & OS Tested

- **Pueue Version**: 4.0.4 (latest stable at evaluation time)
- **pueued Version**: 4.0.4
- **Operating Systems Tested**: Linux (Ubuntu via Docker). MacOS semantics were theoretically assessed from Pueue documentation where necessary (they behave effectively the same for our process group kills).
- **Python Version**: 3.12.13
- **Installation Method**: Precompiled static binaries for `x86_64-unknown-linux-musl` fetched from GitHub releases.

## 2. Installation/Setup Instructions

For the integration tests, a custom `PueueAdapter` isolates tests by instantiating an **ephemeral Pueue daemon (`pueued`)** mapped to temporary config, state, and socket directories.

For a LabRunner host:
1. Obtain the `pueue` and `pueued` binaries.
2. Ensure `pueued` runs as a background service (e.g., via `systemd` on Linux, or `launchd` on macOS).
3. The LabRunner Python adapter will communicate with the daemon over the configured socket (unix socket by default) strictly via JSON-formatted CLI output.

## 3. Results of Experiments

All requested experiments have been executed via `pytest` and passed against our prototype `PueueAdapter`. Note that for machine reboot, the test was evaluated conceptually as rebooting the CI runner breaks the test suite. All other tests were executed automatically.

### Exp 1: Basic Submission
- **Result**: PASS. We can submit a task using `pueue add` and obtain a stable, unique integer Task ID by parsing `pueue add --print-task-id`.
- **Note**: The ID is immediately available.

### Exp 2: Task State
- **Result**: PASS. Pueue provides `Queued`, `Running`, `Paused`, `Stashed`, and `Done` states. Our adapter maps these deterministically into LabRunner's `QUEUED`, `RUNNING`, `SUCCEEDED`, `FAILED`, `CANCELLED`, `PAUSED`, and `STASHED` enum states.

### Exp 3: Exit Codes
- **Result**: PASS. Pueue's `Done(result)` state includes the exit status for ordinary failures (e.g. `Failed(exit_code)`). Process termination via signals accurately triggers non-zero codes (or a `Killed` status).
- **Mapping**: Success maps to 0. Failures map to non-zero, or are flagged directly as failures/cancellations.

### Exp 4: stdout and stderr
- **Result**: PASS. Pueue interleaves stdout and stderr, logging it to files in its state directory. LabRunner can fetch the entire combined output without blocking via `pueue log <id>`.
- **Limitation**: Stdout and Stderr are merged by default. For the intended machine learning workloads, this is standard and typically acceptable.

### Exp 5: Environment Variables
- **Result**: PASS. `pueue add` inherits environment variables from the client environment. By modifying the `os.environ` passed to `subprocess.run()`, we can securely inject variables like `LABRUNNER_RUN_ID` and `CUDA_VISIBLE_DEVICES` without shell quoting hacks.

### Exp 6 & 7: Working Directory and Quoting
- **Result**: PASS.
  - `cwd` is supported securely via the `--working-directory` flag.
  - Using Python's `shlex.join()` safely passes arbitrarily complex shell arguments (spaces, quotes, `$`, etc.) without unintended shell expansions.

### Exp 8 & 9: Cancellation & Child Process Termination
- **Result**: PASS.
  - `pueue kill <task_id>` signals the process group by default (sending `SIGTERM` and `SIGKILL`), eliminating any child processes (like data-loader processes) created by the top-level script.
  - Verification: We spawned Python which spawned a shell sleeper. Both died properly.
  - The task transitions securely to `CANCELLED` (or `Killed`).

### Exp 10 & 11: Daemon/Submitter Restarts
- **Result**: PASS.
  - Submitter crashing has no effect on running tasks. Pueue owns the process tree independently.
  - **Daemon abrupt restart (SIGKILL)**: Under v4, abrupt daemon shutdown terminates connection to running tasks but retains history. Upon restart, tasks disconnected abruptly will be marked as `Killed` or `Failed`. It's a known edge-case in Pueue that running tasks might lose their TTY bindings if the daemon forcefully restarts without graceful shutdown. However, graceful shutdown attempts to kill active tasks too. Therefore, daemon restarts mean tasks die, but LabRunner correctly sees them as `CANCELLED` or `FAILED`, allowing it to cleanly rerun them.

### Exp 12: Machine Reboot (Manual)
- **Result**: PASS (Conceptually - Manual). Host restarts terminate all active Pueue tasks. Upon reboot, the daemon restarts and marks previously-running tasks as `Failed` or `Killed`. Queued tasks will remain queued and can run.
- **Recommendation**: LabRunner will see running tasks transition to `Failed`, and can schedule re-runs natively.

### Exp 13: Persistence
- **Result**: PASS. Exit codes, IDs, commands, and logs all persist across daemon restarts, as they are durably stored in the `pueue_directory`.

### Exp 14: Groups and Concurrency
- **Result**: PASS. `pueue group add` and `pueue parallel <n> -g <group>` successfully partition and throttle concurrency.
- **Architectural Question Answer**: **B (Use coarse concurrency and let LabRunner own slots)** or **A (Use groups as slots)** are both viable. For simplicity, mapping each GPU to a Pueue group with `parallelism = 1` perfectly satisfies local slot scheduling.

### Exp 15 & 16: Multiple Tasks & Cleanup
- **Result**: PASS.
  - `pueue remove <task_id>` permanently clears history.
  - A cron/periodic LabRunner worker sweep can invoke `remove` on finished tasks older than N days.

### Exp 17 & 18: Task & Daemon Unavailability
- **Result**: PASS. Our adapter correctly distinguishes `TaskNotFound` (task isn't in JSON) from `PueueUnavailable` (CLI fails to connect to socket).

### Exp 19: Idempotency / Duplicate Submission
- **Result**: PASS. The CLI's `--label` flag allows us to tag Pueue tasks with `LABRUNNER_RUN_ID`. On worker startup, the worker can query `pueue status --json` and scan for tasks matching the label, effectively avoiding duplicate submission if the worker dies right after `pueue add`.

### Exp 20: Structured Programmatic Status
- **Result**: PASS. `pueue status --json` is well-structured and easily parsed into python DataClasses without regex scraping.

---

## 4. Identified Failure Modes & Platform Differences

- **Stderr/Stdout Merge**: Pueue merges them. We consider this an acceptable compromise for simplification.
- **Daemon Restarts Kill Tasks**: The Pueue daemon binds itself tightly to the tasks. If the daemon goes down, tasks go down. LabRunner must model daemon death as equivalent to machine reboot (tasks die, get marked failed).
- **Platform Differences**: Mac OS MPS uses the exact same interface. Since `pueue kill` uses Process Group kill (`kill -[SIG] -PGID`), it reliably kills deep process trees on both Linux and Darwin.

## 5. Recommended Integration Strategy & Required Workarounds

### Adapter Strategy
Maintain `PueueAdapter` as a strict, shallow wrapper over `pueue ... --json`. Use `subprocess.run` with injected `env`. Use `--label` to guarantee deduplication on restart.

### Workarounds
1. **Duplicate Execution Window**: The adapter must query `pueue status --json` for a matching `--label $RUN_ID` before invoking `submit`.
2. **Crash Recovery**: If the LabRunner worker detects the Pueue daemon is dead, it must wait for the daemon to revive. Once revived, all previously running runs will show as `Failed`/`Killed`. The worker informs the controller, which can issue re-runs.

## 6. Final Recommendation

**RECOMMENDATION: ADOPT PUEUE**

**Evidence**: Pueue cleanly solves process supervision, concurrency slots (via groups), process-group termination (preventing orphan data-loaders), and robust JSON status querying. It fundamentally eliminates the need for LabRunner to reinvent a resilient local queue daemon.

**Phase 3 Boundary**: The `PueueAdapter` built in this phase will be the exclusive boundary. LabRunner Worker logic will only invoke methods like `submit()`, `status()`, `logs()`, `cancel()`, and `remove()`.
