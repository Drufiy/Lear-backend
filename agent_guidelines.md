# Lear — Agent Guidelines

This document outlines the coding traditions, architectural guidelines, and workflows to be followed by any AI agents (like Claude Code, Antigravity, etc.) working on this repository.

## 1. Project Philosophy
**Lear is a local-first AI DevOps agent.**
- **Credentials:** Credentials NEVER leave the user's machine. They are stored locally (e.g. in `.env`) and passed into connectors at runtime. No cloud-hosted backend stores these keys.
- **Cross-Platform:** This is a CLI tool that runs on Windows, macOS, and Linux. Path handling (`pathlib`), shell quoting, and line endings must be OS-agnostic. 

## 2. CLI-First Architecture
Prash is built as a **CLI-based app**. The UI revolves around text interfaces and interactive TUIs (via `rich` and `textual`).
- **Commands:** Every new feature should map to a clear, actionable CLI command or subcommand.
- **Interface:** Avoid assumptions about a GUI. The primary user interaction happens in the terminal (e.g., `prash fix`, `prash watch`).

## 3. Architecture Flow
The repository is split into distinct tracks. Respect these boundaries and don't create tight coupling where none should exist:
- **Track A (CLI & Permissions):** Owns the interface, the action registry, permission engine, circuit breaker, and audit log.
- **Track B (Connectors):** Owns the read-only view into infrastructure. Connectors MUST implement the `Connector` base pattern (`authenticate -> locate -> fetch_logs -> poll_state`). They never hold credentials themselves; they receive them per call.
- **Track C (Write Actions):** Owns operations that mutate infrastructure (e.g., restarting pods). Must be verifiable and respect the permission model.
- **Track D (Brain):** Owns diagnosis. It ingests state from connectors and outputs a `Diagnosis` (with an optional `options` list for ambiguity). It has zero ties to a web stack.
- **Track E (Watcher):** Background process polling connectors to detect anomalies and alert the user.

## 4. Documentation & Logging (Zero Exception Rule)
If it isn't documented, it didn't happen.
- **PRASH_V2.md:** This is the single source of truth.
  - New bugs, ideas, or completed milestones MUST be logged in `§10 running log`.
  - Architectural or cross-track decisions MUST be logged in `§9 decision log`.
- **CHANGELOG.md:** Any new feature (like adding a new connector or CLI command) MUST be documented in `CHANGELOG.md` as a distinct entry.

## 5. Testing
- Every connector and action needs tests.
- Since we can't always hit live infrastructure in CI, use robust mocking (e.g., `botocore.stub.Stubber` for AWS).
- UI flows and permission gates must be tested, especially edge cases like missing credentials or rate limits.
