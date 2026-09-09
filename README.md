# Standalone MAMJ Reflective Optimizer

This repository contains a standalone extraction of the MAMJ reflective-mutation optimizer used by the original project.

The standalone optimizer does not import the MAMJ package at runtime.

> **Authorized-use notice**
>
> This project is intended for authorized multimodal model safety evaluation only. Use it only with systems, accounts, data, and APIs for which you have permission.

## Files

### `strict_MAMJ_reflective_optimizer.py`

Standalone implementation of the project-specific reflective optimizer, including:

* Pareto candidate selection
* in-memory candidate pool
* candidate lineage
* minibatch sampling
* failed-trajectory reflective feedback
* teacher prompt generation and response parsing
* candidate acceptance and validation
* metric-call budget tracking
* runtime trace metadata

### `run_optimize_standalone.py`

Main runner.

It:

* loads JSON task files
* creates a deterministic category-stratified train/validation split
* initializes the adapter and teacher model
* runs the optimizer
* saves the best candidate to JSON

### `vlm_attack_adapter_standalone.py`

Project-specific model and API adapter.

### `failure_feedback_optimizer.py`

Earlier simplified optimizer implementation. It does not include the Pareto candidate pool and should not be used when strict equivalence with the original optimizer is required.

## Requirements

Python 3.10 or newer is recommended.

Install the required packages:

```bash
python -m pip install requests pillow numpy openai
```

## Task Data

The runner expects a directory containing JSON files.

Each task must contain one of the following fields:

* `changed_question`
* `Changed Question`
* `Question`

Tasks are converted internally to:

```json
{
  "task_id": "category_entry_id",
  "instruction": "the task instruction",
  "category": "category_name",
  "source": "Train"
}
```

Example:

```text
data/
└── train_data/
    ├── category_a.json
    ├── category_b.json
    └── category_c.json
```

The default split uses:

* 2 validation examples per category
* all remaining examples for training
* random seed `0`

## Configuration

Configure the model clients in `run_optimize_standalone.py`.

Example:

```python
args = argparse.Namespace(
    attacker_model_name="...",
    attacker_model_url="https://.../v1",
    attacker_model_key=os.environ["ATTACKER_MODEL_API_KEY"],

    victim_model_name="...",
    victim_model_url="https://.../v1",
    victim_model_key=os.environ["VICTIM_MODEL_API_KEY"],

    feedback_model_name="...",
    feedback_model_url="https://.../v1",
    feedback_model_key=os.environ["FEEDBACK_MODEL_API_KEY"],

    Image_Generation_Model="...",
    Image_Generation_Model_base_url="https://...",
    Image_Generation_Model_api_key=os.environ["IMAGE_MODEL_API_KEY"],
)
```

Do not hard-code API keys in source files.

Use environment variables or a local `.env` file that is excluded from Git.

## Run

### Linux / macOS

```bash
export VLM_TRAIN_DIR="./data/train_data"
export VLM_MAX_METRIC_CALLS=6
export VLM_MINIBATCH_SIZE=3
export VLM_TRACE=0
export VLM_SEED_STRATEGY="./seed_candidate.json"
export VLM_OUTPUT_STRATEGY="./results/best_strategy_standalone.json"
export PYTHONPATH="."

python ./run_optimize_standalone.py
```

### Windows PowerShell

```powershell
$env:VLM_TRAIN_DIR = ".\data\train_data"
$env:VLM_MAX_METRIC_CALLS = "6"
$env:VLM_MINIBATCH_SIZE = "3"
$env:VLM_TRACE = "0"
$env:VLM_SEED_STRATEGY = ".\seed_candidate.json"
$env:VLM_OUTPUT_STRATEGY = ".\results\best_strategy_standalone.json"
$env:PYTHONPATH = "."

python .\run_optimize_standalone.py
```

Start with a small metric-call budget to verify the configuration before increasing it.

## Environment Variables

| Variable               |                         Default | Description                        |
| ---------------------- | ------------------------------: | ---------------------------------- |
| `VLM_TRAIN_DIR`        |                   auto-detected | Task JSON directory                |
| `VLM_SEED_STRATEGY`    |           `seed_candidate.json` | Seed candidate JSON                |
| `VLM_OUTPUT_STRATEGY`  | `best_strategy_standalone.json` | Best candidate output path         |
| `VLM_MAX_METRIC_CALLS` |                           `156` | Maximum metric-call budget         |
| `VLM_MINIBATCH_SIZE`   |                             `3` | Reflection minibatch size          |
| `VLM_TRACE`            |                             `1` | Set to `0` to disable trace output |

## Output

The runner generates:

* the best candidate JSON
* runtime logs under `logs/`
* task results and generated images under:

```text
MAMJ_ASP_Evlove/eval_renders/
```

Generated files should not be committed to the repository.

## Before Publishing

Do not commit:

* API keys or access tokens
* `.env`
* logs
* generated images
* result files
* private or restricted datasets

Recommended `.gitignore` entries:

```gitignore
.env
logs/
results/
MAMJ_ASP_Evlove/
```

Rotate any credential that has previously been committed or included in logs.

## Notes

The standalone optimizer was designed to preserve the behavior required by the original project configuration.

External model APIs are nondeterministic, so real runs may produce different text, images, and model responses even with the same configuration.

## License

Add an appropriate repository license and verify compatibility with the licenses of any datasets, model clients, MAMJ-derived components, and copied project code.
