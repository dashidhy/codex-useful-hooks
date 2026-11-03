# Context recovery after compaction

This group gives Codex a fixed copy of the current conversation log to consult when compaction leaves a task detail uncertain.

## Install

Follow the [repository deployment steps](../AGENTS.md#deployment) using [this group's example](hooks.example.json). Use absolute paths to a Python 3.10+ interpreter and to [context_hook.py](context_hook.py) in the retained checkout for both commands. The script uses the Python standard library.

| Event | Configuration | Purpose |
| --- | --- | --- |
| `SessionStart` | Matcher `^compact$`, 30-second timeout, `additionalContextLimit: 1024` | Create the snapshot and inject the recovery prompt before the next model request. |
| `Stop` | 3-second timeout | Delete this session's snapshots on `Stop`. |

For upgrades from the flat layout, update existing repository-root `context_hook.py` commands to `compaction/context_hook.py`.

## Recovery prompt

At `SessionStart(source=compact)`, the script captures the current byte length of the transcript, then copies the complete, newline-terminated JSONL records within that boundary. It provides the snapshot path and the following prompt through `additionalContext`. This event supports context injection before the next model request after compaction. `PostCompact` standard output does not provide the same behavior.

> Context compaction has just completed. Now you should start with assessing and maintaining the completeness of the context information. First, carefully analyze and determine what key information is necessary for conducting current task, what contexts do you have right now, whether any key information has become uncertain or is missing after the compaction, and whether this could block further progress on the current task or introduce potential risks. If some key information fades away and needs to be recovered, try to search and retrieve it as needed from the code, project docs, Git history, and the `conversation history snapshot`.
>
> The `conversation history snapshot` is a fixed, read-only copy of the current conversation's latest JSONL log file. It may contain only recent history; earlier records may be stored in other log files. The `payload.history_base` field in the snapshot's first `session_meta` record identifies the source of earlier history and the cutoff for reading it. The source file may reference still earlier history in the same way. Follow these references as needed to retrieve earlier conversation information.
>
> After completing the assessment and any necessary retrieval, communicate the outcome to the user in a progress update before continuing the task. Explain whether the available context information is sufficient to proceed, the basis for that assessment, any information recovered, and any uncertainties that remain.
>
> If some key information remains uncertain after checking these sources, pause the task and ask the user for clarification. Resume the original task only once the information needed to proceed has been confirmed.
>
> Continue responding in the primary language of the current conversation.

After an idle manual `/compact`, the prompt takes effect when the conversation continues. Automatic compaction during work can deliver the prompt within the same turn. Startup, resume, clear, and fork leave the snapshot directory untouched.

## Snapshot lifetime and limitations

- The snapshot covers the current log block. The first `session_meta` record's `payload.history_base` can identify an earlier source and cutoff. Follow the chain as needed. The hook does not parse or decrypt unreadable log fields.
- Copying assumes an append-only transcript. Later appends are excluded. If the script detects truncation or cannot create a snapshot, it reports the failure and allows the task to continue.
- Snapshots live in the system temporary directory under `simple-context-hook-<uid>`, separated by session. The directory name is retained from earlier releases so existing sessions can find their files. Cleanup removes this session's snapshots and preserves the original transcript.
- Interruption or application exit can leave snapshots until a later stop in the same session. There is no background expiration.
- In the current implementation, only main-agent compaction triggers this event. The prompt asks the model to identify and recover missing details, and the model can still overlook a gap.

## Verify

From the checkout root, run `python3 -m unittest discover -s tests -p test_context_hook.py -v`. The tests exercise snapshot boundaries, truncation, and session-scoped cleanup using synthetic conversations and temporary directories.

For a live check, run `/compact` in a test conversation and send a follow-up that depends on an earlier detail. Inspect the model's progress update and any file or Git calls. If the model identifies a gap, verify that it retrieves the relevant evidence before proceeding. A hook status message or an existing snapshot only establishes that the script ran. After the first `Stop`, confirm that the snapshot path is gone.

When editing `PROMPT` in [context_hook.py](context_hook.py), keep the quotation above synchronized.
