"""DELIBERATE, TEMPORARY failure to live-test apply-ci-fix opening a real
PR from a real diagnosed fix. Throwaway branch/PR, not meant to merge --
deleted right after the live test completes. See PRASH_V2.md §9, 2026-08-15.
"""


def add(a, b):
    return a - b  # DELIBERATE bug: should be a + b


def test_add_returns_the_sum_of_its_two_arguments():
    assert add(2, 3) == 5
