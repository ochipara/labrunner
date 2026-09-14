import pytest
from pathlib import Path
import os
import subprocess
import json
import time

from labrunner.runner.executor import ExperimentExecutor, ExecutorError
from labrunner.registry.dataset_registry import DatasetRegistry
from labrunner.pueue import TaskState


def test_executor_e2e(tmp_path: Path):
    # Setup test workspace
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    os.chdir(workspace)

    # 1. Setup git repo
    subprocess.run(["git", "init"], check=True)
    subprocess.run(["git", "config", "user.name", "Test"], check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], check=True)

    # Train script
    (workspace / "train.py").write_text("""
import os
import json

seed = os.environ.get("LABRUNNER_SEED", "none")
ds_path = os.environ.get("LABRUNNER_DATASET_MOCKDATA", "none")
output_dir = os.environ.get("LABRUNNER_OUTPUT_DIR", ".")

# Read dataset
with open(os.path.join(ds_path, "data.txt"), "r") as f:
    data = f.read()

# Write output
out_file = os.path.join(output_dir, "metrics.json")
with open(out_file, "w") as f:
    json.dump({"accuracy": 0.99, "seed": seed, "data": data}, f)

print(f"Training completed. Metrics written to {out_file}")
""")
    subprocess.run(["git", "add", "train.py"], check=True)
    subprocess.run(["git", "commit", "-m", "init"], check=True)

    # 2. Setup dataset
    data_dir = tmp_path / "mock_dataset"
    data_dir.mkdir()
    (data_dir / "data.txt").write_text("dataset_v1")

    registry = DatasetRegistry(registry_file=tmp_path / "datasets.yaml")
    ds_identity = registry.register(data_dir, "mockdata")

    # 3. Create experiment spec
    spec_content = f"""
schema_version: 1
name: e2e-test
source:
  repository: .
command:
  - python
  - train.py
  - --data
  - ${{{{ datasets.mockdata.path }}}}
seed: 1234
resources:
  accelerator: cpu
  gpus: 0
datasets:
  - name: mockdata
    identity: {ds_identity}
"""
    spec_file = workspace / "experiment.yaml"
    spec_file.write_text(spec_content)

    # Setup labrunner base dir in environment so components use it
    os.environ["LABRUNNER_DATA_ROOT"] = str(tmp_path / "labrunner")

    # Also explicitly provide the same registry file to executor's constructor or setup properly
    executor = ExperimentExecutor(base_dir=tmp_path / "labrunner")
    # Need to override registry to use the one we just made
    executor.registry = DatasetRegistry(registry_file=tmp_path / "datasets.yaml")

    # Ensure Pueued is running - assumed true from other tests environment

    # 4. Submit
    run_id = executor.submit(spec_file)
    assert run_id is not None

    # 5. Monitor status
    status = executor.get_status(run_id)
    assert status["status"] in (TaskState.QUEUED.value, TaskState.RUNNING.value, TaskState.SUCCEEDED.value)

    # Wait for completion
    timeout = 10
    start = time.time()
    while time.time() - start < timeout:
        status = executor.get_status(run_id)
        if status["status"] in (TaskState.SUCCEEDED.value, TaskState.FAILED.value, TaskState.CANCELLED.value):
            break
        time.sleep(0.5)

    assert status["status"] == TaskState.SUCCEEDED.value
    assert status["exit_code"] == 0

    # 6. Check outputs
    run_dir = executor.runs_dir / run_id
    metrics_file = run_dir / "outputs" / "metrics.json"

    assert metrics_file.exists()
    with open(metrics_file, "r") as f:
        metrics = json.load(f)

    assert metrics["accuracy"] == 0.99
    assert metrics["seed"] == "1234"
    assert metrics["data"] == "dataset_v1"

    # 7. Check run metadata
    run_json = run_dir / "run.json"
    assert run_json.exists()
    with open(run_json, "r") as f:
        prov = json.load(f)

    assert prov["experiment"]["name"] == "e2e-test"
    assert prov["seed"] == 1234
    assert prov["datasets"][0]["name"] == "mockdata"
