import os
from typing import Optional

import boto3
from boto3.session import Session


def get_profile_name() -> Optional[str]:
    """Return AWS profile from environment, or None for the default credential chain."""
    profile = os.environ.get("AWS_PROFILE", "").strip()
    return profile or None


def get_session() -> Session:
    """Build a boto3 session using AWS_PROFILE when set."""
    profile = get_profile_name()
    if profile:
        return boto3.Session(profile_name=profile)
    return boto3.Session()


def client(service_name: str, **kwargs):
    """Create a boto3 client using the configured AWS profile."""
    return get_session().client(service_name, **kwargs)


def list_profiles() -> list[str]:
    """Return profile names from ~/.aws/config and ~/.aws/credentials."""
    return boto3.Session().available_profiles
