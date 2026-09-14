import pytest
from pathlib import Path
from labrunner.registry.dataset_registry import DatasetRegistry

def test_dataset_registry(tmp_path: Path):
    # Setup dataset
    ds_dir = tmp_path / "my_dataset"
    ds_dir.mkdir()
    (ds_dir / "data.txt").write_text("hello world")

    registry_file = tmp_path / "datasets.yaml"
    registry = DatasetRegistry(registry_file=registry_file)

    # Register dataset
    identity = registry.register(ds_dir, "my_dataset")

    # Verify it exists in registry
    assert registry_file.exists()

    entry = registry.get_dataset("my_dataset")
    assert entry is not None
    assert entry.path == str(ds_dir.resolve())
    assert entry.identity == identity

    # Verify dataset files created
    assert (ds_dir / ".labrunner_manifest.txt").exists()
    assert (ds_dir / ".labrunner_metadata.json").exists()

    # Verify using registry
    registry.verify("my_dataset", full=False)
    registry.verify("my_dataset", full=True)

    # Load from file again
    registry2 = DatasetRegistry(registry_file=registry_file)
    entry2 = registry2.get_dataset("my_dataset")
    assert entry2 is not None
    assert entry2.identity == identity
