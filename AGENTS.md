# Agent guide

The `codex-useful-hooks` collection contains hooks for context recovery after compaction and task completion checks. Use this guide when deploying, verifying, or modifying them.

## Requirements

- Python 3.10+ and its standard library.
- A Codex client supporting the hook events and fields in `hooks.example.json`.
- A persistent local checkout. The installed commands execute `context_hook.py` and `task_hook.py` directly from that checkout.

Both scripts run locally. The main agent classifies requests, reviews its work, and retrieves context with its existing tools.

## Task completion checks

On `UserPromptSubmit`, `task_hook.py` injects classification instructions and a turn-specific marking command through `additionalContext`. Submission creates no files. The main agent alone decides whether the current request asks it to carry out work and deliver a checkable result.

- For a task, the agent first tells the user in a visible progress update what it will deliver and why the request qualifies as a task. It then runs the supplied command and carries out the work. The command creates an empty marker identified by both session and turn.
- For an ordinary question or discussion, the agent answers directly, with no classification announcement or marking command.

The single configured `Stop` handler runs `task_hook.py`. At the first stop for a marked task, the script consumes the matching marker and returns `decision: "block"` with the self-check instructions in `reason`. It retains the session's snapshots for this review. The agent checks the requested outcome against the delivered work and its verification evidence. If a requirement is open, the agent takes concrete steps with the tools, information, and authorization available. If one part is blocked, the agent still completes independent work and identifies the specific input, access, or external change required for the remainder.

At the following stop, or on an unmarked turn, the handler runs the existing session snapshot cleanup and allows the turn to end. Only the Stop script consumes the marker. A marker left after an interruption can remain in the temporary directory, but cannot trigger a review in another turn or session.

## Context recovery after compaction

1. On `SessionStart(source=compact)`, capture a fixed byte boundary in the current transcript and copy only complete, newline-terminated JSONL records within that boundary.
2. Inject the following prompt and the snapshot path through `additionalContext` before the next model request after compaction:

   > Context compaction has just completed. Now you should start with assessing and maintaining the completeness of the context information. First, carefully analyze and determine what key information is necessary for conducting current task, what contexts do you have right now, whether any key information has become uncertain or is missing after the compaction, and whether this could block further progress on the current task or introduce potential risks. If some key information fades away and needs to be recovered, try to search and retrieve it as needed from the code, project docs, Git history, and the `conversation history snapshot`.
   >
   > The `conversation history snapshot` is a fixed, read-only copy of the current conversation's latest JSONL log file. It may contain only recent history; earlier records may be stored in other log files. The `payload.history_base` field in the snapshot's first `session_meta` record identifies the source of earlier history and the cutoff for reading it. The source file may reference still earlier history in the same way. Follow these references as needed to retrieve earlier conversation information.
   >
   > After completing the assessment and any necessary retrieval, communicate the outcome to the user in a progress update before continuing the task. Explain whether the available context information is sufficient to proceed, the basis for that assessment, any information recovered, and any uncertainties that remain.
   >
   > If some key information remains uncertain after checking these sources, pause the task and ask the user for clarification. Resume the original task only once the information needed to proceed has been confirmed.
   >
   > Continue responding in the primary language of the current conversation.

   The prompt asks the model to analyze what information the current task needs, identify uncertain or missing information, retrieve it as needed, and communicate the outcome in a progress update before continuing. Responses should remain in the conversation's primary language.

After an idle manual `/compact`, the assessment prompt is delivered before the next normal model response, so continue the conversation to test it. Automatic compaction during a task can continue within that same turn. `Stop` runs when the agent attempts to end the turn.

Snapshots live in the system temporary directory, separated by user and session. Cleanup removes all snapshots for the session and preserves the original transcript. Ordinary startup, resume, clear, and fork events leave the snapshot directory untouched. If the application exits or the turn is interrupted before cleanup, snapshots may remain until a later Stop in the same session. There is no expiration policy or background cleanup process.

Both hooks retain the temporary directory name `simple-context-hook-<uid>` across the repository rename. This lets a running session find its existing snapshots and task markers.

## Deployment

