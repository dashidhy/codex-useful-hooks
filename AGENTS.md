# Deploying hook groups

Keep one top-level directory per hook group. The only root files are `.gitignore`, the [README catalog](README.md), and this guide.

Each group is independently deployable. Its directory contains its scripts, prompts (embedded or separate), configuration example, `DEPLOY.md`, and tests. For each group the user selects, follow its `DEPLOY.md` to install and verify it using that directory alone.

When deploying multiple groups, check the selected handlers together and against existing hooks in the target scope. Sharing an event is fine. Look for incompatible decisions or a handler changing data another needs. Resolve concrete conflicts before installing, and preserve unrelated registrations.
