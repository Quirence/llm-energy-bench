"""Preregistered study-level analysis for the frozen two-GPU dataset.

The module deliberately accepts calibration and benchmark runs separately.  A
validated observation can still be useful evidence, but it cannot silently
increase the denominator of the primary two-host decision.
"""

from __future__ import annotations

import json
import math
import random
import statistics
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from llm_energy_bench.results import OUTPUTS, ResultsError, read_jsonl, validate_run

QUALITY_FLOOR = 0.75
MINIMUM_MATERIAL_EFFECT = 0.05
PRIMARY_GIT_COMMIT = "d587a5d6fbeae039009a4e722f2af1249ebcbbf4"
PRIMARY_RUNTIME_VERSION = "0.34.2"
PRIMARY_MODEL_DIGESTS = {
    "llama3.2:3b-instruct-q4_K_M": (
        "a80c4f17acd55265feec403c7aef86be0c25983ab279d83f3bcd3abbcb5b8b72"
    ),
    "llama3.2:3b-instruct-q8_0": (
        "e410b836fe6132b8c5e09bd83156dab0ce2c19f371e0bce2d77e993f8a65241a"
    ),
    "qwen3:4b-instruct-2507-q4_K_M": (
        "0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0"
    ),
    "qwen3:4b-instruct-2507-q8_0": (
        "aa7252f68dda4d25dfffa65b3760af6d2c3231a140c0060c78d444686d98a374"
    ),
}


class AnalysisError(Exception):
    """Input evidence cannot support the preregistered analysis."""


class HypothesisOutcome(StrEnum):
    """Outcome of the frozen decision rule."""

    SUPPORTED = "supported"
    NOT_SUPPORTED = "not_supported"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True, slots=True)
class RequestSample:
    model: str
    model_digest: str
    category: str
    prompt_id: str
    repetition: int
    output_tokens: float
    latency_seconds: float
    gpu_energy_joules: float
    quality_score: float | None = None


@dataclass(frozen=True, slots=True)
class CalibrationThreshold:
    host_id: str
    gpu_fingerprint: str
    category: str
    speed_cv: float
    energy_cv: float
    threshold: float
    run_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ConfigurationAggregate:
    host_id: str
    gpu_fingerprint: str
    category: str
    model: str
    model_digest: str
    request_count: int
    output_tokens: float
    latency_seconds: float
    gpu_energy_joules: float
    tokens_per_second: float
    tokens_per_joule: float
    quality_score: float | None
    eligible: bool


@dataclass(frozen=True, slots=True)
class QualityExclusion:
    host_id: str
    model: str
    model_digest: str
    quality_score: float | None
    quality_floor: float


@dataclass(frozen=True, slots=True)
class DecisionBlock:
    host_id: str
    gpu_fingerprint: str
    category: str
    speed_winner: str
    energy_winner: str
    top_agrees: bool
    eligible_models: tuple[str, ...]
    material_threshold: float


@dataclass(frozen=True, slots=True)
class PairwiseInversion:
    host_id: str
    category: str
    speed_winner: str
    energy_winner: str
    speed_effect: float
    energy_effect: float
    speed_ci_low: float
    speed_ci_high: float
    energy_ci_low: float
    energy_ci_high: float
    threshold: float
    material: bool


@dataclass(frozen=True, slots=True)
class StudyAnalysis:
    schema_version: int
    outcome: HypothesisOutcome
    quality_floor: float
    bootstrap_seed: int
    bootstrap_resamples: int
    blocks_evaluated: int
    blocks_agree: int
    agreement_rate: float
    calibration_run_ids: tuple[str, ...]
    benchmark_run_ids: tuple[str, ...]
    thresholds: tuple[CalibrationThreshold, ...]
    aggregates: tuple[ConfigurationAggregate, ...]
    blocks: tuple[DecisionBlock, ...]
    inversions: tuple[PairwiseInversion, ...]
    exclusions: tuple[QualityExclusion, ...]
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["outcome"] = self.outcome.value
        return payload


