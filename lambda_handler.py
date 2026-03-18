import logging
from dotenv import load_dotenv

load_dotenv()

from src.ingestion import load_latest_billing_data
from src.anomaly_detection import detect_anomalies
from src.llm_advisor import generate_recommendation
from src.slack_notifier import post_summary

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def handler(event: dict, context) -> dict:
    """AWS Lambda entry point. Orchestrates the full cost-anomaly pipeline."""
    logger.info("Loading latest billing data from S3")
    df = load_latest_billing_data()
    logger.info("Loaded %d billing rows", len(df))

    logger.info("Running anomaly detection")
    anomalies = detect_anomalies(df)
    logger.info("Detected %d anomalies", len(anomalies))

    if not anomalies:
        logger.info("No anomalies detected — skipping Slack notification")
        return {"statusCode": 200, "body": "No anomalies detected"}

    logger.info("Generating LLM narratives for %d anomalies", len(anomalies))
    for anomaly in anomalies:
        try:
            anomaly["narrative"] = generate_recommendation(anomaly)
        except Exception as exc:
            logger.warning("Failed to generate narrative for %s: %s", anomaly.get("service"), exc)
            anomaly["narrative"] = ""

    logger.info("Posting summary to Slack")
    post_summary(anomalies)
    logger.info("Done")

    return {"statusCode": 200, "body": f"Posted {len(anomalies)} anomalies to Slack"}
