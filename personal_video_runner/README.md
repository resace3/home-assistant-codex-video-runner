# Personal Video Runner

Headless Home Assistant app that generates the daily and weekly media consumed by Personal Video Studio.

The app uses a fixed allowlist, categorical aggregates, offline storyboards, and the exact `en-GB-LibbyNeural` voice. External TTS is disabled until `allow_external_tts` is explicitly enabled. No raw Home Assistant readings or Supervisor credentials are sent to TTS.