@dataclass(frozen=True, slots=True)
class _LoadedRun:
    path: Path
    run_id: str
    experiment_id: str
    host_id: str
    gpu_fingerprint: str
    gpu_name: str
    git_commit: str
    runtime_name: str
    runtime_version: str
    prompt_set_sha256: str
    controls_signature: str
    model_digests: tuple[tuple[str, str], ...]
    prompt_map: tuple[tuple[str, str], ...]
    repetitions: int
    prompt_count: int
    samples: tuple[RequestSample, ...]


def coefficient_of_variation(values: tuple[float, ...]) -> float:
    """Return sample standard deviation divided by the arithmetic mean."""
    if len(values) < 2:
        raise AnalysisError("CV requires at least two independent values")
    mean = statistics.fmean(values)
    if mean <= 0:
        raise AnalysisError("CV requires a positive mean")
    return statistics.stdev(values) / mean


def material_effect_threshold(speed_cv: float, energy_cv: float) -> float:
    """Apply the frozen 5% or three-times-repeatability rule."""
    if speed_cv < 0 or energy_cv < 0:
        raise AnalysisError("CV values cannot be negative")
    return max(MINIMUM_MATERIAL_EFFECT, 3.0 * max(speed_cv, energy_cv))


def aggregate_quality(samples: tuple[RequestSample, ...]) -> float | None:
    """Average repetitions within a prompt, then weight prompts equally."""
    by_prompt: dict[str, list[float]] = defaultdict(list)
    for sample in samples:
        if sample.quality_score is not None:
            by_prompt[sample.prompt_id].append(sample.quality_score)
    if not by_prompt:
        return None
    return statistics.fmean(
        statistics.fmean(by_prompt[prompt_id]) for prompt_id in sorted(by_prompt)
    )


def assess_pairwise_inversion(
    *,
    host_id: str,
    category: str,
    first: tuple[RequestSample, ...],
    second: tuple[RequestSample, ...],
    threshold: float,
    resamples: int,
    seed: int,
) -> PairwiseInversion | None:
    """Assess one descriptive speed/energy rank inversion with paired bootstrap."""
    if resamples < 1:
        raise AnalysisError("bootstrap resamples must be positive")
    first_speed, first_energy = _ratios(first)
    second_speed, second_energy = _ratios(second)
    if first_speed == second_speed or first_energy == second_energy:
        return None
    speed_winner_samples, speed_winner = (
        (first, first[0].model) if first_speed > second_speed else (second, second[0].model)
    )
    speed_loser_samples = second if first_speed > second_speed else first
    energy_winner_samples, energy_winner = (
        (first, first[0].model) if first_energy > second_energy else (second, second[0].model)
    )
    energy_loser_samples = second if first_energy > second_energy else first
    if speed_winner == energy_winner:
        return None

    speed_effect = max(first_speed, second_speed) / min(first_speed, second_speed) - 1.0
    energy_effect = max(first_energy, second_energy) / min(first_energy, second_energy) - 1.0
    speed_distribution, energy_distribution = _paired_hierarchical_bootstrap(
        speed_winner_samples,
        speed_loser_samples,
        energy_winner_samples,
        energy_loser_samples,
        resamples=resamples,
        seed=seed,
    )
    speed_low, speed_high = _confidence_interval(speed_distribution)
    energy_low, energy_high = _confidence_interval(energy_distribution)
    material = (
        speed_effect >= threshold
        and energy_effect >= threshold
        and speed_low > 0
        and energy_low > 0
    )
    return PairwiseInversion(
        host_id=host_id,
        category=category,
        speed_winner=speed_winner,
        energy_winner=energy_winner,
        speed_effect=speed_effect,
        energy_effect=energy_effect,
        speed_ci_low=speed_low,
        speed_ci_high=speed_high,
        energy_ci_low=energy_low,
        energy_ci_high=energy_high,
        threshold=threshold,
        material=material,
    )


