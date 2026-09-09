import os
import json
from .config import build_configuration, validate_api_configuration, parse_positive_int
from .data import (
    resolve_train_dir,
    load_dataset_from_directory,
    load_seed_candidate,
    repository_path,
    split_dataset,
)
from .prompts import reflection_prompt_template
from .clients import VLMChatClient
from .adapter import MyGUIAttackAdapter
from .optimizers.reflective import EvalBatch, StrictMAMJReflectiveOptimizer


def main():
    current_dir = os.getcwd()
    args = build_configuration()
    validate_api_configuration(args)
    print(f">>> Initializing Teacher LLM with {args.feedback_model_name}...")
    teacher_llm = VLMChatClient(
        api_key=args.feedback_model_key,
        base_url=args.feedback_model_url,
        model=args.feedback_model_name,
        default_system_prompt=reflection_prompt_template,
    )

    train_dir = resolve_train_dir(current_dir)
    if train_dir is None:
        raise FileNotFoundError(
            "Training directory not found. Set VLM_TRAIN_DIR to the directory containing JSON files."
        )
    full_train_data = load_dataset_from_directory(train_dir, "Train")
    if not full_train_data:
        raise RuntimeError(f"No training samples loaded from {train_dir}")

    trainset_pool, valset = split_dataset(full_train_data)
    print("\n>>> Data Split for Optimization:")
    if not trainset_pool:
        raise RuntimeError(
            "Training split is empty; provide more than two tasks per category"
        )
    print(f"    [Total Val Set]: {len(valset)}")
    print(f"    [Total Train Set]: {len(trainset_pool)}")

    attack_adapter = MyGUIAttackAdapter(args=args)

    def evaluate(batch, candidate, capture_traces=False):
        result = attack_adapter.evaluate(
            batch, candidate, capture_traces=capture_traces
        )
        return EvalBatch(
            outputs=list(result.outputs),
            scores=list(result.scores),
            trajectories=(
                list(result.trajectories) if result.trajectories is not None else None
            ),
            objective_scores=(
                list(result.objective_scores)
                if getattr(result, "objective_scores", None) is not None
                else None
            ),
        )

    loaded_seed_candidate = load_seed_candidate(current_dir)
    output_path = os.path.abspath(
        repository_path(
            current_dir,
            os.environ.get(
                "VLM_OUTPUT_STRATEGY", "results/best_strategy_standalone.json"
            ),
        )
    )
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    max_metric_calls = parse_positive_int("VLM_MAX_METRIC_CALLS", 156, 0)
    minibatch_size = parse_positive_int("VLM_MINIBATCH_SIZE", 3, 1)

    trace_raw = os.environ.get("VLM_TRACE", "1").strip().lower()
    trace_enabled = trace_raw not in {"0", "false", "no", "off"}
    print(f"    [Metric budget]: {max_metric_calls}")
    print(f"    [Reflection minibatch]: {minibatch_size}")
    print(f"    [Trace enabled]: {trace_enabled}")

    if max_metric_calls < len(valset):
        print(
            "[Warning] Metric budget is smaller than the validation set; "
            "the initial validation call may exceed the budget."
        )

    if not os.environ.get("VLM_SEED_STRATEGY"):
        print("    [Seed]: built-in seed_candidate.json-compatible candidate")
    if not os.environ.get("VLM_OUTPUT_STRATEGY"):
        print(f"    [Output]: {output_path}")

    # All paths above are resolved relative to this code directory unless absolute.
    # This makes the published folder self-contained.

    optimizer = StrictMAMJReflectiveOptimizer(
        evaluator=evaluate,
        reflective_dataset_builder=attack_adapter.make_reflective_dataset,
        reflection_lm=teacher_llm,
        reflection_prompt_template=reflection_prompt_template,
        max_metric_calls=max_metric_calls,
        reflection_minibatch_size=minibatch_size,
        perfect_score=1.0,
        skip_perfect_score=True,
        seed=0,
        trace=trace_enabled,
    )

    print(f"\n>>> Starting standalone optimization on {len(trainset_pool)} tasks...")
    result = optimizer.optimize(loaded_seed_candidate, trainset_pool, valset)
    print("\n=== Optimization Finished ===")
    print("Best validation score:", result.best_score)
    print("Best Strategy Found:", result.best_candidate)

    save_path = output_path
    with open(save_path, "w", encoding="utf-8") as file:
        json.dump(result.best_candidate, file, indent=4, ensure_ascii=False)
    print(f"Best strategy saved to: {save_path}")
