from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .preflight import PreflightResult
from .stream_manager import StreamAction, StreamSubscriptionManager


@dataclass(frozen=True)
class SessionWindows:
    warmup_start_hhmm: str = "09:20"
    active_start_hhmm: str = "09:35"
    derisk_start_hhmm: str = "15:30"
    close_hhmm: str = "16:00"


@dataclass(frozen=True)
class SessionPlan:
    phase: str
    can_open_new_entries: bool
    stream_actions: tuple[StreamAction, ...]
    reasons: tuple[str, ...]


def _hhmm_to_minutes(value: str, default: int) -> int:
    text = str(value or "").strip()
    if not text or ":" not in text:
        return default
    hh, mm = text.split(":", 1)
    try:
        return max(0, min(23, int(hh))) * 60 + max(0, min(59, int(mm)))
    except ValueError:
        return default


def determine_session_phase(
    now_et: datetime,
    *,
    windows: SessionWindows | None = None,
) -> str:
    cfg = windows or SessionWindows()
    current = now_et.hour * 60 + now_et.minute

    warmup_start = _hhmm_to_minutes(cfg.warmup_start_hhmm, 9 * 60 + 20)
    active_start = _hhmm_to_minutes(cfg.active_start_hhmm, 9 * 60 + 35)
    derisk_start = _hhmm_to_minutes(cfg.derisk_start_hhmm, 15 * 60 + 30)
    close = _hhmm_to_minutes(cfg.close_hhmm, 16 * 60)

    if current < warmup_start:
        return "pre_open"
    if current < active_start:
        return "warmup"
    if current < derisk_start:
        return "active"
    if current < close:
        return "de_risk"
    return "closed"


@dataclass
class SessionOrchestrator:
    stream_manager: StreamSubscriptionManager
    windows: SessionWindows = SessionWindows()

    def plan(
        self,
        *,
        now_et: datetime,
        desired_symbols_by_stream: dict[str, list[str] | tuple[str, ...] | set[str]],
        preflight: PreflightResult,
        force_pause: bool = False,
    ) -> SessionPlan:
        phase = determine_session_phase(now_et, windows=self.windows)

        for stream, symbols in desired_symbols_by_stream.items():
            self.stream_manager.set_desired(stream, symbols)
        actions = tuple(self.stream_manager.reconcile_all())

        reasons: list[str] = []
        if force_pause:
            reasons.append("manual_pause")
        reasons.extend(list(preflight.hard_blocks))

        can_open = True
        if phase in {"pre_open", "closed"}:
            can_open = False
            reasons.append("session_phase_block")
        elif phase == "de_risk":
            can_open = False
            reasons.append("de_risk_phase")

        if not preflight.can_trade:
            can_open = False

        if force_pause:
            can_open = False

        return SessionPlan(
            phase=phase,
            can_open_new_entries=can_open,
            stream_actions=actions,
            reasons=tuple(sorted(set(reasons))),
        )
