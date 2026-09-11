# Dataset Manifests

LabRunner defines dataset identities through deterministic precomputed MD5 manifests. By separating dataset identity from the raw underlying files, LabRunner can efficiently verify large multi-terabyte datasets without expensive hashing during experiment startup.

## Registration and Identity

When a dataset is registered, LabRunner enumerates all regular files within the dataset root (skipping and reporting symlinks), computes their MD5 checksum, file sizes, and modification times.

The dataset **content identity** is then established deterministically by hashing a canonical representation of the relative paths and their MD5 digests via SHA-256.

```text
canonical identity = SHA256( sorted(MD5 + "  " + normalized_path) )
```

> **Note:** MD5 is utilized exclusively as a lightweight content identifier for datasets, **not** as a security primitive.

## Everyday Verification (Fast Check)

For everyday experiment execution, LabRunner performs an inexpensive verification check. It compares the file types, sizes, and modification times against the registered metadata. If these match, the dataset is considered intact without reading and hashing large file contents.

## Symlinks Policy

Dataset symlinks (both file and directory symlinks) are **skipped and reported**. They are never followed to avoid infinite cycles, non-determinism, or hashing data outside the intended dataset directory.
