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

    def _append(self, stream: str, payload: Mapping[str, Any]) -> Path:
        now = datetime.now(timezone.utc)
        date_part = now.strftime("%Y-%m-%d")
        stream_dir = self.root_dir / stream
        stream_dir.mkdir(parents=True, exist_ok=True)
        target = stream_dir / f"{date_part}.jsonl"

        enriched = dict(payload)
        enriched.setdefault("recorded_at", now.isoformat())

        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(enriched, sort_keys=True))
            handle.write("\n")
        return target

    def record_chain_snapshot(self, payload: Mapping[str, Any]) -> Path:
        return self._append("chain_snapshots", payload)

    def record_signal(self, payload: Mapping[str, Any]) -> Path:
        return self._append("signals", payload)

    def record_order(self, payload: Mapping[str, Any]) -> Path:
        return self._append("orders", payload)

    def record_fill(self, payload: Mapping[str, Any]) -> Path:
        return self._append("fills", payload)
