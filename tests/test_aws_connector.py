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
    ssm_client = session.client("ssm")
    
    with Stubber(ec2_client) as ec2_stubber, Stubber(sts_client) as sts_stubber, Stubber(ssm_client) as ssm_stubber:
        sts_stubber.add_response("get_caller_identity", {})
        sts_stubber.add_response("get_caller_identity", {})
        
        # Responses for locate and then status check
        ec2_stubber.add_response("describe_instances", {
            "Reservations": [{"Instances": [{"InstanceId": "i-123", "InstanceType": "t2", "State": {"Name": "running"}}]}]
        })
        
        ec2_stubber.add_response("describe_instance_status", {
            "InstanceStatuses": [{"InstanceStatus": {"Status": "ok"}, "SystemStatus": {"Status": "ok"}}]
        })
        
        # Marker check: no marker present -> stays HEALTHY
        ssm_stubber.add_response("send_command", {
            "Command": {"CommandId": "aaaaaaaa-1111-2222-3333-444444444444"}
        })
        ssm_stubber.add_response("get_command_invocation", {
            "Status": "Success",
            "StandardOutputContent": "ABSENT\n",
            "StandardErrorContent": "",
        })
        
        def mock_client(svc):
            if svc == "ec2": return ec2_client
            if svc == "sts": return sts_client
            if svc == "ssm": return ssm_client
            
        connector._get_boto_session = lambda: type("MockSession", (), {"client": lambda self, svc: mock_client(svc)})()
        
        state = connector.poll_state("i-123")
        assert state.state == ConnectorState.HEALTHY
        assert state.detail["aws_state"] == "running"


def test_poll_state_running_marker_degraded(mock_credentials):
    """When the prash test fixture's break marker is present, a running
    instance with OK status checks reports DEGRADED, not HEALTHY -- the
    service-level health split TESTING_SETUP.md promises."""
    connector = AWSConnector(mock_credentials)
    session = boto3.Session(region_name="us-east-1")
    ec2_client = session.client("ec2")
    sts_client = session.client("sts")
    ssm_client = session.client("ssm")
    
    with Stubber(ec2_client) as ec2_stubber, Stubber(sts_client) as sts_stubber, Stubber(ssm_client) as ssm_stubber:
        sts_stubber.add_response("get_caller_identity", {})
        sts_stubber.add_response("get_caller_identity", {})
        
        ec2_stubber.add_response("describe_instances", {
            "Reservations": [{"Instances": [{"InstanceId": "i-123", "InstanceType": "t2", "State": {"Name": "running"}}]}]
        })
        
        ec2_stubber.add_response("describe_instance_status", {
            "InstanceStatuses": [{"InstanceStatus": {"Status": "ok"}, "SystemStatus": {"Status": "ok"}}]
        })
        
        # Marker present -> DEGRADED
        ssm_stubber.add_response("send_command", {
            "Command": {"CommandId": "bbbbbbbb-1111-2222-3333-444444444444"}
        })
        ssm_stubber.add_response("get_command_invocation", {
            "Status": "Success",
            "StandardOutputContent": "PRESENT\n",
            "StandardErrorContent": "",
        })
        
        def mock_client(svc):
            if svc == "ec2": return ec2_client
            if svc == "sts": return sts_client
            if svc == "ssm": return ssm_client
            
        connector._get_boto_session = lambda: type("MockSession", (), {"client": lambda self, svc: mock_client(svc)})()
        
        state = connector.poll_state("i-123")
        assert state.state == ConnectorState.DEGRADED
        assert state.detail["marker"] == "prash-test-fixture-break"


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


def test_watch_returns_handle(mock_credentials):
    connector = AWSConnector(mock_credentials)
    session = boto3.Session(region_name="us-east-1")
    sts_client = session.client("sts")
    
    with Stubber(sts_client) as sts_stubber:
        sts_stubber.add_response("get_caller_identity", {})
        
        def mock_client(svc):
            if svc == "sts": return sts_client
            
        connector._get_boto_session = lambda: type("MockSession", (), {"client": lambda self, svc: mock_client(svc)})()
        
        handle = connector.watch("i-123")
        assert handle.is_active is True
        assert handle.connector == "aws"
        assert handle.target == "i-123"
        handle.stop()
        assert handle.is_active is False


def test_get_stats(mock_credentials):
    connector = AWSConnector(mock_credentials)
    session = boto3.Session(region_name="us-east-1")
    ec2_client = session.client("ec2")
    sts_client = session.client("sts")
    ct_client = session.client("cloudtrail")
    cw_client = session.client("cloudwatch")
    
    with Stubber(ec2_client) as ec2_stubber, Stubber(sts_client) as sts_stubber, Stubber(ct_client) as ct_stubber, Stubber(cw_client) as cw_stubber:
        sts_stubber.add_response("get_caller_identity", {})
        sts_stubber.add_response("get_caller_identity", {})
        
        ec2_stubber.add_response("describe_instances", {
            "Reservations": [{"Instances": [{"InstanceId": "i-123", "InstanceType": "t2", "State": {"Name": "running"}}]}]
        })
        
        import datetime
        now = datetime.datetime.now(datetime.timezone.utc)
        
        ct_stubber.add_response("lookup_events", {
            "Events": [
                {"EventTime": now - datetime.timedelta(minutes=10), "EventName": "StopInstances"},
            ]
        })
        
        cw_stubber.add_response("get_metric_statistics", {
            "Datapoints": [
                {"Timestamp": now - datetime.timedelta(minutes=5), "Average": 95.0},
                {"Timestamp": now - datetime.timedelta(minutes=2), "Average": 40.0}
            ]
        })
        cw_stubber.add_response("get_metric_statistics", {"Datapoints": []}) # DiskReadOps
        cw_stubber.add_response("get_metric_statistics", {"Datapoints": []}) # DiskWriteOps
        cw_stubber.add_response("get_metric_statistics", {"Datapoints": []}) # NetworkIn
        cw_stubber.add_response("get_metric_statistics", {"Datapoints": []}) # NetworkOut
        cw_stubber.add_response("get_metric_statistics", {"Datapoints": []}) # StatusCheckFailed
        cw_stubber.add_response("describe_alarms_for_metric", {"MetricAlarms": []}) # describe_alarms
        
        def mock_client(svc):
            if svc == "ec2": return ec2_client
            if svc == "sts": return sts_client
            if svc == "cloudtrail": return ct_client
            if svc == "cloudwatch": return cw_client
            
        connector._get_boto_session = lambda: type("MockSession", (), {"client": lambda self, svc: mock_client(svc)})()
        
        stats = connector.get_stats("i-123")
        assert len(stats) == 2
        assert stats[0]["event_type"] == "cloudtrail_event"
        assert stats[1]["event_type"] == "cpu_spike"
        assert stats[1]["summary"] == "CPU Spike: 95.00"


