"""DELIBERATE, TEMPORARY failure for a live test of `prash fix --ci`.

Part of TESTING_CHECKLIST.md §2's "CI multi-failure path" row -- this needs a
real GitHub Actions run with real independent failures, not a mock. This
branch/PR is throwaway: not meant to merge, deleted right after the live
`prash fix --ci --run-id <n>` test completes. See PRASH_V2.md §10, 2026-08-15.
"""


def test_deliberate_failure_unrelated_to_dependency_injection():
    assert False, "DELIBERATE failure #1 of 2 for the live CI multi-failure test -- not a real bug"
