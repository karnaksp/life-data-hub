"""Outdoor readiness scoring."""

from __future__ import annotations

from dataclasses import dataclass

from lifehub.weather import WeatherHour


@dataclass(frozen=True)
class ReadinessScore:
    activity: str
    location_id: str
    score: int
    decision: str
    explanation: str


def score_readiness(hours: list[WeatherHour], scoring_config: dict) -> list[ReadinessScore]:
    if not hours:
        return []
    daylight = [hour for hour in hours if hour.is_day] or hours
    window = daylight[:8]
    return [
        score_skate(window, scoring_config),
        score_snowboard(window, scoring_config),
        score_moto(window, scoring_config),
        score_volleyball(window, scoring_config),
    ]


def score_skate(hours: list[WeatherHour], config: dict) -> ReadinessScore:
    rules = config.get("skate", {})
    score = 100
    reasons: list[str] = []
    rain = sum(hour.rain_mm + hour.precipitation_mm for hour in hours)
    wind = max(hour.wind_gust_kmh for hour in hours)
    min_temp = min(hour.temperature_c for hour in hours)
    if rain > float(rules.get("max_wet_mm", 0.2)):
        score -= 45
        reasons.append("wet pavement risk")
    if wind > float(rules.get("max_wind_gust_kmh", 35)):
        score -= 20
        reasons.append("strong gusts")
    if min_temp < float(rules.get("min_temp_c", 2)):
        score -= 25
        reasons.append("freezing or slush risk")
    return make_score("skate", hours[0].location_id, score, reasons)


def score_snowboard(hours: list[WeatherHour], config: dict) -> ReadinessScore:
    rules = config.get("snowboard", {})
    score = 40
    reasons: list[str] = []
    snow = max(hour.snow_depth_cm for hour in hours)
    snowfall = sum(hour.snowfall_cm for hour in hours)
    max_temp = max(hour.temperature_c for hour in hours)
    wind = max(hour.wind_gust_kmh for hour in hours)
    rain = sum(hour.rain_mm for hour in hours)
    if snow >= float(rules.get("min_snow_depth_cm", 5)) or snowfall >= 1:
        score += 35
        reasons.append("snow base or fresh snowfall")
    if max_temp > float(rules.get("max_temp_c", 2)):
        score -= 25
        reasons.append("thaw risk")
    if rain > 0:
        score -= 25
        reasons.append("rain degrades snow")
    if wind > float(rules.get("max_wind_gust_kmh", 45)):
        score -= 15
        reasons.append("windy lift/session conditions")
    return make_score("snowboard", hours[0].location_id, score, reasons)


def score_moto(hours: list[WeatherHour], config: dict) -> ReadinessScore:
    rules = config.get("moto", {})
    score = 100
    reasons: list[str] = []
    precipitation = sum(hour.precipitation_mm for hour in hours)
    wind = max(hour.wind_gust_kmh for hour in hours)
    min_visibility = min(hour.visibility_m for hour in hours)
    min_temp = min(hour.temperature_c for hour in hours)
    if precipitation > float(rules.get("max_precipitation_mm", 0.2)):
        score -= 35
        reasons.append("precipitation")
    if wind > float(rules.get("max_wind_gust_kmh", 40)):
        score -= 25
        reasons.append("wind gusts")
    if min_visibility < float(rules.get("min_visibility_m", 5000)):
        score -= 20
        reasons.append("low visibility")
    if min_temp < float(rules.get("min_temp_c", 3)):
        score -= 25
        reasons.append("cold road surface")
    return make_score("moto_lesson", hours[0].location_id, score, reasons)


def score_volleyball(hours: list[WeatherHour], config: dict) -> ReadinessScore:
    rules = config.get("volleyball", {})
    score = 80
    reasons: list[str] = ["indoor session is mostly readiness-driven"]
    heat = max(hour.temperature_c for hour in hours)
    if heat > float(rules.get("max_outdoor_temp_c", 28)):
        score -= 10
        reasons.append("hot outdoor conditions")
    return make_score("volleyball", hours[0].location_id, score, reasons)


def make_score(activity: str, location_id: str, score: int, reasons: list[str]) -> ReadinessScore:
    bounded = max(0, min(100, score))
    if bounded >= 75:
        decision = "go"
    elif bounded >= 50:
        decision = "caution"
    else:
        decision = "skip"
    explanation = ", ".join(reasons) if reasons else "conditions look usable"
    return ReadinessScore(activity, location_id, bounded, decision, explanation)


def render_digest(scores: list[ReadinessScore]) -> str:
    if not scores:
        return "LifeHub: no weather data available yet."
    best_by_activity: dict[str, ReadinessScore] = {}
    for score in scores:
        current = best_by_activity.get(score.activity)
        if current is None or score.score > current.score:
            best_by_activity[score.activity] = score
    ranked = sorted(best_by_activity.values(), key=lambda item: item.score, reverse=True)
    best = ranked[0]
    lines = [
        f"LifeHub today: {best.activity} is the best option ({best.score}/100, {best.decision}).",
        "",
        "Outdoor readiness:",
    ]
    for score in ranked:
        lines.append(
            f"- {score.activity}: {score.score}/100, {score.decision} — {score.explanation}"
        )
    lines.append("")
    lines.append("Log after session: /log activity intensity mood fatigue result notes")
    return "\n".join(lines)
