from __future__ import annotations

import asyncio
import json
import tomllib
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError
from typer.testing import CliRunner

from video_runner import __version__
from video_runner.cli import app
from video_runner.config import Settings, TTSConfig, load_settings
from video_runner.home_assistant import HomeAssistantClient
from video_runner.model_policy import estimate_cost, offline_storyboard
from video_runner.scheduler import prepare_addon, should_run
from video_runner.schemas import (
    BrowserVideo,
    PeriodType,
    Scene,
    Storyboard,
    Visual,
    estimated_narration_seconds,
)
from video_runner.security import (
    aggregate_history,
    redact,
    scrub_supervisor_environment,
    validate_runtime_roots,
)
from video_runner.storage import atomic_json, rebuild_indexes, render_lock
from video_runner.tts import resolve_voice, synthesize_edge


def test_release_versions_are_consistent() -> None:
    root = Path(__file__).parents[1]
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    addon = yaml.safe_load(
        (root / "personal_video_runner" / "config.yaml").read_text(encoding="utf-8")
    )
    assert project["project"]["version"] == addon["version"] == __version__


def test_doctor_fails_when_required_media_tools_are_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tmp_path / "config.yaml"
    config.write_text(
        f"video_directory: {(tmp_path / 'share').as_posix()}\n"
        f"private_data_directory: {(tmp_path / 'private').as_posix()}\n",
        encoding="utf-8",
    )
    (tmp_path / "share").mkdir()
    monkeypatch.setattr("video_runner.cli.shutil.which", lambda _name: None)
    result = CliRunner().invoke(
        app,
        ["doctor", "--config", str(config), "--no-require-supervisor-token"],
        env={"VIDEO_RUNNER_TEST_MODE": "1"},
    )
    assert result.exit_code == 1
    assert '"ready": false' in result.output


def test_redaction_masks_tokens_and_headers() -> None:
    secret = "A" * 48
    output = redact(f"Authorization: Bearer {secret} api_key={secret}", (secret,))
    assert secret not in output
    assert "[REDACTED]" in output


def test_aggregate_history_removes_identifiers_and_individual_readings() -> None:
    values = ["10", "10", "11", "11", "13", "14", "14", "15"]
    output = aggregate_history({"sensor.private_name": values, "sensor.location": ["home"]})
    encoded = json.dumps(output)
    assert "private_name" not in encoded
    assert "location" not in encoded
    assert output["metrics"] == {
        "metric_1": {
            "trend": "increasing",
            "variability": "high",
            "observations": "8-15",
        }
    }
    assert not {"minimum", "maximum", "median", "change", "latest"} & set(encoded.split('"'))


def test_aggregate_history_resists_exact_value_reconstruction() -> None:
    low_scale = aggregate_history({"sensor.one": [10, 10, 11, 11, 13, 14, 14, 15]})
    high_scale = aggregate_history({"sensor.one": [100, 100, 110, 110, 130, 140, 140, 150]})
    assert low_scale == high_scale
    assert aggregate_history({"sensor.one": [10, 20, 30]})["metrics"] == {}


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
    assert estimated_narration_seconds(board.narration) == pytest.approx(60.8)


def test_storyboard_rejects_overlap() -> None:
    scene = Scene(
        start_seconds=0,
        duration_seconds=30,
        scene_type="title",
        heading="A",
        body="B",
        visual=Visual(kind="gradient", data_reference="x"),
    )
    with pytest.raises(ValidationError):
        Storyboard(
            title="x",
            period_type="daily",
            summary="x",
            narration="word " * 150,
            scenes=[scene, scene, scene],
        )


def test_cost_is_bounded_and_unknown_models_are_rejected() -> None:
    assert estimate_cost("gpt-5-nano", 1000, 1000) == pytest.approx(0.00045)
    with pytest.raises(ValueError):
        estimate_cost("unknown", 1, 1)


def _manifest(root: Path, period: str, name: str) -> BrowserVideo:
    now = datetime.now(UTC)
    folder = root / period / "2026"
    if period == "daily":
        folder /= "07"
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
    _manifest(tmp_path, "weekly", "weekly-2026-w28")
    bad = tmp_path / "weekly" / "bad.json"
    bad.parent.mkdir(exist_ok=True)
    bad.write_text("not json", encoding="utf-8")
    counts = rebuild_indexes(tmp_path)
    assert counts == {"daily": 1, "weekly": 1}
    catalog = json.loads((tmp_path / "indexes" / "all.json").read_text())
    assert len(catalog) == 2
    assert {item["relative_directory"] for item in catalog} == {
        "daily/2026/07",
        "weekly/2026",
    }


