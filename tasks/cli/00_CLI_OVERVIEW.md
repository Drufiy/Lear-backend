# CLI Architecture — Overview

**Owner:** Aryan  
**Status:** Built  
**Priority:** Tier 1  

---

## Architecture

```
prash (entry point)
  ├── fix <target>           → Diagnose + recommend + dispatch action
  ├── investigate <target>    → Read-only diagnosis
  ├── run <action> <target>   → Direct action execution
  ├── watch                   → Start background watcher
  ├── logs <pod>              → Stream pod logs
  ├── audit                   → View audit trail
  ├── config                  → View/edit configuration
  ├── circuit status/reset    → Circuit breaker management
  ├── actions                 → List registered actions
  ├── notify <message>        → Send team notification
  ├── setup                   → Configuration wizard
  └── repl                    → Interactive session (Stage 1 + 2)
```

### Key Files
- `prash/cli.py` (65K) — All subcommands and argument parsing
- `prash/repl.py` (13K) — Interactive REPL session
- `prash/intent.py` (35K) — Free-text intent parsing
- `prash/tui.py` (28K) — Rich terminal UI
- `prash/ui.py` (4K) — UI utilities
- `prash/fix.py` (29K) — Diagnosis rendering and fix orchestration
- `prash/setup.py` (5K) — Configuration wizard

---

## Submodule Task Files

1. [`01_CLI_COMMANDS.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/cli/01_CLI_COMMANDS.md) — All CLI subcommands
2. [`02_REPL_AND_INTENT.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/cli/02_REPL_AND_INTENT.md) — Interactive session
3. [`03_TUI_AND_UI.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/cli/03_TUI_AND_UI.md) — Rich terminal interface
