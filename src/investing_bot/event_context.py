from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

SEC_SUBMISSIONS_BASE = "https://data.sec.gov/submissions"
SEC_COMPANY_FACTS_BASE = "https://data.sec.gov/api/xbrl/companyfacts"


def _normalize_cik(cik: str | int) -> str:
    text = str(cik).strip()
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits.zfill(10)


def sec_submissions_url(cik: str | int) -> str:
    return f"{SEC_SUBMISSIONS_BASE}/CIK{_normalize_cik(cik)}.json"


def sec_companyfacts_url(cik: str | int) -> str:
    return f"{SEC_COMPANY_FACTS_BASE}/CIK{_normalize_cik(cik)}.json"


@dataclass(frozen=True)
class EventContext:
    filing_shock: bool
    earnings_window: bool
    macro_release_window: bool
    ex_dividend_risk: bool
    assignment_risk_elevated: bool
    event_risk_score: float


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def infer_event_context(metadata: dict[str, Any] | None, now_utc: datetime | None = None) -> EventContext:
    data = metadata or {}
    now = now_utc or datetime.now(timezone.utc)

    filing_time = _parse_dt(data.get("sec_filing_time") or data.get("filing_time"))
    filing_shock = bool(data.get("sec_material_filing")) or (
        filing_time is not None and abs((now - filing_time).total_seconds()) <= 6 * 3600
    )

    earnings_time = _parse_dt(data.get("earnings_time"))
    earnings_window = bool(data.get("is_earnings_window")) or (
        earnings_time is not None and abs((now - earnings_time).total_seconds()) <= 24 * 3600
    )

    macro_release_time = _parse_dt(data.get("macro_release_time"))
    macro_release_window = bool(data.get("is_macro_release_window")) or (
        macro_release_time is not None and abs((now - macro_release_time).total_seconds()) <= 90 * 60
    )

    ex_dividend_time = _parse_dt(data.get("ex_dividend_time"))
    ex_dividend_risk = bool(data.get("is_ex_dividend_window")) or (
        ex_dividend_time is not None and 0 <= (ex_dividend_time - now).total_seconds() <= 24 * 3600
    )

    assignment_risk_elevated = bool(data.get("assignment_risk_elevated")) or (
        float(data.get("assignment_risk") or 0.0) >= 0.6
    )

    score = 0.0
    if filing_shock:
        score += 0.30
    if earnings_window:
        score += 0.30
    if macro_release_window:
        score += 0.20
    if ex_dividend_risk:
        score += 0.20
    if assignment_risk_elevated:
        score += 0.20

    return EventContext(
        filing_shock=filing_shock,
        earnings_window=earnings_window,
        macro_release_window=macro_release_window,
        ex_dividend_risk=ex_dividend_risk,
        assignment_risk_elevated=assignment_risk_elevated,
        event_risk_score=round(min(1.0, max(0.0, score)), 6),
    )


def event_context_penalty(context: EventContext) -> float:
    return round(0.02 * context.event_risk_score, 6)


def event_context_reasons(context: EventContext) -> list[str]:
    reasons: list[str] = []
    if context.filing_shock:
        reasons.append("event_filing_shock")
    if context.earnings_window:
        reasons.append("event_earnings_window")
    if context.macro_release_window:
        reasons.append("event_macro_release_window")
    if context.ex_dividend_risk:
        reasons.append("event_ex_dividend_window")
    if context.assignment_risk_elevated:
        reasons.append("event_assignment_risk_elevated")
    return reasons
