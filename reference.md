## Runtime Requirements

- Python 3.10+
- Installed packages:

```bash
python3 -m pip install garminconnect garth requests
```

## Environment Variables

- `GARMIN_EMAIL`: Garmin login email
- `GARMIN_PASSWORD`: Garmin login password
- `GARMINTOKENS`: token directory, default `~/.garminconnect`
- `GARMIN_IS_CN`: use `true` for Garmin China, default `true`
- `GARMIN_MFA_CODE`: one-time MFA code for fresh login when required

Example:

```bash
export GARMIN_EMAIL="your-account@example.com"
export GARMIN_PASSWORD="your-password"
export GARMIN_IS_CN="true"
export GARMINTOKENS="$HOME/.garminconnect"
```

## Script Location

`.cursor/skills/garmin-connect-data/scripts/fetch_garmin_metrics.py`

`.cursor/skills/garmin-connect-data/scripts/sync_garmin_archive.py`

`.cursor/skills/garmin-connect-data/scripts/query_garmin_archive.py`（只读归档，不调 Garmin API）

Run it with `python3`.

## Supported Commands

Today's summary:

```bash
python3 .cursor/skills/garmin-connect-data/scripts/fetch_garmin_metrics.py --metric summary --pretty
```

Specific date:

```bash
python3 .cursor/skills/garmin-connect-data/scripts/fetch_garmin_metrics.py --metric sleep --date 2026-03-09 --pretty
```

Range query:

```bash
python3 .cursor/skills/garmin-connect-data/scripts/fetch_garmin_metrics.py --metric steps --start-date 2026-03-01 --end-date 2026-03-07 --pretty
```

**时间点：查询某一天的所有指标**（`--metric all` + `--date`）：

```bash
python3 .cursor/skills/garmin-connect-data/scripts/fetch_garmin_metrics.py --metric all --date 2026-03-09 --pretty
```

**时间段：查询某段日期的所有指标**（`--metric all` + `--start-date` / `--end-date`）：

```bash
python3 .cursor/skills/garmin-connect-data/scripts/fetch_garmin_metrics.py --metric all --start-date 2026-03-01 --end-date 2026-03-07 --pretty
```

从归档查询单指标（见下方「查询脚本」）；**从归档查询所有指标**（时间点或时间段）：

```bash
# 时间点：某一天
python3 .cursor/skills/garmin-connect-data/scripts/query_garmin_archive.py --archive-dir garmin_archive --metric all --start-date 2026-03-09 --pretty

# 时间段
python3 .cursor/skills/garmin-connect-data/scripts/query_garmin_archive.py --archive-dir garmin_archive --metric all --start-date 2026-03-01 --end-date 2026-03-07 --pretty
```

Archive initialization:

```bash
python3 .cursor/skills/garmin-connect-data/scripts/sync_garmin_archive.py --mode init --archive-dir garmin_archive --start-date 2024-01-01 --pretty
```

Archive incremental sync:

```bash
python3 .cursor/skills/garmin-connect-data/scripts/sync_garmin_archive.py --mode incremental --archive-dir garmin_archive --pretty
```

## Output Contract

The script returns JSON with a stable outer structure:

```json
{
  "ok": true,
  "metric": "summary",
  "range": {
    "start_date": "2026-03-09",
    "end_date": "2026-03-09"
  },
  "items": [],
  "generated_at": "2026-03-09T11:22:33Z",
  "source": {
    "service": "Garmin Connect",
    "domain": "garmin.cn"
  }
}
```

Each `item` contains normalized fields for the chosen metric and can optionally include a `raw` payload when `--include-raw` is passed.

When `--metric all` is used, the response uses a `metrics` object instead of `items`: each key is a metric name and the value is the list of items for that metric (same shape as the single-metric `items`). Example: `{ "ok": true, "metric": "all", "range": {...}, "metrics": { "sleep": [...], "steps": [...], ... }, "generated_at": "...", "source": {...} }`.

