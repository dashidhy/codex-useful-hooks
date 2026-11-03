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


def owned_snapshot(path: Path) -> bool:
    """Only our generated filenames are eligible for deletion; never recurse."""
    name = path.name
    if not name.endswith(".jsonl"):
        return False
    for prefix in ("snapshot-", ".partial-"):
        if name.startswith(prefix):
            token = name[len(prefix):-len(".jsonl")]
            return len(token) == 32 and all(c in "0123456789abcdef" for c in token)
    return False


def cleanup(directory: Path) -> None:
    if directory.parent.is_symlink() or directory.is_symlink() or not directory.is_dir():
        return
    try:
        entries = list(directory.iterdir())
    except FileNotFoundError:
        return
    for path in entries:
        try:
            if not owned_snapshot(path) or path.is_dir():
                continue
            path.unlink(missing_ok=True)
        except FileNotFoundError:
            pass  # Another cleanup hook already removed it.
    try:
        directory.rmdir()
    except OSError:
        pass  # Another snapshot, or an unrelated file, is still here.
