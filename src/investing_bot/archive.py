from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping


@dataclass
class ArchiveWriter:
    root_dir: Path

    def __post_init__(self) -> None:
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def _normalize_source(self, source: str) -> str:
        normalized = str(source or "").strip().lower()
        if normalized not in {"live", "paper", "ghost"}:
            return "live"
        return normalized

    def _append(self, stream: str, payload: Mapping[str, Any], source: str = "live") -> Path:
        now = datetime.now(timezone.utc)
        date_part = now.strftime("%Y-%m-%d")
        source_norm = self._normalize_source(source)
        stream_dir = self.root_dir / stream / source_norm
        stream_dir.mkdir(parents=True, exist_ok=True)
        target = stream_dir / f"{date_part}.jsonl"

        enriched = dict(payload)
        enriched.setdefault("recorded_at", now.isoformat())
        enriched.setdefault("data_source", source_norm)

        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(enriched, sort_keys=True))
            handle.write("\n")
        return target

    def record_chain_snapshot(self, payload: Mapping[str, Any], source: str = "live") -> Path:
        return self._append("chain_snapshots", payload, source=source)

    def record_signal(self, payload: Mapping[str, Any], source: str = "live") -> Path:
        return self._append("signals", payload, source=source)

    def record_order(self, payload: Mapping[str, Any], source: str = "live") -> Path:
        return self._append("orders", payload, source=source)

    def record_fill(self, payload: Mapping[str, Any], source: str = "live") -> Path:
        return self._append("fills", payload, source=source)
