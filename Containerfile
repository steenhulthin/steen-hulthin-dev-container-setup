FROM docker.io/library/ubuntu:26.04

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8

# System packages and Node.js 24 (pi needs 22.19 or newer).
# Upgrades run here, at build time, so workspaces start from the same packages.
RUN apt-get update \
 && apt-get -y upgrade \
 && apt-get install -y --no-install-recommends \
      ca-certificates curl git gh sudo jq less procps openssh-client nano vim-tiny \
      python3 python3-pip python3-venv tmux \
 && curl -fsSL https://deb.nodesource.com/setup_24.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && rm -rf /var/lib/apt/lists/*

# Non-root user with passwordless sudo. Podman runs rootless, so root in the
# container still has no more access to the host than this user does.
RUN userdel -r ubuntu 2>/dev/null || true \
 && useradd -m -u 1000 -s /bin/bash dev \
 && echo 'dev ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/dev \
 && chmod 0440 /etc/sudoers.d/dev

# Git aliases for every user in the image.
RUN git config --system alias.st status \
 && git config --system alias.ci commit \
 && git config --system alias.co checkout

# Skill sets, copied in at build time, one folder per set under /opt/skills.
# The user picks which sets a workspace gets when creating it (SKILL_SETS);
# init-workspace links the chosen sets' skill folders into the harnesses' skill
# folders at every start.
RUN mkdir -p /opt/skills \
 && git clone --depth 1 https://github.com/mattpocock/skills /opt/skills/mattpocock \
 && git clone --depth 1 https://github.com/cursor/plugins /opt/skills/cursor-plugins \
 && mv /opt/skills/cursor-plugins/pstack /opt/skills/pstack \
 && rm -rf /opt/skills/cursor-plugins \
 && git clone --depth 1 --branch v7.0.2 https://github.com/obra/superpowers /opt/skills/superpowers \
 && git clone --depth 1 --branch 0.6.15 https://github.com/addyosmani/agent-skills /opt/skills/addyosmani \
 && rm -rf /opt/skills/*/.git \
 && for s in tdd teach; do \
      mv /opt/skills/pstack/skills/$s /opt/skills/pstack/skills/pstack-$s \
      && sed -i "s/^name: $s\$/name: pstack-$s/" /opt/skills/pstack/skills/pstack-$s/SKILL.md; \
    done \
 && for set in /opt/skills/*; do \
      test -z "$(find "$set" -name SKILL.md -printf '%h\n' | xargs -n1 basename | sort | uniq -d)" || exit 1; \
    done \
 && chmod -R a+rX /opt/skills

# tmux plugins, pinned to their latest tagged releases, copied in at build time and loaded by the system-wide tmux.conf.
# Saved sessions go to the user's home, so they live in the workspace volume.
RUN git clone --depth 1 --branch v4.0.0 https://github.com/tmux-plugins/tmux-resurrect /opt/tmux-plugins/tmux-resurrect \
 && git clone --depth 1 --branch v3.1.0 https://github.com/tmux-plugins/tmux-continuum /opt/tmux-plugins/tmux-continuum \
 && rm -rf /opt/tmux-plugins/*/.git \
 && chmod -R a+rX /opt/tmux-plugins
COPY image/tmux.conf /etc/tmux.conf

COPY image/init-workspace.sh /usr/local/bin/init-workspace
RUN chmod 0755 /usr/local/bin/init-workspace

# Agent harnesses, installed per user. Each installer is the vendor's documented one.
USER dev
WORKDIR /home/dev
ENV PATH=/home/dev/.local/bin:$PATH

RUN curl -fsSL https://claude.ai/install.sh | bash \
 && curl -fsSL https://chatgpt.com/codex/install.sh | sh \
 && curl -LsSf https://mistral.ai/vibe/install.sh | bash \
 && curl -fsSL https://pi.dev/install.sh | sh

ENTRYPOINT ["/usr/local/bin/init-workspace"]
CMD ["sleep", "infinity"]
