import json
from unittest.mock import MagicMock, patch

from src.s3_reporter import write_report_to_s3


class TestWriteReportToS3:
    def test_writes_dated_and_latest_keys(self, monkeypatch):
        monkeypatch.setenv("AWS_BILLING_BUCKET", "billing-bucket")
        monkeypatch.setenv("AWS_REGION", "eu-north-1")

        mock_s3 = MagicMock()
        report = {"status": "success", "anomaly_count": 0}

        with patch("src.s3_reporter.client", return_value=mock_s3):
            uri = write_report_to_s3(report)

        assert uri == "s3://billing-bucket/reports/latest.json"
        assert mock_s3.put_object.call_count == 2
        keys = [call.kwargs["Key"] for call in mock_s3.put_object.call_args_list]
        assert "reports/latest.json" in keys
        assert any(key.startswith("reports/") and key.endswith(".json") and key != "reports/latest.json" for key in keys)

        body = mock_s3.put_object.call_args.kwargs["Body"].decode()
        assert json.loads(body)["status"] == "success"
