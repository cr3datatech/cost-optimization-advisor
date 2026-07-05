import os
import io
from pathlib import Path

import pandas as pd

from src.aws_session import client


def load_latest_billing_data() -> pd.DataFrame:
    """Download the most recent billing CSV from S3 and return a normalised DataFrame."""
    bucket = os.environ["AWS_BILLING_BUCKET"]
    region = os.environ.get("AWS_REGION", "eu-west-1")

    s3 = client("s3", region_name=region)

    response = s3.list_objects_v2(Bucket=bucket)
    objects = response.get("Contents", [])
    if not objects:
        raise ValueError(f"No objects found in bucket: {bucket}")

    csv_objects = [o for o in objects if o["Key"].endswith(".csv")]
    if not csv_objects:
        raise ValueError(f"No CSV files found in bucket: {bucket}")

    latest = max(csv_objects, key=lambda o: o["LastModified"])
    return load_billing_data_from_key(bucket, latest["Key"], s3_client=s3)


def load_billing_data_from_key(
    bucket: str,
    key: str,
    s3_client=None,
) -> pd.DataFrame:
    """Download a specific billing CSV from S3."""
    if s3_client is None:
        region = os.environ.get("AWS_REGION", "eu-west-1")
        s3_client = client("s3", region_name=region)

    obj = s3_client.get_object(Bucket=bucket, Key=key)
    raw = obj["Body"].read()
    return _parse_billing_csv(raw)


def load_billing_data_from_file(path: Path) -> pd.DataFrame:
    """Load a billing CSV from the local filesystem."""
    return _parse_billing_csv(path.read_bytes())


def _parse_billing_csv(raw: bytes) -> pd.DataFrame:
    df = pd.read_csv(io.BytesIO(raw))
    df = _normalise(df)
    return df.dropna(subset=["cost_usd"])


def _normalise(df: pd.DataFrame) -> pd.DataFrame:
    """Map common AWS CUR column names to the canonical schema."""
    column_map = {
        # AWS Cost & Usage Report column aliases
        "line_item_usage_start_date": "date",
        "line_item_product_code": "service",
        "product_region": "region",
        "line_item_usage_account_id": "account_id",
        "resource_tags_user_team": "team_tag",
        "line_item_blended_cost": "cost_usd",
        # Simplified / test aliases
        "date": "date",
        "service": "service",
        "region": "region",
        "account_id": "account_id",
        "team_tag": "team_tag",
        "cost_usd": "cost_usd",
    }

    df = df.rename(columns={k: v for k, v in column_map.items() if k in df.columns})

    required = ["date", "service", "region", "account_id", "team_tag", "cost_usd"]
    for col in required:
        if col not in df.columns:
            df[col] = None

    df["cost_usd"] = pd.to_numeric(df["cost_usd"], errors="coerce")
    df["date"] = pd.to_datetime(df["date"], errors="coerce")

    return df[required]
