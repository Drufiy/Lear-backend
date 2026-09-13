from __future__ import annotations

import json

from prash.connectors.terraform import TerraformConnector


def test_authenticate_inspects_local_state(tmp_path):
    state = {
        "version": 4,
        "resources": [
            {"type": "aws_instance", "name": "web"},
            {"type": "aws_s3_bucket", "name": "assets"},
        ],
    }
    state_file = tmp_path / "terraform.tfstate"
    state_file.write_text(json.dumps(state), encoding="utf-8")

    connector = TerraformConnector({"TERRAFORM_STATE_PATH": str(tmp_path)})
    assert connector.authenticate() is True
    assert connector.auth_identity == {
        "resource_count": 2,
        "state": str(state_file.resolve()),
    }
    assert connector.auth_error is None


def test_authenticate_reports_missing_local_state(tmp_path):
    connector = TerraformConnector({"TERRAFORM_STATE_PATH": str(tmp_path)})
    assert connector.authenticate() is False
    assert connector.auth_identity == {}
    assert "terraform.tfstate" in connector.auth_error
