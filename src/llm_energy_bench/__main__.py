"""Module entry point: ``python -m llm_energy_bench``."""

from __future__ import annotations

import sys

from llm_energy_bench.cli import main

if __name__ == "__main__":
    sys.exit(main())
