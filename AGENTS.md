# Agent guide

## Deployment

1. Find the groups the user requested in the [README](README.md) or by locating group `DEPLOY.md` files. Read each selected group's guide and configuration example for its requirements, handlers, and upgrade instructions.
2. Reuse a persistent checkout of [codex-useful-hooks](https://github.com/dashidhy/codex-useful-hooks), or clone it into a stable local directory. For all projects, use `hooks.json` in the configured Codex home (normally `~/.codex/hooks.json`). For one project, use its `.codex/hooks.json`.
3. Check the selected handlers against each other and the effective handlers for the target project(s), including registrations inherited from other configuration layers. Sharing an event is supported. Check whether one handler changes or removes data another needs, or whether their decisions conflict for the same input. If you find a conflict, explain the specific effects before changing the affected registrations.
4. Merge handlers individually using each selected group's guide. Update existing registrations for the same handler in place, including older command paths, and remove exact duplicates within the same event, matcher, and scope. Preserve unrelated handlers and settings. Use absolute paths for local commands and quote them as needed for the shell.
5. Validate the resulting JSON. Check that each selected handler appears once with the expected matcher, command, and settings, and that unrelated entries are intact. Have the user review and trust updated hooks under `/hooks` in the CLI or in Codex's Hooks settings. Reload the client if needed and follow each selected group's verification steps.

Keep the README catalog short. Document each group's setup, behavior, verification, and limitations in its own `DEPLOY.md`.
