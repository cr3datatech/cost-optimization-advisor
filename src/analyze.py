import json
from pathlib import Path

import pandas as pd

from src.anomaly_detection import detect_anomalies
from src.ingestion import load_billing_data_from_file, load_latest_billing_data


def build_analysis_report(df: pd.DataFrame) -> dict:
    anomalies = detect_anomalies(df)
    service_totals = (
        df.groupby("service")["cost_usd"]
        .sum()
        .sort_values(ascending=False)
        .round(2)
        .to_dict()
    )

    dates = pd.to_datetime(df["date"], errors="coerce").dropna()
    return {
        "rows": len(df),
        "total_cost_usd": round(float(df["cost_usd"].sum()), 2),
        "date_range": {
            "start": str(dates.min().date()) if not dates.empty else None,
            "end": str(dates.max().date()) if not dates.empty else None,
        },
        "top_services": service_totals,
        "anomaly_count": len(anomalies),
        "anomalies": anomalies,
    }


def load_billing_data(local_csv: str | None = None) -> tuple[pd.DataFrame, str]:
    if local_csv:
        path = Path(local_csv)
        return load_billing_data_from_file(path), str(path)

    df = load_latest_billing_data()
    bucket = __import__("os").environ.get("AWS_BILLING_BUCKET", "unknown-bucket")
    return df, f"s3://{bucket}/ (latest CSV)"


def format_analysis_report(report: dict, source: str) -> str:
    lines = [
        "Cost Analysis Report",
        "====================",
        f"Source: {source}",
        f"Rows analysed: {report['rows']}",
        f"Total cost: ${report['total_cost_usd']:,.2f}",
    ]

    date_range = report["date_range"]
    if date_range["start"] and date_range["end"]:
        lines.append(f"Date range: {date_range['start']} to {date_range['end']}")

    if report["top_services"]:
        lines.append("")
        lines.append("Top services by cost:")
        for service, cost in list(report["top_services"].items())[:10]:
            lines.append(f"  - {service}: ${cost:,.2f}")

    lines.append("")
    lines.append(f"Anomalies detected: {report['anomaly_count']}")

    if report["anomalies"]:
        lines.append("")
        for anomaly in report["anomalies"]:
            severity = anomaly["severity"].upper()
            lines.append(
                f"[{severity}] {anomaly['service']} | {anomaly['region']} | "
                f"team={anomaly['team_tag']} | {anomaly['date']}"
            )
            lines.append(
                f"  Actual ${anomaly['cost_usd']:,.2f} vs baseline "
                f"${anomaly['baseline_usd']:,.2f} "
                f"(+{anomaly['deviation_pct']:.1f}%)"
            )
            narrative = anomaly.get("narrative")
            if narrative:
                lines.append(f"  Recommendation: {narrative}")

    return "\n".join(lines)


def run_analysis(
    local_csv: str | None = None,
    with_narratives: bool = False,
) -> tuple[dict, str]:
    df, source = load_billing_data(local_csv)
    report = build_analysis_report(df)

    if with_narratives and report["anomalies"]:
        from src.llm_advisor import generate_recommendation

        for anomaly in report["anomalies"]:
            try:
                anomaly["narrative"] = generate_recommendation(anomaly)
            except Exception as exc:
                anomaly["narrative"] = f"(failed to generate narrative: {exc})"

    return report, source


def save_report(report: dict, output_path: Path) -> None:
    output_path.write_text(json.dumps(report, indent=2))
