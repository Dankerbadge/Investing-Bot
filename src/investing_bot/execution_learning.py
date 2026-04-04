from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
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


def _normalize_source(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"live", "paper", "ghost"}:
        return normalized
    return "live"


def _weighted_percentile(samples: list[tuple[float, float]], q: float) -> float:
    if not samples:
        return 0.0
    clamped_q = min(1.0, max(0.0, q))
    normalized: list[tuple[float, float]] = []
    for value, weight in samples:
        v = float(value)
        w = max(0.0, float(weight))
        if w <= 0.0:
            continue
        normalized.append((v, w))
    if not normalized:
        return 0.0
    normalized.sort(key=lambda item: item[0])
    total_weight = sum(weight for _, weight in normalized)
    if total_weight <= 0:
        return 0.0
    threshold = total_weight * clamped_q
    cumulative = 0.0
    for value, weight in normalized:
        cumulative += weight
        if cumulative >= threshold:
            return value
    return normalized[-1][0]


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


def _read_stream_records(
    archive_root: Path,
    stream: str,
    allowed_sources: set[str],
) -> list[dict[str, Any]]:
    stream_dir = archive_root / stream
    if not stream_dir.exists() or not stream_dir.is_dir():
        return []

    records: list[dict[str, Any]] = []

    # New layout: stream/source/YYYY-MM-DD.jsonl
    for source in sorted(allowed_sources):
        source_dir = stream_dir / source
        if not source_dir.exists() or not source_dir.is_dir():
            continue
        for path in sorted(source_dir.glob("*.jsonl")):
            for row in _read_jsonl(path):
                row.setdefault("data_source", source)
                records.append(row)

    # Backward-compatible layout: stream/YYYY-MM-DD.jsonl with optional data_source column.
    for path in sorted(stream_dir.glob("*.jsonl")):
        for row in _read_jsonl(path):
            source = _normalize_source(row.get("data_source"))
            if source in allowed_sources:
                row.setdefault("data_source", source)
                records.append(row)

    return records


def _bucket_fields(row: dict[str, Any]) -> tuple[str, str, str, str, str, str, str, str]:
    strategy = str(row.get("strategy_family") or "unknown").strip().lower() or "unknown"
    ticker = str(row.get("ticker") or "").strip().upper()

    spread = _safe_float(row.get("spread_cost") or row.get("spread_dollars"), default=0.0)
    if spread <= 0.01:
        liquidity_bucket = "liq_tight"
    elif spread <= 0.03:
        liquidity_bucket = "liq_medium"
    else:
        liquidity_bucket = "liq_wide"

    dte = _safe_float(row.get("dte_days"), default=-1.0)
    if dte < 0:
        dte_bucket = "dte_unknown"
    elif dte <= 7:
        dte_bucket = "dte_0_7"
    elif dte <= 30:
        dte_bucket = "dte_8_30"
    else:
        dte_bucket = "dte_31_plus"

    moneyness = abs(_safe_float(row.get("moneyness") or row.get("delta_distance"), default=0.0))
    if moneyness <= 0.05:
        moneyness_bucket = "money_atm"
    elif moneyness <= 0.2:
        moneyness_bucket = "money_near"
    else:
        moneyness_bucket = "money_far"

    captured = str(row.get("captured_at") or row.get("recorded_at") or "").strip()
    hour_bucket = "tod_unknown"
    if captured:
        try:
            hour = datetime.fromisoformat(captured.replace("Z", "+00:00")).hour
            if hour < 11:
                hour_bucket = "tod_open"
            elif hour < 14:
                hour_bucket = "tod_mid"
            else:
                hour_bucket = "tod_late"
        except ValueError:
            pass

    event_bucket = "event" if bool(row.get("is_event") or row.get("event_day")) else "non_event"
    style_bucket = str(row.get("execution_style") or row.get("order_style") or "unknown").strip().lower() or "unknown"

    return strategy, ticker, liquidity_bucket, dte_bucket, moneyness_bucket, hour_bucket, event_bucket, style_bucket


