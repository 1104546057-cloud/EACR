"""Bayesian fault-belief utilities with no ROS dependency."""

from __future__ import annotations

import math
from typing import Mapping

from .types import Outcome


def normalize_distribution(values: Mapping[str, float]) -> dict[str, float]:
    cleaned = {str(key): max(0.0, float(value)) for key, value in values.items()}
    total = sum(cleaned.values())
    if not cleaned or total <= 0.0:
        raise ValueError("probability distribution must have positive mass")
    return {key: value / total for key, value in cleaned.items()}


def entropy(distribution: Mapping[str, float]) -> float:
    """Shannon entropy in nats."""

    return -sum(
        float(probability) * math.log(float(probability))
        for probability in distribution.values()
        if probability > 0.0
    )


def bayesian_update(
    prior: Mapping[str, float],
    likelihood_by_fault: Mapping[str, float],
    *,
    floor: float = 1e-12,
) -> dict[str, float]:
    """Return ``P(fault | observation)`` from a prior and fault likelihoods."""

    normalized_prior = normalize_distribution(prior)
    posterior = {
        fault: probability * max(floor, float(likelihood_by_fault.get(fault, floor)))
        for fault, probability in normalized_prior.items()
    }
    return normalize_distribution(posterior)


def predictive_outcomes(
    belief: Mapping[str, float],
    likelihoods: Mapping[str, Mapping[str, float]],
) -> dict[str, float]:
    """Mix per-fault outcome likelihoods using the current belief."""

    normalized_belief = normalize_distribution(belief)
    outcomes: dict[str, float] = {}
    for fault, fault_probability in normalized_belief.items():
        for outcome, likelihood in likelihoods.get(fault, {}).items():
            outcomes[outcome] = outcomes.get(outcome, 0.0) + (
                fault_probability * max(0.0, float(likelihood))
            )
    return normalize_distribution(outcomes)


def expected_information_gain(
    belief: Mapping[str, float],
    likelihoods: Mapping[str, Mapping[str, float]],
) -> float:
    """Expected reduction in fault-belief entropy for an action."""

    prior = normalize_distribution(belief)
    predictive = predictive_outcomes(prior, likelihoods)
    expected_posterior_entropy = 0.0
    for outcome, outcome_probability in predictive.items():
        posterior = bayesian_update(
            prior,
            {
                fault: fault_likelihoods.get(outcome, 0.0)
                for fault, fault_likelihoods in likelihoods.items()
            },
        )
        expected_posterior_entropy += outcome_probability * entropy(posterior)
    return max(0.0, entropy(prior) - expected_posterior_entropy)


def posterior_after_outcome(
    belief: Mapping[str, float],
    likelihoods: Mapping[str, Mapping[str, float]],
    outcome: Outcome | str,
) -> dict[str, float]:
    """Apply one observed discrete outcome to the fault belief."""

    outcome_key = outcome.value if isinstance(outcome, Outcome) else str(outcome)
    return bayesian_update(
        belief,
        {
            fault: fault_likelihoods.get(outcome_key, 0.0)
            for fault, fault_likelihoods in likelihoods.items()
        },
    )
