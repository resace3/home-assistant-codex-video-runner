#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
"$ROOT/.venv/bin/video-runner" doctor --config /data/personal_video_studio/config.yaml
"$ROOT/.venv/bin/video-runner" rebuild-index --config /data/personal_video_studio/config.yaml
echo "Installation verification passed."

