import json
from types import SimpleNamespace

import pytest
from deepeval.dataset import Golden

from evals import generate
from evals.run import load_goldens

pytestmark = pytest.mark.unit


def test_generation_masks_contacts_and_saves_runner_compatible_goldens(
    monkeypatch, tmp_path
):
    corpus = tmp_path / "corpus.json"
    corpus.write_text(
        json.dumps(
            [
                {"title": "Часы", "content": "До 21:00. Телефон +79997778801."},
                {"title": "Кредит", "content": "Первоначальный взнос от 10%."},
            ]
        )
    )
    output = tmp_path / "goldens.json"
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("AG2_MODEL", "test-model")
    monkeypatch.setattr(
        "sys.argv",
        [
            "generate",
            "--corpus",
            str(corpus),
            "--output",
            str(output),
            "--limit-contexts",
            "1",
            "--num-evolutions",
            "3",
        ],
    )
    calls = []

    def synthesize(**kwargs):
        calls.append(kwargs)
        assert len(kwargs["contexts"]) == 1
        assert "+79997778801" not in repr(kwargs)
        assert "[PHONE_1]" in kwargs["contexts"][0][0]
        assert kwargs["include_expected_output"] is True
        assert kwargs["source_files"] == [str(corpus)]
        return [
            Golden(
                input="До скольких работает салон?",
                expected_output="Салон работает до 21:00.",
                context=kwargs["contexts"][0],
                additional_metadata={
                    "evolutions": ["Reasoning", "Constrained", "Reasoning"],
                    "synthetic_input_quality": 0.9,
                },
            )
        ]

    def synthesizer(**kwargs):
        assert kwargs["model"] == "fake-model"
        assert kwargs["evolution_config"].num_evolutions == 3
        assert sum(kwargs["evolution_config"].evolutions.values()) == pytest.approx(1)
        return SimpleNamespace(generate_goldens_from_contexts=synthesize)

    monkeypatch.setattr(generate, "OpenRouterModel", lambda **kwargs: "fake-model")
    monkeypatch.setattr(generate, "Synthesizer", synthesizer)
    generate.main()
    [golden] = load_goldens(output, "test", 10)
    assert golden.name == "synthetic_0001"
    assert golden.expected_output == "Салон работает до 21:00."
    assert golden.additional_metadata["evolutions"] == [
        "Reasoning",
        "Constrained",
        "Reasoning",
    ]
    assert golden.additional_metadata["synthetic_input_quality"] == 0.9
    assert "+79997778801" not in output.read_text()
    saved = output.read_bytes()
    with pytest.raises(SystemExit):
        generate.main()
    assert len(calls) == 1
    assert output.read_bytes() == saved
