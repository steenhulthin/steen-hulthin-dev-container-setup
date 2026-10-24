# Dev workspaces

A Podman image with an Ubuntu environment for working with coding agents, and a script that starts named, persistent workspaces from it. The agents run inside the container, so they can't touch the rest of your machine unless you mount something into the workspace.

## What's in the image

- Ubuntu 26.04, Python 3, Git, GitHub CLI, Node.js 24
- Agent harnesses: Claude Code, Codex, Mistral Vibe, pi
- Skills: the Matt Pocock skills and PStack, both linked into the harnesses at start
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

This creates the container `ws-myproject` and the volume `ws-myproject`, then opens a shell in it. Running the same command later re-attaches to the same workspace.

To mount a host folder into the workspace at `/home/dev/project`:

```bash
bin/workspace myproject --mount ~/src/myproject
```

Mounts are set when the workspace is created. To change them, remove the workspace and create it again. Only mount what the agents need.

## Log in to the harnesses

Log in once per workspace. The credentials are saved in the workspace's volume.

- **Claude Code:** run `claude` and follow the login prompts.
- **Codex:** run `codex login`.
- **Mistral Vibe:** run `vibe` and follow its setup.
- **pi:** run `pi`, then `/login` and pick a provider. Claude, ChatGPT, and Mistral are all options; which ones work with a subscription, and which need an API key, depends on each provider.
- **GitHub:** run `gh auth login`.

## Persistence

Each workspace's home folder is a named volume, so files, shell history, and logins survive restarts and rebuilds.

```bash
bin/workspace rm myproject       # remove the container, keep the volume
bin/workspace myproject          # re-attach later, with everything as it was
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
