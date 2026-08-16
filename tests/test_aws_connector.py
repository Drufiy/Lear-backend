import base64
import pytest
from botocore.exceptions import ClientError, BotoCoreError
from botocore.stub import Stubber

# Import conditionally since boto3 is an optional dependency
pytest.importorskip("boto3")
import boto3

from prash.connectors.aws import AWSConnector
from prash.connectors.base import ConnectorState


@pytest.fixture
def mock_credentials():
    return {
        "AWS_ACCESS_KEY_ID": "mock-access-key",
        "AWS_SECRET_ACCESS_KEY": "mock-secret-key",
        "AWS_REGION": "us-east-1",
    }


def test_authenticate_success(mock_credentials):
    connector = AWSConnector(mock_credentials)
    
    # We must patch the _get_boto_session method to return a mock session with stubbed sts
    session = boto3.Session(region_name="us-east-1")
    sts_client = session.client("sts")
    
    with Stubber(sts_client) as stubber:
        stubber.add_response("get_caller_identity", {"Account": "123456789012", "Arn": "arn:aws:iam::123456789012:user/Test", "UserId": "TESTUSER"})
        
        # Override the method just for this test
        original_get_session = connector._get_boto_session
        connector._get_boto_session = lambda: type("MockSession", (), {"client": lambda self, svc: sts_client})()
        
        assert connector.authenticate() is True
        connector._get_boto_session = original_get_session


def test_authenticate_failure_no_credentials():
    connector = AWSConnector({})
    assert connector.authenticate() is False


def test_authenticate_failure_client_error(mock_credentials):
    connector = AWSConnector(mock_credentials)
    session = boto3.Session(region_name="us-east-1")
    sts_client = session.client("sts")
    
    with Stubber(sts_client) as stubber:
        stubber.add_client_error("get_caller_identity", service_message="Auth failed")
        
        connector._get_boto_session = lambda: type("MockSession", (), {"client": lambda self, svc: sts_client})()
        
        assert connector.authenticate() is False


def test_locate_instance_by_id(mock_credentials):
    connector = AWSConnector(mock_credentials)
    
    session = boto3.Session(region_name="us-east-1")
    ec2_client = session.client("ec2")
    sts_client = session.client("sts")
    
    with Stubber(ec2_client) as ec2_stubber, Stubber(sts_client) as sts_stubber:
        sts_stubber.add_response("get_caller_identity", {})
        
        response = {
            "Reservations": [
                {
                    "Instances": [
                        {
                            "InstanceId": "i-1234567890abcdef0",
                            "InstanceType": "t2.micro",
                            "State": {"Name": "running"}
                        }
                    ]
                }
            ]
        }
        
        ec2_stubber.add_response("describe_instances", response, expected_params={"InstanceIds": ["i-1234567890abcdef0"]})
        
        def mock_client(svc):
            if svc == "ec2": return ec2_client
            if svc == "sts": return sts_client
            
        connector._get_boto_session = lambda: type("MockSession", (), {"client": lambda self, svc: mock_client(svc)})()
        
        res = connector.locate("i-1234567890abcdef0")
        assert res["instance_id"] == "i-1234567890abcdef0"
        assert res["state"] == "running"


def test_locate_not_found(mock_credentials):
    connector = AWSConnector(mock_credentials)
    session = boto3.Session(region_name="us-east-1")
    ec2_client = session.client("ec2")
    sts_client = session.client("sts")
    
    with Stubber(ec2_client) as ec2_stubber, Stubber(sts_client) as sts_stubber:
        sts_stubber.add_response("get_caller_identity", {})
        
        ec2_stubber.add_client_error("describe_instances", service_error_code="InvalidInstanceID.NotFound")
        
        def mock_client(svc):
            if svc == "ec2": return ec2_client
            if svc == "sts": return sts_client
            
        connector._get_boto_session = lambda: type("MockSession", (), {"client": lambda self, svc: mock_client(svc)})()
        
        res = connector.locate("i-unknown")
        assert res == {}


