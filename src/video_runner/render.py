from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from imageio_ffmpeg import get_ffmpeg_exe
from moviepy import AudioFileClip, ImageClip, VideoFileClip, concatenate_videoclips
from PIL import Image, ImageDraw, ImageFont

from .config import RenderConfig, Settings
from .schemas import BrowserVideo, PeriodType, PrivateAudit, Storyboard
from .storage import atomic_json, rebuild_indexes, render_lock
from .tts import synthesize_edge, synthesize_test_tone


def _font(size: int) -> Any:
    candidates = (
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("C:/Windows/Fonts/segoeui.ttf"),
    )
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: Any, width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textlength(candidate, font=font) <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _scene_image(path: Path, heading: str, body: str, config: RenderConfig, index: int) -> None:
    palette = ((26, 31, 66), (17, 60, 72), (52, 35, 72), (31, 54, 48), (64, 42, 28), (31, 45, 70))
    image = Image.new("RGB", (config.width, config.height), palette[index % len(palette)])
    draw = ImageDraw.Draw(image)
    heading_font = _font(max(16, config.width // 18))
    body_font = _font(max(11, config.width // 34))
    small_font = _font(max(8, config.width // 55))
    margin = config.width // 10
    draw.rounded_rectangle(
        (margin, config.height // 8, config.width - margin, config.height * 7 // 8),
        radius=max(12, config.width // 20),
        fill=(8, 12, 24, 190),
        outline=(153, 211, 255),
        width=2,
    )
    y = float(config.height * 0.26)
    for line in _wrap(draw, heading, heading_font, config.width - 4 * margin):
        draw.text((2 * margin, y), line, font=heading_font, fill="white")
        y += heading_font.size * 1.15
    y += max(10, config.width // 30)
    for line in _wrap(draw, body, body_font, config.width - 4 * margin):
        draw.text((2 * margin, y), line, font=body_font, fill=(220, 230, 240))
        y += body_font.size * 1.3
    draw.text(
        (2 * margin, int(config.height * 0.82)),
        "Private reflection • Not medical advice",
        font=small_font,
        fill=(175, 193, 210),
    )
    image.save(path, "PNG", optimize=True)


def _captions(path: Path, narration: str, duration: float) -> None:
    words = narration.split()
    chunks = [words[index : index + 12] for index in range(0, len(words), 12)]
    cue = duration / len(chunks)

    def stamp(seconds: float) -> str:
        milliseconds = int(seconds * 1000)
        hours, remainder = divmod(milliseconds, 3_600_000)
        minutes, remainder = divmod(remainder, 60_000)
        secs, millis = divmod(remainder, 1000)
        return f"{hours:02}:{minutes:02}:{secs:02}.{millis:03}"

    lines = ["WEBVTT", ""]
    for index, chunk in enumerate(chunks):
        start = index * cue
        end = min(duration, (index + 1) * cue)
        lines.extend((f"{stamp(start)} --> {stamp(end)}", " ".join(chunk), ""))
    path.write_text("\n".join(lines), encoding="utf-8")


def _thumbnail(source: Path, destination: Path) -> None:
    with Image.open(source) as image:
        image.thumbnail((540, 960))
        image.save(destination, "WEBP", quality=82, method=6)


def render_storyboard(
    storyboard: Storyboard,
    settings: Settings,
    *,
    use_test_tone: bool = False,
    private_audit: PrivateAudit | None = None,
    lock_already_held: bool = False,
) -> BrowserVideo:
    root = settings.video_directory
    now = datetime.now(UTC)
    if storyboard.period_type == PeriodType.DAILY:
        identifier = f"daily-{now:%Y-%m-%d}"
        folder = root / "daily" / f"{now:%Y}" / f"{now:%m}"
        period_start = now - timedelta(days=1)
    else:
        identifier = f"weekly-{now:%G}-w{now:%V}"
        folder = root / "weekly" / f"{now:%G}"
        period_start = now - timedelta(days=7)
    basename = identifier
    (root / "temporary").mkdir(parents=True, exist_ok=True)
    lock_context = nullcontext() if lock_already_held else render_lock(root)
    with (
        lock_context,
        tempfile.TemporaryDirectory(
            prefix="video-render-", dir=root / "temporary"
        ) as temporary_name,
    ):
        temporary = Path(temporary_name)
        frames: list[Path] = []
        for index, scene in enumerate(storyboard.scenes):
            frame = temporary / f"scene-{index:02}.png"
            _scene_image(frame, scene.heading, scene.body, settings.render, index)
            frames.append(frame)
        audio_path = temporary / ("narration.wav" if use_test_tone else "narration.mp3")
        if use_test_tone or settings.tts.provider == "mock":
            voice = synthesize_test_tone(audio_path, 60)
        else:
            if not settings.tts.allow_external_egress:
                raise RuntimeError(
                    "External TTS is disabled; review the narration disclosure and opt in explicitly"
                )
            voice = synthesize_edge(storyboard.narration, audio_path, settings.tts)
        image_clips: list[ImageClip] = []
        audio: AudioFileClip | None = None
        video = None
        output = temporary / f"{basename}.mp4"
        try:
            audio = AudioFileClip(str(audio_path))
            target_duration = float(audio.duration)
            if not 55 <= target_duration <= 65:
                raise ValueError(
                    "narration duration must already be within 55-65 seconds; audio is never trimmed or sped up"
                )
            scale = target_duration / sum(scene.duration_seconds for scene in storyboard.scenes)
            image_clips = [
                ImageClip(str(frame), duration=scene.duration_seconds * scale)
                for frame, scene in zip(frames, storyboard.scenes, strict=True)
            ]
            video = concatenate_videoclips(image_clips, method="compose").with_audio(audio)
            video.write_videofile(
                str(output),
                fps=settings.render.fps,
                codec="libx264",
                audio_codec="aac",
                preset=settings.render.preset,
                threads=2,
                logger=None,
                ffmpeg_params=["-pix_fmt", "yuv420p", "-movflags", "+faststart"],
            )
        finally:
            if video is not None:
                video.close()
            if audio is not None:
                audio.close()
            for clip in image_clips:
                clip.close()
        normalized = temporary / f"{basename}.normalized.mp4"
        loudness = subprocess.run(
            [
                get_ffmpeg_exe(),
                "-y",
                "-i",
                str(output),
                "-c:v",
                "copy",
                "-af",
                "loudnorm=I=-16:TP=-1.5:LRA=11",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-movflags",
                "+faststart",
                str(normalized),
            ],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        if loudness.returncode:
            raise ValueError("EBU R128 loudness normalization failed")
        os.replace(normalized, output)
        _decode_validate(output, settings.render.width, settings.render.height)
        captions = temporary / f"{basename}.vtt"
        thumbnail = temporary / f"{basename}.webp"
        _captions(captions, storyboard.narration, target_duration)
        _thumbnail(frames[0], thumbnail)
        browser = BrowserVideo(
            id=identifier,
            type=storyboard.period_type,
            title=storyboard.title,
            description=storyboard.summary,
            created_at=now,
            period_start=period_start,
            period_end=now,
            duration_seconds=round(target_duration, 3),
            video_filename=output.name,
            thumbnail_filename=thumbnail.name,
            captions_filename=captions.name,
            generation_status="complete",
        )
        folder.mkdir(parents=True, exist_ok=True)
        folder.chmod(0o755)
        for source in (output, thumbnail, captions):
            shutil.move(str(source), folder / source.name)
            (folder / source.name).chmod(0o644)
        atomic_json(folder / f"{basename}.json", browser.model_dump(mode="json"))
        (folder / f"{basename}.json").chmod(0o644)
        if private_audit:
            audit = private_audit.model_copy(update={"video_id": identifier})
            audit_payload = audit.model_dump(mode="json") | {
                "voice_id": voice,
                "sha256": hashlib.sha256((folder / output.name).read_bytes()).hexdigest(),
            }
            atomic_json(
                settings.private_data_directory / "audit" / f"{basename}.json", audit_payload
            )
        rebuild_indexes(root)
        return browser


def _decode_validate(path: Path, expected_width: int, expected_height: int) -> dict[str, object]:
    if not path.is_file() or path.stat().st_size < 1024:
        raise ValueError("video output is missing or too small")
    with VideoFileClip(str(path)) as clip:
        duration = float(clip.duration)
        if not 55 <= duration <= 65:
            raise ValueError("video duration is outside 55-65 seconds")
        if tuple(clip.size) != (expected_width, expected_height):
            raise ValueError("video resolution does not match configuration")
        if clip.audio is None:
            raise ValueError("video has no audio stream")
    command = [get_ffmpeg_exe(), "-v", "error", "-i", str(path), "-f", "null", "-"]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=180, check=False)
    if completed.returncode:
        raise ValueError("ffmpeg decode validation failed")
    probe = subprocess.run(
        [get_ffmpeg_exe(), "-hide_banner", "-i", str(path)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    ).stderr
    lowered = probe.lower()
    if "video: h264" not in lowered or "audio: aac" not in lowered or "yuv420p" not in lowered:
        raise ValueError("output must contain H.264 video, AAC audio, and yuv420p pixels")
    atoms = path.read_bytes()[:2_000_000]
    moov, mdat = atoms.find(b"moov"), atoms.find(b"mdat")
    if moov < 0 or mdat < 0 or moov > mdat:
        raise ValueError("MP4 is not fast-start optimized")
    silence_result = subprocess.run(
        [
            get_ffmpeg_exe(),
            "-hide_banner",
            "-i",
            str(path),
            "-af",
            "silencedetect=noise=-50dB:d=2",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    if silence_result.returncode:
        raise ValueError("audio silence analysis failed")
    silence = silence_result.stderr
    if any(float(value) > 2.5 for value in re.findall(r"silence_duration:\s*([0-9.]+)", silence)):
        raise ValueError("audio contains a long pause")
    return {
        "duration_seconds": duration,
        "width": expected_width,
        "height": expected_height,
        "video_codec": "h264",
        "audio_codec": "aac",
        "pixel_format": "yuv420p",
        "faststart": True,
        "audio": True,
    }


def validate_output(path: Path) -> dict[str, object]:
    with VideoFileClip(str(path)) as clip:
        width, height = clip.size
    result = _decode_validate(path, int(width), int(height))
    result["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result
