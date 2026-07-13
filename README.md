# Home Assistant Codex Video Runner

A privacy-first, deterministic MoviePy pipeline for one-minute daily and weekly
Home Assistant data stories. The public repository contains only generic code
and synthetic fixtures. The supervised app can automatically read every sensor
and binary-sensor entity, rank the most useful local patterns, and turn them into
animated charts, comparisons, progress visuals, and practical reflections.

> This is not a medical device. Generated observations are descriptive, not medical advice. Review the privacy and cost implications before enabling any external provider.

## Architecture

```mermaid
flowchart LR
  A[Automatically discovered HA sensors] -->|SUPERVISOR_TOKEN stays here| B[Local collector]
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

## Home Assistant installation

Add this repository to Home Assistant's app store, install **Personal Video Runner**, review its options, and explicitly enable `allow_external_tts` before starting it. The headless app owns Python, MoviePy, FFmpeg, FFprobe, Libby TTS, and its scheduler; it does not depend on a shell app or a host package install.

On the first 0.4 start, `generate_personal_on_start` publishes one real daily
and one real weekly video from the instance's sensors. Recurring jobs run inside
the supervised app and survive restarts. Keep Advanced SSH protected and
running if you use it for unrelated work: this project never stops, restarts,
uninstalls, or weakens it.

A real scheduled run receives `SUPERVISOR_TOKEN` from Supervisor at runtime.
The runner uses it with `http://supervisor/core/api/states` and the history API,
then scrubs it before storyboard, TTS, or rendering work. Never paste that token
into configuration.

## Commands

```text
video-runner doctor [--test-tts]
video-runner list-entities
video-runner preview-data --period daily [--synthetic]
video-runner generate --period daily|weekly [--synthetic] [--mock-tts]
video-runner generate-demo [--mock-tts]
video-runner validate-output PATH
video-runner rebuild-index
video-runner cleanup [--no-dry-run]
video-runner print-schedule-example
```

`preview-data` is the disclosure gate: inspect exactly which aggregate aliases could leave the machine before switching `generation.provider` from `offline` to `openai`.

## Voice and timing

The requested product label `Libby, British Warm` is resolved to the provider voice identifier `en-GB-LibbyNeural`. Resolution is checked against the provider's live voice list; production never silently substitutes another voice. Speech uses the natural provider rate (`+0%`, 1.0x). Scripts are constrained to 145–160 words for approximately one minute, using `seconds = word count / 150 * 60`; the rendered audio is also checked for an actual 145–160 WPM pace. If narration is long, shorten the script or extend the scene within 55–65 seconds; never speed up Libby.

Edge TTS is external egress and is disabled by default. Before setting `tts.allow_external_egress: true` in private runtime configuration, use the disclosure preview and understand that the full narration is sent to the provider. CI uses a local test tone; the installed demo uses the exact Libby voice only after explicit consent. The Edge client is not an authenticated enterprise speech SLA; users needing contractual processing terms should implement another provider adapter.

CI uses a deterministic test tone and calls no paid TTS service.

`generate-demo` always uses the offline storyboard and synthetic data, so it never calls an LLM or incurs model cost. By default it renders both a daily and a weekly video with Libby. That requires the explicit `tts.allow_external_egress: true` disclosure setting because the generic narration is sent to Edge TTS. The `--mock-tts` test-tone option exists only for CI and local pipeline diagnostics, not final user-facing videos.

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

The runner renders in a same-filesystem temporary directory, validates video/audio/duration/resolution independently with MoviePy and FFprobe, and performs a complete FFmpeg decode and long-pause scan. Each render gets immutable asset filenames; only after the whole bundle validates does the runner atomically replace the stable `{video-id}.json` sidecar and indexes. A crash can leave an unreferenced orphan, but it cannot expose a mixed old/new bundle. A lock prevents duplicate renders and index rebuild races.

Installation creates an empty valid `indexes/all.json`; seeing zero videos after viewer installation means no completed runner bundle has been published yet. Run `generate-demo` to publish one daily and one weekly bundle, then refresh Personal Video Studio.

`/share` is shared across add-ons and is not a security boundary: any add-on granted share access may read it. Install only trusted add-ons.

## Configuration and privacy

Copy `config.example.yaml` to private `/data`; it is ignored by Git. Real entity IDs, values, provider keys, generated videos, narration, screenshots, Nabu Casa URLs, tokens, cookies, and logs must never enter this public repository.

Automatic mode reads all `sensor.*` and `binary_sensor.*` states up to the
configured fail-closed safety cap, then requests period history in bounded
batches with response-size and observation limits. Every usable entity is
considered locally; at most five high-signal readings are placed on the visual
cards. External model disclosure is count-only. Libby receives generic
narration without sensor names, values, entity identifiers, attributes, raw
history, coordinates, or timestamps.

## Container and scheduler

The same pinned multi-architecture image powers the headless Home Assistant app. A root entrypoint creates only the required `/share/personal_video_studio` and private `/data/personal_video_studio` directories, then drops permanently to UID 10001 before running the scheduler. The image never receives the Docker socket. Each generation runs in a child process so the child can scrub `SUPERVISOR_TOKEN` before importing or calling any provider while the long-lived scheduler retains its supervised runtime credential for the next local collection.

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

The integration test creates real 55–65 second low-resolution daily and weekly
H.264/AAC MP4s from synthetic data, decodes them fully, samples all seven scenes,
and asserts both structural variation and within-scene motion. Public CI never
calls Home Assistant, OpenAI, or live TTS. `scripts/visual_qa.py` can build a
three-second contact sheet and report frame-change cadence, composition diversity,
integrated loudness, silence, duration, resolution, and file size for release QA.

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
