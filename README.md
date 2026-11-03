# codex-useful-hooks

Local hooks for Codex, built with Python 3.10+ and its standard library. Install either group independently or use both.

| Hook group | What it does |
| --- | --- |
| [Context recovery after compaction](compaction/DEPLOY.md) | Saves a conversation snapshot and asks Codex to recover missing task details before continuing. |
| [Task completion checks](task-completion/DEPLOY.md) | Asks Codex to mark requests for concrete work, check what it delivered, and continue unfinished work. Ordinary questions receive a direct answer. |

To deploy, give Codex [the repository link](https://github.com/dashidhy/codex-useful-hooks), name the group or groups you want, and specify one project or all projects. For example, “Install the compaction group from this repository for all my projects.” Review the installed commands under `/hooks` in the CLI or in Codex's Hooks settings. See the [agent guide](AGENTS.md#deployment) for setup.
