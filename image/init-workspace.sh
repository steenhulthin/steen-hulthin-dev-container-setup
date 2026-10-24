#!/usr/bin/env bash
# Runs at every workspace start, as the dev user, before the workspace's command.
set -euo pipefail

# Link every skill folder from the image into each harness's skill folder.
for target in "$HOME/.claude/skills" "$HOME/.agents/skills"; do
  mkdir -p "$target"
  find /opt/skills -name SKILL.md -printf '%h\n' | while read -r dir; do
    ln -sfn "$dir" "$target/$(basename "$dir")"
  done
done

# Point pi at Ollama. Written only when missing, so edits you make survive restarts.
pi_models="$HOME/.pi/agent/models.json"
if [ ! -f "$pi_models" ]; then
  mkdir -p "$(dirname "$pi_models")"
  jq -n --arg url "${OLLAMA_BASE_URL:-http://host.containers.internal:11434/v1}" \
    '{providers: {ollama: {baseUrl: $url, api: "openai-completions", apiKey: "ollama", models: []}}}' \
    > "$pi_models"
fi

exec "$@"
