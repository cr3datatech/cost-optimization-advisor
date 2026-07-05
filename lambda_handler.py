import logging
from datetime import datetime, timezone

from src.analyze import build_analysis_report
from src.ingestion import load_latest_billing_data
from src.llm_advisor import generate_recommendation
from src.s3_reporter import write_report_to_s3
from src.slack_notifier import post_summary

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def handler(event: dict, context) -> dict:
    """AWS Lambda entry point. Analyses billing data, writes a report to S3, and notifies Slack."""
    report = {
        "status": "running",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "anomaly_count": 0,
        "anomalies": [],
        "slack_notified": False,
    }

    try:
        logger.info("Loading latest billing data from S3")
        df = load_latest_billing_data()
        logger.info("Loaded %d billing rows", len(df))

        report.update(build_analysis_report(df))
        anomalies = report["anomalies"]

        if anomalies:
            logger.info("Generating LLM narratives for %d anomalies", len(anomalies))
            for anomaly in anomalies:
                try:
                    anomaly["narrative"] = generate_recommendation(anomaly)
                except Exception as exc:
                    logger.warning(
                        "Failed to generate narrative for %s: %s",
                        anomaly.get("service"),
                        exc,
                    )
                    anomaly["narrative"] = ""

            logger.info("Posting summary to Slack")
            post_summary(anomalies)
            report["slack_notified"] = True
        else:
            logger.info("No anomalies detected — skipping Slack notification")

        report["status"] = "success"
    except Exception as exc:
        logger.exception("Cost advisor run failed")
        report["status"] = "error"
        report["error"] = str(exc)

    report["report_uri"] = write_report_to_s3(report)
    logger.info("Wrote report to %s", report["report_uri"])

    if report["status"] == "error":
        return {"statusCode": 500, "body": report["error"], "report_uri": report["report_uri"]}

    return {
        "statusCode": 200,
        "body": f"Wrote report to {report['report_uri']}",
        "anomaly_count": report.get("anomaly_count", 0),
        "slack_notified": report.get("slack_notified", False),
    }
