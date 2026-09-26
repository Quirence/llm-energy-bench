"""Statistical evaluation of rank inversion between speed and energy.

The reports already say whether speed-only and energy-aware rankings pick the
same configuration. This module decides whether a difference is worth
believing, under the criteria fixed in ``docs/research-plan.md`` before any
data was collected.

A decision block is one host and one prompt category. Within a block the
configurations are the models measured on that host; a configuration is
eligible only when its quality over all scored prompts reaches the 75% floor.

A disagreement counts only when both of these hold:

* its relative effect reaches ``max(5%, 3 x max(CV_speed, CV_energy))``,
  where the CVs come from three independently launched calibration runs on the
  same host and prompt category, so a difference smaller than the
  measurement's own noise never overturns a conclusion;
* a bootstrap 95% confidence interval for the effect excludes zero.

Without calibration data materiality cannot be judged, so a disagreement in
an uncalibrated block keeps the verdict inconclusive instead of being waved
through with a guessed threshold.

The thresholds are deliberately fixed in code rather than chosen per dataset.
Picking them after seeing results is how an honest negative turns into a
positive.

The bootstrap is hierarchical: each draw samples prompt IDs with replacement,
then repetitions within every selected prompt, and recomputes the aggregate
ratio from resampled totals. Prompt IDs are shared between the two compared
configurations because both answered the same prompts.
"""

from __future__ import annotations

import random
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

MINIMUM_EFFECT = 0.05
CV_MULTIPLIER = 3.0
QUALITY_FLOOR = 0.75
AGREEMENT_FLOOR = 0.90
CONFIDENCE = 0.95
BOOTSTRAP_ITERATIONS = 10_000
BOOTSTRAP_SEED = 42
CALIBRATION_RUNS = 3

LIMITATIONS = (
    "Energy is measured through NVML on the GPU only. It excludes the "
    "processor, system memory, power-supply losses, and cooling, so no "
    "wall-energy or total-cost-of-ownership claim follows from these numbers. "
    "Any cost shown is a GPU-only electricity estimate."
)

# One request as (output tokens, energy in joules, latency in seconds).
Request = tuple[float, float, float]


class AnalysisError(ValueError):
    """Run artifacts cannot support the analysis without guessing."""


class HypothesisOutcome(StrEnum):
    """What the data says about energy-aware ranking changing the choice."""

    UNSUPPORTED = "unsupported"
    MATERIAL_INVERSION = "material_inversion"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True, slots=True)
class BlockMeasurements:
    """One configuration's valid requests within one decision block.

    ``prompts`` maps each prompt ID to its repetitions, which the hierarchical
    bootstrap needs. ``quality_score`` belongs to the configuration as a whole,
    not to this block, so a block without scored prompts cannot rescue a
    configuration that failed the scored ones.
    """

    label: str
    block: str
    prompts: Mapping[str, tuple[Request, ...]]
    quality_score: float | None

    @property
    def eligible(self) -> bool:
        """Only a configuration that answers correctly enough may be ranked."""
        return self.quality_score is not None and self.quality_score >= QUALITY_FLOOR

    @property
    def requests(self) -> tuple[Request, ...]:
        return tuple(request for prompt in sorted(self.prompts) for request in self.prompts[prompt])

    @property
    def tokens_per_second(self) -> float | None:
        requests = self.requests
        return aggregate_ratio([r[0] for r in requests], [r[2] for r in requests])

    @property
    def tokens_per_joule(self) -> float | None:
        requests = self.requests
        return aggregate_ratio([r[0] for r in requests], [r[1] for r in requests])


@dataclass(frozen=True, slots=True)
class Inversion:
    """One decision block where speed and energy disagreed."""

    block: str
    speed_winner: str
    energy_winner: str
    relative_effect: float | None
    threshold: float | None
    ci_low: float | None
    ci_high: float | None
    material: bool
    reason: str

    @property
    def assessable(self) -> bool:
        """Whether materiality could be decided at all for this block."""
        return self.threshold is not None and self.relative_effect is not None

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__slots__}


