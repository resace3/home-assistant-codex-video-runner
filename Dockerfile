FROM python:3.14-slim-bookworm@sha256:86f975aca15cf04a40b399eebede9aea7c82eae084d1f1a0a6ef6bcaae871a30
ARG BUILD_VERSION="dev"
ARG BUILD_ARCH="aarch64|amd64"
LABEL io.hass.version="${BUILD_VERSION}" \
      io.hass.type="app" \
      io.hass.arch="${BUILD_ARCH}" \
      io.hass.name="Personal Video Runner" \
      io.hass.description="Privacy-first daily and weekly personal video generator" \
      io.hass.url="https://github.com/resace3/home-assistant-codex-video-runner" \
      org.opencontainers.image.source="https://github.com/resace3/home-assistant-codex-video-runner" \
      org.opencontainers.image.licenses="Apache-2.0"
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core gosu && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml requirements.lock README.md /app/
COPY src /app/src
COPY scripts/container-entrypoint.sh /usr/local/bin/container-entrypoint
RUN pip install --no-cache-dir --require-hashes -r requirements.lock && \
    pip install --no-cache-dir --no-deps . && \
    useradd --system --uid 10001 --home /nonexistent --shell /usr/sbin/nologin runner && \
    chmod 0755 /usr/local/bin/container-entrypoint
ENTRYPOINT ["/usr/local/bin/container-entrypoint"]
CMD ["scheduler"]
