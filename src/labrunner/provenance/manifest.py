from typing import Dict, Any, List
from labrunner.spec.experiment import ExperimentSpec
from labrunner.source.snapshot import SourceSnapshot
from labrunner.provenance.hashing import hash_canonical_json

def create_run_provenance(
    run_id: str,
    spec: ExperimentSpec,
    snapshot: SourceSnapshot,
    dataset_manifest_hashes: Dict[str, str], # dataset_name -> manifest_sha256
) -> Dict[str, Any]:
    """
    Creates a versioned run.json provenance manifest.
    """
    datasets_prov = []
    for ds_spec in spec.datasets:
        manifest_hash = dataset_manifest_hashes.get(ds_spec.name)
        if not manifest_hash:
            raise ValueError(f"Missing manifest hash for dataset: {ds_spec.name}")

        datasets_prov.append({
            "name": ds_spec.name,
            "identity": ds_spec.identity,
            "manifest_sha256": manifest_hash
        })

    provenance = {
        "schema_version": 1,
        "run_id": run_id,
        "experiment": {
            "name": spec.name
        },
        "source": {
            "repository_remote": snapshot.repository_remote,
            "base_commit": snapshot.base_commit,
            "snapshot_id": snapshot.snapshot_id
        },
        "command": spec.command,
        "seed": spec.seed,
        "datasets": datasets_prov
    }

    return provenance
