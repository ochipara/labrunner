import pytest
import subprocess
import tarfile
from pathlib import Path
import os
import json

from labrunner.source.snapshot import create_source_snapshot, SourceSnapshot

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

def test_snapshot_clean_repo(tmp_path):
    repo_dir = setup_repo(tmp_path)
    dest_dir = tmp_path / "snapshot"

    snapshot = create_source_snapshot(repo_dir, dest_dir)

    assert isinstance(snapshot, SourceSnapshot)
    assert snapshot.schema_version == 1
    assert snapshot.base_commit is not None
    assert snapshot.snapshot_id.startswith("sha256:")

    assert (dest_dir / "metadata.json").exists()
    assert (dest_dir / "tracked.patch").exists()
    assert (dest_dir / "untracked.tar").exists()

    # Patch should be empty for a clean repo
    assert (dest_dir / "tracked.patch").stat().st_size == 0

def test_snapshot_unstaged_modifications(tmp_path):
    repo_dir = setup_repo(tmp_path)
    (repo_dir / "base.txt").write_text("mod")

    dest_dir = tmp_path / "snapshot"
    snapshot = create_source_snapshot(repo_dir, dest_dir)

    patch_content = (dest_dir / "tracked.patch").read_text()
    assert "diff --git a/base.txt b/base.txt" in patch_content
    assert "+mod" in patch_content

def test_snapshot_staged_modifications(tmp_path):
    repo_dir = setup_repo(tmp_path)
    (repo_dir / "base.txt").write_text("mod")
    subprocess.run(["git", "add", "base.txt"], cwd=repo_dir, check=True)

    dest_dir = tmp_path / "snapshot"
    snapshot = create_source_snapshot(repo_dir, dest_dir)

    patch_content = (dest_dir / "tracked.patch").read_text()
    assert "diff --git a/base.txt b/base.txt" in patch_content

def test_snapshot_staged_and_unstaged(tmp_path):
    repo_dir = setup_repo(tmp_path)

    (repo_dir / "unstaged.txt").write_text("unstaged")
    subprocess.run(["git", "add", "unstaged.txt"], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-m", "add unstaged tracking"], cwd=repo_dir, check=True)
    (repo_dir / "unstaged.txt").write_text("unstaged_mod")

    (repo_dir / "staged.txt").write_text("staged")
    subprocess.run(["git", "add", "staged.txt"], cwd=repo_dir, check=True)

    dest_dir = tmp_path / "snapshot"
    snapshot = create_source_snapshot(repo_dir, dest_dir)

    patch_content = (dest_dir / "tracked.patch").read_text()
    assert "diff --git a/staged.txt b/staged.txt" in patch_content
    assert "diff --git a/unstaged.txt b/unstaged.txt" in patch_content

def test_snapshot_untracked_and_ignored(tmp_path):
    repo_dir = setup_repo(tmp_path)

    (repo_dir / ".gitignore").write_text("ignored.txt\n")
    (repo_dir / "ignored.txt").write_text("ignore me")
    (repo_dir / "untracked.txt").write_text("untrack me")

    dest_dir = tmp_path / "snapshot"
    snapshot = create_source_snapshot(repo_dir, dest_dir)

    # Check that untracked.tar contains untracked.txt but not ignored.txt
    tar_path = dest_dir / "untracked.tar"
    with tarfile.open(tar_path, "r") as tar:
        names = tar.getnames()
        assert "untracked.txt" in names
        assert "ignored.txt" not in names

        # Verify deterministic metadata
        ti = tar.getmember("untracked.txt")
        assert ti.mtime == 0
        assert ti.uid == 0
        assert ti.gid == 0
        assert ti.uname == ""
        assert ti.gname == ""

def test_snapshot_symlink(tmp_path):
    repo_dir = setup_repo(tmp_path)

    # Create an untracked symlink
    os.symlink("base.txt", repo_dir / "link.txt")

    dest_dir = tmp_path / "snapshot"
    snapshot = create_source_snapshot(repo_dir, dest_dir)

    tar_path = dest_dir / "untracked.tar"
    with tarfile.open(tar_path, "r") as tar:
        names = tar.getnames()
        assert "link.txt" in names
        ti = tar.getmember("link.txt")
        assert ti.issym()
        assert ti.linkname == "base.txt"

def test_snapshot_determinism(tmp_path):
    repo_dir = setup_repo(tmp_path)
    (repo_dir / "untracked.txt").write_text("untrack")
    (repo_dir / "base.txt").write_text("mod")

    dest_dir1 = tmp_path / "snapshot1"
    dest_dir2 = tmp_path / "snapshot2"

    snap1 = create_source_snapshot(repo_dir, dest_dir1)

    # wait a bit to ensure time changes
    import time
    time.sleep(1.1)

    snap2 = create_source_snapshot(repo_dir, dest_dir2)

    assert snap1.snapshot_id == snap2.snapshot_id
    assert snap1.untracked_archive_sha256 == snap2.untracked_archive_sha256
    assert snap1.tracked_patch_sha256 == snap2.tracked_patch_sha256

def test_snapshot_no_mutation(tmp_path):
    repo_dir = setup_repo(tmp_path)
    (repo_dir / "base.txt").write_text("mod")
    (repo_dir / "untracked.txt").write_text("untrack")

    # Capture index and worktree state before
    status_before = subprocess.run(["git", "status", "--porcelain"], cwd=repo_dir, capture_output=True, text=True).stdout

    dest_dir = tmp_path / "snapshot"
    create_source_snapshot(repo_dir, dest_dir)

    # Capture index and worktree state after
    status_after = subprocess.run(["git", "status", "--porcelain"], cwd=repo_dir, capture_output=True, text=True).stdout

    assert status_before == status_after
