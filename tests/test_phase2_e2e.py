import pytest
import subprocess
import shutil
import json
from pathlib import Path
import os

from labrunner.spec.experiment import parse_experiment_spec
from labrunner.source.snapshot import create_source_snapshot
from labrunner.datasets.manifest import register_dataset, verify_dataset, fast_check_dataset
from labrunner.provenance.manifest import create_run_provenance
from labrunner.source.worktree import materialize_snapshot, remove_worktree

def test_phase2_e2e(tmp_path: Path):
    # 1. Setup mock research repository
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_dir, check=True)

    (repo_dir / "train.py").write_text("print('training')")
    (repo_dir / "utils.py").write_text("def util(): pass")
    subprocess.run(["git", "add", "train.py", "utils.py"], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo_dir, check=True)

    # Modifications
    (repo_dir / "train.py").write_text("print('training v2')") # modified tracked
    (repo_dir / "new_tracked.py").write_text("new")
    subprocess.run(["git", "add", "new_tracked.py"], cwd=repo_dir, check=True) # staged tracked

    (repo_dir / "utils.py").unlink()
    subprocess.run(["git", "rm", "utils.py"], cwd=repo_dir, check=True) # deleted tracked

    (repo_dir / "untracked_source.py").write_text("untracked") # untracked source
    (repo_dir / ".gitignore").write_text("ignored.txt\n")
    (repo_dir / "ignored.txt").write_text("ignore me") # ignored

    # 2. Setup mock dataset
    ds_dir = tmp_path / "mock-data"
    ds_dir.mkdir()
    (ds_dir / "data1.csv").write_text("1,2,3")
    (ds_dir / "data2.csv").write_text("4,5,6")

    # 3. Create YAML Spec
    yaml_content = """
schema_version: 1
name: provenance-e2e

source:
  repository: .

command:
  - python
  - train.py

seed: 42

datasets:
  - name: mock-data
    identity: mock-data-v1

resources:
  accelerator: cpu
  gpus: 0
"""
    spec_path = repo_dir / "experiment.yaml"
    spec_path.write_text(yaml_content)

    # Load YAML
    spec = parse_experiment_spec(spec_path)

    # Check that repo state is unchanged before capture
    status_before = subprocess.run(["git", "status", "--porcelain"], cwd=repo_dir, capture_output=True, text=True).stdout

    # 4. Dataset operations
    ds_manifest, _ = register_dataset(ds_dir)
    ds_manifest_path = tmp_path / "mock-data-v1.md5"
    ds_meta_path = tmp_path / "mock-data-v1-meta.json"
    ds_manifest.to_file(ds_manifest_path)
    ds_manifest.to_local_metadata(ds_meta_path)

    # Resolve dataset identity
    ds_identity_hash = ds_manifest.get_canonical_identity()

    # 5. Capture source snapshot
    snapshot_dir = tmp_path / "snapshot1"
    snapshot = create_source_snapshot(repo_dir, snapshot_dir)

    # Verify original checkout unchanged
    status_after = subprocess.run(["git", "status", "--porcelain"], cwd=repo_dir, capture_output=True, text=True).stdout
    assert status_before == status_after

    # Repeat capture and confirm deterministic source identity
    snapshot_dir2 = tmp_path / "snapshot2"
    snapshot2 = create_source_snapshot(repo_dir, snapshot_dir2)
    assert snapshot.snapshot_id == snapshot2.snapshot_id

    # 6. Create run/submission manifest
    run_id = "R001"
    manifest_hashes = {"mock-data": ds_identity_hash}
    prov = create_run_provenance(run_id, spec, snapshot, manifest_hashes)

    prov_file = tmp_path / "run.json"
    with open(prov_file, 'w') as f:
        json.dump(prov, f)

    assert prov["source"]["snapshot_id"] == snapshot.snapshot_id
    assert prov["datasets"][0]["manifest_sha256"] == ds_identity_hash

    # 7. Materialize detached worktree
    worktree_dir = tmp_path / "run_R001_source"
    materialize_snapshot(snapshot_dir, repo_dir, worktree_dir)

    # Verify reconstructed source
    assert (worktree_dir / "train.py").read_text() == "print('training v2')"
    assert (worktree_dir / "new_tracked.py").read_text() == "new"
    assert not (worktree_dir / "utils.py").exists()
    assert (worktree_dir / "untracked_source.py").read_text() == "untracked"
    assert not (worktree_dir / "ignored.txt").exists()

    # 8. Modify source and confirm source identity changes
    (repo_dir / "new_file2.py").write_text("new2")
    snapshot_dir3 = tmp_path / "snapshot3"
    snapshot3 = create_source_snapshot(repo_dir, snapshot_dir3)
    assert snapshot3.snapshot_id != snapshot.snapshot_id

    # 9. Modify dataset content and confirm verification detects the mismatch
    # modify file to have same size to bypass fast check? Wait, verify_dataset always checks md5
    (ds_dir / "data1.csv").write_text("9,9,9")

    import labrunner.datasets.errors as ds_err
    with pytest.raises(ds_err.DatasetVerificationError, match="MD5 mismatch"):
        verify_dataset(ds_dir, ds_manifest_path)

    # 10. Safely remove worktree
    remove_worktree(repo_dir, worktree_dir, allowed_root=tmp_path)
    assert not worktree_dir.exists()
