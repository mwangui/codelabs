#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

from src.discover import discover_all, read_index, write_index
from src.manifest import append_manifest, load_errors, now_iso, write_errors
from src.normalize import ensure_directory, normalize_codelab_url, slug_from_url
from src.render_pdf import render_codelab_pdf
from src.verify import append_verification_report, latest_manifest_rows, verify_artifact


ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = {
    "language": "zh-tw",
    "base_url": "https://codelabs.developers.google.com",
    "index_url": "https://codelabs.developers.google.com/?hl=zh-tw",
    "sitemap_url": "https://codelabs.developers.google.com/sitemap.xml",
    "output": {
        "pdf_dir": "PDF",
        "output_dir": "output",
        "html_dir": "output/html",
        "index": "output/index.json",
        "manifest": "output/manifest.csv",
        "errors": "output/errors.json",
        "verification": "output/verification.csv",
        "log": "output/run.log",
    },
    "render": {
        "format": "A4",
        "print_background": True,
        "margin": {"top": "16mm", "bottom": "16mm", "left": "12mm", "right": "12mm"},
        "timeout_ms": 60000,
        "wait_after_expand_ms": 2000,
    },
    "crawler": {"delay_ms": 1000, "retries": 3, "concurrency": 1},
    "filename": {"max_title_chars": 80, "pattern": "{index:03d}__{slug}__{title_short}.pdf"},
}


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    config = load_config(args.config)
    prepare_directories(config)

    if args.command == "discover":
        return command_discover(args, config)
    if args.command == "dry-run":
        return command_dry_run(args, config)
    if args.command == "render-one":
        return command_render_one(args, config)
    if args.command == "render-all":
        return command_render_all(args, config)
    if args.command == "retry-failed":
        return command_retry_failed(args, config)
    if args.command == "verify-one":
        return command_verify_one(args, config)
    if args.command == "verify-all":
        return command_verify_all(args, config)

    parser.print_help()
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="把 Google Codelabs 批次轉成 PDF，並存到 repository 的 PDF/ 資料夾。",
    )
    parser.add_argument("--config", default="config.yaml", help="設定檔路徑，預設是 config.yaml")

    subparsers = parser.add_subparsers(dest="command")

    discover = subparsers.add_parser("discover", help="探索 Codelab 清單並輸出 output/index.json")
    discover.add_argument("--lang", default=None, help="語言，例如 zh-tw、en")

    dry_run = subparsers.add_parser("dry-run", help="預覽目前會處理哪些 Codelab，不產生 PDF")
    dry_run.add_argument("--filter", default=None, help="用正則表達式篩選 URL 或標題")
    add_batch_selection_args(dry_run)

    render_one = subparsers.add_parser("render-one", help="只產生單一 Codelab PDF")
    render_one.add_argument("--url", required=True, help="Codelab URL")
    render_one.add_argument("--index", type=int, default=1, help="檔名前綴序號")
    render_one.add_argument("--force", action="store_true", help="覆蓋已存在的 PDF")
    render_one.add_argument("--headed", action="store_true", help="顯示瀏覽器視窗，方便除錯")

    render_all = subparsers.add_parser("render-all", help="依 output/index.json 批次產生全部 PDF")
    render_all.add_argument("--filter", default=None, help="用正則表達式篩選 URL 或標題")
    add_batch_selection_args(render_all)
    render_all.add_argument("--force", action="store_true", help="覆蓋已存在的 PDF")
    render_all.add_argument("--headed", action="store_true", help="顯示瀏覽器視窗，方便除錯")

    retry_failed = subparsers.add_parser("retry-failed", help="只重跑 output/errors.json 裡的失敗項")
    retry_failed.add_argument("--force", action="store_true", help="覆蓋已存在的 PDF")
    retry_failed.add_argument("--headed", action="store_true", help="顯示瀏覽器視窗，方便除錯")

    verify_one = subparsers.add_parser("verify-one", help="驗證單一 PDF 是否包含完整步驟")
    verify_one.add_argument("--pdf", default=None, help="PDF 檔案路徑；不填時會驗證 PDF/ 裡唯一或最新的 PDF")
    verify_one.add_argument("--expected-steps", type=int, default=None, help="預期步驟數；不填時會從 manifest 讀取")

    verify_all = subparsers.add_parser("verify-all", help="驗證 PDF/ 裡的所有 PDF")
    verify_all.add_argument("--filter", default=None, help="用正則表達式篩選 PDF 檔名")

    return parser


