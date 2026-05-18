from __future__ import annotations

import html
import time
from pathlib import Path
from typing import Any

from .normalize import build_pdf_filename, ensure_directory


EXPAND_AND_CLEAN_SCRIPT = """
(() => {
  const style = document.createElement('style');
  style.setAttribute('data-codelabs-pdf-exporter', 'true');
  style.textContent = `
    html, body {
      background: #ffffff !important;
      color: #202124 !important;
      overflow: visible !important;
    }
    google-codelab, #main, main, article {
      max-width: 980px !important;
      width: 100% !important;
      margin: 0 auto !important;
      padding: 0 !important;
    }
    google-codelab-step {
      display: block !important;
      visibility: visible !important;
      opacity: 1 !important;
      position: relative !important;
      height: auto !important;
      min-height: auto !important;
      overflow: visible !important;
      break-inside: auto;
      page-break-inside: auto;
      padding: 20px 0 28px !important;
      border-bottom: 1px solid #e5e7eb;
    }
    google-codelab-step[hidden],
    google-codelab-step.iron-selected {
      display: block !important;
    }
    #drawer,
    #header,
    #toolbar,
    #controls,
    #footer,
    .drawer,
    .header,
    .toolbar,
    .controls,
    .step-controls,
    .google-codelab-nav-buttons,
    google-codelab-drawer,
    google-codelab-survey,
    google-codelab-feedback,
    paper-drawer-panel,
    app-drawer,
    app-header,
    footer {
      display: none !important;
    }
    pre, code {
      white-space: pre-wrap !important;
      overflow-wrap: anywhere !important;
    }
    img {
      max-width: 100% !important;
      height: auto !important;
    }
    a {
      color: #1a73e8 !important;
      text-decoration: none !important;
    }
    @page {
      size: A4;
    }
  `;
  document.head.appendChild(style);

  const steps = Array.from(document.querySelectorAll('google-codelab-step'));
  steps.forEach((step, index) => {
    step.removeAttribute('hidden');
    step.setAttribute('selected', '');
    step.style.display = 'block';
    step.style.visibility = 'visible';
    step.style.opacity = '1';
    step.style.position = 'relative';
    step.style.transform = 'none';
    step.style.height = 'auto';
    step.style.overflow = 'visible';

    const collapsibles = step.querySelectorAll('[hidden], .hidden');
    collapsibles.forEach((node) => {
      node.removeAttribute('hidden');
      node.style.display = '';
      node.style.visibility = 'visible';
      node.style.opacity = '1';
    });

    if (!step.querySelector('[data-step-number]')) {
      const marker = document.createElement('div');
      marker.setAttribute('data-step-number', 'true');
      marker.textContent = `步驟 ${index + 1}`;
      marker.style.fontSize = '12px';
      marker.style.fontWeight = '700';
      marker.style.color = '#5f6368';
      marker.style.marginBottom = '8px';
      step.prepend(marker);
    }
  });

  const noisySelectors = [
    '#drawer', '#header', '#toolbar', '#controls', '#footer',
    '.drawer', '.header', '.toolbar', '.controls', '.step-controls',
    '.google-codelab-nav-buttons', 'google-codelab-drawer',
    'google-codelab-survey', 'google-codelab-feedback',
    'paper-drawer-panel', 'app-drawer', 'app-header', 'footer'
  ];
  noisySelectors.forEach((selector) => {
    document.querySelectorAll(selector).forEach((node) => {
      node.style.display = 'none';
    });
  });

  return {
    title: document.title || '',
    stepCount: steps.length,
    headings: steps.map((step) => {
      const heading = step.querySelector('h1, h2, h3, [slot="title"]');
      return heading ? heading.textContent.trim() : '';
    })
  };
})();
"""


