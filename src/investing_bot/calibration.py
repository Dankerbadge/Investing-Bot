from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ReliabilityBin:
    bucket_index: int
    lower: float
    upper: float
    count: int
    mean_prediction: float
    empirical_rate: float


def _as_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "").strip()
    if not text:
        return default
    try:
        return float(text)
    except ValueError:
        return default


def brier_score(predictions: list[float], outcomes: list[float]) -> float:
    if len(predictions) != len(outcomes):
        raise ValueError("predictions and outcomes must have equal length")
    if not predictions:
        return 0.0
    total = 0.0
    for p, y in zip(predictions, outcomes):
        p_clamped = min(1.0, max(0.0, float(p)))
        y_clamped = 1.0 if float(y) >= 0.5 else 0.0
        total += (p_clamped - y_clamped) ** 2
    return total / len(predictions)


def quantile_pinball_loss(predictions: list[float], actuals: list[float], quantile: float) -> float:
    if len(predictions) != len(actuals):
        raise ValueError("predictions and actuals must have equal length")
    if not predictions:
        return 0.0
    q = min(1.0, max(0.0, float(quantile)))
    total = 0.0
    for pred, actual in zip(predictions, actuals):
        err = float(actual) - float(pred)
        total += q * err if err >= 0 else (q - 1.0) * err
    return total / len(predictions)


def reliability_bins(predictions: list[float], outcomes: list[float], n_bins: int = 10) -> list[ReliabilityBin]:
    if len(predictions) != len(outcomes):
        raise ValueError("predictions and outcomes must have equal length")
    if n_bins <= 0:
        raise ValueError("n_bins must be positive")

    bucket_preds: list[list[float]] = [[] for _ in range(n_bins)]
    bucket_outcomes: list[list[float]] = [[] for _ in range(n_bins)]

    for pred, outcome in zip(predictions, outcomes):
        p = min(1.0, max(0.0, float(pred)))
        bucket = min(n_bins - 1, int(p * n_bins))
        bucket_preds[bucket].append(p)
        bucket_outcomes[bucket].append(1.0 if float(outcome) >= 0.5 else 0.0)

    bins: list[ReliabilityBin] = []
    for idx in range(n_bins):
        preds = bucket_preds[idx]
        outs = bucket_outcomes[idx]
        count = len(preds)
        lower = idx / n_bins
        upper = (idx + 1) / n_bins
        mean_prediction = sum(preds) / count if count else 0.0
        empirical_rate = sum(outs) / count if count else 0.0
        bins.append(
            ReliabilityBin(
                bucket_index=idx,
                lower=lower,
                upper=upper,
                count=count,
                mean_prediction=mean_prediction,
                empirical_rate=empirical_rate,
            )
        )
    return bins


def summarize_fill_calibration(
    rows: list[dict[str, Any]],
    *,
    prediction_key: str = "predicted_fill_probability",
    outcome_key: str = "filled",
    n_bins: int = 10,
) -> dict[str, Any]:
    preds: list[float] = []
    outcomes: list[float] = []

    for row in rows:
        if not isinstance(row, dict):
            continue
        preds.append(_as_float(row.get(prediction_key), default=0.0))
        outcomes.append(_as_float(row.get(outcome_key), default=0.0))

    bins = reliability_bins(preds, outcomes, n_bins=n_bins)
    return {
        "count": len(preds),
        "brier_score": brier_score(preds, outcomes),
        "reliability_bins": [
            {
                "bucket_index": item.bucket_index,
                "lower": item.lower,
                "upper": item.upper,
                "count": item.count,
                "mean_prediction": item.mean_prediction,
                "empirical_rate": item.empirical_rate,
            }
            for item in bins
        ],
    }