@dataclass(frozen=True, slots=True)
class HypothesisVerdict:
    """The pre-registered verdict, with everything needed to check it."""

    outcome: HypothesisOutcome
    blocks_evaluated: int
    blocks_in_agreement: int
    agreement_rate: float | None
    inversions: tuple[Inversion, ...]
    excluded: tuple[str, ...]
    statement: str
    limitations: str = LIMITATIONS
    configurations: tuple[str, ...] = field(default_factory=tuple)

    @property
    def material_inversions(self) -> tuple[Inversion, ...]:
        return tuple(inversion for inversion in self.inversions if inversion.material)

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome.value,
            "blocks_evaluated": self.blocks_evaluated,
            "blocks_in_agreement": self.blocks_in_agreement,
            "agreement_rate": self.agreement_rate,
            "inversions": [inversion.to_dict() for inversion in self.inversions],
            "excluded": list(self.excluded),
            "configurations": list(self.configurations),
            "statement": self.statement,
            "limitations": self.limitations,
        }

    def render(self) -> str:
        lines = [
            "## Rank-inversion evaluation",
            "",
            self.statement,
            "",
            f"- Decision blocks (host x prompt category) evaluated: {self.blocks_evaluated}",
            f"- Blocks where speed and energy agreed: {self.blocks_in_agreement}"
            + (
                ""
                if self.agreement_rate is None
                else f" ({self.agreement_rate:.0%}, floor {AGREEMENT_FLOOR:.0%})"
            ),
            f"- Criteria: effect at least max({MINIMUM_EFFECT:.0%}, "
            f"{CV_MULTIPLIER:.0f} x max(CV_speed, CV_energy)) from "
            f"{CALIBRATION_RUNS} calibration runs, and a hierarchical bootstrap "
            f"{CONFIDENCE:.0%} confidence interval ({BOOTSTRAP_ITERATIONS:,} resamples, "
            f"seed {BOOTSTRAP_SEED}) excluding zero",
        ]
        if self.excluded:
            lines.append(
                f"- Excluded below the {QUALITY_FLOOR:.0%} quality floor: "
                f"{', '.join(self.excluded)}"
            )
        lines.append("")

        if self.inversions:
            lines += [
                "| Block | Speed winner | Energy winner | Effect | Threshold | 95% CI | Material |",
                "| --- | --- | --- | --- | --- | --- | --- |",
            ]
            for inversion in self.inversions:
                lines.append(
                    f"| {inversion.block} | {inversion.speed_winner} "
                    f"| {inversion.energy_winner} | {_percent(inversion.relative_effect)} "
                    f"| {_percent(inversion.threshold)} "
                    f"| {_interval(inversion.ci_low, inversion.ci_high)} "
                    f"| {'yes' if inversion.material else 'no'} |"
                )
            lines.append("")

        lines += [self.limitations, ""]
        return "\n".join(lines)


# --------------------------------------------------------------------------
# Statistics
# --------------------------------------------------------------------------


def aggregate_ratio(numerators: Sequence[float], denominators: Sequence[float]) -> float | None:
    """Total over total, the only ratio that survives being combined."""
    if not numerators or not denominators:
        return None
    total = sum(denominators)
    if total <= 0:
        return None
    return sum(numerators) / total


def repeatability_cv(values: Sequence[float]) -> float | None:
    """How much a repeated measurement moves, relative to its own mean."""
    if len(values) < 2:
        return None
    mean = statistics.fmean(values)
    if mean == 0:
        return None
    return abs(statistics.stdev(values) / mean)


def material_threshold(cv: float) -> float:
    """The smallest effect worth believing, given the measurement's noise."""
    return max(MINIMUM_EFFECT, CV_MULTIPLIER * cv)


def bootstrap_relative_effect_ci(
    challenger: Mapping[str, Sequence[tuple[float, float]]],
    baseline: Mapping[str, Sequence[tuple[float, float]]],
    *,
    confidence: float = CONFIDENCE,
    iterations: int = BOOTSTRAP_ITERATIONS,
    seed: int = BOOTSTRAP_SEED,
) -> tuple[float | None, float | None]:
    """Confidence interval for ``ratio(challenger) / ratio(baseline) - 1``.

    Both inputs map a prompt ID to its repetitions as ``(numerator,
    denominator)`` pairs. Every draw samples the shared prompt IDs with
    replacement, then repetitions within each selected prompt for each
    configuration, and recomputes both ratios from the resampled totals. The
    interval therefore describes the effect the verdict actually tests, and a
    prompt with many repetitions never outweighs one with few.
    """
    prompts = sorted(
        prompt
        for prompt in set(challenger) & set(baseline)
        if challenger[prompt] and baseline[prompt]
    )
    if not prompts:
        return None, None

    rng = random.Random(seed)
    effects: list[float] = []
    for _ in range(iterations):
        drawn = [prompts[rng.randrange(len(prompts))] for _ in prompts]
        a = _resampled_ratio(challenger, drawn, rng)
        b = _resampled_ratio(baseline, drawn, rng)
        if a is not None and b is not None and b > 0:
            effects.append(a / b - 1.0)

    if not effects:
        return None, None
    effects.sort()
    tail = (1.0 - confidence) / 2.0
    return _quantile(effects, tail), _quantile(effects, 1.0 - tail)


