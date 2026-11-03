import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
TASK_SCRIPT = ROOT / "task-completion" / "task_hook.py"
CONTEXT_SCRIPT = ROOT / "compaction" / "context_hook.py"


class TaskHookTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="task hook's ")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.env = self.temp_environment(self.base)
        self.ids = {"session_id": "session-a", "turn_id": "turn-one"}

    @staticmethod
    def temp_environment(directory):
        return {**os.environ, **dict.fromkeys(("TMPDIR", "TEMP", "TMP"), str(directory)),
                "PYTHONDONTWRITEBYTECODE": "1"}

    def invoke(self, payload, script=TASK_SCRIPT):
        result = subprocess.run([sys.executable, str(script)], input=payload, text=True,
                                cwd=self.base, env=self.env, capture_output=True, check=True)
        self.assertEqual(result.stderr, "")
        return json.loads(result.stdout)

    def event(self, name, script=TASK_SCRIPT, **fields):
        return self.invoke(json.dumps({**self.ids, "hook_event_name": name, **fields}), script)

    def submit(self, **fields):
        output = self.event("UserPromptSubmit", **fields)["hookSpecificOutput"]
        self.assertEqual(output["hookEventName"], "UserPromptSubmit")
        prompt, command = output["additionalContext"].rstrip().rsplit("\n", 1)
        self.assertTrue(prompt.strip())
        return command

    def mark(self, command, env=None):
        shell = ["powershell", "-NoProfile", "-NonInteractive", "-Command"] if os.name == "nt" else ["sh", "-c"]
        subprocess.run([*shell, command], cwd=self.base, env=env or self.env,
                       capture_output=True, text=True, check=True)

    def create_snapshot(self):
        transcript = self.base / "transcript.jsonl"
        transcript.write_bytes(b'{"synthetic":true}\n')
        output = self.event("SessionStart", script=CONTEXT_SCRIPT, source="compact",
                            transcript_path=str(transcript))["hookSpecificOutput"]
        return Path(json.loads(output["additionalContext"].split("Conversation history snapshot: ")[-1]))

    def test_unmarked_question_creates_no_state_and_stops_normally(self):
        self.submit(prompt="How does compaction work?")
        self.assertEqual(list(self.base.iterdir()), [])
        self.assertEqual(self.event("Stop", stop_hook_active=False), {})
        self.assertEqual(list(self.base.iterdir()), [])

    def test_mark_command_is_idempotent_and_stop_consumes_the_mark(self):
        command = self.submit(prompt="Fix the failing test.")
        # The model's tool shell can use a different temporary directory than the hook process.
        shell_tmp = self.base / "shell temp"
        shell_tmp.mkdir()
        for _ in range(2):
            self.mark(command, self.temp_environment(shell_tmp))
        marker, = self.base.rglob("task-*")
        response = self.event("Stop", stop_hook_active=False)
        self.assertEqual(response["decision"], "block")
        self.assertTrue(response["reason"].strip())
        self.assertFalse(marker.parent.exists())
        self.assertEqual(self.event("Stop", stop_hook_active=False), {})

    def test_independent_stop_handlers_work_in_either_order(self):
        for scripts in ((TASK_SCRIPT, CONTEXT_SCRIPT), (CONTEXT_SCRIPT, TASK_SCRIPT)):
            with self.subTest(first=scripts[0].name):
                self.mark(self.submit())
                snapshot = self.create_snapshot()
                for script in scripts:
                    response = self.event("Stop", script=script, stop_hook_active=False)
                    if script == CONTEXT_SCRIPT:
                        self.assertEqual(response, {})
                        self.assertFalse(snapshot.exists())
                    else:
                        self.assertEqual(response["decision"], "block")
                        self.assertEqual(snapshot.exists(), script == scripts[0])
                self.assertFalse(snapshot.parent.exists())

    def test_unmarked_and_continued_task_stops_leave_snapshots_alone(self):
        snapshot = self.create_snapshot()
        self.submit(prompt="How does compaction work?")
        self.assertEqual(self.event("Stop", stop_hook_active=False), {})
        self.assertTrue(snapshot.is_file())
        command = self.submit(prompt="Fix the failing test.", turn_id="turn-two")
        self.mark(command)
        self.assertEqual(self.event("Stop", turn_id="turn-two")["decision"], "block")
        self.mark(command)
        self.assertEqual(self.event("Stop", turn_id="turn-two", stop_hook_active=True), {})
        self.assertEqual(self.event("Stop", turn_id="turn-two"), {})
        self.assertEqual(snapshot.read_bytes(), b'{"synthetic":true}\n')

    def test_mark_is_isolated_by_session_and_turn(self):
        self.mark(self.submit())
        self.assertEqual(self.event("Stop", session_id="session-b"), {})
        self.assertEqual(self.event("Stop", turn_id="turn-two"), {})
        self.assertEqual(self.event("Stop")["decision"], "block")

    def test_invalid_and_unrelated_events_return_empty_json(self):
        for payload in ("broken json", "null", "[]", "{}", json.dumps({**self.ids, "hook_event_name": "Other"})):
            with self.subTest(payload=payload):
                self.assertEqual(self.invoke(payload), {})
        for name in ("UserPromptSubmit", "Stop"):
            for field in self.ids:
                for value in (None, "", 5):
                    with self.subTest(event=name, field=field, value=value):
                        self.assertEqual(self.event(name, **{field: value}), {})
        self.assertEqual(list(self.base.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
