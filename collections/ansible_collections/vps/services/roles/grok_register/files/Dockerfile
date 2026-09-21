FROM docker.io/library/debian:trixie-slim@sha256:9bb8a3626890e084ab54e888fdd7c4b6d2f119071cd4c5dc5fecb4d73062aa5f

ARG GROK_REGISTER_SOURCE_REVISION
LABEL org.opencontainers.image.source="https://github.com/AaronL725/grok-register"
LABEL org.opencontainers.image.revision="${GROK_REGISTER_SOURCE_REVISION}"
LABEL org.opencontainers.image.base.name="docker.io/library/debian:trixie-slim@sha256:9bb8a3626890e084ab54e888fdd7c4b6d2f119071cd4c5dc5fecb4d73062aa5f"

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH="/opt/grok-register-venv/bin:${PATH}" \
    DISPLAY=:99

RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        ca-certificates \
        chromium \
        fonts-liberation \
        fonts-noto-cjk \
        python3 \
        python3-tk \
        python3-venv \
        xvfb \
        x11vnc \
        novnc \
        websockify \
        procps \
    && python3 -m venv /opt/grok-register-venv \
    && mv /usr/bin/chromium /usr/bin/chromium-real \
    && echo '#!/bin/sh\nexec /usr/bin/chromium-real --no-sandbox "$@"' > /usr/bin/chromium \
    && chmod +x /usr/bin/chromium \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/grok-register

COPY source/requirements.txt /tmp/requirements.txt
COPY constraints.txt /tmp/constraints.txt
RUN python -m pip install --constraint /tmp/constraints.txt -r /tmp/requirements.txt \
    && rm -f /tmp/requirements.txt

COPY source/ /opt/grok-register/
COPY entrypoint.sh /usr/local/bin/grok-register-entrypoint
RUN chmod 0755 /usr/local/bin/grok-register-entrypoint

ENTRYPOINT ["/usr/local/bin/grok-register-entrypoint"]
CMD ["sleep", "infinity"]
