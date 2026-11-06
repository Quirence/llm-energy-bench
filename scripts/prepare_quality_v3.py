"""Build the frozen quality-v3 prompt sets from pinned upstream datasets.

Usage:
    python scripts/prepare_quality_v3.py [--cache DIR]

Downloads MGSM (Russian) and IFEval at pinned revisions, verifies their SHA-256,
and writes prompts/quality-v3-*.jsonl plus prompts/quality-v3-sources.json.
The templates and splits are fixed by docs/quality-v3-preregistration.md.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PROMPTS = REPO / "prompts"

SOURCES = {
    "mgsm_ru": {
        "url": (
            "https://raw.githubusercontent.com/google-research/url-nlp/"
            "4b1e7a43efb517abadd16041e8b47f3be975c76e/mgsm/mgsm_ru.tsv"
        ),
        "revision": "google-research/url-nlp@4b1e7a43efb517abadd16041e8b47f3be975c76e",
        "license": (
            "upstream repository states no license; the Hugging Face mirror "
            "juletxara/mgsm declares CC BY-SA 4.0 (GSM8K source: MIT)"
        ),
        "citation": "Shi et al. Language Models are Multilingual Chain-of-Thought "
        "Reasoners. arXiv:2210.03057, 2022.",
        "sha256": None,  # verified against PINNED_SHA256
    },
    "ifeval": {
        "url": (
            "https://huggingface.co/datasets/google/IFEval/resolve/"
            "966cd89545d6b6acfd7638bc708b98261ca58e84/ifeval_input_data.jsonl"
        ),
        "revision": (
            "huggingface.co/datasets/google/IFEval@966cd89545d6b6acfd7638bc708b98261ca58e84"
        ),
        "license": "Apache-2.0",
        "citation": "Zhou et al. Instruction-Following Evaluation for Large Language "
        "Models. arXiv:2311.07911, 2023.",
        "sha256": None,
    },
}

PINNED_SHA256 = {
    # Set after the first verified download; a mismatch afterwards is fatal.
    "mgsm_ru": "6bd30fd2e80c5bac23f566fb4ae0e6a55a19578401fbf9a01fb21beb3645fef8",
    "ifeval": "6a85310ca8ce15eff755aa08a3a4ff931c7e273e7515ebb3c492ea85fd8288f2",
}

DIRECT_TEMPLATE = "{question}\n\nВыведи только ответ — одно целое число без пояснений."
COT_TEMPLATE = (
    "{question}\n\nРеши задачу пошагово. В последней строке напиши «Ответ: N», где N — целое число."
)
IFEVAL_PARTS = (("a", 0, 181), ("b", 181, 361), ("c", 361, 541))
# Prompts on which Ollama 0.35.0 aborts generation ("token repeat limit reached")
# for some configuration. The runner stops on such server errors, so the prompt
# is removed for every model (protocol section 12.5). Part boundaries stay those
# of the upstream order.
IFEVAL_EXCLUDED = {
    1880: "qwen3:4b-instruct-2507-q4_K_M repeats 'c' until Ollama aborts (2026-11-06)",
}
DETERMINISM_ITEMS = 50
DETERMINISM_SEED = 42


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch(name: str, cache: Path) -> bytes:
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / f"{name}.raw"
    if not target.exists():
        request = urllib.request.Request(
            SOURCES[name]["url"], headers={"User-Agent": "llm-energy-bench-prepare"}
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            target.write_bytes(response.read())
    data = target.read_bytes()
    digest = sha256(data)
    pinned = PINNED_SHA256[name]
    if pinned and digest != pinned:
        raise SystemExit(f"{name}: SHA-256 mismatch {digest} != pinned {pinned}")
    SOURCES[name]["sha256"] = digest
    return data


def write_jsonl(path: Path, records: list[dict]) -> str:
    text = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records)
    path.write_bytes(text.encode("utf-8"))
    return sha256(text.encode("utf-8"))


def mgsm_items(raw: bytes) -> list[tuple[str, str, str]]:
    items = []
    for number, line in enumerate(raw.decode("utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        question, answer = line.rsplit("\t", 1)
        # Four upstream answers use thousands separators ("2,125"); the gold value
        # is the plain integer.
        answer = re.sub(r"(?<=\d),(?=\d{3}\b)", "", answer.strip())
        if not answer.lstrip("-").isdigit():
            raise SystemExit(f"MGSM line {number}: non-integer answer {answer!r}")
        items.append((f"mgsm-ru-{number:03d}", question.strip(), answer))
    if len(items) != 250:
        raise SystemExit(f"MGSM-ru must have 250 items, found {len(items)}")
    return items


def ifeval_items(raw: bytes) -> list[dict]:
    rows = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    missing = set(IFEVAL_EXCLUDED) - {row["key"] for row in rows}
    if missing:
        raise SystemExit(f"excluded IFEval keys not in the dataset: {sorted(missing)}")
    if len(rows) != 541:
        raise SystemExit(f"IFEval must have 541 prompts, found {len(rows)}")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=REPO / "experiments" / "tmp" / "quality-v3")
    args = parser.parse_args()

    mgsm = mgsm_items(fetch("mgsm_ru", args.cache))
    ifeval = ifeval_items(fetch("ifeval", args.cache))

    outputs: dict[str, str] = {}

    def mgsm_records(template: str, subset: list[tuple[str, str, str]]) -> list[dict]:
        return [
            {
                "id": item_id,
                "category": "scored",
                "prompt": template.format(question=question),
                "expect_exact": answer,
            }
            for item_id, question, answer in subset
        ]

    outputs["quality-v3-mgsm-ru-direct.jsonl"] = write_jsonl(
        PROMPTS / "quality-v3-mgsm-ru-direct.jsonl", mgsm_records(DIRECT_TEMPLATE, mgsm)
    )
    outputs["quality-v3-mgsm-ru-cot.jsonl"] = write_jsonl(
        PROMPTS / "quality-v3-mgsm-ru-cot.jsonl", mgsm_records(COT_TEMPLATE, mgsm)
    )

    subset_ids = sorted(
        random.Random(DETERMINISM_SEED).sample([i[0] for i in mgsm], DETERMINISM_ITEMS)
    )
    subset = [item for item in mgsm if item[0] in set(subset_ids)]
    outputs["quality-v3-det-direct.jsonl"] = write_jsonl(
        PROMPTS / "quality-v3-det-direct.jsonl", mgsm_records(DIRECT_TEMPLATE, subset)
    )
    outputs["quality-v3-det-cot.jsonl"] = write_jsonl(
        PROMPTS / "quality-v3-det-cot.jsonl", mgsm_records(COT_TEMPLATE, subset)
    )

    for part, start, stop in IFEVAL_PARTS:
        records = [
            {"id": f"ifeval-{row['key']}", "category": "long", "prompt": row["prompt"]}
            for row in ifeval[start:stop]
            if row["key"] not in IFEVAL_EXCLUDED
        ]
        name = f"quality-v3-ifeval-{part}.jsonl"
        outputs[name] = write_jsonl(PROMPTS / name, records)

    manifest = {
        "protocol": "docs/quality-v3-preregistration.md",
        "sources": {name: {k: v for k, v in source.items()} for name, source in SOURCES.items()},
        "templates": {"mgsm_direct": DIRECT_TEMPLATE, "mgsm_cot": COT_TEMPLATE},
        "determinism_subset": {"seed": DETERMINISM_SEED, "ids": subset_ids},
        "ifeval_parts": {part: [start, stop] for part, start, stop in IFEVAL_PARTS},
        "ifeval_excluded": {f"ifeval-{key}": why for key, why in IFEVAL_EXCLUDED.items()},
        "prompt_file_sha256": outputs,
    }
    (PROMPTS / "quality-v3-sources.json").write_bytes(
        (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    )
    for name, digest in outputs.items():
        print(f"{digest}  prompts/{name}")
    for name, source in SOURCES.items():
        print(f"{name}: {source['sha256']}")


if __name__ == "__main__":
    main()
