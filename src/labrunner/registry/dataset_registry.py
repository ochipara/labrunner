import os
import yaml
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from labrunner.datasets.manifest import (
    register_dataset,
    fast_check_dataset,
    verify_dataset,
)


@dataclass
class DatasetRegistryEntry:
    path: str
    identity: str


class DatasetRegistry:
    def __init__(self, registry_file: Optional[Path] = None):
        if registry_file is None:
            data_root = os.environ.get("LABRUNNER_DATA_ROOT", str(Path.home() / ".labrunner"))
            self.registry_file = Path(data_root) / "datasets.yaml"
        else:
            self.registry_file = registry_file

        self.entries: Dict[str, DatasetRegistryEntry] = {}
        self._load()

    def _load(self) -> None:
        if not self.registry_file.exists():
            self.entries = {}
            return

        with open(self.registry_file, 'r') as f:
            data = yaml.safe_load(f)
            if not isinstance(data, dict):
                return
            for name, entry_data in data.items():
                self.entries[name] = DatasetRegistryEntry(
                    path=entry_data["path"],
                    identity=entry_data["identity"]
                )

    def _save(self) -> None:
        self.registry_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            name: {
                "path": entry.path,
                "identity": entry.identity
            }
            for name, entry in self.entries.items()
        }
        with open(self.registry_file, 'w') as f:
            yaml.safe_dump(data, f, default_flow_style=False)

    def register(self, dataset_path: Path, name: str) -> str:
        """
        Registers a dataset at the given path with the given name.
        Computes manifest, identity, and stores them in the dataset folder.
        Updates the registry and saves it.
        Returns the dataset identity.
        """
        dataset_path = dataset_path.resolve()

        manifest, skipped = register_dataset(dataset_path)
        identity = manifest.get_canonical_identity()

        # Save manifest files alongside the dataset
        manifest_file = dataset_path / ".labrunner_manifest.txt"
        metadata_file = dataset_path / ".labrunner_metadata.json"

        manifest.to_file(manifest_file)
        manifest.to_local_metadata(metadata_file)

        # Update registry
        self.entries[name] = DatasetRegistryEntry(
            path=str(dataset_path),
            identity=identity
        )
        self._save()

        return identity

    def get_dataset(self, name: str) -> Optional[DatasetRegistryEntry]:
        """
        Retrieves the dataset entry by name, returning None if not found.
        """
        return self.entries.get(name)

    def verify(self, name: str, full: bool = False) -> None:
        """
        Verifies the dataset either with fast check (metadata) or full check (md5).
        """
        entry = self.get_dataset(name)
        if not entry:
            raise KeyError(f"Dataset {name} not found in registry.")

        dataset_path = Path(entry.path)
        if full:
            manifest_file = dataset_path / ".labrunner_manifest.txt"
            verify_dataset(dataset_path, manifest_file)
        else:
            metadata_file = dataset_path / ".labrunner_metadata.json"
            fast_check_dataset(dataset_path, metadata_file)
