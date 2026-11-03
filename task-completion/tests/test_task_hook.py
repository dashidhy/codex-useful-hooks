import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest


GROUP = Path(__file__).resolve().parents[1]
TASK_SCRIPT = GROUP / "task_hook.py"


class TaskHookTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="task hook's ")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.env = self.temp_environment(self.base)
        self.ids = {"session_id": "session-a", "turn_id": "turn-one"}

    @staticmethod
    def temp_environment(directory):
        env = {**os.environ, **dict.fromkeys(("TMPDIR", "TEMP", "TMP"), str(directory)),
               "PYTHONDONTWRITEBYTECODE": "1"}
        env.pop("PYTHONPATH", None)
        return env

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

    def test_example_registers_both_events_with_this_script(self):
        hooks = json.loads((GROUP / "hooks.example.json").read_text())["hooks"]
        self.assertEqual(set(hooks), {"UserPromptSubmit", "Stop"})
        for event, groups in hooks.items():
            with self.subTest(event=event):
                group, = groups
                self.assertNotIn("matcher", group)
                handler, = group["hooks"]
                self.assertEqual(handler["type"], "command")
                _, script = shlex.split(handler["command"])
                self.assertEqual(Path(script), Path("/ABSOLUTE/PATH/TO/task-completion") / TASK_SCRIPT.name)
                self.assertEqual(handler["timeout"], 3)
                if event == "UserPromptSubmit":
                    self.assertEqual(handler["additionalContextLimit"], 1024)

    def test_unmarked_question_creates_no_state_and_stops_normally(self):
        self.submit(prompt="How does compaction work?")
        self.assertEqual(list(self.base.iterdir()), [])
        self.assertEqual(self.event("Stop", stop_hook_active=False), {})
        self.assertEqual(list(self.base.iterdir()), [])

    def test_standalone_group_marks_idempotently_and_stop_consumes_the_mark(self):
        install = tempfile.TemporaryDirectory()
        self.addCleanup(install.cleanup)
        target = Path(install.name)
        group = shutil.copytree(GROUP, target / "task-completion",
                                ignore=shutil.ignore_patterns("__pycache__", "tests", target.name))
        script = group / TASK_SCRIPT.name
        command = self.submit(script=script, prompt="Fix the failing test.")
        self.assertIn(str(script.relative_to(target.parent)), command)
        # The model's tool shell can use a different temporary directory than the hook process.
        shell_tmp = self.base / "shell temp"
        shell_tmp.mkdir()
        for _ in range(2):
            self.mark(command, self.temp_environment(shell_tmp))
        marker, = (path for path in self.base.rglob("task-*") if path.is_file())
        response = self.event("Stop", script=script, stop_hook_active=False)
        self.assertEqual(response["decision"], "block")
        self.assertTrue(response["reason"].strip())
        self.assertFalse(marker.parent.exists())
        self.assertEqual(self.event("Stop", script=script, stop_hook_active=False), {})

    def test_unmarked_marked_and_continued_stops_preserve_other_files(self):
        command = self.submit(prompt="Fix the failing test.")
        self.mark(command)
        marker, = (path for path in self.base.rglob("task-*") if path.is_file())
        snapshot = marker.with_name("snapshot-" + "a" * 32 + ".jsonl")
        snapshot.write_bytes(b'{"synthetic":true}\n')
        self.assertEqual(self.event("Stop", turn_id="unmarked"), {})
        self.assertEqual(self.event("Stop")["decision"], "block")
        self.mark(command)
        self.assertEqual(self.event("Stop", stop_hook_active=True), {})
        self.assertEqual(self.event("Stop"), {})
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
