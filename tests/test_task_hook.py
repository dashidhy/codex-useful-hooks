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

    def event(self, name, **fields):
        return self.invoke(json.dumps({**self.ids, "hook_event_name": name, **fields}))

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
        response = self.event("Stop", stop_hook_active=False)
        self.assertEqual(response["decision"], "block")
        self.assertTrue(response["reason"].strip())
        self.assertEqual(self.event("Stop", stop_hook_active=False), {})

    def test_continuation_keeps_snapshot_until_final_stop_even_when_remarked(self):
        command = self.submit()
        self.mark(command)
        transcript = self.base / "transcript.jsonl"
        transcript.write_bytes(b'{"synthetic":true}\n')
        compact = {**self.ids, "hook_event_name": "SessionStart", "source": "compact",
                   "transcript_path": str(transcript)}
        output = self.invoke(json.dumps(compact), CONTEXT_SCRIPT)["hookSpecificOutput"]
        snapshot = Path(json.loads(output["additionalContext"].split("Conversation history snapshot: ")[-1]))
        self.assertEqual(self.event("Stop", stop_hook_active=False)["decision"], "block")
        self.assertEqual(snapshot.read_bytes(), transcript.read_bytes())
        self.mark(command)
        self.assertEqual(self.event("Stop", stop_hook_active=True), {})
        self.assertFalse(snapshot.exists())
        self.assertEqual(transcript.read_bytes(), b'{"synthetic":true}\n')
        self.assertEqual(self.event("Stop", stop_hook_active=False), {})

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