def _bucket_key_candidates(row: dict[str, Any]) -> list[str]:
    explicit = str(row.get("execution_bucket") or "").strip()
    if explicit:
        return [explicit, "global"]

    strategy, ticker, liq, dte, money, tod, event_bucket, style = _bucket_fields(row)
    keys = [
        f"{strategy}|{liq}|{dte}|{money}|{tod}|{event_bucket}|{style}",
        f"{strategy}|{liq}|{event_bucket}",
        f"{strategy}|{event_bucket}",
    ]
    if ticker:
        keys.append(ticker)
    keys.append("global")
    # Preserve order and uniqueness.
    deduped: list[str] = []
    for key in keys:
        if key not in deduped:
            deduped.append(key)
    return deduped


def _bucket_key_candidates_for_candidate(candidate: Candidate) -> list[str]:
    explicit = str(candidate.metadata.get("execution_bucket") or "").strip()
    if explicit:
        return [explicit, "global"]

    synthetic_row = {
        "strategy_family": candidate.strategy_family,
        "ticker": candidate.ticker,
        "spread_cost": candidate.spread_cost,
        "dte_days": candidate.metadata.get("dte_days"),
        "moneyness": candidate.metadata.get("moneyness"),
        "captured_at": candidate.metadata.get("captured_at"),
        "is_event": candidate.metadata.get("is_event"),
        "execution_style": candidate.metadata.get("execution_style"),
    }
    return _bucket_key_candidates(synthetic_row)


def _sample_quality_weight(row: dict[str, Any]) -> float:
    source = _normalize_source(row.get("data_source"))
    source_weight = {
        "live": 1.0,
        "paper": 0.70,
        "ghost": 0.50,
    }.get(source, 0.70)

    quote_score = _safe_float(row.get("quote_reliability_score"), default=-1.0)
    if quote_score < 0.0:
        quote_tier = str(row.get("quote_quality_tier") or "").strip().lower()
        quote_score = {
            "realtime": 1.0,
            "unknown": 0.75,
            "stale": 0.40,
            "delayed": 0.25,
        }.get(quote_tier, 0.75)
    quote_score = min(1.0, max(0.1, quote_score))

    book_score = _safe_float(row.get("book_reliability_score"), default=-1.0)
    if book_score < 0.0:
        book_tier = str(row.get("book_reliability_tier") or "").strip().lower()
        book_score = {
            "high": 0.95,
            "medium": 0.75,
            "low": 0.50,
        }.get(book_tier, 0.75)
    book_score = min(1.0, max(0.2, book_score))

    weight = source_weight * quote_score * book_score
    return min(1.0, max(0.05, weight))


def _blend(specific: float, parent: float, observations: int, half_life: float = 25.0) -> float:
    weight = max(0.0, min(1.0, observations / (observations + half_life)))
    return weight * specific + (1.0 - weight) * parent


