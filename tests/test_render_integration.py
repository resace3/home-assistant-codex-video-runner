from __future__ import annotations

from pathlib import Path

import pytest

from video_runner.config import RenderConfig, Settings
from video_runner.model_policy import offline_storyboard
from video_runner.render import render_storyboard, validate_output
from video_runner.schemas import PeriodType


@pytest.mark.integration
def test_real_synthetic_one_minute_movie(tmp_path: Path) -> None:
    settings = Settings(
        video_directory=tmp_path / "share",
        private_data_directory=tmp_path / "private",
        render=RenderConfig(width=240, height=426, fps=12, preset="ultrafast"),
    )
    item = render_storyboard(offline_storyboard(PeriodType.DAILY), settings, use_test_tone=True)
    video = next((settings.video_directory / "daily").glob("**/*.mp4"))
    report = validate_output(video)
    assert 55 <= report["duration_seconds"] <= 65
    assert report["audio"] is True
    assert item.captions_filename.endswith(".vtt")
