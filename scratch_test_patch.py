import subprocess

# Test 1: standard -p with raw string
cmd1 = ["kubectl", "-n", "lear-demo", "patch", "configmap", "checkout-api-config", "--type", "merge", "-p", r'{"data":{"DATABASE_HOST":"postgres"}}']
res1 = subprocess.run(cmd1, capture_output=True, text=True)
print("TEST 1 - returncode:", res1.returncode)
print("STDOUT:", res1.stdout)
print("STDERR:", res1.stderr)

# Test 2: passing json via stdin or powershell script
# Notice we already have reset-configmap-break.ps1 in scripts/demo/scripts/reset-configmap-break.ps1!
cmd2 = ["powershell", "-ExecutionPolicy", "Bypass", "-File", "scripts/demo/scripts/reset-configmap-break.ps1"]
res2 = subprocess.run(cmd2, capture_output=True, text=True)
print("TEST 2 (PowerShell reset script) - returncode:", res2.returncode)
print("STDOUT:", res2.stdout)
print("STDERR:", res2.stderr)
