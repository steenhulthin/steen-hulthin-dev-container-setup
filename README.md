# Steen Hulthin's Dev Workspaces

A Podman image with an Ubuntu environment for working with coding agents, and a script that starts named, persistent workspaces from it. The agents run inside the container, so they can't touch the rest of your machine unless you mount something into the workspace.

## What's in the image

- Ubuntu 26.04, Python 3, Git, GitHub CLI, Node.js 24, tmux (with resurrect and continuum)
- Agent harnesses: Claude Code, Codex, Mistral Vibe, pi
- Skill sets you choose per workspace: Matt Pocock's skills, PStack, Superpowers, Addy Osmani's agent-skills, and OpenSpec
- Non-root user `dev` with passwordless `sudo`

Nothing is logged in. Each workspace keeps its own logins.

## Prerequisites

- Rootless Podman
- Ollama running on the host (optional, for local models), set up as described in [Ollama on the host](#ollama-on-the-host)

## Build the image

```bash
podman build -t localhost/dev-workspace:latest -f Containerfile .
```

Rebuild with `--pull` to take a fresh Ubuntu base and apply upgrades:

```bash
podman build --pull --no-cache -t localhost/dev-workspace:latest -f Containerfile .
```

Build-time upgrades are the only package updates the image gets. Between rebuilds, you can update a workspace yourself with `sudo apt-get update && sudo apt-get upgrade`.

## Start a workspace

Put `bin/` on your `PATH`, or call `bin/workspace` directly.

```bash
bin/workspace myproject
```

This creates the container `ws-myproject` and the volume `ws-myproject`, then opens a tmux session named `main` in it. Running the same command later attaches to the same workspace and the same tmux session.

Every workspace has a project folder on the host, mounted in the workspace's home. Creating a workspace asks what to call it there (default `project`, so `/home/dev/project`); set `WORKSPACE_FOLDER` to skip the question. By default it is `~/workspaces/<name>`, created for you; set `WORKSPACE_ROOT` to use another parent folder. To use an existing folder instead:

```bash
bin/workspace myproject --mount ~/src/myproject
```

Creating a workspace prints the project folder's host path. Open it in your file manager or editor like any other folder; files you create there are owned by you.

On WSL, run Podman and `bin/workspace` inside the WSL distro. The script also prints the Windows path of the folder, of the form `\\wsl.localhost\<distro>\home\...`, which you can open in Explorer. Keep the folder on the Linux filesystem; don't put it under `/mnt/c`, where permissions and speed suffer.

`workspace rm` and `workspace purge` never delete the project folder. Only the home volume is removed by `purge`.

Mounts are set when the workspace is created. To change them, remove the workspace and create it again. Only mount what the agents need.

## Skill sets

When you create a workspace, it asks which skill sets to install: Matt Pocock's skills, PStack, Superpowers, Addy Osmani's agent-skills, and OpenSpec. Answer with numbers, e.g. `1,3`, or leave it empty for none. To skip the question, set `WORKSPACE_SKILLS`:

```bash
WORKSPACE_SKILLS=mattpocock,openspec bin/workspace myproject
```

The ids are `mattpocock`, `pstack`, `superpowers`, `addyosmani`, and `openspec`. The choice is fixed when the workspace is created; to change it, `workspace rm` and create it again. If two chosen sets have a skill with the same name, the first one wins and a warning is printed at start.

OpenSpec is a CLI, not a folder of skills. It is installed into the workspace's home folder at first start, which needs network access. Run `openspec init` in a project to generate its skills.

## Shells and sessions

Each `bin/workspace myproject` is a tmux client of the session `main`, created on first connect in the project folder. Shells and running processes live in the tmux server inside the container, so they survive you detaching or closing the terminal.

- **Detach:** `Ctrl-b d`. The session keeps running in the background.
- **Re-attach:** run `bin/workspace myproject` again, from any terminal.
- **Several terminals at once:** every invocation is another client of the same session, and all clients show the same screen. For more shells, use tmux's windows and panes: `Ctrl-b c` for a new window, `Ctrl-b %` to split.

Sessions survive closing the terminal, but not stopping the container. `workspace rm`, `workspace purge`, and a host reboot kill every shell and process in the workspace. The volume keeps your files and logins; it doesn't keep running processes.

tmux-resurrect and tmux-continuum are installed. Continuum saves the layout (sessions, windows, panes, working directories) every 15 minutes into the volume, and restores it the next time tmux starts in the workspace. Programs that were running are not restarted. Save by hand with `Ctrl-b Ctrl-s`, restore with `Ctrl-b Ctrl-r`.

## Log in to the harnesses

Log in once per workspace. The credentials are saved in the workspace's volume.

- **Claude Code:** run `claude` and follow the login prompts.
- **Codex:** run `codex login`.
- **Mistral Vibe:** run `vibe` and follow its setup.
- **pi:** run `pi`, then `/login` and pick a provider. Claude, ChatGPT, and Mistral are all options; which ones work with a subscription, and which need an API key, depends on each provider.
- **GitHub:** run `gh auth login`.

## Persistence

Each workspace's home folder is a named volume, so files, shell history, and logins survive restarts and rebuilds. tmux sessions stop with the container, but their layout is restored (see above).

```bash
bin/workspace rm myproject       # remove the container, keep the volume
bin/workspace myproject          # attach later, with files and logins as they were
bin/workspace purge myproject    # remove the container and the volume
```

`purge` deletes everything in the workspace. There is no undo.

A rebuilt image doesn't change an existing workspace's home folder, because the volume already has content. To start a workspace from the new image, keep the work you need, then run `workspace purge` and create the workspace again.

## Ollama on the host

The workspace reaches Ollama at `http://host.containers.internal:11434/v1`. Two things on the host have to be set up for that to work, and both are one-time changes made with `sudo`.

1. **Make Ollama listen on the host's LAN address.** Containers reach the host through its LAN address, not through loopback, so Ollama must listen there. Set it with a systemd override:

   ```bash
   sudo systemctl edit ollama
   ```

   Add:

   ```ini
   [Service]
   Environment="OLLAMA_HOST=XXX.XXX.XXX.XXX:11434"
   ```

   Then `sudo systemctl restart ollama`.

2. **Block port 11434 on the LAN interface.** Ollama is now reachable from the network, so the firewall has to stop it. Allow traffic on the loopback interface, drop it on the LAN interface. Check the rule's order and interface names on your machine before applying it.

Then check both sides:

- From a workspace, `curl http://host.containers.internal:11434/api/version` returns a version.
- From another device on your network, `curl http://XXX.XXX.XXX.XXX:11434/api/version` fails.

If the first check fails, the firewall rule is blocking the containers too. If the second check succeeds, the rule isn't in effect.

Once Ollama answers, pull a model on the host and add it to pi's `models.json` in the workspace (`~/.pi/agent/models.json`), under `providers.ollama.models`.

## Trust

The image installs the agent harnesses with their vendors' installers, and the skills come from GitHub at build time. Rebuilding pulls whatever those sources serve at that point.
