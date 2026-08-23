# -*- coding: utf-8 -*-
"""滚IC数据层：中证500估值 + IC合约行情（纯requests实现，无akshare依赖）

数据源：
- 中证指数官网：000905 价格指数 / H00905 全收益指数（含滚动市盈率）
- 新浪财经：IC 各月合约日K
设计目标：在 GitHub Actions（海外服务器）上稳定运行。
"""
import json
import os
import re
from datetime import date, timedelta

import pandas as pd
import requests

INDEX_CODE = "000905"    # 中证500 价格指数
TR_CODE = "H00905"       # 中证500 全收益指数
CALENDAR_YEARS = 5       # 分红日历使用的样本年数
NOISE_FLOOR = 5e-5       # 指数点位保留2位小数，单日舍入噪声低于此值一律视为0
EROSION_PP_ALERT = 1.5   # 分红侵蚀绝对阈值（年化百分点）
EROSION_REL_ALERT = 0.30 # 分红侵蚀占毛贴水比例阈值
PE_WINDOWS = [("近5年", 365 * 5), ("近10年", 365 * 10), ("全历史", None)]
ENTRY_PE_PCT = 20        # 猫笔刀口径：估值分位舒服买点
ENTRY_NET_ANN = 0.10     # 猫笔刀口径：净贴水年化值得干
BASIS_TH_NEAR = 60       # 当月/下月 基差门槛（点）
BASIS_TH_FAR = 70        # 季月/次季 基差门槛（点）

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.csindex.com.cn/",
}


def fetch_no_proxy(fn):
    """本地开着Clash但代理失效时，摘掉代理环境变量重试一次；CI环境无代理变量，无影响"""
    try:
        return fn()
    except Exception as first_err:
        keys = ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy")
        saved = {k: os.environ.pop(k) for k in keys if k in os.environ}
        if not saved:
            raise first_err
        try:
            return fn()
        finally:
            os.environ.update(saved)


def third_friday(year, month):
    # 中金所规则：到期月第三个周五；遇法定假日顺延（此处不处理，误差仅1-2个自然日）
    first_friday = 1 + (4 - date(year, month, 1).weekday()) % 7
    return date(year, month, first_friday + 14)


def active_contracts(today):
    """返回当日仍在交易的4张IC合约（当月/下月/季月/次季）"""
    y, m = today.year, today.month
    if today >= third_friday(y, m):
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    cur = (y, m)
    nxt = (y + 1, 1) if cur[1] == 12 else (cur[0], cur[1] + 1)
    quarters = sorted(
        (yy, mm)
        for yy in range(cur[0], cur[0] + 3)
        for mm in (3, 6, 9, 12)
        if (yy, mm) > nxt
    )[:2]
    return [
        {
            "label": label,
            "code": f"IC{yy % 100:02d}{mm:02d}",
            "expiry": third_friday(yy, mm),
        }
        for label, (yy, mm) in zip(["当月", "下月", "季月", "次季"], [cur, nxt, *quarters])
    ]


def fetch_index(code, start, end):
    """中证指数官网：日期/收盘/滚动市盈率（原始字段 tradeDate/close/peg）"""
    def call():
        r = requests.get(
            "https://www.csindex.com.cn/csindex-home/perf/index-perf",
            params={"indexCode": code, "startDate": start, "endDate": end},
            headers=HEADERS,
            timeout=30,
        )
        r.raise_for_status()
        return r.json().get("data") or []

    rows = fetch_no_proxy(call)
    if not rows:
        raise RuntimeError(f"csindex返回空数据: {code}")
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["tradeDate"], format="%Y%m%d")
    df["close"] = pd.to_numeric(df["close"])
    df["pe"] = pd.to_numeric(df["peg"], errors="coerce")
    return df[["date", "close", "pe"]].sort_values("date").reset_index(drop=True)


def fetch_future(code):
    """新浪期货日K：日期/收盘"""
    def call():
        url = (
            "https://stock2.finance.sina.com.cn/futures/api/jsonp.php/"
            "var%20_=/InnerFuturesNewService.getDailyKLine"
        )
        r = requests.get(url, params={"symbol": code}, headers=HEADERS, timeout=30)
        r.raise_for_status()
        m = re.search(r"\((\[.*\])\)", r.text, re.S)
        if not m:
            raise RuntimeError(f"新浪接口无数据: {code}")
        data = json.loads(m.group(1))
        if not data:
            raise RuntimeError(f"合约无行情: {code}")
        return data

    data = fetch_no_proxy(call)
    df = pd.DataFrame(data)
    df["date"] = pd.to_datetime(df["d"])
    df["close"] = pd.to_numeric(df["c"])
    return df[["date", "close"]].sort_values("date").reset_index(drop=True)


def build_dividend_calendar(pr, tr, today, years=CALENDAR_YEARS):
    """TR与PR日收益之差≈当日分红收益率；按(月,日)对齐多年取均值成分红日历"""
    df = pd.merge(pr, tr, on="date", suffixes=("_pr", "_tr")).sort_values("date")
    start = pd.Timestamp(today) - pd.Timedelta(days=365 * years + 31)
    df = df[df["date"] >= start].copy()
    diff = (df["close_tr"].pct_change() - df["close_pr"].pct_change()).clip(lower=0)
    df["div"] = diff.where(diff >= NOISE_FLOOR, 0.0)
    md = df["date"].apply(
        lambda d: (d.month, 28) if (d.month, d.day) == (2, 29) else (d.month, d.day)
    )
    cal = df.groupby(md)["div"].mean()
    cal.index = pd.MultiIndex.from_tuples(list(cal.index), names=["month", "day"])
    return cal, cal.sum()


def expected_dividend(cal, start, end):
    """(start, end] 区间内的预期分红收益率：分红日历逐日累加"""
    total, d = 0.0, start + timedelta(days=1)
    while d <= end:
        key = (d.month, 28) if (d.month, d.day) == (2, 29) else (d.month, d.day)
        total += cal.get(key, 0.0)
        d += timedelta(days=1)
    return total


def pe_percentiles(pr, today):
    pe = pr.dropna(subset=["pe"])
    if pe.empty:
        return None, {}
    latest = float(pe["pe"].iloc[-1])
    result = {}
    for name, days in PE_WINDOWS:
        sub = pe[pe["date"] >= pd.Timestamp(today) - pd.Timedelta(days=days)] if days else pe
        result[name] = round((sub["pe"] <= latest).mean() * 100, 1)
    return latest, result
