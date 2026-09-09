"""MAMJ reflective-mutation path with the current project's semantics.

This is a dependency-free extraction of the MAMJ path used by
``run_optimize_claude.py``:

* candidate selection: Pareto-front selection;
* batch sampling: epoch-shuffled ids with least-frequent padding;
* component selection: all components;
* reflective mutation: failed trajectories -> teacher -> new candidate;
* acceptance: strict minibatch-sum improvement;
* validation: full validation evaluation for every accepted candidate;
* stopping: maximum metric calls.

It intentionally does not implement merge, external experiment trackers, or
MAMJ state serialization because those options are not enabled by the current
script. ``trace=True`` prints and records the values needed for an offline
one-to-one comparison with MAMJ.
"""

from __future__ import annotations

import random
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence


Candidate = dict[str, str]


@dataclass
class EvalBatch:
    outputs: list[Any]
    scores: list[float]
    trajectories: list[Any] | None = None
    objective_scores: list[dict[str, float]] | None = None

    def __post_init__(self) -> None:
        if len(self.outputs) != len(self.scores):
            raise ValueError("outputs and scores must have equal lengths")


@dataclass
class TraceEvent:
    name: str
    payload: dict[str, Any]


@dataclass
class StrictResult:
    best_candidate: Candidate
    best_score: float
    candidates: list[Candidate]
    validation_scores: list[float]
    validation_subscores: list[dict[int, float]] = field(default_factory=list)
    per_val_instance_best_candidates: dict[int, set[int]] = field(default_factory=dict)
    trace: list[TraceEvent] = field(default_factory=list)
    parent_program_for_candidate: list[list[int | None]] = field(default_factory=list)
    full_program_trace: list[dict[str, Any]] = field(default_factory=list)
    total_metric_calls: int = 0
    num_full_val_evals: int = 0
    num_metric_calls_by_discovery: list[int] = field(default_factory=list)


class EpochShuffledBatchSampler:
    """Exact equivalent of MAMJ's EpochShuffledBatchSampler for list data."""

    def __init__(self, minibatch_size: int, rng: random.Random):
        self.minibatch_size = minibatch_size
        self.rng = rng
        self.shuffled_ids: list[int] = []
        self.epoch = -1
        self.id_freqs: Counter[int] = Counter()
        self.last_trainset_size = 0

    def _update_shuffled(self, size: int) -> None:
        all_ids = list(range(size))
        self.last_trainset_size = size
        self.shuffled_ids = list(all_ids)
        self.rng.shuffle(self.shuffled_ids)
        self.id_freqs = Counter(self.shuffled_ids)

        remainder = size % self.minibatch_size
        num_to_pad = self.minibatch_size - remainder if remainder else 0
        for _ in range(num_to_pad):
            selected_id = self.id_freqs.most_common()[::-1][0][0]
            self.shuffled_ids.append(selected_id)
            self.id_freqs[selected_id] += 1

    def next_ids(self, size: int, state_i: int) -> list[int]:
        if size == 0:
            raise ValueError("Cannot sample a minibatch from an empty trainset")
        base_idx = state_i * self.minibatch_size
        current_epoch = 0 if self.epoch == -1 else base_idx // max(len(self.shuffled_ids), 1)
        if not self.shuffled_ids or size != self.last_trainset_size or current_epoch > self.epoch:
            self.epoch = current_epoch
            self._update_shuffled(size)
        base_idx %= len(self.shuffled_ids)
        end_idx = base_idx + self.minibatch_size
        if end_idx > len(self.shuffled_ids):
            raise AssertionError("MAMJ sampler produced an incomplete minibatch")
        return self.shuffled_ids[base_idx:end_idx]


def _is_dominated(program: int, programs: set[int], fronts: Mapping[Any, set[int]]) -> bool:
    program_fronts = [front for front in fronts.values() if program in front]
    for front in program_fronts:
        if not any(other in programs for other in front):
            return False
    return True


def _remove_dominated(fronts: Mapping[Any, set[int]], scores: Sequence[float]) -> dict[Any, set[int]]:
    frequency: dict[int, int] = {}
    for front in fronts.values():
        for program in front:
            frequency[program] = frequency.get(program, 0) + 1
    programs = sorted(frequency, key=lambda program: scores[program])
    dominated: set[int] = set()
    found = True
    while found:
        found = False
        for program in programs:
            if program in dominated:
                continue
            others = set(programs).difference({program}).difference(dominated)
            if _is_dominated(program, others, fronts):
                dominated.add(program)
                found = True
                break
    dominators = [program for program in programs if program not in dominated]
    return {
        val_id: {program for program in front if program in dominators}
        for val_id, front in fronts.items()
    }


def _select_pareto_candidate(
    fronts: Mapping[Any, set[int]], scores: Sequence[float], rng: random.Random
) -> int:
    reduced = _remove_dominated(fronts, scores)
    frequencies: dict[int, int] = {}
    for front in reduced.values():
        for program in front:
            frequencies[program] = frequencies.get(program, 0) + 1
    sampling_list = [program for program, count in frequencies.items() for _ in range(count)]
    if not sampling_list:
        raise AssertionError("No candidate survived the Pareto front")
    return rng.choice(sampling_list)


