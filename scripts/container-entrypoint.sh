#!/usr/bin/env bash
set -Eeuo pipefail

install -d -m 0755 -o runner -g runner \
  /share/personal_video_studio \
  /share/personal_video_studio/daily \
  /share/personal_video_studio/weekly \
  /share/personal_video_studio/indexes
install -d -m 0700 -o runner -g runner \
  /share/personal_video_studio/temporary \
  /data/personal_video_studio

if [[ "${1:-scheduler}" == "scheduler" ]]; then
  video-runner prepare-addon \
    --options /data/options.json \
    --config-out /data/personal_video_studio/config.yaml \
    --schedule-out /data/personal_video_studio/schedule.json
  chown runner:runner \
    /data/personal_video_studio/config.yaml \
    /data/personal_video_studio/schedule.json
  exec gosu runner:runner video-runner scheduler \
    --config /data/personal_video_studio/config.yaml \
    --schedule /data/personal_video_studio/schedule.json
fi

exec gosu runner:runner video-runner "$@"
