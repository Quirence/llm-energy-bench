"""Deterministic analysis for the frozen power-quality-v2 campaign."""

from __future__ import annotations

import csv
import io
import json
import statistics
from collections import defaultdict
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from llm_energy_bench.config import HostRole, PromptCategory
from llm_energy_bench.results import OUTPUTS, read_jsonl, validate_run, write_text


class PowerQualityError(Exception):
    """The supplied runs cannot support the frozen power-quality analysis."""


@dataclass(frozen=True, slots=True)
class PowerQualitySample:
    host_id: str
    host_role: HostRole
    model: str
    power_limit_watts: float
    workload: PromptCategory
    launch_index: int
    output_tokens: int
    eval_duration_seconds: float
    energy_joules: float
    latency_seconds: float
    quality_score: float | None


@dataclass(frozen=True, slots=True)
class ConditionAggregate:
    host_id: str
    host_role: HostRole
    model: str
    power_limit_watts: float
    workload: PromptCategory
    tokens_per_second: float
    tokens_per_joule: float
    median_energy_per_request_joules: float
    quality_score: float | None
    energy_per_correct_joules: float | None
    latency_per_correct_seconds: float | None
    throughput_change_from_baseline: float | None = None
    energy_change_from_baseline: float | None = None
    on_tradeoff_frontier: bool = False


@dataclass(frozen=True, slots=True)
class PowerQualityAnalysis:
    rows: tuple[ConditionAggregate, ...]
    primary_comparisons: tuple[ConditionAggregate, ...]
    run_rows: tuple[dict[str, Any], ...]


def aggregate_condition(samples: tuple[PowerQualitySample, ...]) -> ConditionAggregate:
    """Aggregate one host/model/power/workload condition using ratios of sums."""
    if not samples:
        raise PowerQualityError("cannot aggregate an empty condition")
    first = samples[0]
    identity = (
        first.host_id,
        first.host_role,
        first.model,
        first.power_limit_watts,
        first.workload,
    )
    if any(
        (
            sample.host_id,
            sample.host_role,
            sample.model,
            sample.power_limit_watts,
            sample.workload,
        )
        != identity
        for sample in samples
    ):
        raise PowerQualityError("condition samples have inconsistent controls")

    tokens = sum(sample.output_tokens for sample in samples)
    decode_seconds = sum(sample.eval_duration_seconds for sample in samples)
    energy = sum(sample.energy_joules for sample in samples)
    latency = sum(sample.latency_seconds for sample in samples)
    scores = [sample.quality_score for sample in samples if sample.quality_score is not None]
    correct = sum(scores)
    return ConditionAggregate(
        host_id=first.host_id,
        host_role=first.host_role,
        model=first.model,
        power_limit_watts=first.power_limit_watts,
        workload=first.workload,
        tokens_per_second=_positive_ratio(tokens, decode_seconds),
        tokens_per_joule=_positive_ratio(tokens, energy),
        median_energy_per_request_joules=statistics.median(
            sample.energy_joules for sample in samples
        ),
        quality_score=statistics.fmean(scores) if scores else None,
        energy_per_correct_joules=energy / correct if correct > 0 else None,
        latency_per_correct_seconds=latency / correct if correct > 0 else None,
    )


def mark_frontier(rows: tuple[ConditionAggregate, ...]) -> tuple[ConditionAggregate, ...]:
    """Return non-dominated speed/efficiency/quality configurations in input order."""
    return tuple(
        candidate
        for candidate in rows
        if not any(other is not candidate and _dominates(other, candidate) for other in rows)
    )


