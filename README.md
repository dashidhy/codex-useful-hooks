# codex-useful-hooks

Local hooks for Codex. Both run with Python 3.10+ and its standard library.

## Hooks

| Hook | When it runs | What it does |
| --- | --- | --- |
| [Context recovery](context_hook.py) | After compaction | Saves a conversation snapshot. Prompts Codex to recover missing task details from the snapshot, code, project docs, or Git history before continuing. |
| [Task completion check](task_hook.py) | On each request and when Codex tries to finish | Prompts Codex to identify and mark requests for concrete work. On the first stop for a marked turn, Codex checks what it delivered and continues any work it can still complete. Ordinary questions receive a direct answer. |

## Deployment

Give Codex [the repository link](https://github.com/dashidhy/codex-useful-hooks) and ask it to install the hooks for one project or all your projects. Review the installed commands under `/hooks` in the CLI or in Codex’s Hooks settings. See [the agent guide](AGENTS.md#deployment) for the setup steps.
