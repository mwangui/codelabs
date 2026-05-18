from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MANIFEST_COLUMNS = [
    "index",
    "slug",
    "title",
    "pdf_filename",
    "url",
    "status",
    "step_count",
    "created_at",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def read_json(path: str | Path, default: Any) -> Any:
    file_path = Path(path)
    if not file_path.exists():
        return default
    try:
        return json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def write_json(path: str | Path, data: Any) -> None:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def append_manifest(path: str | Path, row: dict[str, Any]) -> None:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    exists = file_path.exists()

    with file_path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_COLUMNS)
        if not exists:
            writer.writeheader()
        writer.writerow({column: row.get(column, "") for column in MANIFEST_COLUMNS})


def write_errors(path: str | Path, errors: list[dict[str, Any]]) -> None:
    write_json(path, errors)


def load_errors(path: str | Path) -> list[dict[str, Any]]:
    data = read_json(path, [])
    return data if isinstance(data, list) else []
