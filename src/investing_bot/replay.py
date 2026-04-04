from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class ReplayResult:
    replayed_count: int
    actions_by_type: dict[str, int]
    deterministic_signature: str
    decision_ids: tuple[str, ...]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return rows
    for line in lines:
        text = line.strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _timestamp_sort_value(value: Any) -> tuple[int, str]:
    text = str(value or "").strip()
    if not text:
        return (1, "")
    try:
        iso = datetime.fromisoformat(text.replace("Z", "+00:00")).isoformat()
        return (0, iso)
    except ValueError:
        return (1, text)


def _decision_id(row: dict[str, Any], index: int) -> str:
    explicit = str(row.get("decision_id") or "").strip()
    if explicit:
        return explicit
    seed = {
        "recorded_at": row.get("recorded_at"),
        "captured_at": row.get("captured_at"),
        "candidate_key": row.get("candidate_key") or row.get("ticker") or row.get("symbol"),
        "index": index,
    }
    encoded = json.dumps(seed, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def replay_records(
    *,
    rows: list[dict[str, Any]],
    decision_fn: Callable[[dict[str, Any]], str],
) -> ReplayResult:
    normalized = [row for row in rows if isinstance(row, dict)]
    ordered = sorted(
        normalized,
        key=lambda row: (
            _timestamp_sort_value(row.get("recorded_at") or row.get("captured_at") or row.get("timestamp")),
            str(row.get("decision_id") or row.get("candidate_key") or row.get("ticker") or ""),
        ),
    )

    actions_by_type: dict[str, int] = {}
    materialized: list[str] = []
    decision_ids: list[str] = []

    for index, row in enumerate(ordered):
        action = str(decision_fn(dict(row)) or "").strip().lower() or "skip"
        actions_by_type[action] = actions_by_type.get(action, 0) + 1
        did = _decision_id(row, index)
        decision_ids.append(did)
        materialized.append(f"{did}|{action}")

    signature_seed = "\n".join(materialized)
    signature = hashlib.sha256(signature_seed.encode("utf-8")).hexdigest()
    return ReplayResult(
        replayed_count=len(ordered),
        actions_by_type=actions_by_type,
        deterministic_signature=signature,
        decision_ids=tuple(decision_ids),
    )


def replay_archive_stream(
    *,
    archive_root: Path,
    stream: str,
    source: str = "live",
    decision_fn: Callable[[dict[str, Any]], str],
) -> ReplayResult:
    source_norm = str(source or "").strip().lower() or "live"
    stream_dir = archive_root / stream / source_norm
    rows: list[dict[str, Any]] = []
    if stream_dir.exists() and stream_dir.is_dir():
        for path in sorted(stream_dir.glob("*.jsonl")):
            rows.extend(_read_jsonl(path))
    return replay_records(rows=rows, decision_fn=decision_fn)
