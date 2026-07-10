from __future__ import annotations

import json
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from pydantic import TypeAdapter

from .schemas import BrowserVideo


def atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, default=str)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


@contextmanager
def render_lock(root: Path, stale_after: int = 7200) -> Iterator[None]:
    root.mkdir(parents=True, exist_ok=True)
    path = root / ".render.lock"
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        if time.time() - path.stat().st_mtime > stale_after:
            path.unlink(missing_ok=True)
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        else:
            raise RuntimeError("another render is already active") from exc
    try:
        os.write(descriptor, str(os.getpid()).encode("ascii"))
        yield
    finally:
        os.close(descriptor)
        path.unlink(missing_ok=True)


def rebuild_indexes(root: Path) -> dict[str, int]:
    adapter = TypeAdapter(BrowserVideo)
    entries: list[dict[str, object]] = []
    for period in ("daily", "weekly"):
        period_entries: list[dict[str, object]] = []
        for path in (root / period).glob("**/*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                video = adapter.validate_python(payload)
                base = path.parent
                if not all((base / filename).is_file() for filename in (video.video_filename, video.thumbnail_filename, video.captions_filename)):
                    continue
                item = video.model_dump(mode="json")
                item["relative_directory"] = str(path.parent.relative_to(root)).replace("\\", "/")
                period_entries.append(item)
            except (ValueError, OSError, json.JSONDecodeError):
                continue
        period_entries.sort(key=lambda item: str(item["created_at"]), reverse=True)
        atomic_json(root / "indexes" / f"{period}.json", period_entries)
        (root / "indexes" / f"{period}.json").chmod(0o644)
        entries.extend(period_entries)
    entries.sort(key=lambda item: str(item["created_at"]), reverse=True)
    atomic_json(root / "indexes" / "all.json", entries)
    (root / "indexes").chmod(0o755)
    (root / "indexes" / "all.json").chmod(0o644)
    return {"daily": sum(x["type"] == "daily" for x in entries), "weekly": sum(x["type"] == "weekly" for x in entries)}
