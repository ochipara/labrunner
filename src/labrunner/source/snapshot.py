import hashlib
import json
from pathlib import Path
from typing import List, Dict, Tuple
from dataclasses import dataclass
from labrunner.source.git import GitHelper
from labrunner.source.archive import create_deterministic_tar
from labrunner.source.errors import SnapshotCreationError

@dataclass
class SourceSnapshot:
    schema_version: int
    repository_remote: str | None
    base_commit: str
    tracked_patch_sha256: str
    untracked_archive_sha256: str
    snapshot_id: str

def file_sha256(path: Path) -> str:
    """Computes SHA-256 for a file without loading it fully into memory."""
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

def create_source_snapshot(repository: Path, destination: Path) -> SourceSnapshot:
    """
    Captures the current state of a Git repository without mutating it.
    Generates a deterministic snapshot ID based on canonical source tree.
    """
    git = GitHelper(repository)
    git.check_version()

    repo_root = git.get_repo_root()
    base_commit = git.get_head_commit()
    remote = git.get_canonical_remote()

    destination.mkdir(parents=True, exist_ok=True)
    patch_path = destination / "tracked.patch"
    untracked_path = destination / "untracked.tar"

    # 1. Capture tracked changes (patch)
    # diff HEAD to capture staged and unstaged changes together
    diff_result = git.run_git(["diff", "HEAD", "--binary"])
    patch_path.write_bytes(diff_result.stdout.encode('utf-8'))

    tracked_patch_sha256 = file_sha256(patch_path)

    # 2. Capture untracked non-ignored files
    # git ls-files -o --exclude-standard gives us exactly untracked, non-ignored files
    untracked_result = git.run_git(["ls-files", "-o", "--exclude-standard", "-z"])
    untracked_paths_str = untracked_result.stdout.strip("\0").split("\0") if untracked_result.stdout else []

    untracked_paths = []
    for p in untracked_paths_str:
        if p:
            abs_p = repo_root / p
            if abs_p.is_file() or abs_p.is_symlink():
                untracked_paths.append(abs_p)

    create_deterministic_tar(untracked_paths, repo_root, untracked_path)

    # If there are no untracked files, we still have an empty tar archive which has a canonical hash
    untracked_archive_sha256 = file_sha256(untracked_path)

    # 3. Calculate canonical source tree identity
    # We must construct a canonical view of the effective source tree without writing objects
    # to the git database (e.g., `git add` writes blobs).
    import os

    # 1. Get HEAD tree elements
    head_ls = git.run_git(["ls-tree", "-r", "-z", "HEAD"])
    head_entries = head_ls.stdout.strip('\0').split('\0') if head_ls.stdout else []

    # path -> (mode, type)
    tracked_state = {}
    for entry in head_entries:
        if not entry:
            continue
        meta, path = entry.split('\t', 1)
        mode, type_, _ = meta.split(' ')
        tracked_state[path] = {"mode": mode, "status": "unmodified"}

    # 2. Get tracked modifications (staged and unstaged) and deletions
    # diff-index --name-status HEAD gives us modified, deleted, added tracked files
    diff_status = git.run_git(["diff", "--name-status", "-z", "HEAD"])
    diff_parts = diff_status.stdout.strip('\0').split('\0') if diff_status.stdout else []

    i = 0
    while i < len(diff_parts):
        status = diff_parts[i]

        if status.startswith("R") or status.startswith("C"):
            # Rename or copy has status, old path, new path
            old_path = diff_parts[i+1]
            new_path = diff_parts[i+2]
            if status.startswith("R"):
                tracked_state[old_path] = {"status": "deleted"}
            tracked_state[new_path] = {"status": "modified"}
            i += 3
        else:
            # Added, Deleted, Modified
            path = diff_parts[i+1]
            if status == "D":
                tracked_state[path] = {"status": "deleted"}
            else:
                tracked_state[path] = {"status": "modified"}
            i += 2

    # Combine everything to compute canonical entries
    canonical_entries = []

    for path, info in tracked_state.items():
        if info["status"] == "deleted":
            continue

        abs_path = repo_root / path

        if not abs_path.exists():
            continue

        if abs_path.is_symlink():
            mode = "120000"
            entry_type = "symlink"
            try:
                target = os.readlink(abs_path)
            except OSError:
                target = ""
            val = target
        else:
            # Regular file, need to determine mode
            # Check executable bit
            if os.access(abs_path, os.X_OK):
                mode = "100755"
            else:
                mode = "100644"

            entry_type = "regular"
            val = f"sha256:{file_sha256(abs_path)}"

        canonical_entries.append(f"{path}\n{entry_type}\n{mode}\n{val}")

    # Also add untracked non-ignored files
    for path in untracked_paths_str:
        if not path:
            continue
        abs_path = repo_root / path
        if not abs_path.exists():
            continue

        if abs_path.is_symlink():
            mode = "120000"
            entry_type = "symlink"
            try:
                target = os.readlink(abs_path)
            except OSError:
                target = ""
            val = target
        else:
            if os.access(abs_path, os.X_OK):
                mode = "100755"
            else:
                mode = "100644"

            entry_type = "regular"
            val = f"sha256:{file_sha256(abs_path)}"

        canonical_entries.append(f"{path}\n{entry_type}\n{mode}\n{val}")

    canonical_entries.sort()
    canonical_effective_source_tree = "\n---\n".join(canonical_entries)

    # 4. Compute snapshot_id
    h = hashlib.sha256()
    h.update(b"1\n") # schema_version
    h.update(f"{remote or ''}\n".encode('utf-8')) # repository_identity
    h.update(f"{base_commit}\n".encode('utf-8')) # base_commit
    h.update(canonical_effective_source_tree.encode('utf-8'))

    snapshot_id = f"sha256:{h.hexdigest()}"

    metadata = {
        "schema_version": 1,
        "repository_remote": remote,
        "base_commit": base_commit,
        "tracked_patch_sha256": tracked_patch_sha256,
        "untracked_archive_sha256": untracked_archive_sha256,
        "snapshot_id": snapshot_id
    }

    with open(destination / "metadata.json", "w") as f:
        json.dump(metadata, f, indent=2, sort_keys=True)

    return SourceSnapshot(**metadata)
