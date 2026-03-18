import os
from unittest.mock import MagicMock, patch
import pytest


SAMPLE_ANOMALY = {
    "service": "EC2",
    "region": "eu-west-1",
    "account_id": "123456789012",
    "team_tag": "platform",
    "cost_usd": 500.0,
    "baseline_usd": 10.0,
    "deviation_pct": 4900.0,
    "severity": "high",
    "date": "2024-01-31",
}


@pytest.fixture(autouse=True)
def env_vars(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")


def _make_anthropic_mock(response_text: str) -> MagicMock:
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = response_text

    message = MagicMock()
    message.content = [text_block]

    client = MagicMock()
    client.messages.create.return_value = message
    return client


class TestGenerateRecommendation:
    def test_happy_path_returns_narrative(self):
        expected = "EC2 costs spiked due to untagged instances. Terminate idle instances to save ~$490/month."
        mock_client = _make_anthropic_mock(expected)

        import src.llm_advisor as advisor
        advisor._client = None  # reset singleton

        with patch("src.llm_advisor.anthropic.Anthropic", return_value=mock_client):
            result = advisor.generate_recommendation(SAMPLE_ANOMALY)

        assert result == expected
        mock_client.messages.create.assert_called_once()
        call_kwargs = mock_client.messages.create.call_args[1]
        assert call_kwargs["model"] == "claude-sonnet-4-6"
        assert "EC2" in call_kwargs["messages"][0]["content"]

    def test_prompt_contains_anomaly_values(self):
        mock_client = _make_anthropic_mock("Some recommendation.")

        import src.llm_advisor as advisor
        advisor._client = None

        with patch("src.llm_advisor.anthropic.Anthropic", return_value=mock_client):
            advisor.generate_recommendation(SAMPLE_ANOMALY)

        prompt_text = mock_client.messages.create.call_args[1]["messages"][0]["content"]
        assert "EC2" in prompt_text
        assert "eu-west-1" in prompt_text
        assert "platform" in prompt_text
        assert "500" in prompt_text

    def test_returns_empty_string_when_no_text_block(self):
        non_text_block = MagicMock()
        non_text_block.type = "tool_use"

        message = MagicMock()
        message.content = [non_text_block]

        mock_client = MagicMock()
        mock_client.messages.create.return_value = message

        import src.llm_advisor as advisor
        advisor._client = None

        with patch("src.llm_advisor.anthropic.Anthropic", return_value=mock_client):
            result = advisor.generate_recommendation(SAMPLE_ANOMALY)

        assert result == ""

    def test_api_error_propagates(self):
        import anthropic as anthropic_lib

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = anthropic_lib.APIConnectionError(request=MagicMock())

        import src.llm_advisor as advisor
        advisor._client = None

        with patch("src.llm_advisor.anthropic.Anthropic", return_value=mock_client):
            with pytest.raises(anthropic_lib.APIConnectionError):
                advisor.generate_recommendation(SAMPLE_ANOMALY)
