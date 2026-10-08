"""Unit tests for date, time and slot logic. No LLM or live session needed."""

import datetime
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
from google.auth.exceptions import RefreshError

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import calendar_service
from calendar_service import TIMEZONE, parse_day, parse_time


def today():
    return datetime.datetime.now(TIMEZONE).date()


class TestParseDay:
    def test_today(self):
        assert parse_day("today") == today()

    def test_tomorrow(self):
        assert parse_day("tomorrow") == today() + datetime.timedelta(days=1)

    def test_weekday_name_resolves_within_a_week(self):
        result = parse_day("thursday")
        assert result is not None
        assert result.weekday() == 3
        assert 0 <= (result - today()).days <= 6

    def test_extra_words_are_tolerated(self):
        assert parse_day("on Saturday please") == parse_day("saturday")

    def test_case_is_ignored(self):
        assert parse_day("THURSDAY") == parse_day("thursday")

    @pytest.mark.parametrize("text", ["the 24th", "next month", "sometime", ""])
    def test_unparseable_returns_none(self, text):
        assert parse_day(text) is None


class TestParseTime:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("10 AM", datetime.time(10, 0)),
            ("10:30 am", datetime.time(10, 30)),
            ("2:30 pm", datetime.time(14, 30)),
            ("12 pm", datetime.time(12, 0)),
            ("5 PM", datetime.time(17, 0)),
        ],
    )
    def test_valid_times(self, text, expected):
        assert parse_time(text) == expected

    def test_bare_hour_assumes_afternoon(self):
        # "book me at 3" during clinic hours means 3 PM
        assert parse_time("3") == datetime.time(15, 0)

    @pytest.mark.parametrize("text", ["10:15 am", "quarter past ten", "midnight-ish"])
    def test_invalid_slots_return_none(self, text):
        assert parse_time(text) is None


def test_service_account_auth_supports_headless_deployment(monkeypatch):
    credentials = object()
    expected_service = object()
    build = Mock(return_value=expected_service)
    from_service_account = Mock(return_value=credentials)

    monkeypatch.setenv(
        "GOOGLE_SERVICE_ACCOUNT_JSON",
        '{"type":"service_account","client_email":"demo@example.com"}',
    )
    monkeypatch.setattr(
        calendar_service.service_account.Credentials,
        "from_service_account_info",
        from_service_account,
    )
    monkeypatch.setattr(calendar_service, "build", build)
    monkeypatch.setattr(
        calendar_service.os.path,
        "exists",
        Mock(side_effect=AssertionError("interactive OAuth files must not be read")),
    )

    assert calendar_service.get_service() is expected_service
    from_service_account.assert_called_once_with(
        {"type": "service_account", "client_email": "demo@example.com"},
        scopes=calendar_service.SCOPES,
    )
    build.assert_called_once_with("calendar", "v3", credentials=credentials)


def test_invalid_service_account_json_fails_explicitly(monkeypatch):
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_JSON", "{")

    with pytest.raises(ValueError, match="valid JSON"):
        calendar_service.get_service()


def test_invalid_oauth_refresh_grant_starts_new_consent_flow(monkeypatch, tmp_path):
    stale_credentials = Mock(
        valid=False,
        expired=True,
        refresh_token="stale-refresh-token",
    )
    stale_credentials.refresh.side_effect = RefreshError("invalid_grant")
    refreshed_credentials = Mock(
        valid=True, to_json=Mock(return_value='{"token":"new"}')
    )
    oauth_flow = Mock(run_local_server=Mock(return_value=refreshed_credentials))
    expected_service = object()

    (tmp_path / "token.json").write_text("stale token", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GOOGLE_SERVICE_ACCOUNT_JSON", raising=False)
    monkeypatch.delenv("GOOGLE_SERVICE_ACCOUNT_FILE", raising=False)
    monkeypatch.setattr(
        calendar_service.Credentials,
        "from_authorized_user_file",
        Mock(return_value=stale_credentials),
    )
    monkeypatch.setattr(
        calendar_service.InstalledAppFlow,
        "from_client_secrets_file",
        Mock(return_value=oauth_flow),
    )
    monkeypatch.setattr(
        calendar_service,
        "build",
        Mock(return_value=expected_service),
    )

    assert calendar_service.get_service() is expected_service
    stale_credentials.refresh.assert_called_once()
    oauth_flow.run_local_server.assert_called_once_with(port=0)
    assert (tmp_path / "token.json").read_text(encoding="utf-8") == '{"token":"new"}'


def test_service_account_auth_reads_mounted_secret_file(monkeypatch, tmp_path):
    credentials = object()
    expected_service = object()
    secret_file = tmp_path / "service-account.json"
    secret_file.write_text(
        '{"type":"service_account","client_email":"mounted@example.com"}',
        encoding="utf-8",
    )
    from_service_account = Mock(return_value=credentials)
    build = Mock(return_value=expected_service)

    monkeypatch.delenv("GOOGLE_SERVICE_ACCOUNT_JSON", raising=False)
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_FILE", str(secret_file))
    monkeypatch.setattr(
        calendar_service.service_account.Credentials,
        "from_service_account_info",
        from_service_account,
    )
    monkeypatch.setattr(calendar_service, "build", build)

    assert calendar_service.get_service() is expected_service
    from_service_account.assert_called_once_with(
        {"type": "service_account", "client_email": "mounted@example.com"},
        scopes=calendar_service.SCOPES,
    )
    build.assert_called_once_with("calendar", "v3", credentials=credentials)


def test_missing_configured_service_account_file_fails_explicitly(
    monkeypatch, tmp_path
):
    monkeypatch.delenv("GOOGLE_SERVICE_ACCOUNT_JSON", raising=False)
    monkeypatch.setenv(
        "GOOGLE_SERVICE_ACCOUNT_FILE",
        str(tmp_path / "missing-service-account.json"),
    )

    with pytest.raises(RuntimeError, match="GOOGLE_SERVICE_ACCOUNT_FILE"):
        calendar_service.get_service()


def test_service_account_file_defaults_to_livekit_mounted_secret(monkeypatch, tmp_path):
    credentials = object()
    expected_service = object()
    secret_file = tmp_path / "mounted-secret.json"
    secret_file.write_text(
        '{"type":"service_account","client_email":"mounted@example.com"}',
        encoding="utf-8",
    )
    from_service_account = Mock(return_value=credentials)
    build = Mock(return_value=expected_service)
    monkeypatch.delenv("GOOGLE_SERVICE_ACCOUNT_JSON", raising=False)
    monkeypatch.delenv("GOOGLE_SERVICE_ACCOUNT_FILE", raising=False)
    monkeypatch.setattr(
        calendar_service,
        "DEFAULT_SERVICE_ACCOUNT_FILE",
        str(secret_file),
    )
    monkeypatch.setattr(
        calendar_service.service_account.Credentials,
        "from_service_account_info",
        from_service_account,
    )
    monkeypatch.setattr(calendar_service, "build", build)

    assert calendar_service.get_service() is expected_service
    from_service_account.assert_called_once_with(
        {"type": "service_account", "client_email": "mounted@example.com"},
        scopes=calendar_service.SCOPES,
    )