EXTRACT_CODELAB_SCRIPT = """
() => {
  const absoluteUrl = (value) => {
    if (!value) return value;
    try {
      return new URL(value, window.location.href).href;
    } catch {
      return value;
    }
  };

  const cleanClone = (source) => {
    const clone = source.cloneNode(true);

    clone.querySelectorAll('script, style, button, iframe, devsite-language-selector').forEach((node) => node.remove());
    clone.querySelectorAll('.devsite-heading-link, [data-step-number], .copy-button, .code-copy, .material-icons').forEach((node) => node.remove());

    clone.querySelectorAll('[src]').forEach((node) => {
      const src = node.getAttribute('src') || node.getAttribute('data-src');
      if (src) node.setAttribute('src', absoluteUrl(src));
    });
    clone.querySelectorAll('[href]').forEach((node) => {
      const href = node.getAttribute('href');
      if (href && !href.startsWith('#') && !href.startsWith('mailto:')) {
        node.setAttribute('href', absoluteUrl(href));
      }
    });
    clone.querySelectorAll('img').forEach((img) => {
      img.removeAttribute('srcset');
      img.removeAttribute('sizes');
      img.setAttribute('loading', 'eager');
      img.setAttribute('decoding', 'sync');
    });

    clone.querySelectorAll('pre code').forEach((code) => {
      code.innerHTML = code.innerHTML.replace(/<br\\s*\\/?>/gi, '\\n');
    });

    return clone;
  };

  const title =
    document.querySelector('meta[property="og:title"]')?.getAttribute('content') ||
    document.querySelector('title')?.textContent ||
    '';
  const description =
    document.querySelector('meta[name="description"]')?.getAttribute('content') ||
    document.querySelector('meta[property="og:description"]')?.getAttribute('content') ||
    '';
  const steps = Array.from(document.querySelectorAll('google-codelab-step')).map((step, index) => {
    const clone = cleanClone(step);
    const content = clone.querySelector('.instructions .inner') || clone;
    const heading =
      content.querySelector('.step-title')?.textContent?.trim() ||
      clone.getAttribute('label') ||
      `步驟 ${index + 1}`;
    return {
      index: index + 1,
      label: clone.getAttribute('label') || heading,
      duration: clone.getAttribute('duration') || '',
      heading,
      html: content.innerHTML
    };
  });

  return {
    title: title.replace(/\\s*\\|\\s*Google Codelabs\\s*/g, '').replace(/&nbsp;/g, ' ').trim(),
    description,
    url: window.location.href,
    steps
  };
}
"""


def _import_playwright():
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "尚未安裝 Playwright。請先執行：pip install -r requirements.txt，接著執行：playwright install chromium"
        ) from exc
    return sync_playwright, PlaywrightTimeoutError


