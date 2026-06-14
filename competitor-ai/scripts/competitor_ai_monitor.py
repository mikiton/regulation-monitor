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
BASE = ROOT / "competitor-ai"
SOURCES = BASE / "sources" / "competitor_ai_sources.yml"
STATE = BASE / "state" / "competitor_ai_snapshots.json"
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
        r = requests.get(url, timeout=25, headers={"User-Agent": "competitor-ai-monitor"})
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
        f"# 島津競合AI動向モニタリングレポート {date}",
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
                "- 島津製作所への示唆: 分析機器AI、ラボ自動化、医用AI、サービスAI、ソフトウェア、データ基盤、AIX推進への影響有無を確認してください。",
                f"- 情報源: {r['url']}",
                "",
            ]

    lines += [
        "## 島津製作所への確認ポイント",
        "",
        "- 分析機器・計測機器におけるAI搭載製品、解析ソフト、スマートラボ化の動向を確認する。",
        "- 医用・診断AI、画像解析、検査自動化、遠隔保守・サービス高度化への示唆を確認する。",
        "- 競合の提携、買収、クラウド・データ基盤、AIソフトウェア戦略を確認する。",
        "- 島津のAIX重点テーマ（営業、製造、SCM、サービス、開発、コーポレート）への横展開可能性を整理する。",
        "",
    ]

    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / f"{date}.md").write_text("\n".join(lines), encoding="utf-8")
    save_state(state)
    print(f"Wrote competitor-ai/reports/{date}.md")


if __name__ == "__main__":
    main()
