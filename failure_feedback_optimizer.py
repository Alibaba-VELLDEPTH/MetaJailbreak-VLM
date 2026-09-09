"""Minimal failure-case feedback optimizer extracted from MAMJ.

This module keeps only the reflective-mutation path needed by the VLM attack
experiment:

1. evaluate the current candidate on a minibatch;
2. retain failed cases as feedback examples;
3. ask a reflection model to rewrite selected components;
4. keep the rewrite only when its minibatch score improves;
5. optionally evaluate the accepted candidate on a validation set.

It deliberately does not depend on the MAMJ package and does not implement
MAMJ's Pareto frontier, merge proposer, experiment trackers, persistence, or
candidate lineage.

The evaluator is intentionally injected so this module can be used with an
existing adapter without copying the attack/evaluation implementation here.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol, Sequence


Candidate = dict[str, str]


@dataclass
class EvaluationResult:
    """Per-example result returned by an evaluator."""

    outputs: list[Any]
    scores: list[float]
    trajectories: list[Any] | None = None

    def __post_init__(self) -> None:
        if len(self.outputs) != len(self.scores):
            raise ValueError("outputs and scores must have the same length")
        if self.trajectories is not None and len(self.trajectories) != len(self.scores):
            raise ValueError("trajectories and scores must have the same length")


class Evaluator(Protocol):
    def __call__(
        self,
        batch: list[Any],
        candidate: Candidate,
        capture_traces: bool = False,
    ) -> EvaluationResult: ...


class ReflectiveDatasetBuilder(Protocol):
    def __call__(
        self,
        candidate: Candidate,
        evaluation: EvaluationResult,
        components_to_update: list[str],
    ) -> Mapping[str, Sequence[Mapping[str, Any]]]: ...


class ReflectionLM(Protocol):
    def __call__(self, prompt: str) -> str: ...


DEFAULT_REFLECTION_PROMPT = """I provided an assistant with the following instructions:
```
<curr_instructions>
```

The following are failed task executions and feedback:
```
<inputs_outputs_feedback>
```

