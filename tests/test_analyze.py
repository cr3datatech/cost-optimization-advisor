import json

import pandas as pd

from src.analyze import build_analysis_report, format_analysis_report, run_analysis


SAMPLE_ROWS = [
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


class TestBuildAnalysisReport:
    def test_builds_summary(self):
        df = pd.DataFrame(SAMPLE_ROWS)
        report = build_analysis_report(df)

        assert report["rows"] == 2
        assert report["total_cost_usd"] == 47.5
        assert report["top_services"]["EC2"] == 42.5
        assert "anomaly_count" in report


class TestFormatAnalysisReport:
    def test_renders_human_readable_report(self):
        report = {
            "rows": 2,
            "total_cost_usd": 47.5,
            "date_range": {"start": "2024-01-15", "end": "2024-01-16"},
            "top_services": {"EC2": 42.5, "S3": 5.0},
            "anomaly_count": 0,
            "anomalies": [],
        }

        text = format_analysis_report(report, "s3://bucket/latest.csv")

        assert "Cost Analysis Report" in text
        assert "Total cost: $47.50" in text
        assert "Anomalies detected: 0" in text


class TestRunAnalysis:
    def test_uses_local_csv(self, tmp_path):
        csv_path = tmp_path / "billing.csv"
        pd.DataFrame(SAMPLE_ROWS).to_csv(csv_path, index=False)

        report, source = run_analysis(local_csv=str(csv_path))

        assert source == str(csv_path)
        assert report["rows"] == 2

    def test_saves_json_output(self, tmp_path):
        csv_path = tmp_path / "billing.csv"
        output_path = tmp_path / "report.json"
        pd.DataFrame(SAMPLE_ROWS).to_csv(csv_path, index=False)

        report, _ = run_analysis(local_csv=str(csv_path))
        output_path.write_text(json.dumps(report, indent=2))

        saved = json.loads(output_path.read_text())
        assert saved["rows"] == 2
