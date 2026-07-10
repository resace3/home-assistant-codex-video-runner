#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec "$ROOT/.venv/bin/video-runner" generate --period daily --synthetic --mock-tts --config /data/personal_video_studio/config.yaml

