# codex-useful-hooks

Each hook group can be copied and installed on its own. Open its guide for setup and verification.

| Hook group | What it does |
| --- | --- |
| [Context recovery after compaction](compaction/DEPLOY.md) | Saves a conversation snapshot and asks Codex to recover missing task details before continuing. |
| [Task completion checks](task-completion/DEPLOY.md) | Asks Codex to mark requests for concrete work, check what it delivered, and continue unfinished work. Ordinary questions receive a direct answer. |

To have Codex install hooks, give it [the repository link](https://github.com/dashidhy/codex-useful-hooks) or a local group folder. Name the group and scope, for example, “Install the compaction group for all my projects.”
