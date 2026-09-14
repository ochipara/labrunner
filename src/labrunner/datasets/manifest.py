import subprocess
import shutil
import hashlib
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List, Tuple
import os

from labrunner.datasets.errors import (
    DatasetNotFound,
    DatasetUnreadable,
    ManifestMalformed,
    DatasetVerificationError,
)


@dataclass
class DatasetEntry:
    path: str
    size: int
    mtime_ns: int
    md5: str


class DatasetManifest:
    def __init__(self, entries: Dict[str, DatasetEntry]):
        self.entries = entries  # path -> DatasetEntry

    def get_canonical_identity(self) -> str:
        """Computes SHA-256 of the normalized MD5 manifest."""
        sorted_paths = sorted(self.entries.keys())
        manifest_lines = []
        for p in sorted_paths:
            manifest_lines.append(f"{self.entries[p].md5}  {p}")

        canonical_str = "\n".join(manifest_lines) + ("\n" if manifest_lines else "")
        return f"sha256:{hashlib.sha256(canonical_str.encode('utf-8')).hexdigest()}"

    def to_file(self, filepath: Path) -> None:
        """Writes the canonical manifest (just MD5 and paths)."""
        sorted_paths = sorted(self.entries.keys())
        lines = []
        for p in sorted_paths:
            lines.append(f"{self.entries[p].md5}  {p}\n")

        with open(filepath, 'w') as f:
            f.writelines(lines)

    def to_local_metadata(self, filepath: Path) -> None:
        """Writes local metadata (size and mtime_ns) for fast checks."""
        import json
        out = {}
        for p, entry in self.entries.items():
            out[p] = {
                "size": entry.size,
                "mtime_ns": entry.mtime_ns,
                "md5": entry.md5,
            }
        with open(filepath, 'w') as f:
            json.dump(out, f, indent=2, sort_keys=True)


def _get_md5_cmd() -> str:
    if shutil.which("md5sum"):
        return "md5sum"
    elif shutil.which("md5"):
        return "md5"
    else:
        raise DatasetUnreadable("Neither md5sum nor md5 utility is available.")


def _compute_file_md5(filepath: Path, cmd: str) -> str:
    try:
        if cmd == "md5sum":
            # Output: "d41d8cd98f00b204e9800998ecf8427e  file.txt"
            res = subprocess.run([cmd, str(filepath)], capture_output=True, text=True, check=True)
            return res.stdout.split()[0].lower()
        else:
            # md5 (macOS) Output: "MD5 (file.txt) = d41d8cd98f00b204e9800998ecf8427e"
            # Or use md5 -q
            res = subprocess.run([cmd, "-q", str(filepath)], capture_output=True, text=True, check=True)
            return res.stdout.strip().lower()
    except subprocess.CalledProcessError as e:
        raise DatasetUnreadable(f"Failed to compute MD5 for {filepath}: {e.stderr}")


def register_dataset(dataset_root: Path) -> Tuple[DatasetManifest, List[str]]:
    """
    Registers a dataset by computing MD5, size, and mtime_ns for all regular files.
    Skips and reports symlinks.
    """
    dataset_root = dataset_root.resolve()
    if not dataset_root.exists():
        raise DatasetNotFound(f"Dataset root {dataset_root} does not exist.")

    cmd = _get_md5_cmd()
    entries = {}
    skipped = []

    # We walk the directory tree manually because os.walk follows symlink dirs if followlinks=True,
    # but we strictly NEVER follow symlinks.
    for root, dirs, files in os.walk(dataset_root, followlinks=False):
        # Prevent os.walk from entering symlink directories
        dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(root, d))]

        # Report skipped symlink directories
        for d in os.listdir(root):
            p = os.path.join(root, d)
            if os.path.islink(p) and os.path.isdir(p):
                 skipped.append(str(Path(p).relative_to(dataset_root)))

        for file in files:
            if file in (".labrunner_manifest.txt", ".labrunner_metadata.json"):
                continue
            filepath = Path(root) / file
            rel_path = str(filepath.relative_to(dataset_root))

            if filepath.is_symlink():
                skipped.append(rel_path)
                continue

            if not filepath.is_file():
                continue

            try:
                st = filepath.stat()
                md5 = _compute_file_md5(filepath, cmd)

                if len(md5) != 32:
                    raise DatasetUnreadable(f"Invalid MD5 output for {filepath}: {md5}")

                entries[rel_path] = DatasetEntry(
                    path=rel_path,
                    size=st.st_size,
                    mtime_ns=st.st_mtime_ns,
                    md5=md5,
                )
            except OSError as e:
                raise DatasetUnreadable(f"Cannot read {filepath}: {e}")

    return DatasetManifest(entries), skipped


