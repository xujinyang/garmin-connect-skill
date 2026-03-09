---
name: garmin-connect-data
description: Access Garmin Connect health data such as sleep, heart rate, stress, steps, and daily summaries. Use when the user mentions Garmin, Garmin Connect, connect.garmin.cn, sleep metrics, heart rate, stress, steps, wellness, or health data from a Garmin account.
---

# Garmin Connect Data

## Use This Skill When

- The user asks for Garmin health or wellness data.
- The request mentions `Garmin Connect`, `garmin.cn`, `睡眠`, `心率`, `压力`, `步数`, `健康数据`.
- The user wants a daily summary or a date-scoped metric from Garmin Connect.
- The user wants to initialize a Garmin archive, backfill all historical Garmin data, or keep a daily incremental sync.

## Required Inputs

- `GARMIN_EMAIL`
- `GARMIN_PASSWORD`

Optional inputs:

- `GARMINTOKENS`: token directory, default `~/.garminconnect`
- `GARMIN_IS_CN`: defaults to `true`; keep this for `connect.garmin.cn`
- `GARMIN_MFA_CODE`: only needed if the account requires MFA during a fresh login

## Default Workflow

1. Identify the metric and time range the user wants.
2. If the user did not specify a date, default to today.
3. If the user asks vaguely for "today's Garmin data", use `summary`.
4. If the user asks to initialize or maintain a categorized archive, run the archive sync workflow instead of a single metric query.
5. Run the fetch script:

```bash
python3 .cursor/skills/garmin-connect-data/scripts/fetch_garmin_metrics.py --metric summary --date 2026-03-09 --pretty
```

6. Summarize the result in natural language first.
7. Only include raw JSON or large payloads when the user explicitly asks for them.

## Supported Metrics

- `sleep`
- `heart-rate`
- `stress`
- `steps`
- `floors`
- `intensity-minutes`
- `weight`
- `blood-pressure`
- `spo2`
- `respiration`
- `body-battery`
- `summary`
- `hrv`
- `fitness-age`
- `training-status`
- `training-readiness`
- `race-predictions`
- `max-metrics`
- `cycling-ftp`
- `lactate-threshold`

## Archive Workflows

Use the archive workflow when the user wants all currently available data copied locally and then incrementally updated over time.

Initialization:

```bash
python3 .cursor/skills/garmin-connect-data/scripts/sync_garmin_archive.py --mode init --archive-dir garmin_archive --start-date 2024-01-01 --pretty
```

Incremental daily sync:

```bash
python3 .cursor/skills/garmin-connect-data/scripts/sync_garmin_archive.py --mode incremental --archive-dir garmin_archive --pretty
```

If the user wants "all history" but does not know the first Garmin usage date:

- Ask for the approximate first Garmin usage date.
- If the user does not know it, run `init` without `--start-date`; the script will infer a start date from the earliest activity it can find, then continue from there.

## Archive Rules

- Store the archive outside the skill directory, for example in `garmin_archive`.
- Use `init` only for the first full backfill or when rebuilding the archive.
- Use `incremental` for later syncs so only new dates are fetched.
- The archive script maintains `state.json` and categorizes output into `daily`, `advanced`, and `activities`.
- Keep raw payloads in the archive so the agent can answer future questions from both normalized and original data.

## Command Patterns

Single day:

```bash
python3 .cursor/skills/garmin-connect-data/scripts/fetch_garmin_metrics.py --metric sleep --date 2026-03-09 --pretty
```

Date range:

```bash
python3 .cursor/skills/garmin-connect-data/scripts/fetch_garmin_metrics.py --metric steps --start-date 2026-03-01 --end-date 2026-03-07 --pretty
```

Include raw payloads:

```bash
python3 .cursor/skills/garmin-connect-data/scripts/fetch_garmin_metrics.py --metric heart-rate --date 2026-03-09 --include-raw --pretty
```

Advanced metric:

```bash
python3 .cursor/skills/garmin-connect-data/scripts/fetch_garmin_metrics.py --metric hrv --date 2026-03-09 --pretty
```

Performance metric:

```bash
python3 .cursor/skills/garmin-connect-data/scripts/fetch_garmin_metrics.py --metric body-battery --date 2026-03-09 --pretty
```

## Response Rules

- Lead with the answer the user cares about, not the entire payload.
- For sleep, highlight total sleep, bed time, wake time, and score when available.
- For heart rate, highlight resting heart rate and daily min/max when available.
- For stress, highlight average or overall stress plus notable distribution if present.
- For steps, highlight total steps, goal completion, distance, and calories when available.
- For HRV, highlight nightly average, 7-day average, baseline band, and status.
- For body battery, highlight charged, drained, and min/max level for the day.
- For race predictions, FTP, and lactate threshold, make it clear these are current performance snapshots and may be stale.
- If data is unavailable for a metric, say so clearly instead of guessing.
- If a metric returns `no_data`, tell the user the metric is unsupported for the account, device, or date instead of treating it as an error.

## Safety And Reliability

- Never print or echo credentials back to the user.
- Reuse token files when possible; avoid repeated fresh logins.
- If login fails, report whether it is likely due to bad credentials, MFA, rate limiting, or a missing package.
- Prefer narrow date ranges unless the user explicitly asks for historical data.

## Additional Reference

- See [reference.md](reference.md) for environment variables, date handling, and troubleshooting.
