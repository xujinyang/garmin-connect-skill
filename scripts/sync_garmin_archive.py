#!/usr/bin/env python3
"""Initialize and incrementally sync categorized Garmin archives."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fetch_garmin_metrics import FETCHERS, authenticate, iter_days, parse_date, safe_call

ARCHIVE_VERSION = 1
DEFAULT_METRICS = [
    "summary",
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
    "hrv",
    "fitness-age",
    "training-status",
    "training-readiness",
    "race-predictions",
    "max-metrics",
    "cycling-ftp",
    "lactate-threshold",
    "activities",
]
METRIC_FILES = {
    "summary": "daily/summary.jsonl",
    "sleep": "daily/sleep.jsonl",
    "heart-rate": "daily/heart-rate.jsonl",
    "stress": "daily/stress.jsonl",
    "steps": "daily/steps.jsonl",
    "floors": "daily/floors.jsonl",
    "intensity-minutes": "daily/intensity-minutes.jsonl",
    "weight": "health/weight.jsonl",
    "blood-pressure": "health/blood-pressure.jsonl",
    "spo2": "health/spo2.jsonl",
    "respiration": "health/respiration.jsonl",
    "body-battery": "health/body-battery.jsonl",
    "hrv": "advanced/hrv.jsonl",
    "fitness-age": "advanced/fitness-age.jsonl",
    "training-status": "performance/training-status.jsonl",
    "training-readiness": "performance/training-readiness.jsonl",
    "race-predictions": "performance/race-predictions.jsonl",
    "max-metrics": "performance/max-metrics.jsonl",
    "cycling-ftp": "performance/cycling-ftp.jsonl",
    "lactate-threshold": "performance/lactate-threshold.jsonl",
    "activities": "activities/activities.jsonl",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Initialize or incrementally sync categorized Garmin archives."
    )
    parser.add_argument(
        "--mode",
        required=True,
        choices=["init", "incremental"],
        help="Archive sync mode.",
    )
    parser.add_argument(
        "--archive-dir",
        default="garmin_archive",
        help="Directory for categorized archive files and sync state.",
    )
    parser.add_argument(
        "--start-date",
        help="Optional YYYY-MM-DD start date. Recommended for init to define history coverage.",
    )
    parser.add_argument(
        "--end-date",
        help="Optional YYYY-MM-DD end date. Defaults to today.",
    )
    parser.add_argument(
        "--chunk-days",
        type=int,
        default=30,
        help="Chunk size for activity sync requests.",
    )
    parser.add_argument(
        "--metrics",
        nargs="*",
        choices=DEFAULT_METRICS,
        default=DEFAULT_METRICS,
        help="Subset of archive categories to sync.",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output.",
    )
    args = parser.parse_args()

    if args.chunk_days <= 0:
        parser.error("--chunk-days must be a positive integer.")

    return args


def emit(payload: dict[str, Any], pretty: bool) -> None:
    json.dump(
        payload,
        sys.stdout,
        ensure_ascii=False,
        indent=2 if pretty else None,
        sort_keys=False,
    )
    sys.stdout.write("\n")


def state_path(archive_dir: Path) -> Path:
    return archive_dir / "state.json"


def load_state(archive_dir: Path) -> dict[str, Any]:
    path = state_path(archive_dir)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(archive_dir: Path, state: dict[str, Any]) -> None:
    archive_dir.mkdir(parents=True, exist_ok=True)
    path = state_path(archive_dir)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def archive_file(archive_dir: Path, metric: str) -> Path:
    return archive_dir / METRIC_FILES[metric]


def load_jsonl_index(path: Path, key_field: str) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return records

    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            key = record.get(key_field)
            if key is None:
                continue
            records[str(key)] = record
    return records


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def sort_records(records: list[dict[str, Any]], metric: str) -> list[dict[str, Any]]:
    if metric == "activities":
        return sorted(
            records,
            key=lambda item: (
                str(item.get("date") or ""),
                str(item.get("start_time_local") or ""),
                str(item.get("activity_id") or ""),
            ),
        )
    return sorted(records, key=lambda item: str(item.get("date") or ""))


def upsert_jsonl(
    path: Path,
    key_field: str,
    new_records: list[dict[str, Any]],
    metric: str,
) -> dict[str, int]:
    existing = load_jsonl_index(path, key_field)
    inserted = 0
    updated = 0

    for record in new_records:
        key = record.get(key_field)
        if key is None:
            continue
        str_key = str(key)
        if str_key in existing:
            updated += 1
        else:
            inserted += 1
        existing[str_key] = record

    ordered = sort_records(list(existing.values()), metric)
    write_jsonl(path, ordered)
    return {
        "inserted": inserted,
        "updated": updated,
        "total_records": len(existing),
    }


def extract_activity_date(activity: dict[str, Any]) -> date | None:
    for key in ("startTimeLocal", "startTimeGMT"):
        value = activity.get(key)
        if isinstance(value, str) and len(value) >= 10:
            try:
                return date.fromisoformat(value[:10])
            except ValueError:
                continue
    return None


def infer_start_date(client: Any) -> tuple[date, str]:
    count = safe_call(client.count_activities)
    if isinstance(count, int) and count > 0:
        start = max(count - 100, 0)
        activities = safe_call(client.get_activities, start, 100) or []
        dates = [
            activity_date
            for activity_date in (extract_activity_date(item) for item in activities)
            if activity_date is not None
        ]
        if dates:
            return min(dates), "inferred from earliest activity date"
    return date.today() - timedelta(days=365), "fallback to last 365 days"


def chunk_ranges(start_day: date, end_day: date, chunk_days: int) -> list[tuple[date, date]]:
    ranges: list[tuple[date, date]] = []
    current = start_day
    while current <= end_day:
        chunk_end = min(current + timedelta(days=chunk_days - 1), end_day)
        ranges.append((current, chunk_end))
        current = chunk_end + timedelta(days=1)
    return ranges


def month_ranges(start_day: date, end_day: date) -> list[tuple[date, date]]:
    ranges: list[tuple[date, date]] = []
    current = start_day
    while current <= end_day:
        if current.month == 12:
            next_month = date(current.year + 1, 1, 1)
        else:
            next_month = date(current.year, current.month + 1, 1)
        chunk_end = min(next_month - timedelta(days=1), end_day)
        ranges.append((current, chunk_end))
        current = chunk_end + timedelta(days=1)
    return ranges


def normalize_activity(activity: dict[str, Any]) -> dict[str, Any]:
    date_value = extract_activity_date(activity)
    activity_type = activity.get("activityType") or {}

    return {
        "activity_id": activity.get("activityId"),
        "date": date_value.isoformat() if date_value else None,
        "metric": "activities",
        "activity_name": activity.get("activityName"),
        "activity_type": activity_type.get("typeKey") if isinstance(activity_type, dict) else None,
        "start_time_local": activity.get("startTimeLocal"),
        "start_time_gmt": activity.get("startTimeGMT"),
        "distance_meters": activity.get("distance"),
        "duration_seconds": activity.get("duration"),
        "moving_duration_seconds": activity.get("movingDuration"),
        "calories": activity.get("calories"),
        "average_hr": activity.get("averageHR"),
        "max_hr": activity.get("maxHR"),
        "raw": activity,
    }


def sync_metric(
    client: Any,
    metric: str,
    archive_dir: Path,
    start_day: date,
    end_day: date,
) -> dict[str, Any]:
    path = archive_file(archive_dir, metric)
    fetcher = FETCHERS[metric]
    errors: list[dict[str, str]] = []
    inserted = 0
    updated = 0
    total_records = 0
    processed_days = 0
    processed_months = 0

    for chunk_start, chunk_end in month_ranges(start_day, end_day):
        processed_months += 1
        records: list[dict[str, Any]] = []
        chunk_days = iter_days(chunk_start, chunk_end)
        print(
            f"[{metric}] syncing {chunk_start.isoformat()} to {chunk_end.isoformat()}",
            file=sys.stderr,
            flush=True,
        )
        for day in chunk_days:
            date_str = day.isoformat()
            try:
                record = fetcher(client, date_str, True)
                records.append(record)
            except Exception as exc:
                errors.append({"date": date_str, "error": str(exc)})

        chunk_result = upsert_jsonl(path, "date", records, metric)
        inserted += chunk_result["inserted"]
        updated += chunk_result["updated"]
        total_records = chunk_result["total_records"]
        processed_days += len(chunk_days)

    return {
        "metric": metric,
        "path": str(path),
        "start_date": start_day.isoformat(),
        "end_date": end_day.isoformat(),
        "processed_days": processed_days,
        "processed_months": processed_months,
        "inserted": inserted,
        "updated": updated,
        "total_records": total_records,
        "error_count": len(errors),
        "errors": errors[:10],
    }


def sync_activities(
    client: Any,
    archive_dir: Path,
    start_day: date,
    end_day: date,
) -> dict[str, Any]:
    path = archive_file(archive_dir, "activities")
    errors: list[dict[str, str]] = []
    inserted = 0
    updated = 0
    total_records = 0
    fetched_records = 0
    processed_months = 0

    for chunk_start, chunk_end in month_ranges(start_day, end_day):
        processed_months += 1
        records: list[dict[str, Any]] = []
        print(
            f"[activities] syncing {chunk_start.isoformat()} to {chunk_end.isoformat()}",
            file=sys.stderr,
            flush=True,
        )
        try:
            items = (
                safe_call(
                    client.get_activities_by_date,
                    chunk_start.isoformat(),
                    chunk_end.isoformat(),
                )
                or []
            )
            for item in items:
                if isinstance(item, dict):
                    records.append(normalize_activity(item))
        except Exception as exc:
            errors.append(
                {
                    "start_date": chunk_start.isoformat(),
                    "end_date": chunk_end.isoformat(),
                    "error": str(exc),
                }
            )

        chunk_result = upsert_jsonl(path, "activity_id", records, "activities")
        inserted += chunk_result["inserted"]
        updated += chunk_result["updated"]
        total_records = chunk_result["total_records"]
        fetched_records += len(records)

    return {
        "metric": "activities",
        "path": str(path),
        "start_date": start_day.isoformat(),
        "end_date": end_day.isoformat(),
        "processed_months": processed_months,
        "fetched_records": fetched_records,
        "inserted": inserted,
        "updated": updated,
        "total_records": total_records,
        "error_count": len(errors),
        "errors": errors[:10],
    }


def resolve_end_date(text: str | None) -> date:
    return parse_date(text) if text else date.today()


def next_day(text: str) -> date:
    return parse_date(text) + timedelta(days=1)


def resolve_metric_start(
    metric: str,
    args: argparse.Namespace,
    state: dict[str, Any],
    default_start: date,
) -> date:
    if args.start_date:
        return parse_date(args.start_date)

    if args.mode == "init":
        return default_start

    metric_state = state.get("metrics", {}).get(metric, {})
    last_synced = metric_state.get("last_synced_date")
    if last_synced:
        return next_day(last_synced)

    archive_start = state.get("archive_start_date")
    if archive_start:
        return parse_date(archive_start)

    raise RuntimeError(
        "Incremental sync needs an existing archive state or an explicit --start-date."
    )


def build_state_update(
    archive_dir: Path,
    state: dict[str, Any],
    mode: str,
    archive_start: date,
    end_day: date,
    results: list[dict[str, Any]],
    inferred_reason: str | None,
) -> dict[str, Any]:
    metrics_state = state.get("metrics", {})
    for result in results:
        metric = result["metric"]
        metrics_state[metric] = {
            "last_synced_date": result["end_date"],
            "path": str(Path(result["path"]).relative_to(archive_dir)),
            "updated_at": utc_now(),
        }

    initialized_at = state.get("initialized_at") or utc_now()
    return {
        "version": ARCHIVE_VERSION,
        "mode": mode,
        "archive_start_date": archive_start.isoformat(),
        "archive_end_date": end_day.isoformat(),
        "initialized_at": initialized_at,
        "updated_at": utc_now(),
        "inferred_start_reason": inferred_reason,
        "metrics": metrics_state,
    }


def main() -> int:
    try:
        args = parse_args()
        archive_dir = Path(args.archive_dir).expanduser().resolve()
        archive_dir.mkdir(parents=True, exist_ok=True)
        end_day = resolve_end_date(args.end_date)
        client = authenticate()
        state = load_state(archive_dir)

        inferred_reason: str | None = None
        if args.start_date:
            archive_start = parse_date(args.start_date)
        elif args.mode == "init":
            archive_start, inferred_reason = infer_start_date(client)
        else:
            archive_start = parse_date(state["archive_start_date"]) if state.get("archive_start_date") else end_day

        if archive_start > end_day:
            raise RuntimeError("Start date must be on or before end date.")

        results: list[dict[str, Any]] = []
        for metric in args.metrics:
            metric_start = resolve_metric_start(metric, args, state, archive_start)
            if metric_start > end_day:
                results.append(
                    {
                        "metric": metric,
                        "path": str(archive_file(archive_dir, metric)),
                        "start_date": metric_start.isoformat(),
                        "end_date": end_day.isoformat(),
                        "skipped": True,
                        "reason": "already up to date",
                    }
                )
                continue

            if metric == "activities":
                result = sync_activities(
                    client,
                    archive_dir,
                    metric_start,
                    end_day,
                )
            else:
                result = sync_metric(client, metric, archive_dir, metric_start, end_day)
            results.append(result)

        state_update = build_state_update(
            archive_dir,
            state,
            args.mode,
            archive_start,
            end_day,
            [item for item in results if not item.get("skipped")],
            inferred_reason,
        )
        save_state(archive_dir, state_update)

        emit(
            {
                "ok": True,
                "mode": args.mode,
                "archive_dir": str(archive_dir),
                "archive_start_date": archive_start.isoformat(),
                "archive_end_date": end_day.isoformat(),
                "metrics": results,
                "state_file": str(state_path(archive_dir)),
                "generated_at": utc_now(),
            },
            args.pretty,
        )
        return 0
    except Exception as exc:
        emit(
            {
                "ok": False,
                "error": str(exc),
                "generated_at": utc_now(),
            },
            pretty=True,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
