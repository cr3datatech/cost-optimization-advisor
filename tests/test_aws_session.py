from unittest.mock import MagicMock, patch

import pytest

from src.aws_session import client, get_profile_name, get_session, list_profiles


class TestGetProfileName:
    def test_returns_none_when_unset(self, monkeypatch):
        monkeypatch.delenv("AWS_PROFILE", raising=False)
        assert get_profile_name() is None

    def test_returns_profile_when_set(self, monkeypatch):
        monkeypatch.setenv("AWS_PROFILE", "work-account")
        assert get_profile_name() == "work-account"

    def test_ignores_blank_profile(self, monkeypatch):
        monkeypatch.setenv("AWS_PROFILE", "   ")
        assert get_profile_name() is None


class TestGetSession:
    def test_uses_profile_when_set(self, monkeypatch):
        monkeypatch.setenv("AWS_PROFILE", "work-account")
        mock_session = MagicMock()

        with patch("src.aws_session.boto3.Session", return_value=mock_session) as session_ctor:
            result = get_session()

        session_ctor.assert_called_once_with(profile_name="work-account")
        assert result is mock_session

    def test_uses_default_chain_when_profile_unset(self, monkeypatch):
        monkeypatch.delenv("AWS_PROFILE", raising=False)
        mock_session = MagicMock()

        with patch("src.aws_session.boto3.Session", return_value=mock_session) as session_ctor:
            result = get_session()

        session_ctor.assert_called_once_with()
        assert result is mock_session


class TestClient:
    def test_delegates_to_session(self):
        mock_session = MagicMock()
        mock_client = MagicMock()
        mock_session.client.return_value = mock_client

        with patch("src.aws_session.get_session", return_value=mock_session):
            result = client("s3", region_name="eu-west-1")

        mock_session.client.assert_called_once_with("s3", region_name="eu-west-1")
        assert result is mock_client


class TestListProfiles:
    def test_returns_available_profiles(self):
        with patch("src.aws_session.boto3.Session") as session_ctor:
            session_ctor.return_value.available_profiles = ["default", "work"]
            assert list_profiles() == ["default", "work"]
