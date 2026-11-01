FROM node:22-slim

ARG RSRS_CLI_VERSION=1.0.19

# Install ca-certificates and curl for health check and upstream secure calls
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g rsrs-cli@${RSRS_CLI_VERSION} \
    && rsrs --version

WORKDIR /data
VOLUME ["/data"]

ENV HOME=/data \
    RSRS_DATA_DIR=/data

ENTRYPOINT ["rsrs"]
CMD ["--runtime-internal", "--host", "127.0.0.1", "--port", "15169", "--no-open"]
