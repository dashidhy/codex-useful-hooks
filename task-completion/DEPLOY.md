# Task completion checks

This group asks the main agent to review the result of an execution task before ending the turn. The agent classifies the request using the user's stated scope.

## Install

Follow the [repository deployment steps](../AGENTS.md#deployment) using [this group's example](hooks.example.json). Use absolute paths to a Python 3.10+ interpreter and to [task_hook.py](task_hook.py) in the retained checkout for both commands. The script uses the Python standard library.

| Event | Configuration | Purpose |
| --- | --- | --- |
| `UserPromptSubmit` | 3-second timeout, `additionalContextLimit: 1024` | Supply the classification instructions and a command to mark this turn. |
| `Stop` | 3-second timeout | Consume the turn marker and request one completion review for a marked task. |

For upgrades from the flat layout, update the existing repository-root `task_hook.py` commands to `task-completion/task_hook.py`.

## What the agent sees

1. On `UserPromptSubmit`, the script injects classification instructions and a turn-specific marking command through `additionalContext`. Submission creates no files. For a request to carry out work and deliver a checkable result, the agent explains in a user-visible progress update what it will deliver and why the request qualifies. It then runs the marking command and carries out the work. For an ordinary question or discussion, it answers directly.
2. The marking command creates an empty file identified by session and turn. On the first stop for that marked turn, the handler consumes the marker and returns `decision: "block"` with the self-check instructions in `reason`.
3. The agent compares what it delivered and verified against the user's requested outcome. For open requirements, it takes the next concrete action using the tools, information, and authorization available. If one part is blocked, it completes independent work and identifies the decision, access, or external change required for the rest.
4. On the following stop, or on an unmarked turn, the handler allows the turn to end. The classification and self-check prompts live in [task_hook.py](task_hook.py) as `CLASSIFY` and `SELF_CHECK` respectively.

## Limitations

The review depends on the main agent recognizing an execution task and successfully running the supplied command. Only the stop handler consumes the marker. An interrupted turn may leave its marker in the system temporary directory, but its session and turn identifiers prevent it from triggering another turn's review.

## Verify

From the checkout root, run `python3 -m unittest discover -s tests -p test_task_hook.py -v`. The tests use synthetic events and temporary directories to check marking, isolation by session and turn, and the one-time review.

For a live check, first ask a factual question and verify that Codex answers without announcing a classification or running a marking command. Then ask for a small, verifiable change. Inspect the progress update, marking command, actual change, and verification evidence. At the first stop the agent should receive the self-check once. If work remains and the agent can act, inspect the tool calls and results to confirm that it continues the work.
