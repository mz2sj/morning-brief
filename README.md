# morning-brief

每个工作日早晨自动运行的数据简报流水线：定时抓取公开数据源 → 计算统计指标 → 推送飞书卡片 → 更新静态数据面板。基于 GitHub Actions 定时任务，无需本机开机。

## 文件结构

| 文件 | 作用 |
|------|------|
| `daily_push.py` | 抓数 → 计算当日指标 → 推送飞书卡片 |
| `build_dashboard.py` | 重建近一年历史序列（`docs/assets/data.js`） |
| `data_layer.py` | 数据层（纯 requests，无重型依赖） |
| `feishu.py` | 飞书 Webhook 推送（支持加签） |
| `docs/` | 静态数据面板（ECharts，data.js 每日由 CI 更新） |
| `.github/workflows/daily-brief.yml` | 定时任务（工作日 08:30，北京时间） |

## 部署步骤（一次性，约10分钟）

### 1. 建飞书机器人

1. 飞书群 → **群设置 → 群机器人 → 添加机器人 → 自定义机器人**
2. 复制生成的 **Webhook 地址**
3. （可选）安全设置勾选"签名校验"，复制 **secret**；不勾则无需 secret

### 2. 配置仓库 Secret

仓库 **Settings → Secrets and variables → Actions → New repository secret**：

| Name | Value |
|------|-------|
| `FEISHU_WEBHOOK` | 步骤1的 Webhook 地址 |
| `FEISHU_SECRET` | （仅当开启了签名校验）签名 secret |

> Webhook 存在 Secret 中，仓库代码不包含任何密钥。

### 3. 开启 GitHub Pages（可选，用于网页面板）

仓库 **Settings → Pages → Source: Deploy from a branch → Branch: main / 目录选 `docs`** → Save

面板地址：`https://<用户名>.github.io/<仓库名>/`

### 4. 手动跑一次验证

仓库 **Actions → daily-brief → Run workflow**，几分钟后飞书群里应收到卡片。

## 日常说明

- 每个工作日 08:30 左右自动收到卡片（GitHub 定时任务可能延迟几分钟，属正常）
- 收到红色"异常"卡片时：去 Actions 页看日志，通常是数据源临时抽风，手动 Run workflow 重跑即可
- 修改推送时间：编辑 `.github/workflows/daily-brief.yml` 里的 cron（UTC 时区，北京时间需减 8 小时）

## 本地调试

```bash
pip install -r requirements.txt
python daily_push.py --dry-run     # 只打印卡片内容，不发送
DASHBOARD_DIR=docs python build_dashboard.py   # 重建面板数据
```
