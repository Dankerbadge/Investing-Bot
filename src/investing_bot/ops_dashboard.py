from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone

from .alerts import Alert
from .telemetry import TelemetrySummary


def _level_rank(level: str) -> int:
    normalized = str(level or "").strip().lower()
    return {"info": 1, "warn": 2, "critical": 3}.get(normalized, 0)


def dashboard_health(alerts: tuple[Alert, ...] | list[Alert]) -> str:
    max_rank = 0
    for alert in alerts:
        max_rank = max(max_rank, _level_rank(alert.level))
    if max_rank >= 3:
        return "halted"
    if max_rank >= 2:
        return "degraded"
    return "healthy"


def build_ops_dashboard(
    *,
    summary: TelemetrySummary,
    alerts: tuple[Alert, ...] | list[Alert],
    stage: str,
    capital_multiplier: float,
    as_of: str | None = None,
) -> dict[str, object]:
    alert_rows = [asdict(alert) for alert in alerts]
    stage_norm = str(stage or "").strip().lower() or "unknown"
    ts = str(as_of or "").strip() or datetime.now(timezone.utc).isoformat()

    return {
        "as_of": ts,
        "stage": stage_norm,
        "health": dashboard_health(alerts),
        "capital_multiplier": round(max(0.0, min(1.0, float(capital_multiplier))), 6),
        "summary": asdict(summary),
        "alert_count": len(alert_rows),
        "alert_levels": {
            "critical": sum(1 for alert in alerts if str(alert.level).lower() == "critical"),
            "warn": sum(1 for alert in alerts if str(alert.level).lower() == "warn"),
            "info": sum(1 for alert in alerts if str(alert.level).lower() == "info"),
        },
        "alerts": alert_rows,
    }
