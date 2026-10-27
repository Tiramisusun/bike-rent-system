"""The comparison inputs are complete: every model is configured, every question translated."""

from pathlib import Path

import yaml

EVALS = Path(__file__).resolve().parents[1] / "evals"


def test_every_benchmark_question_has_german_and_chinese_text():
    ids = [q["id"] for q in yaml.safe_load((EVALS / "benchmark.yaml").read_text())]
    texts = yaml.safe_load((EVALS / "benchmark_i18n.yaml").read_text())
    assert sorted(texts) == sorted(ids)
    assert all(texts[i].get("de") and texts[i].get("zh") for i in ids)


def test_every_model_has_a_key_variable_and_a_price():
    models = yaml.safe_load((EVALS / "models.yaml").read_text())["models"]
    for name, m in models.items():
        assert m["base_url"].startswith("https://") and m["api_key_env"].endswith("_KEY"), name
        assert m["model"] and m["price"]["input"] > 0 and m["price"]["output"] > 0, name