## Metric Notes

- `sleep`: normalized around duration, sleep windows, score, and stage durations.
- `heart-rate`: normalized around resting heart rate, daily min/max, and sample count.
- `stress`: normalized around overall or average stress and available duration buckets.
- `steps`: normalized around steps, goal completion, distance, and calories.
- `floors`: normalized around ascended and descended floors plus active floor samples.
- `intensity-minutes`: normalized around daily and weekly moderate/vigorous minutes.
- `weight`: normalized around weight, BMI, body fat, and composition fields when available.
- `blood-pressure`: normalized around latest available systolic/diastolic/pulse entry for the date.
- `spo2`: normalized around average, lowest, latest, and sleep SpO2.
- `respiration`: normalized around waking and sleep respiration plus min/max values.
- `body-battery`: normalized around charged, drained, and observed battery levels.
- `summary`: combines daily summary, sleep, heart rate, stress, and steps into one record.
- `hrv`: normalized around nightly average, 7-day average, baseline band, and status.
- `fitness-age`: normalized around body age, achievable age, RHR, BMI, and training contributors.
- `training-status`: normalized around current VO2 max, training status, and acclimation fields.
- `training-readiness`: normalized around readiness score when the account/device supports it.
- `race-predictions`: normalized around current 5K, 10K, half marathon, and marathon predictions.
- `max-metrics`: normalized around available VO2 max style fields when the account exposes them.
- `cycling-ftp`: normalized around current functional threshold power snapshot.
- `lactate-threshold`: normalized around speed/heart-rate threshold and power threshold fields.

## Archive Layout

The archive script writes categorized JSONL files plus a sync state file:

```text
garmin_archive/
├── state.json
├── daily/
│   ├── summary.jsonl
│   ├── sleep.jsonl
│   ├── heart-rate.jsonl
│   ├── stress.jsonl
│   ├── steps.jsonl
│   ├── floors.jsonl
│   └── intensity-minutes.jsonl
├── health/
│   ├── weight.jsonl
│   ├── blood-pressure.jsonl
│   ├── spo2.jsonl
│   ├── respiration.jsonl
│   └── body-battery.jsonl
├── advanced/
│   ├── hrv.jsonl
│   └── fitness-age.jsonl
├── performance/
│   ├── training-status.jsonl
│   ├── training-readiness.jsonl
│   ├── race-predictions.jsonl
│   ├── max-metrics.jsonl
│   ├── cycling-ftp.jsonl
│   └── lactate-threshold.jsonl
└── activities/
    └── activities.jsonl
```

Each JSONL line is one normalized record with a `raw` payload retained for later deep analysis.

## Date Handling

- Use `YYYY-MM-DD`.
- If no date arguments are supplied, the script defaults to today.
- Use either `--date` or `--start-date` plus `--end-date`.
- Prefer short ranges unless the user explicitly requests a broader history.
- For archive init, prefer an explicit `--start-date` so the historical coverage is clear.
- If archive init runs without `--start-date`, the script infers a start date from the earliest activity it can find and falls back to the last 365 days if no activities are available.

## Authentication Flow

1. Try resuming from `GARMINTOKENS`.
2. If tokens are missing or expired, login with `GARMIN_EMAIL` and `GARMIN_PASSWORD`.
3. If Garmin requests MFA, provide `GARMIN_MFA_CODE` and retry.
4. Save the refreshed session back to the token directory.

This keeps normal reads fast and avoids re-authenticating on every request.

## Archive Sync Behavior

- `init`: backfills categorized files from `start-date` to `end-date` and creates `state.json`.
- `init` writes archive data month by month, so files start appearing during the run instead of only at the very end.
- `incremental`: reads `state.json`, starts from the next unsynced date for each metric, and only appends new records.
- Re-running `init` is safe because archive files are upserted by date or activity id instead of blindly duplicated.
- Activities are stored separately from daily wellness metrics so later analysis can distinguish workouts from day summaries.
- Some Garmin metrics are device-dependent or account-dependent. When unavailable, the normalized record may contain `no_data: true` or very sparse fields instead of failing the entire sync.

