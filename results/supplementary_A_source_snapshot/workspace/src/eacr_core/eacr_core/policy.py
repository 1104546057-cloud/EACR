"""Safety filtering and explainable EACR action selection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from .belief import expected_information_gain
from .experience import ExperienceModel
from .types import ActionScore, ActionSpec, Context, Decision


@dataclass(frozen=True)
class PolicyWeights:
    information_gain: float = 1.0
    recovery_gain: float = 1.0
    cost: float = 0.6
    uncertainty: float = 0.4
    risk_limit: float = 0.40
    minimum_utility: float = 0.0


def score_action(
    action: ActionSpec,
    belief: Mapping[str, float],
    context: Context,
    experience: ExperienceModel,
    weights: PolicyWeights = PolicyWeights(),
) -> ActionScore:
    if not action.allowed:
        return ActionScore(action.action_id, 0.0, 0.0, action.cost, 0.0, float("-inf"), False, "not_allowed")
    if not action.hard_safe:
        return ActionScore(action.action_id, 0.0, 0.0, action.cost, 0.0, float("-inf"), False, "hard_safety_block")
    if action.risk > weights.risk_limit:
        return ActionScore(action.action_id, 0.0, 0.0, action.cost, 0.0, float("-inf"), False, "risk_limit")

    likelihoods = experience.predict_outcomes(belief, context, action.action_id)
    information_gain = expected_information_gain(belief, likelihoods)
    recovery_gain = experience.recovery_probability(belief, context, action.action_id)
    uncertainty = experience.uncertainty(belief, context, action.action_id)
    utility = (
        weights.information_gain * information_gain
        + weights.recovery_gain * recovery_gain
        - weights.cost * action.cost
        - weights.uncertainty * uncertainty
    )
    return ActionScore(
        action.action_id,
        information_gain,
        recovery_gain,
        action.cost,
        uncertainty,
        utility,
        True,
    )


def choose_action(
    actions: Iterable[ActionSpec],
    belief: Mapping[str, float],
    context: Context,
    experience: ExperienceModel,
    weights: PolicyWeights = PolicyWeights(),
) -> Decision:
    scores = tuple(
        sorted(
            (
                score_action(action, belief, context, experience, weights)
                for action in actions
            ),
            key=lambda score: (-score.utility, score.action_id),
        )
    )
    safe_scores = tuple(score for score in scores if score.safe)
    if not safe_scores:
        return Decision(None, True, "no_safe_action", scores)
    best = safe_scores[0]
    if best.utility < weights.minimum_utility:
        return Decision(None, True, "best_action_below_minimum_utility", scores)
    return Decision(best.action_id, False, "selected_highest_expected_utility", scores)
