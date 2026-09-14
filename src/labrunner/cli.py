import argparse
import sys
import os
import json
import time
from pathlib import Path

from labrunner.runner.executor import ExperimentExecutor, ExecutorError
from labrunner.registry.dataset_registry import DatasetRegistry
from labrunner.pueue import PueueAdapter, TaskState


def format_table(headers, rows):
    # Simple table formatter without requiring 'tabulate'
    if not rows:
        return "  ".join(headers)

    col_widths = [max(len(str(item)) for item in col) for col in zip(*rows, headers)]

    table = []
    header_row = "  ".join(str(h).ljust(w) for h, w in zip(headers, col_widths))
    table.append(header_row)
    table.append("-" * len(header_row))

    for row in rows:
        table.append("  ".join(str(item).ljust(w) for item, w in zip(row, col_widths)))

    return "\n".join(table)


def run_command(args):
    executor = ExperimentExecutor()
    try:
        run_id = executor.submit(
            experiment_file=Path(args.experiment_yaml),
            seed_override=args.seed,
            group=args.group,
            no_verify=args.no_verify
        )
        print(f"Successfully submitted run: {run_id}")

        if not args.detach:
            print("Following logs...")
            # We need to wait for the task to start to get logs
            status = executor.get_status(run_id)
            task_id = status["pueue_task_id"]

            pueue = PueueAdapter()
            # Tailing logs isn't fully supported out of the box in PueueAdapter,
            # we'll just poll for completion and then fetch logs, or use subprocess to tail
            # For simplicity in this spec, we will poll and print.
            last_len = 0
            while True:
                task_status = pueue.status(task_id)
                try:
                    logs = pueue.logs(task_id)
                    new_output = logs.output[last_len:]
                    if new_output:
                        print(new_output, end="", flush=True)
                        last_len = len(logs.output)
                except Exception:
                    pass

                if task_status.state in (TaskState.SUCCEEDED, TaskState.FAILED, TaskState.CANCELLED):
                    break
                time.sleep(1)

            # Final fetch
            try:
                logs = pueue.logs(task_id)
                new_output = logs.output[last_len:]
                if new_output:
                    print(new_output, end="", flush=True)
            except Exception:
                pass

            print(f"\nRun {run_id} finished with state: {task_status.state.value}")
            if task_status.exit_code is not None:
                sys.exit(task_status.exit_code)

    except ExecutorError as e:
        print(f"Error submitting experiment: {e}", file=sys.stderr)
        sys.exit(1)


