import pytest
from labrunner.provenance.hashing import get_canonical_json, hash_canonical_json
from labrunner.provenance.manifest import create_run_provenance
from labrunner.spec.experiment import ExperimentSpec, SourceSpec, ResourcesSpec, DatasetSpec
from labrunner.source.snapshot import SourceSnapshot

def test_canonical_json():
    obj1 = {"b": 2, "a": 1, "c": [3, 2, 1]}
    obj2 = {"a": 1, "b": 2, "c": [3, 2, 1]}

    assert get_canonical_json(obj1) == get_canonical_json(obj2)
    assert get_canonical_json(obj1) == '{"a":1,"b":2,"c":[3,2,1]}'

    # Check stable hash
    h1 = hash_canonical_json(obj1)
    h2 = hash_canonical_json(obj2)
    assert h1 == h2
    assert h1.startswith("sha256:")

def test_create_run_provenance():
    spec = ExperimentSpec(
        schema_version=1,
        name="resnet-baseline",
        source=SourceSpec(repository="."),
        command=["python", "train.py", "--epochs", "100"],
        seed=42,
        resources=ResourcesSpec(accelerator="cuda", gpus=1),
        datasets=[DatasetSpec(name="cifar10", identity="cifar10-v1")]
    )

    snapshot = SourceSnapshot(
        schema_version=1,
        repository_remote="git@example/research.git",
        base_commit="FULL_COMMIT_ID",
        tracked_patch_sha256="sha256:patch",
        untracked_archive_sha256="sha256:tar",
        snapshot_id="sha256:snap"
    )

    manifest_hashes = {
        "cifar10": "sha256:dataset"
    }

    prov = create_run_provenance("R001", spec, snapshot, manifest_hashes)

    assert prov["schema_version"] == 1
    assert prov["run_id"] == "R001"
    assert prov["experiment"]["name"] == "resnet-baseline"
    assert prov["source"]["repository_remote"] == "git@example/research.git"
    assert prov["source"]["base_commit"] == "FULL_COMMIT_ID"
    assert prov["source"]["snapshot_id"] == "sha256:snap"
    assert prov["command"] == ["python", "train.py", "--epochs", "100"]
    assert prov["seed"] == 42
    assert len(prov["datasets"]) == 1
    assert prov["datasets"][0]["name"] == "cifar10"
    assert prov["datasets"][0]["identity"] == "cifar10-v1"
    assert prov["datasets"][0]["manifest_sha256"] == "sha256:dataset"

def test_missing_dataset_hash():
    spec = ExperimentSpec(
        schema_version=1,
        name="resnet-baseline",
        source=SourceSpec(repository="."),
        command=["python", "train.py"],
        seed=42,
        resources=ResourcesSpec(accelerator="cuda", gpus=1),
        datasets=[DatasetSpec(name="cifar10", identity="cifar10-v1")]
    )

    snapshot = SourceSnapshot(
        schema_version=1,
        repository_remote=None,
        base_commit="ID",
        tracked_patch_sha256="1",
        untracked_archive_sha256="2",
        snapshot_id="3"
    )

    with pytest.raises(ValueError, match="Missing manifest hash for dataset: cifar10"):
        create_run_provenance("R001", spec, snapshot, {})
