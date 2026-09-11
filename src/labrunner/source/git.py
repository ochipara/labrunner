import subprocess
import re
from pathlib import Path
from typing import List, Optional

from labrunner.source.errors import (
    UnsupportedGitVersion,
    NotGitRepository,
    UnsupportedRepositoryState,
)


class GitHelper:
    """Safe wrapper for Git CLI operations."""

    MIN_GIT_VERSION = (2, 35)

    def __init__(self, repo_path: Path):
        self.repo_path = repo_path.resolve()

    def run_git(self, args: List[str], check: bool = True) -> subprocess.CompletedProcess:
        """Run a Git command safely with subprocess.run."""
        return subprocess.run(
            ["git"] + args,
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            check=check,
        )

    def get_version(self) -> tuple[int, ...]:
        """Get the Git version as a tuple of integers."""
        try:
            result = subprocess.run(
                ["git", "--version"],
                capture_output=True,
                text=True,
                check=True,
            )
            # Example output: "git version 2.34.1"
            match = re.search(r"git version (\d+\.\d+(\.\d+)?)", result.stdout)
            if not match:
                raise UnsupportedGitVersion(f"Could not parse git version from: {result.stdout}")
            version_str = match.group(1)
            return tuple(int(x) for x in version_str.split("."))
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            raise UnsupportedGitVersion("Git is not installed or not found in PATH.") from e

    def check_version(self) -> None:
        """Ensure Git version is >= MIN_GIT_VERSION."""
        version = self.get_version()
        if version[:2] < self.MIN_GIT_VERSION:
            min_v_str = ".".join(map(str, self.MIN_GIT_VERSION))
            v_str = ".".join(map(str, version))
            raise UnsupportedGitVersion(
                f"Git version >= {min_v_str} required. Found {v_str}."
            )

    def check_is_repo(self) -> None:
        """Ensure the path is a valid Git repository."""
        result = self.run_git(["rev-parse", "--is-inside-work-tree"], check=False)
        if result.returncode != 0:
            raise NotGitRepository(f"Path is not a Git repository: {self.repo_path}")

    def get_repo_root(self) -> Path:
        """Get the absolute path to the repository root."""
        self.check_is_repo()
        result = self.run_git(["rev-parse", "--show-toplevel"])
        return Path(result.stdout.strip())

    def get_head_commit(self) -> str:
        """Get the full commit ID of HEAD."""
        self.check_is_repo()
        result = self.run_git(["rev-parse", "HEAD"], check=False)
        if result.returncode != 0:
            raise UnsupportedRepositoryState("Could not resolve HEAD. Is the repository unborn?")
        return result.stdout.strip()

    def get_canonical_remote(self) -> Optional[str]:
        """Get the URL of the canonical remote ('origin'), if any."""
        self.check_is_repo()
        result = self.run_git(["remote", "get-url", "origin"], check=False)
        if result.returncode == 0:
            return result.stdout.strip()
        return None
