import pytest
import subprocess
from pathlib import Path

from labrunner.source.git import GitHelper
from labrunner.source.errors import (
    UnsupportedGitVersion,
    NotGitRepository,
    UnsupportedRepositoryState,
)

def setup_repo(tmp_path: Path) -> Path:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_dir, check=True)
    return repo_dir

def test_git_version_check(tmp_path):
    # This assumes the test environment has a supported git version installed.
    helper = GitHelper(tmp_path)
    helper.check_version() # Should not raise

    # Mocking version to be old
    original_get_version = helper.get_version
    helper.get_version = lambda: (2, 34, 0)
    with pytest.raises(UnsupportedGitVersion, match="Git version >= 2.35 required"):
        helper.check_version()
    helper.get_version = original_get_version

def test_not_git_repository(tmp_path):
    helper = GitHelper(tmp_path)
    with pytest.raises(NotGitRepository):
        helper.check_is_repo()

def test_unborn_repository(tmp_path):
    repo_dir = setup_repo(tmp_path)
    helper = GitHelper(repo_dir)
    helper.check_is_repo() # Should pass

    with pytest.raises(UnsupportedRepositoryState, match="unborn"):
        helper.get_head_commit()

def test_valid_repository(tmp_path):
    repo_dir = setup_repo(tmp_path)
    # Create initial commit
    (repo_dir / "test.txt").write_text("hello")
    subprocess.run(["git", "add", "test.txt"], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo_dir, check=True)

    helper = GitHelper(repo_dir)
    assert helper.get_repo_root() == repo_dir.resolve()
    commit_id = helper.get_head_commit()
    assert len(commit_id) == 40 # full sha1 length

def test_canonical_remote(tmp_path):
    repo_dir = setup_repo(tmp_path)
    helper = GitHelper(repo_dir)

    assert helper.get_canonical_remote() is None

    subprocess.run(["git", "remote", "add", "origin", "git@example.com:repo.git"], cwd=repo_dir, check=True)
    assert helper.get_canonical_remote() == "git@example.com:repo.git"
