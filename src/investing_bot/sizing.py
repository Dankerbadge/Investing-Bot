from __future__ import annotations


def full_kelly_fraction(*, win_probability: float, payoff_multiple: float, loss_multiple: float = 1.0) -> float:
    if not (0.0 <= win_probability <= 1.0):
        raise ValueError("win_probability must be in [0, 1]")
    if payoff_multiple <= 0:
        raise ValueError("payoff_multiple must be positive")
    if loss_multiple <= 0:
        raise ValueError("loss_multiple must be positive")

    p = float(win_probability)
    q = 1.0 - p
    b = float(payoff_multiple)
    l = float(loss_multiple)

    return (p * b - q * l) / b


def fractional_kelly_fraction(
    *,
    kelly_full: float,
    kelly_fraction: float = 0.25,
    min_fraction: float = 0.0,
    max_fraction: float = 0.10,
) -> float:
    if kelly_fraction < 0:
        raise ValueError("kelly_fraction must be non-negative")
    if max_fraction < min_fraction:
        raise ValueError("max_fraction must be >= min_fraction")

    raw = max(0.0, kelly_full) * kelly_fraction
    clipped = min(max(raw, min_fraction), max_fraction)
    return clipped


def notional_from_fraction(*, bankroll: float, fraction: float) -> float:
    if bankroll <= 0 or fraction <= 0:
        return 0.0
    return round(float(bankroll) * float(fraction), 2)
