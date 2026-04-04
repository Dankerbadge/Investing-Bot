from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


_FEATURE_SOURCE_ALLOWED = {"sec", "fred", "cboe", "schwab", "archive", "composite"}


def _normalize_symbol(value: Any) -> str:
    return str(value or "").strip().upper()


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


def _parse_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _iso_utc(value: Any) -> str:
    dt = _parse_dt(value)
    if dt is None:
        dt = datetime.now(timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def _normalize_source(value: Any) -> str:
    source = str(value or "").strip().lower()
    if source in _FEATURE_SOURCE_ALLOWED:
        return source
    return "composite"


@dataclass(frozen=True)
class FeatureSnapshot:
    symbol: str
    captured_at: str
    source: str
    feature_version: str
    features: dict[str, Any] = field(default_factory=dict)

    def as_row(
        self,
        *,
        as_of: datetime | None = None,
        max_age_seconds: float | None = None,
    ) -> dict[str, Any]:
        row: dict[str, Any] = {
            "symbol": self.symbol,
            "captured_at": self.captured_at,
            "feature_source": self.source,
            "feature_version": self.feature_version,
            **self.features,
        }

        captured_dt = _parse_dt(self.captured_at)
        if captured_dt is not None:
            ref_time = as_of or datetime.now(timezone.utc)
            age_seconds = max(0.0, (ref_time - captured_dt).total_seconds())
            row["feature_age_seconds"] = round(age_seconds, 6)
            if max_age_seconds is not None:
                row["feature_is_stale"] = bool(age_seconds > max(0.0, float(max_age_seconds)))
        return row


@dataclass
class FeatureStore:
    snapshots_by_symbol: dict[str, list[FeatureSnapshot]] = field(default_factory=dict)

    def add_snapshot(
        self,
        *,
        symbol: str,
        features: dict[str, Any],
        captured_at: str | datetime | None = None,
        source: str = "composite",
        feature_version: str = "v1",
    ) -> FeatureSnapshot:
        key = _normalize_symbol(symbol)
        if not key:
            raise ValueError("symbol is required")

        snapshot = FeatureSnapshot(
            symbol=key,
            captured_at=_iso_utc(captured_at),
            source=_normalize_source(source),
            feature_version=str(feature_version or "v1").strip() or "v1",
            features=dict(features or {}),
        )

        rows = self.snapshots_by_symbol.setdefault(key, [])
        rows.append(snapshot)
        rows.sort(key=lambda item: item.captured_at)
        return snapshot

    def bulk_add(
        self,
        rows: list[dict[str, Any]],
        *,
        default_source: str = "composite",
        default_feature_version: str = "v1",
    ) -> int:
        added = 0
        for row in rows:
            if not isinstance(row, dict):
                continue
            symbol = _normalize_symbol(row.get("symbol") or row.get("ticker"))
            if not symbol:
                continue
            captured_at = row.get("captured_at") or row.get("recorded_at")
            source = row.get("feature_source") or row.get("source") or default_source
            version = row.get("feature_version") or default_feature_version
            features = {
                key: value
                for key, value in row.items()
                if key not in {"symbol", "ticker", "captured_at", "recorded_at", "feature_source", "source", "feature_version"}
            }
            self.add_snapshot(
                symbol=symbol,
                features=features,
                captured_at=captured_at,
                source=str(source),
                feature_version=str(version),
            )
            added += 1
        return added

    def latest_snapshot(
        self,
        symbol: str,
        *,
        as_of: str | datetime | None = None,
    ) -> FeatureSnapshot | None:
        key = _normalize_symbol(symbol)
        if not key:
            return None
        snapshots = self.snapshots_by_symbol.get(key)
        if not snapshots:
            return None

        as_of_dt = _parse_dt(as_of)
        if as_of_dt is None:
            return snapshots[-1]

        latest: FeatureSnapshot | None = None
        for snapshot in snapshots:
            snap_dt = _parse_dt(snapshot.captured_at)
            if snap_dt is None:
                continue
            if snap_dt <= as_of_dt:
                latest = snapshot
            else:
                break
        return latest

    def get_feature_row(
        self,
        symbol: str,
        *,
        as_of: str | datetime | None = None,
        max_age_seconds: float | None = None,
    ) -> dict[str, Any] | None:
        snapshot = self.latest_snapshot(symbol, as_of=as_of)
        if snapshot is None:
            return None
        as_of_dt = _parse_dt(as_of)
        return snapshot.as_row(as_of=as_of_dt, max_age_seconds=max_age_seconds)

    def build_feature_rows(
        self,
        *,
        symbols: list[str] | tuple[str, ...] | None = None,
        as_of: str | datetime | None = None,
        max_age_seconds: float | None = 900.0,
    ) -> list[dict[str, Any]]:
        if symbols is None:
            keys = sorted(self.snapshots_by_symbol.keys())
        else:
            keys = sorted({_normalize_symbol(symbol) for symbol in symbols if _normalize_symbol(symbol)})

        rows: list[dict[str, Any]] = []
        for symbol in keys:
            row = self.get_feature_row(symbol, as_of=as_of, max_age_seconds=max_age_seconds)
            if row is None:
                continue
            rows.append(row)
        return rows

    def prune_before(self, cutoff: str | datetime) -> int:
        cutoff_dt = _parse_dt(cutoff)
        if cutoff_dt is None:
            return 0
        removed = 0
        for symbol, snapshots in list(self.snapshots_by_symbol.items()):
            kept: list[FeatureSnapshot] = []
            for snapshot in snapshots:
                snap_dt = _parse_dt(snapshot.captured_at)
                if snap_dt is None or snap_dt >= cutoff_dt:
                    kept.append(snapshot)
                else:
                    removed += 1
            if kept:
                self.snapshots_by_symbol[symbol] = kept
            else:
                self.snapshots_by_symbol.pop(symbol, None)
        return removed

    @classmethod
    def from_rows(
        cls,
        rows: list[dict[str, Any]],
        *,
        default_source: str = "composite",
        default_feature_version: str = "v1",
    ) -> FeatureStore:
        store = cls()
        store.bulk_add(
            rows,
            default_source=default_source,
            default_feature_version=default_feature_version,
        )
        return store


def build_feature_payload(
    *,
    sec_context: dict[str, Any] | None = None,
    macro_context: dict[str, Any] | None = None,
    crowding_context: dict[str, Any] | None = None,
    options_state: dict[str, Any] | None = None,
    equity_minute_context: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for block in (sec_context, macro_context, crowding_context, options_state, equity_minute_context, extra):
        if isinstance(block, dict):
            payload.update(block)

    if "liquidity_score" not in payload:
        depth = max(0.0, _as_float(payload.get("book_depth_contracts"), 0.0))
        spread = max(0.0, _as_float(payload.get("spread_cost"), 0.02))
        depth_component = min(1.0, depth / 200.0)
        spread_component = max(0.0, 1.0 - min(1.0, spread / 0.10))
        payload["liquidity_score"] = round((0.6 * depth_component) + (0.4 * spread_component), 6)

    if "quote_age_seconds" not in payload:
        payload["quote_age_seconds"] = round(max(0.0, _as_float(payload.get("quote_age_ms"), 0.0) / 1000.0), 6)

    if "put_call_ratio" not in payload and "cboe_put_call_ratio" in payload:
        payload["put_call_ratio"] = _as_float(payload.get("cboe_put_call_ratio"), 0.0)

    return payload
