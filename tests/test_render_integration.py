from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from video_runner.cli import app
from video_runner.render import validate_output


@pytest.mark.integration
def test_real_synthetic_daily_and_weekly_movies_match_viewer_contract(tmp_path: Path) -> None:
    share = tmp_path / "share"
    private = tmp_path / "private"
    config = tmp_path / "config.yaml"
    config.write_text(
        "\n".join(
            (
                f"video_directory: {share.as_posix()}",
                f"private_data_directory: {private.as_posix()}",
                "render:",
                "  width: 240",
                "  height: 426",
                "  fps: 12",
                "  preset: ultrafast",
            )
        ),
        encoding="utf-8",
    )
    result = CliRunner().invoke(
        app,
        ["generate-demo", "--config", str(config), "--mock-tts"],
        env={"VIDEO_RUNNER_TEST_MODE": "1", "OPENAI_API_KEY": "", "SUPERVISOR_TOKEN": ""},
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert {item["type"] for item in payload["items"]} == {"daily", "weekly"}
    catalog_path = share / "indexes" / "all.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    assert len(catalog) == 2
    assert {item["type"] for item in catalog} == {"daily", "weekly"}
    for item in catalog:
        folder = share / Path(item["relative_directory"])
        assert (folder / f"{item['id']}.json").is_file()
        assert item["video_filename"].startswith(f"{item['id']}-")
        assert (folder / item["thumbnail_filename"]).is_file()
        assert (folder / item["captions_filename"]).is_file()
        report = validate_output(folder / item["video_filename"])
        assert 55 <= report["duration_seconds"] <= 65
        assert report["audio"] is True
        assert report["validation_backend"] == "moviepy+ffprobe+ffmpeg-decode"
