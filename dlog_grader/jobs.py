"""Job records, persistent queue state, and batch reports."""
from __future__ import annotations

import csv
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .paths import CONFIG_DIR, QUEUE_STATE_PATH, REPORT_DIR

JOB_STATUS_ORDER = ("pending", "running", "success", "failed", "cancelled", "skipped")
JOB_STATUS_LABELS = {
    "pending": "待处理",
    "running": "处理中",
    "success": "成功",
    "failed": "失败",
    "cancelled": "已取消",
    "skipped": "跳过",
    "import_failed": "导入失败",
}


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def format_duration_hms(seconds: float | None) -> str:
    """Format elapsed time as HH:MM:SS, with a short fallback for invalid data."""
    try:
        value = max(0.0, float(seconds))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "—"
    total = int(round(value))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


@dataclass
class JobRecord:
    job_id: int
    source: str
    relative: str
    output: str
    kind: str
    status: str = "pending"       # pending/running/success/failed/cancelled/skipped
    progress: float = 0.0
    encoder: str = ""
    audio_mode: str = ""
    attempts: int = 0
    error: str = ""
    started_at: str = ""
    finished_at: str = ""
    duration_sec: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "JobRecord":
        allowed = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in allowed})


class QueueStore:
    """Save queue state for crash recovery and produce CSV/JSON reports."""

    def __init__(self, state_path: Path | None = None):
        self.state_path = state_path or QUEUE_STATE_PATH

    def save_state(
        self, jobs: list[JobRecord], *, status: str = "running", strict: bool = False
    ) -> bool:
        payload = {
            "version": 1,
            "updated_at": now_iso(),
            "status": status,
            "jobs": [job.to_dict() for job in jobs],
        }
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.state_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.state_path)
            return True
        except Exception:
            if strict:
                raise
            return False

    def load_state(self) -> tuple[str, list[JobRecord]]:
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            jobs = [JobRecord.from_dict(x) for x in data.get("jobs", [])]
            return str(data.get("status", "unknown")), jobs
        except Exception:
            return "none", []

    def write_report(
        self,
        jobs: list[JobRecord],
        *,
        input_dir: Path,
        output_dir: Path,
        started_at: str,
        cancelled: bool = False,
        duration_sec: float | None = None,
        scope: str = "all",
        skipped_scope: int = 0,
        scope_skipped_files: list[str] | None = None,
    ) -> tuple[Path, Path]:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_path = REPORT_DIR / f"batch_{stamp}.json"
        csv_path = REPORT_DIR / f"batch_{stamp}.csv"
        counts: dict[str, int] = {}
        for job in jobs:
            counts[job.status] = counts.get(job.status, 0) + 1
        payload = {
            "version": 1,
            "started_at": started_at,
            "finished_at": now_iso(),
            "duration_sec": duration_sec,
            "cancelled": cancelled,
            "input_dir": str(input_dir),
            "output_dir": str(output_dir),
            "scope": scope,
            "skipped_scope": skipped_scope,
            "scope_skipped_files": scope_skipped_files or [],
            "counts": counts,
            "jobs": [job.to_dict() for job in jobs],
        }
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=list(JobRecord.__dataclass_fields__.keys()))
            writer.writeheader()
            for job in jobs:
                writer.writerow(job.to_dict())
        return json_path, csv_path
