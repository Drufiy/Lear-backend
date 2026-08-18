# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
- **Slack/Discord team notifications (Sprint 2 Tier 2)**: New `prash/notifications.py` with `SlackNotifier`/`DiscordNotifier` incoming-webhook channels (stdlib-only urllib). `prash watch` now pushes every new-problem ping to any configured channel in addition to the desktop toast, and a new **`prash notify <message>`** command sends a message to every configured channel (`SLACK_WEBHOOK_URL` / `DISCORD_WEBHOOK_URL` in `.env`).
- **`prash setup` v0.1 (Configuration Wizard)**: Introduced an interactive terminal UI for setting up Prash. It prompts for all relevant `.env` API keys and configurations grouped by category, masks secrets to prevent terminal history leaks, supports skipping fields to keep existing defaults, and writes the output back while preserving `.env.example` comments.
- **AWS execute-aws Action**: Wired the AWS EC2 `execute_command` logic into the dispatcher as a formal action (`execute-aws`). This action runs under the APPROVAL Risk Tier, gracefully prompts for missing commands, and interactively handles the SSH fallback (`SSMFailedNeedsSSH`) by requesting a `.pem` file from the user.
- **AWS EC2 Connector (Execution & SSH Fallback)**: Promoted the AWS EC2 connector to support `execute_command`. It executes via AWS Systems Manager (SSM) by default and falls back to a robust SSH execution method if SSM fails (e.g. missing IAM roles). The SSH fallback emits a clean `SSMFailedNeedsSSH` exception designed for REPL integration.
- **Verification Script Gemini Fallback**: Live infra testing script now falls back to Gemini 3.5 Flash Lite and 3.1 Flash Lite if the primary diagnosis brain APIs fail.
- **agent_guidelines.md**: Added a guidelines file to establish conventions for AI agents working on this project.

### Fixed
- **AWS Connector — registered and hardened**: `AWSConnector` is now registered in `prash/cli.py`'s `PROVIDERS`, making `prash investigate <resource> --provider aws` usable. `authenticate()` now caches its result per connector instance instead of re-hitting STS on every method call. `read_capabilities` corrected from copy-pasted Kubernetes names (`pod_status`) to `instance_status`/`logs`. `execute_command` remains unwired to any dispatcher action — read-only only, per spec.

### Security
- **Hardcoded Secret Removal**: Removed hardcoded Gemini API keys from `test_live_infra.py` to fix GitHub push protection (GH013) violations. Secrets are now securely loaded from `.env` via `os.getenv`, and `.env.example` has been updated with the corresponding templates.

### Changed
- **`test_live_infra.py` relocated**: Moved from the repo root to `scripts/verify_aws_live.py`. It's a manual live-verification script, not a pytest test file (no `test_` functions), and its old name/location was misleading.
