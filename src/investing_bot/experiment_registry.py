from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


def stable_hash(payload: Mapping[str, Any] | list[Any] | str | int | float | bool | None) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def stamp_decision_context(
    *,
    decision_payload: Mapping[str, Any],
    policy_version: str,
    config: Mapping[str, Any],
    features: Mapping[str, Any],
) -> dict[str, Any]:
    enriched = dict(decision_payload)
    enriched["policy_version"] = str(policy_version or "").strip() or "unknown"
    enriched["config_hash"] = stable_hash(dict(config))
    enriched["feature_hash"] = stable_hash(dict(features))
    enriched["feature_keys"] = sorted(str(key) for key in features.keys())
    return enriched


@dataclass
class ExperimentRegistry:
    root_dir: Path

    def __post_init__(self) -> None:
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def _normalize_source(self, source: str) -> str:
        value = str(source or "").strip().lower()
        if value in {"live", "paper", "ghost"}:
            return value
        return "live"

    def _append(self, stream: str, payload: Mapping[str, Any], source: str) -> Path:
        now = datetime.now(timezone.utc)
        date_part = now.strftime("%Y-%m-%d")
        source_norm = self._normalize_source(source)
        stream_dir = self.root_dir / stream / source_norm
        stream_dir.mkdir(parents=True, exist_ok=True)
        path = stream_dir / f"{date_part}.jsonl"

        row = dict(payload)
        row.setdefault("recorded_at", now.isoformat())
        row.setdefault("data_source", source_norm)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True))
            handle.write("\n")
        return path

    def record_decision(
        self,
        *,
        decision_payload: Mapping[str, Any],
        policy_version: str,
        config: Mapping[str, Any],
        features: Mapping[str, Any],
        source: str = "live",
    ) -> Path:
        stamped = stamp_decision_context(
            decision_payload=decision_payload,
            policy_version=policy_version,
            config=config,
            features=features,
        )
        stamped.setdefault(
            "decision_id",
            stable_hash(
                {
                    "candidate": stamped.get("candidate_key"),
                    "action": stamped.get("action"),
                    "policy_version": stamped.get("policy_version"),
                    "feature_hash": stamped.get("feature_hash"),
                    "recorded_at": stamped.get("recorded_at"),
                }
            )[:16],
        )
        return self._append("decisions", stamped, source=source)
