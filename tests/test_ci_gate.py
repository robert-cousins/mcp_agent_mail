import pytest
from unittest.mock import MagicMock, patch
from mcp_agent_mail.macros.ci_gate import ci_gate

# Mock check runs data
MOCK_SUCCESS_CHECKS = [
    {"name": "Fast Tests (ubuntu)", "status": "completed", "conclusion": "success", "html_url": "http://run/1"},
    {"name": "Fast Tests (macos)", "status": "completed", "conclusion": "skipped", "html_url": "http://run/2"}
]

MOCK_FAIL_CHECKS = [
    {"name": "Fast Tests (ubuntu)", "status": "completed", "conclusion": "failure", "html_url": "http://run/1"}
]

MOCK_PENDING_CHECKS = [
    {"name": "Fast Tests (ubuntu)", "status": "in_progress", "conclusion": None, "html_url": "http://run/1"}
]

class MockGithubClient:
    def __init__(self, checks_data):
        self.checks_data = checks_data

    def get_check_runs(self, owner, repo, sha):
        return self.checks_data

    def get_pr_head_sha(self, owner, repo, pr_number):
        return "mock_sha_123"

@pytest.mark.parametrize("scenario, expected_ok, expected_failed_count", [
    (MOCK_SUCCESS_CHECKS, True, 0),
    (MOCK_FAIL_CHECKS, False, 1),
    (MOCK_PENDING_CHECKS, False, 1),
    ([], False, 1), # Missing required check
])
def test_ci_gate_scenarios(scenario, expected_ok, expected_failed_count):
    client = MockGithubClient(scenario)
    
    # We'll pass the client to the macro if we use dependency injection,
    # or patch the internal client creation. Let's assume DI for cleaner tests.
    result = ci_gate(
        owner="owner",
        repo="repo",
        sha="mock_sha",
        require_checks=["Fast Tests (ubuntu)"],
        allow_skipped={"Fast Tests (macos)"},
        github_client=client
    )
    
    assert result["ok"] == expected_ok
    assert len(result["failed"]) == expected_failed_count
    if expected_ok:
        assert result["sha"] == "mock_sha"

def test_ci_gate_pr_resolution():
    client = MockGithubClient(MOCK_SUCCESS_CHECKS)
    result = ci_gate(
        owner="owner",
        repo="repo",
        pr_number=4,
        require_checks=["Fast Tests (ubuntu)"],
        github_client=client
    )
    assert result["ok"] is True
    assert result["sha"] == "mock_sha_123"