def analyze_power_quality(
    run_dirs: tuple[Path, ...],
    primary_hosts: tuple[str, str],
    external_host: str,
) -> PowerQualityAnalysis:
    """Validate a complete campaign and build host-local response curves."""
    if len(set(primary_hosts)) != 2 or external_host in primary_hosts:
        raise PowerQualityError(
            "analysis requires two distinct primary hosts and one external host"
        )
    if not run_dirs:
        raise PowerQualityError("no power-quality runs were supplied")

    samples: list[PowerQualitySample] = []
    run_rows: list[dict[str, Any]] = []
    conditions: dict[tuple[str, str, float], set[int]] = defaultdict(set)
    expected_hosts = {*primary_hosts, external_host}
    for run_dir in run_dirs:
        manifest_path = run_dir / "manifest.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise PowerQualityError(f"cannot read {manifest_path}: {error}") from error
        if manifest.get("schema_version") != 3:
            raise PowerQualityError(f"{run_dir} must use schema_version 3")
        validation = validate_run(run_dir)
        if not validation.ok:
            raise PowerQualityError(
                f"run {run_dir.name!r} failed validation: {'; '.join(validation.errors)}"
            )

        host_id = _required_string(manifest, "host_id", run_dir)
        if host_id not in expected_hosts:
            raise PowerQualityError(f"run {run_dir.name!r} has undeclared host {host_id!r}")
        study = _required_mapping(manifest, "study", run_dir)
        try:
            role = HostRole(study.get("host_role"))
        except ValueError as error:
            raise PowerQualityError(f"run {run_dir.name!r} has an invalid host role") from error
        expected_role = HostRole.EXTERNAL if host_id == external_host else HostRole.PRIMARY
        if role is not expected_role:
            raise PowerQualityError(f"run {run_dir.name!r} has a host-role mismatch")
        launch = _required_launch(study, run_dir)
        models = manifest.get("models")
        if not isinstance(models, list) or len(models) != 1 or not isinstance(models[0], dict):
            raise PowerQualityError(f"run {run_dir.name!r} must contain exactly one model")
        model = _required_string(models[0], "name", run_dir)
        controls = _required_mapping(manifest, "controls", run_dir)
        power = _required_positive_number(controls, "expected_power_limit_watts", run_dir)
        condition_key = (host_id, model, power)
        if launch in conditions[condition_key]:
            raise PowerQualityError(f"duplicate launch for condition {condition_key!r}")
        conditions[condition_key].add(launch)

        outputs = read_jsonl(run_dir / OUTPUTS)
        run_samples = tuple(
            _sample_from_output(output, host_id, role, model, power, launch, run_dir)
            for output in outputs
        )
        samples.extend(run_samples)
        run_rows.append(
            {
                "run_id": manifest.get("run_id", run_dir.name),
                "host_id": host_id,
                "host_role": role.value,
                "model": model,
                "power_limit_watts": power,
                "launch_index": launch,
                "request_count": len(run_samples),
                "output_tokens": sum(sample.output_tokens for sample in run_samples),
                "energy_joules": sum(sample.energy_joules for sample in run_samples),
                "latency_seconds": sum(sample.latency_seconds for sample in run_samples),
            }
        )

    _validate_matrix(conditions, primary_hosts, external_host)
    grouped: dict[tuple[str, HostRole, str, float, PromptCategory], list[PowerQualitySample]] = (
        defaultdict(list)
    )
    for sample in samples:
        grouped[
            (
                sample.host_id,
                sample.host_role,
                sample.model,
                sample.power_limit_watts,
                sample.workload,
            )
        ].append(sample)
    rows = [aggregate_condition(tuple(grouped[key])) for key in sorted(grouped, key=_sort_key)]
    rows = _add_baselines_and_frontiers(rows)
    primary = tuple(row for row in rows if row.host_id in primary_hosts)
    return PowerQualityAnalysis(
        rows=tuple(rows),
        primary_comparisons=primary,
        run_rows=tuple(sorted(run_rows, key=_run_sort_key)),
    )


def write_power_quality_analysis(
    analysis: PowerQualityAnalysis,
    output_dir: Path,
) -> tuple[Path, Path, Path]:
    """Write byte-deterministic raw, summary, and Markdown artifacts."""
    output_dir.mkdir(parents=True, exist_ok=True)
    runs_path = output_dir / "power-quality-runs.csv"
    summary_path = output_dir / "power-quality-summary.csv"
    report_path = output_dir / "power-quality-report.md"
    write_text(runs_path, _render_csv(analysis.run_rows))
    write_text(summary_path, _render_summary_csv(analysis.rows))
    write_text(report_path, _render_report(analysis))
    return runs_path, summary_path, report_path


