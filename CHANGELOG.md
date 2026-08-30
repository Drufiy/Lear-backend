# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
- **Terraform Integration (Tracks B, C, D, E)**: Added comprehensive Terraform support across the entire architecture.
  - *Connectors*: Added `TerraformConnector` to monitor `.tfstate` and execute drift detection locally, with stubs for future Terraform Cloud integrations.
  - *Actions*: Added `terraform_init` (SAFE tier) and `terraform_apply` (dynamic risk tier defaulting to APPROVAL) to resolve config drift and setup failures.
  - *Brain*: Taught the `SYSTEM_PROMPT` to identify `infra_as_code` category issues, interpret Terraform drift, and recommend appropriate fixes.
  - *Watcher*: Extended `prash watch --provider terraform` to periodically poll local Terraform state. During testing, it gracefully handled missing `.tfstate` files with safe degradation messages without crashing the main watcher loop.
- **Slack/Discord team notifications (Sprint 2 Tier 2)**: New `prash/notifications.py` with `SlackNotifier`/`DiscordNotifier` incoming-webhook channels (stdlib-only urllib). `prash watch` now pushes every new-problem ping to any configured channel in addition to the desktop toast, and a new **`prash notify <message>`** command sends a message to every configured channel (`SLACK_WEBHOOK_URL` / `DISCORD_WEBHOOK_URL` in `.env`).
- **Email/WhatsApp team notifications (Sprint 2 Tier 3)**: Added `EmailNotifier` (SMTP with basic HTML formatting) and `WhatsAppNotifier` (via Twilio API) to `prash/notifications.py`. They integrate directly into `team_notifiers` so `prash watch` and `prash notify` automatically utilize them when configured. Supports multiple recipients via CSV lists.
- **`prash setup` v0.1 (Configuration Wizard)**: Introduced an interactive terminal UI for setting up Prash. It prompts for all relevant `.env` API keys and configurations grouped by category, masks secrets to prevent terminal history leaks, supports skipping fields to keep existing defaults, and writes the output back while preserving `.env.example` comments.
- **AWS execute-aws Action**: Wired the AWS EC2 `execute_command` logic into the dispatcher as a formal action (`execute-aws`). This action runs under the APPROVAL Risk Tier, gracefully prompts for missing commands, and interactively handles the SSH fallback (`SSMFailedNeedsSSH`) by requesting a `.pem` file from the user.
- **AWS EC2 Connector (Execution & SSH Fallback)**: Promoted the AWS EC2 connector to support `execute_command`. It executes via AWS Systems Manager (SSM) by default and falls back to a robust SSH execution method if SSM fails (e.g. missing IAM roles). The SSH fallback emits a clean `SSMFailedNeedsSSH` exception designed for REPL integration.
- **Verification Script Gemini Fallback**: Live infra testing script now falls back to Gemini 3.5 Flash Lite and 3.1 Flash Lite if the primary diagnosis brain APIs fail.
- **agent_guidelines.md**: Added a guidelines file to establish conventions for AI agents working on this project.
- **Azure & GCP Connectors (Execution & SSH Fallback)**: Added `AzureConnector` and `GCPConnector` mirroring the AWS EC2 execution pattern. They support read operations (`instance_status`, `logs`) and use official SDKs with CLI fallbacks (`az`, `gcloud`), ultimately falling back to native SSH execution with `.pem` files if execution APIs fail.
- **Azure/GCP execute actions**: Wired `execute-azure` and `execute-gcp` into the dispatcher as formal actions under the APPROVAL Risk Tier, matching the interactive fallback workflow of AWS.
- **Wizard enhancements**: `prash setup` now prompts for Azure VM configurations (`AZURE_SUBSCRIPTION_ID`, `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `AZURE_LOCATION`) and Google Cloud Compute Engine keys (`GCP_PROJECT_ID`, `GCP_REGION`, `GOOGLE_APPLICATION_CREDENTIALS`).
### Fixed
- **AWS Connector — registered and hardened**: `AWSConnector` is now registered in `prash/cli.py`'s `PROVIDERS`, making `prash investigate <resource> --provider aws` usable. `authenticate()` now caches its result per connector instance instead of re-hitting STS on every method call. `read_capabilities` corrected from copy-pasted Kubernetes names (`pod_status`) to `instance_status`/`logs`. `execute_command` remains unwired to any dispatcher action — read-only only, per spec.

### Security
- **Hardcoded Secret Removal**: Removed hardcoded Gemini API keys from `test_live_infra.py` to fix GitHub push protection (GH013) violations. Secrets are now securely loaded from `.env` via `os.getenv`, and `.env.example` has been updated with the corresponding templates.

### Changed
- **`test_live_infra.py` relocated**: Moved from the repo root to `scripts/verify_aws_live.py`. It's a manual live-verification script, not a pytest test file (no `test_` functions), and its old name/location was misleading.