def analyze_study(
    calibration_dirs: tuple[Path, ...],
    benchmark_dirs: tuple[Path, ...],
    *,
    seed: int = 42,
    resamples: int = 10_000,
) -> StudyAnalysis:
    """Validate and analyze the frozen primary evidence."""
    if len(benchmark_dirs) != 2:
        raise AnalysisError("exactly two benchmark runs are required for the primary verdict")
    if len(calibration_dirs) != 6:
        raise AnalysisError("exactly six calibration runs are required (three per primary GPU)")

    calibration = tuple(_load_run(path) for path in calibration_dirs)
    benchmarks = tuple(_load_run(path) for path in benchmark_dirs)
    _validate_study_compatibility(calibration, benchmarks)

    thresholds = _calibration_thresholds(calibration, benchmarks)
    threshold_by_block = {
        (item.gpu_fingerprint, item.category): item.threshold for item in thresholds
    }
    aggregates, samples_by_config, exclusions = _benchmark_aggregates(benchmarks)

    by_block: dict[tuple[str, str], list[ConfigurationAggregate]] = defaultdict(list)
    for row in aggregates:
        if row.eligible:
            by_block[(row.host_id, row.category)].append(row)

    blocks: list[DecisionBlock] = []
    inversions: list[PairwiseInversion] = []
    for key in sorted(by_block):
        host_id, category = key
        rows = sorted(by_block[key], key=lambda row: row.model)
        if len(rows) < 2:
            raise AnalysisError(f"{host_id}/{category} has fewer than two quality-eligible models")
        fingerprint = rows[0].gpu_fingerprint
        threshold = threshold_by_block.get((fingerprint, category))
        if threshold is None:
            raise AnalysisError(f"{host_id}/{category} has no matching calibration threshold")
        speed_winner = max(rows, key=lambda row: (row.tokens_per_second, row.model)).model
        energy_winner = max(rows, key=lambda row: (row.tokens_per_joule, row.model)).model
        blocks.append(
            DecisionBlock(
                host_id=host_id,
                gpu_fingerprint=fingerprint,
                category=category,
                speed_winner=speed_winner,
                energy_winner=energy_winner,
                top_agrees=speed_winner == energy_winner,
                eligible_models=tuple(row.model for row in rows),
                material_threshold=threshold,
            )
        )
        for index, first in enumerate(rows):
            for second in rows[index + 1 :]:
                inversion = assess_pairwise_inversion(
                    host_id=host_id,
                    category=category,
                    first=samples_by_config[(host_id, category, first.model)],
                    second=samples_by_config[(host_id, category, second.model)],
                    threshold=threshold,
                    resamples=resamples,
                    seed=seed,
                )
                if inversion is not None:
                    inversions.append(inversion)

    blocks_agree = sum(block.top_agrees for block in blocks)
    agreement_rate = blocks_agree / len(blocks) if blocks else 0.0
    if any(inversion.material for inversion in inversions):
        outcome = HypothesisOutcome.SUPPORTED
    elif agreement_rate >= 0.9 and not any(inversion.material for inversion in inversions):
        outcome = HypothesisOutcome.NOT_SUPPORTED
    else:
        outcome = HypothesisOutcome.INCONCLUSIVE

    return StudyAnalysis(
        schema_version=1,
        outcome=outcome,
        quality_floor=QUALITY_FLOOR,
        bootstrap_seed=seed,
        bootstrap_resamples=resamples,
        blocks_evaluated=len(blocks),
        blocks_agree=blocks_agree,
        agreement_rate=agreement_rate,
        calibration_run_ids=tuple(sorted(run.run_id for run in calibration)),
        benchmark_run_ids=tuple(sorted(run.run_id for run in benchmarks)),
        thresholds=tuple(thresholds),
        aggregates=tuple(aggregates),
        blocks=tuple(blocks),
        inversions=tuple(inversions),
        exclusions=tuple(exclusions),
        limitations=(
            "Energy is GPU-only NVML telemetry, not wall-system energy.",
            "The primary domain contains two NVIDIA GPUs, one runtime, and four "
            "model/quantization configurations.",
            "Quality eligibility is host-local because deterministic settings did not "
            "guarantee byte-identical output across GPUs.",
            "Absence of a material inversion in this domain is not evidence that no "
            "inversion exists elsewhere.",
        ),
    )


