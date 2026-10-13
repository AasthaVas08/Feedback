"""Unit tests for the reward calculation algorithm.

Tests the _calculate_reward_points function directly, covering:
- First submitter gets max reward
- Last submitter gets min reward
- Middle submitters get proportionally scaled values
- Single respondent edge case (gets max)
- Zero respondents edge case (total=0)
- Large numbers of respondents
- Custom reward bounds
- Equal max and min (degenerate case handled by API validation)
"""

import pytest

from app.api.rewards import _calculate_reward_points


class TestCalculateRewardPoints:
    """Direct unit tests for the reward formula:
    points = max - (max - min) * (rank - 1) / (total - 1)
    """

    # ── First submitter always gets max ────────────────────────────

    def test_first_of_two_gets_max(self):
        assert _calculate_reward_points(rank=1, total=2, max_pts=100, min_pts=10) == 100.0

    def test_first_of_five_gets_max(self):
        assert _calculate_reward_points(rank=1, total=5, max_pts=100, min_pts=10) == 100.0

    def test_first_of_hundred_gets_max(self):
        assert _calculate_reward_points(rank=1, total=100, max_pts=100, min_pts=10) == 100.0

    # ── Last submitter always gets min ─────────────────────────────

    def test_last_of_two_gets_min(self):
        assert _calculate_reward_points(rank=2, total=2, max_pts=100, min_pts=10) == 10.0

    def test_last_of_five_gets_min(self):
        assert _calculate_reward_points(rank=5, total=5, max_pts=100, min_pts=10) == 10.0

    def test_last_of_hundred_gets_min(self):
        assert _calculate_reward_points(rank=100, total=100, max_pts=100, min_pts=10) == 10.0

    # ── Middle submitters get proportionally scaled values ─────────

    def test_middle_of_three(self):
        """Rank 2 of 3: (100 - 90 * 1/2) = 55.0"""
        result = _calculate_reward_points(rank=2, total=3, max_pts=100, min_pts=10)
        assert result == 55.0

    def test_middle_of_five(self):
        """Rank 3 of 5: (100 - 90 * 2/4) = 55.0"""
        result = _calculate_reward_points(rank=3, total=5, max_pts=100, min_pts=10)
        assert result == 55.0

    def test_rank_2_of_5(self):
        """Rank 2 of 5: (100 - 90 * 1/4) = 77.5"""
        result = _calculate_reward_points(rank=2, total=5, max_pts=100, min_pts=10)
        assert result == 77.5

    def test_rank_4_of_5(self):
        """Rank 4 of 5: (100 - 90 * 3/4) = 32.5"""
        result = _calculate_reward_points(rank=4, total=5, max_pts=100, min_pts=10)
        assert result == 32.5

    def test_all_ranks_strictly_decreasing(self):
        """Points must be strictly decreasing from rank 1 to rank N."""
        total = 10
        points = [
            _calculate_reward_points(rank=r, total=total, max_pts=100, min_pts=10)
            for r in range(1, total + 1)
        ]
        for i in range(len(points) - 1):
            assert points[i] > points[i + 1], (
                f"Rank {i+1} ({points[i]}) should be > rank {i+2} ({points[i+1]})"
            )

    def test_equal_spacing_between_ranks(self):
        """With linear interpolation, the gap between consecutive ranks is constant."""
        total = 5
        max_pts, min_pts = 100.0, 10.0
        points = [
            _calculate_reward_points(rank=r, total=total, max_pts=max_pts, min_pts=min_pts)
            for r in range(1, total + 1)
        ]
        gaps = [points[i] - points[i + 1] for i in range(len(points) - 1)]
        # All gaps should be equal (within floating point tolerance)
        for gap in gaps:
            assert abs(gap - gaps[0]) < 0.01, f"Gaps not equal: {gaps}"

    # ── Single respondent edge case ────────────────────────────────

    def test_single_respondent_gets_max(self):
        """When total=1, the sole respondent gets max_pts (no division by zero)."""
        result = _calculate_reward_points(rank=1, total=1, max_pts=100, min_pts=10)
        assert result == 100.0

    def test_single_respondent_custom_bounds(self):
        result = _calculate_reward_points(rank=1, total=1, max_pts=500, min_pts=50)
        assert result == 500.0

    # ── Zero respondents edge case ─────────────────────────────────

    def test_zero_respondents_returns_max(self):
        """When total=0 (or <=1), the function returns max_pts."""
        result = _calculate_reward_points(rank=1, total=0, max_pts=100, min_pts=10)
        assert result == 100.0

    # ── Custom reward bounds ───────────────────────────────────────

    def test_custom_bounds_200_50(self):
        result_first = _calculate_reward_points(rank=1, total=3, max_pts=200, min_pts=50)
        result_last = _calculate_reward_points(rank=3, total=3, max_pts=200, min_pts=50)
        assert result_first == 200.0
        assert result_last == 50.0

    def test_custom_bounds_1000_1(self):
        result_first = _calculate_reward_points(rank=1, total=2, max_pts=1000, min_pts=1)
        result_last = _calculate_reward_points(rank=2, total=2, max_pts=1000, min_pts=1)
        assert result_first == 1000.0
        assert result_last == 1.0

    def test_fractional_bounds(self):
        """Bounds with decimal values."""
        result = _calculate_reward_points(rank=1, total=2, max_pts=99.99, min_pts=0.01)
        assert result == 99.99

    # ── Large number of respondents ────────────────────────────────

    def test_large_respondent_count(self):
        """Verify formula works with 1000 respondents."""
        total = 1000
        first = _calculate_reward_points(rank=1, total=total, max_pts=100, min_pts=10)
        last = _calculate_reward_points(rank=total, total=total, max_pts=100, min_pts=10)
        mid = _calculate_reward_points(rank=500, total=total, max_pts=100, min_pts=10)

        assert first == 100.0
        assert last == 10.0
        assert 10.0 < mid < 100.0

    # ── Rounding ───────────────────────────────────────────────────

    def test_result_rounded_to_2_decimals(self):
        """The function rounds to 2 decimal places."""
        # rank=2, total=3, max=100, min=10 → 55.0 (exact)
        result = _calculate_reward_points(rank=2, total=3, max_pts=100, min_pts=10)
        # Check it's a float with at most 2 decimal places
        assert result == round(result, 2)

    def test_rounding_with_repeating_decimal(self):
        """rank=2, total=7, max=100, min=10 → 100 - 90*(1/6) = 85.0"""
        result = _calculate_reward_points(rank=2, total=7, max_pts=100, min_pts=10)
        assert result == round(result, 2)
        assert 10.0 <= result <= 100.0

    # ── Sum of all rewards ─────────────────────────────────────────

    def test_total_reward_sum_is_predictable(self):
        """Sum of all rewards = total * (max + min) / 2 for linear distribution."""
        total = 5
        max_pts, min_pts = 100.0, 10.0
        points = [
            _calculate_reward_points(rank=r, total=total, max_pts=max_pts, min_pts=min_pts)
            for r in range(1, total + 1)
        ]
        expected_sum = total * (max_pts + min_pts) / 2
        assert abs(sum(points) - expected_sum) < 0.1
