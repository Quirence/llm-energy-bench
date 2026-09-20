"""Repository collaboration contracts that should not silently disappear."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_codeowners_requires_cross_review_for_methodology_contracts() -> None:
    content = (REPO_ROOT / ".github" / "CODEOWNERS").read_text(encoding="utf-8")

    assert "@Quirence" in content
    assert "@Qcsteeven" in content
    for path in (
        "/src/llm_energy_bench/config.py",
        "/src/llm_energy_bench/results.py",
        "/src/llm_energy_bench/runner.py",
        "/docs/research-plan.md",
    ):
        matching = next(line for line in content.splitlines() if line.startswith(path))
        assert "@Quirence" in matching
        assert "@Qcsteeven" in matching


def test_issue_and_pull_request_templates_cover_reproducible_work() -> None:
    required = (
        ".github/ISSUE_TEMPLATE/bug_report.yml",
        ".github/ISSUE_TEMPLATE/experiment_run.yml",
        ".github/pull_request_template.md",
    )
    for relative in required:
        path = REPO_ROOT / relative
        assert path.is_file(), f"missing collaboration template: {relative}"
        assert path.read_text(encoding="utf-8").strip()

    pull_request = (REPO_ROOT / ".github" / "pull_request_template.md").read_text(
        encoding="utf-8"
    )
    assert "STATUS.md" in pull_request
    assert "schema or methodology" in pull_request
    assert "private" in pull_request.lower()
