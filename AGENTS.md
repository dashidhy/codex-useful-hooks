# Agent guide

This repository contains a Codex hook for context check and recovery after compaction. Use this guide when deploying, verifying, or modifying it.

## Requirements

- Python 3.10+; standard library only, with no dependencies to install or build step.
- A Codex client supporting the hook events and fields in `hooks.example.json`.
- A persistent local checkout: the installed commands execute `context_hook.py` directly from that checkout.

The script makes no model calls and adds no memory database or search tools. Codex retrieves information with its existing file and Git tools.

## How it works

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

3. On `Stop`, delete the current session's snapshots. Cleanup does not request another model turn, block stopping, or delete the original transcript.

After an idle manual `/compact`, the assessment prompt is delivered before the next normal model response, so continue the conversation to test it. Automatic compaction during a task can continue within that same turn. `Stop` runs when the complete agent turn finishes, not after each progress message or tool call.

Snapshots live in the system temporary directory, separated by user and session, rather than in the working repository. If a turn compacts multiple times, cleanup removes all snapshots for that session.

Ordinary startup, resume, clear, and fork events, along with all other unhandled events, do nothing: they do not create snapshots, traverse directories, or delete files. Interruptions and application exits are not handled. If `Stop` does not run, snapshots may remain until a later `Stop` in the same session. There is no expiration policy or background cleanup process.

## Deployment

1. Clone the repository into a stable local directory, or reuse the existing checkout. Keep it there while the hook is installed.
2. Locate a Python 3.10+ interpreter and resolve the absolute path to `context_hook.py`. Replace the placeholder command in both entries of `hooks.example.json` with these paths. Quote paths correctly if they contain spaces. Prefer an absolute interpreter path because the desktop application's PATH may differ from the terminal's.
3. Merge the entries into Codex's user-level `hooks.json` (under its configured Codex home, `~/.codex` by default) for all projects, or project-level `.codex/hooks.json` for one project, according to the requested scope. Preserve unrelated configuration and hooks. If this hook is already installed, update its existing entries rather than adding duplicates.
4. Keep `SessionStart.matcher` set to `^compact$` and retain the `Stop` cleanup entry. The example uses timeouts of 30 seconds and 3 seconds respectively, with `additionalContextLimit: 1024` on `SessionStart`.

Review and trust the new hooks in Codex's Hooks settings or with `/hooks` in the CLI. **Saving the configuration does not grant trust**; untrusted hooks are skipped. Changes to commands or configuration may require renewed trust. If needed, open a new session or restart the client to load the configuration.

The settings label `User config / All projects` means the configuration comes from the user-level file and applies across projects. The same script has two configured entry points:

| Event | Display label | Purpose |
| --- | --- | --- |
| `SessionStart`, `matcher: "^compact$"` | Context recovery: Prepare history snapshot | Create a snapshot and inject the assessment prompt after compaction |
| `Stop` | Context recovery: Clean up snapshots at turn end | Clean up when the model finishes its turn |

These labels are set through `statusMessage` and also appear while the script runs.

The configured command runs `context_hook.py` directly from this repository. No build or reinstallation is needed. Changes to `PROMPT` take effect on the next hook invocation.

The hook uses the `compact` source of `SessionStart` because it can inject context before the next model request after compaction. `PostCompact` standard output does not provide the same context-injection behavior.

Official protocol: [Codex hooks](https://learn.chatgpt.com/docs/hooks).

## Testing

```sh
python3 -m unittest discover -s tests -v
```

The tests use temporary directories and synthetic JSONL. They cover the fixed byte boundary, session-scoped cleanup, ignored events and sources, and the example configuration. They make no model calls, read no private conversations, and do not modify Codex configuration.

For an initial live check, use a test conversation: run `/compact`, then continue with an ordinary task. Observe how the model continues the task. If it identifies information that needs checking, verify that it actually uses file or Git tools to retrieve the relevant information before proceeding. A script status message, successful snapshot creation, or a readable file alone does not verify the model's recovery workflow. After the turn ends, confirm that the snapshot has been deleted. Automatic compaction in the main agent uses the same `source=compact` path.

## Limitations

- The hook assumes append-only JSONL logs. Records appended during copying are excluded from the snapshot; truncation detected during copying is reported as a failure.
- The snapshot contains only the current log block. Earlier history must be retrieved from the original logs by following `history_base` as needed. Logs may contain encrypted or otherwise unreadable fields; the hook does not parse or decrypt them.
- This setup covers compaction in the main agent. In the current Codex implementation, subagent compaction does not trigger `SessionStart(source=compact)`, so it does not run this recovery hook.
- The prompt is a context-recovery reminder. It cannot guarantee that the model will notice every missing detail.
- Snapshots are deleted when `Stop` runs. If another Stop hook forces the model to continue working, the previous snapshots are no longer available.
- If snapshot creation fails, the hook reports the failure and allows the task to continue without forcing a recovery loop.

## Maintenance

Keep the README short: introduction, principle, and deployment by asking Codex. Keep detailed setup, behavior, verification, and limitations in this file. The injected prompt lives in `context_hook.py`; keep the quoted prompt above synchronized when it changes.
