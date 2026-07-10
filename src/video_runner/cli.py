from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Annotated

import typer

from .config import Settings, load_settings
from .home_assistant import HomeAssistantClient
from .schemas import PeriodType, PrivateAudit
from .security import (
    aggregate_history,
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
        return aggregate_history({"synthetic.one": [7.1, 7.5, 7.9], "synthetic.two": [39, 42, 44]})
    with HomeAssistantClient() as client:
        histories = client.fetch_allowlisted_history(
            settings.data.entity_allowlist,
            period=period.value,
            daily_hours=settings.data.history_hours_daily,
            weekly_days=settings.data.history_days_weekly,
        )
    return aggregate_history(histories)


@app.command()
def doctor(config: ConfigOption = None, test_tts: bool = False) -> None:
    """Check runtime, storage, Supervisor, ffmpeg, Codex, and the exact requested voice."""
    settings = _settings(config)
    checks = {
        "supervisor_token_present": bool(os.environ.get("SUPERVISOR_TOKEN")),
        "codex_cli": shutil.which("codex") is not None,
        "ffmpeg": shutil.which("ffmpeg") is not None,
        "video_directory_parent_exists": settings.video_directory.parent.exists(),
        "requested_voice_name": settings.tts.requested_voice_name,
        "requested_voice_id": settings.tts.requested_voice_id,
    }
    if test_tts:
        import asyncio

        scrub_supervisor_environment()
        from .tts import resolve_voice

        checks["resolved_voice_id"] = asyncio.run(resolve_voice(settings.tts))
    typer.echo(json.dumps(checks, indent=2))


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
        json.dumps({"period": period.value, "external_disclosure_preview": minimized}, indent=2)
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


@app.command("validate-output")
def validate_output_command(path: Path) -> None:
    from .render import validate_output

    typer.echo(json.dumps(validate_output(path), indent=2))


@app.command("rebuild-index")
def rebuild_index(config: ConfigOption = None) -> None:
    typer.echo(json.dumps(rebuild_indexes(_settings(config).video_directory), indent=2))


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
