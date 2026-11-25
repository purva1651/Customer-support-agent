import hashlib
from pathlib import Path


def local_source_id(source: str | Path) -> str:
    """Return an opaque, stable identifier for a local knowledge file."""
    resolved = str(Path(source).expanduser().resolve())
    return hashlib.sha256(resolved.encode("utf-8")).hexdigest()
