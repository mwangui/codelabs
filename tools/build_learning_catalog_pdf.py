from __future__ import annotations

import csv
import html
from collections import Counter, defaultdict
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
DOC_DIR = ROOT / "DOC"
CSV_PATH = DOC_DIR / "01_Google_Codelabs_完整索引.csv"
HTML_PATH = DOC_DIR / "01_Google_Codelabs_學習地圖與完整索引.html"
PDF_PATH = DOC_DIR / "01_Google_Codelabs_學習地圖與完整索引.pdf"


def read_rows() -> list[dict[str, str]]:
    return list(csv.DictReader(CSV_PATH.open(encoding="utf-8")))


def esc(value: object) -> str:
    return html.escape(str(value or ""))


def status_counts(rows: list[dict[str, str]]) -> Counter[str]:
    return Counter(row["status"] for row in rows)


def build_html(rows: list[dict[str, str]]) -> str:
    passed = [row for row in rows if row["status"] == "passed"]
    levels = Counter(row["level"] for row in passed)
    categories = Counter(row["category"] for row in passed)
    ai_rows = [row for row in passed if row["category"] == "AI / Gemini / Agent / Vertex AI"]
    month_counts: dict[str, int] = defaultdict(int)
    for row in ai_rows:
        if row["updated_date"]:
            month_counts[row["updated_date"][:7]] += 1

    category_rows = "\n".join(
        f"<tr><td>{esc(category)}</td><td class='num'>{count}</td></tr>"
        for category, count in categories.most_common()
    )
    timeline_rows = "\n".join(
        f"<tr><td>{esc(month)}</td><td class='num'>{count}</td><td>{esc(timeline_interpretation(month))}</td></tr>"
        for month, count in sorted(month_counts.items())
    )
    catalog_rows = "\n".join(
        "<tr>"
        f"<td class='num'>{esc(row['index']).zfill(3)}</td>"
        f"<td>{esc(row['category'])}</td>"
        f"<td>{esc(row['level'])}</td>"
        f"<td>{esc(row['updated_date'])}</td>"
        f"<td>{esc(row['duration_text'])}</td>"
        f"<td>{esc(row['title'])}</td>"
        f"<td class='filename'>{esc(row['pdf_filename'] or ('未產 PDF：' + row.get('slug', '')))}</td>"
        "</tr>"
        for row in rows
    )
    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<title>Google Codelabs PDF 學習地圖與完整索引</title>
<style>
@page {{ size: A4 landscape; margin: 12mm; }}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  color: #202124;
  font-family: Arial, "Noto Sans TC", "PingFang TC", "Microsoft JhengHei", sans-serif;
  font-size: 10px;
  line-height: 1.35;
}}
h1 {{ font-size: 25px; margin: 0 0 8px; }}
h2 {{ font-size: 16px; color: #174EA6; margin: 18px 0 8px; break-after: avoid; }}
p {{ margin: 5px 0; }}
.muted {{ color: #5f6368; }}
.summary {{
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
  margin: 14px 0 12px;
}}
.metric {{ border: 1px solid #dadce0; border-radius: 6px; padding: 8px; }}
.metric strong {{ display: block; font-size: 18px; color: #174EA6; }}
img.chart {{ width: 100%; max-height: 135mm; object-fit: contain; margin: 8px 0 12px; }}
table {{ width: 100%; border-collapse: collapse; table-layout: fixed; break-inside: auto; }}
th, td {{ border: 1px solid #dadce0; padding: 4px 5px; vertical-align: top; overflow-wrap: anywhere; }}
th {{ background: #e8eef5; font-weight: 700; }}
thead {{ display: table-header-group; }}
.num {{ text-align: right; white-space: nowrap; }}
.filename {{ font-size: 8.5px; }}
.catalog th:nth-child(1), .catalog td:nth-child(1) {{ width: 8mm; }}
.catalog th:nth-child(2), .catalog td:nth-child(2) {{ width: 39mm; }}
.catalog th:nth-child(3), .catalog td:nth-child(3) {{ width: 12mm; }}
.catalog th:nth-child(4), .catalog td:nth-child(4) {{ width: 22mm; }}
.catalog th:nth-child(5), .catalog td:nth-child(5) {{ width: 18mm; }}
.catalog th:nth-child(6), .catalog td:nth-child(6) {{ width: 92mm; }}
.catalog th:nth-child(7), .catalog td:nth-child(7) {{ width: 85mm; }}
.page-break {{ break-before: page; }}
</style>
</head>
<body>
<h1>Google Codelabs PDF 學習地圖與完整索引</h1>
<p class="muted">資料範圍：Google Codelabs 首頁 zh-tw 清單共 {len(rows)} 筆；本地 PDF 通過驗證 {len(passed)} 份，未產生 PDF {len(rows) - len(passed)} 筆。</p>
<p class="muted">Updated 日期取自 Google Codelabs 首頁卡片；分類為依標題、URL slug 與描述文字推論。</p>
<div class="summary">
  <div class="metric"><strong>{len(passed)}</strong>PDF 通過驗證</div>
  <div class="metric"><strong>{len(ai_rows)}</strong>AI / Gemini / Agent 類</div>
  <div class="metric"><strong>{levels['初階']} / {levels['中階']}</strong>初階 / 中階</div>
  <div class="metric"><strong>{levels['進階']} / {levels['高階']}</strong>進階 / 高階</div>
</div>
<img class="chart" src="charts/category_counts.png">
<h2>分類數量總表</h2>
<table><thead><tr><th>主分類</th><th>數量</th></tr></thead><tbody>{category_rows}</tbody></table>
<div class="page-break"></div>
<h2>表 2：AI 主題時間演進</h2>
<p class="muted">這裡用 Updated 日期觀察這批 AI 教材的更新重點，不等於產品首次發布日。</p>
<img class="chart" src="charts/ai_timeline.png">
<table><thead><tr><th>時間區間</th><th>AI 案子數</th><th>重點判讀</th></tr></thead><tbody>{timeline_rows}</tbody></table>
<div class="page-break"></div>
<h2>表 1：完整 PDF 分類索引</h2>
<table class="catalog">
<thead><tr><th>序</th><th>主分類</th><th>階段</th><th>Updated</th><th>時長</th><th>標題</th><th>PDF 檔名</th></tr></thead>
<tbody>{catalog_rows}</tbody>
</table>
</body></html>
"""


def timeline_interpretation(month: str) -> str:
    if month == "2026-03":
        return "Gemini / Vertex AI / Cloud Run / BigQuery 生成式 AI 應用與資料基礎集中更新。"
    if month == "2026-04":
        return "production-ready AI、ADK、多代理、評估、安全、觀測與治理成為重點。"
    if month == "2026-05":
        return "Enterprise Agent Platform、Agent Gateway、MCP、Workspace 代理與事件驅動代理更新較新。"
    return "以當月教材更新觀察主要技術焦點。"


def render_pdf() -> None:
    rows = read_rows()
    HTML_PATH.write_text(build_html(rows), encoding="utf-8")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        page.goto(HTML_PATH.resolve().as_uri(), wait_until="load")
        page.pdf(
            path=str(PDF_PATH),
            format="A4",
            landscape=True,
            print_background=True,
            margin={"top": "12mm", "bottom": "12mm", "left": "12mm", "right": "12mm"},
        )
        browser.close()
    print(f"html={HTML_PATH}")
    print(f"pdf={PDF_PATH}")


if __name__ == "__main__":
    render_pdf()
