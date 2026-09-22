"""Unit tests for date, time and slot logic. No LLM or live session needed."""

import datetime
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

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
