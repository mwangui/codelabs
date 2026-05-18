from __future__ import annotations

import csv
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


VERIFICATION_COLUMNS = [
    "created_at",
    "status",
    "pdf_filename",
    "pdf_page_count",
    "pdf_size_bytes",
    "expected_step_count",
    "html_step_count",
    "toc_step_count",
    "last_step_found",
    "message",
]


def verify_artifact(
    *,
    pdf_path: str | Path,
    html_path: str | Path,
    expected_step_count: int | None = None,
    expected_title: str | None = None,
    expected_url: str | None = None,
) -> dict[str, Any]:
    pdf_file = Path(pdf_path)
    html_file = Path(html_path)
    errors: list[str] = []
    warnings: list[str] = []

    pdf_size = 0
    pdf_page_count = 0
    if not pdf_file.exists():
        errors.append("找不到 PDF 檔案")
    else:
        pdf_size = pdf_file.stat().st_size
        pdf_page_count = count_pdf_pages(pdf_file)
        if pdf_size < 20_000:
            errors.append(f"PDF 太小，可能沒有完整輸出：{pdf_size} bytes")
        if pdf_page_count <= 1:
            errors.append(f"PDF 頁數只有 {pdf_page_count} 頁")

    html_text = ""
    html_step_count = 0
    toc_step_count = 0
    last_step_found = False
    if not html_file.exists():
        errors.append("找不到乾淨 HTML 檔案")
    else:
        html_text = html_file.read_text(encoding="utf-8", errors="replace")
        html_step_ids = sorted({int(value) for value in re.findall(r'id=["\']step-(\d+)["\']', html_text)})
        toc_step_ids = sorted({int(value) for value in re.findall(r'href=["\']#step-(\d+)["\']', html_text)})
        html_step_count = len(html_step_ids)
        toc_step_count = len(toc_step_ids)

        if html_step_count == 0:
            errors.append("乾淨 HTML 沒有任何 step 區塊")
        if toc_step_count == 0:
            errors.append("乾淨 HTML 沒有目錄 step 連結")

        target_last_step = expected_step_count or (html_step_ids[-1] if html_step_ids else 0)
        last_step_found = bool(target_last_step and target_last_step in html_step_ids and target_last_step in toc_step_ids)
        if target_last_step and not last_step_found:
            errors.append(f"找不到最後一步 step-{target_last_step}")

        if expected_step_count is not None:
            if html_step_count != expected_step_count:
                errors.append(f"HTML 步驟數 {html_step_count} 與預期 {expected_step_count} 不一致")
            if toc_step_count != expected_step_count:
                errors.append(f"目錄步驟數 {toc_step_count} 與預期 {expected_step_count} 不一致")
            if pdf_page_count and expected_step_count > 1 and pdf_page_count < expected_step_count:
                errors.append(f"PDF 頁數 {pdf_page_count} 少於預期步驟數 {expected_step_count}")

        if expected_title and expected_title not in html_text:
            warnings.append("乾淨 HTML 沒有找到預期標題文字")
        if expected_url and expected_url not in html_text:
            warnings.append("乾淨 HTML 沒有找到來源 URL")

    status = "passed" if not errors else "failed"
    message_parts = errors or ["驗證通過"]
    if warnings:
        message_parts.extend(f"警告：{warning}" for warning in warnings)

    return {
        "status": status,
        "pdf_filename": pdf_file.name,
        "pdf_path": str(pdf_file),
        "html_path": str(html_file),
        "pdf_page_count": pdf_page_count,
        "pdf_size_bytes": pdf_size,
        "expected_step_count": expected_step_count if expected_step_count is not None else "",
        "html_step_count": html_step_count,
        "toc_step_count": toc_step_count,
        "last_step_found": last_step_found,
        "errors": errors,
        "warnings": warnings,
        "message": "；".join(message_parts),
    }


def count_pdf_pages(path: str | Path) -> int:
    data = Path(path).read_bytes()
    return len(re.findall(rb"/Type\s*/Page\b", data))


def append_verification_report(path: str | Path, row: dict[str, Any]) -> None:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    exists = file_path.exists()

    with file_path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=VERIFICATION_COLUMNS)
        if not exists:
            writer.writeheader()
        writer.writerow(
            {
                "created_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
                "status": row.get("status", ""),
                "pdf_filename": row.get("pdf_filename", ""),
                "pdf_page_count": row.get("pdf_page_count", ""),
                "pdf_size_bytes": row.get("pdf_size_bytes", ""),
                "expected_step_count": row.get("expected_step_count", ""),
                "html_step_count": row.get("html_step_count", ""),
                "toc_step_count": row.get("toc_step_count", ""),
                "last_step_found": row.get("last_step_found", ""),
                "message": row.get("message", ""),
            }
        )


def latest_manifest_rows(path: str | Path) -> dict[str, dict[str, str]]:
    file_path = Path(path)
    if not file_path.exists():
        return {}
    with file_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    latest: dict[str, dict[str, str]] = {}
    for row in rows:
        filename = row.get("pdf_filename") or ""
        if filename:
            latest[filename] = row
    return latest
