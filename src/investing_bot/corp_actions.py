from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CorporateActionContext:
    adjusted_option: bool = False
    non_standard_expiration: bool = False
    short_american: bool = False
    days_to_expiration: float = 30.0
    ex_dividend_days: float = 999.0
    intrinsic_value: float = 0.0
    extrinsic_value: float = 0.0


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


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def infer_corporate_action_context(metadata: dict[str, Any] | None = None) -> CorporateActionContext:
    row = metadata if isinstance(metadata, dict) else {}
    expiration_type = str(row.get("expiration_type") or row.get("expiry_type") or "").strip().lower()

    adjusted_option = _as_bool(
        row.get("adjusted_option")
        or row.get("is_adjusted")
        or row.get("contract_adjusted"),
        default=False,
    )
    non_standard = _as_bool(row.get("non_standard_expiration") or row.get("is_non_standard_expiration"), default=False)
    if not non_standard and expiration_type in {"weekly", "quarterly", "non_standard"}:
        non_standard = True

    short_american = _as_bool(row.get("short_american") or row.get("short_american_option"), default=False)
    if not short_american:
        side = str(row.get("side") or "").strip().lower()
        is_american = _as_bool(row.get("is_american") or row.get("american_style"), default=False)
        short_american = bool(is_american and side == "sell")

    return CorporateActionContext(
        adjusted_option=adjusted_option,
        non_standard_expiration=non_standard,
        short_american=short_american,
        days_to_expiration=max(0.0, _as_float(row.get("days_to_expiration") or row.get("dte"), default=30.0)),
        ex_dividend_days=max(0.0, _as_float(row.get("ex_dividend_days"), default=999.0)),
        intrinsic_value=max(0.0, _as_float(row.get("intrinsic_value"), default=0.0)),
        extrinsic_value=max(0.0, _as_float(row.get("extrinsic_value"), default=0.0)),
    )


def assignment_risk_score(context: CorporateActionContext) -> float:
    score = 0.0
    if context.short_american:
        score += 0.15
    if context.days_to_expiration <= 2.0:
        score += 0.25
    if context.ex_dividend_days <= 1.0:
        score += 0.35
    if context.intrinsic_value > 0.0 and context.extrinsic_value <= 0.05:
        score += 0.25
    return min(1.0, round(score, 6))


def corporate_action_penalty(context: CorporateActionContext) -> float:
    penalty = 0.0
    if context.adjusted_option:
        penalty += 0.02
    if context.non_standard_expiration:
        penalty += 0.01
    penalty += assignment_risk_score(context) * 0.02
    return round(penalty, 6)


def corporate_action_hard_block(context: CorporateActionContext) -> bool:
    if context.adjusted_option:
        return True
    if context.non_standard_expiration and context.short_american:
        return True
    return assignment_risk_score(context) >= 0.85


def corporate_action_reasons(context: CorporateActionContext) -> tuple[str, ...]:
    reasons: list[str] = []
    if context.adjusted_option:
        reasons.append("adjusted_option_contract")
    if context.non_standard_expiration:
        reasons.append("non_standard_expiration")
    risk = assignment_risk_score(context)
    if risk >= 0.35:
        reasons.append("assignment_risk_elevated")
    if risk >= 0.85:
        reasons.append("assignment_risk_hard_limit")
    return tuple(reasons)
