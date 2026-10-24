# Glossary

**Environment**: the image built from the Containerfile. It holds the tools, harnesses, and skills, and nothing about any particular project or login.

**Workspace**: a named container created from an environment, with its own persistent home folder. Working in a workspace means running agents inside it.

**Harness**: an agent CLI installed in the environment, such as Claude Code, Codex, Mistral Vibe, or pi.

**Skill**: a folder with a `SKILL.md` file that a harness loads. Skills come from the environment, not from the workspace.

**Mount**: a host folder made visible inside a workspace. Workspaces have none by default.
