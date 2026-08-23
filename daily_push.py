# -*- coding: utf-8 -*-
"""滚IC每日盘前推送：抓数 → 计算快照 → 飞书卡片

本地测试：python daily_push.py --dry-run   （只打印卡片内容，不发送）
CI 环境：由 GitHub Actions 每个交易日北京时间 08:30 触发
"""
import argparse
import os
import sys
import traceback
from datetime import date, timedelta

import pandas as pd

import data_layer as m
import feishu

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

TIER_EMOJI = {"green": "🟢", "yellow": "🟡", "red": "🔴", "na": "⚪"}
HEADER_COLOR = {"green": "green", "yellow": "orange", "red": "red", "na": "blue"}


def compute_snapshot():
    """抓取全部数据并计算当日快照，返回字典；失败抛异常"""
    today = date.today()
    pr = m.fetch_index(
        m.INDEX_CODE,
        (today - timedelta(days=365 * 11)).strftime("%Y%m%d"),
        today.strftime("%Y%m%d"),
    )
    tr = m.fetch_index(
        m.TR_CODE,
        (today - timedelta(days=365 * m.CALENDAR_YEARS + 40)).strftime("%Y%m%d"),
        today.strftime("%Y%m%d"),
    )
    cal, annual_div = m.build_dividend_calendar(pr, tr, today)

    contracts, data_date = [], None
    for c in m.active_contracts(today):
        row = {"label": c["label"], "code": c["code"], "expiry": c["expiry"]}
        try:
            fut = m.fetch_future(c["code"])
        except Exception:
            # 当月合约到期摘牌次日，新的下月合约刚挂牌、尚无行情，属正常情况
            row["empty"] = True
            contracts.append(row)
            continue
        dd = min(pr["date"].max(), fut["date"].max()).date()
        data_date = dd if data_date is None else max(data_date, dd)
        fut_close = float(fut.loc[fut["date"] <= pd.Timestamp(dd), "close"].iloc[-1])
        idx_close = float(pr.loc[pr["date"] <= pd.Timestamp(dd), "close"].iloc[-1])
        days = (c["expiry"] - dd).days
        basis = idx_close - fut_close
        gross_ann = basis / idx_close * 365 / days if days > 0 else float("nan")
        div_ann = m.expected_dividend(cal, dd, c["expiry"]) * 365 / days if days > 0 else float("nan")
        net_ann = gross_ann - div_ann
        erosion_pp = div_ann * 100
        rel = div_ann / gross_ann if gross_ann > 0 else float("nan")
        alert = erosion_pp >= m.EROSION_PP_ALERT or (gross_ann > 0 and rel >= m.EROSION_REL_ALERT)
        basis_th = m.BASIS_TH_NEAR if c["label"] in ("当月", "下月") else m.BASIS_TH_FAR
        row.update(
            empty=False, date=dd, idx=idx_close, fut=fut_close, basis=basis, days=days,
            gross=gross_ann * 100, erosion=erosion_pp, net=net_ann * 100,
            basis_th=basis_th, worth=basis >= basis_th, alert=alert,
        )
        contracts.append(row)

    if data_date is None:
        raise RuntimeError("所有IC合约均无行情，数据源异常")

    pe_latest, pcts = m.pe_percentiles(pr, today)
    idx_close_last = float(pr["close"].iloc[-1])
    pct10 = pcts.get("近10年")
    if pct10 is None:
        tier = {"level": "na", "text": "估值分位数据不足"}
    elif pct10 < m.ENTRY_PE_PCT:
        tier = {"level": "green", "text": f"估值舒服买点（近10年分位{pct10}%）"}
    elif pct10 < 90:
        tier = {"level": "yellow", "text": f"估值分位{pct10}%：可滚，注意仓位力度"}
    else:
        tier = {"level": "red", "text": f"估值分位{pct10}%：显而易见别上"}

    return {
        "today": today, "data_date": data_date,
        "idx_close": idx_close_last, "pe": pe_latest, "pcts": pcts,
        "tier": tier, "annual_div": annual_div, "contracts": contracts,
    }


def _div(md):
    return {"tag": "div", "text": {"tag": "lark_md", "content": md}}


def _hr():
    return {"tag": "hr"}


def _note(text):
    return {"tag": "note", "elements": [{"tag": "plain_text", "content": text}]}


def dashboard_url():
    url = os.environ.get("DASHBOARD_URL")
    if url:
        return url
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if repo and "/" in repo:
        owner, name = repo.split("/", 1)
        return f"https://{owner}.github.io/{name}/"
    return ""