def _sample_from_output(
    output: dict[str, Any],
    host_id: str,
    role: HostRole,
    model: str,
    power: float,
    launch: int,
    run_dir: Path,
) -> PowerQualitySample:
    metrics = output.get("metrics")
    if not isinstance(metrics, dict):
        raise PowerQualityError(f"run {run_dir.name!r} has an output without metrics")
    try:
        workload = PromptCategory(output["prompt_category"])
        tokens = int(output["eval_count"])
        eval_seconds = float(output["eval_duration_ns"]) / 1e9
        energy = float(metrics["gpu_energy_joules"])
        latency = float(output["latency_s"])
        raw_quality = metrics.get("quality_score")
        quality = None if raw_quality is None else float(raw_quality)
    except (KeyError, TypeError, ValueError) as error:
        raise PowerQualityError(f"run {run_dir.name!r} has unusable output metrics") from error
    if min(tokens, eval_seconds, energy, latency) <= 0:
        raise PowerQualityError(f"run {run_dir.name!r} has non-positive output metrics")
    if quality is not None and not 0 <= quality <= 1:
        raise PowerQualityError(f"run {run_dir.name!r} has quality outside [0, 1]")
    return PowerQualitySample(
        host_id,
        role,
        model,
        power,
        workload,
        launch,
        tokens,
        eval_seconds,
        energy,
        latency,
        quality,
    )


def _validate_matrix(
    conditions: dict[tuple[str, str, float], set[int]],
    primary_hosts: tuple[str, str],
    external_host: str,
) -> None:
    for host in (*primary_hosts, external_host):
        host_conditions = {
            (model, power): launches
            for (condition_host, model, power), launches in conditions.items()
            if condition_host == host
        }
        models = sorted({model for model, _power in host_conditions})
        required_power_count = 3 if host == external_host else 4
        complete = len(models) == 2
        power_sets: list[set[float]] = []
        for model in models:
            powers = {power for candidate, power in host_conditions if candidate == model}
            power_sets.append(powers)
            complete = complete and len(powers) == required_power_count
            complete = complete and all(
                host_conditions[(model, power)] == {1, 2, 3} for power in powers
            )
        complete = complete and len(power_sets) == 2 and power_sets[0] == power_sets[1]
        if not complete:
            raise PowerQualityError(f"incomplete matrix for host {host!r}")


def _add_baselines_and_frontiers(
    rows: list[ConditionAggregate],
) -> list[ConditionAggregate]:
    by_curve: dict[tuple[str, str, PromptCategory], list[ConditionAggregate]] = defaultdict(list)
    for row in rows:
        by_curve[(row.host_id, row.model, row.workload)].append(row)
    updated: list[ConditionAggregate] = []
    for row in rows:
        curve = by_curve[(row.host_id, row.model, row.workload)]
        baseline = max(curve, key=lambda item: item.power_limit_watts)
        updated.append(
            replace(
                row,
                throughput_change_from_baseline=(
                    row.tokens_per_second / baseline.tokens_per_second - 1.0
                ),
                energy_change_from_baseline=(
                    row.median_energy_per_request_joules / baseline.median_energy_per_request_joules
                    - 1.0
                ),
            )
        )

    by_block: dict[tuple[str, PromptCategory], list[ConditionAggregate]] = defaultdict(list)
    for row in updated:
        by_block[(row.host_id, row.workload)].append(row)
    frontier_keys = {
        _condition_key(row) for block in by_block.values() for row in mark_frontier(tuple(block))
    }
    return [
        replace(row, on_tradeoff_frontier=_condition_key(row) in frontier_keys) for row in updated
    ]


def _dominates(first: ConditionAggregate, second: ConditionAggregate) -> bool:
    first_quality = first.quality_score if first.quality_score is not None else 0.0
    second_quality = second.quality_score if second.quality_score is not None else 0.0
    comparisons = (
        first.tokens_per_second >= second.tokens_per_second,
        first.tokens_per_joule >= second.tokens_per_joule,
        first_quality >= second_quality,
    )
    improvements = (
        first.tokens_per_second > second.tokens_per_second,
        first.tokens_per_joule > second.tokens_per_joule,
        first_quality > second_quality,
    )
    return all(comparisons) and any(improvements)


def _condition_key(row: ConditionAggregate) -> tuple[str, str, float, PromptCategory]:
    return row.host_id, row.model, row.power_limit_watts, row.workload