def render_codelab_pdf(
    *,
    item: dict[str, Any],
    pdf_dir: str | Path,
    html_dir: str | Path | None,
    render_config: dict[str, Any],
    filename_config: dict[str, Any],
    force: bool = False,
    headless: bool = True,
) -> dict[str, Any]:
    sync_playwright, PlaywrightTimeoutError = _import_playwright()

    url = str(item["url"])
    index = int(item.get("index") or 1)
    slug = str(item.get("slug") or "codelab")
    fallback_title = str(item.get("title") or slug)

    pdf_directory = ensure_directory(pdf_dir)
    html_directory = ensure_directory(html_dir) if html_dir else None

    timeout_ms = int(render_config.get("timeout_ms", 60000))
    wait_after_expand_ms = int(render_config.get("wait_after_expand_ms", 2000))
    max_title_chars = int(filename_config.get("max_title_chars", 48))

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        page = browser.new_page(viewport={"width": 1280, "height": 1600}, device_scale_factor=1)
        try:
            page.goto(url, wait_until="networkidle", timeout=timeout_ms)
        except PlaywrightTimeoutError:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)

        page.emulate_media(media="screen")
        info = page.evaluate(EXPAND_AND_CLEAN_SCRIPT)
        if int(info.get("stepCount") or 0) == 0:
            raise RuntimeError("這個頁面沒有偵測到 Codelab 步驟，已略過以避免產生假 PDF。")
        page.wait_for_timeout(wait_after_expand_ms)

        extracted = page.evaluate(EXTRACT_CODELAB_SCRIPT)
        if not extracted.get("steps"):
            raise RuntimeError("無法抽出 Codelab 的完整步驟內容。")

        title = _clean_title(str(info.get("title") or fallback_title))
        filename = build_pdf_filename(index, slug, title, max_title_chars)
        pdf_path = pdf_directory / filename

        if pdf_path.exists() and not force:
            browser.close()
            return {
                "index": index,
                "slug": slug,
                "title": title,
                "url": url,
                "pdf_filename": filename,
                "pdf_path": str(pdf_path),
                "status": "skipped",
                "step_count": int(info.get("stepCount") or 0),
            }

        clean_html = build_clean_html(
            title=title,
            source_url=url,
            description=str(extracted.get("description") or ""),
            steps=list(extracted.get("steps") or []),
        )

        if html_directory:
            html_path = html_directory / filename.replace(".pdf", ".html")
            html_path.write_text(clean_html, encoding="utf-8")

        page.set_content(clean_html, wait_until="load", timeout=timeout_ms)
        page.emulate_media(media="print")
        _wait_for_images(page, timeout_ms=timeout_ms)

        page.pdf(
            path=str(pdf_path),
            format=str(render_config.get("format", "A4")),
            print_background=bool(render_config.get("print_background", True)),
            margin=render_config.get(
                "margin",
                {"top": "16mm", "bottom": "16mm", "left": "12mm", "right": "12mm"},
            ),
        )
        browser.close()

    return {
        "index": index,
        "slug": slug,
        "title": title,
        "url": url,
        "pdf_filename": filename,
        "pdf_path": str(pdf_path),
        "status": "success",
        "step_count": len(extracted.get("steps") or []),
    }


def _wait_for_images(page: Any, timeout_ms: int) -> None:
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        pending = page.evaluate(
            """
            () => Array.from(document.images)
              .filter((img) => !img.complete || img.naturalWidth === 0)
              .length
            """
        )
        if pending == 0:
            return
        page.wait_for_timeout(250)


def _clean_title(title: str) -> str:
    cleaned = title.replace(" | Google Codelabs", "").replace("Google Codelabs", "")
    cleaned = " ".join(cleaned.split())
    return cleaned.strip(" -|") or "未命名 Codelab"