1. Clone [codex-useful-hooks](https://github.com/dashidhy/codex-useful-hooks) into a stable local directory, or reuse the existing checkout. Keep it there while the hooks are installed.
2. Locate a Python 3.10+ interpreter and resolve the absolute paths to both scripts. Replace the placeholder commands in `hooks.example.json` with the interpreter and corresponding script paths. Quote paths correctly if they contain spaces. Prefer an absolute interpreter path because the desktop application's PATH may differ from the terminal's.
3. Merge the entries into Codex's user-level `hooks.json` (under its configured Codex home, `~/.codex` by default) for all projects, or project-level `.codex/hooks.json` for one project, according to the requested scope. Preserve unrelated configuration and hooks. If this hook is already installed, update its existing entries rather than adding duplicates.
4. Keep `SessionStart.matcher` set to `^compact$`. If upgrading from the compaction-only setup, replace its existing Stop command with `task_hook.py`, so there is a single Stop entry for this project. The example sets a 30-second timeout for `SessionStart`, 3 seconds for each task hook, and `additionalContextLimit: 1024` on both context-injecting events.

If the checkout moved when the repository was renamed, update the absolute script paths in all three installed commands. Review and trust the hooks in Codex's Hooks settings or with `/hooks` in the CLI. Codex skips untrusted hooks. Changes to commands or configuration may require renewed trust. If needed, open a new session or restart the client to load the configuration.

The settings label `User config / All projects` means the configuration comes from the user-level file and applies across projects. The example configures these entry points.

| Event | Display label | Command and purpose |
| --- | --- | --- |
| `SessionStart`, `matcher: "^compact$"` | Context recovery: Prepare history snapshot | `context_hook.py` snapshots history and injects the assessment prompt |
| `UserPromptSubmit` | Task check: Classify this turn | `task_hook.py` gives the main agent classification instructions |
| `Stop` | Task check: Review completion and clean up | `task_hook.py` requests one review for a marked task and cleans up on the final stop |

These labels are set through `statusMessage` and also appear while the script runs.

The configured commands run directly from this repository. Changes to the injected prompts take effect on the next invocation of the corresponding hook.

The hook uses the `compact` source of `SessionStart` because it can inject context before the next model request after compaction. `PostCompact` standard output does not provide the same context-injection behavior.

Official protocol: [Codex hooks](https://learn.chatgpt.com/docs/hooks).

## Testing

```sh
python3 -m unittest discover -s tests -v
```

The tests use temporary directories and synthetic events. They exercise snapshot boundaries, task markers, session-scoped cleanup, and the example configuration. They make no model calls, read no private conversations, and do not modify Codex configuration.

For a live task check, ask a factual question and then request a small, verifiable change. Check the actual conversation and tool calls. The factual answer should have no classification announcement or marking call. For the change, verify that the main agent gives a reason in a progress update, executes the supplied command, performs the requested change, and checks the result. At the first Stop it should receive the self-check once. If work remains, verify that the agent actually uses the relevant tools to finish or investigate it. A status label or promise to continue is insufficient evidence.

For a live recovery check, run `/compact` in a test conversation, then continue with an ordinary task. Observe how the model continues the task. If it identifies information that needs checking, verify that it actually uses file or Git tools to retrieve the relevant information before proceeding. A script status message, successful snapshot creation, or a readable file alone does not verify the model's recovery workflow. After the turn ends, confirm that the snapshot has been deleted. Automatic compaction in the main agent uses the same `source=compact` path.

## Limitations

- The hook assumes append-only JSONL logs. Records appended during copying are excluded from the snapshot; truncation detected during copying is reported as a failure.
- The snapshot contains only the current log block. Earlier history must be retrieved from the original logs by following `history_base` as needed. Logs may contain encrypted or otherwise unreadable fields; the hook does not parse or decrypt them.
- This setup covers compaction in the main agent. In the current Codex implementation, subagent compaction does not trigger `SessionStart(source=compact)`, so it does not run this recovery hook.
- The prompt is a context-recovery reminder. It cannot guarantee that the model will notice every missing detail.
- The task review relies on the main agent classifying the request and successfully running the supplied command. If another Stop hook forces continuation after ordinary cleanup, the previous snapshots are no longer available.
- If snapshot creation fails, the hook reports the failure and allows the task to continue without forcing a recovery loop.

## Maintenance

Keep the README short. Include an introduction, how the hooks work, and deployment by asking Codex. Keep detailed setup, behavior, verification, and limitations in this file. The compaction prompt lives in `context_hook.py`. Keep the quoted prompt above synchronized when it changes. The classification and review prompts live in `task_hook.py`.
