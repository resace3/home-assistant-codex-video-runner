from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from video_runner.config import Settings, TTSConfig
from video_runner.home_assistant import HomeAssistantClient
from video_runner.model_policy import estimate_cost, offline_storyboard
from video_runner.schemas import BrowserVideo, PeriodType, Scene, Storyboard, Visual
from video_runner.security import (
    aggregate_history,
    redact,
    scrub_supervisor_environment,
    validate_runtime_roots,
)
from video_runner.storage import atomic_json, rebuild_indexes, render_lock
from video_runner.tts import resolve_voice


def test_redaction_masks_tokens_and_headers() -> None:
    secret = "A" * 48
    output = redact(f"Authorization: Bearer {secret} api_key={secret}", (secret,))
    assert secret not in output
    assert "[REDACTED]" in output


def test_aggregate_history_removes_identifiers_and_individual_readings() -> None:
    output = aggregate_history({"sensor.private_name": ["10", "12", "14"], "sensor.location": ["home"]})
    encoded = json.dumps(output)
    assert "private_name" not in encoded
    assert "location" not in encoded
    assert output["metrics"] == {
        "metric_1": {"median": 12.0, "minimum": 10.0, "maximum": 14.0, "change": 4.0, "observations": 3}
    }
    assert '"latest"' not in encoded


def test_supervisor_token_is_scrubbed_before_provider_work(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPERVISOR_TOKEN", "canary-value")
    scrub_supervisor_environment()
    assert "SUPERVISOR_TOKEN" not in __import__("os").environ
    import logging

    retained = [
        value
        for handler in logging.getLogger().handlers
        for filter_ in handler.filters
        for value in getattr(filter_, "sensitive_values", ())
    ]
    assert "canary-value" not in retained


def test_production_roots_are_fixed(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        validate_runtime_roots(tmp_path, Path("/data/personal_video_studio"), test_mode=False)
    validate_runtime_roots(tmp_path, tmp_path / "private", test_mode=True)


def test_offline_storyboard_is_one_minute_and_natural_word_count() -> None:
    board = offline_storyboard(PeriodType.DAILY)
    assert sum(scene.duration_seconds for scene in board.scenes) == 60
    assert 145 <= len(board.narration.split()) <= 160


def test_storyboard_rejects_overlap() -> None:
    scene = Scene(start_seconds=0, duration_seconds=30, scene_type="title", heading="A", body="B", visual=Visual(kind="gradient", data_reference="x"))
    with pytest.raises(ValidationError):
        Storyboard(title="x", period_type="daily", summary="x", narration="word " * 150, scenes=[scene, scene, scene])


def test_cost_is_bounded_and_unknown_models_are_rejected() -> None:
    assert estimate_cost("gpt-5-nano", 1000, 1000) == pytest.approx(0.00045)
    with pytest.raises(ValueError):
        estimate_cost("unknown", 1, 1)


def _manifest(root: Path, period: str, name: str) -> BrowserVideo:
    now = datetime.now(UTC)
    folder = root / period / "2026" / "07"
    folder.mkdir(parents=True)
    for suffix in ("mp4", "webp", "vtt"):
        (folder / f"{name}.{suffix}").write_bytes(b"safe")
    video = BrowserVideo(
        id=name,
        type=period,
        title="Synthetic",
        description="Synthetic fixture",
        created_at=now,
        period_start=now - timedelta(days=1),
        period_end=now,
        duration_seconds=60,
        video_filename=f"{name}.mp4",
        thumbnail_filename=f"{name}.webp",
        captions_filename=f"{name}.vtt",
        generation_status="complete",
    )
    atomic_json(folder / f"{name}.json", video.model_dump(mode="json"))
    return video


def test_indexes_ignore_incomplete_and_corrupt_bundles(tmp_path: Path) -> None:
    _manifest(tmp_path, "daily", "daily-2026-07-10")
    bad = tmp_path / "weekly" / "bad.json"
    bad.parent.mkdir()
    bad.write_text("not json", encoding="utf-8")
    counts = rebuild_indexes(tmp_path)
    assert counts == {"daily": 1, "weekly": 0}
    assert len(json.loads((tmp_path / "indexes" / "all.json").read_text())) == 1


def test_render_lock_prevents_duplicates(tmp_path: Path) -> None:
    with render_lock(tmp_path):
        with pytest.raises(RuntimeError):
            with render_lock(tmp_path):
                pass


def test_config_rejects_arbitrary_fields() -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({"unknown": True})


def test_history_client_uses_period_aggregates_not_current_state(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        def json(self) -> list[list[dict[str, object]]]:
            return [[
                {"entity_id": "sensor.example_steps", "state": "10"},
                {"state": "20"},
            ]]

    seen: dict[str, object] = {}
    client = object.__new__(HomeAssistantClient)

    def fake_get(path: str, *, params: dict[str, str]) -> Response:
        seen.update({"path": path, "params": params})
        return Response()

    monkeypatch.setattr(client, "_get", fake_get)
    history = client.fetch_allowlisted_history(
        ["sensor.example_steps"], period="daily", daily_hours=24, weekly_days=7
    )
    assert history == {"sensor.example_steps": ["10", "20"]}
    assert "/history/period/" in str(seen["path"])
    assert "/states/" not in str(seen["path"])


def test_empty_allowlist_never_calls_history_api(monkeypatch: pytest.MonkeyPatch) -> None:
    client = object.__new__(HomeAssistantClient)

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("history API must not be called for an empty allowlist")

    monkeypatch.setattr(client, "_get", forbidden)
    assert client.fetch_allowlisted_history([], period="daily", daily_hours=24, weekly_days=7) == {}


def test_exact_libby_mapping_and_no_silent_substitution(monkeypatch: pytest.MonkeyPatch) -> None:
    async def voices() -> list[dict[str, str]]:
        return [{"ShortName": "en-GB-LibbyNeural", "Locale": "en-GB", "Gender": "Female"}]

    monkeypatch.setattr("video_runner.tts.edge_tts.list_voices", voices)
    assert asyncio.run(resolve_voice(TTSConfig())) == "en-GB-LibbyNeural"
    with pytest.raises(RuntimeError):
        asyncio.run(resolve_voice(TTSConfig(requested_voice_id="en-GB-SoniaNeural")))
