# Personal Video Runner

1. Keep `auto_discover_sensors` enabled to read every `sensor.*` and, when
   `include_binary_sensors` is enabled, every `binary_sensor.*` entity through
   Home Assistant's internal Core API.
2. Enable `allow_external_tts` only after accepting that generic narration text
   is sent to Edge TTS. Sensor names and values stay on the local visual cards
   and are never included in that narration.
3. Start the app. With `generate_personal_on_start` enabled, the first 0.3
   startup publishes one real daily and one real weekly sensor story.
4. Keep `boot: auto` enabled so the internal scheduler survives host and app restarts.

`weekly_day` uses Monday `0` through Sunday `6`. Times use the Home Assistant host timezone and 24-hour `HH:MM` format.

Set `auto_discover_sensors: false` only when you want the older explicit
`entity_allowlist` mode. The runner reads all discovered states and histories,
then selects at most five informative readings for a one-minute video.

The app writes media only below `/share/personal_video_studio` and private
scheduler/audit data below its own `/data/personal_video_studio` volume. It does
not need access to Home Assistant's configuration directory.