class StrictMAMJReflectiveOptimizer:
    """Equivalent reflective optimizer for the options used by the script."""

    def __init__(
        self,
        evaluator: Callable[[list[Any], Candidate, bool], EvalBatch],
        reflective_dataset_builder: Callable[
            [Candidate, EvalBatch, list[str]], Mapping[str, Sequence[Mapping[str, Any]]]
        ],
        reflection_lm: Callable[[str], str],
        *,
        reflection_prompt_template: str,
        max_metric_calls: int,
        reflection_minibatch_size: int = 3,
        perfect_score: float = 1.0,
        skip_perfect_score: bool = True,
        seed: int = 0,
        trace: bool = True,
    ) -> None:
        self.evaluator = evaluator
        self.build_feedback = reflective_dataset_builder
        self.reflection_lm = reflection_lm
        self.template = reflection_prompt_template
        self.max_metric_calls = max_metric_calls
        self.minibatch_size = reflection_minibatch_size
        self.perfect_score = perfect_score
        self.skip_perfect_score = skip_perfect_score
        self.rng = random.Random(seed)
        self.sampler = EpochShuffledBatchSampler(reflection_minibatch_size, self.rng)
        self.trace_enabled = trace
        self.events: list[TraceEvent] = []

        missing_placeholders = [
            placeholder
            for placeholder in ("<curr_instructions>", "<inputs_outputs_feedback>")
            if placeholder not in self.template
        ]
        if missing_placeholders:
            raise ValueError(
                "Missing placeholder(s) in reflection prompt template: "
                + ", ".join(missing_placeholders)
            )

    def _trace(self, name: str, **payload: Any) -> None:
        event = TraceEvent(name, payload)
        self.events.append(event)
        if self.trace_enabled:
            print(f"[STRICT-TRACE] {name}: {payload}")

    @staticmethod
    def _render_value(value: Any, level: int = 3) -> str:
        if isinstance(value, Mapping):
            result = ""
            for key, item in value.items():
                result += f"{'#' * level} {key}\n"
                result += StrictMAMJReflectiveOptimizer._render_value(item, min(level + 1, 6))
            return result or "\n"
        if isinstance(value, (list, tuple)):
            result = ""
            for index, item in enumerate(value):
                result += f"{'#' * level} Item {index + 1}\n"
                result += StrictMAMJReflectiveOptimizer._render_value(item, min(level + 1, 6))
            return result or "\n"
        return f"{str(value).strip()}\n\n"

    @classmethod
    def _render_dataset(cls, dataset: Sequence[Mapping[str, Any]]) -> str:
        rendered_examples = []
        for number, sample in enumerate(dataset, 1):
            text = f"# Example {number}\n"
            for key, value in sample.items():
                text += f"## {key}\n"
                text += cls._render_value(value)
            rendered_examples.append(text)
        return "\n\n".join(rendered_examples)

    def _proposal(self, candidate: Candidate, evaluation: EvalBatch) -> Candidate:
        # This mirrors AllReflectionComponentSelector and the adapter contract.
        components = list(candidate.keys())
        feedback = self.build_feedback(candidate, evaluation, components)
        proposed = candidate.copy()
        for component in components:
            records = feedback.get(component, [])
            if not records:
                continue
            prompt = self.template.replace("<component_name>", component)
            prompt = prompt.replace("<curr_instructions>", candidate[component])
            prompt = prompt.replace("<inputs_outputs_feedback>", self._render_dataset(records))
            self._trace(
                "reflection_prompt",
                component=component,
                prompt=prompt,
                record_count=len(records),
            )
            raw = self.reflection_lm(prompt)
            self._trace("reflection_output", component=component, raw_output=raw)
            start = raw.find("```") + 3
            end = raw.rfind("```")
            if start >= end:
                revised = raw.strip()
                if revised.startswith("```"):
                    revised = re.sub(r"^```\S*\n?", "", raw).strip()
                elif revised.endswith("```"):
                    revised = revised[:-3].strip()
            else:
                content = raw[start:end]
                language = re.match(r"^\S*\n", content)
                revised = content[language.end():] if language else content
                revised = revised.strip()
            proposed[component] = revised
        return proposed

    @staticmethod
    def _mean(scores: Sequence[float]) -> float:
        return sum(scores) / len(scores) if scores else float("-inf")

    def optimize(self, seed_candidate: Mapping[str, str], trainset: Sequence[Any], valset: Sequence[Any]) -> StrictResult:
        train_data = list(trainset)
        val_data = list(valset)
        candidate = dict(seed_candidate)
        candidates = [candidate.copy()]
        parents: list[list[int | None]] = [[None]]
        val_scores_by_candidate: list[dict[int, float]] = []
        pareto_fronts: dict[int, set[int]] = {}
        full_program_trace: list[dict[str, Any]] = []
        num_metric_calls_by_discovery = [0]
        metric_calls = 0

        initial = self.evaluator(val_data, candidate, False)
        metric_calls += len(val_data)
        base_scores = {index: score for index, score in enumerate(initial.scores)}
        val_scores_by_candidate.append(base_scores)
        pareto_fronts = {index: {0} for index in base_scores}
        self._trace(
            "initial_validation",
            candidate_index=0,
            scores=list(initial.scores),
            mean=self._mean(initial.scores),
            metric_calls=metric_calls,
        )

        iteration = 0
        while metric_calls < self.max_metric_calls:
            iteration += 1
            selected_index = _select_pareto_candidate(
                pareto_fronts,
                [self._mean(list(scores.values())) for scores in val_scores_by_candidate],
                self.rng,
            )
            current_candidate = candidates[selected_index]
            batch_ids = self.sampler.next_ids(len(train_data), iteration - 1)
            batch = [train_data[index] for index in batch_ids]
            iteration_trace = {
                "i": iteration,
                "selected_program_candidate": selected_index,
                "subsample_ids": list(batch_ids),
            }
            full_program_trace.append(iteration_trace)
            self._trace(
                "iteration_start",
                iteration=iteration,
                selected_candidate=selected_index,
                batch_ids=batch_ids,
                metric_calls=metric_calls,
            )

            current_eval = self.evaluator(batch, current_candidate, True)
            metric_calls += len(batch)
            iteration_trace["subsample_scores"] = list(current_eval.scores)
            self._trace(
                "current_evaluation",
                iteration=iteration,
                candidate_index=selected_index,
                scores=list(current_eval.scores),
                metric_calls=metric_calls,
            )
            if current_eval.trajectories is None or len(current_eval.trajectories) == 0:
                self._trace("skip_no_trajectories", iteration=iteration)
                continue
            if self.skip_perfect_score and all(score >= self.perfect_score for score in current_eval.scores):
                self._trace("skip_perfect_score", iteration=iteration)
                continue

            try:
                new_candidate = self._proposal(current_candidate, current_eval)
            except Exception as exc:
                self._trace("reflection_exception", iteration=iteration, error=repr(exc))
                continue

            new_eval = self.evaluator(batch, new_candidate, False)
            metric_calls += len(batch)
            iteration_trace["new_subsample_scores"] = list(new_eval.scores)
            self._trace(
                "new_evaluation",
                iteration=iteration,
                parent_candidate=selected_index,
                scores=list(new_eval.scores),
                metric_calls=metric_calls,
            )
            old_sum = sum(current_eval.scores)
            new_sum = sum(new_eval.scores)
            if new_sum <= old_sum:
                self._trace("candidate_rejected", iteration=iteration, old_sum=old_sum, new_sum=new_sum)
                continue

            full_eval = self.evaluator(val_data, new_candidate, False)
            metric_calls += len(val_data)
            new_index = len(candidates)
            candidates.append(new_candidate.copy())
            parents.append([selected_index])
            num_metric_calls_by_discovery.append(metric_calls - len(full_eval.scores))
            val_scores = {index: score for index, score in enumerate(full_eval.scores)}
            val_scores_by_candidate.append(val_scores)
            for val_id, score in val_scores.items():
                previous = max((scores[val_id] for scores in val_scores_by_candidate[:-1] if val_id in scores), default=float("-inf"))
                if score > previous:
                    pareto_fronts[val_id] = {new_index}
                elif score == previous:
                    pareto_fronts.setdefault(val_id, set()).add(new_index)
            iteration_trace["new_program_idx"] = new_index
            iteration_trace["evaluated_val_indices"] = list(range(len(full_eval.scores)))
            self._trace(
                "candidate_accepted",
                iteration=iteration,
                new_candidate=new_index,
                parent_candidate=selected_index,
                old_sum=old_sum,
                new_sum=new_sum,
                validation_scores=list(full_eval.scores),
                metric_calls=metric_calls,
            )

        aggregate_scores = [self._mean(list(scores.values())) for scores in val_scores_by_candidate]
        best_index = max(range(len(aggregate_scores)), key=lambda index: aggregate_scores[index])
        self._trace("optimization_finished", metric_calls=metric_calls, best_candidate=best_index, aggregate_scores=aggregate_scores)
        return StrictResult(
            best_candidate=candidates[best_index],
            best_score=aggregate_scores[best_index],
            candidates=candidates,
            validation_scores=aggregate_scores,
            validation_subscores=val_scores_by_candidate,
            per_val_instance_best_candidates=pareto_fronts,
            trace=self.events,
            parent_program_for_candidate=parents,
            full_program_trace=full_program_trace,
            total_metric_calls=metric_calls,
            num_full_val_evals=len(candidates),
            num_metric_calls_by_discovery=num_metric_calls_by_discovery,
        )


__all__ = ["Candidate", "EvalBatch", "StrictMAMJReflectiveOptimizer", "StrictResult"]
