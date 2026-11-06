"""Score and analyse the quality-v3 MGSM-ru blocks (docs/quality-v3-preregistration.md).

Usage:
    python scripts/score_quality_v3.py [--runs DIR] [--out DIR]

Reads the newest completed run of every quality-v3 MGSM block and of its
repeat passes (``-p2``, ``-p3``), applies the scoring rules of protocol
section 7, the analysis of section 9 and the aggregation of section 12.2, and
writes ``mgsm-scores.csv`` (one row per request) and ``mgsm-analysis.json``.
IFEval is scored separately with the official checker.

Pure standard library, so it runs in the measurement venv without adding
packages.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
QWEN_Q4 = "qwen3:4b-instruct-2507-q4_K_M"
LLAMA_Q4 = "llama3.2:3b-instruct-q4_K_M"
MODELS = (
    QWEN_Q4,
    "qwen3:4b-instruct-2507-q8_0",
    LLAMA_Q4,
    "llama3.2:3b-instruct-q8_0",
)
HOST_ID = "maibenben-x16c-rtx5060"
MGSM_BLOCKS = {"mgsm-ru-direct": "direct", "mgsm-ru-cot": "cot"}
REPEAT_SUFFIXES = ("", "-p2", "-p3")  # pass 1, 2, 3 (protocol section 12.2)
DET_BLOCKS = {"det-direct": "mgsm-ru-direct", "det-cot": "mgsm-ru-cot"}
BOOTSTRAP_SAMPLES = 10_000
BOOTSTRAP_SEED = 42

# --------------------------------------------------------------------------
# Scoring rules (protocol section 7)
# --------------------------------------------------------------------------

# Thousands separators: space, no-break space, narrow no-break space, or a
# comma, each followed by exactly three digits.
_THOUSANDS = re.compile(r"(?<=\d)[   ,](?=\d{3}(?!\d))")
# A number; a minus sign counts only when it does not follow a digit or letter.
_NUMBER = re.compile(r"(?:(?<![\w])[-−])?\d+(?:[.,]\d+)?")
_ANSWER_LINE = re.compile(r"ответ\s*[:：]", re.IGNORECASE)


def _strip_separators(text: str) -> str:
    previous = None
    while previous != text:
        previous, text = text, _THOUSANDS.sub("", text)
    return text


def _to_number(token: str) -> float:
    return float(token.replace("−", "-").replace(",", "."))


def extract_answer(text: str, mode: str) -> float | None:
    """The value a response commits to, by the correctness-axis rule."""
    clean = _strip_separators(text)
    if mode == "cot":
        for line in reversed(clean.splitlines()):
            match = _ANSWER_LINE.search(line)
            if match:
                numbers = _NUMBER.findall(line[match.end() :])
                if numbers:
                    return _to_number(numbers[0])
    numbers = _NUMBER.findall(clean)
    return _to_number(numbers[-1]) if numbers else None


def score_correct(text: str, gold: str, mode: str) -> int:
    value = extract_answer(text, mode)
    return int(value is not None and value == float(gold))


def score_strict(text: str, gold: str, mode: str) -> int:
    if mode == "direct":
        body = text.strip()
        if body.endswith("."):
            body = body[:-1]
        return int(body == gold)
    lines = [line for line in text.splitlines() if line.strip()]
    return int(bool(lines) and lines[-1].strip() == f"Ответ: {gold}")


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------


def completed_run(runs: Path, block: str) -> Path | None:
    for run_dir in sorted(runs.glob(f"quality-v3-{block}-{HOST_ID}-*"), reverse=True):
        manifest = run_dir / "manifest.json"
        if manifest.is_file():
            status = json.loads(manifest.read_text(encoding="utf-8"))["status"]
            if status == "completed":
                return run_dir
    return None


def load_gold(prompt_file: Path) -> dict[str, str]:
    with prompt_file.open(encoding="utf-8") as handle:
        return {row["id"]: row["expect_exact"] for row in map(json.loads, handle)}


def instant_power_energy(samples: list[dict]) -> float | None:
    """Trapezoidal integral of NVML instantaneous power, as the tool's fallback does.

    The tool prefers the NVML total-energy counter and falls back to this
    integral when the counter is implausible; recomputing every request this
    way gives one energy source across all passes (robustness check).
    """
    points: list[tuple[float, float]] = []
    for sample in sorted(samples, key=lambda x: x["monotonic_s"]):
        if sample.get("power_instant_watts") is None:
            continue
        if points and sample["monotonic_s"] == points[-1][0]:
            points[-1] = (sample["monotonic_s"], sample["power_instant_watts"])
        else:
            points.append((sample["monotonic_s"], sample["power_instant_watts"]))
    if len(points) < 2:
        return None
    return sum(
        (t1 - t0) * (p0 + p1) / 2 for (t0, p0), (t1, p1) in zip(points, points[1:], strict=False)
    )


def load_telemetry(run_dir: Path) -> dict[str, list[dict]]:
    by_request: dict[str, list[dict]] = defaultdict(list)
    with gzip.open(run_dir / "telemetry.jsonl.gz", "rt", encoding="utf-8") as handle:
        for sample in map(json.loads, handle):
            if sample["request_id"]:
                by_request[sample["request_id"]].append(sample)
    return by_request


def load_block(run_dir: Path, gold: dict[str, str], mode: str, pass_no: int = 1) -> list[dict]:
    rows = []
    telemetry = load_telemetry(run_dir)
    with (run_dir / "outputs.jsonl").open(encoding="utf-8") as handle:
        for record in map(json.loads, handle):
            if not record["valid"]:
                raise SystemExit(f"{run_dir.name}: invalid request {record['request_id']}")
            item = record["prompt_id"]
            rows.append(
                {
                    "run": run_dir.name,
                    "pass": pass_no,
                    "model": record["model"],
                    "item": item,
                    "repetition": record["repetition"],
                    "gold": gold[item],
                    "extracted": extract_answer(record["text"], mode),
                    "correct": score_correct(record["text"], gold[item], mode),
                    "strict": score_strict(record["text"], gold[item], mode),
                    "truncated": int(record["done_reason"] == "length"),
                    "output_tokens": record["metrics"]["output_tokens"],
                    "energy_j": record["metrics"]["gpu_energy_joules"],
                    "energy_source": record["metrics"]["energy_source"],
                    "energy_instant_j": instant_power_energy(telemetry[record["request_id"]]),
                    "latency_s": record["metrics"]["latency_seconds"],
                    "text": record["text"],
                }
            )
    return rows


# --------------------------------------------------------------------------
# Statistics (protocol section 9)
# --------------------------------------------------------------------------


def wilson(successes: float, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if n == 0:
        return (math.nan, math.nan)
    p = successes / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (centre - half, centre + half)


def mcnemar_exact(b: int, c: int) -> dict[str, float]:
    """Exact McNemar test on discordant counts b (first only) and c (second only)."""
    n = b + c
    if n == 0:
        return {"b": b, "c": c, "p_two_sided": 1.0, "p_one_sided_b_gt_c": 1.0}
    pmf = [math.comb(n, k) / 2**n for k in range(n + 1)]
    tail_low = sum(pmf[: min(b, c) + 1])
    return {
        "b": b,
        "c": c,
        "p_two_sided": min(1.0, 2 * tail_low),
        "p_one_sided_b_gt_c": sum(pmf[b:]),
    }


def holm(pvalues: dict[str, float]) -> dict[str, float]:
    ordered = sorted(pvalues.items(), key=lambda kv: kv[1])
    adjusted: dict[str, float] = {}
    running = 0.0
    for rank, (name, p) in enumerate(ordered):
        running = max(running, min(1.0, (len(ordered) - rank) * p))
        adjusted[name] = running
    return adjusted


def per_item(rows: list[dict], model: str) -> dict[str, dict[str, float]]:
    """Per-item totals for one model; repetitions are summed (quality averaged later)."""
    totals: dict[str, dict[str, float]] = defaultdict(
        lambda: {
            "n": 0,
            "correct": 0,
            "strict": 0,
            "energy_j": 0.0,
            "energy_instant_j": 0.0,
            "latency_s": 0.0,
        }
    )
    for row in rows:
        if row["model"] == model:
            entry = totals[row["item"]]
            entry["n"] += 1
            for key in ("correct", "strict", "energy_j", "energy_instant_j", "latency_s"):
                entry[key] += row[key]
    return dict(totals)


def bootstrap(items: list[str], statistic, seed: int = BOOTSTRAP_SEED) -> list[float]:
    rng = random.Random(seed)
    values = []
    for _ in range(BOOTSTRAP_SAMPLES):
        sample = [items[rng.randrange(len(items))] for _ in items]
        value = statistic(sample)
        if value is not None and math.isfinite(value):
            values.append(value)
    values.sort()
    return values


def percentile_ci(values: list[float]) -> tuple[float, float]:
    def at(q: float) -> float:
        position = q * (len(values) - 1)
        low, high = math.floor(position), math.ceil(position)
        return values[low] + (values[high] - values[low]) * (position - low)

    return (at(0.025), at(0.975))


def cost_per_correct(table: dict[str, dict[str, float]], sample: list[str], key: str):
    correct = sum(table[item]["correct"] for item in sample)
    return sum(table[item][key] for item in sample) / correct if correct else None


def model_summary(rows: list[dict], model: str) -> dict:
    mine = [row for row in rows if row["model"] == model]
    n = len(mine)
    correct = sum(row["correct"] for row in mine)
    strict = sum(row["strict"] for row in mine)
    energy = sum(row["energy_j"] for row in mine)
    energy_instant = sum(row["energy_instant_j"] for row in mine)
    latency = sum(row["latency_s"] for row in mine)
    table = per_item(rows, model)
    items = sorted(table)
    k = len(items)
    summary = {
        "passes": sorted({row["pass"] for row in mine}),
        "items": k,
        "requests": n,
        "correct": correct,
        "accuracy": correct / n,
        # Section 12.2: averaged proportion, interval over the number of items.
        "accuracy_wilson95": wilson(correct / n * k, k),
        "strict": strict,
        "strict_accuracy": strict / n,
        "strict_wilson95": wilson(strict / n * k, k),
        "correct_but_format_violation": sum(r["correct"] and not r["strict"] for r in mine),
        "truncated": sum(row["truncated"] for row in mine),
        "mean_output_tokens": sum(row["output_tokens"] for row in mine) / n,
        "energy_per_request_j": energy / n,
        "latency_per_request_s": latency / n,
        "energy_per_correct_j": energy / correct if correct else None,
        "energy_per_correct_instant_j": energy_instant / correct if correct else None,
        "energy_source_counts": dict(Counter(row["energy_source"] for row in mine)),
        "latency_per_correct_s": latency / correct if correct else None,
    }
    for key, name in (
        ("energy_j", "energy_per_correct_ci95"),
        ("energy_instant_j", "energy_per_correct_instant_ci95"),
        ("latency_s", "latency_per_correct_ci95"),
    ):
        values = bootstrap(items, lambda s, k=key: cost_per_correct(table, s, k))
        summary[name] = percentile_ci(values)
    return summary


def ratio_test(first: dict, second: dict, key: str) -> dict:
    """Paired bootstrap of cost_per_correct(first) / cost_per_correct(second)."""
    items = sorted(set(first) & set(second))

    def statistic(sample: list[str]):
        a = cost_per_correct(first, sample, key)
        b = cost_per_correct(second, sample, key)
        return a / b if a is not None and b else None

    values = bootstrap(items, statistic)
    point = statistic(items)
    return {
        "ratio": point,
        "ci95": percentile_ci(values),
        "p_one_sided_ratio_le_1": sum(v <= 1 for v in values) / len(values),
        "bootstrap_samples_used": len(values),
    }


def gap_difference(rows: list[dict]) -> dict:
    """H3: (correct - strict) of Llama Q4 minus the same for Qwen Q4, paired over items."""
    llama, qwen = per_item(rows, LLAMA_Q4), per_item(rows, QWEN_Q4)
    items = sorted(set(llama) & set(qwen))

    def gap(table, sample):
        n = sum(table[i]["n"] for i in sample)
        correct = sum(table[i]["correct"] for i in sample)
        return (correct - sum(table[i]["strict"] for i in sample)) / n

    def statistic(sample):
        return gap(llama, sample) - gap(qwen, sample)

    values = bootstrap(items, statistic)
    return {
        "gap_llama": gap(llama, items),
        "gap_qwen": gap(qwen, items),
        "difference": statistic(items),
        "ci95": percentile_ci(values),
        "p_one_sided_difference_le_0": sum(v <= 0 for v in values) / len(values),
    }


def format_violation_mcnemar(rows: list[dict]) -> dict:
    """H2: per item, 'correct value but strict format failed', Llama Q4 vs Qwen Q4.

    With several passes an item is flagged by majority (section 12.2).
    """

    def flags(model):
        votes: dict[str, list[int]] = defaultdict(list)
        for r in rows:
            if r["model"] == model:
                votes[r["item"]].append(int(r["correct"] and not r["strict"]))
        return {item: int(sum(v) * 2 > len(v)) for item, v in votes.items()}

    llama, qwen = flags(LLAMA_Q4), flags(QWEN_Q4)
    items = sorted(set(llama) & set(qwen))
    b = sum(llama[i] and not qwen[i] for i in items)
    c = sum(qwen[i] and not llama[i] for i in items)
    result = mcnemar_exact(b, c)
    result["violations_llama"] = sum(llama.values())
    result["violations_qwen"] = sum(qwen.values())
    return result


def determinism(main: list[dict], det: list[dict]) -> dict:
    index = {(r["model"], r["item"]): r for r in main if r["pass"] == 1}
    out = {}
    for model in MODELS:
        pairs = [(index[(r["model"], r["item"])], r) for r in det if r["model"] == model]
        n = len(pairs)
        out[model] = {
            "items": n,
            "text_differs": sum(a["text"] != b["text"] for a, b in pairs),
            "extracted_differs": sum(a["extracted"] != b["extracted"] for a, b in pairs),
            "correct_differs": sum(a["correct"] != b["correct"] for a, b in pairs),
            "strict_differs": sum(a["strict"] != b["strict"] for a, b in pairs),
        }
    return out


# --------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, default=REPO / "experiments" / "runs" / "quality-v3")
    parser.add_argument("--out", type=Path, default=REPO / "experiments" / "studies" / "quality-v3")
    args = parser.parse_args()

    blocks: dict[str, list[dict]] = {}
    runs_used: dict[str, str] = {}
    for block, mode in {**MGSM_BLOCKS, "det-direct": "direct", "det-cot": "cot"}.items():
        gold = load_gold(REPO / "prompts" / f"quality-v3-{block}.jsonl")
        suffixes = REPEAT_SUFFIXES if block in MGSM_BLOCKS else ("",)
        blocks[block] = []
        for pass_no, suffix in enumerate(suffixes, start=1):
            run_dir = completed_run(args.runs, block + suffix)
            if run_dir is None:
                if pass_no == 1:
                    raise SystemExit(f"no completed run for {block}")
                print(f"warning: {block}{suffix} not completed; using {pass_no - 1} pass(es)")
                break
            blocks[block] += load_block(run_dir, gold, mode, pass_no)
            runs_used[block + suffix] = run_dir.name

    args.out.mkdir(parents=True, exist_ok=True)
    fields = [k for k in next(iter(blocks.values()))[0] if k != "text"]
    with (args.out / "mgsm-scores.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["block", *fields])
        writer.writeheader()
        for block, rows in blocks.items():
            for row in rows:
                writer.writerow({"block": block, **{k: row[k] for k in fields}})

    analysis: dict = {"protocol": "docs/quality-v3-preregistration.md", "runs": runs_used}
    for block in MGSM_BLOCKS:
        analysis[block] = {model: model_summary(blocks[block], model) for model in MODELS}
        by_pass = defaultdict(list)
        for row in blocks[block]:
            by_pass[row["pass"]].append(row)
        analysis[f"{block}-per-pass"] = {
            str(pass_no): {
                model: {
                    key: value
                    for key, value in model_summary(rows, model).items()
                    if key
                    in (
                        "accuracy",
                        "strict_accuracy",
                        "energy_per_correct_j",
                        "energy_per_correct_instant_j",
                        "energy_source_counts",
                    )
                }
                for model in MODELS
            }
            for pass_no, rows in sorted(by_pass.items())
        }

    direct = blocks["mgsm-ru-direct"]
    h1 = ratio_test(per_item(direct, LLAMA_Q4), per_item(direct, QWEN_Q4), "energy_j")
    h1_time = ratio_test(per_item(direct, LLAMA_Q4), per_item(direct, QWEN_Q4), "latency_s")
    h1_instant = ratio_test(
        per_item(direct, LLAMA_Q4), per_item(direct, QWEN_Q4), "energy_instant_j"
    )
    h2 = format_violation_mcnemar(direct)
    h3 = gap_difference(direct)
    pvalues = {
        "H1": h1["p_one_sided_ratio_le_1"],
        "H2": h2["p_one_sided_b_gt_c"],
        "H3": h3["p_one_sided_difference_le_0"],
    }
    analysis["hypotheses"] = {
        "H1_energy_ratio_llama_over_qwen_q4_direct": h1,
        "H1_robustness_latency_ratio": h1_time,
        "H1_robustness_single_energy_source": h1_instant,
        "H2_format_violation_mcnemar_q4_direct": h2,
        "H3_gap_difference_q4_direct": h3,
        "H3_supplementary_cot": gap_difference(blocks["mgsm-ru-cot"]),
        "one_sided_p": pvalues,
        "holm_adjusted_p": holm(pvalues),
        "sidedness_note": (
            "H1-H3 are directional, so one-sided p-values enter the Holm correction; "
            "the two-sided exact McNemar p is reported alongside."
        ),
    }
    analysis["V1_cot_over_direct_energy_per_correct"] = {
        model: ratio_test(
            per_item(blocks["mgsm-ru-cot"], model), per_item(direct, model), "energy_j"
        )
        for model in MODELS
    }
    cot = blocks["mgsm-ru-cot"]
    analysis["cot_energy_ratio_llama_over_qwen"] = {
        quant: {
            key: ratio_test(per_item(cot, llama), per_item(cot, qwen), key)
            for key in ("energy_j", "energy_instant_j", "latency_s")
        }
        for quant, llama, qwen in (
            ("q4", LLAMA_Q4, QWEN_Q4),
            ("q8", "llama3.2:3b-instruct-q8_0", "qwen3:4b-instruct-2507-q8_0"),
        )
    }
    analysis["determinism"] = {
        block: determinism(blocks[main_block], blocks[block])
        for block, main_block in DET_BLOCKS.items()
    }
    (args.out / "mgsm-analysis.json").write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(analysis["determinism"], indent=1))
    print(json.dumps(analysis["hypotheses"], indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
