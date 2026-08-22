"""Interactive setup wizard for Prash."""

from pathlib import Path

from rich.console import Console
from rich.prompt import Prompt

GROUPS = {
    "AI Models (Diagnosis Brain)": [
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_MODEL",
        "KIMI_API_KEY",
        "KIMI_MODEL",
        "GEMINI_API_KEY",
    ],
    "GitHub Integration (CI logs, opening fix PRs)": [
        "GITHUB_TOKEN",
    ],
    "Kubernetes Setup": [
        "KUBECONFIG",
        "KUBE_CONTEXT",
        "KUBE_NAMESPACE",
    ],
    "Google Cloud (Cloud Run & Compute Engine)": [
        "GCP_PROJECT_ID",
        "GCP_REGION",
        "GOOGLE_APPLICATION_CREDENTIALS",
    ],
    "Microsoft Azure (VMs)": [
        "AZURE_SUBSCRIPTION_ID",
        "AZURE_TENANT_ID",
        "AZURE_CLIENT_ID",
        "AZURE_CLIENT_SECRET",
        "AZURE_LOCATION",
    ],
    "AWS Configuration": [
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_REGION",
    ],
    "Vercel": [
        "VERCEL_TOKEN",
    ],
    "Team Notifications": [
        "SLACK_WEBHOOK_URL",
        "DISCORD_WEBHOOK_URL",
        "EMAIL_SMTP_HOST",
        "EMAIL_SMTP_PORT",
        "EMAIL_USER",
        "EMAIL_PASSWORD",
        "EMAIL_FROM",
        "EMAIL_TO",
        "TWILIO_ACCOUNT_SID",
        "TWILIO_AUTH_TOKEN",
        "WHATSAPP_FROM_NUMBER",
        "WHATSAPP_TO_NUMBERS",
    ],
    "Prash Settings & Watcher": [
        "PRASH_PERMISSION_MODE",
        "PRASH_ENVIRONMENT",
        "PRASH_AUDIT_LOG_PATH",
        "PRASH_CIRCUIT_MAX_ACTIONS",
        "PRASH_CIRCUIT_WINDOW_SECONDS",
        "PRASH_CIRCUIT_STATE_PATH",
        "PRASH_WATCH_INTERVAL_SECONDS",
    ],
}

def _is_secret(key: str) -> bool:
    key_lower = key.lower()
    return "key" in key_lower or "token" in key_lower or "secret" in key_lower or "credentials" in key_lower

def _mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "****"
    return value[:4] + "****" + value[-4:]

def run_setup_wizard(env_path: str = ".env", template_path: str = ".env.example") -> None:
    """Run the interactive configuration wizard."""
    console = Console()
    console.print("[bold green]Welcome to the Prash Configuration Wizard![/bold green]")
    console.print(f"This will help you set up your local `{env_path}` file.")
    console.print("Press [bold]Enter[/bold] to skip a field or keep its existing value.\n")

    env_file = Path(env_path)
    template_file = Path(template_path)

    existing_values = {}
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                parts = line.split("=", 1)
                if len(parts) == 2:
                    existing_values[parts[0].strip()] = parts[1].strip()

    new_values = {}
    
    for group_name, keys in GROUPS.items():
        console.print(f"[bold cyan]--- {group_name} ---[/bold cyan]")
        for key in keys:
            existing = existing_values.get(key, "")
            is_sec = _is_secret(key)
            
            # Use masked version for display if it's a secret
            default_display = _mask_secret(existing) if is_sec and existing else existing
            
            prompt_str = f"{key}"
            if default_display:
                prompt_str += f" [dim]({default_display})[/dim]"
            
            # password=True masks what the user types for secrets (the PR's
            # intent) — otherwise a fresh secret value is echoed in plaintext
            # on screen, leaking it to anyone shoulder-surfing or recording
            # the terminal session.
            val = Prompt.ask(prompt_str, default=existing, show_default=False, password=is_sec)
            new_values[key] = val
        console.print()

    # Reconstruct the .env file
    lines = []
    keys_written = set()
    
    if template_file.exists():
        for line in template_file.read_text(encoding="utf-8").splitlines():
            line_stripped = line.strip()
            if not line_stripped or line_stripped.startswith("#"):
                lines.append(line)
            else:
                parts = line_stripped.split("=", 1)
                if len(parts) == 2:
                    key = parts[0].strip()
                    # Only write keys that are in the template
                    val = new_values.get(key, existing_values.get(key, ""))
                    lines.append(f"{key}={val}")
                    keys_written.add(key)
                else:
                    lines.append(line)
    else:
        # Fallback if no template exists
        for key, val in new_values.items():
            lines.append(f"{key}={val}")
            keys_written.add(key)
            
    # Carry over any extra keys that existed in the original .env but aren't in the GROUPS/template
    extra_keys = set(existing_values.keys()) - keys_written - set(new_values.keys())
    if extra_keys:
        lines.append("")
        lines.append("# --- Custom Existing Keys ---")
        for key in extra_keys:
            lines.append(f"{key}={existing_values[key]}")

    # Ensure parent directory exists (just in case)
    env_file.parent.mkdir(parents=True, exist_ok=True)
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    
    console.print(f"[bold green]Configuration successfully saved to {env_path}![/bold green]")
