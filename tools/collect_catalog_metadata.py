from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.normalize import normalize_codelab_url, slug_from_url


def collect(index_url: str, language: str, timeout_ms: int) -> list[dict[str, object]]:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1400})
        page.goto(index_url, wait_until="networkidle", timeout=timeout_ms)

        last_height = 0
        for _ in range(18):
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(700)
            current_height = page.evaluate("document.body.scrollHeight")
            if current_height == last_height:
                break
            last_height = current_height

        rows = page.evaluate(
            """
            () => {
              const output = [];
              const seen = new Set();

              const textOf = (node) => (node?.textContent || '').replace(/\\s+/g, ' ').trim();
              const pieces = (root, selector) =>
                Array.from(root.querySelectorAll?.(selector) || [])
                  .map((node) => textOf(node))
                  .filter(Boolean);

              const walk = (root) => {
                if (!root) return;
                const cards = root.querySelectorAll?.('devsite-card, .devsite-card, li') || [];
                cards.forEach((card) => {
                  const anchor = card.querySelector?.(
                    'a[href*="codelabs.developers.google.com"], a[href^="/"], a[href*="/codelabs/"], a[href]'
                  );
                  if (!anchor || !anchor.href) return;
                  const href = anchor.href;
                  if (!href.includes('codelabs.developers.google.com') && !href.includes('/codelabs/')) return;
                  if (seen.has(href)) return;
                  seen.add(href);

                  const title =
                    textOf(card.querySelector?.('h2, h3, .devsite-card-title, .card-title, [slot="title"]')) ||
                    textOf(anchor);

                  output.push({
                    url: href,
                    title,
                    text: textOf(card),
                    tags: Array.from(new Set([
                      ...pieces(card, '.devsite-card-label'),
                      ...pieces(card, '.devsite-card-category'),
                      ...pieces(card, '.devsite-chip'),
                      ...pieces(card, '.devsite-tag'),
                      ...pieces(card, '[class*="tag"]'),
                      ...pieces(card, '[class*="chip"]'),
                      ...pieces(card, '[class*="label"]'),
                      ...pieces(card, '[class*="category"]'),
                    ])).slice(0, 20),
                    timeText: (
                      textOf(card.querySelector?.('time')) ||
                      pieces(card, '[class*="date"], [class*="time"], [datetime]').join(' | ')
                    ),
                  });
                });
                root.querySelectorAll?.('*')?.forEach((node) => {
                  if (node.shadowRoot) walk(node.shadowRoot);
                });
              };

              walk(document);
              return output;
            }
            """
        )
        browser.close()

    normalized: list[dict[str, object]] = []
    seen_urls: set[str] = set()
    for row in rows:
        url = normalize_codelab_url(str(row.get("url", "")), language)
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        normalized.append(
            {
                "slug": slug_from_url(url),
                "url": url,
                "title": str(row.get("title", "")).strip(),
                "text": str(row.get("text", "")).strip(),
                "tags": row.get("tags", []),
                "time_text": str(row.get("timeText", "")).strip(),
            }
        )
    return normalized


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect Google Codelabs homepage card metadata.")
    parser.add_argument("--index-url", default="https://codelabs.developers.google.com/?hl=zh-tw")
    parser.add_argument("--lang", default="zh-tw")
    parser.add_argument("--out", default="output/catalog_metadata.json")
    parser.add_argument("--timeout-ms", type=int, default=60000)
    args = parser.parse_args()

    rows = collect(args.index_url, args.lang, args.timeout_ms)
    output_path = Path(args.out)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"catalog_metadata_count={len(rows)}")
    print(json.dumps(rows[:3], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
