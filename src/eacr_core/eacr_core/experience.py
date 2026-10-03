"""Beta recovery and Dirichlet outcome experience models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from .types import Context, Outcome


ALL_OUTCOMES = tuple(outcome.value for outcome in Outcome)


@dataclass
class BetaPosterior:
    alpha: float = 1.0
    beta: float = 1.0

    @property
    def mean(self) -> float:
        return self.alpha / (self.alpha + self.beta)

    @property
    def variance(self) -> float:
        total = self.alpha + self.beta
        return (self.alpha * self.beta) / (total * total * (total + 1.0))

    def update(self, success_weight: float = 0.0, failure_weight: float = 0.0) -> None:
        if success_weight < 0.0 or failure_weight < 0.0:
            raise ValueError("Beta update weights must be non-negative")
        self.alpha += float(success_weight)
        self.beta += float(failure_weight)

    def as_dict(self) -> dict[str, float]:
        return {"alpha": self.alpha, "beta": self.beta, "mean": self.mean, "variance": self.variance}


@dataclass
class DirichletPosterior:
    counts: dict[str, float] = field(
        default_factory=lambda: {outcome: 1.0 for outcome in ALL_OUTCOMES}
    )

    @property
    def total(self) -> float:
        return sum(self.counts.values())

    def probabilities(self) -> dict[str, float]:
        total = self.total
        return {outcome: count / total for outcome, count in self.counts.items()}

    def update(self, outcome: Outcome | str, weight: float = 1.0) -> None:
        if weight < 0.0:
            raise ValueError("Dirichlet update weight must be non-negative")
        outcome_key = outcome.value if isinstance(outcome, Outcome) else str(outcome)
        if outcome_key not in self.counts:
            self.counts[outcome_key] = 1.0
        self.counts[outcome_key] += float(weight)

    def variance(self) -> float:
        total = self.total
        probabilities = self.probabilities()
        return sum(probability * (1.0 - probability) / (total + 1.0) for probability in probabilities.values())

    def as_dict(self) -> dict:
        return {"counts": dict(self.counts), "probabilities": self.probabilities(), "variance": self.variance()}


@dataclass
class ActionExperience:
    recovery: BetaPosterior = field(default_factory=BetaPosterior)
    outcomes: DirichletPosterior = field(default_factory=DirichletPosterior)

    def as_dict(self) -> dict:
        return {"recovery": self.recovery.as_dict(), "outcomes": self.outcomes.as_dict()}


class ExperienceModel:
    """Experience keyed by (fault, context bin, action).

    Online updates use the current belief as a fractional responsibility. This
    avoids using simulator ground truth in the decision loop.
    """

    def __init__(self) -> None:
        self._entries: dict[tuple[str, str, str], ActionExperience] = {}

    @classmethod
    def from_snapshot(cls, snapshot: Mapping[str, Mapping]) -> "ExperienceModel":
        """Rehydrate a model written by :meth:`snapshot`.

        Snapshots are treated as experiment state, so malformed entries are
        rejected instead of silently changing the policy prior.
        """
        model = cls()
        for key, payload in snapshot.items():
            parts = str(key).split("|", 1)
            if len(parts) == 2:
                fault, context_and_action = parts
                context_key, action = context_and_action.rsplit("|", 1)
                parts = [fault, context_key, action]
            if len(parts) != 3:
                raise ValueError(f"Invalid experience snapshot key: {key!r}")
            fault, context_key, action = parts
            recovery = payload.get("recovery", {})
            outcomes = payload.get("outcomes", {})
            rec = BetaPosterior(float(recovery.get("alpha", 1.0)), float(recovery.get("beta", 1.0)))
            counts = {str(k): float(v) for k, v in outcomes.get("counts", {}).items()}
            if not counts:
                counts = {outcome: 1.0 for outcome in ALL_OUTCOMES}
            model._entries[(fault, context_key, action)] = ActionExperience(
                recovery=rec, outcomes=DirichletPosterior(counts)
            )
        return model

    def seed_domain_prior(self, faults: Mapping[str, float], context: Context, action_ids: list[str]) -> None:
        """Create an explicit M0 prior without using observations from this run."""
        recovery_actions = {
            "localization_drift": "relocalize_amcl",
            "costmap_blockage": "clear_costmaps",
            "planner_failure": "reconfigure_planner",
            "controller_failure": "reconfigure_controller",
        }
        for fault in faults:
            for action in action_ids:
                entry = self._entry(fault, context, action)
                if action == recovery_actions.get(fault):
                    entry.recovery = BetaPosterior(alpha=2.0, beta=1.0)
                else:
                    # M0 treats diagnostic-only actions as uncertain and
                    # non-recovering until an observed episode supports them.
                    entry.recovery = BetaPosterior(alpha=1.0, beta=5.0)

    def seed_weak_prior(self, faults: Mapping[str, float], context: Context, action_ids: list[str]) -> None:
        """Create a weak shared M0 prior for adaptation experiments.

        The action catalogue gives each fault family a mildly preferred
        recovery action, while all other actions start conservative.  This
        keeps Static and Evolving identical at initialization, but leaves
        enough uncertainty for repeated feedback to change the ranking.
        """
        recovery_actions = {
            "localization_drift": "relocalize_amcl",
            "costmap_blockage": "clear_costmaps",
            "planner_failure": "reconfigure_planner",
            "controller_failure": "reconfigure_controller",
        }
        for fault in faults:
            for action in action_ids:
                entry = self._entry(fault, context, action)
                if action == recovery_actions.get(fault):
                    entry.recovery = BetaPosterior(alpha=1.2, beta=1.0)
                else:
                    entry.recovery = BetaPosterior(alpha=1.0, beta=3.0)

    def _entry(self, fault: str, context: Context, action_id: str) -> ActionExperience:
        key = (str(fault), context.key(), str(action_id))
        if key not in self._entries:
            self._entries[key] = ActionExperience()
        return self._entries[key]

    def predict_outcomes(
        self,
        faults: Mapping[str, float],
        context: Context,
        action_id: str,
    ) -> dict[str, dict[str, float]]:
        return {
            fault: self._entry(fault, context, action_id).outcomes.probabilities()
            for fault in faults
        }

    def recovery_probability(
        self,
        belief: Mapping[str, float],
        context: Context,
        action_id: str,
    ) -> float:
        return sum(
            float(probability) * self._entry(fault, context, action_id).recovery.mean
            for fault, probability in belief.items()
        )

    def uncertainty(
        self,
        belief: Mapping[str, float],
        context: Context,
        action_id: str,
    ) -> float:
        return sum(
            float(probability)
            * (
                self._entry(fault, context, action_id).recovery.variance
                + self._entry(fault, context, action_id).outcomes.variance()
            )
            for fault, probability in belief.items()
        )

    def update(
        self,
        belief: Mapping[str, float],
        context: Context,
        action_id: str,
        outcome: Outcome | str,
        recovery_success: bool | None = None,
        outcome_weight: float = 1.0,
    ) -> None:
        if outcome_weight < 0.0:
            raise ValueError("outcome_weight must be non-negative")
        for fault, responsibility in belief.items():
            entry = self._entry(fault, context, action_id)
            weight = max(0.0, float(responsibility))
            entry.outcomes.update(outcome, weight * float(outcome_weight))
            if recovery_success is True:
                entry.recovery.update(success_weight=weight)
            elif recovery_success is False:
                entry.recovery.update(failure_weight=weight)

    def snapshot(self) -> dict:
        return {
            f"{fault}|{context_key}|{action}": entry.as_dict()
            for (fault, context_key, action), entry in sorted(self._entries.items())
        }
