import pytest
from unittest.mock import MagicMock, patch
from mcp_agent_mail.macros.send_ready_report import send_ready_report

@pytest.fixture
def mock_am_client():
    client = MagicMock()
    # Mock successful message delivery
    client.send_message.return_value = {"deliveries": [{"id": 99}]}
    return client

@patch("mcp_agent_mail.macros.send_ready_report.ci_gate")
def test_send_ready_report_gate_fails(mock_ci_gate, mock_am_client):
    # Setup ci_gate to fail
    mock_ci_gate.return_value = {"ok": False, "sha": "sha123", "failed": [{"name": "Check", "reason": "failure"}]}
    
    with pytest.raises(ValueError) as excinfo:
        send_ready_report(
            project_key="proj",
            sender="CalmDeer",
            recipients=["PearlCove"],
            owner="owner",
            repo="repo",
            pr_number=4,
            local_commands=["pytest"],
            am_client=mock_am_client
        )
    
    assert "CI gate failed" in str(excinfo.value)
    mock_am_client.send_message.assert_not_called()

@patch("mcp_agent_mail.macros.send_ready_report.ci_gate")
def test_send_ready_report_gate_passes(mock_ci_gate, mock_am_client):
    # Setup ci_gate to pass
    mock_ci_gate.return_value = {
        "ok": True,
        "sha": "sha123",
        "required": [{"name": "Fast Tests (ubuntu)", "status": "completed", "conclusion": "success"}],
        "others": [],
        "failed": [],
        "url": "http://run/1"
    }
    
    result = send_ready_report(
        project_key="proj",
        sender="CalmDeer",
        recipients=["PearlCove"],
        owner="owner",
        repo="repo",
        pr_number=4,
        local_commands=["pytest"],
        am_client=mock_am_client
    )
    
    assert result["message_sent"] is True
    mock_am_client.send_message.assert_called_once()
    
    # Verify body contents
    call_args = mock_am_client.send_message.call_args[1]
    body = call_args["body_md"]
    assert "sha123" in body
    assert "Fast Tests (ubuntu)" in body
    assert "pytest" in body
    assert "http://run/1" in body
