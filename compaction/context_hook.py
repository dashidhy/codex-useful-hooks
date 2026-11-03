#!/usr/bin/env python3
"""A small Codex context-recovery hook. Python 3.10+, standard library only."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "shared"))
from hook_state import session_directory, snapshot_root


PROMPT = """Context compaction has just completed. Now you should start with assessing and maintaining the completeness of the context information. First, carefully analyze and determine what key information is necessary for conducting current task, what contexts do you have right now, whether any key information has become uncertain or is missing after the compaction, and whether this could block further progress on the current task or introduce potential risks. If some key information fades away and needs to be recovered, try to search and retrieve it as needed from the code, project docs, Git history, and the `conversation history snapshot`.

The `conversation history snapshot` is a fixed, read-only copy of the current conversation's latest JSONL log file. It may contain only recent history; earlier records may be stored in other log files. The `payload.history_base` field in the snapshot's first `session_meta` record identifies the source of earlier history and the cutoff for reading it. The source file may reference still earlier history in the same way. Follow these references as needed to retrieve earlier conversation information.

After completing the assessment and any necessary retrieval, communicate the outcome to the user in a progress update before continuing the task. Explain whether the available context information is sufficient to proceed, the basis for that assessment, any information recovered, and any uncertainties that remain.

If some key information remains uncertain after checking these sources, pause the task and ask the user for clarification. Resume the original task only once the information needed to proceed has been confirmed.

Continue responding in the primary language of the current conversation."""
COPY_CHUNK = 1024 * 1024


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


def completed_prefix_end(source, size: int) -> int:
    """Find the last newline within a fixed byte boundary without loading the log."""
    position = size
    while position:
        start = max(0, position - COPY_CHUNK)
        source.seek(start)
        block = source.read(position - start)
        if len(block) != position - start:
            raise OSError("Conversation history was truncated before copying")
        newline = block.rfind(b"\n")
        if newline >= 0:
            return start + newline + 1
        position = start
    return 0


def create_snapshot(transcript: Path, directory: Path) -> Path:
    # Open first: subsequent appends are excluded by this captured size. A rename
    # of the live log does not change this already-open file handle.
    with transcript.open("rb") as source:
        size = os.fstat(source.fileno()).st_size
        end = completed_prefix_end(source, size)
        if end == 0:
            raise OSError("Conversation history contains no complete JSONL records")
        for folder in (directory.parent, directory):
            if folder.is_symlink():
                raise OSError("Snapshot directories must not be symbolic links")
            folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        token = uuid.uuid4().hex
        partial = directory / f".partial-{token}.jsonl"
        target = directory / f"snapshot-{token}.jsonl"
        try:
            source.seek(0)
            with partial.open("xb") as destination:
                os.chmod(partial, 0o600)
                remaining = end
                while remaining:
                    block = source.read(min(COPY_CHUNK, remaining))
                    if not block:
                        raise OSError("Conversation history was truncated while copying")
                    destination.write(block)
                    remaining -= len(block)
            if os.fstat(source.fileno()).st_size < end:
                raise OSError("Conversation history was truncated while copying")
            partial.replace(target)
            # The agent only needs to read it. Deletion still works via its parent.
            if os.name != "nt":
                target.chmod(0o400)
            return target
        except BaseException:
            partial.unlink(missing_ok=True)
            target.unlink(missing_ok=True)
            raise


def handle(event: object, root: Path | None = None) -> dict:
    if not isinstance(event, dict):
        return {}
    name = event.get("hook_event_name")
    source = event.get("source")
    if name != "Stop" and not (name == "SessionStart" and source == "compact"):
        return {}
    session_id = event.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        return {}
    root = snapshot_root() if root is None else root
    directory = session_directory(root, session_id)

    if name == "Stop":
        cleanup(directory)
        return {}  # Never blocks stopping or requests another model turn.

    output = {"hookSpecificOutput": {"hookEventName": "SessionStart"}}
    try:
        path = event.get("transcript_path")
        if not isinstance(path, str) or not path:
            raise OSError("Codex did not provide a conversation history path")
        snapshot = create_snapshot(Path(path), directory)
        output["hookSpecificOutput"]["additionalContext"] = (
            PROMPT + "\n\nConversation history snapshot: " + json.dumps(str(snapshot), ensure_ascii=False)
        )
    except OSError as error:
        output["hookSpecificOutput"]["additionalContext"] = (
            PROMPT + "\n\nConversation history snapshot: Could not create a snapshot for this run. Do not assume the conversation history has been recovered."
        )
        output["systemMessage"] = f"codex-useful-hooks: Could not create a history snapshot ({error})"
    return output


def main() -> None:
    try:
        event = json.load(sys.stdin)
    except (ValueError, OSError):
        result = {}
    else:
        try:
            result = handle(event)
        except OSError as error:
            result = {"systemMessage": f"codex-useful-hooks: File operation failed ({error})"}
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
