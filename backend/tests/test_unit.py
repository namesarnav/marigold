"""Unit tests for pure functions (no HTTP, no DB)."""
from datetime import date, timedelta
from unittest.mock import MagicMock

import bcrypt
import pytest

from backend.routes.auth import (
    _create_access_token,
    _hash_password,
    _verify_password,
)
from backend.routes.stats import calculate_streak


# ---------------------------------------------------------------------------
# Password helpers
# ---------------------------------------------------------------------------

def test_hash_password_produces_bcrypt_hash():
    hashed = _hash_password("mysecret")
    assert bcrypt.checkpw("mysecret".encode(), hashed.encode())


def test_verify_password_correct():
    hashed = _hash_password("correct_pass")
    assert _verify_password("correct_pass", hashed) is True


def test_verify_password_wrong():
    hashed = _hash_password("correct_pass")
    assert _verify_password("wrong_pass", hashed) is False


# ---------------------------------------------------------------------------
# JWT creation
# ---------------------------------------------------------------------------

def test_create_access_token_returns_string():
    token = _create_access_token(42)
    assert isinstance(token, str)
    assert len(token) > 0


def test_create_access_token_different_users():
    t1 = _create_access_token(1)
    t2 = _create_access_token(2)
    assert t1 != t2


# ---------------------------------------------------------------------------
# Streak calculation
# ---------------------------------------------------------------------------

def _mock_db(dates):
    db = MagicMock()
    rows = [MagicMock(date=d) for d in dates]
    db.query.return_value.filter.return_value.all.return_value = rows
    return db


def test_streak_no_activity():
    assert calculate_streak(1, _mock_db([])) == 0


def test_streak_today_only():
    assert calculate_streak(1, _mock_db([date.today()])) == 1


def test_streak_consecutive_three_days():
    today = date.today()
    dates = [today - timedelta(days=i) for i in range(3)]
    assert calculate_streak(1, _mock_db(dates)) == 3


def test_streak_broken_yesterday():
    today = date.today()
    # Activity today and two days ago — broken streak
    dates = [today, today - timedelta(days=2)]
    assert calculate_streak(1, _mock_db(dates)) == 1


def test_streak_only_yesterday():
    yesterday = date.today() - timedelta(days=1)
    assert calculate_streak(1, _mock_db([yesterday])) == 1


def test_streak_old_activity_only():
    old = date.today() - timedelta(days=10)
    assert calculate_streak(1, _mock_db([old])) == 0