def _sort_key(
    key: tuple[str, HostRole, str, float, PromptCategory],
) -> tuple[str, str, str, float, str]:
    host, role, model, power, workload = key
    return host, role.value, model, -power, workload.value


def _run_sort_key(row: dict[str, Any]) -> tuple[str, str, float, int]:
    return (
        str(row["host_id"]),
        str(row["model"]),
        -float(row["power_limit_watts"]),
        int(row["launch_index"]),
    )


def _positive_ratio(numerator: float, denominator: float) -> float:
    if numerator <= 0 or denominator <= 0:
        raise PowerQualityError("aggregate ratios require positive values")
    return numerator / denominator


def _required_mapping(record: dict[str, Any], field: str, run_dir: Path) -> dict[str, Any]:
    value = record.get(field)
    if not isinstance(value, dict):
        raise PowerQualityError(f"run {run_dir.name!r} has no {field}")
    return value


def _required_string(record: dict[str, Any], field: str, run_dir: Path) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value:
        raise PowerQualityError(f"run {run_dir.name!r} has no {field}")
    return value


def _required_positive_number(record: dict[str, Any], field: str, run_dir: Path) -> float:
    value = record.get(field)
    if not isinstance(value, int | float) or isinstance(value, bool) or value <= 0:
        raise PowerQualityError(f"run {run_dir.name!r} has invalid {field}")
    return float(value)


def _required_launch(study: dict[str, Any], run_dir: Path) -> int:
    value = study.get("launch_index")
    if not isinstance(value, int) or isinstance(value, bool) or value not in {1, 2, 3}:
        raise PowerQualityError(f"run {run_dir.name!r} has invalid launch_index")
    return value


def _render_csv(rows: tuple[dict[str, Any], ...]) -> str:
    fields = (
        "run_id",
        "host_id",
        "host_role",
        "model",
        "power_limit_watts",
        "launch_index",
        "request_count",
        "output_tokens",
        "energy_joules",
        "latency_seconds",
    )
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: _csv_value(row.get(field)) for field in fields})
    return buffer.getvalue()


def _render_summary_csv(rows: tuple[ConditionAggregate, ...]) -> str:
    fields = tuple(asdict(rows[0])) if rows else tuple(asdict(FAST_EMPTY_ROW))
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        payload = asdict(row)
        payload["host_role"] = row.host_role.value
        payload["workload"] = row.workload.value
        writer.writerow({field: _csv_value(payload.get(field)) for field in fields})
    return buffer.getvalue()


FAST_EMPTY_ROW = ConditionAggregate(
    "", HostRole.PRIMARY, "", 1.0, PromptCategory.SHORT, 1.0, 1.0, 1.0, None, None, None
)


def _render_report(analysis: PowerQualityAnalysis) -> str:
    primary_count = len(analysis.primary_comparisons)
    external_count = len(analysis.rows) - primary_count
    frontier_count = sum(row.on_tradeoff_frontier for row in analysis.rows)
    lines = [
        "# Анализ power-quality-v2",
        "",
        f"Основных сравнительных строк: {primary_count}.",
        f"Внешних наблюдательных строк: {external_count}.",
        f"Конфигураций на границе компромисса: {frontier_count}.",
        "",
        "GTX 1080 имеет роль external и не объединяется с основными GPU.",
        "Относительные изменения рассчитаны от максимального лимита мощности "
        "для той же модели и нагрузки.",
        "",
        "| Стенд | Роль | Модель | Вт | Нагрузка | ток/с | ток/Дж | Точность | Граница |",
        "|---|---|---|---:|---|---:|---:|---:|---|",
    ]
    for row in analysis.rows:
        quality = "—" if row.quality_score is None else f"{row.quality_score:.3f}"
        lines.append(
            f"| {row.host_id} | {row.host_role.value} | {row.model} | "
            f"{row.power_limit_watts:g} | {row.workload.value} | "
            f"{row.tokens_per_second:.3f} | {row.tokens_per_joule:.3f} | "
            f"{quality} | {'да' if row.on_tradeoff_frontier else 'нет'} |"
        )
    return "\n".join(lines) + "\n"


def _csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, float):
        return format(value, ".12g")
    if isinstance(value, bool):
        return "true" if value else "false"
    return value
