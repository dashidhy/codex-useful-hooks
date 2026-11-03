# Task completion checks

This group asks the main agent to review work before ending the turn when the user's request has multiple milestones or acceptance criteria and a partial result could plausibly look complete.

## Install

1. Copy this directory to a stable local path, or use it in an existing persistent checkout. It requires Python 3.10+ and uses only the standard library.
2. For all projects, use `hooks.json` in your Codex home (normally `~/.codex/hooks.json`). For one trusted project, use `.codex/hooks.json` at the project root.
3. If creating the file, start with [hooks.example.json](hooks.example.json). For an existing file, merge the two handlers below into their respective events, preserving other handlers and their matchers. Check the active hook sources for registrations of this script. When upgrading or moving it, update its existing commands in the selected scope, including any from the old flat layout.
4. Set both commands to the absolute path of your Python interpreter followed by the absolute path to [task_hook.py](task_hook.py) in the installed directory. Quote each path as needed for the hook's shell.
5. Validate the edited JSON (for example, `python3 -m json.tool /path/to/hooks.json`). Open `/hooks` in the CLI or **Settings > Hooks** in the desktop app. Confirm that each registration appears once with the expected command and matcher, then review and trust it. [Codex hooks documentation](https://learn.chatgpt.com/docs/hooks#review-and-trust-hooks)

| Event | Configuration | Purpose |
| --- | --- | --- |
| `UserPromptSubmit` | 3-second timeout, `additionalContextLimit: 1024` | Supply the classification instructions and a command to mark this turn. |
| `Stop` | 3-second timeout | Consume the turn marker and request one completion review for a marked task. |

## What the agent sees

1. On `UserPromptSubmit`, the script injects classification instructions and a turn-specific marking command through `additionalContext`. Submission creates no files. For a qualifying request, the agent explains in a progress update which intermediate result could look complete and what it would still need to deliver or verify. It then runs the marking command and carries out the work. Ordinary questions and routine steps toward a single clear result normally proceed without marking or a classification announcement.
2. The marking command creates an empty file identified by session and turn. On the first stop for that marked turn, the handler consumes the marker and returns `decision: "block"` with the self-check instructions in `reason`.
3. The agent compares what it delivered and verified against the user's requested outcome. For open requirements, it takes the next concrete action using the tools, information, and authorization available. If one part is blocked, it completes independent work and identifies the decision, access, or external change required for the rest.
4. On the following stop, or on an unmarked turn, the handler allows the turn to end. The classification and self-check prompts live in [task_hook.py](task_hook.py) as `CLASSIFY` and `SELF_CHECK` respectively.

## Limitations

The review depends on the main agent recognizing a qualifying request and successfully running the supplied command. Only the stop handler consumes the marker. An interrupted turn may leave its marker in the system temporary directory, but its session and turn identifiers prevent it from triggering another turn's review.

## Verify

Run the included tests from the installed group directory with Python 3.10+.

```sh
python3 -m unittest discover -s tests -v
```

They check that a marked turn triggers one review and that unmarked turns and other sessions can stop normally.

For a live check, ask Codex to check whether a particular file is writable. It should report the result without announcing a classification or running the marking command, even if it takes several steps to check.

Then ask Codex to add a feature to an API, connect it to the UI, and verify the flow end to end. Its progress update should explain that a working API would still leave the UI connection and end-to-end check outstanding. Verify that it runs the marking command and receives the self-check once at the first stop. If work remains and the agent can act, inspect the tool calls and results to confirm that it continues the work.
