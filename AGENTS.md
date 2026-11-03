# Agent guide

Each hook group has a deployment guide and a standalone `hooks.example.json`. Read the guide for each group the user wants installed.

| Group | Deployment guide |
| --- | --- |
| Context recovery after compaction | [compaction/DEPLOY.md](compaction/DEPLOY.md) |
| Task completion checks | [task-completion/DEPLOY.md](task-completion/DEPLOY.md) |

## Deployment

1. Reuse one persistent checkout of [codex-useful-hooks](https://github.com/dashidhy/codex-useful-hooks), or clone it into a stable local directory. The installed commands execute scripts directly from this checkout. Keep the group directories and their common `shared/` directory in place.
2. Select the requested scope. For all projects, use `hooks.json` in the configured Codex home (normally `~/.codex/hooks.json`). For a single project, use its `.codex/hooks.json`. Inspect the existing configuration for groups already installed, including commands pointing to older checkout locations or the former repository-root scripts.
3. Use the relevant group examples and their merge instructions to determine the entries needed after installation. Merge individual handlers by event and matcher, preserving other hooks and settings. Update an existing handler in place, including any old script path, and remove duplicate registrations for this collection. When groups share an event, apply the coexistence rules in their deployment guides.
4. In each installed `command`, use absolute paths to a Python 3.10+ interpreter and to the corresponding script inside the retained checkout. Quote each path as needed for the shell, including when a directory contains spaces. Codex's desktop environment may have a different `PATH` from the terminal. Both groups use the Python standard library.
5. Check the resulting JSON, event matchers, handler counts, and resolved script paths against the group guides. Review and trust the updated hooks under `/hooks` in the CLI or in Codex's Hooks settings. Codex skips untrusted hooks, and an edited command or configuration may require renewed trust. Open a new session or restart the client if needed to load changes. The settings label `User config / All projects` identifies user-level configuration. Each handler's `statusMessage` identifies it while running.

## Verification and maintenance

Use a Codex client that supports the events and fields in the selected example. Follow each installed group's live verification steps. The [Codex hooks documentation](https://learn.chatgpt.com/docs/hooks) describes the protocol.

From the checkout root, run `python3 -m unittest discover -s tests -v`. The suite uses synthetic events and temporary files to exercise the handlers and example configuration. It runs locally without model calls, access to private conversations, or changes to Codex configuration.

Keep the README short and link to each group's guide. Keep setup, prompt details, verification, and limitations for each group in its `DEPLOY.md`. Edits to the scripts in the retained checkout take effect on their next invocation.
