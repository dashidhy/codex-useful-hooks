"""Session storage shared by context recovery and task completion."""
import hashlib
import os
from pathlib import Path
import tempfile


def snapshot_root() -> Path:
    uid = str(os.getuid()) if hasattr(os, "getuid") else hashlib.sha256(
        str(Path.home()).encode()
    ).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / f"simple-context-hook-{uid}"


def session_directory(root: Path, session_id: str) -> Path:
    return root / hashlib.sha256(session_id.encode()).hexdigest()
