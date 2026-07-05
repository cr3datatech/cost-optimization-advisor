import json
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from botocore.exceptions import ClientError

from src.infra import (
    bucket_owned_in_account,
    ensure_billing_bucket,
    ensure_lambda_role,
    load_lambda_policy,
    provision_infrastructure,
)


class TestLoadLambdaPolicy:
    def test_substitutes_bucket_name(self):
        policy = load_lambda_policy("my-billing-bucket")
        assert "${BILLING_BUCKET}" not in policy
        assert "arn:aws:s3:::my-billing-bucket" in policy


class TestBucketOwnedInAccount:
    def test_returns_true_when_bucket_listed(self):
        s3 = MagicMock()
        s3.get_paginator.return_value.paginate.return_value = [
            {"Buckets": [{"Name": "bucket"}]}
        ]
        assert bucket_owned_in_account(s3, "bucket") is True

    def test_returns_false_when_bucket_missing(self):
        s3 = MagicMock()
        s3.get_paginator.return_value.paginate.return_value = [{"Buckets": []}]
        assert bucket_owned_in_account(s3, "bucket") is False


class TestEnsureBillingBucket:
    def test_skips_creation_when_bucket_exists(self):
        s3 = MagicMock()
        with patch("src.infra.bucket_owned_in_account", return_value=True):
            created = ensure_billing_bucket(s3, "bucket", "eu-west-1")
        assert created is False
        s3.create_bucket.assert_not_called()

    def test_creates_bucket_with_region(self):
        s3 = MagicMock()
        s3.get_paginator.return_value.paginate.return_value = [{"Buckets": []}]
        with patch("src.infra.bucket_owned_in_account", return_value=False):
            created = ensure_billing_bucket(s3, "bucket", "eu-west-1")
        assert created is True
        s3.create_bucket.assert_called_once_with(
            Bucket="bucket",
            CreateBucketConfiguration={"LocationConstraint": "eu-west-1"},
        )
        s3.put_public_access_block.assert_called_once()


class TestEnsureLambdaRole:
    def test_creates_role_when_missing(self):
        iam = MagicMock()
        iam.get_role.side_effect = ClientError(
            {"Error": {"Code": "NoSuchEntity", "Message": "missing"}},
            "GetRole",
        )
        iam.create_role.return_value = {"Role": {"Arn": "arn:aws:iam::123:role/cost-advisor-lambda-role"}}

        role_arn, created = ensure_lambda_role(iam, "cost-advisor-lambda-role", "bucket")

        assert created is True
        assert role_arn == "arn:aws:iam::123:role/cost-advisor-lambda-role"
        iam.create_role.assert_called_once()
        iam.put_role_policy.assert_called_once()

    def test_updates_policy_when_role_exists(self):
        iam = MagicMock()
        iam.get_role.return_value = {"Role": {"Arn": "arn:aws:iam::123:role/cost-advisor-lambda-role"}}

        role_arn, created = ensure_lambda_role(iam, "cost-advisor-lambda-role", "bucket")

        assert created is False
        assert role_arn == "arn:aws:iam::123:role/cost-advisor-lambda-role"
        iam.create_role.assert_not_called()
        iam.put_role_policy.assert_called_once()


class TestProvisionInfrastructure:
    def test_provisions_bucket_and_role(self):
        session = MagicMock()
        session.client.side_effect = lambda service, **kwargs: MagicMock(name=service)

        with patch("src.infra.ensure_billing_bucket", return_value=True) as ensure_bucket:
            with patch(
                "src.infra.ensure_lambda_role",
                return_value=("arn:aws:iam::123:role/cost-advisor-lambda-role", True),
            ) as ensure_role:
                result = provision_infrastructure(
                    session,
                    bucket_name="billing-bucket",
                    region="eu-west-1",
                    role_name="cost-advisor-lambda-role",
                )

        ensure_bucket.assert_called_once()
        ensure_role.assert_called_once()
        assert result.bucket_created is True
        assert result.role_created is True
        assert result.role_arn.endswith("cost-advisor-lambda-role")
