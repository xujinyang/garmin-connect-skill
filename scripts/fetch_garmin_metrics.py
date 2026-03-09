#!/usr/bin/env python3
"""Fetch normalized Garmin Connect metrics for agent workflows."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable


def _lazy_imports():
    try:
        from garth.exc import GarthException, GarthHTTPError
        from garminconnect import Garmin, GarminConnectAuthenticationError
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Missing dependency. Install with: python3 -m pip install garminconnect garth requests"
        ) from exc

    return Garmin, GarminConnectAuthenticationError, GarthException, GarthHTTPError


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch normalized Garmin Connect metrics as JSON."
    )
    parser.add_argument(
        "--metric",
        required=True,
        choices=[
            "sleep",
            "heart-rate",
            "stress",
            "steps",
            "floors",
            "intensity-minutes",
            "weight",
            "blood-pressure",
            "spo2",
            "respiration",
            "body-battery",
            "summary",
            "hrv",
            "fitness-age",
            "training-status",
            "training-readiness",
            "race-predictions",
            "max-metrics",
            "cycling-ftp",
            "lactate-threshold",
            "all",
            "init-archive",
        ],
        help="Metric to fetch. Use 'all' to fetch every metric for the given date or range. Use 'init-archive' to initialize a local archive.",
    )
    parser.add_argument("--date", help="Single date in YYYY-MM-DD format.")
    parser.add_argument("--start-date", help="Start date in YYYY-MM-DD format.")
    parser.add_argument("--end-date", help="End date in YYYY-MM-DD format.")
    parser.add_argument(
        "--archive-dir",
        default="garmin_archive",
        help="Directory for archive files (only used for init-archive metric).",
    )
    parser.add_argument(
        "--include-raw",
        action="store_true",
        help="Include raw Garmin payloads inside the normalized response.",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output.",
    )
    args = parser.parse_args()

    if args.date and (args.start_date or args.end_date):
        parser.error("Use either --date or --start-date/--end-date, not both.")
    if bool(args.start_date) != bool(args.end_date):
        parser.error("Both --start-date and --end-date are required for a range.")

    return args


def parse_date(text: str) -> date:
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"Invalid date '{text}'. Expected YYYY-MM-DD.") from exc


def resolve_dates(args: argparse.Namespace) -> tuple[date, date]:
    if args.date:
        day = parse_date(args.date)
        return day, day
    if args.start_date and args.end_date:
        start_day = parse_date(args.start_date)
        end_day = parse_date(args.end_date)
        if end_day < start_day:
            raise ValueError("--end-date must be on or after --start-date.")
        return start_day, end_day
    today = date.today()
    return today, today


def iter_days(start_day: date, end_day: date) -> list[date]:
    current = start_day
    days: list[date] = []
    while current <= end_day:
        days.append(current)
        current += timedelta(days=1)
    return days


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def to_number(value: Any) -> int | float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        try:
            if "." in value:
                return float(value)
            return int(value)
        except ValueError:
            return None
    return None


def round_number(value: Any, digits: int = 2) -> float | None:
    number = to_number(value)
    if number is None:
        return None
    return round(float(number), digits)


def pick_first(mapping: Any, *keys: str) -> Any:
    if not isinstance(mapping, dict):
        return None
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return None


def timestamp_to_iso(value: Any) -> str | None:
    number = to_number(value)
    if number is None:
        return value if isinstance(value, str) else None
    try:
        timestamp = float(number)
        if timestamp > 1_000_000_000_000:
            timestamp /= 1000
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def flatten_numeric_values(value: Any) -> list[float]:
    values: list[float] = []

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            for child in node.values():
                visit(child)
            return
        if isinstance(node, (list, tuple)):
            for child in node:
                visit(child)
            return
        number = to_number(node)
        if number is None:
            return
        number = float(number)
        if number >= 0:
            values.append(number)

    visit(value)
    return values


def extract_series_values(value: Any) -> list[float]:
    values: list[float] = []

    if isinstance(value, dict):
        for item in value.values():
            number = to_number(item)
            if number is not None and float(number) >= 0:
                values.append(float(number))
        return values

    if isinstance(value, list):
        for item in value:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                number = to_number(item[1])
            else:
                number = to_number(item)
            if number is not None and float(number) >= 0:
                values.append(float(number))
        return values

    return flatten_numeric_values(value)


def summarize_series(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"samples": 0, "minimum": None, "maximum": None, "average": None}
    return {
        "samples": len(values),
        "minimum": round(min(values), 2),
        "maximum": round(max(values), 2),
        "average": round(sum(values) / len(values), 2),
    }


def compact_dict(mapping: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in mapping.items() if value is not None}


def mark_no_data(result: dict[str, Any]) -> dict[str, Any]:
    if set(result.keys()) <= {"date", "metric"}:
        result["no_data"] = True
    return result


def normalize_sleep(date_str: str, raw: Any, include_raw: bool) -> dict[str, Any]:
    payload = raw.get("dailySleepDTO") if isinstance(raw, dict) else raw
    payload = payload if isinstance(payload, dict) else {}

    total_sleep_seconds = pick_first(
        payload, "sleepTimeSeconds", "sleepTimeSecs", "totalSleepSeconds"
    )
    result = compact_dict(
        {
            "date": date_str,
            "metric": "sleep",
            "total_sleep_seconds": to_number(total_sleep_seconds),
            "total_sleep_hours": round_number(
                (to_number(total_sleep_seconds) or 0) / 3600 if total_sleep_seconds is not None else None
            ),
            "sleep_score": to_number(
                pick_first(payload, "sleepScore", "overallSleepScore", "overallSleepScoreValue")
            ),
            "bed_time": timestamp_to_iso(
                pick_first(
                    payload,
                    "sleepStartTimestampLocal",
                    "sleepStartTimestampGMT",
                    "sleepStartTimestamp",
                )
            ),
            "wake_time": timestamp_to_iso(
                pick_first(
                    payload,
                    "sleepEndTimestampLocal",
                    "sleepEndTimestampGMT",
                    "sleepEndTimestamp",
                )
            ),
            "deep_sleep_seconds": to_number(pick_first(payload, "deepSleepSeconds")),
            "light_sleep_seconds": to_number(pick_first(payload, "lightSleepSeconds")),
            "rem_sleep_seconds": to_number(pick_first(payload, "remSleepSeconds")),
            "awake_sleep_seconds": to_number(
                pick_first(payload, "awakeSleepSeconds", "awakeTimeSeconds")
            ),
            "nap_sleep_seconds": to_number(pick_first(payload, "napTimeSeconds")),
        }
    )
    if include_raw:
        result["raw"] = raw
    return result


def normalize_floors(date_str: str, raw: Any, include_raw: bool) -> dict[str, Any]:
    payload = raw if isinstance(raw, dict) else {}
    values = payload.get("floorValuesArray") if isinstance(payload.get("floorValuesArray"), list) else []
    ascended = 0
    descended = 0
    non_zero_samples = 0
    for item in values:
        if isinstance(item, (list, tuple)) and len(item) >= 4:
            up = to_number(item[2]) or 0
            down = to_number(item[3]) or 0
            ascended += int(up)
            descended += int(down)
            if up or down:
                non_zero_samples += 1

    result = compact_dict(
        {
            "date": date_str,
            "metric": "floors",
            "floors_ascended": ascended,
            "floors_descended": descended,
            "samples": len(values),
            "active_floor_samples": non_zero_samples,
        }
    )
    result = mark_no_data(result)
    if include_raw:
        result["raw"] = raw
    return result


def normalize_intensity_minutes(date_str: str, raw: Any, include_raw: bool) -> dict[str, Any]:
    payload = raw if isinstance(raw, dict) else {}
    moderate = to_number(pick_first(payload, "moderateMinutes"))
    vigorous = to_number(pick_first(payload, "vigorousMinutes"))
    total = None
    if moderate is not None or vigorous is not None:
        total = (moderate or 0) + 2 * (vigorous or 0)

    result = compact_dict(
        {
            "date": date_str,
            "metric": "intensity-minutes",
            "moderate_minutes": moderate,
            "vigorous_minutes": vigorous,
            "daily_total": total,
            "weekly_moderate": to_number(pick_first(payload, "weeklyModerate")),
            "weekly_vigorous": to_number(pick_first(payload, "weeklyVigorous")),
            "weekly_total": to_number(pick_first(payload, "weeklyTotal")),
            "weekly_goal": to_number(pick_first(payload, "weekGoal")),
        }
    )
    result = mark_no_data(result)
    if include_raw:
        result["raw"] = raw
    return result


def normalize_heart_rate(date_str: str, raw: Any, include_raw: bool) -> dict[str, Any]:
    payload = raw if isinstance(raw, dict) else {}
    series = extract_series_values(
        pick_first(payload, "heartRateValues", "allDayHeartRateValues")
    )
    summary = summarize_series(series)

    result = compact_dict(
        {
            "date": date_str,
            "metric": "heart-rate",
            "resting_heart_rate": to_number(
                pick_first(payload, "restingHeartRate", "restingHeartRateValue")
            ),
            "minimum_heart_rate": to_number(
                pick_first(payload, "minHeartRate", "minimumHeartRate")
            )
            or summary["minimum"],
            "maximum_heart_rate": to_number(
                pick_first(payload, "maxHeartRate", "maximumHeartRate")
            )
            or summary["maximum"],
            "average_heart_rate": summary["average"],
            "samples": summary["samples"],
        }
    )
    if include_raw:
        result["raw"] = raw
    return result


def normalize_stress(date_str: str, raw: Any, include_raw: bool) -> dict[str, Any]:
    summary_payload = raw.get("summary") if isinstance(raw, dict) else None
    detail_payload = raw.get("detail") if isinstance(raw, dict) else None
    summary_payload = summary_payload if isinstance(summary_payload, dict) else {}
    detail_payload = detail_payload if isinstance(detail_payload, dict) else {}

    series_source = (
        pick_first(detail_payload, "allDayStress", "stressValuesArray", "stressValues")
        or pick_first(summary_payload, "allDayStress", "stressValuesArray", "stressValues")
        or detail_payload
        or summary_payload
    )
    series = extract_series_values(series_source)
    series_summary = summarize_series(series)

    result = compact_dict(
        {
            "date": date_str,
            "metric": "stress",
            "overall_stress_level": to_number(
                pick_first(
                    summary_payload,
                    "overallStressLevel",
                    "averageStressLevel",
                    "stressLevel",
                )
            )
            or series_summary["average"],
            "maximum_stress_level": to_number(
                pick_first(summary_payload, "maxStressLevel", "maximumStressLevel")
            )
            or series_summary["maximum"],
            "rest_stress_duration_seconds": to_number(
                pick_first(summary_payload, "restStressDuration")
            ),
            "low_stress_duration_seconds": to_number(
                pick_first(summary_payload, "lowStressDuration")
            ),
            "medium_stress_duration_seconds": to_number(
                pick_first(summary_payload, "mediumStressDuration")
            ),
            "high_stress_duration_seconds": to_number(
                pick_first(summary_payload, "highStressDuration")
            ),
            "samples": series_summary["samples"],
        }
    )
    if include_raw:
        result["raw"] = raw
    return result


def normalize_steps(date_str: str, raw: Any, include_raw: bool) -> dict[str, Any]:
    summary_payload = raw.get("summary") if isinstance(raw, dict) else None
    steps_payload = raw.get("steps_data") if isinstance(raw, dict) else None
    summary_payload = summary_payload if isinstance(summary_payload, dict) else {}
    steps_payload = steps_payload if isinstance(steps_payload, dict) else {}

    total_steps = to_number(
        pick_first(summary_payload, "totalSteps", "steps", "dailyStepCount")
    )
    daily_goal = to_number(
        pick_first(summary_payload, "dailyStepGoal", "stepGoal", "goal")
    )
    goal_completion = None
    if total_steps is not None and daily_goal:
        goal_completion = round((float(total_steps) / float(daily_goal)) * 100, 2)

    result = compact_dict(
        {
            "date": date_str,
            "metric": "steps",
            "total_steps": total_steps,
            "daily_step_goal": daily_goal,
            "goal_completion_percent": goal_completion,
            "distance_meters": to_number(
                pick_first(summary_payload, "totalDistanceMeters", "distanceInMeters")
            ),
            "calories": to_number(
                pick_first(summary_payload, "totalKilocalories", "kilocalories")
            ),
            "floors_climbed": to_number(pick_first(summary_payload, "floorsClimbed")),
            "step_samples": len(flatten_numeric_values(steps_payload)),
        }
    )
    if include_raw:
        result["raw"] = raw
    return result


def normalize_weight(date_str: str, raw: Any, include_raw: bool) -> dict[str, Any]:
    payload = raw if isinstance(raw, dict) else {}
    entries = payload.get("dateWeightList") if isinstance(payload.get("dateWeightList"), list) else []
    match = None
    for item in entries:
        if not isinstance(item, dict):
            continue
        item_date = item.get("date")
        if isinstance(item_date, str) and item_date.startswith(date_str):
            match = item
            break
    if match is None and len(entries) == 1 and isinstance(entries[0], dict):
        match = entries[0]

    result = compact_dict(
        {
            "date": date_str,
            "metric": "weight",
            "weight": round_number(pick_first(match or {}, "weight")),
            "bmi": round_number(pick_first(match or {}, "bmi")),
            "body_fat": round_number(pick_first(match or {}, "bodyFat")),
            "body_water": round_number(pick_first(match or {}, "bodyWater")),
            "bone_mass": round_number(pick_first(match or {}, "boneMass")),
            "muscle_mass": round_number(pick_first(match or {}, "muscleMass")),
            "physique_rating": round_number(pick_first(match or {}, "physiqueRating")),
            "visceral_fat": round_number(pick_first(match or {}, "visceralFat")),
            "metabolic_age": round_number(pick_first(match or {}, "metabolicAge")),
        }
    )
    result = mark_no_data(result)
    if include_raw:
        result["raw"] = raw
    return result


def normalize_blood_pressure(date_str: str, raw: Any, include_raw: bool) -> dict[str, Any]:
    payload = raw if isinstance(raw, dict) else {}
    summaries = (
        payload.get("measurementSummaries")
        if isinstance(payload.get("measurementSummaries"), list)
        else []
    )
    latest = summaries[-1] if summaries and isinstance(summaries[-1], dict) else {}

    result = compact_dict(
        {
            "date": date_str,
            "metric": "blood-pressure",
            "measurement_count": len(summaries),
            "systolic": to_number(
                pick_first(latest, "systolic", "systolicValue", "avgSystolic")
            ),
            "diastolic": to_number(
                pick_first(latest, "diastolic", "diastolicValue", "avgDiastolic")
            ),
            "pulse": to_number(pick_first(latest, "pulse", "pulseValue")),
        }
    )
    if len(summaries) == 0:
        result["no_data"] = True
    result = mark_no_data(result)
    if include_raw:
        result["raw"] = raw
    return result


def normalize_spo2(date_str: str, raw: Any, include_raw: bool) -> dict[str, Any]:
    payload = raw if isinstance(raw, dict) else {}
    result = compact_dict(
        {
            "date": date_str,
            "metric": "spo2",
            "average_spo2": to_number(pick_first(payload, "averageSpO2")),
            "lowest_spo2": to_number(pick_first(payload, "lowestSpO2")),
            "latest_spo2": to_number(pick_first(payload, "latestSpO2")),
            "last_seven_days_average_spo2": to_number(pick_first(payload, "lastSevenDaysAvgSpO2")),
            "average_sleep_spo2": to_number(pick_first(payload, "avgSleepSpO2")),
            "latest_spo2_timestamp": pick_first(payload, "latestSpO2TimestampLocal", "latestSpO2TimestampGMT"),
        }
    )
    result = mark_no_data(result)
    if include_raw:
        result["raw"] = raw
    return result


def normalize_respiration(date_str: str, raw: Any, include_raw: bool) -> dict[str, Any]:
    payload = raw if isinstance(raw, dict) else {}
    result = compact_dict(
        {
            "date": date_str,
            "metric": "respiration",
            "lowest_respiration": to_number(pick_first(payload, "lowestRespirationValue")),
            "highest_respiration": to_number(pick_first(payload, "highestRespirationValue")),
            "average_waking_respiration": to_number(pick_first(payload, "avgWakingRespirationValue")),
            "average_sleep_respiration": to_number(pick_first(payload, "avgSleepRespirationValue")),
        }
    )
    result = mark_no_data(result)
    if include_raw:
        result["raw"] = raw
    return result


def normalize_body_battery(date_str: str, raw: Any, include_raw: bool) -> dict[str, Any]:
    entries = raw if isinstance(raw, list) else [raw] if isinstance(raw, dict) else []
    match = None
    for item in entries:
        if isinstance(item, dict) and item.get("date") == date_str:
            match = item
            break
    if match is None and len(entries) == 1 and isinstance(entries[0], dict):
        match = entries[0]
    match = match or {}

    values = match.get("bodyBatteryValuesArray") if isinstance(match.get("bodyBatteryValuesArray"), list) else []
    levels = extract_series_values(values)
    summary = summarize_series(levels)

    result = compact_dict(
        {
            "date": date_str,
            "metric": "body-battery",
            "charged": to_number(pick_first(match, "charged")),
            "drained": to_number(pick_first(match, "drained")),
            "minimum_level": summary["minimum"],
            "maximum_level": summary["maximum"],
            "average_level": summary["average"],
            "samples": summary["samples"],
        }
    )
    result = mark_no_data(result)
    if include_raw:
        result["raw"] = raw
    return result


def normalize_summary(date_str: str, raw: Any, include_raw: bool) -> dict[str, Any]:
    summary_payload = raw.get("summary") if isinstance(raw, dict) else {}
    summary_payload = summary_payload if isinstance(summary_payload, dict) else {}

    result = compact_dict(
        {
            "date": date_str,
            "metric": "summary",
            "daily_summary": compact_dict(
                {
                    "active_seconds": to_number(pick_first(summary_payload, "activeSeconds")),
                    "moderate_intensity_minutes": to_number(
                        pick_first(summary_payload, "moderateIntensityMinutes")
                    ),
                    "vigorous_intensity_minutes": to_number(
                        pick_first(summary_payload, "vigorousIntensityMinutes")
                    ),
                    "calories": to_number(
                        pick_first(summary_payload, "totalKilocalories", "kilocalories")
                    ),
                }
            ),
            "steps": normalize_steps(
                date_str,
                {"summary": raw.get("summary"), "steps_data": raw.get("steps_data")},
                False,
            ),
            "sleep": normalize_sleep(date_str, raw.get("sleep"), False),
            "heart_rate": normalize_heart_rate(date_str, raw.get("heart_rate"), False),
            "stress": normalize_stress(date_str, raw.get("stress"), False),
        }
    )
    if include_raw:
        result["raw"] = raw
    return result


def normalize_hrv(date_str: str, raw: Any, include_raw: bool) -> dict[str, Any]:
    payload = raw.get("hrvSummary") if isinstance(raw, dict) else raw
    payload = payload if isinstance(payload, dict) else {}
    baseline = payload.get("baseline") if isinstance(payload.get("baseline"), dict) else {}

    result = compact_dict(
        {
            "date": date_str,
            "metric": "hrv",
            "weekly_average": to_number(pick_first(payload, "weeklyAvg", "weeklyAverage")),
            "last_night_average": to_number(pick_first(payload, "lastNightAvg")),
            "last_night_5min_high": to_number(pick_first(payload, "lastNight5MinHigh")),
            "status": pick_first(payload, "status"),
            "feedback_phrase": pick_first(payload, "feedbackPhrase"),
            "baseline_low_upper": to_number(pick_first(baseline, "lowUpper")),
            "baseline_balanced_low": to_number(pick_first(baseline, "balancedLow")),
            "baseline_balanced_upper": to_number(pick_first(baseline, "balancedUpper")),
        }
    )
    if include_raw:
        result["raw"] = raw
    return result


def normalize_training_status(date_str: str, raw: Any, include_raw: bool) -> dict[str, Any]:
    payload = raw if isinstance(raw, dict) else {}
    training_status = (
        payload.get("mostRecentTrainingStatus")
        if isinstance(payload.get("mostRecentTrainingStatus"), dict)
        else {}
    )
    acclimation = (
        payload.get("heatAltitudeAcclimationDTO")
        if isinstance(payload.get("heatAltitudeAcclimationDTO"), dict)
        else {}
    )

    result = compact_dict(
        {
            "date": date_str,
            "metric": "training-status",
            "vo2max": round_number(pick_first(payload, "mostRecentVO2Max")),
            "training_status": pick_first(training_status, "trainingStatusKey", "trainingStatus"),
            "training_load_balance": pick_first(
                payload.get("mostRecentTrainingLoadBalance", {})
                if isinstance(payload.get("mostRecentTrainingLoadBalance"), dict)
                else {},
                "trainingLoadBalanceCategory",
                "trainingLoadBalanceStatus",
            ),
            "heat_acclimation": round_number(
                pick_first(acclimation, "heatAcclimationPercentage", "heatAcclimation")
            ),
            "altitude_acclimation": round_number(
                pick_first(acclimation, "altitudeAcclimationPercentage", "altitudeAcclimation")
            ),
        }
    )
    result = mark_no_data(result)
    if include_raw:
        result["raw"] = raw
    return result


def normalize_training_readiness(date_str: str, raw: Any, include_raw: bool) -> dict[str, Any]:
    if isinstance(raw, list) and not raw:
        result = {"date": date_str, "metric": "training-readiness", "no_data": True}
        if include_raw:
            result["raw"] = raw
        return result

    payload = raw[0] if isinstance(raw, list) and raw and isinstance(raw[0], dict) else raw
    payload = payload if isinstance(payload, dict) else {}
    result = compact_dict(
        {
            "date": date_str,
            "metric": "training-readiness",
            "score": to_number(
                pick_first(payload, "value", "trainingReadiness", "readinessScore")
            ),
            "status": pick_first(payload, "status", "displayString"),
        }
    )
    result = mark_no_data(result)
    if include_raw:
        result["raw"] = raw
    return result


def normalize_race_predictions(date_str: str, raw: Any, include_raw: bool) -> dict[str, Any]:
    payload = raw if isinstance(raw, dict) else {}
    result = compact_dict(
        {
            "date": pick_first(payload, "calendarDate") or date_str,
            "metric": "race-predictions",
            "time_5k_seconds": to_number(pick_first(payload, "time5K")),
            "time_10k_seconds": to_number(pick_first(payload, "time10K")),
            "time_half_marathon_seconds": to_number(pick_first(payload, "timeHalfMarathon")),
            "time_marathon_seconds": to_number(pick_first(payload, "timeMarathon")),
        }
    )
    result = mark_no_data(result)
    if include_raw:
        result["raw"] = raw
    return result


def normalize_max_metrics(date_str: str, raw: Any, include_raw: bool) -> dict[str, Any]:
    payload = raw[0] if isinstance(raw, list) and raw and isinstance(raw[0], dict) else raw
    payload = payload if isinstance(payload, dict) else {}
    vo2_sources = [
        payload,
        payload.get("generic") if isinstance(payload.get("generic"), dict) else {},
        payload.get("cycling") if isinstance(payload.get("cycling"), dict) else {},
        payload.get("running") if isinstance(payload.get("running"), dict) else {},
    ]
    vo2max = None
    fitness_age = None
    for source in vo2_sources:
        vo2max = vo2max or round_number(pick_first(source, "vo2Max", "maxVO2", "maxVO2Value"))
        fitness_age = fitness_age or round_number(pick_first(source, "fitnessAge"))

    result = compact_dict(
        {
            "date": date_str,
            "metric": "max-metrics",
            "vo2max": vo2max,
            "fitness_age": fitness_age,
        }
    )
    result = mark_no_data(result)
    if include_raw:
        result["raw"] = raw
    return result


def normalize_cycling_ftp(date_str: str, raw: Any, include_raw: bool) -> dict[str, Any]:
    payload = raw[0] if isinstance(raw, list) and raw and isinstance(raw[0], dict) else raw
    payload = payload if isinstance(payload, dict) else {}
    result = compact_dict(
        {
            "date": (pick_first(payload, "calendarDate") or date_str)[:10] if isinstance(pick_first(payload, "calendarDate"), str) else date_str,
            "metric": "cycling-ftp",
            "functional_threshold_power": to_number(pick_first(payload, "functionalThresholdPower")),
            "sport": pick_first(payload, "sport"),
            "is_stale": pick_first(payload, "isStale"),
        }
    )
    result = mark_no_data(result)
    if include_raw:
        result["raw"] = raw
    return result


def normalize_lactate_threshold(date_str: str, raw: Any, include_raw: bool) -> dict[str, Any]:
    payload = raw if isinstance(raw, dict) else {}
    speed_hr = payload.get("speed_and_heart_rate") if isinstance(payload.get("speed_and_heart_rate"), dict) else {}
    power = payload.get("power") if isinstance(payload.get("power"), dict) else {}
    result = compact_dict(
        {
            "date": date_str,
            "metric": "lactate-threshold",
            "speed": round_number(pick_first(speed_hr, "speed")),
            "heart_rate": to_number(pick_first(speed_hr, "heartRate", "heartRateCycling")),
            "functional_threshold_power": to_number(pick_first(power, "functionalThresholdPower")),
            "power_to_weight": round_number(pick_first(power, "powerToWeight")),
            "sport": pick_first(power, "sport"),
            "is_stale": pick_first(power, "isStale"),
        }
    )
    result = mark_no_data(result)
    if include_raw:
        result["raw"] = raw
    return result


def normalize_fitness_age(date_str: str, raw: Any, include_raw: bool) -> dict[str, Any]:
    payload = raw if isinstance(raw, dict) else {}
    components = payload.get("components") if isinstance(payload.get("components"), dict) else {}

    result = compact_dict(
        {
            "date": date_str,
            "metric": "fitness-age",
            "chronological_age": to_number(pick_first(payload, "chronologicalAge")),
            "fitness_age": round_number(pick_first(payload, "fitnessAge")),
            "achievable_fitness_age": round_number(pick_first(payload, "achievableFitnessAge")),
            "previous_fitness_age": round_number(pick_first(payload, "previousFitnessAge")),
            "resting_heart_rate": to_number(
                pick_first(components.get("rhr", {}), "value")
                if isinstance(components.get("rhr"), dict)
                else None
            ),
            "bmi": round_number(
                pick_first(components.get("bmi", {}), "value")
                if isinstance(components.get("bmi"), dict)
                else None
            ),
            "vigorous_days_average": round_number(
                pick_first(components.get("vigorousDaysAvg", {}), "value")
                if isinstance(components.get("vigorousDaysAvg"), dict)
                else None
            ),
            "vigorous_minutes_average": round_number(
                pick_first(components.get("vigorousMinutesAvg", {}), "value")
                if isinstance(components.get("vigorousMinutesAvg"), dict)
                else None
            ),
            "last_updated": pick_first(payload, "lastUpdated"),
        }
    )
    if include_raw:
        result["raw"] = raw
    return result


def dump_tokens(client: Any, token_path: Path) -> None:
    garth_client = getattr(client, "garth", None)
    if garth_client is None or not hasattr(garth_client, "dump"):
        return
    token_path.mkdir(parents=True, exist_ok=True)
    garth_client.dump(str(token_path))


def authenticate() -> Any:
    Garmin, GarminConnectAuthenticationError, GarthException, GarthHTTPError = _lazy_imports()

    token_path = Path(os.getenv("GARMINTOKENS", "~/.garminconnect")).expanduser()
    token_files = [
        token_path / "oauth1_token.json",
        token_path / "oauth2_token.json",
    ]

    if any(path.exists() for path in token_files):
        try:
            client = Garmin()
            client.login(str(token_path))
            return client
        except Exception:
            pass

    email = os.getenv("GARMIN_EMAIL")
    password = os.getenv("GARMIN_PASSWORD")

    # Interactive prompt if credentials are not set
    if not email or not password:
        print("\n🔐 未检测到 Garmin 登录信息，请输入账号密码进行登录", file=sys.stderr)
        email = input("Garmin 账号（邮箱）: ").strip()
        if not email:
            raise RuntimeError("GARMIN_EMAIL is required.")
        password = input("Garmin 密码：").strip()
        if not password:
            raise RuntimeError("GARMIN_PASSWORD is required.")

    is_cn = env_bool("GARMIN_IS_CN", True)

    try:
        client = Garmin(
            email=email,
            password=password,
            is_cn=is_cn,
            return_on_mfa=True,
        )
    except TypeError:
        client = Garmin(email=email, password=password, is_cn=is_cn)

    try:
        login_result = client.login()
    except GarminConnectAuthenticationError as exc:
        raise RuntimeError(f"Garmin authentication failed: {exc}") from exc
    except GarthHTTPError as exc:
        raise RuntimeError(f"Garmin HTTP error during login: {exc}") from exc
    except GarthException as exc:
        raise RuntimeError(f"Garmin login error: {exc}") from exc

    if isinstance(login_result, tuple) and login_result and login_result[0] == "needs_mfa":
        mfa_code = os.getenv("GARMIN_MFA_CODE")
        if not mfa_code:
            # Interactive prompt for MFA code
            print("\n📱 Garmin 需要双重验证 (MFA)，请输入验证码", file=sys.stderr)
            mfa_code = input("验证码：").strip()
            if not mfa_code:
                raise RuntimeError(
                    "Garmin MFA is required. Set GARMIN_MFA_CODE or enter the code when prompted."
                )
        try:
            client.resume_login(login_result[1], mfa_code)
        except Exception as exc:
            raise RuntimeError(f"Garmin MFA verification failed: {exc}") from exc

    dump_tokens(client, token_path)
    print("\n✅ 登录成功！Token 已保存到 ~/.garminconnect/", file=sys.stderr)
    return client


def safe_call(func: Callable[..., Any], *args: Any) -> Any:
    try:
        return func(*args)
    except Exception:
        return None


def fetch_sleep(client: Any, date_str: str, include_raw: bool) -> dict[str, Any]:
    raw = client.get_sleep_data(date_str)
    return normalize_sleep(date_str, raw, include_raw)


def fetch_heart_rate(client: Any, date_str: str, include_raw: bool) -> dict[str, Any]:
    raw = client.get_heart_rates(date_str)
    if isinstance(raw, dict) and not pick_first(raw, "restingHeartRate", "restingHeartRateValue"):
        resting = safe_call(client.get_resting_heart_rate, date_str)
        if resting is not None:
            raw = dict(raw)
            raw["restingHeartRate"] = resting
    return normalize_heart_rate(date_str, raw, include_raw)


def fetch_stress(client: Any, date_str: str, include_raw: bool) -> dict[str, Any]:
    raw = {
        "summary": safe_call(client.get_stress_data, date_str),
        "detail": safe_call(client.get_all_day_stress, date_str),
    }
    if raw["summary"] is None and raw["detail"] is None:
        raise RuntimeError(f"No stress data available for {date_str}.")
    return normalize_stress(date_str, raw, include_raw)


def fetch_steps(client: Any, date_str: str, include_raw: bool) -> dict[str, Any]:
    summary = client.get_user_summary(date_str)
    steps_data = safe_call(client.get_steps_data, date_str)
    raw = {"summary": summary, "steps_data": steps_data}
    return normalize_steps(date_str, raw, include_raw)


def fetch_summary(client: Any, date_str: str, include_raw: bool) -> dict[str, Any]:
    raw = {
        "summary": safe_call(client.get_user_summary, date_str),
        "steps_data": safe_call(client.get_steps_data, date_str),
        "sleep": safe_call(client.get_sleep_data, date_str),
        "heart_rate": safe_call(client.get_heart_rates, date_str),
        "stress": {
            "summary": safe_call(client.get_stress_data, date_str),
            "detail": safe_call(client.get_all_day_stress, date_str),
        },
    }
    return normalize_summary(date_str, raw, include_raw)


def fetch_hrv(client: Any, date_str: str, include_raw: bool) -> dict[str, Any]:
    raw = client.get_hrv_data(date_str)
    return normalize_hrv(date_str, raw, include_raw)


def fetch_floors(client: Any, date_str: str, include_raw: bool) -> dict[str, Any]:
    raw = client.get_floors(date_str)
    return normalize_floors(date_str, raw, include_raw)


def fetch_intensity_minutes(client: Any, date_str: str, include_raw: bool) -> dict[str, Any]:
    raw = client.get_intensity_minutes_data(date_str)
    return normalize_intensity_minutes(date_str, raw, include_raw)


def fetch_weight(client: Any, date_str: str, include_raw: bool) -> dict[str, Any]:
    raw = client.get_body_composition(date_str, date_str)
    return normalize_weight(date_str, raw, include_raw)


def fetch_blood_pressure(client: Any, date_str: str, include_raw: bool) -> dict[str, Any]:
    raw = client.get_blood_pressure(date_str, date_str)
    return normalize_blood_pressure(date_str, raw, include_raw)


def fetch_spo2(client: Any, date_str: str, include_raw: bool) -> dict[str, Any]:
    raw = client.get_spo2_data(date_str)
    return normalize_spo2(date_str, raw, include_raw)


def fetch_respiration(client: Any, date_str: str, include_raw: bool) -> dict[str, Any]:
    raw = client.get_respiration_data(date_str)
    return normalize_respiration(date_str, raw, include_raw)


def fetch_body_battery(client: Any, date_str: str, include_raw: bool) -> dict[str, Any]:
    raw = client.get_body_battery(date_str, date_str)
    return normalize_body_battery(date_str, raw, include_raw)


def fetch_fitness_age(client: Any, date_str: str, include_raw: bool) -> dict[str, Any]:
    raw = client.get_fitnessage_data(date_str)
    return normalize_fitness_age(date_str, raw, include_raw)


def fetch_training_status(client: Any, date_str: str, include_raw: bool) -> dict[str, Any]:
    raw = client.get_training_status(date_str)
    return normalize_training_status(date_str, raw, include_raw)


def fetch_training_readiness(client: Any, date_str: str, include_raw: bool) -> dict[str, Any]:
    raw = client.get_training_readiness(date_str)
    return normalize_training_readiness(date_str, raw, include_raw)


def fetch_race_predictions(client: Any, date_str: str, include_raw: bool) -> dict[str, Any]:
    raw = client.get_race_predictions()
    return normalize_race_predictions(date_str, raw, include_raw)


def fetch_max_metrics(client: Any, date_str: str, include_raw: bool) -> dict[str, Any]:
    raw = client.get_max_metrics(date_str)
    return normalize_max_metrics(date_str, raw, include_raw)


def fetch_cycling_ftp(client: Any, date_str: str, include_raw: bool) -> dict[str, Any]:
    raw = client.get_cycling_ftp()
    return normalize_cycling_ftp(date_str, raw, include_raw)


def fetch_lactate_threshold(client: Any, date_str: str, include_raw: bool) -> dict[str, Any]:
    raw = client.get_lactate_threshold()
    return normalize_lactate_threshold(date_str, raw, include_raw)


FETCHERS: dict[str, Callable[[Any, str, bool], dict[str, Any]]] = {
    "sleep": fetch_sleep,
    "heart-rate": fetch_heart_rate,
    "stress": fetch_stress,
    "steps": fetch_steps,
    "floors": fetch_floors,
    "intensity-minutes": fetch_intensity_minutes,
    "weight": fetch_weight,
    "blood-pressure": fetch_blood_pressure,
    "spo2": fetch_spo2,
    "respiration": fetch_respiration,
    "body-battery": fetch_body_battery,
    "summary": fetch_summary,
    "hrv": fetch_hrv,
    "fitness-age": fetch_fitness_age,
    "training-status": fetch_training_status,
    "training-readiness": fetch_training_readiness,
    "race-predictions": fetch_race_predictions,
    "max-metrics": fetch_max_metrics,
    "cycling-ftp": fetch_cycling_ftp,
    "lactate-threshold": fetch_lactate_threshold,
}


def build_success_response(
    metric: str,
    start_day: date,
    end_day: date,
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "ok": True,
        "metric": metric,
        "range": {
            "start_date": start_day.isoformat(),
            "end_date": end_day.isoformat(),
        },
        "items": items,
        "generated_at": utc_now(),
        "source": {
            "service": "Garmin Connect",
            "domain": "garmin.cn" if env_bool("GARMIN_IS_CN", True) else "garmin.com",
        },
    }


def build_success_response_all(
    start_day: date,
    end_day: date,
    metrics_items: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    return {
        "ok": True,
        "metric": "all",
        "range": {
            "start_date": start_day.isoformat(),
            "end_date": end_day.isoformat(),
        },
        "metrics": metrics_items,
        "generated_at": utc_now(),
        "source": {
            "service": "Garmin Connect",
            "domain": "garmin.cn" if env_bool("GARMIN_IS_CN", True) else "garmin.com",
        },
    }


def build_error_response(message: str) -> dict[str, Any]:
    return {
        "ok": False,
        "error": message,
        "generated_at": utc_now(),
        "source": {
            "service": "Garmin Connect",
            "domain": "garmin.cn" if env_bool("GARMIN_IS_CN", True) else "garmin.com",
        },
    }


def emit(payload: dict[str, Any], pretty: bool) -> None:
    json.dump(
        payload,
        sys.stdout,
        ensure_ascii=False,
        indent=2 if pretty else None,
        sort_keys=False,
    )
    sys.stdout.write("\n")


def main() -> int:
    try:
        args = parse_args()
        start_day, end_day = resolve_dates(args)
        client = authenticate()

        # Handle init-archive metric specially by calling sync_garmin_archive.py
        if args.metric == "init-archive":
            import subprocess

            print("\n📦 正在初始化 Garmin 本地数据归档...", file=sys.stderr)
            archive_dir = Path(args.archive_dir).expanduser().resolve()
            print(f"归档目录：{archive_dir.absolute()}", file=sys.stderr)
            print(f"日期范围：{start_day.isoformat()} 至 {end_day.isoformat()}", file=sys.stderr)
            print("\n这可能需要一些时间，请稍候...\n", file=sys.stderr)

            # Build command for sync_garmin_archive.py
            script_dir = Path(__file__).parent
            sync_script = script_dir / "sync_garmin_archive.py"

            cmd = [
                sys.executable,
                str(sync_script),
                "--mode", "init",
                "--archive-dir", str(archive_dir),
                "--start-date", start_day.isoformat(),
                "--end-date", end_day.isoformat(),
            ]
            if args.pretty:
                cmd.append("--pretty")

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                raise RuntimeError(f"Archive sync failed: {result.stderr}")

            emit({
                "ok": True,
                "metric": "init-archive",
                "archive_dir": str(archive_dir.absolute()),
                "start_date": start_day.isoformat(),
                "end_date": end_day.isoformat(),
                "message": "归档初始化完成",
                "generated_at": utc_now(),
                "source": {
                    "service": "Garmin Connect",
                    "domain": "garmin.cn" if env_bool("GARMIN_IS_CN", True) else "garmin.com",
                },
            }, args.pretty)
            return 0

        if args.metric == "all":
            metrics_items: dict[str, list[dict[str, Any]]] = {}
            for name, fetcher in FETCHERS.items():
                items: list[dict[str, Any]] = []
                for day in iter_days(start_day, end_day):
                    date_str = day.isoformat()
                    try:
                        items.append(fetcher(client, date_str, args.include_raw))
                    except Exception as exc:
                        items.append(
                            {
                                "date": date_str,
                                "metric": name,
                                "error": str(exc),
                            }
                        )
                metrics_items[name] = items
            emit(
                build_success_response_all(start_day, end_day, metrics_items),
                args.pretty,
            )
            return 0

        items: list[dict[str, Any]] = []
        fetcher = FETCHERS[args.metric]
        for day in iter_days(start_day, end_day):
            date_str = day.isoformat()
            try:
                items.append(fetcher(client, date_str, args.include_raw))
            except Exception as exc:
                items.append(
                    {
                        "date": date_str,
                        "metric": args.metric,
                        "error": str(exc),
                    }
                )

        emit(build_success_response(args.metric, start_day, end_day, items), args.pretty)
        return 0
    except Exception as exc:
        emit(build_error_response(str(exc)), pretty=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