def learn_execution_priors(
    archive_root: Path,
    min_observations: int = 3,
    allowed_sources: tuple[str, ...] = ("live",),
) -> dict[str, LearnedExecutionPrior]:
    allowed = {_normalize_source(value) for value in allowed_sources if str(value).strip()}
    if not allowed:
        allowed = {"live"}

    orders = _read_stream_records(archive_root, "orders", allowed)
    fills = _read_stream_records(archive_root, "fills", allowed)
    signals = _read_stream_records(archive_root, "signals", allowed)

    attempted_by_bucket: dict[str, float] = {}
    filled_by_bucket: dict[str, float] = {}
    slippage_by_bucket: dict[str, list[tuple[float, float]]] = {}
    alpha_decay_by_bucket: dict[str, list[tuple[float, float]]] = {}
    model_error_by_bucket: dict[str, list[tuple[float, float]]] = {}

    for row in orders:
        keys = _bucket_key_candidates(row)
        qty = max(1.0, _safe_float(row.get("order_quantity") or row.get("requested_quantity") or 1.0, default=1.0))
        quality_weight = _sample_quality_weight(row)
        for key in keys:
            attempted_by_bucket[key] = attempted_by_bucket.get(key, 0.0) + (qty * quality_weight)

    for row in fills:
        keys = _bucket_key_candidates(row)
        quality_weight = _sample_quality_weight(row)
        fill_qty = max(0.0, _safe_float(row.get("fill_quantity") or row.get("filled_quantity") or 0.0, default=0.0))
        slippage = abs(_safe_float(row.get("slippage_dollars") or row.get("fill_vs_mid_dollars"), default=0.0))
        decay = abs(
            _safe_float(
                row.get("post_fill_alpha_decay")
                or row.get("alpha_decay_2m")
                or row.get("post_fill_drift_2m"),
                default=0.0,
            )
        )

        for key in keys:
            if fill_qty > 0:
                filled_by_bucket[key] = filled_by_bucket.get(key, 0.0) + (fill_qty * quality_weight)
            if slippage > 0:
                slippage_by_bucket.setdefault(key, []).append((slippage, quality_weight))
            if decay > 0:
                alpha_decay_by_bucket.setdefault(key, []).append((decay, quality_weight))

    for row in signals:
        keys = _bucket_key_candidates(row)
        quality_weight = _sample_quality_weight(row)
        predicted = _safe_float(row.get("predicted_net_edge") or row.get("expected_net_edge"), default=0.0)
        realized = _safe_float(row.get("realized_net_edge"), default=0.0)
        if predicted != 0.0 or realized != 0.0:
            err = abs(predicted - realized)
            for key in keys:
                model_error_by_bucket.setdefault(key, []).append((err, quality_weight))

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
        slippage_samples = slippage_by_bucket.get(key, [])
        alpha_decay_samples = alpha_decay_by_bucket.get(key, [])
        model_error_samples = model_error_by_bucket.get(key, [])
        weighted_slippage_obs = sum(weight for _, weight in slippage_samples)
        weighted_alpha_decay_obs = sum(weight for _, weight in alpha_decay_samples)
        weighted_model_error_obs = sum(weight for _, weight in model_error_samples)
        observations = int(
            round(max(attempts, weighted_slippage_obs, weighted_alpha_decay_obs, weighted_model_error_obs))
        )
        if observations < min_observations:
            continue

        fill_probability = (fills_qty + 1.0) / (attempts + 2.0) if attempts > 0 else 0.5

        slippage_p95 = _weighted_percentile(slippage_samples, 0.95)
        alpha_decay_p95 = _weighted_percentile(alpha_decay_samples, 0.95)
        model_error_p95 = _weighted_percentile(model_error_samples, 0.95)

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

    keys = _bucket_key_candidates_for_candidate(candidate)
    selected = next((priors.get(key) for key in keys if key in priors), None)
    if selected is None:
        return ExecutionAdjustments()

    # Hierarchical shrinkage: back off to broader/global priors when sparse.
    parent = None
    for key in keys[1:]:
        if key in priors:
            parent = priors[key]
            break

    expected_fill_probability = selected.expected_fill_probability
    slippage_p95_penalty = selected.slippage_p95_penalty
    alpha_decay_penalty = selected.post_fill_alpha_decay_penalty
    uncertainty_penalty = selected.uncertainty_penalty
    execution_penalty = selected.execution_penalty
    model_error_score = selected.model_error_score

    if parent is not None and parent.bucket_key != selected.bucket_key:
        expected_fill_probability = _blend(
            selected.expected_fill_probability,
            parent.expected_fill_probability,
            selected.observations,
        )
        slippage_p95_penalty = _blend(
            selected.slippage_p95_penalty,
            parent.slippage_p95_penalty,
            selected.observations,
        )
        alpha_decay_penalty = _blend(
            selected.post_fill_alpha_decay_penalty,
            parent.post_fill_alpha_decay_penalty,
            selected.observations,
        )
        uncertainty_penalty = _blend(
            selected.uncertainty_penalty,
            parent.uncertainty_penalty,
            selected.observations,
        )
        execution_penalty = _blend(
            selected.execution_penalty,
            parent.execution_penalty,
            selected.observations,
        )
        model_error_score = _blend(
            selected.model_error_score,
            parent.model_error_score,
            selected.observations,
        )

    blend = min(0.8, selected.observations / (selected.observations + 20.0))
    blended_fill_probability = (1.0 - blend) * float(candidate.fill_probability) + blend * expected_fill_probability

    return ExecutionAdjustments(
        expected_fill_probability=blended_fill_probability,
        slippage_p95_penalty=max(0.0, slippage_p95_penalty),
        post_fill_alpha_decay_penalty=max(0.0, alpha_decay_penalty),
        uncertainty_penalty=max(0.0, uncertainty_penalty),
        execution_penalty=max(0.0, execution_penalty),
        model_error_score=min(1.0, max(0.0, model_error_score)),
    )
