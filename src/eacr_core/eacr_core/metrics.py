"""Evaluation metrics for the phase-three EACR experiments."""

from __future__ import annotations

import math
from typing import Iterable, Mapping, Sequence


def _keys(*distributions: Mapping[str, float]) -> tuple[str, ...]:
    return tuple(sorted({key for distribution in distributions for key in distribution}))


def policy_kl(reference: Mapping[str, float], candidate: Mapping[str, float], floor: float = 1e-12) -> float:
    """KL(reference || candidate), with a floor for unseen actions."""
    return sum(
        float(reference.get(key, 0.0))
        * math.log(max(float(reference.get(key, 0.0)), floor) / max(float(candidate.get(key, 0.0)), floor))
        for key in _keys(reference, candidate)
        if float(reference.get(key, 0.0)) > 0.0
    )


def outcome_nll(probability: float, observed: bool, floor: float = 1e-12) -> float:
    """Binary negative log likelihood for a verified recovery outcome."""
    p = min(1.0 - floor, max(floor, float(probability)))
    return -math.log(p if observed else 1.0 - p)


def brier_score(probability: float, observed: bool) -> float:
    return (float(probability) - float(bool(observed))) ** 2


def expected_calibration_error(
    probabilities: Sequence[float], observations: Sequence[bool], bins: int = 10
) -> float:
    """Expected calibration error using equal-width confidence bins."""
    if len(probabilities) != len(observations):
        raise ValueError("probabilities and observations must have equal length")
    if not probabilities:
        return 0.0
    total = len(probabilities)
    error = 0.0
    for index in range(bins):
        lower = index / bins
        upper = (index + 1) / bins
        members = [
            (float(probability), bool(observation))
            for probability, observation in zip(probabilities, observations)
            if lower <= float(probability) < upper or (index == bins - 1 and float(probability) == upper)
        ]
        if members:
            confidence = sum(item[0] for item in members) / len(members)
            accuracy = sum(float(item[1]) for item in members) / len(members)
            error += len(members) / total * abs(confidence - accuracy)
    return error


def mean_time_to_recovery(durations_sec: Iterable[float | None]) -> float | None:
    values = [float(value) for value in durations_sec if value is not None and float(value) >= 0.0]
    return sum(values) / len(values) if values else None


def recovery_rate(outcomes: Iterable[bool]) -> float:
    values = [bool(value) for value in outcomes]
    return sum(values) / len(values) if values else 0.0
