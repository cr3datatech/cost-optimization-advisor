import os
import io
import boto3
import pandas as pd


def load_latest_billing_data() -> pd.DataFrame:
    """Download the most recent billing CSV from S3 and return a normalised DataFrame."""
    bucket = os.environ["AWS_BILLING_BUCKET"]
    region = os.environ.get("AWS_REGION", "eu-west-1")

    s3 = boto3.client("s3", region_name=region)

    response = s3.list_objects_v2(Bucket=bucket)
    objects = response.get("Contents", [])
    if not objects:
        raise ValueError(f"No objects found in bucket: {bucket}")

    csv_objects = [o for o in objects if o["Key"].endswith(".csv")]
    if not csv_objects:
        raise ValueError(f"No CSV files found in bucket: {bucket}")

    latest = max(csv_objects, key=lambda o: o["LastModified"])
    key = latest["Key"]

    obj = s3.get_object(Bucket=bucket, Key=key)
    raw = obj["Body"].read()

    df = pd.read_csv(io.BytesIO(raw))

    df = _normalise(df)
    df = df.dropna(subset=["cost_usd"])

    return df


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
