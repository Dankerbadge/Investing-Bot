from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .fault_injection import (
    inject_delayed_quotes,
    inject_order_change_race,
    inject_request_burst,
    inject_stream_gap,
)


@dataclass(frozen=True)
class ChaosScenario:
    name: str
    description: str
    mutate: Callable[[list[dict[str, Any]]], list[dict[str, Any]]]


@dataclass(frozen=True)
class ChaosScenarioResult:
    scenario: str
    passed: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ChaosRunResult:
    total_scenarios: int
    passed_scenarios: int
    failed_scenarios: int
    results: tuple[ChaosScenarioResult, ...]


def default_fault_scenarios() -> tuple[ChaosScenario, ...]:
    return (
        ChaosScenario(
            name="stream_gap",
            description="Injects a stream gap after first event.",
            mutate=lambda rows: inject_stream_gap(rows, gap_seconds=8.0, at_index=0),
        ),
        ChaosScenario(
            name="delayed_quotes",
            description="Marks all quotes as delayed.",
            mutate=lambda rows: inject_delayed_quotes(rows, start_index=0, every_n=1),
        ),
        ChaosScenario(
            name="order_change_race",
            description="Adds simultaneous cancel/fill race events.",
            mutate=lambda rows: inject_order_change_race(rows, order_id="race-order"),
        ),
        ChaosScenario(
            name="request_burst",
            description="Injects order request burst to simulate throttle pressure.",
            mutate=lambda rows: inject_request_burst(rows, burst_count=150),
        ),
    )


def run_chaos_suite(
    *,
    base_rows: list[dict[str, Any]],
    validator: Callable[[list[dict[str, Any]]], tuple[bool, list[str] | tuple[str, ...] | None]],
    scenarios: tuple[ChaosScenario, ...] | list[ChaosScenario] | None = None,
) -> ChaosRunResult:
    scenario_rows = tuple(scenarios or default_fault_scenarios())
    results: list[ChaosScenarioResult] = []

    for scenario in scenario_rows:
        try:
            mutated = scenario.mutate([dict(row) for row in base_rows if isinstance(row, dict)])
            passed, reasons_raw = validator(mutated)
            reasons = tuple(str(reason) for reason in (reasons_raw or []) if str(reason))
            results.append(
                ChaosScenarioResult(
                    scenario=scenario.name,
                    passed=bool(passed),
                    reasons=reasons,
                )
            )
        except Exception as exc:  # pragma: no cover
            results.append(
                ChaosScenarioResult(
                    scenario=scenario.name,
                    passed=False,
                    reasons=(f"exception:{exc.__class__.__name__}",),
                )
            )

    passed = sum(1 for row in results if row.passed)
    return ChaosRunResult(
        total_scenarios=len(results),
        passed_scenarios=passed,
        failed_scenarios=len(results) - passed,
        results=tuple(results),
    )
