# -*- coding: utf-8 -*-
"""飞书自定义机器人 Webhook 推送（支持加签）"""
import base64
import hashlib
import hmac
import os
import time

import requests


def _sign(secret, timestamp):
    msg = f"{timestamp}\n{secret}".encode("utf-8")
    return base64.b64encode(hmac.new(msg, digestmod=hashlib.sha256).digest()).decode("utf-8")


def push_card(card, webhook=None, secret=None):
    webhook = webhook or os.environ.get("FEISHU_WEBHOOK")
    secret = secret or os.environ.get("FEISHU_SECRET")
    if not webhook:
        raise RuntimeError("缺少 FEISHU_WEBHOOK（GitHub仓库Secret 或 环境变量）")
    body = {"msg_type": "interactive", "card": card}
    if secret:
        ts = str(int(time.time()))
        body["timestamp"] = ts
        body["sign"] = _sign(secret, ts)
    resp = requests.post(webhook, json=body, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code", 0) != 0 or data.get("StatusCode", 0) != 0:
        raise RuntimeError(f"飞书返回错误: {data}")
    return data
