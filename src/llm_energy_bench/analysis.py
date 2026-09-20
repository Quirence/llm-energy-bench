"""Statistical evaluation of rank inversion between speed and energy.

The reports already say whether speed-only and energy-aware rankings pick the
same configuration. This module decides whether a difference is worth
believing, under the criteria fixed in the approved design before any data was
collected.

A disagreement counts only when both of these hold:

* its relative effect reaches ``max(5%, 3 x repeatability CV)``, so a
  difference smaller than the measurement's own noise never overturns a
  conclusion;
* a bootstrap 95% confidence interval for the difference excludes zero.

The thresholds are deliberately fixed in code rather than chosen per dataset.
Picking them after seeing results is how an honest negative turns into a
positive.

Bootstrap resampling is over requests, and every draw recomputes the aggregate
ratio from resampled totals. Resampling per-request ratios instead would let a
tiny request weigh as much as a long one, which the analysis rules forbid.
"""

from __future__ import annotations

import random
import statistics
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

MINIMUM_EFFECT = 0.05
CV_MULTIPLIER = 3.0
QUALITY_FLOOR = 0.75
AGREEMENT_FLOOR = 0.90
CONFIDENCE = 0.95
BOOTSTRAP_ITERATIONS = 2000
BOOTSTRAP_SEED = 42

LIMITATIONS = (
    "Energy is measured through NVML on the GPU only. It excludes the "
    "processor, system memory, power-supply losses, and cooling, so no "
    "wall-energy or total-cost-of-ownership claim follows from these numbers. "
    "Any cost shown is a GPU-only electricity estimate."
)


class HypothesisOutcome(StrEnum):
    """What the data says about energy-aware ranking changing the choice."""

    UNSUPPORTED = "unsupported"
    MATERIAL_INVERSION = "material_inversion"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True, slots=True)
class BlockMeasurements:
    """One configuration's requests within one workload block."""

    label: str
    block: str
    output_tokens: tuple[float, ...]
    energy_joules: tuple[float, ...]
    latency_seconds: tuple[float, ...]
    quality_score: float | None = None

    @property
    def eligible(self) -> bool:
        """Only a configuration that answers correctly enough may be ranked."""
        return self.quality_score is None or self.quality_score >= QUALITY_FLOOR

    @property
    def tokens_per_second(self) -> float | None:
        return aggregate_ratio(self.output_tokens, self.latency_seconds)

    @property
    def tokens_per_joule(self) -> float | None:
        return aggregate_ratio(self.output_tokens, self.energy_joules)

    def repeatability(self) -> float | None:
        """Spread of the per-request energy cost, used to size a real effect."""
        per_request = [
            energy / tokens
            for tokens, energy in zip(self.output_tokens, self.energy_joules, strict=False)
            if tokens
        ]
        return repeatability_cv(per_request)


@dataclass(frozen=True, slots=True)
class Inversion:
    """One workload block where speed and energy disagreed."""

    block: str
    speed_winner: str
    energy_winner: str
    relative_effect: float | None
    threshold: float
    ci_low: float | None
    ci_high: float | None
    material: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {field: getattr(self, field) for field in self.__slots__}


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
            f"- Workload blocks evaluated: {self.blocks_evaluated}",
            f"- Blocks where speed and energy agreed: {self.blocks_in_agreement}"
            + (
                ""
                if self.agreement_rate is None
                else f" ({self.agreement_rate:.0%}, floor {AGREEMENT_FLOOR:.0%})"
            ),
            f"- Criteria: effect at least max({MINIMUM_EFFECT:.0%}, "
            f"{CV_MULTIPLIER:.0f} x repeatability CV) and a bootstrap "
            f"{CONFIDENCE:.0%} confidence interval excluding zero",
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


def material_threshold(cv: float | None) -> float:
    """The smallest effect worth believing, given the measurement's noise."""
    if cv is None:
        return MINIMUM_EFFECT
    return max(MINIMUM_EFFECT, CV_MULTIPLIER * cv)


def bootstrap_ratio_difference_ci(
    a_numerators: Sequence[float],
    a_denominators: Sequence[float],
    b_numerators: Sequence[float],
    b_denominators: Sequence[float],
    *,
    confidence: float = CONFIDENCE,
    iterations: int = BOOTSTRAP_ITERATIONS,
    seed: int = BOOTSTRAP_SEED,
) -> tuple[float | None, float | None]:
    """Confidence interval for ``ratio(a) - ratio(b)``, resampling requests.

    Each draw recomputes the aggregate ratio from resampled totals, so the
    interval describes the quantity the reports actually publish.
    """
    if aggregate_ratio(a_numerators, a_denominators) is None:
        return None, None
    if aggregate_ratio(b_numerators, b_denominators) is None:
        return None, None

    rng = random.Random(seed)
    differences: list[float] = []
    for _ in range(iterations):
        a = _resampled_ratio(a_numerators, a_denominators, rng)
        b = _resampled_ratio(b_numerators, b_denominators, rng)
        if a is not None and b is not None:
            differences.append(a - b)

    if not differences:
        return None, None
    differences.sort()
    tail = (1.0 - confidence) / 2.0
    return _quantile(differences, tail), _quantile(differences, 1.0 - tail)


