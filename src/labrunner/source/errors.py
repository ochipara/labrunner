class LabRunnerSourceError(Exception):
    """Base class for source-related LabRunner errors."""
    pass

class NotGitRepository(LabRunnerSourceError):
    """Raised when the specified directory is not a Git repository."""
    pass

class UnsupportedRepositoryState(LabRunnerSourceError):
    """Raised when the repository is in an unsupported state (e.g. unborn)."""
    pass

class SnapshotCreationError(LabRunnerSourceError):
    """Raised when source snapshot creation fails."""
    pass

class SnapshotVerificationError(LabRunnerSourceError):
    """Raised when verifying a reconstructed source snapshot fails."""
    pass

class WorktreeCreationError(LabRunnerSourceError):
    """Raised when creating a detached worktree fails."""
    pass

class UnsafeCleanupError(LabRunnerSourceError):
    """Raised when a cleanup operation violates safety constraints."""
    pass

class UnsupportedGitVersion(LabRunnerSourceError):
    """Raised when the Git version is older than required."""
    pass
