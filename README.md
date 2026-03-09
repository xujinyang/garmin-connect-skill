# Garmin Connect Skill

从 Garmin Connect（connect.garmin.cn）获取睡眠、心率、压力、步数等健康数据。支持 API 查询和本地归档增量同步。

## 功能特性

- **实时查询**：通过 Garmin Connect API 获取任意日期的睡眠、心率、压力、步数、身体电量、HRV 等指标
- **本地归档**：初始化本地 JSONL 归档，之后每日增量同步，避免频繁请求 API
- **归档查询**：从本地文件按日期范围查询，支持单指标或全量查询

默认使用 **Garmin 中国区**（`connect.garmin.cn`），也可配置为其他地区。

## 快速开始

### 1. 安装依赖

```bash
pip install garminconnect garth requests
```

需要 Python 3.10+

### 2. 配置账号（仅环境变量，切勿提交）

复制 `env.example` 到 `.env` 并填写 Garmin 账号：

```bash
cp env.example .env
```

必填：
- `GARMIN_EMAIL`
- `GARMIN_PASSWORD`

可选：`GARMIN_IS_CN=true`（默认）、`GARMINTOKENS`、`GARMIN_MFA_CODE`（需要 MFA 时）

**注意：`.env` 包含敏感信息，切勿提交到版本库。** `.gitignore` 已排除 `.env` 和 `.garminconnect/`。

### 3. 运行脚本

| 脚本 | 用途 |
|------|------|
| `scripts/fetch_garmin_metrics.py` | 从 API 获取单日/时间段的指标数据 |
| `scripts/sync_garmin_archive.py` | `--mode init` 初始化归档；`--mode incremental` 增量同步 |
| `scripts/query_garmin_archive.py` | 从本地归档查询（不调用 API） |

## 使用示例

### 从 API 查询

**今日摘要：**
```bash
python3 scripts/fetch_garmin_metrics.py --metric summary --pretty
```

**指定日期的睡眠：**
```bash
python3 scripts/fetch_garmin_metrics.py --metric sleep --date 2026-03-09 --pretty
```

**时间段内全部指标：**
```bash
python3 scripts/fetch_garmin_metrics.py --metric all --start-date 2026-03-01 --end-date 2026-03-07 --pretty
```

### 初始化和同步归档

**初始化归档（首次使用）：**
```bash
python3 scripts/sync_garmin_archive.py --mode init --archive-dir garmin_archive --start-date 2024-01-01 --pretty
```

**每日增量同步：**
```bash
python3 scripts/sync_garmin_archive.py --mode incremental --archive-dir garmin_archive --pretty
```

### 从归档查询（不调用 API）

**查询某日睡眠：**
```bash
python3 scripts/query_garmin_archive.py --archive-dir garmin_archive --metric sleep --start-date 2026-03-01 --end-date 2026-03-31 --pretty
```

**查询某日全部指标：**
```bash
python3 scripts/query_garmin_archive.py --archive-dir garmin_archive --metric all --start-date 2026-03-09 --pretty
```

## 支持的指标

| 指标 | 参数名 | 说明 |
|------|--------|------|
| 睡眠 | `sleep` | 总睡眠时间、深浅睡/REM/清醒时长、睡眠评分 |
| 心率 | `heart-rate` | 静息心率、日最低/最高/平均心率 |
| 压力 | `stress` | 整体压力水平、最高压力、压力分布 |
| 步数 | `steps` | 总步数、目标完成度、距离、卡路里 |
| 身体电量 | `body-battery` | 充电量、消耗量、最低/最高电量 |
| HRV | `hrv` | 夜间平均 HRV、7 天平均、基线状态 |
| 每日摘要 | `summary` | 综合当日所有核心指标（推荐默认使用） |
| 楼层 | `floors` | 上升/下降楼层数 |
| 强度分钟 | `intensity-minutes` | 中高强度活动分钟数 |
| 血氧 | `spo2` | 血氧饱和度 |
| 呼吸率 | `respiration` | 呼吸频率 |
| 体重 | `weight` | 体重、BMI、体脂率等 |
| 血压 | `blood-pressure` | 收缩压/舒张压 |
| 健身年龄 | `fitness-age` | 基于体能评估的"健身年龄" |
| 训练状态 | `training-status` | 当前训练负荷与状态 |
| 训练准备度 | `training-readiness` | 今日是否适合训练 |
| 比赛预测 | `race-predictions` | 各距离跑步成绩预测 |
| 骑行 FTP | `cycling-ftp` | 骑行功能阈值功率 |
| 乳酸阈值 | `lactate-threshold` | 乳酸阈值心率/配速 |

## 环境要求

- **运行时**：Python 3.10+, `garminconnect`, `garth`, `requests`
- **账号**：Garmin 账号；设置 `GARMIN_EMAIL` 和 `GARMIN_PASSWORD`
- **MFA**：如账号开启双重验证，首次登录时设置 `GARMIN_MFA_CODE`
- **网络**：HTTPS 访问 Garmin Connect（connect.garmin.cn 或 garmin.com）

## 常见问题

- **ModuleNotFoundError**：运行 `pip install garminconnect garth requests`
- **认证失败**：检查邮箱/密码和区域设置（中国区用 `GARMIN_IS_CN=true`）
- **需要 MFA**：设置 `GARMIN_MFA_CODE` 后重试
- **数据为空**：部分指标依赖设备型号，可能返回 `no_data`
- **限流 (429)**：等待后重试，避免频繁请求

详细文档请查看 **reference.md**。

## 许可证

MIT-0。可自由使用、修改和分发。
