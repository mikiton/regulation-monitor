#!/usr/bin/env python3
"""Daily regulation monitoring script.

This first version monitors official/trusted source pages for changes, creates a
Japanese Markdown report, and stores a simple hash-based history.

It does not claim that every page change is a legal/regulatory update. Use the
report as an early-warning list and review the linked official sources.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import requests
import yaml

ROOT = Path(__file__).resolve().parents[1]
SOURCES_FILE = ROOT / "sources" / "official_sources.yml"
STATE_DIR = ROOT / "state"
STATE_FILE = STATE_DIR / "snapshots.json"
REPORTS_DIR = ROOT / "reports"

USER_AGENT = "regulation-monitor/0.1 (+https://github.com/mikiton/regulation-monitor)"


def jst_today() -> dt.date:
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date()


def normalize_text(text: str) -> str:
    text = re.sub(r"<script[\s\S]*?</script>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_state() -> dict[str, Any]:
    if not STATE_FILE.exists():
        return {"sources": {}}
    with STATE_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_state(state: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with STATE_FILE.open("w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")


def fetch_url(url: str) -> tuple[str | None, str | None]:
    try:
        res = requests.get(
            url,
            timeout=25,
            headers={"User-Agent": USER_AGENT},
            allow_redirects=True,
        )
        res.raise_for_status()
        return normalize_text(res.text), None
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)


def classify_importance(regulation_name: str, changed: bool, error: str | None) -> str:
    if error:
        return "中"
    if not changed:
        return "低"
    # Conservative first-pass classification. Users should review official pages.
    if regulation_name in {"EU AI Act", "Cyber Resilience Act", "CBAM"}:
        return "中"
    return "中"


def impact_note(regulation_name: str, changed: bool, error: str | None) -> str:
    if error:
        return "取得エラーのため、公式ページを直接確認してください。"
    if not changed:
        return "前回取得時点から大きなページ変更は検出されませんでした。"

    notes = {
        "RoHS": "製品含有化学物質管理、PLM/SAP/E-System連携、部品・材料情報の更新要否を確認してください。",
        "EU Battery Regulation": "電池搭載製品、サプライチェーン情報、デジタルバッテリーパスポート関連の影響を確認してください。",
        "CBAM": "輸出入・通関、原産地・サプライチェーン情報、対象材料の報告要否を確認してください。",
        "EU AI Act": "AI活用・AI搭載製品・AIガバナンス上の分類、責任分担、記録管理への影響を確認してください。",
        "Cyber Resilience Act": "ネットワーク接続製品、ソフトウェア、脆弱性対応、製品セキュリティ体制への影響を確認してください。",
    }
    return notes.get(regulation_name, "関連部門で影響有無を確認してください。")


def create_report(results: list[dict[str, Any]], report_date: dt.date) -> str:
    changed_items = [r for r in results if r["changed"]]
    error_items = [r for r in results if r.get("error")]

    lines: list[str] = []
    lines.append(f"# 規制情報モニタリングレポート {report_date.isoformat()}")
    lines.append("")
    lines.append("## 本日のサマリー")
    lines.append("")
    lines.append(f"- 監視対象URL数: {len(results)}")
    lines.append(f"- ページ変更検出: {len(changed_items)}")
    lines.append(f"- 取得エラー: {len(error_items)}")
    lines.append("")
    lines.append("> 注: 本レポートは公式・信頼情報源ページの変更検知を起点とする一次スクリーニングです。ページ変更が直ちに規制改正を意味するわけではありません。重要項目は必ずリンク先の原文を確認してください。")
    lines.append("")

    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in results:
        grouped.setdefault(item["regulation"], []).append(item)

    for regulation, items in grouped.items():
        lines.append(f"## {regulation}")
        lines.append("")
        for item in items:
            status = "変更あり" if item["changed"] else "変更なし"
            if item.get("first_seen"):
                status = "初回取得"
            if item.get("error"):
                status = "取得エラー"
            lines.append(f"### {item['title']}")
            lines.append("")
            lines.append(f"- 状態: {status}")
            lines.append(f"- 更新確認日: {report_date.isoformat()}")
            lines.append(f"- 重要度: {item['importance']}")
            lines.append(f"- 島津製作所への影響: {item['impact']}")
            if item.get("error"):
                lines.append(f"- エラー: `{item['error']}`")
            lines.append(f"- 情報源: {item['url']}")
            lines.append("")

    lines.append("## 島津製作所としての確認ポイント")
    lines.append("")
    if changed_items:
        lines.append("- 変更検出ページについて、規制本文・ガイダンス・FAQ・適用時期の変更有無を確認する。")
        lines.append("- PLM、SAP、E-System、輸出入・通関、AIガバナンス、製品セキュリティのどこに影響するかを切り分ける。")
        lines.append("- 必要に応じて、関係部門へ一次確認を依頼する。")
    else:
        lines.append("- 本日はページ変更検出はありません。定期監視を継続します。")
    lines.append("")

    lines.append("## 情報源")
    lines.append("")
    for item in results:
        lines.append(f"- {item['regulation']} / {item['title']}: {item['url']}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    config = load_yaml(SOURCES_FILE)
    state = load_state()
    state.setdefault("sources", {})
    today = jst_today()

    results: list[dict[str, Any]] = []

    for regulation in config.get("regulations", []):
        name = regulation["name"]
        for source in regulation.get("sources", []):
            title = source["title"]
            url = source["url"]
            text, error = fetch_url(url)
            source_state = state["sources"].get(url, {})
            first_seen = url not in state["sources"]
            changed = False
            digest = None
            if text is not None:
                digest = sha256(text)
                changed = (not first_seen) and source_state.get("sha256") != digest
                state["sources"][url] = {
                    "title": title,
                    "regulation": name,
                    "sha256": digest,
                    "last_checked": today.isoformat(),
                    "last_status": "ok",
                }
            else:
                state["sources"][url] = {
                    **source_state,
                    "title": title,
                    "regulation": name,
                    "last_checked": today.isoformat(),
                    "last_status": "error",
                    "last_error": error,
                }

            results.append(
                {
                    "regulation": name,
                    "title": title,
                    "url": url,
                    "changed": changed,
                    "first_seen": first_seen,
                    "sha256": digest,
                    "error": error,
                    "importance": classify_importance(name, changed, error),
                    "impact": impact_note(name, changed, error),
                }
            )

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"{today.isoformat()}.md"
    report_path.write_text(create_report(results, today), encoding="utf-8")
    save_state(state)

    print(f"Wrote {report_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