def _resampled_ratio(
    samples: Mapping[str, Sequence[tuple[float, float]]],
    prompts: Sequence[str],
    rng: random.Random,
) -> float | None:
    numerator = 0.0
    denominator = 0.0
    for prompt in prompts:
        repetitions = samples[prompt]
        for _ in repetitions:
            value, weight = repetitions[rng.randrange(len(repetitions))]
            numerator += value
            denominator += weight
    return numerator / denominator if denominator > 0 else None


def _quantile(sorted_values: Sequence[float], fraction: float) -> float:
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = fraction * (len(sorted_values) - 1)
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = position - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


# --------------------------------------------------------------------------
# The verdict
# --------------------------------------------------------------------------


def evaluate_hypothesis(
    measurements: Sequence[BlockMeasurements],
    repeatability: Mapping[str, float] | None = None,
    *,
    seed: int = BOOTSTRAP_SEED,
    iterations: int = BOOTSTRAP_ITERATIONS,
) -> HypothesisVerdict:
    """Apply the pre-registered criteria to a frozen dataset.

    ``repeatability`` maps a decision block to ``max(CV_speed, CV_energy)``
    from its calibration runs; see :func:`calibration_repeatability`.
    """
    repeatability = repeatability or {}
    excluded = tuple(sorted({m.label for m in measurements if not m.eligible}))
    eligible = [m for m in measurements if m.eligible]
    labels = tuple(sorted({m.label for m in eligible}))

    by_block: dict[str, list[BlockMeasurements]] = {}
    for measurement in eligible:
        by_block.setdefault(measurement.block, []).append(measurement)
    comparable = {
        name: entries for name, entries in by_block.items() if len({e.label for e in entries}) > 1
    }

    if not comparable:
        return HypothesisVerdict(
            outcome=HypothesisOutcome.INCONCLUSIVE,
            blocks_evaluated=0,
            blocks_in_agreement=0,
            agreement_rate=None,
            inversions=(),
            excluded=excluded,
            configurations=labels,
            statement=_no_comparison_statement(labels, excluded),
        )

    inversions: list[Inversion] = []
    agreed = 0
    for name in sorted(comparable):
        entries = comparable[name]
        speed_winner = _winner(entries, "tokens_per_second")
        energy_winner = _winner(entries, "tokens_per_joule")
        if speed_winner is None or energy_winner is None:
            continue
        if speed_winner.label == energy_winner.label:
            agreed += 1
            continue
        inversions.append(
            _assess(
                name,
                speed_winner,
                energy_winner,
                repeatability.get(name),
                seed=seed,
                iterations=iterations,
            )
        )

    evaluated = agreed + len(inversions)
    rate = agreed / evaluated if evaluated else None
    material = [inversion for inversion in inversions if inversion.material]
    unassessed = [inversion for inversion in inversions if not inversion.assessable]

    if material:
        outcome = HypothesisOutcome.MATERIAL_INVERSION
    elif rate is not None and rate >= AGREEMENT_FLOOR and not unassessed:
        outcome = HypothesisOutcome.UNSUPPORTED
    else:
        outcome = HypothesisOutcome.INCONCLUSIVE

    return HypothesisVerdict(
        outcome=outcome,
        blocks_evaluated=evaluated,
        blocks_in_agreement=agreed,
        agreement_rate=rate,
        inversions=tuple(inversions),
        excluded=excluded,
        configurations=labels,
        statement=_statement(outcome, agreed, evaluated, rate, material, unassessed),
    )


def _winner(entries: Sequence[BlockMeasurements], metric: str) -> BlockMeasurements | None:
    ranked = [entry for entry in entries if getattr(entry, metric) is not None]
    if not ranked:
        return None
    # Ties break on the label so a verdict never depends on input ordering.
    return max(ranked, key=lambda entry: (getattr(entry, metric), entry.label))


