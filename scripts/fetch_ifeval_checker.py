"""Fetch the official IFEval checker at a pinned commit (quality-v3, protocol section 7).

Usage:
    python scripts/fetch_ifeval_checker.py [--dest DIR]

Downloads google-research/instruction_following_eval at ``COMMIT`` into
``DEST/instruction_following_eval`` (default: experiments/tmp/ifeval-checker,
gitignored), verifies every file against ``PINNED_SHA256`` and fetches the NLTK
tokenizer data the checker needs into ``DEST/nltk_data``.

The checker runs in its own virtual environment, so the lock-verified
measurement environment stays untouched:

    py -3.12 -m venv experiments/tmp/ifeval-venv
    experiments/tmp/ifeval-venv/Scripts/python -m pip install -r requirements/quality-v3-ifeval.txt
    experiments/tmp/ifeval-venv/Scripts/python scripts/fetch_ifeval_checker.py
"""

from __future__ import annotations

import argparse
import hashlib
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
COMMIT = "e6890f85757dd84e27ca6df2dd30651dafad28e0"
BASE = (
    "https://raw.githubusercontent.com/google-research/google-research/"
    f"{COMMIT}/instruction_following_eval/"
)
# Reference responses shipped with the checker; used to reproduce published scores.
GPT4_RESPONSES = "data/input_response_data_gpt4_20231107_145030.jsonl"
PINNED_SHA256 = {
    "evaluation_lib.py": "35decc06000718487f44d7deafa6d3f48a8ec0886281edf40162c0265b7d248c",
    "evaluation_main.py": "e6df07a04d25a0e7134933ba2400c26e0129a243e449c88df55043e583fc4b4a",
    "instructions.py": "60e086f5342a03ce8e18b64bbcccf86308f523c08aa826707a562150a52f3edf",
    "instructions_registry.py": "ec92d72c264f6d906978613085db262356174300370a3fffe6fefd5969ce9cfc",
    "instructions_util.py": "a73797261eee5bf447e279d82a2b700b1bdd3cb1193412dbab1270a85832bc6b",
    "requirements.txt": "1b1716c9ac21b9cc2bd0d7354ed8f7b6982ccf35598529601a7c08508acec94a",
    "data/input_data.jsonl": "67ffeee0fcb87c317c5b08a2de85557b4a7e96ada6178aa645b4954fe4b53d49",
    GPT4_RESPONSES: "0cff1d1469b774e80296bee20ca696894df35f3c6d6539f2c886d67c07599dcb",
}
NLTK_PACKAGES = ("punkt", "punkt_tab")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dest", type=Path, default=REPO / "experiments" / "tmp" / "ifeval-checker"
    )
    args = parser.parse_args()

    package = args.dest / "instruction_following_eval"
    (package / "data").mkdir(parents=True, exist_ok=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    for name, pinned in PINNED_SHA256.items():
        target = package / name
        if not target.exists():
            request = urllib.request.Request(
                BASE + name, headers={"User-Agent": "llm-energy-bench-fetch"}
            )
            with urllib.request.urlopen(request, timeout=60) as response:
                target.write_bytes(response.read())
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        if pinned and digest != pinned:
            raise SystemExit(f"{name}: SHA-256 mismatch {digest} != pinned {pinned}")
        print(f"{digest}  {name}")

    import nltk  # only available in the checker environment

    nltk_dir = args.dest / "nltk_data"
    for package_name in NLTK_PACKAGES:
        if not nltk.download(package_name, download_dir=str(nltk_dir), quiet=True):
            raise SystemExit(f"NLTK package {package_name} could not be downloaded")
    print(f"NLTK data: {nltk_dir}")


if __name__ == "__main__":
    main()
