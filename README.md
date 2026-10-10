<h1 align="center">MAMJ: Meta-Adaptive Multimodal Jailbreaking</h1>

<p align="center">
  <a href="https://arxiv.org/abs/2608.27531"><img src="https://img.shields.io/badge/Paper-arXiv%3A2608.27531-B31B1B?logo=arxiv&logoColor=white" alt="Paper on arXiv" /></a>
  <a href="https://github.com/Alibaba-VELLDEPTH/MetaJailbreak-VLM"><img src="https://img.shields.io/badge/Code-MetaJailbreak--VLM-181717?logo=github&logoColor=white" alt="Official code" /></a>
</p>

# Fully Unleashing the Multimodal Attacker: Meta-Adaptive Jailbreaking of Vision-Language Models

> Benlei Cui<sup>1,*</sup>, Shen Pang<sup>2,*</sup>, Yuke Wang<sup>2</sup>, Xuemei Dong<sup>2,†</sup>, Yuwen Zhai<sup>1</sup>, Jingqun Tang<sup>1</sup>, Haiyang Yu<sup>1</sup>, Hui Xue<sup>1</sup>, Longtao Huang<sup>1</sup>, Haiwen Hong<sup>1,†</sup>
>
> <sup>1</sup> Yuvion Team, Alibaba Group  
> <sup>2</sup> Laboratory for Statistical Monitoring and Intelligent Governance of Common Prosperity, School of Statistics and Data Science, Zhejiang Gongshang University  
> <sup>*</sup> Equal contribution. <sup>†</sup> Corresponding authors.

## Abstract

Multimodal jailbreak evaluation often adapts individual image–text inputs while leaving the attack strategy and attacker parameters fixed. **Meta-Adaptive Multimodal Jailbreaking (MAMJ)** shifts adaptation to the attacker itself: it refines an **attack strategy prompt (ASP)** using diagnostic feedback across groups of attack trajectories, then optimizes **attacker model weights** using group-based rewards. The resulting attacker combines a learned strategy with a learned policy, and the paper evaluates its effectiveness, transfer to unseen models, and behavior under representative defenses.

<p align="center">
  <img src="assets/intro.png" alt="Comparison of template-based, sample-level adaptive, and meta-adaptive multimodal jailbreaking" width="95%" />
</p>
<p align="center"><em>Three paradigms of multimodal jailbreaking: fixed templates, adaptation within an individual sample, and MAMJ adaptation across groups of samples.</em></p>

## Highlights

- **Meta-level adaptation:** optimize both the attack strategy prompt and attacker weights, beyond changes to individual attack inputs.
- **Group-based diagnosis:** aggregate feedback from multiple trajectories to refine a shared strategy.
- **Policy optimization:** use group-relative reinforcement learning to update the attacker.
- **Transfer evaluation:** test the learned attacker on unseen victim models without retraining and under representative defenses.

## Method Overview

MAMJ uses two stages. First, diagnostic feedback from groups of trajectories refines the attack strategy prompt while the attacker weights remain frozen. Second, the optimized strategy conditions reinforcement learning of the attacker. This connects qualitative strategy refinement with quantitative policy optimization.

<p align="center">
  <img src="assets/training_curve.png" alt="GRPO training curve showing mean reward, its five-step moving average, and policy entropy" width="95%" />
</p>
<p align="center"><em>Attacker training dynamics: mean reward and its five-step moving average increase while policy entropy generally decreases over GRPO update steps.</em></p>

## Results

The supplied local manuscript reports the following attack success rates (ASR) on **MM-SafetyBench**, using a sample-level micro-average over **1,680 test samples**:

| Victim model | MAMJ ASR (%) |
| --- | ---: |
| GPT-4o | 82.02 |
| Gemini-3-Pro-Preview | 79.29 |
| Seed 2.0 | 83.04 |

These values follow the local manuscript, [`acl_latex (1).tex`](../acl_latex%20%281%29.tex). The [arXiv abstract](https://arxiv.org/abs/2608.27531) reports 81.0%, 78.9%, and 82.3%, respectively; the two versions use different reported values.

## News

- **September 3, 2026:** The revised manuscript (v2) is available on [arXiv](https://arxiv.org/abs/2608.27531v2).
- **August 27, 2026:** The first version of the paper was released on [arXiv](https://arxiv.org/abs/2608.27531v1).
- The [arXiv record](https://arxiv.org/abs/2608.27531) lists acceptance at **EMNLP 2026 Main Conference**.

## Resources

| Resource | Link |
| --- | --- |
| Paper | [arXiv:2608.27531](https://arxiv.org/abs/2608.27531) |
| Official implementation | [MetaJailbreak-VLM](https://github.com/Alibaba-VELLDEPTH/MetaJailbreak-VLM) |
| Local manuscript | [LaTeX source](../acl_latex%20%281%29.tex) |
| Paradigm overview | [intro.png](assets/intro.png) |
| Training dynamics | [training_curve.png](assets/training_curve.png) |

## Citation

If you find this work useful in your research, please cite:

```bibtex
@article{cui2026fully,
  title={Fully Unleashing the Multimodal Attacker: Meta-Adaptive Jailbreaking of Vision-Language Models},
  author={Cui, Benlei and Pang, Shen and Wang, Yuke and Dong, Xuemei and Zhai, Yuwen and Tang, Jingqun and Yu, Haiyang and Xue, Hui and Huang, Longtao and Hong, Haiwen},
  journal={arXiv preprint arXiv:2608.27531},
  year={2026}
}
```

## Implementation Guide

The instructions below apply from the root of the [official code repository](https://github.com/Alibaba-VELLDEPTH/MetaJailbreak-VLM). They document the existing toolkit; the offline smoke test does not reproduce the paper's complete two-stage experiments or reported research results.

Multimodal model safety evaluation and reflective optimization toolkit. Use with systems, accounts, data, and APIs for which you have authorization.


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
Supply your own task directory; see [data format](https://github.com/Alibaba-VELLDEPTH/MetaJailbreak-VLM/blob/main/data/README.md).

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
