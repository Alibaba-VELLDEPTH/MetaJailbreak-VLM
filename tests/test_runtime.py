import json
import os
import socket
import sys
from unittest.mock import Mock

import pytest

from metajailbreak_vlm.cli import main
from metajailbreak_vlm.config import build_configuration, load_dotenv
from metajailbreak_vlm.data import (
    load_dataset_from_directory,
    load_seed_candidate,
    resolve_train_dir,
    split_dataset,
)
from metajailbreak_vlm.clients import VLMChatClient, ImageGenerationClient
from metajailbreak_vlm.optimizers.reflective import EvalBatch
from metajailbreak_vlm.smoke import run


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("Tests must not access the network")

    monkeypatch.setattr(socket.socket, "connect", denied)
    for key in list(os.environ):
        if key.startswith(("VLM_", "ATTACKER_", "VICTIM_", "FEEDBACK_", "IMAGE_")):
            monkeypatch.delenv(key)


@pytest.fixture
def tasks(tmp_path):
    directory = tmp_path / "tasks"
    directory.mkdir()
    (directory / "sample.json").write_text(
        json.dumps({str(i): {"Question": f"Describe color {i}"} for i in range(5)})
    )
    return directory


def credentials(monkeypatch):
    for prefix in ["ATTACKER", "VICTIM", "FEEDBACK", "IMAGE"]:
        monkeypatch.setenv(f"{prefix}_MODEL_API_KEY", "offline-test-placeholder")


def test_smoke():
    assert run().total_metric_calls == 4


def test_real_adapter_with_mock_clients(tmp_path, monkeypatch):
    from metajailbreak_vlm.adapter import MyGUIAttackAdapter
    from metajailbreak_vlm.images import pil_to_base64
    from metajailbreak_vlm.prompts import seed_candidate
    from PIL import Image

    credentials(monkeypatch)
    monkeypatch.chdir(tmp_path)
    adapter = MyGUIAttackAdapter(build_configuration())
    adapter.attacker_llm.chat = Mock(
        side_effect=[
            (
                "[THINKING]color[/THINKING][IMAGE_PROMPT]blue square[/IMAGE_PROMPT][ANCHOR_PROMPT]Describe the color[/ANCHOR_PROMPT]",
                [],
            ),
            ("[ATTACK_PROMPT]Name the color again[/ATTACK_PROMPT]", []),
        ]
    )
    adapter.t2i_model.generate = Mock(
        return_value=(pil_to_base64(Image.new("RGB", (8, 8), "blue")), {})
    )
    adapter.victim_vlm.chat = Mock(
        side_effect=[("blue", []), ("blue", []), ("mock explanation", [])]
    )
    adapter.feedback_client.chat = Mock(return_value=("#thescore: 1", []))
    task = dict(
        task_id="color_1", instruction="Describe blue", category="color", source="Train"
    )
    result = adapter.evaluate([task], dict(seed_candidate), capture_traces=True)
    assert result.outputs == ["blue"]
    assert result.scores == [0.0]
    assert len(result.trajectories) == 1
    assert list(tmp_path.rglob("*.jpg"))
    assert list(tmp_path.rglob("result.json"))
    feedback = adapter.make_reflective_dataset(dict(seed_candidate), result)
    assert all(feedback[key] for key in seed_candidate)


