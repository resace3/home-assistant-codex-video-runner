FROM python:3.12-slim-bookworm@sha256:8a7e7cc04fd3e2bd787f7f24e22d5d119aa590d429b50c95dfe12b3abe52f48b
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml requirements.lock README.md /app/
COPY src /app/src
RUN pip install --no-cache-dir --require-hashes -r requirements.lock && pip install --no-cache-dir --no-deps . && useradd --system --uid 10001 --home /nonexistent --shell /usr/sbin/nologin runner
USER runner
ENTRYPOINT ["video-runner"]
CMD ["--help"]
