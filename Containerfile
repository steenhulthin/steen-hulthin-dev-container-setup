FROM docker.io/library/ubuntu:26.04

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8

# System packages and Node.js 24 (pi needs 22.19 or newer).
# Upgrades run here, at build time, so workspaces start from the same packages.
RUN apt-get update \
 && apt-get -y upgrade \
 && apt-get install -y --no-install-recommends \
      ca-certificates curl git gh sudo jq less procps openssh-client vim-tiny \
      python3 python3-pip python3-venv \
 && curl -fsSL https://deb.nodesource.com/setup_24.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && rm -rf /var/lib/apt/lists/*

# Non-root user with passwordless sudo. Podman runs rootless, so root in the
# container still has no more access to the host than this user does.
RUN userdel -r ubuntu 2>/dev/null || true \
 && useradd -m -u 1000 -s /bin/bash dev \
 && echo 'dev ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/dev \
 && chmod 0440 /etc/sudoers.d/dev

# Skills, copied in at build time. Each SKILL.md's folder is linked into the
# harnesses' skill folders by init-workspace at every start.
RUN mkdir -p /opt/skills \
 && git clone --depth 1 https://github.com/mattpocock/skills /opt/skills/mattpocock \
 && git clone --depth 1 https://github.com/cursor/plugins /opt/skills/cursor-plugins \
 && mv /opt/skills/cursor-plugins/pstack /opt/skills/pstack \
 && rm -rf /opt/skills/cursor-plugins /opt/skills/*/.git \
 && for s in tdd teach; do \
      mv /opt/skills/pstack/skills/$s /opt/skills/pstack/skills/pstack-$s \
      && sed -i "s/^name: $s\$/name: pstack-$s/" /opt/skills/pstack/skills/pstack-$s/SKILL.md; \
    done \
 && test -z "$(find /opt/skills -name SKILL.md -printf '%h\n' | xargs -n1 basename | sort | uniq -d)" \
 && chmod -R a+rX /opt/skills

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
