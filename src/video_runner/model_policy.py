from __future__ import annotations

import os
from dataclasses import dataclass

from openai import APIError, OpenAI

from .config import GenerationConfig
from .personalization import external_disclosure_summary
from .schemas import PeriodType, Scene, Storyboard, Visual

# Verified against official OpenAI model pages on 2026-07-10. Runtime overrides are
# supported because prices and model availability change.
MODEL_PRICES_PER_MILLION: dict[str, tuple[float, float]] = {
    "gpt-5-nano": (0.05, 0.40),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-5.4-nano": (0.20, 1.25),
}


@dataclass(frozen=True)
class ModelResult:
    storyboard: Storyboard
    model: str
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    fallback_reason: str = ""


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    if model not in MODEL_PRICES_PER_MILLION:
        raise ValueError(f"No verified price is configured for {model}")
    input_price, output_price = MODEL_PRICES_PER_MILLION[model]
    return (input_tokens * input_price + output_tokens * output_price) / 1_000_000


def offline_storyboard(period: PeriodType) -> Storyboard:
    period_word = "daily" if period == PeriodType.DAILY else "weekly"
    narration = (
        f"Welcome to your {period_word} reflection, a private summary using only the categories you "
        "deliberately allowed and focusing on broad patterns rather than isolated readings; notice "
        "what felt steady, because consistency can offer useful context when no single number tells "
        "the whole story, then look for movement across the period and remember that change is an "
        "observation, not a diagnosis; consider what was happening around your routines, energy, "
        "rest, and activity, and choose one realistic action for the next period, such as protecting "
        "bedtime, taking a short walk, or planning a quiet pause; keep the experiment easy to repeat, "
        "compare the same broad signals next time, and remember that your data stays under your "
        "control while external services remain optional; this reflection is informational, not "
        "medical advice, so if anything concerns you, use your judgment and speak with a qualified "
        "professional; for now, carry forward one helpful observation and one kind next step."
    )
    scenes = [
        Scene(
            start_seconds=0,
            duration_seconds=10,
            scene_type="title",
            heading=f"Your {period_word.title()} Reflection",
            body="Private, calm, and descriptive.",
            visual=Visual(kind="gradient", data_reference="period"),
        ),
        Scene(
            start_seconds=10,
            duration_seconds=10,
            scene_type="metric",
            heading="What Stayed Steady",
            body="Look for useful consistency across allowed categories.",
            visual=Visual(kind="chart", data_reference="aggregates"),
        ),
        Scene(
            start_seconds=20,
            duration_seconds=10,
            scene_type="timeline",
            heading="What Shifted",
            body="Changes are observations, not diagnoses.",
            visual=Visual(kind="timeline", data_reference="trend"),
        ),
        Scene(
            start_seconds=30,
            duration_seconds=10,
            scene_type="reflection",
            heading="Add Context",
            body="Routines, rest, activity, and ordinary events all matter.",
            visual=Visual(kind="icon_grid", data_reference="context"),
        ),
        Scene(
            start_seconds=40,
            duration_seconds=10,
            scene_type="recommendation",
            heading="One Kind Next Step",
            body="Choose something small, realistic, and repeatable.",
            visual=Visual(kind="gradient", data_reference="recommendation"),
        ),
        Scene(
            start_seconds=50,
            duration_seconds=10,
            scene_type="closing",
            heading="Keep Learning Gently",
            body="Your data stays under your control.",
            visual=Visual(kind="gradient", data_reference="closing"),
        ),
    ]
    return Storyboard(
        title=f"Your {period_word.title()} Reflection",
        period_type=period,
        summary="A privacy-controlled reflection built from allowed aggregate categories.",
        narration=narration,
        scenes=scenes,
        safety_notes=["Descriptive only", "Not medical advice"],
        data_categories_used=[],
    )


