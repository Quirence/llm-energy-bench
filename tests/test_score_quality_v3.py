"""Scoring rules of the quality-v3 preregistration (section 7) and its statistics."""

from __future__ import annotations

import importlib.util
import math
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "score_quality_v3", Path(__file__).resolve().parents[1] / "scripts" / "score_quality_v3.py"
)
assert _SPEC and _SPEC.loader
score = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(score)


@pytest.mark.parametrize(
    ("text", "gold", "correct", "strict"),
    [
        ("42", "42", 1, 1),
        ("42.", "42", 1, 1),
        (" 42 \n", "42", 1, 1),
        ("**42**", "42", 1, 0),
        ("2 125", "2125", 1, 0),
        ("2 125", "2125", 1, 0),
        ("2,125", "2125", 1, 0),
        ("1 234 567", "1234567", 1, 0),
        ("12,5", "12", 0, 0),
        ("222 − 220 = 2", "2", 1, 0),
        ("-5", "-5", 1, 1),
        ("10 + 21 = 31, значит 8", "31", 0, 0),
        ("Нет ответа", "3", 0, 0),
    ],
)
def test_direct_mode(text: str, gold: str, correct: int, strict: int) -> None:
    assert score.score_correct(text, gold, "direct") == correct
    assert score.score_strict(text, gold, "direct") == strict


@pytest.mark.parametrize(
    ("text", "gold", "correct", "strict"),
    [
        ("5 + 7 = 12\nОтвет: 12", "12", 1, 1),
        ("5 + 7 = 12\n\nОтвет: 12\n\n", "12", 1, 1),
        ("**Ответ: 2**\n\nОтвет: 2", "2", 1, 1),
        ("**Ответ: 2**", "2", 1, 0),
        ("Ответ: 3\nПроверка: 3 + 1 = 4", "3", 1, 0),
        ("Ответ: 3\nОтвет: 4", "3", 0, 0),
        ("итого 7 мотков", "7", 1, 0),
        ("ответ: 2 125", "2125", 1, 0),
        ("Ответ: 12", "13", 0, 0),
    ],
)
def test_cot_mode(text: str, gold: str, correct: int, strict: int) -> None:
    assert score.score_correct(text, gold, "cot") == correct
    assert score.score_strict(text, gold, "cot") == strict


def test_wilson_matches_reference_values() -> None:
    low, high = score.wilson(50, 100)
    assert low == pytest.approx(0.4038, abs=1e-4)
    assert high == pytest.approx(0.5962, abs=1e-4)
    assert all(math.isnan(v) for v in score.wilson(0, 0))


def test_exact_mcnemar() -> None:
    result = score.mcnemar_exact(6, 13)
    assert result["p_two_sided"] == pytest.approx(0.16707, abs=1e-5)
    assert result["p_one_sided_b_gt_c"] == pytest.approx(0.96822, abs=1e-5)
    assert score.mcnemar_exact(0, 0)["p_two_sided"] == 1.0


def test_holm_is_monotone_and_capped() -> None:
    adjusted = score.holm({"H1": 0.01, "H2": 0.04, "H3": 0.5})
    assert adjusted == pytest.approx({"H1": 0.03, "H2": 0.08, "H3": 0.5})
    assert score.holm({"a": 0.6, "b": 0.7}) == {"a": 1.0, "b": 1.0}


def _row(model: str, item: str, correct: int, strict: int, pass_no: int = 1) -> dict:
    return {
        "model": model,
        "item": item,
        "correct": correct,
        "strict": strict,
        "energy_j": 1.0,
        "energy_instant_j": 1.0,
        "latency_s": 1.0,
        "pass": pass_no,
    }


def test_format_violation_uses_majority_over_passes() -> None:
    rows = [
        _row(score.LLAMA_Q4, "a", 1, 0, 1),
        _row(score.LLAMA_Q4, "a", 1, 0, 2),
        _row(score.LLAMA_Q4, "a", 1, 1, 3),
        _row(score.QWEN_Q4, "a", 1, 1, 1),
        _row(score.QWEN_Q4, "a", 1, 0, 2),
        _row(score.QWEN_Q4, "a", 1, 1, 3),
    ]
    result = score.format_violation_mcnemar(rows)
    assert (result["violations_llama"], result["violations_qwen"]) == (1, 0)
    assert (result["b"], result["c"]) == (1, 0)


def test_cost_per_correct_pools_passes() -> None:
    table = score.per_item(
        [_row("m", "a", 1, 1, 1), _row("m", "a", 0, 0, 2), _row("m", "b", 1, 1, 1)], "m"
    )
    assert score.cost_per_correct(table, ["a", "b"], "energy_j") == pytest.approx(1.5)
    assert score.cost_per_correct(table, ["a"], "energy_j") == pytest.approx(2.0)


def test_instant_power_energy_is_a_trapezoid_over_sorted_samples() -> None:
    samples = [
        {"monotonic_s": 1.0, "power_instant_watts": 20.0},
        {"monotonic_s": 0.0, "power_instant_watts": 10.0},
        {"monotonic_s": 1.0, "power_instant_watts": 30.0},
        {"monotonic_s": 2.0, "power_instant_watts": None},
        {"monotonic_s": 3.0, "power_instant_watts": 30.0},
    ]
    assert score.instant_power_energy(samples) == pytest.approx(20.0 + 60.0)
    assert score.instant_power_energy(samples[:1]) is None
