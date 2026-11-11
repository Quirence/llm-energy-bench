"""Score the quality-v3 IFEval runs with the official checker (protocol sections 3 В2, 7).

Usage (in the checker environment, see scripts/fetch_ifeval_checker.py):
    experiments/tmp/ifeval-venv/Scripts/python scripts/score_ifeval_quality_v3.py
    experiments/tmp/ifeval-venv/Scripts/python scripts/score_ifeval_quality_v3.py --validate

``--validate`` scores the GPT-4 responses shipped with the checker, to compare
with the published numbers before scoring our runs.

Instructions are checked against the pinned Hugging Face dataset, which is what
the models were given. ``langdetect`` is seeded (0) so the verdicts are
reproducible; the number of prompt-level verdicts that change under seeds 1-4
is reported as a sensitivity check. Writes ``ifeval-scores.csv`` (one row per
request) and ``ifeval-analysis.json``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import score_quality_v3 as base  # noqa: E402  (stdlib-only helpers shared with MGSM)

PARTS = ("ifeval-a", "ifeval-b", "ifeval-c")
DATASET_SHA256 = "6a85310ca8ce15eff755aa08a3a4ff931c7e273e7515ebb3c492ea85fd8288f2"
LANGDETECT_SEED = 0
SENSITIVITY_SEEDS = (1, 2, 3, 4)


def load_checker(checker: Path):
    os.environ["NLTK_DATA"] = str(checker / "nltk_data")
    sys.path.insert(0, str(checker))
    import langdetect
    from instruction_following_eval import evaluation_lib

    return evaluation_lib, langdetect


def evaluate(evaluation_lib, langdetect, examples, prompt_to_response, seed: int):
    langdetect.DetectorFactory.seed = seed
    strict = [
        evaluation_lib.test_instruction_following_strict(e, prompt_to_response) for e in examples
    ]
    langdetect.DetectorFactory.seed = seed
    loose = [
        evaluation_lib.test_instruction_following_loose(e, prompt_to_response) for e in examples
    ]
    return strict, loose


def four_metrics(strict, loose) -> dict[str, float]:
    def prompt_level(outputs):
        return sum(o.follow_all_instructions for o in outputs) / len(outputs)

    def instruction_level(outputs):
        flags = [flag for o in outputs for flag in o.follow_instruction_list]
        return sum(flags) / len(flags)

    metrics = {
        "prompt_strict": prompt_level(strict),
        "instruction_strict": instruction_level(strict),
        "prompt_loose": prompt_level(loose),
        "instruction_loose": instruction_level(loose),
    }
    metrics["mean_of_four"] = sum(metrics.values()) / 4
    return metrics


def validate(evaluation_lib, langdetect, checker: Path, dataset: Path) -> None:
    # The shipped GPT-4 responses answer the Hugging Face prompt texts (item 2785
    # differs from the checker's own input_data.jsonl), so the pinned dataset is
    # the input here as well.
    data = checker / "instruction_following_eval" / "data"
    examples = evaluation_lib.read_prompt_list(str(dataset))
    responses = evaluation_lib.read_prompt_to_response_dict(
        str(data / "input_response_data_gpt4_20231107_145030.jsonl")
    )
    strict, loose = evaluate(evaluation_lib, langdetect, examples, responses, LANGDETECT_SEED)
    for name, value in four_metrics(strict, loose).items():
        print(f"GPT-4 reference {name}: {100 * value:.2f}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, default=REPO / "experiments" / "runs" / "quality-v3")
    parser.add_argument(
        "--checker", type=Path, default=REPO / "experiments" / "tmp" / "ifeval-checker"
    )
    parser.add_argument(
        "--dataset", type=Path, default=REPO / "experiments" / "tmp" / "quality-v3" / "ifeval.raw"
    )
    parser.add_argument("--out", type=Path, default=REPO / "experiments" / "studies" / "quality-v3")
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()

    evaluation_lib, langdetect = load_checker(args.checker)
    if args.validate:
        validate(evaluation_lib, langdetect, args.checker, args.dataset)
        return

    raw = args.dataset.read_bytes()
    if hashlib.sha256(raw).hexdigest() != DATASET_SHA256:
        raise SystemExit("IFEval dataset does not match the pinned SHA-256")
    dataset = {row["key"]: row for row in map(json.loads, raw.decode("utf-8").splitlines())}
    sources = json.loads((REPO / "prompts" / "quality-v3-sources.json").read_text(encoding="utf-8"))

    requests: list[dict] = []
    runs_used = {}
    for part in PARTS:
        run_dir = base.completed_run(args.runs, part)
        if run_dir is None:
            raise SystemExit(f"no completed run for {part}")
        runs_used[part] = run_dir.name
        telemetry = base.load_telemetry(run_dir)
        with (run_dir / "outputs.jsonl").open(encoding="utf-8") as handle:
            for record in map(json.loads, handle):
                if not record["valid"]:
                    raise SystemExit(f"{run_dir.name}: invalid request {record['request_id']}")
                metrics = record["metrics"]
                requests.append(
                    {
                        "part": part,
                        "model": record["model"],
                        "item": record["prompt_id"],
                        "key": int(record["prompt_id"].removeprefix("ifeval-")),
                        "text": record["text"],
                        "truncated": int(record["done_reason"] == "length"),
                        "output_tokens": metrics["output_tokens"],
                        "energy_j": metrics["gpu_energy_joules"],
                        "energy_source": metrics["energy_source"],
                        "energy_instant_j": base.instant_power_energy(
                            telemetry[record["request_id"]]
                        ),
                        "latency_s": metrics["latency_seconds"],
                    }
                )

    analysis: dict = {
        "protocol": "docs/quality-v3-preregistration.md",
        "checker": (
            "google-research/instruction_following_eval@e6890f85757dd84e27ca6df2dd30651dafad28e0"
        ),
        "dataset": "huggingface.co/datasets/google/IFEval@966cd89545d6b6acfd7638bc708b98261ca58e84",
        "langdetect_seed": LANGDETECT_SEED,
        "excluded": sources.get("ifeval_excluded", {}),
        "runs": runs_used,
        "models": {},
    }
    rows_out = []
    for model in base.MODELS:
        mine = [r for r in requests if r["model"] == model]
        keys = sorted(r["key"] for r in mine)
        if len(keys) != len(set(keys)):
            raise SystemExit(f"{model}: duplicate IFEval items")
        examples = [
            evaluation_lib.InputExample(
                key=k,
                instruction_id_list=dataset[k]["instruction_id_list"],
                prompt=dataset[k]["prompt"],
                kwargs=dataset[k]["kwargs"],
            )
            for k in keys
        ]
        by_key = {r["key"]: r for r in mine}
        responses = {dataset[k]["prompt"]: by_key[k]["text"] for k in keys}
        strict, loose = evaluate(evaluation_lib, langdetect, examples, responses, LANGDETECT_SEED)

        flips = Counter()
        for seed in SENSITIVITY_SEEDS:
            s_alt, l_alt = evaluate(evaluation_lib, langdetect, examples, responses, seed)
            flips["prompt_strict"] += sum(
                a.follow_all_instructions != b.follow_all_instructions
                for a, b in zip(strict, s_alt, strict=True)
            )
            flips["prompt_loose"] += sum(
                a.follow_all_instructions != b.follow_all_instructions
                for a, b in zip(loose, l_alt, strict=True)
            )

        per_item = {}
        for k, s, lo in zip(keys, strict, loose, strict=True):
            r = by_key[k]
            row = {
                "part": r["part"],
                "model": model,
                "item": r["item"],
                "instructions": len(s.follow_instruction_list),
                "prompt_strict": int(s.follow_all_instructions),
                "prompt_loose": int(lo.follow_all_instructions),
                "instructions_strict": sum(s.follow_instruction_list),
                "instructions_loose": sum(lo.follow_instruction_list),
                "truncated": r["truncated"],
                "output_tokens": r["output_tokens"],
                "energy_j": r["energy_j"],
                "energy_source": r["energy_source"],
                "energy_instant_j": r["energy_instant_j"],
                "latency_s": r["latency_s"],
            }
            rows_out.append(row)
            per_item[r["item"]] = {
                "n": 1,
                "correct": row["prompt_strict"],
                "strict": row["prompt_strict"],
                "energy_j": row["energy_j"],
                "energy_instant_j": row["energy_instant_j"],
                "latency_s": row["latency_s"],
            }

        n = len(keys)
        passed = sum(o.follow_all_instructions for o in strict)
        energy = sum(r["energy_j"] for r in mine)
        energy_instant = sum(r["energy_instant_j"] for r in mine)
        latency = sum(r["latency_s"] for r in mine)
        items = sorted(per_item)
        summary = {
            "items": n,
            "metrics": four_metrics(strict, loose),
            "prompt_strict_wilson95": base.wilson(passed, n),
            "truncated": sum(r["truncated"] for r in mine),
            "truncated_prompt_strict_pass": sum(
                o.follow_all_instructions
                for k, o in zip(keys, strict, strict=True)
                if by_key[k]["truncated"]
            ),
            "mean_output_tokens": sum(r["output_tokens"] for r in mine) / n,
            "energy_per_request_j": energy / n,
            "energy_per_strict_pass_j": energy / passed if passed else None,
            "energy_per_strict_pass_instant_j": energy_instant / passed if passed else None,
            "latency_per_strict_pass_s": latency / passed if passed else None,
            "energy_source_counts": dict(Counter(r["energy_source"] for r in mine)),
            "langdetect_seed_flips_over_4_seeds": dict(flips),
        }
        for key, name in (
            ("energy_j", "energy_per_strict_pass_ci95"),
            ("energy_instant_j", "energy_per_strict_pass_instant_ci95"),
            ("latency_s", "latency_per_strict_pass_ci95"),
        ):
            values = base.bootstrap(
                items, lambda s, k=key, t=per_item: base.cost_per_correct(t, s, k)
            )
            summary[name] = base.percentile_ci(values)
        analysis["models"][model] = summary
        analysis.setdefault("_per_item", {})[model] = per_item

    tables = analysis.pop("_per_item")
    analysis["ratios_llama_over_qwen"] = {
        quant: {
            key: base.ratio_test(tables[llama], tables[qwen], key)
            for key in ("energy_j", "energy_instant_j", "latency_s")
        }
        for quant, llama, qwen in (
            ("q4", base.LLAMA_Q4, base.QWEN_Q4),
            ("q8", "llama3.2:3b-instruct-q8_0", "qwen3:4b-instruct-2507-q8_0"),
        )
    }

    args.out.mkdir(parents=True, exist_ok=True)
    with (args.out / "ifeval-scores.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows_out[0]))
        writer.writeheader()
        writer.writerows(rows_out)
    (args.out / "ifeval-analysis.json").write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    for model, summary in analysis["models"].items():
        m = summary["metrics"]
        print(
            f"{model}: prompt strict {100 * m['prompt_strict']:.1f}, "
            f"instruction strict {100 * m['instruction_strict']:.1f}, "
            f"prompt loose {100 * m['prompt_loose']:.1f}, "
            f"instruction loose {100 * m['instruction_loose']:.1f}, "
            f"mean {100 * m['mean_of_four']:.1f}; "
            f"E/pass {summary['energy_per_strict_pass_j']:.0f} J"
        )


if __name__ == "__main__":
    main()
