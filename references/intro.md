# Garmin Connect Skill 参考文档

## 交互式登录流程

当用户首次使用或未配置环境变量时，脚本会自动进入交互式登录流程：

### 登录提示

```
🔐 未检测到 Garmin 登录信息，请输入账号密码进行登录
Garmin 账号（邮箱）: [用户输入]
Garmin 密码：[用户输入]
```

### MFA 验证（如需要）

```
📱 Garmin 需要双重验证 (MFA)，请输入验证码
验证码：[用户输入]
```

### 登录成功

```
✅ 登录成功！Token 已保存到 ~/.garminconnect/
```

## 响应模板

### 标准开场白

当用户请求 Garmin 数据时，首先展示：

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

## 命令速查表

| 场景 | 命令 |
|------|------|
| 今日摘要 | `--metric summary --pretty` |
| 指定日期 | `--metric sleep --date 2026-03-09 --pretty` |
| 时间段 | `--metric steps --start-date 2026-03-01 --end-date 2026-03-07 --pretty` |
| 全部指标 | `--metric all --date 2026-03-09 --pretty` |
| 初始化归档 | `--metric init-archive --archive-dir garmin_archive --pretty` |
| 增量同步 | `scripts/sync_garmin_archive.py --mode incremental --archive-dir garmin_archive --pretty` |

## 输出结构

```json
{
  "ok": true,
  "metric": "sleep",
  "range": {
    "start_date": "2026-03-09",
    "end_date": "2026-03-09"
  },
  "items": [
    {
      "date": "2026-03-09",
      "metric": "sleep",
      "total_sleep_seconds": 28800,
      "total_sleep_hours": 8.0,
      "sleep_score": 85,
      ...
    }
  ],
  "generated_at": "2026-03-09T14:00:00Z",
  "source": {
    "service": "Garmin Connect",
    "domain": "garmin.cn"
  }
}
```

## 错误处理

| 错误 | 原因 | 解决方案 |
|------|------|----------|
| `Missing GARMIN_EMAIL` | 未配置账号 | 设置环境变量或交互式输入 |
| `Garmin authentication failed` | 密码错误 | 检查账号密码 |
| `Garmin MFA is required` | 需要验证码 | 设置 `GARMIN_MFA_CODE` 或输入验证码 |
| `no_data` | 设备不支持 | 该指标对当前设备/日期不可用 |
| `429 Too Many Requests` | 限流 | 等待后重试 |
