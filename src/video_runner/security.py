from __future__ import annotations

import logging
import os
import re
import statistics
from collections.abc import Mapping
from pathlib import Path

TOKEN_PATTERNS = (
    re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;]+"),
    re.compile(r"(?i)((?:api[_-]?key|cookie|token)\s*[:=]\s*)[^\s,;]+"),
    re.compile(r"\b[A-Za-z0-9_-]{40,}\b"),
)


def redact(value: object, sensitive_values: tuple[str, ...] = ()) -> str:
    text = str(value)
    for secret in sensitive_values:
        if secret:
            text = text.replace(secret, "[REDACTED]")
    for pattern in TOKEN_PATTERNS:
        if pattern.groups:
            text = pattern.sub(r"\1[REDACTED]", text)
        else:
            text = pattern.sub("[REDACTED]", text)
    return text


class RedactingFilter(logging.Filter):
    def __init__(self, sensitive_values: tuple[str, ...] = ()) -> None:
        super().__init__()
        self.sensitive_values = sensitive_values

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage(), self.sensitive_values)
        record.args = ()
        return True


def configure_logging(sensitive_values: tuple[str, ...] = ()) -> None:
    handler = logging.StreamHandler()
    handler.addFilter(RedactingFilter(sensitive_values))
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)


def aggregate_history(histories: Mapping[str, list[object]]) -> dict[str, object]:
    """Return bounded period aggregates; never return an individual reading."""
    categories: dict[str, dict[str, float | int]] = {}
    for index, (_, raw_values) in enumerate(histories.items(), start=1):
        values: list[float] = []
        for raw in raw_values:
            try:
                values.append(float(str(raw)))
            except (TypeError, ValueError):
                continue
        if len(values) < 2:
            continue
        categories[f"metric_{index}"] = {
            "median": round(statistics.median(values), 2),
            "minimum": round(min(values), 2),
            "maximum": round(max(values), 2),
            "change": round(values[-1] - values[0], 2),
            "observations": len(values),
        }
    return {"schema_version": 1, "metrics": categories}


def scrub_supervisor_environment() -> None:
    """Remove the Supervisor credential before importing or calling provider code."""
    os_token = os.environ.pop("SUPERVISOR_TOKEN", None)
    if os_token:
        del os_token
    # Replace handlers so no redaction filter retains the credential in memory.
    configure_logging(())


def validate_runtime_roots(video_root: Path, private_root: Path, *, test_mode: bool) -> None:
    if test_mode:
        return
    if video_root != Path("/share/personal_video_studio"):
        raise ValueError("production video_directory must be /share/personal_video_studio")
    if private_root != Path("/data/personal_video_studio"):
        raise ValueError("production private_data_directory must be /data/personal_video_studio")
