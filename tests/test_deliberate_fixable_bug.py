"""Tests for deliberately planted fixable bugs (fixture for the repair agent)."""


def add(a: int, b: int) -> int:
    """Return the sum of two arguments."""
    return a + b


def test_add_returns_the_sum_of_its_two_arguments():
    assert add(2, 3) == 5