def add_batch_selection_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--start-index", type=int, default=None, help="只處理 index 大於等於此數字的項目")
    parser.add_argument("--end-index", type=int, default=None, help="只處理 index 小於等於此數字的項目")
    parser.add_argument("--limit", type=int, default=None, help="最多處理幾筆，適合先小批量驗收")


def load_config(config_path: str) -> dict[str, Any]:
    config = deep_copy(DEFAULT_CONFIG)
    path = ROOT / config_path
    if path.exists():
        if yaml is None:
            print("提醒：尚未安裝 PyYAML，將使用內建預設設定。")
        else:
            with path.open("r", encoding="utf-8") as handle:
                loaded = yaml.safe_load(handle) or {}
            merge_dict(config, loaded)
    return config


def prepare_directories(config: dict[str, Any]) -> None:
    output = config["output"]
    ensure_directory(ROOT / output["pdf_dir"])
    ensure_directory(ROOT / output["output_dir"])
    ensure_directory(ROOT / output["html_dir"])


def command_discover(args: argparse.Namespace, config: dict[str, Any]) -> int:
    language = args.lang or config["language"]
    rows, messages = discover_all(
        sitemap_url=config["sitemap_url"],
        index_url=config["index_url"],
        manual_file=ROOT / "manual_urls.txt",
        language=language,
        timeout_ms=int(config["render"]["timeout_ms"]),
    )
    for message in messages:
        log(config, message)

    index_path = ROOT / config["output"]["index"]
    write_index(index_path, rows)
    log(config, f"已寫入 {index_path}，共 {len(rows)} 筆。")
    return 0 if rows else 2


def command_dry_run(args: argparse.Namespace, config: dict[str, Any]) -> int:
    rows = load_or_discover_index(config)
    rows = select_rows(rows, args)
    if not rows:
        print("沒有可處理的 Codelab。")
        return 2
    for item in rows:
        print(f"{int(item['index']):03d}  {item['slug']}  {item['url']}")
    print(f"\n總共 {len(rows)} 筆，這次只是預覽，沒有產生 PDF。")
    return 0


def command_render_one(args: argparse.Namespace, config: dict[str, Any]) -> int:
    url = normalize_codelab_url(args.url, config["language"])
    if not url:
        print("這不是有效的 Google Codelabs URL。")
        return 2
    item = {"index": args.index, "slug": slug_from_url(url), "title": "", "url": url}
    result = render_with_retry(item, config, force=args.force, headed=args.headed)
    print_result(result)
    return 0 if result["status"] in {"success", "skipped"} else 1


def command_render_all(args: argparse.Namespace, config: dict[str, Any]) -> int:
    rows = load_or_discover_index(config)
    rows = select_rows(rows, args)
    if not rows:
        print("沒有可處理的 Codelab。")
        return 2
    return render_many(rows, config, force=args.force, headed=args.headed)


def command_retry_failed(args: argparse.Namespace, config: dict[str, Any]) -> int:
    errors_path = ROOT / config["output"]["errors"]
    errors = load_errors(errors_path)
    if not errors:
        print("目前沒有失敗項可以重跑。")
        return 0
    rows = [
        {
            "index": int(item.get("index") or idx),
            "slug": item.get("slug") or slug_from_url(str(item.get("url"))),
            "title": item.get("title") or "",
            "url": item.get("url"),
        }
        for idx, item in enumerate(errors, start=1)
        if item.get("url")
    ]
    return render_many(rows, config, force=args.force, headed=args.headed)


def command_verify_one(args: argparse.Namespace, config: dict[str, Any]) -> int:
    pdf_path = resolve_pdf_path(args.pdf, config)
    if not pdf_path:
        print("找不到可驗證的 PDF。")
        return 2
    manifest_row = latest_manifest_rows(ROOT / config["output"]["manifest"]).get(pdf_path.name, {})
    expected_steps = args.expected_steps if args.expected_steps is not None else parse_int(manifest_row.get("step_count"))
    verification = verify_pdf_path(pdf_path, config, expected_steps=expected_steps, manifest_row=manifest_row)
    print_verification(verification)
    return 0 if verification["status"] == "passed" else 1


