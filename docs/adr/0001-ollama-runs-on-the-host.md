# 0001: Ollama runs on the host, not in the environment

## Status

Accepted.

## Context

Workspaces need to run local models through Ollama. Two places could run it: the host, or the environment image.

- The host already has Ollama installed and the models downloaded.
- Running Ollama in the image would need GPU passthrough into rootless containers, which is extra setup on every machine that uses the image.
- Containers reach the host through `host.containers.internal`, which forwards to the host's LAN address, not loopback. So Ollama has to listen on a non-loopback address, which makes it reachable from the network. The firewall has to restrict it.

## Decision

Ollama stays on the host. Workspaces reach it at `host.containers.internal`. The host restricts port 11434 to loopback, so only the container path reaches it.

## Consequences

- Setup has two host-side steps (the listen address and the firewall rule). They're documented in the README, and they're not automated.
- Models are shared by everything on the host that uses Ollama, not kept per workspace.
- If the firewall step isn't applied, Ollama is reachable from the network. The README includes a check for this.
- If GPU passthrough becomes easy to set up, moving Ollama into the environment would remove the exposure. That would be a new decision.