def build_clean_html(*, title: str, source_url: str, description: str, steps: list[dict[str, Any]]) -> str:
    escaped_title = html.escape(title)
    escaped_source_url = html.escape(source_url, quote=True)
    escaped_description = html.escape(description)
    toc_items = "\n".join(
        f'<li><a href="#step-{step["index"]}">{html.escape(str(step["heading"]))}</a></li>'
        for step in steps
    )
    step_sections = "\n".join(
        f"""
        <section class="step" id="step-{step["index"]}">
          <div class="step-kicker">步驟 {step["index"]}{_duration_text(step)}</div>
          <div class="step-body">{step["html"]}</div>
        </section>
        """
        for step in steps
    )

    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escaped_title}</title>
  <style>
    @page {{
      size: A4;
      margin: 16mm 13mm;
    }}
    * {{
      box-sizing: border-box;
    }}
    html, body {{
      margin: 0;
      padding: 0;
      background: #ffffff;
      color: #202124;
      font-family: Arial, "Noto Sans TC", "PingFang TC", "Microsoft JhengHei", sans-serif;
      font-size: 13px;
      line-height: 1.58;
    }}
    body {{
      max-width: 920px;
      margin: 0 auto;
    }}
    a {{
      color: #1a73e8;
      text-decoration: none;
      overflow-wrap: anywhere;
    }}
    .cover {{
      min-height: 220px;
      padding: 20px 0 26px;
      border-bottom: 2px solid #1a73e8;
      break-after: page;
    }}
    .cover h1 {{
      margin: 0 0 18px;
      font-size: 30px;
      line-height: 1.18;
      font-weight: 700;
      letter-spacing: 0;
    }}
    .meta {{
      color: #5f6368;
      font-size: 12px;
      margin: 6px 0;
      overflow-wrap: anywhere;
    }}
    .description {{
      margin-top: 18px;
      color: #3c4043;
      font-size: 14px;
    }}
    .toc {{
      break-after: page;
      padding-top: 4px;
    }}
    .toc h2 {{
      margin: 0 0 12px;
      font-size: 22px;
    }}
    .toc ol {{
      margin: 0;
      padding-left: 22px;
    }}
    .toc li {{
      margin: 5px 0;
    }}
    .step {{
      padding: 0 0 22px;
      margin: 0 0 24px;
      border-bottom: 1px solid #dadce0;
      break-inside: auto;
    }}
    .step:not(:first-of-type) {{
      break-before: page;
    }}
    .step-kicker {{
      color: #5f6368;
      font-size: 12px;
      font-weight: 700;
      margin: 0 0 6px;
    }}
    h1, h2, h3, h4 {{
      color: #202124;
      letter-spacing: 0;
      line-height: 1.25;
      break-after: avoid;
    }}
    h2 {{
      font-size: 21px;
      margin: 0 0 13px;
    }}
    h3 {{
      font-size: 17px;
      margin: 18px 0 8px;
    }}
    h4 {{
      font-size: 15px;
      margin: 16px 0 8px;
    }}
    p {{
      margin: 9px 0;
    }}
    ul, ol {{
      margin: 8px 0 12px 22px;
      padding: 0;
    }}
    li {{
      margin: 4px 0;
    }}
    img {{
      display: block;
      max-width: 100%;
      height: auto;
      margin: 12px auto;
      break-inside: avoid;
    }}
    .image-container {{
      text-align: center;
    }}
    aside {{
      display: block;
      margin: 14px 0;
      padding: 12px 14px;
      border-left: 4px solid #1a73e8;
      background: #f8fbff;
      break-inside: avoid;
    }}
    aside.warning {{
      border-left-color: #f9ab00;
      background: #fff8e1;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin: 14px 0;
      font-size: 12px;
    }}
    th, td {{
      border: 1px solid #dadce0;
      padding: 6px 8px;
      vertical-align: top;
    }}
    code {{
      font-family: "Roboto Mono", "SFMono-Regular", Consolas, monospace;
      font-size: 12px;
      background: #f1f3f4;
      padding: 1px 4px;
      border-radius: 3px;
      overflow-wrap: anywhere;
    }}
    pre {{
      margin: 12px 0;
      padding: 12px;
      border-radius: 6px;
      background: #f1f3f4;
      border: 1px solid #dadce0;
      overflow: visible;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      break-inside: avoid;
    }}
    pre code {{
      display: block;
      padding: 0;
      background: transparent;
      border-radius: 0;
      white-space: pre-wrap;
    }}
    devsite-code {{
      display: block;
    }}
    .step-title a {{
      color: inherit;
    }}
  </style>
</head>
<body>
  <section class="cover">
    <h1>{escaped_title}</h1>
    <div class="meta">來源：<a href="{escaped_source_url}">{escaped_source_url}</a></div>
    <div class="meta">步驟數：{len(steps)}</div>
    {f'<p class="description">{escaped_description}</p>' if escaped_description else ''}
  </section>
  <section class="toc">
    <h2>目錄</h2>
    <ol>
      {toc_items}
    </ol>
  </section>
  {step_sections}
</body>
</html>
"""


def _duration_text(step: dict[str, Any]) -> str:
    duration = str(step.get("duration") or "").strip()
    return f" · 約 {html.escape(duration)} 分鐘" if duration else ""
