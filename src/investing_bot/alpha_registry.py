from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .models import Candidate


@dataclass(frozen=True)
class AlphaFamilySpec:
    name: str
    description: str
    risk_class: str
    allowed_structures: tuple[str, ...]
    required_features: tuple[str, ...]
    expected_holding_minutes: float
    default_stage: str = "probe"


@dataclass(frozen=True)
class AlphaSignal:
    family: str
    symbol: str
    underlying: str
    event_key: str
    side: str
    expected_edge: float
    confidence: float
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


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


def _as_int(value: Any, default: int = 0) -> int:
    return int(round(_as_float(value, float(default))))


def _normalize_symbol(value: Any) -> str:
    return str(value or "").strip().upper()


SignalGenerator = Callable[[list[dict[str, Any]]], list[AlphaSignal]]


@dataclass
class AlphaRegistry:
    specs: dict[str, AlphaFamilySpec] = field(default_factory=dict)
    generators: dict[str, SignalGenerator] = field(default_factory=dict)

    def register(self, spec: AlphaFamilySpec, generator: SignalGenerator) -> None:
        key = str(spec.name or "").strip().lower()
        if not key:
            return
        self.specs[key] = spec
        self.generators[key] = generator

    def available_families(self) -> tuple[str, ...]:
        return tuple(sorted(self.specs.keys()))

    def get_spec(self, family: str) -> AlphaFamilySpec | None:
        key = str(family or "").strip().lower()
        return self.specs.get(key)

    def evaluate_family(self, family: str, feature_rows: list[dict[str, Any]]) -> list[AlphaSignal]:
        key = str(family or "").strip().lower()
        generator = self.generators.get(key)
        if generator is None:
            return []
        rows = [row for row in feature_rows if isinstance(row, dict)]
        return generator(rows)

    def _resolve_enabled_families(
        self,
        enabled_families: tuple[str, ...] | list[str] | None,
    ) -> tuple[str, ...]:
        if enabled_families:
            return tuple(dict.fromkeys(str(name).strip().lower() for name in enabled_families if str(name).strip()))
        return self.available_families()

    @staticmethod
    def _normalize_evidence_map(live_evidence_by_family: dict[str, int] | None) -> dict[str, int]:
        return {
            str(name or "").strip().lower(): int(value)
            for name, value in (live_evidence_by_family or {}).items()
            if str(name or "").strip()
        }

    def evaluate_shadow_all(
        self,
        feature_rows: list[dict[str, Any]],
        enabled_families: tuple[str, ...] | list[str] | None = None,
    ) -> list[AlphaSignal]:
        families = self._resolve_enabled_families(enabled_families)
        signals: list[AlphaSignal] = []
        for family in families:
            signals.extend(self.evaluate_family(family, feature_rows))
        return sorted(signals, key=lambda row: (row.score, row.expected_edge, row.confidence), reverse=True)

    def evaluate_capital_eligible(
        self,
        feature_rows: list[dict[str, Any]],
        enabled_families: tuple[str, ...] | list[str] | None = None,
        live_evidence_by_family: dict[str, int] | None = None,
        min_broker_confirmed_live_samples: int = 30,
    ) -> list[AlphaSignal]:
        families = self._resolve_enabled_families(enabled_families)
        evidence_map = self._normalize_evidence_map(live_evidence_by_family)
        minimum = max(0, int(min_broker_confirmed_live_samples))

        signals: list[AlphaSignal] = []
        for family in families:
            if minimum > 0 and evidence_map.get(family, 0) < minimum:
                continue
            signals.extend(self.evaluate_family(family, feature_rows))
        return sorted(signals, key=lambda row: (row.score, row.expected_edge, row.confidence), reverse=True)

    def evaluate_all(
        self,
        feature_rows: list[dict[str, Any]],
        enabled_families: tuple[str, ...] | list[str] | None = None,
        live_evidence_by_family: dict[str, int] | None = None,
        min_broker_confirmed_live_samples: int = 0,
    ) -> list[AlphaSignal]:
        # Backward-compatible entrypoint:
        # - no evidence threshold => shadow lane
        # - evidence threshold > 0 => capital-eligible lane
        if int(min_broker_confirmed_live_samples) > 0:
            return self.evaluate_capital_eligible(
                feature_rows,
                enabled_families=enabled_families,
                live_evidence_by_family=live_evidence_by_family,
                min_broker_confirmed_live_samples=min_broker_confirmed_live_samples,
            )
        return self.evaluate_shadow_all(feature_rows, enabled_families=enabled_families)

    def signals_to_candidates(
        self,
        signals: list[AlphaSignal],
        feature_index: dict[str, dict[str, Any]] | None = None,
    ) -> list[Candidate]:
        index = {str(k).upper(): v for k, v in (feature_index or {}).items() if isinstance(v, dict)}
        candidates: list[Candidate] = []
        for signal in signals:
            symbol = _normalize_symbol(signal.symbol)
            row = index.get(symbol, {})
            quote_age_seconds = _as_float(row.get("quote_age_seconds"), 1.0)
            spread_cost = _as_float(row.get("spread_cost"), 0.01)
            hedge_cost = _as_float(row.get("hedge_cost"), 0.005)
            stale_quote_penalty = _as_float(row.get("stale_quote_penalty"), 0.001)
            event_gap_penalty = _as_float(row.get("event_gap_penalty"), 0.001)
            capital_lockup_penalty = _as_float(row.get("capital_lockup_penalty"), 0.001)
            fill_probability = max(0.0, min(1.0, _as_float(row.get("fill_probability"), 0.65)))
            convergence_probability = max(0.0, min(1.0, _as_float(row.get("convergence_probability"), 0.60)))
            reference_price = max(0.01, _as_float(row.get("reference_price"), 1.0))
            payoff_multiple = max(0.1, _as_float(row.get("payoff_multiple"), 1.2))
            loss_multiple = max(0.1, _as_float(row.get("loss_multiple"), 1.0))
            book_depth = max(0, _as_int(row.get("book_depth_contracts"), 50))
            event_key = str(signal.event_key or row.get("event_key") or f"{signal.family}:{symbol}").strip()

            metadata = {
                "alpha_family": signal.family,
                "alpha_score": signal.score,
                "expected_holding_minutes": _as_float(signal.metadata.get("expected_holding_minutes"), 60.0),
                **{k: v for k, v in row.items() if k not in {"symbol", "ticker", "underlying"}},
                **signal.metadata,
            }

            candidates.append(
                Candidate(
                    ticker=symbol,
                    underlying=_normalize_symbol(signal.underlying or symbol),
                    event_key=event_key,
                    strategy_family=signal.family,
                    side=str(signal.side or "buy").strip().lower() or "buy",
                    reference_price=reference_price,
                    surface_residual=signal.expected_edge,
                    convergence_probability=convergence_probability,
                    fill_probability=fill_probability,
                    spread_cost=spread_cost,
                    hedge_cost=hedge_cost,
                    stale_quote_penalty=stale_quote_penalty,
                    event_gap_penalty=event_gap_penalty,
                    capital_lockup_penalty=capital_lockup_penalty,
                    confidence=max(0.0, min(1.0, signal.confidence)),
                    book_depth_contracts=book_depth,
                    quote_age_seconds=quote_age_seconds,
                    payoff_multiple=payoff_multiple,
                    loss_multiple=loss_multiple,
                    metadata=metadata,
                )
            )
        return candidates


def build_default_alpha_registry() -> AlphaRegistry:
    from .alpha_families.filing_vol import filing_vol_family
    from .alpha_families.open_drive import open_drive_family
    from .alpha_families.post_event_iv import post_event_iv_family

    registry = AlphaRegistry()
    for spec, generator in (filing_vol_family(), post_event_iv_family(), open_drive_family()):
        registry.register(spec, generator)
    return registry
