from typing import Any

import pytest

from mcp_agent_mail.macros.ci_gate import ci_gate

# Mock check runs data
MOCK_SUCCESS_CHECKS: list[dict[str, Any]] = [
    {"name": "Fast Tests (ubuntu)", "status": "completed", "conclusion": "success", "html_url": "http://run/1"},
    {"name": "Fast Tests (macos)", "status": "completed", "conclusion": "skipped", "html_url": "http://run/2"}
]

MOCK_FAIL_CHECKS: list[dict[str, Any]] = [
    {"name": "Fast Tests (ubuntu)", "status": "completed", "conclusion": "failure", "html_url": "http://run/1"}
]

MOCK_PENDING_CHECKS: list[dict[str, Any]] = [
    {"name": "Fast Tests (ubuntu)", "status": "in_progress", "conclusion": None, "html_url": "http://run/1"}
]

class MockGithubClient:
    def __init__(self, checks_data: list[dict[str, Any]]) -> None:
        self.checks_data = checks_data

    def get_check_runs(self, owner: str, repo: str, sha: str) -> list[dict[str, Any]]:
        return self.checks_data

    def get_pr_head_sha(self, owner: str, repo: str, pr_number: int) -> str:
        return "mock_sha_123"

@pytest.mark.parametrize(
    "scenario, expected_ok, expected_failed_count",
    [
        (MOCK_SUCCESS_CHECKS, True, 0),
        (MOCK_FAIL_CHECKS, False, 1),
        (MOCK_PENDING_CHECKS, False, 1),
        ([], False, 1),  # Missing required check
    ],
)
def test_ci_gate_scenarios(
    scenario: list[dict[str, Any]],
    expected_ok: bool,
    expected_failed_count: int,
) -> None:
    client = MockGithubClient(scenario)

    result = ci_gate(
        owner="owner",
        repo="repo",
        sha="mock_sha",
        require_checks=["Fast Tests (ubuntu)"],
        allow_skipped={"Fast Tests (macos)"},
        github_client=client,
    )

    assert result["ok"] == expected_ok
    assert len(result["failed"]) == expected_failed_count
    assert result["sha"] == "mock_sha"

def test_ci_gate_pr_resolution() -> None:
    client = MockGithubClient(MOCK_SUCCESS_CHECKS)
    result = ci_gate(
        owner="owner",
        repo="repo",
        pr_number=4,
        require_checks=["Fast Tests (ubuntu)"],
        github_client=client,
    )
    assert result["ok"] is True
    assert result["sha"] == "mock_sha_123"
