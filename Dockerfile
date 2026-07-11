FROM python:3.12-slim-bookworm@sha256:8a7e7cc04fd3e2bd787f7f24e22d5d119aa590d429b50c95dfe12b3abe52f48b
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
