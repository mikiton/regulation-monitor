#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "manufacturing-dx"
SOURCES = BASE / "sources" / "manufacturing_dx_sources.yml"
STATE = BASE / "state" / "manufacturing_dx_snapshots.json"
REPORTS = BASE / "reports"


def today_jst():
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date().isoformat()


def clean_html(text: str) -> str:
    text = re.sub(r"<script[\s\S]*?</script>", " ", text, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def load_state():
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {"sources": {}}


def save_state(state):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fetch(url: str):
    try:
        r = requests.get(url, timeout=25, headers={"User-Agent": "manufacturing-dx-monitor"})
        r.raise_for_status()
        return clean_html(r.text), None
    except Exception as e:
        return None, str(e)


def main():
    date = today_jst()
    config = yaml.safe_load(SOURCES.read_text(encoding="utf-8"))
    state = load_state()
    state.setdefault("sources", {})
    rows = []

    for group in config.get("categories", []):
        category = group["name"]
        for src in group.get("sources", []):
            url = src["url"]
            title = src["title"]
            text, err = fetch(url)
            prev = state["sources"].get(url, {})
            first = url not in state["sources"]
            changed = False
            if text:
                h = digest(text)
                changed = (not first) and prev.get("sha256") != h
                state["sources"][url] = {"title": title, "category": category, "sha256": h, "last_checked": date, "status": "ok"}
            else:
                state["sources"][url] = {**prev, "title": title, "category": category, "last_checked": date, "status": "error", "error": err}
            rows.append({"category": category, "title": title, "url": url, "first": first, "changed": changed, "error": err})

    changed_count = sum(1 for r in rows if r["changed"])
    error_count = sum(1 for r in rows if r["error"])

    lines = [
        f"# SAP／PLM／SCM・製造DXモニタリングレポート {date}",
        "",
        "## 本日の重要ポイント",
        "",
        f"- 監視対象URL数: {len(rows)}",
        f"- ページ変更検出: {changed_count}",
        f"- 取得エラー: {error_count}",
        "",
        "> 注: 本レポートは公式・信頼情報源ページの変更検知を起点とする一次スクリーニングです。重要項目はリンク先の原文確認が必要です。",
        "",
    ]

    for category in sorted(set(r["category"] for r in rows)):
        lines += [f"## {category}", ""]
        for r in [x for x in rows if x["category"] == category]:
            status = "初回取得" if r["first"] else ("変更あり" if r["changed"] else "変更なし")
            if r["error"]:
                status = "取得エラー"
            importance = "中" if (r["changed"] or r["error"]) else "低"
            lines += [
                f"### {r['title']}",
                "",
                f"- 状態: {status}",
                f"- 重要度: {importance}",
                "- 島津製作所への示唆: SAP導入、PLM/SAP連携、MDG、BOM/ロット/原産地、規制対応、SCM最適化、製造DXへの影響有無を確認してください。",
                f"- 情報源: {r['url']}",
                "",
            ]

    lines += [
        "## 島津製作所への確認ポイント",
        "",
        "- SAP、PLM、E-System、NEO、WMSなど周辺システムとの連携示唆を確認する。",
        "- 製品含有化学物質、原産地、DPP、トレーサビリティへの影響を確認する。",
        "- SCM/ロジ、需給、在庫、納期回答、調達リスクへの活用可能性を整理する。",
        "- AIX推進テーマとしてAIエージェント、ERP AI、PLM AI、SCM AIの活用余地を確認する。",
        "",
    ]

    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / f"{date}.md").write_text("\n".join(lines), encoding="utf-8")
    save_state(state)
    print(f"Wrote manufacturing-dx/reports/{date}.md")


if __name__ == "__main__":
    main()
