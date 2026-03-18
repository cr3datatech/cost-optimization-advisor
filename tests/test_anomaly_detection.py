import pandas as pd
import numpy as np
import pytest
from datetime import date, timedelta

from src.anomaly_detection import detect_anomalies


def _make_df(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df["cost_usd"] = df["cost_usd"].astype(float)
    return df


def _steady_rows(service="EC2", region="eu-west-1", team="platform", n=30, base=10.0):
    start = date(2024, 1, 1)
    return [
        {
            "date": str(start + timedelta(days=i)),
            "service": service,
            "region": region,
            "account_id": "123456789012",
            "team_tag": team,
            "cost_usd": base,
        }
        for i in range(n)
    ]


class TestDetectAnomalies:
    def test_returns_empty_list_for_empty_df(self):
        df = pd.DataFrame(columns=["date", "service", "region", "account_id", "team_tag", "cost_usd"])
        result = detect_anomalies(df)
        assert result == []

    def test_detects_obvious_spike(self):
        rows = _steady_rows(base=10.0)
        # Add a massive spike on day 31
        rows.append({
            "date": "2024-02-01",
            "service": "EC2",
            "region": "eu-west-1",
            "account_id": "123456789012",
            "team_tag": "platform",
            "cost_usd": 500.0,  # >100% above baseline → high severity
        })
        df = _make_df(rows)
        result = detect_anomalies(df)

        assert len(result) >= 1
        spike = next(a for a in result if a["cost_usd"] == 500.0)
        assert spike["severity"] == "high"
        assert spike["service"] == "EC2"
        assert spike["deviation_pct"] > 100

    def test_severity_thresholds(self):
        from src.anomaly_detection import _severity

        assert _severity(150) == "high"
        assert _severity(75) == "medium"
        assert _severity(30) == "low"
        assert _severity(10) == "low"

    def test_anomaly_dict_has_required_keys(self):
        rows = _steady_rows(base=10.0)
        rows.append({
            "date": "2024-02-01",
            "service": "EC2",
            "region": "eu-west-1",
            "account_id": "123456789012",
            "team_tag": "platform",
            "cost_usd": 500.0,
        })
        df = _make_df(rows)
        result = detect_anomalies(df)

        required_keys = {"service", "region", "account_id", "team_tag", "cost_usd",
                         "baseline_usd", "deviation_pct", "severity", "date"}
        for anomaly in result:
            assert required_keys.issubset(anomaly.keys()), f"Missing keys: {required_keys - anomaly.keys()}"

    def test_no_false_positives_on_flat_data(self):
        # Perfectly flat data (std=0) should not produce z-score anomalies
        rows = _steady_rows(base=10.0, n=35)
        df = _make_df(rows)
        result = detect_anomalies(df)
        # z-score method should produce nothing; IsolationForest might catch outliers but flat data won't
        zscore_hits = [a for a in result if a["cost_usd"] == 10.0]
        assert len(zscore_hits) == 0

    def test_results_sorted_by_severity(self):
        rows = _steady_rows(base=10.0, n=30)
        rows += [
            {"date": "2024-02-01", "service": "EC2", "region": "eu-west-1",
             "account_id": "123", "team_tag": "platform", "cost_usd": 500.0},
            {"date": "2024-02-02", "service": "S3", "region": "eu-west-1",
             "account_id": "123", "team_tag": "data", "cost_usd": 20.0},
        ]
        df = _make_df(rows)
        result = detect_anomalies(df)

        severity_rank = {"high": 3, "medium": 2, "low": 1}
        ranks = [severity_rank[a["severity"]] for a in result]
        assert ranks == sorted(ranks, reverse=True)
