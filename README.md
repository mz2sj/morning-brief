# morning-brief

GitHub Actions 定时任务仓库。按 cron 在云端运行脚本，通过飞书发送提醒。本机关机不影响。

## 现有任务

| 工作流 | 触发 | 入口脚本 |
|--------|------|----------|
| `daily-brief` | 工作日 08:30（北京时间） | `daily_push.py` |

手动跑一次：仓库 **Actions → 对应工作流 → Run workflow**。

## 仓库结构

```
.github/workflows/   每个定时任务一个 yml
*.py                 任务脚本与公共模块
feishu.py            飞书发送封装（各任务共用）
requirements.txt     Python 依赖
```

凭证放在仓库 **Settings → Secrets and variables → Actions**，不要写进代码。

| Secret | 用途 |
|--------|------|
| `FEISHU_APP_ID` | 飞书自建应用 App ID |
| `FEISHU_APP_SECRET` | 飞书自建应用 App Secret |
| `FEISHU_OPEN_ID` | 接收人 open_id（`ou_...`） |

飞书应用需要：启用机器人、开通应用身份 `im:message`、发布版本、并在飞书里对该应用点过一次「发起会话」。

## 接入一条新的定时提醒

### 1. 写任务脚本

新建例如 `jobs/my_alert.py`（或仓库根目录 `my_alert.py`）。脚本只做两件事：准备内容，调用 `feishu.push_card`。

```python
# my_alert.py
import feishu

def build_card():
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "blue",
            "title": {"tag": "plain_text", "content": "提醒标题"},
        },
        "elements": [
            {
                "tag": "div",
                "text": {"tag": "lark_md", "content": "这里写正文，支持 **加粗** 和换行。"},
            }
        ],
    }

if __name__ == "__main__":
    feishu.push_card(build_card())
```

需要先算内容时，把计算写在 `build_card()` 前面即可；发送失败会抛异常，Actions 会标红。

本地预览（不发送）：在脚本里自己 `print`，或先注释掉 `push_card`。已有任务可用：

```bash
pip install -r requirements.txt
python daily_push.py --dry-run
```

### 2. 加工作流

在 `.github/workflows/` 新建 yml，例如 `my-alert.yml`：

```yaml
name: my-alert

on:
  schedule:
    # GitHub 用 UTC。北京时间 = UTC + 8
    # 每天 09:00 北京时间 → 01:00 UTC
    - cron: "0 1 * * *"
  workflow_dispatch: {}   # 允许在网页上手动跑

jobs:
  run:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip
      - run: pip install -r requirements.txt
      - name: 发送提醒
        env:
          FEISHU_APP_ID: ${{ secrets.FEISHU_APP_ID }}
          FEISHU_APP_SECRET: ${{ secrets.FEISHU_APP_SECRET }}
          FEISHU_OPEN_ID: ${{ secrets.FEISHU_OPEN_ID }}
        run: python my_alert.py
```

cron 最小间隔建议 ≥ 10 分钟。GitHub 定时任务可能延迟几分钟，属正常。

常用 cron（均为 UTC，括号内为北京时间）：

| 需求 | cron |
|------|------|
| 每个工作日 08:30 | `30 0 * * 1-5` |
| 每天 21:00 | `0 13 * * *` |
| 每周一 09:00 | `0 1 * * 1` |

### 3. 提交并验证

1. 把脚本和 yml 推进 `main`
2. **Actions → 新工作流 → Run workflow** 先手动跑通
3. 飞书收到消息即接入完成；之后按 cron 自动跑

同一套飞书 Secret 可给多条任务共用。若某条任务要发给另一个人，再加一个 Secret（例如 `FEISHU_OPEN_ID_2`），在该工作流的 `env` 里覆盖 `FEISHU_OPEN_ID`。

## 改已有任务的时间

只改对应 yml 里的 `cron`，提交即可。不要改任务脚本，除非提醒内容也要变。