def test_aws_alert_action(mock_credentials):
    from prash.actions.aws_alert import AWSAlertAction
    from prash.actions.contract import ActionContext, Target
    
    # Needs AWS_SNS_TOPIC_ARN
    mock_credentials["AWS_SNS_TOPIC_ARN"] = "arn:aws:sns:us-east-1:123456789012:MyTopic"
    connector = AWSConnector(mock_credentials)
    
    session = boto3.Session(region_name="us-east-1")
    sns_client = session.client("sns")
    
    with Stubber(sns_client) as sns_stubber:
        sns_stubber.add_response("publish", {"MessageId": "msg-1234"})
        
        connector._get_boto_session = lambda: type("MockSession", (), {"client": lambda self, svc: sns_client})()
        
        action = AWSAlertAction()
        ctx = ActionContext(
            target=Target("i-123", environment="staging"),
            credentials=mock_credentials,
            dry_run=False,
            extra={"connectors": {"aws": connector}, "message": "Test Alert!"}
        )
        
        res = action.execute(ctx)
        assert res.status.value == "succeeded"
        assert res.detail["MessageId"] == "msg-1234"
        
        ver = action.verify(ctx, res)
        assert ver.ok is True


def test_aws_alert_action_missing_arn(mock_credentials):
    from prash.actions.aws_alert import AWSAlertAction
    from prash.actions.contract import ActionContext, Target
    
    connector = AWSConnector(mock_credentials)
    
    action = AWSAlertAction()
    ctx = ActionContext(
        target=Target("i-123", environment="staging"),
        credentials=mock_credentials,
        dry_run=False,
        extra={"connectors": {"aws": connector}, "message": "Test Alert!"}
    )
    
    res = action.execute(ctx)
    assert res.status.value == "failed"
    assert "credential is required" in res.summary

def test_get_stats_enhanced(mock_credentials):
    import datetime
    connector = AWSConnector(mock_credentials)
    
    session = boto3.Session(region_name="us-east-1")
    ec2_client = session.client("ec2")
    sts_client = session.client("sts")
    cloudtrail_client = session.client("cloudtrail")
    cw_client = session.client("cloudwatch")
    
    with Stubber(ec2_client) as ec2_stubber, Stubber(sts_client) as sts_stubber, Stubber(cloudtrail_client) as ct_stubber, Stubber(cw_client) as cw_stubber:
        sts_stubber.add_response("get_caller_identity", {})
        
        # locate
        ec2_stubber.add_response("describe_instances", {
            "Reservations": [{"Instances": [{"InstanceId": "i-123", "InstanceType": "t2", "State": {"Name": "running"}}]}]
        }, expected_params={"InstanceIds": ["i-123"]})
        
        # cloudtrail
        ct_stubber.add_response("lookup_events", {"Events": []})
        
        # cloudwatch metrics
        now = datetime.datetime.now(datetime.timezone.utc)
        
        # CPU
        cw_stubber.add_response("get_metric_statistics", {
            "Datapoints": [{"Timestamp": now, "Average": 95.0}]
        })
        # DiskReadOps
        cw_stubber.add_response("get_metric_statistics", {
            "Datapoints": [{"Timestamp": now, "Sum": 6000.0}]
        })
        # DiskWriteOps
        cw_stubber.add_response("get_metric_statistics", {"Datapoints": []})
        # NetworkIn
        cw_stubber.add_response("get_metric_statistics", {"Datapoints": []})
        # NetworkOut
        cw_stubber.add_response("get_metric_statistics", {"Datapoints": []})
        # StatusCheckFailed
        cw_stubber.add_response("get_metric_statistics", {
            "Datapoints": [{"Timestamp": now, "Maximum": 1.0}]
        })
        
        # Alarms
        cw_stubber.add_response("describe_alarms_for_metric", {
            "MetricAlarms": [{
                "AlarmName": "HighCPU",
                "StateValue": "ALARM",
                "StateUpdatedTimestamp": now
            }]
        })
        
        def mock_client(svc):
            if svc == "ec2": return ec2_client
            if svc == "sts": return sts_client
            if svc == "cloudtrail": return cloudtrail_client
            if svc == "cloudwatch": return cw_client
            
        connector._get_boto_session = lambda: type("MockSession", (), {"client": lambda self, svc: mock_client(svc)})()
        
        stats = connector.get_stats("i-123")
        assert len(stats) == 4
        
        types = [s["event_type"] for s in stats]
        assert "cpu_spike" in types
        assert "high_disk_read" in types
        assert "status_check_failed" in types
        assert "cloudwatch_alarm" in types