## Recommended Archive Strategy (方便后续查询与增量更新)

### 1. 归档方式（如何存）

- **单指标单文件**：每个指标一个 JSONL（如 `daily/sleep.jsonl`），不按日期再分子文件。这样增量时只需追加/覆盖同一文件，state 只记「该指标同步到哪一天」即可。
- **主键**：日指标用 `date`（YYYY-MM-DD）做唯一键；活动用 `activity_id`。写入时按主键 upsert，避免重复。
- **按月落盘**：init 时按月拉取、每月写一次盘，避免长跑中途无数据可见；中断后重跑会从 state 继续，已写入的月不会丢。
- **固定目录**：归档根目录固定（如项目下的 `garmin_archive/`），`state.json` 只放在根目录一份，记录各 metric 的 `last_synced_date`。

### 2. 增量更新（如何更新）

- **每日定时**：建议每天跑一次 incremental（例如 cron 凌晨 1 点），只拉「上一同步日期的下一天 → 今天」，API 调用最少。
- **命令**：`python3 .cursor/skills/garmin-connect-data/scripts/sync_garmin_archive.py --mode incremental --archive-dir garmin_archive --pretty`
- **幂等**：重复跑 incremental 是安全的（同一天会 upsert 覆盖）。漏跑几天再跑会从 state 的 last_synced_date 往后补。
- **state 更新时机**：当前在整次 run 成功结束时才写 state；若中途崩溃，下次会从上次 state 再拉，可能重拉最后一段，但不会乱序或丢主键。

### 3. 后续查询（如何查）

- **优先查归档**：历史或大区间查询优先从本地 JSONL 读，不占 Garmin API、速度快。用脚本 `query_garmin_archive.py`（见下）按 metric + 日期区间输出 JSON。
- **需要实时再调 API**：仅当要「刚过去这一天」且尚未跑完当日 incremental 时，再用 `fetch_garmin_metrics.py` 拉一次。
- **按日期过滤**：JSONL 每行一个 JSON 对象，含 `date` 字段。可用 `jq` 或脚本过滤，例如：  
  `jq -c 'select(.date >= "2024-01-01" and .date <= "2024-01-31")' garmin_archive/daily/sleep.jsonl`
- **分析型查询**：需要聚合（如「最近 7 天平均睡眠」）时，可把 JSONL 导入 DuckDB / pandas 再查，例如 DuckDB：  
  `SELECT date, total_sleep_hours FROM read_json_auto('garmin_archive/daily/sleep.jsonl') WHERE date BETWEEN '2024-01-01' AND '2024-01-31'`

### 4. 查询脚本（只读归档，不调 API）

```bash
# 查某指标、某日期区间（从归档读）
python3 .cursor/skills/garmin-connect-data/scripts/query_garmin_archive.py \
  --archive-dir garmin_archive --metric sleep \
  --start-date 2024-06-01 --end-date 2024-06-30 --pretty
```

输出格式与 `fetch_garmin_metrics.py` 的 `items` 一致，便于 Skill 或下游统一处理。脚本见 `scripts/query_garmin_archive.py`。

## Troubleshooting

- `ModuleNotFoundError`: install `garminconnect`, `garth`, and `requests`.
- Authentication error: verify account credentials and confirm the account belongs to Garmin China if `GARMIN_IS_CN=true`.
- MFA required: set `GARMIN_MFA_CODE` for the current run.
- Empty metric data: some Garmin accounts or devices do not expose every wellness endpoint every day.
- Rate limiting or `429`: retry later instead of looping aggressively.

## Notes About Data Source

The user-facing site is [`https://connect.garmin.cn/app/home`](https://connect.garmin.cn/app/home), but the implementation should prefer Garmin Connect's underlying API client instead of scraping the page. This is more stable for structured metrics like sleep and heart rate.
