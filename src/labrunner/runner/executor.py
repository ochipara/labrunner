import os
import json
import time
from pathlib import Path
from typing import Optional, Dict

from labrunner.spec.experiment import ExperimentSpec
from labrunner.source.snapshot import create_source_snapshot
from labrunner.source.worktree import materialize_snapshot
from labrunner.registry.dataset_registry import DatasetRegistry
from labrunner.provenance.manifest import create_run_provenance
from labrunner.pueue import PueueAdapter, TaskState


class ExecutorError(Exception):
    pass


class ExperimentExecutor:
    def __init__(self, base_dir: Optional[Path] = None):
        if base_dir is None:
            self.base_dir = Path(os.environ.get("LABRUNNER_DATA_ROOT", str(Path.home() / ".labrunner")))
        else:
            self.base_dir = base_dir

        self.runs_dir = self.base_dir / "runs"
        self.snapshots_dir = self.base_dir / "snapshots"
        self.registry = DatasetRegistry(registry_file=self.base_dir / "datasets.yaml")
        self.pueue = PueueAdapter()

    def _generate_run_id(self) -> str:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        import uuid
        short_uuid = uuid.uuid4().hex[:4]
        return f"run_{timestamp}_{short_uuid}"

    def submit(
        self,
        experiment_file: Path,
        seed_override: Optional[int] = None,
        group: Optional[str] = None,
        no_verify: bool = False
    ) -> str:
        from labrunner.spec.experiment import parse_experiment_spec
        spec = parse_experiment_spec(experiment_file)

        if seed_override is not None:
            spec.seed = seed_override

        run_id = self._generate_run_id()
        run_dir = self.runs_dir / run_id
        outputs_dir = run_dir / "outputs"
        worktree_dir = run_dir / "worktree"

        run_dir.mkdir(parents=True, exist_ok=True)
        outputs_dir.mkdir(parents=True, exist_ok=True)

        # 1. Capture snapshot
        # For phase 2, we assume the command is run from the root of the repo being snapshotted.
        repo_path = Path.cwd()

        # We need a unique snapshot dir per run to avoid conflicts, or use snapshot ID.
        # Let's generate it to a temp dir first, then move it to snapshot_id dir
        import tempfile
        import shutil
        with tempfile.TemporaryDirectory() as td:
            temp_snapshot_dir = Path(td) / "snap"
            snapshot = create_source_snapshot(repo_path, temp_snapshot_dir)
            snapshot_dir = self.snapshots_dir / snapshot.snapshot_id.replace("sha256:", "")
            if not snapshot_dir.exists():
                self.snapshots_dir.mkdir(parents=True, exist_ok=True)
                shutil.copytree(temp_snapshot_dir, snapshot_dir)

        # 2. Dataset resolution and verification
        dataset_manifest_hashes = {}
        env_vars = {
            "LABRUNNER_RUN_ID": run_id,
            "LABRUNNER_SEED": str(spec.seed),
            "LABRUNNER_OUTPUT_DIR": str(outputs_dir),
            "LABRUNNER_RUN_DIR": str(run_dir)
        }
        dataset_paths_json = {}
        dataset_paths_by_name = {}

        for ds_spec in spec.datasets:
            entry = self.registry.get_dataset(ds_spec.name)
            if not entry:
                raise ExecutorError(f"Dataset '{ds_spec.name}' not found in registry.")

            if entry.identity != ds_spec.identity:
                raise ExecutorError(f"Dataset identity mismatch for '{ds_spec.name}'. Expected {ds_spec.identity}, got {entry.identity}.")

            if not no_verify:
                try:
                    self.registry.verify(ds_spec.name, full=False)
                except Exception as e:
                    raise ExecutorError(f"Failed to verify dataset '{ds_spec.name}': {e}")

            dataset_paths_json[ds_spec.name] = entry.path
            dataset_paths_by_name[ds_spec.name] = entry.path
            env_vars[f"LABRUNNER_DATASET_{ds_spec.name.upper()}"] = entry.path

            # Read the manifest to get its hash for provenance
            manifest_path = Path(entry.path) / ".labrunner_manifest.txt"
            if manifest_path.exists():
                from labrunner.source.snapshot import file_sha256
                dataset_manifest_hashes[ds_spec.name] = f"sha256:{file_sha256(manifest_path)}"
            else:
                dataset_manifest_hashes[ds_spec.name] = "unknown"

        env_vars["LABRUNNER_DATASETS_JSON"] = json.dumps(dataset_paths_json)

        # 3. Provenance
        provenance = create_run_provenance(run_id, spec, snapshot, dataset_manifest_hashes)
        with open(run_dir / "run.json", "w") as f:
            json.dump(provenance, f, indent=2, sort_keys=True)

        # 4. Materialize worktree
        materialize_snapshot(snapshot_dir, repo_path, worktree_dir)

        # 5. Resolve command placeholders
        resolved_command = []
        for arg in spec.command:
            for name, path in dataset_paths_by_name.items():
                arg = arg.replace(f"${{{{ datasets.{name}.path }}}}", path)
            resolved_command.append(arg)

        # 6. Submit to Pueue
        try:
            task_id = self.pueue.submit(
                run_id=run_id,
                argv=resolved_command,
                cwd=worktree_dir,
                env=env_vars,
                group=group
            )
        except Exception as e:
            raise ExecutorError(f"Failed to submit task to Pueue: {e}")

        # Store metadata
        status_data = {
            "pueue_task_id": task_id,
            "run_id": run_id,
            "experiment_file": str(experiment_file.resolve()),
            "status": TaskState.QUEUED.value
        }
        with open(run_dir / "status.json", "w") as f:
            json.dump(status_data, f, indent=2)

        return run_id

    def get_status(self, run_id: str) -> Dict:
        run_dir = self.runs_dir / run_id
        if not run_dir.exists():
            raise ExecutorError(f"Run directory not found: {run_dir}")

        status_file = run_dir / "status.json"
        if not status_file.exists():
            raise ExecutorError(f"Status file not found for run: {run_id}")

        with open(status_file, "r") as f:
            status_data = json.load(f)

        try:
            task_status = self.pueue.status(status_data["pueue_task_id"])
            status_data["status"] = task_status.state.value
            status_data["exit_code"] = task_status.exit_code
            status_data["start_time"] = task_status.start_time
            status_data["end_time"] = task_status.end_time

            # Save updated status
            with open(status_file, "w") as f:
                json.dump(status_data, f, indent=2)

            return status_data
        except Exception as e:
            # Pueue might be down or task might be purged. Return last known.
            status_data["error"] = str(e)
            return status_data
