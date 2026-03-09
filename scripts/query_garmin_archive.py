#!/usr/bin/env python3
"""Query Garmin metrics from local archive (no API calls)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

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
        description="Query Garmin metrics from local archive (no API)."
    )
    parser.add_argument(
        "--archive-dir",
        default="garmin_archive",
        help="Archive root directory.",
    )
    parser.add_argument(
        "--metric",
        required=True,
        choices=[*METRIC_FILES, "all"],
        help="Metric to query. Use 'all' to query every metric for the given range.",
    )
    parser.add_argument(
        "--start-date",
        required=True,
        help="Start date YYYY-MM-DD.",
    )
    parser.add_argument(
        "--end-date",
        help="End date YYYY-MM-DD (default: start-date).",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON.",
    )
    args = parser.parse_args()
    return args


def parse_date(s: str) -> date:
    return date.fromisoformat(s)


def in_range(d: str | None, start: date, end: date) -> bool:
    if not d:
        return False
    try:
        dt = parse_date(d)
        return start <= dt <= end
    except ValueError:
        return False


def query_one_metric(archive_dir: Path, metric: str, start: date, end: date) -> list[dict]:
    rel_path = METRIC_FILES[metric]
    path = archive_dir / rel_path
    items: list[dict] = []
    if path.exists():
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                d = obj.get("date")
                if in_range(d, start, end):
                    items.append(obj)
    return items


def main() -> None:
    args = parse_args()
    start = parse_date(args.start_date)
    end = parse_date(args.end_date) if args.end_date else start
    if end < start:
        end = start

    archive_dir = Path(args.archive_dir)

    if args.metric == "all":
        metrics_items: dict[str, list[dict]] = {}
        for name in METRIC_FILES:
            metrics_items[name] = query_one_metric(archive_dir, name, start, end)
        payload = {
            "ok": True,
            "metric": "all",
            "range": {"start_date": start.isoformat(), "end_date": end.isoformat()},
            "metrics": metrics_items,
            "generated_at": utc_now(),
            "source": {"type": "archive", "archive_dir": str(archive_dir)},
        }
    else:
        items = query_one_metric(archive_dir, args.metric, start, end)
        path = archive_dir / METRIC_FILES[args.metric]
        payload = {
            "ok": True,
            "metric": args.metric,
            "range": {"start_date": start.isoformat(), "end_date": end.isoformat()},
            "items": items,
            "generated_at": utc_now(),
            "source": {"type": "archive", "path": str(path)},
        }
    json.dump(
        payload,
        sys.stdout,
        ensure_ascii=False,
        indent=2 if args.pretty else None,
        sort_keys=False,
    )
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