def status_command(args):
    executor = ExperimentExecutor()
    if args.run_id:
        try:
            status = executor.get_status(args.run_id)
            run_dir = executor.runs_dir / args.run_id

            print(f"Run ID: {args.run_id}")
            print(f"Status: {status.get('status', 'UNKNOWN')}")
            print(f"Pueue Task ID: {status.get('pueue_task_id', 'N/A')}")
            print(f"Exit Code: {status.get('exit_code', 'N/A')}")
            print(f"Start Time: {status.get('start_time', 'N/A')}")
            print(f"End Time: {status.get('end_time', 'N/A')}")

            run_json = run_dir / "run.json"
            if run_json.exists():
                with open(run_json, "r") as f:
                    prov = json.load(f)
                    print("\nProvenance:")
                    print(f"  Experiment: {prov.get('experiment', {}).get('name')}")
                    print(f"  Snapshot ID: {prov.get('source', {}).get('snapshot_id')}")
                    print(f"  Seed: {prov.get('seed')}")
                    print("  Datasets:")
                    for ds in prov.get("datasets", []):
                        print(f"    - {ds['name']} ({ds['identity']})")
        except Exception as e:
            print(f"Error getting status: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        # List all runs
        if not executor.runs_dir.exists():
            print("No runs found.")
            return

        runs = []
        for d in sorted(executor.runs_dir.iterdir(), key=os.path.getmtime, reverse=True):
            if d.is_dir() and (d / "status.json").exists():
                try:
                    status = executor.get_status(d.name)

                    experiment_name = "N/A"
                    run_json = d / "run.json"
                    if run_json.exists():
                        with open(run_json, "r") as f:
                            prov = json.load(f)
                            experiment_name = prov.get('experiment', {}).get('name', "N/A")

                    start = status.get('start_time')
                    end = status.get('end_time')
                    duration = "N/A"
                    # Pueue times are like "2023-10-15 14:30:00"
                    if start and end:
                        try:
                            import datetime
                            dt_start = datetime.datetime.fromisoformat(start) if 'T' in start else datetime.datetime.strptime(start, "%Y-%m-%d %H:%M:%S")
                            dt_end = datetime.datetime.fromisoformat(end) if 'T' in end else datetime.datetime.strptime(end, "%Y-%m-%d %H:%M:%S")
                            duration = str(dt_end - dt_start)
                        except Exception:
                            duration = f"{start} - {end}"

                    # Using getctime might not always be the exact run generation time, but it's okay for created
                    import datetime
                    created = datetime.datetime.fromtimestamp(os.path.getmtime(d)).strftime("%Y-%m-%d %H:%M:%S")

                    # pueue group needs another status call, but we can assume default if we don't have it saved
                    # Wait, we can get group from pueue.status(task_id).group
                    # Get the group from the adapter
                    group = "default"
                    try:
                        pueue = PueueAdapter()
                        task_status = pueue.status(status["pueue_task_id"])
                        group = task_status.group
                    except Exception:
                        pass

                    runs.append([
                        d.name,
                        experiment_name,
                        status.get("status", "UNKNOWN"),
                        group,
                        duration,
                        created
                    ])
                except Exception:
                    runs.append([d.name, "ERROR", "ERROR", "ERROR", "ERROR", "ERROR"])

        if not runs:
            print("No runs found.")
        else:
            print(format_table(["RUN ID", "EXPERIMENT", "STATUS", "SLOT/GROUP", "DURATION", "CREATED"], runs))


def logs_command(args):
    executor = ExperimentExecutor()
    try:
        status = executor.get_status(args.run_id)
        task_id = status["pueue_task_id"]

        pueue = PueueAdapter()

        if args.follow:
            last_len = 0
            while True:
                task_status = pueue.status(task_id)
                try:
                    logs = pueue.logs(task_id)
                    new_output = logs.output[last_len:]
                    if new_output:
                        print(new_output, end="", flush=True)
                        last_len = len(logs.output)
                except Exception:
                    pass

                if task_status.state in (TaskState.SUCCEEDED, TaskState.FAILED, TaskState.CANCELLED):
                    break
                time.sleep(1)
        else:
            logs = pueue.logs(task_id)
            print(logs.output)

    except Exception as e:
        print(f"Error getting logs: {e}", file=sys.stderr)
        sys.exit(1)


def inspect_command(args):
    executor = ExperimentExecutor()
    run_dir = executor.runs_dir / args.run_id
    outputs_dir = run_dir / "outputs"

    if not outputs_dir.exists():
        print(f"No outputs directory found for run {args.run_id}")
        sys.exit(1)

    if getattr(args, "path", False):
        print(str(outputs_dir))
        return

    if getattr(args, "cat", None):
        target_file = outputs_dir / args.cat
        if not target_file.exists():
            print(f"File {args.cat} not found in outputs.", file=sys.stderr)
            sys.exit(1)
        with open(target_file, "r") as f:
            print(f.read())
        return

    print(f"Outputs for run {args.run_id} ({outputs_dir}):\n")

    metrics_file = outputs_dir / "metrics.json"
    if metrics_file.exists():
        print("Summary Metrics:")
        with open(metrics_file, "r") as f:
            try:
                metrics = json.load(f)
                print(json.dumps(metrics, indent=2))
            except json.JSONDecodeError:
                print("  [Invalid JSON in metrics.json]")
        print("")

    print("Files:")
    rows = []
    for root, dirs, files in os.walk(outputs_dir):
        for name in files:
            p = Path(root) / name
            rel = p.relative_to(outputs_dir)
            size = p.stat().st_size
            rows.append([str(rel), f"{size} bytes"])

    if rows:
        print(format_table(["File Path", "Size"], rows))
    else:
        print("  (No files generated)")


def cancel_command(args):
    executor = ExperimentExecutor()
    try:
        status = executor.get_status(args.run_id)
        task_id = status["pueue_task_id"]
        pueue = PueueAdapter()
        pueue.cancel(task_id)
        print(f"Cancelled run {args.run_id} (Task ID {task_id}).")
    except Exception as e:
        print(f"Error cancelling run: {e}", file=sys.stderr)
        sys.exit(1)


def dataset_command(args):
    registry = DatasetRegistry()

    if args.dataset_cmd == "register":
        try:
            print(f"Registering dataset {args.name} at {args.path}...")
            identity = registry.register(Path(args.path), args.name)
            print(f"Successfully registered dataset '{args.name}' with identity: {identity}")
        except Exception as e:
            print(f"Failed to register dataset: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.dataset_cmd == "list":
        if not registry.entries:
            print("No datasets registered.")
            return

        rows = []
        for name, entry in registry.entries.items():
            rows.append([name, entry.path, entry.identity])

        print(format_table(["Name", "Path", "Identity"], rows))

    elif args.dataset_cmd == "verify":
        try:
            print(f"Verifying dataset {args.name}...")
            registry.verify(args.name, full=args.full)
            print("Verification successful.")
        except Exception as e:
            print(f"Verification failed: {e}", file=sys.stderr)
            sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="LabRunner CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # run
    parser_run = subparsers.add_parser("run", help="Submit an experiment for execution")
    parser_run.add_argument("experiment_yaml", help="Path to experiment.yaml")
    parser_run.add_argument("--seed", type=int, help="Override or set random seed")
    parser_run.add_argument("--group", type=str, help="Target a specific Pueue slot/group")
    parser_run.add_argument("--detach", "-d", action="store_true", help="Return immediately after submission")
    parser_run.add_argument("--no-verify", action="store_true", help="Skip dataset integrity check")

    # status
    parser_status = subparsers.add_parser("status", help="Show status of runs")
    parser_status.add_argument("run_id", nargs="?", help="Specific run ID to show details for")

    # logs
    parser_logs = subparsers.add_parser("logs", help="Show logs for a run")
    parser_logs.add_argument("run_id", help="Run ID")
    parser_logs.add_argument("--follow", "-f", action="store_true", help="Follow log output")

    # inspect / data
    parser_inspect = subparsers.add_parser("inspect", aliases=["data"], help="Inspect outputs of a run")
    parser_inspect.add_argument("run_id", help="Run ID")
    parser_inspect.add_argument("--path", action="store_true", help="Print output directory path")
    parser_inspect.add_argument("--cat", type=str, help="View content of a specific output file")

    # cancel
    parser_cancel = subparsers.add_parser("cancel", help="Cancel a running task")
    parser_cancel.add_argument("run_id", help="Run ID")

    # dataset
    parser_dataset = subparsers.add_parser("dataset", help="Dataset registry commands")
    dataset_subparsers = parser_dataset.add_subparsers(dest="dataset_cmd", required=True)

    ds_register = dataset_subparsers.add_parser("register", help="Register a dataset")
    ds_register.add_argument("path", help="Path to dataset")
    ds_register.add_argument("--name", required=True, help="Name of the dataset")

    ds_list = dataset_subparsers.add_parser("list", help="List registered datasets")

    ds_verify = dataset_subparsers.add_parser("verify", help="Verify a dataset")
    ds_verify.add_argument("name", help="Name of the dataset")
    ds_verify.add_argument("--full", action="store_true", help="Perform full MD5 verification")

    args = parser.parse_args()

    if args.command == "run":
        run_command(args)
    elif args.command == "status":
        status_command(args)
    elif args.command == "logs":
        logs_command(args)
    elif args.command in ("inspect", "data"):
        inspect_command(args)
    elif args.command == "cancel":
        cancel_command(args)
    elif args.command == "dataset":
        dataset_command(args)

if __name__ == "__main__":
    main()
