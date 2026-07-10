from __future__ import annotations

import os
import time
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

import httpx


class HomeAssistantClient:
    def __init__(
        self, token: str | None = None, base_url: str = "http://supervisor/core/api"
    ) -> None:
        self._token = token or os.environ.get("SUPERVISOR_TOKEN", "")
        if not self._token:
            raise RuntimeError("SUPERVISOR_TOKEN is unavailable in this supervised runtime")
        self._client = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {self._token}"},
            timeout=httpx.Timeout(15),
        )

    def close(self) -> None:
        self._client.close()

    def _get(self, path: str, *, params: dict[str, str]) -> httpx.Response:
        last_response: httpx.Response | None = None
        for attempt in range(4):
            try:
                response = self._client.get(path, params=params)
                last_response = response
                if response.status_code not in {429, 500, 502, 503, 504}:
                    response.raise_for_status()
                    return response
            except (httpx.TimeoutException, httpx.NetworkError):
                if attempt == 3:
                    raise
            time.sleep(min(4.0, 0.5 * (2**attempt)))
        assert last_response is not None
        last_response.raise_for_status()
        return last_response

    def fetch_allowlisted_history(
        self, entity_ids: Iterable[str], *, period: str, daily_hours: int, weekly_days: int
    ) -> dict[str, list[object]]:
        allowed = list(entity_ids)
        if not allowed:
            return {}
        for entity_id in allowed:
            if not entity_id.startswith(("sensor.", "binary_sensor.", "input_number.")):
                raise ValueError("entity allowlist contains a disallowed domain")
        delta = timedelta(hours=daily_hours) if period == "daily" else timedelta(days=weekly_days)
        start = (datetime.now(UTC) - delta).isoformat()
        response = self._get(
            f"/history/period/{start}",
            params={
                "filter_entity_id": ",".join(allowed),
                "minimal_response": "true",
                "no_attributes": "true",
            },
        )
        result: dict[str, list[object]] = {entity_id: [] for entity_id in allowed}
        for series in response.json():
            if not isinstance(series, list) or not series or not isinstance(series[0], dict):
                continue
            series_entity = series[0].get("entity_id")
            if not isinstance(series_entity, str) or series_entity not in result:
                continue
            for sample in series:
                if not isinstance(sample, dict):
                    continue
                result[series_entity].append(sample.get("state"))
        return result

    def __enter__(self) -> HomeAssistantClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
