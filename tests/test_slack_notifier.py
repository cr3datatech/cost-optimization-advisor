from unittest.mock import MagicMock, patch
import pytest
import requests


SAMPLE_ANOMALIES = [
    {
        "service": "EC2",
        "region": "eu-west-1",
        "account_id": "123456789012",
        "team_tag": "platform",
        "cost_usd": 500.0,
        "baseline_usd": 10.0,
        "deviation_pct": 4900.0,
        "severity": "high",
        "date": "2024-01-31",
        "narrative": "EC2 costs spiked — terminate idle instances to save ~$490/month.",
    },
    {
        "service": "S3",
        "region": "eu-west-1",
        "account_id": "123456789012",
        "team_tag": "data",
        "cost_usd": 15.0,
        "baseline_usd": 8.0,
        "deviation_pct": 87.5,
        "severity": "medium",
        "date": "2024-01-31",
        "narrative": "S3 egress increased — review data transfer patterns.",
    },
]


@pytest.fixture(autouse=True)
def env_vars(monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/TEST/TEST/TEST")


class TestPostSummary:
    def test_happy_path_posts_to_webhook(self):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None

        with patch("src.slack_notifier.requests.post", return_value=mock_response) as mock_post:
            from src.slack_notifier import post_summary
            post_summary(SAMPLE_ANOMALIES)

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args[1]
        assert call_kwargs["json"] is not None
        assert "hooks.slack.com" in mock_post.call_args[0][0]

    def test_blocks_contain_service_names(self):
        captured_payload = {}

        def capture_post(url, json=None, **kwargs):
            captured_payload.update(json or {})
            resp = MagicMock()
            resp.raise_for_status.return_value = None
            return resp

        with patch("src.slack_notifier.requests.post", side_effect=capture_post):
            from src.slack_notifier import post_summary
            post_summary(SAMPLE_ANOMALIES)

        all_text = str(captured_payload)
        assert "EC2" in all_text
        assert "S3" in all_text

    def test_footer_has_correct_counts(self):
        captured_payload = {}

        def capture_post(url, json=None, **kwargs):
            captured_payload.update(json or {})
            resp = MagicMock()
            resp.raise_for_status.return_value = None
            return resp

        with patch("src.slack_notifier.requests.post", side_effect=capture_post):
            from src.slack_notifier import post_summary
            post_summary(SAMPLE_ANOMALIES)

        footer_block = captured_payload["blocks"][-1]
        footer_text = footer_block["elements"][0]["text"]
        assert "Total anomalies: 2" in footer_text
        assert "High: 1" in footer_text
        assert "Medium: 1" in footer_text

    def test_empty_anomaly_list_still_posts(self):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None

        with patch("src.slack_notifier.requests.post", return_value=mock_response) as mock_post:
            from src.slack_notifier import post_summary
            post_summary([])

        mock_post.assert_called_once()

    def test_http_error_propagates(self):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.HTTPError("500 Server Error")

        with patch("src.slack_notifier.requests.post", return_value=mock_response):
            from src.slack_notifier import post_summary
            with pytest.raises(requests.HTTPError):
                post_summary(SAMPLE_ANOMALIES)
