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

    def _as_float(self, value: Any, default: float = 0.0) -> float:
        if isinstance(value, bool):
            return default
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value or "").strip()
        if not text:
            return default
        try:
            return float(text)
        except ValueError:
            return default

    def _quote_quality_tier(self, payload: Mapping[str, Any]) -> str:
        quote_mode = str(payload.get("quote_mode") or payload.get("entitlement") or "").strip().lower()
        if "delayed" in quote_mode or bool(payload.get("quotes_delayed")):
            return "delayed"
        quote_age = self._as_float(payload.get("quote_age_seconds"), default=0.0)
        if quote_age > 5.0:
            return "stale"
        if quote_age > 0.0:
            return "realtime"
        return "unknown"

    def _quote_reliability_score(self, tier: str, payload: Mapping[str, Any]) -> float:
        explicit = self._as_float(payload.get("quote_reliability_score"), default=-1.0)
        if explicit >= 0.0:
            return min(1.0, max(0.0, explicit))
        return {
            "realtime": 1.0,
            "unknown": 0.75,
            "stale": 0.40,
            "delayed": 0.25,
        }.get(tier, 0.75)

    def _book_reliability_score(self, payload: Mapping[str, Any]) -> float:
        explicit = self._as_float(payload.get("book_reliability_score"), default=-1.0)
        if explicit >= 0.0:
            return min(1.0, max(0.0, explicit))
        source = str(payload.get("book_source") or "").strip().lower()
        if "reverse" in source or "unknown" in source:
            return 0.55
        if self._as_float(payload.get("book_depth_contracts"), default=0.0) <= 0:
            return 0.50
        return 0.90

    def _book_reliability_tier(self, score: float) -> str:
        if score >= 0.85:
            return "high"
        if score >= 0.65:
            return "medium"
        return "low"

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
        quote_tier = self._quote_quality_tier(enriched)
        quote_score = self._quote_reliability_score(quote_tier, enriched)
        book_score = self._book_reliability_score(enriched)
        enriched.setdefault("quote_quality_tier", quote_tier)
        enriched.setdefault("quote_reliability_score", round(quote_score, 6))
        enriched.setdefault("book_reliability_score", round(book_score, 6))
        enriched.setdefault("book_reliability_tier", self._book_reliability_tier(book_score))

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
