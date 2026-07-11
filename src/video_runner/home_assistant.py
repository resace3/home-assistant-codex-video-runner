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
                    try:
                        response.raise_for_status()
                    except httpx.HTTPStatusError as exc:
                        raise RuntimeError(
                            f"Home Assistant history request failed with HTTP {exc.response.status_code}"
                        ) from None
                    return response
            except (httpx.TimeoutException, httpx.NetworkError):
                if attempt == 3:
                    raise
            time.sleep(min(4.0, 0.5 * (2**attempt)))
        assert last_response is not None
        try:
            last_response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"Home Assistant history request failed with HTTP {exc.response.status_code}"
            ) from None
        return last_response

    def fetch_allowlisted_history(
        self,
        entity_ids: Iterable[str],
        *,
        period: str,
        daily_hours: int,
        weekly_days: int,
        max_observations_per_entity: int = 512,
        max_response_bytes: int = 2_000_000,
    ) -> dict[str, list[object]]:
        allowed = list(entity_ids)
        if not allowed:
            return {}
        for entity_id in allowed:
            if not entity_id.startswith(("sensor.", "binary_sensor.", "input_number.")):
                raise ValueError("entity allowlist contains a disallowed domain")
        delta = timedelta(hours=daily_hours) if period == "daily" else timedelta(days=weekly_days)
        start = (datetime.now(UTC) - delta).isoformat()
        result: dict[str, list[object]] = {entity_id: [] for entity_id in allowed}
        for entity_id in allowed:
            response = self._get(
                f"/history/period/{start}",
                params={
                    "filter_entity_id": entity_id,
                    "minimal_response": "true",
                    "no_attributes": "true",
                },
            )
            if len(response.content) > max_response_bytes:
                raise RuntimeError("Home Assistant history response exceeded the configured cap")
            for series in response.json():
                if not isinstance(series, list) or not series or not isinstance(series[0], dict):
                    continue
                series_entity = series[0].get("entity_id")
                if series_entity != entity_id:
                    continue
                states = [sample.get("state") for sample in series if isinstance(sample, dict)]
                if len(states) > max_observations_per_entity:
                    stride = max(1, len(states) // (max_observations_per_entity - 1))
                    states = states[::stride][: (max_observations_per_entity - 1)] + [states[-1]]
                result[entity_id] = states
        return result

    def __enter__(self) -> HomeAssistantClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
