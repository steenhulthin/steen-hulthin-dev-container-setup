#!/usr/bin/env bash
# Runs at every workspace start, as the dev user, before the workspace's command.
set -euo pipefail

# Link the skill folders of the chosen sets (SKILL_SETS, comma-separated) into
# each harness's skill folder. Links from earlier starts are removed first, so
# the folders always match the current choice.
for target in "$HOME/.claude/skills" "$HOME/.agents/skills"; do
  mkdir -p "$target"
  find "$target" -maxdepth 1 -type l -lname '/opt/skills/*' -delete
  for set in $(echo "${SKILL_SETS:-}" | tr ',' ' '); do
    [ -d "/opt/skills/$set" ] || { echo "init-workspace: unknown skill set '$set'" >&2; continue; }
    find "/opt/skills/$set" -name SKILL.md -printf '%h\n' | while read -r dir; do
      link="$target/$(basename "$dir")"
      if [ -e "$link" ]; then
        echo "init-workspace: skill '$(basename "$dir")' from '$set' skipped; the name is already taken" >&2
      else
        ln -s "$dir" "$link"
      fi
    done
  done
done

# OpenSpec is a CLI that writes skills into each project (openspec init), so it is
# installed into the home folder when chosen rather than linked.
if echo ",${SKILL_SETS:-}," | grep -q ',openspec,' && ! command -v openspec >/dev/null; then
  npm install -g --prefix "$HOME/.local" @fission-ai/openspec@1.16.0 >/dev/null \
    || echo "init-workspace: could not install openspec; it will retry at the next start" >&2
fi

# Point pi at Ollama. Written only when missing, so edits you make survive restarts.
pi_models="$HOME/.pi/agent/models.json"
if [ ! -f "$pi_models" ]; then
  mkdir -p "$(dirname "$pi_models")"
  jq -n --arg url "${OLLAMA_BASE_URL:-http://host.containers.internal:11434/v1}" \
    '{providers: {ollama: {baseUrl: $url, api: "openai-completions", apiKey: "ollama", models: []}}}' \
    > "$pi_models"
fi

# Set the git identity given at creation. Only when unset, so later edits survive restarts.
if [ -n "${GIT_USER_NAME:-}" ] && ! git config --global user.name >/dev/null; then
  git config --global user.name "$GIT_USER_NAME"
fi
if [ -n "${GIT_USER_EMAIL:-}" ] && ! git config --global user.email >/dev/null; then
  git config --global user.email "$GIT_USER_EMAIL"
fi

exec "$@"