def build_card(snap):
    tier = snap["tier"]
    p = snap["pcts"]
    elements = []

    est = [f"**中证500 {snap['idx_close']:,.2f}　PE-TTM {snap['pe']:.2f}**"]
    if p:
        est.append(
            "估值分位：近5年 {}%｜近10年 **{}%**｜全历史 {}%".format(
                p.get("近5年", "-"), p.get("近10年", "-"), p.get("全历史", "-")
            )
        )
    est.append(f"{TIER_EMOJI[tier['level']]} **{tier['text']}**")
    elements.append(_div("\n".join(est)))
    elements.append(_hr())

    lines = []
    for r in snap["contracts"]:
        if r.get("empty"):
            lines.append(f"**{r['label']} {r['code']}**：新挂牌暂无行情")
            continue
        if r["alert"]:
            status = "⚠️跨分红季·年化有水分"
        elif r["worth"]:
            status = "✓值得滚"
        else:
            status = "贴水偏薄"
        lines.append(
            f"**{r['label']} {r['code']}**（{r['days']}天后到期）基差 {r['basis']:.0f}点 / 门槛{r['basis_th']}\n"
            f"表面 {r['gross']:.1f}% − 虚胖 {r['erosion']:.1f}pp ＝ **真实 {r['net']:.1f}%**　{status}"
        )
    elements.append(_div("\n\n".join(lines)))
    elements.append(_hr())

    far = [r for r in snap["contracts"] if not r.get("empty") and r["label"] in ("季月", "次季")]
    far_best = max((r["net"] for r in far), default=None)
    sig = []
    if far_best is None:
        sig.append("⚪ 季月/次季暂无数据，今日无法给出信号")
    elif tier["level"] == "red":
        sig.append(f"🔴 作者口径：估值分位≥90%，显而易见别上（季月/次季最高真实年化 {far_best:.1f}%）")
    elif tier["level"] == "green" and far_best >= m.ENTRY_NET_ANN * 100:
        sig.append(f"✅ 双条件满足：估值便宜 + 真实年化 {far_best:.1f}% ≥ 10%，作者口径的入场区")
    elif tier["level"] == "green":
        sig.append(f"🟢 估值便宜，但贴水偏薄：季月/次季最高真实年化 {far_best:.1f}%（目标≥10%）")
    else:
        sig.append(f"🟡 可滚，注意仓位力度；季月/次季最高真实年化 {far_best:.1f}%")
    for r in snap["contracts"]:
        if not r.get("empty") and r["alert"]:
            sig.append(
                f"⚠️ {r['code']} 跨分红季：表面 {r['gross']:.1f}% 里有 {r['erosion']:.1f}pp 是分红虚胖，真实仅 {r['net']:.1f}%"
            )
    elements.append(_div("\n".join(sig)))

    url = dashboard_url()
    if url:
        elements.append(
            _div(f"📈 完整面板（近一年曲线）：[点这里打开]({url})")
        )

    elements.append(
        _note(
            f"口径：基差=指数−期货；真实年化=表面年化−分红侵蚀；数据截至 {snap['data_date']} 收盘；"
            f"年化分红参考 {snap['annual_div']:.2%}"
        )
    )

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": HEADER_COLOR[tier["level"]],
            "title": {"tag": "plain_text", "content": f"滚IC盘前日报 · {snap['data_date']}收盘数据"},
        },
        "elements": elements,
    }


def error_card(err_text):
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "red",
            "title": {"tag": "plain_text", "content": f"滚IC日报异常 · {date.today()}"},
        },
        "elements": [
            _div(f"数据抓取或计算失败，请手动检查：\n```\n{err_text[:500]}\n```"),
            _note("可在 GitHub 仓库 Actions 页面查看运行日志并手动重跑"),
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="只打印卡片内容，不发送")
    args = parser.parse_args()

    try:
        snap = compute_snapshot()
        card = build_card(snap)
    except Exception:
        err = traceback.format_exc()
        print(err)
        card = error_card(err)

    if args.dry_run:
        print("\n===== 卡片预览（dry-run） =====")
        print(f"标题: {card['header']['title']['content']}  [template={card['header']['template']}]")
        for el in card["elements"]:
            if el.get("tag") == "div":
                print("-" * 40)
                print(el["text"]["content"])
            elif el.get("tag") == "note":
                print("-" * 40)
                print("note:", el["elements"][0]["content"])
        return

    if not os.environ.get("FEISHU_WEBHOOK"):
        print("⚠ 未配置 FEISHU_WEBHOOK（仓库Secret），本次跳过飞书推送；面板数据仍会正常更新")
        return

    feishu.push_card(card)
    print("飞书日报已推送")


if __name__ == "__main__":
    main()
