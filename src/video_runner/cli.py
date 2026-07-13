from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Annotated

import typer

from .config import Settings, load_settings
from .home_assistant import HomeAssistantClient
from .personalization import build_personal_summary, external_disclosure_summary
from .schemas import PeriodType, PrivateAudit
from .security import (
    configure_logging,
    scrub_supervisor_environment,
    validate_runtime_roots,
)
from .storage import rebuild_indexes, render_lock

app = typer.Typer(
    no_args_is_help=True, help="Privacy-first Home Assistant personalized video runner"
)
ConfigOption = Annotated[Path | None, typer.Option("--config", exists=True, dir_okay=False)]


def _settings(config: Path | None) -> Settings:
    token = os.environ.get("SUPERVISOR_TOKEN", "")
    configure_logging((token, os.environ.get("OPENAI_API_KEY", "")))
    settings = load_settings(config)
    validate_runtime_roots(
        settings.video_directory,
        settings.private_data_directory,
        test_mode=os.environ.get("VIDEO_RUNNER_TEST_MODE") == "1",
    )
    return settings


def _collect(settings: Settings, period: PeriodType, synthetic: bool) -> dict[str, object]:
    if synthetic:
        from .home_assistant import SensorSnapshot

        snapshots = {
            "sensor.synthetic_sleep_minutes_asleep": SensorSnapshot(
                "sensor.synthetic_sleep_minutes_asleep",
                "Synthetic Sleep Minutes Asleep",
                "428",
                "min",
                "duration",
            ),
            "sensor.synthetic_sleep_efficiency": SensorSnapshot(
                "sensor.synthetic_sleep_efficiency",
                "Synthetic Sleep Efficiency",
                "91",
                "%",
                "percentage",
            ),
            "sensor.synthetic_steps": SensorSnapshot(
                "sensor.synthetic_steps", "Synthetic Steps", "8123", "steps", "distance"
            ),
            "sensor.synthetic_resting_heart_rate": SensorSnapshot(
                "sensor.synthetic_resting_heart_rate",
                "Synthetic Resting Heart Rate",
                "61",
                "bpm",
                "heart_rate",
            ),
            "sensor.synthetic_meditation_minutes": SensorSnapshot(
                "sensor.synthetic_meditation_minutes",
                "Synthetic Meditation Minutes",
                "18",
                "min",
                "duration",
            ),
        }
        histories: dict[str, list[object]] = {
            "sensor.synthetic_sleep_minutes_asleep": [382, 395, 401, 415, 422, 428],
            "sensor.synthetic_sleep_efficiency": [86, 88, 87, 90, 91, 91],
            "sensor.synthetic_steps": [2200, 3100, 4700, 6400, 7800, 8123],
            "sensor.synthetic_resting_heart_rate": [64, 63, 62, 61, 60, 61],
            "sensor.synthetic_meditation_minutes": [0, 8, 10, 12, 15, 18],
        }
        return build_personal_summary(
            snapshots,
            histories,
            period=period.value,
            max_highlights=settings.data.max_highlights,
        )
    with HomeAssistantClient() as client:
        explicit_ids = (
            None if settings.data.auto_discover_sensors else settings.data.entity_allowlist
        )
        snapshots = client.fetch_sensor_snapshots(
            explicit_ids,
            include_binary_sensors=settings.data.include_binary_sensors,
            max_entities=settings.data.max_discovered_entities,
            max_response_bytes=settings.data.max_response_bytes,
        )
        histories = client.fetch_allowlisted_history(
            snapshots,
            period=period.value,
            daily_hours=settings.data.history_hours_daily,
            weekly_days=settings.data.history_days_weekly,
            max_observations_per_entity=settings.data.max_observations_per_entity,
            max_response_bytes=settings.data.max_response_bytes,
            batch_size=settings.data.history_batch_size,
        )
    return build_personal_summary(
        snapshots,
        histories,
        period=period.value,
        max_highlights=settings.data.max_highlights,
    )


@app.command()
def doctor(
    config: ConfigOption = None,
    test_tts: bool = False,
    require_supervisor_token: bool = True,
) -> None:
    """Check runtime, storage, Supervisor, ffmpeg, Codex, and the exact requested voice."""
    settings = _settings(config)
    checks: dict[str, object] = {
        "supervisor_token_present": bool(os.environ.get("SUPERVISOR_TOKEN")),
        "codex_cli_optional": shutil.which("codex") is not None,
        "ffmpeg": shutil.which("ffmpeg") is not None,
        "ffprobe": shutil.which("ffprobe") is not None,
        "video_directory_parent_exists": settings.video_directory.parent.exists(),
        "video_directory_parent_writable": os.access(settings.video_directory.parent, os.W_OK),
        "requested_voice_name": settings.tts.requested_voice_name,
        "requested_voice_id": settings.tts.requested_voice_id,
    }
    if test_tts:
        import asyncio

        scrub_supervisor_environment()
        from .tts import resolve_voice

        if not settings.tts.allow_external_egress:
            raise typer.BadParameter(
                "--test-tts requires explicit tts.allow_external_egress consent"
            )
        checks["resolved_voice_id"] = asyncio.run(resolve_voice(settings.tts))
        checks["requested_voice_exact_match"] = (
            checks["resolved_voice_id"] == settings.tts.requested_voice_id
        )
    required = [
        bool(checks["ffmpeg"]),
        bool(checks["ffprobe"]),
        bool(checks["video_directory_parent_exists"]),
        bool(checks["video_directory_parent_writable"]),
    ]
    if require_supervisor_token:
        required.append(bool(checks["supervisor_token_present"]))
    if test_tts:
        required.append(bool(checks.get("requested_voice_exact_match")))
    checks["ready"] = all(required)
    typer.echo(json.dumps(checks, indent=2))
    if not checks["ready"]:
        raise typer.Exit(code=1)


