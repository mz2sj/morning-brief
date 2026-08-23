# -*- coding: utf-8 -*-
"""飞书推送：优先走自建应用 OpenAPI（个人账号可用），Webhook 作为备选"""
import json
import os

import requests

FEISHU_HOST = "https://open.feishu.cn"


def _tenant_token(app_id, app_secret):
    r = requests.post(
        f"{FEISHU_HOST}/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": app_id, "app_secret": app_secret},
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    if data.get("code") != 0 or not data.get("tenant_access_token"):
        raise RuntimeError(f"获取 tenant_access_token 失败: {data}")
    return data["tenant_access_token"]


def push_card_via_app(card, app_id=None, app_secret=None, open_id=None):
    """用自建应用以 bot 身份给用户发交互卡片"""
    app_id = app_id or os.environ.get("FEISHU_APP_ID")
    app_secret = app_secret or os.environ.get("FEISHU_APP_SECRET")
    open_id = open_id or os.environ.get("FEISHU_OPEN_ID")
    if not (app_id and app_secret and open_id):
        raise RuntimeError("缺少 FEISHU_APP_ID / FEISHU_APP_SECRET / FEISHU_OPEN_ID")
    token = _tenant_token(app_id, app_secret)
    r = requests.post(
        f"{FEISHU_HOST}/open-apis/im/v1/messages",
        params={"receive_id_type": "open_id"},
        headers={"Authorization": f"Bearer {token}"},
        json={
            "receive_id": open_id,
            "msg_type": "interactive",
            "content": json.dumps(card, ensure_ascii=False),
        },
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    if data.get("code") != 0:
        raise RuntimeError(f"飞书发消息失败: {data}")
    return data


def push_card_via_webhook(card, webhook=None, secret=None):
    """企业版自定义机器人 Webhook（个人账号通常不可用）"""
    import base64
    import hashlib
    import hmac
    import time

    webhook = webhook or os.environ.get("FEISHU_WEBHOOK")
    secret = secret or os.environ.get("FEISHU_SECRET")
    if not webhook:
        raise RuntimeError("缺少 FEISHU_WEBHOOK")
    body = {"msg_type": "interactive", "card": card}
    if secret:
        ts = str(int(time.time()))
        msg = f"{ts}\n{secret}".encode("utf-8")
        body["timestamp"] = ts
        body["sign"] = base64.b64encode(hmac.new(msg, digestmod=hashlib.sha256).digest()).decode("utf-8")
    resp = requests.post(webhook, json=body, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code", 0) != 0 or data.get("StatusCode", 0) != 0:
        raise RuntimeError(f"飞书 Webhook 返回错误: {data}")
    return data


def push_card(card):
    """优先自建应用，其次 Webhook"""
    if os.environ.get("FEISHU_APP_ID") and os.environ.get("FEISHU_APP_SECRET") and os.environ.get("FEISHU_OPEN_ID"):
        return push_card_via_app(card)
    if os.environ.get("FEISHU_WEBHOOK"):
        return push_card_via_webhook(card)
    raise RuntimeError("未配置飞书推送凭证（需要 FEISHU_APP_ID+SECRET+OPEN_ID，或 FEISHU_WEBHOOK）")
