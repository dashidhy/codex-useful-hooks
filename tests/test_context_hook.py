import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "context_hook.py"
spec = importlib.util.spec_from_file_location("context_hook", SCRIPT)
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)


class ContextHookTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "snapshots"
        self.transcript = self.base / 'history \U0001f4ac "name".jsonl'
        self.original = b'{"message":"one"}\n' + '{"message":"\U0001f4ac"}\n'.encode()
        self.transcript.write_bytes(self.original)
        self.event = {
            "hook_event_name": "SessionStart", "source": "compact",
            "session_id": "session-a", "transcript_path": str(self.transcript),
        }

    def create(self, event=None):
        return hook.handle(self.event if event is None else event, self.root)

    def snapshots(self, session_id="session-a"):
        return list(hook.session_directory(self.root, session_id).glob("snapshot-*.jsonl"))

    def test_short_prompt_and_snapshot_without_cwd(self):
        result = self.create()
        context = result["hookSpecificOutput"]["additionalContext"]
        self.assertEqual(result["hookSpecificOutput"]["hookEventName"], "SessionStart")
        self.assertTrue(context.startswith(hook.PROMPT))
        self.assertNotIn("Current working directory", context)
        path = json.loads(context.split("Conversation history snapshot: ", 1)[1])
        self.assertEqual(Path(path).read_bytes(), self.original)
        self.assertNotEqual(Path(path), self.transcript)

    def test_incomplete_trailing_record_is_excluded(self):
        self.transcript.write_bytes(self.original + b'{"partial":')
        self.create()
        self.assertEqual(self.snapshots()[0].read_bytes(), self.original)

    def test_appends_after_boundary_are_excluded(self):
        real = hook.completed_prefix_end

        def append_after_capture(source, size):
            with self.transcript.open("ab") as writer:
                writer.write(b'{"late":true}\n')
            return real(source, size)

        with patch.object(hook, "completed_prefix_end", side_effect=append_after_capture):
            self.create()
        snapshot = self.snapshots()[0]
        self.assertEqual(snapshot.read_bytes(), self.original)
        with self.transcript.open("ab") as writer:
            writer.write(b'{"even_later":true}\n')
        self.assertEqual(snapshot.read_bytes(), self.original)

    def test_truncation_during_copy_removes_partial_snapshot(self):
        real = hook.completed_prefix_end

        def truncate_after_capture(source, size):
            end = real(source, size)
            self.transcript.write_bytes(b"")
            return end

        with patch.object(hook, "completed_prefix_end", side_effect=truncate_after_capture):
            result = self.create()
        self.assertIn("systemMessage", result)
        self.assertEqual(self.snapshots(), [])
        self.assertEqual(list(self.root.glob("**/.partial-*.jsonl")), [])

    def test_multiple_snapshots_are_cleaned_at_stop_and_original_survives(self):
        self.create()
        self.create()
        self.assertEqual(len(self.snapshots()), 2)
        result = hook.handle({"hook_event_name": "Stop", "session_id": "session-a"}, self.root)
        self.assertEqual(result, {})
        self.assertEqual(self.snapshots(), [])
        self.assertEqual(self.transcript.read_bytes(), self.original)

    def test_cleanup_is_session_scoped_and_preserves_unrelated_files(self):
        self.create()
        self.create({**self.event, "session_id": "session-b"})
        directory = hook.session_directory(self.root, "session-a")
        unrelated = directory / "keep.txt"
        unrelated.write_text("not ours")
        hook.handle({"hook_event_name": "Stop", "session_id": "session-a"}, self.root)
        self.assertEqual(self.snapshots(), [])
        self.assertEqual(len(self.snapshots("session-b")), 1)
        self.assertTrue(unrelated.exists())

    def test_other_events_and_sources_do_not_create_or_cleanup(self):
        self.create()
        self.create({**self.event, "session_id": "session-b"})
        existing = self.snapshots() + self.snapshots("session-b")
        events = [
            {**self.event, "source": source}
            for source in ("startup", "resume", "clear", "fork", None, "Compact", "compact-extra")
        ] + [
            {**self.event, "hook_event_name": name}
            for name in ("Interrupt", "SessionEnd", "PostCompact", "PreCompact", "UserPromptSubmit", "unknown", None)
        ]
        events.append({key: value for key, value in self.event.items() if key != "source"})
        with patch.object(hook, "snapshot_root") as root, \
                patch.object(hook, "create_snapshot") as create, \
                patch.object(hook, "cleanup") as cleanup, \
                patch.object(Path, "iterdir", side_effect=AssertionError("unexpected directory traversal")):
            for event in events:
                with self.subTest(event=event):
                    self.assertEqual(hook.handle(event, self.root), {})
                    self.assertEqual(hook.handle(event), {})
            root.assert_not_called()
            create.assert_not_called()
            cleanup.assert_not_called()
        self.assertEqual(set(self.snapshots() + self.snapshots("session-b")), set(existing))
        for snapshot in existing:
            self.assertEqual(snapshot.read_bytes(), self.original)

    @unittest.skipIf(os.name == "nt", "symlink setup may require Windows privileges")
    def test_cleanup_rejects_symlinked_snapshot_root(self):
        external = self.base / "external"
        directory = hook.session_directory(external, "session-a")
        directory.mkdir(parents=True)
        protected = directory / ("snapshot-" + "a" * 32 + ".jsonl")
        protected.write_text("must survive")
        self.root.symlink_to(external, target_is_directory=True)
        hook.handle({"hook_event_name": "Stop", "session_id": "session-a"}, self.root)
        self.assertTrue(protected.exists())

    def test_compact_preserves_existing_snapshots_regardless_of_age(self):
        self.create()
        self.create({**self.event, "session_id": "session-b"})
        existing = self.snapshots() + self.snapshots("session-b")
        for snapshot in existing:
            os.utime(snapshot, (0, 0))
        with patch.object(hook, "cleanup") as cleanup:
            self.create()
            cleanup.assert_not_called()
        self.assertEqual(len(self.snapshots()), 2)
        self.assertEqual(len(self.snapshots("session-b")), 1)
        for snapshot in existing:
            self.assertEqual(snapshot.read_bytes(), self.original)

    def test_missing_transcript_is_nonblocking(self):
        for transcript in (None, str(self.base / "missing")):
            with self.subTest(transcript=transcript):
                result = self.create({**self.event, "transcript_path": transcript})
                self.assertIn("systemMessage", result)
                self.assertIn("Could not create a snapshot", result["hookSpecificOutput"]["additionalContext"])
                self.assertNotIn("decision", result)
                self.assertNotIn("continue", result)

    def test_missing_session_or_unrelated_event_is_noop(self):
        for event in (None, {}, {"hook_event_name": "Stop"}, {**self.event, "hook_event_name": "PostCompact"}):
            self.assertEqual(hook.handle(event, self.root), {})

    def test_session_id_cannot_escape_snapshot_root(self):
        session_id = "../../unrelated"
        self.create({**self.event, "session_id": session_id})
        self.assertEqual(hook.session_directory(self.root, session_id).parent, self.root)
        self.assertEqual(len(self.snapshots(session_id)), 1)

    def test_json_stdout_for_invalid_input_and_cleanup(self):
        for payload in ("{invalid", json.dumps({"hook_event_name": "Stop"})):
            result = subprocess.run([sys.executable, str(SCRIPT)], input=payload, text=True,
                                    capture_output=True, check=True)
            self.assertEqual(json.loads(result.stdout), {})
            self.assertEqual(result.stderr, "")

    def test_example_wiring_routes_each_event_to_one_command(self):
        config = json.loads((SCRIPT.parent / "hooks.example.json").read_text())
        expected = {"SessionStart": "context_hook.py", "UserPromptSubmit": "task_hook.py", "Stop": "task_hook.py"}
        self.assertEqual(set(config["hooks"]), set(expected))
        for event, script in expected.items():
            with self.subTest(event=event):
                group, = config["hooks"][event]
                self.assertEqual(group.get("matcher"), "^compact$" if event == "SessionStart" else None)
                handler, = group["hooks"]
                self.assertEqual(handler["type"], "command")
                self.assertEqual(Path(shlex.split(handler["command"])[-1]).name, script)


if __name__ == "__main__":
    unittest.main()
