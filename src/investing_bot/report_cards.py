from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import ceil, sqrt
from typing import Any


@dataclass(frozen=True)
class FamilyUniverseReportCard:
    date: str
    alpha_family: str
    evidence_universe: str
    broker_confirmed_samples: int
    total_samples: int
    mean_alpha_density: float
    lcb95_alpha_density: float
    mean_realized_pnl: float
    fill_rate: float
    slippage_over_model_p75: float
    status: str
    promotion_ready: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ReportCardBundle:
    cards: tuple[FamilyUniverseReportCard, ...]


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


def _date_of(row: dict[str, Any]) -> str:
    for key in ("recorded_at", "timestamp", "captured_at", "event_time"):
        value = str(row.get(key) or "").strip()
        if not value:
            continue
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.date().isoformat()
        except ValueError:
            if len(value) >= 10:
                return value[:10]
    return "unknown"


def _quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    q_norm = min(1.0, max(0.0, float(q)))
    index = max(1, ceil(len(ordered) * q_norm))
    return float(ordered[index - 1])


def _mean_lcb(values: list[float]) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    n = len(values)
    mean = sum(values) / n
    if n == 1:
        return mean, mean
    variance = sum((value - mean) ** 2 for value in values) / max(1, n - 1)
    stderr = sqrt(max(0.0, variance) / n)
    return mean, mean - (1.96 * stderr)


def build_report_cards(
    rows: list[dict[str, Any]],
    *,
    as_of_date: str | None = None,
    min_samples_for_promotion: int = 30,
    min_lcb95_alpha_density: float = 0.0,
    min_fill_rate: float = 0.35,
    max_slippage_over_model_p75: float = 0.25,
) -> ReportCardBundle:
    date_filter = str(as_of_date or "").strip()

    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        date = _date_of(row)
        if date_filter and date != date_filter:
            continue
        family = str(row.get("alpha_family") or row.get("family") or "unknown").strip().lower() or "unknown"
        universe = str(row.get("evidence_universe") or row.get("universe") or "default").strip().lower() or "default"
        grouped.setdefault((date, family, universe), []).append(row)

    cards: list[FamilyUniverseReportCard] = []
    for (date, family, universe), group in sorted(grouped.items()):
        broker_rows = [row for row in group if bool(row.get("broker_confirmed", True))]
        rewards = [_as_float(row.get("realized_alpha_density"), 0.0) for row in broker_rows]
        pnls = [_as_float(row.get("realized_pnl"), 0.0) for row in broker_rows]
        fills = [1.0 if bool(row.get("filled")) or _as_float(row.get("fill_quantity"), 0.0) > 0 else 0.0 for row in broker_rows]

        slippage_over_model: list[float] = []
        for row in broker_rows:
            slip = _as_float(row.get("slippage"), _as_float(row.get("slippage_p75"), 0.0))
            modeled = _as_float(row.get("modeled_slippage"), _as_float(row.get("modeled_slippage_p75"), 0.0))
            spread = _as_float(row.get("prevailing_spread"), _as_float(row.get("spread_cost"), 0.0))
            denom = spread if spread > 0 else 1.0
            slippage_over_model.append(max(0.0, slip - modeled) / denom)

        mean_alpha, lcb_alpha = _mean_lcb(rewards)
        mean_pnl = (sum(pnls) / len(pnls)) if pnls else 0.0
        fill_rate = (sum(fills) / len(fills)) if fills else 0.0
        slip_p75 = _quantile(slippage_over_model, 0.75)

        reasons: list[str] = []
        if len(broker_rows) < int(min_samples_for_promotion):
            reasons.append("insufficient_samples")
        if lcb_alpha <= float(min_lcb95_alpha_density):
            reasons.append("lcb_not_positive")
        if fill_rate < float(min_fill_rate):
            reasons.append("fill_rate_too_low")
        if slip_p75 > float(max_slippage_over_model_p75):
            reasons.append("slippage_drift")

        promotion_ready = len(reasons) == 0
        if promotion_ready:
            status = "promote_candidate"
        elif len(broker_rows) == 0:
            status = "no_broker_evidence"
        elif "insufficient_samples" in reasons:
            status = "probe_continue"
        else:
            status = "hold_or_degrade"

        cards.append(
            FamilyUniverseReportCard(
                date=date,
                alpha_family=family,
                evidence_universe=universe,
                broker_confirmed_samples=len(broker_rows),
                total_samples=len(group),
                mean_alpha_density=round(mean_alpha, 12),
                lcb95_alpha_density=round(lcb_alpha, 12),
                mean_realized_pnl=round(mean_pnl, 8),
                fill_rate=round(fill_rate, 6),
                slippage_over_model_p75=round(slip_p75, 6),
                status=status,
                promotion_ready=promotion_ready,
                reasons=tuple(sorted(set(reasons))),
            )
        )

    return ReportCardBundle(cards=tuple(cards))


def summarize_report_cards(bundle: ReportCardBundle) -> dict[str, Any]:
    cards = list(bundle.cards)
    by_status: dict[str, int] = {}
    for row in cards:
        by_status[row.status] = by_status.get(row.status, 0) + 1

    promote = [row for row in cards if row.promotion_ready]
    top = sorted(promote, key=lambda row: (row.lcb95_alpha_density, row.mean_alpha_density), reverse=True)

    return {
        "total_cards": len(cards),
        "status_counts": by_status,
        "top_promote_candidates": [
            {
                "date": row.date,
                "alpha_family": row.alpha_family,
                "evidence_universe": row.evidence_universe,
                "lcb95_alpha_density": row.lcb95_alpha_density,
            }
            for row in top[:5]
        ],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
