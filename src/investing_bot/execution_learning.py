from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from .models import Candidate
from .scoring import ExecutionAdjustments


@dataclass(frozen=True)
class LearnedExecutionPrior:
    bucket_key: str
    observations: int
    expected_fill_probability: float
    slippage_p95_penalty: float
    post_fill_alpha_decay_penalty: float
    uncertainty_penalty: float
    execution_penalty: float
    model_error_score: float


def _safe_float(value: Any, default: float = 0.0) -> float:
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


def _percentile(sorted_values: list[float], q: float) -> float:
    if not sorted_values:
        return 0.0
    clamped_q = min(1.0, max(0.0, q))
    idx = int((len(sorted_values) - 1) * clamped_q)
    return sorted_values[idx]


def _bucket_key_from_row(row: dict[str, Any]) -> str:
    explicit = str(row.get("execution_bucket") or "").strip()
    if explicit:
        return explicit
    strategy = str(row.get("strategy_family") or "").strip().lower()
    underlying = str(row.get("underlying") or "").strip().upper()
    ticker = str(row.get("ticker") or "").strip().upper()
    if strategy and underlying:
        return f"{strategy}|{underlying}"
    if strategy and ticker:
        return f"{strategy}|{ticker}"
    if ticker:
        return ticker
    return "global"


def _bucket_key_from_candidate(candidate: Candidate) -> str:
    explicit = str(candidate.metadata.get("execution_bucket") or "").strip()
    if explicit:
        return explicit
    strategy = str(candidate.strategy_family or "").strip().lower()
    underlying = str(candidate.underlying or "").strip().upper()
    ticker = str(candidate.ticker or "").strip().upper()
    if strategy and underlying:
        return f"{strategy}|{underlying}"
    if strategy and ticker:
        return f"{strategy}|{ticker}"
    if ticker:
        return ticker
    return "global"


def _read_jsonl_records(stream_dir: Path) -> list[dict[str, Any]]:
    if not stream_dir.exists() or not stream_dir.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(stream_dir.glob("*.jsonl")):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
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


def learn_execution_priors(archive_root: Path, min_observations: int = 3) -> dict[str, LearnedExecutionPrior]:
    orders = _read_jsonl_records(archive_root / "orders")
    fills = _read_jsonl_records(archive_root / "fills")
    signals = _read_jsonl_records(archive_root / "signals")

    attempted_by_bucket: dict[str, float] = {}
    filled_by_bucket: dict[str, float] = {}
    slippage_by_bucket: dict[str, list[float]] = {}
    alpha_decay_by_bucket: dict[str, list[float]] = {}
    model_error_by_bucket: dict[str, list[float]] = {}

    for row in orders:
        key = _bucket_key_from_row(row)
        qty = max(1.0, _safe_float(row.get("order_quantity") or row.get("requested_quantity") or 1.0, default=1.0))
        attempted_by_bucket[key] = attempted_by_bucket.get(key, 0.0) + qty

    for row in fills:
        key = _bucket_key_from_row(row)
        fill_qty = max(0.0, _safe_float(row.get("fill_quantity") or row.get("filled_quantity") or 0.0, default=0.0))
        if fill_qty > 0:
            filled_by_bucket[key] = filled_by_bucket.get(key, 0.0) + fill_qty

        slippage = abs(_safe_float(row.get("slippage_dollars") or row.get("fill_vs_mid_dollars"), default=0.0))
        if slippage > 0:
            slippage_by_bucket.setdefault(key, []).append(slippage)

        decay = abs(
            _safe_float(
                row.get("post_fill_alpha_decay")
                or row.get("alpha_decay_2m")
                or row.get("post_fill_drift_2m"),
                default=0.0,
            )
        )
        if decay > 0:
            alpha_decay_by_bucket.setdefault(key, []).append(decay)

    for row in signals:
        key = _bucket_key_from_row(row)
        predicted = _safe_float(row.get("predicted_net_edge") or row.get("expected_net_edge"), default=0.0)
        realized = _safe_float(row.get("realized_net_edge"), default=0.0)
        if predicted != 0.0 or realized != 0.0:
            model_error_by_bucket.setdefault(key, []).append(abs(predicted - realized))

    all_keys = (
        set(attempted_by_bucket)
        | set(filled_by_bucket)
        | set(slippage_by_bucket)
        | set(alpha_decay_by_bucket)
        | set(model_error_by_bucket)
    )

    priors: dict[str, LearnedExecutionPrior] = {}
    for key in sorted(all_keys):
        attempts = attempted_by_bucket.get(key, 0.0)
        fills_qty = filled_by_bucket.get(key, 0.0)
        observations = int(max(attempts, len(slippage_by_bucket.get(key, [])), len(alpha_decay_by_bucket.get(key, []))))
        if observations < min_observations:
            continue

        # Laplace-smoothed fill rate keeps sparse buckets from overreacting.
        fill_probability = (fills_qty + 1.0) / (attempts + 2.0) if attempts > 0 else 0.5

        slippages = sorted(slippage_by_bucket.get(key, []))
        alpha_decays = sorted(alpha_decay_by_bucket.get(key, []))
        model_errors = sorted(model_error_by_bucket.get(key, []))

        slippage_p95 = _percentile(slippages, 0.95)
        alpha_decay_p95 = _percentile(alpha_decays, 0.95)
        model_error_p95 = _percentile(model_errors, 0.95)

        execution_penalty = max(0.0, (1.0 - fill_probability) * 0.02)
        uncertainty_penalty = model_error_p95

        priors[key] = LearnedExecutionPrior(
            bucket_key=key,
            observations=observations,
            expected_fill_probability=min(1.0, max(0.0, fill_probability)),
            slippage_p95_penalty=max(0.0, slippage_p95),
            post_fill_alpha_decay_penalty=max(0.0, alpha_decay_p95),
            uncertainty_penalty=max(0.0, uncertainty_penalty),
            execution_penalty=execution_penalty,
            model_error_score=min(1.0, max(0.0, model_error_p95)),
        )

    return priors


def adjustments_for_candidate(
    candidate: Candidate,
    priors: dict[str, LearnedExecutionPrior] | None,
) -> ExecutionAdjustments:
    if not priors:
        return ExecutionAdjustments()

    key = _bucket_key_from_candidate(candidate)
    prior = priors.get(key) or priors.get(str(candidate.ticker or "").strip().upper()) or priors.get("global")
    if prior is None:
        return ExecutionAdjustments()

    # Shrink learning impact when sample is small.
    blend = min(0.8, prior.observations / (prior.observations + 20.0))
    blended_fill_probability = (1.0 - blend) * float(candidate.fill_probability) + blend * prior.expected_fill_probability

    return ExecutionAdjustments(
        expected_fill_probability=blended_fill_probability,
        slippage_p95_penalty=prior.slippage_p95_penalty,
        post_fill_alpha_decay_penalty=prior.post_fill_alpha_decay_penalty,
        uncertainty_penalty=prior.uncertainty_penalty,
        execution_penalty=prior.execution_penalty,
        model_error_score=prior.model_error_score,
    )
