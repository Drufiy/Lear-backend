"""AWS CLI compatibility shim for kubectl exec auth."""

import sys
import os
import json
import base64
from datetime import datetime, timezone, timedelta
import boto3
from botocore.signers import RequestSigner

def get_token(cluster_name: str, region: str = 'ap-south-1') -> str:
    session = boto3.Session(region_name=region)
    sts_client = session.client('sts')
    service_id = sts_client.meta.service_model.service_id

    signer = RequestSigner(
        service_id,
        region,
        'sts',
        'v4',
        session.get_credentials(),
        session.events
    )

    params = {
        'method': 'GET',
        'url': f'https://sts.{region}.amazonaws.com/?Action=GetCallerIdentity&Version=2011-06-15',
        'body': {},
        'headers': {
            'x-k8s-aws-id': cluster_name
        },
        'context': {}
    }

    url = signer.generate_presigned_url(
        params,
        region_name=region,
        expires_in=60,
        operation_name=''
    )

    base64_url = base64.urlsafe_b64encode(url.encode('utf-8')).decode('utf-8').rstrip('=')
    return 'k8s-aws-v1.' + base64_url

def main():
    args = sys.argv[1:]
    if len(args) >= 2 and args[0] == 'eks' and args[1] == 'get-token':
        cluster_name = 'lear-demo'
        region = os.environ.get('AWS_REGION', 'ap-south-1')
        for i, arg in enumerate(args):
            if arg in ('--cluster-name', '--cluster') and i + 1 < len(args):
                cluster_name = args[i + 1]
            elif arg == '--region' and i + 1 < len(args):
                region = args[i + 1]

        token = get_token(cluster_name, region)
        exp = (datetime.now(timezone.utc) + timedelta(minutes=14)).strftime('%Y-%m-%dT%H:%M:%SZ')
        response = {
            "kind": "ExecCredential",
            "apiVersion": "client.authentication.k8s.io/v1beta1",
            "spec": {},
            "status": {
                "expirationTimestamp": exp,
                "token": token
            }
        }
        print(json.dumps(response))
        sys.exit(0)

    # Fallback to standard python aws if needed
    print(f"Unsupported subcommand: {args}", file=sys.stderr)
    sys.exit(1)

if __name__ == '__main__':
    main()
