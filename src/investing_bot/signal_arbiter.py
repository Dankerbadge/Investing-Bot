from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import Candidate


def _as_float(value: Any, default: float = 0.0) -> float:
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


def _normalize_text(value: Any) -> str:
    return str(value or "").strip().lower()


@dataclass(frozen=True)
class ArbitratedSignal:
    candidate: Candidate
    thesis_key: str
    arbiter_score: float


@dataclass(frozen=True)
class ArbitrationResult:
    selected: tuple[ArbitratedSignal, ...]
    dropped: tuple[ArbitratedSignal, ...]


def thesis_key_for_candidate(candidate: Candidate, *, default_window: str = "session") -> str:
    metadata = candidate.metadata if isinstance(candidate.metadata, dict) else {}
    window = str(
        metadata.get("event_window")
        or metadata.get("thesis_window")
        or metadata.get("event_key")
        or candidate.event_key
        or default_window
    ).strip()
    window_norm = window.lower() if window else default_window
    underlying = str(candidate.underlying or candidate.ticker).strip().upper()
    return f"{underlying}|{window_norm}"


def arbiter_score_for_candidate(candidate: Candidate) -> float:
    metadata = candidate.metadata if isinstance(candidate.metadata, dict) else {}
    alpha_lcb = _as_float(
        metadata.get("alpha_density_lcb")
        or metadata.get("live_alpha_density_lcb")
        or metadata.get("alpha_density")
        or metadata.get("alpha_score"),
        default=candidate.surface_residual,
    )
    spread_penalty = max(0.0, candidate.spread_cost)
    assignment_risk = max(0.0, _as_float(metadata.get("assignment_risk"), 0.0))
    capital_usage = max(0.0, _as_float(metadata.get("capital_usage_score"), 0.0))
    evidence_penalty = 0.0
    if _normalize_text(metadata.get("evidence_lane")) == "capital":
        live_samples = int(_as_float(metadata.get("broker_confirmed_live_samples"), 0.0))
        if live_samples <= 0:
            evidence_penalty += 0.05

    score = alpha_lcb - spread_penalty - (assignment_risk * 0.40) - (capital_usage * 0.20) - evidence_penalty
    return round(score, 12)


def arbitrate_signals(
    candidates: list[Candidate],
    *,
    max_per_thesis: int = 1,
    default_window: str = "session",
) -> ArbitrationResult:
    limit = max(1, int(max_per_thesis))
    grouped: dict[str, list[ArbitratedSignal]] = {}

    for candidate in candidates:
        key = thesis_key_for_candidate(candidate, default_window=default_window)
        row = ArbitratedSignal(
            candidate=candidate,
            thesis_key=key,
            arbiter_score=arbiter_score_for_candidate(candidate),
        )
        grouped.setdefault(key, []).append(row)

    selected: list[ArbitratedSignal] = []
    dropped: list[ArbitratedSignal] = []
    for key, rows in grouped.items():
        ranked = sorted(
            rows,
            key=lambda item: (
                item.arbiter_score,
                item.candidate.confidence,
                item.candidate.ticker,
            ),
            reverse=True,
        )
        selected.extend(ranked[:limit])
        dropped.extend(ranked[limit:])

    selected_sorted = tuple(
        sorted(selected, key=lambda item: (item.arbiter_score, item.candidate.confidence, item.candidate.ticker), reverse=True)
    )
    dropped_sorted = tuple(
        sorted(dropped, key=lambda item: (item.arbiter_score, item.candidate.confidence, item.candidate.ticker), reverse=True)
    )
    return ArbitrationResult(selected=selected_sorted, dropped=dropped_sorted)


def selected_candidates(result: ArbitrationResult) -> tuple[Candidate, ...]:
    return tuple(item.candidate for item in result.selected)
