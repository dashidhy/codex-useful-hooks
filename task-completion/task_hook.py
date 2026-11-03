#!/usr/bin/env python3
"""Classify a Codex turn on submission and review a marked task at Stop."""
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import sys
import tempfile


CLASSIFY = """Mark this turn for a completion review only if the user asks you to carry out work with multiple milestones or acceptance criteria, and a partial result could plausibly be mistaken for completion. Routine steps or tool calls used to establish a single clear result do not by themselves warrant a review.

If the turn qualifies, explain in a progress update which intermediate result could look complete and what would still need to be delivered or verified. Run the supplied marking command, then proceed.

Otherwise, proceed normally without marking the turn or announcing a classification. Use the primary language of the conversation."""

SELF_CHECK = """Before ending this turn, compare what you have delivered with the user's requested outcome, acceptance criteria, and latest scope constraints. Determine which requirements are satisfied, what evidence supports that judgment, and what work remains.

For each unfinished requirement, identify the next concrete action. If you can implement, investigate, or verify it with the information, tools, and authorization already available, take that action now. Continue any independent work even if another part of the task is blocked.

If further progress requires the user's input, explain exactly what is blocked, why you need the user, and what decision, information, or access would unblock it. If an external condition prevents progress, identify that condition and what remains unverified.

Once the requested outcome is complete, finish with the relevant verification results. Avoid repeating results the user has already received. Use the primary language of the conversation."""


def marker_root() -> Path:
    uid = str(os.getuid()) if hasattr(os, "getuid") else hashlib.sha256(
        str(Path.home()).encode()
    ).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / f"simple-context-hook-{uid}"


def marking_command(marker: Path) -> str:
    # Pass the absolute path because the tool shell may have a different TMPDIR.
    args = [sys.executable, str(Path(__file__).resolve()), "mark", str(marker)]
    if os.name == "nt":  # PowerShell requires a call operator for a quoted executable.
        return "& " + " ".join("'" + arg.replace("'", "''") + "'" for arg in args)
    return shlex.join(args)


def mark(marker: Path) -> None:
    session = marker.parent
    root = session.parent
    if (not marker.is_absolute() or root.name != marker_root().name
            or not re.fullmatch(r"[0-9a-f]{64}", session.name)
            or not re.fullmatch(r"task-[0-9a-f]{64}", marker.name)):
        raise ValueError("Invalid task marker path")
    for directory in (root, session):
        if directory.is_symlink():
            raise OSError("Task marker directories must not be symbolic links")
        directory.mkdir(mode=0o700, exist_ok=True)
    try:
        with marker.open("xb"):
            pass
    except FileExistsError:
        if marker.is_symlink() or not marker.is_file():
            raise OSError("Expected a regular task marker file")


def consume(marker: Path) -> bool:
    if marker.parent.is_symlink() or marker.parent.parent.is_symlink():
        return False
    try:
        marker.unlink()  # Only one Stop invocation can consume the turn's marker.
    except FileNotFoundError:
        return False
    try:
        marker.parent.rmdir()
    except OSError:
        pass  # The directory may already be gone or still contain other files.
    return True


def handle(event: object) -> dict:
    if not isinstance(event, dict):
        return {}
    name = event.get("hook_event_name")
    session_id = event.get("session_id")
    if name not in ("UserPromptSubmit", "Stop") or not isinstance(session_id, str) or not session_id:
        return {}
    session = marker_root() / hashlib.sha256(session_id.encode()).hexdigest()
    turn_id = event.get("turn_id")
    if isinstance(turn_id, str) and turn_id:
        marker = session / ("task-" + hashlib.sha256(turn_id.encode()).hexdigest())
        if name == "UserPromptSubmit":
            return {"hookSpecificOutput": {
                "hookEventName": name,
                "additionalContext": CLASSIFY + "\n\nTurn marking command:\n" + marking_command(marker),
            }}
        if consume(marker) and not event.get("stop_hook_active", False):
            return {"decision": "block", "reason": SELF_CHECK}

    return {}


def main() -> int:
    if len(sys.argv) > 1:
        if len(sys.argv) != 3 or sys.argv[1] != "mark":
            print("Usage: task_hook.py mark <turn-marker>", file=sys.stderr)
            return 2
        try:
            mark(Path(sys.argv[2]))
        except (OSError, ValueError) as error:
            print(f"Could not mark this turn: {error}", file=sys.stderr)
            return 1
        return 0
    try:
        result = handle(json.load(sys.stdin))
    except ValueError:
        result = {}
    except OSError as error:
        result = {"systemMessage": f"Task hook file operation failed: {error}"}
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
