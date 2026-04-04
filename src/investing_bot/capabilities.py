from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class CapabilityRecord:
    name: str
    verified: bool
    verified_at: str
    notes: str = ""


@dataclass
class CapabilityRegistry:
    records: dict[str, CapabilityRecord] = field(default_factory=dict)

    def set_verified(self, name: str, verified: bool, notes: str = "") -> None:
        key = str(name or "").strip().lower()
        if not key:
            return
        self.records[key] = CapabilityRecord(
            name=key,
            verified=bool(verified),
            verified_at=datetime.now(timezone.utc).isoformat(),
            notes=str(notes or "").strip(),
        )

    def is_verified(self, name: str) -> bool:
        key = str(name or "").strip().lower()
        record = self.records.get(key)
        return bool(record and record.verified)


def action_is_allowed(
    *,
    action: str,
    registry: CapabilityRegistry | None,
    is_realtime_quote: bool = True,
    is_stock_etf_option: bool = True,
    in_regular_hours: bool = True,
) -> bool:
    action_norm = str(action or "").strip().lower()
    if action_norm == "native_walk_limit":
        if not is_realtime_quote or not is_stock_etf_option or not in_regular_hours:
            return False
        if registry is None:
            return False
        return registry.is_verified("native_walk_limit_api")
    return True
