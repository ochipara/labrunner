import pytest
import subprocess
from pathlib import Path
import os

from labrunner.source.snapshot import create_source_snapshot
from labrunner.source.worktree import materialize_snapshot, remove_worktree
from labrunner.source.errors import WorktreeCreationError, UnsafeCleanupError

def setup_repo(tmp_path: Path) -> Path:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_dir, check=True)

    (repo_dir / "base.txt").write_text("base")
    subprocess.run(["git", "add", "base.txt"], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo_dir, check=True)

    return repo_dir

def test_materialize_and_cleanup(tmp_path):
    repo_dir = setup_repo(tmp_path)

    # modify tracked
    (repo_dir / "base.txt").write_text("mod")
    # add untracked
    (repo_dir / "untracked.txt").write_text("untrack")
    # add ignored
    (repo_dir / ".gitignore").write_text("ignored.txt\n")
    (repo_dir / "ignored.txt").write_text("ignore")

    snapshot_dir = tmp_path / "snapshot"
    create_source_snapshot(repo_dir, snapshot_dir)

    worktree_dir = tmp_path / "worktree"
    materialize_snapshot(snapshot_dir, repo_dir, worktree_dir)

    # Verify reconstructed state
    assert worktree_dir.exists()
    assert (worktree_dir / "base.txt").read_text() == "mod"
    assert (worktree_dir / "untracked.txt").read_text() == "untrack"
    assert not (worktree_dir / "ignored.txt").exists()

    # Ensure it's detached and on correct commit conceptually
    # (Checking the branch name which is HEAD in a detached worktree)
    res = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=worktree_dir, capture_output=True, text=True, check=True)
    assert res.stdout.strip() == "HEAD"

    # Cleanup
    remove_worktree(repo_dir, worktree_dir, allowed_root=tmp_path)
    assert not worktree_dir.exists()

def test_simultaneous_worktrees(tmp_path):
    repo_dir = setup_repo(tmp_path)
    snapshot_dir = tmp_path / "snapshot"
    create_source_snapshot(repo_dir, snapshot_dir)

    wt1 = tmp_path / "wt1"
    wt2 = tmp_path / "wt2"

    materialize_snapshot(snapshot_dir, repo_dir, wt1)
    materialize_snapshot(snapshot_dir, repo_dir, wt2)

    assert wt1.exists()
    assert wt2.exists()

    remove_worktree(repo_dir, wt1, allowed_root=tmp_path)
    assert not wt1.exists()
    assert wt2.exists()  # Ensure cleanup of one doesn't affect the other

def test_malicious_cleanup_targets(tmp_path):
    repo_dir = setup_repo(tmp_path)
    allowed = tmp_path / "allowed"
    allowed.mkdir()

    outside = tmp_path / "outside"
    outside.mkdir()

    # 1. target is allowed_root itself
    with pytest.raises(UnsafeCleanupError, match="itself"):
        remove_worktree(repo_dir, allowed, allowed_root=allowed)

    # 2. target is outside allowed_root
    with pytest.raises(UnsafeCleanupError, match="strict descendant"):
        remove_worktree(repo_dir, outside, allowed_root=allowed)

    # 3. traversal escapes
    target_escape = allowed / ".." / "outside"
    with pytest.raises(UnsafeCleanupError, match="strict descendant"):
        remove_worktree(repo_dir, target_escape, allowed_root=allowed)

    # 4. root
    with pytest.raises(UnsafeCleanupError, match="strict descendant"):
        remove_worktree(repo_dir, Path("/"), allowed_root=allowed)

    # 5. symlink escape
    symlink_target = allowed / "symlink"
    os.symlink(str(outside), str(symlink_target))

    with pytest.raises(UnsafeCleanupError, match="strict descendant"):
        remove_worktree(repo_dir, symlink_target / "some_dir", allowed_root=allowed)

def test_missing_base_commit(tmp_path):
    repo_dir = setup_repo(tmp_path)
    snapshot_dir = tmp_path / "snapshot"
    create_source_snapshot(repo_dir, snapshot_dir)

    # Modify metadata to have non-existent commit
    import json
    metadata_path = snapshot_dir / "metadata.json"
    with open(metadata_path, 'r') as f:
        meta = json.load(f)
    meta["base_commit"] = "0" * 40
    with open(metadata_path, 'w') as f:
        json.dump(meta, f)

    worktree_dir = tmp_path / "worktree"
    with pytest.raises(WorktreeCreationError, match="Base commit"):
        materialize_snapshot(snapshot_dir, repo_dir, worktree_dir)
