# Personal Video Runner

1. Review the entity allowlist and leave it empty for the synthetic first run.
2. Enable `allow_external_tts` only after accepting that generic narration text is sent to Edge TTS.
3. Start the app. With `run_demo_on_start` enabled, it publishes one daily and one weekly video.
4. Keep `boot: auto` enabled so the internal scheduler survives host and app restarts.

`weekly_day` uses Monday `0` through Sunday `6`. Times use the Home Assistant host timezone and 24-hour `HH:MM` format.

The app writes media only below `/share/personal_video_studio` and private scheduler/audit data below its own `/data/personal_video_studio` volume. It does not need access to Home Assistant's configuration directory.
