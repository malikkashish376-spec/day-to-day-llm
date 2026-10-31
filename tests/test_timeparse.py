from __future__ import annotations

from datetime import datetime

import pytest

from daytoday.timeparse import humanise, parse_when

BASE = datetime(2026, 10, 31, 12, 0)  # a Saturday


@pytest.mark.parametrize("phrase,expected", [
    ("tomorrow at 6pm", datetime(2026, 11, 1, 18, 0)),
    ("tomorrow", datetime(2026, 11, 1, 9, 0)),
    ("today 21:30", datetime(2026, 10, 31, 21, 30)),
    ("tonight", datetime(2026, 10, 31, 20, 0)),
    ("by friday 5pm", datetime(2026, 11, 6, 17, 0)),
    ("in 2 hours", datetime(2026, 10, 31, 14, 0)),
    ("in 3 days", datetime(2026, 11, 3, 12, 0)),
    ("25/12", datetime(2026, 12, 25, 9, 0)),
    ("2026-11-05", datetime(2026, 11, 5, 9, 0)),
    ("monday", datetime(2026, 11, 2, 9, 0)),
])
def test_parse_when_resolves(phrase, expected):
    assert parse_when(phrase, base=BASE) == expected


@pytest.mark.parametrize("phrase", [None, "", "call mom", "the project"])
def test_parse_when_returns_none_without_time(phrase):
    assert parse_when(phrase, base=BASE) is None


def test_weekday_rolls_forward_never_back():
    # Saturday + "saturday" must mean next Saturday, not today.
    assert parse_when("saturday", base=BASE).date() == datetime(2026, 11, 7).date()


def test_evening_clock_without_meridiem():
    assert parse_when("at 8", base=BASE).hour == 20


def test_humanise_labels():
    assert humanise(datetime(2026, 11, 1, 18, 0)) == "tomorrow 6:00 PM"
