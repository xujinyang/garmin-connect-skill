# garmin-connect-skill

Cursor / Codex 可用的 Garmin Connect 数据 Skill：按需拉取睡眠、心率、压力、步数、每日摘要等健康数据，支持本地归档与增量同步。

## 依赖

- Python 3.10+
- `garminconnect`、`garth`、`requests`

```bash
pip install garminconnect garth requests
```

## 环境变量

- `GARMIN_EMAIL`、`GARMIN_PASSWORD`（必填）
- `GARMIN_IS_CN`：中国区用 `true`（默认）
- `GARMINTOKENS`：Token 目录，默认 `~/.garminconnect`
- `GARMIN_MFA_CODE`：需要 MFA 时填入当次验证码

复制 `env.example` 为 `.env` 并填入本地值；**切勿将 `.env` 或真实账号密码提交到仓库**（`.gitignore` 已忽略 `.env` 与 `.garminconnect/`）。

## 脚本

| 脚本 | 说明 |
|------|------|
| `scripts/fetch_garmin_metrics.py` | 按指标/日期拉取 Garmin API，输出归一化 JSON |
| `scripts/sync_garmin_archive.py` | 初始化或增量同步本地归档（`--mode init` / `incremental`） |
| `scripts/query_garmin_archive.py` | 从本地归档按日期区间查询（不调 API） |

## 文档

- **SKILL.md**：Skill 触发条件与工作流
- **reference.md**：命令示例、输出约定、归档建议、排错

## 使用示例

```bash
# 今日摘要
python3 scripts/fetch_garmin_metrics.py --metric summary --pretty

# 某天睡眠
python3 scripts/fetch_garmin_metrics.py --metric sleep --date 2026-03-09 --pretty

# 从归档查本月睡眠
python3 scripts/query_garmin_archive.py --archive-dir garmin_archive --metric sleep --start-date 2026-03-01 --end-date 2026-03-31 --pretty
```

将本仓库放入 Cursor 的 `.cursor/skills/` 下即可作为 Skill 使用。
