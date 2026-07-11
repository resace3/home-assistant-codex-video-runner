# Changelog

## 0.2.2

- Keep MoviePy's temporary audio mux file in the writable private render
  directory, fixing first-run generation on the read-only HAOS image.

## 0.2.1

- Align the release scan with the existing PR and image-publish vulnerability
  policy while continuing to fail on patchable High and Critical findings.

## 0.2.0

- Add a persistent Home Assistant runner app for ARM64 and AMD64.
- Generate daily and weekly synthetic media on first start.
- Schedule recurring generation without relying on Advanced SSH.
- Keep Edge TTS egress disabled until explicitly enabled.