Write a revised instruction for the component named <component_name>.
Generalize the feedback instead of overfitting to one example. Preserve useful
behavior, fix the observed failure modes, and return only the complete revised
instruction inside a fenced code block.
"""


@dataclass
class OptimizationStep:
    iteration: int
    component_names: list[str]
    failed_cases: int
    score_before: float
    score_after: float | None
    accepted: bool
    candidate: Candidate


@dataclass
class OptimizationResult:
    best_candidate: Candidate
    best_score: float
    history: list[OptimizationStep]


class FailureFeedbackOptimizer:
    """A small, evaluator-agnostic reflective mutation loop."""

    def __init__(
        self,
        evaluator: Evaluator,
        reflective_dataset_builder: ReflectiveDatasetBuilder,
        reflection_lm: ReflectionLM,
        *,
        max_iterations: int = 20,
        minibatch_size: int = 3,
        components: Sequence[str] | None = None,
        component_selector: str = "round_robin",
        perfect_score: float = 1.0,
        reflection_prompt_template: str | None = None,
        seed: int = 0,
        verbose: bool = True,
    ) -> None:
        if max_iterations < 1:
            raise ValueError("max_iterations must be at least 1")
        if minibatch_size < 1:
            raise ValueError("minibatch_size must be at least 1")
        if component_selector not in {"round_robin", "all"}:
            raise ValueError("component_selector must be 'round_robin' or 'all'")
        if reflection_prompt_template is not None:
            self._validate_template(reflection_prompt_template)

        self.evaluator = evaluator
        self.reflective_dataset_builder = reflective_dataset_builder
        self.reflection_lm = reflection_lm
        self.max_iterations = max_iterations
        self.minibatch_size = minibatch_size
        self.components = list(components) if components is not None else None
        self.component_selector = component_selector
        self.perfect_score = perfect_score
        self.reflection_prompt_template = reflection_prompt_template or DEFAULT_REFLECTION_PROMPT
        self.rng = random.Random(seed)
        self.verbose = verbose

    @staticmethod
    def _validate_template(template: str) -> None:
        required = ("<curr_instructions>", "<inputs_outputs_feedback>", "<component_name>")
        missing = [item for item in required if item not in template]
        if missing:
            raise ValueError(f"Reflection prompt is missing placeholder(s): {', '.join(missing)}")

    @staticmethod
    def _render_value(value: Any, level: int = 3) -> str:
        if isinstance(value, Mapping):
            rendered = []
            for key, item in value.items():
                rendered.append(f"{'#' * level} {key}\n")
                rendered.append(FailureFeedbackOptimizer._render_value(item, min(level + 1, 6)))
            return "".join(rendered) or "\n"
        if isinstance(value, (list, tuple)):
            rendered = []
            for index, item in enumerate(value, 1):
                rendered.append(f"{'#' * level} Item {index}\n")
                rendered.append(FailureFeedbackOptimizer._render_value(item, min(level + 1, 6)))
            return "".join(rendered) or "\n"
        return f"{str(value).strip()}\n\n"

    @classmethod
    def _render_dataset(cls, dataset: Sequence[Mapping[str, Any]]) -> str:
        examples = []
        for index, record in enumerate(dataset, 1):
            lines = [f"# Example {index}\n"]
            for key, value in record.items():
                lines.append(f"## {key}\n")
                lines.append(cls._render_value(value))
            examples.append("".join(lines))
        return "\n".join(examples)

    def _build_reflection_prompt(
        self,
        component_name: str,
        current_instruction: str,
        dataset: Sequence[Mapping[str, Any]],
    ) -> str:
        return (
            self.reflection_prompt_template
            .replace("<component_name>", component_name)
            .replace("<curr_instructions>", current_instruction)
            .replace("<inputs_outputs_feedback>", self._render_dataset(dataset))
        )

    @staticmethod
    def _extract_revised_instruction(text: str) -> str:
        """Extract the first useful fenced block, or use the whole response."""
        match = re.search(r"```(?:[^\n]*)\n?(.*?)```", text, flags=re.DOTALL)
        if match:
            value = match.group(1).strip()
            if value:
                return value
        value = text.strip()
        if value.startswith("```"):
            value = re.sub(r"^```\S*\s*", "", value)
        if value.endswith("```"):
            value = value[:-3]
        return value.strip()

    def _select_components(self, candidate: Candidate, iteration: int) -> list[str]:
        names = self.components or list(candidate)
        names = [name for name in names if name in candidate]
        if not names:
            raise ValueError("No optimizable components exist in the candidate")
        if self.component_selector == "all":
            return names
        return [names[(iteration - 1) % len(names)]]

    def _select_batch(self, dataset: Sequence[Any]) -> list[Any]:
        if not dataset:
            return []
        size = min(self.minibatch_size, len(dataset))
        return self.rng.sample(list(dataset), size)

    @staticmethod
    def _failed_indices(result: EvaluationResult) -> list[int]:
        return [index for index, score in enumerate(result.scores) if score < 1.0]

    def _propose_candidate(
        self,
        candidate: Candidate,
        evaluation: EvaluationResult,
        component_names: list[str],
    ) -> Candidate | None:
        failed = self._failed_indices(evaluation)
        if not failed:
            return None

        failed_evaluation = EvaluationResult(
            outputs=[evaluation.outputs[index] for index in failed],
            scores=[evaluation.scores[index] for index in failed],
            trajectories=(
                [evaluation.trajectories[index] for index in failed]
                if evaluation.trajectories is not None
                else None
            ),
        )
        reflective_data = self.reflective_dataset_builder(
            candidate,
            failed_evaluation,
            component_names,
        )
        proposed = candidate.copy()
        changed = False

        for component_name in component_names:
            records = list(reflective_data.get(component_name, []))
            if not records:
                self._log(f"No failed feedback for component {component_name}; skipping")
                continue
            prompt = self._build_reflection_prompt(component_name, candidate[component_name], records)
            revised = self._extract_revised_instruction(self.reflection_lm(prompt))
            if revised and revised != candidate[component_name]:
                proposed[component_name] = revised
                changed = True

        return proposed if changed else None

    def optimize(self, seed_candidate: Mapping[str, str], trainset: Sequence[Any], valset: Sequence[Any] | None = None) -> OptimizationResult:
        candidate = dict(seed_candidate)
        train_data = list(trainset)
        validation_data = list(valset) if valset is not None else train_data
        if not train_data:
            raise ValueError("trainset must not be empty")
        if not validation_data:
            raise ValueError("valset must not be empty")

        initial_validation = self.evaluator(validation_data, candidate, capture_traces=False)
        best_score = self._mean(initial_validation.scores)
        history: list[OptimizationStep] = []
        best_candidate = candidate.copy()

        for iteration in range(1, self.max_iterations + 1):
            batch = self._select_batch(train_data)
            current = self.evaluator(batch, candidate, capture_traces=True)
            score_before = sum(current.scores)
            failed_count = len(self._failed_indices(current))
            component_names = self._select_components(candidate, iteration)

            if failed_count == 0 or all(score >= self.perfect_score for score in current.scores):
                history.append(OptimizationStep(iteration, component_names, failed_count, score_before, None, False, candidate.copy()))
                self._log(f"Iteration {iteration}: no failed cases; stopping")
                break

            proposed = self._propose_candidate(candidate, current, component_names)
            if proposed is None:
                history.append(OptimizationStep(iteration, component_names, failed_count, score_before, None, False, candidate.copy()))
                self._log(f"Iteration {iteration}: reflection produced no change")
                continue

            updated = self.evaluator(batch, proposed, capture_traces=False)
            score_after = sum(updated.scores)
            accepted = score_after > score_before
            if accepted:
                candidate = proposed
                validation = self.evaluator(validation_data, candidate, capture_traces=False)
                validation_score = self._mean(validation.scores)
                if validation_score >= best_score:
                    best_score = validation_score
                    best_candidate = candidate.copy()

            history.append(OptimizationStep(iteration, component_names, failed_count, score_before, score_after, accepted, candidate.copy()))
            self._log(
                f"Iteration {iteration}: failed={failed_count}, "
                f"minibatch {score_before:.3f}->{score_after:.3f}, "
                f"{'accepted' if accepted else 'rejected'}"
            )

        return OptimizationResult(best_candidate=best_candidate, best_score=best_score, history=history)

    @staticmethod
    def _mean(scores: Sequence[float]) -> float:
        return sum(scores) / len(scores) if scores else 0.0

    def _log(self, message: str) -> None:
        if self.verbose:
            print(message)


def optimize_failure_cases(
    seed_candidate: Mapping[str, str],
    trainset: Sequence[Any],
    evaluator: Evaluator,
    reflective_dataset_builder: ReflectiveDatasetBuilder,
    reflection_lm: ReflectionLM,
    **kwargs: Any,
) -> OptimizationResult:
    """Functional wrapper for the minimal optimizer."""
    optimizer = FailureFeedbackOptimizer(
        evaluator=evaluator,
        reflective_dataset_builder=reflective_dataset_builder,
        reflection_lm=reflection_lm,
        **kwargs,
    )
    return optimizer.optimize(seed_candidate, trainset)


__all__ = [
    "Candidate",
    "EvaluationResult",
    "FailureFeedbackOptimizer",
    "OptimizationResult",
    "OptimizationStep",
    "optimize_failure_cases",
]