def _assess(
    block: str,
    speed_winner: BlockMeasurements,
    energy_winner: BlockMeasurements,
    cv: float | None,
    *,
    seed: int,
    iterations: int,
) -> Inversion:
    """Decide whether one block's disagreement is large and stable enough to matter."""
    baseline = speed_winner.tokens_per_joule
    challenger = energy_winner.tokens_per_joule
    effect = None
    if baseline is not None and challenger is not None and baseline > 0:
        effect = (challenger - baseline) / baseline

    threshold = None if cv is None else material_threshold(cv)

    low, high = bootstrap_relative_effect_ci(
        _energy_pairs(energy_winner),
        _energy_pairs(speed_winner),
        iterations=iterations,
        seed=seed,
    )
    excludes_zero = low is not None and high is not None and (low > 0 or high < 0)

    if effect is None:
        reason = "the energy metric is unavailable for one configuration"
    elif threshold is None:
        reason = (
            f"no {CALIBRATION_RUNS}-run calibration exists for this block, so "
            "materiality cannot be assessed"
        )
    elif abs(effect) < threshold:
        reason = (
            f"the {abs(effect):.1%} effect is below the {threshold:.1%} threshold set by "
            "repeatability"
        )
    elif not excludes_zero:
        reason = "the bootstrap 95% confidence interval crosses zero"
    else:
        reason = "the effect exceeds the repeatability threshold and the interval excludes zero"

    material = (
        effect is not None and threshold is not None and abs(effect) >= threshold and excludes_zero
    )
    return Inversion(
        block=block,
        speed_winner=speed_winner.label,
        energy_winner=energy_winner.label,
        relative_effect=effect,
        threshold=threshold,
        ci_low=low,
        ci_high=high,
        material=material,
        reason=reason,
    )


def _energy_pairs(measurement: BlockMeasurements) -> dict[str, tuple[tuple[float, float], ...]]:
    return {
        prompt: tuple((tokens, energy) for tokens, energy, _latency in requests)
        for prompt, requests in measurement.prompts.items()
    }


def _statement(
    outcome: HypothesisOutcome,
    agreed: int,
    evaluated: int,
    rate: float | None,
    material: Sequence[Inversion],
    unassessed: Sequence[Inversion],
) -> str:
    if outcome is HypothesisOutcome.UNSUPPORTED:
        return (
            f"Speed-only and energy-aware ranking selected the same configuration in "
            f"{agreed} of {evaluated} decision blocks ({rate:.0%}), at or above the "
            f"{AGREEMENT_FLOOR:.0%} floor, and no material rank inversion was found. "
            "The hypothesis is reported as unsupported in the tested scope. This is a "
            "valid result: it says energy-aware metrics did not change the engineering "
            "choice here, not that they cannot elsewhere."
        )
    if outcome is HypothesisOutcome.MATERIAL_INVERSION:
        blocks = ", ".join(inversion.block for inversion in material)
        return (
            f"Speed-only and energy-aware ranking selected different configurations in "
            f"{len(material)} decision block(s) ({blocks}) by a margin exceeding the "
            "repeatability threshold, with a bootstrap 95% confidence interval that "
            "excludes zero. The hypothesis is supported in the tested scope."
        )
    if rate is None:
        return "No comparable decision block was available, so no verdict is recorded."
    if unassessed:
        blocks = ", ".join(inversion.block for inversion in unassessed)
        return (
            f"Speed and energy agreed in {agreed} of {evaluated} decision blocks "
            f"({rate:.0%}), but the disagreement in {blocks} could not be assessed "
            "because calibration data or the energy metric is missing. The result is "
            "inconclusive until that data exists; neither verdict is recorded."
        )
    return (
        f"Speed and energy agreed in {agreed} of {evaluated} decision blocks "
        f"({rate:.0%}), below the {AGREEMENT_FLOOR:.0%} floor, but no disagreement was "
        "large or stable enough to count as a material inversion. The result is "
        "inconclusive in the tested scope; neither verdict is recorded."
    )


def _no_comparison_statement(labels: Sequence[str], excluded: Sequence[str]) -> str:
    if len(labels) < 2:
        base = (
            "Only one configuration was eligible, so no ranking comparison is possible "
            "and no verdict is recorded."
        )
    else:
        base = (
            "No decision block contained two eligible configurations, so no ranking "
            "comparison is possible and no verdict is recorded."
        )
    if excluded:
        base += (
            f" Excluded below the {QUALITY_FLOOR:.0%} quality floor or without a "
            f"quality score: {', '.join(excluded)}."
        )
    return base


def _percent(value: float | None) -> str:
    return "—" if value is None else f"{value:+.1%}"


def _interval(low: float | None, high: float | None) -> str:
    if low is None or high is None:
        return "—"
    return f"[{low:+.1%}, {high:+.1%}]"


# --------------------------------------------------------------------------
# Bridge from run artifacts
# --------------------------------------------------------------------------


