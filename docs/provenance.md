# Run Provenance Manifest

LabRunner encapsulates the deterministic definition of a run inside a versioned JSON provenance manifest (`run.json`).

## Structure

The submission provenance manifest records exactly what was requested for a specific execution:
- `schema_version`: Currently set to 1.
- `run_id`: The identifier for this run.
- `experiment`: Name and properties of the parsed experiment.
- `source`: The repository remote, base commit, and the deterministic `snapshot_id` of the captured source code.
- `command`: The specific command strings executed.
- `seed`: An explicitly defined 32-bit unsigned integer. LabRunner will never generate a missing seed itself.
- `datasets`: Details of datasets and their deterministic MD5 canonical SHA-256 identities.

## Serialization and Hashing

Provenance manifests are formatted using a canonical JSON representation:
- UTF-8 encoding.
- Sorted object keys.
- Stable separators (`:`, `,`).
- Stripped of irrelevant metadata and timestamps.

This ensures that the manifest object itself can be securely identified via a SHA-256 hash if required.