def personalized_storyboard(period: PeriodType, summary: dict[str, object]) -> Storyboard:
    highlights_value = summary.get("highlights")
    highlights = (
        [item for item in highlights_value if isinstance(item, dict)]
        if isinstance(highlights_value, list)
        else []
    )
    if not highlights:
        return offline_storyboard(period)
    period_word = "daily" if period == PeriodType.DAILY else "weekly"
    narration = (
        f"Welcome to your {period_word} Home Assistant reflection. The cards on screen were built "
        "locally from your own current sensor states and the readings recorded during this period. "
        "Start with the first highlighted signal, then compare its current value with its recent "
        "direction. Move through the next cards slowly, noticing what changed, what stayed steady, "
        "and which readings may reflect ordinary routines in your home. A shift is context, not a "
        "diagnosis, and a single value rarely tells the whole story. Use these observations to "
        "choose one small, practical next step, such as checking a device, adjusting a routine, or "
        "simply watching the pattern for another period. Your Supervisor credential was used only "
        "inside Home Assistant and was not placed in this video. The spoken narration contains no "
        "sensor names or values; your personal details appear only on the private visual cards. "
        "Keep the comparison gentle, repeatable, and useful, and seek qualified help if a reading "
        "genuinely concerns you."
    )

    def count(key: str) -> int:
        value = summary.get(key, 0)
        return value if isinstance(value, int) else 0

    discovered = count("discovered_sensor_count")
    usable = count("usable_sensor_count")
    historical = count("history_sensor_count")

    def heading(item: dict[str, object]) -> str:
        return str(item.get("label", "Personal sensor"))[:80]

    def body(item: dict[str, object]) -> str:
        current = str(item.get("current", "available"))
        detail = str(item.get("detail", "current reading"))
        return f"Now {current}. {detail.capitalize()}."[:240]

    cards = highlights[:4]
    scenes = [
        Scene(
            start_seconds=0,
            duration_seconds=10,
            scene_type="title",
            heading=f"Your {period_word.title()} Sensor Story",
            body=(
                f"Read {discovered} Home Assistant sensors; {usable} have usable current states "
                f"and {historical} have {period_word} history."
            ),
            visual=Visual(kind="gradient", data_reference="personal-counts"),
        )
    ]
    for index, item in enumerate(cards, start=1):
        scenes.append(
            Scene(
                start_seconds=index * 10,
                duration_seconds=10,
                scene_type="metric",
                heading=heading(item),
                body=body(item),
                visual=Visual(kind="chart", data_reference=f"personal-highlight-{index}"),
            )
        )
    while len(scenes) < 5:
        scenes.append(
            Scene(
                start_seconds=len(scenes) * 10,
                duration_seconds=10,
                scene_type="reflection",
                heading="More of Your Sensors",
                body=f"All {discovered} discovered sensors were considered locally for this story.",
                visual=Visual(kind="icon_grid", data_reference="personal-coverage"),
            )
        )
    extra = highlights[4:5]
    closing_body = (
        f"Also highlighted: {heading(extra[0])} is now {extra[0].get('current', 'available')}."
        if extra
        else f"All {discovered} discovered sensors were considered; the strongest signals are above."
    )
    scenes.append(
        Scene(
            start_seconds=50,
            duration_seconds=10,
            scene_type="closing",
            heading="Personal, Local, and Current",
            body=closing_body[:240],
            visual=Visual(kind="gradient", data_reference="privacy-boundary"),
        )
    )
    preview = "; ".join(
        f"{heading(item)} {item.get('current', 'available')}" for item in highlights[:3]
    )
    categories = list(dict.fromkeys(str(item.get("device_class", "sensor")) for item in highlights))
    return Storyboard(
        title=f"Your {period_word.title()} Sensor Story",
        period_type=period,
        summary=(
            f"Personalized locally from {discovered} Home Assistant sensors. Highlights: {preview}"
        )[:400],
        narration=narration,
        scenes=scenes,
        safety_notes=["Descriptive only", "Not medical advice", "Personal values stay visual"],
        data_categories_used=categories[:20],
    )


def generate_storyboard(
    period: PeriodType, summary: dict[str, object], config: GenerationConfig
) -> ModelResult:
    if config.provider == "offline":
        return ModelResult(personalized_storyboard(period, summary), "offline-personal", 0, 0, 0.0)
    if config.provider != "openai":
        raise ValueError("generation.provider must be offline or openai")
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        if config.offline_fallback:
            return ModelResult(
                personalized_storyboard(period, summary),
                "offline-personal",
                0,
                0,
                0.0,
                "OpenAI credential unavailable",
            )
        raise RuntimeError("OPENAI_API_KEY is unavailable")
    candidates = [config.preferred_model or "gpt-5-nano", *config.fallback_models]
    client = OpenAI(api_key=api_key)
    last_error = ""
    reserved_cost = 0.0
    safe_summary = external_disclosure_summary(summary)
    user_content = f"Period: {period.value}. Count-only summary: {safe_summary}"
    # One token per character plus system overhead is deliberately pessimistic.
    bounded_input_tokens = len(user_content) + 300
    for model in dict.fromkeys(candidates):
        projected = estimate_cost(model, bounded_input_tokens, 1200)
        if reserved_cost + projected > config.maximum_estimated_cost_usd:
            raise RuntimeError("Projected generation cost exceeds configured cap")
        for _attempt in range(2):
            if reserved_cost + projected > config.maximum_estimated_cost_usd:
                raise RuntimeError("Cumulative retry reservation exceeds configured cost cap")
            reserved_cost += projected
            try:
                response = client.responses.parse(
                    model=model,
                    input=[
                        {
                            "role": "system",
                            "content": "Create a safe 60-second descriptive reflection. Use 145-160 narration words. Return only the schema.",
                        },
                        {"role": "user", "content": user_content},
                    ],
                    text_format=Storyboard,
                    max_output_tokens=1200,
                )
                if response.output_parsed is None:
                    raise ValueError("model returned no parsed storyboard")
                usage = response.usage
                input_tokens = int(getattr(usage, "input_tokens", 0))
                output_tokens = int(getattr(usage, "output_tokens", 0))
                cost = estimate_cost(model, input_tokens, output_tokens)
                if cost > config.maximum_estimated_cost_usd:
                    raise RuntimeError("Actual generation cost exceeds configured cap")
                return ModelResult(
                    response.output_parsed,
                    model,
                    input_tokens,
                    output_tokens,
                    max(cost, reserved_cost),
                    last_error,
                )
            except (ValueError, TypeError, APIError) as exc:
                last_error = type(exc).__name__
                continue
    if config.offline_fallback:
        return ModelResult(
            personalized_storyboard(period, summary),
            "offline-personal",
            0,
            0,
            0.0,
            last_error or "schema validation failed",
        )
    raise RuntimeError("No configured model produced a valid storyboard")