def block_name(host: str, category: str) -> str:
    """The decision block for one host and prompt category."""
    return f"{host} / {category}"


def blocks_from_records(
    records: Sequence[Mapping[str, Any]], manifests: Mapping[str, Mapping[str, Any]]
) -> tuple[BlockMeasurements, ...]:
    """Group valid request records into per-configuration decision blocks.

    A configuration is one host and model pair. Its quality score averages
    repetitions of each scored prompt first and then prompt IDs, over every
    category, so eligibility is a property of the configuration rather than of
    whichever block happens to contain the scored prompts.
    """
    requests: dict[tuple[str, str, str], dict[str, list[Request]]] = {}
    quality: dict[tuple[str, str], dict[str, list[float]]] = {}

    for record in records:
        metrics = record.get("metrics")
        if not isinstance(metrics, Mapping):
            continue
        host = _host(record, manifests)
        model = str(record.get("model") or "unknown")
        category = str(record.get("prompt_category") or metrics.get("prompt_category") or "")
        prompt = str(record.get("prompt_id") or metrics.get("prompt_id") or "")

        score = metrics.get("quality_score")
        if isinstance(score, (int, float)) and not isinstance(score, bool):
            quality.setdefault((host, model), {}).setdefault(prompt, []).append(float(score))

        request = _request(metrics)
        if request is not None:
            by_prompt = requests.setdefault((host, model, category), {})
            by_prompt.setdefault(prompt, []).append(request)

    blocks = []
    for (host, model, category), by_prompt in sorted(requests.items()):
        scores = quality.get((host, model))
        blocks.append(
            BlockMeasurements(
                label=f"{host} / {model}",
                block=block_name(host, category),
                prompts={prompt: tuple(by_prompt[prompt]) for prompt in sorted(by_prompt)},
                quality_score=(
                    statistics.fmean(statistics.fmean(values) for values in scores.values())
                    if scores
                    else None
                ),
            )
        )
    return tuple(blocks)


def calibration_repeatability(
    records: Sequence[Mapping[str, Any]], manifests: Mapping[str, Mapping[str, Any]]
) -> dict[str, float]:
    """``max(CV_speed, CV_energy)`` per decision block from calibration runs.

    Each run contributes one run-level aggregate per host, model, and prompt
    category: total output tokens over total latency and over total energy.
    The CV is taken across runs, so it measures how much an independently
    launched repetition of the whole run moves. A block needs at least
    ``CALIBRATION_RUNS`` runs; with several calibration models on one host the
    largest CV is kept.
    """
    totals: dict[tuple[str, str, str], dict[str, list[float]]] = {}
    for record in records:
        metrics = record.get("metrics")
        if not isinstance(metrics, Mapping):
            continue
        request = _request(metrics)
        if request is None:
            continue
        host = _host(record, manifests)
        model = str(record.get("model") or "unknown")
        category = str(record.get("prompt_category") or metrics.get("prompt_category") or "")
        run = totals.setdefault((host, model, category), {}).setdefault(
            str(record.get("run_id") or ""), [0.0, 0.0, 0.0]
        )
        for index, value in enumerate(request):
            run[index] += value

    repeatability: dict[str, float] = {}
    for (host, _model, category), runs in totals.items():
        if len(runs) < CALIBRATION_RUNS:
            continue
        speed = repeatability_cv([tokens / latency for tokens, _energy, latency in runs.values()])
        energy = repeatability_cv([tokens / energy for tokens, energy, _latency in runs.values()])
        if speed is None or energy is None:
            continue
        name = block_name(host, category)
        repeatability[name] = max(repeatability.get(name, 0.0), speed, energy)
    return repeatability


def _host(record: Mapping[str, Any], manifests: Mapping[str, Mapping[str, Any]]) -> str:
    run_id = str(record.get("run_id") or "")
    host = (manifests.get(run_id) or {}).get("host_id")
    if not isinstance(host, str) or not host:
        raise AnalysisError(f"run {run_id!r} has no host_id in its manifest")
    return host


def _request(metrics: Mapping[str, Any]) -> Request | None:
    tokens = _positive(metrics.get("output_tokens"))
    energy = _positive(metrics.get("gpu_energy_joules"))
    latency = _positive(metrics.get("latency_seconds"))
    if tokens is None or energy is None or latency is None:
        return None
    return tokens, energy, latency


def _positive(value: Any) -> float | None:
    """Accept only a usable positive number; anything else is missing data."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if number > 0 else None
