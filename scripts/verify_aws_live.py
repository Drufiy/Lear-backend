import argparse
import asyncio
import os
import boto3
from openai import AsyncOpenAI
from prash.credentials import CredentialStore
from prash.connectors.aws import AWSConnector

async def main():
    parser = argparse.ArgumentParser(description="Live-verify the AWS connector against a real instance.")
    parser.add_argument("--pem", help="Path to an SSH .pem for the SSH fallback (default: PRASH_PEM_PATH env).")
    args = parser.parse_args()
    pem_path = args.pem or os.environ.get("PRASH_PEM_PATH")

    print("--- Starting Live Infra Verification ---")
    
    # 1. Load Credentials
    store = CredentialStore.from_env()
    creds = store.load()
    
    aws_access = creds.get("AWS_ACCESS_KEY_ID")
    aws_secret = creds.get("AWS_SECRET_ACCESS_KEY")
    aws_region = creds.get("AWS_REGION", "us-east-1")
    ds_key = creds.get("DEEPSEEK_API_KEY")
    
    if not aws_access or not ds_key:
        print("ERROR: Please ensure AWS_ACCESS_KEY_ID and DEEPSEEK_API_KEY are saved in your .env file.")
        print(f"(Currently loaded from: {store.path})")
        return

    # Put credentials in env for OpenAI client if needed, or pass explicitly
    
    # 2. Test AWSConnector (Prash capabilities)
    print("\n[1/4] Initializing AWS Connector and discovering instances...")
    aws_creds = {
        "AWS_ACCESS_KEY_ID": aws_access,
        "AWS_SECRET_ACCESS_KEY": aws_secret,
        "AWS_REGION": aws_region,
    }
    connector = AWSConnector(aws_creds)
    
    if not connector.authenticate():
        print("ERROR: AWS Authentication failed. Check your keys.")
        return
    print("AWS Authentication successful.")
    
    # Get instance ID (either from env or auto-discover)
    instance_id = creds.get("EC2_INSTANCE_ID")
    if not instance_id:
        print("No EC2_INSTANCE_ID in .env. Attempting to discover a running instance...")
        session = boto3.Session(
            aws_access_key_id=aws_creds["AWS_ACCESS_KEY_ID"],
            aws_secret_access_key=aws_creds["AWS_SECRET_ACCESS_KEY"],
            region_name=aws_creds["AWS_REGION"]
        )
        ec2 = session.client("ec2")
        resp = ec2.describe_instances(Filters=[{"Name": "instance-state-name", "Values": ["running"]}])
        instances = [i["InstanceId"] for r in resp.get("Reservations", []) for i in r.get("Instances", [])]
        if not instances:
            print("ERROR: No running EC2 instances found to test against.")
            return
        instance_id = instances[0]
    
    print(f"Target EC2 Instance: {instance_id}")
    
    # Test connector locate, poll, and logs
    print(f"Locating instance: {connector.locate(instance_id)}")
    state = connector.poll_state(instance_id)
    print(f"Current State: {state.state.name}")
    
    logs = connector.fetch_logs(instance_id)
    log_preview = "\n".join(logs[-5:]) if logs else "<no logs>"
    print(f"Fetched {len(logs)} lines of console output. Last 5 lines:\n{log_preview}")

    # 3. Query DeepSeek
    print("\n[2/4] Querying DeepSeek for a verification command...")
    client = AsyncOpenAI(api_key=ds_key, base_url="https://api.deepseek.com/v1")
    prompt = (
        f"We have an EC2 instance {instance_id} in {state.state.name} state. "
        "Please provide a single, extremely lightweight bash command to run on it via SSM just to verify execution "
        "(e.g. echo 'Hello from DeepSeek' && uptime). "
        "Output ONLY the command. Do not wrap in markdown or backticks."
    )
    
    try:
        response = await client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=50
        )
        command = response.choices[0].message.content.strip().strip('`').strip()
        print(f"DeepSeek suggested command: {command}")
    except Exception as e:
        print(f"\n[!] DeepSeek API error: {e}")
        print("[!] Falling back to Gemini 3.5 Flash Lite...")
        gemini_key = os.getenv("GEMINI_API_KEY")
        if not gemini_key:
            print("[!] GEMINI_API_KEY not found in .env, falling back to hardcoded command.")
            command = "echo 'Hello from fallback!' && uptime"
        else:
            gemini_client = AsyncOpenAI(api_key=gemini_key, base_url="https://generativelanguage.googleapis.com/v1beta/openai/")
            try:
                response = await gemini_client.chat.completions.create(
                    model="gemini-3.5-flash-lite",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=50
                )
                command = response.choices[0].message.content.strip().strip('`').strip()
                print(f"Gemini (3.5) suggested command: {command}")
            except Exception as e2:
                print(f"\n[!] Gemini 3.5 API error: {e2}")
                print("[!] Falling back to Gemini 3.1 Flash Lite...")
                try:
                    response = await gemini_client.chat.completions.create(
                        model="gemini-3.1-flash-lite",
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=50
                    )
                    command = response.choices[0].message.content.strip().strip('`').strip()
                    print(f"Gemini (3.1) suggested command: {command}")
                except Exception as e3:
                    print(f"\n[!] Gemini 3.1 API error: {e3}")
                    print("[!] Falling back to a hardcoded command.")
                    command = "echo 'Hello from fallback!' && uptime"

    # 4. Execute via Connector
    print(f"\n[3/4] Executing command via AWS Connector (SSM with SSH fallback)...")
    from prash.connectors.aws import SSMFailedNeedsSSH
    
    try:
        res = connector.execute_command(instance_id, command)
        if "error" in res:
             print(f"Execution Error: {res['error']}")
        else:
            print("--- Execution Output ---")
            print(f"Source: {res.get('source')}, Status: {res.get('status')}")
            print(res.get("stdout", "").strip())
            if res.get("stderr", "").strip():
                 print(f"STDERR: {res['stderr'].strip()}")
            print("------------------------")
    except SSMFailedNeedsSSH as e:
        print(f"\n[!] {e}")
        if not pem_path:
            print("ERROR: No PEM path given. Pass --pem or set PRASH_PEM_PATH to use the SSH fallback.")
            return
        if not os.path.exists(pem_path):
            print(f"ERROR: PEM file not found at {pem_path}")
            return
        print(f"\nRetrying execution with SSH fallback (pem: {pem_path})...")
        res = connector.execute_command(instance_id, command, pem_path=pem_path)
        if "error" in res:
            print(f"ERROR: {res['error']}")
        else:
            print("--- SSH Execution Output ---")
            print(f"Source: {res.get('source')}, Status: {res.get('status')}")
            print(res.get("stdout", "").strip())
            if res.get("stderr", "").strip():
                print(f"STDERR: {res['stderr'].strip()}")
            print("----------------------------")
    except Exception as e:
        print(f"Unexpected error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