def test_dotenv_quotes_and_precedence(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text('ATTACKER_MODEL_NAME="quoted"\nVICTIM_MODEL_NAME=from-file\n')
    monkeypatch.setenv("VICTIM_MODEL_NAME", "from-shell")
    load_dotenv(path)
    config = build_configuration()
    assert config.attacker_model_name == "quoted"
    assert config.victim_model_name == "from-shell"


def test_split(tasks):
    data = load_dataset_from_directory(tasks, "Train")
    train, validation = split_dataset(data)
    assert (len(train), len(validation)) == (3, 2)
    assert not {t["task_id"] for t in train} & {t["task_id"] for t in validation}
    assert split_dataset(data) == (train, validation)
    with pytest.raises(ValueError, match="at least"):
        split_dataset(data[:2])


@pytest.mark.parametrize(
    "body", ["{broken", "[]", '{"1": 9}', '{"1": {"Question": ""}}']
)
def test_invalid_data(tasks, body):
    (tasks / "sample.json").write_text(body)
    with pytest.raises(ValueError):
        load_dataset_from_directory(tasks, "Train")


def test_explicit_missing_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("VLM_TRAIN_DIR", "missing")
    with pytest.raises(FileNotFoundError):
        resolve_train_dir(tmp_path)
    monkeypatch.setenv("VLM_SEED_STRATEGY", "missing.json")
    with pytest.raises(FileNotFoundError):
        load_seed_candidate(tmp_path)


def test_cli_check(tasks, monkeypatch, capsys):
    credentials(monkeypatch)
    assert main(["--train-dir", str(tasks), "--check"]) == 0
    assert "3 train, 2 validation" in capsys.readouterr().out


def test_cli_missing_credentials(capsys):
    assert main(["--env-file", "/nonexistent/config.env", "--check"]) == 1
    assert "credentials" in capsys.readouterr().err


def test_invalid_budget(tasks, monkeypatch):
    credentials(monkeypatch)
    assert main(["--train-dir", str(tasks), "--max-metric-calls", "-1", "--check"]) == 1


def test_chat_transport(monkeypatch):
    client = VLMChatClient("test", "https://example.invalid/v1/", "mock")
    post = Mock(
        return_value=Mock(
            status_code=200,
            json=lambda: {"choices": [{"message": {"content": "blue"}}]},
        )
    )
    monkeypatch.setattr(client.session, "post", post)
    text, _ = client.chat(prompt="Describe the color")
    assert text == "blue"
    assert post.call_args.args[0] == "https://example.invalid/v1/chat/completions"


def test_image_transport(monkeypatch):
    post = Mock(
        return_value=Mock(
            status_code=200,
            json=lambda: {"data": [{"url": "https://example.invalid/image.png"}]},
        )
    )
    monkeypatch.setattr("metajailbreak_vlm.clients.requests.post", post)
    url, _ = ImageGenerationClient(
        "test", "https://example.invalid/v1", "mock"
    ).generate("a blue square")
    assert url.endswith("image.png")
    assert post.call_args.args[0].endswith("/images/generations")


def test_full_cli_with_mock_adapter(tasks, tmp_path, monkeypatch):
    from metajailbreak_vlm import runner

    credentials(monkeypatch)
    monkeypatch.chdir(tmp_path)

    class Adapter:
        def __init__(self, args):
            pass

        def evaluate(self, batch, candidate, capture_traces=False):
            return EvalBatch(
                outputs=["mock"] * len(batch),
                scores=[1.0] * len(batch),
                trajectories=["mock"] * len(batch) if capture_traces else None,
            )

        def make_reflective_dataset(self, *args):
            return {}

    monkeypatch.setattr(runner, "MyGUIAttackAdapter", Adapter)
    before = sys.stdout, sys.stderr
    assert (
        main(
            [
                "--train-dir",
                str(tasks),
                "--max-metric-calls",
                "2",
                "--output",
                "results/test.json",
            ]
        )
        == 0
    )
    assert (sys.stdout, sys.stderr) == before
    assert json.loads((tmp_path / "results/test.json").read_text())
    assert list((tmp_path / "logs").glob("*.txt"))


def test_stream_restoration_on_failure(tasks, tmp_path, monkeypatch):
    from metajailbreak_vlm import runner

    credentials(monkeypatch)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        runner, "main", Mock(side_effect=RuntimeError("simulated failure"))
    )
    before = sys.stdout, sys.stderr
    assert main(["--train-dir", str(tasks)]) == 1
    assert (sys.stdout, sys.stderr) == before
