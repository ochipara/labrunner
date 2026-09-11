import pytest
import os
import shutil
from pathlib import Path

from labrunner.datasets.manifest import (
    register_dataset,
    fast_check_dataset,
    verify_dataset,
)
from labrunner.datasets.errors import (
    DatasetNotFound,
    DatasetVerificationError,
    ManifestMalformed,
)

def create_dataset(tmp_path: Path):
    ds_dir = tmp_path / "dataset"
    ds_dir.mkdir()

    (ds_dir / "file1.txt").write_text("hello")
    (ds_dir / "file2.bin").write_bytes(b"\x00\x01\x02")

    sub = ds_dir / "sub"
    sub.mkdir()
    (sub / "file3.txt").write_text("world")

    # Symlink file
    os.symlink("file1.txt", ds_dir / "link.txt")

    # Symlink dir
    os.symlink("sub", ds_dir / "link_dir")

    return ds_dir

def test_register_dataset(tmp_path):
    ds_dir = create_dataset(tmp_path)

    manifest, skipped = register_dataset(ds_dir)

    assert len(manifest.entries) == 3
    assert "file1.txt" in manifest.entries
    assert "file2.bin" in manifest.entries
    assert "sub/file3.txt" in manifest.entries

    # Ensure MD5 is correct for file1.txt
    import hashlib
    h = hashlib.md5(b"hello").hexdigest()
    assert manifest.entries["file1.txt"].md5 == h

    assert len(skipped) == 2
    assert set(skipped) == {"link.txt", "link_dir"}

    identity = manifest.get_canonical_identity()
    assert identity.startswith("sha256:")

def test_dataset_determinism(tmp_path):
    ds_dir = create_dataset(tmp_path)

    m1, _ = register_dataset(ds_dir)

    import time
    time.sleep(1.1)

    # Re-register without changes
    m2, _ = register_dataset(ds_dir)

    # Even though mtime changed (wait, mtime didn't change unless we touch it),
    # let's touch a file to change mtime but not content.
    os.utime(ds_dir / "file1.txt", None)

    m3, _ = register_dataset(ds_dir)

    # The canonical identity should be the same, because it depends only on MD5s and paths!
    assert m1.get_canonical_identity() == m2.get_canonical_identity()
    assert m2.get_canonical_identity() == m3.get_canonical_identity()

def test_fast_check_dataset(tmp_path):
    ds_dir = create_dataset(tmp_path)
    meta_path = tmp_path / "meta.json"

    manifest, _ = register_dataset(ds_dir)
    manifest.to_local_metadata(meta_path)

    # Fast check should succeed
    fast_check_dataset(ds_dir, meta_path)

    # Change file size
    (ds_dir / "file1.txt").write_text("hello world")
    with pytest.raises(DatasetVerificationError, match="Size changed"):
        fast_check_dataset(ds_dir, meta_path)

    # Revert size, change mtime
    (ds_dir / "file1.txt").write_text("hello")
    # Wait to ensure mtime is strictly different
    import time
    time.sleep(0.1)
    os.utime(ds_dir / "file1.txt", None)
    with pytest.raises(DatasetVerificationError, match="Modification time changed"):
        fast_check_dataset(ds_dir, meta_path)

def test_verify_dataset(tmp_path):
    ds_dir = create_dataset(tmp_path)
    manifest_path = tmp_path / "manifest.md5"

    manifest, _ = register_dataset(ds_dir)
    manifest.to_file(manifest_path)

    verify_dataset(ds_dir, manifest_path)

    # Change content (but keep size same if we want to bypass fast check, but here we just test verify)
    (ds_dir / "file1.txt").write_text("world") # same size

    with pytest.raises(DatasetVerificationError, match="MD5 mismatch"):
        verify_dataset(ds_dir, manifest_path)

def test_missing_and_extra_files(tmp_path):
    ds_dir = create_dataset(tmp_path)
    manifest_path = tmp_path / "manifest.md5"

    manifest, _ = register_dataset(ds_dir)
    manifest.to_file(manifest_path)

    (ds_dir / "file1.txt").unlink()
    with pytest.raises(DatasetVerificationError, match="Missing files: file1.txt"):
        verify_dataset(ds_dir, manifest_path)

    (ds_dir / "file1.txt").write_text("hello") # restore

    (ds_dir / "extra.txt").write_text("extra")
    with pytest.raises(DatasetVerificationError, match="Extra file found: extra.txt"):
        verify_dataset(ds_dir, manifest_path)

def test_spaces_and_unicode_filenames(tmp_path):
    ds_dir = tmp_path / "dataset"
    ds_dir.mkdir()

    (ds_dir / "file with spaces.txt").write_text("spaces")
    (ds_dir / "ünicödé.txt").write_text("unicode")

    manifest, _ = register_dataset(ds_dir)
    assert len(manifest.entries) == 2

    manifest_path = tmp_path / "manifest.md5"
    manifest.to_file(manifest_path)

    verify_dataset(ds_dir, manifest_path)
