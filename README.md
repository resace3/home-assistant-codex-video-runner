# Home Assistant Codex Video Runner

A privacy-first, deterministic MoviePy pipeline for one-minute daily and weekly Home Assistant reflections. The public repository contains only generic code and synthetic fixtures. Users explicitly choose every Home Assistant entity included.

> This is not a medical device. Generated observations are descriptive, not medical advice. Review the privacy and cost implications before enabling any external provider.

## Architecture

```mermaid
flowchart LR
  A[Allowlisted HA entities] -->|SUPERVISOR_TOKEN stays here| B[Local collector]
  B --> C[Aggregate-only disclosure DTO]
  C --> D{Offline or external storyboard}
  D --> E[Strict Pydantic validation]
  E --> F[Libby TTS at 1.0x]
  F --> G[Local MoviePy and FFmpeg]
  G --> H[Private staging and validation]
  H -->|manifest last| I[/share/personal_video_studio]
```

The Supervisor token exists only during the collector phase in an in-memory HTTP client. The client is closed, the environment value and token-aware logging filter are destroyed, and provider/TTS modules are imported only after that scrub boundary. It is never written, logged, sent to a model/TTS service, passed on a command line, put into Docker metadata, or exposed to a browser. Do not run `docker run -e SUPERVISOR_TOKEN=...`; if Docker is used, keep it tokenless and feed it only the minimized job specification.

The browser-safe manifest contains titles, dates, filenames, duration, and a short safe description. Model, cost, voice, checksum, fallback reason, and category audit records stay under private `/data`. Raw states and prompts are never written into the shared catalog.

## Quick start in Advanced SSH & Web Terminal

Keep Advanced SSH protected. This project never uninstalls or restarts it and never asks you to weaken protected mode.

```bash
git clone https://github.com/resace3/home-assistant-codex-video-runner.git
cd home-assistant-codex-video-runner
scripts/install.sh
cp config.example.yaml /data/personal_video_studio/config.yaml
chmod 600 /data/personal_video_studio/config.yaml
.venv/bin/video-runner doctor --config /data/personal_video_studio/config.yaml --test-tts
.venv/bin/video-runner generate --period daily --synthetic --mock-tts --config /data/personal_video_studio/config.yaml
```

Use only synthetic mode during repeated testing. A real run reads the runtime `SUPERVISOR_TOKEN` automatically; never paste it into configuration.

## Commands

```text
video-runner doctor [--test-tts]
video-runner list-entities
video-runner preview-data --period daily [--synthetic]
video-runner generate --period daily|weekly [--synthetic] [--mock-tts]
video-runner validate-output PATH
video-runner rebuild-index
video-runner cleanup [--no-dry-run]
video-runner print-schedule-example
```

`preview-data` is the disclosure gate: inspect exactly which aggregate aliases could leave the machine before switching `generation.provider` from `offline` to `openai`.

## Voice and timing

The requested product label `Libby, British Warm` is resolved to the provider voice identifier `en-GB-LibbyNeural`. Resolution is checked against the provider's live voice list; production never silently substitutes another voice. Speech uses the natural provider rate (`+0%`, 1.0x). Scripts are constrained to 145–160 words for approximately one minute. If narration is long, shorten the script or extend the scene within 55–65 seconds; never speed up Libby.

Edge TTS is external egress and is disabled by default. Before setting `tts.allow_external_egress: true` in private runtime configuration, use the disclosure preview and understand that the full narration is sent to the provider. Synthetic CI and demo runs use a local test tone. The Edge client is not an authenticated enterprise speech SLA; users needing contractual processing terms should implement another provider adapter.

CI uses a deterministic test tone and calls no paid TTS service.

## Model and cost policy

Offline template mode is the default and costs nothing. For OpenAI mode, the policy currently tries `gpt-5-nano` for this small structured task, then `gpt-5.4-nano`; both support Structured Outputs. Prices are explicitly versioned in code and were verified from the official model pages on 2026-07-10. The default maximum estimated LLM cost is `$0.05` per video. The request is rejected before sending if projected cost exceeds the cap, and invalid structured output is retried once before fallback.

Pricing changes. Reverify the [OpenAI model catalog](https://developers.openai.com/api/docs/models), [GPT-5 nano](https://developers.openai.com/api/docs/models/gpt-5-nano), and [GPT-5.4 nano](https://developers.openai.com/api/docs/models/gpt-5.4-nano) before releases.

Codex is the engineering tool used to build and maintain this project. The optional production OpenAI API is a separate metered service. MoviePy and FFmpeg render the final video locally; no generative video model is used.

## Storage and atomic publication

```text
/share/personal_video_studio/
├── daily/YYYY/MM/{mp4,webp,vtt,json}
├── weekly/YYYY/{mp4,webp,vtt,json}
├── indexes/{daily,weekly,all}.json
└── temporary/
/data/personal_video_studio/
├── config.yaml
├── audit/
└── logs/
```

The runner renders in a same-filesystem temporary directory, validates video/audio/duration/resolution and a complete FFmpeg decode, moves completed assets, writes the browser-safe sidecar, then atomically replaces indexes last. A lock prevents duplicate renders. The viewer ignores anything not present in a valid index.

`/share` is shared across add-ons and is not a security boundary: any add-on granted share access may read it. Install only trusted add-ons.

## Configuration and privacy

Copy `config.example.yaml` to private `/data`; it is ignored by Git. Real entity IDs, values, provider keys, generated videos, narration, screenshots, Nabu Casa URLs, tokens, cookies, and logs must never enter this public repository.

The collector accepts only allowlisted sensor-like domains, fetches only those states, removes entity identifiers before external disclosure, bounds the schema, and rejects unknown fields. Free text, raw history, coordinates, attributes, database exports, and exact timestamps are not sent externally.

## Docker

The Docker image is reproducible for offline/synthetic tokenless rendering. Building or controlling Docker from Advanced SSH may be unavailable under protected mode. Never disable protection or mount the Docker socket for this project. The supported private collector path is the supervised shell runtime; Docker receives no Supervisor token.

## Tests

```bash
python -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/ruff format --check .
.venv/bin/ruff check .
.venv/bin/mypy src
.venv/bin/pytest -m 'not integration'
.venv/bin/pytest -m integration
```

The integration test creates a real 55–65 second low-resolution H.264/AAC MP4 from synthetic data and decodes it fully. Public CI never calls Home Assistant, OpenAI, or live TTS.

## Update, rollback, and uninstall

- Update: `scripts/update.sh`
- Validate: `scripts/verify_installation.sh`
- Roll back: check out the previous signed/tagged release and rerun `scripts/install.sh`.
- Uninstall runtime: `scripts/uninstall.sh`. It deliberately preserves `/data` and `/share`; delete those only after a separate explicit privacy decision.

See [scheduling](docs/SCHEDULING.md), [security policy](SECURITY.md), [contributing](CONTRIBUTING.md), and [release history](CHANGELOG.md).

## Limitations

- Exact Libby availability depends on the live Edge voice catalog and network access.
- Audible autoplay is controlled by the browser; the viewer starts muted and provides a play/unmute fallback.
- Chrome emulation does not prove iOS or Android Companion App WebView behavior.
- Home Assistant Green should start at 720×1280, 24 fps, one render at a time.
- The production runner is intentionally not a privileged Docker-socket add-on.
