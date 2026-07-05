import json
import os
from datetime import datetime, timezone

from src.aws_session import client


def write_report_to_s3(report: dict) -> str:
    """Write a JSON report to S3 and update reports/latest.json."""
    bucket = os.environ["AWS_BILLING_BUCKET"]
    region = os.environ.get("AWS_REGION", "eu-west-1")
    timestamp = datetime.now(timezone.utc)
    dated_key = f"reports/{timestamp.strftime('%Y/%m/%d')}/run-{timestamp.strftime('%H%M%S')}.json"
    latest_key = "reports/latest.json"
    body = json.dumps(report, indent=2, default=str).encode("utf-8")

    s3 = client("s3", region_name=region)
    for key in (dated_key, latest_key):
        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=body,
            ContentType="application/json",
        )

    return f"s3://{bucket}/{latest_key}"
