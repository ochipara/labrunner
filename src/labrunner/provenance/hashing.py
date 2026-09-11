import json
import hashlib
from typing import Any

def get_canonical_json(data: Any) -> str:
    """
    Serializes a Python object to canonical JSON.
    Uses UTF-8, sorted keys, stable separators, and no irrelevant timestamps.
    """
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':'))

def hash_canonical_json(data: Any) -> str:
    """
    Computes a SHA-256 digest of the canonical JSON representation.
    """
    canonical = get_canonical_json(data)
    return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"
