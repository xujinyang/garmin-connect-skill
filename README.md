# Garmin Connect Skill

Fetch sleep, heart rate, stress, steps, and daily summaries from Garmin Connect (connect.garmin.cn). Supports one-off API queries and local archive with incremental sync.

## What It Does

- **Live queries**: Pull any supported metric for a date or range via Garmin Connect API (sleep, heart rate, stress, steps, body battery, HRV, training status, etc.).
- **Archive mode**: Initialize a local JSONL archive from a start date, then run daily incremental sync so historical and recent data can be queried without hitting the API every time.
- **Query from archive**: Filter by date range on local files; supports single metric or “all metrics” for a time point or range.

Works with **Garmin China** (`connect.garmin.cn`) by default; configurable for other regions.

## How to Use

### 1. Install dependencies

```bash
pip install garminconnect garth requests
```

Python 3.10+ required.

### 2. Set credentials (env only; never commit)

Copy `env.example` to `.env` and fill in your Garmin login. Required:

- `GARMIN_EMAIL`
- `GARMIN_PASSWORD`

Optional: `GARMIN_IS_CN=true` (default), `GARMINTOKENS`, `GARMIN_MFA_CODE` when MFA is needed.

**Do not commit `.env` or real credentials.** `.gitignore` already excludes `.env` and `.garminconnect/`.

### 3. Run scripts

| Script | Purpose |
|--------|--------|
| `scripts/fetch_garmin_metrics.py` | Fetch one metric (or `--metric all`) for a date/range from Garmin API. |
| `scripts/sync_garmin_archive.py` | `--mode init` backfill archive; `--mode incremental` daily sync. |
| `scripts/query_garmin_archive.py` | Query local archive by metric and date range (no API). |

Paths above assume you are in the skill repo root. If the skill lives under Cursor at `.cursor/skills/garmin-connect-data/`, use that path prefix for the same scripts.

## Examples

**Today’s summary (API):**
```bash
python3 scripts/fetch_garmin_metrics.py --metric summary --pretty
```

**Sleep for a specific date (API):**
```bash
python3 scripts/fetch_garmin_metrics.py --metric sleep --date 2026-03-09 --pretty
```

**All metrics for a date range (API):**
```bash
python3 scripts/fetch_garmin_metrics.py --metric all --start-date 2026-03-01 --end-date 2026-03-07 --pretty
```

**Initialize archive then incremental sync:**
```bash
python3 scripts/sync_garmin_archive.py --mode init --archive-dir garmin_archive --start-date 2024-01-01 --pretty
python3 scripts/sync_garmin_archive.py --mode incremental --archive-dir garmin_archive --pretty
```

**Query sleep from archive (no API):**
```bash
python3 scripts/query_garmin_archive.py --archive-dir garmin_archive --metric sleep --start-date 2026-03-01 --end-date 2026-03-31 --pretty
```

**All metrics for a date from archive:**
```bash
python3 scripts/query_garmin_archive.py --archive-dir garmin_archive --metric all --start-date 2026-03-09 --pretty
```

## Requirements

- **Runtime**: Python 3.10+, `garminconnect`, `garth`, `requests`.
- **Credentials**: Garmin account; set `GARMIN_EMAIL` and `GARMIN_PASSWORD` (e.g. via `.env`). For China use `GARMIN_IS_CN=true`.
- **MFA**: If your account uses MFA, set `GARMIN_MFA_CODE` for the run that performs login.
- **Network**: HTTPS access to Garmin Connect (connect.garmin.cn or garmin.com).

## Troubleshooting

- **ModuleNotFoundError**: Install deps with `pip install garminconnect garth requests`.
- **Authentication error**: Check email/password and region (`GARMIN_IS_CN=true` for China).
- **MFA required**: Set `GARMIN_MFA_CODE` and run again.
- **Empty or sparse data**: Some metrics are device/account-dependent; the script may return `no_data` or sparse fields instead of failing.
- **Rate limiting (429)**: Wait and retry; avoid aggressive polling.

See **reference.md** for full env vars, output contract, archive layout, and date handling.

## License

MIT-0. Use, modify, and redistribute freely.
