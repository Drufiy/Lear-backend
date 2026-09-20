# CLI Commands — `cli.py`

**Owner:** Aryan  
**Status:** Built  
**Priority:** Tier 1  

---

## Tasks

### T1. `prash fix` — core diagnosis + fix pipeline
- [ ] K8s path: `prash fix namespace/pod` → gather → diagnose → recommend → dispatch
- [ ] CI path: `prash fix owner/repo --ci --run-id N` → multi-diagnosis → combined PR
- [ ] AWS path: `prash fix instance-id --provider aws` → `diagnose_aws_instance`
- [ ] `--repo owner/name` for manifest fix path
- [ ] `--dry-run` produces plan without executing
- [ ] `--mode` respects permission system
- [ ] `--noninteractive` + options → report options, take no action
- [ ] Options rendering: `render_options()` shows ranked menu with rationale

### T2. `prash investigate` — read-only diagnosis
- [ ] Same as `fix` but never dispatches an action
- [ ] Shows diagnosis, recommended action, but does not execute

### T3. `prash run <action> <target>` — direct action execution
- [ ] Routes through dispatcher with permission/circuit-breaker/audit
- [ ] Supports `--replicas`, `--set KEY=VALUE`, `--exec-command`, `--container`
- [ ] `--grant` overrides permission prompt (for scripting)

### T4. `prash watch` — background watcher
- [ ] Starts poll loop for configured connectors
- [ ] Team notifications (Slack/Discord/Email/WhatsApp) on new problems
- [ ] Desktop notification via `plyer`
- [ ] Graceful shutdown on SIGINT

### T5. `prash logs namespace/pod` — log streaming
- [ ] Non-follow: decoded text (not `b'...'` — regression test exists)
- [ ] `--follow`: live stream, clean SIGINT handling
- [ ] No raw traceback on interrupt

### T6. `prash setup` — configuration wizard
- [ ] Parses `.env.example` for field definitions
- [ ] Groups by category (AI Models, Cloud, CI, Monitoring, etc.)
- [ ] Masks secrets during input
- [ ] Preserves existing values on skip
- [ ] Retains `.env.example` comments when saving

### T7. `prash audit/config/circuit/actions/notify` — utility commands
- [ ] `audit` — view audit trail
- [ ] `config` — view/edit configuration
- [ ] `circuit status/reset` — circuit breaker management
- [ ] `actions` — list registered actions with risk tiers
- [ ] `notify <message>` — send to configured team channels

### T8. Cross-platform compatibility
- [ ] All commands work on Windows (PowerShell) and macOS
- [ ] `pathlib` for all paths, no Unix-only shell commands
- [ ] Signal handling differs between OSes (SIGINT handling)
- [ ] Line endings: `\r\n` on Windows, `\n` on macOS/Linux

---

## Tests

| Test | File | What it verifies |
|---|---|---|
| `test_fix_k8s_pipeline` | `tests/test_fix.py` | Full K8s fix path |
| `test_fix_ci_pipeline` | `tests/test_fix.py` | Full CI fix path |
| `test_fix_options_render` | `tests/test_fix.py` | Options menu displayed |
| `test_fix_noninteractive` | `tests/test_fix.py` | No action taken with options |
| `test_run_with_permission` | `tests/test_cli.py` | Permission system applied |
| `test_logs_decoded` | `tests/test_cli.py` | Not `b'...'` format |
| `test_setup_wizard` | `tests/test_cli.py` | Wizard parses .env.example |
| `test_cross_platform` | CI matrix | Linux + Windows + macOS |

---

## Acceptance Criteria

- [ ] All commands functional on both platforms
- [ ] `prash fix` end-to-end pipeline works for K8s, CI, and AWS
- [ ] Permission system, circuit breaker, and audit trail active for every action
- [ ] All 18K+ of CLI tests pass
