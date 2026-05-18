from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable

from .normalize import normalize_codelab_url, slug_from_url


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        for key, value in attrs:
            if key.lower() == "href" and value:
                self.links.append(value)


def fetch_text(url: str, timeout: int = 60) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 Codelabs PDF Exporter",
            "Accept": "text/html,application/xml,text/xml,*/*",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def discover_from_sitemap(sitemap_url: str, language: str, timeout: int = 60) -> list[str]:
    return dedupe(_discover_from_sitemap_recursive(sitemap_url, language, timeout, seen=set()))


def _discover_from_sitemap_recursive(
    sitemap_url: str,
    language: str,
    timeout: int,
    seen: set[str],
) -> list[str]:
    if sitemap_url in seen:
        return []
    seen.add(sitemap_url)

    xml_text = fetch_text(sitemap_url, timeout=timeout)
    root = ET.fromstring(xml_text)

    if root.tag.endswith("sitemapindex"):
        urls: list[str] = []
        for loc in root.findall(".//{*}loc"):
            if loc.text:
                urls.extend(_discover_from_sitemap_recursive(loc.text, language, timeout, seen))
        return urls

    urls: list[str] = []
    for loc in root.findall(".//{*}loc"):
        if loc.text:
            normalized = normalize_codelab_url(loc.text, language)
            if normalized:
                urls.append(normalized)
    return urls


def discover_from_index_html(index_url: str, language: str, timeout: int = 60) -> list[str]:
    html = fetch_text(index_url, timeout=timeout)
    parser = LinkParser()
    parser.feed(html)

    urls: list[str] = []
    for href in parser.links:
        if href.startswith("/"):
            href = f"https://codelabs.developers.google.com{href}"
        normalized = normalize_codelab_url(href, language)
        if normalized:
            urls.append(normalized)

    for match in re.findall(r"https://codelabs\.developers\.google\.com/[A-Za-z0-9._~%/-]+(?:\?[^\"'<>\\s]+)?", html):
        normalized = normalize_codelab_url(match, language)
        if normalized:
            urls.append(normalized)

    return dedupe(urls)


def discover_from_index_browser(index_url: str, language: str, timeout_ms: int = 60000) -> list[str]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("尚未安裝 Playwright，無法用瀏覽器探索首頁。") from exc

    links: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1200})
        page.goto(index_url, wait_until="networkidle", timeout=timeout_ms)

        last_height = 0
        for _ in range(12):
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(800)
            current_height = page.evaluate("document.body.scrollHeight")
            if current_height == last_height:
                break
            last_height = current_height

        links = page.evaluate(
            """
            () => {
              const output = new Set();
              const walk = (root) => {
                if (!root) return;
                const anchors = root.querySelectorAll?.(
                  'devsite-card a[href], .devsite-card-content a[href], .devsite-card-buttons a[href]'
                ) || [];
                anchors.forEach((anchor) => output.add(anchor.href));
                root.querySelectorAll?.('*')?.forEach((node) => {
                  if (node.shadowRoot) walk(node.shadowRoot);
                });
              };
              walk(document);
              return Array.from(output);
            }
            """
        )
        browser.close()

    urls: list[str] = []
    for link in links:
        normalized = normalize_codelab_url(link, language)
        if normalized:
            urls.append(normalized)
    return dedupe(urls)


def discover_from_manual_file(path: str | Path, language: str) -> list[str]:
    file_path = Path(path)
    if not file_path.exists():
        return []

    urls: list[str] = []
    for line in file_path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        normalized = normalize_codelab_url(raw, language)
        if normalized:
            urls.append(normalized)
    return dedupe(urls)


def dedupe(urls: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        output.append(url)
    return output


def build_index(urls: list[str]) -> list[dict[str, object]]:
    return [
        {
            "index": index,
            "slug": slug_from_url(url),
            "title": "",
            "url": url,
        }
        for index, url in enumerate(urls, start=1)
    ]


def write_index(path: str | Path, rows: list[dict[str, object]]) -> None:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def read_index(path: str | Path) -> list[dict[str, object]]:
    file_path = Path(path)
    if not file_path.exists():
        return []
    data = json.loads(file_path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


def discover_all(
    *,
    sitemap_url: str,
    index_url: str,
    manual_file: str | Path,
    language: str,
    timeout_ms: int,
) -> tuple[list[dict[str, object]], list[str]]:
    """優先使用首頁專案卡片；首頁失敗時才用 sitemap / HTML / 手動清單備援。"""
    messages: list[str] = []
    timeout = max(1, timeout_ms // 1000)

    for name, loader in [
        ("首頁 Playwright", lambda: discover_from_index_browser(index_url, language, timeout_ms)),
        ("sitemap", lambda: discover_from_sitemap(sitemap_url, language, timeout)),
        ("首頁", lambda: discover_from_index_html(index_url, language, timeout)),
    ]:
        try:
            urls = loader()
            messages.append(f"{name} 探索到 {len(urls)} 筆 URL")
            if urls:
                manual_urls = discover_from_manual_file(manual_file, language)
                if manual_urls:
                    messages.append(f"manual_urls.txt 補充 {len(manual_urls)} 筆 URL")
                return build_index(dedupe([*urls, *manual_urls])), messages
        except (urllib.error.URLError, TimeoutError, ET.ParseError, OSError, RuntimeError) as exc:
            messages.append(f"{name} 探索失敗：{exc}")
            time.sleep(0.2)

    manual_urls = discover_from_manual_file(manual_file, language)
    messages.append(f"manual_urls.txt 探索到 {len(manual_urls)} 筆 URL")
    return build_index(manual_urls), messages
