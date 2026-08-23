# -*- coding: utf-8 -*-
"""构建滚IC HTML面板数据：回溯近一年，逐日重建估值分位与4张合约的贴水年化序列

输出 {DASHBOARD_DIR}/assets/data.js（嵌入JSON），供 ECharts 前端渲染。
DASHBOARD_DIR 环境变量可指定面板目录，默认 roll-ic-dashboard；云端CI设为 docs。
"""
import json
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import data_layer as m

REPORT_DIR = HERE / os.environ.get("DASHBOARD_DIR", "roll-ic-dashboard")
ASSETS = REPORT_DIR / "assets"
LOOKBACK_DAYS = 365


def codes_needed(start, end):
    """窗口内每个交易日处于交易状态的合约代码并集"""
    codes = set()
    d = start
    while d <= end:
        for c in m.active_contracts(d):
            codes.add(c["code"])
        d += timedelta(days=1)
    return sorted(codes)


def rolling_pctile(pr, dates, years):
    """对每个历史交易日，计算PE在滚动的years年窗口内的分位"""
    pe_df = pr.dropna(subset=["pe"]).reset_index(drop=True)
    ts = pd.DatetimeIndex(pe_df["date"])
    pe_vals = pe_df["pe"].to_numpy()
    out = []
    for d in dates:
        t = pd.Timestamp(d)
        lo = ts.searchsorted(t - pd.Timedelta(days=365 * years), side="left")
        hi = ts.searchsorted(t, side="right")
        window = pe_vals[lo:hi]
        cur = pe_vals[hi - 1] if hi > lo else None
        if cur is None or len(window) == 0:
            out.append(None)
        else:
            out.append(round(float((window <= cur).mean() * 100), 1))
    return out


