import io
from unittest.mock import MagicMock, patch
import pandas as pd
import pytest


@pytest.fixture(autouse=True)
def env_vars(monkeypatch):
    monkeypatch.setenv("AWS_BILLING_BUCKET", "test-bucket")
    monkeypatch.setenv("AWS_REGION", "eu-west-1")


def _make_csv_bytes(rows: list[dict]) -> bytes:
    df = pd.DataFrame(rows)
    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    return buf.getvalue()


def _make_s3_mock(csv_bytes: bytes, key: str = "billing/2024-01.csv"):
    from datetime import datetime, timezone

    mock_s3 = MagicMock()
    mock_s3.list_objects_v2.return_value = {
        "Contents": [
            {"Key": key, "LastModified": datetime(2024, 1, 31, tzinfo=timezone.utc)}
        ]
    }
    mock_s3.get_object.return_value = {"Body": io.BytesIO(csv_bytes)}
    return mock_s3


class TestLoadLatestBillingData:
    def test_happy_path_normalises_columns(self):
        rows = [
            {
                "date": "2024-01-15",
                "service": "EC2",
                "region": "eu-west-1",
                "account_id": "123456789012",
                "team_tag": "platform",
                "cost_usd": 42.5,
            },
            {
                "date": "2024-01-16",
                "service": "S3",
                "region": "eu-west-1",
                "account_id": "123456789012",
                "team_tag": "data",
                "cost_usd": 5.0,
            },
        ]
        csv_bytes = _make_csv_bytes(rows)
        mock_s3 = _make_s3_mock(csv_bytes)

        with patch("src.ingestion.boto3.client", return_value=mock_s3):
            from src.ingestion import load_latest_billing_data
            df = load_latest_billing_data()

        assert list(df.columns) == ["date", "service", "region", "account_id", "team_tag", "cost_usd"]
        assert len(df) == 2
        assert df["service"].tolist() == ["EC2", "S3"]

    def test_drops_null_cost_rows(self):
        rows = [
            {
                "date": "2024-01-15",
                "service": "EC2",
                "region": "eu-west-1",
                "account_id": "123456789012",
                "team_tag": "platform",
                "cost_usd": 42.5,
            },
            {
                "date": "2024-01-16",
                "service": "Lambda",
                "region": "eu-west-1",
                "account_id": "123456789012",
                "team_tag": "platform",
                "cost_usd": None,
            },
        ]
        csv_bytes = _make_csv_bytes(rows)
        mock_s3 = _make_s3_mock(csv_bytes)

        with patch("src.ingestion.boto3.client", return_value=mock_s3):
            from src.ingestion import load_latest_billing_data
            df = load_latest_billing_data()

        assert len(df) == 1
        assert df["service"].iloc[0] == "EC2"

    def test_raises_when_bucket_empty(self):
        mock_s3 = MagicMock()
        mock_s3.list_objects_v2.return_value = {"Contents": []}

        with patch("src.ingestion.boto3.client", return_value=mock_s3):
            from src.ingestion import load_latest_billing_data
            with pytest.raises(ValueError, match="No objects found"):
                load_latest_billing_data()

    def test_raises_when_no_csv_files(self):
        from datetime import datetime, timezone

        mock_s3 = MagicMock()
        mock_s3.list_objects_v2.return_value = {
            "Contents": [
                {"Key": "billing/report.json", "LastModified": datetime(2024, 1, 31, tzinfo=timezone.utc)}
            ]
        }

        with patch("src.ingestion.boto3.client", return_value=mock_s3):
            from src.ingestion import load_latest_billing_data
            with pytest.raises(ValueError, match="No CSV files"):
                load_latest_billing_data()

    def test_picks_most_recent_csv(self):
        from datetime import datetime, timezone

        rows = [
            {
                "date": "2024-02-01",
                "service": "RDS",
                "region": "eu-west-1",
                "account_id": "111",
                "team_tag": "db",
                "cost_usd": 100.0,
            }
        ]
        csv_bytes = _make_csv_bytes(rows)

        mock_s3 = MagicMock()
        mock_s3.list_objects_v2.return_value = {
            "Contents": [
                {"Key": "billing/2024-01.csv", "LastModified": datetime(2024, 1, 31, tzinfo=timezone.utc)},
                {"Key": "billing/2024-02.csv", "LastModified": datetime(2024, 2, 28, tzinfo=timezone.utc)},
            ]
        }
        mock_s3.get_object.return_value = {"Body": io.BytesIO(csv_bytes)}

        with patch("src.ingestion.boto3.client", return_value=mock_s3):
            from src.ingestion import load_latest_billing_data
            load_latest_billing_data()

        call_args = mock_s3.get_object.call_args
        assert call_args[1]["Key"] == "billing/2024-02.csv"