def test_indexes_reject_misnamed_metadata_and_period_mismatch(tmp_path: Path) -> None:
    video = _manifest(tmp_path, "daily", "daily-2026-07-10")
    folder = tmp_path / "daily" / "2026" / "07"
    (folder / f"{video.id}.json").rename(folder / "unexpected-name.json")
    wrong_period = _manifest(tmp_path, "weekly", "weekly-2026-w28")
    payload = wrong_period.model_dump(mode="json") | {"type": "daily"}
    atomic_json(tmp_path / "weekly" / "2026" / f"{wrong_period.id}.json", payload)
    assert rebuild_indexes(tmp_path) == {"daily": 0, "weekly": 0}
    assert json.loads((tmp_path / "indexes" / "all.json").read_text()) == []


def test_render_lock_prevents_duplicates(tmp_path: Path) -> None:
    with render_lock(tmp_path):
        with pytest.raises(RuntimeError):
            with render_lock(tmp_path):
                pass


def test_config_rejects_arbitrary_fields() -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({"unknown": True})


def test_history_client_uses_period_aggregates_not_current_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Response:
        content = b"bounded"

        def json(self) -> list[list[dict[str, object]]]:
            return [
                [
                    {"entity_id": "sensor.example_steps", "state": "10"},
                    {"state": "20"},
                ]
            ]

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


def test_history_client_caps_observations(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        content = b"bounded"

        def json(self) -> list[list[dict[str, object]]]:
            return [[{"entity_id": "sensor.example", "state": str(index)} for index in range(100)]]

    client = object.__new__(HomeAssistantClient)
    monkeypatch.setattr(client, "_get", lambda *_args, **_kwargs: Response())
    history = client.fetch_allowlisted_history(
        ["sensor.example"],
        period="daily",
        daily_hours=24,
        weekly_days=7,
        max_observations_per_entity=8,
    )
    assert len(history["sensor.example"]) == 8
    assert history["sensor.example"][-1] == "99"


def test_prepare_addon_and_schedule_are_private_and_deterministic(tmp_path: Path) -> None:
    options_path = tmp_path / "options.json"
    config_path = tmp_path / "private" / "config.yaml"
    schedule_path = tmp_path / "private" / "schedule.json"
    options_path.write_text(
        json.dumps(
            {
                "allow_external_tts": True,
                "entity_allowlist": ["sensor.example"],
                "daily_time": "06:15",
                "weekly_time": "06:30",
            }
        ),
        encoding="utf-8",
    )
    prepared = prepare_addon(options_path, config_path, schedule_path)
    settings = load_settings(config_path)
    assert prepared.allow_external_tts is True
    assert settings.tts.requested_voice_id == "en-GB-LibbyNeural"
    assert settings.tts.allow_external_egress is True
    assert settings.data.entity_allowlist == ["sensor.example"]
    due, key = should_run(datetime(2026, 7, 10, 6, 15, tzinfo=UTC), "06:15", "")
    assert due is True
    assert should_run(datetime(2026, 7, 10, 6, 15, tzinfo=UTC), "06:15", key)[0] is False


def test_exact_libby_mapping_and_no_silent_substitution(monkeypatch: pytest.MonkeyPatch) -> None:
    async def voices() -> list[dict[str, str]]:
        return [{"ShortName": "en-GB-LibbyNeural", "Locale": "en-GB", "Gender": "Female"}]

    monkeypatch.setattr("video_runner.tts.edge_tts.list_voices", voices)
    assert asyncio.run(resolve_voice(TTSConfig())) == "en-GB-LibbyNeural"
    with pytest.raises(RuntimeError):
        asyncio.run(resolve_voice(TTSConfig(requested_voice_id="en-GB-SoniaNeural")))


def test_libby_uses_natural_rate_and_rejects_speedup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seen: dict[str, str] = {}

    async def voice(_config: TTSConfig) -> str:
        return "en-GB-LibbyNeural"

    class Communicate:
        def __init__(self, _text: str, *, voice: str, rate: str) -> None:
            seen.update({"voice": voice, "rate": rate})

        async def save(self, path: str) -> None:
            Path(path).write_bytes(b"synthetic")

    monkeypatch.setattr("video_runner.tts.resolve_voice", voice)
    monkeypatch.setattr("video_runner.tts.edge_tts.Communicate", Communicate)
    assert synthesize_edge("safe generic narration", tmp_path / "speech.mp3", TTSConfig()) == (
        "en-GB-LibbyNeural"
    )
    assert seen == {"voice": "en-GB-LibbyNeural", "rate": "+0%"}
    with pytest.raises(ValidationError):
        TTSConfig(speaking_rate=1.01)
