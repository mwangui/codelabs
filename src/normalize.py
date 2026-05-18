from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


CODELABS_HOST = "codelabs.developers.google.com"
ALLOWED_CODELAB_HOSTS = {
    CODELABS_HOST,
    "developers.google.com",
    "developers.home.google.com",
}
EXCLUDED_PATH_SEGMENTS = {"img", "images", "assets", "files", "_static", "static"}
EXCLUDED_SINGLE_SEGMENTS = {"s", "_static", "static"}
EXCLUDED_LAST_SEGMENTS = {"OWNERS", "README", "README.MD", "LICENSE", "CODEOWNERS"}


def normalize_language(value: str | None) -> str:
    """把 zh_tw、zh-TW 等寫法統一成 zh-tw。"""
    if not value:
        return "zh-tw"
    return value.strip().replace("_", "-").lower()


def normalize_codelab_url(url: str, language: str = "zh-tw") -> str | None:
    """正規化 Codelab URL：去掉 #step、補上 hl 參數、排除非 Codelab 頁。"""
    raw = (url or "").strip()
    if not raw or raw.startswith("#"):
        return None

    parsed = urlparse(raw)
    if not parsed.scheme:
        raw = f"https://{raw.lstrip('/')}"
        parsed = urlparse(raw)

    host = parsed.netloc.lower()
    if host not in ALLOWED_CODELAB_HOSTS:
        return None

    path = parsed.path.strip("/")
    if not path:
        return None

    segments = [segment for segment in path.split("/") if segment]
    first_segment = segments[0]
    if first_segment in {"events", "about", "tools", "sitemap.xml"}:
        return None
    if host != CODELABS_HOST and "codelabs" not in segments:
        return None
    if first_segment in EXCLUDED_SINGLE_SEGMENTS:
        return None
    if any(segment in EXCLUDED_PATH_SEGMENTS for segment in segments):
        return None
    if any("." in segment for segment in segments):
        return None
    if segments[-1].upper() in EXCLUDED_LAST_SEGMENTS:
        return None
    if first_segment == "codelabs":
        if len(segments) < 2 or "." in segments[1]:
            return None
        codelab_path = "/" + "/".join(segments)
    else:
        codelab_path = "/" + "/".join(segments)

    query = dict(parse_qsl(parsed.query, keep_blank_values=False))
    query["hl"] = normalize_language(language)
    normalized_query = urlencode(sorted(query.items()))

    return urlunparse(
        (
            "https",
            host,
            codelab_path,
            "",
            normalized_query,
            "",
        )
    )


def slug_from_url(url: str) -> str:
    parsed = urlparse(url)
    segments = [segment for segment in parsed.path.strip("/").split("/") if segment]
    if not segments:
        return "codelab"
    if segments[0] == "codelabs" and len(segments) > 1:
        segments = segments[1:]
    return "-".join(segments) or "codelab"


def strip_fragment(url: str) -> str:
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, parsed.query, ""))


def safe_filename_part(value: str, max_chars: int = 48) -> str:
    """保留中文可讀性，同時移除 macOS/Windows 不適合檔名的字元。"""
    text = unicodedata.normalize("NFKC", value or "").strip()
    text = re.sub(r"[\\/:*?\"<>|#%&{}$!`'@+=]", " ", text)
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-. ")
    if not text:
        return "未命名"
    return text[:max_chars].strip("-. ") or "未命名"


def build_pdf_filename(index: int, slug: str, title: str, max_title_chars: int = 48) -> str:
    title_short = safe_filename_part(title, max_title_chars)
    slug_safe = safe_filename_part(slug, 80)
    return f"{index:03d}__{slug_safe}__{title_short}.pdf"


def ensure_directory(path: str | Path) -> Path:
    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    return directory