def main():
    today = date.today()
    start = today - timedelta(days=LOOKBACK_DAYS)

    print("拉取中证500价格指数(11年)...")
    pr = m.fetch_index(m.INDEX_CODE, (today - timedelta(days=365 * 11)).strftime("%Y%m%d"), today.strftime("%Y%m%d"))
    print("拉取中证500全收益指数(5年)...")
    tr = m.fetch_index(m.TR_CODE, (today - timedelta(days=365 * m.CALENDAR_YEARS + 40)).strftime("%Y%m%d"), today.strftime("%Y%m%d"))

    cal, annual_div = m.build_dividend_calendar(pr, tr, today)

    dates = [d.date() for d in pr.loc[pr["date"] >= pd.Timestamp(start), "date"]]
    print(f"回溯区间 {dates[0]} ~ {dates[-1]}，共 {len(dates)} 个交易日")

    codes = codes_needed(dates[0], dates[-1])
    print(f"需要 {len(codes)} 张合约: {codes}")
    fut_px = {}
    for i, code in enumerate(codes, 1):
        try:
            df = m.fetch_future(code)
            fut_px[code] = dict(zip(df["date"].dt.strftime("%Y-%m-%d"), df["close"].astype(float)))
            print(f"  [{i}/{len(codes)}] {code}: {len(df)} 根K线")
        except Exception as e:
            print(f"  [{i}/{len(codes)}] {code}: 无数据({type(e).__name__})，跳过")
        time.sleep(0.4)

    pct5 = rolling_pctile(pr, dates, 5)
    pct10 = rolling_pctile(pr, dates, 10)

    idx_close = [round(float(pr.loc[pr["date"] == pd.Timestamp(d), "close"].iloc[0]), 2) for d in dates]
    pe = [None if pd.isna(v) else round(float(v), 2) for v in
          (pr.set_index("date").reindex(pd.to_datetime(dates))["pe"])]

    slots = {k: {"gross": [], "net": [], "erosion": [], "basis": [], "idx": [], "fut": [], "expiry": [], "code": []} for k in ["当月", "下月", "季月", "次季"]}
    for d in dates:
        key = d.isoformat()
        contracts = m.active_contracts(d)
        idx = float(pr.loc[pr["date"] == pd.Timestamp(d), "close"].iloc[0])
        for c in contracts:
            s = slots[c["label"]]
            px = fut_px.get(c["code"], {}).get(key)
            days = (c["expiry"] - d).days
            if px is None or days <= 0:
                for f in ("gross", "net", "erosion", "basis", "idx", "fut"):
                    s[f].append(None)
                s["expiry"].append(None)
                s["code"].append(c["code"])
                continue
            gross = (idx - px) / idx * 365 / days
            div_ann = m.expected_dividend(cal, d, c["expiry"]) * 365 / days
            net = gross - div_ann
            s["gross"].append(round(gross * 100, 2))
            s["net"].append(round(net * 100, 2))
            s["erosion"].append(round(div_ann * 100, 2))
            s["basis"].append(round(idx - px, 1))
            s["idx"].append(idx)
            s["fut"].append(px)
            s["expiry"].append(c["expiry"].isoformat())
            s["code"].append(c["code"])

    last = len(dates) - 1
    latest_rows = []
    for label in ["当月", "下月", "季月", "次季"]:
        s = slots[label]
        i = last
        while i >= 0 and s["net"][i] is None:
            i -= 1
        if i < 0:
            latest_rows.append({"label": label, "code": s["code"][last] if s["code"] else "-", "empty": True})
            continue
        gross, net, ero, basis = s["gross"][i], s["net"][i], s["erosion"][i], s["basis"][i]
        alert = (ero >= m.EROSION_PP_ALERT) or (gross and gross > 0 and ero / gross >= m.EROSION_REL_ALERT)
        basis_th = m.BASIS_TH_NEAR if label in ("当月", "下月") else m.BASIS_TH_FAR
        worth = basis is not None and basis >= basis_th
        latest_rows.append({
            "label": label, "code": s["code"][i], "date": dates[i].isoformat(),
            "expiry": s["expiry"][i], "days": (date.fromisoformat(s["expiry"][i]) - dates[i]).days,
            "gross": gross, "net": net, "erosion": ero, "basis": basis,
            "idx": s["idx"][i], "fut": s["fut"][i],
            "basisTh": basis_th, "worth": bool(worth),
            "alert": bool(alert), "empty": False,
        })

    pe_now = pct10[last] if pct10[last] is not None else None
    if pe_now is None:
        tier = {"level": "na", "text": "估值分位数据不足", "pct": None}
    elif pe_now < m.ENTRY_PE_PCT:
        tier = {"level": "green", "text": f"估值舒服买点（分位{pe_now}%）", "pct": pe_now}
    elif pe_now < 90:
        tier = {"level": "yellow", "text": f"估值分位{pe_now}%：可滚，注意仓位力度", "pct": pe_now}
    else:
        tier = {"level": "red", "text": f"估值分位{pe_now}%：显而易见别上", "pct": pe_now}

    payload = {
        "meta": {
            "generated": today.isoformat(),
            "dataRange": [dates[0].isoformat(), dates[-1].isoformat()],
            "annualDividend": round(annual_div * 100, 2),
            "tier": tier,
            "thresholds": {"entryPePct": m.ENTRY_PE_PCT, "exitPePct": 90,
                           "basisNear": m.BASIS_TH_NEAR, "basisFar": m.BASIS_TH_FAR,
                           "erosionAlert": m.EROSION_PP_ALERT},
        },
        "dates": [d.isoformat() for d in dates],
        "idxClose": idx_close,
        "pe": pe,
        "pct5": pct5,
        "pct10": pct10,
        "slots": slots,
        "latest": latest_rows,
    }
    ASSETS.mkdir(parents=True, exist_ok=True)
    out = ASSETS / "data.js"
    out.write_text("window.ROLL_IC = " + json.dumps(payload, ensure_ascii=False) + ";\n", encoding="utf-8")
    print(f"\n已生成 {out} ({out.stat().st_size/1024:.0f} KB)")
    print(f"估值档位: {tier['text']} | 次季基差: {next((r['basis'] for r in latest_rows if r['label']=='次季' and not r.get('empty')), None)}")


if __name__ == "__main__":
    main()