def command_verify_all(args: argparse.Namespace, config: dict[str, Any]) -> int:
    pdf_dir = ROOT / config["output"]["pdf_dir"]
    pdfs = sorted(pdf_dir.glob("*.pdf"))
    if args.filter:
        regex = re.compile(args.filter, re.IGNORECASE)
        pdfs = [path for path in pdfs if regex.search(path.name)]
    if not pdfs:
        print("沒有可驗證的 PDF。")
        return 2

    manifest_rows = latest_manifest_rows(ROOT / config["output"]["manifest"])
    failed = 0
    for pdf_path in pdfs:
        row = manifest_rows.get(pdf_path.name, {})
        verification = verify_pdf_path(pdf_path, config, expected_steps=parse_int(row.get("step_count")), manifest_row=row)
        print_verification(verification)
        if verification["status"] != "passed":
            failed += 1
    print(f"驗證完成：共 {len(pdfs)} 份，失敗 {failed} 份。")
    return 0 if failed == 0 else 1


def load_or_discover_index(config: dict[str, Any]) -> list[dict[str, Any]]:
    index_path = ROOT / config["output"]["index"]
    rows = read_index(index_path)
    if rows:
        return rows
    log(config, "找不到 output/index.json，先自動執行 discover。")
    discovered, messages = discover_all(
        sitemap_url=config["sitemap_url"],
        index_url=config["index_url"],
        manual_file=ROOT / "manual_urls.txt",
        language=config["language"],
        timeout_ms=int(config["render"]["timeout_ms"]),
    )
    for message in messages:
        log(config, message)
    write_index(index_path, discovered)
    return discovered


def render_many(rows: list[dict[str, Any]], config: dict[str, Any], *, force: bool, headed: bool) -> int:
    delay_ms = int(config["crawler"].get("delay_ms", 1000))
    errors: list[dict[str, Any]] = []
    success_count = 0
    skipped_count = 0

    for position, item in enumerate(rows, start=1):
        log(config, f"[{position}/{len(rows)}] 開始處理：{item.get('slug')} {item.get('url')}")
        result = render_with_retry(item, config, force=force, headed=headed)
        print_result(result)

        if result["status"] == "success":
            success_count += 1
        elif result["status"] == "skipped":
            skipped_count += 1
        else:
            errors.append(result)
            write_errors(ROOT / config["output"]["errors"], errors)

        if position < len(rows) and delay_ms > 0:
            time.sleep(delay_ms / 1000)

    write_errors(ROOT / config["output"]["errors"], errors)
    log(config, f"批次完成：成功 {success_count}，跳過 {skipped_count}，失敗 {len(errors)}。")
    return 0 if not errors else 1


def render_with_retry(item: dict[str, Any], config: dict[str, Any], *, force: bool, headed: bool) -> dict[str, Any]:
    retries = int(config["crawler"].get("retries", 3))
    last_error = ""

    for attempt in range(1, retries + 1):
        try:
            result = render_codelab_pdf(
                item=item,
                pdf_dir=ROOT / config["output"]["pdf_dir"],
                html_dir=ROOT / config["output"]["html_dir"],
                render_config=config["render"],
                filename_config=config["filename"],
                force=force,
                headless=not headed,
            )
            verification = verify_render_result(result, config)
            result["verification"] = verification
            if verification["status"] != "passed":
                raise RuntimeError(f"PDF 驗證失敗：{verification['message']}")
            append_manifest(
                ROOT / config["output"]["manifest"],
                {
                    "index": result["index"],
                    "slug": result["slug"],
                    "title": result["title"],
                    "pdf_filename": result["pdf_filename"],
                    "url": result["url"],
                    "status": result["status"],
                    "step_count": result["step_count"],
                    "created_at": now_iso(),
                },
            )
            return result
        except Exception as exc:  # noqa: BLE001
            last_error = f"{type(exc).__name__}: {exc}"
            log(config, f"第 {attempt}/{retries} 次失敗：{item.get('url')}：{last_error}")
            time.sleep(min(2 * attempt, 8))

    return {
        "index": item.get("index"),
        "slug": item.get("slug"),
        "title": item.get("title") or "",
        "url": item.get("url"),
        "status": "failed",
        "error": last_error,
        "attempts": retries,
        "step_count": 0,
    }


