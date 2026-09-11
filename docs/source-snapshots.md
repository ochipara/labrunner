# Source Snapshots

LabRunner uses Source Snapshots to deterministically capture, version, and materialize the exact source code required to reproduce an experiment.

## Principles

1. **Safety First:** Capturing a source snapshot will never checkout branches, modify the index, or rewrite files in the researcher's checkout.
2. **Deterministic Identity:** Capturing identical source code twice will always yield the exact same snapshot ID. Snapshot identity is independent of non-semantic archive metadata (e.g., file modification times or ownership) and depends only on canonical source content (paths, executable bits, and symlink targets).
3. **Ignored is Excluded:** Files ignored by Git are not part of a LabRunner source snapshot by default.

## Snapshot Components

A snapshot is represented as a directory containing:

- `metadata.json`: Contains the `schema_version`, remote identity, base commit, `tracked_patch_sha256`, `untracked_archive_sha256`, and the final `snapshot_id`.
- `tracked.patch`: Contains the unified diff of all staged and unstaged modifications against the base commit.
- `untracked.tar`: A deterministic archive of all non-ignored untracked files and symlinks.

## Reconstruction

Snapshots are reconstructed by creating a detached Git worktree at the `base_commit` and applying `tracked.patch` along with `untracked.tar`. This mechanism ensures experiments are run in full isolation safely, avoiding per-run branch pollution.

### Symlinks Policy

Source symlinks are preserved exactly as symlinks and are **never** followed. Dangers such as repository-escaping symlinks will still be captured as symlinks (since this represents the original state) but they are never followed or resolved during capture, reconstruction, or comparison.
