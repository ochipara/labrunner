import tarfile
import time
from pathlib import Path

def reset_tarinfo(tarinfo: tarfile.TarInfo) -> tarfile.TarInfo:
    """Normalize tar metadata to ensure deterministic outputs."""
    tarinfo.uid = 0
    tarinfo.gid = 0
    tarinfo.uname = ""
    tarinfo.gname = ""
    tarinfo.mtime = 0

    # We preserve the permissions for regular files and symlinks.
    # We do not override type (it might be REG or SYMTYPE).
    return tarinfo

def create_deterministic_tar(source_paths: list[Path], root_dir: Path, output_tar: Path):
    """
    Creates a deterministic tar archive containing the source_paths.
    source_paths should be absolute paths or relative to the cwd, but we want
    them to be stored relative to root_dir in the tar archive.
    """
    # Sort files deterministically based on their normalized relative path
    def get_arcname(p: Path) -> str:
        # resolve relative to root_dir
        try:
            return str(p.relative_to(root_dir))
        except ValueError:
            return p.name # fallback, shouldn't happen if properly filtered

    sorted_paths = sorted(source_paths, key=get_arcname)

    with tarfile.open(output_tar, "w") as tar:
        for path in sorted_paths:
            arcname = get_arcname(path)

            # Use tarfile's gettarinfo but do not dereference symlinks
            tarinfo = tar.gettarinfo(name=str(path), arcname=arcname)
            tarinfo = reset_tarinfo(tarinfo)

            if tarinfo.issym():
                # Add symlink
                tar.addfile(tarinfo)
            elif tarinfo.isreg():
                # Add regular file with content
                with open(path, "rb") as f:
                    tar.addfile(tarinfo, f)
            else:
                # We do not add directories directly if they are just parents,
                # nor other types of special files.
                # If we want to capture empty directories, we'd need to handle them,
                # but the spec focuses on regular files and symlinks.
                # For untracked files from git ls-files, they are just files or symlinks.
                pass
