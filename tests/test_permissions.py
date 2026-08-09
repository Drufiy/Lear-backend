import pytest

from prash.actions.contract import Decision, RiskTier
from prash.permissions import PRODUCTION, PermissionMode, decide


@pytest.mark.parametrize("tier", list(RiskTier))
def test_read_only_refuses_everything(tier):
    assert decide(PermissionMode.READ_ONLY, tier) is Decision.REFUSE


@pytest.mark.parametrize("tier", [RiskTier.SAFE, RiskTier.APPROVAL])
def test_ask_prompts_every_action(tier):
    assert decide(PermissionMode.ASK, tier) is Decision.PROMPT


def test_auto_safe_allows_safe():
    assert decide(PermissionMode.AUTO_SAFE, RiskTier.SAFE) is Decision.ALLOW


def test_auto_safe_prompts_approval():
    assert decide(PermissionMode.AUTO_SAFE, RiskTier.APPROVAL) is Decision.PROMPT


def test_environment_scoped_safe_auto_on_staging():
    assert decide(PermissionMode.ENVIRONMENT_SCOPED, RiskTier.SAFE, "staging") is Decision.ALLOW


def test_environment_scoped_safe_prompts_on_production():
    assert decide(PermissionMode.ENVIRONMENT_SCOPED, RiskTier.SAFE, PRODUCTION) is Decision.PROMPT


def test_environment_scoped_approval_needs_grant_on_staging():
    assert decide(PermissionMode.ENVIRONMENT_SCOPED, RiskTier.APPROVAL, "staging") is Decision.PROMPT
    assert decide(PermissionMode.ENVIRONMENT_SCOPED, RiskTier.APPROVAL, "staging", grant=True) is Decision.ALLOW


def test_bypass_allows_safe():
    assert decide(PermissionMode.BYPASS, RiskTier.SAFE) is Decision.ALLOW


def test_bypass_approval_still_prompts_without_grant():
    assert decide(PermissionMode.BYPASS, RiskTier.APPROVAL) is Decision.PROMPT


def test_bypass_approval_allow_with_explicit_grant():
    assert decide(PermissionMode.BYPASS, RiskTier.APPROVAL, grant=True) is Decision.ALLOW


def test_never_refused_even_with_grant_in_bypass():
    assert decide(PermissionMode.BYPASS, RiskTier.NEVER, grant=True) is Decision.REFUSE
    assert decide(PermissionMode.ASK, RiskTier.NEVER, grant=True) is Decision.REFUSE
    assert decide(PermissionMode.AUTO_SAFE, RiskTier.NEVER, grant=True) is Decision.REFUSE
