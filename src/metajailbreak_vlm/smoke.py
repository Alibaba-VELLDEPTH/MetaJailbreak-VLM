"""Offline check using synthetic values; no network, credentials, or output files."""

from .optimizers.reflective import EvalBatch, StrictMAMJReflectiveOptimizer


def run():
    def evaluate(batch, candidate, capture_traces=False):
        scores = [float(candidate["text"] == "updated") for _ in batch]
        return EvalBatch(
            outputs=["mock"] * len(batch),
            scores=scores,
            trajectories=["mock"] * len(batch) if capture_traces else None,
        )

    optimizer = StrictMAMJReflectiveOptimizer(
        evaluator=evaluate,
        reflective_dataset_builder=lambda candidate, evaluation, components: {
            key: [{"feedback": "mock"}] for key in components
        },
        reflection_lm=lambda prompt: "```\nupdated\n```",
        reflection_prompt_template="<curr_instructions>\n<inputs_outputs_feedback>",
        max_metric_calls=4,
        reflection_minibatch_size=1,
        trace=False,
    )
    result = optimizer.optimize({"text": "initial"}, ["train"], ["validation"])
    if (
        result.best_candidate != {"text": "updated"}
        or result.best_score != 1.0
        or result.total_metric_calls != 4
    ):
        raise RuntimeError("Offline optimizer smoke test failed")
    print(
        "Offline smoke test passed: evaluation, reflection, acceptance, validation (4 metric calls)."
    )
    return result
