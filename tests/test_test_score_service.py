"""Tests for services/test_score_service.py — TestScoreService."""

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from models.test_score_base import TestScoreSchema
from services.test_score_service import NEEDS_ATTENTION_THRESHOLD, TestScoreService


@pytest.fixture
def service():
    return TestScoreService()


def _make_score(enrollment_id=1, obtained=70, max_marks=100):
    s = TestScoreSchema()
    s.id = 1
    s.enrollment_id = enrollment_id
    s.test_name = "Unit Test"
    s.subject = "Maths"
    s.date = date.today()
    s.max_marks = max_marks
    s.obtained_marks = obtained
    return s


# ─── add_score validation ──────────────────────────────────────────────────────


async def test_add_score_raises_if_obtained_exceeds_max(service):
    mock_db = AsyncMock()
    with pytest.raises(ValueError, match="cannot exceed"):
        await service.add_score(mock_db, 1, "Test", "Maths", date.today(), 100, 101)


async def test_add_score_raises_if_max_marks_zero(service):
    mock_db = AsyncMock()
    with pytest.raises(ValueError, match="must be positive"):
        await service.add_score(mock_db, 1, "Test", "Maths", date.today(), 0, 0)


async def test_add_score_raises_if_obtained_negative(service):
    mock_db = AsyncMock()
    with pytest.raises(ValueError, match="cannot be negative"):
        await service.add_score(mock_db, 1, "Test", "Maths", date.today(), 100, -1)


async def test_add_score_creates_record(service):
    mock_db = AsyncMock()
    saved = _make_score(obtained=80)

    with patch.object(service.repo, "create", new=AsyncMock(return_value=saved)):
        result = await service.add_score(mock_db, 1, "Midterm", "Maths", date.today(), 100, 80)

    assert result.obtained_marks == 80


# ─── get_scores_for_enrollment ────────────────────────────────────────────────


async def test_needs_attention_false_when_fewer_than_3_scores(service):
    mock_db = AsyncMock()
    scores = [_make_score(obtained=40, max_marks=100), _make_score(obtained=30, max_marks=100)]

    with patch.object(service.repo, "get_by_enrollment_id", new=AsyncMock(return_value=scores)):
        result = await service.get_scores_for_enrollment(mock_db, 1)

    assert result["needs_attention"] is False


async def test_needs_attention_true_when_avg_below_threshold(service):
    mock_db = AsyncMock()
    # avg = (40+50+55)/3 / 100 = 48.3% — below 60%
    scores = [
        _make_score(obtained=40, max_marks=100),
        _make_score(obtained=50, max_marks=100),
        _make_score(obtained=55, max_marks=100),
    ]

    with patch.object(service.repo, "get_by_enrollment_id", new=AsyncMock(return_value=scores)):
        result = await service.get_scores_for_enrollment(mock_db, 1)

    assert result["needs_attention"] is True


async def test_needs_attention_false_when_avg_above_threshold(service):
    mock_db = AsyncMock()
    # avg = (70+80+90)/3 / 100 = 80% — above 60%
    scores = [
        _make_score(obtained=70, max_marks=100),
        _make_score(obtained=80, max_marks=100),
        _make_score(obtained=90, max_marks=100),
    ]

    with patch.object(service.repo, "get_by_enrollment_id", new=AsyncMock(return_value=scores)):
        result = await service.get_scores_for_enrollment(mock_db, 1)

    assert result["needs_attention"] is False


async def test_needs_attention_exactly_at_threshold_is_false(service):
    mock_db = AsyncMock()
    # avg = 60% exactly — NOT below threshold, so needs_attention = False
    scores = [
        _make_score(obtained=60, max_marks=100),
        _make_score(obtained=60, max_marks=100),
        _make_score(obtained=60, max_marks=100),
    ]

    with patch.object(service.repo, "get_by_enrollment_id", new=AsyncMock(return_value=scores)):
        result = await service.get_scores_for_enrollment(mock_db, 1)

    assert result["needs_attention"] is False


async def test_scores_returned_in_result(service):
    mock_db = AsyncMock()
    scores = [_make_score(obtained=75)]

    with patch.object(service.repo, "get_by_enrollment_id", new=AsyncMock(return_value=scores)):
        result = await service.get_scores_for_enrollment(mock_db, 1)

    assert len(result["scores"]) == 1
    assert result["scores"][0].obtained_marks == 75