def _load_run(path: Path) -> _LoadedRun:
    path = Path(path)
    try:
        validation = validate_run(path)
    except ResultsError as error:
        raise AnalysisError(f"{path.name}: validation could not run: {error}") from error
    if not validation.ok:
        detail = "; ".join(validation.errors) or f"status={validation.status.value}"
        raise AnalysisError(f"{path.name}: run is not valid: {detail}")
    try:
        manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        records = read_jsonl(path / OUTPUTS)
    except (OSError, json.JSONDecodeError, ResultsError) as error:
        raise AnalysisError(f"{path.name}: artifacts could not be loaded: {error}") from error

    samples = tuple(_sample_from_record(path.name, record) for record in records)
    controls = manifest.get("controls")
    gpu = manifest.get("gpu")
    runtime = manifest.get("runtime")
    models = manifest.get("models")
    if not isinstance(controls, dict) or not isinstance(gpu, dict) or not isinstance(runtime, dict):
        raise AnalysisError(f"{path.name}: manifest lacks controls, GPU, or runtime metadata")
    if not isinstance(models, list):
        raise AnalysisError(f"{path.name}: manifest has no model inventory")
    model_digests = tuple(
        sorted((str(model.get("name")), str(model.get("digest"))) for model in models)
    )
    repetitions = _positive_int(manifest.get("repetitions"), path.name, "repetitions")
    prompt_count = _positive_int(manifest.get("prompt_count"), path.name, "prompt_count")
    prompt_map = tuple(sorted({(sample.prompt_id, sample.category) for sample in samples}))
    expected = len(model_digests) * prompt_count * repetitions
    if len(samples) != expected:
        raise AnalysisError(f"{path.name}: expected {expected} measurements, found {len(samples)}")
    counts = Counter((sample.model, sample.prompt_id, sample.repetition) for sample in samples)
    if set(counts.values()) != {1}:
        raise AnalysisError(f"{path.name}: model/prompt/repetition cells are duplicated")
    if len(prompt_map) != prompt_count:
        raise AnalysisError(f"{path.name}: prompt map does not match prompt_count")
    for model, _digest in model_digests:
        cells = {
            (sample.prompt_id, sample.repetition) for sample in samples if sample.model == model
        }
        expected_cells = {
            (prompt_id, repetition)
            for prompt_id, _category in prompt_map
            for repetition in range(repetitions)
        }
        if cells != expected_cells:
            raise AnalysisError(f"{path.name}: incomplete matrix for model {model}")

    controls_for_signature = {
        key: controls.get(key)
        for key in ("models", "options", "order_seed", "concurrency", "repetitions")
    }
    return _LoadedRun(
        path=path,
        run_id=str(manifest.get("run_id") or path.name),
        experiment_id=str(manifest.get("experiment_id") or ""),
        host_id=str(manifest.get("host_id") or ""),
        gpu_fingerprint=str(gpu.get("gpu_fingerprint") or ""),
        gpu_name=str(gpu.get("name") or ""),
        git_commit=str(manifest.get("git_commit") or ""),
        runtime_name=str(runtime.get("name") or ""),
        runtime_version=str(runtime.get("version") or ""),
        prompt_set_sha256=str(manifest.get("prompt_set_sha256") or ""),
        controls_signature=json.dumps(
            controls_for_signature, sort_keys=True, separators=(",", ":")
        ),
        model_digests=model_digests,
        prompt_map=prompt_map,
        repetitions=repetitions,
        prompt_count=prompt_count,
        samples=samples,
    )


