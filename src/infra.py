import json
import time
from dataclasses import dataclass
from pathlib import Path

from botocore.exceptions import ClientError

ROOT = Path(__file__).resolve().parent.parent
IAM_POLICY_PATH = ROOT / "infra" / "iam_policy.json"
TRUST_POLICY_PATH = ROOT / "infra" / "lambda_trust_policy.json"


@dataclass
class InfraResult:
    bucket_name: str
    bucket_created: bool
    role_name: str
    role_arn: str
    role_created: bool


def load_lambda_policy(bucket_name: str) -> str:
    template = IAM_POLICY_PATH.read_text()
    return template.replace("${BILLING_BUCKET}", bucket_name)


def bucket_owned_in_account(s3_client, bucket_name: str) -> bool:
    """Return True when the bucket already exists in the caller's account."""
    for page in s3_client.get_paginator("list_buckets").paginate():
        for bucket in page.get("Buckets", []):
            if bucket["Name"] == bucket_name:
                return True
    return False


def ensure_billing_bucket(s3_client, bucket_name: str, region: str) -> bool:
    """Create the billing bucket when missing. Returns True if created."""
    if bucket_owned_in_account(s3_client, bucket_name):
        return False

    for attempt in range(6):
        try:
            if region == "us-east-1":
                s3_client.create_bucket(Bucket=bucket_name)
            else:
                s3_client.create_bucket(
                    Bucket=bucket_name,
                    CreateBucketConfiguration={"LocationConstraint": region},
                )
            break
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code == "OperationAborted" and attempt < 5:
                time.sleep(2 ** attempt)
                continue
            if code in {"BucketAlreadyExists", "BucketAlreadyOwnedByYou"}:
                raise RuntimeError(
                    f"S3 bucket name '{bucket_name}' is already taken globally. "
                    "Choose a unique AWS_BILLING_BUCKET value in .env and retry."
                ) from exc
            raise

    s3_client.put_public_access_block(
        Bucket=bucket_name,
        PublicAccessBlockConfiguration={
            "BlockPublicAcls": True,
            "IgnorePublicAcls": True,
            "BlockPublicPolicy": True,
            "RestrictPublicBuckets": True,
        },
    )
    return True


def role_exists(iam_client, role_name: str) -> bool:
    try:
        iam_client.get_role(RoleName=role_name)
        return True
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "NoSuchEntity":
            return False
        raise


def ensure_lambda_role(
    iam_client,
    role_name: str,
    bucket_name: str,
    policy_name: str = "cost-advisor-lambda-policy",
) -> tuple[str, bool]:
    """Create or update the Lambda execution role. Returns (role_arn, created)."""
    trust_policy = TRUST_POLICY_PATH.read_text()
    policy_document = load_lambda_policy(bucket_name)
    created = False

    if role_exists(iam_client, role_name):
        iam_client.put_role_policy(
            RoleName=role_name,
            PolicyName=policy_name,
            PolicyDocument=policy_document,
        )
    else:
        response = iam_client.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=trust_policy,
            Description="Execution role for cost-optimization-advisor Lambda",
        )
        iam_client.put_role_policy(
            RoleName=role_name,
            PolicyName=policy_name,
            PolicyDocument=policy_document,
        )
        created = True
        role_arn = response["Role"]["Arn"]
        return role_arn, created

    response = iam_client.get_role(RoleName=role_name)
    return response["Role"]["Arn"], created


def provision_infrastructure(
    session,
    bucket_name: str,
    region: str,
    role_name: str,
) -> InfraResult:
    s3_client = session.client("s3", region_name=region)
    iam_client = session.client("iam")

    bucket_created = ensure_billing_bucket(s3_client, bucket_name, region)
    role_arn, role_created = ensure_lambda_role(iam_client, role_name, bucket_name)

    return InfraResult(
        bucket_name=bucket_name,
        bucket_created=bucket_created,
        role_name=role_name,
        role_arn=role_arn,
        role_created=role_created,
    )


def format_infra_summary(result: InfraResult, region: str) -> str:
    bucket_status = "created" if result.bucket_created else "already exists"
    role_status = "created" if result.role_created else "already exists"

    return (
        f"Infrastructure ready in {region}:\n"
        f"  S3 bucket: {result.bucket_name} ({bucket_status})\n"
        f"  IAM role:  {result.role_name} ({role_status})\n"
        f"  Role ARN:  {result.role_arn}\n"
        "\n"
        "Add or update these values in .env:\n"
        f"  AWS_BILLING_BUCKET={result.bucket_name}\n"
        f"  LAMBDA_ROLE_ARN={result.role_arn}\n"
        "\n"
        "Next steps:\n"
        "  1. Enable AWS Cost & Usage Reports in the Billing console\n"
        f"     and point delivery to s3://{result.bucket_name}/\n"
        "  2. Wait for the first CSV export (can take up to 24 hours)\n"
        "  3. Run: python scripts/manage.py analyze\n"
        "  4. Run: python scripts/manage.py deploy"
    )