@app.command("list-entities")
def list_entities(config: ConfigOption = None) -> None:
    settings = _settings(config)
    for entity in settings.data.entity_allowlist:
        typer.echo(entity)


@app.command("preview-data")
def preview_data(
    period: PeriodType = PeriodType.DAILY, config: ConfigOption = None, synthetic: bool = False
) -> None:
    settings = _settings(config)
    if synthetic:
        minimized = _collect(settings, period, True)
    else:
        minimized = _collect(settings, period, False)
    typer.echo(
        json.dumps(
            {"external_disclosure_preview": external_disclosure_summary(minimized)}, indent=2
        )
    )


@app.command()
def generate(
    period: PeriodType = PeriodType.DAILY,
    config: ConfigOption = None,
    synthetic: bool = False,
    mock_tts: bool = False,
) -> None:
    settings = _settings(config)
    if settings.data.include_raw_values_in_external_requests:
        raise typer.BadParameter("raw values are never allowed in external requests")
    with render_lock(settings.video_directory):
        summary = _collect(settings, period, synthetic)
        scrub_supervisor_environment()
        # Provider and media modules are imported only after the Supervisor token is removed.
        from .model_policy import generate_storyboard
        from .render import render_storyboard

        result = generate_storyboard(period, summary, settings.generation)
        audit = PrivateAudit(
            video_id="pending",
            model=result.model,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            estimated_cost_usd=result.estimated_cost_usd,
            fallback_reason=result.fallback_reason,
            data_categories=result.storyboard.data_categories_used,
        )
        video = render_storyboard(
            result.storyboard,
            settings,
            use_test_tone=mock_tts,
            private_audit=audit,
            lock_already_held=True,
        )
    typer.echo(json.dumps(video.model_dump(mode="json"), indent=2))


@app.command("generate-demo")
def generate_demo(config: ConfigOption = None, mock_tts: bool = False) -> None:
    """Publish viewer-ready synthetic daily and weekly videos without an LLM call."""
    settings = _settings(config)
    if not mock_tts and settings.tts.provider != "edge":
        raise typer.BadParameter("Libby demo narration requires tts.provider: edge")
    if not mock_tts and not settings.tts.allow_external_egress:
        raise typer.BadParameter(
            "Libby sends the generic demo narration to Edge TTS; explicitly set "
            "tts.allow_external_egress: true after reviewing the disclosure"
        )
    with render_lock(settings.video_directory):
        scrub_supervisor_environment()
        from .model_policy import offline_storyboard
        from .render import render_storyboard

        videos = []
        for period in (PeriodType.DAILY, PeriodType.WEEKLY):
            storyboard = offline_storyboard(period)
            audit = PrivateAudit(
                video_id="pending",
                model="offline-template",
                input_tokens=0,
                output_tokens=0,
                estimated_cost_usd=0,
                fallback_reason="Synthetic demo; no LLM request",
                data_categories=[],
            )
            videos.append(
                render_storyboard(
                    storyboard,
                    settings,
                    use_test_tone=mock_tts,
                    private_audit=audit,
                    lock_already_held=True,
                ).model_dump(mode="json")
            )
    typer.echo(json.dumps({"items": videos}, indent=2))


@app.command("validate-output")
def validate_output_command(path: Path) -> None:
    from .render import validate_output

    typer.echo(json.dumps(validate_output(path), indent=2))


@app.command("rebuild-index")
def rebuild_index(config: ConfigOption = None) -> None:
    root = _settings(config).video_directory
    with render_lock(root):
        counts = rebuild_indexes(root)
    typer.echo(json.dumps(counts, indent=2))


@app.command("prepare-addon", hidden=True)
def prepare_addon_command(
    options: Annotated[Path, typer.Option("--options")],
    config_out: Annotated[Path, typer.Option("--config-out")],
    schedule_out: Annotated[Path, typer.Option("--schedule-out")],
) -> None:
    from .scheduler import prepare_addon

    prepared = prepare_addon(options, config_out, schedule_out)
    typer.echo(
        json.dumps(
            {
                "prepared": True,
                "automatic_sensor_discovery": prepared.auto_discover_sensors,
                "configured_entities": len(prepared.entity_allowlist),
                "external_tts_enabled": prepared.allow_external_tts,
            }
        )
    )


@app.command()
def scheduler(
    config: Annotated[Path, typer.Option("--config", exists=True, dir_okay=False)],
    schedule: Annotated[Path, typer.Option("--schedule", exists=True, dir_okay=False)],
) -> None:
    """Run the persistent daily/weekly Home Assistant app scheduler."""
    _settings(config)
    from .scheduler import run_scheduler

    run_scheduler(config, schedule)


@app.command()
def cleanup(config: ConfigOption = None, dry_run: bool = True) -> None:
    settings = _settings(config)
    root = settings.video_directory.resolve()
    temporary = (root / "temporary").resolve()
    if root not in temporary.parents:
        raise typer.BadParameter("unsafe cleanup path")
    items = [path for path in temporary.iterdir()] if temporary.exists() else []
    if not dry_run:
        for path in items:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
    typer.echo(json.dumps({"dry_run": dry_run, "candidates": len(items)}))


@app.command("print-schedule-example")
def print_schedule_example() -> None:
    typer.echo("# Home Assistant automation examples are in docs/SCHEDULING.md")


if __name__ == "__main__":
    app()