def _sample_from_record(run_name: str, record: dict[str, Any]) -> RequestSample:
    metrics = record.get("metrics")
    if record.get("valid") is not True or not isinstance(metrics, dict):
        raise AnalysisError(f"{run_name}: output contains an invalid measurement")
    try:
        sample = RequestSample(
            model=str(record["model"]),
            model_digest=str(record["model_digest"]),
            category=str(record["prompt_category"]),
            prompt_id=str(record["prompt_id"]),
            repetition=int(record["repetition"]),
            output_tokens=float(metrics["output_tokens"]),
            latency_seconds=float(metrics["latency_seconds"]),
            gpu_energy_joules=float(metrics["gpu_energy_joules"]),
            quality_score=(
                None if metrics.get("quality_score") is None else float(metrics["quality_score"])
            ),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise AnalysisError(f"{run_name}: malformed output measurement: {error}") from error
    if (
        sample.output_tokens <= 0
        or sample.latency_seconds <= 0
        or sample.gpu_energy_joules <= 0
        or sample.repetition < 0
    ):
        raise AnalysisError(f"{run_name}: measurement contains non-positive values")
    return sample


def _positive_int(value: Any, run_name: str, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise AnalysisError(f"{run_name}: manifest {field} must be a positive integer")
    return value


def _validate_study_compatibility(
    calibration: tuple[_LoadedRun, ...], benchmarks: tuple[_LoadedRun, ...]
) -> None:
    benchmark_fingerprints = {run.gpu_fingerprint for run in benchmarks}
    if len(benchmark_fingerprints) != 2 or "" in benchmark_fingerprints:
        raise AnalysisError("benchmark runs must describe two distinct GPU fingerprints")
    signatures = {
        (
            run.experiment_id,
            run.git_commit,
            run.runtime_name,
            run.runtime_version,
            run.prompt_set_sha256,
            run.controls_signature,
            run.model_digests,
            run.prompt_map,
        )
        for run in benchmarks
    }
    if len(signatures) != 1:
        raise AnalysisError("benchmark runs do not share an identical frozen contract")
    for run in benchmarks:
        if run.experiment_id != "benchmark-v1":
            raise AnalysisError(f"{run.run_id}: expected benchmark-v1")
        if run.git_commit != PRIMARY_GIT_COMMIT:
            raise AnalysisError(f"{run.run_id}: unexpected benchmark code commit")
        if run.runtime_version != PRIMARY_RUNTIME_VERSION:
            raise AnalysisError(f"{run.run_id}: unexpected runtime version")
        if dict(run.model_digests) != PRIMARY_MODEL_DIGESTS:
            raise AnalysisError(f"{run.run_id}: model digest set is not the frozen primary set")

    calibration_groups: dict[str, list[_LoadedRun]] = defaultdict(list)
    for run in calibration:
        calibration_groups[run.gpu_fingerprint].append(run)
    if set(calibration_groups) != benchmark_fingerprints:
        raise AnalysisError("calibration GPU fingerprints do not match the benchmark hosts")
    for fingerprint, runs in calibration_groups.items():
        if len(runs) != 3:
            raise AnalysisError(f"GPU {fingerprint} requires exactly three calibration launches")
        signatures = {
            (
                run.experiment_id,
                run.runtime_name,
                run.runtime_version,
                run.prompt_set_sha256,
                run.controls_signature,
                run.model_digests,
                run.prompt_map,
            )
            for run in runs
        }
        if len(signatures) != 1:
            raise AnalysisError(f"GPU {fingerprint} calibration launches are not compatible")
        if runs[0].experiment_id != "pilot-v1":
            raise AnalysisError(f"GPU {fingerprint} calibration is not pilot-v1")
        if runs[0].runtime_version != PRIMARY_RUNTIME_VERSION:
            raise AnalysisError(f"GPU {fingerprint} calibration runtime is not frozen")
        if dict(runs[0].model_digests) != {
            "llama3.2:3b-instruct-q4_K_M": PRIMARY_MODEL_DIGESTS["llama3.2:3b-instruct-q4_K_M"]
        }:
            raise AnalysisError(f"GPU {fingerprint} calibration model is not frozen Llama Q4")


def _calibration_thresholds(
    calibration: tuple[_LoadedRun, ...], benchmarks: tuple[_LoadedRun, ...]
) -> list[CalibrationThreshold]:
    host_by_fingerprint = {run.gpu_fingerprint: run.host_id for run in benchmarks}
    groups: dict[str, list[_LoadedRun]] = defaultdict(list)
    for run in calibration:
        groups[run.gpu_fingerprint].append(run)
    thresholds: list[CalibrationThreshold] = []
    for fingerprint in sorted(groups):
        runs = sorted(groups[fingerprint], key=lambda run: run.run_id)
        categories = sorted({sample.category for sample in runs[0].samples})
        for category in categories:
            speeds: list[float] = []
            energies: list[float] = []
            for run in runs:
                samples = tuple(sample for sample in run.samples if sample.category == category)
                speed, energy = _ratios(samples)
                speeds.append(speed)
                energies.append(energy)
            speed_cv = coefficient_of_variation(tuple(speeds))
            energy_cv = coefficient_of_variation(tuple(energies))
            thresholds.append(
                CalibrationThreshold(
                    host_id=host_by_fingerprint[fingerprint],
                    gpu_fingerprint=fingerprint,
                    category=category,
                    speed_cv=speed_cv,
                    energy_cv=energy_cv,
                    threshold=material_effect_threshold(speed_cv, energy_cv),
                    run_ids=tuple(run.run_id for run in runs),
                )
            )
    return sorted(thresholds, key=lambda item: (item.host_id, item.category))


def _benchmark_aggregates(
    benchmarks: tuple[_LoadedRun, ...],
) -> tuple[
    list[ConfigurationAggregate],
    dict[tuple[str, str, str], tuple[RequestSample, ...]],
    list[QualityExclusion],
]:
    rows: list[ConfigurationAggregate] = []
    samples_by_config: dict[tuple[str, str, str], tuple[RequestSample, ...]] = {}
    exclusions: list[QualityExclusion] = []
    for run in sorted(benchmarks, key=lambda item: item.host_id):
        by_model: dict[str, list[RequestSample]] = defaultdict(list)
        for sample in run.samples:
            by_model[sample.model].append(sample)
        quality_by_model = {
            model: aggregate_quality(tuple(samples)) for model, samples in by_model.items()
        }
        for model in sorted(by_model):
            quality = quality_by_model[model]
            eligible = quality is not None and quality >= QUALITY_FLOOR
            digest = dict(run.model_digests)[model]
            if not eligible:
                exclusions.append(
                    QualityExclusion(
                        host_id=run.host_id,
                        model=model,
                        model_digest=digest,
                        quality_score=quality,
                        quality_floor=QUALITY_FLOOR,
                    )
                )
            categories = sorted({sample.category for sample in by_model[model]})
            for category in categories:
                samples = tuple(sample for sample in by_model[model] if sample.category == category)
                speed, energy = _ratios(samples)
                rows.append(
                    ConfigurationAggregate(
                        host_id=run.host_id,
                        gpu_fingerprint=run.gpu_fingerprint,
                        category=category,
                        model=model,
                        model_digest=digest,
                        request_count=len(samples),
                        output_tokens=sum(sample.output_tokens for sample in samples),
                        latency_seconds=sum(sample.latency_seconds for sample in samples),
                        gpu_energy_joules=sum(sample.gpu_energy_joules for sample in samples),
                        tokens_per_second=speed,
                        tokens_per_joule=energy,
                        quality_score=quality,
                        eligible=eligible,
                    )
                )
                samples_by_config[(run.host_id, category, model)] = samples
    rows.sort(key=lambda item: (item.host_id, item.category, item.model))
    exclusions.sort(key=lambda item: (item.host_id, item.model))
    return rows, samples_by_config, exclusions


def _ratios(samples: tuple[RequestSample, ...]) -> tuple[float, float]:
    if not samples:
        raise AnalysisError("cannot aggregate an empty sample")
    tokens = sum(sample.output_tokens for sample in samples)
    latency = sum(sample.latency_seconds for sample in samples)
    energy = sum(sample.gpu_energy_joules for sample in samples)
    if tokens <= 0 or latency <= 0 or energy <= 0:
        raise AnalysisError("ratio-of-sums requires positive totals")
    return tokens / latency, tokens / energy


def _paired_hierarchical_bootstrap(
    speed_winner: tuple[RequestSample, ...],
    speed_loser: tuple[RequestSample, ...],
    energy_winner: tuple[RequestSample, ...],
    energy_loser: tuple[RequestSample, ...],
    *,
    resamples: int,
    seed: int,
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    groups = tuple(
        _group_by_prompt_and_repetition(samples)
        for samples in (speed_winner, speed_loser, energy_winner, energy_loser)
    )
    prompt_ids = tuple(sorted(groups[0]))
    if not prompt_ids or any(tuple(sorted(group)) != prompt_ids for group in groups[1:]):
        raise AnalysisError("paired bootstrap requires identical prompt IDs")
    for prompt_id in prompt_ids:
        repetitions = tuple(sorted(groups[0][prompt_id]))
        if not repetitions or any(
            tuple(sorted(group[prompt_id])) != repetitions for group in groups[1:]
        ):
            raise AnalysisError("paired bootstrap requires identical repetition cells")

    rng = random.Random(seed)
    speed_effects: list[float] = []
    energy_effects: list[float] = []
    for _ in range(resamples):
        selected: list[tuple[str, int]] = []
        for _prompt_position in prompt_ids:
            prompt_id = rng.choice(prompt_ids)
            repetitions = tuple(sorted(groups[0][prompt_id]))
            for _repetition_position in repetitions:
                selected.append((prompt_id, rng.choice(repetitions)))
        aggregate_samples = tuple(
            tuple(group[prompt_id][repetition] for prompt_id, repetition in selected)
            for group in groups
        )
        speed_top = _ratios(aggregate_samples[0])[0]
        speed_bottom = _ratios(aggregate_samples[1])[0]
        energy_top = _ratios(aggregate_samples[2])[1]
        energy_bottom = _ratios(aggregate_samples[3])[1]
        speed_effects.append(speed_top / speed_bottom - 1.0)
        energy_effects.append(energy_top / energy_bottom - 1.0)
    return tuple(speed_effects), tuple(energy_effects)


def _group_by_prompt_and_repetition(
    samples: tuple[RequestSample, ...],
) -> dict[str, dict[int, RequestSample]]:
    grouped: dict[str, dict[int, RequestSample]] = defaultdict(dict)
    for sample in samples:
        if sample.repetition in grouped[sample.prompt_id]:
            raise AnalysisError("paired bootstrap received a duplicate repetition cell")
        grouped[sample.prompt_id][sample.repetition] = sample
    return dict(grouped)


def _confidence_interval(values: tuple[float, ...]) -> tuple[float, float]:
    ordered = tuple(sorted(values))
    return _percentile(ordered, 0.025), _percentile(ordered, 0.975)


def _percentile(ordered: tuple[float, ...], fraction: float) -> float:
    if not ordered:
        raise AnalysisError("cannot calculate a percentile of no values")
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight
