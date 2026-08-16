# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
- **AWS EC2 Connector (Execution & SSH Fallback)**: Promoted the AWS EC2 connector to support `execute_command`. It executes via AWS Systems Manager (SSM) by default and falls back to a robust SSH execution method if SSM fails (e.g. missing IAM roles). The SSH fallback emits a clean `SSMFailedNeedsSSH` exception designed for REPL integration.
- **Verification Script Gemini Fallback**: Live infra testing script now falls back to Gemini 3.5 Flash Lite and 3.1 Flash Lite if the primary diagnosis brain APIs fail.
- **agent_guidelines.md**: Added a guidelines file to establish conventions for AI agents working on this project.

### Security
- **Hardcoded Secret Removal**: Removed hardcoded Gemini API keys from `test_live_infra.py` to fix GitHub push protection (GH013) violations. Secrets are now securely loaded from `.env` via `os.getenv`, and `.env.example` has been updated with the corresponding templates.
