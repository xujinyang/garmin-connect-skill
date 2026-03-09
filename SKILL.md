---
name: garmin-connect-skill
description: 获取 Garmin Connect 健康数据（睡眠、心率、压力、步数等）和本地归档同步。当用户请求 Garmin 数据、connect.garmin.cn、或提到 睡眠/心率/压力/步数 时使用此技能。
version: 2.0.0
metadata:
  homepage: https://github.com/xujinyang/garmin-connect-skill
---

# Garmin Connect 健康数据

## 使用场景

当用户提到以下关键词时使用此技能：
- `Garmin Connect`、`garmin.cn`、`佳明`
- `睡眠 `、` 心率 `、` 压力`、`步数`、`健康数据`
- `身体电量 `、`HRV`、` 血氧`、`呼吸率`

## 标准响应流程

### 第一步：响应模板

当用户请求 Garmin 数据时，首先展示可获取的指标列表：

```
我可以帮您获取以下 Garmin 健康数据：

【常用指标】
• 睡眠数据 - 总睡眠时间、入睡/起床时间、睡眠评分
• 心率 - 静息心率、每日最低/最高心率
• 压力 - 平均压力值、压力分布
• 步数 - 总步数、目标完成度、距离、卡路里
• 身体电量 - 充电/消耗电量、最低/最高水平
• HRV - 夜间平均值、7 天平均值、基线状态

【其他指标】
• 楼层数、强度分钟数、血氧、呼吸率
• 体重、血压、健身年龄、训练状态/准备度
• 比赛预测、骑行 FTP、乳酸阈值

【数据归档】
• 初始化本地归档 - 拉取所有历史数据到本地，支持后续增量更新

请告诉我您想查看哪个指标？日期是哪天？（不指定则默认为今天）
```

### 第二步：判断登录状态

运行脚本检测是否有可用 token：

```bash
python3 scripts/fetch_garmin_metrics.py --metric summary --date 2026-03-09 --pretty
```

**情况 A - 已有 token**：直接返回数据，用自然语言总结关键指标

**情况 B - 未登录**：脚本会提示输入账号密码
- 提示：`🔐 未检测到 Garmin 登录信息，请输入账号密码进行登录`
- 依次输入：邮箱 → 密码 → 验证码（如开启 MFA）
- 登录成功后显示：`✅ 登录成功！Token 已保存到 ~/.garminconnect/`
- 后续使用无需重复登录

### 第三步：返回结果

- 先说结论（自然语言总结关键数据）
- 仅在用户明确要求时展示完整 JSON

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
| **初始化归档** | `init-archive` | 首次拉取全部历史数据到本地 |

## 命令示例

### 获取单日数据

```bash
# 今日摘要（默认）
python3 scripts/fetch_garmin_metrics.py --metric summary --pretty

# 指定日期
python3 scripts/fetch_garmin_metrics.py --metric sleep --date 2026-03-08 --pretty

# 指定指标和日期
python3 scripts/fetch_garmin_metrics.py --metric heart-rate --date 2026-03-08 --pretty
```

### 获取时间段数据

```bash
# 查询某一周的步数
python3 scripts/fetch_garmin_metrics.py --metric steps --start-date 2026-03-01 --end-date 2026-03-07 --pretty
```

### 获取全部指标

```bash
# 单日所有指标
python3 scripts/fetch_garmin_metrics.py --metric all --date 2026-03-09 --pretty

# 时间段所有指标
python3 scripts/fetch_garmin_metrics.py --metric all --start-date 2026-03-01 --end-date 2026-03-07 --pretty
```

### 初始化本地归档

```bash
# 指定日期范围
python3 scripts/fetch_garmin_metrics.py --metric init-archive --start-date 2024-01-01 --end-date 2026-03-09 --archive-dir garmin_archive --pretty

# 自动检测最早日期
python3 scripts/fetch_garmin_metrics.py --metric init-archive --archive-dir garmin_archive --pretty
```

### 增量同步归档

```bash
python3 scripts/sync_garmin_archive.py --mode incremental --archive-dir garmin_archive --pretty
```

## 归档工作流

### 何时使用归档

- 用户希望保留所有历史数据的本地备份
- 需要离线查询过去的数据
- 希望避免频繁请求 Garmin API

### 归档结构

```
garmin_archive/
├── state.json          # 同步状态记录
├── daily/              # 每日数据
│   ├── summary.jsonl
│   ├── sleep.jsonl
│   ├── steps.jsonl
│   └── ...
├── health/             # 健康指标
│   ├── weight.jsonl
│   ├── blood-pressure.jsonl
│   └── ...
├── advanced/           # 高级指标
│   ├── hrv.jsonl
│   └── fitness-age.jsonl
├── performance/        # 运动表现
│   ├── training-status.jsonl
│   └── ...
└── activities/         # 运动记录
    └── activities.jsonl
```

### 归档规则

- `init` 模式：仅首次使用，全量回写历史数据
- `incremental` 模式：后续日常同步，仅获取新日期
- 归档目录应放在技能目录外，如 `~/garmin_archive`
- 使用 `state.json` 追踪已同步的最后日期

## 环境变量（可选）

脚本优先使用交互式登录，无需预先配置环境变量。

如需预设，可在 `~/.garminconnect/.env` 配置：

```bash
GARMIN_EMAIL=your-account@example.com
GARMIN_PASSWORD=your-password
GARMIN_IS_CN=true          # 中国区账号，默认 true
GARMINTOKENS=~/.garminconnect
GARMIN_MFA_CODE=123456     # 仅在需要 MFA 时设置
```

## 响应规则

1. **先说人话**：先用自然语言总结关键数据，再展示 JSON
2. **睡眠**：强调总时长、入睡/起床时间、睡眠评分
3. **心率**：强调静息心率、日最低/最高值
4. **压力**：强调整体压力水平、压力分布
5. **步数**：强调总步数、目标完成度、距离
6. **HRV**：强调夜间平均、7 天平均、基线状态
7. **身体电量**：强调充电量、消耗量
8. **无数据**：明确告知用户该指标无数据，而非报错

## 安全与可靠性

- 绝不向用户展示完整账号密码
- 优先复用 token 文件，避免重复登录
- 登录失败时说明可能原因（密码错误/MFA/限流）
- 默认使用窄日期范围，除非用户明确要求历史数据
