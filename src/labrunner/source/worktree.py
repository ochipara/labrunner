import tarfile
import shutil
import os
from pathlib import Path

from labrunner.source.git import GitHelper
from labrunner.source.snapshot import SourceSnapshot
from labrunner.source.errors import WorktreeCreationError, UnsafeCleanupError

def materialize_snapshot(snapshot_dir: Path, repository: Path, destination: Path) -> None:
    """
    Materializes a source snapshot into a detached worktree.
    Ensures the base commit exists, creates the worktree, applies patch,
    and restores untracked files.
    """
    import json

    metadata_path = snapshot_dir / "metadata.json"
    if not metadata_path.exists():
        raise WorktreeCreationError(f"Snapshot metadata not found in {snapshot_dir}")

    with open(metadata_path, 'r') as f:
        metadata = json.load(f)

    base_commit = metadata["base_commit"]

    git = GitHelper(repository)

    # 1. Ensure the base commit exists
    result = git.run_git(["cat-file", "-t", base_commit], check=False)
    if result.returncode != 0 or result.stdout.strip() != "commit":
        raise WorktreeCreationError(f"Base commit {base_commit} not found in {repository}.")

    # 2. Create a detached worktree
    destination = destination.resolve()
    if destination.exists():
        raise WorktreeCreationError(f"Destination {destination} already exists.")

    git.run_git(["worktree", "add", "--detach", str(destination), base_commit])

    try:
        # 3. Apply captured tracked changes (patch)
        patch_path = snapshot_dir / "tracked.patch"
        if patch_path.exists() and patch_path.stat().st_size > 0:
            # We apply the patch in the new worktree
            # Use 'git apply' from the worktree
            # --whitespace=nowarn avoids rejecting due to trailing whitespaces that might have been in the repo
            git_wt = GitHelper(destination)
            res = git_wt.run_git(["apply", "--whitespace=nowarn", str(patch_path.resolve())], check=False)
            if res.returncode != 0:
                raise WorktreeCreationError(f"Failed to apply patch: {res.stderr}\n{res.stdout}")

        # 4. Restore captured untracked files
        untracked_path = snapshot_dir / "untracked.tar"
        if untracked_path.exists() and untracked_path.stat().st_size > 0:
            with tarfile.open(untracked_path, "r") as tar:
                # We need to extract safely, but tarfile might complain in newer pythons without filter
                tar.extractall(path=destination, filter='data' if hasattr(tarfile, 'data_filter') else None)

        # 5. Verify reconstructed source state
        from labrunner.source.snapshot import create_source_snapshot

        # We verify by capturing the reconstructed tree's identity and comparing it to the snapshot identity
        # However, create_source_snapshot relies on a git checkout, and detached worktrees ARE checkouts.
        # So we can just create a snapshot from the worktree!
        # But wait - we just extracted untracked files into the worktree. In the worktree, they will be untracked!
        # And any modified tracked files (which we patched) will show up as modified relative to the base commit!
        # This matches the definition of capture exactly.
        # So we can capture a temporary snapshot of the worktree and its ID MUST match.
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            temp_snap = create_source_snapshot(destination, Path(td))
            if temp_snap.snapshot_id != metadata["snapshot_id"]:
                from labrunner.source.errors import SnapshotVerificationError
                raise SnapshotVerificationError(f"Reconstruction failed: expected {metadata['snapshot_id']}, got {temp_snap.snapshot_id}")

    except Exception as e:
        remove_worktree(repository, destination, allowed_root=destination.parent)
        raise e

def remove_worktree(repository: Path, worktree: Path, allowed_root: Path) -> None:
    """
    Safely removes a detached worktree.
    Ensures that the worktree is inside the allowed_root and doesn't violate safety constraints.
    """
    allowed_root = allowed_root.resolve()
    worktree = worktree.resolve()

    # 2. reject the root itself
    if worktree == allowed_root:
        raise UnsafeCleanupError(f"Cannot delete the allowed_root itself: {worktree}")

    # 1. require the target to be a strict descendant
    if not str(worktree).startswith(str(allowed_root) + os.sep):
        raise UnsafeCleanupError(f"Worktree {worktree} is not a strict descendant of allowed_root {allowed_root}")

    # 3. reject filesystem root, home directory, etc. (implicitly covered by strict descendant + allowed root checks,
    # but we can add explicit safeguards)
    if str(worktree) == "/" or str(worktree) == str(Path.home()):
        raise UnsafeCleanupError(f"Cannot delete root or home directory: {worktree}")

    # Remove via git worktree remove if possible
    git = GitHelper(repository)
    res = git.run_git(["worktree", "list"], check=False)

    is_registered = False
    if res.returncode == 0:
        for line in res.stdout.splitlines():
            if line.startswith(str(worktree)):
                is_registered = True
                break

    if is_registered:
        res = git.run_git(["worktree", "remove", "--force", str(worktree)], check=False)
        if res.returncode != 0:
            raise UnsafeCleanupError(f"Failed to remove git worktree: {res.stderr}\n{res.stdout}")
    else:
        # Fallback filesystem cleanup
        if worktree.exists():
            shutil.rmtree(worktree)
