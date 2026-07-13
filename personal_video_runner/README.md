# Personal Video Runner

Headless Home Assistant app that generates the daily and weekly media consumed by Personal Video Studio.

The app automatically discovers Home Assistant sensor and binary-sensor
entities, reads current states plus daily/weekly history through the supervised
Core API, and creates a fully local personalized storyboard. The real friendly
names and values appear on the video cards. The exact `en-GB-LibbyNeural` voice
uses generic narration at natural 1.0x, so raw Home Assistant readings and the
Supervisor credential are never sent to TTS.