def fast_check_dataset(dataset_root: Path, metadata_filepath: Path) -> None:
    """
    Performs a cheap check comparing path, size, and mtime_ns against local metadata.
    """
    import json
    dataset_root = dataset_root.resolve()

    if not metadata_filepath.exists():
        raise DatasetVerificationError("Local metadata not found. Run verification or register again.")

    try:
        with open(metadata_filepath, 'r') as f:
            metadata = json.load(f)
    except Exception as e:
        raise ManifestMalformed(f"Failed to parse local metadata: {e}")

    # Walk dataset to compare against metadata
    actual_paths = set()

    for root, dirs, files in os.walk(dataset_root, followlinks=False):
        dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(root, d))]

        for file in files:
            if file in (".labrunner_manifest.txt", ".labrunner_metadata.json"):
                continue
            filepath = Path(root) / file
            rel_path = str(filepath.relative_to(dataset_root))

            if filepath.is_symlink():
                continue

            if not filepath.is_file():
                continue

            actual_paths.add(rel_path)

            if rel_path not in metadata:
                raise DatasetVerificationError(f"Extra file found: {rel_path}")

            expected = metadata[rel_path]
            try:
                st = filepath.stat()
            except OSError:
                raise DatasetVerificationError(f"Missing file: {rel_path}")

            if st.st_size != expected["size"]:
                raise DatasetVerificationError(f"Size changed for {rel_path}")

            if st.st_mtime_ns != expected["mtime_ns"]:
                raise DatasetVerificationError(f"Modification time changed for {rel_path}")

    expected_paths = set(metadata.keys())
    missing = expected_paths - actual_paths
    if missing:
        raise DatasetVerificationError(f"Missing files: {', '.join(missing)}")


def verify_dataset(dataset_root: Path, manifest_filepath: Path) -> None:
    """
    Expensive check: recomputes MD5 for all files in the manifest and compares.
    """
    dataset_root = dataset_root.resolve()

    if not manifest_filepath.exists():
        raise DatasetVerificationError("Manifest file not found.")

    expected_md5s = {}
    try:
        with open(manifest_filepath, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split("  ", 1)
                if len(parts) != 2:
                    raise ManifestMalformed(f"Invalid manifest line: {line}")
                md5, path = parts
                expected_md5s[path] = md5
    except Exception as e:
        if isinstance(e, ManifestMalformed):
            raise
        raise ManifestMalformed(f"Failed to read manifest: {e}")

    cmd = _get_md5_cmd()

    # We walk the directory tree
    actual_paths = set()
    for root, dirs, files in os.walk(dataset_root, followlinks=False):
        dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(root, d))]

        for file in files:
            if file in (".labrunner_manifest.txt", ".labrunner_metadata.json"):
                continue
            filepath = Path(root) / file
            rel_path = str(filepath.relative_to(dataset_root))

            if filepath.is_symlink():
                continue

            if not filepath.is_file():
                continue

            actual_paths.add(rel_path)

            if rel_path not in expected_md5s:
                raise DatasetVerificationError(f"Extra file found: {rel_path}")

            actual_md5 = _compute_file_md5(filepath, cmd)
            if actual_md5 != expected_md5s[rel_path]:
                raise DatasetVerificationError(f"MD5 mismatch for {rel_path}: expected {expected_md5s[rel_path]}, got {actual_md5}")

    missing = set(expected_md5s.keys()) - actual_paths
    if missing:
        raise DatasetVerificationError(f"Missing files: {', '.join(missing)}")