def apply_filter(rows: list[dict[str, Any]], pattern: str | None) -> list[dict[str, Any]]:
    if not pattern:
        return rows
    regex = re.compile(pattern, re.IGNORECASE)
    return [
        row
        for row in rows
        if regex.search(str(row.get("url", ""))) or regex.search(str(row.get("title", ""))) or regex.search(str(row.get("slug", "")))
    ]


def select_rows(rows: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    selected = apply_filter(rows, getattr(args, "filter", None))
    start_index = getattr(args, "start_index", None)
    end_index = getattr(args, "end_index", None)
    limit = getattr(args, "limit", None)

    if start_index is not None:
        selected = [row for row in selected if int(row.get("index") or 0) >= start_index]
    if end_index is not None:
        selected = [row for row in selected if int(row.get("index") or 0) <= end_index]
    if limit is not None:
        selected = selected[: max(0, limit)]
    return selected


def print_result(result: dict[str, Any]) -> None:
    status = result.get("status")
    if status == "success":
        verification = result.get("verification") or {}
        verify_text = f"，驗證：{verification.get('status')}" if verification else ""
        print(f"完成：{result['pdf_filename']}（步驟數：{result.get('step_count', 0)}{verify_text}）")
    elif status == "skipped":
        verification = result.get("verification") or {}
        verify_text = f"，驗證：{verification.get('status')}" if verification else ""
        print(f"跳過：{result['pdf_filename']} 已存在（步驟數：{result.get('step_count', 0)}{verify_text}）。")
    else:
        print(f"失敗：{result.get('slug')}：{result.get('error')}")


def verify_render_result(result: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    pdf_path = Path(result["pdf_path"])
    verification = verify_pdf_path(
        pdf_path,
        config,
        expected_steps=parse_int(result.get("step_count")),
        manifest_row={
            "title": str(result.get("title") or ""),
            "url": str(result.get("url") or ""),
        },
    )
    log(config, f"驗證 {pdf_path.name}：{verification['status']}，{verification['message']}")
    return verification


def verify_pdf_path(
    pdf_path: Path,
    config: dict[str, Any],
    *,
    expected_steps: int | None,
    manifest_row: dict[str, Any],
) -> dict[str, Any]:
    html_path = ROOT / config["output"]["html_dir"] / f"{pdf_path.stem}.html"
    verification = verify_artifact(
        pdf_path=pdf_path,
        html_path=html_path,
        expected_step_count=expected_steps,
        expected_title=str(manifest_row.get("title") or "") or None,
        expected_url=str(manifest_row.get("url") or "") or None,
    )
    append_verification_report(ROOT / config["output"]["verification"], verification)
    return verification


def resolve_pdf_path(value: str | None, config: dict[str, Any]) -> Path | None:
    if value:
        path = Path(value)
        return path if path.is_absolute() else ROOT / path
    pdfs = sorted((ROOT / config["output"]["pdf_dir"]).glob("*.pdf"), key=lambda path: path.stat().st_mtime)
    return pdfs[-1] if pdfs else None


def print_verification(verification: dict[str, Any]) -> None:
    label = "通過" if verification["status"] == "passed" else "失敗"
    print(
        f"{label}：{verification['pdf_filename']}；"
        f"PDF 頁數 {verification['pdf_page_count']}；"
        f"PDF 大小 {verification['pdf_size_bytes']} bytes；"
        f"預期步驟 {verification['expected_step_count']}；"
        f"HTML 步驟 {verification['html_step_count']}；"
        f"目錄步驟 {verification['toc_step_count']}；"
        f"{verification['message']}"
    )


def parse_int(value: Any) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def log(config: dict[str, Any], message: str) -> None:
    text = f"[{now_iso()}] {message}"
    print(text)
    log_path = ROOT / config["output"]["log"]
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(text + "\n")


def merge_dict(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            merge_dict(target[key], value)
        else:
            target[key] = value


def deep_copy(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: deep_copy(inner) for key, inner in value.items()}
    if isinstance(value, list):
        return [deep_copy(inner) for inner in value]
    return value


if __name__ == "__main__":
    sys.exit(main())
