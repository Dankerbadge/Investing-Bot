from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class StreamAction:
    stream: str
    action: str
    symbols: tuple[str, ...]


@dataclass
class StreamSubscriptionManager:
    """
    Serial stream-subscription reconciler.
    Keeps one desired set per stream and emits deterministic subscribe/unsubscribe actions.
    """

    current: dict[str, set[str]] = field(default_factory=dict)
    desired: dict[str, set[str]] = field(default_factory=dict)
    generation: int = 0

    def set_desired(self, stream: str, symbols: list[str] | tuple[str, ...] | set[str]) -> None:
        stream_key = str(stream or "").strip().lower()
        if not stream_key:
            return
        cleaned = {str(symbol or "").strip().upper() for symbol in symbols if str(symbol or "").strip()}
        self.desired[stream_key] = cleaned

    def get_current(self, stream: str) -> tuple[str, ...]:
        stream_key = str(stream or "").strip().lower()
        return tuple(sorted(self.current.get(stream_key, set())))

    def reconcile(self, stream: str) -> list[StreamAction]:
        stream_key = str(stream or "").strip().lower()
        if not stream_key:
            return []

        current = self.current.get(stream_key, set())
        desired = self.desired.get(stream_key, set())

        to_unsubscribe = tuple(sorted(symbol for symbol in current if symbol not in desired))
        to_subscribe = tuple(sorted(symbol for symbol in desired if symbol not in current))

        actions: list[StreamAction] = []
        if to_unsubscribe:
            actions.append(StreamAction(stream=stream_key, action="unsubscribe", symbols=to_unsubscribe))
        if to_subscribe:
            actions.append(StreamAction(stream=stream_key, action="subscribe", symbols=to_subscribe))

        # Apply immediately so repeated reconcile calls are stable and idempotent.
        self.current[stream_key] = set(desired)
        self.generation += 1
        return actions

    def reconcile_all(self) -> list[StreamAction]:
        actions: list[StreamAction] = []
        for stream in sorted(set(self.current) | set(self.desired)):
            actions.extend(self.reconcile(stream))
        return actions
