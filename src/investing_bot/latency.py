from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class LatencyProfile:
    quote_age_ms: float
    decision_ms: float
    submit_to_ack_ms: float
    ack_to_fill_ms: float
    cancel_roundtrip_ms: float
    stale_quote: bool
    has_complete_timestamps: bool


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


def _to_epoch_seconds(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        v = float(value)
        if v > 1_000_000_000_000:  # likely milliseconds
            return v / 1000.0
        return v
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _diff_ms(start: Any, end: Any) -> float:
    s = _to_epoch_seconds(start)
    e = _to_epoch_seconds(end)
    if s is None or e is None:
        return 0.0
    return max(0.0, (e - s) * 1000.0)


def build_latency_profile(observation: dict[str, Any] | None) -> LatencyProfile:
    row = observation or {}
    quote_age_ms = _as_float(row.get("quote_age_ms"), default=-1.0)
    if quote_age_ms < 0:
        quote_age_seconds = _as_float(row.get("quote_age_seconds"), default=0.0)
        quote_age_ms = max(0.0, quote_age_seconds * 1000.0)

    decision_ms = _as_float(row.get("decision_ms"), default=-1.0)
    if decision_ms < 0:
        decision_ms = _diff_ms(row.get("decision_start"), row.get("decision_end"))

    submit_to_ack_ms = _as_float(row.get("submit_to_ack_ms"), default=-1.0)
    if submit_to_ack_ms < 0:
        submit_to_ack_ms = _diff_ms(row.get("submit_time"), row.get("ack_time"))

    ack_to_fill_ms = _as_float(row.get("ack_to_fill_ms"), default=-1.0)
    if ack_to_fill_ms < 0:
        ack_to_fill_ms = _diff_ms(row.get("ack_time"), row.get("final_fill_time"))

    cancel_roundtrip_ms = _as_float(row.get("cancel_roundtrip_ms"), default=-1.0)
    if cancel_roundtrip_ms < 0:
        cancel_roundtrip_ms = _diff_ms(row.get("cancel_request_time"), row.get("cancel_ack_time"))

    stale_quote = bool(row.get("quotes_delayed")) or bool(quote_age_ms > 3000.0)
    has_complete_timestamps = bool(
        _to_epoch_seconds(row.get("decision_start")) is not None
        and _to_epoch_seconds(row.get("decision_end")) is not None
        and _to_epoch_seconds(row.get("submit_time")) is not None
    )

    return LatencyProfile(
        quote_age_ms=round(max(0.0, quote_age_ms), 6),
        decision_ms=round(max(0.0, decision_ms), 6),
        submit_to_ack_ms=round(max(0.0, submit_to_ack_ms), 6),
        ack_to_fill_ms=round(max(0.0, ack_to_fill_ms), 6),
        cancel_roundtrip_ms=round(max(0.0, cancel_roundtrip_ms), 6),
        stale_quote=stale_quote,
        has_complete_timestamps=has_complete_timestamps,
    )


def estimate_latency_penalty(profile: LatencyProfile) -> float:
    penalty = 0.0
    penalty += min(0.010, profile.quote_age_ms / 1000.0 * 0.0025)
    penalty += min(0.006, profile.decision_ms / 1000.0 * 0.0015)
    penalty += min(0.006, profile.submit_to_ack_ms / 1000.0 * 0.0015)
    penalty += min(0.004, profile.ack_to_fill_ms / 1000.0 * 0.0008)
    if profile.stale_quote:
        penalty += 0.010
    if not profile.has_complete_timestamps:
        penalty += 0.002
    return round(max(0.0, penalty), 6)


def latency_kill_switch(
    profile: LatencyProfile,
    *,
    max_quote_age_ms: float = 3000.0,
    max_decision_ms: float = 1200.0,
    max_submit_to_ack_ms: float = 5000.0,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if profile.quote_age_ms > max_quote_age_ms:
        reasons.append("latency_quote_age_exceeded")
    if profile.decision_ms > max_decision_ms:
        reasons.append("latency_decision_exceeded")
    if profile.submit_to_ack_ms > max_submit_to_ack_ms:
        reasons.append("latency_submit_ack_exceeded")
    if profile.stale_quote:
        reasons.append("latency_stale_quote")
    return (len(reasons) > 0), reasons
