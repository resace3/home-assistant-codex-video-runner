# Changelog

## 0.2.2 - 2026-07-10

- Write MoviePy's intermediate audio mux file inside the private writable
  render-temporary directory so the read-only application image works on HAOS.
- Exercise daily and weekly generation from a read-only working directory.

## 0.2.1 - 2026-07-10

- Aligned the tag release scan with the existing PR and image-publish policy so
  unfixed upstream operating-system findings are reported without hiding any
  patchable High or Critical vulnerability.

## 0.2.0 - 2026-07-10

- Added one-command, LLM-free daily-and-weekly synthetic generation with Libby by default.
- Initialized the viewer catalog during install and tightened sidecar, directory, duplicate-ID, and symlink checks.
- Added independent FFprobe metadata validation alongside MoviePy and full FFmpeg decode validation.
- Added a persistent ARM64/AMD64 Home Assistant runner app with an internal scheduler.
- Replaced reconstructible numeric aggregates with minimum-sample categorical bands and bounded history collection.
- Published immutable render assets before atomically switching metadata and indexes.
- Upgraded to security-fixed Pillow 12.3 through a hash-pinned upstream MoviePy commit.
- Enforced actual 145–160 WPM Libby pacing at natural 1.0x and prevented narration speedups.

## 0.1.0 - 2026-07-10

- Initial privacy-first runner with allowlisted collection, aggregate disclosure preview, offline/OpenAI structured storyboard policy, cost cap, exact Libby voice resolution, MoviePy rendering, FFmpeg validation, atomic indexes, CLI, Docker, tests, and focused CI workflows.