def test_poll_state_running(mock_credentials):
    connector = AWSConnector(mock_credentials)
    session = boto3.Session(region_name="us-east-1")
    ec2_client = session.client("ec2")
    sts_client = session.client("sts")
    
    with Stubber(ec2_client) as ec2_stubber, Stubber(sts_client) as sts_stubber:
        sts_stubber.add_response("get_caller_identity", {})
        sts_stubber.add_response("get_caller_identity", {})
        
        # Responses for locate and then status check
        ec2_stubber.add_response("describe_instances", {
            "Reservations": [{"Instances": [{"InstanceId": "i-123", "InstanceType": "t2", "State": {"Name": "running"}}]}]
        })
        
        ec2_stubber.add_response("describe_instance_status", {
            "InstanceStatuses": [{"InstanceStatus": {"Status": "ok"}, "SystemStatus": {"Status": "ok"}}]
        })
        
        def mock_client(svc):
            if svc == "ec2": return ec2_client
            if svc == "sts": return sts_client
            
        connector._get_boto_session = lambda: type("MockSession", (), {"client": lambda self, svc: mock_client(svc)})()
        
        state = connector.poll_state("i-123")
        assert state.state == ConnectorState.HEALTHY
        assert state.detail["aws_state"] == "running"


def test_poll_state_status_check_failed(mock_credentials):
    connector = AWSConnector(mock_credentials)
    session = boto3.Session(region_name="us-east-1")
    ec2_client = session.client("ec2")
    sts_client = session.client("sts")
    
    with Stubber(ec2_client) as ec2_stubber, Stubber(sts_client) as sts_stubber:
        sts_stubber.add_response("get_caller_identity", {})
        sts_stubber.add_response("get_caller_identity", {})
        
        ec2_stubber.add_response("describe_instances", {
            "Reservations": [{"Instances": [{"InstanceId": "i-123", "InstanceType": "t2", "State": {"Name": "running"}}]}]
        })
        
        ec2_stubber.add_response("describe_instance_status", {
            "InstanceStatuses": [{"InstanceStatus": {"Status": "impaired"}, "SystemStatus": {"Status": "ok"}}]
        })
        
        def mock_client(svc):
            if svc == "ec2": return ec2_client
            if svc == "sts": return sts_client
            
        connector._get_boto_session = lambda: type("MockSession", (), {"client": lambda self, svc: mock_client(svc)})()
        
        state = connector.poll_state("i-123")
        assert state.state == ConnectorState.FAILED


def test_poll_state_stopped(mock_credentials):
    connector = AWSConnector(mock_credentials)
    session = boto3.Session(region_name="us-east-1")
    ec2_client = session.client("ec2")
    sts_client = session.client("sts")
    
    with Stubber(ec2_client) as ec2_stubber, Stubber(sts_client) as sts_stubber:
        sts_stubber.add_response("get_caller_identity", {})
        sts_stubber.add_response("get_caller_identity", {})
        
        ec2_stubber.add_response("describe_instances", {
            "Reservations": [{"Instances": [{"InstanceId": "i-123", "InstanceType": "t2", "State": {"Name": "stopped"}}]}]
        })
        
        def mock_client(svc):
            if svc == "ec2": return ec2_client
            if svc == "sts": return sts_client
            
        connector._get_boto_session = lambda: type("MockSession", (), {"client": lambda self, svc: mock_client(svc)})()
        
        state = connector.poll_state("i-123")
        assert state.state == ConnectorState.STABLE


def test_fetch_logs(mock_credentials):
    connector = AWSConnector(mock_credentials)
    session = boto3.Session(region_name="us-east-1")
    ec2_client = session.client("ec2")
    sts_client = session.client("sts")
    
    with Stubber(ec2_client) as ec2_stubber, Stubber(sts_client) as sts_stubber:
        sts_stubber.add_response("get_caller_identity", {})
        sts_stubber.add_response("get_caller_identity", {})
        
        # Locate
        ec2_stubber.add_response("describe_instances", {
            "Reservations": [{"Instances": [{"InstanceId": "i-123", "InstanceType": "t2", "State": {"Name": "running"}}]}]
        })
        
        # Fetch logs
        fake_log = b"Booting linux...\nKernel panic!"
        encoded_log = base64.b64encode(fake_log).decode("utf-8")
        ec2_stubber.add_response("get_console_output", {"Output": encoded_log})
        
        def mock_client(svc):
            if svc == "ec2": return ec2_client
            if svc == "sts": return sts_client
            
        connector._get_boto_session = lambda: type("MockSession", (), {"client": lambda self, svc: mock_client(svc)})()
        
        logs = connector.fetch_logs("i-123")
        assert logs == ["Booting linux...", "Kernel panic!"]