def _resampled_ratio(
    numerators: Sequence[float], denominators: Sequence[float], rng: random.Random
) -> float | None:
    size = min(len(numerators), len(denominators))
    indices = [rng.randrange(size) for _ in range(size)]
    return aggregate_ratio([numerators[i] for i in indices], [denominators[i] for i in indices])


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
    *,
    seed: int = BOOTSTRAP_SEED,
    iterations: int = BOOTSTRAP_ITERATIONS,
) -> HypothesisVerdict:
    """Apply the pre-registered criteria to a frozen dataset."""
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
            _assess(name, speed_winner, energy_winner, seed=seed, iterations=iterations)
        )

    evaluated = agreed + len(inversions)
    rate = agreed / evaluated if evaluated else None
    material = [inversion for inversion in inversions if inversion.material]

    if material:
        outcome = HypothesisOutcome.MATERIAL_INVERSION
    elif rate is not None and rate >= AGREEMENT_FLOOR:
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
        statement=_statement(outcome, agreed, evaluated, rate, material),
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

    cv = max(
        (
            value
            for value in (speed_winner.repeatability(), energy_winner.repeatability())
            if value is not None
        ),
        default=None,
    )
    threshold = material_threshold(cv)

    low, high = bootstrap_ratio_difference_ci(
        energy_winner.output_tokens,
        energy_winner.energy_joules,
        speed_winner.output_tokens,
        speed_winner.energy_joules,
        iterations=iterations,
        seed=seed,
    )
    excludes_zero = low is not None and high is not None and (low > 0 or high < 0)

    if effect is None:
        reason = "the energy metric is unavailable for one configuration"
    elif abs(effect) < threshold:
        reason = (
            f"the {abs(effect):.1%} effect is below the {threshold:.1%} threshold set by "
            "repeatability"
        )
    elif not excludes_zero:
        reason = "the bootstrap 95% confidence interval crosses zero"
    else:
        reason = "the effect exceeds the repeatability threshold and the interval excludes zero"

    material = effect is not None and abs(effect) >= threshold and excludes_zero
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


def _statement(
    outcome: HypothesisOutcome,
    agreed: int,
    evaluated: int,
    rate: float | None,
    material: Sequence[Inversion],
) -> str:
    if outcome is HypothesisOutcome.UNSUPPORTED:
        return (
            f"Speed-only and energy-aware ranking selected the same configuration in "
            f"{agreed} of {evaluated} workload blocks ({rate:.0%}), at or above the "
            f"{AGREEMENT_FLOOR:.0%} floor, and no material rank inversion was found. "
            "The hypothesis is reported as unsupported in the tested scope. This is a "
            "valid result: it says energy-aware metrics did not change the engineering "
            "choice here, not that they cannot elsewhere."
        )
    if outcome is HypothesisOutcome.MATERIAL_INVERSION:
        blocks = ", ".join(inversion.block for inversion in material)
        return (
            f"Speed-only and energy-aware ranking selected different configurations in "
            f"{len(material)} workload block(s) ({blocks}) by a margin exceeding the "
            "repeatability threshold, with a bootstrap 95% confidence interval that "
            "excludes zero. The hypothesis is supported in the tested scope."
        )
    if rate is None:
        return "No comparable workload block was available, so no verdict is recorded."
    return (
        f"Speed and energy agreed in {agreed} of {evaluated} workload blocks "
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
            "No workload block contained two eligible configurations, so no ranking "
            "comparison is possible and no verdict is recorded."
        )
    if excluded:
        base += f" Excluded below the {QUALITY_FLOOR:.0%} quality floor: {', '.join(excluded)}."
    return base


def _percent(value: float | None) -> str:
    return "—" if value is None else f"{value:+.1%}"


def _interval(low: float | None, high: float | None) -> str:
    if low is None or high is None:
        return "—"
    return f"[{low:+.3g}, {high:+.3g}]"


# --------------------------------------------------------------------------
# Bridge from run artifacts
# --------------------------------------------------------------------------


def blocks_from_records(
    records: Sequence[dict[str, Any]], manifests: dict[str, dict[str, Any]] | None = None
) -> tuple[BlockMeasurements, ...]:
    """Group validated request records into per-configuration workload blocks.

    A workload block is one prompt category, matching how the reports already
    rank configurations. A configuration is one host and model pair, so the
    same model measured on two hosts stays comparable.
    """
    manifests = manifests or {}
    grouped: dict[tuple[str, str], dict[str, list[float]]] = {}
    quality: dict[tuple[str, str], list[float]] = {}

    for record in records:
        metrics = record.get("metrics")
        if not isinstance(metrics, dict):
            continue
        run_id = str(record.get("run_id", ""))
        host = str((manifests.get(run_id, {}).get("config") or {}).get("host_id") or run_id)
        label = f"{host} / {metrics.get('model') or record.get('model') or ''}"
        key = (label, str(metrics.get("prompt_category") or ""))

        tokens = _positive(metrics.get("output_tokens"))
        energy = _positive(metrics.get("gpu_energy_joules"))
        latency = _positive(metrics.get("latency_seconds"))
        if tokens is None or energy is None or latency is None:
            continue

        bucket = grouped.setdefault(key, {"tokens": [], "energy": [], "latency": []})
        bucket["tokens"].append(tokens)
        bucket["energy"].append(energy)
        bucket["latency"].append(latency)

        score = metrics.get("quality_score")
        if isinstance(score, (int, float)):
            quality.setdefault(key, []).append(float(score))

    blocks = []
    for (label, category), bucket in sorted(grouped.items()):
        scores = quality.get((label, category))
        blocks.append(
            BlockMeasurements(
                label=label,
                block=category,
                output_tokens=tuple(bucket["tokens"]),
                energy_joules=tuple(bucket["energy"]),
                latency_seconds=tuple(bucket["latency"]),
                quality_score=statistics.fmean(scores) if scores else None,
            )
        )
    return tuple(blocks)


def _positive(value: Any) -> float | None:
    """Accept only a usable positive number; anything else is missing data."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if number > 0 else None
