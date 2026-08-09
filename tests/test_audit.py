from prash.actions.contract import ActionResult, ActionResultStatus, Decision, RiskTier
from prash.audit import AuditLog
from prash.permissions import PermissionMode


def _entry_id(tmp_path):
    audit = AuditLog(path=tmp_path / "audit.jsonl")
    result = ActionResult(status=ActionResultStatus.SUCCEEDED, summary="ok")
    return audit.append("test-action", RiskTier.SAFE, PermissionMode.ASK, Decision.ALLOW, result)


def test_append_creates_entry(tmp_path):
    audit = AuditLog(path=tmp_path / "audit.jsonl")
    entries = audit.read()
    assert entries == []
    _entry_id(tmp_path)
    entries = audit.read()
    assert len(entries) == 1
    assert entries[0]["action"] == "test-action"
    assert entries[0]["verification_ok"] is False


def test_entries_accumulate_and_seq_increments(tmp_path):
    _entry_id(tmp_path)
    _entry_id(tmp_path)
    audit = AuditLog(path=tmp_path / "audit.jsonl")
    entries = audit.read()
    assert len(entries) == 2
    assert entries[0]["seq"] == 1
    assert entries[1]["seq"] == 2


def test_read_limit(tmp_path):
    for _ in range(5):
        _entry_id(tmp_path)
    audit = AuditLog(path=tmp_path / "audit.jsonl")
    assert len(audit.read(limit=2)) == 2
    assert len(audit.read()) == 5


def test_file_contains_append_only_json_lines(tmp_path):
    path = tmp_path / "audit.jsonl"
    _entry_id(tmp_path)
    raw = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(raw) == 1
