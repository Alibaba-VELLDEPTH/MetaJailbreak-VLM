# MetaJailbreak-VLM

Multimodal model safety evaluation and reflective optimization toolkit.
Use with systems, accounts, data, and APIs for which you have authorization.

## Install

Python 3.10 or newer:

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install -e .
metajailbreak --help
metajailbreak --smoke-test
```

The smoke test runs evaluation, reflection, candidate acceptance, and validation
with synthetic responses, entirely offline. It does not test live API availability.

## Run

Copy `.env.example` to `.env` and fill in credentials, model names, and endpoints.
Supply your own task directory; see [data format](data/README.md).

```bash
cp .env.example .env
metajailbreak --train-dir /absolute/path/to/tasks --check
metajailbreak --train-dir /absolute/path/to/tasks --max-metric-calls 156
```

`--check` validates local settings and data without making API calls. Actual
execution makes paid API requests. Metric calls count evaluated samples, not API
requests, tokens, or money. The inherited optimizer finishes evaluation batches
and may exceed this budget; it is not a hard spending cap.

Relative paths resolve from the **current working directory**. Shell variables
override `.env`; CLI path and budget options override both. `--env-file` selects
another configuration file. Two records per category become validation data,
with the rest used for training (seed 0). Each category needs at least three tasks.

| Environment variable | Default |
| --- | --- |
| `VLM_TRAIN_DIR` | `data/train_data` |
| `VLM_SEED_STRATEGY` | `configs/seed_candidate.json` |
| `VLM_OUTPUT_STRATEGY` | `results/best_strategy_standalone.json` |
| `VLM_MAX_METRIC_CALLS` | `156` |
| `VLM_MINIBATCH_SIZE` | `3` |
| `VLM_TRACE` | `1`; set to `0` to disable |

The default seed falls back to the equivalent built-in configuration for wheel
installations. Explicitly configured missing paths cause an error.
Logs go to `logs/`, best strategies to `results/`, and evaluation artifacts to
`MAMJ_ASP_Evlove/eval_renders/`. These directories are ignored by Git.
Traces can contain prompts and model responses.

## Layout

```text
configs/seed_candidate.json       Reference seed configuration
src/metajailbreak_vlm/
  cli.py                         CLI and local checks
  config.py                      Environment configuration
  data.py                        Task loading and deterministic split
  runner.py                      Experiment orchestration
  adapter.py                     Existing multimodal evaluation flow
  clients.py                     Chat and image API clients
  images.py                      Image encoding and response parsing
  prompts.py                     Existing prompt constants
  types.py                       Evaluation trajectory type
  evaluation.py                  Auxiliary judge helper
  optimizers/reflective.py        Primary optimizer
  optimizers/legacy.py            Earlier simplified optimizer
  smoke.py                       Offline optimizer check
tests/                           Offline regression tests
.github/workflows/tests.yml       Python 3.10 / 3.12 CI
```

After installation, `python -m metajailbreak_vlm` and the legacy command
`python run_optimize_standalone.py` invoke the same CLI. Old direct imports move
to the package modules listed above. The legacy optimizer is retained for reference.

## Development

```bash
python -m pip install -e '.[dev]'
pytest -q
ruff check src tests
python -m build
```

Tests mock network transport and require no credentials. Live provider
compatibility and research results require a separately configured real run.
No open-source license has been declared yet; rights holders must establish
licensing and third-party provenance before granting reuse rights.
